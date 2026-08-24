"""Helpers for keeping Telegram sessions outside the repository."""

from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
SESSION_DIR = Path.home() / ".telethon_api" / "sessions"
DEFAULT_USER_ID = "default"
LEGACY_DEFAULT_SESSION = Path("mysession.session")


def get_session_path(user_id: str | int) -> Path:
    """Return a user's session path without reading its contents.

    The unauthenticated legacy API keeps using the existing default session
    for compatibility. Authenticated users always use the external directory.
    """
    if str(user_id) == DEFAULT_USER_ID:
        return LEGACY_DEFAULT_SESSION
    safe_user_id = str(user_id).replace("/", "_").replace("\\", "_")
    return SESSION_DIR / f"{safe_user_id}.session"


def create_session(user_id: str | int) -> Path:
    """Create the external session directory and return the user's path."""
    if str(user_id) == DEFAULT_USER_ID:
        return get_session_path(user_id)
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    return get_session_path(user_id)


def remove_session(user_id: str | int) -> None:
    """Remove a user's session file if it exists, without inspecting it."""
    if str(user_id) == DEFAULT_USER_ID:
        return
    get_session_path(user_id).unlink(missing_ok=True)
