
import os

from config import read_secret_env

import psycopg2



def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "postgres"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "modbus_fw"),
        user=os.getenv("DB_USER", "admin"),
        password=read_secret_env("DB_PASSWORD"),
    )

def init_db():
    required_tables = {
        "devices",
        "observed_connections",
        "modbus_register_state",
        "events",
        "metrics_bucket",
        "critical_registers",
    }

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
            (list(required_tables),),
        )

        existing_tables = {row[0] for row in cur.fetchall()}
        missing_tables = sorted(required_tables - existing_tables)

        if missing_tables:
            raise RuntimeError(
                "Database schema missing required tables: "
                + ", ".join(missing_tables)
            )

    finally:
        if cur is not None:
            cur.close()
        conn.close()

        