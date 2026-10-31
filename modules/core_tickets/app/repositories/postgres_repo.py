from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import json
import psycopg
from app.database import get_db_connection
from app.markdown_gen import generate_bitacora_markdown
from app.repositories.base import (
    AbstractTicketRepository,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    RepositoryError,
    UnauthorizedError,
    ValidationError,
)
from app.schemas import (
    AuthenticatedUser,
    TicketAssignUpdate,
    TicketCreate,
    TicketStatusUpdate,
    WorkLogCreate,
)


def _translate_pg_error(exc: psycopg.Error, step: str) -> RepositoryError:
    """Convierte errores de PostgreSQL en errores controlados indicando el paso exacto que falló."""
    diag_msg = (exc.diag.message_primary if exc.diag and exc.diag.message_primary else str(exc)).strip()
    sqlstate = getattr(exc, "sqlstate", None)

    if sqlstate == "28000":  # invalid_authorization_specification
        return UnauthorizedError(message=diag_msg, step=step)
    if sqlstate == "42501":  # insufficient_privilege
        return ForbiddenError(message=diag_msg, step=step)
    if sqlstate == "23505":  # unique_violation
        return ConflictError(message=diag_msg, step=step)
    if sqlstate == "P0002":  # no_data_found
        return NotFoundError(message=diag_msg, step=step)
    if sqlstate in ("22023", "23514", "23503"):  # invalid_parameter_value / check / fk
        return ValidationError(message=diag_msg, step=step)
    return RepositoryError(message=diag_msg, step=step, status_code=400)


