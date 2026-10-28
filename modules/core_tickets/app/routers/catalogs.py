from fastapi import APIRouter
from app.database import get_db_cursor

router = APIRouter(prefix="/api/v1/catalogs", tags=["Catálogos"])


@router.get("")
def get_all_catalogs():
    """Devuelve colas, estados y prioridades disponibles."""
    with get_db_cursor() as cur:
        cur.execute("SELECT id, slug, prefix, name, description, is_active FROM ticket_queues ORDER BY id")
        queues = cur.fetchall()

        cur.execute("SELECT id, name, is_closed, sort_order FROM ticket_statuses ORDER BY sort_order")
        statuses = cur.fetchall()

        cur.execute("SELECT id, name, weight FROM ticket_priorities ORDER BY weight")
        priorities = cur.fetchall()

    return {
        "queues": queues,
        "statuses": statuses,
        "priorities": priorities,
    }
