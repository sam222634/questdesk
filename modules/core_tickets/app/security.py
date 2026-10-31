import hashlib
from typing import Optional
from fastapi import Depends, Header
from app.repositories import AbstractTicketRepository, UnauthorizedError, get_ticket_repository
from app.schemas import AuthenticatedUser


def get_current_user(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    repo: AbstractTicketRepository = Depends(get_ticket_repository),
) -> AuthenticatedUser:
    raw_key = (x_api_key or "").strip()
    if not raw_key:
        raise UnauthorizedError("Se requiere la cabecera de autenticación X-API-Key.")

    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    return repo.authenticate_by_key_hash(key_hash)
