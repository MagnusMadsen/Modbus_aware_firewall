# devices.py er storage-laget for devices-tabellen.
# Filen indeholder kun databasefunktioner: hent device, opret/opdater device og ændr status.
# Selve beslutningen om hvornår en IP/MAC er set sker i state/devices.py.
# Denne fil står kun for at skrive/læse data i PostgreSQL.

from storage.base import execute, query_one


# get_device_by_ip() henter én enhed ud fra IP-adressen.
# Bruges når state-laget skal vide om en IP allerede findes i devices-tabellen.
# LIMIT 1 bruges fordi ip er UNIQUE i databasen, så der kan maksimalt være én rigtig række.
# Funktionen returnerer None, hvis IP mangler eller ikke findes.
def get_device_by_ip(ip):
    if not ip:
        return None

    return query_one(
        """
        SELECT
            id,
            ip::text AS ip,
            mac,
            role,
            status,
            first_seen,
            last_seen
        FROM devices
        WHERE ip = %s
        LIMIT 1 
        """,
        (ip,),
    )


# upsert_device() opretter eller opdaterer en enhed i devices-tabellen.
# INSERT bruges første gang en IP ses.
# ON CONFLICT (ip) bruges når IP'en allerede findes, så samme device-række opdateres i stedet for at lave dubletter.
# COALESCE gør at en ny NULL-værdi ikke overskriver en kendt MAC eller rolle.
# 0.0.0.0 og 255.255.255.255 ignoreres, fordi de ikke er normale enhedsadresser.
def upsert_device(ip, mac=None, role=None):
    if not ip or ip in ("0.0.0.0", "255.255.255.255"):
        return

    execute(
        """
        INSERT INTO devices (ip, mac, role, first_seen, last_seen)
        VALUES (%s, %s, %s, NOW(), NOW())
        ON CONFLICT (ip)
        DO UPDATE SET
            mac = COALESCE(EXCLUDED.mac, devices.mac),
            role = COALESCE(EXCLUDED.role, devices.role),
            last_seen = NOW()
        """,
        (ip, mac, role),
    )


# update_device_status() ændrer brugerstatus på en device-række.
# Bruges når frontend godkender, blokerer eller ignorerer en ukendt enhed.
# Funktionen returnerer True hvis en række faktisk blev ændret, ellers False.
def update_device_status(device_id: int, status: str) -> bool:
    affected_rows = execute(
        """
        UPDATE devices
        SET status = %s
        WHERE id = %s
        """,
        (status, device_id),
    )
    return affected_rows > 0