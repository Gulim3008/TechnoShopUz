import logging
import os
import sys
import threading
import traceback
import uuid

import requests
from flask import Flask, jsonify, request, send_from_directory

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

import db

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


def log(msg):
    print(msg, flush=True)


log("🚀 app.py yuklanmoqda...")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
_admin_raw = os.getenv("ADMIN_CHAT_ID", "0").strip()
try:
    ADMIN_CHAT_ID = int(_admin_raw) if _admin_raw else 0
except ValueError:
    log(f"⚠️ ADMIN_CHAT_ID noto'g'ri qiymat: {_admin_raw!r} — 0 sifatida olinmoqda")
    ADMIN_CHAT_ID = 0

WEBAPP_URL = os.getenv("WEBAPP_URL", "https://technoshopuz.onrender.com")

if not BOT_TOKEN:
    log("❌ OGOHLANTIRISH: BOT_TOKEN environment variable topilmadi!")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")

try:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    log(f"📁 Upload papkasi tayyor: {UPLOAD_DIR}")
except Exception:
    log("❌ Upload papkasini yaratishda xato:")
    traceback.print_exc()

try:
    db.init_db()
    log("🗄️ Ma'lumotlar bazasi tayyor")
except Exception:
    log("❌ Bazani ishga tushirishda xato:")
    traceback.print_exc()

# ============================================================
#  FLASK APP (serves the Mini App + JSON API)
# ============================================================

flask_app = Flask(__name__, static_folder="static", template_folder="templates")


@flask_app.route("/")
def index():
    return send_from_directory("templates", "index.html")


@flask_app.route("/api/categories")
def api_categories():
    cats = db.get_categories()
    for c in cats:
        c["photo_url"] = f"/static/uploads/{c['photo']}" if c.get("photo") else None
    return jsonify(cats)


@flask_app.route("/api/categories/<int:cid>/products")
def api_products_by_category(cid):
    products = db.get_products_by_category(cid)
    for p in products:
        p["photo_url"] = f"/static/uploads/{p['photo']}" if p.get("photo") else None
    return jsonify(products)


@flask_app.route("/api/products/<int:pid>")
def api_product(pid):
    p = db.get_product(pid)
    if not p:
        return jsonify({"error": "not found"}), 404
    p["photo_url"] = f"/static/uploads/{p['photo']}" if p.get("photo") else None
    return jsonify(p)


@flask_app.route("/api/order", methods=["POST"])
def api_order():
    data = request.get_json(force=True) or {}
    pid = data.get("product_id")
    product = db.get_product(int(pid)) if pid else None
    if not product:
        return jsonify({"ok": False, "error": "product not found"}), 404

    qty = data.get("qty", "1")
    customer_name = data.get("customer_name", "")
    phone = data.get("phone", "")
    user_id = data.get("user_id")

    oid = db.add_order(product["id"], product["name"], product["price"], qty, customer_name, phone, user_id)

    text = (
        f"🆕 BUYURTMA #{oid}\n"
        f"📦 {product['name']}\n"
        f"💰 {product['price']} so'm\n"
        f"📊 {qty} dona\n"
        f"👤 {customer_name}\n"
        f"📱 {phone}"
    )
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Tasdiqlash", "callback_data": f"confirm_{oid}"},
            {"text": "❌ Rad qilish", "callback_data": f"reject_{oid}"},
        ]]
    }
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": ADMIN_CHAT_ID, "text": text, "reply_markup": keyboard},
            timeout=10,
        )
    except Exception as e:
        logger.error(f"Admin xabarini yuborishda xato: {e}")

    return jsonify({"ok": True, "order_id": oid})


# ============================================================
#  TELEGRAM BOT
# ============================================================

CAT_NAME, CAT_PHOTO = range(2)
PROD_CAT, PROD_NAME, PROD_PRICE, PROD_DESC, PROD_PHOTO = range(2, 7)


def is_admin(user_id):
    return user_id == ADMIN_CHAT_ID


async def save_photo(context: ContextTypes.DEFAULT_TYPE, photo_size, prefix) -> str:
    """Downloads a Telegram photo and returns its filename (relative to static/uploads)."""
    file = await context.bot.get_file(photo_size.file_id)
    filename = f"{prefix}_{uuid.uuid4().hex[:10]}.jpg"
    path = os.path.join(UPLOAD_DIR, filename)
    await file.download_to_drive(path)
    return filename


