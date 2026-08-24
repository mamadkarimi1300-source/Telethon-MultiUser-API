"""Small SQLite foundation for application data."""

import sqlite3
import hashlib
import secrets
from pathlib import Path

from session_manager import get_session_path


def get_connection(database_path: str | Path = "telethon_api.sqlite3") -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS auth_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash TEXT UNIQUE,
            token TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS telegram_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            telegram_user_id INTEGER,
            phone TEXT,
            api_id INTEGER,
            api_hash TEXT,
            session_path TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE UNIQUE INDEX IF NOT EXISTS auth_tokens_raw_token_unique
            ON auth_tokens(token) WHERE token IS NOT NULL;
        """
    )
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(telegram_accounts)")
    }
    if "api_id" not in columns:
        connection.execute("ALTER TABLE telegram_accounts ADD COLUMN api_id INTEGER")
    if "api_hash" not in columns:
        connection.execute("ALTER TABLE telegram_accounts ADD COLUMN api_hash TEXT")
    if "session_path" not in columns:
        connection.execute("ALTER TABLE telegram_accounts ADD COLUMN session_path TEXT")
    from session_manager import get_session_path

    for account in connection.execute(
        "SELECT id, user_id FROM telegram_accounts"
    ):
        connection.execute(
            "UPDATE telegram_accounts SET session_path = ? WHERE id = ?",
            (str(get_session_path(account["user_id"])), account["id"]),
        )
    token_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(auth_tokens)")
    }
    if "token_hash" not in token_columns:
        connection.execute("ALTER TABLE auth_tokens ADD COLUMN token_hash TEXT")
    connection.commit()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_application_user(connection: sqlite3.Connection) -> tuple[int, str]:
    """Create one application user and return its raw bearer token exactly once."""
    user_id = connection.execute("INSERT INTO users DEFAULT VALUES").lastrowid
    token = secrets.token_urlsafe(32)
    connection.execute(
        "INSERT INTO auth_tokens (user_id, token) VALUES (?, ?)",
        (user_id, token),
    )
    connection.commit()
    return int(user_id), token


def find_user_id_by_token(connection: sqlite3.Connection, token: str) -> int | None:
    row = connection.execute(
        "SELECT user_id, token_hash, token FROM auth_tokens WHERE token_hash = ? OR token = ?",
        (hash_token(token), token),
    ).fetchone()
    return int(row["user_id"]) if row else None


def find_telegram_account(
    connection: sqlite3.Connection, user_id: int | str
) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM telegram_accounts WHERE user_id = ? ORDER BY id LIMIT 1",
        (user_id,),
    ).fetchone()


def find_telegram_account_by_phone(
    connection: sqlite3.Connection, user_id: int | str, phone: str
) -> sqlite3.Row | None:
    """Phone lookup is always constrained by the authenticated owner."""
    return connection.execute(
        "SELECT * FROM telegram_accounts WHERE user_id = ? AND phone = ? ORDER BY id LIMIT 1",
        (user_id, phone),
    ).fetchone()


def create_telegram_account(
    connection: sqlite3.Connection,
    user_id: int,
    phone: str | None,
    api_id: int,
    api_hash: str,
    telegram_user_id: int | None = None,
) -> int:
    row = connection.execute(
        """INSERT INTO telegram_accounts
           (user_id, telegram_user_id, phone, api_id, api_hash)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, telegram_user_id, phone, api_id, api_hash),
    )
    connection.commit()
    account_id = int(row.lastrowid)
    connection.execute(
        "UPDATE telegram_accounts SET session_path = ? WHERE id = ?",
        (str(get_session_path(user_id)), account_id),
    )
    connection.commit()
    return account_id


def update_telegram_account_user(
    connection: sqlite3.Connection, account_id: int, telegram_user_id: int | None
) -> None:
    connection.execute(
        "UPDATE telegram_accounts SET telegram_user_id = ? WHERE id = ?",
        (telegram_user_id, account_id),
    )
    connection.commit()
