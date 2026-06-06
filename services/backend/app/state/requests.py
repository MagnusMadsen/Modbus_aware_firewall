# requests.py holder styr på Modbus requests der venter på et response.
# Data kommer fra state/manager.py, som kalder RequestTracker.add_request(data) ved Modbus requests.
# Responses kommer også fra state/manager.py, som kalder RequestTracker.handle_response(data) ved Modbus responses.
# Den modtager data-dicts fra packet_parser/parser.py, som allerede er parset.
# Formålet er at matche request og response, beregne latency, opdage timeouts og registrere Modbus exception responses.
# Resultater sendes videre til metrics.py og storage-laget via metrics.* og writer.insert_event().

from state.time_utils import now

from datetime import datetime


# _packet_time() finder tidspunktet for en observation.
# parser.py lægger timestamp i data["ts"] ud fra Scapy pkt.time.
# Hvis timestamp mangler eller ikke kan parses, bruges now() som fallback.
def _packet_time(data):
    # ts kommer fra data-dictet som parser.py har lavet.
    ts = data.get("ts")
    # Hvis der ikke findes timestamp i observationen, bruges nuværende tid.
    if not ts:
        return now()

    try:
        # Parser ISO-formatet tilbage til datetime, så der kan regnes latency.
        return datetime.fromisoformat(ts)
    # Hvis timestamp-formatet er ugyldigt, bruges now() i stedet for at stoppe programmet.
    except ValueError:
        return now()


