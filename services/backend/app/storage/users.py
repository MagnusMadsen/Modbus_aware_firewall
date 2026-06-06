# users.py læser og skriver brugere i app_users-tabellen.
# Data kommer fra API-routes, når backend skal logge en bruger ind, vise brugerlisten, oprette/opdatere en bruger eller gemme last_login.
# Filen arbejder kun med databaseoperationer for brugere og returnerer data tilbage til API-laget.
from storage.base import execute, query_all, query_one


# get_user_by_username() bruges ved login og opslag af én bestemt bruger.
# username kommer fra API-laget, typisk fra login-formularen.
# Funktionen returnerer også password_hash, fordi login-koden skal kunne sammenligne brugerens password med den gemte hash.
def get_user_by_username(username):
    # Uden username kan der ikke laves et meningsfuldt brugeropslag.
    if not username:
        return None
    # query_one() bruges fordi der forventes præcis nul eller én bruger for et username.
    return query_one(
        """
        -- Henter brugerdata for ét username.
        SELECT
            id,
            username,
            password_hash,
            role,
            is_active,
            created_at,
            last_login
        FROM app_users
        WHERE username = %s
        """,
        (username,),
    )


# list_users() bruges af API-routes/frontend til brugeradministration.
# Funktionen returnerer brugerlisten uden password_hash, fordi hashes ikke skal sendes til frontend.
def list_users():
    # query_all() bruges fordi frontend skal have en liste med alle brugere.
    return query_all(
        """
        -- Henter brugere til brugeradministration uden password_hash.
        SELECT
            id,
            username,
            role,
            is_active,
            TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_at,
            TO_CHAR(last_login, 'YYYY-MM-DD HH24:MI:SS') AS last_login
        FROM app_users
        ORDER BY username
        """
    )


# upsert_user() bruges når API-laget opretter eller opdaterer en bruger.
# username er brugerens unikke login-navn.
# password_hash er det hashede password, ikke det rå password.
# role bestemmer brugerens adgangsniveau i backend/frontend.
# is_active bestemmer om brugeren må logge ind.
# INSERT ... ON CONFLICT betyder: opret brugeren hvis username ikke findes, ellers opdater den eksisterende bruger.
def upsert_user(username, password_hash=None, role="operator", is_active=True):
    # Uden username kan brugeren ikke identificeres sikkert.
    if not username:
        return
    # Sender SQL-kommandoen videre til storage/base.py execute(), som åbner connection og kører queryen.
    execute(
        """
        -- Opretter en ny bruger.
        INSERT INTO app_users
            (username, password_hash, role, is_active, created_at)
        VALUES
            (%s, %s, %s, %s, NOW())
        -- Hvis username allerede findes, opdateres brugeren i stedet for at lave en dublet.
        ON CONFLICT (username)
        DO UPDATE SET
            -- Hvis der ikke sendes ny password_hash med, beholdes den gamle hash.
            password_hash = COALESCE(EXCLUDED.password_hash, app_users.password_hash),
            role = EXCLUDED.role,
            is_active = EXCLUDED.is_active
        """,
        # Parametrene bindes separat, så værdierne ikke sættes direkte ind i SQL-strengen.
        (username, password_hash, role, is_active),
    )


# update_last_login() bruges efter et succesfuldt login.
# Funktionen opdaterer last_login på den bruger der netop er logget ind.
def update_last_login(username):
    # Uden username er der ingen bruger at opdatere.
    if not username:
        return
    # Sender UPDATE videre til storage/base.py execute().
    execute(
        """
        -- Gemmer tidspunktet for seneste login.
        UPDATE app_users
        SET last_login = NOW()
        WHERE username = %s
        """,
        (username,),
    )