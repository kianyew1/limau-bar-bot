import os
import logging
import json
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')
STAFF_GROUP_ID = os.getenv('STAFF_GROUP_ID')

# Data file for persistence
DATA_FILE = Path('user_orders.json')

# Menu data - easily update between events
MENU = {
    'cocktails': {
        'Margarita': 12.00,
        'Mojito': 11.00,
        'Old Fashioned': 14.00,
        'Negroni': 13.00,
        'Espresso Martini': 13.00,
    },
    'tapas': {
        'Patatas Bravas': 8.00,
        'Gambas al Ajillo': 12.00,
        'Croquetas': 9.00,
        'Jamón Ibérico': 15.00,
        'Pan con Tomate': 6.00,
    }
}

def load_orders():
    """Load orders from file"""
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading orders: {e}")
            return {}
    return {}

def save_orders(orders):
    """Save orders to file"""
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(orders, f)
    except Exception as e:
        logger.error(f"Error saving orders: {e}")

# Load existing orders on startup
user_orders = load_orders()

def ensure_user_exists(user_id, user_name):
    """Make sure user is initialized"""
    if user_id not in user_orders:
        user_orders[user_id] = {
            'name': user_name,
            'orders': [],
            'total': 0.00
        }
        save_orders(user_orders)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message and main menu"""
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.first_name
    
    ensure_user_exists(user_id, user_name)
    
    keyboard = [
        [InlineKeyboardButton("🍹 Cocktails", callback_data='menu_cocktails')],
        [InlineKeyboardButton("🍤 Tapas", callback_data='menu_tapas')],
        [InlineKeyboardButton("🛒 View Cart", callback_data='view_cart')],
        [InlineKeyboardButton("💰 My Tab", callback_data='view_tab')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Hey {user_name}! 👋\n\n"
        "Welcome to the bar! What would you like to order?",
        reply_markup=reply_markup
    )

async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show menu category"""
    query = update.callback_query
    await query.answer()
    
    # Ensure user exists
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.first_name
    ensure_user_exists(user_id, user_name)
    
    category = query.data.split('_')[1]
    
    keyboard = []
    for item, price in MENU[category].items():
        keyboard.append([
            InlineKeyboardButton(
                f"{item} - ${price:.2f}", 
                callback_data=f'add_{category}_{item}'
            )
        ])
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data='back_main')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    title = "🍹 Cocktails" if category == 'cocktails' else "🍤 Tapas"
    await query.edit_message_text(
        f"{title}\n\nSelect an item to add to your order:",
        reply_markup=reply_markup
    )

async def add_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add item to user's cart"""
    query = update.callback_query
    await query.answer("Added to cart! ✅")
    
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.first_name
    ensure_user_exists(user_id, user_name)
    
    parts = query.data.split('_', 2)
    category = parts[1]
    item = parts[2]
    price = MENU[category][item]
    
    user_orders[user_id]['orders'].append({
        'item': item,
        'price': price,
        'category': category
    })
    user_orders[user_id]['total'] += price
    save_orders(user_orders)
    
    # Show updated menu
    await show_menu(update, context)

