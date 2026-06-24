# main.py er frontendens Flask-applikation.
# Filen viser login-siden, dashboardet og de frontend-API endpoints som browseren kalder.
# Frontenden taler ikke direkte med PostgreSQL.
# Frontenden henter og sender data gennem backendens API med requests.get()/requests.post()/requests.delete().
# Backend taler derefter med storage-laget og PostgreSQL.

# Overordnet dataflow:
# Browser
# └─ frontend Flask route i denne fil
#    └─ requests.* til backend API med X-API-Token
#       └─ backend API-route
#          └─ backend storage/state/dashboard-lag
#             └─ PostgreSQL eller live runtime-state
#
# Eksempel ved dashboard:
# Browser GET /
# └─ index()
#    └─ get_dashboard_data()
#       ├─ GET backend /api/dashboard
#       │  └─ backend henter metrics, events, connections, ports og alarm approvals
#       └─ GET backend /api/devices
#          └─ backend henter devices fra databasen
#
# Eksempel ved alarm approval:
# Browser POST /api/alarm-approvals
# └─ save_alarm_approval()
#    └─ POST backend /api/alarm-approvals
#       └─ backend gemmer approval igennem alarm_approvals og opdaterer events.status

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from datetime import datetime, timedelta
from functools import wraps

import os
import requests


# read_secret() læser frontendens secrets fra Docker secrets-mappen.
# Funktionen bruges til frontend_secret_key og backend_api_token.
# Hvis en secret mangler eller er tom, stoppes frontenden med en tydelig fejl.
def read_secret(secret_name: str) -> str:
    # Docker secrets monteres som filer under /run/secrets/.
    path = f"/run/secrets/{secret_name}"
    try:
        with open(path, "r", encoding="utf-8") as f:
            value = f.read().strip()
    except FileNotFoundError as exc:
        raise RuntimeError(f"Missing required secret: {secret_name}") from exc

    if not value:
        raise RuntimeError(f"Secret is empty: {secret_name}")

    return value


# Opretter frontendens Flask-applikation.
# Denne Flask-app serverer HTML-dashboardet og fungerer som proxy mellem browseren og backend API'et.
app = Flask(__name__)

# Redis bruges af Flask-Limiter til rate limiting.
# Det begrænser især login-forsøg, så brute force mod login-siden bliver sværere.
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")

# Limiter kobles på Flask-applikationen og bruger klientens IP-adresse til rate limiting.
# Vi gemmer kun rate limit state i Redis, så flere frontend-instanser kan dele samme limiter. !!!!!!!
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri=f"redis://{REDIS_HOST}:{REDIS_PORT}/0",
)

# Flask secret_key bruges til at signere session-cookies.
# Den skal være hemmelig, fordi sessionen bruges til at huske om brugeren er logget ind.
app.secret_key = read_secret("frontend_secret_key")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("APP_ENV") == "production",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=1),
)

# BACKEND_API_TOKEN bruges når frontenden kalder backend API'et.
# Token sendes i X-API-Token-headeren, så backend kan afvise kald der ikke kommer fra den forventede frontend.
# API_BASE_URL fortæller frontenden hvor backendens API ligger.
BACKEND_API_TOKEN = read_secret("backend_api_token")
API_BASE_URL = os.getenv("API_BASE_URL", "http://host.docker.internal:8000")

# backend_headers() samler de headers frontenden skal sende til backend.
# Alle backend-kald fra denne fil bruger X-API-Token.
def backend_headers() -> dict:
    return {
        "X-API-Token": BACKEND_API_TOKEN
    }

# backend_login() sender brugerens login-data videre til backendens /api/auth/login.
# Frontenden validerer ikke passwordet selv.
# Backend slår brugeren op i app_users-tabellen og sammenligner passwordet med password_hash.
def backend_login(username: str, password: str):
    response = requests.post(
        f"{API_BASE_URL}/api/auth/login",
        headers=backend_headers(),
        json={
            "username": username,
            "password": password,
        },
        timeout=5,
    )

    return response


# login_required() beskytter frontend-routes.
# Hvis sessionen ikke siger at brugeren er authenticated, sendes brugeren tilbage til /login.
def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        # session er frontendens login-state i brugerens cookie.
        if not session.get("authenticated"):
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)
    return wrapped_view


