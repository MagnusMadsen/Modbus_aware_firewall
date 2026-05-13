# Dekode coil/discrete-input bitfelter.

def decode_coils(byte_data: bytes, count: int) -> list[int]:
    values = []

    for i in range(count):
        byte_index = i // 8
        bit_index = i % 8

        if byte_index >= len(byte_data):
            break

        values.append(1 if (byte_data[byte_index] >> bit_index) & 0x01 else 0)

    return values

