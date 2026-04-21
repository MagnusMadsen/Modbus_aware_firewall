from flask import Flask, jsonify
from db import get_connection
from psycopg2.extras import RealDictCursor

from capture import start_capture
from parser import parse_packet

from api import api_bp
from storage import save_packet
from capture import start_capture_thread

import threading
import os

CAPTURE_INTERFACE = os.getenv("CAPTURE_INTERFACE", "eth0")

app = Flask(__name__)
app.register_blueprint(api_bp)


if __name__ == "__main__":
    start_capture_thread()
    app.run(host="0.0.0.0", port=8000, debug=False)
    