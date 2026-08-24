import logging
from asyncio import TimeoutError as AsyncTimeoutError

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, HttpUrl, field_validator
from telethon.errors import (
    CodeEmptyError,
    CodeHashInvalidError,
    ChatAdminRequiredError,
    FloodWaitError,
    PhoneCodeEmptyError,
    PhoneCodeHashEmptyError,
    PasswordEmptyError,
    PasswordHashInvalidError,
    PasswordRequiredError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberBannedError,
    PhoneNumberFloodError,
    PhoneNumberInvalidError,
    PeerIdInvalidError,
    RPCError,
    UserAlreadyParticipantError,
    UserChannelsTooMuchError,
    UserNotMutualContactError,
    UserPrivacyRestrictedError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
)
from telethon.tl.functions.contacts import ImportContactsRequest
from telethon.tl.functions.messages import (
    AddChatUserRequest,
    CreateChatRequest,
    ExportChatInviteRequest,
    GetFullChatRequest,
)
from telethon.tl.functions.channels import GetFullChannelRequest, InviteToChannelRequest
from telethon.tl.types import (
    Channel,
    Chat,
    InputPeerChat,
    InputPhoneContact,
    PeerChannel,
    PeerChat,
    PeerUser,
)
from telegram import LEGACY_API_HASH, LEGACY_API_ID, telegram_clients
from auth import get_user_id_from_token
from database import (
    create_application_user,
    create_telegram_account,
    find_telegram_account_by_phone,
    find_telegram_account,
    get_connection,
    initialize_database,
)

