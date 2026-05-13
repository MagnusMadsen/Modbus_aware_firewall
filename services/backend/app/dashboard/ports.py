from switch_monitor import get_mac_to_port_map, get_switch_ports


def build_connection_groups(rows):
    groups = {}

    for row in rows:
        master = row["master_ip"]
        if master not in groups:
            groups[master] = {
                "master": master,
                "slave_count": 0,
                "last_seen": row["last_seen"],
                "slaves": [],
            }

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


def enrich_ports_with_devices(ports, devices, connections):
    mac_to_port = get_mac_to_port_map()

    device_by_ip = {
        (device.get("ip") or "").split("/")[0]: device
        for device in devices
        if device.get("ip")
    }

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

    port_index = {port["port"]: port for port in ports}

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

        duplicate_macs = [
            {"mac": mac, "ips": sorted(set(ips))}
            for mac, ips in mac_groups.items()
            if len(set(ips)) > 1
        ]

        port["duplicate_macs"] = duplicate_macs
        port["has_duplicate_mac_alarm"] = bool(duplicate_macs)

    return ports


def build_ports(devices, connections):
    ports = get_switch_ports()
    return enrich_ports_with_devices(ports, devices, connections)