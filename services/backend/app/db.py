# db.py er backendens fælles adgang til PostgreSQL.
# Filen bruges af storage/base.py og startup-kode, når backend skal åbne en databaseforbindelse eller kontrollere schemaet.
# get_connection() opretter en ny PostgreSQL-forbindelse ud fra environment variables og secrets.
# apply_schema() læser SQL-filen 01_schema.sql og kører den mod databasen.
# verify_schema() opretter ikke tabeller. Den tjekker kun, at de tabeller backend kræver, findes.
# Formålet er at samle databaseforbindelse og schema-kontrol ét sted, så resten af backend ikke selv skal kende connection-parametre.

# Dataflow:
# storage/base.py
# └─ get_connection()
#    └─ psycopg2.connect(...)
#       └─ PostgreSQL
#
# Startup/schema-flow:
# backend startup
# ├─ apply_schema()
# │  └─ læser 01_schema.sql og kører CREATE/ALTER SQL mod PostgreSQL
# └─ verify_schema()
#    └─ spørger information_schema om REQUIRED_TABLES findes

import os
import psycopg2
from config import read_secret_env

# SCHEMA_FILE er stien til SQL-filen med tabeldefinitioner og migrationer.
# Værdien kan sættes med DB_SCHEMA_FILE.
# Hvis DB_SCHEMA_FILE ikke er sat, bruges default-stien fra Docker-containeren.
SCHEMA_FILE = os.getenv("DB_SCHEMA_FILE", "/db/init/01_schema.sql")

# REQUIRED_TABLES er minimumslisten over tabeller backend forventer findes.
# verify_schema() bruger listen ved startup for at opdage en database der ikke er initialiseret korrekt.
# Tjekket er bevidst simpelt: det kontrollerer tabelnavne, ikke alle kolonner, indexes eller constraints.
# De detaljer styres i 01_schema.sql.
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

# get_connection() opretter én ny PostgreSQL-forbindelse.
# Funktionen bliver brugt af storage/base.py, som åbner en connection når en query skal køres.
# Host, port, database og bruger læses fra environment variables.
# Password læses med read_secret_env("DB_PASSWORD"), så det kan komme fra Docker secrets eller environment variable.
# Funktionen gemmer ikke connectionen globalt. Kaldende kode er ansvarlig for at lukke connectionen igen.
def get_connection():
    # psycopg2.connect() åbner selve TCP-forbindelsen til PostgreSQL.
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "postgres"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "modbus_fw"),
        user=os.getenv("DB_USER", "admin"),
        password=read_secret_env("DB_PASSWORD"),
    )

# apply_schema() kører SQL-filen mod databasen.
# Funktionen bruges ved startup/setup, når backend skal sikre at schema og migrationer er kørt.
# Den læser hele 01_schema.sql og sender SQL'en til PostgreSQL.
# CREATE TABLE IF NOT EXISTS kan oprette manglende tabeller.
# ALTER TABLE-migrationer i samme SQL-fil kan ændre eksisterende tabeller.
# Hvis noget fejler, laves rollback, så databasen ikke efterlades midt i en halv ændring.
def apply_schema():
    # Backend skal stoppe tydeligt, hvis schema-filen ikke findes.
    if not os.path.exists(SCHEMA_FILE):
        raise RuntimeError(f"Database schema file not found: {SCHEMA_FILE}")

    # Læser hele SQL-filen ind som tekst, så den kan sendes til PostgreSQL på én gang.
    with open(SCHEMA_FILE, "r", encoding="utf-8") as schema_file:
        schema_sql = schema_file.read()

    # En tom schema-fil er en konfigurationsfejl og skal opdages ved startup.
    if not schema_sql.strip():
        raise RuntimeError(f"Database schema file is empty: {SCHEMA_FILE}")

    # Åbner databaseforbindelsen der skal bruges til schema-kørslen.
    conn = get_connection()
    cur = None

    try:
        cur = conn.cursor()
        # Sender hele SQL-scriptet til PostgreSQL.
        cur.execute(schema_sql)
        # commit gemmer schema-ændringerne, hvis hele SQL-scriptet lykkes.
        conn.commit()
    except Exception:
        # rollback fortryder ændringer fra denne kørsel, hvis SQL-scriptet fejler.
        conn.rollback()
        raise
    finally:
        # Cursor og connection lukkes altid, også hvis der opstod fejl.
        if cur is not None:
            cur.close()
        conn.close()

# verify_schema() kontrollerer at backendens nødvendige tabeller findes.
# Funktionen bruges ved startup som en hurtig sanity-check efter schema/migrationer.
# Den bruger information_schema.tables, som er PostgreSQLs egen oversigt over eksisterende tabeller.
# Den opretter ikke noget og ændrer ikke databasen.
# Hvis tabeller mangler, stoppes backend med en tydelig fejlbesked.
def verify_schema():
    # Åbner en databaseforbindelse til schema-tjekket.
    conn = get_connection()
    cur = None

    try:
        cur = conn.cursor()
        # Spørger PostgreSQL hvilke af REQUIRED_TABLES der findes i public schema.
        cur.execute(
            """
            -- Henter tabelnavne for de tabeller backend kræver.
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = ANY(%s)
            """,
            # REQUIRED_TABLES sendes som parameter til SQL'en i stedet for at blive bygget ind som tekst.
            (list(REQUIRED_TABLES),),
        )

        # Laver database-resultatet om til et set med tabelnavne der faktisk findes.
        existing_tables = {row[0] for row in cur.fetchall()}
        # Set-difference viser hvilke krævede tabeller der mangler.
        missing_tables = sorted(REQUIRED_TABLES - existing_tables)

        # Backend stoppes hvis databasen ikke har alle nødvendige tabeller.
        if missing_tables:
            raise RuntimeError(
                "Database schema missing required tables: "
                + ", ".join(missing_tables)
            )

    finally:
        # Cursor og connection lukkes altid, også hvis schema-tjekket fejler.
        if cur is not None:
            cur.close()
        conn.close()