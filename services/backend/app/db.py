import os
import psycopg2

def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "postgres"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "modbus_fw"),
        user=os.getenv("DB_USER", "modbus"),
        password=os.getenv("DB_PASSWORD", "modbuspassword"),
    )