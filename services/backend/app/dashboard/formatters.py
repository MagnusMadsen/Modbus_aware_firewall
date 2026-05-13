def build_combined_series(rows):
    series = []
    traffic_history = []
    latency_history = []

    for row in rows:
        traffic = row["traffic"] or 0
        latency = row["latency"] or 0

        traffic_history.append(traffic)
        if latency > 0:
            latency_history.append(latency)

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
            }
        )

    return series


def build_recent_events(rows):
    events = []

    for row in rows:
        details = row["details"] or {}
        message = details.get("message", row["event_type"])
        is_pinned = bool(details.get("is_pinned", False))
        pin_reason = details.get("pin_reason")
        critical_label = details.get("critical_label")

        parts = []
        if row["source_ip"] and row["target_ip"]:
            parts.append(f"{row['source_ip']} -> {row['target_ip']}")

        if row["register_address"] is not None:
            parts.append(f"register {row['register_address']}")

        if row["old_value"] is not None or row["new_value"] is not None:
            parts.append(f"{row['old_value']} -> {row['new_value']}")

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


def build_arp_monitor(rows):
    events = []

    for row in rows:
        event_label = (
            "Identity MAC change"
            if row.get("event_type") == "identity_mac_changed"
            else "ARP MAC change"
        )

        events.append(
            {
                "type": event_label,
                "severity": "high",
                "details": f"{row['source_ip']} changed MAC from {row['old_value']} to { event_label,
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