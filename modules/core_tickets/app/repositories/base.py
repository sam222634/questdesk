from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from app.schemas import (
    AuthenticatedUser,
    TicketAssignUpdate,
    TicketCreate,
    TicketStatusUpdate,
    WorkLogCreate,
)


class RepositoryError(Exception):
    """Error base controlado de la capa de persistencia."""

    def __init__(self, message: str, step: str = "database", status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.step = step
        self.status_code = status_code


class ValidationError(RepositoryError):
    def __init__(self, message: str, step: str = "validation"):
        super().__init__(message=message, step=step, status_code=400)


class UnauthorizedError(RepositoryError):
    def __init__(self, message: str, step: str = "authentication"):
        super().__init__(message=message, step=step, status_code=401)


class ForbiddenError(RepositoryError):
    def __init__(self, message: str, step: str = "authorization"):
        super().__init__(message=message, step=step, status_code=403)


class NotFoundError(RepositoryError):
    def __init__(self, message: str, step: str = "lookup"):
        super().__init__(message=message, step=step, status_code=404)


class ConflictError(RepositoryError):
    def __init__(self, message: str, step: str = "conflict"):
        super().__init__(message=message, step=step, status_code=409)


class AbstractTicketRepository(ABC):
    """Contrato agnóstico del motor de base de datos (Patrón Repositorio)."""

    @abstractmethod
    def authenticate_by_key_hash(self, api_key_hash: str) -> AuthenticatedUser:
        raise NotImplementedError

    @abstractmethod
    def get_catalogs(self, requester: AuthenticatedUser) -> Dict[str, List[Dict[str, Any]]]:
        raise NotImplementedError

    @abstractmethod
    def list_tickets(
        self,
        requester: AuthenticatedUser,
        status: Optional[str] = None,
        queue: Optional[str] = None,
        include_closed: bool = False,
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_ticket_detail(self, ticket_code: str, requester: AuthenticatedUser) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def create_ticket(self, payload: TicketCreate, requester: AuthenticatedUser) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def update_status(
        self,
        ticket_code: str,
        payload: TicketStatusUpdate,
        requester: AuthenticatedUser,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def assign_ticket(
        self,
        ticket_code: str,
        payload: TicketAssignUpdate,
        requester: AuthenticatedUser,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def add_work_log(
        self,
        ticket_code: str,
        payload: WorkLogCreate,
        requester: AuthenticatedUser,
    ) -> Dict[str, Any]:
        raise NotImplementedError
