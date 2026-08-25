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
    ReplyKeyboardMarkup,
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

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
_admin_raw = os.getenv("ADMIN_CHAT_ID", "0").strip()
try:
    ADMIN_CHAT_ID = int(_admin_raw) if _admin_raw else 0
except ValueError:
    log(f"⚠️ ADMIN_CHAT_ID noto'g'ri qiymat: {_admin_raw!r} — 0 sifatida olinmoqda")
    ADMIN_CHAT_ID = 0

WEBAPP_URL = os.getenv("WEBAPP_URL", "https://technoshopuz.onrender.com").strip()

if not BOT_TOKEN:
    log("❌ OGOHLANTIRISH: BOT_TOKEN environment variable topilmadi!")

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "uploads").strip()

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    log("❌ OGOHLANTIRISH: SUPABASE_URL yoki SUPABASE_SERVICE_KEY topilmadi! Rasm yuklash ishlamaydi.")

try:
    db.init_db()
    log("🗄️ Ma'lumotlar bazasi tayyor (Supabase Postgres)")
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
        c["photo_url"] = c.get("photo") or None
    return jsonify(cats)


@flask_app.route("/api/categories/<int:cid>/products")
def api_products_by_category(cid):
    products = db.get_products_by_category(cid)
    for p in products:
        first_photo = p["photo"].split(",")[0] if p.get("photo") else None
        p["photo_url"] = first_photo or None
    return jsonify(products)


@flask_app.route("/api/products/<int:pid>")
def api_product(pid):
    p = db.get_product(pid)
    if not p:
        return jsonify({"error": "not found"}), 404
    urls = [f for f in (p.get("photo") or "").split(",") if f]
    p["photo_urls"] = urls
    p["photo_url"] = urls[0] if urls else None
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
        f"💰 {product['price']}\n"
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
    """Downloads a Telegram photo and uploads it to Supabase Storage. Returns the public URL."""
    from io import BytesIO

    file = await context.bot.get_file(photo_size.file_id)
    filename = f"{prefix}_{uuid.uuid4().hex[:10]}.jpg"

    buf = BytesIO()
    await file.download_to_memory(out=buf)
    file_bytes = buf.getvalue()

    log(f"📤 Supabase'ga yuklanmoqda: {filename} ({len(file_bytes)} bayt)")

    upload_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{filename}"
    resp = requests.post(
        upload_url,
        headers={
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Content-Type": "image/jpeg",
            "x-upsert": "true",
        },
        data=file_bytes,
        timeout=60,
    )
    if resp.status_code not in (200, 201):
        log(f"❌ Supabase'ga rasm yuklashda xato: {resp.status_code} {resp.text}")
        raise Exception(f"Supabase upload failed: {resp.status_code} {resp.text}")

    public_url = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{filename}"
    log(f"✅ Rasm yuklandi: {public_url}")
    return public_url


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
        [InlineKeyboardButton("🗑 Mahsulot/kategoriya o'chirish", callback_data="admin_manage")],
        [InlineKeyboardButton("📬 Buyurtmalarni ko'rish", callback_data="admin_view_orders")],
    ]
    await update.message.reply_text("🛠 ADMIN PANEL", reply_markup=InlineKeyboardMarkup(keyboard))


# ---------- Delete categories / products ----------

