from datetime import datetime

from scapy.layers.inet import IP, TCP
from scapy.layers.l2 import ARP, Ether


def _decode_coils(byte_data: bytes, count: int):
    values = []
    for i in range(count):
        byte_index = i // 8
        bit_index = i % 8
        if byte_index >= len(byte_data):
            break
        values.append(1 if (byte_data[byte_index] >> bit_index) & 0x01 else 0)
    return values


def _parse_mbap(payload: bytes):
    if len(payload) < 8:
        return None

    transaction_id = int.from_bytes(payload[0:2], byteorder="big")
    protocol_id = int.from_bytes(payload[2:4], byteorder="big")
    length_field = int.from_bytes(payload[4:6], byteorder="big")
    unit_id = payload[6]
    function_code = payload[7]
    pdu = payload[8:]

    if protocol_id != 0:
        return None

    return {
        "transaction_id": transaction_id,
        "protocol_id": protocol_id,
        "length_field": length_field,
        "unit_id": unit_id,
        "function_code": function_code,
        "pdu": pdu,
    }


def _decode_request_fields(function_code: int, pdu: bytes):
    decoded = {
        "register_type": None,
        "register_address": None,
        "register_count": None,
        "values": None,
    }

    if function_code in (1, 2, 3, 4) and len(pdu) >= 4:
        decoded["register_type"] = "coil" if function_code in (1, 2) else "holding_register"
        decoded["register_address"] = int.from_bytes(pdu[0:2], byteorder="big")
        decoded["register_count"] = int.from_bytes(pdu[2:4], byteorder="big")
        return decoded

    if function_code == 5 and len(pdu) >= 4:
        address = int.from_bytes(pdu[0:2], byteorder="big")
        raw_value = int.from_bytes(pdu[2:4], byteorder="big")
        decoded["register_type"] = "coil"
        decoded["register_address"] = address
        decoded["register_count"] = 1
        decoded["values"] = [1 if raw_value == 0xFF00 else 0]
        return decoded

    if function_code == 6 and len(pdu) >= 4:
        address = int.from_bytes(pdu[0:2], byteorder="big")
        value = int.from_bytes(pdu[2:4], byteorder="big")
        decoded["register_type"] = "holding_register"
        decoded["register_address"] = address
        decoded["register_count"] = 1
        decoded["values"] = [value]
        return decoded

    if function_code == 15 and len(pdu) >= 5:
        address = int.from_bytes(pdu[0:2], byteorder="big")
        count = int.from_bytes(pdu[2:4], byteorder="big")
        byte_count = pdu[4]
        coil_bytes = pdu[5:5 + byte_count]
        decoded["register_type"] = "coil"
        decoded["register_address"] = address
        decoded["register_count"] = count
        decoded["values"] = _decode_coils(coil_bytes, count)
        return decoded

    if function_code == 16 and len(pdu) >= 5:
        address = int.from_bytes(pdu[0:2], byteorder="big")
        count = int.from_bytes(pdu[2:4], byteorder="big")
        byte_count = pdu[4]
        value_bytes = pdu[5:5 + byte_count]
        values = []

        for i in range(0, min(len(value_bytes), count * 2), 2):
            if i + 2 <= len(value_bytes):
                values.append(int.from_bytes(value_bytes[i:i + 2], byteorder="big"))

        decoded["register_type"] = "holding_register"
        decoded["register_address"] = address
        decoded["register_count"] = count
        decoded["values"] = values
        return decoded

    return decoded


def _decode_response_fields(function_code: int, pdu: bytes):
    decoded = {
        "register_type": None,
        "register_address": None,
        "register_count": None,
        "values": None,
        "is_exception": False,
        "exception_code": None,
    }

    if function_code & 0x80:
        decoded["is_exception"] = True
        decoded["exception_code"] = pdu[0] if pdu else None
        return decoded

    if function_code in (1, 2) and len(pdu) >= 1:
        byte_count = pdu[0]
        coil_bytes = pdu[1:1 + byte_count]
        decoded["register_type"] = "coil"
        decoded["register_count"] = byte_count * 8
        decoded["values"] = _decode_coils(coil_bytes, byte_count * 8)
        return decoded

    if function_code in (3, 4) and len(pdu) >= 1:
        byte_count = pdu[0]
        value_bytes = pdu[1:1 + byte_count]
        values = []

        for i in range(0, len(value_bytes), 2):
            if i + 2 <= len(value_bytes):
                values.append(int.from_bytes(value_bytes[i:i + 2], byteorder="big"))

        decoded["register_type"] = "holding_register"
        decoded["register_count"] = len(values)
        decoded["values"] = values
        return decoded

    if function_code in (5, 6) and len(pdu) >= 4:
        address = int.from_bytes(pdu[0:2], byteorder="big")
        raw_value = int.from_bytes(pdu[2:4], byteorder="big")

        if function_code == 5:
            decoded["register_type"] = "coil"
            decoded["values"] = [1 if raw_value == 0xFF00 else 0]
        else:
            decoded["register_type"] = "holding_register"
            decoded["values"] = [raw_value]

        decoded["register_address"] = address
        decoded["register_count"] = 1
        return decoded

    if function_code in (15, 16) and len(pdu) >= 4:
        decoded["register_address"] = int.from_bytes(pdu[0:2], byteorder="big")
        decoded["register_count"] = int.from_bytes(pdu[2:4], byteorder="big")
        decoded["register_type"] = "coil" if function_code == 15 else "holding_register"
        return decoded

    return decoded


