# registers.py holder styr på Modbus-registerværdier mens backend kører.
# Data kommer fra state/manager.py, som kalder RegisterTracker.process_changes(data) ved Modbus write requests.
# Denne fil modtager ikke rå Scapy-pakker. Den modtager et data-dict, som allerede er parset af packet_parser/parser.py og fordelt af manager.py.
# Filen bruger kun write function codes: 5, 6, 15 og 16, fordi det er dem der ændrer coils eller holding registers.
# Register-state gemmes lokalt i self.register_state og sendes videre til databasen via writer.upsert_register_state().
# Nye registre og ændrede registerværdier kan oprette events via writer.insert_event().
# Kritiske registre vurderes via writer.get_critical_register(), som læser policy fra critical_registers-tabellen.

# RegisterTracker holder lokal runtime-state for kendte registerværdier.
# register_state bruger nøglen (slave_ip, unit_id, register_type, address), så samme register kan genkendes igen.
# last_event_id gemmer det seneste event-id for et register, når der oprettes en event.
class RegisterTracker:
    # __init__() får writer og learning_mode fra ModbusStateManager.
    # writer er forbindelsen videre til storage-laget/databasefunktionerne.
    # learning_mode fortæller om systemet stadig er i læringsperioden.
    def __init__(self, writer, learning_mode):
        self.writer = writer
        self.learning_mode = learning_mode
        self.register_state = {}
        self.last_event_id = {}

    # process_changes() er hovedfunktionen i denne fil.
    # Den bliver kaldt fra manager.py, når en Modbus request kan indeholde en registerændring.
    # data kommer fra parser.py -> manager.py og indeholder f.eks. dst_ip, unit_id, function_code, register_type, register_address og values.
    # Funktionen opdaterer lokal register_state, skriver til modbus_register_state og opretter events ved nye eller ændrede værdier.
    def process_changes(self, data):
        # function_code kommer fra Modbus-pakken og fortæller hvilken operation masteren forsøger at udføre.
        function_code = data.get("function_code")

        # Kun write-funktioner ændrer register-state.
        # 5 = Write Single Coil, 6 = Write Single Register, 15 = Write Multiple Coils, 16 = Write Multiple Registers.
        if function_code not in (5, 6, 15, 16):
            return

        # Ved en Modbus write request er dst_ip den slave/PLC, som masteren skriver til.
        # De næste felter beskriver hvilket registerområde og hvilke værdier der skrives.
        slave_ip = data.get("dst_ip")
        unit_id = data.get("unit_id")
        register_type = data.get("register_type")
        start_address = data.get("register_address")
        values = data.get("values") or []

        # Hvis parseren ikke fandt de nødvendige registerfelter, kan ændringen ikke spores sikkert.
        if slave_ip is None or unit_id is None or register_type is None or start_address is None:
            return

        # values kan indeholde én eller flere værdier.
        # Ved multiple-write svarer offset til placeringen efter start_address.
        # Eksempel: start_address=9 og values=[42, 16, 255] betyder register 9=42, 10=16, 11=255.
        for offset, value in enumerate(values):
            # Den konkrete registeradresse beregnes ud fra start_address plus offset i values-listen.
            address = start_address + offset

            # state_key identificerer ét bestemt register på én bestemt slave og unit_id.
            state_key = (slave_ip, unit_id, register_type, address)

            # old_value er den værdi backend sidst har set for dette register i runtime-state.
            old_value = self.register_state.get(state_key)

            # Vurderer om registeret er kritisk, og om ændringen skal pins eller have højere severity.
            classification = self._classify_register_change(
                slave_ip=slave_ip,
                unit_id=unit_id,
                register_type=register_type,
                register_address=address,
                new_value=value,
            )

            # Hvis registeret ikke findes i lokal state endnu, er det første gang backend ser dette register.
            if old_value is None:
                # Gemmer første observerede værdi lokalt, så fremtidige ændringer kan sammenlignes.
                self.register_state[state_key] = value

                # Sender registerets aktuelle værdi videre til storage-laget, som skriver til modbus_register_state.
                self.writer.upsert_register_state(slave_ip, unit_id, register_type, address, value)

                # Under learning mode oprettes normalt ikke events for nye registre.
                # Kritiske/pinnede registre opretter stadig event, fordi de er vigtige uanset learning mode.
                if not self.learning_mode() or classification["is_pinned"]:
                    # Opretter et new_register_observed event i events-tabellen.
                    event_id = self.writer.insert_event(
                        event_key=f"new_register_observed:{slave_ip}:{unit_id}:{register_type}:{address}",
                        event_type="new_register_observed",
                        severity=classification["severity"] if classification["is_pinned"] else "info",
                        source_ip=data.get("src_ip"),
                        target_ip=slave_ip,
                        unit_id=unit_id,
                        function_code=function_code,
                        register_type=register_type,
                        register_address=address,
                        new_value=value,
                        details={
                            "message": "New register observed",
                            "is_pinned": classification["is_pinned"],
                            "pin_reason": classification["pin_reason"],
                            "critical_label": classification["critical_label"],
                        },
                    )
                    self.last_event_id[state_key] = event_id
                continue

            # Hvis registeret allerede er kendt, oprettes der kun event når værdien faktisk ændrer sig.
            if old_value != value:
                # Opdaterer lokal state til den nye registerværdi.
                self.register_state[state_key] = value

                # Sender den nye registerværdi videre til modbus_register_state via storage-laget.
                self.writer.upsert_register_state(slave_ip, unit_id, register_type, address, value)

                # Opretter et register_value_changed event med gammel og ny værdi.
                event_id = self.writer.insert_event(
                    event_key=f"register_value_changed:{slave_ip}:{unit_id}:{register_type}:{address}",
                    event_type="register_value_changed",
                    severity=classification["severity"],
                    source_ip=data.get("src_ip"),
                    target_ip=slave_ip,
                    unit_id=unit_id,
                    function_code=function_code,
                    register_type=register_type,
                    register_address=address,
                    old_value=old_value,
                    new_value=value,
                    details={
                        "message": "Register value changed",
                        "is_pinned": classification["is_pinned"],
                        "pin_reason": classification["pin_reason"],
                        "critical_label": classification["critical_label"],
                    },
                )
                self.last_event_id[state_key] = event_id

    # _classify_register_change() vurderer om registeret er defineret som kritisk.
    # Data hentes fra critical_registers-tabellen via writer.get_critical_register().
    # Funktionen returnerer severity, is_pinned, pin_reason og critical_label.
    # Den skriver ikke selv til databasen.
    def _classify_register_change(self, slave_ip, unit_id, register_type, register_address, new_value):
        # Spørger storage-laget om dette register findes i critical_registers-tabellen.
        critical = self.writer.get_critical_register(
            slave_ip=slave_ip,
            unit_id=unit_id,
            register_type=register_type,
            register_address=register_address,
        )

        # Standardklassifikation for almindelige registerændringer.
        result = {
            "severity": "medium",
            "is_pinned": False,
            "pin_reason": None,
            "critical_label": None,
        }

        # Hvis registeret ikke er markeret som kritisk, bruges standardklassifikationen.
        if not critical:
            return result

        # Label bruges af frontend til at vise et menneskeligt navn for det kritiske register.
        result["critical_label"] = critical.get("label")

        # allowed_values er en valgfri liste over værdier registeret må have.
        allowed_values = critical.get("allowed_values")
        if allowed_values is not None:
            # Værdier sammenlignes som tekst, så f.eks. 1 og "1" behandles ens.
            normalized_allowed = {str(v) for v in allowed_values}
            # Hvis den nye værdi ikke er tilladt, markeres eventet som critical og pinned.
            if str(new_value) not in normalized_allowed:
                result["severity"] = "critical"
                result["is_pinned"] = True
                result["pin_reason"] = "Value outside allowed values"
                return result

        # pin_on_change betyder at enhver ændring på dette register skal fremhæves.
        if critical.get("pin_on_change"):
            result["severity"] = "high"
            result["is_pinned"] = True
            result["pin_reason"] = "Critical register changed"

        return result
