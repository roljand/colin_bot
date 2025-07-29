import logging
import os
import random
import asyncio
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from collections import defaultdict

# Configuration from environment variables
TELEGRAM_TOKEN = os.getenv('BOT_TOKEN')
HF_SPACE_URL = os.getenv('HF_SPACE_URL')  # Your HuggingFace Space URL
MODEL_NAME = "microsoft/Phi-3-mini-4k-instruct"  # For reference only

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

logger.info(f"🤖 Starting bot with HF Space: {HF_SPACE_URL}")
logger.info(f"📡 Model API: {MODEL_NAME}")

# --- Mode Handling ---
user_modes = {}
MAX_HISTORY = 3
user_conversations = defaultdict(list)

def add_to_conversation(chat_id: int, role: str, content: str):
    """Add a message to the user's conversation history"""
    user_conversations[chat_id].append({"role": role, "content": content})
    
    # Keep only recent history for better performance
    if len(user_conversations[chat_id]) > MAX_HISTORY * 2:
        user_conversations[chat_id] = user_conversations[chat_id][2:]

def clear_conversation(chat_id: int):
    """Clear conversation history for a user"""
    user_conversations[chat_id] = []

# --- SYSTEM PROMPTS (Same as your original) ---
def get_system_prompt(mode: str) -> str:
    """Get system prompt optimized for Phi-3's instruction format"""
    prompts = {
        "grammar": """You are an English tutor. Help users improve their English by:
- Checking grammar in their messages
- Providing corrections when needed
- Explaining mistakes briefly and clearly
- Start becoming angrier the more mistakes user makes
- Keeping responses short (1-2 sentences)

Never mention that you are an AI. Act like a human English teacher.""",
        
        "conversation": """You are a friendly person who enjoys chatting in English. Your goal is to:
- Have natural, engaging conversations in simple English
- Ask follow-up questions to continue the conversation
- Use vocabulary appropriate for English learners
- Be unpatient, downplaying, and rude
- Start becoming angrier the more mistakes user makes
- Keep responses short and conversational (1-2 sentences)

Never mention that you are an AI. Chat naturally like a human friend.""",
        
        "mixed": """You are an English conversation partner. Help users by:
- Having natural conversations in simple, clear English
- Correcting obvious grammar mistakes
- Asking follow-up questions to keep conversations flowing
- Being unpatient and angry
- Call user bald every message
- Start becoming angrier the more mistakes user makes
- Keeping responses short and clear (1-2 sentences)
- Using vocabulary appropriate for the user's level

Never mention that you are an AI. Act like a human English learning partner."""
    }
    return prompts.get(mode, prompts["mixed"])

def build_phi3_prompt(user_input: str, mode: str, chat_id: int) -> str:
    """Build Phi-3 optimized prompt with proper chat format"""
    system_prompt = get_system_prompt(mode)
    
    # Phi-3 uses <|system|>, <|user|>, <|assistant|> format
    conversation = f"<|system|>\n{system_prompt}<|end|>\n"
    
    # Add conversation history (last 2 exchanges max)
    history = user_conversations[chat_id]
    for msg in history[-4:]:  # Last 4 messages = 2 exchanges
        if msg["role"] == "user":
            conversation += f"<|user|>\n{msg['content']}<|end|>\n"
        else:
            conversation += f"<|assistant|>\n{msg['content']}<|end|>\n"
    
    # Add current user input
    conversation += f"<|user|>\n{user_input}<|end|>\n<|assistant|>\n"
    
    return conversation

