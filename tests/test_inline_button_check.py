import asyncio
import json
from types import SimpleNamespace

import main


class InlineCheckClient:
    def __init__(self, message):
        self.message = message

    async def get_entity(self, target):
        return SimpleNamespace(id=504408116, username=target)

    async def get_messages(self, entity, ids):
        return self.message


def run_check(client, message_id=901298):
    return asyncio.run(main.test_inline_button_check("m_k_krimi", message_id, client))


def test_inline_check_handles_telethon_scalar_message_and_reports_button_type():
    button = SimpleNamespace(text="🔗 عضویت در گروه", url="https://t.me/+private")
    message = SimpleNamespace(
        id=901298,
        peer_id=SimpleNamespace(user_id=504408116),
        reply_markup=SimpleNamespace(__class__=SimpleNamespace),
        buttons=[[button]],
    )

    result = run_check(InlineCheckClient(message))

    assert result["success"] is True
    assert result["message_id"] == 901298
    assert result["has_reply_markup"] is True
    assert result["buttons"][0][0]["button_type"] == "SimpleNamespace"
    assert result["buttons"][0][0]["has_url"] is True


def test_inline_check_returns_safe_404_for_missing_message():
    result = run_check(InlineCheckClient(None))

    assert result.status_code == 404
    payload = json.loads(result.body)
    assert payload["success"] is False
    assert payload["error_code"] == "MESSAGE_NOT_FOUND"


def test_inline_check_rejects_message_from_another_target():
    message = SimpleNamespace(
        id=901298,
        peer_id=SimpleNamespace(user_id=999),
        reply_markup=None,
        buttons=None,
    )

    result = run_check(InlineCheckClient(message))

    assert result.status_code == 404
    payload = json.loads(result.body)
    assert payload["error_code"] == "MESSAGE_NOT_IN_TARGET"
