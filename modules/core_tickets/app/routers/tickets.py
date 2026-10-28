from datetime import datetime, timezone
from typing import Optional
import json
from fastapi import APIRouter, HTTPException, Query
from app.database import get_db_cursor
from app.markdown_gen import generate_bitacora_markdown
from app.schemas import (
    EmailWebhookPayload,
    TicketCreate,
    TicketStatusUpdate,
    WorkLogCreate,
)

router = APIRouter(prefix="/api/v1/tickets", tags=["Tickets"])


def _create_ticket_record(cur, payload: TicketCreate) -> dict:
    # 1. Resolver cola y obtener prefijo + secuencia atómica
    cur.execute(
        """
        UPDATE ticket_queues
        SET next_seq = next_seq + 1
        WHERE slug = %s AND is_active = TRUE
        RETURNING id, slug, prefix, name, next_seq - 1 AS seq_num
        """,
        (payload.queue_slug.lower(),),
    )
    queue_row = cur.fetchone()
    if not queue_row:
        raise HTTPException(status_code=400, detail=f"La cola '{payload.queue_slug}' no existe o está inactiva.")

    # 2. Resolver prioridad
    cur.execute(
        "SELECT id, name, weight FROM ticket_priorities WHERE UPPER(name) = UPPER(%s)",
        (payload.priority_name,),
    )
    prio_row = cur.fetchone()
    if not prio_row:
        raise HTTPException(status_code=400, detail=f"La prioridad '{payload.priority_name}' no es válida.")

    # 3. Resolver estado inicial (NEW)
    cur.execute("SELECT id, name FROM ticket_statuses WHERE name = 'NEW'")
    status_row = cur.fetchone()

    ticket_code = f"{queue_row['prefix']}-{queue_row['seq_num']:04d}"

    # 4. Insertar ticket base
    cur.execute(
        """
        INSERT INTO tickets (ticket_code, title, description, queue_id, status_id, priority_id, estimated_points)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id, ticket_code, title, description, estimated_points, created_at, updated_at
        """,
        (
            ticket_code,
            payload.title.strip(),
            payload.description.strip(),
            queue_row["id"],
            status_row["id"],
            prio_row["id"],
            payload.estimated_points,
        ),
    )
    ticket = cur.fetchone()

    # 5. Registrar origen en ticket_sources
    cur.execute(
        """
        INSERT INTO ticket_sources (ticket_id, channel, sender_email, message_id, raw_headers)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            ticket["id"],
            payload.channel.upper(),
            payload.sender_email,
            payload.message_id,
            json.dumps(payload.raw_headers) if payload.raw_headers else None,
        ),
    )

    # 6. Generar archivo Markdown de bitácora y vincular en ticket_documents
    bitacora_uri = generate_bitacora_markdown(
        ticket_code=ticket_code,
        title=payload.title,
        description=payload.description,
        queue_slug=queue_row["slug"],
        priority_name=prio_row["name"],
        estimated_points=payload.estimated_points,
        channel=payload.channel.upper(),
        sender_email=payload.sender_email,
    )
    cur.execute(
        """
        INSERT INTO ticket_documents (ticket_id, doc_type, uri, sync_status)
        VALUES (%s, 'MARKDOWN_BITACORA', %s, 'SYNCED')
        """,
        (ticket["id"], bitacora_uri),
    )

    # 7. Registrar en auditoría
    cur.execute(
        """
        INSERT INTO ticket_audit_log (ticket_id, action, new_value, actor)
        VALUES (%s, 'CREATED', %s, %s)
        """,
        (
            ticket["id"],
            json.dumps({"status": "NEW", "priority": prio_row["name"], "channel": payload.channel}),
            payload.sender_email or payload.channel.lower(),
        ),
    )

    return {
        **ticket,
        "queue_slug": queue_row["slug"],
        "queue_name": queue_row["name"],
        "status_name": status_row["name"],
        "priority_name": prio_row["name"],
        "bitacora_uri": bitacora_uri,
    }


@router.get("")
def list_tickets(
    status: Optional[str] = Query(default=None, description="Filtrar por estado (ej. NEW, IN_PROGRESS, RESOLVED)"),
    queue: Optional[str] = Query(default=None, description="Filtrar por slug de cola (ej. dev, infra)"),
    include_closed: bool = Query(default=False, description="Incluir tickets cerrados/resueltos"),
):
    """Lista los tickets con sus métricas de tiempo y enlace a bitácora."""
    conditions = []
    params = []

    if status:
        conditions.append("UPPER(s.name) = UPPER(%s)")
        params.append(status)
    elif not include_closed:
        conditions.append("s.is_closed = FALSE")

    if queue:
        conditions.append("LOWER(q.slug) = LOWER(%s)")
        params.append(queue)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    query = f"""
        SELECT
            t.id,
            t.ticket_code,
            t.title,
            q.slug AS queue_slug,
            q.name AS queue_name,
            s.name AS status_name,
            s.is_closed,
            p.name AS priority_name,
            p.weight AS priority_weight,
            t.estimated_points,
            COALESCE((SELECT SUM(w.duration_minutes) FROM ticket_work_logs w WHERE w.ticket_id = t.id), 0) AS total_minutes,
            (SELECT d.uri FROM ticket_documents d WHERE d.ticket_id = t.id AND d.doc_type = 'MARKDOWN_BITACORA' LIMIT 1) AS bitacora_uri,
            t.created_at,
            t.updated_at
        FROM tickets t
        JOIN ticket_queues q ON q.id = t.queue_id
        JOIN ticket_statuses s ON s.id = t.status_id
        JOIN ticket_priorities p ON p.id = t.priority_id
        {where_clause}
        ORDER BY p.weight DESC, t.created_at DESC
    """
    with get_db_cursor() as cur:
        cur.execute(query, params)
        return cur.fetchall()


@router.post("", status_code=201)
def create_ticket(payload: TicketCreate):
    """Crea un nuevo ticket, genera su código único y su archivo Markdown de bitácora."""
    with get_db_cursor(commit=True) as cur:
        return _create_ticket_record(cur, payload)


@router.post("/email-webhook", status_code=201)
def create_ticket_from_email_webhook(payload: EmailWebhookPayload):
    """
    Endpoint Zero-Credentials para filtros locales de Thunderbird o demonios de correo.
    Evita duplicados verificando el Message-ID si está presente.
    """
    with get_db_cursor(commit=True) as cur:
        if payload.message_id:
            cur.execute(
                "SELECT ticket_id FROM ticket_sources WHERE message_id = %s",
                (payload.message_id,),
            )
            existing = cur.fetchone()
            if existing:
                raise HTTPException(status_code=409, detail="Este correo ya fue registrado previamente como ticket.")

        clean_title = payload.subject.replace("[TASK]", "").replace("[URGENTE]", "").strip() or payload.subject
        ticket_in = TicketCreate(
            title=clean_title[:255],
            description=payload.body,
            queue_slug=payload.queue_slug,
            priority_name=payload.priority_name,
            estimated_points=payload.estimated_points,
            channel="EMAIL",
            sender_email=payload.sender,
            message_id=payload.message_id,
            raw_headers=payload.headers,
        )
        return _create_ticket_record(cur, ticket_in)


@router.get("/{ticket_code}")
def get_ticket_detail(ticket_code: str):
    """Devuelve toda la información normalizada de un ticket (origen, bitácoras, tiempos y auditoría)."""
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT
                t.*,
                q.slug AS queue_slug,
                q.name AS queue_name,
                s.name AS status_name,
                s.is_closed,
                p.name AS priority_name,
                p.weight AS priority_weight
            FROM tickets t
            JOIN ticket_queues q ON q.id = t.queue_id
            JOIN ticket_statuses s ON s.id = t.status_id
            JOIN ticket_priorities p ON p.id = t.priority_id
            WHERE UPPER(t.ticket_code) = UPPER(%s)
            """,
            (ticket_code,),
        )
        ticket = cur.fetchone()
        if not ticket:
            raise HTTPException(status_code=404, detail=f"Ticket '{ticket_code}' no encontrado.")

        tid = ticket["id"]
        cur.execute("SELECT * FROM ticket_sources WHERE ticket_id = %s", (tid,))
        source = cur.fetchone()

        cur.execute("SELECT * FROM ticket_documents WHERE ticket_id = %s ORDER BY created_at", (tid,))
        documents = cur.fetchall()

        cur.execute("SELECT * FROM ticket_work_logs WHERE ticket_id = %s ORDER BY started_at DESC", (tid,))
        work_logs = cur.fetchall()

        cur.execute("SELECT * FROM ticket_audit_log WHERE ticket_id = %s ORDER BY created_at DESC", (tid,))
        audit_logs = cur.fetchall()

    return {
        **ticket,
        "source": source,
        "documents": documents,
        "work_logs": work_logs,
        "audit_logs": audit_logs,
    }


