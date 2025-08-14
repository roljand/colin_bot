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
        
        # API endpoints to try
        endpoints = [
            f"{self.hf_space_url}/api/predict",
            f"{self.hf_space_url}/predict",
            f"{self.hf_space_url}/api/generate",
            f"{self.hf_space_url}/generate"
        ]
        
        # Different payload formats to try
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
        
        # Try different combinations
        for i, endpoint in enumerate(endpoints):
            for j, payload in enumerate(payloads):
                try:
                    self.logger.info(f"🔄 Attempt {i+1}.{j+1}: {endpoint}")
                    self.logger.info(f"📦 Payload: {payload}")
                    
                    response = requests.post(
                        endpoint,
                        json=payload,
                        headers=headers,
                        timeout=30
                    )
                    
                    self.logger.info(f"📊 Status: {response.status_code}")
                    self.logger.info(f"📋 Headers: {dict(response.headers)}")
                    
                    if response.status_code == 200:
                        result = response.json()
                        self.logger.info(f"✅ Success! Response: {result}")
                        
                        # Try to extract text from different response formats
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
                    else:
                        response_text = response.text[:500]
                        self.logger.warning(f"❌ Failed: {response.status_code} - {response_text}")
                        
                except requests.exceptions.RequestException as e:
                    self.logger.error(f"🚨 Request error for {endpoint}: {str(e)}")
                    continue
                except Exception as e:
                    self.logger.error(f"🚨 Unexpected error: {str(e)}")
                    continue
        
        # Emergency fallback with contextual responses
        self.logger.warning("🆘 All API attempts failed, using emergency fallback")
        
        # Simple contextual responses based on message content
        message_lower = user_message.lower()
        
        if any(greeting in message_lower for greeting in ['hello', 'hi', 'hey', 'good morning', 'good afternoon']):
            return "Hello! I'm Colin. How can I help you today? (Note: I'm currently having trouble connecting to my AI model, but I'm working on it!)"
        elif any(question in message_lower for question in ['how are you', 'what\'s up', 'how do you do']):
            return "I'm doing well, thank you for asking! Though I'm having some technical difficulties right now. What can I help you with?"
        elif 'help' in message_lower:
            return "I'm Colin, your AI assistant! I can help with questions, conversations, and various tasks. I'm currently experiencing some connectivity issues, but feel free to ask me anything!"
        elif any(farewell in message_lower for farewell in ['bye', 'goodbye', 'see you', 'farewell']):
            return "Goodbye! Have a great day! 👋"
        else:
            return f"I hear you saying: '{user_message}'. I'm currently having trouble connecting to my full AI capabilities, but I'm working on fixing this issue!"

# Initialize bot instance
colin_bot = ColinBot()

async def start_command(update: Update, context):
    """Handle /start command"""
    welcome_message = """
🤖 Hello! I'm Colin, your AI assistant!

I can help you with:
• Answering questions
• Having conversations  
• Providing information
• And much more!

Just send me a message and I'll respond. Let's chat!
    """
    await update.message.reply_text(welcome_message)

async def help_command(update: Update, context):
    """Handle /help command"""
    help_message = """
🆘 Colin Bot Help

Commands:
• /start - Start the bot
• /help - Show this help message

Just send me any message and I'll respond! I'm powered by AI and ready to chat.

Having issues? The bot is constantly being improved!
    """
    await update.message.reply_text(help_message)

async def handle_message(update: Update, context):
    """Handle regular messages"""
    user_message = update.message.text
    user_name = update.effective_user.first_name
    
    logger.info(f"💬 Message from {user_name}: {user_message}")
    
    try:
        # Show typing indicator
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        # Get AI response (synchronous call)
        ai_response = colin_bot.call_huggingface_api(user_message)
        
        logger.info(f"🤖 Colin's response: {ai_response}")
        
        # Send response
        await update.message.reply_text(ai_response)
        
    except Exception as e:
        logger.error(f"🚨 Error in handle_message: {str(e)}")
        await update.message.reply_text(
            "Sorry, I'm experiencing technical difficulties right now. Please try again in a moment! 🔧"
        )

def process_telegram_update(json_data):
    """Process Telegram update in a separate thread"""
    def run_update():
        try:
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Parse the update
            update = Update.de_json(json_data, application.bot)
            logger.info(f"📨 Processing update from {update.effective_user.first_name if update.effective_user else 'Unknown'}")
            
            # Process the update
            loop.run_until_complete(application.process_update(update))
            
        except Exception as e:
            logger.error(f"🚨 Error processing update: {str(e)}")
        finally:
            loop.close()
    
    # Run in background thread
    thread = threading.Thread(target=run_update, daemon=True)
    thread.start()

# Flask webhook endpoint
@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    """Handle incoming webhooks from Telegram"""
    try:
        json_data = request.get_json(force=True)
        logger.info(f"📨 Received webhook data: {json_data}")
        
        # Process update in background thread
        process_telegram_update(json_data)
        
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.error(f"🚨 Webhook error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/')
def index():
    """Health check endpoint"""
    return jsonify({
        "status": "active",
        "bot": "ColinBot",
        "version": "2.1",
        "hf_space": HF_SPACE_URL
    })

@app.route('/health')
def health():
    """Health check"""
    return jsonify({"status": "healthy"})

def setup_webhook():
    """Setup webhook with Telegram"""
    webhook_url = f"https://{WEBHOOK_URL}/{BOT_TOKEN}"
    
    logger.info(f"🔗 Setting up webhook: {webhook_url}")
    
    try:
        # Delete existing webhook first
        delete_url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook"
        requests.post(delete_url)
        logger.info("🗑️  Deleted existing webhook")
        
        # Set new webhook
        set_webhook_url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
        response = requests.post(set_webhook_url, json={"url": webhook_url})
        
        if response.status_code == 200:
            logger.info("✅ Webhook set successfully!")
            return True
        else:
            logger.error(f"❌ Failed to set webhook: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"🚨 Webhook setup error: {str(e)}")
        return False

if __name__ == '__main__':
    logger.info(f"🤖 Starting ColinBot with HF Space: {HF_SPACE_URL}")
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Initialize the application
    asyncio.run(application.initialize())
    
    # Setup webhook if WEBHOOK_URL is provided, otherwise use polling
    if WEBHOOK_URL:
        logger.info(f"🌐 Using WEBHOOK mode with URL: {WEBHOOK_URL}")
        setup_webhook()
        
        # Run Flask app
        app.run(host='0.0.0.0', port=PORT, debug=False)
    else:
        logger.info("🔄 Using POLLING mode (for local development)")
        application.run_polling()
