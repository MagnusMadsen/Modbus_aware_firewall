from flask import Flask, jsonify
from capture import start_capture
from parser import parse_packet
from db import get_connection
from psycopg2.extras import RealDictCursor
from api import api_bp

import threading
import os



CAPTURE_INTERFACE = os.getenv("CAPTURE_INTERFACE", "eth0")

app = Flask(__name__)
app.register_blueprint(api_bp)

def save_packet(data):
    print("PACKET:", data, flush=True)

    conn = get_connection()
    cur = conn.cursor()

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

    if data["src_mac"] and data["src_ip"] and data["src_ip"] != "0.0.0.0":
        cur.execute(
            """
            INSERT INTO devices (ip, mac, first_seen, last_seen)
            VALUES (%s, %s, NOW(), NOW())
            ON CONFLICT (ip, mac)
            DO UPDATE SET last_seen = NOW()
            """,
            (data["src_ip"], data["src_mac"]),
        )

    conn.commit()
    cur.close()
    conn.close()

def run_capture():
    start_capture(CAPTURE_INTERFACE, lambda pkt: save_packet(parse_packet(pkt)))

def start_capture_thread():
    thread = threading.Thread(target=run_capture, daemon=True)
    thread.start()



if __name__ == "__main__":
    start_capture_thread()
    app.run(host="0.0.0.0", port=8000, debug=False)