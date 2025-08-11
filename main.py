import os
import logging
import json
import requests
import random
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import asyncio

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Get environment variables
BOT_TOKEN = os.getenv('BOT_TOKEN')
WEBHOOK_HOST = os.getenv('WEBHOOK_HOST')
HF_SPACE_URL = os.getenv('HF_SPACE_URL')

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required")

# Initialize bot
bot = Bot(token=BOT_TOKEN)

# User conversation history and context storage
user_conversations = {}
user_contexts = {}

class UserContext:
    def __init__(self):
        self.level = "beginner"
        self.interests = []
        self.conversation_count = 0
        self.last_active = datetime.now()
        self.learning_goals = []
        self.mistakes = []
        self.topics_covered = []

def get_user_context(user_id):
    """Get or create user context"""
    if user_id not in user_contexts:
        user_contexts[user_id] = UserContext()
    return user_contexts[user_id]

def update_user_context(user_id, message):
    """Update user context based on message"""
    context = get_user_context(user_id)
    context.conversation_count += 1
    context.last_active = datetime.now()

def call_hf_space_api(prompt):
    """Call HuggingFace Space API with extensive debugging"""
    
    logger.info(f"🚀 === HF API Call Debug Info ===")
    logger.info(f"📝 Prompt: '{prompt}'")
    logger.info(f"🔗 HF_SPACE_URL: {HF_SPACE_URL}")
    
    if not HF_SPACE_URL:
        logger.error("❌ HF_SPACE_URL environment variable not set!")
        return None
    
    # Try multiple API endpoints that might work with Gradio
    api_endpoints = [
        f"{HF_SPACE_URL.rstrip('/')}/api/predict",
        f"{HF_SPACE_URL.rstrip('/')}/run/predict",
        f"{HF_SPACE_URL.rstrip('/')}/call/predict"
    ]
    
    for endpoint in api_endpoints:
        logger.info(f"🎯 Trying endpoint: {endpoint}")
        
        try:
            # Try different payload formats that Gradio might accept
            payloads = [
                {"data": [prompt]},  # Simple format
                {"data": [prompt, 150, 0.7]},  # With parameters
                {"inputs": prompt},  # Alternative format
                {"prompt": prompt, "max_length": 150, "temperature": 0.7}  # Direct format
            ]
            
            for i, payload in enumerate(payloads):
                logger.info(f"📦 Trying payload format {i+1}: {payload}")
                
                headers = {
                    'Content-Type': 'application/json',
                    'User-Agent': 'Colin-Bot/1.0'
                }
                
                response = requests.post(
                    endpoint,
                    json=payload,
                    headers=headers,
                    timeout=30
                )
                
                logger.info(f"📊 Response status: {response.status_code}")
                logger.info(f"📋 Response headers: {dict(response.headers)}")
                
                if response.status_code == 200:
                    try:
                        result = response.json()
                        logger.info(f"✅ Raw API response: {json.dumps(result, indent=2)}")
                        
                        # Try to extract response from different possible formats
                        possible_responses = [
                            result.get('data', [None])[0] if 'data' in result else None,
                            result.get('output'),
                            result.get('generated_text'),
                            result.get('response'),
                            result if isinstance(result, str) else None
                        ]
                        
                        for response_text in possible_responses:
                            if response_text and isinstance(response_text, str) and len(response_text.strip()) > 0:
                                logger.info(f"🎉 SUCCESS! Extracted response: {response_text}")
                                return response_text.strip()
                        
                    except json.JSONDecodeError as e:
                        # Maybe it's plain text response?
                        if len(response.text.strip()) > 0:
                            logger.info(f"📄 Plain text response: {response.text}")
                            return response.text.strip()
                        else:
                            logger.error(f"💥 JSON decode error: {e}")
                
                elif response.status_code == 404:
                    logger.warning(f"⚠️ Endpoint not found: {endpoint}")
                    break  # Try next endpoint
                else:
                    logger.error(f"❌ HTTP {response.status_code}: {response.text[:200]}...")
                    
        except requests.exceptions.Timeout:
            logger.error(f"⏰ Timeout for endpoint: {endpoint}")
            continue
            
        except requests.exceptions.ConnectionError as e:
            logger.error(f"🔌 Connection error for {endpoint}: {e}")
            continue
            
        except Exception as e:
            logger.error(f"💥 Unexpected error for {endpoint}: {e}")
            continue
    
    logger.error("😞 All API attempts failed")
    return None

