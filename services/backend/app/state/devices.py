# devices.py holder styr på devices mens backend kører.
# Filen bruges af state/manager.py, som kalder DeviceTracker.touch(ip, mac, role), når en IP-adresse ses i trafikken.
# Denne fil modtager ikke rå Scapy-pakker. Den modtager allerede parsede IP/MAC/rolle-værdier fra manager.py.
# Rollen kommer fra manager.py: ARP bliver unknown, Modbus source-IP bliver master, og Modbus destination-IP bliver slave.
# Filen sender data videre til storage-laget via writer.get_device_by_ip(), writer.upsert_device() og writer.insert_event().
# devices-tabellen opdateres via upsert_device(), og nye eller ændrede devices kan oprette events i events-tabellen.
from state.time_utils import now


# DeviceTracker holder lokal runtime-state for kendte devices.
# known_devices er en lokal cache med IP som nøgle. Den gør at databasen ikke skal spørges for hver eneste packet.
# last_sql_touch holder styr på hvornår samme IP sidst blev skrevet til SQL.
# Det begrænser databasewrites, så en kendt device ikke opdaterer devices-tabellen ved hver eneste packet.
# Uden denne begrænsning kan høj trafik give unødigt mange databasewrites for samme device.
class DeviceTracker:
    # __init__() får writer, learning_mode og sql_touch_seconds fra ModbusStateManager.
    # writer er forbindelsen videre til storage-laget/databasefunktionerne.
    # learning_mode er en funktion fra manager.py, som fortæller om systemet stadig er i læringsperioden.
    # sql_touch_seconds bestemmer hvor lang tid der minimum skal gå før en kendt device opdateres i SQL igen.
    def __init__(self, writer, learning_mode, sql_touch_seconds: int):
        self.writer = writer
        self.learning_mode = learning_mode
        self.sql_touch_seconds = sql_touch_seconds
        self.known_devices = {}
        self.last_sql_touch = {}

    # touch() er hovedfunktionen i denne fil.
    # Den bliver kaldt fra manager.py hver gang en IP-adresse skal registreres eller opdateres.
    # Input kommer ikke direkte fra Scapy, men fra parser.py -> manager.py.
    # ip er den observerede IP-adresse.
    # mac er MAC-adressen, hvis parser.py/manager.py har den tilgængelig.
    # role er managerens vurdering af rollen: unknown, master eller slave.
    # Funktionen opdaterer lokal state og skriver device-data videre til devices-tabellen via writer.upsert_device().
    def touch(self, ip, mac=None, role=None):
        # Uden en brugbar IP-adresse kan der ikke oprettes en device.
        # 0.0.0.0 og 255.255.255.255 ignoreres, fordi de ikke repræsenterer normale individuelle devices.
        if not ip or ip in ("0.0.0.0", "255.255.255.255"):
            return

        # current_time bruges til first_seen/last_seen og til at styre hvornår databasen må opdateres igen.
        current_time = now()
        # MAC og rolle normaliseres, så samme værdi ikke behandles forskelligt på grund af store bogstaver eller mellemrum.
        normalized_mac = self._normalize_mac(mac)
        normalized_role = str(role).strip().lower() if role else None

        # Først tjekkes den lokale cache.
        # Hvis IP'en allerede findes her, behøver vi ikke spørge databasen for hver packet.
        existing = self.known_devices.get(ip) 

        # Hvis IP'en ikke findes i lokal cache, tjekkes databasen.
        # Det håndterer devices som allerede var gemt fra tidligere backend-kørsler.
        if existing is None:
            # Spørger storage-laget om IP'en allerede findes i devices-tabellen.
            db_device = self.writer.get_device_by_ip(ip)

            # Hvis databasen allerede kender IP'en, lægges den ind i lokal cache.
            # Den skal ikke oprettes igen.
            if db_device:
                existing = {
                    "mac": self._normalize_mac(db_device.get("mac")),
                    "role": db_device.get("role"),
                    "first_seen": db_device.get("first_seen"),
                    "last_seen": current_time,
                }
                self.known_devices[ip] = existing
            else:
                # Hvis IP'en hverken findes i cache eller database, er det en ny device.
                self.known_devices[ip] = {
                    "mac": normalized_mac,
                    "role": normalized_role,
                    "first_seen": current_time,
                    "last_seen": current_time,
                }

                # Sender den nye device videre til storage-laget, som laver INSERT/UPDATE i devices-tabellen.
                self.writer.upsert_device(ip, normalized_mac, normalized_role)

                # Under learning mode læres nye devices som normal trafik uden alarm.
                # Efter learning mode oprettes et new_device event, fordi enheden er ny i forhold til det lærte mønster.
                if not self.learning_mode():
                    # Opretter et event i events-tabellen, så frontend kan vise den nye device som hændelse.
                    event_id = self.writer.insert_event(
                        event_key=f"new_device:{ip}",
                        event_type="new_device",
                        severity="info",
                        source_ip=ip,
                        details={
                            "message": "New device observed",
                            "mac": normalized_mac,
                            "role": normalized_role,
                        },
                    )
                    self.known_devices[ip]["last_event_id"] = event_id

                # Gemmer hvornår denne IP sidst blev skrevet til SQL.
                self.last_sql_touch[ip] = current_time
                return

        # Herfra er device kendt enten fra cache eller database.
        # Nu sammenlignes den nye observation med det vi allerede kender.
        old_mac = self._normalize_mac(existing.get("mac"))
        old_role = existing.get("role")
        # Rollen flettes, så unknown ikke overskriver en kendt master/slave-rolle.
        merged_role = self._merge_role(old_role, normalized_role)

        # MAC-skift registreres kun hvis både gammel og ny MAC findes og de er forskellige.
        mac_changed = bool(normalized_mac and old_mac and old_mac != normalized_mac)
        # Rolle-skift registreres kun som alarm ved reelt skift mellem master og slave.
        role_changed = bool(
            old_role
            and merged_role
            and old_role != merged_role
            and {old_role, merged_role} == {"master", "slave"}
        )

        # Hvis samme IP ses med en anden MAC, oprettes et identity_mac_changed event.
        # Det kan indikere ARP spoofing, MITM eller udskiftet netværksenhed.
        # Event-key indeholder tidspunktet, så hvert MAC-skift gemmes som en ny alarm.
        # Det betyder at A -> B, B -> A og A -> B igen alle bliver synlige i events-tabellen.
        if mac_changed:
            # Sender MAC-skiftet videre til events-tabellen via storage-laget.
            event_id = self.writer.insert_event(
                event_key=f"identity_mac_changed:{ip}:{old_mac}:{normalized_mac}:{current_time.isoformat()}",
                event_type="identity_mac_changed",
                severity="high",
                source_ip=ip,
                old_value=old_mac,
                new_value=normalized_mac,
                details={
                    "message": "Known IP observed with a different MAC address",
                    "old_mac": old_mac,
                    "new_mac": normalized_mac,
                    "role": merged_role,
                    "is_pinned": True,
                    "pin_reason": "IP/MAC identity changed",
                },
            )
            existing["last_event_id"] = event_id
            existing["mac"] = normalized_mac

        # Hvis en kendt device skifter mellem master og slave, oprettes et identity_role_changed event.
        if role_changed:
            # Sender rolleskiftet videre til events-tabellen via storage-laget.
            event_id = self.writer.insert_event(
                event_key=f"identity_role_changed:{ip}",
                event_type="identity_role_changed",
                severity="high",
                source_ip=ip,
                old_value=old_role,
                new_value=merged_role,
                details={
                    "message": "Known device changed Modbus role",
                    "old_role": old_role,
                    "new_role": merged_role,
                    "mac": normalized_mac or old_mac,
                    "is_pinned": True,
                    "pin_reason": "Device role changed",
                },
            )
            existing["last_event_id"] = event_id

        # Lokal cache opdateres med den nyeste rolle og last_seen-tid.
        existing["role"] = merged_role
        existing["last_seen"] = current_time

        # Hvis device allerede er kendt, skrives den ikke nødvendigvis til databasen hver gang.
        # last_sql_touch bruges til at se hvornår IP'en sidst blev skrevet til SQL.
        last_touch = self.last_sql_touch.get(ip)
        # SQL opdateres hvis intervallet er gået, eller hvis MAC/rolle har ændret sig.
        should_touch_sql = (
            last_touch is None
            or (current_time - last_touch).total_seconds() >= self.sql_touch_seconds
            or mac_changed
            or role_changed
        )

        # Når der skal skrives til SQL, sendes den aktuelle device-state videre til storage-laget.
        if should_touch_sql:
            # upsert_device() opdaterer devices-tabellen med ny MAC, rolle og last_seen.
            self.writer.upsert_device(ip, existing.get("mac"), existing.get("role"))
            self.last_sql_touch[ip] = current_time

    # _normalize_mac() gør MAC-adresser ensartede.
    # Den fjerner whitespace og gør bogstaver små, så samme MAC ikke behandles som to forskellige værdier.
    def _normalize_mac(self, mac):
        if not mac:
            return None
        return str(mac).strip().lower()

    # _merge_role() bestemmer hvilken rolle en device skal have.
    # Hvis enheden allerede er kendt som master eller slave, overskrives den ikke af unknown.
    # Hvis rollen reelt skifter mellem master og slave, kan touch() oprette et identity_role_changed event.
    def _merge_role(self, current_role, new_role):
        if not new_role:
            return current_role

        new_role = str(new_role).strip().lower()
        current_role = str(current_role).strip().lower() if current_role else None

        if new_role == "unknown" and current_role in ("master", "slave"):
            return current_role

        return new_role
