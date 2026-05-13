# Dekode Modbus requests.

from packet_parser.coils import decode_coils
from packet_parser.constants import READ_REGISTER_TYPES, WRITE_REGISTER_TYPES
from packet_parser.mbap import u16


def decode_read_request(function_code: int, pdu: bytes):
    if function_code not in READ_REGISTER_TYPES or len(pdu) != 4:
        return None

    return {
        "register_type": READ_REGISTER_TYPES[function_code],
        "register_address": u16(pdu, 0),
        "register_count": u16(pdu, 2),
        "values": None,
    }


def decode_write_request(function_code: int, pdu: bytes):
    if function_code == 5 and len(pdu) == 4:
        raw_value = u16(pdu, 2)
        return {
            "register_type": "coil",
            "register_address": u16(pdu, 0),
            "register_count": 1,
            "values": [1 if raw_value == 0xFF00 else 0],
        }

    if function_code == 6 and len(pdu) == 4:
        return {
            "register_type": "holding_register",
            "register_address": u16(pdu, 0),
            "register_count": 1,
            "values": [u16(pdu, 2)],
        }

    if function_code == 15 and len(pdu) >= 5:
        address = u16(pdu, 0)
        count = u16(pdu, 2)
        byte_count = pdu[4]

        if len(pdu) != 5 + byte_count:
            return None

        return {
            "register_type": "coil",
            "register_address": address,
            "register_count": count,
            "values": decode_coils(pdu[5:], count),
        }

    if function_code == 16 and len(pdu) >= 5:
        address = u16(pdu, 0)
        count = u16(pdu, 2)
        byte_count = pdu[4]

        if byte_count != count * 2:
            return None

        if len(pdu) != 5 + byte_count:
            return None

        value_bytes = pdu[5:]
        values = [
            u16(value_bytes, offset)
            for offset in range(0, len(value_bytes), 2)
        ]

        return {
            "register_type": "holding_register",
            "register_address": address,
            "register_count": count,
            "values": values,
        }

    return None


def decode_request_fields(function_code: int, pdu: bytes):
    if function_code in READ_REGISTER_TYPES:
        return decode_read_request(function_code, pdu)

    if function_code in WRITE_REGISTER_TYPES:
        return decode_write_request(function_code, pdu)

    return None
