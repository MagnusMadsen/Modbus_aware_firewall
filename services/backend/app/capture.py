import logging
import subprocess
from scapy.all import sniff

logger = logging.getLogger(__name__)

def setup_interface(interface: str) -> None:
    subprocess.run(["ip", "link", "set", interface, "up"], check=False)
    subprocess.run(["ip", "link", "set", interface, "promisc", "on"], check=False)
    logger.info("Interface ready: %s", interface)

def start_capture(interface: str, handler) -> None:
    setup_interface(interface)
    sniff(iface=interface, prn=handler, store=False, promisc=True)