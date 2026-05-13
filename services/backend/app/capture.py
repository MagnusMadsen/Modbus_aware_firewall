# Formål 
# 1. Læs capture-konfiguration fra environment
# 2. Sæt netværksinterfaces op
# 3. Start packet sniffing
# 4. For hver packet:
#   - parse packet
#   - send observation til state manager
# 5. Log fejl uden at stoppe capture

import logging
import os
import subprocess
import threading

from scapy.all import sniff
from scapy.error import Scapy_Exception

from packet_parser import parse_packet
from state_manager import process_observation

CAPTURE_INTERFACE = os.getenv("CAPTURE_INTERFACE", "eth0")
CAPTURE_FILTER = os.getenv("CAPTURE_FILTER", "arp or tcp port 502")

SWITCH_INTERFACE = os.getenv("SWITCH_INTERFACE", "")
SWITCH_INTERFACE_IP = os.getenv("SWITCH_INTERFACE_IP", "192.168.61.250/24")

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def run_command(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
    )


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
    thread = threading.Thread(
        target=run_capture,
        daemon=True,
        name="packet-capture",
    )
    thread.start()


def setup_interface(interface: str) -> None:
    logger.info("Setting up interface: %s", interface)

    up_result = run_command(["ip", "link", "set", interface, "up"])
    if up_result.returncode != 0:
        logger.warning(
            "Could not bring interface %s up: %s",
            interface,
            up_result.stderr.strip(),
        )
        return

    promisc_result = run_command(["ip", "link", "set", interface, "promisc", "on"])
    if promisc_result.returncode != 0:
        logger.warning(
            "Could not enable promiscuous mode on %s: %s",
            interface,
            promisc_result.stderr.strip(),
        )
        return

    logger.info("Interface ready: %s", interface)


def setup_switch_interface() -> None:
    if not SWITCH_INTERFACE:
        logger.info("No switch interface configured")
        return

    logger.info("Setting up switch interface: %s", SWITCH_INTERFACE)

    up_result = run_command(["ip", "link", "set", SWITCH_INTERFACE, "up"])
    if up_result.returncode != 0:
        logger.warning(
            "Could not bring switch interface %s up: %s",
            SWITCH_INTERFACE,
            up_result.stderr.strip(),
        )
        return

    addr_result = run_command(
        ["ip", "addr", "add", SWITCH_INTERFACE_IP, "dev", SWITCH_INTERFACE]
    )

    already_assigned = (
        "File exists" in addr_result.stderr
        or "Address already assigned" in addr_result.stderr
    )

    if addr_result.returncode != 0 and not already_assigned:
        logger.warning(
            "Could not add IP %s to %s: %s",
            SWITCH_INTERFACE_IP,
            SWITCH_INTERFACE,
            addr_result.stderr.strip(),
        )
        return

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
        logger.exception("Filtered sniff failed. Capture stopped.")