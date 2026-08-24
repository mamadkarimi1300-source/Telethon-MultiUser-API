import asyncio
from types import SimpleNamespace

from telethon.errors import UserPrivacyRestrictedError
from telethon.tl.functions.messages import (
    AddChatUserRequest,
    CreateChatRequest,
    ExportChatInviteRequest,
)
from telethon.tl.types import Chat, InputPeerChat, InputPeerUser, User

import main


class FakeGroupClient:
    def __init__(self, *, privacy_ids=(), absent_ids=(), fail_invites=False):
        self.users = {f"user{user_id}": User(user_id, access_hash=user_id) for user_id in range(1, 6)}
        self.group = Chat(123, "Test Group", None, 1, None, 1, creator=True)
        self.privacy_ids = set(privacy_ids)
        self.absent_ids = set(absent_ids)
        self.fail_invites = fail_invites
        self.export_count = 0
        self.export_requests = []
        self.sent_messages = []

    async def get_entity(self, value):
        return self.users[value]

    async def get_input_entity(self, entity):
        return InputPeerUser(entity.id, entity.access_hash)

    async def get_participants(self, _group):
        return [user for user in self.users.values() if user.id not in self.absent_ids]

    async def __call__(self, request):
        if isinstance(request, CreateChatRequest):
            return SimpleNamespace(chats=[self.group])
        if isinstance(request, ExportChatInviteRequest):
            self.export_count += 1
            self.export_requests.append(request)
            return SimpleNamespace(link="https://t.me/+test-only")
        if isinstance(request, AddChatUserRequest) and request.user_id.user_id in self.privacy_ids:
            raise UserPrivacyRestrictedError(None)
        return SimpleNamespace()

    async def send_message(self, entity, text, buttons=None, parse_mode=None):
        if self.fail_invites:
            raise RuntimeError("invite send failed")
        self.sent_messages.append((entity.id, text, buttons, parse_mode))


def run_group(client, users, invite_message=None):
    return asyncio.run(
        main.create_group(
            main.CreateGroupRequest(
                title="Test Group",
                users=users,
                invite_message=invite_message,
            ),
            client,
        )
    )


def test_direct_add_stays_successful_without_invite_message():
    client = FakeGroupClient()
    result = run_group(client, ["user1", "user2"])

    assert result["users"][0]["status"] == "success"
    assert result["users"][1]["status"] == "success"
    assert not client.sent_messages


def test_privacy_and_confirmed_absence_share_one_invite_link():
    client = FakeGroupClient(privacy_ids={2}, absent_ids={3})
    message = "Custom invitation text"
    result = run_group(client, ["user1", "user2", "user3", "user4"], message)

    assert result["users"][0]["status"] == "success"
    assert result["users"][1]["status"] == "invite_sent"
    assert result["users"][2]["status"] == "invite_sent"
    assert result["users"][3]["status"] == "success"
    assert result["success_count"] == 4
    assert result["failed_count"] == 0
    assert client.export_count == 1
    assert isinstance(client.export_requests[0].peer, InputPeerChat)
    assert client.export_requests[0].peer.chat_id == client.group.id
    assert [sent[1] for sent in client.sent_messages] == [
        f"{message}\n\nhttps://t.me/+test-only",
    ] * 2
    assert all(sent[1] != message for sent in client.sent_messages)
    assert all(sent[2] is None and sent[3] is None for sent in client.sent_messages)


def test_confirmed_absence_without_message_is_not_added():
    client = FakeGroupClient(absent_ids={2})
    result = run_group(client, ["user1", "user2"])

    assert result["users"][1]["status"] == "not_added"
    assert result["failed_count"] == 1
    assert client.export_count == 0
    assert not client.sent_messages


def test_invite_send_failure_is_reported_per_user():
    client = FakeGroupClient(privacy_ids={2}, fail_invites=True)
    result = run_group(client, ["user1", "user2"], "Custom invitation text")

    assert result["group_id"] == 123
    assert result["users"][1]["status"] == "invite_failed"
    assert result["users"][1]["invite_message_sent"] is False
    assert result["users"][1]["error_code"] == "INVITE_MESSAGE_SEND_FAILED"


def test_empty_invite_message_does_not_send_invite():
    client = FakeGroupClient(privacy_ids={2})
    result = run_group(client, ["user1", "user2"], "")

    assert result["users"][1]["status"] == "not_added"
    assert client.export_count == 0
    assert not client.sent_messages
