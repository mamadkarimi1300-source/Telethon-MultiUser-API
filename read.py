import os

from telethon import TelegramClient

from session_manager import create_session

api_id = int(os.environ["TELEGRAM_API_ID"])
api_hash = os.environ["TELEGRAM_API_HASH"]

client = TelegramClient(str(create_session(os.environ.get("TELEGRAM_USER_ID", "default"))), api_id, api_hash)

async def main():
    entity = await client.get_entity("@mob83")

    async for message in client.iter_messages(entity, limit=20):
        print(message.id, message.date)
        print(message.text)
        print("----------------")

with client:
    client.loop.run_until_complete(main())
