from flask import Flask, jsonify
from capture import start_capture
from parser import parse_packet

import threading
import os

CAPTURE_INTERFACE = os.getenv("CAPTURE_INTERFACE", "eth0")

app = Flask(__name__)

def save_packet(data):
    print("PACKET:", data, flush=True)

def run_capture():
    start_capture(CAPTURE_INTERFACE, lambda pkt: save_packet(parse_packet(pkt)))

def start_capture_thread():
    thread = threading.Thread(target=run_capture, daemon=True)
    thread.start()

@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "backend"})

if __name__ == "__main__":
    start_capture_thread()
    app.run(host="0.0.0.0", port=8000, debug=False)