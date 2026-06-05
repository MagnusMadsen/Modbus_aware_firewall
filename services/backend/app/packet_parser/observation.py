# observation.py definerer det fælles output-format fra packet_parser.
# parser.py starter med base_observation(pkt), så alle observationer har de samme nøgler fra starten.
# Derefter udfylder parser.py felterne lag for lag: MAC, IP, TCP og Modbus.
# apply_decoded_fields() bruges til sidst til at lægge de dekodede Modbus-felter fra request.py eller response.py ind i samme data-dict.
# Filen gemmer ikke noget i databasen. Den standardiserer kun den dictionary, som sendes videre til state/manager.py.

from datetime import datetime


# base_observation() opretter standardformen for én observation.
# pkt er den rå Scapy-packet fra capture.py.
# ts kommer fra pkt.time, som er tidspunktet Scapy fangede pakken.
# Felter starter som None eller False, fordi parser.py først udfylder dem, hvis pakken faktisk indeholder det lag eller den Modbus-data.
# length er den samlede pakkelængde, som Scapy rapporterer med len(pkt).
def base_observation(pkt):
    return {
        # Tidspunktet for den fangede packet, konverteret til ISO-format så det er let at sende videre som JSON.
        "ts": datetime.fromtimestamp(float(pkt.time)).isoformat(),
        # Ethernet-felter. Udfyldes i parser.py hvis pakken har Ether-lag.
        "src_mac": None,
        "dst_mac": None,
        # IP-felter. Udfyldes fra ARP eller IP-laget, afhængigt af pakketypen.
        "src_ip": None,
        "dst_ip": None,
        # protocol fortæller hvilket niveau parseren nåede: ARP, IP, TCP eller MODBUS.
        "protocol": None,
        # TCP-porte. Udfyldes kun hvis pakken har TCP-lag.
        "src_port": None,
        "dst_port": None,
        # Samlet længde på den sniffede packet.
        "length": len(pkt),
        # Modbus-felter. De bliver kun udfyldt hvis pakken er TCP-trafik på Modbus port 502 og MBAP-headeren kan parses.
        "is_modbus": False,
        "direction": None,
        "transaction_id": None,
        "unit_id": None,
        "function_code": None,
        # Registerfelter. Udfyldes af request.py eller response.py, hvis function code indeholder registeradresse/værdier.
        "register_type": None,
        "register_address": None,
        "register_count": None,
        "values": None,
        # Exception-felter. Bruges hvis en Modbus response er en exception response.
        "is_exception": False,
        "exception_code": None,
        # ARP operation. Udfyldes kun for ARP-pakker.
        "arp_op": None,
    }


# apply_decoded_fields() kopierer dekodede Modbus-felter ind i den fælles observation.
# decoded kommer fra decode_request_fields() eller decode_response_fields().
# Hvis decoded er None, betyder det at request.py/response.py ikke kunne eller skulle dekode flere felter.
# Funktionen ændrer data-dictet direkte og returnerer ikke noget.
def apply_decoded_fields(data: dict, decoded: dict | None) -> None:
    # Ingen dekodede felter at tilføje.
    if decoded is None:
        return

    # Disse felter bruges senere af state/registers.py og events-tabellen til at forstå registerændringer.
    data["register_type"] = decoded.get("register_type")
    data["register_address"] = decoded.get("register_address")
    data["register_count"] = decoded.get("register_count")
    data["values"] = decoded.get("values")
    data["is_exception"] = decoded.get("is_exception", False)
    data["exception_code"] = decoded.get("exception_code")