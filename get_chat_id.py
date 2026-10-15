"""Send any message to your bot in Telegram first, then run this to print your chat ID."""
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
if not token:
    sys.exit("Put TELEGRAM_BOT_TOKEN in .env first (get it from @BotFather).")

resp = requests.get("https://api.telegram.org/bot{}/getUpdates".format(token), timeout=15).json()
if not resp.get("ok"):
    sys.exit("Telegram error: {}".format(resp))

chats = {}
for update in resp["result"]:
    msg = update.get("message") or update.get("channel_post") or {}
    chat = msg.get("chat")
    if chat:
        chats[chat["id"]] = chat.get("username") or chat.get("title") or chat.get("first_name")

if not chats:
    sys.exit("No messages found. Open your bot in Telegram, send it 'hi', then run this again.")
for chat_id, name in chats.items():
    print("TELEGRAM_CHAT_ID={}   ({})".format(chat_id, name))
