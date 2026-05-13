# formål: 
#   1. Oprette PostgreSQL-forbindelser
#   2. Kontrollere at database-schemaet er klar ved backend startup
#   3. Den opretter ikke tabeller den kontrollerer kun, at de nødvendige tabeller findes.

import os

import psycopg2

from config import read_secret_env


REQUIRED_TABLES = {
    "devices",
    "observed_connections",
    "modbus_register_state",
    "events",
    "metrics_bucket",
    "critical_registers",
}


def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "postgres"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "modbus_fw"),
        user=os.getenv("DB_USER", "admin"),
        password=read_secret_env("DB_PASSWORD"),
    )


def verify_schema():
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