import os
from db import get_connection
from psycopg2.extras import RealDictCursor

CAPTURE_INTERFACE = os.getenv("CAPTURE_INTERFACE", "eth0")


def get_device_count(cur):
    cur.execute("SELECT COUNT(*) AS count FROM devices;")
    return cur.fetchone()["count"]


def get_recent_packet_count(cur):
    cur.execute("""
        SELECT COUNT(*) AS count
        FROM packet_logs
        WHERE ts >= NOW() - INTERVAL '60 seconds'
    """)
    return cur.fetchone()["count"]


def get_recent_arp_count(cur):
    cur.execute("""
        SELECT COUNT(*) AS count
        FROM packet_logs
        WHERE protocol = 'ARP'
          AND ts >= NOW() - INTERVAL '60 seconds'
    """)
    return cur.fetchone()["count"]


def get_traffic_rows(cur):
    cur.execute("""
        SELECT
            TO_CHAR(date_trunc('minute', ts), 'HH24:MI') AS time,
            COUNT(*) AS traffic
        FROM packet_logs
        WHERE ts >= NOW() - INTERVAL '10 minutes'
        GROUP BY date_trunc('minute', ts)
        ORDER BY date_trunc('minute', ts)
    """)
    return cur.fetchall()


def build_combined_series(traffic_rows):
    return [
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


def fetch_summary():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    device_count = get_device_count(cur)
    recent_packets = get_recent_packet_count(cur)
    arp_packets = get_recent_arp_count(cur)
    traffic_rows = get_traffic_rows(cur)
    connections = get_observed_connections(cur)
    device_roles = get_device_roles(cur)

    cur.close()
    conn.close()

    combined_series = build_combined_series(traffic_rows)

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
        "connections": connections,
        "device_roles": device_roles,
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

def get_device_roles(cur):
    cur.execute("""
        SELECT
            ip,
            COUNT(DISTINCT peer_ip) AS peer_count,
            CASE
                WHEN COUNT(DISTINCT peer_ip) = 0 THEN 'unknown'
                WHEN COUNT(DISTINCT peer_ip) = 1 THEN 'slave'
                ELSE 'master'
            END AS role
        FROM (
            SELECT src_ip AS ip, dst_ip AS peer_ip
            FROM observed_connections
            WHERE src_ip IS NOT NULL AND dst_ip IS NOT NULL

            UNION

            SELECT dst_ip AS ip, src_ip AS peer_ip
            FROM observed_connections
            WHERE src_ip IS NOT NULL AND dst_ip IS NOT NULL
        ) peers
        GROUP BY ip
        ORDER BY peer_count DESC, ip
    """)
    return cur.fetchall()

def get_observed_connections(cur):
    cur.execute("""
        SELECT
            src_ip,
            dst_ip,
            protocol,
            src_port,
            dst_port,
            first_seen,
            last_seen,
            packet_count
        FROM observed_connections
        ORDER BY last_seen DESC
        LIMIT 20
    """)
    return cur.fetchall()

