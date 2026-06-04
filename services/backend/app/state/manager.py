import os
import threading
import time

from state.connections import ConnectionTracker
from state.devices import DeviceTracker
from state.metrics import MetricsTracker
from state.registers import RegisterTracker
from state.requests import RequestTracker
from state.time_utils import now
from storage import get_writer

LEARNING_WINDOW_SECONDS = int(os.getenv("LEARNING_WINDOW_SECONDS", "300"))
FLUSH_INTERVAL_SECONDS = int(os.getenv("FLUSH_INTERVAL_SECONDS", "5"))

REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "10.0"))
LATENCY_SPIKE_MS = float(os.getenv("LATENCY_SPIKE_MS", "1000.0"))
TIMEOUT_EVENT_THROTTLE_SECONDS = float(os.getenv("TIMEOUT_EVENT_THROTTLE_SECONDS", "60.0"))

DEVICE_SQL_TOUCH_SECONDS = int(os.getenv("DEVICE_SQL_TOUCH_SECONDS", "120"))
CONNECTION_SQL_TOUCH_SECONDS = int(os.getenv("CONNECTION_SQL_TOUCH_SECONDS", "120"))


class ModbusStateManager:
    def __init__(self):
        self.writer = get_writer()
        self.lock = threading.Lock()
        self.started_at = now()
        self.known_function_codes = set()
        self._maintenance_thread = None

        self.devices = DeviceTracker(
            writer=self.writer,
            learning_mode=self.in_learning_mode,
            sql_touch_seconds=DEVICE_SQL_TOUCH_SECONDS,
        )
        self.connections = ConnectionTracker(
            writer=self.writer,
            learning_mode=self.in_learning_mode,
            sql_touch_seconds=CONNECTION_SQL_TOUCH_SECONDS,
        )
        self.metrics = MetricsTracker(
            writer=self.writer,
            flush_interval_seconds=FLUSH_INTERVAL_SECONDS,
            connection_last_seen=self.connections.last_seen,
        )
        self.registers = RegisterTracker(
            writer=self.writer,
            learning_mode=self.in_learning_mode,
        )
        self.requests = RequestTracker(
            writer=self.writer,
            metrics=self.metrics,
            learning_mode=self.in_learning_mode,
            request_timeout_seconds=REQUEST_TIMEOUT_SECONDS,
            latency_spike_ms=LATENCY_SPIKE_MS,
            timeout_event_throttle_seconds=TIMEOUT_EVENT_THROTTLE_SECONDS,
        )

    def in_learning_mode(self):
        return (now() - self.started_at).total_seconds() < LEARNING_WINDOW_SECONDS

    def start(self):
        if self._maintenance_thread is not None:
            return

        self._maintenance_thread = threading.Thread(target=self._maintenance_loop, daemon=True)
        self._maintenance_thread.start()

    def process(self, data):
        with self.lock:
            self.metrics.flush_if_due()
            self.requests.expire_if_needed()

            protocol = data.get("protocol")
            if protocol == "ARP":
                self._handle_arp(data)
                return

            if not data.get("is_modbus"):
                return

            self.metrics.count_traffic()

            if data.get("direction") == "request":
                self._handle_modbus_request(data)
            elif data.get("direction") == "response":
                self.requests.handle_response(data)

    def _maintenance_loop(self):
        while True:
            time.sleep(1)
            with self.lock:
                self.requests.expire_if_needed()
                self.metrics.flush_if_due()

    def _handle_arp(self, data):
        self.metrics.count_arp()
        self.devices.touch(data.get("src_ip"), data.get("src_mac"), role="unknown")

    def _handle_modbus_request(self, data):
        master_ip = data.get("src_ip")
        slave_ip = data.get("dst_ip")
        unit_id = data.get("unit_id")
        function_code = data.get("function_code")

        self.metrics.count_request()

        self.devices.touch(master_ip, data.get("src_mac"), role="master")
        self.devices.touch(slave_ip, data.get("dst_mac"), role="slave")
        self.connections.touch(master_ip, slave_ip, unit_id)
        self._track_function_code(master_ip, slave_ip, unit_id, function_code)
        self.registers.process_changes(data)
        self.requests.add_request(data)

    def _track_function_code(self, master_ip, slave_ip, unit_id, function_code):
        fc_key = (slave_ip, unit_id, function_code)
        if fc_key in self.known_function_codes:
            return

        self.known_function_codes.add(fc_key)
        if self.in_learning_mode():
            return

        self.writer.insert_event(
            event_key=f"new_function_code:{slave_ip}:{unit_id}:{function_code}",
            event_type="new_function_code",
            severity="info",
            source_ip=master_ip,
            target_ip=slave_ip,
            unit_id=unit_id,
            function_code=function_code,
            details={"message": "New function code observed on this slave"},
        )


