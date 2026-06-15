from telethon import TelegramClient

api_id = 34216039
api_hash = "aeafe65f91b250c95d3a443a4f7dbf06"
phone = "+447988029161"

client = TelegramClient("mysession", api_id, api_hash)

client.start(phone)
print("Logged in successfully")

client.run_until_disconnected()
