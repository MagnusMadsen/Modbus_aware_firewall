from datetime import datetime

from scapy.layers.inet import IP, TCP
from scapy.layers.l2 import ARP, Ether


MODBUS_PORT = 502

READ_REGISTER_TYPES = {
    1: "coil",
    2: "discrete_input",
    3: "holding_register",
    4: "input_register",
}

WRITE_REGISTER_TYPES = {
    5: "coil",
    6: "holding_register",
    15: "coil",
    16: "holding_register",
}

SUPPORTED_FUNCTION_CODES = {1, 2, 3, 4, 5, 6, 15, 16}


def _base_observation(pkt):
    return {
        "ts": datetime.fromtimestamp(float(pkt.time)).isoformat(),
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


def _u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 2], byteorder="big")


def _decode_coils(byte_data: bytes, count: int) -> list[int]:
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

    transaction_id = _u16(payload, 0)
    protocol_id = _u16(payload, 2)
    length_field = _u16(payload, 4)

    if protocol_id != 0:
        return None

    expected_total_length = 6 + length_field
    if expected_total_length < 8:
        return None

    if len(payload) < expected_total_length:
        return None

    frame = payload[:expected_total_length]

    return {
        "transaction_id": transaction_id,
        "unit_id": frame[6],
        "function_code": frame[7],
        "pdu": frame[8:],
    }


def _infer_direction(src_port: int, dst_port: int, raw_function_code: int, pdu: bytes):
    if dst_port == MODBUS_PORT and src_port != MODBUS_PORT:
        return "request"

    if src_port == MODBUS_PORT and dst_port != MODBUS_PORT:
        return "response"

    if raw_function_code & 0x80:
        return "response"

    function_code = raw_function_code & 0x7F

    if function_code in (1, 2, 3, 4):
        if len(pdu) >= 1 and len(pdu) == 1 + pdu[0]:
            return "response"
        if len(pdu) == 4:
            return "request"

    if function_code in (15, 16):
        if len(pdu) == 4:
            return "response"
        if len(pdu) >= 5 and len(pdu) == 5 + pdu[4]:
            return "request"

    # FC5 and FC6 request/response have identical payload format.
    # If ports cannot prove direction, do not guess.
    if function_code in (5, 6):
        return None

    return None


def _decode_read_request(function_code: int, pdu: bytes):
    if function_code not in READ_REGISTER_TYPES or len(pdu) != 4:
        return None

    return {
        "register_type": READ_REGISTER_TYPES[function_code],
        "register_address": _u16(pdu, 0),
        "register_count": _u16(pdu, 2),
        "values": None,
    }


def _decode_write_request(function_code: int, pdu: bytes):
    if function_code == 5 and len(pdu) == 4:
        raw_value = _u16(pdu, 2)
        return {
            "register_type": "coil",
            "register_address": _u16(pdu, 0),
            "register_count": 1,
            "values": [1 if raw_value == 0xFF00 else 0],
        }

    if function_code == 6 and len(pdu) == 4:
        return {
            "register_type": "holding_register",
            "register_address": _u16(pdu, 0),
            "register_count": 1,
            "values": [_u16(pdu, 2)],
        }

    if function_code == 15 and len(pdu) >= 5:
        address = _u16(pdu, 0)
        count = _u16(pdu, 2)
        byte_count = pdu[4]

        if len(pdu) != 5 + byte_count:
            return None

        return {
            "register_type": "coil",
            "register_address": address,
            "register_count": count,
            "values": _decode_coils(pdu[5:], count),
        }

    if function_code == 16 and len(pdu) >= 5:
        address = _u16(pdu, 0)
        count = _u16(pdu, 2)
        byte_count = pdu[4]

        if byte_count != count * 2:
            return None

        if len(pdu) != 5 + byte_count:
            return None

        value_bytes = pdu[5:]
        values = [
            _u16(value_bytes, offset)
            for offset in range(0, len(value_bytes), 2)
        ]

        return {
            "register_type": "holding_register",
            "register_address": address,
            "register_count": count,
            "values": values,
        }

    return None


def _decode_request_fields(function_code: int, pdu: bytes):
    if function_code in READ_REGISTER_TYPES:
        return _decode_read_request(function_code, pdu)

    if function_code in WRITE_REGISTER_TYPES:
        return _decode_write_request(function_code, pdu)

    return None