app = FastAPI()
logger = logging.getLogger(__name__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://82.115.8.34:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEFAULT_USER_ID = "default"


class PhoneRequest(BaseModel):
    phone: str


class CodeRequest(BaseModel):
    code: str


class PasswordRequest(BaseModel):
    password: str


class CreateGroupRequest(BaseModel):
    title: str
    users: list[str]
    invite_message: str | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must be a non-empty string")
        return value

    @field_validator("users")
    @classmethod
    def validate_users(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("users must be a non-empty array")
        normalized = [user.strip() for user in value]
        if any(not user for user in normalized):
            raise ValueError("users must contain non-empty strings")
        return normalized


def _group_user_error(error: Exception) -> tuple[str, str]:
    if isinstance(error, (UsernameNotOccupiedError, UsernameInvalidError)):
        return "USER_NOT_FOUND", "Telegram user could not be resolved"
    if isinstance(error, PhoneNumberInvalidError):
        return "PHONE_INVALID", "Telegram phone number is invalid"
    if isinstance(error, UserPrivacyRestrictedError):
        return "USER_PRIVACY_RESTRICTED", "The user privacy settings prevent this operation"
    if isinstance(error, UserNotMutualContactError):
        return "USER_NOT_MUTUAL_CONTACT", "The user is not a mutual contact"
    if isinstance(error, PeerIdInvalidError):
        return "PEER_ID_INVALID", "Telegram rejected the supplied peer"
    if isinstance(error, UserChannelsTooMuchError):
        return "USER_CHANNELS_TOO_MUCH", "The user has joined too many channels or groups"
    if isinstance(error, UserAlreadyParticipantError):
        return "USER_ALREADY_PARTICIPANT", "The user is already a member of the group"
    if isinstance(error, ChatAdminRequiredError):
        return "CHAT_ADMIN_REQUIRED", "Chat administrator privileges are required"
    if isinstance(error, FloodWaitError):
        seconds = max(0, int(getattr(error, "seconds", 0) or 0))
        return "FLOOD_WAIT", f"Telegram requires waiting {seconds} seconds before retrying"
    if isinstance(error, RPCError):
        return "TELEGRAM_RPC_ERROR", "Telegram rejected the request"
    return "TELEGRAM_ERROR", "Telegram user processing failed"


def _group_creation_error(error: Exception) -> HTTPException:
    def detail(error_code: str, fallback: str) -> dict[str, str]:
        message = str(error).strip()
        sensitive_markers = (
            "api_hash",
            "api hash",
            "api_id",
            "api id",
            "credential",
            "password",
            "secret",
            "session",
            "token",
            "phone_code",
            "phone code",
            "/",
            "\\",
        )
        if not message or any(marker in message.lower() for marker in sensitive_markers):
            message = fallback
        return {"error_code": error_code, "message": message}

    if isinstance(error, FloodWaitError):
        seconds = max(0, int(getattr(error, "seconds", 0) or 0))
        return HTTPException(
            status_code=429,
            detail={
                "error_code": "FLOOD_WAIT",
                "message": f"Telegram requires waiting {seconds} seconds before creating a group",
                "retry_after": seconds,
            },
            headers={"Retry-After": str(seconds)},
        )
    if isinstance(error, ChatAdminRequiredError):
        return HTTPException(
            status_code=403,
            detail=detail(
                "CHAT_ADMIN_REQUIRED",
                "Telegram requires administrator privileges to create this group.",
            ),
        )
    if isinstance(error, UserPrivacyRestrictedError):
        return HTTPException(
            status_code=403,
            detail=detail(
                "USER_PRIVACY_RESTRICTED",
                "A Telegram user privacy setting prevents this operation.",
            ),
        )
    if isinstance(error, PeerIdInvalidError):
        return HTTPException(
            status_code=400,
            detail=detail("PEER_ID_INVALID", "Telegram rejected the supplied peer."),
        )
    if isinstance(error, UserNotMutualContactError):
        return HTTPException(
            status_code=403,
            detail=detail("USER_NOT_MUTUAL_CONTACT", "The Telegram user is not a mutual contact."),
        )
    if isinstance(error, UserChannelsTooMuchError):
        return HTTPException(
            status_code=403,
            detail=detail(
                "USER_CHANNELS_TOO_MUCH",
                "The user has joined too many channels or groups.",
            ),
        )
    if isinstance(error, UserAlreadyParticipantError):
        return HTTPException(
            status_code=409,
            detail=detail("USER_ALREADY_PARTICIPANT", "The user is already a member of the group."),
        )
    if isinstance(error, UserPrivacyRestrictedError):
        return HTTPException(
            status_code=403,
            detail=detail(
                "USER_PRIVACY_RESTRICTED",
                "A Telegram user privacy setting prevents this operation.",
            ),
        )
    if isinstance(error, PeerIdInvalidError):
        return HTTPException(
            status_code=400,
            detail=detail("PEER_ID_INVALID", "Telegram rejected the supplied peer."),
        )
    if isinstance(error, UserNotMutualContactError):
        return HTTPException(
            status_code=403,
            detail=detail("USER_NOT_MUTUAL_CONTACT", "The Telegram user is not a mutual contact."),
        )
    if isinstance(error, RPCError):
        return HTTPException(
            status_code=502,
            detail=detail(error.__class__.__name__, "Telegram rejected the group creation request."),
        )
    if isinstance(error, (OSError, ConnectionError, AsyncTimeoutError)):
        return HTTPException(
            status_code=503,
            detail=detail(error.__class__.__name__, "Telegram is unavailable."),
        )
    return HTTPException(
        status_code=500,
        detail=detail(error.__class__.__name__, "Telegram group creation failed."),
    )


def _telegram_error(error: Exception) -> HTTPException:
    """Log Telegram's technical error, but expose only a safe API response."""
    logger.exception("Telegram operation failed: %s", error)

    if isinstance(error, FloodWaitError):
        seconds = max(0, int(getattr(error, "seconds", 0) or 0))
        detail = (
            f"ارسال کد موقتاً محدود شده است. لطفاً {seconds} ثانیه دیگر تلاش کنید."
            if seconds
            else "ارسال کد تأیید موقتاً محدود شده است. لطفاً کمی بعد دوباره تلاش کنید."
        )
        return HTTPException(status_code=429, detail=detail, headers={"Retry-After": str(seconds)})

    if isinstance(error, (PhoneNumberInvalidError, PhoneNumberBannedError)):
        return HTTPException(status_code=422, detail="شماره تلفن واردشده معتبر نیست.")
    if isinstance(error, (PhoneNumberFloodError,)) or error.__class__.__name__ in {
        "PhoneCodeFloodError", "PhonePasswordFloodError", "SendCodeUnavailableError", "ResendCodeRequest",
    }:
        return HTTPException(
            status_code=429,
            detail="ارسال کد تأیید موقتاً محدود شده است. لطفاً کمی بعد دوباره تلاش کنید.",
        )
    if isinstance(error, PhoneCodeExpiredError):
        return HTTPException(
            status_code=410,
            detail="کد تأیید منقضی شده است. لطفاً درخواست کد جدید کنید.",
        )
    if isinstance(error, (PhoneCodeInvalidError, PhoneCodeEmptyError, PhoneCodeHashEmptyError,
                          CodeEmptyError, CodeHashInvalidError)):
        return HTTPException(status_code=400, detail="کد تأیید واردشده صحیح نیست.")
    if isinstance(error, (PasswordHashInvalidError, PasswordEmptyError)):
        return HTTPException(status_code=400, detail="رمز عبور دو مرحله‌ای صحیح نیست.")
    if isinstance(error, PasswordRequiredError):
        return HTTPException(status_code=400, detail="برای ادامه، رمز عبور دو مرحله‌ای تلگرام را وارد کنید.")
    if isinstance(error, (OSError, ConnectionError, AsyncTimeoutError)):
        return HTTPException(status_code=503, detail="ارتباط با تلگرام برقرار نشد. لطفاً دوباره تلاش کنید.")

    # Unknown Telethon errors must never be serialized to the client.
    if isinstance(error, RPCError):
        return HTTPException(status_code=502, detail="ارتباط با تلگرام برقرار نشد. لطفاً دوباره تلاش کنید.")
    return HTTPException(status_code=500, detail="خطایی رخ داد. لطفاً دوباره تلاش کنید.")


@app.exception_handler(RPCError)
async def telegram_exception_handler(_request: Request, error: RPCError):
    response = _telegram_error(error)
    return JSONResponse(status_code=response.status_code, content={"detail": response.detail}, headers=response.headers)


def _account_for_phone(user_id: str, phone: str):
    connection = get_connection()
    try:
        initialize_database(connection)
        account = find_telegram_account_by_phone(connection, user_id, phone)
        if account:
            return dict(account)
        account_id = create_telegram_account(
            connection, int(user_id), phone, LEGACY_API_ID, LEGACY_API_HASH
        )
        return dict(
            connection.execute("SELECT * FROM telegram_accounts WHERE id = ?", (account_id,)).fetchone()
        )
    finally:
        connection.close()


def get_user_id(secret_key: str | None = Header(default=None, alias="X-Secret-Key")) -> str:
    """Resolve the authenticated application user from a Secret Key."""
    if not secret_key:
        raise HTTPException(status_code=401, detail="secret key required")
    connection = get_connection()
    try:
        initialize_database(connection)
        user_id = get_user_id_from_token(connection, secret_key)
    finally:
        connection.close()
    if user_id is None:
        raise HTTPException(status_code=401, detail="invalid secret key")
    return str(user_id)


def get_secret_key(secret_key: str | None = Header(default=None, alias="X-Secret-Key")) -> str:
    if not secret_key:
        raise HTTPException(status_code=401, detail="secret key required")
    return secret_key


async def get_request_client(user_id: str = Depends(get_user_id)):
    try:
        return await telegram_clients.start(user_id)
    except Exception as error:
        raise _telegram_error(error) from error


@app.post("/telegram/register")
async def register_telegram_user(request: PhoneRequest):
    connection = get_connection()
    try:
        initialize_database(connection)
        user_id, token = create_application_user(connection)
        account_id = create_telegram_account(
            connection, user_id, request.phone, LEGACY_API_ID, LEGACY_API_HASH
        )
        account = dict(
            connection.execute("SELECT * FROM telegram_accounts WHERE id = ?", (account_id,)).fetchone()
        )
    finally:
        connection.close()

    try:
        already_connected = await telegram_clients.request_code(str(user_id), account)
        if already_connected:
            client = await telegram_clients.start(str(user_id))
            await client.send_message("me", token)
            return {
                "status": "connected",
                "api_token": token,
                "message": "existing Telegram session reused",
            }
    except Exception as error:
        raise _telegram_error(error) from error
    pending = telegram_clients.pending_status(str(user_id))
    return {
        "status": "code_sent",
        "expires_in": pending[1] if pending else 120,
        "api_token": token,
    }


@app.post("/telegram/connect", include_in_schema=False)
@app.post("/telegram/connect/start")
async def start_telegram_connection(
    request: PhoneRequest,
    user_id: str = Depends(get_user_id),
    secret_key: str = Depends(get_secret_key),
):
    account = _account_for_phone(user_id, request.phone)
    try:
        already_connected = await telegram_clients.request_code(user_id, account)
    except Exception as error:
        raise _telegram_error(error) from error
    if already_connected:
        try:
            await telegram_clients.start(user_id)
            await telegram_clients.get_client(user_id).send_message("me", secret_key)
        except Exception as error:
            raise _telegram_error(error) from error
        return {"status": "connected", "api_token": secret_key, "message": "existing Telegram session reused"}
    return {"status": "code_sent", "expires_in": telegram_clients.pending_status(user_id)[1]}


@app.post("/telegram/connect/verify")
async def verify_telegram_code(
    request: CodeRequest,
    user_id: str = Depends(get_user_id),
    secret_key: str = Depends(get_secret_key),
):
    try:
        verified = await telegram_clients.verify_code(user_id, request.code)
    except Exception as error:
        raise _telegram_error(error) from error
    if not verified:
        return {"status": "two_factor_required"}
    try:
        client = await telegram_clients.start(user_id)
        await client.send_message("me", secret_key)
    except Exception as error:
        raise _telegram_error(error) from error
    return {"status": "connected", "api_token": secret_key}


@app.post("/telegram/connect/2fa")
async def verify_telegram_2fa(
    request: PasswordRequest,
    user_id: str = Depends(get_user_id),
    secret_key: str = Depends(get_secret_key),
):
    try:
        await telegram_clients.verify_2fa(user_id, request.password)
        client = await telegram_clients.start(user_id)
        await client.send_message("me", secret_key)
    except Exception as error:
        raise _telegram_error(error) from error
    return {"status": "connected", "api_token": secret_key}


@app.get("/telegram/status")
async def telegram_status(user_id: str = Depends(get_user_id)):
    pending = telegram_clients.pending_status(user_id)
    if pending:
        status, expires_in = pending
        return {"status": status, "expires_in": expires_in}

    connection = get_connection()
    try:
        initialize_database(connection)
        account = find_telegram_account(connection, user_id)
        if not account:
            return {"status": "not_connected"}
        account = dict(account)
    finally:
        connection.close()

    try:
        client = telegram_clients.get_account_client(user_id, account)
        await client.connect()
        authorized = await client.is_user_authorized()
    except Exception as error:
        raise _telegram_error(error) from error
    return {
        "status": "connected" if authorized else "not_connected",
        "phone": account.get("phone"),
    }


# Start Telegram client when FastAPI starts
@app.on_event("startup")
async def startup():
    # Telegram clients are created lazily when an endpoint needs one.
    return None


@app.on_event("shutdown")
async def shutdown():
    await telegram_clients.disconnect_all()


@app.get("/")
async def read_root(client=Depends(get_request_client)):
    try:
        entity = await client.get_entity("@mob83")

        messages = []
        async for msg in client.iter_messages(entity, limit=20):
            messages.append({
                "id": msg.id,
                "text": msg.text,
                "date": str(msg.date)
            })

        return {"messages": messages}
    except Exception as error:
        raise _telegram_error(error) from error


def _is_phone_target(target: str) -> bool:
    clean_target = target.strip()
    return clean_target.startswith("+") or (
        clean_target.isdigit() and len(clean_target) >= 11
    )


async def _resolve_numeric_user_id(client, target: str):
    """Resolve a numeric Telegram user ID using this user's client/cache."""
    user_id = int(target)
    last_error: Exception | None = None

    # A cached PeerUser preserves the access_hash required by Telethon.
    for candidate in (PeerUser(user_id), user_id):
        try:
            return await client.get_entity(candidate)
        except Exception as error:
            last_error = error

    # If the entity is not in Telethon's entity cache, inspect this user's
    # dialogs. The returned entity carries the user's valid access_hash.
    iter_dialogs = getattr(client, "iter_dialogs", None)
    if callable(iter_dialogs):
        try:
            async for dialog in iter_dialogs():
                entity = getattr(dialog, "entity", dialog)
                if getattr(entity, "id", None) == user_id:
                    return entity
        except Exception as error:
            last_error = error

    if last_error is not None:
        raise last_error
    raise ValueError("Telegram user ID could not be resolved")


async def _resolve_target(client, target: str):
    """Resolve username, phone number, or numeric user ID consistently."""
    clean_target = target.strip()
    if not clean_target:
        raise ValueError("target is required")

    # Preserve the existing phone-number behavior. Long unsigned numbers are
    # treated as phones first; a failed lookup can still fall through to an ID
    # lookup for accounts whose numeric Telegram ID is that long.
    if _is_phone_target(clean_target):
        try:
            return await client.get_entity(clean_target)
        except Exception as phone_error:
            if not clean_target.isdigit():
                raise phone_error
            try:
                return await _resolve_numeric_user_id(client, clean_target)
            except Exception:
                raise phone_error

    if clean_target.isdigit():
        return await _resolve_numeric_user_id(client, clean_target)

    return await client.get_entity(clean_target)


@app.get("/get-message")
async def get_message(
    target: str,
    client=Depends(get_request_client),
):
    try:
        entity = await _resolve_target(client, target)

        messages = []

        async for msg in client.iter_messages(entity, limit=60):
            messages.append({
                "id": msg.id,
                "text": msg.text,
                "date": str(msg.date),
            })

        return {
            "target": target,
            "entity": {
                "id": entity.id,
                "type": type(entity).__name__,
                "username": getattr(entity, "username", None),
                "first_name": getattr(entity, "first_name", None),
                "last_name": getattr(entity, "last_name", None),
                "title": getattr(entity, "title", None),
                "phone": getattr(entity, "phone", None),
            },
            "messages": messages,
        }

    except Exception as error:
        raise _telegram_error(error) from error


async def test_inline_button_check(target: str, message_id: int, client):
    """Inspect one message without changing Telegram state.

    Telethon 1.44 returns a single ``Message`` when ``ids`` is an integer and
    a list-like result when multiple IDs are requested. Keep this helper
    scalar-safe so diagnostics never assume ``messages[0]`` exists.
    """
    try:
        entity = await client.get_entity(target)
        message = await client.get_messages(entity, ids=message_id)
    except Exception as error:
        raise HTTPException(status_code=502, detail="Telegram request failed") from error

    if isinstance(message, (list, tuple)):
        message = message[0] if message else None
    if message is None:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error_code": "MESSAGE_NOT_FOUND"},
        )

    peer = getattr(message, "peer_id", None)
    entity_id = getattr(entity, "id", None)
    peer_ids = {
        getattr(peer, "user_id", None),
        getattr(peer, "chat_id", None),
        getattr(peer, "channel_id", None),
    }
    if entity_id is not None and entity_id not in peer_ids:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error_code": "MESSAGE_NOT_IN_TARGET"},
        )

    buttons = []
    for row in getattr(message, "buttons", None) or []:
        for button in row or []:
            buttons.append({
                "text": getattr(button, "text", None),
                "button_type": type(button).__name__,
                "has_url": bool(getattr(button, "url", None)),
            })

    return {
        "success": True,
        "message_id": getattr(message, "id", message_id),
        "has_reply_markup": getattr(message, "reply_markup", None) is not None,
        "buttons": [buttons],
    }


