import asyncio
import sqlite3

from database import create_application_user, initialize_database
from main import PhoneRequest, register_telegram_user


def test_registration_creates_user_token_and_starts_code_flow(monkeypatch):
    database = sqlite3.connect(":memory:")
    database.row_factory = sqlite3.Row
    initialize_database(database)

    class ConnectionWithoutClose:
        def __getattr__(self, name):
            return getattr(database, name)

        def close(self):
            pass

    class FakeClients:
        def __init__(self):
            self.account = None

        async def request_code(self, user_id, account):
            self.account = (user_id, account)
            return False

        def pending_status(self, user_id):
            return ("code_pending", 90)

    clients = FakeClients()
    monkeypatch.setattr("main.get_connection", lambda: ConnectionWithoutClose())
    monkeypatch.setattr("main.telegram_clients", clients)

    response = asyncio.run(register_telegram_user(PhoneRequest(phone="+100")))

    assert response["status"] == "code_sent"
    assert response["expires_in"] == 90
    assert response["api_token"]
    row = database.execute("SELECT user_id, token FROM auth_tokens").fetchone()
    assert row["token"] == response["api_token"]
    assert clients.account[1]["phone"] == "+100"


def test_application_user_token_is_unique_and_raw():
    database = sqlite3.connect(":memory:")
    database.row_factory = sqlite3.Row
    initialize_database(database)

    first_id, first_token = create_application_user(database)
    second_id, second_token = create_application_user(database)

    assert first_id != second_id
    assert first_token != second_token
    assert [row[0] for row in database.execute("SELECT token FROM auth_tokens ORDER BY id")] == [
        first_token,
        second_token,
    ]
