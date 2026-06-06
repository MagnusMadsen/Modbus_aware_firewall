# critical_registers.py læser og skriver regler for kritiske Modbus-registre.
# Data kommer primært fra to steder:
# 1. API-routes/frontend, når brugeren opretter, ændrer, lister eller sletter kritiske registre.
# 2. state/registers.py, når en registerændring skal vurderes mod critical_registers-tabellen.
# Denne fil modtager ikke rå packets og laver ikke Modbus-parsing.
# Den arbejder kun med allerede validerede felter som slave_ip, unit_id, register_type og register_address.
from psycopg2.extras import Json

from storage.base import execute, query_all, query_one


# get_critical_register() bruges af state/registers.py, når et register ændrer værdi.
# Funktionen slår op i critical_registers-tabellen for at se om netop dette register er markeret som kritisk.
# slave_ip kommer fra Modbus write requestens dst_ip, altså den slave/PLC der skrives til.
# unit_id kommer fra MBAP-headeren.
# register_type og register_address kommer fra packet_parser/request.py.
# Funktionen returnerer én aktiv regel, hvis registeret findes som kritisk og is_enabled er TRUE.
def get_critical_register(slave_ip, unit_id, register_type, register_address):
    return query_one(
        """
        -- Finder den aktive critical_registers-regel for præcis dette register.
        SELECT
            id,
            slave_ip::text AS slave_ip,
            unit_id,
            register_type,
            register_address,
            label,
            allowed_values,
            pin_on_change,
            is_enabled
        FROM critical_registers
        WHERE slave_ip = %s
            AND unit_id = %s
            AND register_type = %s
            AND register_address = %s
            AND is_enabled = TRUE
        """,
        (slave_ip, unit_id, register_type, register_address),
    )
    # query_one() returnerer reglen til RegisterTracker, som bruger den til severity, pinning og allowed_values.


# list_critical_registers() bruges af API-routes/frontend til at vise alle kritiske registerregler.
# Funktionen henter alle regler, både aktive og deaktiverede, så brugeren kan administrere dem i dashboardet.
def list_critical_registers():
    return query_all(
        """
        -- Henter alle critical_registers-regler til frontend-administration.
        SELECT
            id,
            slave_ip::text AS slave_ip,
            unit_id,
            register_type,
            register_address,
            label,
            allowed_values,
            pin_on_change,
            is_enabled,
            TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_at
        FROM critical_registers
        ORDER BY slave_ip, unit_id, register_type, register_address
        """
    )
    # query_all() bruges her, fordi frontend skal have en liste med alle kritiske registerregler.


# save_critical_register() bruges af API-routes, når frontend opretter eller ændrer en kritisk registerregel.
# payload er allerede valideret i api/validators.py, før funktionen kaldes.
# Funktionen skriver til critical_registers-tabellen med INSERT ... ON CONFLICT.
# Det betyder: opret reglen hvis den ikke findes, ellers opdater den eksisterende regel for samme slave_ip/unit_id/register_type/register_address.
def save_critical_register(payload):
    # Sender SQL-kommandoen videre til storage/base.py execute(), som åbner connection og kører queryen.
    execute(
        """
        -- Opretter en ny kritisk registerregel.
        INSERT INTO critical_registers
            (slave_ip, unit_id, register_type, register_address, label, allowed_values, pin_on_change, is_enabled)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s)
        -- Hvis reglen allerede findes for samme register, opdateres den i stedet for at lave en dublet.
        ON CONFLICT (slave_ip, unit_id, register_type, register_address)
        DO UPDATE SET
            label = EXCLUDED.label,
            allowed_values = EXCLUDED.allowed_values,
            pin_on_change = EXCLUDED.pin_on_change,
            is_enabled = EXCLUDED.is_enabled
        """,
        (
            # Parametrene bindes separat, så brugerinput ikke sættes direkte ind i SQL-strengen.
            # allowed_values gemmes som JSONB via psycopg2.extras.Json, hvis brugeren har angivet tilladte værdier.
            payload["slave_ip"],
            payload["unit_id"],
            payload["register_type"],
            payload["register_address"],
            payload.get("label"),
            Json(payload.get("allowed_values")) if payload.get("allowed_values") is not None else None,
            payload.get("pin_on_change", True),
            payload.get("is_enabled", True),
        ),
    )


# delete_critical_register() bruges af API-routes/frontend, når brugeren sletter en kritisk registerregel.
# register_id er den primære nøgle fra critical_registers-tabellen.
# Funktionen sletter kun selve reglen. Den sletter ikke historiske events eller register-state.
def delete_critical_register(register_id):
    # Sender DELETE videre til storage/base.py execute().
    return execute(
        """
        -- Sletter reglen med det konkrete id.
        DELETE FROM critical_registers
        WHERE id = %s
        """,
        (register_id,),
    )