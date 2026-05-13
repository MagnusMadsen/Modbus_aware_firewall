# Modbus/TCP MBAP-header parsing. 

def u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 2], byteorder="big")


def parse_mbap(payload: bytes):
    if len(payload) < 8:
        return None

    transaction_id = u16(payload, 0)
    protocol_id = u16(payload, 2)
    length_field = u16(payload, 4)

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