# get_dashboard_data() bygger det samlede dataobjekt som dashboard.html bruger.
# Funktionen starter med fallback-data, så dashboardet stadig kan rendere hvis backend er nede.
# Derefter hentes live/dashboard-data fra backendens API.
# Frontenden læser ikke databasen direkte; alt databaseindhold kommer via backend API'et.
def get_dashboard_data():
    # Fallback-strukturen matcher det format dashboard.html forventer.
    data = {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "sensor": {
            "status": "Online",
            "mode": "Passive monitoring",
            "interface": "eth0",
        },
        "arp_monitor": {
            "status": "Normal",
            "summary": "No ARP alerts yet",
            "gateway_ip": "-",
            "gateway_expected_mac": "-",
            "gateway_seen_mac": "-",
            "critical_pairs": [],
            "events": [],
        },
        "summary": [
            {"label": "Online devices", "value": 0, "note": "Observed in SQL"},
            {"label": "Packets last 60s", "value": 0, "note": "Live capture"},
            {"label": "ARP last 60s", "value": 0, "note": "Live capture"},
        ],
        "combined_series": [],
        "chart_events": [],
        "combined_note": "Traffic and latency data will appear here when available.",
        "connections": [],
        "ports": [],
        "events": [],
        "devices": [],
        "approved_alarm_keys": [],
        "alarm_approvals": [],
    }

    try:
        # Henter hoveddashboard-data fra backend.
        # Backend samler her metrics, events, connections, ports, ARP-status og alarm approvals.
        dashboard_resp = requests.get(
                f"{API_BASE_URL}/api/dashboard",
                headers=backend_headers(),
                timeout=5,
            )
        dashboard_resp.raise_for_status()
        dashboard_json = dashboard_resp.json()

        # Henter devices separat fra backendens /api/devices endpoint.
        # Backend henter devices fra PostgreSQL via storage-laget.
        devices_resp = requests.get(
                f"{API_BASE_URL}/api/devices",
                headers=backend_headers(),
                timeout=5,
            )
        devices_resp.raise_for_status()
        devices_json = devices_resp.json()

        # Kopierer backendens svar ind i frontendens dataobjekt, men beholder fallback-værdier hvis felter mangler.
        data["generated_at"] = dashboard_json.get("generated_at", data["generated_at"])
        data["sensor"] = dashboard_json.get("sensor", data["sensor"])
        data["summary"] = dashboard_json.get("summary", data["summary"])
        data["combined_series"] = dashboard_json.get("combined_series", data["combined_series"])
        data["chart_events"] = dashboard_json.get("chart_events", data["chart_events"])
        data["combined_note"] = dashboard_json.get("combined_note", data["combined_note"])
        data["arp_monitor"] = dashboard_json.get("arp_monitor", data["arp_monitor"])
        data["connections"] = dashboard_json.get("connections", data["connections"])
        data["ports"] = dashboard_json.get("ports", data["ports"])
        data["events"] = dashboard_json.get("events", data["events"])
        data["approved_alarm_keys"] = dashboard_json.get("approved_alarm_keys", data["approved_alarm_keys"])
        data["alarm_approvals"] = dashboard_json.get("alarm_approvals", data["alarm_approvals"])
        data["devices"] = devices_json

    except Exception as exc:
        # Hvis backend ikke svarer, vises dashboardet stadig med en fejltekst i summary-feltet.
        data["summary"] = [
            {"label": "Online devices", "value": 0, "note": str(exc)},
            {"label": "Packets last 60s", "value": 0, "note": "No backend data"},
            {"label": "ARP last 60s", "value": 0, "note": "No backend data"},
        ]

    return data


# /login viser login-formularen og håndterer login-submit.
# Login-forsøg rate-limites med 3 forsøg pr. minut.
@app.route("/login", methods=["GET", "POST"])
@limiter.limit("30 per minute")
def login():
    # Hvis brugeren allerede er logget ind i frontend-sessionen, sendes brugeren til dashboardet.
    if session.get("authenticated"):
        return redirect(url_for("index"))

    if request.method == "POST":
        # Login-formularens input læses fra browserens POST-request.
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        try:
            # Sender login videre til backend, som validerer mod app_users i databasen.
            response = backend_login(username, password)

            if response.status_code == 200:
                result = response.json()
                user = result.get("user", {})

                # Ved succes gemmes kun nødvendig login-state i frontend-sessionen.
                session.clear()
                session["authenticated"] = True
                session["username"] = user.get("username", username)
                session["role"] = user.get("role", "operator")
                session.permanent = True

                return redirect(url_for("index"))

        except Exception:
            pass

        # Brugeren får samme fejlbesked uanset årsag, så login ikke afslører om username findes.
        flash("Invalid username or password", "error")

    return render_template("login.html")


