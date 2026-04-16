from flask import Flask, render_template
from datetime import datetime

app = Flask(__name__)


@app.route("/")
def index():
    dashboard_data = {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "sensor": {
            "status": "Online",
            "interface": "eth1",
            "db": "Connected",
            "redis": "Connected",
            "capture": "Running",
        },
        "kpis": [
            {"label": "Active Alerts", "value": 3, "delta": "+1 last hour", "severity": "critical"},
            {"label": "Events 24h", "value": 1482, "delta": "+12%", "severity": "normal"},
            {"label": "Known Assets", "value": 14, "delta": "2 new", "severity": "normal"},
            {"label": "Write Requests", "value": 67, "delta": "5 blocked", "severity": "warning"},
            {"label": "Top Talkers", "value": 6, "delta": "stable", "severity": "normal"},
            {"label": "Policy Hits", "value": 21, "delta": "+4 today", "severity": "warning"},
        ],
        "alerts": [
            {
                "severity": "Critical",
                "title": "Unauthorized write to holding registers",
                "asset": "PLC-03",
                "source": "10.168.40.21",
                "time": "10:14:22",
            },
            {
                "severity": "High",
                "title": "Register scan spike detected",
                "asset": "RTU-07",
                "source": "10.168.40.33",
                "time": "10:12:09",
            },
            {
                "severity": "Medium",
                "title": "New client observed on OT segment",
                "asset": "Unknown",
                "source": "10.168.40.54",
                "time": "09:58:51",
            },
        ],
        "events": [
            {
                "time": "10:14:22",
                "severity": "Critical",
                "source": "10.168.40.21",
                "target": "PLC-03",
                "function": "0x10",
                "event": "Write multiple registers",
                "action": "Blocked",
            },
            {
                "time": "10:12:09",
                "severity": "High",
                "source": "10.168.40.33",
                "target": "RTU-07",
                "function": "0x03",
                "event": "Bulk register enumeration",
                "action": "Allowed",
            },
            {
                "time": "10:09:44",
                "severity": "Medium",
                "source": "10.168.40.18",
                "target": "PLC-01",
                "function": "0x06",
                "event": "Single register write",
                "action": "Allowed",
            },
            {
                "time": "10:07:03",
                "severity": "Low",
                "source": "10.168.40.12",
                "target": "HMI-01",
                "function": "0x03",
                "event": "Read holding registers",
                "action": "Allowed",
            },
        ],
        "assets": [
            {"name": "PLC-01", "ip": "10.168.40.10", "role": "Controller", "status": "Online", "risk": "Medium", "last_seen": "10:15:02"},
            {"name": "PLC-03", "ip": "10.168.40.13", "role": "Controller", "status": "Alert", "risk": "High", "last_seen": "10:14:22"},
            {"name": "RTU-07", "ip": "10.168.40.27", "role": "RTU", "status": "Online", "risk": "Medium", "last_seen": "10:12:09"},
            {"name": "HMI-01", "ip": "10.168.40.40", "role": "HMI", "status": "Online", "risk": "Low", "last_seen": "10:13:41"},
        ],
        "traffic": [
            {"label": "Read Coils (0x01)", "value": 18},
            {"label": "Read Holding Registers (0x03)", "value": 46},
            {"label": "Write Single Register (0x06)", "value": 9},
            {"label": "Write Multiple Registers (0x10)", "value": 5},
        ],
    }

    return render_template("dashboard.html", data=dashboard_data)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)