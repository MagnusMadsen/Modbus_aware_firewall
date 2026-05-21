import os

from datetime import datetime

from storage import get_approved_alarm_keys, list_alarm_approvals

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

        "approved_alarm_keys": get_approved_alarm_keys(),
        "alarm_approvals": list_alarm_approvals(),
    }


