# manager.py styrer det samlede state-flow for observeret trafik.
# Den modtager data fra state/__init__.py gennem process(data).
# Filen fordeler observationen videre til de rigtige trackers: devices, connections, metrics, registers og requests.
# Den skriver ikke selv direkte SQL, men bruger self.writer fra storage-laget når der skal oprettes events.

import os
import threading
import time

from state.connections import ConnectionTracker
from state.devices import DeviceTracker
from state.metrics import MetricsTracker
from state.registers import RegisterTracker
from state.requests import RequestTracker
from state.time_utils import now
from storage import get_writer

# Learning window er perioden efter startup hvor systemet lærer normal trafik.
# I denne periode registreres kendte enheder, forbindelser og funktioner uden at alt nødvendigvis bliver alarm.
LEARNING_WINDOW_SECONDS = int(os.getenv("LEARNING_WINDOW_SECONDS", "300"))

# FLUSH_INTERVAL_SECONDS bestemmer hvor ofte metrics skrives til metrics_bucket.
# Det bruges for ikke at skrive til databasen for hver eneste packet.
FLUSH_INTERVAL_SECONDS = int(os.getenv("FLUSH_INTERVAL_SECONDS", "5"))

# Request/response-indstillinger.
# REQUEST_TIMEOUT_SECONDS er hvor længe en Modbus request må mangle svar før den kan tælles som timeout.
# LATENCY_SPIKE_MS er grænsen for hvornår en response vurderes som latency spike.
# TIMEOUT_EVENT_THROTTLE_SECONDS begrænser hvor ofte timeout-events oprettes, så samme fejl ikke spammer events-tabellen.
REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "10.0"))
LATENCY_SPIKE_MS = float(os.getenv("LATENCY_SPIKE_MS", "1000.0"))
TIMEOUT_EVENT_THROTTLE_SECONDS = float(os.getenv("TIMEOUT_EVENT_THROTTLE_SECONDS", "80.0"))

# SQL touch-intervaller begrænser hvor ofte kendte devices/connections opdaterer last_seen i databasen.
# Uden denne begrænsning ville samme kendte enhed kunne give mange databasewrites pr. sekund.
DEVICE_SQL_TOUCH_SECONDS = int(os.getenv("DEVICE_SQL_TOUCH_SECONDS", "120"))
CONNECTION_SQL_TOUCH_SECONDS = int(os.getenv("CONNECTION_SQL_TOUCH_SECONDS", "120"))


