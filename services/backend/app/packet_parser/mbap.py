# mbap.py parser Modbus delen i TCP payloaden.
# MBAP står for Modbus Application Protocol header.
# PDU står for Protocol Data Unit. I denne fil betyder PDU: selve Modbus-kommandoens data efter function code.
# Funktionen bruges af packet_parser/parser.py, efter parser.py har fundet en TCP-pakke på Modbus port 502.
# Denne fil gemmer ikke noget i databasen. Den validerer og opdeler kun Modbus TCP payloaden.

# En sniffet Ethernet frame består af flere lag.
# MAC-adresser ligger i Ethernet-headeren.
# IP-adresser ligger i IP-headeren.
# TCP-porte ligger i TCP-headeren.
# MBAP-headeren ligger først inde i TCP payloaden, altså efter Ethernet-, IP- og TCP-headerne.

# Ethernet frame
# ┌──────────────┬──────────────┬────────────┬───────────────┬───────────────┬──────────────────────────────────────────┐
# │ dst MAC      │ src MAC      │ EtherType  │ IP header     │ TCP header    │ TCP payload                              │
# └──────────────┴──────────────┴────────────┴───────────────┴───────────────┴──────────────────────────────────────────┘
#                                                                                  │
#                                                                                  ▼
#             TCP payload ved Modbus TCP
#             ┌──────────────────────────── MBAP header ────────────────────────────┬────────────── Modbus PDU ──────────────┐
#             │ Transaction ID │ Protocol ID │ Length │ Unit ID │ Function Code     │ Data                                   │
#             │ 2 bytes        │ 2 bytes     │ 2 bytes│ 1 byte  │ 1 byte            │ Varierer efter function code           │
#             └────────────────┴─────────────┴────────┴─────────┴───────────────────┴────────────────────────────────────────┘

# parse_mbap(payload) får bytes(pkt[TCP].payload) fra parser.py.
# Først læses MBAP-headeren: transaction_id, protocol_id, length og unit_id.
# transaction_id bruges senere til at matche request og response.
# protocol_id skal være 0 for Modbus TCP.
# length fortæller hvor lang Modbus TCP-framen er efter de første 6 bytes.
# unit_id fortæller hvilken Modbus unit/slave pakken er rettet mod.
# function_code fortæller hvilken Modbus-operation det er, f.eks. read holding registers eller write single coil.
# Hvis MBAP-headeren er ugyldig, returnerer parse_mbap() None, så parser.py stopper den dybere Modbus-dekodning.

# u16() læser 2 bytes fra data og laver dem om til et heltal.
# Modbus TCP bruger big-endian byteorden, derfor bruges byteorder="big".
# offset fortæller hvor i byte-arrayet de 2 bytes starter.
def u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 2], byteorder="big")


# parse_mbap() læser MBAP-headeren fra TCP payloaden.
# payload er bytes fra pkt[TCP].payload i parser.py.
# Hvis payloaden er for kort, har forkert protocol_id eller mangler data ifølge length-feltet, returneres None.
# Hvis headeren er gyldig, returneres transaction_id, unit_id, function_code og pdu.
def parse_mbap(payload: bytes):
    # Minimum er 8 bytes: 7 bytes MBAP-header + 1 byte function_code.
    if len(payload) < 8:
        return None

    # MBAP-headerens faste felter læses fra deres faste offsets.
    # transaction_id bruges til at matche Modbus request og response.
    transaction_id = u16(payload, 0)
    protocol_id = u16(payload, 2)
    length_field = u16(payload, 4)

    # protocol_id skal være 0 for Modbus TCP.
    # Hvis den ikke er 0, behandler parseren ikke payloaden som Modbus TCP.
    if protocol_id != 0:
        return None

    # length_field tæller bytes efter de første 6 MBAP-bytes.
    # Derfor er den forventede totale Modbus TCP frame-længde 6 + length_field.
    expected_total_length = 6 + length_field
    # En gyldig frame skal stadig mindst kunne indeholde unit_id og function_code.
    if expected_total_length < 8:
        return None

    # Hvis TCP payloaden er kortere end length-feltet siger, mangler frame-data.
    if len(payload) < expected_total_length:
        return None

    # frame afgrænses til den længde MBAP-headeren siger tilhører denne Modbus TCP frame.
    frame = payload[:expected_total_length]

    # unit_id ligger på byte 6, function_code på byte 7, og PDU-data starter på byte 8.
    return {
        "transaction_id": transaction_id,
        "unit_id": frame[6],
        "function_code": frame[7],
        "pdu": frame[8:],
    }