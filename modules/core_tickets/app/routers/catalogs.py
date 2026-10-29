from fastapi import APIRouter, Depends
from app.repositories import AbstractTicketRepository, get_ticket_repository

router = APIRouter(prefix="/api/v1/catalogs", tags=["Catálogos"])


@router.get("")
def get_all_catalogs(repo: AbstractTicketRepository = Depends(get_ticket_repository)):
    """Devuelve colas, estados y prioridades disponibles a través del Repositorio."""
    return repo.get_catalogs()
