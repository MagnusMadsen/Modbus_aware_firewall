import os 
import re
import subprocess

from typing import Dict, List

SWITCH_IP = os.getenv("SWITCH_IP","192.168.61.162")
SNMP_COMMUNITY = os.getenv("SNMP_COMMUNITY", "public")
SNMP_VERSION = os.getenv("SNMP_VERSION", "2c")

OID_IF_NAME = "1.3.6.1.2.1.2.2.1.2"
OID_IF_SPEED = "1.3.6.1.2.1.2.2.1.5"
OID_IF_ADMIN_STATUS = "1.3.6.1.2.1.2.2.1.7"
OID_IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8"

OID_QBRIDGE_FDB_PORT = "1.3.6.1.2.1.17.7.1.2.2.1.2"
OID_QBRIDGE_FDB_STATUS = "1.3.6.1.2.1.17.7.1.2.2.1.3"
OID_BASEPORT_IFINDEX = "1.3.6.1.2.1.17.1.4.1.2"
OID_IP_NET_TO_MEDIA_PHYS = "1.3.6.1.2.1.4.22.1.2"

PHYSICAL_PORT_RE = re.compile(r"eth(\d+)$")


def _run_snmpwalk(oid: str) -> str:
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
    return result.stdout


def _parse_snmp_output(raw: str) -> Dict[int, str]:
    parsed: Dict[int, str] = {}

    for line in raw.splitlines():
        line = line.strip()
        if not line or " = " not in line:
            continue

        left, right = line.split(" = ", 1)
        index_str = left.split(".")[-1]

        try:
            index = int(index_str)
        except ValueError:
            continue

        if ": " in right:
            value = right.split(": ", 1)[1].strip()
        else:
            value = right.strip()

        value = value.strip('"')
        parsed[index] = value

    return parsed


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


def _map_state(oper_status: str) -> str:
    return "active" if oper_status == "1" else "inactive"


def _map_activity(oper_status: str, speed_raw: str) -> str:
    if oper_status == "1":
        return "link up"
    return "no link"


def _extract_port_number(name: str) -> int:
    cleaned = name.strip()
    match = PHYSICAL_PORT_RE.search(cleaned)
    if not match:
        return 9999
    return int(match.group(1))


def _is_physical_port(name: str) -> bool:
    cleaned = name.strip()
    if cleaned in {"lo", "vlan1"}:
        return False
    return bool(PHYSICAL_PORT_RE.search(cleaned))


def get_mac_to_port_map() -> Dict[str, dict]:
    names = _parse_snmp_output(_run_snmpwalk(OID_IF_NAME))
    baseport_ifindex = _parse_snmp_output(_run_snmpwalk(OID_BASEPORT_IFINDEX))
    qbridge_ports = _parse_qbridge_port_map(_run_snmpwalk(OID_QBRIDGE_FDB_PORT))
    qbridge_status = _parse_qbridge_status_map(_run_snmpwalk(OID_QBRIDGE_FDB_STATUS))

    mac_to_port: Dict[str, dict] = {}

    for mac, entry in qbridge_ports.items():
        bridge_port = entry["bridge_port"]
        ifindex_raw = baseport_ifindex.get(bridge_port)
        if ifindex_raw is None:
            continue

        try:
            ifindex = int(ifindex_raw)
        except Exception:
            continue

        if_name = (names.get(ifindex) or "").strip()
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


def get_switch_ports() -> List[dict]:
    try:
        names = _parse_snmp_output(_run_snmpwalk(OID_IF_NAME))
        speeds = _parse_snmp_output(_run_snmpwalk(OID_IF_SPEED))
        admin_statuses = _parse_snmp_output(_run_snmpwalk(OID_IF_ADMIN_STATUS))
        oper_statuses = _parse_snmp_output(_run_snmpwalk(OID_IF_OPER_STATUS))
    except Exception as exc:
        return [
            {
                "port": "SNMP",
                "name": "Westermo switch",
                "speed": "-",
                "activity": str(exc),
                "state": "inactive",
            }
        ]

    ports: List[dict] = []

    for index, raw_name in names.items():
        name = raw_name.strip()
        if not _is_physical_port(name):
            continue

        oper_status = oper_statuses.get(index, "2")
        admin_status = admin_statuses.get(index, "2")
        speed_raw = speeds.get(index, "0")

        state = _map_state(oper_status)
        activity = _map_activity(oper_status, speed_raw)

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

    ports.sort(key=lambda item: int(item["port"].split()[-1]))
    return ports

def _parse_qbridge_port_map(raw: str) -> Dict[str, dict]:
    result = {}

    for line in raw.splitlines():
        line = line.strip()
        if " = " not in line:
            continue

        left, right = line.split(" = ", 1)
        oid_tail = left.split(OID_QBRIDGE_FDB_PORT, 1)[-1].lstrip(".")
        parts = oid_tail.split(".")

        if len(parts) < 7:
            continue

        try:
            vlan_id = int(parts[0])
            mac_bytes = [int(x) for x in parts[1:7]]
            bridge_port = int(right.split(": ", 1)[1].strip())
        except Exception:
            continue

        mac = ":".join(f"{b:02x}" for b in mac_bytes)
        result[mac] = {
            "vlan_id": vlan_id,
            "bridge_port": bridge_port,
        }

    return result

def _parse_qbridge_status_map(raw: str) -> Dict[str, int]:
    result = {}

    for line in raw.splitlines():
        line = line.strip()
        if " = " not in line:
            continue

        left, right = line.split(" = ", 1)
        oid_tail = left.split(OID_QBRIDGE_FDB_STATUS, 1)[-1].lstrip(".")
        parts = oid_tail.split(".")

        if len(parts) < 7:
            continue

        try:
            mac_bytes = [int(x) for x in parts[1:7]]
            status = int(right.split(": ", 1)[1].strip())
        except Exception:
            continue

        mac = ":".join(f"{b:02x}" for b in mac_bytes)
        result[mac] = status

    return result


