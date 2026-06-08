# capture.py starter selve packet capture-delen af backend.
# Filen sætter netværksinterface op, starter Scapy sniff(), og sender hver fanget packet videre i programmet.
# capture.py læser ikke selv Ethernet-, IP-, TCP-, MBAP- eller Modbus-felter.
# Den modtager en rå Scapy-packet fra sniff(), sender den til packet_parser/parser.py, og sender derefter parserens data-dict videre til state-laget.

# Flowet i denne fil:
# start_capture_thread()
# └─ run_capture()
#    ├─ setup_switch_interface()
#    └─ start_capture(CAPTURE_INTERFACE)
#       └─ sniff(..., prn=handle_packet, filter=CAPTURE_FILTER)
#          └─ handle_packet(pkt)
#             ├─ parse_packet(pkt)
#             └─ process_observation(data)
#                └─ state/manager.py behandler observationen videre

# Hele pakken som Scapy fanger kan forstås sådan her hvilket også bliver refereret i packet_parser/parser.py:
# Ethernet frame
# ┌──────────────┬──────────────┬────────────┬───────────────┬───────────────┬──────────────────────────────────────────┐
# │ dst MAC      │ src MAC      │ EtherType  │ IP header     │ TCP header    │ TCP payload                              │
# └──────────────┴──────────────┴────────────┴───────────────┴───────────────┴──────────────────────────────────────────┘
#                                                                                  │
#                                                                                  ▼
#             TCP payload ved Modbus TCP
#             ┌──────────────────────────── MBAP header ────────────────────────────┬────────────── Modbus PDU ──────────────┐
#             │ Transaction ID │ Protocol ID │ Length │ Unit ID │ Function Code     │ Data                                   │
#             │ 2 bytes        │ 2 bytes     │ 2 bytes│ 1 byte  │ 1 byte            │ Modbus-data efter function code        │
#             └────────────────┴─────────────┴────────┴─────────┴───────────────────┴────────────────────────────────────────┘
#
# Vigtigt: capture.py ser kun den rå packet som pkt.
# packet_parser/parser.py er filen der læser lagene individuelt: pkt[Ether], pkt[ARP], pkt[IP], pkt[TCP] og bytes(pkt[TCP].payload).
# capture.py fungerer derfor som indgangen til pipeline: fang packet -> parser packet -> send observation videre.

import logging
import os
import subprocess
import threading

from scapy.all import sniff
from scapy.error import Scapy_Exception

from packet_parser import parse_packet
from state import process_observation


# CAPTURE_INTERFACE er det netværksinterface der lyttes på. Standard er eth0.
# CAPTURE_FILTER er et BPF-filter til Scapy/libpcap-laget.
# BPF står for Berkeley Packet Filter.
# Filteret begrænser hvilke pakker Scapy modtager fra interfacet, før Python-koden behandler dem.
# Her fanges kun ARP og TCP port 502, fordi ARP bruges til IP/MAC-observationer, og TCP port 502 er Modbus TCP.
CAPTURE_INTERFACE = os.getenv("CAPTURE_INTERFACE", "eth0")
CAPTURE_FILTER = os.getenv("CAPTURE_FILTER", "arp or tcp port 502")

# SWITCH_INTERFACE bruges kun hvis backend også skal sætte et separat switch-management interface op.
# Hvis variablen er tom, springes switch-setup over.
# SWITCH_INTERFACE_IP er den IP backend prøver at give dette interface.
SWITCH_INTERFACE = os.getenv("SWITCH_INTERFACE", "")
SWITCH_INTERFACE_IP = os.getenv("SWITCH_INTERFACE_IP", "192.168.61.250/24")

# Logger bruges til at vise status og fejl i backend-containerens logs.
# Det er derfor man kan se capture-fejl med docker compose logs backend.
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# run_command() kører Linux-kommandoer fra Python.
# Den bruges her til ip link/ip addr kommandoer, når interfaces skal sættes op.
# check=False betyder at programmet selv håndterer fejl i stedet for at crashe automatisk.
def run_command(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
    )


# handle_packet() bliver kaldt af Scapy én gang for hver packet sniff() fanger.
# pkt er den rå Scapy-packet.
# parse_packet(pkt) laver pakken om til en dictionary med f.eks. src_ip, dst_ip, src_mac, dst_mac og Modbus-felter.
# process_observation(data) sender den parsede observation videre til state-laget.
# try/except gør at én dårlig packet ikke stopper hele capture-processen.
def handle_packet(pkt):
    try:
        # parse_packet() er første sted hvor den rå packet bliver læst lag for lag.
        # Resultatet er et data-dict med f.eks. src_ip, dst_ip, protocol, direction, unit_id og function_code.
        data = parse_packet(pkt)
        # None betyder at parseren ikke kunne bruge pakken, f.eks. hvis den hverken var ARP eller IP.
        if data is None:
            return

        # Sender den parsede observation videre til state/__init__.py.
        # Derfra går den videre til ModbusStateManager.process(data).
        process_observation(data)

    except Exception:
        logger.exception("Failed to process packet")


# run_capture() er hovedflowet for capture.
# Først sættes switch-interface op, hvis det er konfigureret.
# Derefter startes sniffing på CAPTURE_INTERFACE.
def run_capture():
    setup_switch_interface()
    start_capture(CAPTURE_INTERFACE)


# start_capture_thread() starter capture i en baggrundstråd.
# daemon=True betyder at tråden stopper sammen med resten af backend-processen.
# Det gør at Flask/API kan køre samtidig med at packet capture lytter i baggrunden.
def start_capture_thread():
    thread = threading.Thread(
        target=run_capture,
        daemon=True,
        name="packet-capture",
    )
    thread.start()


# setup_interface() gør capture-interfacet klar.
# ip link set <interface> up aktiverer interfacet.
# promisc on sætter interfacet i promiscuous mode, så det kan se mere trafik end kun pakker direkte til egen MAC.
# Det er nødvendigt når IDS'en skal overvåge spejlet OT-trafik passivt.
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


# setup_switch_interface() bruges kun til et separat switch-management interface.
# Funktionen springer over hvis SWITCH_INTERFACE ikke er sat.
# Den sætter interfacet up og prøver at tildele SWITCH_INTERFACE_IP.
# "File exists" accepteres, fordi IP'en allerede kan være sat fra en tidligere kørsel.
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


# start_capture() starter Scapy sniffing.
# iface bestemmer hvilket interface der lyttes på.
# prn=handle_packet betyder at hver packet sendes til handle_packet().
# store=False betyder at Scapy ikke gemmer alle pakker i RAM.
# promisc=True beder Scapy om promiscuous mode under sniffing.
# filter=CAPTURE_FILTER begrænser capture til ARP og Modbus TCP-trafik.
def start_capture(interface: str) -> None:
    setup_interface(interface)
    logger.info("Starting sniff on interface: %s with filter: %s", interface, CAPTURE_FILTER)

    try:
        # sniff() er Scapy-funktionen der lytter live på interfacet.
        # For hver packet der matcher CAPTURE_FILTER, kalder Scapy handle_packet(pkt).
        sniff(
            iface=interface,
            prn=handle_packet,
            store=False,
            promisc=True,
            filter=CAPTURE_FILTER,
        )
    except Scapy_Exception:
        logger.exception("Filtered sniff failed. Capture stopped.")