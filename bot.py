import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ConversationHandler, ContextTypes, filters
from products import PRODUCTS, get_product

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))

orders = {}
order_counter = [1]
NAME, PHONE, QTY, CONFIRM = range(4)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🛍 Katalogni ko'rish", callback_data="catalog")]]
    await update.message.reply_text("Assalomu alaykum! Texnika do'konimizga xush kelibsiz 👋", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_CHAT_ID:
        await update.message.reply_text("❌ Siz admin emassiz!")
        return
    keyboard = [
        [InlineKeyboardButton("➕ Mahsulot qo'shish", callback_data="add_product")],
        [InlineKeyboardButton("📬 Buyurtmalarni ko'rish", callback_data="view_orders")]
    ]
    await update.message.reply_text("🛠 ADMIN PANEL", reply_markup=InlineKeyboardMarkup(keyboard))

async def catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    for p in PRODUCTS:
        btn = [[InlineKeyboardButton("🛒 Buyurtma", callback_data=f"order_{p['id']}")]]
        text = f"*{p['name']}*\n💰 {p['price']} so'm\n\n{p['description']}"
        await query.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(btn))

async def start_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pid = int(query.data.split("_")[1])
    p = get_product(pid)
    if not p:
        await query.message.reply_text("❌ Topilmadi")
        return ConversationHandler.END
    context.user_data["order"] = {"name": p["name"], "price": p["price"]}
    await query.message.reply_text(f"✅ {p['name']}\n\nIsmingizni kiriting:", reply_markup=ReplyKeyboardRemove())
    return NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["order"]["customer_name"] = update.message.text
    keyboard = ReplyKeyboardMarkup([[KeyboardButton("📱 Raqamni yuborish", request_contact=True)]], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Telefon raqamingiz:", reply_markup=keyboard)
    return PHONE

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.contact.phone_number if update.message.contact else update.message.text
    context.user_data["order"]["phone"] = phone
    await update.message.reply_text("Nechta dona?", reply_markup=ReplyKeyboardRemove())
    return QTY

async def get_qty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["order"]["qty"] = update.message.text
    o = context.user_data["order"]
    text = f"📋 Tasdiqlang:\n\n{o['name']}\n💰 {o['price']}\n👤 {o['customer_name']}\n📱 {o['phone']}\n📦 {o['qty']} dona"
    btn = [[InlineKeyboardButton("✅ Ha", callback_data="conf_yes"), InlineKeyboardButton("❌ Yo'q", callback_data="conf_no")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(btn))
    return CONFIRM

async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "conf_no":
        await query.message.reply_text("❌ Bekor qilindi")
        context.user_data.clear()
        return ConversationHandler.END
    
    o = context.user_data["order"]
    oid = order_counter[0]
    order_counter[0] += 1
    orders[oid] = {**o, "id": oid, "user_id": query.from_user.id, "status": "pending", "username": query.from_user.username or "N/A"}
    
    admin_text = f"🆕 BUYURTMA #{oid}\n📦 {o['name']}\n💰 {o['price']}\n📊 {o['qty']} dona\n👤 {o['customer_name']}\n📱 {o['phone']}"
    btn = [[InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"confirm_{oid}"), InlineKeyboardButton("❌ Rad qilish", callback_data=f"reject_{oid}")]]
    await context.bot.send_message(ADMIN_CHAT_ID, admin_text, reply_markup=InlineKeyboardMarkup(btn))
    await query.message.reply_text("✅ Buyurtma qabul qilindi!")
    context.user_data.clear()
    return ConversationHandler.END

async def admin_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    oid = int(query.data.split("_")[1])
    if oid in orders:
        orders[oid]["status"] = "confirmed"
        await query.message.reply_text(f"✅ #{oid} TASDIQLANDI")

async def admin_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    oid = int(query.data.split("_")[1])
    if oid in orders:
        orders[oid]["status"] = "rejected"
        await query.message.reply_text(f"❌ #{oid} RAD QILINDI")

async def view_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not orders:
        await query.message.reply_text("📭 Buyurtma yo'q")
        return
    for oid, o in orders.items():
        text = f"*#{oid}*\n📦 {o['name']} x{o['qty']}\n💰 {o['price']}\n👤 {o['customer_name']}\n📱 {o['phone']}\n📊 {o['status']}"
        await query.message.reply_text(text, parse_mode="Markdown")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Bekor qilindi")
    return ConversationHandler.END

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_menu))
    app.add_handler(CallbackQueryHandler(catalog, pattern="^catalog$"))
    app.add_handler(CallbackQueryHandler(view_orders, pattern="^view_orders$"))
    app.add_handler(CallbackQueryHandler(admin_confirm, pattern="^confirm_"))
    app.add_handler(CallbackQueryHandler(admin_reject, pattern="^reject_"))
    
    order_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_order, pattern="^order_")],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            PHONE: [MessageHandler((filters.TEXT | filters.CONTACT) & ~filters.COMMAND, get_phone)],
            QTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_qty)],
            CONFIRM: [CallbackQueryHandler(confirm_order, pattern="^conf_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(order_conv)
    
    print("✅ Bot ishga tushdi...")
    app.run_polling()

if __name__ == "__main__":
    main()
