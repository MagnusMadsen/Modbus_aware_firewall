# formål:
#   1. Oprette PostgreSQL-forbindelser
#   2. Køre database-migrations ved backend startup
#   3. Kontrollere at database-schemaet er klar

import glob
import hashlib
import os
from pathlib import Path

import psycopg2

from config import read_secret_env


REQUIRED_TABLES = {
    "devices",
    "observed_connections",
    "modbus_register_state",
    "events",
    "metrics_bucket",
    "critical_registers",
    "alert_approvals",
    "alerts",
}

MIGRATIONS_DIR = os.getenv("DB_MIGRATIONS_DIR", "/db-migrations")


def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "postgres"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "modbus_fw"),
        user=os.getenv("DB_USER", "admin"),
        password=read_secret_env("DB_PASSWORD"),
    )


def ensure_migration_table(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            checksum TEXT NOT NULL,
            applied_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """
    )


def parse_migration(path: str):
    filename = Path(path).name
    stem = Path(path).stem

    if "_" not in stem:
        raise RuntimeError(f"Invalid migration filename: {filename}")

    version, name = stem.split("_", 1)

    if not version.isdigit():
        raise RuntimeError(f"Invalid migration version: {filename}")

    with open(path, "r", encoding="utf-8") as file:
        sql = file.read()

    checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()

    return {
        "version": version,
        "name": name,
        "filename": filename,
        "sql": sql,
        "checksum": checksum,
    }


def get_applied_migrations(cur):
    cur.execute(
        """
        SELECT version, checksum
        FROM schema_migrations
        """
    )
    return {row[0]: row[1] for row in cur.fetchall()}


def run_migrations():
    migration_paths = sorted(glob.glob(os.path.join(MIGRATIONS_DIR, "*.sql")))

    if not migration_paths:
        raise RuntimeError(f"No database migrations found in {MIGRATIONS_DIR}")

    conn = get_connection()
    cur = None

    try:
        cur = conn.cursor()
        cur.execute("SELECT pg_advisory_xact_lock(502502);")

        ensure_migration_table(cur)
        applied = get_applied_migrations(cur)

        for path in migration_paths:
            migration = parse_migration(path)
            applied_checksum = applied.get(migration["version"])

            if applied_checksum:
                if applied_checksum != migration["checksum"]:
                    raise RuntimeError(
                        "Migration checksum mismatch for "
                        + migration["filename"]
                        + ". Do not edit migrations after they have been applied."
                    )
                continue

            cur.execute(migration["sql"])

            cur.execute(
                """
                INSERT INTO schema_migrations (version, name, checksum)
                VALUES (%s, %s, %s)
                """,
                (
                    migration["version"],
                    migration["name"],
                    migration["checksum"],
                ),
            )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        if cur is not None:
            cur.close()
        conn.close()


def verify_schema():
    run_migrations()

    conn = get_connection()
    cur = None

    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = ANY(%s)
            """,
            (list(REQUIRED_TABLES),),
        )

        existing_tables = {row[0] for row in cur.fetchall()}
        missing_tables = sorted(REQUIRED_TABLES - existing_tables)

        if missing_tables:
            raise RuntimeError(
                "Database schema missing required tables: "
                + ", ".join(missing_tables)
            )

    finally:
        if cur is not None:
            cur.close()
        conn.close()
