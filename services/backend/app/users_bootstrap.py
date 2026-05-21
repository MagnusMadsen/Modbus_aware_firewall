import os

from config import read_secret_env
from storage import get_user_by_username, upsert_user


VALID_ROLES = {"admin", "operator", "viewer"}


def bootstrap_default_user():
    username = os.getenv("APP_USERNAME", "").strip()
    role = os.getenv("APP_USER_ROLE", "admin").strip().lower()

    if not username:
        raise RuntimeError("APP_USERNAME is required to bootstrap the first SQL user")

    if role not in VALID_ROLES:
        raise RuntimeError(f"Invalid APP_USER_ROLE: {role}")

    existing_user = get_user_by_username(username)
    if existing_user:
        return

    password_hash = read_secret_env("FRONTEND_PASSWORD_HASH")

    if not password_hash:
        raise RuntimeError("FRONTEND_PASSWORD_HASH is empty")

    upsert_user(
        username=username,
        password_hash=password_hash,
        role=role,
        is_active=True,
    )