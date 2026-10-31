from fastapi import APIRouter, Depends
from app.repositories import AbstractTicketRepository, get_ticket_repository
from app.schemas import AuthenticatedUser
from app.security import get_current_user

router = APIRouter(prefix="/api/v1/catalogs", tags=["Catálogos"])


@router.get("")
def get_all_catalogs(
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: AbstractTicketRepository = Depends(get_ticket_repository),
):
    return repo.get_catalogs(requester=current_user)
