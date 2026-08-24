"""Secret-key helpers for the single-token application user model."""

import sqlite3

from database import find_user_id_by_token


def get_user_id_from_token(
    connection: sqlite3.Connection, token: str | None
) -> int | None:
    """Look up a plain-text secret key without exposing it."""
    if not token:
        return None
    return find_user_id_by_token(connection, token)
