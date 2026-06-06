# switch_monitor.py henter port- og MAC-information fra Westermo-switchen via SNMP.
# Data kommer ikke fra packet capture. Den kommer fra snmpwalk-kommandoer mod switchens SNMP OID'er.
# Filen bruges af dashboard/ports.py til at koble switch-porte sammen med devices og Modbus-forbindelser.
# Formålet er at vise hvilke fysiske switch-porte der er aktive, og hvilke MAC/IP-adresser der kan kobles til hvilke porte.

# Overordnet dataflow:
# dashboard/ports.py
# ├─ get_switch_ports()
# │  └─ henter portnavn, hastighed, admin-status og link-status fra switchen
# ├─ get_ip_to_port_map()
# │  ├─ henter IP -> MAC fra switchens ARP-tabel
# │  └─ henter MAC -> port fra switchens forwarding database
# └─ kombinerer switch-data med devices og observed_connections til frontend
#
# SNMP-flow i denne fil:
# _run_snmpwalk(oid)
# └─ kører kommandoen snmpwalk mod SWITCH_IP
#    └─ raw tekst-output fra switchen
#       └─ parser-funktioner laver output om til Python dictionaries

import os 
import re
import subprocess


from typing import Dict, List
from config import read_secret_env


# SWITCH_IP er IP-adressen på den switch der spørges via SNMP.
# SNMP_COMMUNITY læses som secret, fordi community-string fungerer som adgangskode til SNMP.
# SNMP_VERSION er som standard v2c.
SWITCH_IP = os.getenv("SWITCH_IP","192.168.61.162")
SNMP_COMMUNITY = read_secret_env("SNMP_COMMUNITY")
SNMP_VERSION = os.getenv("SNMP_VERSION", "2c")

# OID_* værdierne er SNMP-adresser til bestemte tabeller/felter i switchen.
# IF-MIB OID'er bruges til interface-navn, hastighed, admin-status og oper-status.
# Q-BRIDGE/BRIDGE OID'er bruges til at finde MAC-adresser i switchens forwarding database og koble dem til bridge ports.
# IP-MIB OID bruges til at læse switchens IP -> MAC mapping fra ARP/neighbor-tabellen.
OID_IF_NAME = "1.3.6.1.2.1.2.2.1.2"
OID_IF_SPEED = "1.3.6.1.2.1.2.2.1.5"
OID_IF_ADMIN_STATUS = "1.3.6.1.2.1.2.2.1.7"
OID_IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8"

OID_QBRIDGE_FDB_PORT = "1.3.6.1.2.1.17.7.1.2.2.1.2"
OID_QBRIDGE_FDB_STATUS = "1.3.6.1.2.1.17.7.1.2.2.1.3"
OID_BASEPORT_IFINDEX = "1.3.6.1.2.1.17.1.4.1.2"

OID_IP_NET_TO_MEDIA_PHYS = "1.3.6.1.2.1.4.22.1.2"

# Matcher fysiske porte med navne som eth1, eth2 osv.
# Bruges til at sortere rigtige switch-porte fra interne interfaces som lo og vlan1.
PHYSICAL_PORT_RE = re.compile(r"eth(\d+)$")


