import hashlib
from typing import Optional
from fastapi import Depends, Header
from app.config import settings
from app.repositories import AbstractTicketRepository, UnauthorizedError, get_ticket_repository
from app.schemas import AuthenticatedUser


def get_current_user(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    repo: AbstractTicketRepository = Depends(get_ticket_repository),
) -> AuthenticatedUser:
    """
    Valida en cada petición la API-Key (vía hash SHA-256) y recupera el rol vigente del usuario.
    Si no se envía cabecera en modo local, usa la clave local configurada en entorno.
    """
    raw_key = (x_api_key or settings.default_api_key or "").strip()
    if not raw_key:
        raise UnauthorizedError("Falta la cabecera de autenticación X-API-Key.")

    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    return repo.authenticate_by_key_hash(key_hash)
