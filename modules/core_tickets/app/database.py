from contextlib import contextmanager
from typing import Generator
import psycopg
from psycopg.rows import dict_row
from app.config import settings


@contextmanager
def get_db_cursor(commit: bool = False) -> Generator[psycopg.Cursor, None, None]:
    conn = psycopg.connect(settings.database_url, row_factory=dict_row)
    try:
        with conn.cursor() as cur:
            yield cur
            if commit:
                conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
