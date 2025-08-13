import os
import logging
from flask import Flask, request, jsonify
import requests
from telegram import Bot

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')
WEBHOOK_URL = os.getenv('RAILWAY_STATIC_URL', os.getenv('RENDER_EXTERNAL_URL', ''))
PORT = int(os.getenv('PORT', 8080))
HF_SPACE_URL = "https://roljand-colin-bot.hf.space"
HF_API_TOKEN = os.getenv('HF_TOKEN', '')

# Initialize Flask app and Bot
app = Flask(__name__)
bot = Bot(BOT_TOKEN)

class ColinBot:
    def __init__(self):
        self.hf_space_url = HF_SPACE_URL
        self.hf_api_token = HF_API_TOKEN
        self.logger = logging.getLogger(__name__)
        
    def call_huggingface_api(self, user_message):
        """Call HuggingFace Space API with optimized timeouts"""
        self.logger.info(f"🚀 === HF API Call Debug Info ===")
        self.logger.info(f"📝 User message: {user_message}")
        self.logger.info(f"🌐 HF Space URL: {self.hf_space_url}")
        
        # Check if HF Space is reachable first
        try:
            ping_response = requests.get(self.hf_space_url, timeout=3)
            if ping_response.status_code != 200:
                self.logger.warning(f"⚠️ HF Space ping failed: {ping_response.status_code}")
                return self._get_contextual_fallback(user_message)
        except Exception as e:
            self.logger.warning(f"⚠️ HF Space not reachable: {str(e)} - using fallback")
            return self._get_contextual_fallback(user_message)
        
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'ColinBot/1.0'
        }
        
        if self.hf_api_token:
            headers['Authorization'] = f'Bearer {self.hf_api_token}'
            self.logger.info("🔑 Using HF API token")
        else:
            self.logger.info("⚠️  No HF API token provided")
        
        # Try HF Space API with reduced timeouts to prevent Telegram duplicates
        endpoints_to_try = [
            (f"{self.hf_space_url}/api/predict", {"data": [user_message]}),
            (f"{self.hf_space_url}/predict", {"inputs": user_message}),
            (f"{self.hf_space_url}/api/generate", {"prompt": user_message}),
            (f"{self.hf_space_url}/generate", {"text": user_message})
        ]
        
        for i, (endpoint, payload) in enumerate(endpoints_to_try):
            try:
                self.logger.info(f"🔄 Attempt {i+1}: {endpoint}")
                self.logger.info(f"📦 Payload: {payload}")
                
                response = requests.post(
                    endpoint,
                    json=payload,
                    headers=headers,
                    timeout=8  # Reduced timeout to prevent Telegram duplicate messages
                )
                
                self.logger.info(f"📊 Status: {response.status_code}")
                
                if response.status_code == 200:
                    result = response.json()
                    self.logger.info(f"✅ Success! Response: {result}")
                    
                    # Extract response text
                    if isinstance(result, dict):
                        if 'data' in result and isinstance(result['data'], list) and result['data']:
                            extracted = str(result['data'][0])
                            self.logger.info(f"📄 Extracted from 'data': {extracted}")
                            return extracted
                        elif 'output' in result:
                            extracted = str(result['output'])
                            self.logger.info(f"📄 Extracted from 'output': {extracted}")
                            return extracted
                        elif 'generated_text' in result:
                            self.logger.info(f"📄 Extracted from 'generated_text': {result['generated_text']}")
                            return result['generated_text']
                        elif 'response' in result:
                            self.logger.info(f"📄 Extracted from 'response': {result['response']}")
                            return result['response']
                    elif isinstance(result, list) and result:
                        extracted = str(result[0])
                        self.logger.info(f"📄 Extracted from list: {extracted}")
                        return extracted
                    elif isinstance(result, str):
                        self.logger.info(f"📄 Direct string response: {result}")
                        return result
                    
                    # Fallback - convert to string
                    fallback_result = str(result)
                    self.logger.info(f"📄 Fallback conversion: {fallback_result}")
                    return fallback_result
                    
                else:
                    response_text = response.text[:200]
                    self.logger.warning(f"❌ Failed: {response.status_code} - {response_text}")
                    
            except requests.exceptions.Timeout:
                self.logger.warning(f"⏰ Timeout for {endpoint}")
                continue
            except Exception as e:
                self.logger.error(f"🚨 Error for {endpoint}: {str(e)}")
                continue
        
        # If all API attempts fail, use intelligent fallback
        return self._get_contextual_fallback(user_message)
    
    def _get_contextual_fallback(self, user_message):
        """Get contextual fallback response when HF API is unavailable"""
        self.logger.warning("🆘 Using contextual fallback response")
        
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
        elif 'when' in message_lower:
            return "That's a great question about timing! I'm currently working on reconnecting to my full capabilities to give you better answers."
        else:
            return f"I hear you saying: '{user_message}'. I'm currently having trouble connecting to my full AI capabilities, but I'm working on fixing this issue!"

