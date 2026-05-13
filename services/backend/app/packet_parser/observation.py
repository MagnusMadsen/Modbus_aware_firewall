# Standard output-formatet fra parseren 

from datetime import datetime


def base_observation(pkt):
    return {
        "ts": datetime.fromtimestamp(float(pkt.time)).isoformat(),
        "src_mac": None,
        "dst_mac": None,
        "src_ip": None,
        "dst_ip": None,
        "protocol": None,
        "src_port": None,
        "dst_port": None,
        "length": len(pkt),
        "is_modbus": False,
        "direction": None,
        "transaction_id": None,
        "unit_id": None,
        "function_code": None,
        "register_type": None,
        "register_address": None,
        "register_count": None,
        "values": None,
        "is_exception": False,
        "exception_code": None,
        "arp_op": None,
    }


def apply_decoded_fields(data: dict, decoded: dict | None) -> None:
    if decoded is None:
        return

    data["register_type"] = decoded.get("register_type")
    data["register_address"] = decoded.get("register_address")
    data["register_count"] = decoded.get("register_count")
    data["values"] = decoded.get("values")
    data["is_exception"] = decoded.get("is_exception", False)
    data["exception_code"] = decoded.get("exception_code")