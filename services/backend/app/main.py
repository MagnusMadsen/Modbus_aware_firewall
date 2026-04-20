from flask import Flask, jsonify
from capture import start_capture
from parser import parse_packet
from db import get_connection
from psycopg2.extras import RealDictCursor

import threading
import os

CAPTURE_INTERFACE = os.getenv("CAPTURE_INTERFACE", "eth0")

app = Flask(__name__)

def save_packet(data):
    print("PACKET:", data, flush=True)

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO packet_logs (src_mac, dst_mac, src_ip, dst_ip, protocol, src_port, dst_port, length)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            data["src_mac"],
            data["dst_mac"],
            data["src_ip"],
            data["dst_ip"],
            data["protocol"],
            data["src_port"],
            data["dst_port"],
            data["length"],
        ),
    )

    if data["src_mac"] and data["src_ip"] and data["src_ip"] != "0.0.0.0":
        cur.execute(
            """
            INSERT INTO devices (ip, mac, first_seen, last_seen)
            VALUES (%s, %s, NOW(), NOW())
            ON CONFLICT (ip, mac)
            DO UPDATE SET last_seen = NOW()
            """,
            (data["src_ip"], data["src_mac"]),
        )

    conn.commit()
    cur.close()
    conn.close()

def run_capture():
    start_capture(CAPTURE_INTERFACE, lambda pkt: save_packet(parse_packet(pkt)))

def start_capture_thread():
    thread = threading.Thread(target=run_capture, daemon=True)
    thread.start()


def fetch_summary():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT COUNT(*) AS count FROM devices;")
    device_count = cur.fetchone()["count"]

    cur.execute("""
        SELECT COUNT(*) AS count
        FROM packet_logs
        WHERE ts >= NOW() - INTERVAL '60 seconds'
    """)
    recent_packets = cur.fetchone()["count"]

    cur.execute("""
        SELECT COUNT(*) AS count
        FROM packet_logs
        WHERE protocol = 'ARP'
          AND ts >= NOW() - INTERVAL '60 seconds'
    """)
    arp_packets = cur.fetchone()["count"]

    cur.close()
    conn.close()

    return {
        "generated_at": "live",
        "summary": [
            {"label": "Online devices", "value": device_count, "note": "Observed in SQL"},
            {"label": "Packets last 60s", "value": recent_packets, "note": "Live capture"},
            {"label": "ARP last 60s", "value": arp_packets, "note": "Live capture"},
        ]
    }

def fetch_devices():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT ip, mac, first_seen, last_seen
        FROM devices
        ORDER BY last_seen DESC
    """)
    rows = cur.fetchall()

    cur.close()
    conn.close()
    return rows

@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "backend"})

@app.route("/api/dashboard")
def api_dashboard():
    return jsonify(fetch_summary())

@app.route("/api/devices")
def api_devices():
    return jsonify(fetch_devices())

if __name__ == "__main__":
    start_capture_thread()
    app.run(host="0.0.0.0", port=8000, debug=False)