# ---------- /start ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🛍 Do'konni ochish", web_app=WebAppInfo(url=WEBAPP_URL))]]
    await update.message.reply_text(
        "Assalomu alaykum! Texnika do'konimizga xush kelibsiz 👋",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ---------- /admin menu ----------

async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Siz admin emassiz!")
        return
    keyboard = [
        [InlineKeyboardButton("➕ Kategoriya qo'shish", callback_data="admin_add_cat")],
        [InlineKeyboardButton("➕ Mahsulot qo'shish", callback_data="admin_add_prod")],
        [InlineKeyboardButton("📬 Buyurtmalarni ko'rish", callback_data="admin_view_orders")],
    ]
    await update.message.reply_text("🛠 ADMIN PANEL", reply_markup=InlineKeyboardMarkup(keyboard))


# ---------- Add category flow ----------

async def add_cat_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END
    await query.message.reply_text(
        "📂 Yangi kategoriya nomini kiriting (masalan: 📱 TELEFONLAR):",
        reply_markup=ReplyKeyboardRemove(),
    )
    return CAT_NAME


async def add_cat_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_cat_name"] = update.message.text
    await update.message.reply_text("🖼 Endi shu kategoriya uchun rasm yuboring:")
    return CAT_PHOTO


async def add_cat_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("❌ Iltimos, rasm yuboring (fayl emas, oddiy rasm sifatida).")
        return CAT_PHOTO
    filename = await save_photo(context, update.message.photo[-1], "cat")
    name = context.user_data.pop("new_cat_name")
    cid = db.add_category(name, filename)
    await update.message.reply_text(f"✅ Kategoriya qo'shildi!\n📂 {name} (ID: {cid})")
    return ConversationHandler.END


# ---------- Add product flow ----------

async def add_prod_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END
    cats = db.get_categories()
    if not cats:
        await query.message.reply_text("❌ Avval kamida bitta kategoriya qo'shing (/admin orqali).")
        return ConversationHandler.END
    keyboard = [[InlineKeyboardButton(c["name"], callback_data=f"prodcat_{c['id']}")] for c in cats]
    await query.message.reply_text("📂 Qaysi kategoriyaga mahsulot qo'shasiz?", reply_markup=InlineKeyboardMarkup(keyboard))
    return PROD_CAT


async def add_prod_cat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cid = int(query.data.split("_")[1])
    context.user_data["new_prod_cat"] = cid
    await query.message.reply_text("📦 Mahsulot nomini kiriting:")
    return PROD_NAME


async def add_prod_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_prod_name"] = update.message.text
    await update.message.reply_text("💰 Narxini kiriting (faqat raqam, masalan: 3200000):")
    return PROD_PRICE


async def add_prod_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_prod_price"] = update.message.text
    await update.message.reply_text("📝 Tavsifini kiriting (masalan: 256GB, kafolat 12 oy):")
    return PROD_DESC


async def add_prod_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_prod_desc"] = update.message.text
    await update.message.reply_text("🖼 Endi mahsulot rasmini yuboring:")
    return PROD_PHOTO


async def add_prod_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("❌ Iltimos, rasm yuboring (fayl emas, oddiy rasm sifatida).")
        return PROD_PHOTO
    filename = await save_photo(context, update.message.photo[-1], "prod")
    cid = context.user_data.pop("new_prod_cat")
    name = context.user_data.pop("new_prod_name")
    price = context.user_data.pop("new_prod_price")
    desc = context.user_data.pop("new_prod_desc")
    pid = db.add_product(cid, name, price, desc, filename)
    await update.message.reply_text(f"✅ Mahsulot qo'shildi!\n📦 {name} — {price} so'm (ID: {pid})")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Bekor qilindi")
    return ConversationHandler.END


# ---------- Orders (admin) ----------

async def admin_view_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    orders = db.get_all_orders()
    if not orders:
        await query.message.reply_text("📭 Buyurtma yo'q")
        return
    for o in orders[:20]:
        text = (
            f"*#{o['id']}*\n📦 {o['product_name']} x{o['qty']}\n💰 {o['price']}\n"
            f"👤 {o['customer_name']}\n📱 {o['phone']}\n📊 {o['status']}"
        )
        await query.message.reply_text(text, parse_mode="Markdown")


async def order_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    oid = int(query.data.split("_")[1])
    db.set_order_status(oid, "confirmed")
    await query.message.reply_text(f"✅ #{oid} TASDIQLANDI")


async def order_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    oid = int(query.data.split("_")[1])
    db.set_order_status(oid, "rejected")
    await query.message.reply_text(f"❌ #{oid} RAD QILINDI")


def run_bot():
    if not BOT_TOKEN:
        log("❌ BOT_TOKEN yo'q, bot ishga tushmaydi (faqat Mini App ishlaydi).")
        return

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_menu))
    application.add_handler(CallbackQueryHandler(admin_view_orders, pattern="^admin_view_orders$"))
    application.add_handler(CallbackQueryHandler(order_confirm, pattern="^confirm_"))
    application.add_handler(CallbackQueryHandler(order_reject, pattern="^reject_"))

    cat_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_cat_start, pattern="^admin_add_cat$")],
        states={
            CAT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_cat_name)],
            CAT_PHOTO: [MessageHandler(filters.PHOTO, add_cat_photo)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(cat_conv)

    prod_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_prod_start, pattern="^admin_add_prod$")],
        states={
            PROD_CAT: [CallbackQueryHandler(add_prod_cat, pattern="^prodcat_")],
            PROD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_prod_name)],
            PROD_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_prod_price)],
            PROD_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_prod_desc)],
            PROD_PHOTO: [MessageHandler(filters.PHOTO, add_prod_photo)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(prod_conv)

    log("✅ Bot polling ishga tushdi...")
    application.run_polling(stop_signals=None)


def run_bot_safe():
    try:
        run_bot()
    except Exception:
        log("❌ BOT THREAD ICHIDA XATOLIK:")
        traceback.print_exc()


if __name__ == "__main__":
    try:
        bot_thread = threading.Thread(target=run_bot_safe, daemon=True)
        bot_thread.start()
        log("🧵 Bot thread ishga tushirildi")

        port = int(os.getenv("PORT", "10000"))
        log(f"🌐 Flask server {port}-portda ishga tushmoqda (host=0.0.0.0)...")
        flask_app.run(host="0.0.0.0", port=port)
    except Exception:
        log("❌ ASOSIY DASTURDA (main) XATOLIK:")
        traceback.print_exc()
        sys.exit(1)
