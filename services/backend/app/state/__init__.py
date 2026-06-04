# state/__init__.py er adgangslaget foran ModbusStateManager.
# capture.py kalder process_observation(data) her i stedet for selv at oprette en manager.
# Det gør capture.py simpelt: den sender kun parsede observationer videre.
# Denne fil opretter, starter og genbruger én fælles ModbusStateManager.
# Det forhindrer flere managers, flere maintenance-tråde og flere lokale caches i samme backend-proces.
# Selve analysen af devices, connections, registers, requests og metrics sker bagefter i state/manager.py.

import threading

from state.manager import ModbusStateManager

# _manager holder den ene fælles ModbusStateManager-instans.
# Den starter som None, fordi manageren først oprettes når første observation skal behandles.
# Når den først er oprettet, genbruges den for alle nye observationer.
_manager: ModbusStateManager | None = None

# Locken sikrer, at to threads ikke opretter hver sin manager samtidig.
# Det kan ske fordi capture kører i baggrunden, mens Flask/API også kan køre i samme backend-proces.
# Uden lock kunne to samtidige kald nå at se _manager som None og oprette to managers.
_manager_lock = threading.Lock()

# init_state_manager() returnerer den fælles ModbusStateManager.
# Hvis manageren allerede findes, returneres den med det samme.
# Hvis den ikke findes, oprettes den én gang, startes med manager.start(), og gemmes i _manager.
# Det er her designet sikrer én manager og én maintenance-thread i backend-processen.
def init_state_manager() -> ModbusStateManager:
    global _manager

    if _manager is not None:
        return _manager

    with _manager_lock:
        if _manager is None:
            _manager = ModbusStateManager()
            _manager.start()

    return _manager

# process_observation() er den funktion capture.py kalder efter parse_packet().
# data er dictionary'en fra packet_parser/parser.py, f.eks. med src_ip, dst_ip, protocol, function_code og direction.
# Funktionen henter først den fælles manager med init_state_manager().
# Derefter sendes observationen videre til manager.process(data), hvor den egentlige state-opdatering sker.
def process_observation(data: dict) -> None:
    manager = init_state_manager()
    manager.process(data)