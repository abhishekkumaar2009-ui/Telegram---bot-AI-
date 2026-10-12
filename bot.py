import os
import asyncio
import logging
import sqlite3
from datetime import date
import httpx
from aiohttp import web
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# --- BOT CONFIGURATION ---
BOT_TOKEN = "8056463990:AAGoV71k_sH8W5jH2vVfJ8Lw8Z7Z8Z8Z8Z8"  # Apna Info Bot Token
ADMIN_ID = 6878347712

FOOTER_TEXT = "\n\n━━━━━━━━━━━━━━━━━━━━\nCreated by - Abhishek ( @abhisxhxz )"

http_client = httpx.AsyncClient(timeout=45.0)
USER_STATES = {}

# --- DATABASE SETUP ---
DB_FILE = "users_data.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            credits INTEGER DEFAULT 5,
            last_date TEXT,
            referred_by INTEGER
        )
    """)
    conn.commit()
    conn.close()

init_db()

def get_user_credits(user_id):
    today_str = str(date.today())
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT credits, last_date FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()

    if not row:
        c.execute("INSERT INTO users (user_id, credits, last_date) VALUES (?, 5, ?)", (user_id, today_str))
        conn.commit()
        conn.close()
        return 5
    else:
        credits, last_date = row
        # Daily reset agar new day ho gaya hai
        if last_date != today_str:
            credits = 5
            c.execute("UPDATE users SET credits = ?, last_date = ? WHERE user_id = ?", (credits, today_str, user_id))
            conn.commit()
        conn.close()
        return credits

def deduct_credit(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE users SET credits = credits - 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def add_referral_credits(referrer_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE users SET credits = credits + 5 WHERE user_id = ?", (referrer_id,))
    conn.commit()
    conn.close()

# --- KEYBOARDS ---
def get_main_menu():
    keyboard = [
        [
            InlineKeyboardButton("🔍 Num Info", callback_data="num_info"),
            InlineKeyboardButton("👤 User to Num", callback_data="user_to_num"),
        ],
        [
            InlineKeyboardButton("🎁 Refer & Earn", callback_data="refer_earn"),
            InlineKeyboardButton("💳 My Credits", callback_data="my_credits"),
        ],
        [
            InlineKeyboardButton("👑 Owner", url="https://t.me/abhisxhxz"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_button():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 Back to Menu", callback_data="back_home")]]
    )

# --- COMMANDS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    today_str = str(date.today())

    # Check Referral
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    existing_user = c.fetchone()

    if not existing_user and context.args:
        arg = context.args[0]
        if arg.startswith("ref_"):
            try:
                referrer_id = int(arg.replace("ref_", ""))
                if referrer_id != user_id:
                    # New user register with referrer
                    c.execute("INSERT INTO users (user_id, credits, last_date, referred_by) VALUES (?, 5, ?, ?)", (user_id, today_str, referrer_id))
                    conn.commit()
                    add_referral_credits(referrer_id)

                    try:
                        await context.bot.send_message(
                            chat_id=referrer_id,
                            text=f"🎉 <b>New Referral!</b>\n\nUser <b>{user.first_name}</b> ne aapke link se join kiya!\nAapko <b>+5 Credits</b> mil gaye hain! 🎁",
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass
            except Exception:
                pass
    conn.close()

    credits = get_user_credits(user_id)

    welcome_text = (
        f"👋 Welcome <b>{user.first_name}</b>!\n\n"
        "⚡ <b>Abhishek Info Bot</b> me aapka swagat hai.\n"
        f"💳 <b>Aapke Credits:</b> <code>{credits}</code> searches bache hain (Daily 5 free).\n\n"
        "Niche diye gaye buttons me se select karein:"
        f"{FOOTER_TEXT}"
    )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            welcome_text, reply_markup=get_main_menu(), parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            welcome_text, reply_markup=get_main_menu(), parse_mode="HTML"
        )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id
    bot_info = await context.bot.get_me()

    if data == "num_info":
        if get_user_credits(user_id) <= 0:
            await query.edit_message_text(
                "❌ <b>Daily Limit Khatam!</b>\n\n"
                "Aapke aaj ke 5 searches pure ho chuke hain.\n"
                "Friends ko refer karein aur har refer par <b>+5 Credits</b> paayein!",
                reply_markup=get_main_menu(),
                parse_mode="HTML"
            )
            return

        USER_STATES[user_id] = "AWAITING_NUM"
        await query.edit_message_text(
            "📞 <b>Mobile Number Bhejo:</b>\n\n"
            "Example: <code>9876543210</code>"
            f"{FOOTER_TEXT}",
            reply_markup=get_back_button(),
            parse_mode="HTML",
        )

    elif data == "user_to_num":
        if get_user_credits(user_id) <= 0:
            await query.edit_message_text(
                "❌ <b>Daily Limit Khatam!</b>\n\n"
                "Aapke aaj ke 5 searches pure ho chuke hain.\n"
                "Friends ko refer karein aur har refer par <b>+5 Credits</b> paayein!",
                reply_markup=get_main_menu(),
                parse_mode="HTML"
            )
            return

        USER_STATES[user_id] = "AWAITING_USERNAME"
        await query.edit_message_text(
            "👤 <b>Telegram Username Bhejo:</b>\n\n"
            "Example: <code>@abhisxhxz</code> ya <code>abhisxhxz</code>"
            f"{FOOTER_TEXT}",
            reply_markup=get_back_button(),
            parse_mode="HTML",
        )

    elif data == "refer_earn":
        ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
        await query.edit_message_text(
            "🎁 <b>Refer & Earn Program:</b>\n\n"
            "Apne dosto ko bot refer karo aur har referral par <b>5 extra credits</b> paao!\n\n"
            f"🔗 <b>Aapka Unique Referral Link:</b>\n<code>{ref_link}</code>\n\n"
            "<i>(Link par tap karke copy karein aur share karein)</i>"
            f"{FOOTER_TEXT}",
            reply_markup=get_back_button(),
            parse_mode="HTML"
        )

    elif data == "my_credits":
        credits = get_user_credits(user_id)
        ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
        await query.edit_message_text(
            "💳 <b>Aapka Account Status:</b>\n\n"
            f"🔹 <b>Available Credits:</b> <code>{credits}</code> searches\n"
            "🔹 <b>Daily Reset:</b> 5 Searches Har Din\n\n"
            f"🔗 <b>Invite Link:</b>\n<code>{ref_link}</code>"
            f"{FOOTER_TEXT}",
            reply_markup=get_back_button(),
            parse_mode="HTML"
        )

    elif data == "back_home":
        USER_STATES[user_id] = None
        await start(update, context)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = USER_STATES.get(user_id)
    text = update.message.text.strip()

    if not state:
        await update.message.reply_text(
            "Kripya menu se option select karein:",
            reply_markup=get_main_menu(),
        )
        return

    if get_user_credits(user_id) <= 0:
        await update.message.reply_text(
            "❌ <b>Credits Khatam!</b>\n\n"
            "Aapka aaj ka limit complete ho chuka hai. Referral link share karke credits add karein.",
            reply_markup=get_main_menu(),
            parse_mode="HTML"
        )
        USER_STATES[user_id] = None
        return

    # --- NUM INFO LOOKUP ---
    if state == "AWAITING_NUM":
        clean_num = text.replace("+91", "").replace(" ", "").replace("-", "")
        if not (clean_num.isdigit() and len(clean_num) == 10):
            await update.message.reply_text(
                "❌ Kripya sahi 10-digit mobile number enter karein.",
                reply_markup=get_back_button(),
            )
            return

        deduct_credit(user_id)
        rem_credits = get_user_credits(user_id)

        status_msg = await update.message.reply_text("⏳ <i>Searching details in database...</i>", parse_mode="HTML")
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

        try:
            url = f"https://kallu-api.vercel.app/api?num={clean_num}"
            res = await http_client.get(url)
            if res.status_code == 200:
                data = res.json()
                if data.get("status") == "success" and "result" in data:
                    r = data["result"]
                    reply = (
                        "📋 <b>DETAILS FOUND:</b>\n"
                        "━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"👤 <b>Name:</b> <code>{r.get('name', 'N/A')}</code>\n"
                        f"📞 <b>Mobile:</b> <code>{r.get('mobile', clean_num)}</code>\n"
                        f"📱 <b>Alt Mobile:</b> <code>{r.get('alt_mobile', 'N/A')}</code>\n"
                        f"📍 <b>Circle:</b> <code>{r.get('circle', 'N/A')}</code>\n"
                        f"🏠 <b>Address:</b> <code>{r.get('address', 'N/A')}</code>\n\n"
                        f"💳 <i>Remaining Credits: {rem_credits}</i>"
                        f"{FOOTER_TEXT}"
                    )
                else:
                    reply = f"❌ Number <code>{clean_num}</code> ka data nahi mila.\n💳 <i>Remaining Credits: {rem_credits}</i>{FOOTER_TEXT}"
            else:
                reply = f"⚠️ Server response error ({res.status_code}).{FOOTER_TEXT}"
        except httpx.TimeoutException:
            reply = f"⏱️ Server Timeout! Database busy hai.{FOOTER_TEXT}"
        except Exception as e:
            reply = f"⚠️ Error: {str(e)}{FOOTER_TEXT}"

        USER_STATES[user_id] = None
        await status_msg.edit_text(reply, reply_markup=get_back_button(), parse_mode="HTML")

    # --- USERNAME TO NUMBER LOOKUP ---
    elif state == "AWAITING_USERNAME":
        clean_user = text.replace("@", "").strip()

        deduct_credit(user_id)
        rem_credits = get_user_credits(user_id)

        status_msg = await update.message.reply_text("⏳ <i>Searching username in database...</i>", parse_mode="HTML")
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

        try:
            url = f"https://kallu-api.vercel.app/tg?username={clean_user}"
            res = await http_client.get(url)
            if res.status_code == 200:
                data = res.json()
                if data.get("status") == "success" and "number" in data:
                    phone = data["number"]
                    reply = (
                        "🎯 <b>NUMBER FOUND:</b>\n"
                        "━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"🏷 <b>Username:</b> @{clean_user}\n"
                        f"📞 <b>Phone:</b> <code>{phone}</code>\n\n"
                        f"💳 <i>Remaining Credits: {rem_credits}</i>"
                        f"{FOOTER_TEXT}"
                    )
                else:
                    reply = (
                        f"❌ Username @{clean_user} ka number nahi mila.\n\n"
                        f"💳 <i>Remaining Credits: {rem_credits}</i>"
                        f"{FOOTER_TEXT}"
                    )
            else:
                reply = f"⚠️ Server error ({res.status_code}).{FOOTER_TEXT}"
        except httpx.TimeoutException:
            reply = f"⏱️ Server Timeout! API response time out ho gaya.{FOOTER_TEXT}"
        except Exception as e:
            reply = f"⚠️ Error: {str(e)}{FOOTER_TEXT}"

        USER_STATES[user_id] = None
        await status_msg.edit_text(reply, reply_markup=get_back_button(), parse_mode="HTML")

# --- RENDER WEB SERVER ---
async def handle_health_check(request):
    return web.Response(text="Info Bot 24/7 is active!")

async def start_web_server():
    server = web.Application()
    server.router.add_get("/", handle_health_check)
    runner = web.AppRunner(server)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def keep_alive_ping():
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if not render_url:
        return
    while True:
        await asyncio.sleep(600)
        try:
            await http_client.get(render_url)
        except Exception:
            pass

async def main():
    await start_web_server()
    asyncio.create_task(keep_alive_ping())

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)

    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