# _run_snmpwalk() kører systemkommandoen snmpwalk for én bestemt OID.
# oid fortæller hvilken SNMP-tabel eller hvilket SNMP-felt der skal hentes fra switchen.
# Funktionen returnerer rå tekst-output fra snmpwalk.
# Parser-funktionerne nedenunder laver den rå tekst om til dictionaries.
def _run_snmpwalk(oid: str) -> str:
    # subprocess.run() starter snmpwalk som ekstern kommando i containeren.
    # check=True betyder at Python kaster en fejl, hvis snmpwalk fejler.
    result = subprocess.run(
        [
            "snmpwalk",
            f"-v{SNMP_VERSION}",
            "-c",
            SNMP_COMMUNITY,
            SWITCH_IP,
            oid,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    # stdout er tekst-outputtet fra snmpwalk. Det parses bagefter af de andre funktioner.
    return result.stdout


# _parse_snmp_output() parser almindeligt SNMP-output hvor sidste OID-tal er interface-index.
# Eksempel: IF-MIB::ifDescr.3 = STRING: eth3 bliver til {3: "eth3"}.
# Funktionen bruges til interface-navne, hastigheder og statusfelter.
def _parse_snmp_output(raw: str) -> Dict[int, str]:
    # parsed får formatet {index: value}.
    parsed: Dict[int, str] = {}

    # Gennemgår snmpwalk-output linje for linje.
    for line in raw.splitlines():
        line = line.strip()
        if not line or " = " not in line:
            continue

        # Venstre side er OID'en. Højre side er typen og værdien fra SNMP.
        left, right = line.split(" = ", 1)
        # Sidste tal i OID'en bruges som interface-index.
        index_str = left.split(".")[-1]

        try:
            index = int(index_str)
        except ValueError:
            continue

        # SNMP-output har ofte formatet TYPE: value. Vi gemmer kun selve value.
        if ": " in right:
            value = right.split(": ", 1)[1].strip()
        else:
            value = right.strip()

        value = value.strip('"')
        parsed[index] = value

    return parsed


# _format_speed() laver rå interface-hastighed fra SNMP om til læsbar tekst.
# SNMP returnerer hastighed som tal i bits per second.
# Dashboardet viser derfor f.eks. 100 Mbps eller 1 Gbps i stedet for 100000000.
def _format_speed(speed_raw: str) -> str:
    try:
        speed = int(speed_raw)
    except (TypeError, ValueError):
        return "-"

    if speed <= 0:
        return "-"
    if speed >= 1_000_000_000:
        return f"{speed // 1_000_000_000} Gbps"
    if speed >= 1_000_000:
        return f"{speed // 1_000_000} Mbps"
    if speed >= 1_000:
        return f"{speed // 1_000} Kbps"
    return f"{speed} bps"


# _map_state() oversætter SNMP oper_status til dashboard-state.
# oper_status "1" betyder up/link aktiv. Alt andet behandles som inactive.
def _map_state(oper_status: str) -> str:
    return "active" if oper_status == "1" else "inactive"


# _map_activity() laver en kort tekst til frontend om portens linkstatus.
# Hvis oper_status er 1, vises link up. Ellers vises no link.
def _map_activity(oper_status: str, speed_raw: str) -> str:
    if oper_status == "1":
        return "link up"
    return "no link"


# _extract_port_number() trækker portnummeret ud af interface-navnet.
# Eksempel: eth7 bliver til 7.
# Hvis navnet ikke matcher en fysisk port, returneres 9999, så den sorteres sidst.
def _extract_port_number(name: str) -> int:
    cleaned = name.strip()
    match = PHYSICAL_PORT_RE.search(cleaned)
    if not match:
        return 9999
    return int(match.group(1))


# _is_physical_port() afgør om et interface skal vises som fysisk switch-port.
# lo og vlan1 sorteres fra, fordi de ikke er fysiske frontporte.
# Kun navne der matcher eth<nummer> accepteres.
def _is_physical_port(name: str) -> bool:
    cleaned = name.strip()
    if cleaned in {"lo", "vlan1"}:
        return False
    return bool(PHYSICAL_PORT_RE.search(cleaned))


# _parse_ip_net_to_media_phys() parser switchens IP -> MAC mapping fra SNMP.
# Det svarer praktisk til at læse switchens ARP/neighbor-information.
# Output bliver et dict med formatet {ip: mac}.
# Det bruges senere til at koble en device-IP fra databasen til en MAC-adresse på en switch-port.
def _parse_ip_net_to_media_phys(raw: str) -> Dict[str, str]:
    # result får formatet {"192.168.61.x": "aa:bb:cc:dd:ee:ff"}.
    result: Dict[str, str] = {}

    for line in raw.splitlines():
        line = line.strip()
        if not line or " = " not in line:
            continue

        left, right = line.split(" = ", 1)
        # IP-adressen ligger som de sidste fire tal i OID'en.
        oid_tail = left.split(OID_IP_NET_TO_MEDIA_PHYS, 1)[-1].lstrip(".")
        parts = oid_tail.split(".")

        if len(parts) < 5:
            continue

        ip = ".".join(parts[-4:])

        if ": " not in right:
            continue

        # SNMP returnerer MAC som hex bytes med mellemrum. Den laves om til aa:bb:cc-format.
        mac_hex = right.split(": ", 1)[1].strip()
        mac = ":".join(part.lower() for part in mac_hex.split())

        result[ip] = mac

    return result


# get_ip_to_port_map() bygger den samlede mapping fra IP-adresse til switch-port.
# Den kombinerer to SNMP-kilder:
# 1. IP -> MAC fra switchens ARP/neighbor-tabel.
# 2. MAC -> port fra switchens forwarding database.
# Resultatet bruges af dashboard/ports.py til at placere devices på de rigtige fysiske porte.
def get_ip_to_port_map() -> Dict[str, dict]:
    # Først hentes IP -> MAC fra switchen.
    arp_map = _parse_ip_net_to_media_phys(_run_snmpwalk(OID_IP_NET_TO_MEDIA_PHYS))
    # Derefter hentes MAC -> port, så IP kan kobles videre til port.
    mac_to_port = get_mac_to_port_map()

    # For hver IP/MAC prøver vi at finde den fysiske port hvor MAC-adressen er lært.
    ip_to_port: Dict[str, dict] = {}

    for ip, mac in arp_map.items():
        mapping = mac_to_port.get(mac.lower())
        if not mapping:
            continue

        ip_to_port[ip] = {
            "mac": mac.lower(),
            "port": mapping["port"],
            "ifindex": mapping.get("ifindex"),
            "ifname": mapping.get("ifname"),
            "vlan_id": mapping.get("vlan_id"),
            "fdb_status": mapping.get("fdb_status"),
        }

    return ip_to_port


# get_mac_to_port_map() bygger mapping fra MAC-adresse til fysisk switch-port.
# Q-BRIDGE-FDB fortæller hvilken bridge_port en MAC-adresse er lært på.
# BASEPORT_IFINDEX oversætter bridge_port til ifindex.
# IF-MIB ifName oversætter ifindex til interface-navn, f.eks. eth7.
# Til sidst laves eth7 om til "Port 7".
def get_mac_to_port_map() -> Dict[str, dict]:
    # Henter alle nødvendige SNMP-tabeller og parser dem til dictionaries.
    names = _parse_snmp_output(_run_snmpwalk(OID_IF_NAME))
    baseport_ifindex = _parse_snmp_output(_run_snmpwalk(OID_BASEPORT_IFINDEX))
    qbridge_ports = _parse_qbridge_port_map(_run_snmpwalk(OID_QBRIDGE_FDB_PORT))
    qbridge_status = _parse_qbridge_status_map(_run_snmpwalk(OID_QBRIDGE_FDB_STATUS))

    mac_to_port: Dict[str, dict] = {}

    # Gennemgår MAC-adresser switchen har lært i forwarding database.
    for mac, entry in qbridge_ports.items():
        # bridge_port er switchens interne bridge-portnummer, ikke nødvendigvis det samme som eth-portnummeret.
        bridge_port = entry["bridge_port"]
        # bridge_port oversættes til ifindex, som IF-MIB bruger til interface-navne.
        ifindex_raw = baseport_ifindex.get(bridge_port)
        if ifindex_raw is None:
            continue

        try:
            ifindex = int(ifindex_raw)
        except Exception:
            continue

        # ifindex oversættes til interface-navn, f.eks. eth7.
        if_name = (names.get(ifindex) or "").strip()
        # Interne interfaces sorteres fra, så dashboardet kun viser fysiske switch-porte.
        if not _is_physical_port(if_name):
            continue

        mac_to_port[mac] = {
            "port": f"Port {_extract_port_number(if_name)}",
            "ifindex": ifindex,
            "ifname": if_name,
            "vlan_id": entry["vlan_id"],
            "fdb_status": qbridge_status.get(mac),
        }

    return mac_to_port


# get_switch_ports() henter status for de fysiske switch-porte.
# Funktionen bruges af dashboard/ports.py som grundliste over porte.
# Den henter interface-navn, hastighed, admin-status og oper-status via SNMP.
# Resultatet er en liste af port-dicts, som frontend kan vise i port-sektionen.
def get_switch_ports() -> List[dict]:
    # SNMP kan fejle hvis switchen ikke svarer, community er forkert, eller snmpwalk ikke virker.
    try:
        names = _parse_snmp_output(_run_snmpwalk(OID_IF_NAME))
        speeds = _parse_snmp_output(_run_snmpwalk(OID_IF_SPEED))
        admin_statuses = _parse_snmp_output(_run_snmpwalk(OID_IF_ADMIN_STATUS))
        oper_statuses = _parse_snmp_output(_run_snmpwalk(OID_IF_OPER_STATUS))
    except Exception as exc:
        # Ved SNMP-fejl returneres en dummy-port med fejlteksten, så dashboardet kan vise problemet i stedet for at crashe.
        return [
            {
                "port": "SNMP",
                "name": "Westermo switch",
                "speed": "-",
                "activity": str(exc),
                "state": "inactive",
            }
        ]

    # ports bliver listen som frontend senere får via dashboard/ports.py.
    ports: List[dict] = []

    # Gennemgår alle interfaces fra SNMP og beholder kun fysiske eth-porte.
    for index, raw_name in names.items():
        name = raw_name.strip()
        if not _is_physical_port(name):
            continue

        # oper_status viser om linket faktisk er oppe eller nede.
        # admin_status viser om porten administrativt er enabled eller disabled.
        oper_status = oper_statuses.get(index, "2")
        admin_status = admin_statuses.get(index, "2")
        speed_raw = speeds.get(index, "0")

        state = _map_state(oper_status)
        activity = _map_activity(oper_status, speed_raw)

        # Hvis porten administrativt er nede, vises den som inactive uanset oper_status.
        if admin_status != "1":
            activity = "admin down"
            state = "inactive"

        port_number = _extract_port_number(name)

        ports.append(
            {
                "port": f"Port {port_number}",
                "name": name,
                "speed": _format_speed(speed_raw),
                "activity": activity,
                "state": state,
                "devices": [],
            }
        )

    # Sorterer portene numerisk, så Port 2 ikke kommer efter Port 10 som tekstsortering.
    ports.sort(key=lambda item: int(item["port"].split()[-1]))
    return ports

# _parse_qbridge_port_map() parser Q-BRIDGE forwarding database.
# SNMP-OID'en indeholder VLAN ID og MAC-adresse som tal i slutningen af OID'en.
# Værdien på højre side er bridge_port.
# Output bliver {mac: {vlan_id, bridge_port}}.
def _parse_qbridge_port_map(raw: str) -> Dict[str, dict]:
    result: Dict[str, dict] = {}

    for line in raw.splitlines():
        line = line.strip()
        if not line or " = " not in line:
            continue

        left, right = line.split(" = ", 1)

        # Samler alle tal fra OID'en, så VLAN ID og MAC-bytes kan hentes ud.
        numeric_parts = []
        for token in left.split("."):
            if token.isdigit():
                numeric_parts.append(int(token))

        # De sidste 7 tal er typisk VLAN ID + 6 MAC-bytes.
        if len(numeric_parts) < 7:
            continue

        tail = numeric_parts[-7:]
        vlan_id = tail[0]
        mac_bytes = tail[1:7]

        try:
            # Højre side af SNMP-linjen er bridge_port som MAC-adressen er lært på.
            bridge_port = int(right.split(": ", 1)[1].strip())
        except Exception:
            continue

        # MAC-bytes laves om til almindeligt aa:bb:cc:dd:ee:ff-format.
        mac = ":".join(f"{b:02x}" for b in mac_bytes)
        result[mac] = {
            "vlan_id": vlan_id,
            "bridge_port": bridge_port,
        }

    return result

# _parse_qbridge_status_map() parser status for MAC-adresser i Q-BRIDGE forwarding database.
# Output bliver {mac: status}.
# Status kan bruges til at se om en MAC-entry f.eks. er learned eller self.
def _parse_qbridge_status_map(raw: str) -> Dict[str, int]:
    result: Dict[str, int] = {}

    for line in raw.splitlines():
        line = line.strip()
        if not line or " = " not in line:
            continue

        left, right = line.split(" = ", 1)

        # Samler alle tal fra OID'en, så MAC-bytes kan hentes ud.
        numeric_parts = []
        for token in left.split("."):
            if token.isdigit():
                numeric_parts.append(int(token))

        # De sidste 7 tal er typisk VLAN ID + 6 MAC-bytes. Her bruges kun MAC-bytes.
        if len(numeric_parts) < 7:
            continue

        tail = numeric_parts[-7:]
        mac_bytes = tail[1:7]

        try:
            # Højre side af SNMP-linjen er statuskoden for MAC-entryen.
            status = int(right.split(": ", 1)[1].strip())
        except Exception:
            continue

        # MAC-bytes laves om til almindeligt aa:bb:cc:dd:ee:ff-format.
        mac = ":".join(f"{b:02x}" for b in mac_bytes)
        result[mac] = status

    return result
