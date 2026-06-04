# routes.py definerer backendens HTTP API-routes.
# Frontend kalder disse endpoints for at hente dashboard-data, devices, users, critical registers og alarm approvals.
# Filen indeholder ikke selve SQL-koden. Den validerer input, kalder storage/dashboard-funktioner og returnerer JSON-svar.
# De fleste routes er beskyttet med @require_api_token, så frontend skal sende X-API-Token headeren.

from flask import Blueprint, jsonify, request
from werkzeug.security import check_password_hash

from api.auth import require_api_token
from api.validators import validate_critical_register_payload
from dashboard.service import fetch_devices, fetch_summary
from storage import (
    delete_critical_register,
    get_approved_alarm_keys,
    get_user_by_username,
    list_alarm_approvals,
    list_critical_registers,
    list_users,
    save_alarm_approval,
    save_critical_register,
    update_last_login,
    upsert_user,
)
from storage.devices import update_device_status

# Flask Blueprint samler API-routes, så main.py kan registrere dem samlet på Flask-appen.
api_bp = Blueprint("api", __name__)

# Mapper frontendens alarm-knapper til den status der gemmes i databasen.
# Eksempel: action="approve" bliver til status="approved".
# Denne status gemmes både i alarm_approvals og bruges til at opdatere events.status.
ALARM_ACTION_TO_STATUS = {
    "approve": "approved",
    "block": "blocked",
    "ignore": "ignored",
    "critical": "critical",
}

# Roller som API'et accepterer, når en bruger oprettes eller opdateres.
USER_ROLES = {"admin", "operator"}


# validate_alarm_approval_payload() kontrollerer data fra POST /api/alarm-approvals.
# Den sikrer at alarm_key, alarm_type, action, handled_by, details og event_id har det format backend forventer.
# event_id er påkrævet, fordi alarm_approvals skal kunne pege tilbage på den konkrete række i events.
# Funktionen returnerer enten et renset payload-dict eller en fejltekst.
def validate_alarm_approval_payload(payload):
    if not isinstance(payload, dict):
        return None, "Invalid JSON payload"

    alarm_key = str(payload.get("alarm_key") or "").strip()
    alarm_type = str(payload.get("alarm_type") or "").strip()
    action = str(payload.get("action") or "").strip().lower()
    handled_by = str(payload.get("handled_by") or "").strip()
    details = payload.get("details") or {}
    event_id = payload.get("event_id")

    if not alarm_key:
        return None, "alarm_key is required"

    if not alarm_type:
        return None, "alarm_type is required"

    if action not in ALARM_ACTION_TO_STATUS:
        return None, "invalid action"

    if not handled_by:
        return None, "handled_by is required"

    if not isinstance(details, dict):
        return None, "details must be an object"

    if event_id is None:
        return None, "event_id is required"

    try:
        event_id = int(event_id)
    except (TypeError, ValueError):
        return None, "event_id must be an integer"

    return {
        "alarm_key": alarm_key,
        "alarm_type": alarm_type,
        "action": action,
        "status": ALARM_ACTION_TO_STATUS[action],
        "handled_by": handled_by,
        "event_id": event_id,
        "details": details,
    }, None


# public_user() laver en bruger-række om til et sikkert JSON-svar.
# Password-hash returneres ikke til frontend.
def public_user(user):
    return {
        "id": user.get("id"),
        "username": user.get("username"),
        "role": user.get("role"),
        "is_active": user.get("is_active"),
        "created_at": user.get("created_at"),
        "last_login": user.get("last_login"),
    }


# Healthcheck uden API-token.
# Bruges til hurtigt at se om backend-processen svarer.
@api_bp.get("/health")
def health():
    return jsonify({"status": "ok", "service": "backend"})


# Returnerer samlet dashboard-data.
# fetch_summary() bygger svaret fra metrics, devices, events, ports, connections og alarm approvals.
@api_bp.get("/api/dashboard")
@require_api_token
def api_dashboard():
    return jsonify(fetch_summary())


# Returnerer devices-listen til frontend.
# Data hentes via fetch_devices(), som læser fra devices-tabellen gennem dashboard-laget.
@api_bp.get("/api/devices")
@require_api_token
def api_devices():
    return jsonify(fetch_devices())


# Returnerer gemte alarm approvals.
# Bruges af frontend til at vide hvilke alarmer brugeren allerede har håndteret.
@api_bp.get("/api/alarm-approvals")
@require_api_token
def api_alarm_approvals():
    return jsonify(list_alarm_approvals())


# Returnerer kun alarm keys for håndterede alarmer.
# Det er et letvægts-endpoint, så frontend hurtigt kan filtrere alarmer der allerede er behandlet.
@api_bp.get("/api/approved-alarm-keys")
@require_api_token
def api_approved_alarm_keys():
    return jsonify({
        "approved_alarm_keys": get_approved_alarm_keys()
    })


