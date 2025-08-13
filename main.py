import os
import logging
from flask import Flask, request, jsonify
import requests
from gradio_client import Client
import time

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - **%(name)s** - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
BOT_TOKEN = os.environ.get('BOT_TOKEN')
HF_SPACE_URL = os.environ.get('HF_SPACE_URL', 'https://roljand-colin-bot.hf.space')

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN environment variable is required!")
    exit(1)

# Initialize Gradio client
gradio_client = None

def initialize_gradio_client():
    """Initialize or reinitialize the Gradio client"""
    global gradio_client
    try:
        logger.info(f"🔌 Initializing Gradio client for: {HF_SPACE_URL}")
        gradio_client = Client(HF_SPACE_URL)
        logger.info("✅ Gradio client initialized successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to initialize Gradio client: {e}")
        gradio_client = None
        return False

def get_ai_response(message):
    """Get response from HuggingFace Space using Gradio Client"""
    global gradio_client
    
    # Try to initialize client if not already done
    if gradio_client is None:
        if not initialize_gradio_client():
            return get_fallback_response(message)
    
    try:
        logger.info(f"🚀 === HF Gradio Call Debug Info ===")
        logger.info(f"📝 User message: {message}")
        logger.info(f"🌐 HF Space URL: {HF_SPACE_URL}")
        
        # Make the API call using Gradio client
        logger.info("🔄 Calling Gradio predict...")
        result = gradio_client.predict(
            message=message,
            api_name="/chat"  # This should match your Gradio interface
        )
        
        logger.info(f"✅ HF Response received: {result}")
        
        # Handle different response formats
        if isinstance(result, str):
            response = result
        elif isinstance(result, list) and len(result) > 0:
            response = result[0] if isinstance(result[0], str) else str(result[0])
        elif isinstance(result, dict):
            response = result.get('output', str(result))
        else:
            response = str(result)
            
        # Clean up the response
        response = response.strip()
        if not response:
            logger.warning("⚠️ Empty response from HF Space")
            return get_fallback_response(message)
            
        return response
        
    except Exception as e:
        logger.error(f"❌ HF Space error: {e}")
        # Try to reinitialize client for next time
        gradio_client = None
        return get_fallback_response(message)

def get_fallback_response(message):
    """Smart contextual fallback responses"""
    logger.warning("🆘 Using contextual fallback response")
    
    message_lower = message.lower().strip()
    
    # Command responses
    if message_lower in ['/start', '/help']:
        return "👋 Hi! I'm Colin, your English learning assistant! I'm currently having some technical difficulties connecting to my full AI capabilities, but I'm working on getting back to full functionality soon!"
    
    if message_lower == '/clear':
        return "I understand you want to clear our conversation. I'm currently having trouble connecting to my full AI capabilities, but I'm working on fixing this issue!"
    
    # Question detection
    if any(word in message_lower for word in ['?', 'what', 'how', 'why', 'when', 'where', 'who']):
        return f"That's an interesting question about '{message}'. I'm currently experiencing some technical difficulties with my AI connection, but I'm working on resolving this!"
    
    # Greeting detection
    if any(word in message_lower for word in ['hello', 'hi', 'hey', 'good morning', 'good afternoon', 'good evening']):
        return "Hello there! 👋 I'm Colin, and I'd love to help you with English, but I'm currently having some connection issues with my AI brain. I'm working on fixing this!"
    
    # Default response
    return f"I hear you saying: '{message}'. I'm currently having trouble connecting to my full AI capabilities, but I'm working on fixing this issue!"

def send_telegram_message(chat_id, text):
    """Send message to Telegram"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'Markdown'
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            logger.info(f"✅ Message sent successfully to {chat_id}")
            return True
        else:
            logger.error(f"❌ Failed to send message: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ Error sending message: {e}")
        return False

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    """Handle incoming Telegram webhooks"""
    try:
        data = request.get_json()
        logger.info(f"📨 Received webhook data: {data}")
        
        if not data or 'message' not in data:
            return jsonify({'status': 'no message'}), 200
        
        message = data['message']
        chat_id = message['chat']['id']
        user_message = message.get('text', '')
        user_name = message.get('from', {}).get('first_name', 'User')
        
        logger.info(f"💬 Message from {user_name}: {user_message}")
        
        # Get AI response
        ai_response = get_ai_response(user_message)
        logger.info(f"🤖 Colin's response: {ai_response}")
        
        # Send response
        send_telegram_message(chat_id, ai_response)
        
        return jsonify({'status': 'success'}), 200
        
    except Exception as e:
        logger.error(f"❌ Webhook error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'bot_token_configured': bool(BOT_TOKEN),
        'hf_space_url': HF_SPACE_URL,
        'gradio_client_ready': gradio_client is not None
    }), 200

@app.route('/test-hf', methods=['GET'])
def test_hf():
    """Test HuggingFace Space connection"""
    test_message = "Hello, this is a test"
    response = get_ai_response(test_message)
    return jsonify({
        'test_message': test_message,
        'ai_response': response,
        'client_status': 'ready' if gradio_client else 'not initialized'
    }), 200

if __name__ == '__main__':
    logger.info("🚀 Starting Colin English Bot...")
    logger.info(f"🤖 Bot Token: {'✅ Configured' if BOT_TOKEN else '❌ Missing'}")
    logger.info(f"🌐 HF Space: {HF_SPACE_URL}")
    
    # Initialize Gradio client on startup
    initialize_gradio_client()
    
    # Start the Flask app
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
