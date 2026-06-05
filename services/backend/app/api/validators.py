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
    # slave_ip er IP-adressen på den Modbus slave/PLC, som registeret tilhører.
    # ipaddress.ip_address() fejler hvis værdien ikke er en gyldig IP-adresse.
    # str(...) sikrer at IP'en ender som en almindelig tekststreng til resten af koden.
    try:
        slave_ip = str(ipaddress.ip_address(payload.get("slave_ip", "")))
    except ValueError:
        return None, "Invalid slave_ip"

    # unit_id kommer fra Modbus og skal være et heltal.
    # int(...) sikrer at f.eks. "1" fra JSON bliver behandlet som tallet 1.
    try:
        unit_id = int(payload.get("unit_id"))
    except (TypeError, ValueError):
        return None, "Invalid unit_id"

    # Modbus unit_id kan kun ligge fra 0 til 255.
    if unit_id < 0 or unit_id > 255:
        return None, "unit_id must be between 0 and 255"

    # register_type fortæller hvilken Modbus-registertype reglen gælder for.
    # strip() fjerner mellemrum før/efter teksten, så " holding_register " bliver til "holding_register". 
    # Det er defensiv input-rensning af api'et, så små fejl i frontend ikke ødelægger backend-data.
    register_type = str(payload.get("register_type", "")).strip()
    # Kun de registertyper som resten af backend og databasen kender, må accepteres.
    allowed_register_types = {
        "coil",
        "discrete_input",
        "input_register",
        "holding_register",
    }

    if register_type not in allowed_register_types:
        return None, "Invalid register_type"

    # register_address er adressen på selve Modbus-registeret.
    # Værdien konverteres til int, fordi JSON-input kan komme ind som tekst.
    try:
        register_address = int(payload.get("register_address"))
    except (TypeError, ValueError):
        return None, "Invalid register_address"

    # Modbus-registeradressen er et 16-bit felt i protokollen.
    # Derfor kan adressen kun være 0-65535.
    if register_address < 0 or register_address > 65535:
        return None, "register_address must be between 0 and 65535"

    # label er kun et menneskeligt navn til dashboardet.
    # Den er valgfri, men hvis den findes, fjernes mellemrum før/efter teksten.
    label = payload.get("label")
    if label is not None:
        label = str(label).strip()
        if len(label) > 100:
            return None, "label must be max 100 characters"

    # allowed_values er valgfri.
    # Hvis den bruges, skal den være en liste, fordi den kan indeholde flere tilladte værdier.
    allowed_values = payload.get("allowed_values")
    if allowed_values is not None and not isinstance(allowed_values, list):
        return None, "allowed_values must be a list or null"

    # Her returneres et nyt payload-dict med de rensede og korrekt typede værdier.
    # routes.py sender dette dict videre til storage-laget, som gemmer det i critical_registers.
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