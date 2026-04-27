import logging
import os
import subprocess
import threading

from scapy.all import sniff
from scapy.error import Scapy_Exception

from parser import parse_packet
from state_manager import process_observation

CAPTURE_INTERFACE = os.getenv("CAPTURE_INTERFACE", "eth0")
CAPTURE_FILTER = os.getenv("CAPTURE_FILTER", "arp or tcp port 502")

SWITCH_INTERFACE = os.getenv("SWITCH_INTERFACE", "")
SWITCH_INTERFACE_IP = os.getenv("SWITCH_INTERFACE_IP", "192.168.61.250/24") 

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
    setup_switch_interface()
    start_capture(CAPTURE_INTERFACE)


def start_capture_thread():
    thread = threading.Thread(target=run_capture, daemon=True)
    thread.start()


def setup_interface(interface: str) -> None:
    logger.info("Setting up interface: %s", interface)
    subprocess.run(["ip", "link", "set", interface, "up"], check=False)
    subprocess.run(["ip", "link", "set", interface, "promisc", "on"], check=False)
    logger.info("Interface ready: %s", interface)
    
def setup_switch_interface() -> None:
    if not SWITCH_INTERFACE:
        logger.info("No switch interface configured")
        return

    logger.info("Setting up switch interface: %s", SWITCH_INTERFACE)

    subprocess.run(
        ["ip", "link", "set", SWITCH_INTERFACE, "up"],
        check=False,
    )

    result = subprocess.run(
        ["ip", "addr", "add", SWITCH_INTERFACE_IP, "dev", SWITCH_INTERFACE],
        check=False,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0 and "File exists" not in result.stderr:
        logger.warning(
            "Could not add IP %s to %s: %s",
            SWITCH_INTERFACE_IP,
            SWITCH_INTERFACE,
            result.stderr.strip(),
        )

    logger.info("Switch interface ready: %s %s", SWITCH_INTERFACE, SWITCH_INTERFACE_IP)

def start_capture(interface: str) -> None:
    setup_interface(interface)
    logger.info("Starting sniff on interface: %s with filter: %s", interface, CAPTURE_FILTER)

    try:
        sniff(
            iface=interface,
            prn=handle_packet,
            store=False,
            promisc=True,
            filter=CAPTURE_FILTER,
        )
    except Scapy_Exception:
        logger.exception("Filtered sniff failed. Falling back to unfiltered sniff.")
        sniff(
            iface=interface,
            prn=handle_packet,
            store=False,
            promisc=True,
        )