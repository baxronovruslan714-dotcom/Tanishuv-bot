"""
💕 TANISHUV BOT — To'liq Telegram Dating Bot
Muallif: Claude (Anthropic)
Versiya: 1.0

Talablar:
  pip install python-telegram-bot==20.7 aiosqlite

Ishga tushirish:
  python tanishuv_bot.py
"""

import asyncio
import logging
import sqlite3
import os
from datetime import datetime
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, ContextTypes, filters
)

# ══════════════════════════════════════════
#  SOZLAMALAR — bu yerni o'zgartiring
# ══════════════════════════════════════════
BOT_TOKEN = "8917321620:AAGHWTm0Q5mGQao_X9j34eAOne92_4IvznQ"
ADMIN_ID   = 2050916191

# ══════════════════════════════════════════
#  HOLATLAR (ConversationHandler states)
# ══════════════════════════════════════════
(
    REG_NAME, REG_AGE, REG_GENDER, REG_LOOKING,
    REG_CITY, REG_BIO, REG_PHOTO,
    BROWSING, SEND_MSG
) = range(9)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)

DB = "tanishuv.db"

# ══════════════════════════════════════════
#  MA'LUMOTLAR BAZASI
# ══════════════════════════════════════════
def init_db():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY,   -- Telegram ID
            name        TEXT,
            age         INTEGER,
            gender      TEXT,                  -- 'erkak' | 'ayol'
            looking     TEXT,                  -- 'erkak' | 'ayol' | 'farqi_yoq'
            city        TEXT,
            bio         TEXT,
            photo_id    TEXT,
            active      INTEGER DEFAULT 1,
            created_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS likes (
            from_id  INTEGER,
            to_id    INTEGER,
            PRIMARY KEY (from_id, to_id)
        );
        CREATE TABLE IF NOT EXISTS matches (
            user1    INTEGER,
            user2    INTEGER,
            PRIMARY KEY (user1, user2)
        );
        CREATE TABLE IF NOT EXISTS messages (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            from_id   INTEGER,
            to_id     INTEGER,
            text      TEXT,
            sent_at   TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS views (
            viewer_id   INTEGER,
            viewed_id   INTEGER,
            PRIMARY KEY (viewer_id, viewed_id)
        );
    """)
    con.commit()
    con.close()

def db():
    return sqlite3.connect(DB)

def get_user(uid):
    con = db()
    row = con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    con.close()
    if not row:
        return None
    keys = ["id","name","age","gender","looking","city","bio","photo_id","active","created_at"]
    return dict(zip(keys, row))

def save_user(uid, data: dict):
    con = db()
    fields = ", ".join(f"{k}=?" for k in data)
    vals = list(data.values()) + [uid]
    con.execute(f"UPDATE users SET {fields} WHERE id=?", vals)
    con.commit(); con.close()

def create_user(uid):
    con = db()
    con.execute("INSERT OR IGNORE INTO users (id) VALUES (?)", (uid,))
    con.commit(); con.close()

def get_candidate(uid):
    """Ko'rilmagan, like/dislike qilinmagan, mos keladigan profil topish"""
    u = get_user(uid)
    if not u:
        return None
    looking = u["looking"]
    gender_filter = "" if looking == "farqi_yoq" else f"AND gender='{looking}'"
    con = db()
    row = con.execute(f"""
        SELECT * FROM users
        WHERE id != ?
          AND active = 1
          AND id NOT IN (SELECT to_id   FROM likes   WHERE from_id=?)
          AND id NOT IN (SELECT viewed_id FROM views WHERE viewer_id=?)
          {gender_filter}
        ORDER BY RANDOM()
        LIMIT 1
    """, (uid, uid, uid)).fetchone()
    con.close()
    if not row:
        return None
    keys = ["id","name","age","gender","looking","city","bio","photo_id","active","created_at"]
    return dict(zip(keys, row))

def add_view(viewer, viewed):
    con = db()
    con.execute("INSERT OR IGNORE INTO views VALUES (?,?)", (viewer, viewed))
    con.commit(); con.close()

def add_like(from_id, to_id):
    con = db()
    con.execute("INSERT OR IGNORE INTO likes VALUES (?,?)", (from_id, to_id))
    # O'zaro like — match!
    mutual = con.execute(
        "SELECT 1 FROM likes WHERE from_id=? AND to_id=?", (to_id, from_id)
    ).fetchone()
    matched = False
    if mutual:
        u1, u2 = sorted([from_id, to_id])
        con.execute("INSERT OR IGNORE INTO matches VALUES (?,?)", (u1, u2))
        matched = True
    con.commit(); con.close()
    return matched

def get_matches(uid):
    con = db()
    rows = con.execute("""
        SELECT u.id, u.name, u.age, u.city, u.photo_id
        FROM matches m
        JOIN users u ON (
            CASE WHEN m.user1=? THEN m.user2 ELSE m.user1 END = u.id
        )
        WHERE m.user1=? OR m.user2=?
    """, (uid, uid, uid)).fetchall()
    con.close()
    return rows

def save_message(from_id, to_id, text):
    con = db()
    con.execute("INSERT INTO messages (from_id,to_id,text) VALUES (?,?,?)", (from_id, to_id, text))
    con.commit(); con.close()

def get_stats():
    con = db()
    users  = con.execute("SELECT COUNT(*) FROM users WHERE active=1").fetchone()[0]
    likes  = con.execute("SELECT COUNT(*) FROM likes").fetchone()[0]
    matchs = con.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    msgs   = con.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    con.close()
    return users, likes, matchs, msgs

# ══════════════════════════════════════════
#  YORDAMCHI FUNKSIYALAR
# ══════════════════════════════════════════
GENDER_UZ = {"erkak": "👨 Erkak", "ayol": "👩 Ayol"}
LOOKING_UZ = {"erkak": "👨 Erkak", "ayol": "👩 Ayol", "farqi_yoq": "💫 Farqi yo'q"}

def profile_text(u):
    g = GENDER_UZ.get(u["gender"], u["gender"])
    l = LOOKING_UZ.get(u["looking"], u["looking"])
    return (
        f"✨ *{u['name']}*, {u['age']} yosh\n"
        f"📍 {u['city']}\n"
        f"👤 Jinsi: {g}  |  Qidiryapti: {l}\n\n"
        f"💬 _{u['bio']}_"
    )

def browse_keyboard(candidate_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("❤️ Like",    callback_data=f"like:{candidate_id}"),
            InlineKeyboardButton("👎 O'tkazish", callback_data=f"skip:{candidate_id}"),
        ],
        [InlineKeyboardButton("💌 Xabar yoz", callback_data=f"msg:{candidate_id}")],
        [InlineKeyboardButton("🏠 Bosh menyu",  callback_data="menu")],
    ])

