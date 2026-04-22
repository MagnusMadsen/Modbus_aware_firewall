import threading
from datetime import datetime

from psycopg2.extras import Json

from db import get_connection


class StorageWriter:
    def __init__(self):
        self._lock = threading.Lock()
        self._conn = None

    def _ensure_connection(self):
        if self._conn is None or self._conn.closed != 0:
            self._conn = get_connection()

    def _execute(self, query, params=None, fetchone=False):
        with self._lock:
            self._ensure_connection()
            try:
                cur = self._conn.cursor()
                cur.execute(query, params or ())
                result = cur.fetchone() if fetchone else None
                self._conn.commit()
                cur.close()
                return result
            except Exception:
                if self._conn:
                    self._conn.rollback()
                raise

    def upsert_device(self, ip, mac=None, role=None):
        if not ip or ip in ("0.0.0.0", "255.255.255.255"):
            return

        self._execute(
            """
            INSERT INTO devices (ip, mac, role, first_seen, last_seen)
            VALUES (%s, %s, %s, NOW(), NOW())
            ON CONFLICT (ip)
            DO UPDATE SET
                mac = COALESCE(EXCLUDED.mac, devices.mac),
                role = COALESCE(EXCLUDED.role, devices.role),
                last_seen = NOW()
            """,
            (ip, mac, role),
        )

    def upsert_connection(self, master_ip, slave_ip, unit_id=None):
        if not master_ip or not slave_ip:
            return

        self._execute(
            """
            INSERT INTO observed_connections
                (master_ip, slave_ip, unit_id, first_seen, last_seen, request_count)
            VALUES
                (%s, %s, %s, NOW(), NOW(), 1)
            ON CONFLICT (master_ip, slave_ip, unit_id)
            DO UPDATE SET
                last_seen = NOW(),
                request_count = observed_connections.request_count + 1
            """,
            (master_ip, slave_ip, unit_id),
        )

    def upsert_register_state(self, slave_ip, unit_id, register_type, register_address, value):
        if slave_ip is None or unit_id is None or register_type is None or register_address is None:
            return

        self._execute(
            """
            INSERT INTO modbus_register_state
                (slave_ip, unit_id, register_type, register_address, last_value, first_seen, last_seen, write_count)
            VALUES
                (%s, %s, %s, %s, %s, NOW(), NOW(), 1)
            ON CONFLICT (slave_ip, unit_id, register_type, register_address)
            DO UPDATE SET
                last_value = EXCLUDED.last_value,
                last_seen = NOW(),
                write_count = modbus_register_state.write_count + 1
            """,
            (slave_ip, unit_id, register_type, register_address, str(value)),
        )

    def insert_event(
        self,
        event_type,
        severity="info",
        source_ip=None,
        target_ip=None,
        unit_id=None,
        function_code=None,
        register_type=None,
        register_address=None,
        old_value=None,
        new_value=None,
        details=None,
    ):
        self._execute(
            """
            INSERT INTO events
                (ts, event_type, severity, source_ip, target_ip, unit_id, function_code,
                 register_type, register_address, old_value, new_value, details)
            VALUES
                (NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                event_type,
                severity,
                source_ip,
                target_ip,
                unit_id,
                function_code,
                register_type,
                register_address,
                None if old_value is None else str(old_value),
                None if new_value is None else str(new_value),
                Json(details or {}),
            ),
        )

    def insert_metrics_bucket(
        self,
        bucket_ts: datetime,
        traffic_count,
        request_count,
        response_count,
        failed_count,
        arp_count,
        avg_latency_ms,
        p95_latency_ms,
        active_connections,
    ):
        self._execute(
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


_writer = None
_writer_lock = threading.Lock()


def get_writer():
    global _writer
    with _writer_lock:
        if _writer is None:
            _writer = StorageWriter()
        return _writer