from flask import Flask, render_template, request, redirect, url_for, session, flash
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

app.secret_key = read_secret("frontend_secret_key")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=1),
)

USERNAME = os.getenv("APP_USERNAME")
if not USERNAME:
    raise RuntimeError("APP_USERNAME is not set")

PASSWORD_HASH = read_secret("frontend_password_hash")


def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)
    return wrapped_view


def get_dashboard_data():
    try:
        dashboard_resp = requests.get(f"{API_BASE_URL}/api/dashboard", timeout=5)
        dashboard_resp.raise_for_status()
        data = dashboard_resp.json()

        devices_resp = requests.get(f"{API_BASE_URL}/api/devices", timeout=5)
        devices_resp.raise_for_status()
        devices = devices_resp.json()

        data["devices"] = devices
        return data

    except Exception as exc:
        return {
            "generated_at": "backend unavailable",
            "summary": [
                {"label": "Online devices", "value": 0, "note": str(exc)},
                {"label": "Packets last 60s", "value": 0, "note": "No backend data"},
                {"label": "ARP last 60s", "value": 0, "note": "No backend data"},
            ],
            "devices": [],
        }

@app.route("/login", methods=["GET", "POST"])
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)