def main_menu_keyboard():
    return ReplyKeyboardMarkup([
        ["🔍 Qidirish", "💕 Matchlarim"],
        ["👤 Profilim", "⚙️ Sozlamalar"],
    ], resize_keyboard=True)

# ══════════════════════════════════════════
#  /start — BOSHLASH
# ══════════════════════════════════════════
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
< truncated lines 226-426 >
            # Ikkoviga ham xabar
            await q.message.reply_text(
                f"🎉 *MATCH!* {other['name']} ham sizni yoqtirdi!\n"
                f"Endi xabar yoza olasiz 💌",
                parse_mode="Markdown", reply_markup=main_menu_keyboard()
            )
            try:
                await ctx.bot.send_message(
                    cid,
                    f"🎉 *MATCH!* {me['name']} ham sizni yoqtirdi!\n"
                    f"Endi xabar yoza olasiz 💌",
                    parse_mode="Markdown"
                )
            except: pass
        else:
            await q.answer("❤️ Like yuborildi!", show_alert=False)
        await show_next_candidate(q, ctx, uid)

    elif action == "skip":
        await show_next_candidate(q, ctx, uid)

    elif action == "msg":
        # Match borligini tekshirish
        u1, u2 = sorted([uid, cid])
        con = db()
        match = con.execute("SELECT 1 FROM matches WHERE user1=? AND user2=?", (u1, u2)).fetchone()
        con.close()
        if not match:
            await q.answer("❗ Xabar yozish uchun avval match bo'lishi kerak!", show_alert=True)
            return
        ctx.user_data["msg_to"] = cid
        other = get_user(cid)
        await q.message.reply_text(
            f"✍️ *{other['name']}* ga xabar yozing:\n_(Bekor qilish uchun /cancel)_",
            parse_mode="Markdown", reply_markup=ReplyKeyboardRemove()
        )
        return SEND_MSG

    elif action.startswith("send_msg:"):
        ctx.user_data["msg_to"] = int(action.split(":")[1])
        other = get_user(ctx.user_data["msg_to"])
        await q.message.reply_text(
            f"✍️ *{other['name']}* ga xabar yozing:",
            parse_mode="Markdown", reply_markup=ReplyKeyboardRemove()
        )
        return SEND_MSG

# ══════════════════════════════════════════
#  XABAR YUBORISH (match bo'lganlar orasida)
# ══════════════════════════════════════════
async def send_message_handler(update: Update, ctx):
    uid  = update.effective_user.id
    to   = ctx.user_data.get("msg_to")
    text = update.message.text.strip()

    if not to:
        await update.message.reply_text("❗ Xato. /start bosing.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    save_message(uid, to, text)
    me = get_user(uid)
    try:
        await ctx.bot.send_message(
            to,
            f"💌 *{me['name']}* dan xabar:\n\n{text}\n\n"
            f"_(Javob berish uchun quyidagi tugmani bosing)_",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💬 Javob berish", callback_data=f"send_msg:{uid}")
            ]])
        )
        await update.message.reply_text("✅ Xabar yuborildi!", reply_markup=main_menu_keyboard())
    except:
        await update.message.reply_text("❗ Xabar yuborib bo'lmadi (foydalanuvchi botni bloklagan bo'lishi mumkin).",
                                        reply_markup=main_menu_keyboard())
    ctx.user_data.pop("msg_to", None)
    return ConversationHandler.END

