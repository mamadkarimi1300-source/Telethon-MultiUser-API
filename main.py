from fastapi import FastAPI
from telethon import TelegramClient
import asyncio
import re

# ==============================
# Telegram Config
# ==============================

api_id = 34216039
api_hash = "aeafe65f91b250c95d3a443a4f7dbf06"

app = FastAPI()
client = TelegramClient("mysession", api_id, api_hash)

# ==============================
# Cache
# ==============================

cache_data = []
CACHE_SECONDS = 120

# ==============================
# Helpers
# ==============================

def to_int(value):
    if value is None:
        return None
    try:
        return int(str(value).replace(",", "").strip())
    except:
        return None


def price_or_zero(value):
    v = to_int(value)
    return v if v else 0


def extract_first(pattern, text, flags=re.S | re.I):
    m = re.search(pattern, text, flags)
    return m.group(1) if m else None

# ==============================
# Parsers
# ==============================

def parse_fardaedolar(text):
    sell = extract_first(r"فروش.*?دلار[:\s]+([\d,]+)", text)
    buy = extract_first(r"خرید.*?دلار[:\s]+([\d,]+)", text)
    return {"sell_price": price_or_zero(sell), "buy_price": price_or_zero(buy)}


def parse_hareta(text):
    sell = extract_first(r"([\d,]+)\s*فروش", text)
    buy = extract_first(r"([\d,]+)\s*خ[\W_]*رید", text)
    return {"sell_price": price_or_zero(sell), "buy_price": price_or_zero(buy)}


def parse_abshdh(text):
    price = extract_first(r"آ?بشده[^\d\n]*([\d,]+)", text)
    return {"sell_price": price_or_zero(price), "buy_price": 0}


def parse_qeymatabshodeh(text):
    sell = extract_first(r"([\d,]+)[^\n]*فروش", text)
    buy = extract_first(r"([\d,]+)[^\n]*خرید", text)
    return {"sell_price": price_or_zero(sell), "buy_price": price_or_zero(buy)}


def parse_goldrate(text):
    price = extract_first(r"(\d+(?:\.\d+)?)", text)
    return {"sell_price": price_or_zero(price), "buy_price": 0}


def parse_default(text):
    return {"sell_price": 0, "buy_price": 0}

# ==============================
# Parser Map
# ==============================

PARSERS = {
    "fardaedolar": parse_fardaedolar,
    "Hareta_Dollar_Bloe": parse_hareta,
    "abshdh": parse_abshdh,
    "Qeymatabshodeh": parse_qeymatabshodeh,
    "NaghdP": parse_qeymatabshodeh,
    "goldratepric2020": parse_goldrate,
}

# ==============================
# Output Builder
# ==============================

def build_output(parsed, username):

    sell_raw = parsed.get("sell_price", 0)
    buy_raw = parsed.get("buy_price", 0)

    sell = sell_raw * 10000
    buy = buy_raw * 10000
    gram = sell_raw if sell_raw else None

    profit = (sell - buy) / 2 if sell and buy else 0
    price = buy + profit if buy else sell

    return {
        "sell": sell,
        "buy": buy,
        "gram": gram,
        "profit": profit,
        "price": price,
        "uuid": f"telegram-{username}",
        "provider": "24telegram"
    }

# ==============================
# Channels
# ==============================

CHANNELS = [
    "mob83",
    "fardaedolar",
    "Hareta_Dollar_Bloe",
    "abshdh",
    "Qeymatabshodeh",
    "NaghdP",
    "goldratepric2020"
]

# ==============================
# Background Updater
# ==============================

async def update_cache():

    global cache_data

    while True:

        results = []

        for username in CHANNELS:

            try:
                entity = await client.get_entity(username)
                parser = PARSERS.get(username, parse_default)

                async for msg in client.iter_messages(entity, limit=1):

                    parsed = parser(msg.text or "")
                    data = build_output(parsed, username)

                    data["date"] = str(msg.date)

                    results.append(data)

            except Exception as e:

                results.append({
                    "uuid": f"telegram-{username}",
                    "error": str(e),
                    "provider": "24telegram"
                })

        cache_data = results

        await asyncio.sleep(CACHE_SECONDS)

# ==============================
# Startup
# ==============================

@app.on_event("startup")
async def startup():

    await client.start()

    asyncio.create_task(update_cache())

# ==============================
# Shutdown
# ==============================

@app.on_event("shutdown")
async def shutdown():
    await client.disconnect()

# ==============================
# Route
# ==============================

@app.get("/")
async def get_prices():

    return {
        "count": len(cache_data),
        "data": cache_data,
        "refresh_seconds": CACHE_SECONDS
    }