# RequestTracker holder lokal runtime-state for Modbus requests der endnu ikke har fået response.
# pending_requests er en cache i RAM med requests der venter på svar.
# last_timeout_event_at bruges til at begrænse hvor ofte samme timeout-type opretter events.
# Klassen er nødvendig, fordi latency og timeout kun kan vurderes ved at sammenligne en request med senere response eller manglende response.
class RequestTracker:
    # __init__() får writer, metrics, learning_mode og grænseværdier fra ModbusStateManager.
    # writer sender events videre til storage-laget/databasefunktionerne.
    # metrics bruges til at tælle responses, failed requests og latency.
    # learning_mode fortæller om systemet stadig er i læringsperioden.
    # request_timeout_seconds bestemmer hvor længe en request må vente på response.
    # latency_spike_ms bestemmer hvornår latency bliver en latency_spike event.
    # timeout_event_throttle_seconds begrænser gentagne timeout-events for samme master/slave/unit_id.
    def __init__(
        self,
        writer,
        metrics,
        learning_mode,
        request_timeout_seconds: float,
        latency_spike_ms: float,
        timeout_event_throttle_seconds: float,
    ):
        self.writer = writer
        self.metrics = metrics
        self.learning_mode = learning_mode
        self.request_timeout_seconds = request_timeout_seconds
        self.latency_spike_ms = latency_spike_ms
        self.timeout_event_throttle_seconds = timeout_event_throttle_seconds
        self.pending_requests = {}
        self.last_timeout_event_at = {}

    # add_request() kaldes fra manager.py, når en Modbus request er observeret.
    # data kommer fra parser.py -> manager.py og indeholder src_ip, dst_ip, transaction_id, unit_id og registerfelter.
    # Requesten gemmes i pending_requests, så en senere response kan matches og latency kan beregnes.
    def add_request(self, data):
        # Disse felter bruges til at identificere requesten entydigt.
        # src_ip er masteren, og dst_ip er slaven ved en request.
        transaction_id = data.get("transaction_id")
        unit_id = data.get("unit_id")
        master_ip = data.get("src_ip")
        slave_ip = data.get("dst_ip")

        # Uden transaction_id, unit_id, master_ip og slave_ip kan request/response ikke matches sikkert.
        if transaction_id is None or unit_id is None or not master_ip or not slave_ip:
            return

        # key bruges senere til at finde samme request, når response kommer retur.
        key = (master_ip, slave_ip, transaction_id, unit_id)

        # Gemmer requesten i RAM indtil response kommer eller requesten udløber på timeout.
        # Registerfelterne gemmes også, så timeout-events kan fortælle hvad requesten handlede om.
        self.pending_requests[key] = {
            "ts": _packet_time(data),
            "function_code": data.get("function_code"),
            "register_type": data.get("register_type"),
            "register_address": data.get("register_address"),
            "values": data.get("values"),
        }

    # handle_response() kaldes fra manager.py, når en Modbus response er observeret.
    # data kommer fra parser.py -> manager.py og indeholder response-felter som src_ip, dst_ip, transaction_id, unit_id og exception-data.
    # Funktionen prøver at finde den tilsvarende request i pending_requests.
    # Hvis den findes, beregnes latency og requesten fjernes fra pending_requests.
    def handle_response(self, data):
        # Responsen tælles i metrics, uanset om den kan matches med en pending request.
        self.metrics.count_response()

        # Ved en response er retningen vendt: src_ip er slaven, og dst_ip er masteren.
        # Derfor bygges pending_key med master_ip=dst_ip og slave_ip=src_ip.
        master_ip = data.get("dst_ip")
        slave_ip = data.get("src_ip")
        transaction_id = data.get("transaction_id")
        unit_id = data.get("unit_id")

        # Hvis de nødvendige match-felter mangler, kan responsen ikke kobles til en request.
        if transaction_id is None or unit_id is None or not master_ip or not slave_ip:
            return

        # Samme nøgle som add_request() brugte, bare bygget ud fra response-retningen.
        pending_key = (master_ip, slave_ip, transaction_id, unit_id)
        # pop() henter og fjerner den ventende request.
        # Når response er fundet, skal requesten ikke længere ligge som pending.
        pending = self.pending_requests.pop(pending_key, None)

        # Hvis der ikke findes en matchende request, kan latency ikke beregnes.
        if pending is None:
            return

        # Latency beregnes som response-tidspunkt minus request-tidspunkt.
        # Resultatet laves om til millisekunder.
        latency_ms = round((_packet_time(data) - pending["ts"]).total_seconds() * 1000.0, 2)

        # Negativ latency kan ske ved tidsfejl og ignoreres.
        if latency_ms < 0:
            return

        # Meget høj latency over 10 sekunder ignoreres som ugyldig måling her.
        # Timeouts håndteres separat i expire_if_needed().
        if latency_ms > 10000:
            return

        # Sender latency-målingen videre til MetricsTracker, som gemmer den i det aktuelle metrics bucket.
        self.metrics.add_latency(latency_ms)

        # Efter learning mode oprettes latency_spike event, hvis latency overstiger grænsen.
        if latency_ms >= self.latency_spike_ms and not self.learning_mode():
            # Sender latency_spike-hændelsen videre til events-tabellen via storage-laget.
            self.writer.insert_event(
                event_key=f"latency_spike:{master_ip}:{slave_ip}:{unit_id}",
                event_type="latency_spike",
                severity="medium",
                source_ip=master_ip,
                target_ip=slave_ip,
                unit_id=unit_id,
                function_code=data.get("function_code"),
                new_value=latency_ms,
                details={
                    "message": "High latency detected",
                    "latency_ms": latency_ms,
                    "is_pinned": True,
                    "pin_reason": "Latency spike",
                },
            )

        # Modbus exception responses betyder at slaven svarede med en fejl.
        # Efter learning mode tælles det som failed request og oprettes som event.
        if data.get("is_exception") and not self.learning_mode():
            # Exception response tælles som failed request i metrics.
            self.metrics.count_failed()
            # Sender exception_response-hændelsen videre til events-tabellen via storage-laget.
            self.writer.insert_event(
                event_key=f"exception_response:{master_ip}:{slave_ip}:{unit_id}:{data.get('function_code')}:{data.get('exception_code')}",
                event_type="exception_response",
                severity="high",
                source_ip=master_ip,
                target_ip=slave_ip,
                unit_id=unit_id,
                function_code=data.get("function_code"),
                new_value=data.get("exception_code"),
                details={
                    "message": "Modbus exception response",
                    "exception_code": data.get("exception_code"),
                    "is_pinned": True,
                    "pin_reason": "Modbus exception response",
                },
            )

    # expire_if_needed() kaldes løbende fra manager.process(data) og managerens maintenance loop.
    # Funktionen gennemgår pending_requests og finder requests der har ventet længere end request_timeout_seconds.
    # Requests der er udløbet fjernes fra pending_requests.
    # Efter learning mode kan en timeout oprette request_timeout event og tælles som failed request.
    def expire_if_needed(self):
        # current_time bruges til at beregne hvor gamle pending requests er.
        current_time = now()
        # Først samles keys for udløbne requests.
        # Selve dictet ændres først bagefter, så vi ikke ændrer pending_requests mens vi itererer over det.
        expired_keys = []

        # Gennemgår alle requests der stadig venter på response.
        for key, pending in self.pending_requests.items():
            # age er hvor længe requesten har ventet på response.
            age = (current_time - pending["ts"]).total_seconds()
            # Hvis requesten har ventet for længe, markeres den som udløbet.
            if age >= self.request_timeout_seconds:
                expired_keys.append(key)

        # Nu behandles de udløbne requests én ad gangen.
        for key in expired_keys:
            # Fjerner requesten fra pending_requests, fordi den ikke længere skal vente på response.
            pending = self.pending_requests.pop(key, None)
            # Hvis requesten allerede er fjernet, springes den over.
            if pending is None:
                continue

            # Under learning mode fjernes timeouten, men der oprettes ikke alarm-event.
            if self.learning_mode():
                continue

            # Timeout-events throttles, så samme master/slave/unit_id ikke spammer events-tabellen.
            if not self._should_emit_timeout_event(key, current_time):
                continue

            # Pakker nøglen ud. transaction_id bruges ikke i eventet her, derfor ignoreres den med _.
            master_ip, slave_ip, _, unit_id = key
            # Timeout tælles som failed request i metrics.
            self.metrics.count_failed()

            # Sender request_timeout-hændelsen videre til events-tabellen via storage-laget.
            self.writer.insert_event(
                event_key=f"request_timeout:{master_ip}:{slave_ip}:{unit_id}:{pending.get('function_code')}:{pending.get('register_type')}:{pending.get('register_address')}",
                event_type="request_timeout",
                severity="high",
                source_ip=master_ip,
                target_ip=slave_ip,
                unit_id=unit_id,
                function_code=pending.get("function_code"),
                register_type=pending.get("register_type"),
                register_address=pending.get("register_address"),
                details={
                    "message": "No response seen before timeout",
                    "is_pinned": True,
                    "pin_reason": "Request timeout",
                },
            )

    # _should_emit_timeout_event() afgør om en timeout-event må oprettes nu.
    # Den bruges for at undgå mange ens timeout-events på kort tid.
    # Throttle sker pr. master_ip, slave_ip og unit_id.
    def _should_emit_timeout_event(self, key, current_time):
        # transaction_id ignoreres her, fordi throttle skal gælde relationen og ikke kun én bestemt request.
        master_ip, slave_ip, _, unit_id = key
        # Finder tidspunktet for seneste timeout-event for samme master/slave/unit_id.
        throttle_key = (master_ip, slave_ip, unit_id)

        # Hvis der allerede er sendt timeout-event for relationen, tjekkes alderen.
        last_event_at = self.last_timeout_event_at.get(throttle_key)
        if last_event_at is not None:
            # Hvis sidste event er for nylig, oprettes der ikke en ny event.
            age = (current_time - last_event_at).total_seconds()
            if age < self.timeout_event_throttle_seconds:
                return False

        # Gemmer at der nu sendes timeout-event for denne relation.
        self.last_timeout_event_at[throttle_key] = current_time
        return True