@router.patch("/{ticket_code}/status")
def update_ticket_status(ticket_code: str, payload: TicketStatusUpdate):
    """Actualiza el estado del ticket y registra la transición en auditoría."""
    with get_db_cursor(commit=True) as cur:
        cur.execute(
            """
            SELECT t.id, t.ticket_code, s.name AS current_status
            FROM tickets t
            JOIN ticket_statuses s ON s.id = t.status_id
            WHERE UPPER(t.ticket_code) = UPPER(%s)
            """,
            (ticket_code,),
        )
        ticket = cur.fetchone()
        if not ticket:
            raise HTTPException(status_code=404, detail=f"Ticket '{ticket_code}' no encontrado.")

        cur.execute(
            "SELECT id, name, is_closed FROM ticket_statuses WHERE UPPER(name) = UPPER(%s)",
            (payload.status_name,),
        )
        new_status = cur.fetchone()
        if not new_status:
            raise HTTPException(status_code=400, detail=f"Estado '{payload.status_name}' no válido.")

        cur.execute(
            "UPDATE tickets SET status_id = %s WHERE id = %s",
            (new_status["id"], ticket["id"]),
        )

        # Si pasa a IN_PROGRESS y no tiene sesión de trabajo abierta, abrimos una automáticamente
        if new_status["name"] == "IN_PROGRESS":
            cur.execute(
                "SELECT id FROM ticket_work_logs WHERE ticket_id = %s AND ended_at IS NULL",
                (ticket["id"],),
            )
            if not cur.fetchone():
                cur.execute(
                    "INSERT INTO ticket_work_logs (ticket_id, notes) VALUES (%s, %s)",
                    (ticket["id"], payload.notes or "Sesión iniciada al activar ticket"),
                )
        elif new_status["is_closed"] or new_status["name"] == "BLOCKED":
            # Cerramos cualquier sesión de trabajo que estuviera en curso
            cur.execute(
                """
                UPDATE ticket_work_logs
                SET ended_at = NOW()
                WHERE ticket_id = %s AND ended_at IS NULL
                """,
                (ticket["id"],),
            )

        cur.execute(
            """
            INSERT INTO ticket_audit_log (ticket_id, action, old_value, new_value, actor)
            VALUES (%s, 'STATUS_CHANGED', %s, %s, %s)
            """,
            (
                ticket["id"],
                json.dumps({"status": ticket["current_status"]}),
                json.dumps({"status": new_status["name"], "notes": payload.notes}),
                payload.actor,
            ),
        )

    return {
        "ticket_code": ticket["ticket_code"],
        "previous_status": ticket["current_status"],
        "new_status": new_status["name"],
    }


@router.post("/{ticket_code}/work-logs", status_code=201)
def add_work_log(ticket_code: str, payload: WorkLogCreate):
    """Registra una sesión de trabajo en el ticket."""
    with get_db_cursor(commit=True) as cur:
        cur.execute("SELECT id, ticket_code FROM tickets WHERE UPPER(ticket_code) = UPPER(%s)", (ticket_code,))
        ticket = cur.fetchone()
        if not ticket:
            raise HTTPException(status_code=404, detail=f"Ticket '{ticket_code}' no encontrado.")

        started = payload.started_at or datetime.now(timezone.utc)
        cur.execute(
            """
            INSERT INTO ticket_work_logs (ticket_id, started_at, ended_at, notes)
            VALUES (%s, %s, %s, %s)
            RETURNING id, started_at, ended_at, duration_minutes, notes
            """,
            (ticket["id"], started, payload.ended_at, payload.notes),
        )
        log_row = cur.fetchone()

    return log_row
