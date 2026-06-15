from fastapi import FastAPI
from telethon import TelegramClient
import asyncio

# ==============================
# Telegram Config
# ==============================

api_id = 34216039
api_hash = "aeafe65f91b250c95d3a443a4f7dbf06"

# ==============================
# App
# ==============================

app = FastAPI()
client = TelegramClient("mysession", api_id, api_hash)

# ==============================
# Startup / Shutdown
# ==============================

@app.on_event("startup")
async def startup():
    await client.start()


@app.on_event("shutdown")
async def shutdown():
    await client.disconnect()


# ==============================
# Route
# ==============================

@app.get("/")
async def read_root(limit: int = 100):

    usernames = [
        "mob83",
        "fardaedolar",
        "Hareta_Dollar_Bloe",
        "abshdh",
        "Qeymatabshodeh",
        "NaghdP",
        "goldratepric2020"
    ]

    async def get_last_messages(username: str):
        try:
            entity = await client.get_entity(username)

            posts = []

            async for msg in client.iter_messages(entity, limit=limit):
                posts.append({
                    "username": username,   # ✅ مشخص می‌کند پست مال کیست
                    "message_id": msg.id,
                    "text": msg.text,
                    "date": str(msg.date)
                })

            posts.reverse()

            return posts

        except Exception as e:
            return [{
                "username": username,
                "error": str(e)
            }]

    results = await asyncio.gather(
        *(get_last_messages(u) for u in usernames)
    )

    # flatten کردن لیست‌ها
    all_posts = [post for user_posts in results for post in user_posts]

    return {
        "total_posts": len(all_posts),
        "posts": all_posts
    }
