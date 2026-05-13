class RegisterTracker:
    def __init__(self, writer, learning_mode):
        self.writer = writer
        self.learning_mode = learning_mode
        self.register_state = {}

    def process_changes(self, data):
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
                slave_ip=slave_ip,
                unit_id=unit_id,
                register_type=register_type,
                register_address=address,
                new_value=value,
            )

            if old_value is None:
                self.register_state[state_key] = value
                self.writer.upsert_register_state(slave_ip, unit_id, register_type, address, value)

                if not self.learning_mode() or classification["is_pinned"]:
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

    def _classify_register_change(self, slave_ip, unit_id, register_type, register_address, new_value):
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
