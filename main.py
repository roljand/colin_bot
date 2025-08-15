import os
import logging
import asyncio
from flask import Flask, request, jsonify
import requests
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# --- Basic Configuration ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("RAILWAY_STATIC_URL")
HF_SPACE_URL = "https://huggingface.co/spaces/Roljand/Colin_English_Bot"
HF_API_TOKEN = os.getenv("HF_TOKEN")

# --- Bot Logic ---
def get_ai_response(user_message: str) -> str:
    """Calls the Hugging Face Space to get a response."""
    try:
        response = requests.post(
            f"{HF_SPACE_URL}/api/predict",
            json={"data": [user_message]},
            headers={"Authorization": f"Bearer {HF_API_TOKEN}" if HF_API_TOKEN else ""},
            timeout=30,
        )
        if response.status_code == 200:
            result = response.json()
            return result.get("data", ["Sorry, I had a problem."])[0]
    except requests.exceptions.RequestException as e:
        logger.error(f"HF API call failed: {e}")
    return "I'm having some trouble connecting right now. Please try again in a moment."

async def start_command(update: Update, context) -> None:
    await update.message.reply_text("🤖 Hello! I'm Colin, your AI assistant! Let's chat!")

async def help_command(update: Update, context) -> None:
    await update.message.reply_text("🆘 Just send me any message and I'll respond!")

async def handle_message(update: Update, context) -> None:
    user_message = update.message.text
    logger.info(f"Message from {update.effective_user.first_name}: {user_message}")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    ai_response = get_ai_response(user_message)
    await update.message.reply_text(ai_response)

# --- Web App and Bot Initialization ---
# Initialize the bot application first
application = Application.builder().token(BOT_TOKEN).build()
application.add_handler(CommandHandler("start", start_command))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# Initialize Flask app
app = Flask(__name__)

@app.route("/")
def index():
    """A simple health check endpoint."""
    return jsonify({"status": "active", "bot": "ColinBot"})

@app.route("/webhook", methods=["POST"])
async def webhook():
    """Handles incoming Telegram updates."""
    update = Update.de_json(request.get_json(force=True), application.bot)
    await application.process_update(update)
    return jsonify({"status": "ok"})

# --- Main Execution ---
def main() -> None:
    """Sets up the webhook and prepares the application to be run by Gunicorn."""
    if not WEBHOOK_URL:
        logger.error("RAILWAY_STATIC_URL environment variable not set!")
        return

    loop = asyncio.get_event_loop()
    # Initialize the bot and set the webhook
    loop.run_until_complete(application.initialize())
    loop.run_until_complete(application.bot.set_webhook(url=f"https://{WEBHOOK_URL}/webhook"))
    logger.info(f"Webhook set up at https://{WEBHOOK_URL}/webhook")

# This block runs once when the application starts on Railway
main()
