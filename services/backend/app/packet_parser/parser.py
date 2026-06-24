# parser.py er første sted en sniffet packet bliver lavet om til data, resten af programmet kan bruge.
# pkt er én packet fra Scapy. Scapy deler pakken op i lag, f.eks. Ether -> IP -> TCP -> payload eller Ether -> ARP.
# Denne fil gemmer ikke noget i databasen. Den parser kun pakken og returnerer data videre til capture.py -> state-laget.

# Ethernet/IP/TCP/Modbus ligger som lag inde i hinanden.
# parser.py læser lagene i samme rækkefølge som pakken er bygget op.
# MAC-adresser læses fra Ethernet-laget, IP-adresser fra IP/ARP-laget, TCP-porte fra TCP-laget,
# og Modbus-data læses først inde i TCP payloaden, hvis porten er 502.

# Ethernet frame ved Modbus TCP
# ┌──────────────┬──────────────┬────────────┬───────────────┬───────────────┬──────────────────────────────────────────┐
# │ dst MAC      │ src MAC      │ EtherType  │ IP header     │ TCP header    │ TCP payload                              │
# └──────────────┴──────────────┴────────────┴───────────────┴───────────────┴──────────────────────────────────────────┘
#        │              │              │              │              │
#        │              │              │              │              └─ bytes(pkt[TCP].payload) -> parse_mbap(payload)
#        │              │              │              └─ pkt[TCP].sport / pkt[TCP].dport
#        │              │              └─ pkt[IP].src / pkt[IP].dst hvis pakken har IP-lag
#        │              └─ pkt[Ether].src
#        └─ pkt[Ether].dst
#                                                                                          │
#                                                                                          ▼
#             TCP payload ved Modbus TCP
#             ┌──────────────────────────── MBAP header ────────────────────────────┬────────────── Modbus PDU ──────────────┐
#             │ Transaction ID │ Protocol ID │ Length │ Unit ID │ Function Code     │ Data                                   │
#             │ 2 bytes        │ 2 bytes     │ 2 bytes│ 1 byte  │ 1 byte            │ Det som denne fil kalder pdu           │
#             └────────────────┴─────────────┴────────┴─────────┴───────────────────┴────────────────────────────────────────┘


# ARP-pakker stopper før IP/TCP/Modbus.
# ARP ligger direkte efter Ethernet-laget, så ARP-IP'er læses fra pkt[ARP].psrc og pkt[ARP].pdst.
# Derfor returnerer parseren med det samme efter ARP, fordi ARP ikke indeholder TCP payload eller Modbus.

# Scapy-udtryk i denne fil:
# pkt.haslayer(IP) betyder: har pakken et IP-lag?
# pkt[IP].src betyder: gå ind i IP-laget og hent source IP-adressen.
# pkt[Ether].src/dst bruges til MAC-adresser.
# pkt[TCP].sport/dport bruges til TCP-porte.

from scapy.layers.inet import IP, TCP
from scapy.layers.l2 import ARP, Ether

from packet_parser.constants import MODBUS_PORT, SUPPORTED_FUNCTION_CODES
from packet_parser.direction import infer_direction
from packet_parser.mbap import parse_mbap
from packet_parser.observation import apply_decoded_fields, base_observation
from packet_parser.request import decode_request_fields
from packet_parser.response import decode_response_fields


