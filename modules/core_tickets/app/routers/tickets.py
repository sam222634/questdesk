from typing import Optional
from fastapi import APIRouter, Depends, Query
from app.repositories import AbstractTicketRepository, get_ticket_repository
from app.schemas import (
    AuthenticatedUser,
    EmailWebhookPayload,
    TicketAssignUpdate,
    TicketCreate,
    TicketStatusUpdate,
    WorkLogCreate,
)
from app.security import get_current_user

router = APIRouter(prefix="/api/v1/tickets", tags=["Tickets"])


@router.get("")
def list_tickets(
    status: Optional[str] = Query(default=None, description="Filtrar por estado (ej. NEW, IN_PROGRESS, RESOLVED)"),
    queue: Optional[str] = Query(default=None, description="Filtrar por slug de cola (ej. dev, infra)"),
    include_closed: bool = Query(default=False, description="Incluir tickets cerrados/resueltos"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: AbstractTicketRepository = Depends(get_ticket_repository),
):
    """
    Lista los tickets autorizados para el usuario autenticado (sin nombres de usuario en la URL).
    - ADMIN: ve todos los tickets.
    - SUPERVISOR / AGENT: solo ve sus propios tickets y los de sus subordinados directos.
    """
    return repo.list_tickets(
        requester=current_user,
        status=status,
        queue=queue,
        include_closed=include_closed,
    )


@router.post("", status_code=201)
def create_ticket(
    payload: TicketCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: AbstractTicketRepository = Depends(get_ticket_repository),
):
    """Crea un nuevo ticket dentro de una transacción Todo-o-Nada."""
    return repo.create_ticket(payload, requester=current_user)


@router.post("/email-webhook", status_code=201)
def create_ticket_from_email_webhook(
    payload: EmailWebhookPayload,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: AbstractTicketRepository = Depends(get_ticket_repository),
):
    """
    Endpoint Zero-Credentials para filtros locales de Thunderbird o demonios de correo.
    """
    clean_title = payload.subject.replace("[TASK]", "").replace("[URGENTE]", "").strip() or payload.subject
    ticket_in = TicketCreate(
        title=clean_title[:255],
        description=payload.body,
        queue_slug=payload.queue_slug,
        priority_name=payload.priority_name,
        estimated_points=payload.estimated_points,
        assignee_uuid=payload.assignee_uuid,
        channel="EMAIL",
        sender_email=payload.sender,
        message_id=payload.message_id,
        raw_headers=payload.headers,
    )
    return repo.create_ticket(ticket_in, requester=current_user)


@router.get("/{ticket_code}")
def get_ticket_detail(
    ticket_code: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: AbstractTicketRepository = Depends(get_ticket_repository),
):
    """Devuelve toda la información normalizada de un ticket tras verificar permisos de acceso."""
    return repo.get_ticket_detail(ticket_code, requester=current_user)


@router.patch("/{ticket_code}/status")
def update_ticket_status(
    ticket_code: str,
    payload: TicketStatusUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: AbstractTicketRepository = Depends(get_ticket_repository),
):
    """Actualiza el estado del ticket de forma transaccional tras verificar permisos."""
    return repo.update_status(ticket_code, payload, requester=current_user)


@router.patch("/{ticket_code}/assign")
def assign_ticket(
    ticket_code: str,
    payload: TicketAssignUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: AbstractTicketRepository = Depends(get_ticket_repository),
):
    """
    Delega o reasigna el ticket a un subordinado o compañero usando su UUID opaco en el cuerpo JSON.
    """
    return repo.assign_ticket(ticket_code, payload, requester=current_user)


@router.post("/{ticket_code}/work-logs", status_code=201)
def add_work_log(
    ticket_code: str,
    payload: WorkLogCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: AbstractTicketRepository = Depends(get_ticket_repository),
):
    """Registra una sesión de trabajo en el ticket vinculada al usuario autenticado."""
    return repo.add_work_log(ticket_code, payload, requester=current_user)