def get_emergency_fallback(message_text, user_context):
    """Emergency fallback when API completely fails"""
    message_lower = message_text.lower()
    
    # Try to give somewhat intelligent responses based on keywords
    if any(word in message_lower for word in ['hello', 'hi', 'hey']):
        return "Hello! I'm Colin, your English tutor. I'd love to help you practice English today! What would you like to talk about?"
    
    if any(word in message_lower for word in ['how', 'what', 'where', 'when', 'why', 'who']):
        return f"That's a great question! You asked: '{message_text}'. I think that shows good curiosity. Can you tell me more about what you're thinking?"
    
    if any(word in message_lower for word in ['cat', 'cats']):
        return "Cats are wonderful pets! They're independent and playful. Do you have a cat? What's your cat like?"
    
    if any(word in message_lower for word in ['dog', 'dogs']):
        return "Dogs are amazing companions! They're loyal and friendly. Tell me about your experience with dogs!"
    
    if any(word in message_lower for word in ['food', 'eat', 'hungry']):
        return "Food is always an interesting topic! What's your favorite type of food? Can you describe a meal you really enjoyed?"
    
    if '?' in message_text:
        return f"You asked a question about '{message_text}'. That's great for practicing English! Questions help us learn. What do you think the answer might be?"
    
    # Default intelligent response
    return f"I understand you said: '{message_text}'. That's interesting! Can you tell me more details about that? I'd love to learn about your thoughts."

