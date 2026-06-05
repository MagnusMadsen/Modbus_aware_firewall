# coils.py dekoder Modbus coil/discrete-input værdier fra bytes til enkelte bit-værdier.
# Coils og discrete inputs er 1-bit værdier, altså 0/1 eller OFF/ON.
# Modbus sender flere coil-værdier pakket sammen i bytes, hvor hver bit repræsenterer én coil.
# decode_coils() pakker derfor byte_data ud til en liste med 0 og 1, som resten af parseren kan bruge.


# decode_coils() læser count antal coil/discrete-input værdier ud af byte_data.
# byte_index finder hvilken byte den aktuelle coil ligger i.
# bit_index finder hvilken bit inde i den byte der skal læses.
# Hvis byte_data er kortere end forventet, stoppes loopet for ikke at læse uden for dataen.
def decode_coils(byte_data: bytes, count: int) -> list[int]:
    values = []

    for i in range(count):
        # Der er 8 bits i én byte, så i // 8 finder hvilken byte der indeholder coil nummer i.
        byte_index = i // 8
        # i % 8 finder placeringen inde i den byte, fra bit 0 til bit 7.
        bit_index = i % 8
        # Hvis pakken ikke indeholder flere bytes, stopper vi i stedet for at give en index-fejl.
        if byte_index >= len(byte_data):
            break
        # Byte-værdien rykkes bit_index pladser mod højre, så den ønskede bit ender sidst.
        # & 0x01 isolerer den sidste bit. Resultatet gemmes som 1 hvis bit er sat, ellers 0.
        values.append(1 if (byte_data[byte_index] >> bit_index) & 0x01 else 0)

    return values

