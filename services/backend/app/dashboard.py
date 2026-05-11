import os
from datetime import datetime

from psycopg2.extras import RealDictCursor

from switch_monitor import get_switch_ports, get_mac_to_port_map

from db import get_connection

CAPTURE_INTERFACE = os.getenv("CAPTURE_INTERFACE", "eth0")


def get_device_count(cur):
    cur.execute("SELECT COUNT(*) AS count FROM devices;")
    return cur.fetchone()["count"]


def get_recent_metrics(cur):
    cur.execute(
        """
        SELECT
            COALESCE(SUM(traffic_count), 0) AS traffic_count,
            COALESCE(SUM(request_count), 0) AS request_count,
            COALESCE(SUM(response_count), 0) AS response_count,
            COALESCE(SUM(failed_count), 0) AS failed_count,
            COALESCE(SUM(arp_count), 0) AS arp_count,
            ROUND(AVG(avg_latency_ms)::numeric, 2) AS avg_latency_ms
        FROM metrics_bucket
        WHERE bucket_ts >= NOW() - INTERVAL '60 seconds'
        """
    )
    return cur.fetchone()


def get_combined_series(cur):
    cur.execute(
        """
        SELECT
            bucket_ts,
            TO_CHAR(bucket_ts, 'HH24:MI:SS') AS time,
            traffic_count AS traffic,
            COALESCE(avg_latency_ms, 0) AS latency,
            failed_count AS failed_requests,
            CASE WHEN traffic_count = 0 THEN TRUE ELSE FALSE END AS downtime
        FROM metrics_bucket
        WHERE bucket_ts >= NOW() - INTERVAL '30 minutes'
        ORDER BY bucket_ts
        """
    )
    rows = cur.fetchall()

    series = []
    traffic_history = []
    latency_history = []

    for row in rows:
        traffic = row["traffic"] or 0
        latency = row["latency"] or 0

        traffic_history.append(traffic)
        if latency > 0:
            latency_history.append(latency)

        traffic_baseline = round(sum(traffic_history) / len(traffic_history), 2) if traffic_history else 0
        latency_baseline = round(sum(latency_history) / len(latency_history), 2) if latency_history else 0
        latency_threshold = round(latency_baseline * 1.5, 2) if latency_baseline else 0

        series.append(
            {
                "time": row["time"],
                "traffic": traffic,
                "latency": latency,
                "traffic_baseline": traffic_baseline,
                "latency_baseline": latency_baseline,
                "latency_threshold": latency_threshold,
                "failed_requests": row["failed_requests"] or 0,
                "downtime": bool(row["downtime"]),
            }
        )

    return series


def get_chart_events(cur):
    cur.execute(
        """
        SELECT
            TO_CHAR(ts, 'HH24:MI:SS') AS time,
            event_type,
            severity,
            source_ip::text AS source_ip,
            target_ip::text AS target_ip,
            register_address,
            old_value,
            new_value
        FROM events
        WHERE ts >= NOW() - INTERVAL '30 minutes'
        ORDER BY ts DESC
        LIMIT 50
        """
    )
    rows = cur.fetchall()

    events = []
    for row in rows:
        label = row["event_type"]
        if row["register_address"] is not None:
            label = f"{row['event_type']} reg {row['register_address']}"

        events.append(
            {
                "time": row["time"],
                "label": label,
                "severity": row["severity"],
            }
        )

    return list(reversed(events))


