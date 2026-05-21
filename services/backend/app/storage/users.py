from storage.base import execute, query_all, query_one


def get_user_by_username(username):
    if not username:
        return None

    return query_one(
        """
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
        LIMIT 1
        """,
        (username,),
    )


def list_users():
    return query_all(
        """
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


def upsert_user(username, password_hash=None, role="operator", is_active=True):
    if not username:
        return

    execute(
        """
        INSERT INTO app_users
            (username, password_hash, role, is_active, created_at)
        VALUES
            (%s, %s, %s, %s, NOW())
        ON CONFLICT (username)
        DO UPDATE SET
            password_hash = COALESCE(EXCLUDED.password_hash, app_users.password_hash),
            role = EXCLUDED.role,
            is_active = EXCLUDED.is_active
        """,
        (username, password_hash, role, is_active),
    )


def update_last_login(username):
    if not username:
        return

    execute(
        """
        UPDATE app_users
        SET last_login = NOW()
        WHERE username = %s
        """,
        (username,),
    )