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
            {"label": "Critical Alerts", "value": 3, "delta": "1 requires action", "severity": "critical"},
            {"label": "Blocked Writes", "value": 8, "delta": "2 on critical PLC", "severity": "critical"},
            {"label": "Allowed Reads", "value": 146, "delta": "normal traffic", "severity": "normal"},
            {"label": "Known Assets", "value": 14, "delta": "1 unclassified", "severity": "warning"},
            {"label": "Write Requests", "value": 12, "delta": "above baseline", "severity": "warning"},
            {"label": "Policy Hits", "value": 21, "delta": "+4 today", "severity": "warning"},
        ],
        "zones": [
            {"name": "SCADA", "value": "2 approved masters", "state": "normal"},
            {"name": "Control", "value": "4 PLC/RTU", "state": "warning"},
            {"name": "Operations", "value": "1 HMI", "state": "normal"},
            {"name": "Unknown", "value": "1 host needs review", "state": "critical"},
        ],
        "network_nodes": [
            {"name": "SCADA-01", "ip": "10.168.40.21", "role": "Master", "status": "critical", "x": "12%", "y": "20%"},
            {"name": "ENG-WS-02", "ip": "10.168.40.33", "role": "Engineering", "status": "warning", "x": "18%", "y": "68%"},
            {"name": "HMI-01", "ip": "10.168.40.40", "role": "HMI", "status": "normal", "x": "44%", "y": "50%"},
            {"name": "PLC-01", "ip": "10.168.40.10", "role": "PLC", "status": "normal", "x": "76%", "y": "20%"},
            {"name": "PLC-03", "ip": "10.168.40.13", "role": "PLC", "status": "critical", "x": "79%", "y": "50%"},
            {"name": "RTU-07", "ip": "10.168.40.27", "role": "RTU", "status": "warning", "x": "75%", "y": "78%"},
        ],
        "network_links": [
            {"from_x": "18%", "from_y": "24%", "to_x": "73%", "to_y": "22%", "state": "allowed", "label": "0x03 Read"},
            {"from_x": "18%", "from_y": "24%", "to_x": "76%", "to_y": "50%", "state": "blocked", "label": "0x10 Write"},
            {"from_x": "24%", "from_y": "72%", "to_x": "73%", "to_y": "78%", "state": "warning", "label": "Scan spike"},
            {"from_x": "47%", "from_y": "53%", "to_x": "72%", "to_y": "22%", "state": "allowed", "label": "0x03 Read"},
        ],
        "timeline": [
            {"time": "09:55", "allowed": 22, "blocked": 1},
            {"time": "10:00", "allowed": 26, "blocked": 1},
            {"time": "10:05", "allowed": 21, "blocked": 2},
            {"time": "10:10", "allowed": 18, "blocked": 4},
            {"time": "10:15", "allowed": 20, "blocked": 6},
            {"time": "10:20", "allowed": 24, "blocked": 3},
        ],
        "function_mix": [
            {"label": "0x01", "name": "Read Coils", "value": 18, "pct": 22},
            {"label": "0x03", "name": "Read Holding", "value": 46, "pct": 58},
            {"label": "0x06", "name": "Write Single", "value": 9, "pct": 11},
            {"label": "0x10", "name": "Write Multiple", "value": 5, "pct": 9},
        ],
        "register_heatmap": [
            {"range": "40001-40010", "label": "Telemetry", "level": 28, "risk": "low"},
            {"range": "40020-40030", "label": "Critical setpoints", "level": 94, "risk": "critical"},
            {"range": "40100-40120", "label": "Pump control", "level": 71, "risk": "warning"},
            {"range": "40200-40210", "label": "Maintenance", "level": 36, "risk": "warning"},
            {"range": "40300-40310", "label": "Reserved", "level": 12, "risk": "low"},
        ],
        "operator_actions": [
            {
                "priority": "Immediate",
                "title": "Investigate blocked write to PLC-03",
                "text": "Unauthorized write attempt against critical setpoint range 40020-40024 from SCADA-01.",
                "owner": "Production technician",
            },
            {
                "priority": "High",
                "title": "Verify engineering workstation mode",
                "text": "ENG-WS-02 is generating abnormal read sweep against RTU-07 and may be scanning.",
                "owner": "OT responsible",
            },
            {
                "priority": "Normal",
                "title": "Review unknown host classification",
                "text": "New client on OT segment should be assigned policy or isolated.",
                "owner": "Network admin",
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
                "target": "PLC-01",
                "unit_id": 1,
                "function": "0x03",
                "registers": "40001-40008",
                "event": "Read holding registers",
                "action": "Allowed",
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