from db import get_connection


def insert_packet_log(cur, data):
    cur.execute(
        """
        INSERT INTO packet_logs (src_mac, dst_mac, src_ip, dst_ip, protocol, src_port, dst_port, length)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            data["src_mac"],
            data["dst_mac"],
            data["src_ip"],
            data["dst_ip"],
            data["protocol"],
            data["src_port"],
            data["dst_port"],
            data["length"],
        ),
    )


def upsert_device(cur, data):
    if not data["src_mac"] or not data["src_ip"] or data["src_ip"] == "0.0.0.0":
        return

    cur.execute(
        """
        INSERT INTO devices (ip, mac, first_seen, last_seen)
        VALUES (%s, %s, NOW(), NOW())
        ON CONFLICT (ip, mac)
        DO UPDATE SET last_seen = NOW()
        """,
        (data["src_ip"], data["src_mac"]),
    )


def save_packet(data):
    print("PACKET:", data, flush=True)

    conn = get_connection()
    cur = conn.cursor()

    insert_packet_log(cur, data)
    upsert_device(cur, data)

    conn.commit()
    cur.close()
    conn.close()