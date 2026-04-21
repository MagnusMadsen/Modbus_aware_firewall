from flask import Flask, jsonify
from db import get_connection
from psycopg2.extras import RealDictCursor

from capture import start_capture
from parser import parse_packet

from api import api_bp
from storage import save_packet

import threading
import os



CAPTURE_INTERFACE = os.getenv("CAPTURE_INTERFACE", "eth0")

app = Flask(__name__)
app.register_blueprint(api_bp)


def run_capture():
    start_capture(CAPTURE_INTERFACE, lambda pkt: save_packet(parse_packet(pkt)))

def start_capture_thread():
    thread = threading.Thread(target=run_capture, daemon=True)
    thread.start()



if __name__ == "__main__":
    start_capture_thread()
    app.run(host="0.0.0.0", port=8000, debug=False)