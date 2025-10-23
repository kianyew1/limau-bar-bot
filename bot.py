import os
import logging
import json
import csv
from pathlib import Path
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from menu import MENU

#for local
from dotenv import load_dotenv
load_dotenv()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')
STAFF_GROUP_ID = os.getenv('STAFF_GROUP_ID')
ADMIN_USER_ID = os.getenv('ADMIN_USER_ID')  # Add this to your .env file

# Data file for persistence
DATA_FILE = Path('user_orders.json')

def load_orders():
    """Load orders from file"""
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                # Migrate old data structure to new one
                for user_id, user_data in data.items():
                    # Ensure order_history exists
                    if 'order_history' not in user_data:
                        data[user_id]['order_history'] = []
                return data
        except Exception as e:
            logger.error(f"Error loading orders: {e}")
            return {}
    return {}

def save_orders(orders):
    """Save orders to file"""
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(orders, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving orders: {e}")

# Load existing orders on startup
user_orders = load_orders()

def ensure_user_exists(user_id, user_name):
    """Make sure user is initialized"""
    if user_id not in user_orders:
        user_orders[user_id] = {
            'name': user_name,
            'cart': [],  # Current cart items (not yet submitted)
            'tab': 0.00,   # Running tab of submitted orders
            'order_history': []  # List of all ordered items
        }
        save_orders(user_orders)
    else:
        # Ensure the user has the new structure
        if 'cart' not in user_orders[user_id]:
            user_orders[user_id]['cart'] = []
        if 'tab' not in user_orders[user_id]:
            user_orders[user_id]['tab'] = 0.00
        if 'order_history' not in user_orders[user_id]:
            user_orders[user_id]['order_history'] = []
        save_orders(user_orders)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message and regional menu"""
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.first_name
    
    ensure_user_exists(user_id, user_name)
    
    keyboard = [
        [InlineKeyboardButton("🌮 Latin America", callback_data='region_latin')],
        [InlineKeyboardButton("🍜 Southeast Asia", callback_data='region_sea')],
        [InlineKeyboardButton("🦘 Oceania", callback_data='region_oceania')],
        [InlineKeyboardButton("💰 My Tab", callback_data='view_tab')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Hey {user_name}! 👋\n\n"
        "Welcome to our three-region culinary journey!\n"
        "Select a region to explore:",
        reply_markup=reply_markup
    )

async def show_region_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, region: str = None):
    """Show region menu with current cart"""
    query = update.callback_query
    
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.first_name
    ensure_user_exists(user_id, user_name)
    
    # Get region from parameter or callback data
    if region is None:
        region = query.data.split('_')[1]
    
    # Get region details
    region_emojis = {
        'latin': '🌮',
        'sea': '🍜',
        'oceania': '🦘'
    }
    region_names = {
        'latin': 'Latin America',
        'sea': 'Southeast Asia',
        'oceania': 'Oceania'
    }
    
    # Get current cart
    cart = user_orders[user_id]['cart']
    
    # Build message text
    message_text = f"{region_emojis[region]} {region_names[region]}\n"
    message_text += "━━━━━━━━━━━━━━\n\n"
    
    if cart:
        message_text += "🛒 Your Current Cart:\n"
        for idx, order in enumerate(cart):
            message_text += f"{idx + 1}. {order['item']} - ${order['price']:.2f}\n"
        
        subtotal = sum(order['price'] for order in cart)
        message_text += f"\n💵 Cart Subtotal: ${subtotal:.2f}\n"
        message_text += "━━━━━━━━━━━━━━\n\n"
    
    message_text += "Select items to add to your cart:"
    
    # Build menu keyboard
    keyboard = []
    for item, price in MENU[region].items():
        keyboard.append([
            InlineKeyboardButton(
                f"{item} - ${price:.2f}", 
                callback_data=f'add_{region}_{item}'
            )
        ])
    
    # Add action buttons
    if cart:
        keyboard.append([
            InlineKeyboardButton("➖ Remove Item", callback_data=f'remove_menu_{region}'),
            InlineKeyboardButton("🗑️ Clear Cart", callback_data=f'clear_{region}')
        ])
        keyboard.append([InlineKeyboardButton("✅ Submit Order", callback_data='submit_order')])
    
    keyboard.append([InlineKeyboardButton("⬅️ Back to Regions", callback_data='back_main')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(message_text, reply_markup=reply_markup)

async def add_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add item to user's cart and refresh menu"""
    query = update.callback_query
    await query.answer("Added! ✅")
    
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.first_name
    ensure_user_exists(user_id, user_name)
    
    parts = query.data.split('_', 2)
    region = parts[1]
    item = parts[2]
    price = MENU[region][item]
    
    user_orders[user_id]['cart'].append({
        'item': item,
        'price': price,
        'region': region
    })
    save_orders(user_orders)
    
    # Refresh the menu with updated cart
    await show_region_menu(update, context, region=region)

async def show_remove_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show menu to remove items from cart"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    cart = user_orders[user_id]['cart']
    
    if not cart:
        await query.answer("Cart is empty!", show_alert=True)
        return
    
    # Get region from callback data
    region = query.data.split('_')[2]
    
    # Build message
    message_text = "🛒 Select item to remove:\n\n"
    for idx, order in enumerate(cart):
        message_text += f"{idx + 1}. {order['item']} - ${order['price']:.2f}\n"
    
    # Build keyboard with remove buttons
    keyboard = []
    for idx, order in enumerate(cart):
        keyboard.append([
            InlineKeyboardButton(
                f"❌ Remove: {order['item']}", 
                callback_data=f'removeitem_{region}_{idx}'
            )
        ])
    
    keyboard.append([InlineKeyboardButton("⬅️ Back to Menu", callback_data=f'region_{region}')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(message_text, reply_markup=reply_markup)

async def remove_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove specific item from cart"""
    query = update.callback_query
    await query.answer("Removed! ❌")
    
    user_id = str(update.effective_user.id)
    
    parts = query.data.split('_')
    region = parts[1]
    item_idx = int(parts[2])
    
    # Remove item from cart
    if item_idx < len(user_orders[user_id]['cart']):
        user_orders[user_id]['cart'].pop(item_idx)
        save_orders(user_orders)
    
    # Go back to region menu
    await show_region_menu(update, context, region=region)

async def submit_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Submit order and send ticket to staff"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    user_name = user_orders[user_id]['name']
    cart = user_orders[user_id]['cart']
    
    if not cart:
        await query.answer("Your cart is empty!", show_alert=True)
        return
    
    # Group orders by region
    latin_orders = [o for o in cart if o['region'] == 'latin']
    sea_orders = [o for o in cart if o['region'] == 'sea']
    oceania_orders = [o for o in cart if o['region'] == 'oceania']
    
    # Create order ticket
    ticket = f"🎫 NEW ORDER\n"
    ticket += f"━━━━━━━━━━━━━━\n"
    ticket += f"👤 Customer: {user_name}\n"
    ticket += f"🆔 ID: {user_id}\n\n"
    
    if latin_orders:
        ticket += "🌮 LATIN AMERICA:\n"
        for item in latin_orders:
            ticket += f"  • {item['item']}\n"
        ticket += "\n"
    
    if sea_orders:
        ticket += "🍜 SOUTHEAST ASIA:\n"
        for item in sea_orders:
            ticket += f"  • {item['item']}\n"
        ticket += "\n"
    
    if oceania_orders:
        ticket += "🦘 OCEANIA:\n"
        for item in oceania_orders:
            ticket += f"  • {item['item']}\n"
        ticket += "\n"
    
    order_total = sum(order['price'] for order in cart)
    ticket += f"━━━━━━━━━━━━━━\n"
    ticket += f"💵 Order Total: ${order_total:.2f}"
    
    # Send to staff group
    try:
        await context.bot.send_message(chat_id=STAFF_GROUP_ID, text=ticket)
    except Exception as e:
        logger.error(f"Failed to send to staff group: {e}")
    
    # Add items to order history with timestamp
    timestamp = datetime.now().isoformat()
    for item in cart:
        user_orders[user_id]['order_history'].append({
            'item': item['item'],
            'price': item['price'],
            'region': item['region'],
            'timestamp': timestamp
        })
    
    # Add cart total to running tab and clear cart
    user_orders[user_id]['tab'] += order_total
    user_orders[user_id]['cart'] = []
    save_orders(user_orders)
    
    # Confirm to user
    keyboard = [[InlineKeyboardButton("🏠 Back to Regions", callback_data='back_main')]]
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
    
    tab = user_orders.get(user_id, {}).get('tab', 0.00)
    order_history = user_orders.get(user_id, {}).get('order_history', [])
    
    tab_text = f"💰 Your Tab Tonight\n\n"
    
    if order_history:
        tab_text += "📝 Items Ordered:\n"
        for item in order_history:
            tab_text += f"  • {item['item']} - ${item['price']:.2f}\n"
        tab_text += "\n"
    
    tab_text += f"Total: ${tab:.2f}\n\n"
    tab_text += "Pay at the end of the night! 🎊"
    
    keyboard = [[InlineKeyboardButton("⬅️ Back to Regions", callback_data='back_main')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(tab_text, reply_markup=reply_markup)

async def clear_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear current cart items"""
    query = update.callback_query
    await query.answer("Cart cleared! 🗑️")
    
    user_id = str(update.effective_user.id)
    
    # Get region from callback data
    region = query.data.split('_')[1]
    
    # Clear cart
    user_orders[user_id]['cart'] = []
    save_orders(user_orders)
    
    # Return to the same region menu
    await show_region_menu(update, context, region=region)

async def back_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Return to main menu"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.first_name
    ensure_user_exists(user_id, user_name)
    
    keyboard = [
        [InlineKeyboardButton("🌮 Latin America", callback_data='region_latin')],
        [InlineKeyboardButton("🍜 Southeast Asia", callback_data='region_sea')],
        [InlineKeyboardButton("🦘 Oceania", callback_data='region_oceania')],
        [InlineKeyboardButton("💰 My Tab", callback_data='view_tab')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "Select a region to explore:",
        reply_markup=reply_markup
    )

async def reset_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset all tabs - staff only command"""
    user_id = str(update.effective_user.id)
    
    # Check if user is admin
    if ADMIN_USER_ID and user_id != ADMIN_USER_ID:
        await update.message.reply_text("⛔ This command is only available to staff.")
        return
    
    global user_orders
    user_orders = {}
    save_orders(user_orders)
    await update.message.reply_text("✅ All tabs have been reset!")

async def export_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Export all orders and tabs - staff only command"""
    user_id = str(update.effective_user.id)
    
    # Check if user is admin
    if ADMIN_USER_ID and user_id != ADMIN_USER_ID:
        await update.message.reply_text("⛔ This command is only available to staff.")
        return
    
    if not user_orders:
        await update.message.reply_text("No orders to export!")
        return
    
    # Create detailed export message
    export_text = "📊 END OF NIGHT SUMMARY\n"
    export_text += "━━━━━━━━━━━━━━━━━━━━\n\n"
    
    total_revenue = 0.00
    
    for user_id, user_data in user_orders.items():
        name = user_data['name']
        tab = user_data['tab']
        order_history = user_data.get('order_history', [])
        total_revenue += tab
        
        export_text += f"👤 {name} (ID: {user_id})\n"
        if order_history:
            export_text += "Items ordered:\n"
            for item in order_history:
                export_text += f"  • {item['item']} - ${item['price']:.2f}\n"
        export_text += f"💵 Total: ${tab:.2f}\n"
        export_text += "─────────────────\n"
    
    export_text += f"\n💰 TOTAL REVENUE: ${total_revenue:.2f}\n"
    export_text += f"👥 Total Customers: {len(user_orders)}\n"
    
    # Send the summary (split if too long)
    if len(export_text) > 4096:
        # Split into chunks
        chunks = [export_text[i:i+4096] for i in range(0, len(export_text), 4096)]
        for chunk in chunks:
            await update.message.reply_text(chunk)
    else:
        await update.message.reply_text(export_text)
    
    # Create CSV file
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    csv_filename = f"orders_export_{timestamp}.csv"
    csv_path = Path(csv_filename)
    
    try:
        with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['User ID', 'Name', 'Item', 'Price', 'Region', 'Timestamp', 'User Total']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for user_id, user_data in user_orders.items():
                name = user_data['name']
                tab = user_data['tab']
                order_history = user_data.get('order_history', [])
                
                if order_history:
                    for item in order_history:
                        writer.writerow({
                            'User ID': user_id,
                            'Name': name,
                            'Item': item['item'],
                            'Price': item['price'],
                            'Region': item['region'],
                            'Timestamp': item.get('timestamp', ''),
                            'User Total': tab
                        })
                else:
                    # Write user with no orders
                    writer.writerow({
                        'User ID': user_id,
                        'Name': name,
                        'Item': '',
                        'Price': 0.00,
                        'Region': '',
                        'Timestamp': '',
                        'User Total': tab
                    })
        
        # Send CSV file
        with open(csv_path, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=csv_filename,
                caption="📊 Orders export (CSV)"
            )
        
        # Clean up CSV file
        csv_path.unlink()
        
    except Exception as e:
        logger.error(f"Failed to create/send CSV: {e}")
        await update.message.reply_text(f"Error creating CSV: {e}")
    
    # Send the JSON file
    try:
        with open(DATA_FILE, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=f"orders_export_{timestamp}.json",
                caption="📁 Full order data (JSON)"
            )
    except Exception as e:
        logger.error(f"Failed to send JSON file: {e}")
        await update.message.reply_text(f"Error sending JSON file: {e}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route button callbacks"""
    query = update.callback_query
    
    if query.data.startswith('region_'):
        await show_region_menu(update, context)
    elif query.data.startswith('add_'):
        await add_item(update, context)
    elif query.data.startswith('remove_menu_'):
        await show_remove_menu(update, context)
    elif query.data.startswith('removeitem_'):
        await remove_item(update, context)
    elif query.data.startswith('clear_'):
        await clear_cart(update, context)
    elif query.data == 'submit_order':
        await submit_order(update, context)
    elif query.data == 'view_tab':
        await view_tab(update, context)
    elif query.data == 'back_main':
        await back_main(update, context)

def main():
    """Start the bot"""
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("reset", reset_all))
    application.add_handler(CommandHandler("export", export_orders))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Start the bot
    logger.info("Bot starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()