# Gemmer brugerens beslutning på en alarm.
# Payload valideres først, og derefter gemmer save_alarm_approval() beslutningen i alarm_approvals.
# save_alarm_approval() opdaterer også events.status ud fra event_id.
@api_bp.post("/api/alarm-approvals")
@require_api_token
def api_save_alarm_approval():
    payload = request.get_json(silent=True)
    validated_payload, error = validate_alarm_approval_payload(payload)

    if error:
        return jsonify({"error": error}), 400

    save_alarm_approval(validated_payload)
    return jsonify({"status": "ok"})


# Returnerer brugere til administrationsdelen af frontend.
@api_bp.get("/api/users")
@require_api_token
def api_users():
    return jsonify(list_users())


# Opretter eller opdaterer en bruger.
# API'et validerer username, role og is_active før upsert_user() skriver til databasen.
# Password-hash forventes allerede at være hashet, når det sendes til dette endpoint.
@api_bp.post("/api/users")
@require_api_token
def api_save_user():
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid JSON payload"}), 400

    username = str(payload.get("username") or "").strip()
    password_hash = payload.get("password_hash")
    role = str(payload.get("role") or "operator").strip().lower()
    is_active = payload.get("is_active", True)

    if not username:
        return jsonify({"error": "username is required"}), 400

    if role not in USER_ROLES:
        return jsonify({"error": "invalid role"}), 400

    if not isinstance(is_active, bool):
        return jsonify({"error": "is_active must be true or false"}), 400

    upsert_user(
        username=username,
        password_hash=password_hash,
        role=role,
        is_active=is_active,
    )

    return jsonify({"status": "ok"})


# Login-endpoint for dashboard-brugere.
# Brugeren findes i app_users, password kontrolleres med check_password_hash(), og last_login opdateres ved succes.
# Endpointet kræver stadig API-token, så login-formularen kun kan bruges af frontend der kender backend-tokenen.
@api_bp.post("/api/auth/login")
@require_api_token
def api_auth_login():
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid JSON payload"}), 400

    username = str(payload.get("username") or "").strip()
    password = payload.get("password") or ""

    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400

    user = get_user_by_username(username)

    if not user:
        return jsonify({"error": "invalid username or password"}), 401

    if not user.get("is_active"):
        return jsonify({"error": "user is disabled"}), 403

    password_hash = user.get("password_hash")
    if not password_hash or not check_password_hash(password_hash, password):
        return jsonify({"error": "invalid username or password"}), 401

    update_last_login(username)

    return jsonify({
        "status": "ok",
        "user": {
            "username": user["username"],
            "role": user["role"],
        },
    })


# Returnerer listen over kritiske Modbus-registre.
# Tabellen bruges som policy for hvilke registerændringer der skal fremhæves.
@api_bp.get("/api/critical-registers")
@require_api_token
def api_critical_registers():
    return jsonify(list_critical_registers())


# Opretter eller opdaterer et kritisk register.
# validate_critical_register_payload() sikrer at IP, unit_id, register_type og register_address er gyldige før data gemmes.
@api_bp.post("/api/critical-registers")
@require_api_token
def api_save_critical_register():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid JSON payload"}), 400

    validated_payload, error = validate_critical_register_payload(payload)
    if error:
        return jsonify({"error": error}), 400

    save_critical_register(validated_payload)
    return jsonify({"status": "ok"})


# Sletter et kritisk register ud fra dets id.
@api_bp.delete("/api/critical-registers/<int:register_id>")
@require_api_token
def api_delete_critical_register(register_id):
    delete_critical_register(register_id)
    return jsonify({"status": "ok"})


# Ændrer status på en device-række, f.eks. approve, block eller ignore.
# Først opdateres devices.status via update_device_status().
# Hvis payload også indeholder handled_by og alarm_key, gemmes brugerens beslutning som alarm approval.
# event_id er påkrævet i approval-flowet, så device-beslutningen kan kobles til den oprindelige event.
@api_bp.post("/api/devices/<int:device_id>/<action>")
@require_api_token
def api_update_device_status(device_id, action):
    allowed_actions = {
        "approve": "approved",
        "block": "blocked",
        "ignore": "ignored",
    }

    status = allowed_actions.get(action)
    if status is None:
        return jsonify({"error": "invalid action"}), 400

    updated = update_device_status(device_id, status)
    if not updated:
        return jsonify({"error": "device not found"}), 404

    payload = request.get_json(silent=True) or {}

    handled_by = str(payload.get("handled_by") or "").strip()
    alarm_key = str(payload.get("alarm_key") or "").strip()

    if handled_by and alarm_key:
        event_id = payload.get("event_id")
        if event_id is None:
            return jsonify({"error": "event_id is required"}), 400

        try:
            event_id = int(event_id)
        except (TypeError, ValueError):
            return jsonify({"error": "event_id must be an integer"}), 400

        save_alarm_approval({
            "alarm_key": alarm_key,
            "alarm_type": "device",
            "action": action,
            "status": status,
            "handled_by": handled_by,
            "event_id": event_id,
            "details": payload.get("details") or {},
        })

    return jsonify({"status": "ok"})
