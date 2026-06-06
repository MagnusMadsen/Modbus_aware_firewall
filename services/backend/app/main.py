# main.py er backendens startpunkt.
# Filen opretter Flask-applikationen, registrerer API-routes og starter de vigtigste backend-processer.
# Når filen køres direkte, klargør den databasen, starter state-manageren og starter packet capture.
# Til sidst startes Flask-serveren på port 8000, så frontend kan kalde backendens API-endpoints.

# Startup-flow:
# main.py
# ├─ apply_schema()
# │  └─ kører 01_schema.sql mod PostgreSQL og opretter/opdaterer schema
# ├─ verify_schema()
# │  └─ tjekker at de nødvendige tabeller findes
# ├─ init_state_manager()
# │  └─ opretter den fælles ModbusStateManager i RAM
# ├─ start_capture_thread()
# │  └─ starter packet capture i en baggrundstråd
# └─ app.run(...)
#    └─ starter Flask API-serveren

from flask import Flask

from api import api_bp
from capture import start_capture_thread
from db import apply_schema, verify_schema
from state import init_state_manager


# Flask(__name__) opretter selve webserver-applikationen.
# __name__ fortæller Flask hvilken Python-modulfil applikationen starter fra.
app = Flask(__name__)

# api_bp kommer fra api-mappen.
# register_blueprint() kobler backendens API-routes på Flask-applikationen.
# Det er derfor endpoints som /api/dashboard og /api/devices kan svare på HTTP-kald fra frontend.
app.register_blueprint(api_bp)


# Denne blok køres kun når main.py startes direkte som program.
# Den køres ikke hvis filen kun importeres af en anden Python-fil.
if __name__ == "__main__":
    # Kører schema/migrationer mod PostgreSQL før backend begynder at bruge databasen.
    apply_schema()
    # Stopper backend tidligt hvis de nødvendige tabeller stadig mangler.
    verify_schema()
    # Opretter den fælles state-manager, som holder runtime-state for devices, connections, requests, registers og metrics.
    init_state_manager()
    # Starter packet capture i baggrunden, så Flask-serveren stadig kan svare på API-kald samtidig.
    start_capture_thread()
    # Starter Flask-serveren.
    # host="0.0.0.0" gør API'et tilgængeligt uden for containeren.
    # debug=False bruges fordi backend kører som en egentlig service og ikke som udviklings-debugserver.
    app.run(host="0.0.0.0", port=8000, debug=False)
