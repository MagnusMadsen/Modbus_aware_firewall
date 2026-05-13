"""State tracking package for Modbus observations."""

import threading

from state.manager import ModbusStateManager

_manager: ModbusStateManager | None = None
_manager_lock = threading.Lock()


def init_state_manager() -> ModbusStateManager:
    global _manager

    if _manager is not None:
        return _manager

    with _manager_lock:
        if _manager is None:
            _manager = ModbusStateManager()
            _manager.start()

    return _manager


def process_observation(data: dict) -> None:
    manager = init_state_manager()
    manager.process(data)