from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class AuthenticatedUser(BaseModel):
    user_id: int
    user_uuid: UUID
    username: str
    display_name: str
    role: str


class TicketCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=255)
    description: str = Field(..., min_length=1)
    queue_slug: str = Field(default="general")
    priority_name: str = Field(default="MEDIUM")
    estimated_points: int = Field(default=1, ge=1, le=10)
    assignee_uuid: Optional[UUID] = Field(
        default=None,
        description="UUID opaco del usuario responsable (si se omite, se asigna al solicitante actual)",
    )
    channel: str = Field(default="API")
    sender_email: Optional[str] = None
    message_id: Optional[str] = None
    raw_headers: Optional[Dict[str, Any]] = None


class EmailWebhookPayload(BaseModel):
    subject: str = Field(..., min_length=1, max_length=255)
    body: str = Field(default="Sin contenido en el cuerpo del correo.")
    sender: str = Field(..., min_length=3, max_length=255)
    message_id: Optional[str] = None
    queue_slug: str = Field(default="general")
    priority_name: str = Field(default="MEDIUM")
    estimated_points: int = Field(default=1, ge=1, le=10)
    assignee_uuid: Optional[UUID] = None
    headers: Optional[Dict[str, Any]] = None


class TicketStatusUpdate(BaseModel):
    status_name: str = Field(..., description="NEW, ASSIGNED, IN_PROGRESS, BLOCKED, RESOLVED, CLOSED")
    notes: Optional[str] = None


class TicketAssignUpdate(BaseModel):
    target_user_uuid: UUID = Field(..., description="UUID opaco del compañero o subordinado al que se delega")
    notes: Optional[str] = None


class WorkLogCreate(BaseModel):
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    notes: Optional[str] = None


class BitacoraUpdate(BaseModel):
    content: str = Field(..., min_length=1, description="Contenido Markdown completo de la bitácora")
