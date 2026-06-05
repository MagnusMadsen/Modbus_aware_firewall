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


# parse_packet() læser pakken lag for lag og bygger en data-dictionary.
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
    data = base_observation(pkt)

    if pkt.haslayer(Ether):
        data["src_mac"] = pkt[Ether].src
        data["dst_mac"] = pkt[Ether].dst

    if pkt.haslayer(ARP):
        data["protocol"] = "ARP"
        data["src_ip"] = pkt[ARP].psrc
        data["dst_ip"] = pkt[ARP].pdst
        data["arp_op"] = pkt[ARP].op
        return data

    if not pkt.haslayer(IP):
        return None

    data["protocol"] = "IP"
    data["src_ip"] = pkt[IP].src
    data["dst_ip"] = pkt[IP].dst

    if not pkt.haslayer(TCP):
        return data

    data["protocol"] = "TCP"
    data["src_port"] = pkt[TCP].sport
    data["dst_port"] = pkt[TCP].dport

    if data["src_port"] != MODBUS_PORT and data["dst_port"] != MODBUS_PORT:
        return data

    payload = bytes(pkt[TCP].payload)
    if not payload:
        return data

    mbap = parse_mbap(payload)
    if mbap is None:
        return data

    raw_function_code = mbap["function_code"]
    function_code = raw_function_code & 0x7F

    if function_code not in SUPPORTED_FUNCTION_CODES:
        return data

    data["protocol"] = "MODBUS"
    data["is_modbus"] = True
    data["transaction_id"] = mbap["transaction_id"]
    data["unit_id"] = mbap["unit_id"]
    data["function_code"] = function_code

    direction = infer_direction(
        data["src_port"],
        data["dst_port"],
        raw_function_code,
        mbap["pdu"],
    )

    if direction is None:
        return data

    data["direction"] = direction

    if direction == "request":
        decoded = decode_request_fields(function_code, mbap["pdu"])
    else:
        decoded = decode_response_fields(raw_function_code, mbap["pdu"])

    apply_decoded_fields(data, decoded)

    return data
