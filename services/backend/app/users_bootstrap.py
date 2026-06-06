# users_bootstrap.py er et standalone setup-script til at oprette den første bruger i app_users-tabellen.
# Scriptet køres manuelt ved første opsætning af en tom database, eller hvis app_users-tabellen er blevet nulstillet.
# Data kommer fra environment variables og secret-filer:
# APP_USERNAME bestemmer brugernavnet.
# APP_USER_ROLE bestemmer rollen, standard er admin.
# FRONTEND_PASSWORD_HASH indeholder det hashede password.
# Funktionen opretter kun brugeren hvis den ikke allerede findes i databasen.
# Hvis brugeren allerede findes, ændres password og rolle ikke.

import os

from config import read_secret_env
from storage import get_user_by_username, upsert_user


# Kun admin og operator er gyldige roller.
VALID_ROLES = {"admin", "operator"}


# bootstrap_default_user() er hovedfunktionen i dette setup-script.
# Den skal kaldes manuelt, når der skal oprettes en første bruger i en tom database.
# Funktionen læser konfiguration, validerer rolle, tjekker om brugeren findes, og opretter brugeren hvis den mangler.
# Hvis brugeren allerede findes, returnerer funktionen uden at ændre password eller rolle.
def bootstrap_default_user():
    # APP_USERNAME læses fra environment variables.
    # strip() fjerner mellemrum før/efter navnet, så " admin " bliver til "admin".
    username = os.getenv("APP_USERNAME", "").strip()
    # APP_USER_ROLE bestemmer brugerens rolle.
    # Hvis variablen ikke er sat, bruges admin som standard.
    # lower() gør at f.eks. "Admin" og "ADMIN" behandles som "admin".
    role = os.getenv("APP_USER_ROLE", "admin").strip().lower()

    # Backend må ikke starte uden et bootstrap-brugernavn.
    # Ellers kan systemet ende uden en bruger man kan logge ind med.
    if not username:
        raise RuntimeError("APP_USERNAME is required to bootstrap the first SQL user")

    # Rollen valideres tidligt, så en forkert APP_USER_ROLE opdages ved startup.
    if role not in VALID_ROLES:
        raise RuntimeError(f"Invalid APP_USER_ROLE: {role}")

    # Tjekker i app_users-tabellen om bootstrap-brugeren allerede findes.
    existing_user = get_user_by_username(username)
    # Hvis brugeren allerede findes, skal password og rolle ikke overskrives ved hver startup.
    if existing_user:
        return

    # Password læses som hash, ikke som råt password.
    # read_secret_env() kræver at værdien findes enten som secret-fil eller environment variable.
    password_hash = read_secret_env("FRONTEND_PASSWORD_HASH")

    # En tom password_hash er en konfigurationsfejl og skal stoppe startup.
    if not password_hash:
        raise RuntimeError("FRONTEND_PASSWORD_HASH is empty")

    # Opretter bootstrap-brugeren i app_users-tabellen via storage-laget.
    # is_active=True betyder at brugeren kan logge ind med det samme.
    upsert_user(
        username=username,
        password_hash=password_hash,
        role=role,
        is_active=True,
    )


# Gør filen mulig at køre direkte som setup-script.
# Eksempel inde i backend-containeren:
# python app/users_bootstrap.py
if __name__ == "__main__":
    bootstrap_default_user()