# Formål: 

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


class StorageWriter:
    def get_device_by_ip(self, ip):
        return get_device_by_ip(ip)

    def upsert_device(self, ip, mac=None, role=None):
        return upsert_device(ip, mac, role)

    def upsert_connection(self, master_ip, slave_ip, unit_id=None):
        return upsert_connection(master_ip, slave_ip, unit_id)

    def upsert_register_state(self, slave_ip, unit_id, register_type, register_address, value):
        return upsert_register_state(slave_ip, unit_id, register_type, register_address, value)

    def insert_event(self, *args, **kwargs):
        return insert_event(*args, **kwargs)

    def insert_metrics_bucket(self, *args, **kwargs):
        return insert_metrics_bucket(*args, **kwargs)

    def get_critical_register(self, *args, **kwargs):
        return get_critical_register(*args, **kwargs)

    def list_critical_registers(self):
        return list_critical_registers()

    def save_critical_register(self, payload):
        return save_critical_register(payload)

    def delete_critical_register(self, register_id):
        return delete_critical_register(register_id)
    
    def save_alarm_approval(self, payload):
        return save_alarm_approval(payload)

    def list_alarm_approvals(self):
        return list_alarm_approvals()

    def get_alarm_approval(self, alarm_key):
        return get_alarm_approval(alarm_key)

    def get_approved_alarm_keys(self):
        return get_approved_alarm_keys()
    
    def get_user_by_username(self, username):
        return get_user_by_username(username)

    def list_users(self):
        return list_users()

    def upsert_user(self, username, password_hash=None, role="operator", is_active=True):
        return upsert_user(username, password_hash, role, is_active)

    def update_last_login(self, username):
        return update_last_login(username)


_writer = StorageWriter()


def get_writer():
    return _writer