import os
import psycopg2

def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "postgres"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "modbus_fw"),
        user=os.getenv("DB_USER", "admin"),
        password=os.getenv("DB_PASSWORD", "Admin1234!"),
    )

def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS observed_connections (
            id SERIAL PRIMARY KEY,
            src_ip INET NOT NULL,
            dst_ip INET NOT NULL,
            protocol TEXT NOT NULL,
            src_port INTEGER,
            dst_port INTEGER,
            first_seen TIMESTAMP NOT NULL DEFAULT NOW(),
            last_seen TIMESTAMP NOT NULL DEFAULT NOW(),
            packet_count INTEGER NOT NULL DEFAULT 1,
            UNIQUE (src_ip, dst_ip, protocol, src_port, dst_port)
        );
    """)

    conn.commit()
    cur.close()
    conn.close()
    