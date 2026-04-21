import os
from db import get_connection
from psycopg2.extras import RealDictCursor

CAPTURE_INTERFACE = os.getenv("CAPTURE_INTERFACE", "eth0")

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

    cur.execute("""
        SELECT
            TO_CHAR(date_trunc('minute', ts), 'HH24:MI') AS time,
            COUNT(*) AS traffic
        FROM packet_logs
        WHERE ts >= NOW() - INTERVAL '10 minutes'
        GROUP BY date_trunc('minute', ts)
        ORDER BY date_trunc('minute', ts)
    """)
    traffic_rows = cur.fetchall()

    cur.close()
    conn.close()

    combined_series = [
        {
            "time": row["time"],
            "traffic": row["traffic"],
            "latency": 0,
            "traffic_baseline": 0,
            "latency_baseline": 0,
            "latency_threshold": 0,
            "failed_requests": 0,
            "downtime": False,
        }
        for row in traffic_rows
    ]

    return {
        "generated_at": "live",
        "sensor": {
            "status": "Online",
            "mode": "Passive monitoring",
            "interface": CAPTURE_INTERFACE,
        },
        "summary": [
            {"label": "Online devices", "value": device_count, "note": "Observed in SQL"},
            {"label": "Packets last 60s", "value": recent_packets, "note": "Live capture"},
            {"label": "ARP last 60s", "value": arp_packets, "note": "Live capture"},
        ],
        "combined_series": combined_series,
        "chart_events": [],
        "combined_note": "Live traffic from packet_logs. Latency not implemented yet.",
        "arp_monitor": {
            "status": "Normal",
            "summary": f"{arp_packets} ARP packets last 60s",
            "gateway_ip": "-",
            "gateway_expected_mac": "-",
            "gateway_seen_mac": "-",
            "critical_pairs": [],
            "events": [],
        },
        "connections": [],
        "ports": [],
        "events": [],
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