# parse_packet() læser pakken lag for lag og bygger et data-dictionary.
# 1. base_observation(pkt) opretter standardfelter med None/False.
# 2. Ether-laget læses først, fordi MAC-adresser ligger yderst i Ethernet-framen.
# 3. Hvis pakken er ARP, læses ARP-IP'er og funktionen returnerer med det samme.
# 4. Hvis pakken har IP-lag, læses src_ip og dst_ip.
# 5. Hvis pakken har TCP-lag, læses source/destination port.
# 6. Kun TCP-trafik på Modbus port 502 sendes videre til parse_mbap().
# 7. Hvis MBAP-headeren er gyldig, sættes Modbus-felter som transaction_id, unit_id og function_code.
# 8. infer_direction() afgør request/response, og request.py eller response.py dekoder resten.
# Hvis pakken ikke er Modbus, returneres de felter der allerede er fundet, så state-laget stadig kan bruge IP/MAC-data.
def parse_packet(pkt):
    # Starter med et standard data-dict fra observation.py.
    # Alle felter findes fra starten, men de fleste er None/False indtil parseren finder dem i pakken.
    data = base_observation(pkt)

    # Ethernet-laget ligger yderst i pakken.
    # Her hentes MAC-adresser, hvis pakken har et Ethernet-lag.
    if pkt.haslayer(Ether):
        data["src_mac"] = pkt[Ether].src
        data["dst_mac"] = pkt[Ether].dst

    # ARP håndteres tidligt, fordi ARP ikke indeholder IPHEADER/TCP/Modbus på samme måde som TCP-trafik.
    # ARP-IP'er læses fra pkt[ARP].psrc og pkt[ARP].pdst.
    if pkt.haslayer(ARP):
        data["protocol"] = "ARP"
        data["src_ip"] = pkt[ARP].psrc
        data["dst_ip"] = pkt[ARP].pdst
        data["arp_op"] = pkt[ARP].op
        return data

    # Hvis pakken hverken var ARP eller har IP-lag, kan parseren ikke bruge den videre.
    if not pkt.haslayer(IP):
        return None

    # IP-laget giver src_ip og dst_ip.
    # Disse IP'er bruges senere i state/manager.py til devices, connections og events.
    data["protocol"] = "IP"
    data["src_ip"] = pkt[IP].src
    data["dst_ip"] = pkt[IP].dst

    # Ikke al IP-trafik er TCP.
    # Hvis der ikke er TCP-lag, returneres IP/MAC-data stadig, men der parses ikke Modbus.
    if not pkt.haslayer(TCP):
        return data

    # TCP-laget giver source og destination port.
    # Portene bruges til at afgøre om pakken er Modbus TCP og senere om den er request eller response.
    data["protocol"] = "TCP"
    data["src_port"] = pkt[TCP].sport
    data["dst_port"] = pkt[TCP].dport

    # Modbus TCP bruger port 502.
    # Hvis hverken src_port eller dst_port er 502, stopper Modbus-parsingen her.
    if data["src_port"] != MODBUS_PORT and data["dst_port"] != MODBUS_PORT:
        return data

    # TCP payloaden er applikationsdataen inde i TCP-pakken.
    # Ved Modbus TCP starter payloaden med MBAP-headeren.
    payload = bytes(pkt[TCP].payload)
    # Hvis TCP-pakken ikke har payload, er der ingen Modbus-data at parse.
    if not payload:
        return data

    # parse_mbap() validerer MBAP-headeren og returnerer transaction_id, unit_id, function_code og pdu.
    mbap = parse_mbap(payload)
    # Hvis MBAP-headeren er ugyldig, beholder vi TCP/IP-data men stopper Modbus-dekodningen.
    if mbap is None:
        return data

    # raw_function_code er den function code der står i pakken.
    # Ved exception responses kan 0x80-bitten være sat oven i den normale function code.
    raw_function_code = mbap["function_code"]
    # 0x7F fjerner en eventuel exception-bit, så function_code kan sammenlignes med de understøttede normale codes.
    function_code = raw_function_code & 0x7F

    # Hvis function code ikke er en af dem projektet parser, returneres pakken uden register-dekodning.
    if function_code not in SUPPORTED_FUNCTION_CODES:
        return data

    # Her er pakken bekræftet som Modbus TCP, og fælles Modbus-felter lægges ind i data-dictet.
    data["protocol"] = "MODBUS"
    data["is_modbus"] = True
    data["transaction_id"] = mbap["transaction_id"]
    data["unit_id"] = mbap["unit_id"]
    data["function_code"] = function_code

    # direction.py afgør om pakken er en request eller response.
    # Det er nødvendigt, fordi request.py og response.py dekoder PDU-data forskelligt.
    direction = infer_direction(
        data["src_port"],
        data["dst_port"],
        raw_function_code,
        mbap["pdu"],
    )

    # Hvis retningen ikke kan afgøres sikkert, stoppes dybere dekodning.
    # De Modbus-felter der allerede er fundet bliver stadig returneret.
    if direction is None:
        return data

    data["direction"] = direction

    # Request-pakker dekodes i request.py.
    # Response-pakker dekodes i response.py.
    if direction == "request":
        decoded = decode_request_fields(function_code, mbap["pdu"])
    else:
        decoded = decode_response_fields(raw_function_code, mbap["pdu"])

    # decoded indeholder register_type, register_address, register_count, values eller exception-data.
    # apply_decoded_fields() kopierer de felter ind i data-dictet, som sendes videre til state-laget.
    apply_decoded_fields(data, decoded)

    # Returnerer én samlet observation til capture.py, som derefter sender den videre til process_observation(data).
    return data

