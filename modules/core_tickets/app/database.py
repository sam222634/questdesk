from contextlib import contextmanager
from typing import Generator
import psycopg
from psycopg.rows import dict_row
from app.config import settings


@contextmanager
def get_db_connection() -> Generator[psycopg.Connection, None, None]:
    """Provee una conexión a PostgreSQL con dict_row y cierre garantizado."""
    conn = psycopg.connect(settings.database_url, row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()
