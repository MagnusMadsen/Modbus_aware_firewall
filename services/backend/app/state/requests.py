from state.time_utils import now


class RequestTracker:
    def __init__(self, writer, metrics, learning_mode, request_timeout_seconds: float, latency_spike_ms: float):
        self.writer = writer
        self.metrics = metrics
        self.learning_mode = learning_mode
        self.request_timeout_seconds = request_timeout_seconds
        self.latency_spike_ms = latency_spike_ms
        self.pending_requests = {}

    def add_request(self, data):
        key = (
            data.get("src_ip"),
            data.get("dst_ip"),
            data.get("transaction_id"),
            data.get("unit_id"),
        )
        self.pending_requests[key] = {
            "ts": now(),
            "function_code": data.get("function_code"),
            "register_type": data.get("register_type"),
            "register_address": data.get("register_address"),
            "values": data.get("values"),
        }

    def handle_response(self, data):
        self.metrics.count_response()

        master_ip = data.get("dst_ip")
        slave_ip = data.get("src_ip")
        unit_id = data.get("unit_id")
        pending_key = (master_ip, slave_ip, data.get("transaction_id"), unit_id)

        pending = self.pending_requests.pop(pending_key, None)
        if pending is None:
            return

        latency_ms = round((now() - pending["ts"]).total_seconds() * 1000.0, 2)
        self.metrics.add_latency(latency_ms)

        if latency_ms >= self.latency_spike_ms and not self.learning_mode():
            self.writer.insert_event(
                event_type="latency_spike",
                severity="medium",
                source_ip=master_ip,
                target_ip=slave_ip,
                unit_id=unit_id,
                function_code=data.get("function_code"),
                new_value=latency_ms,
                details={
                    "message": "High latency detected",
                    "latency_ms": latency_ms,
                    "is_pinned": True,
                    "pin_reason": "Latency spike",
                },
            )

        if data.get("is_exception"):
            self.metrics.count_failed()
            self.writer.insert_event(
                event_type="exception_response",
                severity="high",
                source_ip=master_ip,
                target_ip=slave_ip,
                unit_id=unit_id,
                function_code=data.get("function_code"),
                new_value=data.get("exception_code"),
                details={
                    "message": "Modbus exception response",
                    "exception_code": data.get("exception_code"),
                    "is_pinned": True,
                    "pin_reason": "Modbus exception response",
                },
            )

    def expire_if_needed(self):
        current_time = now()
        expired_keys = []

        for key, pending in self.pending_requests.items():
            age = (current_time - pending["ts"]).total_seconds()
            if age >= self.request_timeout_seconds:
                expired_keys.append(key)

        for key in expired_keys:
            pending = self.pending_requests.pop(key, None)
            if pending is None:
                continue

            master_ip, slave_ip, _, unit_id = key
            self.metrics.count_failed()

            self.writer.insert_event(
                event_type="request_timeout",
                severity="high",
                source_ip=master_ip,
                target_ip=slave_ip,
                unit_id=unit_id,
                function_code=pending.get("function_code"),
                register_type=pending.get("register_type"),
                register_address=pending.get("register_address"),
                details={
                    "message": "No response seen before timeout",
                    "is_pinned": True,
                    "pin_reason": "Request timeout",
                },
            )
