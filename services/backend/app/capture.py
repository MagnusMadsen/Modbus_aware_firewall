import logging
import os
import subprocess
import threading

from scapy.all import sniff

from parser import parse_packet
from state_manager import process_observation

CAPTURE_INTERFACE = os.getenv("CAPTURE_INTERFACE", "eth0")
CAPTURE_FILTER = os.getenv("CAPTURE_FILTER", "arp or tcp port 502")

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def handle_packet(pkt):
    try:
        data = parse_packet(pkt)
        if data is None:
            return
        process_observation(data)
    except Exception:
        logger.exception("Failed to process packet")


def run_capture():
    start_capture(CAPTURE_INTERFACE)


def start_capture_thread():
    thread = threading.Thread(target=run_capture, daemon=True)
    thread.start()


def setup_interface(interface: str) -> None:
    logger.info("Setting up interface: %s", interface)
    subprocess.run(["ip", "link", "set", interface, "up"], check=False)
    subprocess.run(["ip", "link", "set", interface, "promisc", "on"], check=False)
    logger.info("Interface ready: %s", interface)


def start_capture(interface: str) -> None:
    setup_interface(interface)
    logger.info("Starting sniff on interface: %s with filter: %s", interface, CAPTURE_FILTER)
    sniff(
        iface=interface,
        prn=handle_packet,
        store=False,
        promisc=True,
        filter=CAPTURE_FILTER,
    )