import os
import logging
import asyncio
import threading
from flask import Flask, request, jsonify
import requests
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')
WEBHOOK_URL = os.getenv('RAILWAY_STATIC_URL', os.getenv('RENDER_EXTERNAL_URL', ''))
PORT = int(os.getenv('PORT', 8080))
HF_SPACE_URL = "https://huggingface.co/spaces/Roljand/Colin_English_Bot"
HF_API_TOKEN = os.getenv('HF_TOKEN', '')

# Initialize Flask app
app = Flask(__name__)

# Global application instance
application = None

class ColinBot:
    def __init__(self):
        self.hf_space_url = HF_SPACE_URL
        self.hf_api_token = HF_API_TOKEN
        self.logger = logging.getLogger(__name__)
        
    def call_huggingface_api(self, user_message):
        """Call HuggingFace Space API with extensive debugging - SYNCHRONOUS VERSION"""
        self.logger.info(f"🚀 === HF API Call Debug Info ===")
        self.logger.info(f"📝 User message: {user_message}")
        self.logger.info(f"🌐 HF Space URL: {self.hf_space_url}")
        
        endpoints = [
            f"{self.hf_space_url}/api/predict",
            f"{self.hf_space_url}/predict",
            f"{self.hf_space_url}/api/generate",
            f"{self.hf_space_url}/generate"
        ]
        
        payloads = [
            {"data": [user_message]},
            {"inputs": user_message},
            {"prompt": user_message},
            {"text": user_message},
            {"message": user_message}
        ]
        
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'ColinBot/1.0'
        }
        
        if self.hf_api_token:
            headers['Authorization'] = f'Bearer {self.hf_api_token}'
            self.logger.info("🔑 Using HF API token")
        else:
            self.logger.info("⚠️  No HF API token provided")
        
        for i, endpoint in enumerate(endpoints):
            for j, payload in enumerate(payloads):
                try:
                    response = requests.post(endpoint, json=payload, headers=headers, timeout=30)
                    if response.status_code == 200:
                        result = response.json()
                        if isinstance(result, dict):
                            if 'data' in result and isinstance(result['data'], list):
                                return result['data'][0] if result['data'] else "No response"
                            elif 'output' in result:
                                return str(result['output'])
                            elif 'generated_text' in result:
                                return result['generated_text']
                            elif 'response' in result:
                                return result['response']
                        elif isinstance(result, list) and result:
                            return str(result[0])
                        elif isinstance(result, str):
                            return result
                        return str(result)
                except requests.exceptions.RequestException as e:
                    self.logger.error(f"🚨 Request error for {endpoint}: {str(e)}")
                    continue
        
        self.logger.warning("🆘 All API attempts failed, using emergency fallback")
        message_lower = user_message.lower()
        if any(greeting in message_lower for greeting in ['hello', 'hi', 'hey']):
            return "Hello! I'm Colin. How can I help you today?"
        else:
            return f"I hear you saying: '{user_message}'. I'm having trouble connecting to my AI model."

# Initialize bot instance
colin_bot = ColinBot()

async def start_command(update: Update, context):
    await update.message.reply_text("🤖 Hello! I'm Colin, your AI assistant! Let's chat!")

async def help_command(update: Update, context):
    await update.message.reply_text("🆘 Just send me any message and I'll respond!")

async def handle_message(update: Update, context):
    user_message = update.message.text
    logger.info(f"💬 Message from {update.effective_user.first_name}: {user_message}")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    ai_response = colin_bot.call_huggingface_api(user_message)
    logger.info(f"🤖 Colin's response: {ai_response}")
    await update.message.reply_text(ai_response)

def process_telegram_update(json_data):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    update = Update.de_json(json_data, application.bot)
    loop.run_until_complete(application.process_update(update))

@app.route('/webhook', methods=['POST'])
def webhook():
    threading.Thread(target=process_telegram_update, args=(request.get_json(force=True),)).start()
    return jsonify({"status": "ok"})

@app.route('/')
def index():
    return jsonify({"status": "active", "bot": "ColinBot"})

def setup_webhook():
    webhook_url = f"https://{WEBHOOK_URL}/webhook"
    logger.info(f"🔗 Setting up webhook: {webhook_url}")
    response = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook", json={"url": webhook_url})
    if response.status_code == 200:
        logger.info("✅ Webhook set successfully!")
    else:
        logger.error(f"❌ Failed to set webhook: {response.text}")

if __name__ == '__main__':
    logger.info(f"🤖 Starting ColinBot with HF Space: {HF_SPACE_URL}")
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    asyncio.run(application.initialize())
    
    if WEBHOOK_URL:
        setup_webhook()
        app.run(host='0.0.0.0', port=PORT)
    else:
        logger.info("🔄 Using POLLING mode")
        application.run_polling()