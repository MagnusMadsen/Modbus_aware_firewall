from storage.base import query_all, query_one


def get_device_count():
    row = query_one("SELECT COUNT(*) AS count FROM devices;")
    return row["count"]


def get_recent_metrics():
    return query_one(
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


def get_metric_rows():
    return query_all(
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


def get_recent_event_rows(limit=20):
    return query_all(
        """
        SELECT
            id,
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
        LIMIT %s
        """,
        (limit,),
    )


def get_arp_event_rows(limit=4):
    return query_all(
        """
        SELECT
            id,
            TO_CHAR(ts, 'YYYY-MM-DD HH24:MI:SS') AS time,
            event_type,
            source_ip::text AS source_ip,
            old_value,
            new_value
        FROM events
        WHERE event_type IN ('arp_mac_changed', 'identity_mac_changed')
        ORDER BY ts DESC
        LIMIT %s
        """,
        (limit,),
    )


def get_devices():
    return query_all(
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

def get_chart_event_rows():
    return query_all(
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


def get_connection_rows():
    return query_all(
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
