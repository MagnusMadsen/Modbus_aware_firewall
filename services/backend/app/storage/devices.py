from storage.base import execute, query_one


def get_device_by_ip(ip):
    if not ip:
        return None

    return query_one(
        """
        SELECT
            id,
            ip::text AS ip,
            mac,
            role,
            status,
            first_seen,
            last_seen
        FROM devices
        WHERE ip = %s
        LIMIT 1
        """,
        (ip,),
    )


def upsert_device(ip, mac=None, role=None):
    if not ip or ip in ("0.0.0.0", "255.255.255.255"):
        return

    execute(
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


def update_device_status(device_id: int, status: str) -> bool:
    affected_rows = execute(
        """
        UPDATE devices
        SET status = %s
        WHERE id = %s
        """,
        (status, device_id),
    )
    return affected_rows > 0