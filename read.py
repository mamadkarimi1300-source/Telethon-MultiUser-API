from telethon import TelegramClient

api_id = 39297563
api_hash = "19fa457d712a4e679708dfed2c6dde1c"

client = TelegramClient("mysession", api_id, api_hash)

async def main():
    entity = await client.get_entity("@mob83")

    async for message in client.iter_messages(entity, limit=20):
        print(message.id, message.date)
        print(message.text)
        print("----------------")

with client:
    client.loop.run_until_complete(main())