def _create_chat_response_fields(response: object) -> list[str]:
    response_fields = getattr(response, "__dict__", None)
    if isinstance(response_fields, dict):
        return sorted(str(field) for field in response_fields)
    known_fields = ("chats", "updates", "update", "users", "date", "seq")
    return [field for field in known_fields if hasattr(response, field)]


def _create_chat_update_types(response: object) -> list[str]:
    try:
        updates_container = getattr(response, "updates", None)
        updates: list[object] = []

        if updates_container is not None:
            if isinstance(updates_container, (list, tuple)):
                updates.extend(updates_container)
            else:
                nested_updates = getattr(updates_container, "updates", None)
                if nested_updates is not None:
                    if isinstance(nested_updates, (list, tuple)):
                        updates.extend(nested_updates)
                    else:
                        updates.extend(list(nested_updates))
                else:
                    short_update = getattr(updates_container, "update", None)
                    if short_update is not None:
                        updates.append(short_update)
                    else:
                        updates.extend(item for item in updates_container)

        update = getattr(response, "update", None)
        if update is not None:
            updates.append(update)
        return [type(item).__name__ for item in updates]
    except Exception:
        logger.warning(
            "Unable to parse CreateChatRequest updates response_type=%s",
            type(response).__name__,
        )
        return []


