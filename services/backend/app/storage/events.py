from psycopg2.extras import Json

from storage.base import query_one


def insert_event(
    event_type,
    severity="info",
    event_key=None,
    status="open",
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
            (ts, event_key, event_type, severity, status, source_ip, target_ip, unit_id, function_code,
             register_type, register_address, old_value, new_value, details)
        VALUES
            (NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (event_key)
        DO UPDATE SET
            ts = NOW(),
            severity = EXCLUDED.severity,
            status = CASE
                WHEN events.status IN ('approved', 'blocked', 'ignored', 'critical', 'closed') THEN events.status
                ELSE EXCLUDED.status
            END,
            source_ip = EXCLUDED.source_ip,
            target_ip = EXCLUDED.target_ip,
            unit_id = EXCLUDED.unit_id,
            function_code = EXCLUDED.function_code,
            register_type = EXCLUDED.register_type,
            register_address = EXCLUDED.register_address,
            old_value = EXCLUDED.old_value,
            new_value = EXCLUDED.new_value,
            details = EXCLUDED.details
        RETURNING id
        """,
        (
            event_key,
            event_type,
            severity,
            status,
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
