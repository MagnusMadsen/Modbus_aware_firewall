from psycopg2.extras import Json

from storage.base import execute, query_all, query_one


def save_alarm_approval(payload):
    execute(
        """
        INSERT INTO alarm_approvals
            (alarm_key, alarm_type, action, status, handled_by, event_id, details)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (alarm_key)
        DO UPDATE SET
            alarm_type = EXCLUDED.alarm_type,
            action = EXCLUDED.action,
            status = EXCLUDED.status,
            handled_by = EXCLUDED.handled_by,
            handled_at = NOW(),
            event_id = COALESCE(EXCLUDED.event_id, alarm_approvals.event_id),
            details = EXCLUDED.details
        """,
        (
            payload["alarm_key"],
            payload["alarm_type"],
            payload["action"],
            payload["status"],
            payload["handled_by"],
            payload.get("event_id"),
            Json(payload.get("details") or {}),
        ),
    )

    event_id = payload.get("event_id")
    if event_id is not None:
        execute(
            """
            UPDATE events
            SET status = %s
            WHERE id = %s
            """,
            (payload["status"], event_id),
        )


def list_alarm_approvals():
    return query_all(
        """
        SELECT
            id,
            alarm_key,
            alarm_type,
            action,
            status,
            handled_by,
            TO_CHAR(handled_at, 'YYYY-MM-DD HH24:MI:SS') AS handled_at,
            event_id,
            details
        FROM alarm_approvals
        ORDER BY handled_at DESC
        """
    )


def get_alarm_approval(alarm_key):
    return query_one(
        """
        SELECT
            id,
            alarm_key,
            alarm_type,
            action,
            status,
            handled_by,
            TO_CHAR(handled_at, 'YYYY-MM-DD HH24:MI:SS') AS handled_at,
            event_id,
            details
        FROM alarm_approvals
        WHERE alarm_key = %s
        LIMIT 1
        """,
        (alarm_key,),
    )


def get_approved_alarm_keys():
    rows = query_all(
        """
        SELECT alarm_key
        FROM alarm_approvals
        WHERE status IN ('approved', 'blocked', 'ignored', 'critical')
        """
    )

    return [row["alarm_key"] for row in rows]
