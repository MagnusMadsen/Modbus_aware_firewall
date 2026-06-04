# db.py samler backendens adgang til PostgreSQL ét sted.
# get_connection() opretter selve databaseforbindelsen ud fra environment variables og secrets.
# apply_schema() kan læse 01_schema.sql og køre den mod databasen, så schemaet kan oprettes/opdateres.
# verify_schema() opretter ikke tabeller. Den tjekker kun om de nødvendige tabeller findes.
# Formålet med verify_schema() er at backend fejler tidligt og tydeligt, hvis databasen ikke er klar.

import os
import psycopg2
from config import read_secret_env

# Stien til SQL-filen med tabeldefinitioner og migrationer.
# Default-stien passer til Docker-containeren, hvor schema-filen mountes ind.
SCHEMA_FILE = os.getenv("DB_SCHEMA_FILE", "/db/init/01_schema.sql")

# Liste over tabeller backend forventer findes.
# verify_schema() bruger listen til at opdage manglende tabeller ved startup.
# Listen tjekker kun tabelnavne, ikke om alle kolonner/constraints er korrekte.
REQUIRED_TABLES = {
    "devices",
    "observed_connections",
    "modbus_register_state",
    "events",
    "metrics_bucket",
    "critical_registers",
    "app_users",
    "alarm_approvals",
}

# Opretter en ny PostgreSQL-forbindelse.
# Alle connection-parametre læses fra miljøvariabler, så koden kan køre både lokalt og i Docker.
# Password læses via read_secret_env(), så det kan komme fra Docker secrets i stedet for hardcoded tekst.
def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "postgres"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "modbus_fw"),
        user=os.getenv("DB_USER", "admin"),
        password=read_secret_env("DB_PASSWORD"),
    )

# Kører SQL-skemaet mod databasen.
# Funktionen læser hele 01_schema.sql og sender den til PostgreSQL.
# Den kan derfor både oprette tabeller og køre ALTER TABLE-migrationer, hvis SQL-filen indeholder det.
# Hvis noget fejler, laves rollback, så databasen ikke efterlades midt i en halv ændring.
def apply_schema():
    if not os.path.exists(SCHEMA_FILE):
        raise RuntimeError(f"Database schema file not found: {SCHEMA_FILE}")

    with open(SCHEMA_FILE, "r", encoding="utf-8") as schema_file:
        schema_sql = schema_file.read()

    if not schema_sql.strip():
        raise RuntimeError(f"Database schema file is empty: {SCHEMA_FILE}")

    conn = get_connection()
    cur = None

    try:
        cur = conn.cursor()
        cur.execute(schema_sql)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if cur is not None:
            cur.close()
        conn.close()

# Kontrollerer kun at de vigtigste tabeller findes i public schema.
# Den bruger information_schema.tables, som er PostgreSQLs oversigt over eksisterende tabeller.
# Der skal hentes alle tabeller som matcher REQUIRED_TABLES.
# Hvis en eller flere tabeller mangler, stoppes backend med en tydelig fejlbesked.
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