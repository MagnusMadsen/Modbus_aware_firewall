from state.time_utils import now

from datetime import datetime


def _packet_time(data):
    ts = data.get("ts")
    if not ts:
        return now()

    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return now()


class RequestTracker:
    def __init__(
        self,
        writer,
        metrics,
        learning_mode,
        request_timeout_seconds: float,
        latency_spike_ms: float,
        timeout_event_throttle_seconds: float,
    ):
        self.writer = writer
        self.metrics = metrics
        self.learning_mode = learning_mode
        self.request_timeout_seconds = request_timeout_seconds
        self.latency_spike_ms = latency_spike_ms
        self.timeout_event_throttle_seconds = timeout_event_throttle_seconds
        self.pending_requests = {}
        self.last_timeout_event_at = {}

    def add_request(self, data):
        transaction_id = data.get("transaction_id")
        unit_id = data.get("unit_id")
        master_ip = data.get("src_ip")
        slave_ip = data.get("dst_ip")

        if transaction_id is None or unit_id is None or not master_ip or not slave_ip:
            return

        key = (master_ip, slave_ip, transaction_id, unit_id)

        self.pending_requests[key] = {
            "ts": _packet_time(data),
            "function_code": data.get("function_code"),
            "register_type": data.get("register_type"),
            "register_address": data.get("register_address"),
            "values": data.get("values"),
        }

    def handle_response(self, data):
        self.metrics.count_response()

        master_ip = data.get("dst_ip")
        slave_ip = data.get("src_ip")
        transaction_id = data.get("transaction_id")
        unit_id = data.get("unit_id")

        if transaction_id is None or unit_id is None or not master_ip or not slave_ip:
            return

        pending_key = (master_ip, slave_ip, transaction_id, unit_id)
        pending = self.pending_requests.pop(pending_key, None)

        if pending is None:
            return

        latency_ms = round((_packet_time(data) - pending["ts"]).total_seconds() * 1000.0, 2)

        if latency_ms < 0:
            return

        if latency_ms > 10000:
            return

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

        if data.get("is_exception") and not self.learning_mode():
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

            if self.learning_mode():
                continue

            if not self._should_emit_timeout_event(key, current_time):
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

    def _should_emit_timeout_event(self, key, current_time):
        master_ip, slave_ip, _, unit_id = key
        throttle_key = (master_ip, slave_ip, unit_id)

        last_event_at = self.last_timeout_event_at.get(throttle_key)
        if last_event_at is not None:
            age = (current_time - last_event_at).total_seconds()
            if age < self.timeout_event_throttle_seconds:
                return False

        self.last_timeout_event_at[throttle_key] = current_time
        return True