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
            mb.bucket_ts,
            TO_CHAR(mb.bucket_ts, 'HH24:MI:SS') AS time,
            mb.traffic_count AS traffic,
            COALESCE(mb.avg_latency_ms, 0) AS latency,
            mb.failed_count AS failed_requests,
            CASE WHEN mb.traffic_count = 0 THEN TRUE ELSE FALSE END AS downtime,
            downtime_event.id AS downtime_event_id,
            failed_event.id AS failed_event_id,
            latency_event.id AS latency_event_id
        FROM metrics_bucket mb
        LEFT JOIN events downtime_event
            ON downtime_event.event_type = 'downtime'
            AND downtime_event.status = 'open'
            AND (downtime_event.details->>'bucket_ts')::timestamp = mb.bucket_ts
        LEFT JOIN events failed_event
            ON failed_event.event_type = 'failed_requests'
            AND failed_event.status = 'open'
            AND (failed_event.details->>'bucket_ts')::timestamp = mb.bucket_ts
        LEFT JOIN events latency_event
            ON latency_event.event_type = 'latency_spike'
            AND latency_event.status = 'open'
            AND latency_event.ts >= mb.bucket_ts - INTERVAL '5 seconds'
            AND latency_event.ts < mb.bucket_ts + INTERVAL '5 seconds'
        WHERE mb.bucket_ts >= NOW() - INTERVAL '30 minutes'
        ORDER BY mb.bucket_ts
        """
    )


def get_recent_event_rows(limit=20):
    return query_all(
        """
        SELECT
            id,
            event_key,
            TO_CHAR(ts, 'YYYY-MM-DD HH24:MI:SS') AS time,
            event_type,
            severity,
            status,
            source_ip::text AS source_ip,
            target_ip::text AS target_ip,
            register_address,
            old_value,
            new_value,
            details
        FROM events
        WHERE status = 'open'
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
            event_key,
            TO_CHAR(ts, 'YYYY-MM-DD HH24:MI:SS') AS time,
            event_type,
            status,
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
            d.id,
            d.ip::text AS ip,
            d.mac,
            d.role,
            d.status,
            new_device_event.id AS event_id,
            TO_CHAR(d.first_seen, 'YYYY-MM-DD HH24:MI:SS') AS first_seen,
            TO_CHAR(d.last_seen, 'YYYY-MM-DD HH24:MI:SS') AS last_seen
        FROM devices d
        LEFT JOIN events new_device_event
            ON new_device_event.event_type = 'new_device'
            AND new_device_event.status = 'open'
            AND new_device_event.source_ip = d.ip
        ORDER BY d.last_seen DESC
        """
    )

def get_chart_event_rows():
    return query_all(
        """
        SELECT
            id,
            event_key,
            TO_CHAR(ts, 'HH24:MI:SS') AS time,
            event_type,
            severity,
            status,
            source_ip::text AS source_ip,
            target_ip::text AS target_ip,
            register_address,
            old_value,
            new_value
        FROM events
        WHERE ts >= NOW() - INTERVAL '30 minutes'
            AND status = 'open'
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
