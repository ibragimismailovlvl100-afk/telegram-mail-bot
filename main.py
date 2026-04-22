import os
import json
import random
import string
from pathlib import Path

import requests
from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================
# НАСТРОЙКИ
# =========================
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
PORT = int(os.environ.get("PORT", 10000))

DATA_FILE = Path("data.json")
MAIL_TM_API = "https://api.mail.tm"

if not TOKEN:
    raise RuntimeError("BOT_TOKEN не задан в Render Environment")

# =========================
# FLASK
# =========================
app = Flask(__name__)

# =========================
# КЛАВИАТУРА
# =========================
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["📧 New Email", "📨 Check Inbox"],
    ],
    resize_keyboard=True,
)

# =========================
# ДАННЫЕ
# =========================
def load_data():
    if DATA_FILE.exists():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"users": {}}

data = load_data()

def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)

def ensure_user(user_id):
    uid = str(user_id)
    if uid not in data["users"]:
        data["users"][uid] = {"mailbox": None}
        save_data()
    return data["users"][uid]

# =========================
# MAIL.TM
# =========================
def create_email():
    domains = requests.get(f"{MAIL_TM_API}/domains").json()["hydra:member"]
    domain = random.choice(domains)["domain"]

    username = "".join(random.choices(string.ascii_lowercase, k=10))
    password = "Qwerty123"

    email = f"{username}@{domain}"

    requests.post(
        f"{MAIL_TM_API}/accounts",
        json={"address": email, "password": password},
    )

    token = requests.post(
        f"{MAIL_TM_API}/token",
        json={"address": email, "password": password},
    ).json()["token"]

    return email, token

def check_mail(token):
    headers = {"Authorization": f"Bearer {token}"}
    data = requests.get(f"{MAIL_TM_API}/messages", headers=headers).json()
    return data.get("hydra:member", [])

# =========================
# TELEGRAM ЛОГИКА
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update.effective_user.id)
    await update.message.reply_text(
        "Выбери действие:",
        reply_markup=MAIN_KEYBOARD,
    )

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = ensure_user(update.effective_user.id)
    text = update.message.text

    if text == "📧 New Email":
        await update.message.reply_text("Создаю почту...")
        email, token = create_email()
        user["mailbox"] = {"email": email, "token": token}
        save_data()
        await update.message.reply_text(f"✅ {email}")

    elif text == "📨 Check Inbox":
        mailbox = user.get("mailbox")
        if not mailbox:
            await update.message.reply_text("Сначала создай почту.")
            return

        messages = check_mail(mailbox["token"])
        if not messages:
            await update.message.reply_text("📭 Писем нет")
            return

        for msg in messages:
            await update.message.reply_text(
                f"📨 Тема: {msg.get('subject')}"
            )

# =========================
# TELEGRAM APP
# =========================
telegram_app = Application.builder().token(TOKEN).build()
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))


@app.route("/", methods=["GET"])
def home():
    return "Bot is running"


@app.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), telegram_app.bot)
    telegram_app.update_queue.put_nowait(update)
    return "ok"


if __name__ == "__main__":
    webhook_url = os.getenv("RENDER_EXTERNAL_URL") + "/webhook"

    # Создаем цикл событий
    loop = asyncio.get_event_loop()

    # Инициализируем и запускаем бота
    loop.run_until_complete(telegram_app.initialize())
    loop.run_until_complete(telegram_app.bot.set_webhook(webhook_url))
    loop.run_until_complete(telegram_app.start())

    # Запускаем Flask (этот метод блокирующий, он будет крутиться бесконечно)
    app.run(host="0.0.0.0", port=PORT)
