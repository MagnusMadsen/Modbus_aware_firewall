import hmac
import os
import ipaddress
from pathlib import Path

from flask import Blueprint, jsonify, request

from dashboard import fetch_summary, fetch_devices
from storage import (
    list_critical_registers,
    save_critical_register,
    delete_critical_register,
)

api_bp = Blueprint("api", __name__)

def read_secret_env(name: str) -> str:
    file_path = os.getenv(f"{name}_FILE")

    if file_path:
        value = Path(file_path).read_text(encoding="utf-8").strip()
    else:
        value = os.getenv(name, "").strip()

    if not value:
        raise RuntimeError(f"Missing required secret or environment variable: {name}")

    return value


BACKEND_API_TOKEN = read_secret_env("BACKEND_API_TOKEN")


def require_api_token():
    provided_token = request.headers.get("X-API-Token", "")

    if not hmac.compare_digest(provided_token, BACKEND_API_TOKEN):
        return jsonify({"error": "unauthorized"}), 401

    return None


@api_bp.route("/health")
def health():
    return jsonify({"status": "ok", "service": "backend"})


@api_bp.route("/api/dashboard")
def api_dashboard():
    auth_error = require_api_token()
    if auth_error:
        return auth_error

    return jsonify(fetch_summary())


@api_bp.route("/api/devices")
def api_devices():
    auth_error = require_api_token()
    if auth_error:
        return auth_error

    return jsonify(fetch_devices())


@api_bp.route("/api/critical-registers", methods=["GET"])
def api_critical_registers():
    auth_error = require_api_token()
    if auth_error:
        return auth_error

    return jsonify(list_critical_registers())


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

    pin_on_change = bool(payload.get("pin_on_change", True))
    is_enabled = bool(payload.get("is_enabled", True))

    return {
        "slave_ip": slave_ip,
        "unit_id": unit_id,
        "register_type": register_type,
        "register_address": register_address,
        "label": label,
        "allowed_values": allowed_values,
        "pin_on_change": pin_on_change,
        "is_enabled": is_enabled,
    }, None


@api_bp.route("/api/critical-registers", methods=["POST"])
def api_save_critical_register():
    auth_error = require_api_token()
    if auth_error:
        return auth_error

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid JSON payload"}), 400

    validated_payload, error = validate_critical_register_payload(payload)
    if error:
        return jsonify({"error": error}), 400

    save_critical_register(validated_payload)
    return jsonify({"status": "ok"})


@api_bp.route("/api/critical-registers/<int:register_id>", methods=["DELETE"])
def api_delete_critical_register(register_id):
    auth_error = require_api_token()
    if auth_error:
        return auth_error

    delete_critical_register(register_id)
    return jsonify({"status": "ok"})