"""Find your Telegram chat ID and send a test alert. A bot can't message a phone number: open your bot in Telegram,
tap Start (or send it any message), then run from backend/:

    python scripts/telegram_setup.py <bot-token>

It prints the TELEGRAM_CHAT_ID line to put in .env (and on Render) next to TELEGRAM_BOT_TOKEN.
"""
import sys

import requests

if len(sys.argv) != 2:
    sys.exit(__doc__)
token = sys.argv[1].strip()
me = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=15).json()
if not me.get("ok"):
    sys.exit("Telegram refused that token. Copy it again from @BotFather.")
updates = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=15).json().get("result", [])
chats = {u["message"]["chat"]["id"]: u["message"]["chat"].get("first_name", "") for u in updates if "message" in u}
if not chats:
    sys.exit(f"No messages yet. Open https://t.me/{me['result']['username']} in Telegram, tap Start, then run this again.")
for chat_id, name in chats.items():
    requests.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=15,
                  json={"chat_id": chat_id, "text": "FINN is connected. Alerts will arrive here."})
    print(f"{name}: TELEGRAM_CHAT_ID={chat_id}  (test message sent)")
