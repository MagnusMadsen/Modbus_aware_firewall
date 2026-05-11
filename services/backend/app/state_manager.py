import os
import threading
import time
from datetime import datetime

from storage import get_writer

LEARNING_WINDOW_SECONDS = int(os.getenv("LEARNING_WINDOW_SECONDS", "300"))
FLUSH_INTERVAL_SECONDS = int(os.getenv("FLUSH_INTERVAL_SECONDS", "5"))
REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "2.0"))
LATENCY_SPIKE_MS = float(os.getenv("LATENCY_SPIKE_MS", "500.0"))
DEVICE_SQL_TOUCH_SECONDS = int(os.getenv("DEVICE_SQL_TOUCH_SECONDS", "30"))
CONNECTION_SQL_TOUCH_SECONDS = int(os.getenv("CONNECTION_SQL_TOUCH_SECONDS", "30"))


def _now():
    return datetime.now()


def _floor_bucket(dt: datetime, seconds: int):
    floored_second = dt.second - (dt.second % seconds)
    return dt.replace(second=floored_second, microsecond=0)


def _compute_p95(values):
    if not values:
        return None
    ordered = sorted(values)
    index = int(round(0.95 * (len(ordered) - 1)))
    return float(ordered[index])


class ModbusStateManager:
    def __init__(self):
        self.writer = get_writer()
        self.lock = threading.Lock()
        self.started_at = _now()
        self.bucket_ts = _floor_bucket(_now(), FLUSH_INTERVAL_SECONDS)

        self.known_devices = {}
        self.device_last_sql_touch = {}

        self.known_connections = set()
        self.connection_last_seen = {}
        self.connection_last_sql_touch = {}

        self.known_function_codes = set()
        self.register_state = {}
        self.pending_requests = {}

        self.metrics = self._new_metrics_bucket()
        self._maintenance_thread = None

    def _new_metrics_bucket(self):
        return {
            "traffic_count": 0,
            "request_count": 0,
            "response_count": 0,
            "failed_count": 0,
            "arp_count": 0,
            "latencies_ms": [],
        }

    def in_learning_mode(self):
        return (_now() - self.started_at).total_seconds() < LEARNING_WINDOW_SECONDS

    def start(self):
        if self._maintenance_thread is not None:
            return

        self._maintenance_thread = threading.Thread(target=self._maintenance_loop, daemon=True)
        self._maintenance_thread.start()

    def process(self, data):
        with self.lock:
            self._flush_metrics_if_due()
            self._expire_requests_if_needed()

            protocol = data.get("protocol")
            if protocol == "ARP":
                self._handle_arp(data)
                return

            if not data.get("is_modbus"):
                return

            self.metrics["traffic_count"] += 1

            if data.get("direction") == "request":
                self._handle_modbus_request(data)
            elif data.get("direction") == "response":
                self._handle_modbus_response(data)

    def _maintenance_loop(self):
        while True:
            time.sleep(1)
            with self.lock:
                self._expire_requests_if_needed()
                self._flush_metrics_if_due()

    def _flush_metrics_if_due(self):
        now = _now()
        current_bucket = _floor_bucket(now, FLUSH_INTERVAL_SECONDS)

        if current_bucket <= self.bucket_ts:
            return

        active_connections = sum(
            1 for last_seen in self.connection_last_seen.values()
            if (now - last_seen).total_seconds() <= 60
        )

        latencies = self.metrics["latencies_ms"]
        avg_latency_ms = round(sum(latencies) / len(latencies), 2) if latencies else None
        p95_latency_ms = round(_compute_p95(latencies), 2) if latencies else None

        self.writer.insert_metrics_bucket(
            bucket_ts=self.bucket_ts,
            traffic_count=self.metrics["traffic_count"],
            request_count=self.metrics["request_count"],
            response_count=self.metrics["response_count"],
            failed_count=self.metrics["failed_count"],
            arp_count=self.metrics["arp_count"],
            avg_latency_ms=avg_latency_ms,
            p95_latency_ms=p95_latency_ms,
            active_connections=active_connections,
        )

        self.bucket_ts = current_bucket
        self.metrics = self._new_metrics_bucket()

    def _normalize_mac(self, mac):
        if not mac:
            return None
        return str(mac).strip().lower()

    def _merge_role(self, current_role, new_role):
        if not new_role:
            return current_role

        new_role = str(new_role).strip().lower()
        current_role = str(current_role).strip().lower() if current_role else None

        if new_role == "unknown" and current_role in ("master", "slave"):
            return current_role

        return new_role

    def _touch_device(self, ip, mac=None, role=None):
        if not ip or ip in ("0.0.0.0", "255.255.255.255"):
            return

        now = _now()
        normalized_mac = self._normalize_mac(mac)
        normalized_role = str(role).strip().lower() if role else None

        existing = self.known_devices.get(ip)

        if existing is None:
            db_device = self.writer.get_device_by_ip(ip)

            if db_device:
                existing = {
                    "mac": self._normalize_mac(db_device.get("mac")),
                    "role": db_device.get("role"),
                    "first_seen": db_device.get("first_seen"),
                    "last_seen": now,
                }
                self.known_devices[ip] = existing
            else:
                self.known_devices[ip] = {
                    "mac": normalized_mac,
                    "role": normalized_role,
                    "first_seen": now,
                    "last_seen": now,
                }

                self.writer.upsert_device(ip, normalized_mac, normalized_role)

                if not self.in_learning_mode():
                    self.writer.insert_event(
                        event_type="new_device",
                        severity="info",
                        source_ip=ip,
                        details={
                            "message": "New device observed",
                            "mac": normalized_mac,
                            "role": normalized_role,
                        },
                    )

                self.device_last_sql_touch[ip] = now
                return

        old_mac = self._normalize_mac(existing.get("mac"))
        old_role = existing.get("role")
        merged_role = self._merge_role(old_role, normalized_role)

        mac_changed = bool(normalized_mac and old_mac and old_mac != normalized_mac)
        role_changed = bool(
            old_role
            and merged_role
            and old_role != merged_role
            and {old_role, merged_role} == {"master", "slave"}
        )

        if mac_changed:
            self.writer.insert_event(
                event_type="identity_mac_changed",
                severity="high",
                source_ip=ip,
                old_value=old_mac,
                new_value=normalized_mac,
                details={
                    "message": "Known IP observed with a different MAC address",
                    "old_mac": old_mac,
                    "new_mac": normalized_mac,
                    "role": merged_role,
                    "is_pinned": True,
                    "pin_reason": "IP/MAC identity changed",
                },
            )
            existing["mac"] = normalized_mac

        if role_changed:
            self.writer.insert_event(
                event_type="identity_role_changed",
                severity="high",
                source_ip=ip,
                old_value=old_role,
                new_value=merged_role,
                details={
                    "message": "Known device changed Modbus role",
                    "old_role": old_role,
                    "new_role": merged_role,
                    "mac": normalized_mac or old_mac,
                    "is_pinned": True,
                    "pin_reason": "Device role changed",
                },
            )

        existing["role"] = merged_role
        existing["last_seen"] = now

        last_touch = self.device_last_sql_touch.get(ip)
        should_touch_sql = (
            last_touch is None
            or (now - last_touch).total_seconds() >= DEVICE_SQL_TOUCH_SECONDS
            or mac_changed
            or role_changed
        )

        if should_touch_sql:
            self.writer.upsert_device(
                ip,
                existing.get("mac"),
                existing.get("role"),
            )
            self.device_last_sql_touch[ip] = now

    def _touch_connection(self, master_ip, slave_ip, unit_id):
        if not master_ip or not slave_ip:
            return

        now = _now()
        key = (master_ip, slave_ip, unit_id)
        is_new = key not in self.known_connections

        self.known_connections.add(key)
        self.connection_last_seen[key] = now

        if is_new:
            self.writer.upsert_connection(master_ip, slave_ip, unit_id)
            self.connection_last_sql_touch[key] = now

            if not self.in_learning_mode():
                self.writer.insert_event(
                    event_type="new_connection",
                    severity="info",
                    source_ip=master_ip,
                    target_ip=slave_ip,
                    unit_id=unit_id,
                    details={"message": "New master/slave relation observed"},
                )
            return

        last_touch = self.connection_last_sql_touch.get(key)
        if last_touch is None or (now - last_touch).total_seconds() >= CONNECTION_SQL_TOUCH_SECONDS:
            self.writer.upsert_connection(master_ip, slave_ip, unit_id)
            self.connection_last_sql_touch[key] = now

    def _handle_arp(self, data):
        self.metrics["arp_count"] += 1
        self._touch_device(data.get("src_ip"), data.get("src_mac"), role="unknown")

    def _handle_modbus_request(self, data):
        master_ip = data.get("src_ip")
        slave_ip = data.get("dst_ip")
        unit_id = data.get("unit_id")
        function_code = data.get("function_code")

        self.metrics["request_count"] += 1

        self._touch_device(master_ip, data.get("src_mac"), role="master")
        self._touch_device(slave_ip, data.get("dst_mac"), role="slave")
        self._touch_connection(master_ip, slave_ip, unit_id)

        fc_key = (slave_ip, unit_id, function_code)
        if fc_key not in self.known_function_codes:
            self.known_function_codes.add(fc_key)
            if not self.in_learning_mode():
                self.writer.insert_event(
                    event_type="new_function_code",
                    severity="info",
                    source_ip=master_ip,
                    target_ip=slave_ip,
                    unit_id=unit_id,
                    function_code=function_code,
                    details={"message": "New function code observed on this slave"},
                )

        self._process_register_changes(data)

        pending_key = (master_ip, slave_ip, data.get("transaction_id"), unit_id)
        self.pending_requests[pending_key] = {
            "ts": _now(),
            "function_code": function_code,
            "register_type": data.get("register_type"),
            "register_address": data.get("register_address"),
            "values": data.get("values"),
        }

    def _classify_register_change(self, master_ip, slave_ip, unit_id, register_type, register_address, old_value, new_value):
        critical = self.writer.get_critical_register(
            slave_ip=slave_ip,
            unit_id=unit_id,
            register_type=register_type,
            register_address=register_address,
        )

        result = {
            "severity": "medium",
            "is_pinned": False,
            "pin_reason": None,
            "critical_label": None,
        }

        if not critical:
            return result

        result["critical_label"] = critical.get("label")

        allowed_values = critical.get("allowed_values")
        if allowed_values is not None:
            normalized_allowed = {str(v) for v in allowed_values}
            if str(new_value) not in normalized_allowed:
                result["severity"] = "critical"
                result["is_pinned"] = True
                result["pin_reason"] = "Value outside allowed values"
                return result

        if critical.get("pin_on_change"):
            result["severity"] = "high"
            result["is_pinned"] = True
            result["pin_reason"] = "Critical register changed"

        return result

    def _process_register_changes(self, data):
        function_code = data.get("function_code")
        if function_code not in (5, 6, 15, 16):
            return

        slave_ip = data.get("dst_ip")
        unit_id = data.get("unit_id")
        register_type = data.get("register_type")
        start_address = data.get("register_address")
        values = data.get("values") or []

        if slave_ip is None or unit_id is None or register_type is None or start_address is None:
            return

        for offset, value in enumerate(values):
            address = start_address + offset
            state_key = (slave_ip, unit_id, register_type, address)
            old_value = self.register_state.get(state_key)

            classification = self._classify_register_change(
                master_ip=data.get("src_ip"),
                slave_ip=slave_ip,
                unit_id=unit_id,
                register_type=register_type,
                register_address=address,
                old_value=old_value,
                new_value=value,
            )

            if old_value is None:
                self.register_state[state_key] = value
                self.writer.upsert_register_state(slave_ip, unit_id, register_type, address, value)

                if not self.in_learning_mode() or classification["is_pinned"]:
                    self.writer.insert_event(
                        event_type="new_register_observed",
                        severity=classification["severity"] if classification["is_pinned"] else "info",
                        source_ip=data.get("src_ip"),
                        target_ip=slave_ip,
                        unit_id=unit_id,
                        function_code=function_code,
                        register_type=register_type,
                        register_address=address,
                        new_value=value,
                        details={
                            "message": "New register observed",
                            "is_pinned": classification["is_pinned"],
                            "pin_reason": classification["pin_reason"],
                            "critical_label": classification["critical_label"],
                        },
                    )
                continue

            if old_value != value:
                self.register_state[state_key] = value
                self.writer.upsert_register_state(slave_ip, unit_id, register_type, address, value)

                self.writer.insert_event(
                    event_type="register_value_changed",
                    severity=classification["severity"],
                    source_ip=data.get("src_ip"),
                    target_ip=slave_ip,
                    unit_id=unit_id,
                    function_code=function_code,
                    register_type=register_type,
                    register_address=address,
                    old_value=old_value,
                    new_value=value,
                    details={
                        "message": "Register value changed",
                        "is_pinned": classification["is_pinned"],
                        "pin_reason": classification["pin_reason"],
                        "critical_label": classification["critical_label"],
                    },
                )

    def _handle_modbus_response(self, data):
        self.metrics["response_count"] += 1

        master_ip = data.get("dst_ip")
        slave_ip = data.get("src_ip")
        unit_id = data.get("unit_id")
        pending_key = (master_ip, slave_ip, data.get("transaction_id"), unit_id)

        pending = self.pending_requests.pop(pending_key, None)
        if pending is None:
            return

        latency_ms = round((_now() - pending["ts"]).total_seconds() * 1000.0, 2)
        self.metrics["latencies_ms"].append(latency_ms)

        if latency_ms >= LATENCY_SPIKE_MS and not self.in_learning_mode():
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
            self.metrics["failed_count"] += 1
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

    def _expire_requests_if_needed(self):
        now = _now()
        expired_keys = []

        for key, pending in self.pending_requests.items():
            age = (now - pending["ts"]).total_seconds()
            if age >= REQUEST_TIMEOUT_SECONDS:
                expired_keys.append(key)

        for key in expired_keys:
            pending = self.pending_requests.pop(key, None)
            if pending is None:
                continue

            master_ip, slave_ip, _, unit_id = key
            self.metrics["failed_count"] += 1

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


_manager = None
_manager_lock = threading.Lock()


def init_state_manager():
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = ModbusStateManager()
            _manager.start()
    return _manager


def process_observation(data):
    manager = init_state_manager()
    manager.process(data)