# service.py er samlingspunktet for dashboardets backend-data.
# Flowet er: frontend -> routes.py GET /api/dashboard -> fetch_summary() i denne fil.
# fetch_summary() kalder queries.py for at hente rå database-rækker.
# Nogle af rækkerne sendes videre til formatters.py, som laver dem om til frontend-klare datastrukturer.
# Port-data sendes videre til ports.py, som kombinerer switch-data, devices og connections.
# Til sidst samler fetch_summary() det hele i ét dict, som routes.py returnerer som JSON til frontend.
# Den læser, formatterer og samler dashboardets API-svar.

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

# CAPTURE_INTERFACE vises i dashboardets sensor-status, så frontend kan se hvilket interface backend lytter på.
CAPTURE_INTERFACE = os.getenv("CAPTURE_INTERFACE", "eth0")

# fetch_devices() er en wrapper omkring get_devices() fra queries.py.
# routes.py bruger den direkte i GET /api/devices.
# fetch_summary() bruger den også, fordi devices både vises i dashboardet og bruges til at bygge port-sektionen.
def fetch_devices():
    return get_devices()

# fetch_summary() bygger det samlede svar til GET /api/dashboard.
# Denne funktion bestemmer hvilke queries der skal køres, hvilke formatters der skal bruges, og hvilke nøgler frontend får i JSON-svaret.
# queries.py leverer rå database-rækker.
# formatters.py bygger grafdata, event-lister og ARP-sektionen.
# ports.py bygger switch-portsektionen ud fra devices, connections og SNMP-data.
# Return-værdien er et Python dict, som routes.py/jsonify() sender til frontend som JSON.
def fetch_summary():
    # Henter devices fra queries.py -> devices-tabellen.
    # Devices sendes både direkte til frontend via /api/devices og bruges her som input til build_ports().
    devices = fetch_devices()
    # Henter summary-tal fra queries.py -> metrics_bucket.
    # Bruges til dashboardets øverste summary-kort.
    recent_metrics = get_recent_metrics()
    # get_connection_rows() henter rå rows fra observed_connections.
    # build_connection_groups() i ports.py grupperer dem efter master_ip, så frontend kan vise master -> slave relationer.
    connections = build_connection_groups(get_connection_rows())

    # get_metric_rows() henter rå tidsserie-rækker fra metrics_bucket.
    # build_combined_series() i formatters.py laver dem om til grafdata til frontend.
    combined_series = build_combined_series(get_metric_rows())
    # get_chart_event_rows() henter åbne events fra events-tabellen.
    # build_chart_events() i formatters.py laver dem om til markører på grafen.
    chart_events = build_chart_events(get_chart_event_rows())
    # get_recent_event_rows() henter åbne IDS-events fra events-tabellen.
    # build_recent_events() i formatters.py laver dem om til den event-liste frontend viser.
    recent_events = build_recent_events(get_recent_event_rows())
    # get_arp_event_rows() henter ARP/MAC-events fra events-tabellen.
    # build_arp_monitor() i formatters.py bygger ARP detection-sektionen til frontend.
    arp_monitor = build_arp_monitor(get_arp_event_rows())
    # build_ports() i ports.py kombinerer devices, grouped connections og SNMP-data fra switch_monitor.py.
    # Resultatet bliver port-sektionen i dashboardet.
    ports = build_ports(devices, connections)

    # recent_metrics kommer fra SQL og kan have NULL for latency, hvis der ikke er målt latency i perioden.
    # Frontend får 0 i stedet for NULL, så summary-kortet altid har en numerisk værdi.
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
        # Nøglerne her matcher de navne frontend forventer i dashboardets JavaScript.
        "combined_series": combined_series,
        "chart_events": chart_events,
        "combined_note": "Traffic, latency, failures and anomalies from SQL buckets.",
        "arp_monitor": arp_monitor,
        "connections": connections,
        "device_roles": [],
        "ports": ports,
        "events": recent_events,
        "alarm_events": recent_events,

        # Approval-data kommer fra storage/alarm_approvals.
        # Frontend bruger det til at skjule/markere alarmer der allerede er håndteret.
        "approved_alarm_keys": get_approved_alarm_keys(),
        "alarm_approvals": list_alarm_approvals(),
    }