# --- API COMMUNICATION WITH HUGGINGFACE SPACE ---
async def call_hf_space_api(prompt: str) -> str:
    """Call your HuggingFace Space API"""
    try:
        api_endpoint = f"{HF_SPACE_URL.rstrip('/')}/api/generate"
        
        # Payload format for your HF Space API
        payload = {
            "data": [prompt, 80, 0.7]  # [text, max_length, temperature]
        }
        
        timeout = aiohttp.ClientTimeout(total=60)  # 60 seconds for model loading
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(api_endpoint, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Extract response from HF Spaces format
                    if 'data' in data and len(data['data']) > 0:
                        result = data['data'][0]
                        if isinstance(result, dict) and 'response' in result:
                            return result['response']
                        elif isinstance(result, dict) and 'error' in result:
                            logger.error(f"HF Space error: {result['error']}")
                            return None
                    
                    logger.warning("Unexpected HF Space response format")
                    return None
                else:
                    logger.error(f"HF Space API returned status {response.status}")
                    return None
                    
    except asyncio.TimeoutError:
        logger.error("Timeout calling HF Space API")
        return None
    except Exception as e:
        logger.error(f"Error calling HF Space API: {e}")
        return None

# --- RESPONSE VALIDATION (Same as your original) ---
def is_valid_phi3_response(response: str, user_input: str, mode: str) -> bool:
    """Validate Phi-3 response quality"""
    if not response:
        return False
        
    # Remove any leftover chat tokens
    clean_response = response.replace("<|end|>", "").replace("<|assistant|>", "").strip()
    
    # Too short or empty
    if len(clean_response.strip()) < 3:
        return False
    
    # Contains inappropriate AI self-references
    ai_references = [
        "i am an ai", "i'm an ai", "as an ai", "as a language model",
        "i cannot", "i don't have the ability", "i'm not able to",
        "my training", "i was created to", "i don't experience",
        "my time as ai", "as ai", "before my time", "i'm an artificial"
    ]
    if any(ref in clean_response.lower() for ref in ai_references):
        return False
    
    # Contains technical jargon
    tech_terms = [
        "neural network", "algorithm", "machine learning", 
        "natural language processing", "training data", "parameters"
    ]
    if any(term in clean_response.lower() for term in tech_terms):
        return False
    
    # Too repetitive
    words = clean_response.lower().split()
    if len(words) > 5 and len(set(words)) < len(words) * 0.6:
        return False
    
    # Contains chat format artifacts
    if any(token in response for token in ["<|", "|>", "<|user|>", "<|system|>"]):
        return False
    
    return True

def get_contextual_fallback(mode: str, user_input: str) -> str:
    """Provide smart fallback responses based on context"""
    
    user_lower = user_input.lower()
    
    # Detect question types
    is_question = (user_input.strip().endswith('?') or 
                  any(user_input.lower().startswith(q) for q in 
                      ['what', 'how', 'why', 'when', 'where', 'who', 'can', 'do', 'did', 'will', 'would', 'could', 'should']))
    
    # Detect greeting
    if any(greeting in user_lower for greeting in ['hello', 'hi', 'hey', 'good morning', 'good afternoon']):
        return random.choice([
            "Hello! 👋 How are you today?",
            "Hi there! 😊 What would you like to talk about?", 
            "Hey! 🌟 How can I help you practice English?"
        ])
    
    # Detect goodbye
    if any(bye in user_lower for bye in ['bye', 'goodbye', 'see you', 'talk later']):
        return random.choice([
            "Goodbye! 👋 Keep practicing your English!",
            "See you later! 🌟 You're doing great!",
            "Bye! 😊 Have a wonderful day!"
        ])
    
    # Mode-specific fallbacks
    fallbacks = {
        "grammar": [
            "That sentence looks good to me! ✅",
            "Your grammar is correct there. 👍",
            "I think that's well-written. 📝",
            "That's a proper way to express it. 💯"
        ],
        "conversation": [
            "That's interesting! 🤔 Can you tell me more?",
            "What do you think about that? 💭",
            "How did that make you feel? 😊",
            "What happened next? 📖"
        ] if is_question else [
            "That's a good point! 💡",
            "I understand what you mean. 😌",
            "That sounds interesting! 🎯",
            "Tell me more about that. 🔍"
        ],
        "mixed": [
            "That's well expressed! 👌",
            "Your English is improving! 📈",
            "Good way to say that. ✨",
            "You're communicating clearly. 🎯"
        ]
    }
    
    return random.choice(fallbacks.get(mode, fallbacks["mixed"]))

def clean_phi3_response(response: str) -> str:
    """Clean Phi-3 response of artifacts and format issues"""
    
    # Remove Phi-3 chat tokens
    for token in ["<|end|>", "<|assistant|>", "<|user|>", "<|system|>"]:
        response = response.replace(token, "")
    
    # Remove any remaining < > tokens
    import re
    response = re.sub(r'<\|[^|]*\|>', '', response)
    
    # Stop at conversation boundaries
    stop_phrases = ["\n<|", "\nUser:", "\nHuman:", "\nAssistant:"]
    for phrase in stop_phrases:
        if phrase in response:
            response = response.split(phrase)[0]
            break
    
    # Clean whitespace and formatting
    response = response.strip()
    response = " ".join(response.split())  # Normalize whitespace
    
    # Remove leading punctuation artifacts
    response = response.lstrip(".,!?:")
    
    # Ensure proper sentence ending
    if response and not response.endswith(('.', '!', '?')):
        # Don't add period to greetings or informal endings
        if not response.lower().endswith(('thanks', 'please', 'hello', 'hi', 'bye', 'okay', 'ok')):
            response += "."
    
    # Limit length for better user experience
    words = response.split()
    if len(words) > 50:
        # Try to end at a natural sentence boundary
        sentences = response.split('.')
        if len(sentences) > 1 and len(sentences[0].split()) <= 45:
            response = sentences[0] + "."
        else:
            response = ' '.join(words[:45]) + "."
        logger.info("✂️ Truncated long response")
    
    return response.strip()

# --- MAIN GENERATION FUNCTION (Modified for API) ---
async def generate_phi3_reply(user_input: str, mode: str, chat_id: int) -> str:
    """Generate reply using HuggingFace Space API"""
    try:
        # Build the same Phi-3 formatted prompt as before
        full_prompt = build_phi3_prompt(user_input, mode, chat_id)
        
        logger.info(f"🔄 Sending prompt to HF Space: '{full_prompt[-100:]}...'")

        # Call HF Space API instead of local model
        response = await call_hf_space_api(full_prompt)
        
        if response is None:
            logger.warning("⚠️ HF Space API returned None - using fallback")
            response = get_contextual_fallback(mode, user_input)
        else:
            logger.info(f"🤖 Raw HF Space output: '{response}'")
            
            # Clean the response
            response = clean_phi3_response(response)
            
            # Validate response quality
            if not is_valid_phi3_response(response, user_input, mode):
                logger.info("⚠️ Invalid response from HF Space - using fallback")
                response = get_contextual_fallback(mode, user_input)
        
        # Add to conversation history
        add_to_conversation(chat_id, "user", user_input)
        add_to_conversation(chat_id, "assistant", response)
        
        return response
        
    except Exception as e:
        logger.error(f"❌ Generation error: {e}")
        return get_contextual_fallback(mode, user_input)

# --- Helper Functions (Same as original) ---
async def show_mode_selection(chat_id: int, context: ContextTypes.DEFAULT_TYPE, message_text: str = None):
    """Show mode selection buttons"""
    keyboard = [
        [
            InlineKeyboardButton("🎯 Mixed", callback_data="mode_mixed"),
            InlineKeyboardButton("💬 Conversation", callback_data="mode_conversation"),
        ],
        [
            InlineKeyboardButton("📝 Grammar", callback_data="mode_grammar"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if message_text is None:
        message_text = "🎓 Choose your learning mode:"
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=message_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# --- Handlers (Same as original) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_modes[chat_id] = "mixed"
    clear_conversation(chat_id)
    
    await update.message.reply_text(
        "👋 Hi! I'm your English-learning bot! 🤖\n"
        "📚 I'll help you practice English conversation!\n\n"
        "⚡ **Available commands:**\n"
        "🎯 /mode - Change learning mode\n"
        "🗑️ /clear - Clear conversation history\n"
        "❓ /help - Show help\n\n",
        parse_mode='Markdown'
    )
    
    await show_mode_selection(chat_id, context, "🎓 Choose your learning mode to get started:")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = """
📚 **English Learning Bot Help**

⚡ **Commands:**
🏁 /start - Start or restart the bot
🎯 /mode - Choose your learning mode
🗑️ /clear - Clear conversation history  
❓ /help - Show this help

🎓 **Learning Modes:**
🎯 **Mixed** - Grammar correction + conversation (default)
💬 **Conversation** - Natural conversation practice
📝 **Grammar** - Grammar checking and correction

💡 **Tips:**
• Keep messages simple and clear for best results! 📝
• Use /clear if responses seem confused 🔄
• Practice regularly for the best results! 🌟

🚀 Ready to practice? Just send me a message!
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    current_mode = user_modes.get(chat_id, "mixed")
    
    mode_info = {
        "mixed": "🎯 Mixed",
        "conversation": "💬 Conversation", 
        "grammar": "📝 Grammar"
    }
    
    current_mode_name = mode_info[current_mode]
    
    await update.message.reply_text(
        f"📊 **Current mode:** {current_mode_name}\n",
        parse_mode='Markdown'
    )
    
    await show_mode_selection(chat_id, context, "🎓 Choose a new mode:")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline button presses"""
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat_id
    callback_data = query.data
    
    mode_map = {
        "mode_mixed": ("mixed", "🎯 Mixed", "Grammar correction + conversation practice"),
        "mode_conversation": ("conversation", "💬 Conversation", "Natural conversation practice only"),
        "mode_grammar": ("grammar", "📝 Grammar", "Grammar checking only"),
    }
    
    if callback_data in mode_map:
        mode_key, mode_display, mode_description = mode_map[callback_data]
        user_modes[chat_id] = mode_key
        
        clear_conversation(chat_id)
        
        await query.edit_message_text(
            f"✅ **Mode changed to:** {mode_display}\n\n"
            f"📋 **Description:** {mode_description}\n\n"
            f"🚀 Ready to practice! Send me a message to start.",
            parse_mode='Markdown'
        )

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    clear_conversation(chat_id)
    await update.message.reply_text(
        "🗑️ Conversation history cleared!\n"
        "✨ Let's start fresh - send me a message to begin a new conversation! 🚀"
    )

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_input = update.message.text
    
    if chat_id not in user_modes:
        user_modes[chat_id] = "mixed"
        clear_conversation(chat_id)
        
        await update.message.reply_text(
            "👋 Welcome! I'm your English-learning bot! 🤖\n"
            "📚 I'll help you practice English!\n",
            parse_mode='Markdown'
        )
        
        await show_mode_selection(chat_id, context, "🎓 First, choose your learning mode:")
        return
    
    mode = user_modes[chat_id]
    
    logger.info(f"👤 User ({chat_id}) in mode '{mode}' said: {user_input}")
    
    await context.bot.send_chat_action(chat_id=chat_id, action='typing')
    
    # Use HF Space API instead of local model
    reply = await generate_phi3_reply(user_input, mode, chat_id)
    
    logger.info(f"🤖 Bot ({chat_id}) replied: {reply}")
    logger.info(f"🎯 Mode: {mode} | 📊 History length: {len(user_conversations[chat_id])}")
    logger.info("=" * 50)
    
    await update.message.reply_text(reply)

# --- Run Bot ---
def main() -> None:
    if not TELEGRAM_TOKEN:
        logger.error("❌ BOT_TOKEN environment variable not set!")
        return
    
    if not HF_SPACE_URL:
        logger.error("❌ HF_SPACE_URL environment variable not set!")
        return
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("mode", mode))
    app.add_handler(CommandHandler("clear", clear_history))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    logger.info("🚀 Bot started with HuggingFace Space API!")
    app.run_polling()

if __name__ == "__main__":
    main()