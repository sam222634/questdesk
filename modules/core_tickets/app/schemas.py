from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TicketCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=255)
    description: str = Field(..., min_length=1)
    queue_slug: str = Field(default="general")
    priority_name: str = Field(default="MEDIUM")
    estimated_points: int = Field(default=1, ge=1, le=10)
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
    headers: Optional[Dict[str, Any]] = None


class TicketStatusUpdate(BaseModel):
    status_name: str = Field(..., description="NEW, ASSIGNED, IN_PROGRESS, BLOCKED, RESOLVED, CLOSED")
    actor: str = Field(default="user")
    notes: Optional[str] = None


class WorkLogCreate(BaseModel):
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    notes: Optional[str] = None


class TicketSummaryResponse(BaseModel):
    id: int
    ticket_code: str
    title: str
    queue_slug: str
    queue_name: str
    status_name: str
    is_closed: bool
    priority_name: str
    priority_weight: int
    estimated_points: int
    total_minutes: int
    bitacora_uri: Optional[str] = None
    created_at: datetime
    updated_at: datetime
