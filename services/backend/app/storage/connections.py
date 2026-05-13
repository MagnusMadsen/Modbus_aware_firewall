from storage.base import execute


def upsert_connection(master_ip, slave_ip, unit_id=None):
    if not master_ip or not slave_ip:
        return

    execute(
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