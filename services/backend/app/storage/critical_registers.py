from psycopg2.extras import Json

from storage.base import execute, query_all, query_one


def get_critical_register(slave_ip, unit_id, register_type, register_address):
    return query_one(
        """
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
        LIMIT 1
        """,
        (slave_ip, unit_id, register_type, register_address),
    )


def list_critical_registers():
    return query_all(
        """
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


def save_critical_register(payload):
    execute(
        """
        INSERT INTO critical_registers
            (slave_ip, unit_id, register_type, register_address, label, allowed_values, pin_on_change, is_enabled)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (slave_ip, unit_id, register_type, register_address)
        DO UPDATE SET
            label = EXCLUDED.label,
            allowed_values = EXCLUDED.allowed_values,
            pin_on_change = EXCLUDED.pin_on_change,
            is_enabled = EXCLUDED.is_enabled
        """,
        (
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


def delete_critical_register(register_id):
    return execute(
        """
        DELETE FROM critical_registers
        WHERE id = %s
        """,
        (register_id,),
    )