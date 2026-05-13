# Afgøre request/response-retning.

from packet_parser.constants import MODBUS_PORT


def infer_direction(src_port: int, dst_port: int, raw_function_code: int, pdu: bytes):
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

    if function_code in (5, 6):
        return None

    return None

