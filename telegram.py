"""Per-user Telegram client management."""

from typing import Callable, Dict, Mapping
import time

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from database import find_telegram_account, get_connection, initialize_database
from session_manager import create_session


LEGACY_API_ID = 34216039
LEGACY_API_HASH = "aeafe65f91b250c95d3a443a4f7dbf06"


def _legacy_api_id() -> int:
    return LEGACY_API_ID


def _database_account_provider(user_id: str) -> Mapping[str, object] | None:
    connection = get_connection()
    try:
        initialize_database(connection)
        return find_telegram_account(connection, user_id)
    finally:
        connection.close()


class TelegramClientManager:
    def __init__(
        self,
        account_provider: Callable[[str], Mapping[str, object] | None]
        | None = None,
    ) -> None:
        self._clients: Dict[str, TelegramClient] = {}
        self._pending: Dict[str, dict[str, object]] = {}
        self._account_provider = account_provider or _database_account_provider

    def _credentials(self, user_id: str) -> tuple[int, str]:
        account = self._account_provider(user_id)
        if not account or account["api_id"] is None or not account["api_hash"]:
            raise RuntimeError("Telegram API credentials are not configured for this user")
        return int(account["api_id"]), str(account["api_hash"])

    def get_client(self, user_id: str | int) -> TelegramClient:
        key = str(user_id)
        if key == "default":
            return self._get_or_create_client(key, None, _legacy_api_id(), LEGACY_API_HASH)
        account = self._account_provider(key)
        if not account:
            raise RuntimeError("Telegram account credentials are not configured for this user")
        return self._get_or_create_client(key, account)

    def _get_or_create_client(
        self,
        user_id: str,
        account: Mapping[str, object] | None,
        api_id: int | None = None,
        api_hash: str | None = None,
    ) -> TelegramClient:
        if account is None:
            client_key = user_id
            session_key = user_id
        else:
            if account["api_id"] is None or not account["api_hash"]:
                raise RuntimeError("Telegram API credentials are not configured for this user")
            api_id, api_hash = int(account["api_id"]), str(account["api_hash"])
            account_id = account["id"] if "id" in account.keys() else user_id
            client_key = f"account:{account_id}"
            session_key = user_id
        if client_key not in self._clients:
            self._clients[client_key] = TelegramClient(
                str(create_session(session_key)), api_id, api_hash
            )
        return self._clients[client_key]

    def get_account_client(self, user_id: str | int, account: Mapping[str, object]) -> TelegramClient:
        return self._get_or_create_client(str(user_id), account)

    async def start(self, user_id: str | int) -> TelegramClient:
        client = self.get_client(user_id)
        # connect() reuses an existing authorized session.  Calling Telethon's
        # start() here would prompt for phone/code when the session is absent.
        await client.connect()
        if not await client.is_user_authorized():
            raise RuntimeError(
                "Telegram session is not authorized; login flow is not implemented"
            )
        return client

    def prepare_login(self, user_id: str | int) -> TelegramClient:
        """Return the isolated client for a future phone/code/2FA flow."""
        return self.get_client(user_id)

    async def request_code(
        self, user_id: str | int, account: Mapping[str, object]
    ) -> bool:
        key = str(user_id)
        client = self.get_account_client(key, account)
        await client.connect()
        if await client.is_user_authorized():
            return True
        sent_code = await client.send_code_request(str(account["phone"]))
        self._pending[key] = {
            "client": client,
            "phone": str(account["phone"]),
            "phone_code_hash": sent_code.phone_code_hash,
            "account_id": int(account["id"]),
            "expires_at": time.monotonic() + float(getattr(sent_code, "timeout", None) or 120),
            "two_factor": False,
        }
        return False

    async def verify_code(self, user_id: str | int, code: str) -> bool:
        pending = self._pending.get(str(user_id))
        if not pending:
            raise RuntimeError("no Telegram login is pending")
        if pending["expires_at"] <= time.monotonic():
            self._pending.pop(str(user_id), None)
            raise RuntimeError("Telegram verification code expired")
        client = pending["client"]
        try:
            await client.sign_in(
                phone=pending["phone"],
                code=code,
                phone_code_hash=pending["phone_code_hash"],
            )
        except SessionPasswordNeededError:
            pending["two_factor"] = True
            return False
        await self._finish_login(str(user_id), pending)
        return True

    async def verify_2fa(self, user_id: str | int, password: str) -> None:
        pending = self._pending.get(str(user_id))
        if not pending:
            raise RuntimeError("no Telegram login is pending")
        if pending["expires_at"] <= time.monotonic():
            self._pending.pop(str(user_id), None)
            raise RuntimeError("Telegram verification expired; request a new code")
        await pending["client"].sign_in(password=password)
        await self._finish_login(str(user_id), pending)

    async def _finish_login(self, user_id: str, pending: Mapping[str, object]) -> None:
        client = pending["client"]
        me = await client.get_me()
        connection = get_connection()
        try:
            initialize_database(connection)
            from database import update_telegram_account_user

            update_telegram_account_user(connection, int(pending["account_id"]), getattr(me, "id", None))
        finally:
            connection.close()
        self._pending.pop(user_id, None)

    def pending_status(self, user_id: str | int) -> tuple[str, int] | None:
        pending = self._pending.get(str(user_id))
        if not pending:
            return None
        remaining = max(0, int(pending["expires_at"] - time.monotonic()))
        if remaining == 0:
            return "expired", 0
        return ("two_factor_required" if pending["two_factor"] else "code_pending", remaining)

    async def disconnect_all(self) -> None:
        for client in self._clients.values():
            if client.is_connected():
                await client.disconnect()


telegram_clients = TelegramClientManager()