def _infer_direction(src_port, dst_port, function_code, pdu):
    if dst_port == 502 and src_port != 502:
        return "request"

    if src_port == 502 and dst_port != 502:
        return "response"

    if function_code & 0x80:
        return "response"

    # Fallback for 502 -> 502 traffic
    if function_code in (1, 2, 3, 4):
        if len(pdu) >= 1 and len(pdu) == 1 + pdu[0]:
            return "response"
        if len(pdu) >= 4:
            return "request"

    if function_code in (15, 16):
        if len(pdu) == 4:
            return "response"
        if len(pdu) >= 5:
            byte_count = pdu[4]
            if len(pdu) == 5 + byte_count:
                return "request"

    if function_code in (5, 6):
        if len(pdu) >= 4:
            return "request_or_response"

    return None

def parse_packet(pkt):
    data = {
        "ts": datetime.utcnow().isoformat(),
        "src_mac": None,
        "dst_mac": None,
        "src_ip": None,
        "dst_ip": None,
        "protocol": None,
        "src_port": None,
        "dst_port": None,
        "length": len(pkt),
        "is_modbus": False,
        "direction": None,
        "transaction_id": None,
        "unit_id": None,
        "function_code": None,
        "register_type": None,
        "register_address": None,
        "register_count": None,
        "values": None,
        "is_exception": False,
        "exception_code": None,
        "arp_op": None,
    }

    if pkt.haslayer(Ether):
        data["src_mac"] = pkt[Ether].src
        data["dst_mac"] = pkt[Ether].dst

    if pkt.haslayer(ARP):
        data["protocol"] = "ARP"
        data["src_ip"] = pkt[ARP].psrc
        data["dst_ip"] = pkt[ARP].pdst
        data["arp_op"] = pkt[ARP].op
        return data

    if not pkt.haslayer(IP):
        return None

    data["src_ip"] = pkt[IP].src
    data["dst_ip"] = pkt[IP].dst
    data["protocol"] = "IP"

    if not pkt.haslayer(TCP):
        return data

    data["protocol"] = "TCP"
    data["src_port"] = pkt[TCP].sport
    data["dst_port"] = pkt[TCP].dport

    if data["src_port"] != 502 and data["dst_port"] != 502:
        return data

    payload = bytes(pkt[TCP].payload)
    if not payload:
        return data

    mbap = _parse_mbap(payload)
    if mbap is None:
        return data

    raw_function_code = mbap["function_code"]
    base_function_code = raw_function_code & 0x7F
    pdu = mbap["pdu"]

    data["is_modbus"] = True
    data["protocol"] = "MODBUS"
    data["transaction_id"] = mbap["transaction_id"]
    data["unit_id"] = mbap["unit_id"]
    data["function_code"] = base_function_code
    direction = _infer_direction(
        data["src_port"],
        data["dst_port"],
        raw_function_code,
        pdu,
    )

    if direction is None:
        return data

    # FC 5/6 on 502->502 cannot be distinguished from one packet alone
    # Treat server-originated packet as response when possible, otherwise request
    if direction == "request_or_response":
        if data["src_ip"] == data["dst_ip"]:
            return data
        direction = "request"

    data["direction"] = direction

    if raw_function_code & 0x80:
        response_fields = _decode_response_fields(raw_function_code, pdu)
        data["is_exception"] = response_fields["is_exception"]
        data["exception_code"] = response_fields["exception_code"]
        data["direction"] = "response"
        return data

    if data["direction"] == "request":
        request_fields = _decode_request_fields(base_function_code, pdu)
        data["register_type"] = request_fields["register_type"]
        data["register_address"] = request_fields["register_address"]
        data["register_count"] = request_fields["register_count"]
        data["values"] = request_fields["values"]
    else:
        response_fields = _decode_response_fields(base_function_code, pdu)
        data["register_type"] = response_fields["register_type"]
        data["register_address"] = response_fields["register_address"]
        data["register_count"] = response_fields["register_count"]
        data["values"] = response_fields["values"]
        data["is_exception"] = response_fields["is_exception"]
        data["exception_code"] = response_fields["exception_code"]

    return data