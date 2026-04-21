import os
import threading

from parser import parse_packet
from storage import save_packet

import logging
import subprocess
from scapy.all import sniff

CAPTURE_INTERFACE = os.getenv("CAPTURE_INTERFACE", "eth0") 

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def handle_packet(pkt):
    data = parse_packet(pkt)
    save_packet(data)


def run_capture():
    start_capture(CAPTURE_INTERFACE, handle_packet)


def start_capture_thread():
    thread = threading.Thread(target=run_capture, daemon=True)
    thread.start()


def setup_interface(interface: str) -> None:
    logger.info("Setting up interface: %s", interface)
    subprocess.run(["ip", "link", "set", interface, "up"], check=False)
    subprocess.run(["ip", "link", "set", interface, "promisc", "on"], check=False)
    logger.info("Interface ready: %s", interface)


def start_capture(interface: str, handler) -> None:
    setup_interface(interface)
    logger.info("Starting sniff on interface: %s", interface)
    sniff(iface=interface, prn=handler, store=False, promisc=True)