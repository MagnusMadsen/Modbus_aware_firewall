# request.py dekoder Modbus requests.
# Filen bruges kun efter parser.py har fundet en Modbus TCP-pakke og direction.py har vurderet, at pakken er en request.
# På dette tidspunkt er Ethernet-, IP-, TCP- og MBAP-lag allerede læst.
# request.py får derfor kun function_code og pdu-data efter function code.
# Filen gemmer ikke noget i databasen. Den gør request-bytes forståelige for state-laget.

# Hele pakken ligger sådan her:
# Ethernet frame
# ┌──────────────┬──────────────┬────────────┬───────────────┬───────────────┬──────────────────────────────────────────┐
# │ dst MAC      │ src MAC      │ EtherType  │ IP header     │ TCP header    │ TCP payload                              │
# └──────────────┴──────────────┴────────────┴───────────────┴───────────────┴──────────────────────────────────────────┘
#                                                                                  │
#                                                                                  ▼
#             TCP payload ved Modbus TCP
#             ┌──────────────────────────── MBAP header ────────────────────────────┬────────────── Modbus PDU ──────────────┐
#             │ Transaction ID │ Protocol ID │ Length │ Unit ID │ Function Code     │ Data                                   │
#             │ 2 bytes        │ 2 bytes     │ 2 bytes│ 1 byte  │ 1 byte            │ Det som denne fil kalder pdu           │
#             └────────────────┴─────────────┴────────┴─────────┴───────────────────┴────────────────────────────────────────┘
#                                                                                            │
#                                                                                            ▼
#                                                                    request.py modtager function_code og data.

# Vigtigt: request.py ser ikke MAC, IP eller TCP-porte direkte.
# De felter blev læst tidligere i parser.py.
# request.py arbejder kun med Modbus request-indholdet inde i TCP payloaden.

# Eksempel ved function code 3: Read Holding Registers request.
# Masteren beder slaven om at returnere registerværdier.
# Requesten indeholder derfor ikke selve registerværdierne endnu.
# Data/PDU efter function_code:
# ┌──────────────────┬────────────────┐
# │ Start address    │ Quantity       │
# │ 2 bytes          │ 2 bytes        │
# └──────────────────┴────────────────┘
# Start address er første registeradresse masteren vil læse fra. 
# Quantity er hvor mange registre masteren vil læse.
# Derfor returnerer decode_read_request() register_address og register_count, men values er None.

# Eksempel ved function code 16: Write Multiple Registers request.
# Masteren skriver konkrete registerværdier til slaven.
# Requesten indeholder derfor både hvor der skal skrives, hvor mange registre der skrives, og hvilke værdier der skrives.
# Data/PDU efter function_code:
# ┌──────────────────┬────────────────┬────────────┬──────────────────────────────┐
# │ Start address    │ Quantity       │ Byte count │ Register values              │
# │ 2 bytes          │ 2 bytes        │ 1 byte     │ 2 bytes pr. register         │
# └──────────────────┴────────────────┴────────────┴──────────────────────────────┘
# Byte count fortæller hvor mange bytes registerværdierne fylder.
# Register values er de værdier masteren forsøger at skrive til slaven.
# Hvert holding register fylder 2 bytes, altså 16 bit.
# Eksempel: byte-parret 00 2A bliver med u16() til decimalværdien 42.
# Derfor returnerer decode_write_request() register_address, register_count og values.

from packet_parser.coils import decode_coils
from packet_parser.constants import READ_REGISTER_TYPES, WRITE_REGISTER_TYPES
from packet_parser.mbap import u16


# decode_read_request() dekoder read requests for function code 1, 2, 3 og 4.
# READ_REGISTER_TYPES oversætter function code til register_type, f.eks. 3 -> holding_register.
# Read requests har altid 4 bytes PDU-data efter function code: 2 bytes startadresse + 2 bytes antal.
# Der findes ingen values i en read request, fordi masteren kun spørger efter værdier.
def decode_read_request(function_code: int, pdu: bytes):
    # Hvis function code ikke er en understøttet read-type, eller PDU-længden ikke er 4 bytes, kan requesten ikke dekodes sikkert.
    if function_code not in READ_REGISTER_TYPES or len(pdu) != 4:
        return None

    # u16(pdu, 0) læser de første 2 bytes som startadresse.
    # u16(pdu, 2) læser de næste 2 bytes som antal coils/registers masteren vil læse.
    return {
        "register_type": READ_REGISTER_TYPES[function_code],
        "register_address": u16(pdu, 0),
        "register_count": u16(pdu, 2),
        "values": None,
    }


