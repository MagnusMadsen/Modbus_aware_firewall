import json

from storage.base import execute, query_all


def map_action_to_status(action: str) -> str:
    if action == "approve":
        return "approved"
    if action == "block":
        return "blocked"
    if action == "ignore":
        return "ignored"
    return "handled"


def save_alert_approval(payload: dict) -> None:
    details = payload.get("details") or []

    execute(
        """
        INSERT INTO alert_approvals (
            alert_key,
            alert_type,
            title,
            message,
            action,
            status,
            details,
            device_id,
            handled_by,
            handled_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, NOW())
        ON CONFLICT (alert_key)
        DO UPDATE SET
            alert_type = EXCLUDED.alert_type,
            title = EXCLUDED.title,
            message = EXCLUDED.message,
            action = EXCLUDED.action,
            status = EXCLUDED.status,
            details = EXCLUDED.details,
            device_id = EXCLUDED.device_id,
            handled_by = EXCLUDED.handled_by,
            handled_at = NOW()
        """,
        (
            payload["alert_key"],
            payload["alert_type"],
            payload["title"],
            payload.get("message"),
            payload["action"],
            payload.get("status") or map_action_to_status(payload["action"]),
            json.dumps(details),
            payload.get("device_id"),
            payload.get("handled_by"),
        ),
    )


def list_alert_approvals(limit: int = 50):
    return query_all(
        """
        SELECT
            id,
            alert_key,
            alert_type,
            title,
            message,
            action,
            status,
            details,
            device_id,
            handled_by,
            TO_CHAR(handled_at, 'YYYY-MM-DD HH24:MI:SS') AS handled_at
        FROM alert_approvals
        ORDER BY handled_at DESC
        LIMIT %s
        """,
        (limit,),
    )