def get_recent_events(cur):
    cur.execute(
        """
        SELECT
            TO_CHAR(ts, 'YYYY-MM-DD HH24:MI:SS') AS time,
            event_type,
            severity,
            source_ip::text AS source_ip,
            target_ip::text AS target_ip,
            register_address,
            old_value,
            new_value,
            details
        FROM events
        ORDER BY
            COALESCE((details->>'is_pinned')::boolean, FALSE) DESC,
            ts DESC
        LIMIT 20
        """
    )
    rows = cur.fetchall()

    events = []
    for row in rows:
        parts = []

        if row["source_ip"] and row["target_ip"]:
            parts.append(f"{row['source_ip']} -> {row['target_ip']}")

        if row["register_address"] is not None:
            parts.append(f"register {row['register_address']}")

        if row["old_value"] is not None or row["new_value"] is not None:
            parts.append(f"{row['old_value']} -> {row['new_value']}")

        is_pinned = bool((row["details"] or {}).get("is_pinned", False))
        pin_reason = (row["details"] or {}).get("pin_reason")
        critical_label = (row["details"] or {}).get("critical_label")

        details = row["details"] or {}
        message = details.get("message", row["event_type"])

        impact_parts = [message]

        if critical_label:
            impact_parts.append(f"Critical register: {critical_label}")

        if pin_reason:
            impact_parts.append(f"Reason: {pin_reason}")

        events.append(
            {
                "type": row["event_type"],
                "time": row["time"],
                "severity": row["severity"],
                "details": " | ".join(parts) if parts else message,
                "impact": " | ".join(impact_parts),
                "is_pinned": is_pinned,
                "pin_reason": pin_reason,
                "critical_label": critical_label,
            }
        )

    return events


def get_arp_monitor(cur):
    cur.execute(
        """
        SELECT
            TO_CHAR(ts, 'YYYY-MM-DD HH24:MI:SS') AS time,
            event_type,
            source_ip::text AS source_ip,
            old_value,
            new_value
        FROM events
        WHERE event_type IN ('arp_mac_changed', 'identity_mac_changed')
        ORDER BY ts DESC
        LIMIT 10
        """
    )
    rows = cur.fetchall()

    events = []
    for row in rows:
        event_label = "Identity MAC change" if row.get("event_type") == "identity_mac_changed" else "ARP MAC change"

        events.append(
            {
                "type": event_label,
                "severity": "high",
                "details": f"{row['source_ip']} changed MAC from {row['old_value']} to {row['new_value']}",
                "time": row["time"],
            }
        )

    return {
        "status": "Warning" if events else "Normal",
        "summary": f"{len(events)} ARP MAC change events" if events else "No ARP anomalies detected",
        "gateway_ip": "-",
        "gateway_expected_mac": "-",
        "gateway_seen_mac": "-",
        "critical_pairs": [],
        "events": events,
    }



def get_master_slave_groups(cur):
    cur.execute(
        """
        SELECT
            master_ip::text AS master_ip,
            slave_ip::text AS slave_ip,
            COALESCE(unit_id, 0) AS unit_id,
            request_count,
            TO_CHAR(last_seen, 'YYYY-MM-DD HH24:MI:SS') AS last_seen
        FROM observed_connections
        ORDER BY master_ip, slave_ip, unit_id
        """
    )
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

        groups[master]["slaves"].append(
            {
                "ip": f"{row['slave_ip']} (unit {row['unit_id']})" if row["unit_id"] else row["slave_ip"],
                "status": "online",
                "packets": row["request_count"],
                "last_seen": row["last_seen"],
            }
        )
        groups[master]["slave_count"] += 1
        groups[master]["last_seen"] = max(groups[master]["last_seen"], row["last_seen"])

    return list(groups.values())


