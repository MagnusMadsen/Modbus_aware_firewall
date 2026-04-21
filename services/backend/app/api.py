from flask import Blueprint, jsonify
from dashboard import fetch_summary, fetch_devices

api_bp = Blueprint("api", __name__)


@api_bp.route("/health")
def health():
    return jsonify({"status": "ok", "service": "backend"})


@api_bp.route("/api/dashboard")
def api_dashboard():
    return jsonify(fetch_summary())


@api_bp.route("/api/devices")
def api_devices():
    return jsonify(fetch_devices())