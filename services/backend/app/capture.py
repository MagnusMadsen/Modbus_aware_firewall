import logging
import subprocess
from scapy.all import sniff

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def setup_interface(interface: str) -> None:
    logger.info("Setting up interface: %s", interface)
    subprocess.run(["ip", "link", "set", interface, "up"], check=False)
    subprocess.run(["ip", "link", "set", interface, "promisc", "on"], check=False)
    logger.info("Interface ready: %s", interface)

def start_capture(interface: str, handler) -> None:
    setup_interface(interface)
    logger.info("Starting sniff on interface: %s", interface)
    sniff(iface=interface, prn=handler, store=False, promisc=True)