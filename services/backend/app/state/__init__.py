# Jeg har brugt classes i state-laget, fordi de dele af programmet skal huske data mellem pakker.
# Packet_parser er stateless. Den læser én packet, laver den om til et data-dict og returnerer resultatet. Den behøver ikke huske tidligere pakker.
# State-laget er anderledes. Her skal programmet kunne sammenligne den aktuelle observation med tidligere observationer. Derfor har tracker-klasserne interne variabler på self.
# For eksempel bruger RegisterTracker self.register_state til at huske tidligere registerværdier. 
# Hvis register 2 først var 42 og senere bliver 43, kan programmet kun opdage ændringen, fordi den gamle værdi blev gemt i objektet.
# Det samme gælder DeviceTracker, som husker kendte IP/MAC-adresser, ConnectionTracker, som husker master/slave-relationer, RequestTracker, som husker requests der venter på responses, og MetricsTracker, som holder tællere i det aktuelle metrics bucket.
# 
# Så kort sagt: Jeg bruger funktioner i parseren, fordi parsing ikke kræver hukommelse mellem pakker, 
# Jeg bruger classes i state-laget, fordi systemet skal holde runtime-state og kunne sammenligne nye observationer med tidligere observationer. 
# 
# Inde i ModbusStateManager findes tracker-objekterne, f.eks: 
#   self.devices = DeviceTracker(...)
#   self.connections = ConnectionTracker(...)
#   self.registers = RegisterTracker(...)
#   self.requests = RequestTracker(...)
#   self.metrics = MetricsTracker(...)


# state/__init__.py er adgangslaget ind til ModbusStateManager.
# capture.py sender parsede pakker hertil med process_observation(data).
# capture.py opretter ikke selv ModbusStateManager, fordi manageren skal være fælles for hele backend-processen.
# Denne fil opretter derfor manageren første gang den skal bruges, starter dens maintenance-thread og genbruger den bagefter.
# Det er vigtigt, fordi ModbusStateManager holder lokal runtime-state: kendte devices, connections, function codes, pending requests og metrics-buffer.
# Hvis der blev oprettet en ny manager for hver packet, ville systemet miste historik og kunne starte flere maintenance-tråde.

# Flowet ser sådan her ud:
#
# capture.py
# └─ handle_packet(pkt)
#    └─ parser.py parse_packet(pkt)
#       └─ data-dict med src_ip, dst_ip, protocol, function_code, direction osv.
#          └─ state/__init__.py process_observation(data)
#             └─ init_state_manager()
#                ├─ hvis manager findes: genbrug den
#                └─ hvis manager mangler: opret ModbusStateManager og start manager.start()
#                   └─ manager.process(data)
#                      ├─ DeviceTracker
#                      ├─ ConnectionTracker
#                      ├─ RegisterTracker
#                      ├─ RequestTracker
#                      └─ MetricsTracker
#
# Selve analysen sker ikke i denne fil.
# Denne fil sørger kun for, at alle observationer sendes ind i den samme aktive ModbusStateManager.

import threading

from state.manager import ModbusStateManager

# _manager er den ene fælles ModbusStateManager-instans for backend-processen.
# Den starter som None, fordi der endnu ikke er modtaget en observation, der kræver state-behandling.
# Når den først er oprettet, bliver den genbrugt for alle nye packets.
# Det gør at manageren kan huske runtime-state mellem pakker, f.eks. pending requests og kendte function codes.
_manager: ModbusStateManager | None = None

# _manager_lock beskytter selve oprettelsen af manageren.
# Capture kører i en baggrundstråd, og Flask/API kan også køre i samme backend-proces.
# Uden lock kunne to samtidige kald begge nå at se _manager som None og oprette hver sin manager.
# Det ville give to forskellige caches og potentielt to maintenance-tråde.
_manager_lock = threading.Lock()

# init_state_manager() returnerer den fælles ModbusStateManager.
# Først tjekkes om _manager allerede findes. Hvis ja, returneres den direkte.
# Hvis _manager mangler, låses _manager_lock, så kun én thread kan oprette manageren.
# Den nye manager startes med start(), fordi den også har en maintenance-thread til timeouts og metrics flush.
# Derefter gemmes manageren i _manager, så næste observation bruger samme instans.
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
# Derefter sendes observationen videre til manager.process(data).
# Det er manager.process(data), ikke denne fil, der fordeler observationen til devices, connections, registers, requests og metrics.
def process_observation(data: dict) -> None:
    manager = init_state_manager()
    manager.process(data)