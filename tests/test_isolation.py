from session_manager import get_session_path
from telegram import TelegramClientManager


def test_users_have_distinct_external_sessions():
    first = get_session_path("user-a")
    second = get_session_path("user-b")

    assert first != second
    assert ".telethon_api" in str(first)
    assert "/opt/Telethon-v2-test" not in str(first)


def test_default_keeps_legacy_session():
    assert str(get_session_path("default")) == "mysession.session"


def test_default_uses_legacy_credentials(monkeypatch):
    clients = []

    class FakeClient:
        def __init__(self, *args):
            clients.append(args)

    monkeypatch.setattr("telegram.TelegramClient", FakeClient)
    client = TelegramClientManager().get_client("default")

    assert client is not None
    assert clients[0][0] == "mysession.session"
    assert clients[0][1:] == (34216039, "aeafe65f91b250c95d3a443a4f7dbf06")


def test_manager_keeps_clients_per_user(monkeypatch, tmp_path):
    clients = []

    class FakeClient:
        def __init__(self, *args):
            clients.append(args)

    monkeypatch.setattr("telegram.TelegramClient", FakeClient)
    monkeypatch.setattr("session_manager.SESSION_DIR", tmp_path)
    accounts = {
        "one": {"api_id": 1, "api_hash": "hash-one"},
        "two": {"api_id": 2, "api_hash": "hash-two"},
    }
    manager = TelegramClientManager(accounts.get)

    assert manager.get_client("one") is manager.get_client("one")
    assert manager.get_client("two") is not manager.get_client("one")
    assert len(clients) == 2
    assert clients[0][0] != clients[1][0]
    assert clients[0][1:] == (1, "hash-one")
    assert clients[1][1:] == (2, "hash-two")


def test_authenticated_user_without_account_credentials_is_rejected():
    manager = TelegramClientManager(lambda user_id: None)

    try:
        manager.get_client("user-without-account")
    except RuntimeError as error:
        assert "credentials" in str(error)
    else:
        raise AssertionError("missing account credentials were accepted")
