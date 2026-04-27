

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from datetime import datetime, timedelta
from functools import wraps
from werkzeug.security import check_password_hash
import os
import requests


def read_secret(secret_name: str) -> str:
    path = f"/run/secrets/{secret_name}"
    try:
        with open(path, "r", encoding="utf-8") as f:
            value = f.read().strip()
    except FileNotFoundError as exc:
        raise RuntimeError(f"Missing required secret: {secret_name}") from exc

    if not value:
        raise RuntimeError(f"Secret is empty: {secret_name}")

    return value


app = Flask(__name__)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
)

app.secret_key = read_secret("frontend_secret_key")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("APP_ENV") == "production",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=1),
)

USERNAME = os.getenv("APP_USERNAME")
if not USERNAME:
    raise RuntimeError("APP_USERNAME is not set")

PASSWORD_HASH = read_secret("frontend_password_hash")
BACKEND_API_TOKEN = read_secret("backend_api_token")
API_BASE_URL = os.getenv("API_BASE_URL", "http://host.docker.internal:8000")

def backend_headers() -> dict:
    return {
        "X-API-Token": BACKEND_API_TOKEN
    }


def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)
    return wrapped_view


def get_dashboard_data():
    data = {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "sensor": {
            "status": "Online",
            "mode": "Passive monitoring",
            "interface": "eth0",
        },
        "arp_monitor": {
            "status": "Normal",
            "summary": "No ARP alerts yet",
            "gateway_ip": "-",
            "gateway_expected_mac": "-",
            "gateway_seen_mac": "-",
            "critical_pairs": [],
            "events": [],
        },
        "summary": [
            {"label": "Online devices", "value": 0, "note": "Observed in SQL"},
            {"label": "Packets last 60s", "value": 0, "note": "Live capture"},
            {"label": "ARP last 60s", "value": 0, "note": "Live capture"},
        ],
        "combined_series": [],
        "chart_events": [],
        "combined_note": "Traffic and latency data will appear here when available.",
        "connections": [],
        "ports": [],
        "events": [],
        "devices": [],
    }

    try:
        dashboard_resp = requests.get(
                f"{API_BASE_URL}/api/dashboard",
                headers=backend_headers(),
                timeout=5,
            )
        dashboard_resp.raise_for_status()
        dashboard_json = dashboard_resp.json()

        devices_resp = requests.get(
                f"{API_BASE_URL}/api/devices",
                headers=backend_headers(),
                timeout=5,
            )
        devices_resp.raise_for_status()
        devices_json = devices_resp.json()

        data["generated_at"] = dashboard_json.get("generated_at", data["generated_at"])
        data["sensor"] = dashboard_json.get("sensor", data["sensor"])
        data["summary"] = dashboard_json.get("summary", data["summary"])
        data["combined_series"] = dashboard_json.get("combined_series", data["combined_series"])
        data["chart_events"] = dashboard_json.get("chart_events", data["chart_events"])
        data["combined_note"] = dashboard_json.get("combined_note", data["combined_note"])
        data["arp_monitor"] = dashboard_json.get("arp_monitor", data["arp_monitor"])
        data["connections"] = dashboard_json.get("connections", data["connections"])
        data["ports"] = dashboard_json.get("ports", data["ports"])
        data["events"] = dashboard_json.get("events", data["events"])
        data["devices"] = devices_json

    except Exception as exc:
        data["summary"] = [
            {"label": "Online devices", "value": 0, "note": str(exc)},
            {"label": "Packets last 60s", "value": 0, "note": "No backend data"},
            {"label": "ARP last 60s", "value": 0, "note": "No backend data"},
        ]

    return data


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("3 per minute")
def login():
    if session.get("authenticated"):
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if username == USERNAME and check_password_hash(PASSWORD_HASH, password):
            session.clear()
            session["authenticated"] = True
            session["username"] = username
            session.permanent = True
            return redirect(url_for("index"))

        flash("Invalid username or password", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    return render_template(
        "dashboard.html",
        data=get_dashboard_data(),
        username=session.get("username")
    )


@app.route("/api/live-dashboard")
@login_required
def live_dashboard():
    return jsonify(get_dashboard_data())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)