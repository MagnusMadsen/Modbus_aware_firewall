# Dekode Modbus responses.

from packet_parser.coils import decode_coils
from packet_parser.constants import READ_REGISTER_TYPES, WRITE_REGISTER_TYPES
from packet_parser.mbap import u16


def decode_read_response(function_code: int, pdu: bytes):
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
            "values": decode_coils(value_bytes, count),
        }

    if byte_count % 2 != 0:
        return None

    values = [
        u16(value_bytes, offset)
        for offset in range(0, len(value_bytes), 2)
    ]

    return {
        "register_type": READ_REGISTER_TYPES[function_code],
        "register_address": None,
        "register_count": len(values),
        "values": values,
    }


def decode_write_response(function_code: int, pdu: bytes):
    if function_code in (5, 6) and len(pdu) == 4:
        raw_value = u16(pdu, 2)
        register_type = WRITE_REGISTER_TYPES[function_code]

        if function_code == 5:
            values = [1 if raw_value == 0xFF00 else 0]
        else:
            values = [raw_value]

        return {
            "register_type": register_type,
            "register_address": u16(pdu, 0),
            "register_count": 1,
            "values": values,
        }

    if function_code in (15, 16) and len(pdu) == 4:
        return {
            "register_type": WRITE_REGISTER_TYPES[function_code],
            "register_address": u16(pdu, 0),
            "register_count": u16(pdu, 2),
            "values": None,
        }

    return None


def decode_response_fields(raw_function_code: int, pdu: bytes):
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
        decoded = decode_read_response(function_code, pdu)
    elif function_code in WRITE_REGISTER_TYPES:
        decoded = decode_write_response(function_code, pdu)
    else:
        decoded = None

    if decoded is None:
        return None

    decoded["is_exception"] = False
    decoded["exception_code"] = None
    return decoded

