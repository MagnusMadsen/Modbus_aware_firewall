# config.py læser konfiguration fra environment variabler og secret-filer.
# read_secret_env() bruges til værdier der skal findes, f.eks. DB_PASSWORD, BACKEND_API_TOKEN, FRONTEND_PASSWORD_HASH og SNMP_COMMUNITY.
# get_env(), get_int_env() og get_float_env() bruges til almindelige konfigurationsværdier med en bevidst default.
# Filen ændrer ikke konfigurationen. Den læser kun værdier og stopper med en tydelig fejl, hvis en krævet værdi mangler eller har forkert type.
import os
from pathlib import Path


# read_secret_env() læser en krævet værdi, som enten ligger direkte i en environment variable eller i en fil.
# Funktionen tjekker først NAME_FILE, f.eks. DB_PASSWORD_FILE.
# Hvis NAME_FILE er sat, læses værdien fra den filsti.
# Hvis NAME_FILE ikke er sat, læses værdien fra NAME, f.eks. DB_PASSWORD.
# Hvis ingen af dem findes, stoppes backend. Der er ingen default, fordi funktionen bruges til krævede secrets/tokens.
def read_secret_env(name: str) -> str:
    file_path = os.getenv(f"{name}_FILE")

    if file_path:
        return Path(file_path).read_text(encoding="utf-8").strip()

    value = os.getenv(name)
    if value:
        return value

    raise RuntimeError(f"Missing required secret or environment variable: {name}")


# get_env() læser en almindelig environment variable som tekst.
# Hvis variablen ikke findes, bruges default-værdien.
def get_env(name: str, default: str) -> str:
    return os.getenv(name, default)


# get_int_env() læser en environment variable og konverterer den til int.
# Bruges til konfiguration der skal være et heltal, f.eks. intervaller eller grænseværdier.
# Hvis værdien ikke kan konverteres til int, gives en tydelig fejl i stedet for at fejlen opstår senere.
def get_int_env(name: str, default: int) -> int:
    value = os.getenv(name, str(default))
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer, got: {value}") from exc


# get_float_env() læser en environment variable og konverterer den til float.
# Bruges til konfiguration med kommatal, f.eks. timeout eller latency thresholds.
# Hvis værdien ikke kan konverteres til float, stoppes backend med en forklarende fejl.
def get_float_env(name: str, default: float) -> float:
    value = os.getenv(name, str(default))
    try:
        return float(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a float, got: {value}") from exc
    

