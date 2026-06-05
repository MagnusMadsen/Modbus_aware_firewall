# direction.py afgør om en Modbus TCP-pakke er en request eller en response.
# Parseren skal kende retningen, fordi requests og responses har forskellig PDU-struktur.
# Retningen bruges senere til at afgøre om pakken skal dekodes med request.py eller response.py.
# Hvis retningen ikke kan afgøres sikkert, returneres None, og parseren stopper den dybere Modbus-dekodning.

from packet_parser.constants import MODBUS_PORT


# infer_direction() bruger først TCP-portene til at afgøre retningen.
# Hvis destination port er 502, er pakken normalt en request til Modbus-serveren/slaven.
# Hvis source port er 502, er pakken normalt en response fra Modbus-serveren/slaven.
# Hvis portene ikke afgør det, bruges function code og PDU-længde som fallback.
def infer_direction(src_port: int, dst_port: int, raw_function_code: int, pdu: bytes):
    # Request: klient/master sender til Modbus TCP port 502 på slave/server.
    if dst_port == MODBUS_PORT and src_port != MODBUS_PORT:
        return "request"

    # Response: slave/server svarer fra Modbus TCP port 502 tilbage til klient/master.
    if src_port == MODBUS_PORT and dst_port != MODBUS_PORT:
        return "response"

    # I Modbus betyder bit 0x80 i function code, at pakken er en exception response.
    # Exception responses er altid responses, også hvis PDU-længden ellers ikke matcher normal response-struktur.
    if raw_function_code & 0x80:
        return "response"

    # 0x7F fjerner exception-bitten, så function_code kan sammenlignes med de normale function codes.
    function_code = raw_function_code & 0x7F

    # Read-funktioner: 1, 2, 3 og 4.
    # Request-PDU for disse har 4 bytes: startadresse + antal.
    # Response-PDU starter med byte count, og resten af PDU'en skal passe med den byte count.
    if function_code in (1, 2, 3, 4):
        if len(pdu) >= 1 and len(pdu) == 1 + pdu[0]:
            return "response"
        if len(pdu) == 4:
            return "request"

    # Write multiple: 15 og 16.
    # Response-PDU har 4 bytes: startadresse + antal skrevet.
    # Request-PDU har startadresse, antal, byte count og derefter selve værdierne.
    if function_code in (15, 16):
        if len(pdu) == 4:
            return "response"
        if len(pdu) >= 5 and len(pdu) == 5 + pdu[4]:
            return "request"

    # Write single: 5 og 6.
    # Request og response har samme længde og næsten samme struktur, så retningen kan ikke afgøres sikkert ud fra PDU'en alene.
    if function_code in (5, 6):
        return None

    # Ukendt eller ikke-understøttet struktur. Parseren skal ikke gætte på retningen.
    return None
