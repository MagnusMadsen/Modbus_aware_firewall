import hmac
from functools import wraps

from flask import jsonify, request

from config import read_secret_env

BACKEND_API_TOKEN = read_secret_env("BACKEND_API_TOKEN")


def require_api_token(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        provided_token = request.headers.get("X-API-Token", "")

        if not hmac.compare_digest(provided_token, BACKEND_API_TOKEN):
            return jsonify({"error": "unauthorized"}), 401

        return view_func(*args, **kwargs)

    return wrapper