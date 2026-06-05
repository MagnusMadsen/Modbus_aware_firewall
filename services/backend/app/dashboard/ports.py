# ports.py bygger port-sektionen til dashboardet.
# Filen kombinerer data fra switch_monitor, devices-tabellen og observed_connections.
# Resultatet er en liste over switch-porte med status, tilknyttede devices, VLANs og event_id til port-alarmer.
# Filen læser switch-data via SNMP-funktioner i switch_monitor.py og bruger storage-writeren til at oprette port_active events.
from switch_monitor import get_mac_to_port_map, get_switch_ports
from storage import get_writer


# attach_port_events() opretter et event for hver aktiv switch-port.
# Kun porte hvor state == "active" får et port_active event.
# event_key bygges som port_active:<portnavn>, så samme aktive port genbruger samme event i events-tabellen.
# event_id gemmes direkte på port-dictet, så frontend kan sende alarm_approvals.event_id tilbage ved godkendelse.
def attach_port_events(ports):
    writer = get_writer()

    for port in ports:
        # state læses fra port-data og gøres lowercase, så sammenligningen med "active" er stabil.
        state = str(port.get("state") or "").lower()
        if state != "active":
            continue

        # port_name vælger den bedste tilgængelige port-identitet.
        # Den bruges i event_key, så samme port kan genkendes næste gang dashboardet opdateres.
        port_name = port.get("port") or port.get("name") or port.get("ifname") or "unknown"
        event_id = writer.insert_event(
            event_key=f"port_active:{port_name}",
            event_type="port_active",
            severity="medium",
            details={
                "message": "Switch port is active",
                "port": port.get("port"),
                "name": port.get("name"),
                "state": port.get("state"),
                "activity": port.get("activity"),
            },
        )
        port["event_id"] = event_id

    return ports


# build_connection_groups() samler observed_connections-rækker efter master_ip.
# Input kommer fra dashboard/queries.py get_connection_rows().
# Output bruges af frontend til at vise hvilke slaves hver master kommunikerer med.
# unit_id vises sammen med slave_ip, fordi samme slave-IP kan have flere Modbus unit IDs.
def build_connection_groups(rows): 
    groups = {}

    for row in rows:
        master = row["master_ip"]
        # Første gang en master ses, oprettes en gruppe til dens slaves.
        if master not in groups:
            groups[master] = {
                "master": master,
                "slave_count": 0,
                "last_seen": row["last_seen"],
                "slaves": [],
            }

        # Hver database-række repræsenterer én master -> slave -> unit_id relation.
        groups[master]["slaves"].append(
            {
                "ip": f"{row['slave_ip']} (unit {row['unit_id']})" if row["unit_id"] else row["slave_ip"],
                "status": "online",
                "packets": row["request_count"],
                "last_seen": row["last_seen"],
            }
        )
        groups[master]["slave_count"] += 1
        groups[master]["last_seen"] = max(groups[master]["last_seen"], row["last_seen"])

    return list(groups.values())


# enrich_ports_with_devices() kobler switch-porte sammen med kendte devices.
# get_mac_to_port_map() henter switchens MAC->port map fra switch_monitor.py.
# devices kommer fra devices-tabellen, og connections kommer fra observed_connections.
# Formålet er at vise hvilke IP/MAC-adresser der sidder på hvilken fysisk switch-port.
def enrich_ports_with_devices(ports, devices, connections):
    mac_to_port = get_mac_to_port_map()

    # device_by_ip gør det hurtigt at slå en device op på IP uden CIDR-suffix.
    # split("/")[0] fjerner f.eks. /32, hvis PostgreSQL INET returnerer IP med suffix.
    device_by_ip = {
        (device.get("ip") or "").split("/")[0]: device
        for device in devices
        if device.get("ip")
    }

    # connection_map bruges til at give en device en rolle ud fra Modbus-kommunikationen.
    # Hvis en IP står som master i observed_connections, får den role_hint master.
    # Hvis en IP står som slave, gemmes dens unit_ids.
    connection_map = {}

    for group in connections:
        master_ip = (group.get("master") or "").split("/")[0]
        connection_map.setdefault(master_ip, {"role_hint": "master", "unit_ids": set()})

        for slave in group.get("slaves", []):
            raw_ip = (slave.get("ip") or "").split(" ")[0]
            slave_ip = raw_ip.split("/")[0]
            unit_text = slave.get("ip") or ""
            unit_id = None

            if "(unit " in unit_text:
                try:
                    unit_id = int(unit_text.split("(unit ")[1].split(")")[0])
                except Exception:
                    unit_id = None

            entry = connection_map.setdefault(slave_ip, {"role_hint": "slave", "unit_ids": set()})
            if unit_id is not None:
                entry["unit_ids"].add(unit_id)

    # port_index gør det hurtigt at finde port-dictet ud fra portnavnet fra switchens MAC-table.
    port_index = {port["port"]: port for port in ports}

    # Her kobles devices til switch-porte.
    # Device MAC bruges til at slå porten op i mac_to_port fra switchen.
    for ip, device in device_by_ip.items():
        mac = (device.get("mac") or "").lower()
        if not mac:
            continue

        mapping = mac_to_port.get(mac)
        if not mapping:
            continue

        port = port_index.get(mapping["port"])
        if not port:
            continue

        conn_info = connection_map.get(ip, {})
        role = device.get("role") or conn_info.get("role_hint") or "unknown"
        unit_ids = sorted(conn_info.get("unit_ids", set()))
        # label er et frontend-navn baseret på rollen: slave vises som PLC, master som Master.
        label = "PLC" if role == "slave" else "Master" if role == "master" else "Device"

        port["devices"].append(
            {
                "ip": ip,
                "mac": mac,
                "role": role,
                "label": label,
                "unit_ids": unit_ids,
                "vlan_id": mapping.get("vlan_id"),
                "ifname": mapping.get("ifname"),
                "ifindex": mapping.get("ifindex"),
            }
        )

    # Efter devices er koblet på porte, beregnes VLANs og duplicate MAC alarms pr. port.
    for port in ports:
        vlan_ids = sorted({
            device["vlan_id"]
            for device in port.get("devices", [])
            if device.get("vlan_id") is not None
        })
        port["vlans"] = vlan_ids

        mac_groups = {}
        for device in port.get("devices", []):
            mac = (device.get("mac") or "").lower()
            ip = device.get("ip")
            if not mac or not ip:
                continue
            mac_groups.setdefault(mac, []).append(ip)

        # duplicate_macs viser om samme MAC er knyttet til flere IP'er på samme port.
        # Det kan indikere uventet netværksadfærd og markeres til frontend.
        duplicate_macs = [
            {"mac": mac, "ips": sorted(set(ips))}
            for mac, ips in mac_groups.items()
            if len(set(ips)) > 1
        ]

        port["duplicate_macs"] = duplicate_macs
        port["has_duplicate_mac_alarm"] = bool(duplicate_macs)

    return ports


# build_ports() er hovedfunktionen som dashboard/service.py bruger.
# Først hentes portstatus fra switch_monitor.py.
# Derefter får aktive porte event_id via attach_port_events().
# Til sidst kobles devices og Modbus connections på portene med enrich_ports_with_devices().
def build_ports(devices, connections):
    ports = get_switch_ports()
    ports = attach_port_events(ports)
    return enrich_ports_with_devices(ports, devices, connections)

