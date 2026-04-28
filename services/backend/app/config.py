import os
from pathlib import Path


def read_secret_env(name: str, default: str | None = None) -> str:
    file_path = os.getenv(f"{name}_FILE")

    if file_path:
        return Path(file_path).read_text(encoding="utf-8").strip()

    value = os.getenv(name)
    if value:
        return value

    if default is not None:
        return default

    raise RuntimeError(f"Missing required secret or environment variable: {name}")


def get_env(name: str, default: str) -> str:
    return os.getenv(name, default)


def get_int_env(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def get_float_env(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))