import threading

from state.manager import ModbusStateManager

_manager = None
_manager_lock = threading.Lock()


def init_state_manager():
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = ModbusStateManager()
            _manager.start()
    return _manager


def process_observation(data):
    manager = init_state_manager()
    manager.process(data)
