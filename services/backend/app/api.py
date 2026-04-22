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

@api_bp.route("/api/critical-registers", methods=["GET"])
def api_critical_registers():
    return jsonify(fetch_critical_registers())

@api_bp.route("/api/critical-registers", methods=["POST"])
def api_create_critical_register():
    payload = request.get_json(force=True)
    return jsonify(save_critical_register(payload))

@api_bp.route("/api/critical-registers/<int:register_id>", methods=["DELETE"])
def api_delete_critical_register(register_id):
    delete_critical_register(register_id)
    return jsonify({"status": "ok"})

