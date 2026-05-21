import json

from storage.base import execute, query_all, query_one


ACTION_TO_STATUS = {
    "approve": "approved",
    "block": "blocked",
    "ignore": "ignored",
}


def create_or_touch_alert(
    alert_key,
    alert_type,
    title,
    message=None,
    severity="medium",
    source_ip=None,
    target_ip=None,
    device_id=None,
    details=None,
):
    execute(
        """
        INSERT INTO alerts (
            alert_key,
            alert_type,
            title,
            message,
            severity,
            source_ip,
            target_ip,
            device_id,
            details,
            status,
            created_at,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, 'pending', NOW(), NOW())
        ON CONFLICT (alert_key)
        DO UPDATE SET
            message = EXCLUDED.message,
            severity = EXCLUDED.severity,
            source_ip = EXCLUDED.source_ip,
            target_ip = EXCLUDED.target_ip,
            device_id = EXCLUDED.device_id,
            details = EXCLUDED.details,
            updated_at = NOW()
        WHERE alerts.status = 'pending'
        """,
        (
            alert_key,
            alert_type,
            title,
            message,
            severity,
            source_ip,
            target_ip,
            device_id,
            json.dumps(details or {}),
        ),
    )


def get_alert(alert_id):
    return query_one(
        """
        SELECT
            id,
            alert_key,
            alert_type,
            title,
            message,
            severity,
            source_ip::text AS source_ip,
            target_ip::text AS target_ip,
            device_id,
            details,
            status,
            action,
            handled_by,
            TO_CHAR(handled_at, 'YYYY-MM-DD HH24:MI:SS') AS handled_at,
            TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_at,
            TO_CHAR(updated_at, 'YYYY-MM-DD HH24:MI:SS') AS updated_at
        FROM alerts
        WHERE id = %s
        LIMIT 1
        """,
        (alert_id,),
    )


def list_pending_alerts(limit=10):
    return query_all(
        """
        SELECT
            id,
            alert_key,
            alert_type,
            title,
            message,
            severity,
            source_ip::text AS source_ip,
            target_ip::text AS target_ip,
            device_id,
            details,
            status,
            TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_at,
            TO_CHAR(updated_at, 'YYYY-MM-DD HH24:MI:SS') AS updated_at
        FROM alerts
        WHERE status = 'pending'
        ORDER BY
            CASE severity
                WHEN 'critical' THEN 5
                WHEN 'high' THEN 4
                WHEN 'medium' THEN 3
                WHEN 'low' THEN 2
                ELSE 1
            END DESC,
            updated_at DESC
        LIMIT %s
        """,
        (limit,),
    )


def list_alert_history(limit=50):
    return query_all(
        """
        SELECT
            id,
            alert_key,
            alert_type,
            title,
            message,
            severity,
            source_ip::text AS source_ip,
            target_ip::text AS target_ip,
            device_id,
            details,
            status,
            action,
            handled_by,
            TO_CHAR(handled_at, 'YYYY-MM-DD HH24:MI:SS') AS handled_at,
            TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_at,
            TO_CHAR(updated_at, 'YYYY-MM-DD HH24:MI:SS') AS updated_at
        FROM alerts
        ORDER BY COALESCE(handled_at, updated_at) DESC
        LIMIT %s
        """,
        (limit,),
    )


def handle_alert(alert_id, action, handled_by=None):
    status = ACTION_TO_STATUS.get(action)
    if status is None:
        raise ValueError("invalid action")

    affected_rows = execute(
        """
        UPDATE alerts
        SET
            status = %s,
            action = %s,
            handled_by = %s,
            handled_at = NOW(),
            updated_at = NOW()
        WHERE id = %s
          AND status = 'pending'
        """,
        (status, action, handled_by, alert_id),
    )

    return affected_rows > 0


def get_pending_alert_by_key(alert_key):
    return query_one(
        """
        SELECT id
        FROM alerts
        WHERE alert_key = %s
          AND status = 'pending'
        LIMIT 1
        """,
        (alert_key,),
    )