# ══════════════════════════════════════════
#  MATCHLAR RO'YXATI
# ══════════════════════════════════════════
async def my_matches(update: Update, ctx):
    uid = update.effective_user.id
    matches = get_matches(uid)
    if not matches:
        await update.message.reply_text(
            "💔 Hozircha matchlaringiz yo'q.\nQidiruvni davom ettiring! 🔍",
            reply_markup=main_menu_keyboard()
        )
        return
    text = "💕 *Sizning matchlaringiz:*\n\n"
    btns = []
    for m in matches:
        mid, mname, mage, mcity, _ = m
        text += f"• *{mname}*, {mage} yosh — {mcity}\n"
        btns.append([InlineKeyboardButton(f"💌 {mname}ga yoz", callback_data=f"send_msg:{mid}")])
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(btns))

# ══════════════════════════════════════════
#  PROFIL KO'RISH / SOZLAMALAR
# ══════════════════════════════════════════
async def my_profile(update: Update, ctx):
    uid = update.effective_user.id
    u = get_user(uid)
    if not u or not u["name"]:
        await update.message.reply_text("Profil topilmadi. /start bosing.")
        return
    txt = f"👤 *Sizning profilingiz:*\n\n{profile_text(u)}"
    if u["photo_id"]:
        await update.message.reply_photo(u["photo_id"], caption=txt, parse_mode="Markdown",
                                         reply_markup=main_menu_keyboard())
    else:
        await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_menu_keyboard())

async def settings(update: Update, ctx):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Profilni qayta yaratish", callback_data="restart")],
        [InlineKeyboardButton("🚫 Profilni o'chirish",     callback_data="deactivate")],
        [InlineKeyboardButton("✅ Profilni yoqish",        callback_data="activate")],
    ])
    await update.message.reply_text("⚙️ *Sozlamalar:*", parse_mode="Markdown", reply_markup=kb)

async def settings_callback(update: Update, ctx):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    if q.data == "deactivate":
        save_user(uid, {"active": 0})
        await q.edit_message_text("🚫 Profilingiz vaqtincha yashirildi.")
    elif q.data == "activate":
        save_user(uid, {"active": 1})
        await q.edit_message_text("✅ Profilingiz faollashtirildi!")
    elif q.data == "restart":
        save_user(uid, {"name": None, "bio": None})
        await q.edit_message_text("Profilni qayta yaratamiz. /start bosing.")

# ══════════════════════════════════════════
#  ADMIN PANEL
# ══════════════════════════════════════════
async def admin_stats(update: Update, ctx):
    if update.effective_user.id != ADMIN_ID:
        return
    users, likes, matchs, msgs = get_stats()
    await update.message.reply_text(
        f"📊 *Admin statistika:*\n\n"
        f"👥 Foydalanuvchilar: `{users}`\n"
        f"❤️  Likelar:          `{likes}`\n"
        f"💕 Matchlar:         `{matchs}`\n"
        f"💬 Xabarlar:         `{msgs}`",
        parse_mode="Markdown"
    )

# ══════════════════════════════════════════
#  ASOSIY XABAR HANDLER
# ══════════════════════════════════════════
async def text_router(update: Update, ctx):
    txt = update.message.text
    if txt == "🔍 Qidirish":
        await browse(update, ctx)
    elif txt == "💕 Matchlarim":
        await my_matches(update, ctx)
    elif txt == "👤 Profilim":
        await my_profile(update, ctx)
    elif txt == "⚙️ Sozlamalar":
        await settings(update, ctx)
    else:
        await update.message.reply_text(
            "Menyu tugmalaridan foydalaning 👇",
            reply_markup=main_menu_keyboard()
        )

async def cancel(update: Update, ctx):
    await update.message.reply_text("❌ Bekor qilindi.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END

# ══════════════════════════════════════════
#  ASOSIY ISHGA TUSHIRISH
# ══════════════════════════════════════════
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # Ro'yxatdan o'tish / profil yaratish
    reg_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            REG_NAME:    [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_name)],
            REG_AGE:     [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_age)],
            REG_GENDER:  [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_gender)],
            REG_LOOKING: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_looking)],
            REG_CITY:    [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_city)],
            REG_BIO:     [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_bio)],
            REG_PHOTO:   [
                MessageHandler(filters.PHOTO, reg_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, reg_photo),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    # Xabar yuborish holati
    msg_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(callback_handler, pattern="^send_msg:")],
        states={
            SEND_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_message_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(reg_conv)
    app.add_handler(msg_conv)
    app.add_handler(CallbackQueryHandler(settings_callback, pattern="^(deactivate|activate|restart)$"))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(CommandHandler("stats", admin_stats))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))

    log.info("💕 Tanishuv bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
