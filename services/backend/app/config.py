# config.py er backendens fælles sted til at læse konfiguration.
# Data kommer fra environment variables eller fra secret-filer, typisk sat i Docker/compose.
# Filen sender ikke data videre til databasen og holder ikke runtime-state.
# Andre filer importerer funktionerne herfra, når de skal bruge en konfigurationsværdi.
# read_secret_env() bruges til krævede hemmelige værdier. 
# get_env(), get_int_env() og get_float_env() bruges til almindelige indstillinger, hvor koden har en bevidst default.
import os
from pathlib import Path


# read_secret_env() læser en krævet secret eller token.
# Funktionen bruges til værdier hvor backend ikke må starte med en tilfældig/default værdi, f.eks. database-password eller API-token.
# Først tjekkes NAME_FILE, f.eks. DB_PASSWORD_FILE.
# Hvis NAME_FILE findes, læses værdien fra filen. Det passer til Docker secrets, hvor hemmelige værdier monteres som filer.
# Hvis NAME_FILE ikke findes, tjekkes NAME direkte som environment variable, f.eks. DB_PASSWORD.
# Hvis hverken fil eller environment variable findes, stoppes backend med RuntimeError.
def read_secret_env(name: str) -> str:
    # Eksempel: name="DB_PASSWORD" betyder at funktionen først leder efter DB_PASSWORD_FILE.
    file_path = os.getenv(f"{name}_FILE")

    # Hvis *_FILE er sat, prioriteres filen over den direkte environment variable.
    if file_path:
        return Path(file_path).read_text(encoding="utf-8").strip()

    # Hvis der ikke findes en secret-fil, prøves den direkte environment variable.
    value = os.getenv(name)
    if value:
        return value

    # Ingen default her: manglende secrets skal opdages ved startup og ikke senere under drift.
    raise RuntimeError(f"Missing required secret or environment variable: {name}")


# get_env() læser en almindelig tekstbaseret konfigurationsværdi.
# Hvis environment variablen ikke findes, bruges default-værdien fra koden.
# Den bruges kun til værdier hvor en default er acceptabel, f.eks. interface-navn eller feature-indstillinger.
def get_env(name: str, default: str) -> str:
    return os.getenv(name, default)


# get_int_env() læser en konfigurationsværdi der skal være et heltal.
# Hvis environment variablen mangler, bruges default-værdien.
# Hvis værdien findes men ikke kan konverteres til int, stoppes backend med en tydelig fejl.
# Det gør konfigurationsfejl nemmere at finde ved startup i stedet for senere i programflowet.
def get_int_env(name: str, default: int) -> int:
    # os.getenv() returnerer tekst, derfor konverteres default også til tekst her.
    value = os.getenv(name, str(default))
    try:
        # Konverterer environment-værdien til int, så resten af koden får den rigtige datatype.
        return int(value)
    except ValueError as exc:
        # RuntimeError gør fejlen forståelig: hvilken variabel er forkert, og hvilken værdi blev læst.
        raise RuntimeError(f"{name} must be an integer, got: {value}") from exc


# get_float_env() læser en konfigurationsværdi der skal være et decimaltal.
# Hvis environment variablen mangler, bruges default-værdien.
# Bruges til grænseværdier hvor decimaler kan give mening, f.eks. latency eller timeout.
# Hvis værdien findes men ikke kan konverteres til float, stoppes backend med en tydelig fejl.
def get_float_env(name: str, default: float) -> float:
    # os.getenv() returnerer tekst, derfor konverteres default også til tekst her.
    value = os.getenv(name, str(default))
    try:
        # Konverterer environment-værdien til float, så resten af koden får den rigtige datatype.
        return float(value)
    except ValueError as exc:
        # RuntimeError gør fejlen forståelig: hvilken variabel er forkert, og hvilken værdi blev læst.
        raise RuntimeError(f"{name} must be a float, got: {value}") from exc
    