async def view_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current cart"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.first_name
    ensure_user_exists(user_id, user_name)
    
    orders = user_orders.get(user_id, {}).get('orders', [])
    
    if not orders:
        keyboard = [[InlineKeyboardButton("⬅️ Back to Menu", callback_data='back_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Your cart is empty! 🛒",
            reply_markup=reply_markup
        )
        return
    
    cart_text = "🛒 Your Cart:\n\n"
    for order in orders:
        cart_text += f"• {order['item']} - ${order['price']:.2f}\n"
    
    total = sum(order['price'] for order in orders)
    cart_text += f"\n💵 Subtotal: ${total:.2f}"
    
    keyboard = [
        [InlineKeyboardButton("✅ Submit Order", callback_data='submit_order')],
        [InlineKeyboardButton("🗑️ Clear Cart", callback_data='clear_cart')],
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data='back_main')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(cart_text, reply_markup=reply_markup)

async def submit_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Submit order and send ticket to staff"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    user_name = user_orders[user_id]['name']
    orders = user_orders[user_id]['orders']
    
    if not orders:
        await query.edit_message_text("Your cart is empty!")
        return
    
    # Create order ticket
    ticket = f"🎫 NEW ORDER\n"
    ticket += f"━━━━━━━━━━━━━━\n"
    ticket += f"👤 Customer: {user_name}\n"
    ticket += f"🆔 ID: {user_id}\n\n"
    
    cocktails = [o for o in orders if o['category'] == 'cocktails']
    tapas = [o for o in orders if o['category'] == 'tapas']
    
    if cocktails:
        ticket += "🍹 COCKTAILS:\n"
        for item in cocktails:
            ticket += f"  • {item['item']}\n"
        ticket += "\n"
    
    if tapas:
        ticket += "🍤 TAPAS:\n"
        for item in tapas:
            ticket += f"  • {item['item']}\n"
        ticket += "\n"
    
    total = sum(order['price'] for order in orders)
    ticket += f"━━━━━━━━━━━━━━\n"
    ticket += f"💵 Order Total: ${total:.2f}"
    
    # Send to staff group
    try:
        await context.bot.send_message(chat_id=STAFF_GROUP_ID, text=ticket)
    except Exception as e:
        logger.error(f"Failed to send to staff group: {e}")
    
    # Clear user's cart but keep running tab
    user_orders[user_id]['orders'] = []
    save_orders(user_orders)
    
    # Confirm to user
    keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data='back_main')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "✅ Order submitted!\n\n"
        "Your order has been sent to the bar. We'll have it ready soon! 🎉",
        reply_markup=reply_markup
    )

async def view_tab(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's running tab for the night"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.first_name
    ensure_user_exists(user_id, user_name)
    
    total = user_orders.get(user_id, {}).get('total', 0.00)
    
    tab_text = f"💰 Your Tab Tonight\n\n"
    tab_text += f"Total: ${total:.2f}\n\n"
    tab_text += "Pay at the end of the night! 🎊"
    
    keyboard = [[InlineKeyboardButton("⬅️ Back to Menu", callback_data='back_main')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(tab_text, reply_markup=reply_markup)

async def clear_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear current cart items"""
    query = update.callback_query
    await query.answer("Cart cleared! 🗑️")
    
    user_id = str(update.effective_user.id)
    if user_id in user_orders:
        # Remove cart items from total
        cart_total = sum(order['price'] for order in user_orders[user_id]['orders'])
        user_orders[user_id]['total'] -= cart_total
        user_orders[user_id]['orders'] = []
        save_orders(user_orders)
    
    keyboard = [[InlineKeyboardButton("⬅️ Back to Menu", callback_data='back_main')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "Cart cleared! 🗑️",
        reply_markup=reply_markup
    )

async def back_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Return to main menu"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.first_name
    ensure_user_exists(user_id, user_name)
    
    keyboard = [
        [InlineKeyboardButton("🍹 Cocktails", callback_data='menu_cocktails')],
        [InlineKeyboardButton("🍤 Tapas", callback_data='menu_tapas')],
        [InlineKeyboardButton("🛒 View Cart", callback_data='view_cart')],
        [InlineKeyboardButton("💰 My Tab", callback_data='view_tab')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "What would you like to order?",
        reply_markup=reply_markup
    )

async def reset_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset all tabs - staff only command"""
    global user_orders
    user_orders = {}
    save_orders(user_orders)
    await update.message.reply_text("✅ All tabs have been reset!")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route button callbacks"""
    query = update.callback_query
    
    if query.data.startswith('menu_'):
        await show_menu(update, context)
    elif query.data.startswith('add_'):
        await add_item(update, context)
    elif query.data == 'view_cart':
        await view_cart(update, context)
    elif query.data == 'submit_order':
        await submit_order(update, context)
    elif query.data == 'view_tab':
        await view_tab(update, context)
    elif query.data == 'clear_cart':
        await clear_cart(update, context)
    elif query.data == 'back_main':
        await back_main(update, context)

def main():
    """Start the bot"""
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("reset", reset_all))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Start the bot
    logger.info("Bot starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()