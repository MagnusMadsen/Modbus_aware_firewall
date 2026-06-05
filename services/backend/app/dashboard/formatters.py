# formatters.py laver database-rækker om til det JSON-format frontend forventer.
# SQL-queries i dashboard/queries.py henter rå data fra databasen.
# Funktionerne her ændrer ikke databasen. De omformer kun data til grafer, event-lister og ARP-sektionen i dashboardet.

# build_combined_series() bygger dataserien til trafik/latency-grafen.
# rows kommer fra get_metric_rows() i dashboard/queries.py.
# Funktionen beregner baseline ud fra de datapunkter der allerede er gennemløbet.
# latency_threshold sættes til latency_baseline * 1.5, så frontend kan vise hvornår latency ligger over normalniveauet.
# Event-id'er sendes med, så frontend kan koble downtime, failed requests og latency alarms tilbage til events-tabellen.
def build_combined_series(rows):
    series = []
    traffic_history = []
    latency_history = []

    for row in rows:
        traffic = row["traffic"] or 0
        latency = row["latency"] or 0

        # traffic_history bruges til løbende gennemsnit for traffic_baseline.
        # latency_history ignorerer 0-værdier, fordi 0 betyder ingen målt latency i det tidsvindue.
        traffic_history.append(traffic)
        if latency > 0:
            latency_history.append(latency)

        # Baseline beregnes som gennemsnittet af de tidligere punkter i serien.
        # Den er simpel men det virker :) 
        traffic_baseline = round(sum(traffic_history) / len(traffic_history), 2)
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
                "downtime_event_id": row.get("downtime_event_id"),
                "failed_event_id": row.get("failed_event_id"),
                "latency_event_id": row.get("latency_event_id"),
            }
        )

    return series


# build_chart_events() bygger små event-markører til grafen.
# Hvis eventet handler om et register, tilføjes register_address til labelen.
# Listen vendes til sidst, så frontend får events i kronologisk rækkefølge.
def build_chart_events(rows):
    events = []

    for row in rows:
        label = row["event_type"]
        if row["register_address"] is not None:
            label = f"{row['event_type']} reg {row['register_address']}"

        events.append(
            {
                "event_id": row.get("id"),
                "event_key": row.get("event_key"),
                "time": row["time"],
                "label": label,
                "severity": row["severity"],
                "status": row.get("status"),
            }
        )

    return list(reversed(events))


# build_recent_events() bygger listen over seneste IDS-events til dashboardet.
# details JSONB fra events-tabellen bruges til message, pin_reason og critical_label.
# Funktionen samler source/target IP, registeradresse og value change til en kort læsbar tekst.
def build_recent_events(rows):
    events = []

    for row in rows:
        details = row["details"] or {}
        message = details.get("message", row["event_type"])
        is_pinned = bool(details.get("is_pinned", False))
        pin_reason = details.get("pin_reason")
        critical_label = details.get("critical_label")

        # parts bliver den tekniske forklaring, f.eks. IP -> IP, register og gammel -> ny værdi.
        parts = []
        if row["source_ip"] and row["target_ip"]:
            parts.append(f"{row['source_ip']} -> {row['target_ip']}")

        if row["register_address"] is not None:
            parts.append(f"register {row['register_address']}")

        if row["old_value"] is not None or row["new_value"] is not None:
            parts.append(f"{row['old_value']} -> {row['new_value']}")

        # impact_parts bliver den menneskelige forklaring, som frontend viser som eventets betydning.
        impact_parts = [message]
        if critical_label:
            impact_parts.append(f"Critical register: {critical_label}")
        if pin_reason:
            impact_parts.append(f"Reason: {pin_reason}")

        events.append(
            {
                "event_id": row.get("id"),
                "event_key": row.get("event_key"),
                "type": row["event_type"],
                "time": row["time"],
                "severity": row["severity"],
                "status": row.get("status"),
                "details": " | ".join(parts) if parts else message,
                "impact": " | ".join(impact_parts),
                "is_pinned": is_pinned,
                "pin_reason": pin_reason,
                "critical_label": critical_label,
            }
        )

    return events


# build_arp_monitor() bygger ARP detection-sektionen i dashboardet.
# rows kommer fra get_arp_event_rows() og indeholder MAC-skift fra events-tabellen.
# identity_mac_changed betyder at en kendt IP er set med en anden MAC.
# Andre ARP-events vises som ARP MAC change.
def build_arp_monitor(rows):
    events = []

    for row in rows:
        # Labelen gøres mere læsbar for frontend, så event_type ikke vises direkte som teknisk databasenavn.
        event_label = (
            "Identity MAC change"
            if row.get("event_type") == "identity_mac_changed"
            else "ARP MAC change"
        )

        events.append(
            {
                "event_id": row.get("id"),
                "event_key": row.get("event_key"),
                "type": event_label,
                "severity": "high",
                "status": row.get("status"),
                "details": f"{row['source_ip']} changed MAC from {row['old_value']} to {row['new_value']}",
                "time": row["time"],
            }
        )

    # Hvis der er ARP/MAC-events, vises sektionen som Warning. Ellers vises den som Normal.
    return {
        "status": "Warning" if events else "Normal",
        "summary": f"{len(events)} ARP MAC change events" if events else "No ARP anomalies detected",
        "gateway_ip": "-",
        "gateway_expected_mac": "-",
        "gateway_seen_mac": "-",
        "critical_pairs": [],
        "events": events,
    }