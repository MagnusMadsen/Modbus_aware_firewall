from flask import Flask, render_template, request, redirect, url_for, session, flash
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.security import check_password_hash
import os


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
    traffic_points = [
        {"time": "00", "value": 18},
        {"time": "02", "value": 16},
        {"time": "04", "value": 15},
        {"time": "06", "value": 19},
        {"time": "08", "value": 42},
        {"time": "10", "value": 58},
        {"time": "12", "value": 51},
        {"time": "14", "value": 47},
        {"time": "16", "value": 53},
        {"time": "18", "value": 49},
        {"time": "20", "value": 28},
        {"time": "22", "value": 21},
    ]

    latency_points = [
        {"time": "00", "value": 0.5},
        {"time": "02", "value": 0.5},
        {"time": "04", "value": 0.4},
        {"time": "06", "value": 0.5},
        {"time": "08", "value": 0.7},
        {"time": "10", "value": 1.1},
        {"time": "12", "value": 1.4},
        {"time": "14", "value": 1.5},
        {"time": "16", "value": 1.3},
        {"time": "18", "value": 1.0},
        {"time": "20", "value": 0.8},
        {"time": "22", "value": 0.6},
    ]

    max_traffic = max(point["value"] for point in traffic_points)
    max_latency = max(point["value"] for point in latency_points)

    for point in traffic_points:
        point["height"] = max(16, int((point["value"] / max_traffic) * 180))

    for point in latency_points:
        point["height"] = max(16, int((point["value"] / max_latency) * 180))

    return {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "sensor": {
            "status": "Online",
            "mode": "Inline enforcement",
            "interface": "eth1",
        },
        "summary": [
            {"label": "Online devices", "value": 14, "note": "2 masters · 4 PLC/RTU · 1 HMI"},
            {"label": "Disconnected links", "value": 2, "note": "1 master affected"},
            {"label": "Average latency", "value": "1.5 s", "note": "was 0.5 s baseline"},
            {"label": "Active ports", "value": "5 / 8", "note": "3 inactive on Westermo"},
        ],
        "traffic_points": traffic_points,
        "traffic_note": "Traffic spike detected around 10:00-18:00 compared to night baseline.",
        "latency_points": latency_points,
        "latency_note": "Latency increased from normal 0.5 s to peak 1.5 s during daytime activity.",
        "connections": [
            {
                "master": "SCADA-01",
                "slave": "PLC-01",
                "status": "Connected",
                "downtime": "0 min",
                "last_change": "Stable",
            },
            {
                "master": "SCADA-01",
                "slave": "PLC-03",
                "status": "Interrupted",
                "downtime": "7 min",
                "last_change": "10:14",
            },
            {
                "master": "HMI-01",
                "slave": "RTU-07",
                "status": "Connected",
                "downtime": "0 min",
                "last_change": "Stable",
            },
            {
                "master": "ENG-WS-02",
                "slave": "RTU-07",
                "status": "Unstable",
                "downtime": "2 min",
                "last_change": "10:12",
            },
        ],
        "ports": [
            {"port": "Port 1", "name": "SCADA-01", "state": "active", "speed": "100 Mbps", "activity": "High"},
            {"port": "Port 2", "name": "PLC-01", "state": "active", "speed": "100 Mbps", "activity": "Medium"},
            {"port": "Port 3", "name": "PLC-03", "state": "active", "speed": "100 Mbps", "activity": "High"},
            {"port": "Port 4", "name": "RTU-07", "state": "active", "speed": "100 Mbps", "activity": "Medium"},
            {"port": "Port 5", "name": "HMI-01", "state": "active", "speed": "100 Mbps", "activity": "Low"},
            {"port": "Port 6", "name": "Unused", "state": "inactive", "speed": "-", "activity": "None"},
            {"port": "Port 7", "name": "Unused", "state": "inactive", "speed": "-", "activity": "None"},
            {"port": "Port 8", "name": "Service laptop", "state": "inactive", "speed": "-", "activity": "None"},
        ],
        "events": [
            {
                "time": "10:14",
                "type": "Link interruption",
                "details": "SCADA-01 lost communication to PLC-03",
                "impact": "Write commands delayed",
            },
            {
                "time": "10:12",
                "type": "Latency increase",
                "details": "Average Modbus request time increased above 1.0 s",
                "impact": "Slower operator feedback",
            },
            {
                "time": "09:58",
                "type": "Traffic spike",
                "details": "Traffic volume above night baseline",
                "impact": "Needs review",
            },
        ],
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