def generate_ai_reply(message_text, user_context):
    """Generate AI reply with HF API and smart fallback"""
    
    logger.info(f"🤖 Generating AI reply for: '{message_text}'")
    
    try:
        # First try the HF Space API
        api_response = call_hf_space_api(message_text)
        
        if api_response and len(api_response.strip()) > 5:
            logger.info(f"✅ Using HF API response: {api_response[:100]}...")
            return api_response.strip()
        else:
            logger.warning("⚠️ HF API failed or returned empty response, using intelligent fallback")
            
    except Exception as e:
        logger.error(f"💥 Exception in API call: {e}")
    
    # Use intelligent fallback
    fallback_response = get_emergency_fallback(message_text, user_context)
    logger.info(f"🆘 Using emergency fallback: {fallback_response[:50]}...")
    return fallback_response

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user_id = update.effective_user.id
    user_context = get_user_context(user_id)
    
    welcome_message = """
🌟 Hello! I'm Colin, your AI English learning companion! 

I'm here to help you:
📚 Practice English conversation
✍️ Improve your grammar
🗣️ Build confidence in speaking
🌍 Learn about different topics

Just start chatting with me in English! I'll respond naturally and help you learn.

Type /help anytime for more information.
"""
    
    await update.message.reply_text(welcome_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_message = """
🤖 I'm Colin, your AI English teacher bot!

📝 Commands:
• /start - Welcome message
• /help - Show this help
• /clear - Clear conversation history
• /level - Set your English level

💬 How to use me:
• Just chat with me in English!
• Ask me questions about anything
• Tell me about your interests
• Practice describing things
• Don't worry about mistakes - I'm here to help!

🎯 Tips:
• Try to write complete sentences
• Ask me to explain words you don't know  
• Tell me about your day, hobbies, or dreams
• The more you practice, the better you'll get!

Ready to practice? Send me a message! 🚀
"""
    
    await update.message.reply_text(help_message)

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /clear command"""
    user_id = update.effective_user.id
    
    # Clear user's conversation history
    if user_id in user_conversations:
        del user_conversations[user_id]
    
    # Reset user context but keep learning progress
    if user_id in user_contexts:
        old_context = user_contexts[user_id]
        user_contexts[user_id] = UserContext()
        user_contexts[user_id].level = old_context.level
        user_contexts[user_id].interests = old_context.interests
    
    await update.message.reply_text(
        "✨ Conversation history cleared! 📚 Let's start fresh - send me a message to begin a new conversation! 🚀"
    )

async def level_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /level command"""
    user_id = update.effective_user.id
    user_context = get_user_context(user_id)
    
    if context.args:
        level = context.args[0].lower()
        if level in ['beginner', 'intermediate', 'advanced']:
            user_context.level = level
            await update.message.reply_text(f"✅ Your level is now set to: {level.capitalize()}! 📊")
        else:
            await update.message.reply_text("Please use: /level beginner, /level intermediate, or /level advanced")
    else:
        await update.message.reply_text(f"📊 Your current level: {user_context.level.capitalize()}\n\nTo change: /level [beginner/intermediate/advanced]")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular messages with AI responses"""
    try:
        user_id = update.effective_user.id
        message_text = update.message.text
        user_name = update.effective_user.first_name or "Student"
        
        logger.info(f"📨 Message from {user_name} (ID: {user_id}): '{message_text}'")
        
        # Get or create user context
        user_context = get_user_context(user_id)
        
        # Update user context
        update_user_context(user_id, message_text)
        
        # Initialize conversation history if not exists
        if user_id not in user_conversations:
            user_conversations[user_id] = []
        
        # Add user message to conversation history
        user_conversations[user_id].append({
            'role': 'user',
            'content': message_text,
            'timestamp': datetime.now()
        })
        
        # Keep only last 10 messages to prevent memory issues
        if len(user_conversations[user_id]) > 20:
            user_conversations[user_id] = user_conversations[user_id][-10:]
        
        # Generate AI response
        reply = generate_ai_reply(message_text, user_context)
        
        # Add bot response to conversation history
        user_conversations[user_id].append({
            'role': 'assistant',
            'content': reply,
            'timestamp': datetime.now()
        })
        
        # Send reply
        await update.message.reply_text(reply)
        
        logger.info(f"📤 Sent reply to {user_name}: '{reply[:100]}...'")
        
    except Exception as e:
        logger.error(f"💥 Error handling message: {e}")
        await update.message.reply_text(
            "I'm having a small technical issue, but I'm still here to help you! 🤖 Try sending your message again!"
        )

# Flask webhook endpoint
@app.route(f'/webhook/{BOT_TOKEN}', methods=['POST'])
def webhook():
    """Handle webhook updates"""
    try:
        json_data = request.get_json()
        logger.info(f"📨 Webhook received message")
        
        if json_data:
            update = Update.de_json(json_data, bot)
            
            # Run the update in the asyncio event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Create application instance for handling updates
            application = Application.builder().token(BOT_TOKEN).build()
            
            # Add handlers
            application.add_handler(CommandHandler("start", start_command))
            application.add_handler(CommandHandler("help", help_command))
            application.add_handler(CommandHandler("clear", clear_command))
            application.add_handler(CommandHandler("level", level_command))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
            
            # Process the update
            loop.run_until_complete(application.process_update(update))
            loop.close()
            
        return jsonify({"status": "ok"})
        
    except Exception as e:
        logger.error(f"💥 Webhook error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "bot_token_configured": bool(BOT_TOKEN),
        "hf_space_url_configured": bool(HF_SPACE_URL),
        "webhook_host_configured": bool(WEBHOOK_HOST)
    })

@app.route('/', methods=['GET'])
def home():
    """Home endpoint"""
    return jsonify({
        "service": "Colin English Learning Bot",
        "status": "running",
        "endpoints": {
            "webhook": f"/webhook/{BOT_TOKEN}",
            "health": "/health"
        }
    })

def setup_webhook():
    """Set up webhook using requests to avoid async issues"""
    if not WEBHOOK_HOST:
        logger.warning("⚠️ WEBHOOK_HOST not configured - webhook setup skipped")
        return
        
    try:
        webhook_url = f"{WEBHOOK_HOST}/webhook/{BOT_TOKEN}"
        telegram_api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
        
        logger.info(f"🔗 Setting webhook to: {webhook_url}")
        
        response = requests.post(telegram_api_url, json={'url': webhook_url}, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('ok'):
                logger.info(f"✅ Webhook successfully set!")
            else:
                logger.error(f"❌ Telegram API error: {result}")
        else:
            logger.error(f"❌ Failed to set webhook. Status: {response.status_code}")
        
    except Exception as e:
        logger.error(f"💥 Failed to set webhook: {e}")

if __name__ == "__main__":
    logger.info("🚀 Starting Colin English Learning Bot...")
    
    # Set up webhook
    setup_webhook()
    
    # Start Flask app
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"🌐 Starting Flask server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
