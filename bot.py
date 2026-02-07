import os
import requests
from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ---------------- CONFIG ----------------
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN")
SHOPIFY_STORE = os.getenv("SHOPIFY_STORE")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN")
#ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))

SHOPIFY_API = f"https://{SHOPIFY_STORE}/admin/api/2023-10"
HEADERS = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json"
}

# ---------------- CART (IN-MEMORY) ----------------
user_carts = {}

def add_to_cart(user_id, product):
    user_carts.setdefault(user_id, [])
    user_carts[user_id].append(product)

def get_cart(user_id):
    return user_carts.get(user_id, [])

def clear_cart(user_id):
    user_carts.pop(user_id, None)

# ---------------- SHOPIFY ----------------
def get_products():
    r = requests.get(f"{SHOPIFY_API}/products.json", headers=HEADERS)
    return r.json().get("products", [])

def create_draft_order(user, cart):
    items = []
    for p in cart:
        items.append({
            "title": p["title"],
            "price": p["price"],
            "quantity": 1
        })

    payload = {
        "draft_order": {
            "line_items": items,
            "email": f"{user.id}@telegram.shop",
            "financial_status": "paid"
        }
    }

    r = requests.post(
        f"{SHOPIFY_API}/draft_orders.json",
        headers=HEADERS,
        json=payload
    )

    return r.json()["draft_order"]["id"]

# ---------------- HANDLERS ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛍 Welcome to our shop!\n\n"
        "/products – Browse products\n"
        "/cart – View cart\n"
        "/checkout – Pay inside Telegram"
    )

async def products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    products = get_products()

    for p in products[:10]:
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "➕ Add to Cart",
                    callback_data=p["id"]
                )
            ]
        ])

        context.bot_data[str(p["id"])] = {
            "title": p["title"],
            "price": p["variants"][0]["price"]
        }

        await update.message.reply_text(
            f"📦 {p['title']}\n💵 ${p['variants'][0]['price']}",
            reply_markup=keyboard
        )

async def cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cart = get_cart(update.effective_user.id)

    if not cart:
        await update.message.reply_text("🛒 Your cart is empty.")
        return

    msg = "🛒 Your Cart:\n"
    total = 0
    for i in cart:
        msg += f"- {i['title']} (${i['price']})\n"
        total += float(i["price"])

    msg += f"\n💰 Total: ${total}"
    await update.message.reply_text(msg)

async def checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cart = get_cart(update.effective_user.id)

    if not cart:
        await update.message.reply_text("🛒 Cart is empty.")
        return

    prices = []
    for item in cart:
        prices.append(
            LabeledPrice(
                item["title"],
                int(float(item["price"]) * 100)
            )
        )

    await context.bot.send_invoice(
        chat_id=update.effective_user.id,
        title="Order Payment",
        description="Pay securely inside Telegram",
        payload="telegram-shopify-order",
        provider_token=PROVIDER_TOKEN,
        currency="USD",
        prices=prices
    )

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    cart = get_cart(user.id)

    order_id = create_draft_order(user, cart)
    clear_cart(user.id)

    await update.message.reply_text(
        f"✅ Payment successful!\n🧾 Shopify Order ID: {order_id}"
    )

    await context.bot.send_message(
        ADMIN_CHAT_ID,
        f"🧾 New Paid Order\nOrder ID: {order_id}\nUser: {user.full_name}"
    )

async def add_product_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    product = context.bot_data.get(query.data)
    add_to_cart(query.from_user.id, product)

    await query.message.reply_text("✅ Added to cart")

# ---------------- RUN BOT ----------------
from telegram.ext import CallbackQueryHandler

app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("products", products))
app.add_handler(CommandHandler("cart", cart))
app.add_handler(CommandHandler("checkout", checkout))

app.add_handler(CallbackQueryHandler(add_product_callback))
app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

app.run_polling()