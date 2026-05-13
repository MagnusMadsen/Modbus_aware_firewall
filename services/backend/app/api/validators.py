import ipaddress


def validate_critical_register_payload(payload: dict) -> tuple[dict | None, str | None]:
    try:
        slave_ip = str(ipaddress.ip_address(payload.get("slave_ip", "")))
    except ValueError:
        return None, "Invalid slave_ip"

    try:
        unit_id = int(payload.get("unit_id"))
    except (TypeError, ValueError):
        return None, "Invalid unit_id"

    if unit_id < 0 or unit_id > 255:
        return None, "unit_id must be between 0 and 255"

    register_type = str(payload.get("register_type", "")).strip()
    allowed_register_types = {
        "coil",
        "discrete_input",
        "input_register",
        "holding_register",
    }

    if register_type not in allowed_register_types:
        return None, "Invalid register_type"

    try:
        register_address = int(payload.get("register_address"))
    except (TypeError, ValueError):
        return None, "Invalid register_address"

    if register_address < 0 or register_address > 65535:
        return None, "register_address must be between 0 and 65535"

    label = payload.get("label")
    if label is not None:
        label = str(label).strip()
        if len(label) > 100:
            return None, "label must be max 100 characters"

    allowed_values = payload.get("allowed_values")
    if allowed_values is not None and not isinstance(allowed_values, list):
        return None, "allowed_values must be a list or null"

    return {
        "slave_ip": slave_ip,
        "unit_id": unit_id,
        "register_type": register_type,
        "register_address": register_address,
        "label": label,
        "allowed_values": allowed_values,
        "pin_on_change": bool(payload.get("pin_on_change", True)),
        "is_enabled": bool(payload.get("is_enabled", True)),
    }, None