# registers.py skriver seneste kendte Modbus-registerværdi til modbus_register_state-tabellen.
# Data kommer fra state/registers.py gennem StorageWriter.upsert_register_state().
# Den får allerede færdige værdier: slave_ip, unit_id, register_type, register_address og value.
# Formålet er kun at gemme registerets aktuelle værdi, last_seen og write_count i databasen.
from storage.base import execute


 # upsert_register_state() opretter eller opdaterer én register-state-række.
 # Funktionen spørger ikke selv efter registerdata. Den modtager værdierne som parametre fra StorageWriter.upsert_register_state().
 # slave_ip kommer fra Modbus write requestens dst_ip, altså den slave/PLC der skrives til.
 # unit_id kommer fra MBAP-headeren.
 # register_type og register_address kommer fra packet_parser/request.py.
 # value kommer fra requestens write-værdier, som state/registers.py har pakket ud.
 # Funktionen laver kun databasearbejdet: INSERT hvis registeret ikke findes, UPDATE hvis registeret allerede findes.
def upsert_register_state(slave_ip, unit_id, register_type, register_address, value):
    # Hvis et af nøglefelterne mangler, kan registeret ikke identificeres sikkert.
    # value må godt være 0, derfor tjekkes value ikke med samme None-check her.
    if slave_ip is None or unit_id is None or register_type is None or register_address is None:
        return

    # På dette tidspunkt er værdierne allerede fundet og vurderet af parser/state-laget.
    # Denne funktion bruger dem kun som SQL-parametre.
    # Sender SQL-kommandoen videre til storage/base.py execute(), som åbner connection og kører queryen.
    execute(
        """
        -- Opretter register-state første gang registeret ses.
        INSERT INTO modbus_register_state
            (slave_ip, unit_id, register_type, register_address, last_value, first_seen, last_seen, write_count)
        VALUES
            (%s, %s, %s, %s, %s, NOW(), NOW(), 1)
        -- Hvis samme register allerede findes, opdateres rækken i stedet for at lave en dublet.
        ON CONFLICT (slave_ip, unit_id, register_type, register_address)
        DO UPDATE SET
            -- EXCLUDED.last_value er den nye værdi fra INSERT-forsøget.
            last_value = EXCLUDED.last_value,
            last_seen = NOW(),
            -- write_count tælles op hver gang backend ser et write til samme register.
            write_count = modbus_register_state.write_count + 1
        """,
        # Parametrene bindes separat, så værdierne ikke sættes direkte ind i SQL-strengen.
        # value gemmes som tekst, fordi coils og registers kan have forskellige værdiformater.
        (slave_ip, unit_id, register_type, register_address, str(value)),
    )

    