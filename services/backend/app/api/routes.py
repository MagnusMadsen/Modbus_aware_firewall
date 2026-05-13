from flask import Blueprint, jsonify, request

from api.auth import require_api_token
from api.validators import validate_critical_register_payload
from dashboard.service import fetch_devices, fetch_summary
from storage import (
    delete_critical_register,
    list_critical_registers,
    save_critical_register,
)
from storage.devices import update_device_status

api_bp = Blueprint("api", __name__)


@api_bp.get("/health")
def health():
    return jsonify({"status": "ok", "service": "backend"})


@api_bp.get("/api/dashboard")
@require_api_token
def api_dashboard():
    return jsonify(fetch_summary())


@api_bp.get("/api/devices")
@require_api_token
def api_devices():
    return jsonify(fetch_devices())


@api_bp.get("/api/critical-registers")
@require_api_token
def api_critical_registers():
    return jsonify(list_critical_registers())


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


@api_bp.delete("/api/critical-registers/<int:register_id>")
@require_api_token
def api_delete_critical_register(register_id):
    delete_critical_register(register_id)
    return jsonify({"status": "ok"})


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

    return jsonify({"status": "ok"})