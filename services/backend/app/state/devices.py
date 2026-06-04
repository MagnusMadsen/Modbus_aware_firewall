from state.time_utils import now


class DeviceTracker:
    def __init__(self, writer, learning_mode, sql_touch_seconds: int):
        self.writer = writer
        self.learning_mode = learning_mode
        self.sql_touch_seconds = sql_touch_seconds
        self.known_devices = {}
        self.last_sql_touch = {}

    def touch(self, ip, mac=None, role=None):
        if not ip or ip in ("0.0.0.0", "255.255.255.255"):
            return

        current_time = now()
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
                    "last_seen": current_time,
                }
                self.known_devices[ip] = existing
            else:
                self.known_devices[ip] = {
                    "mac": normalized_mac,
                    "role": normalized_role,
                    "first_seen": current_time,
                    "last_seen": current_time,
                }

                self.writer.upsert_device(ip, normalized_mac, normalized_role)

                if not self.learning_mode():
                    event_id = self.writer.insert_event(
                        event_key=f"new_device:{ip}",
                        event_type="new_device",
                        severity="info",
                        source_ip=ip,
                        details={
                            "message": "New device observed",
                            "mac": normalized_mac,
                            "role": normalized_role,
                        },
                    )
                    self.known_devices[ip]["last_event_id"] = event_id

                self.last_sql_touch[ip] = current_time
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
            event_id = self.writer.insert_event(
                event_key=f"identity_mac_changed:{ip}",
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
            existing["last_event_id"] = event_id
            existing["mac"] = normalized_mac

        if role_changed:
            event_id = self.writer.insert_event(
                event_key=f"identity_role_changed:{ip}",
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
            existing["last_event_id"] = event_id

        existing["role"] = merged_role
        existing["last_seen"] = current_time

        last_touch = self.last_sql_touch.get(ip)
        should_touch_sql = (
            last_touch is None
            or (current_time - last_touch).total_seconds() >= self.sql_touch_seconds
            or mac_changed
            or role_changed
        )

        if should_touch_sql:
            self.writer.upsert_device(ip, existing.get("mac"), existing.get("role"))
            self.last_sql_touch[ip] = current_time

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