def _decode_read_response(function_code: int, pdu: bytes):
    if function_code not in READ_REGISTER_TYPES or len(pdu) < 1:
        return None

    byte_count = pdu[0]

    if len(pdu) != 1 + byte_count:
        return None

    value_bytes = pdu[1:]

    if function_code in (1, 2):
        count = byte_count * 8
        return {
            "register_type": READ_REGISTER_TYPES[function_code],
            "register_address": None,
            "register_count": count,
            "values": _decode_coils(value_bytes, count),
        }

    if byte_count % 2 != 0:
        return None

    values = [
        _u16(value_bytes, offset)
        for offset in range(0, len(value_bytes), 2)
    ]

    return {
        "register_type": READ_REGISTER_TYPES[function_code],
        "register_address": None,
        "register_count": len(values),
        "values": values,
    }


def _decode_write_response(function_code: int, pdu: bytes):
    if function_code in (5, 6) and len(pdu) == 4:
        raw_value = _u16(pdu, 2)
        register_type = WRITE_REGISTER_TYPES[function_code]

        if function_code == 5:
            values = [1 if raw_value == 0xFF00 else 0]
        else:
            values = [raw_value]

        return {
            "register_type": register_type,
            "register_address": _u16(pdu, 0),
            "register_count": 1,
            "values": values,
        }

    if function_code in (15, 16) and len(pdu) == 4:
        return {
            "register_type": WRITE_REGISTER_TYPES[function_code],
            "register_address": _u16(pdu, 0),
            "register_count": _u16(pdu, 2),
            "values": None,
        }

    return None


def _decode_response_fields(raw_function_code: int, pdu: bytes):
    if raw_function_code & 0x80:
        return {
            "register_type": None,
            "register_address": None,
            "register_count": None,
            "values": None,
            "is_exception": True,
            "exception_code": pdu[0] if len(pdu) == 1 else None,
        }

    function_code = raw_function_code & 0x7F

    if function_code in READ_REGISTER_TYPES:
        decoded = _decode_read_response(function_code, pdu)
    elif function_code in WRITE_REGISTER_TYPES:
        decoded = _decode_write_response(function_code, pdu)
    else:
        decoded = None

    if decoded is None:
        return None

    decoded["is_exception"] = False
    decoded["exception_code"] = None
    return decoded


def _apply_decoded_fields(data: dict, decoded: dict | None) -> None:
    if decoded is None:
        return

    data["register_type"] = decoded.get("register_type")
    data["register_address"] = decoded.get("register_address")
    data["register_count"] = decoded.get("register_count")
    data["values"] = decoded.get("values")
    data["is_exception"] = decoded.get("is_exception", False)
    data["exception_code"] = decoded.get("exception_code")


def parse_packet(pkt):
    data = _base_observation(pkt)

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

    data["protocol"] = "IP"
    data["src_ip"] = pkt[IP].src
    data["dst_ip"] = pkt[IP].dst

    if not pkt.haslayer(TCP):
        return data

    data["protocol"] = "TCP"
    data["src_port"] = pkt[TCP].sport
    data["dst_port"] = pkt[TCP].dport

    if data["src_port"] != MODBUS_PORT and data["dst_port"] != MODBUS_PORT:
        return data

    payload = bytes(pkt[TCP].payload)
    if not payload:
        return data

    mbap = _parse_mbap(payload)
    if mbap is None:
        return data

    raw_function_code = mbap["function_code"]
    function_code = raw_function_code & 0x7F

    if function_code not in SUPPORTED_FUNCTION_CODES:
        return data

    data["protocol"] = "MODBUS"
    data["is_modbus"] = True
    data["transaction_id"] = mbap["transaction_id"]
    data["unit_id"] = mbap["unit_id"]
    data["function_code"] = function_code

    direction = _infer_direction(
        data["src_port"],
        data["dst_port"],
        raw_function_code,
        mbap["pdu"],
    )

    if direction is None:
        return data

    data["direction"] = direction

    if direction == "request":
        decoded = _decode_request_fields(function_code, mbap["pdu"])
    else:
        decoded = _decode_response_fields(raw_function_code, mbap["pdu"])

    _apply_decoded_fields(data, decoded)

    return data