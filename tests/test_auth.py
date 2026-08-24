import sqlite3

from auth import get_user_id_from_token
from database import initialize_database


def test_token_lookup_returns_user_id():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_database(connection)
    user_id = connection.execute("INSERT INTO users DEFAULT VALUES").lastrowid
    connection.execute(
        "INSERT INTO auth_tokens (user_id, token) VALUES (?, ?)",
        (user_id, "test-token"),
    )
    connection.commit()

    assert get_user_id_from_token(connection, "test-token") == user_id
    assert get_user_id_from_token(connection, "missing") is None
