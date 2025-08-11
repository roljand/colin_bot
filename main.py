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
import threading

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
    
    # Simple interest detection
    interests_keywords = {
        'sports': ['football', 'soccer', 'basketball', 'tennis', 'gym', 'workout'],
        'movies': ['movie', 'film', 'cinema', 'actor', 'actress', 'director'],
        'music': ['song', 'music', 'band', 'singer', 'concert', 'album'],
        'travel': ['travel', 'trip', 'vacation', 'country', 'city', 'visit'],
        'food': ['food', 'restaurant', 'cook', 'recipe', 'eat', 'meal'],
        'technology': ['computer', 'phone', 'internet', 'app', 'software']
    }
    
    message_lower = message.lower()
    for interest, keywords in interests_keywords.items():
        if any(keyword in message_lower for keyword in keywords):
            if interest not in context.interests:
                context.interests.append(interest)

def call_hf_space_api(prompt, max_length=150, temperature=0.7):
    """Call HuggingFace Space API with proper error handling and debugging"""
    
    hf_space_url = HF_SPACE_URL
    
    logger.info(f"=== HF API Call Debug Info ===")
    logger.info(f"HF_SPACE_URL: {hf_space_url}")
    logger.info(f"Prompt: {prompt[:50]}...")
    logger.info(f"Max length: {max_length}, Temperature: {temperature}")
    
    if not hf_space_url:
        logger.error("HF_SPACE_URL environment variable not set!")
        return None
    
    # Construct the API endpoint
    api_endpoint = f"{hf_space_url.rstrip('/')}/api/predict"
    logger.info(f"API Endpoint: {api_endpoint}")
    
    try:
        # Prepare the payload in the format Gradio expects
        payload = {
            "data": [
                prompt,           # First input: prompt
                max_length,       # Second input: max_length  
                temperature       # Third input: temperature
            ]
        }
        
        logger.info(f"Payload: {json.dumps(payload, indent=2)}")
        
        # Make the request with proper headers and timeout
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Colin-Bot/1.0'
        }
        
        logger.info(f"Making request to {api_endpoint}...")
        
        response = requests.post(
            api_endpoint,
            json=payload,
            headers=headers,
            timeout=30  # 30 second timeout
        )
        
        logger.info(f"Response status: {response.status_code}")
        logger.info(f"Response headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            try:
                result = response.json()
                logger.info(f"Raw API response: {json.dumps(result, indent=2)}")
                
                # Extract the response from Gradio format
                if 'data' in result and len(result['data']) > 0:
                    generated_text = result['data'][0]
                    logger.info(f"Extracted text: {generated_text}")
                    return generated_text
                else:
                    logger.error(f"Unexpected response format: {result}")
                    return None
                    
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response: {e}")
                logger.error(f"Raw response: {response.text}")
                return None
                
        else:
            logger.error(f"API request failed with status {response.status_code}")
            logger.error(f"Response text: {response.text}")
            return None
            
    except requests.exceptions.Timeout:
        logger.error("Request timed out after 30 seconds")
        return None
        
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error: {e}")
        return None
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Request exception: {e}")
        return None
        
    except Exception as e:
        logger.error(f"Unexpected error in API call: {e}")
        return None

def get_contextual_fallback(message_text, user_context):
    """Generate contextual fallback responses"""
    message_lower = message_text.lower()
    
    # Greeting responses
    if any(word in message_lower for word in ['hello', 'hi', 'hey', 'good morning', 'good afternoon']):
        greetings = [
            "Hi there! 😊 What would you like to talk about?",
            "Hello! I'm excited to help you practice English today! 🌟",
            "Hey! 🌟 How can I help you practice English?",
            "Good to see you! Let's have a great English conversation! ✨"
        ]
        return random.choice(greetings)
    
    # Help requests
    if any(word in message_lower for word in ['help', 'assist', 'support']):
        help_responses = [
            "I'm here to help! We can practice conversation, work on grammar, or discuss any topic you like! 💪",
            "Of course! I can help you with speaking practice, grammar questions, or just casual conversation! 🎯",
            "I'd love to help you improve your English! What would you like to work on? 📚"
        ]
        return random.choice(help_responses)
    
    # Grammar/learning requests
    if any(word in message_lower for word in ['grammar', 'learn', 'study', 'practice']):
        grammar_responses = [
            "Grammar practice is great! Feel free to write sentences and I'll help you improve them! ✍️",
            "Let's work on your English together! Try writing about something you enjoy! 📝",
            "Perfect! The best way to learn is through practice. Tell me about your day! 🗣️"
        ]
        return random.choice(grammar_responses)
    
    # Questions about topics
    if '?' in message_text:
        question_responses = [
            "That's a great question! Let me think about that... 🤔",
            "Interesting question! I'd love to discuss that with you! 💭",
            "Good question! What are your thoughts on this? 🎯"
        ]
        return random.choice(question_responses)
    
    # General encouragement based on user context
    if user_context.conversation_count > 10:
        advanced_responses = [
            "Your English is really improving! I can see your progress! 📈",
            "You're becoming more confident with English! Keep it up! 🚀",
            "I'm impressed by your English skills! Let's keep practicing! ⭐"
        ]
        return random.choice(advanced_responses)
    
    # Default responses
    general_responses = [
        "That's interesting! Tell me more about that! 🗨️",
        "I'd love to hear more about your thoughts on this! 💬",
        "That's well expressed! 👌",
        "You're communicating clearly! 🎯",
        "Great! What else would you like to discuss? 🌟",
        "That's a good way to put it! What do you think about...? 💭",
        "I enjoy our conversation! What's on your mind? 😊"
    ]
    
    return random.choice(general_responses)

def generate_phi3_reply(message_text, user_context):
    """Generate reply using HF Space API with fallback"""
    
    logger.info(f"=== Generating reply for: {message_text[:50]}... ===")
    
    try:
        # Call the HF Space API
        api_response = call_hf_space_api(message_text, max_length=150, temperature=0.7)
        
        if api_response and len(api_response.strip()) > 0:
            logger.info(f"✅ API Success! Response: {api_response[:100]}...")
            return api_response.strip()
        else:
            logger.warning("❌ API returned empty/null response, using fallback")
            
    except Exception as e:
        logger.error(f"❌ Exception in generate_phi3_reply: {e}")
    
    # Fallback to contextual response
    logger.info("Using contextual fallback response")
    return get_contextual_fallback(message_text, user_context)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user_id = update.effective_user.id
    user_context = get_user_context(user_id)
    
    welcome_message = """
🌟 Hello! I'm Colin, your English learning companion! 

I'm here to help you:
📚 Practice English conversation
✍️ Improve your grammar
🗣️ Build confidence in speaking
🌍 Learn about different topics

Just start chatting with me in English! I'll help you learn naturally through conversation.

Type /help anytime for more information.
"""
    
    await update.message.reply_text(welcome_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_message = """
🤖 I'm Colin, your English teacher bot!

📝 Commands:
• /start - Welcome message
• /help - Show this help
• /clear - Clear conversation history
• /level - Set your English level

💬 How to use me:
• Just chat with me in English!
• Ask me questions about grammar
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
        user_contexts[user_id].level = old_context.level  # Keep level
        user_contexts[user_id].interests = old_context.interests  # Keep interests
    
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
    """Handle regular messages"""
    try:
        user_id = update.effective_user.id
        message_text = update.message.text
        user_name = update.effective_user.first_name or "Student"
        
        logger.info(f"Received message from {user_name} (ID: {user_id}): {message_text[:50]}...")
        
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
        
        # Generate response
        reply = generate_phi3_reply(message_text, user_context)
        
        # Add bot response to conversation history
        user_conversations[user_id].append({
            'role': 'assistant',
            'content': reply,
            'timestamp': datetime.now()
        })
        
        # Send reply
        await update.message.reply_text(reply)
        
        logger.info(f"Sent reply to {user_name}: {reply[:50]}...")
        
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        await update.message.reply_text(
            "I'm having a small technical issue, but I'm still here to help you! 🤖 Try sending your message again!"
        )

# Flask webhook endpoint
@app.route(f'/webhook/{BOT_TOKEN}', methods=['POST'])
def webhook():
    """Handle webhook updates"""
    try:
        json_data = request.get_json()
        logger.info(f"📨 Webhook received: {json_data}")
        
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
        logger.error(f"Webhook error: {e}")
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
    """Set up webhook for the bot - FIXED VERSION"""
    if not WEBHOOK_HOST:
        logger.warning("WEBHOOK_HOST not configured - webhook setup skipped")
        return
        
    try:
        webhook_url = f"{WEBHOOK_HOST}/webhook/{BOT_TOKEN}"
        
        # Set webhook using requests instead of bot.set_webhook() to avoid async issues
        telegram_api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
        
        response = requests.post(telegram_api_url, json={'url': webhook_url})
        
        if response.status_code == 200:
            result = response.json()
            if result.get('ok'):
                logger.info(f"✅ Webhook successfully set to: {webhook_url}")
            else:
                logger.error(f"❌ Telegram API error: {result}")
        else:
            logger.error(f"❌ Failed to set webhook. Status: {response.status_code}, Response: {response.text}")
        
    except Exception as e:
        logger.error(f"Failed to set webhook: {e}")

if __name__ == "__main__":
    # Set up webhook
    setup_webhook()
    
    # Start Flask app
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
