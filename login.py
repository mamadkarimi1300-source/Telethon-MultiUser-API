import os

from telethon import TelegramClient

from session_manager import create_session

api_id = int(os.environ["TELEGRAM_API_ID"])
api_hash = os.environ["TELEGRAM_API_HASH"]
phone = os.environ["TELEGRAM_PHONE"]

client = TelegramClient(str(create_session(os.environ.get("TELEGRAM_USER_ID", "default"))), api_id, api_hash)

client.start(phone)
print("Logged in successfully")

client.run_until_disconnected()