async def admin_manage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    cats = db.get_categories()
    if not cats:
        await query.message.reply_text("📭 Hali kategoriya yo'q")
        return
    keyboard = [[InlineKeyboardButton(f"📂 {c['name']}", callback_data=f"managecat_{c['id']}")] for c in cats]
    await query.message.reply_text("Qaysi kategoriyani boshqarasiz?", reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_manage_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cid = int(query.data.split("_")[1])
    category = db.get_category(cid)
    if not category:
        await query.message.reply_text("❌ Kategoriya topilmadi")
        return
    products = db.get_products_by_category(cid)

    keyboard = [[InlineKeyboardButton(f"❌ {p['name']} o'chirish", callback_data=f"delprod_{p['id']}")] for p in products]
    keyboard.append([InlineKeyboardButton(f"🗑 BUTUN '{category['name']}' kategoriyani o'chirish", callback_data=f"delcat_{cid}")])

    text = f"📂 {category['name']}\n\n" + (
        "Mahsulotlar:" if products else "Bu kategoriyada mahsulot yo'q."
    )
    await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_delete_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pid = int(query.data.split("_")[1])
    product = db.get_product(pid)
    if product:
        db.delete_product(pid)
        await query.message.reply_text(f"✅ '{product['name']}' o'chirildi")
    else:
        await query.message.reply_text("❌ Mahsulot topilmadi")


async def admin_delete_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cid = int(query.data.split("_")[1])
    category = db.get_category(cid)
    if category:
        db.delete_category(cid)
        await query.message.reply_text(f"✅ '{category['name']}' kategoriyasi va uning barcha mahsulotlari o'chirildi")
    else:
        await query.message.reply_text("❌ Kategoriya topilmadi")


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
    try:
        filename = await save_photo(context, update.message.photo[-1], "cat")
    except Exception as e:
        log(f"❌ Kategoriya rasmini yuklashda xato: {e}")
        await update.message.reply_text(
            "❌ Rasmni yuklashda xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring, "
            "yoki /cancel yozib bekor qiling."
        )
        return CAT_PHOTO
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
    context.user_data["new_prod_photos"] = []
    keyboard = ReplyKeyboardMarkup([["✅ Tugatdi"]], resize_keyboard=True)
    await update.message.reply_text(
        "🖼 Mahsulot rasmlarini yuboring (bir nechtasini ketma-ket yuborishingiz mumkin).\n"
        "Barchasini yuborib bo'lgach, pastdagi '✅ Tugatdi' tugmasini bosing.",
        reply_markup=keyboard,
    )
    return PROD_PHOTO


async def add_prod_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("❌ Rasm yuboring yoki '✅ Tugatdi' tugmasini bosing.")
        return PROD_PHOTO
    try:
        filename = await save_photo(context, update.message.photo[-1], "prod")
    except Exception as e:
        log(f"❌ Mahsulot rasmini yuklashda xato: {e}")
        await update.message.reply_text(
            "❌ Rasmni yuklashda xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring, "
            "yoki /cancel yozib bekor qiling."
        )
        return PROD_PHOTO
    context.user_data.setdefault("new_prod_photos", []).append(filename)
    count = len(context.user_data["new_prod_photos"])
    await update.message.reply_text(f"✅ {count}-rasm qabul qilindi. Yana yuborishingiz mumkin, yoki '✅ Tugatdi' tugmasini bosing.")
    return PROD_PHOTO


async def add_prod_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photos = context.user_data.get("new_prod_photos", [])
    if not photos:
        await update.message.reply_text("❌ Kamida bitta rasm yuboring.")
        return PROD_PHOTO
    cid = context.user_data.pop("new_prod_cat")
    name = context.user_data.pop("new_prod_name")
    price = context.user_data.pop("new_prod_price")
    desc = context.user_data.pop("new_prod_desc")
    context.user_data.pop("new_prod_photos", None)
    photo_str = ",".join(photos)
    pid = db.add_product(cid, name, price, desc, photo_str)
    await update.message.reply_text(
        f"✅ Mahsulot qo'shildi!\n📦 {name} — {price} (ID: {pid})\n🖼 {len(photos)} ta rasm bilan",
        reply_markup=ReplyKeyboardRemove(),
    )
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

    order = db.get_order(oid)
    if order and order.get("user_id"):
        try:
            await context.bot.send_message(
                chat_id=order["user_id"],
                text=(
                    f"✅ Buyurtmangiz qabul qilindi!\n\n"
                    f"📦 {order['product_name']}\n"
                    f"📊 {order['qty']} dona\n\n"
                    f"Tez orada siz bilan bog'lanamiz. Rahmat! 🙏"
                ),
            )
        except Exception as e:
            log(f"⚠️ Mijozga xabar yuborib bo'lmadi (user_id={order['user_id']}): {e}")


async def order_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    oid = int(query.data.split("_")[1])
    db.set_order_status(oid, "rejected")
    await query.message.reply_text(f"❌ #{oid} RAD QILINDI")

    order = db.get_order(oid)
    if order and order.get("user_id"):
        try:
            await context.bot.send_message(
                chat_id=order["user_id"],
                text=(
                    f"❌ Afsuski, buyurtmangiz bekor qilindi.\n\n"
                    f"📦 {order['product_name']}\n\n"
                    f"Savollaringiz bo'lsa, biz bilan bog'laning."
                ),
            )
        except Exception as e:
            log(f"⚠️ Mijozga xabar yuborib bo'lmadi (user_id={order['user_id']}): {e}")


def run_bot():
    if not BOT_TOKEN:
        log("❌ BOT_TOKEN yo'q, bot ishga tushmaydi (faqat Mini App ishlaydi).")
        return

    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_menu))
    application.add_handler(CallbackQueryHandler(admin_view_orders, pattern="^admin_view_orders$"))
    application.add_handler(CallbackQueryHandler(admin_manage, pattern="^admin_manage$"))
    application.add_handler(CallbackQueryHandler(admin_manage_category, pattern="^managecat_"))
    application.add_handler(CallbackQueryHandler(admin_delete_product, pattern="^delprod_"))
    application.add_handler(CallbackQueryHandler(admin_delete_category, pattern="^delcat_"))
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
            PROD_PHOTO: [
                MessageHandler(filters.Regex("^✅ Tugatdi$"), add_prod_finish),
                MessageHandler(filters.PHOTO, add_prod_photo),
            ],
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
