# response.py dekoder Modbus responses.
# Filen bruges kun efter parser.py har fundet en Modbus TCP-pakke og direction.py har vurderet, at pakken er en response.
# På dette tidspunkt er Ethernet-, IP-, TCP- og MBAP-lag allerede læst.
# response.py får derfor kun raw_function_code og pdu-data efter function code.
# Filen gemmer ikke noget i databasen. Den gør response-bytes forståelige for state-laget.

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
#                                                                    response.py modtager raw_function_code og data.

# Vigtigt: response.py ser ikke MAC, IP eller TCP-porte direkte.
# De felter blev læst tidligere i parser.py.
# response.py arbejder kun med Modbus response-indholdet inde i TCP payloaden.

# Eksempel ved function code 3: Read Holding Registers response.
# Masteren har først sendt en read request.
# Slaven svarer her med de registerværdier, der blev efterspurgt.
# Data/PDU efter function_code:
# ┌────────────┬──────────────────────────────┐
# │ Byte count │ Register values              │
# │ 1 byte     │ 2 bytes pr. register         │
# └────────────┴──────────────────────────────┘
# Byte count fortæller hvor mange bytes værdierne fylder.
# Register values er selve registerværdierne fra slaven.
# Hvert holding/input register fylder 2 bytes, altså 16 bit.
# Eksempel: byte-parret 00 2A bliver med u16() til decimalværdien 42.

# Eksempel ved function code 16: Write Multiple Registers response.
# Masteren har sendt registerværdierne i requesten.
# Slaven sender ikke værdierne tilbage i responsen.
# Slaven bekræfter kun startadresse og antal registre, der blev skrevet.
# Data/PDU efter function_code:
# ┌──────────────────┬────────────────┐
# │ Start address    │ Quantity       │
# │ 2 bytes          │ 2 bytes        │
# └──────────────────┴────────────────┘
# Derfor returnerer decode_write_response() register_address og register_count, men values er None for multiple-write response.

# Eksempel ved exception response.
# Hvis raw_function_code har 0x80-bitten sat, er responsen en Modbus exception.
# Så indeholder pdu normalt kun exception_code, og funktionen markerer is_exception=True.

from packet_parser.coils import decode_coils
from packet_parser.constants import READ_REGISTER_TYPES, WRITE_REGISTER_TYPES
from packet_parser.mbap import u16


# decode_read_response() dekoder read responses for function code 1, 2, 3 og 4.
# READ_REGISTER_TYPES oversætter function code til register_type, f.eks. 3 -> holding_register.
# Read responses starter med byte_count, som fortæller hvor mange bytes værdierne fylder.
# Function code 1 og 2 returnerer coil/discrete-input bits.
# Function code 3 og 4 returnerer registerværdier, hvor hver værdi fylder 2 bytes.
def decode_read_response(function_code: int, pdu: bytes):
    # Hvis function code ikke er en understøttet read-type, eller PDU'en ikke engang har byte_count, kan responsen ikke dekodes sikkert.
    if function_code not in READ_REGISTER_TYPES or len(pdu) < 1:
        return None

    # Første byte i en read response er byte_count.
    # Den fortæller hvor mange bytes der følger efter med værdier.
    byte_count = pdu[0]

    # PDU-længden skal være 1 byte_count-byte plus det antal value-bytes byte_count beskriver.
    if len(pdu) != 1 + byte_count:
        return None

    # Selve værdierne starter efter byte_count.
    value_bytes = pdu[1:]

    # Function code 1 og 2 returnerer bits for coils/discrete inputs.
    # byte_count * 8 er det maksimale antal bitværdier der kan ligge i value_bytes.
    if function_code in (1, 2):
        count = byte_count * 8
        return {
            "register_type": READ_REGISTER_TYPES[function_code],
            "register_address": None,
            "register_count": count,
            "values": decode_coils(value_bytes, count),
        }

    # Registerværdier skal komme i par af 2 bytes.
    # Hvis byte_count er ulige, kan det ikke være komplette 16-bit registre.
    if byte_count % 2 != 0:
        return None

    # Hver registerværdi læses som 2 bytes med u16().
    # Eksempel: byte-parret 00 2A bliver til decimalværdien 42.
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


# decode_write_response() dekoder write responses for function code 5, 6, 15 og 16.
# Function code 5 og 6 echoer adresse og værdi tilbage for single write.
# Function code 15 og 16 bekræfter startadresse og antal skrevne coils/registers.
# Multiple-write responses indeholder ikke selve værdierne, fordi de allerede blev sendt i requesten.
def decode_write_response(function_code: int, pdu: bytes):
    # Function code 5 og 6: single write response.
    # PDU-data er 2 bytes startadresse + 2 bytes skrevet værdi.
    if function_code in (5, 6) and len(pdu) == 4:
        raw_value = u16(pdu, 2)
        register_type = WRITE_REGISTER_TYPES[function_code]

        # Function code 5 er Write Single Coil.
        # Modbus bruger 0xFF00 som ON og 0x0000 som OFF.
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

    # Function code 15 og 16: multiple write response.
    # PDU-data er 2 bytes startadresse + 2 bytes antal skrevne coils/registers.
    # Responsen bekræfter kun hvad der blev skrevet, men sender ikke værdierne tilbage.
    if function_code in (15, 16) and len(pdu) == 4:
        return {
            "register_type": WRITE_REGISTER_TYPES[function_code],
            "register_address": u16(pdu, 0),
            "register_count": u16(pdu, 2),
            "values": None,
        }

    # Hvis function code eller PDU-struktur ikke matcher de understøttede write responses, returneres None.
    return None


# decode_response_fields() er indgangen fra parser.py.
# raw_function_code bruges her, fordi Modbus exception responses sætter 0x80-bitten oven i den normale function code.
# Først tjekkes om responsen er en exception response.
# Hvis ikke, fjernes exception-bitten med 0x7F, og responsen dekodes som read eller write.
def decode_response_fields(raw_function_code: int, pdu: bytes):
    # Hvis 0x80-bitten er sat, er det en Modbus exception response.
    # I så fald indeholder pdu normalt kun én byte: exception_code.
    if raw_function_code & 0x80:
        return {
            "register_type": None,
            "register_address": None,
            "register_count": None,
            "values": None,
            "is_exception": True,
            "exception_code": pdu[0] if len(pdu) == 1 else None,
        }

    # 0x7F fjerner exception-bitten, så function_code matcher de normale function codes i constants.py.
    function_code = raw_function_code & 0x7F

    if function_code in READ_REGISTER_TYPES:
        decoded = decode_read_response(function_code, pdu)
    elif function_code in WRITE_REGISTER_TYPES:
        decoded = decode_write_response(function_code, pdu)
    else:
        decoded = None

    # Hvis read/write-dekodningen ikke kunne forstå responsen, sendes None tilbage til parser.py.
    if decoded is None:
        return None

    # Almindelige responses markeres eksplicit som ikke-exception.
    decoded["is_exception"] = False
    decoded["exception_code"] = None
    return decoded
