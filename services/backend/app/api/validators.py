# validators.py indeholder validering af data, før routes.py sender det videre til storage-laget.
# Filen ændrer ikke databasen. Den kontrollerer kun input fra API-kald og returnerer enten et renset payload eller en fejltekst.
# Her bruges den til critical_registers, så ugyldige IP'er, unit_id, registertyper og registeradresser ikke bliver gemt.
import ipaddress


# validate_critical_register_payload() bruges af POST /api/critical-registers i routes.py.
# payload er JSON-data fra frontend, når brugeren opretter eller ændrer et kritisk Modbus-register.
# Funktionen validerer slave_ip, unit_id, register_type, register_address, label, allowed_values, pin_on_change og is_enabled.
# Hvis noget er ugyldigt, returneres None og en fejltekst.
# Hvis alt er gyldigt, returneres et nyt dict med rensede og korrekt typede værdier.
# ipaddress.ip_address() bruges til at validere og normalisere IP-adressen, så databasen får en korrekt IP-streng.
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