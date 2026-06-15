from fastapi import FastAPI
from telethon import TelegramClient
import asyncio
import re

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
# Helpers
# ==============================

def to_int(value):
    if value is None:
        return None
    try:
        return int(value.replace(",", "").strip())
    except Exception:
        return None


def extract_first(pattern, text, flags=re.S | re.I):
    match = re.search(pattern, text, flags)
    return match.group(1) if match else None


# ==============================
# Parsers
# ==============================

def parse_fardaedolar(text: str):
    """
    نمونه متن:
    🔴 فروش
    💵 دلار: 162,320 ↘️  |  🟢 تتر: 163,650 ↗️
    🔵 خرید
    💵 دلار: 162,290 ➖  |  🟢 تتر: 163,651 ↘️
    """
    text = text or ""

    sell_dollar = extract_first(r"فروش.*?دلار[:\s]+([\d,]+)", text)
    sell_tether = extract_first(r"فروش.*?تتر[:\s]+([\d,]+)", text)
    buy_dollar = extract_first(r"خرید.*?دلار[:\s]+([\d,]+)", text)
    buy_tether = extract_first(r"خرید.*?تتر[:\s]+([\d,]+)", text)

    return {
        "sell_dollar": to_int(sell_dollar),
        "sell_tether": to_int(sell_tether),
        "buy_dollar": to_int(buy_dollar),
        "buy_tether": to_int(buy_tether),
    }


def parse_hareta(text: str):
    """
    نمونه متن:
    هرات فردایی ⏳ 162,900 فروش🔴
    هرات فردایی ⏳ 162,600 خــرید🔵
    """
    text = text or ""

    # اول فروش
    sell = extract_first(r"([\d,]+)\s*فروش", text)
    # خرید ممکنه خــرید یا خرید باشد
    buy = extract_first(r"([\d,]+)\s*خ[\W_]*رید", text)

    return {
        "sell_price": to_int(sell),
        "buy_price": to_int(buy),
    }


def parse_abshdh(text: str):
    text = text or ""

    text = clean_channel_footer(text)
    text = text.replace("**", "")

    abshode = extract_first(
        r"آ?بشده[^\d\n]*([\d,]+)",
        text
    )

    gram = extract_first(
        r"گرم[^\d\n:]*[:\s]*([\d,]+)",
        text
    )

    return {
        "abshode_price": to_int(abshode),
        "gold_gram": to_int(gram),
    }

def clean_channel_footer(text: str) -> str:
    if not text:
        return ""

    # حذف بخش Just In Time تا آخر متن
def clean_channel_footer(text: str) -> str:
    if not text:
        return ""

    # حذف کاراکترهای مخفی RTL / نیم‌فاصله / کشیده
    text = re.sub(r"[\u200c\u200f\u202a-\u202e\u0640]", "", text)

    # حذف خطی که شامل Just In Time است (فقط همان خط)
    text = re.sub(r"^.*Just\s*In\s*Time.*$", "", text, flags=re.I | re.M)

    # حذف خطوطی که فقط آیدی تلگرام دارند
    text = re.sub(r"^@\w+.*$", "", text, flags=re.M)

    # حذف لینک‌های t.me
    text = re.sub(r"t\.me/\S+", "", text)

    # حذف خطوط خالی اضافه
    text = re.sub(r"\n\s*\n", "\n", text)

    return text.strip()


def parse_qeymatabshodeh(text: str):
    """
    نمونه متن:
    72,300,000⏳باحواله✅معامله
    گرم: 16,690,521
    71,900,000☀️امروز🔵خرید
    گرم: 16,598,180
    72,350,000⏳باحواله🔴فروش
    گرم: 16,702,063
    """
    text = text or ""

    sell = extract_first(r"([\d,]+)[^\n]*فروش", text)
    buy = extract_first(r"([\d,]+)[^\n]*خرید", text)
    gram = extract_first(r"گرم[:\s]+([\d,]+)", text)

    return {
        "sell_price": to_int(sell),
        "buy_price": to_int(buy),
        "gram_price": to_int(gram),
    }


def parse_goldrate(text: str):
    """
    نمونه متن:
    ♦️ 4338.45
    """
    text = text or ""

    price = extract_first(r"(\d+(?:\.\d+)?)", text)

    return {
        "gold_price": float(price) if price else None
    }


def parse_default(text: str):
    return {
        "raw_text": text or ""
    }


# ==============================
# Parser Registry
# ==============================

PARSERS = {
    "fardaedolar": parse_fardaedolar,
    "Hareta_Dollar_Bloe": parse_hareta,
    "abshdh": parse_abshdh,
    "Qeymatabshodeh": parse_qeymatabshodeh,
    "NaghdP": parse_qeymatabshodeh,  # اگر ساختارش مشابه است
    "goldratepric2020": parse_goldrate,
}

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
            parser = PARSERS.get(username, parse_default)

            posts = []

            async for msg in client.iter_messages(entity, limit=limit):
                text = msg.text or ""
                parsed_data = parser(text)

                posts.append({
                    "username": username,
                    "message_id": msg.id,
                    "date": str(msg.date),
                    "text": text,
                    "parsed": parsed_data
                })

            posts.reverse()
            return {
                "username": username,
                "count": len(posts),
                "posts": posts
            }

        except Exception as e:
            return {
                "username": username,
                "error": str(e),
                "count": 0,
                "posts": []
            }

    results = await asyncio.gather(*(get_last_messages(u) for u in usernames))

    return {
        "total_channels": len(results),
        "channels": results
    }
