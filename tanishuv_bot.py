import logging
import os
import re
import sqlite3

from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from telegram.helpers import escape_markdown

# =========================
# LOAD ENV
# =========================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB = "tanishuv.db"

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN topilmadi!")

# =========================
# STATES
# =========================

(
    REG_NAME,
    REG_AGE,
    REG_GENDER,
    REG_LOOKING,
    REG_CITY,
    REG_BIO,
    REG_PHOTO,
    SEND_MSG,
) = range(8)

# =========================
# LOGGING
# =========================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

log = logging.getLogger(__name__)

# =========================
# DATABASE
# =========================


def db():
    con = sqlite3.connect(DB, timeout=30)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = db()

    try:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                name TEXT,
                age INTEGER,
                gender TEXT,
                looking TEXT,
                city TEXT,
                bio TEXT,
                photo_id TEXT,
                active INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS likes (
                from_id INTEGER,
                to_id INTEGER,
                PRIMARY KEY (from_id, to_id)
            );

            CREATE TABLE IF NOT EXISTS matches (
                user1 INTEGER,
                user2 INTEGER,
                PRIMARY KEY (user1, user2)
            );

            CREATE TABLE IF NOT EXISTS views (
                viewer_id INTEGER,
                viewed_id INTEGER,
                PRIMARY KEY (viewer_id, viewed_id)
            );
            """
        )

        con.commit()

    finally:
        con.close()


# =========================
# DATABASE HELPERS
# =========================


def create_user(uid: int):
    con = db()

    try:
        con.execute(
            "INSERT OR IGNORE INTO users (id) VALUES (?)",
            (uid,),
        )
        con.commit()

    finally:
        con.close()


def get_user(uid: int):
    con = db()

    try:
        row = con.execute(
            "SELECT * FROM users WHERE id=?",
            (uid,),
        ).fetchone()

        return dict(row) if row else None

    finally:
        con.close()


def save_user(uid: int, data: dict):
    if not data:
        return

    con = db()

    try:
        fields = ", ".join(f"{k}=?" for k in data.keys())

        values = list(data.values())
        values.append(uid)

        con.execute(
            f"UPDATE users SET {fields} WHERE id=?",
            values,
        )

        con.commit()

    finally:
        con.close()


def add_view(viewer_id: int, viewed_id: int):
    con = db()

    try:
        con.execute(
            """
            INSERT OR IGNORE INTO views
            VALUES (?, ?)
            """,
            (viewer_id, viewed_id),
        )

        con.commit()

    finally:
        con.close()


def get_candidate(uid: int):
    user = get_user(uid)

    if not user:
        return None

    query = """
        SELECT *
        FROM users
        WHERE id != ?
          AND active = 1
          AND name IS NOT NULL
          AND id NOT IN (
              SELECT to_id
              FROM likes
              WHERE from_id = ?
          )
          AND id NOT IN (
              SELECT viewed_id
              FROM views
              WHERE viewer_id = ?
          )
    """

    params = [uid, uid, uid]

    if user["looking"] != "farqi_yoq":
        query += " AND gender = ?"
        params.append(user["looking"])

    query += " ORDER BY RANDOM() LIMIT 1"

    con = db()

    try:
        row = con.execute(query, params).fetchone()

        return dict(row) if row else None

    finally:
        con.close()


def add_like(from_id: int, to_id: int):
    con = db()

    try:
        con.execute(
            """
            INSERT OR IGNORE INTO likes
            VALUES (?, ?)
            """,
            (from_id, to_id),
        )

        mutual = con.execute(
            """
            SELECT 1
            FROM likes
            WHERE from_id=? AND to_id=?
            """,
            (to_id, from_id),
        ).fetchone()

        matched = False

        if mutual:
            u1, u2 = sorted([from_id, to_id])

            con.execute(
                """
                INSERT OR IGNORE INTO matches
                VALUES (?, ?)
                """,
                (u1, u2),
            )

            matched = True

        con.commit()

        return matched

    finally:
        con.close()


def get_matches(uid: int):
    con = db()

    try:
        rows = con.execute(
            """
            SELECT
                u.id,
                u.name,
                u.age,
                u.city,
                u.photo_id
            FROM matches m
            JOIN users u
            ON u.id = CASE
                WHEN m.user1 = ? THEN m.user2
                ELSE m.user1
            END
            WHERE m.user1 = ? OR m.user2 = ?
            """,
            (uid, uid, uid),
        ).fetchall()

        return rows

    finally:
        con.close()


# =========================
# HELPERS
# =========================


def esc(text):
    return escape_markdown(str(text), version=2)


def profile_text(user):
    gender = "👨 Erkak" if user["gender"] == "erkak" else "👩 Ayol"

    looking = {
        "erkak": "👨 Erkak",
        "ayol": "👩 Ayol",
        "farqi_yoq": "💫 Farqi yo'q",
    }.get(user["looking"], "")

    return (
        f"✨ *{esc(user['name'])}*, {user['age']} yosh\n"
        f"📍 {esc(user['city'])}\n"
        f"👤 {gender} | {looking}\n\n"
        f"💬 _{esc(user['bio'])}_"
    )


def main_kb():
    return ReplyKeyboardMarkup(
        [
            ["🔍 Qidirish", "💕 Matchlarim"],
            ["👤 Profilim", "⚙️ Sozlamalar"],
        ],
        resize_keyboard=True,
    )


def browse_kb(cid: int):
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "❤️ Like",
                    callback_data=f"like:{cid}",
                ),
                InlineKeyboardButton(
                    "👎 O'tkazish",
                    callback_data=f"skip:{cid}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "💌 Xabar yoz",
                    callback_data=f"msg:{cid}",
                )
            ],
        ]
    )


# =========================
# SHOW PROFILE
# =========================


async def show_next(update, ctx, uid):
    candidate = get_candidate(uid)

    if update.callback_query:
        try:
            await update.callback_query.message.delete()
        except Exception:
            pass

        chat_id = update.callback_query.message.chat.id

    else:
        chat_id = update.effective_chat.id

    if not candidate:
        await ctx.bot.send_message(
            chat_id=chat_id,
            text="😔 Hozircha yangi profil topilmadi.",
            reply_markup=main_kb(),
        )
        return

    add_view(uid, candidate["id"])

    text = profile_text(candidate)
    kb = browse_kb(candidate["id"])

    try:
        if candidate["photo_id"]:
            await ctx.bot.send_photo(
                chat_id=chat_id,
                photo=candidate["photo_id"],
                caption=text,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=kb,
            )
        else:
            await ctx.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=kb,
            )

    except Exception as e:
        log.error(f"show_next error: {e}")


# =========================
# START
# =========================


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    create_user(uid)

    user = get_user(uid)

    if user and user["name"]:
        await update.message.reply_text(
            f"Xush kelibsiz, {user['name']} 👋",
            reply_markup=main_kb(),
        )

        return ConversationHandler.END

    await update.message.reply_text(
        "💕 TANISHUV BOT\n\n"
        "Ismingizni yuboring:",
        reply_markup=ReplyKeyboardRemove(),
    )

    return REG_NAME


# =========================
# REGISTRATION
# =========================


async def reg_name(update, ctx):
    name = update.message.text.strip()

    if not re.match(r"^[A-Za-zА-Яа-яЁё\s\-']{2,30}$", name):
        await update.message.reply_text(
            "❗ Ism noto'g'ri.\n"
            "2-30 harf ishlating."
        )

        return REG_NAME

    ctx.user_data["reg"] = {
        "name": name
    }

    await update.message.reply_text(
        "Yoshingizni kiriting:"
    )

    return REG_AGE


async def reg_age(update, ctx):
    try:
        age = int(update.message.text)

        if age < 16 or age > 80:
            raise ValueError

    except ValueError:
        await update.message.reply_text(
            "❗ 16-80 oralig'ida kiriting."
        )

        return REG_AGE

    ctx.user_data["reg"]["age"] = age

    kb = ReplyKeyboardMarkup(
        [["👨 Erkak", "👩 Ayol"]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    await update.message.reply_text(
        "Jinsingiz:",
        reply_markup=kb,
    )

    return REG_GENDER


async def reg_gender(update, ctx):
    text = update.message.text

    if "Erkak" in text:
        gender = "erkak"

    elif "Ayol" in text:
        gender = "ayol"

    else:
        await update.message.reply_text(
            "❗ Tugmadan tanlang."
        )

        return REG_GENDER

    ctx.user_data["reg"]["gender"] = gender

    kb = ReplyKeyboardMarkup(
        [
            ["👨 Erkak", "👩 Ayol"],
            ["💫 Farqi yo'q"],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    await update.message.reply_text(
        "Kim bilan tanishmoqchisiz?",
        reply_markup=kb,
    )

    return REG_LOOKING


async def reg_looking(update, ctx):
    text = update.message.text

    if "Erkak" in text:
        looking = "erkak"

    elif "Ayol" in text:
        looking = "ayol"

    else:
        looking = "farqi_yoq"

    ctx.user_data["reg"]["looking"] = looking

    await update.message.reply_text(
        "📍 Shahringiz:",
        reply_markup=ReplyKeyboardRemove(),
    )

    return REG_CITY


async def reg_city(update, ctx):
    city = update.message.text.strip()

    if len(city) < 2:
        await update.message.reply_text(
            "❗ Shahar nomini kiriting."
        )

        return REG_CITY

    ctx.user_data["reg"]["city"] = city

    await update.message.reply_text(
        "💬 O'zingiz haqingizda yozing:"
    )

    return REG_BIO


async def reg_bio(update, ctx):
    bio = update.message.text.strip()

    if len(bio) < 5:
        await update.message.reply_text(
            "❗ Kamida 5 ta belgi."
        )

        return REG_BIO

    ctx.user_data["reg"]["bio"] = bio

    kb = ReplyKeyboardMarkup(
        [["⏭ O'tkazish"]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    await update.message.reply_text(
        "📸 Rasmingizni yuboring:",
        reply_markup=kb,
    )

    return REG_PHOTO


async def reg_photo(update, ctx):
    uid = update.effective_user.id

    photo_id = None

    if update.message.photo:
        photo_id = update.message.photo[-1].file_id

    elif update.message.text != "⏭ O'tkazish":
        await update.message.reply_text(
            "❗ Foto yuboring yoki o'tkazib yuboring."
        )

        return REG_PHOTO

    reg = ctx.user_data["reg"]

    save_user(
        uid,
        {
            "name": reg["name"],
            "age": reg["age"],
            "gender": reg["gender"],
            "looking": reg["looking"],
            "city": reg["city"],
            "bio": reg["bio"],
            "photo_id": photo_id,
            "active": 1,
        },
    )

    ctx.user_data.pop("reg", None)

    await update.message.reply_text(
        "🎉 Profil yaratildi!",
        reply_markup=main_kb(),
    )

    return ConversationHandler.END


# =========================
# CALLBACKS
# =========================


async def cb(update, ctx):
    q = update.callback_query
    await q.answer()

    uid = q.from_user.id
    data = q.data

    if ":" not in data:
        return

    action, cid_str = data.split(":", 1)

    if not cid_str.isdigit():
        return

    cid = int(cid_str)

    if action == "like":
        matched = add_like(uid, cid)

        if matched:
            other = get_user(cid)
            me = get_user(uid)

            await ctx.bot.send_message(
                q.message.chat.id,
                f"🎉 MATCH!\n"
                f"{other['name']} sizni ham yoqtirdi ❤️",
            )

            try:
                await ctx.bot.send_message(
                    cid,
                    f"🎉 MATCH!\n"
                    f"{me['name']} sizni ham yoqtirdi ❤️",
                )

            except Exception as e:
                log.error(e)

        await show_next(update, ctx, uid)

    elif action == "skip":
        await show_next(update, ctx, uid)

    elif action in ["msg", "send_msg"]:
        ctx.user_data["msg_to"] = cid

        other = get_user(cid)

        await ctx.bot.send_message(
            q.message.chat.id,
            f"✍️ {other['name']} ga yozing:",
            reply_markup=ReplyKeyboardRemove(),
        )

        return SEND_MSG


# =========================
# SEND MESSAGE
# =========================


async def send_msg(update, ctx):
    uid = update.effective_user.id

    to = ctx.user_data.get("msg_to")

    if not to:
        return ConversationHandler.END

    me = get_user(uid)

    text = update.message.text

    try:
        await ctx.bot.send_message(
            chat_id=to,
            text=f"💌 {me['name']} dan:\n\n{text}",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "💬 Javob",
                            callback_data=f"send_msg:{uid}",
                        )
                    ]
                ]
            ),
        )

        await update.message.reply_text(
            "✅ Xabar yuborildi!",
            reply_markup=main_kb(),
        )

    except Exception as e:
        log.error(e)

        await update.message.reply_text(
            "❗ Xabar yuborilmadi.",
            reply_markup=main_kb(),
        )

    ctx.user_data.pop("msg_to", None)

    return ConversationHandler.END


# =========================
# PROFILE
# =========================


async def my_profile(update, ctx):
    user = get_user(update.effective_user.id)

    if not user:
        return

    text = profile_text(user)

    if user["photo_id"]:
        await update.message.reply_photo(
            photo=user["photo_id"],
            caption=text,
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    else:
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN_V2,
        )


async def my_matches(update, ctx):
    uid = update.effective_user.id

    matches = get_matches(uid)

    if not matches:
        await update.message.reply_text(
            "💔 Matchlar yo'q."
        )

        return

    buttons = []

    text = "💕 Matchlaringiz:\n\n"

    for m in matches:
        text += f"• {m['name']} ({m['age']})\n"

        buttons.append(
            [
                InlineKeyboardButton(
                    f"💌 {m['name']}",
                    callback_data=f"msg:{m['id']}",
                )
            ]
        )

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


# =========================
# SETTINGS
# =========================


async def settings(update, ctx):
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🚫 Yashirish",
                    callback_data="deactivate",
                )
            ],
            [
                InlineKeyboardButton(
                    "✅ Faollashtirish",
                    callback_data="activate",
                )
            ],
        ]
    )

    await update.message.reply_text(
        "⚙️ Sozlamalar:",
        reply_markup=kb,
    )


async def settings_cb(update, ctx):
    q = update.callback_query
    await q.answer()

    uid = q.from_user.id

    if q.data == "deactivate":
        save_user(uid, {"active": 0})

        await q.edit_message_text(
            "🚫 Profil yashirildi."
        )

    elif q.data == "activate":
        save_user(uid, {"active": 1})

        await q.edit_message_text(
            "✅ Profil faollashtirildi."
        )


# =========================
# TEXT ROUTER
# =========================


async def text_router(update, ctx):
    text = update.message.text
    uid = update.effective_user.id

    if text == "🔍 Qidirish":
        await show_next(update, ctx, uid)

    elif text == "💕 Matchlarim":
        await my_matches(update, ctx)

    elif text == "👤 Profilim":
        await my_profile(update, ctx)

    elif text == "⚙️ Sozlamalar":
        await settings(update, ctx)

    else:
        await update.message.reply_text(
            "👇 Menyudan foydalaning",
            reply_markup=main_kb(),
        )


# =========================
# CANCEL
# =========================


async def cancel(update, ctx):
    await update.message.reply_text(
        "❌ Bekor qilindi.",
        reply_markup=main_kb(),
    )

    return ConversationHandler.END


# =========================
# ADMIN
# =========================


async def stats(update, ctx):
    if update.effective_user.id != ADMIN_ID:
        return

    con = db()

    try:
        users = con.execute(
            "SELECT COUNT(*) FROM users WHERE name IS NOT NULL"
        ).fetchone()[0]

        likes = con.execute(
            "SELECT COUNT(*) FROM likes"
        ).fetchone()[0]

        matches = con.execute(
            "SELECT COUNT(*) FROM matches"
        ).fetchone()[0]

    finally:
        con.close()

    await update.message.reply_text(
        f"📊 Statistika\n\n"
        f"👤 Users: {users}\n"
        f"❤️ Likes: {likes}\n"
        f"💕 Matches: {matches}"
    )


# =========================
# MAIN
# =========================


def main():
    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    reg_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start)
        ],

        states={
            REG_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    reg_name,
                )
            ],

            REG_AGE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    reg_age,
                )
            ],

            REG_GENDER: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    reg_gender,
                )
            ],

            REG_LOOKING: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    reg_looking,
                )
            ],

            REG_CITY: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    reg_city,
                )
            ],

            REG_BIO: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    reg_bio,
                )
            ],

            REG_PHOTO: [
                MessageHandler(
                    filters.PHOTO,
                    reg_photo,
                ),

                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    reg_photo,
                ),
            ],
        },

        fallbacks=[
            CommandHandler("cancel", cancel)
        ],

        allow_reentry=True,
    )

    msg_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                cb,
                pattern="^(msg:|send_msg:)"
            )
        ],

        states={
            SEND_MSG: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    send_msg,
                )
            ]
        },

        fallbacks=[
            CommandHandler("cancel", cancel)
        ],
    )

    app.add_handler(reg_handler)
    app.add_handler(msg_handler)

    app.add_handler(
        CallbackQueryHandler(
            settings_cb,
            pattern="^(activate|deactivate)$",
        )
    )

    app.add_handler(
        CallbackQueryHandler(cb)
    )

    app.add_handler(
        CommandHandler("stats", stats)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_router,
        )
    )

    log.info("Bot ishga tushdi!")

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    mai
