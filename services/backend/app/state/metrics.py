from state.time_utils import compute_p95, floor_bucket, now


class MetricsTracker:
    def __init__(self, writer, flush_interval_seconds: int, connection_last_seen: dict):
        self.writer = writer
        self.flush_interval_seconds = flush_interval_seconds
        self.connection_last_seen = connection_last_seen
        self.bucket_ts = floor_bucket(now(), flush_interval_seconds)
        self.current = self._new_bucket()

    def _new_bucket(self):
        return {
            "traffic_count": 0,
            "request_count": 0,
            "response_count": 0,
            "failed_count": 0,
            "arp_count": 0,
            "latencies_ms": [],
        }

    def count_traffic(self):
        self.current["traffic_count"] += 1

    def count_request(self):
        self.current["request_count"] += 1

    def count_response(self):
        self.current["response_count"] += 1

    def count_failed(self):
        self.current["failed_count"] += 1

    def count_arp(self):
        self.current["arp_count"] += 1

    def add_latency(self, latency_ms: float):
        self.current["latencies_ms"].append(latency_ms)

    def flush_if_due(self):
        current_bucket = floor_bucket(now(), self.flush_interval_seconds)

        if current_bucket <= self.bucket_ts:
            return

        active_connections = sum(
            1
            for last_seen in self.connection_last_seen.values()
            if (now() - last_seen).total_seconds() <= 60
        )

        latencies = self.current["latencies_ms"]
        avg_latency_ms = round(sum(latencies) / len(latencies), 2) if latencies else None
        p95_latency_ms = round(compute_p95(latencies), 2) if latencies else None

        self.writer.insert_metrics_bucket(
            bucket_ts=self.bucket_ts,
            traffic_count=self.current["traffic_count"],
            request_count=self.current["request_count"],
            response_count=self.current["response_count"],
            failed_count=self.current["failed_count"],
            arp_count=self.current["arp_count"],
            avg_latency_ms=avg_latency_ms,
            p95_latency_ms=p95_latency_ms,
            active_connections=active_connections,
        )

        self.bucket_ts = current_bucket
        self.current = self._new_bucket()