class PostgresTicketRepository(AbstractTicketRepository):
    """
    Implementación para PostgreSQL que invoca funciones pequeñas especializadas
    dentro de bloques transaccionales explícitos (with conn.transaction():).
    """

    def authenticate_by_key_hash(self, api_key_hash: str) -> AuthenticatedUser:
        current_step = "fn_authenticate_by_key_hash"
        try:
            with get_db_connection() as conn, conn.cursor() as cur:
                cur.execute("SELECT * FROM fn_authenticate_by_key_hash(%s)", (api_key_hash,))
                row = cur.fetchone()
                return AuthenticatedUser(**row)
        except psycopg.Error as exc:
            raise _translate_pg_error(exc, step=current_step) from exc

    def get_catalogs(self) -> Dict[str, List[Dict[str, Any]]]:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, slug, prefix, name, description, is_active FROM ticket_queues ORDER BY id")
            queues = cur.fetchall()

            cur.execute("SELECT id, name, is_closed, sort_order FROM ticket_statuses ORDER BY sort_order")
            statuses = cur.fetchall()

            cur.execute("SELECT id, name, weight FROM ticket_priorities ORDER BY weight")
            priorities = cur.fetchall()

            cur.execute(
                """
                SELECT u.user_uuid, u.username, u.display_name, COALESCE(uh.role, 'AGENT') AS role
                FROM users u
                LEFT JOIN user_hierarchy uh ON uh.user_id = u.id
                WHERE u.is_active = TRUE
                ORDER BY u.display_name
                """
            )
            users = cur.fetchall()

        return {"queues": queues, "statuses": statuses, "priorities": priorities, "users": users}

    def list_tickets(
        self,
        requester: AuthenticatedUser,
        status: Optional[str] = None,
        queue: Optional[str] = None,
        include_closed: bool = False,
    ) -> List[Dict[str, Any]]:
        conditions: List[str] = []
        params: List[Any] = []

        # Control de acceso por rol: si no es ADMIN, solo ve sus tickets o los de sus subordinados directos
        if requester.role.upper() != "ADMIN":
            conditions.append("(assigned_user_id = %s OR assignee_manager_id = %s)")
            params.extend([requester.user_id, requester.user_id])

        if status:
            conditions.append("UPPER(status_name) = UPPER(%s)")
            params.append(status)
        elif not include_closed:
            conditions.append("is_closed = FALSE")

        if queue:
            conditions.append("LOWER(queue_slug) = LOWER(%s)")
            params.append(queue)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"""
            SELECT *
            FROM v_tickets_summary
            {where_clause}
            ORDER BY priority_weight DESC, created_at DESC
        """
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()

    def get_ticket_detail(self, ticket_code: str, requester: AuthenticatedUser) -> Dict[str, Any]:
        current_step = "get_ticket_detail"
        try:
            with get_db_connection() as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM v_tickets_summary WHERE UPPER(ticket_code) = UPPER(%s)",
                    (ticket_code.strip(),),
                )
                ticket = cur.fetchone()
                if not ticket:
                    raise NotFoundError(f"El ticket '{ticket_code}' no fue encontrado.", step=current_step)

                # Verificar permiso de lectura (Propio, Subordinado o ADMIN)
                current_step = "fn_assert_ticket_access"
                cur.execute(
                    "SELECT fn_assert_ticket_access(%s, %s, %s)",
                    (ticket["assigned_user_id"], requester.user_id, requester.role),
                )

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
        except psycopg.Error as exc:
            raise _translate_pg_error(exc, step=current_step) from exc

    def create_ticket(self, payload: TicketCreate, requester: AuthenticatedUser) -> Dict[str, Any]:
        current_step = "init_transaction"
        try:
            with get_db_connection() as conn:
                with conn.transaction():
                    with conn.cursor() as cur:
                        # Paso 1: Resolver usuario asignado (por UUID opaco o el propio solicitante)
                        assigned_user_id = requester.user_id
                        assigned_display_name = requester.display_name
                        if payload.assignee_uuid:
                            current_step = "fn_get_user_by_uuid"
                            cur.execute("SELECT * FROM fn_get_user_by_uuid(%s)", (payload.assignee_uuid,))
                            target_user = cur.fetchone()
                            assigned_user_id = target_user["user_id"]
                            assigned_display_name = target_user["display_name"]

                        # Paso 2: Validar prioridad
                        current_step = "fn_get_priority"
                        cur.execute("SELECT * FROM fn_get_priority(%s)", (payload.priority_name,))
                        prio = cur.fetchone()

                        # Paso 3: Obtener estado inicial NEW
                        current_step = "fn_get_status"
                        cur.execute("SELECT * FROM fn_get_status('NEW')")
                        status = cur.fetchone()

                        # Paso 4: Reservar folio en la cola
                        current_step = "fn_reserve_queue_folio"
                        cur.execute("SELECT * FROM fn_reserve_queue_folio(%s)", (payload.queue_slug,))
                        queue = cur.fetchone()

                        ticket_code = queue["ticket_code"]
                        bitacora_uri = f"bitacoras/{ticket_code}.md"

                        # Paso 5: Insertar fila en tickets
                        current_step = "fn_insert_ticket"
                        cur.execute(
                            "SELECT * FROM fn_insert_ticket(%s, %s, %s, %s, %s, %s, %s, %s)",
                            (
                                ticket_code,
                                payload.title,
                                payload.description,
                                queue["queue_id"],
                                status["status_id"],
                                prio["priority_id"],
                                assigned_user_id,
                                payload.estimated_points,
                            ),
                        )
                        ticket = cur.fetchone()

                        # Paso 6: Insertar origen en ticket_sources
                        current_step = "fn_insert_source"
                        cur.execute(
                            "SELECT fn_insert_source(%s, %s, %s, %s, %s)",
                            (
                                ticket["id"],
                                payload.channel,
                                payload.sender_email,
                                payload.message_id,
                                json.dumps(payload.raw_headers) if payload.raw_headers else None,
                            ),
                        )

                        # Paso 7: Insertar vínculo de documento en ticket_documents
                        current_step = "fn_insert_document"
                        cur.execute(
                            "SELECT fn_insert_document(%s, 'MARKDOWN_BITACORA', %s, 'SYNCED')",
                            (ticket["id"], bitacora_uri),
                        )

                        # Paso 8: Insertar registro de auditoría en ticket_audit_log
                        current_step = "fn_insert_audit"
                        cur.execute(
                            "SELECT fn_insert_audit(%s, 'CREATED', NULL, %s, %s)",
                            (
                                ticket["id"],
                                json.dumps(
                                    {
                                        "status": status["status_name"],
                                        "priority": prio["priority_name"],
                                        "assigned_user_id": assigned_user_id,
                                        "channel": payload.channel.upper(),
                                    }
                                ),
                                requester.username,
                            ),
                        )

                        # Paso 9: Crear archivo físico .md (si falla en disco, revierte toda la transacción SQL)
                        current_step = "generate_bitacora_markdown"
                        generate_bitacora_markdown(
                            ticket_code=ticket_code,
                            title=payload.title,
                            description=payload.description,
                            queue_slug=queue["queue_slug"],
                            priority_name=prio["priority_name"],
                            estimated_points=payload.estimated_points,
                            channel=payload.channel.upper(),
                            sender_email=payload.sender_email,
                        )

                return {
                    **ticket,
                    "queue_slug": queue["queue_slug"],
                    "queue_name": queue["queue_name"],
                    "status_name": status["status_name"],
                    "priority_name": prio["priority_name"],
                    "assignee_display_name": assigned_display_name,
                    "bitacora_uri": bitacora_uri,
                }
        except psycopg.Error as exc:
            raise _translate_pg_error(exc, step=current_step) from exc
        except OSError as exc:
            raise RepositoryError(
                message=f"No se pudo escribir el archivo Markdown de bitácora: {exc}",
                step=current_step,
                status_code=500,
            ) from exc

    def update_status(
        self,
        ticket_code: str,
        payload: TicketStatusUpdate,
        requester: AuthenticatedUser,
    ) -> Dict[str, Any]:
        current_step = "init_transaction"
        try:
            with get_db_connection() as conn:
                with conn.transaction():
                    with conn.cursor() as cur:
                        # Paso 1: Bloquear fila del ticket (FOR UPDATE)
                        current_step = "fn_lock_ticket_by_code"
                        cur.execute("SELECT * FROM fn_lock_ticket_by_code(%s)", (ticket_code,))
                        locked = cur.fetchone()

                        # Paso 2: Verificar que el usuario tenga permiso sobre este ticket
                        current_step = "fn_assert_ticket_access"
                        cur.execute(
                            "SELECT fn_assert_ticket_access(%s, %s, %s)",
                            (locked["assigned_user_id"], requester.user_id, requester.role),
                        )

                        # Paso 3: Validar nuevo estado
                        current_step = "fn_get_status"
                        cur.execute("SELECT * FROM fn_get_status(%s)", (payload.status_name,))
                        new_status = cur.fetchone()

                        # Paso 4: Actualizar estado en tickets
                        current_step = "fn_set_ticket_status"
                        cur.execute(
                            "SELECT fn_set_ticket_status(%s, %s)",
                            (locked["ticket_id"], new_status["status_id"]),
                        )

                        # Paso 5: Sincronizar sesión de trabajo en ticket_work_logs registrando al usuario
                        current_step = "fn_sync_work_log_on_status"
                        cur.execute(
                            "SELECT fn_sync_work_log_on_status(%s, %s, %s, %s, %s)",
                            (
                                locked["ticket_id"],
                                requester.user_id,
                                new_status["status_name"],
                                new_status["is_closed"],
                                payload.notes,
                            ),
                        )

                        # Paso 6: Registrar en auditoría
                        current_step = "fn_insert_audit"
                        cur.execute(
                            "SELECT fn_insert_audit(%s, 'STATUS_CHANGED', %s, %s, %s)",
                            (
                                locked["ticket_id"],
                                json.dumps({"status": locked["current_status"]}),
                                json.dumps({"status": new_status["status_name"], "notes": payload.notes}),
                                requester.username,
                            ),
                        )

                return {
                    "ticket_code": locked["ticket_code"],
                    "previous_status": locked["current_status"],
                    "new_status": new_status["status_name"],
                }
        except psycopg.Error as exc:
            raise _translate_pg_error(exc, step=current_step) from exc

    def assign_ticket(
        self,
        ticket_code: str,
        payload: TicketAssignUpdate,
        requester: AuthenticatedUser,
    ) -> Dict[str, Any]:
        current_step = "init_transaction"
        try:
            with get_db_connection() as conn:
                with conn.transaction():
                    with conn.cursor() as cur:
                        # Paso 1: Bloquear ticket
                        current_step = "fn_lock_ticket_by_code"
                        cur.execute("SELECT * FROM fn_lock_ticket_by_code(%s)", (ticket_code,))
                        locked = cur.fetchone()

                        # Paso 2: Verificar que el usuario actual sea dueño del ticket, su jefe o ADMIN
                        current_step = "fn_assert_ticket_access"
                        cur.execute(
                            "SELECT fn_assert_ticket_access(%s, %s, %s)",
                            (locked["assigned_user_id"], requester.user_id, requester.role),
                        )

                        # Paso 3: Resolver destinatario por su UUID opaco
                        current_step = "fn_get_user_by_uuid"
                        cur.execute("SELECT * FROM fn_get_user_by_uuid(%s)", (payload.target_user_uuid,))
                        target_user = cur.fetchone()

                        # Paso 4: Delegar ticket
                        current_step = "fn_set_ticket_assignee"
                        cur.execute(
                            "SELECT fn_set_ticket_assignee(%s, %s)",
                            (locked["ticket_id"], target_user["user_id"]),
                        )

                        # Paso 5: Registrar delegación en auditoría
                        current_step = "fn_insert_audit"
                        cur.execute(
                            "SELECT fn_insert_audit(%s, 'ASSIGNED', %s, %s, %s)",
                            (
                                locked["ticket_id"],
                                json.dumps({"assigned_user_id": locked["assigned_user_id"]}),
                                json.dumps(
                                    {
                                        "assigned_user_id": target_user["user_id"],
                                        "assignee_username": target_user["username"],
                                        "notes": payload.notes,
                                    }
                                ),
                                requester.username,
                            ),
                        )

                return {
                    "ticket_code": locked["ticket_code"],
                    "delegated_by": requester.username,
                    "new_assignee_uuid": str(target_user["user_uuid"]),
                    "new_assignee_display_name": target_user["display_name"],
                }
        except psycopg.Error as exc:
            raise _translate_pg_error(exc, step=current_step) from exc

    def add_work_log(
        self,
        ticket_code: str,
        payload: WorkLogCreate,
        requester: AuthenticatedUser,
    ) -> Dict[str, Any]:
        current_step = "init_transaction"
        try:
            with get_db_connection() as conn:
                with conn.transaction():
                    with conn.cursor() as cur:
                        # Paso 1: Bloquear ticket
                        current_step = "fn_lock_ticket_by_code"
                        cur.execute("SELECT * FROM fn_lock_ticket_by_code(%s)", (ticket_code,))
                        locked = cur.fetchone()

                        # Paso 2: Verificar acceso al ticket
                        current_step = "fn_assert_ticket_access"
                        cur.execute(
                            "SELECT fn_assert_ticket_access(%s, %s, %s)",
                            (locked["assigned_user_id"], requester.user_id, requester.role),
                        )

                        # Paso 3: Insertar sesión de trabajo vinculada al usuario
                        current_step = "fn_insert_work_log"
                        started = payload.started_at or datetime.now(timezone.utc)
                        cur.execute(
                            "SELECT * FROM fn_insert_work_log(%s, %s, %s, %s, %s)",
                            (locked["ticket_id"], requester.user_id, started, payload.ended_at, payload.notes),
                        )
                        log_row = cur.fetchone()

                        # Paso 4: Registrar en auditoría
                        current_step = "fn_insert_audit"
                        cur.execute(
                            "SELECT fn_insert_audit(%s, 'TIME_LOGGED', NULL, %s, %s)",
                            (
                                locked["ticket_id"],
                                json.dumps(
                                    {
                                        "work_log_id": log_row["id"],
                                        "user_id": requester.user_id,
                                        "duration_minutes": log_row["duration_minutes"],
                                        "notes": payload.notes,
                                    }
                                ),
                                requester.username,
                            ),
                        )

                return log_row
        except psycopg.Error as exc:
            raise _translate_pg_error(exc, step=current_step) from exc


def get_ticket_repository() -> AbstractTicketRepository:
    return PostgresTicketRepository()