def _create_chat_peer_candidates(response: object) -> list[object]:
    candidates: list[object] = []
    objects: list[object] = []
    updates_container = getattr(response, "updates", None)
    if isinstance(updates_container, (list, tuple)):
        objects.extend(updates_container)
    elif updates_container is not None:
        nested_updates = getattr(updates_container, "updates", None)
        if isinstance(nested_updates, (list, tuple)):
            objects.extend(nested_updates)
    update = getattr(response, "update", None)
    if update is not None:
        objects.append(update)

    for item in objects:
        message = getattr(item, "message", None)
        peers = [getattr(item, "peer_id", None), getattr(item, "peer", None)]
        if message is not None:
            peers.extend((
                getattr(message, "peer_id", None),
                getattr(message, "peer", None),
            ))
        for peer in peers:
            if isinstance(peer, (PeerChat, PeerChannel)) and peer not in candidates:
                candidates.append(peer)

    return candidates


async def _created_group_from_response(client, response: object) -> Chat | Channel | None:
    response_fields = _create_chat_response_fields(response)
    update_types = _create_chat_update_types(response)
    logger.debug(
        "CreateChatRequest response type=%s fields=%s update_types=%s",
        type(response).__name__,
        response_fields,
        update_types,
    )

    direct_chats = list(getattr(response, "chats", None) or [])
    if direct_chats:
        group = direct_chats[0]
        logger.debug(
            "CreateChatRequest extracted direct group type=%s group_id=%s",
            type(group).__name__,
            getattr(group, "id", None),
        )
        if isinstance(group, (Chat, Channel)):
            return group

    candidates = _create_chat_peer_candidates(response)
    logger.debug(
        "CreateChatRequest peer candidates=%s",
        [type(candidate).__name__ for candidate in candidates],
    )
    for candidate in candidates:
        try:
            group = await client.get_entity(candidate)
        except Exception as error:
            logger.debug(
                "CreateChatRequest peer resolution failed peer_type=%s error_type=%s",
                type(candidate).__name__,
                error.__class__.__name__,
            )
            group = None
        if isinstance(group, (Chat, Channel)):
            logger.debug(
                "CreateChatRequest extracted resolved group type=%s group_id=%s",
                type(group).__name__,
                getattr(group, "id", None),
            )
            return group

        try:
            if isinstance(candidate, PeerChat):
                full = await client(GetFullChatRequest(chat_id=candidate.chat_id))
            else:
                full = await client(GetFullChannelRequest(channel=candidate))
            full_chats = list(getattr(full, "chats", None) or [])
            if full_chats and isinstance(full_chats[0], (Chat, Channel)):
                group = full_chats[0]
                logger.debug(
                    "CreateChatRequest extracted group via full entity request type=%s group_id=%s",
                    type(group).__name__,
                    getattr(group, "id", None),
                )
                return group
        except Exception as error:
            logger.debug(
                "CreateChatRequest full entity resolution failed peer_type=%s error_type=%s",
                type(candidate).__name__,
                error.__class__.__name__,
            )

    return None