def enrich_ports_with_devices(ports, devices, connections):
    mac_to_port = get_mac_to_port_map()

    device_by_ip = {
        (device.get("ip") or "").split("/")[0]: device
        for device in devices
        if device.get("ip")
    }

    connection_map = {}

    for group in connections:
        master_ip = (group.get("master") or "").split("/")[0]
        connection_map.setdefault(master_ip, {"role_hint": "master", "unit_ids": set()})

        for slave in group.get("slaves", []):
            raw_ip = (slave.get("ip") or "").split(" ")[0]
            slave_ip = raw_ip.split("/")[0]
            unit_text = slave.get("ip") or ""
            unit_id = None

            if "(unit " in unit_text:
                try:
                    unit_id = int(unit_text.split("(unit ")[1].split(")")[0])
                except Exception:
                    unit_id = None

            entry = connection_map.setdefault(slave_ip, {"role_hint": "slave", "unit_ids": set()})
            if unit_id is not None:
                entry["unit_ids"].add(unit_id)

    port_index = {port["port"]: port for port in ports}

    for ip, device in device_by_ip.items():
        mac = (device.get("mac") or "").lower()
        if not mac:
            continue

        mapping = mac_to_port.get(mac)
        if not mapping:
            continue

        port = port_index.get(mapping["port"])
        if not port:
            continue

        conn_info = connection_map.get(ip, {})
        role = device.get("role") or conn_info.get("role_hint") or "unknown"
        unit_ids = sorted(conn_info.get("unit_ids", set()))
        label = "PLC" if role == "slave" else "Master" if role == "master" else "Device"

        port["devices"].append(
            {
                "ip": ip,
                "mac": mac,
                "role": role,
                "label": label,
                "unit_ids": unit_ids,
                "vlan_id": mapping.get("vlan_id"),
                "ifname": mapping.get("ifname"),
                "ifindex": mapping.get("ifindex"),
            }
        )

    for port in ports:
        vlan_ids = sorted({
            device["vlan_id"]
            for device in port.get("devices", [])
            if device.get("vlan_id") is not None
        })
        port["vlans"] = vlan_ids

        mac_groups = {}
        for device in port.get("devices", []):
            mac = (device.get("mac") or "").lower()
            ip = device.get("ip")
            if not mac or not ip:
                continue
            mac_groups.setdefault(mac, []).append(ip)

        duplicate_macs = [
            {"mac": mac, "ips": sorted(set(ips))}
            for mac, ips in mac_groups.items()
            if len(set(ips)) > 1
        ]

        port["duplicate_macs"] = duplicate_macs
        port["has_duplicate_mac_alarm"] = bool(duplicate_macs)

    return ports

def fetch_summary():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    device_count = get_device_count(cur)
    recent_metrics = get_recent_metrics(cur)
    combined_series = get_combined_series(cur)
    chart_events = get_chart_events(cur)
    recent_events = get_recent_events(cur)
    arp_monitor = get_arp_monitor(cur)
    connections = get_master_slave_groups(cur)
    ports = get_switch_ports()
    devices = fetch_devices()
    ports = enrich_ports_with_devices(ports, devices, connections)

    cur.close()
    conn.close()

    avg_latency = recent_metrics["avg_latency_ms"] or 0

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sensor": {
            "status": "Online",
            "mode": "Passive monitoring",
            "interface": CAPTURE_INTERFACE,
        },
        "summary": [
            {"label": "Online devices", "value": device_count, "note": "Observed devices"},
            {"label": "Requests last 60s", "value": recent_metrics["request_count"], "note": "From SQL buckets"},
            {"label": "Avg latency ms", "value": avg_latency, "note": "Matched request/response"},
        ],
        "combined_series": combined_series,
        "chart_events": chart_events,
        "combined_note": "Traffic, latency, failures and anomalies from SQL buckets.",
        "arp_monitor": arp_monitor,
        "connections": connections,
        "device_roles": [],
        "ports": ports,
        "events": recent_events,
    }


def fetch_devices():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute(
        """
        SELECT
            id,
            ip::text AS ip,
            mac,
            role,
            status,
            TO_CHAR(first_seen, 'YYYY-MM-DD HH24:MI:SS') AS first_seen,
            TO_CHAR(last_seen, 'YYYY-MM-DD HH24:MI:SS') AS last_seen
        FROM devices
        ORDER BY last_seen DESC
        """
    )
    rows = cur.fetchall()

    cur.close()
    conn.close()

    return rows