# /logout nulstiller frontend-sessionen og sender brugeren tilbage til login.
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# / er dashboard-siden.
# Siden kræver frontend-login og renderer dashboard.html med data fra get_dashboard_data().
@app.route("/")
@login_required
def index():
    return render_template(
        "dashboard.html",
        data=get_dashboard_data(),
        username=session.get("username")
    )


# /api/live-dashboard kaldes af browserens JavaScript for at opdatere dashboardet uden fuld sidegenindlæsning.
# Endpointet returnerer samme dataformat som dashboardets første render.
@app.route("/api/live-dashboard")
@login_required
def live_dashboard():
    return jsonify(get_dashboard_data())


# Frontend-proxy for alarm approvals.
# Browseren kalder frontendens endpoint, og frontenden videresender til backendens /api/alarm-approvals.
@app.get("/api/alarm-approvals")
@login_required
def alarm_approvals():
    try:
        response = requests.get(
            f"{API_BASE_URL}/api/alarm-approvals",
            headers=backend_headers(),
            timeout=5,
        )
        return jsonify(response.json()), response.status_code
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502


# Gemmer brugerens alarmbeslutning gennem backend API'et.
# handled_by tilføjes fra frontend-sessionen, så backend kan gemme hvem der håndterede alarmen.
@app.post("/api/alarm-approvals")
@login_required
def save_alarm_approval():
    payload = request.get_json(silent=True) or {}
    payload["handled_by"] = session.get("username", "unknown")

    try:
        response = requests.post(
            f"{API_BASE_URL}/api/alarm-approvals",
            headers=backend_headers(),
            json=payload,
            timeout=5,
        )
        return jsonify(response.json()), response.status_code
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502


# Frontend-proxy for critical_registers.
# Backend henter reglerne fra critical_registers-tabellen.
@app.get("/api/critical-registers")
@login_required
def critical_registers():
    try:
        response = requests.get(
            f"{API_BASE_URL}/api/critical-registers",
            headers=backend_headers(),
            timeout=5,
        )
        return jsonify(response.json()), response.status_code
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502


# Sender en ny eller ændret critical register-regel videre til backend.
# Backend validerer payload og gemmer reglen i critical_registers-tabellen.
@app.post("/api/critical-registers")
@login_required
def save_critical_register():
    try:
        response = requests.post(
            f"{API_BASE_URL}/api/critical-registers",
            headers=backend_headers(),
            json=request.get_json(silent=True) or {},
            timeout=5,
        )
        return jsonify(response.json()), response.status_code
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502


# Sender sletning af en critical register-regel videre til backend.
# register_id er database-id'et for reglen i critical_registers.
@app.delete("/api/critical-registers/<int:register_id>")
@login_required
def delete_critical_register(register_id):
    try:
        response = requests.delete(
            f"{API_BASE_URL}/api/critical-registers/{register_id}",
            headers=backend_headers(),
            timeout=5,
        )
        return jsonify(response.json()), response.status_code
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502


# Device action endpoints er frontend-proxies til backend.
# Brugeren kan approve, block eller ignore en device fra dashboardet.
@app.post("/api/devices/<int:device_id>/approve")
@login_required
def approve_device(device_id):
    return proxy_device_action(device_id, "approve")


@app.post("/api/devices/<int:device_id>/block")
@login_required
def block_device(device_id):
    return proxy_device_action(device_id, "block")


@app.post("/api/devices/<int:device_id>/ignore")
@login_required
def ignore_device(device_id):
    return proxy_device_action(device_id, "ignore")


# proxy_device_action() sender device-beslutningen videre til backendens device endpoint.
# device_id er id'et fra devices-tabellen.
# handled_by tilføjes fra frontend-sessionen, så backend kan gemme hvem der traf beslutningen.
def proxy_device_action(device_id: int, action: str):
    payload = request.get_json(silent=True) or {}
    payload["handled_by"] = session.get("username", "unknown")

    try:
        response = requests.post(
            f"{API_BASE_URL}/api/devices/{device_id}/{action}",
            headers=backend_headers(),
            json=payload,
            timeout=5,
        )
        return jsonify(response.json()), response.status_code
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502


# Starter frontendens Flask-server, når filen køres direkte.
# I Docker vil denne service normalt køre på port 5000.
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
