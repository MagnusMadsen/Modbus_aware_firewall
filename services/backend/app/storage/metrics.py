from storage.base import execute


def insert_metrics_bucket(
    bucket_ts,
    traffic_count,
    request_count,
    response_count,
    failed_count,
    arp_count,
    avg_latency_ms,
    p95_latency_ms,
    active_connections,
):
    execute(
        """
        INSERT INTO metrics_bucket
            (bucket_ts, traffic_count, request_count, response_count, failed_count, arp_count,
             avg_latency_ms, p95_latency_ms, active_connections)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (bucket_ts)
        DO UPDATE SET
            traffic_count = EXCLUDED.traffic_count,
            request_count = EXCLUDED.request_count,
            response_count = EXCLUDED.response_count,
            failed_count = EXCLUDED.failed_count,
            arp_count = EXCLUDED.arp_count,
            avg_latency_ms = EXCLUDED.avg_latency_ms,
            p95_latency_ms = EXCLUDED.p95_latency_ms,
            active_connections = EXCLUDED.active_connections
        """,
        (
            bucket_ts,
            traffic_count,
            request_count,
            response_count,
            failed_count,
            arp_count,
            avg_latency_ms,
            p95_latency_ms,
            active_connections,
        ),
    )