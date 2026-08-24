import sqlite3

import asyncio
from telethon.errors import SessionPasswordNeededError

from database import (
    create_application_user,
    create_telegram_account,
    find_telegram_account_by_phone,
    initialize_database,
)
from telegram import TelegramClientManager


def connection():
    result = sqlite3.connect(":memory:")
    result.row_factory = sqlite3.Row
    initialize_database(result)
    return result


def test_generated_token_is_stored_raw_and_resolves_to_one_user():
    db = connection()
    user_id, token = create_application_user(db)

    assert db.execute("SELECT token FROM auth_tokens").fetchone()[0] == token
    from auth import get_user_id_from_token

    assert get_user_id_from_token(db, token) == user_id
    assert get_user_id_from_token(db, "wrong") is None


def test_phone_lookup_is_owned_by_authenticated_user():
    db = connection()
    first, _ = create_application_user(db)
    second, _ = create_application_user(db)
    create_telegram_account(db, first, "+100", 1, "hash")

    assert find_telegram_account_by_phone(db, first, "+100")["user_id"] == first
    assert find_telegram_account_by_phone(db, second, "+100") is None


def test_existing_session_is_connected_without_login_prompt(monkeypatch, tmp_path):
    calls = []

    class FakeClient:
        def __init__(self, *args):
            calls.append(("init", args))

        async def connect(self):
            calls.append("connect")

        async def is_user_authorized(self):
            calls.append("authorized")
            return True

    monkeypatch.setattr("telegram.TelegramClient", FakeClient)
    monkeypatch.setattr("session_manager.SESSION_DIR", tmp_path)
    manager = TelegramClientManager(lambda _: {"api_id": 1, "api_hash": "hash"})

    async def run():
        first = await manager.start("user-1")
        second = await manager.start("user-1")
        return first, second

    first, second = asyncio.run(run())
    assert first is second
    assert "start" not in calls
    assert calls.count("connect") == 2


def test_connection_flow_sends_code_then_verifies_without_repeating_it(monkeypatch, tmp_path):
    class SentCode:
        phone_code_hash = "hash"

    class FakeClient:
        def __init__(self, *args):
            self.codes_sent = 0
            self.sign_ins = []

        async def connect(self):
            pass

        async def is_user_authorized(self):
            return self.codes_sent > 0 and bool(self.sign_ins)

        async def send_code_request(self, phone):
            self.codes_sent += 1
            return SentCode()

        async def sign_in(self, **kwargs):
            self.sign_ins.append(kwargs)

    monkeypatch.setattr("telegram.TelegramClient", FakeClient)
    monkeypatch.setattr("session_manager.SESSION_DIR", tmp_path)
    manager = TelegramClientManager(lambda _: {"id": 9, "api_id": 1, "api_hash": "hash", "phone": "+100"})

    async def run():
        account = {"id": 9, "api_id": 1, "api_hash": "hash", "phone": "+100"}
        assert await manager.request_code("user-1", account) is False
        monkeypatch.setattr(manager, "_finish_login", lambda *_: asyncio.sleep(0))
        assert await manager.verify_code("user-1", "12345") is True
        assert await manager.request_code("user-1", account) is True

    asyncio.run(run())


def test_connection_flow_supports_two_factor(monkeypatch, tmp_path):
    class SentCode:
        phone_code_hash = "hash"

    class FakeClient:
        def __init__(self, *args):
            self.password_used = False

        async def connect(self):
            pass

        async def is_user_authorized(self):
            return self.password_used

        async def send_code_request(self, phone):
            return SentCode()

        async def sign_in(self, **kwargs):
            if "code" in kwargs:
                raise SessionPasswordNeededError(None)
            self.password_used = True

    monkeypatch.setattr("telegram.TelegramClient", FakeClient)
    monkeypatch.setattr("session_manager.SESSION_DIR", tmp_path)
    manager = TelegramClientManager(lambda _: {"id": 10, "api_id": 1, "api_hash": "hash", "phone": "+100"})
    monkeypatch.setattr(manager, "_finish_login", lambda *_: asyncio.sleep(0))

    async def run():
        account = {"id": 10, "api_id": 1, "api_hash": "hash", "phone": "+100"}
        assert await manager.request_code("user-2", account) is False
        assert await manager.verify_code("user-2", "12345") is False
        await manager.verify_2fa("user-2", "password")

    asyncio.run(run())
