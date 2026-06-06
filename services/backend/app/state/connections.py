# connections.py holder styr på master/slave-forbindelser mens backend kører.
# Data kommer fra state/manager.py, som kalder ConnectionTracker.touch(master_ip, slave_ip, unit_id) ved Modbus requests.
# Denne fil modtager altså ikke rå packets. Den modtager allerede parsede IP'er og unit_id fra manageren.
# Filen sender data videre til storage-laget via writer.upsert_connection() og writer.insert_event().
# observed_connections opdateres via upsert_connection(), og nye forbindelser kan oprette new_connection events.
from state.time_utils import now


 # ConnectionTracker holder lokal runtime-state for kendte master -> slave -> unit_id relationer.
 # known_connections bruges til hurtigt at se om relationen er set før i denne backend-kørsel.
 # last_seen bruges af metrics/dashboard til at vide hvornår forbindelsen sidst blev observeret.
 # last_sql_touch begrænser hvor ofte samme kendte forbindelse opdateres i databasen.
 # last_event_id gemmer event-id for nye forbindelser, når der oprettes et event efter learning mode.
class ConnectionTracker:
    # __init__() får writer, learning_mode og sql_touch_seconds fra ModbusStateManager.
    # writer er forbindelsen videre til storage-laget/databasefunktionerne.
    # learning_mode er en funktion fra manager.py, som fortæller om systemet stadig er i læringsperioden.
    # sql_touch_seconds bestemmer hvor lang tid der minimum skal gå før en kendt connection opdateres i SQL igen.
    def __init__(self, writer, learning_mode, sql_touch_seconds: int):
        self.writer = writer
        self.learning_mode = learning_mode
        self.sql_touch_seconds = sql_touch_seconds
        self.known_connections = set()
        self.last_seen = {}
        self.last_sql_touch = {}
        self.last_event_id = {}

    # touch() er hovedfunktionen i denne fil.
    # Den bliver kaldt fra manager.py, når en Modbus request viser at en master taler med en slave.
    # Input kommer ikke direkte fra Scapy, men fra parser.py -> manager.py.
    # master_ip er den enhed der sender requesten.
    # slave_ip er den enhed der modtager requesten.
    # unit_id er Modbus unit/slave-id'et fra MBAP-headeren.
    # Funktionen opdaterer lokal state og skriver relationen videre til observed_connections via writer.upsert_connection().
    def touch(self, master_ip, slave_ip, unit_id):
        # Uden både master_ip og slave_ip kan der ikke oprettes en meningsfuld forbindelse.
        if not master_ip or not slave_ip:
            return

        # current_time bruges både til lokal last_seen og til at styre hvornår databasen må opdateres igen.
        current_time = now()
        # key er den unikke relation: denne master taler med denne slave på dette unit_id.
        key = (master_ip, slave_ip, unit_id)
        # is_new fortæller om relationen ikke er set før i denne backend-kørsel.
        is_new = key not in self.known_connections

        # Relation gemmes i lokal cache, så den ikke behandles som ny næste gang samme trafik ses.
        self.known_connections.add(key)
        self.last_seen[key] = current_time

        # Første gang relationen ses, skrives den med det samme til observed_connections.
        if is_new:
            # Sender relationen videre til storage-laget, som laver INSERT/UPDATE i observed_connections.
            self.writer.upsert_connection(master_ip, slave_ip, unit_id)
            self.last_sql_touch[key] = current_time

            # Under learning mode læres forbindelsen som normal trafik uden alarm.
            # Efter learning mode oprettes et new_connection event, fordi relationen er ny i forhold til det lærte mønster.
            if not self.learning_mode():
                # Opretter et event i events-tabellen, så dashboard/frontenden kan vise den nye forbindelse som hændelse.
                event_id = self.writer.insert_event(
                    event_key=f"new_connection:{master_ip}:{slave_ip}:{unit_id}",
                    event_type="new_connection",
                    severity="info",
                    source_ip=master_ip,
                    target_ip=slave_ip,
                    unit_id=unit_id,
                    details={"message": "New master/slave relation observed"},
                )
                self.last_event_id[key] = event_id
            return

        # Hvis relationen allerede er kendt, opdateres databasen kun med mellemrum.
        # Det undgår databasewrites for hver eneste Modbus request på samme forbindelse.
        last_touch = self.last_sql_touch.get(key)
        # Når sql_touch_seconds er gået, opdateres observed_connections igen med ny last_seen/request_count.
        if last_touch is None or (current_time - last_touch).total_seconds() >= self.sql_touch_seconds:
            # Sender den kendte relation videre til storage-laget, så databasen kan opdatere last_seen og tællere.
            self.writer.upsert_connection(master_ip, slave_ip, unit_id)
            self.last_sql_touch[key] = current_time