# Initialize bot instance
colin_bot = ColinBot()

def send_message(chat_id, text):
    """Send message via Telegram API directly"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML"
        }
        
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"✅ Message sent successfully to {chat_id}")
            return True
        else:
            logger.error(f"❌ Failed to send message: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"🚨 Error sending message: {str(e)}")
        return False

def send_typing_action(chat_id):
    """Send typing action via Telegram API"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendChatAction"
        payload = {
            "chat_id": chat_id,
            "action": "typing"
        }
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        logger.error(f"🚨 Error sending typing action: {str(e)}")

# Flask webhook endpoint
@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    """Handle incoming webhooks from Telegram - OPTIMIZED VERSION"""
    try:
        json_data = request.get_json(force=True)
        logger.info(f"📨 Received webhook data: {json_data}")
        
        # Extract message data
        if 'message' in json_data:
            message = json_data['message']
            chat_id = message['chat']['id']
            user_name = message['from'].get('first_name', 'User')
            
            if 'text' in message:
                user_message = message['text']
                logger.info(f"💬 Message from {user_name}: {user_message}")
                
                # Handle commands
                if user_message.startswith('/start'):
                    welcome_message = """🤖 Hello! I'm Colin, your AI assistant!

I can help you with:
• Answering questions
• Having conversations  
• Providing information
• And much more!

Just send me a message and I'll respond. Let's chat!"""
                    send_message(chat_id, welcome_message)
                    
                elif user_message.startswith('/help'):
                    help_message = """🆘 Colin Bot Help

Commands:
• /start - Start the bot
• /help - Show this help message

Just send me any message and I'll respond! I'm powered by AI and ready to chat.

Having issues? The bot is constantly being improved!"""
                    send_message(chat_id, help_message)
                    
                else:
                    # Handle regular messages
                    try:
                        # Send typing indicator
                        send_typing_action(chat_id)
                        
                        # Get AI response (now with optimized timeouts)
                        ai_response = colin_bot.call_huggingface_api(user_message)
                        logger.info(f"🤖 Colin's response: {ai_response}")
                        
                        # Send response
                        send_message(chat_id, ai_response)
                        
                    except Exception as e:
                        logger.error(f"🚨 Error processing message: {str(e)}")
                        send_message(chat_id, "Sorry, I'm experiencing technical difficulties right now. Please try again in a moment! 🔧")
        
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
        "version": "3.1-OPTIMIZED",
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
    logger.info(f"🤖 Starting ColinBot OPTIMIZED VERSION")
    logger.info(f"🌐 HF Space: {HF_SPACE_URL}")
    logger.info(f"🔗 Webhook URL: {WEBHOOK_URL}")
    
    if WEBHOOK_URL:
        logger.info(f"🌐 Using WEBHOOK mode")
        setup_webhook()
        
        # Run Flask app
        app.run(host='0.0.0.0', port=PORT, debug=False)
    else:
        logger.error("❌ No WEBHOOK_URL provided - cannot run in webhook mode")

# REBUILD TRIGGER 2025-08-13
# Version 3.1 - Optimized webhook with fast HF API calls