# decode_write_request() dekoder write requests for function code 5, 6, 15 og 16.
# Function code 5 skriver én coil.
# Function code 6 skriver ét holding register.
# Function code 15 skriver flere coils.
# Function code 16 skriver flere holding registers.
# Write requests indeholder de værdier masteren forsøger at skrive, derfor returneres values.
def decode_write_request(function_code: int, pdu: bytes):
    # Function code 5: Write Single Coil.
    # PDU-data er startadresse + coil-værdi.
    # Modbus bruger 0xFF00 som ON og 0x0000 som OFF for single coil write.
    if function_code == 5 and len(pdu) == 4:
        raw_value = u16(pdu, 2)
        return {
            "register_type": "coil",
            "register_address": u16(pdu, 0),
            "register_count": 1,
            "values": [1 if raw_value == 0xFF00 else 0],
        }

    # Function code 6: Write Single Register.
    # PDU-data er 2 bytes startadresse + 2 bytes registerværdi.
    # De sidste 2 bytes er selve værdien der skrives til holding registeret.
    if function_code == 6 and len(pdu) == 4:
        return {
            "register_type": "holding_register",
            "register_address": u16(pdu, 0),
            "register_count": 1,
            "values": [u16(pdu, 2)],
        }

    # Function code 15: Write Multiple Coils.
    # PDU-data er startadresse + antal coils + byte_count + coil bytes.
    # Coil-værdierne er pakket som bits, så decode_coils() bruges til at pakke dem ud til 0/1 værdier.
    if function_code == 15 and len(pdu) >= 5:
        address = u16(pdu, 0)
        count = u16(pdu, 2)
        byte_count = pdu[4]

        # PDU-længden skal passe med byte_count. Ellers mangler der data eller pakken er ikke den struktur parseren forventer.
        if len(pdu) != 5 + byte_count:
            return None

        return {
            "register_type": "coil",
            "register_address": address,
            "register_count": count,
            "values": decode_coils(pdu[5:], count),
        }

    # Function code 16: Write Multiple Registers.
    # PDU-data er startadresse + antal registre + byte_count + register bytes.
    # Hvert holding register er 2 bytes, altså 16 bit.
    # Derfor skal byte_count være count * 2.
    if function_code == 16 and len(pdu) >= 5:
        address = u16(pdu, 0)
        count = u16(pdu, 2)
        byte_count = pdu[4]

        # byte_count skal matche antal registre gange 2 bytes pr. register.
        if byte_count != count * 2:
            return None

        # Den samlede PDU-længde skal være 5 faste bytes plus de register bytes byte_count beskriver.
        if len(pdu) != 5 + byte_count:
            return None

        # Registerværdierne starter efter startadresse, count og byte_count.
        value_bytes = pdu[5:]
        # Hver registerværdi læses som 2 bytes med u16().
        # Eksempel: byte-parret 00 2A bliver til decimalværdien 42.
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

    # Hvis function code eller PDU-struktur ikke matcher de understøttede write-formater, returneres None.
    return None


# decode_request_fields() er indgangen fra parser.py.
# Funktionen vælger om requesten skal dekodes som read eller write ud fra function_code.
# READ_REGISTER_TYPES og WRITE_REGISTER_TYPES kommer fra constants.py og fungerer som opslagstabeller.
# Hvis function code ikke understøttes, returneres None.
def decode_request_fields(function_code: int, pdu: bytes):
    if function_code in READ_REGISTER_TYPES:
        return decode_read_request(function_code, pdu)

    if function_code in WRITE_REGISTER_TYPES:
        return decode_write_request(function_code, pdu)

    return None
