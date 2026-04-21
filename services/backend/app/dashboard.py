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
    connections = get_master_slave_groups(cur)
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


def get_master_slave_groups(cur):
    cur.execute("""
        WITH peer_stats AS (
            SELECT
                ip,
                COUNT(DISTINCT peer_ip) AS peer_count
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
        ),
        relation_stats AS (
            SELECT
                a.ip AS ip_a,
                b.ip AS ip_b,
                a.peer_count AS peer_count_a,
                b.peer_count AS peer_count_b
            FROM peer_stats a
            JOIN peer_stats b ON a.ip < b.ip
        ),
        directed_relations AS (
            SELECT
                CASE
                    WHEN peer_count_a > peer_count_b THEN ip_a
                    WHEN peer_count_b > peer_count_a THEN ip_b
                    ELSE LEAST(ip_a, ip_b)
                END AS master_ip,
                CASE
                    WHEN peer_count_a > peer_count_b THEN ip_b
                    WHEN peer_count_b > peer_count_a THEN ip_a
                    ELSE GREATEST(ip_a, ip_b)
                END AS slave_ip
            FROM relation_stats
        ),
        aggregated_relations AS (
            SELECT
                dr.master_ip,
                dr.slave_ip,
                SUM(oc.packet_count) AS packets,
                MAX(oc.last_seen) AS last_seen
            FROM directed_relations dr
            JOIN observed_connections oc
              ON (
                   (oc.src_ip = dr.master_ip AND oc.dst_ip = dr.slave_ip)
                OR (oc.src_ip = dr.slave_ip AND oc.dst_ip = dr.master_ip)
              )
            GROUP BY dr.master_ip, dr.slave_ip
        )
        SELECT
            master_ip,
            slave_ip,
            packets,
            last_seen
        FROM aggregated_relations
        ORDER BY master_ip, slave_ip
    """)
    rows = cur.fetchall()

    groups = {}
    for row in rows:
        master = row["master_ip"]
        if master not in groups:
            groups[master] = {
                "master": master,
                "slave_count": 0,
                "last_seen": row["last_seen"],
                "slaves": [],
            }

        groups[master]["slaves"].append({
            "ip": row["slave_ip"],
            "status": "online",
            "packets": row["packets"],
            "last_seen": row["last_seen"],
        })

        groups[master]["slave_count"] += 1

        if row["last_seen"] and row["last_seen"] > groups[master]["last_seen"]:
            groups[master]["last_seen"] = row["last_seen"]

    return list(groups.values())