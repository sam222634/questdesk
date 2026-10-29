from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from app.schemas import TicketCreate, TicketStatusUpdate, WorkLogCreate


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


class NotFoundError(RepositoryError):
    def __init__(self, message: str, step: str = "lookup"):
        super().__init__(message=message, step=step, status_code=404)


class ConflictError(RepositoryError):
    def __init__(self, message: str, step: str = "conflict"):
        super().__init__(message=message, step=step, status_code=409)


class AbstractTicketRepository(ABC):
    """Contrato agnóstico del motor de base de datos (Patrón Repositorio)."""

    @abstractmethod
    def get_catalogs(self) -> Dict[str, List[Dict[str, Any]]]:
        raise NotImplementedError

    @abstractmethod
    def list_tickets(
        self,
        status: Optional[str] = None,
        queue: Optional[str] = None,
        include_closed: bool = False,
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_ticket_detail(self, ticket_code: str) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def create_ticket(self, payload: TicketCreate) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def update_status(self, ticket_code: str, payload: TicketStatusUpdate) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def add_work_log(self, ticket_code: str, payload: WorkLogCreate) -> Dict[str, Any]:
        raise NotImplementedError
