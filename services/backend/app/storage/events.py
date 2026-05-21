from psycopg2.extras import Json

from storage.base import execute
from storage.alerts import create_or_touch_alert


ALERT_EVENT_TYPES = {
    "latency_spike": {
        "title": "Latency over threshold",
        "message": "Modbus latency exceeded the configured threshold.",
    },
    "request_timeout": {
        "title": "Modbus request timeout",
        "message": "A Modbus request did not receive a response before timeout.",
    },
    "exception_response": {
        "title": "Modbus exception response",
        "message": "A Modbus slave returned an exception response.",
    },
    "identity_mac_changed": {
        "title": "Device MAC identity changed",
        "message": "A known IP address was observed with a different MAC address.",
    },
    "identity_role_changed": {
        "title": "Device role changed",
        "message": "A known device changed Modbus role.",
    },
    "new_device": {
        "title": "Unknown device discovered",
        "message": "A new device was observed on the OT network.",
    },
    "new_function_code": {
        "title": "New Modbus function code",
        "message": "A new Modbus function code was observed for this slave.",
    },
    "register_value_changed": {
        "title": "Critical register changed",
        "message": "A monitored critical register changed value.",
    },
    "new_register_observed": {
        "title": "Critical register observed",
        "message": "A monitored critical register was observed for the first time.",
    },
}


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
    details = details or {}

    execute(
        """
        INSERT INTO events
            (ts, event_type, severity, source_ip, target_ip, unit_id, function_code,
             register_type, register_address, old_value, new_value, details)
        VALUES
            (NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            Json(details),
        ),
    )

    create_alert_from_event(
        event_type=event_type,
        severity=severity,
        source_ip=source_ip,
        target_ip=target_ip,
        unit_id=unit_id,
        function_code=function_code,
        register_type=register_type,
        register_address=register_address,
        old_value=old_value,
        new_value=new_value,
        details=details,
    )


def create_alert_from_event(
    event_type,
    severity,
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
    config = ALERT_EVENT_TYPES.get(event_type)
    if config is None:
        return

    details = details or {}
    is_pinned = bool(details.get("is_pinned"))

    if event_type in {"register_value_changed", "new_register_observed"} and not is_pinned:
        return

    if severity not in {"medium", "high", "critical"} and not is_pinned:
        return

    alert_key = build_alert_key(
        event_type=event_type,
        source_ip=source_ip,
        target_ip=target_ip,
        unit_id=unit_id,
        function_code=function_code,
        register_type=register_type,
        register_address=register_address,
    )

    alert_details = {
        "event_type": event_type,
        "unit_id": unit_id,
        "function_code": function_code,
        "register_type": register_type,
        "register_address": register_address,
        "old_value": None if old_value is None else str(old_value),
        "new_value": None if new_value is None else str(new_value),
        **details,
    }

    create_or_touch_alert(
        alert_key=alert_key,
        alert_type=event_type,
        title=config["title"],
        message=details.get("message") or config["message"],
        severity=severity,
        source_ip=source_ip,
        target_ip=target_ip,
        details=alert_details,
    )


def build_alert_key(
    event_type,
    source_ip=None,
    target_ip=None,
    unit_id=None,
    function_code=None,
    register_type=None,
    register_address=None,
):
    parts = [
        event_type,
        str(source_ip or "-"),
        str(target_ip or "-"),
        str(unit_id if unit_id is not None else "-"),
        str(function_code if function_code is not None else "-"),
        str(register_type or "-"),
        str(register_address if register_address is not None else "-"),
    ]
    return ":".join(parts)
