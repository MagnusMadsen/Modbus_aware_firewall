import hmac
import os
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


@api_bp.route("/api/critical-registers", methods=["POST"])
def api_save_critical_register():
    auth_error = require_api_token()
    if auth_error:
        return auth_error

    payload = request.get_json(force=True)
    save_critical_register(payload)
    return jsonify({"status": "ok"})


@api_bp.route("/api/critical-registers/<int:register_id>", methods=["DELETE"])
def api_delete_critical_register(register_id):
    auth_error = require_api_token()
    if auth_error:
        return auth_error

    delete_critical_register(register_id)
    return jsonify({"status": "ok"})