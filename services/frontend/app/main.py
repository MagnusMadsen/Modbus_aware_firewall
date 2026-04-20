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
    return {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "sensor": {
            "status": "Online",
            "mode": "Inline enforcement",
            "interface": "eth1",
            "capture": "Running",
            "db": "Connected",
            "redis": "Connected",
            "policy_engine": "Active",
        },
        "kpis": [
            {"label": "Active Assets", "value": 14, "delta": "+2 this week", "severity": "normal"},
            {"label": "Active Sessions", "value": 9, "delta": "3 write-capable", "severity": "normal"},
            {"label": "Policy Violations", "value": 21, "delta": "+4 today", "severity": "warning"},
            {"label": "Blocked Requests", "value": 8, "delta": "2 critical", "severity": "critical"},
            {"label": "Critical Alerts", "value": 3, "delta": "1 unresolved", "severity": "critical"},
            {"label": "Writes / min", "value": 12, "delta": "above baseline", "severity": "warning"},
        ],
        "zones": [
            {"name": "SCADA", "value": "2 masters", "state": "normal"},
            {"name": "Control", "value": "4 PLC/RTU", "state": "warning"},
            {"name": "Supervision", "value": "1 HMI", "state": "normal"},
            {"name": "Quarantine", "value": "1 unknown host", "state": "critical"},
        ],
        "flows": [
            {
                "source": "SCADA-01",
                "src_ip": "10.168.40.21",
                "target": "PLC-03",
                "dst_ip": "10.168.40.13",
                "unit_id": 1,
                "service": "TCP/502",
                "state": "Blocked",
            },
            {
                "source": "ENG-WS-02",
                "src_ip": "10.168.40.33",
                "target": "RTU-07",
                "dst_ip": "10.168.40.27",
                "unit_id": 7,
                "service": "TCP/502",
                "state": "Monitored",
            },
            {
                "source": "HMI-01",
                "src_ip": "10.168.40.40",
                "target": "PLC-01",
                "dst_ip": "10.168.40.10",
                "unit_id": 1,
                "service": "TCP/502",
                "state": "Allowed",
            },
            {
                "source": "SCADA-02",
                "src_ip": "10.168.40.18",
                "target": "PLC-02",
                "dst_ip": "10.168.40.11",
                "unit_id": 2,
                "service": "TCP/502",
                "state": "Allowed",
            },
        ],
        "alerts": [
            {
                "severity": "Critical",
                "title": "Unauthorized write to critical holding register range",
                "asset": "PLC-03",
                "source": "10.168.40.21",
                "time": "10:14:22",
                "decision": "Blocked",
            },
            {
                "severity": "High",
                "title": "Register scan spike detected",
                "asset": "RTU-07",
                "source": "10.168.40.33",
                "time": "10:12:09",
                "decision": "Alerted",
            },
            {
                "severity": "Medium",
                "title": "New Modbus client observed on OT segment",
                "asset": "Unknown",
                "source": "10.168.40.54",
                "time": "09:58:51",
                "decision": "Monitored",
            },
        ],
        "modbus_summary": [
            {"label": "Read Coils (0x01)", "value": 18},
            {"label": "Read Holding Registers (0x03)", "value": 46},
            {"label": "Write Single Register (0x06)", "value": 9},
            {"label": "Write Multiple Registers (0x10)", "value": 5},
            {"label": "Exception Responses", "value": 4},
        ],
        "top_registers": [
            {"range": "40001-40010", "purpose": "Process telemetry", "writes": 0, "risk": "Low"},
            {"range": "40020-40030", "purpose": "Critical setpoints", "writes": 3, "risk": "High"},
            {"range": "40100-40120", "purpose": "Pump control", "writes": 2, "risk": "Medium"},
            {"range": "40200-40210", "purpose": "Maintenance flags", "writes": 1, "risk": "Medium"},
        ],
        "events": [
            {
                "time": "10:14:22",
                "severity": "Critical",
                "source": "10.168.40.21",
                "target": "PLC-03",
                "unit_id": 1,
                "function": "0x10",
                "registers": "40020-40024",
                "event": "Write multiple registers",
                "action": "Blocked",
            },
            {
                "time": "10:12:09",
                "severity": "High",
                "source": "10.168.40.33",
                "target": "RTU-07",
                "unit_id": 7,
                "function": "0x03",
                "registers": "40100-40120",
                "event": "Bulk register enumeration",
                "action": "Allowed",
            },
            {
                "time": "10:09:44",
                "severity": "Medium",
                "source": "10.168.40.18",
                "target": "PLC-01",
                "unit_id": 1,
                "function": "0x06",
                "registers": "40112",
                "event": "Single register write",
                "action": "Allowed",
            },
            {
                "time": "10:07:03",
                "severity": "Low",
                "source": "10.168.40.40",
                "target": "HMI-01",
                "unit_id": 1,
                "function": "0x03",
                "registers": "40001-40008",
                "event": "Read holding registers",
                "action": "Allowed",
            },
        ],
        "policies": [
            {
                "name": "SCADA write access to critical PLC ranges",
                "scope": "SCADA-01 -> PLC-03",
                "rule": "Allow writes only from approved master to 40020-40030",
                "hits": 11,
                "mode": "Enforce",
            },
            {
                "name": "Read-only engineering workstation",
                "scope": "ENG-WS-02 -> RTU-07",
                "rule": "Deny 0x05/0x06/0x0F/0x10",
                "hits": 4,
                "mode": "Enforce",
            },
            {
                "name": "Broadcast suppression",
                "scope": "All zones",
                "rule": "Block Unit ID 0 write requests",
                "hits": 2,
                "mode": "Enforce",
            },
            {
                "name": "Maintenance override",
                "scope": "PLC-02",
                "rule": "Temporary write window for 40100-40120",
                "hits": 1,
                "mode": "Monitor",
            },
        ],
        "assets": [
            {
                "name": "PLC-01",
                "ip": "10.168.40.10",
                "unit_id": 1,
                "role": "Controller",
                "status": "Online",
                "risk": "Medium",
                "writes": "Restricted",
                "last_seen": "10:15:02",
            },
            {
                "name": "PLC-03",
                "ip": "10.168.40.13",
                "unit_id": 1,
                "role": "Controller",
                "status": "Alert",
                "risk": "High",
                "writes": "Critical range protected",
                "last_seen": "10:14:22",
            },
            {
                "name": "RTU-07",
                "ip": "10.168.40.27",
                "unit_id": 7,
                "role": "RTU",
                "status": "Online",
                "risk": "Medium",
                "writes": "Read-heavy",
                "last_seen": "10:12:09",
            },
            {
                "name": "HMI-01",
                "ip": "10.168.40.40",
                "unit_id": 1,
                "role": "HMI",
                "status": "Online",
                "risk": "Low",
                "writes": "None",
                "last_seen": "10:13:41",
            },
        ],
        "inspector": {
            "source": "10.168.40.21",
            "destination": "10.168.40.13",
            "unit_id": 1,
            "transaction_id": 18422,
            "function_code": "0x10 Write Multiple Registers",
            "register_range": "40020-40024",
            "values": "[55, 55, 70, 80, 90]",
            "decision": "Blocked",
            "rule": "Unauthorized source for critical register range 40020-40030",
            "reason": "Source host is not in the approved writer list for PLC-03 critical setpoints.",
        },
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