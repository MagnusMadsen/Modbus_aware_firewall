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

BUILTIN_MIGRATIONS = [
    {
        "version": "003",
        "name": "create_alerts",
        "filename": "003_create_alerts.sql",
        "sql": """
        CREATE TABLE IF NOT EXISTS alerts (
            id BIGSERIAL PRIMARY KEY,
            alert_key TEXT NOT NULL UNIQUE,
            alert_type TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT,
            severity TEXT NOT NULL DEFAULT 'medium',
            source_ip INET,
            target_ip INET,
            device_id INTEGER REFERENCES devices(id) ON DELETE SET NULL,
            details JSONB NOT NULL DEFAULT '{}'::jsonb,
            status TEXT NOT NULL DEFAULT 'pending',
            action TEXT,
            handled_by TEXT,
            handled_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT chk_alerts_status
                CHECK (status IN ('pending', 'approved', 'blocked', 'ignored')),
            CONSTRAINT chk_alerts_action
                CHECK (action IS NULL OR action IN ('approve', 'block', 'ignore')),
            CONSTRAINT chk_alerts_severity
                CHECK (severity IN ('info', 'low', 'medium', 'high', 'critical'))
        );

        CREATE INDEX IF NOT EXISTS idx_alerts_status_created
            ON alerts (status, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_alerts_updated_at
            ON alerts (updated_at DESC);
        """,
    }
]


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

    return build_migration(version, name, filename, sql)


def build_migration(version: str, name: str, filename: str, sql: str):
    checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()

    return {
        "version": version,
        "name": name,
        "filename": filename,
        "sql": sql,
        "checksum": checksum,
    }


def get_builtin_migrations():
    return [
        build_migration(
            item["version"],
            item["name"],
            item["filename"],
            item["sql"],
        )
        for item in BUILTIN_MIGRATIONS
    ]


def get_applied_migrations(cur):
    cur.execute(
        """
        SELECT version, checksum
        FROM schema_migrations
        """
    )
    return {row[0]: row[1] for row in cur.fetchall()}


def apply_migration(cur, migration):
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

        migrations = [parse_migration(path) for path in migration_paths]
        migrations.extend(get_builtin_migrations())
        migrations.sort(key=lambda item: item["version"])

        for migration in migrations:
            applied_checksum = applied.get(migration["version"])

            if applied_checksum:
                if applied_checksum != migration["checksum"]:
                    raise RuntimeError(
                        "Migration checksum mismatch for "
                        + migration["filename"]
                        + ". Do not edit migrations after they have been applied."
                    )
                continue

            apply_migration(cur, migration)

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
