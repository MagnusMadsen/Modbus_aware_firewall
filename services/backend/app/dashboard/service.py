import os
from datetime import datetime

from dashboard.formatters import (
    build_arp_monitor,
    build_chart_events,
    build_combined_series,
    build_recent_events,
)
from dashboard.ports import build_connection_groups, build_ports
from dashboard.queries import (
    get_arp_event_rows,
    get_chart_event_rows,
    get_connection_rows,
    get_device_count,
    get_devices,
    get_metric_rows,
    get_recent_event_rows,
    get_recent_metrics,
)
from storage.alerts import create_or_touch_alert

CAPTURE_INTERFACE = os.getenv("CAPTURE_INTERFACE", "eth0")


def fetch_devices():
    return get_devices()


def fetch_summary():
    devices = fetch_devices()
    recent_metrics = get_recent_metrics()
    connections = build_connection_groups(get_connection_rows())

    combined_series = build_combined_series(get_metric_rows())
    chart_events = build_chart_events(get_chart_event_rows())
    recent_events = build_recent_events(get_recent_event_rows())
    arp_monitor = build_arp_monitor(get_arp_event_rows())
    ports = build_ports(devices, connections)

    sync_dashboard_alerts(
        devices=devices,
        combined_series=combined_series,
        arp_monitor=arp_monitor,
        ports=ports,
    )

    avg_latency = recent_metrics["avg_latency_ms"] or 0

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sensor": {
            "status": "Online",
            "mode": "Passive monitoring",
            "interface": CAPTURE_INTERFACE,
        },
        "summary": [
            {"label": "Online devices", "value": get_device_count(), "note": "Observed devices"},
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


def sync_dashboard_alerts(devices, combined_series, arp_monitor, ports):
    create_pending_device_alert(devices)
    create_arp_alert(arp_monitor)
    create_downtime_alert(combined_series)
    create_failed_request_alert(combined_series)
    create_latency_alert(combined_series)
    create_active_port_alerts(ports)


def create_pending_device_alert(devices):
    for device in devices or []:
        status = str(device.get("status") or "").lower()
        if status not in {"pending", "unknown"}:
            continue

        device_id = device.get("id")
        alert_key = f"device:{device_id or device.get('ip') or device.get('mac')}"
        create_or_touch_alert(
            alert_key=alert_key,
            alert_type="device",
            title="UKENDT ENHED FUNDET",
            message="En ny enhed er observeret på netværket.",
            severity="medium",
            source_ip=device.get("ip"),
            device_id=device_id,
            details={
                "ip": device.get("ip") or "-",
                "mac": device.get("mac") or "-",
                "role": device.get("role") or "unknown",
                "first_seen": device.get("first_seen") or "-",
            },
        )
        return


def create_arp_alert(arp_monitor):
    events = (arp_monitor or {}).get("events") or []
    if not events:
        return

    event = events[0]
    alert_key = f"arp:{event.get('time')}:{event.get('details')}"
    create_or_touch_alert(
        alert_key=alert_key,
        alert_type="arp",
        title="ARP MAC ÆNDRING",
        message="En IP-adresse har skiftet MAC-adresse. Dette kan indikere MITM eller ARP spoofing.",
        severity=event.get("severity") or "high",
        details={
            "type": event.get("type") or "ARP event",
            "severity": event.get("severity") or "high",
            "time": event.get("time") or "-",
            "details": event.get("details") or "-",
        },
    )


def create_downtime_alert(series):
    item = find_last(series, lambda row: bool(row.get("downtime")))
    if not item:
        return

    create_or_touch_alert(
        alert_key=f"downtime:{item.get('time')}",
        alert_type="downtime",
        title="NETVÆRKSUDFALD",
        message="Der er registreret et tidsvindue uden trafik.",
        severity="high",
        details={
            "time": item.get("time") or "-",
            "traffic": item.get("traffic"),
            "failed_requests": item.get("failed_requests"),
            "latency_ms": item.get("latency"),
        },
    )


def create_failed_request_alert(series):
    item = find_last(series, lambda row: int(row.get("failed_requests") or 0) > 0)
    if not item:
        return

    failed_requests = int(item.get("failed_requests") or 0)
    create_or_touch_alert(
        alert_key=f"failed:{item.get('time')}:{failed_requests}",
        alert_type="failed_requests",
        title="FAILED MODBUS REQUESTS",
        message="Der er registreret fejlede requests. Dette kan ske ved afbrydelse, bridge/MITM eller ustabil slave.",
        severity="high",
        details={
            "time": item.get("time") or "-",
            "failed_requests": failed_requests,
            "traffic": item.get("traffic"),
            "latency_ms": item.get("latency"),
        },
    )


def create_latency_alert(series):
    item = find_last(
        series,
        lambda row: float(row.get("latency") or 0) > 0
        and float(row.get("latency_threshold") or 0) > 0
        and float(row.get("latency") or 0) > float(row.get("latency_threshold") or 0),
    )
    if not item:
        return

    create_or_touch_alert(
        alert_key=f"latency:{item.get('time')}:{item.get('latency')}",
        alert_type="latency",
        title="LATENCY OVER THRESHOLD",
        message="Latency er over den beregnede threshold.",
        severity="medium",
        details={
            "time": item.get("time") or "-",
            "latency_ms": item.get("latency"),
            "threshold_ms": item.get("latency_threshold"),
            "baseline_ms": item.get("latency_baseline"),
        },
    )


def create_active_port_alerts(ports):
    for port in ports or []:
        state = str(port.get("state") or "").lower()
        if state != "active":
            continue

        port_name = port.get("port") or "unknown"
        create_or_touch_alert(
            alert_key=f"port-active:{port_name}",
            alert_type="port_active",
            title="SWITCH PORT AKTIV",
            message="En switch-port er aktiv og skal godkendes.",
            severity="medium",
            details={
                "port": port_name,
                "interface": port.get("name") or "-",
                "state": port.get("state") or "-",
                "activity": port.get("activity") or "-",
            },
        )


def find_last(items, predicate):
    for item in reversed(items or []):
        if predicate(item):
            return item
    return None