# ModbusStateManager samler alle trackers i én controller.
# process(data) er hovedindgangen for nye observationer.
# start() starter en baggrundstråd, som løbende håndterer timeouts og metrics-flush.
class ModbusStateManager:
    # __init__() opretter writer og alle under-trackers.
    # writer kommer fra storage og er den samlede adgang til databasefunktionerne.
    # started_at bruges til at beregne om systemet stadig er i learning mode.
    # known_function_codes bruges til at opdage nye Modbus function codes efter learning mode.
    def __init__(self):
        self.writer = get_writer()
        self.lock = threading.Lock()
        self.started_at = now()
        self.known_function_codes = set()
        self._maintenance_thread = None

        self.devices = DeviceTracker(
            writer=self.writer,
            learning_mode=self.in_learning_mode,
            sql_touch_seconds=DEVICE_SQL_TOUCH_SECONDS,
        )
        self.connections = ConnectionTracker(
            writer=self.writer,
            learning_mode=self.in_learning_mode,
            sql_touch_seconds=CONNECTION_SQL_TOUCH_SECONDS,
        )
        self.metrics = MetricsTracker(
            writer=self.writer,
            flush_interval_seconds=FLUSH_INTERVAL_SECONDS,
            connection_last_seen=self.connections.last_seen,
        )
        self.registers = RegisterTracker(
            writer=self.writer,
            learning_mode=self.in_learning_mode,
        )
        self.requests = RequestTracker(
            writer=self.writer,
            metrics=self.metrics,
            learning_mode=self.in_learning_mode,
            request_timeout_seconds=REQUEST_TIMEOUT_SECONDS,
            latency_spike_ms=LATENCY_SPIKE_MS,
            timeout_event_throttle_seconds=TIMEOUT_EVENT_THROTTLE_SECONDS,
        )

    # in_learning_mode() returnerer True så længe backend stadig er inden for learning window.
    # Efter learning window kan nye observationer udløse events, fordi de afviger fra det systemet først lærte.
    def in_learning_mode(self):
        return (now() - self.started_at).total_seconds() < LEARNING_WINDOW_SECONDS

    # start() starter maintenance-tråden én gang.
    # Hvis tråden allerede findes, returnerer funktionen uden at starte en ekstra tråd.
    def start(self):
        if self._maintenance_thread is not None:
            return

        self._maintenance_thread = threading.Thread(target=self._maintenance_loop, daemon=True)
        self._maintenance_thread.start()

    # process(data) er hovedindgangen til ModbusStateManager.
    # Data kommer fra: capture.py -> parser.py -> state/__init__.py -> manager.process(data).
    # data er ikke en rå packet længere. Det er et dictionary fra parser.py med f.eks. src_ip, dst_ip, src_mac, dst_mac, protocol, is_modbus, direction, unit_id, function_code og values.
    # Funktionen henter ikke selv data fra netværket eller databasen. Den modtager én observation som argument og fordeler den videre.
    # Data sendes videre til trackers afhængigt af hvad observationen indeholder:
    # ARP -> _handle_arp(data) -> metrics + devices
    # Modbus request -> _handle_modbus_request(data) -> metrics + devices + connections + registers + requests
    # Modbus response -> requests.handle_response(data) -> request/response matching + latency/timeout metrics
    # Ikke-Modbus trafik returneres her, fordi parser.py allerede har læst IP/MAC-felter, men manageren kun tracker ARP og Modbus.
    def process(self, data):
        # Locken gør at én observation behandles færdig ad gangen.
        # Det beskytter de lokale caches i devices, connections, requests, registers og metrics.
        with self.lock:
            # Før ny observation behandles, skrives metrics til metrics_bucket hvis flush-intervallet er nået.
            self.metrics.flush_if_due()
            # Tjekker om tidligere Modbus requests har ventet for længe på response.
            # Hvis de er for gamle, kan RequestTracker registrere timeout/failed request.
            self.requests.expire_if_needed()

            # protocol kommer fra parser.py og fortæller hvilket niveau pakken blev parset til: ARP, IP, TCP eller MODBUS.
            protocol = data.get("protocol")
            # ARP går sin egen vej, fordi ARP ikke har Modbus function_code, unit_id eller request/response-retning.
            if protocol == "ARP":
                self._handle_arp(data)
                return

            # Hvis observationen ikke er Modbus, stopper manageren her.
            # IP/TCP-trafik uden Modbus bruges ikke til register-, request- eller connection-tracking.
            if not data.get("is_modbus"):
                return

            # Her er observationen bekræftet som Modbus, så den tælles som Modbus-trafik i metrics.
            self.metrics.count_traffic()

            # direction kommer fra parser.py/direction.py.
            # Request og response behandles forskelligt, fordi de betyder forskellige ting for state-laget.
            if data.get("direction") == "request":
                # Requesten sendes videre til _handle_modbus_request(), som registrerer master/slave, connection, function code, registerændringer og pending request.
                self._handle_modbus_request(data)
            elif data.get("direction") == "response":
                # Responsen sendes til RequestTracker, som matcher den med en tidligere request via transaction_id/IP/unit_id og beregner latency.
                self.requests.handle_response(data)

    # _maintenance_loop() kører i baggrunden én gang i sekundet.
    # Den sikrer at timeouts og metrics stadig behandles, selv hvis der ikke kommer nye packets hele tiden.
    def _maintenance_loop(self):
        while True:
            time.sleep(1)
            with self.lock:
                self.requests.expire_if_needed()
                self.metrics.flush_if_due()

    # _handle_arp() håndterer ARP-observationer.
    # Den tæller ARP i metrics og sender src_ip/src_mac videre til DeviceTracker som role="unknown".
    # Rollen er unknown, fordi ARP ikke fortæller om enheden er Modbus master eller slave.
    def _handle_arp(self, data):
        self.metrics.count_arp()
        self.devices.touch(data.get("src_ip"), data.get("src_mac"), role="unknown")

    # _handle_modbus_request() håndterer Modbus requests.
    # src_ip behandles som master, fordi den sender requesten.
    # dst_ip behandles som slave, fordi den modtager requesten.
    # Funktionen opdaterer devices, connection relationen, function code tracking, registerændringer og pending request-state.
    def _handle_modbus_request(self, data):
        master_ip = data.get("src_ip")
        slave_ip = data.get("dst_ip")
        unit_id = data.get("unit_id")
        function_code = data.get("function_code")

        self.metrics.count_request()

        self.devices.touch(master_ip, data.get("src_mac"), role="master")
        self.devices.touch(slave_ip, data.get("dst_mac"), role="slave")
        self.connections.touch(master_ip, slave_ip, unit_id)
        self._track_function_code(master_ip, slave_ip, unit_id, function_code)
        self.registers.process_changes(data)
        self.requests.add_request(data)

    # _track_function_code() holder styr på hvilke Modbus function codes der er set pr. slave/unit_id.
    # fc_key består af slave_ip, unit_id og function_code.
    # Hvis samme fc_key allerede er set, returneres der for at undgå dubletter.
    # Efter learning mode oprettes et new_function_code event, hvis en ny function code observeres.
    def _track_function_code(self, master_ip, slave_ip, unit_id, function_code):
        fc_key = (slave_ip, unit_id, function_code)
        if fc_key in self.known_function_codes:
            return

        self.known_function_codes.add(fc_key)
        if self.in_learning_mode():
            return

        self.writer.insert_event(
            event_key=f"new_function_code:{slave_ip}:{unit_id}:{function_code}",
            event_type="new_function_code",
            severity="info",
            source_ip=master_ip,
            target_ip=slave_ip,
            unit_id=unit_id,
            function_code=function_code,
            details={"message": "New function code observed on this slave"},
        )


