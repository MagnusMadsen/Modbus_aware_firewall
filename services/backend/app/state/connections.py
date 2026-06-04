from state.time_utils import now


class ConnectionTracker:
    def __init__(self, writer, learning_mode, sql_touch_seconds: int):
        self.writer = writer
        self.learning_mode = learning_mode
        self.sql_touch_seconds = sql_touch_seconds
        self.known_connections = set()
        self.last_seen = {}
        self.last_sql_touch = {}
        self.last_event_id = {}

    def touch(self, master_ip, slave_ip, unit_id):
        if not master_ip or not slave_ip:
            return

        current_time = now()
        key = (master_ip, slave_ip, unit_id)
        is_new = key not in self.known_connections

        self.known_connections.add(key)
        self.last_seen[key] = current_time

        if is_new:
            self.writer.upsert_connection(master_ip, slave_ip, unit_id)
            self.last_sql_touch[key] = current_time

            if not self.learning_mode():
                event_id = self.writer.insert_event(
                    event_key=f"new_connection:{master_ip}:{slave_ip}:{unit_id}",
                    event_type="new_connection",
                    severity="info",
                    source_ip=master_ip,
                    target_ip=slave_ip,
                    unit_id=unit_id,
                    details={"message": "New master/slave relation observed"},
                )
                self.last_event_id[key] = event_id
            return

        last_touch = self.last_sql_touch.get(key)
        if last_touch is None or (current_time - last_touch).total_seconds() >= self.sql_touch_seconds:
            self.writer.upsert_connection(master_ip, slave_ip, unit_id)
            self.last_sql_touch[key] = current_time