@app.post("/create-group")
async def create_group(
    request: CreateGroupRequest,
    client=Depends(get_request_client),
):
    unique_users = list(dict.fromkeys(request.users))
    results: list[dict[str, object]] = []
    resolved_users: list[tuple[int, str, object, object]] = []

    for user_input in unique_users:
        try:
            normalized_input = user_input
            if normalized_input.lstrip("-").isdigit() and (
                normalized_input.startswith("-")
                or len(normalized_input.lstrip("-")) < 11
            ):
                entity = await client.get_entity(int(normalized_input))
            else:
                entity = await client.get_entity(normalized_input)
            user_id = getattr(entity, "id", None)
            if user_id is None:
                raise ValueError("Telegram entity has no user ID")
            input_entity = await client.get_input_entity(entity)
            resolved_users.append((len(results), user_input, entity, input_entity))
            results.append({
                "input": user_input,
                "user_id": user_id,
                "status": "pending",
            })
        except Exception as error:
            error_code, message = _group_user_error(error)
            results.append({
                "input": user_input,
                "status": "failed",
                "error_code": error_code,
                "message": message,
            })

    if not resolved_users:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "At least one Telegram user must be resolved",
                "users": results,
            },
        )

    logger.info(
        "Creating Telegram group title=%r resolved_user_count=%d",
        request.title,
        len(resolved_users),
    )
    try:
        _, first_input, first_entity, first_input_entity = resolved_users[0]
        created = await client(CreateChatRequest(
            users=[first_input_entity],
            title=request.title,
        ))
    except Exception as error:
        raise _group_creation_error(error) from error

    group_entity = await _created_group_from_response(client, created)
    if group_entity is None:
        logger.error(
            "CreateChatRequest succeeded but no resolvable group entity was found response_type=%s",
            type(created).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail={
                "error_code": "GROUP_ID_UNAVAILABLE",
                "message": "Telegram created the group but did not return a resolvable group ID",
            },
        )

    group_id = int(group_entity.id)
    logger.info(
        "Telegram group created group_type=%s group_id=%s",
        type(group_entity).__name__,
        group_id,
    )

    # CreateChatRequest creates a basic Chat with its first user already
    # included. A Channel would require channel invitation requests instead.
    request_successes: set[int] = set()
    invite_link: str | None = None
    invite_link_error: Exception | None = None
    invite_peer = None
    if isinstance(group_entity, Chat):
        request_successes.add(resolved_users[0][0])
        logger.info(
            "Telegram group creation included initial member group_id=%s user_id=%s",
            group_id,
            first_entity.id,
        )
        users_to_add = resolved_users[1:]
    elif isinstance(group_entity, Channel):
        users_to_add = resolved_users
    else:
        raise HTTPException(
            status_code=502,
            detail={
                "error_code": "UNSUPPORTED_GROUP_TYPE",
                "message": "Telegram returned an unsupported group entity type",
            },
        )

    resolved_by_index = {item[0]: item for item in resolved_users}
    pending_invites: set[int] = set()

    async def send_invitation(result_index: int) -> None:
        nonlocal invite_link, invite_link_error, invite_peer
        _, user_input, entity, _ = resolved_by_index[result_index]

        if not request.invite_message:
            results[result_index] = {
                "input": user_input,
                "user_id": entity.id,
                "status": "not_added",
            }
            return

        try:
            if invite_link_error is not None:
                raise invite_link_error
            if invite_link is None:
                if invite_peer is None:
                    invite_peer = (
                        InputPeerChat(chat_id=group_id)
                        if isinstance(group_entity, Chat)
                        else await client.get_input_entity(group_entity)
                    )
                invite_response = await client(
                    ExportChatInviteRequest(peer=invite_peer)
                )
                invite_link = getattr(invite_response, "link", None)
            if not invite_link:
                raise ValueError("Telegram did not return an invite link")

            user_id = entity.id
            invite_text = request.invite_message.rstrip()
            final_message = f"{invite_text}\n\n{invite_link}"
            logger.info(
                "Invite message prepared target=%s invite_link_attached=%s message_length=%s",
                user_input,
                True,
                len(final_message),
            )
            await client.send_message(
                entity,
                final_message,
            )
            results[result_index] = {
                "input": user_input,
                "user_id": user_id,
                "status": "invite_sent",
                "invite_message_sent": True,
            }
        except Exception as invite_error:
            # Keep the invite URL and message body out of logs.
            invite_link_error = invite_error
            logger.warning(
                "Telegram invite message failed group_id=%s user_id=%s error_type=%s",
                group_id,
                entity.id,
                invite_error.__class__.__name__,
            )
            results[result_index] = {
                "input": user_input,
                "user_id": entity.id,
                "status": "invite_failed",
                "invite_message_sent": False,
                "error_code": "INVITE_MESSAGE_SEND_FAILED",
                "message": "The invite message could not be sent",
            }

    for result_index, user_input, entity, input_entity in users_to_add:
        logger.info(
            "Adding Telegram group member group_id=%s user_id=%s",
            group_id,
            entity.id,
        )
        try:
            if isinstance(group_entity, Chat):
                request_to_add = AddChatUserRequest(
                    chat_id=group_id,
                    user_id=input_entity,
                    fwd_limit=0,
                )
            else:
                request_to_add = InviteToChannelRequest(
                    channel=group_entity,
                    users=[input_entity],
                )
            await client(request_to_add)
            request_successes.add(result_index)
            logger.info(
                "Telegram group member add succeeded group_id=%s user_id=%s",
                group_id,
                entity.id,
            )
        except Exception as error:
            error_code, message = _group_user_error(error)
            logger.warning(
                "Telegram group member add failed group_id=%s user_id=%s error_type=%s",
                group_id,
                entity.id,
                error.__class__.__name__,
            )

            if isinstance(error, UserPrivacyRestrictedError):
                pending_invites.add(result_index)
                if not request.invite_message:
                    await send_invitation(result_index)
                continue

            results[result_index] = {
                "input": user_input,
                "user_id": entity.id,
                "status": "failed",
                "error_code": error_code,
                "message": message,
            }

    verification_warning = None
    try:
        participants = await client.get_participants(group_entity)
        participant_ids = {
            int(participant.id)
            for participant in participants
            if getattr(participant, "id", None) is not None
        }
        for result_index in list(request_successes):
            _, user_input, entity, _ = resolved_by_index[result_index]
            if int(entity.id) not in participant_ids:
                # A successful add request can still be contradicted by a
                # successful participant lookup. Queue this user for the same
                # invite flow used for privacy-restricted add errors.
                request_successes.remove(result_index)
                pending_invites.add(result_index)
                logger.warning(
                    "Telegram group member verification found user absent group_id=%s user_id=%s",
                    group_id,
                    entity.id,
                )
    except Exception as error:
        # Verification is supplementary. In particular, Telegram can reject
        # participant enumeration because of entity/access limitations even
        # though AddChatUserRequest already succeeded.
        verification_warning = "Telegram membership could not be independently verified"
        logger.warning(
            "Telegram group member verification warning group_id=%s error_type=%s",
            group_id,
            error.__class__.__name__,
        )

    for result_index in request_successes:
        _, user_input, entity, _ = resolved_by_index[result_index]
        results[result_index] = {
            "input": user_input,
            "user_id": entity.id,
            "status": "success",
        }

    for result_index in pending_invites:
        await send_invitation(result_index)

    success_count = sum(
        result["status"] in {"success", "invite_sent"}
        for result in results
    )
    return {
        "success": True,
        "group_id": group_id,
        "group": {
            "id": group_id,
            "title": request.title,
        },
        "total": len(results),
        "success_count": success_count,
        "failed_count": len(results) - success_count,
        "users": results,
        "verification_warning": verification_warning,
    }


@app.get("/send-message")
async def create_chat(
    target: str,
    text: str = "hi",
    first_name: str = "User",
    last_name: str = "",
    client=Depends(get_request_client),
):
    try:
        phone_target = _is_phone_target(target)
        try:
            user = await _resolve_target(client, target)
        except Exception as resolve_error:
            if not _is_phone_target(target):
                raise resolve_error

            contact = InputPhoneContact(
                client_id=0,
                phone=target,
                first_name=first_name,
                last_name=last_name,
            )
            result = await client(ImportContactsRequest([contact]))
            if not result.users:
                return {
                    "ok": False,
                    "error": "user_not_found",
                    "message": "این شماره در تلگرام پیدا نشد",
                }
            phone_target = False
            user = result.users[0]

        msg = await client.send_message(user, text)

        if phone_target:
            return {
                "chat_created": True,
                "message_id": msg.id,
                "method": "direct_phone",
            }

        return {
            "chat_created": True,
            "user_id": user.id,
            "message_id": msg.id
        }

    except Exception as error:
        logger.exception("Telegram chat operation failed: %s", error)
        raise HTTPException(status_code=502, detail="ارتباط با تلگرام برقرار نشد. لطفاً دوباره تلاش کنید.") from error
