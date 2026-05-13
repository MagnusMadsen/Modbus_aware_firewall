import threading
from contextlib import contextmanager

from psycopg2.extras import RealDictCursor

from db import get_connection

_lock = threading.Lock()
_conn = None


def _get_conn():
    global _conn
    if _conn is None or _conn.closed != 0:
        _conn = get_connection()
    return _conn


@contextmanager
def db_cursor(dict_cursor: bool = False):
    with _lock:
        conn = _get_conn()
        cursor_factory = RealDictCursor if dict_cursor else None
        cur = conn.cursor(cursor_factory=cursor_factory)

        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


def query_one(query: str, params=None):
    with db_cursor(dict_cursor=True) as cur:
        cur.execute(query, params or ())
        row = cur.fetchone()
        return dict(row) if row is not None else None


def query_all(query: str, params=None):
    with db_cursor(dict_cursor=True) as cur:
        cur.execute(query, params or ())
        return cur.fetchall()


def execute(query: str, params=None) -> int:
    with db_cursor() as cur:
        cur.execute(query, params or ())
        return cur.rowcount