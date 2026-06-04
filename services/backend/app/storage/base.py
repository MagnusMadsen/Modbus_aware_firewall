# base.py er den fælles database-adgang for alle filer i storage-mappen.
# I stedet for at hver storage-fil selv skal åbne forbindelse, lave cursor, commit og rollback,
# bruger de hjælpefunktionerne i denne fil.
# Det gør storage-koden kortere og sikrer, at databaseadgang håndteres ens alle steder.
import threading
from contextlib import contextmanager

from psycopg2.extras import RealDictCursor

from db import get_connection

# Backend kan både modtage API-kald og samtidig køre packet capture/state-tracking i baggrunden.
# Begge dele kan ramme databasen på samme tid.
# Locken sørger for, at kun én databaseoperation bruger den fælles connection ad gangen.
_lock = threading.Lock()
# _conn er den databaseforbindelse, som denne fil genbruger.
# Den starter som None, fordi forbindelsen først åbnes, når koden faktisk skal bruge databasen.
_conn = None


# Finder den aktive PostgreSQL-forbindelse.
# Hvis der ikke findes en connection endnu, eller hvis den gamle er lukket,
# oprettes en ny forbindelse med get_connection() fra db.py.
def _get_conn():
    global _conn
    if _conn is None or _conn.closed != 0:
        _conn = get_connection()
    return _conn


# db_cursor() er fælles ramme omkring en SQL-operation.
# Den åbner en cursor, giver den videre til query_one/query_all/execute,
# og sørger bagefter for commit, rollback og close.
# commit betyder: gem ændringen i databasen.
# rollback betyder: fortryd ændringen, hvis der skete en fejl.
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


# query_one() bruges til SELECT, hvor vi kun skal bruge én række.
# Eksempel: find én bruger, én alarm eller én optalt værdi.
# Funktionen returnerer en dict, så man kan skrive row["username"] i stedet for at bruge kolonnenummer.
# Hvis der ikke findes en række, returnerer den None.
def query_one(query: str, params=None):
    with db_cursor(dict_cursor=True) as cur:
        cur.execute(query, params or ())
        row = cur.fetchone()
        return dict(row) if row is not None else None


# query_all() bruges til SELECT, hvor vi forventer flere rækker.
# Eksempel: hent alle devices, seneste events eller alle alarm approvals.
# Den returnerer en liste af rows, hvor hver row kan læses som en dict.
def query_all(query: str, params=None):
    with db_cursor(dict_cursor=True) as cur:
        cur.execute(query, params or ())
        return cur.fetchall()


# execute() bruges til SQL, der ændrer data: INSERT, UPDATE eller DELETE.
# Den bruges når vi ikke behøver at få en række tilbage fra databasen.
# Returnerer rowcount, altså hvor mange rækker PostgreSQL siger blev påvirket.
def execute(query: str, params=None) -> int:
    with db_cursor() as cur:
        cur.execute(query, params or ())
        return cur.rowcount