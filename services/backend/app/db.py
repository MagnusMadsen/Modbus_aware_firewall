import os
from pathlib import Path

import psycopg2

def read_secret_env(name: str, default: str | None = None) -> str:
    file_path = os.getenv(f"{name}_FILE")

    if file_path:
        return Path(file_path).read_text(encoding="utf-8").strip()

    value = os.getenv(name)
    if value:
        return value

    if default is not None:
        return default

    raise RuntimeError(f"Missing required secret or environment variable: {name}")


def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "postgres"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "modbus_fw"),
        user=os.getenv("DB_USER", "admin"),
        password=read_secret_env("DB_PASSWORD"),
    )


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS devices (
            id SERIAL PRIMARY KEY,
            ip INET NOT NULL UNIQUE,
            mac TEXT,
            role TEXT,
            first_seen TIMESTAMP NOT NULL DEFAULT NOW(),
            last_seen TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS observed_connections (
            id SERIAL PRIMARY KEY,
            master_ip INET NOT NULL,
            slave_ip INET NOT NULL,
            unit_id INTEGER,
            first_seen TIMESTAMP NOT NULL DEFAULT NOW(),
            last_seen TIMESTAMP NOT NULL DEFAULT NOW(),
            request_count BIGINT NOT NULL DEFAULT 1,
            UNIQUE (master_ip, slave_ip, unit_id)
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS modbus_register_state (
            id SERIAL PRIMARY KEY,
            slave_ip INET NOT NULL,
            unit_id INTEGER NOT NULL,
            register_type TEXT NOT NULL,
            register_address INTEGER NOT NULL,
            last_value TEXT,
            first_seen TIMESTAMP NOT NULL DEFAULT NOW(),
            last_seen TIMESTAMP NOT NULL DEFAULT NOW(),
            write_count BIGINT NOT NULL DEFAULT 0,
            UNIQUE (slave_ip, unit_id, register_type, register_address)
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id BIGSERIAL PRIMARY KEY,
            ts TIMESTAMP NOT NULL DEFAULT NOW(),
            event_type TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'info',
            source_ip INET,
            target_ip INET,
            unit_id INTEGER,
            function_code INTEGER,
            register_type TEXT,
            register_address INTEGER,
            old_value TEXT,
            new_value TEXT,
            details JSONB NOT NULL DEFAULT '{}'::jsonb
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS metrics_bucket (
            id BIGSERIAL PRIMARY KEY,
            bucket_ts TIMESTAMP NOT NULL UNIQUE,
            traffic_count BIGINT NOT NULL DEFAULT 0,
            request_count BIGINT NOT NULL DEFAULT 0,
            response_count BIGINT NOT NULL DEFAULT 0,
            failed_count BIGINT NOT NULL DEFAULT 0,
            arp_count BIGINT NOT NULL DEFAULT 0,
            avg_latency_ms DOUBLE PRECISION,
            p95_latency_ms DOUBLE PRECISION,
            active_connections INTEGER NOT NULL DEFAULT 0
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS critical_registers (
            id SERIAL PRIMARY KEY,
            slave_ip INET NOT NULL,
            unit_id INTEGER NOT NULL,
            register_type TEXT NOT NULL,
            register_address INTEGER NOT NULL,
            label TEXT,
            allowed_values JSONB,
            pin_on_change BOOLEAN NOT NULL DEFAULT TRUE,
            is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE (slave_ip, unit_id, register_type, register_address)
        );
        """
    )

    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_critical_registers_lookup "
        "ON critical_registers (slave_ip, unit_id, register_type, register_address);"
    )

    cur.execute("CREATE INDEX IF NOT EXISTS idx_devices_last_seen ON devices (last_seen DESC);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_connections_last_seen ON observed_connections (last_seen DESC);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_register_state_slave ON modbus_register_state (slave_ip, unit_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events (ts DESC);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_metrics_bucket_ts ON metrics_bucket (bucket_ts DESC);")

    conn.commit()
    cur.close()
    conn.close()