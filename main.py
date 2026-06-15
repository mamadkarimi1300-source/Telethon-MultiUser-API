from fastapi import FastAPI
from telethon import TelegramClient
import asyncio,re

api_id=34216039
api_hash="aeafe65f91b250c95d3a443a4f7dbf06"

app=FastAPI()
client=TelegramClient("mysession",api_id,api_hash)

def normalize(text:str)->str:
    if not text:return ""
    text=text.replace("`","")
    text=re.sub(r"[\u200c\u200f\u202a-\u202e\u0640]","",text)
    text=re.sub(r"\s+"," ",text)
    return text.strip()

def to_int(v):
    try:return int(str(v).replace(",","").strip())
    except:return None

def price(v):
    x=to_int(v)
    return x if x else 0

def extract(pattern,text):
    m=re.search(pattern,text,re.I|re.S)
    return m.group(1) if m else None

def clean_footer(text):
    if not text:return ""
    text=re.sub(r"^.*Just\s*In\s*Time.*$","",text,flags=re.I|re.M)
    text=re.sub(r"^@\w+.*$","",text,flags=re.M)
    text=re.sub(r"t\.me/\S+","",text)
    return text.strip()

def parse_hareta(text):
    text=normalize(text)
    sell=re.search(r"(?:🔴|فروشنده|فروش)\s*([\d,]+)|([\d,]+)\s*(?:فروشنده|فروش)",text)
    buy=re.search(r"(?:🔵|خریدار|خرید)\s*([\d,]+)|([\d,]+)\s*(?:خریدار|خرید)",text)
    s=(sell.group(1) or sell.group(2)) if sell else None
    b=(buy.group(1) or buy.group(2)) if buy else None
    return {"sell_price":price(s),"buy_price":price(b)}

def parse_farda(text):
    text=normalize(text)
    sell=extract(r"فروش.*?دلار[:\s]+([\d,]+)",text)
    buy=extract(r"خرید.*?دلار[:\s]+([\d,]+)",text)
    return {"sell_price":price(sell),"buy_price":price(buy)}

def parse_abshdh(text):
    text=clean_footer(normalize(text))
    p=extract(r"آ?بشده[^\d\n]*([\d,]+)",text)
    return {"sell_price":price(p),"buy_price":0}

def parse_qeymat(text):
    text=normalize(text)
    sell=extract(r"([\d,]+)[^\n]*فروش",text)
    buy=extract(r"([\d,]+)[^\n]*خرید",text)
    return {"sell_price":price(sell),"buy_price":price(buy)}

def parse_gold(text):
    text=normalize(text)
    p=extract(r"(\d+(?:\.\d+)?)",text)
    return {"sell_price":float(p) if p else 0,"buy_price":0}

def parse_default(text):
    return {"sell_price":0,"buy_price":0}

PARSERS={
"fardaedolar":parse_farda,
"Hareta_Dollar_Bloe":parse_hareta,
"abshdh":parse_abshdh,
"Qeymatabshodeh":parse_qeymat,
"NaghdP":parse_qeymat,
"goldratepric2020":parse_gold
}

@app.on_event("startup")
async def startup():
    await client.start()

@app.on_event("shutdown")
async def shutdown():
    await client.disconnect()

@app.get("/")
async def read_root(limit:int=10):

    usernames=[
        "fardaedolar",
        "Hareta_Dollar_Bloe",
        "abshdh",
        "Qeymatabshodeh",
        "NaghdP",
        "goldratepric2020"
    ]

    async def get_channel(username:str):
        try:
            entity=await client.get_entity(username)
            parser=PARSERS.get(username,parse_default)
            posts=[]
            last_sell=0
            last_buy=0

            async for msg in client.iter_messages(entity,limit=limit):
                text=msg.text or ""
                parsed=parser(text)

                if parsed["sell_price"]:last_sell=parsed["sell_price"]
                if parsed["buy_price"]:last_buy=parsed["buy_price"]

                posts.append({
                    "message_id":msg.id,
                    "date":str(msg.date),
                    "parsed":parsed
                })

            posts.reverse()

            return{
                "username":username,
                "latest_prices":{"sell_price":last_sell,"buy_price":last_buy},
                "count":len(posts),
                "posts":posts
            }

        except Exception as e:
            return{"username":username,"error":str(e)}

    results=await asyncio.gather(*(get_channel(u) for u in usernames))

    return{
        "total_channels":len(results),
        "channels":results
    }

@app.get("/username/{username}")
async def read_root(username: str):
    entity = await client.get_entity(username)

    messages = []
    async for msg in client.iter_messages(entity, limit=20):
        messages.append({
            "id": msg.id,
            "text": msg.text,
            "date": str(msg.date)
        })

    return {"messages": messages}
