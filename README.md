## Telethon API

This project exposes the existing FastAPI Telegram routes and keeps Telegram
sessions outside the repository at `~/.telethon_api/sessions/` for
authenticated users. The existing `mysession.session` remains the legacy
session for the default user.

The legacy `default` client retains its original credentials. Authenticated
users must have their own `api_id` and `api_hash` in the `telegram_accounts`
table. Authentication and account modules provide foundations only; no new
login or account-creation flow has been added.

Run the checks with:

```bash
python -m compileall .
pytest -q
```
