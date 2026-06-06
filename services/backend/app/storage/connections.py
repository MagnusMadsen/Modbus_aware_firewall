# connections.py skriver master/slave-relationer til observed_connections-tabellen.
# Filen henter ikke selv master_ip, slave_ip eller unit_id.
# De værdier bliver sendt ind som argumenter, når en anden del af programmet kalder upsert_connection(master_ip, slave_ip, unit_id).
# Flowet er:
# capture.py fanger packet -> parser.py finder IP'er og unit_id -> state/__init__.py sender data til manager.py
# manager.py kalder ConnectionTracker.touch(master_ip, slave_ip, unit_id)
# state/connections.py kalder self.writer.upsert_connection(master_ip, slave_ip, unit_id)
# StorageWriter i storage/__init__.py videresender kaldet til denne fil: storage/connections.py upsert_connection(...)
# master_ip og slave_ip kommer fra IP-headeren i Modbus requesten.
# unit_id kommer fra MBAP-headeren i TCP payloaden.
# Denne fil er derfor sidste led i flowet: den modtager færdige værdier og skriver dem til SQL.
from storage.base import execute


# upsert_connection() opretter eller opdaterer én relation i observed_connections.
# Funktionen spørger ikke selv efter master_ip, slave_ip eller unit_id.
# Den modtager dem som parametre fra StorageWriter.upsert_connection(), som blev kaldt fra state/connections.py.
# master_ip = src_ip fra IP-headeren ved en Modbus request.
# slave_ip = dst_ip fra IP-headeren ved en Modbus request.
# unit_id = Modbus unit/slave-id fra MBAP-headeren.
# Funktionen laver kun databasearbejdet: INSERT hvis relationen er ny, UPDATE hvis relationen allerede findes.
def upsert_connection(master_ip, slave_ip, unit_id=None):
    # Uden både master_ip og slave_ip kan relationen ikke gemmes meningsfuldt.
    if not master_ip or not slave_ip:
        return

    # På dette tidspunkt er værdierne allerede besluttet af manager/state-laget.
    # Denne funktion bruger dem bare som SQL-parametre.
    # Sender SQL-kommandoen videre til storage/base.py execute(), som åbner connection og kører queryen.
    execute(
        """
        -- Opretter relationen første gang den ses.
        INSERT INTO observed_connections
            (master_ip, slave_ip, unit_id, first_seen, last_seen, request_count)
        VALUES
            (%s, %s, %s, NOW(), NOW(), 1)
        -- Hvis relationen allerede findes, opdateres den i stedet for at oprette en dublet.
        ON CONFLICT (master_ip, slave_ip, unit_id)
        DO UPDATE SET
            -- last_seen flyttes frem, og request_count tælles op for hver observeret request på relationen.
            last_seen = NOW(),
            request_count = observed_connections.request_count + 1
        """,
        # Parametrene bindes separat, så værdierne ikke sættes direkte ind i SQL-strengen.
        (master_ip, slave_ip, unit_id),
    )