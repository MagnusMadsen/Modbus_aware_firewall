# auth.py beskytter backend API-routes med en delt API-token.
# Tokenen læses fra BACKEND_API_TOKEN via read_secret_env(), så den skal findes som env variable eller secret-fil.
# Frontend skal sende samme token i HTTP-headeren X-API-Token.
# Hvis tokenen mangler eller er forkert, returnerer backend 401 unauthorized.
import hmac
from functools import wraps

from flask import jsonify, request

from config import read_secret_env

# BACKEND_API_TOKEN læses én gang når filen importeres.
# Hvis tokenen ikke findes, stopper backend med en tydelig fejl fra read_secret_env().
BACKEND_API_TOKEN = read_secret_env("BACKEND_API_TOKEN")


# require_api_token() er en decorator til Flask-routes.
# En route der bruger denne decorator kræver en gyldig X-API-Token header.
# @wraps(view_func) bevarer navnet og metadata fra den oprindelige route-funktion.
# hmac.compare_digest() bruges til token-sammenligning, så sammenligningen ikke afhænger af hvor mange tegn der matcher.
def require_api_token(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        provided_token = request.headers.get("X-API-Token", "")

        if not hmac.compare_digest(provided_token, BACKEND_API_TOKEN):
            return jsonify({"error": "unauthorized"}), 401

        return view_func(*args, **kwargs)

    return wrapper