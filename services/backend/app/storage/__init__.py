# storage/__init__.py samler storage-funktioner bag én StorageWriter-klasse.
# State-laget bruger ikke storage/devices.py, storage/events.py osv. direkte.
# I stedet får ModbusStateManager én writer via get_writer(), og tracker-klasserne kalder metoder på den.
# Det gør dataflowet mere ensartet: state-laget sender databasearbejde til writeren, og writeren videresender til den rigtige storage-fil.
# Filen indeholder næsten ingen egen logik. Den fungerer primært som et samlet adgangslag til databasefunktionerne.

# Eksempel på flow:
# state/devices.py
# └─ self.writer.upsert_device(ip, mac, role)
#    └─ StorageWriter.upsert_device(...)
#       └─ storage/devices.py upsert_device(...)
#          └─ SQL INSERT/UPDATE i devices-tabellen
#
# Det samme mønster bruges for events, metrics, connections, registers, users, critical_registers og alarm_approvals. 

from storage.connections import upsert_connection
from storage.critical_registers import (
    delete_critical_register,
    get_critical_register,
    list_critical_registers,
    save_critical_register,
)

from storage.alarm_approvals import (
    get_alarm_approval,
    get_approved_alarm_keys,
    list_alarm_approvals,
    save_alarm_approval,
)

from storage.users import (
    get_user_by_username,
    list_users,
    update_last_login,
    upsert_user,
)

from storage.devices import get_device_by_ip, update_device_status, upsert_device
from storage.events import insert_event
from storage.metrics import insert_metrics_bucket
from storage.registers import upsert_register_state


# StorageWriter er et lille wrapper-objekt omkring storage-funktionerne.
# Den holder ikke runtime-state på samme måde som tracker-klasserne i state-laget.
# Formålet er at give manageren og tracker-klasserne ét samlet objekt til databaseadgang.
class StorageWriter:
    # Device-metoder bruges især af state/devices.py.
    # get_device_by_ip() læser fra devices-tabellen, og upsert_device() opretter/opdaterer devices.
    def get_device_by_ip(self, ip):
        return get_device_by_ip(ip) 

    def upsert_device(self, ip, mac=None, role=None):
        return upsert_device(ip, mac, role) 

    # Connection-metoder bruges af state/connections.py til observed_connections-tabellen.
    def upsert_connection(self, master_ip, slave_ip, unit_id=None):
        return upsert_connection(master_ip, slave_ip, unit_id)

    # Register-state bruges af state/registers.py til at gemme seneste kendte registerværdi i modbus_register_state.
    def upsert_register_state(self, slave_ip, unit_id, register_type, register_address, value):
        return upsert_register_state(slave_ip, unit_id, register_type, register_address, value)

    # Event-metoden bruges af flere trackers til at oprette IDS-hændelser i events-tabellen.
    def insert_event(self, *args, **kwargs):
        return insert_event(*args, **kwargs)

    # Metrics-metoden bruges af state/metrics.py til at skrive afsluttede metrics buckets i metrics_bucket.
    def insert_metrics_bucket(self, *args, **kwargs):
        return insert_metrics_bucket(*args, **kwargs)

    # Critical register-metoder bruges både af state/registers.py og API-routes.
    # state/registers.py bruger get_critical_register() til at vurdere om en registerændring er kritisk.
    def get_critical_register(self, *args, **kwargs):
        return get_critical_register(*args, **kwargs)

    def list_critical_registers(self):
        return list_critical_registers()

    def save_critical_register(self, payload):
        return save_critical_register(payload)

    def delete_critical_register(self, register_id):
        return delete_critical_register(register_id)
    
    # Alarm approval-metoder bruges af API-routes/frontend-flowet til at gemme brugerens beslutning på en alarm.
    def save_alarm_approval(self, payload):
        return save_alarm_approval(payload)

    def list_alarm_approvals(self):
        return list_alarm_approvals()

    def get_alarm_approval(self, alarm_key):
        return get_alarm_approval(alarm_key)

    def get_approved_alarm_keys(self):
        return get_approved_alarm_keys()
    
    # User-metoder bruges af API-routes til login og brugeradministration.
    def get_user_by_username(self, username):
        return get_user_by_username(username)

    def list_users(self):
        return list_users()

    def upsert_user(self, username, password_hash=None, role="operator", is_active=True):
        return upsert_user(username, password_hash, role, is_active)

    def update_last_login(self, username):
        return update_last_login(username)


# _writer er én fælles StorageWriter-instans.
# Den gemmer ikke database-data selv, men giver resten af backend ét fast adgangsobjekt til storage-laget.
_writer = StorageWriter()


# get_writer() bruges af ModbusStateManager til at få adgang til storage-laget.
# Manageren sender writeren videre til tracker-klasserne, så de kan skrive/læse database-data uden selv at importere alle storage-filer.
def get_writer():
    return _writer