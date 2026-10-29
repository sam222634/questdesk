from typing import Optional
from fastapi import APIRouter, Depends, Query
from app.repositories import AbstractTicketRepository, get_ticket_repository
from app.schemas import (
    EmailWebhookPayload,
    TicketCreate,
    TicketStatusUpdate,
    WorkLogCreate,
)

router = APIRouter(prefix="/api/v1/tickets", tags=["Tickets"])


@router.get("")
def list_tickets(
    status: Optional[str] = Query(default=None, description="Filtrar por estado (ej. NEW, IN_PROGRESS, RESOLVED)"),
    queue: Optional[str] = Query(default=None, description="Filtrar por slug de cola (ej. dev, infra)"),
    include_closed: bool = Query(default=False, description="Incluir tickets cerrados/resueltos"),
    repo: AbstractTicketRepository = Depends(get_ticket_repository),
):
    """Lista los tickets con sus métricas de tiempo y enlace a bitácora."""
    return repo.list_tickets(status=status, queue=queue, include_closed=include_closed)


@router.post("", status_code=201)
def create_ticket(
    payload: TicketCreate,
    repo: AbstractTicketRepository = Depends(get_ticket_repository),
):
    """Crea un nuevo ticket dentro de una transacción Todo-o-Nada."""
    return repo.create_ticket(payload)


@router.post("/email-webhook", status_code=201)
def create_ticket_from_email_webhook(
    payload: EmailWebhookPayload,
    repo: AbstractTicketRepository = Depends(get_ticket_repository),
):
    """
    Endpoint Zero-Credentials para filtros locales de Thunderbird o demonios de correo.
    Transforma el payload de correo y delega la transacción al Repositorio.
    """
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
    return repo.create_ticket(ticket_in)


@router.get("/{ticket_code}")
def get_ticket_detail(
    ticket_code: str,
    repo: AbstractTicketRepository = Depends(get_ticket_repository),
):
    """Devuelve toda la información normalizada de un ticket."""
    return repo.get_ticket_detail(ticket_code)


@router.patch("/{ticket_code}/status")
def update_ticket_status(
    ticket_code: str,
    payload: TicketStatusUpdate,
    repo: AbstractTicketRepository = Depends(get_ticket_repository),
):
    """Actualiza el estado del ticket de forma transaccional y gestiona sesiones de trabajo."""
    return repo.update_status(ticket_code, payload)


@router.post("/{ticket_code}/work-logs", status_code=201)
def add_work_log(
    ticket_code: str,
    payload: WorkLogCreate,
    repo: AbstractTicketRepository = Depends(get_ticket_repository),
):
    """Registra una sesión de trabajo en el ticket."""
    return repo.add_work_log(ticket_code, payload)
