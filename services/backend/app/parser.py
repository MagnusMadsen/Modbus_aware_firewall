from scapy.layers.l2 import Ether, ARP
from scapy.layers.inet import IP, TCP

def parse_packet(pkt):
    data = {
        "src_mac": None,
        "dst_mac": None,
        "src_ip": None,
        "dst_ip": None,
        "protocol": None,
        "src_port": None,
        "dst_port": None,
        "length": len(pkt),
    }

    if pkt.haslayer(Ether):
        data["src_mac"] = pkt[Ether].src
        data["dst_mac"] = pkt[Ether].dst

    if pkt.haslayer(ARP):
        data["protocol"] = "ARP"
        data["src_ip"] = pkt[ARP].psrc
        data["dst_ip"] = pkt[ARP].pdst
        return data

    if pkt.haslayer(IP):
        data["src_ip"] = pkt[IP].src
        data["dst_ip"] = pkt[IP].dst
        data["protocol"] = "IP"

    if pkt.haslayer(TCP):
        data["protocol"] = "TCP"
        data["src_port"] = pkt[TCP].sport
        data["dst_port"] = pkt[TCP].dport

    return data