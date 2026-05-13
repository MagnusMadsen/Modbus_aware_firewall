from storage.base import execute


def upsert_register_state(slave_ip, unit_id, register_type, register_address, value):
    if slave_ip is None or unit_id is None or register_type is None or register_address is None:
        return

    execute(
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

    