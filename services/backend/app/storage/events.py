from psycopg2.extras import Json

from storage.base import query_one


def insert_event(
    event_type,
    severity="info",
    source_ip=None,
    target_ip=None,
    unit_id=None,
    function_code=None,
    register_type=None,
    register_address=None,
    old_value=None,
    new_value=None,
    details=None,
):
    row = query_one(
        """
        INSERT INTO events
            (ts, event_type, severity, source_ip, target_ip, unit_id, function_code,
             register_type, register_address, old_value, new_value, details)
        VALUES
            (NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """,
        (
            event_type,
            severity,
            source_ip,
            target_ip,
            unit_id,
            function_code,
            register_type,
            register_address,
            None if old_value is None else str(old_value),
            None if new_value is None else str(new_value),
            Json(details or {}),
        ),
    )

    return row["id"] if row else None
