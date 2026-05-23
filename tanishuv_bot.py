import asyncio
import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, ContextTypes, filters

BOT_TOKEN = "8917321620:AAGHWTm0Q5mGQao_X9j34eAOne92_4IvznQ"
ADMIN_ID = 2050916191

REG_NAME, REG_AGE, REG_GENDER, REG_LOOKING, REG_CITY, REG_BIO, REG_PHOTO, SEND_MSG = range(8)

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)
DB = "tanishuv.db"

def init_db():
    con = sqlite3.connect(DB)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT, age INTEGER, gender TEXT, looking TEXT, city TEXT, bio TEXT, photo_id TEXT, active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS likes (from_id INTEGER, to_id INTEGER, PRIMARY KEY (from_id, to_id));
        CREATE TABLE IF NOT EXISTS matches (user1 INTEGER, user2 INTEGER, PRIMARY KEY (user1, user2));
        CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, from_id INTEGER, to_id INTEGER, text TEXT);
        CREATE TABLE IF NOT EXISTS views (viewer_id INTEGER, viewed_id INTEGER, PRIMARY KEY (viewer_id, viewed_id));
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
    return dict(zip(["id","name","age","gender","looking","city","bio","photo_id","active"], row))

def save_user(uid, data):
    con = db()
    fields = ", ".join(f"{k}=?" for k in data)
    con.execute(f"UPDATE users SET {fields} WHERE id=?", list(data.values()) + [uid])
    con.commit()
    con.close()

def create_user(uid):
    con = db()
    con.execute("INSERT OR IGNORE INTO users (id) VALUES (?)", (uid,))
    con.commit()
    con.close()

def get_candidate(uid):
    u = get_user(uid)
    if not u:
        return None
    gf = "" if u["looking"] == "farqi_yoq" else f"AND gender='{u['looking']}'"
    con = db()
    row = con.execute(f"SELECT * FROM users WHERE id!=? AND active=1 AND id NOT IN (SELECT to_id FROM likes WHERE from_id=?) AND id NOT IN (SELECT viewed_id FROM views WHERE viewer_id=?) {gf} ORDER BY RANDOM() LIMIT 1", (uid, uid, uid)).fetchone()
    con.close()
    if not row:
        return None
    return dict(zip(["id","name","age","gender","looking","city","bio","photo_id","active"], row))

def add_like(from_id, to_id):
    con = db()
    con.execute("INSERT OR IGNORE INTO likes VALUES (?,?)", (from_id, to_id))
    mutual = con.execute("SELECT 1 FROM likes WHERE from_id=? AND to_id=?", (to_id, from_id)).fetchone()
    matched = False
    if mutual:
        u1, u2 = sorted([from_id, to_id])
        con.execute("INSERT OR IGNORE INTO matches VALUES (?,?)", (u1, u2))
        matched = True
    con.commit()
    con.close()
    return matched

def get_matches(uid):
    con = db()
    rows = con.execute("SELECT u.id, u.name, u.age, u.city, u.photo_id FROM matches m JOIN users u ON (CASE WHEN m.user1=? THEN m.user2 ELSE m.user1 END = u.id) WHERE m.user1=? OR m.user2=?", (uid, uid, uid)).fetchall()
    con.close()
    return rows

def profile_text(u):
    g = "👨 Erkak" if u["gender"] == "erkak" else "👩 Ayol"
    l = {"erkak": "👨 Erkak", "ayol": "👩 Ayol", "farqi_yoq": "💫 Farqi yo'q"}.get(u["looking"], "")
    return f"✨ *{u['name']}*, {u['age']} yosh\n📍 {u['city']}\n👤 {g} | {l}\n\n💬 _{u['bio']}_"

def browse_kb(cid):
    return InlineKeyboardMarkup([[InlineKeyboardButton("❤️ Like", callback_data=f"like:{cid}"), InlineKeyboardButton("👎 O'tkazish", callback_data=f"skip:{cid}")], [InlineKeyboardButton("💌 Xabar yoz", callback_data=f"msg:{cid}")], [InlineKeyboardButton("🏠 Menyu", callback_data="menu")]])

def main_kb():
    return ReplyKeyboardMarkup([["🔍 Qidirish", "💕 Matchlarim"], ["👤 Profilim", "⚙️ Sozlamalar"]], resize_keyboard=True)

async def show_next(update, ctx, uid):
    c = get_candidate(uid)
    con = db()
    if c:
        con.execute("INSERT OR IGNORE INTO views VALUES (?,?)", (uid, c["id"]))
        con.commit()
    con.close()
    send = update.message.reply_text if hasattr(update, "message") and update.message else update.edit_message_text
    send_photo = update.message.reply_photo if hasattr(update, "message") and update.message else None
    if not c:
        txt = "😔 Hozircha profil yo'q!"
        if hasattr(update, "message") and update.message:
            await update.message.reply_text(txt, reply_markup=main_kb())
        else:
            await update.edit_message_text(txt)
        return
    kb = browse_kb(c["id"])
    txt = profile_text(c)
    if c["photo_id"] and send_photo:
        await send_photo(c["photo_id"], caption=txt, parse_mode="Markdown", reply_markup=kb)
    elif c["photo_id"]:
        await update.message.reply_photo(c["photo_id"], caption=txt, parse_mode="Markdown", reply_markup=kb)
    elif hasattr(update, "message") and update.message:
        await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.edit_message_text(txt, parse_mode="Markdown", reply_markup=kb)

async def start(update, ctx):
    uid = update.effective_user.id
    create_user(uid)
    u = get_user(uid)
    if u and u["name"]:
        await update.message.reply_text(f"Xush kelibsiz, *{u['name']}*!", parse_mode="Markdown", reply_markup=main_kb())
        return ConversationHandler.END
    await update.message.reply_text("💕 *TANISHUV BOT*ga xush kelibsiz!\n\nIsmingizni yozing:", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    return REG_NAME

async def reg_name(update, ctx):
    name = update.message.text.strip()
    if len(name) < 2 or len(name) > 30:
        await update.message.reply_text("❗ Ism 2-30 belgi bo'lsin:")
        return REG_NAME
    ctx.user_data["reg"] = {"name": name}
    await update.message.reply_text(f"Zo'r, *{name}*! Yoshingizni yozing:", parse_mode="Markdown")
    return REG_AGE

async def reg_age(update, ctx):
    try:
        age = int(update.message.text.strip())
        assert 16 <= age <= 80
    except:
        await update.message.reply_text("❗ Yoshingizni to'g'ri kiriting (16-80):")
        return REG_AGE
    ctx.user_data["reg"]["age"] = age
    await update.message.reply_text("Jinsingiz?", reply_markup=ReplyKeyboardMarkup([["👨 Erkak", "👩 Ayol"]], resize_keyboard=True, one_time_keyboard=True))
    return REG_GENDER

async def reg_gender(update, ctx):
    txt = update.message.text
    if "Erkak" in txt:
        ctx.user_data["reg"]["gender"] = "erkak"
    elif "Ayol" in txt:
        ctx.user_data["reg"]["gender"] = "ayol"
    else:
        await update.message.reply_text("❗ Tugmadan tanlang.")
        return REG_GENDER
    await update.message.reply_text("Kim bilan tanishmoqchisiz?", reply_markup=ReplyKeyboardMarkup([["👨 Erkak", "👩 Ayol"], ["💫 Farqi yo'q"]], resize_keyboard=True, one_time_keyboard=True))
    return REG_LOOKING

async def reg_looking(update, ctx):
    txt = update.message.text
    if "Erkak" in txt:
        ctx.user_data["reg"]["looking"] = "erkak"
    elif "Ayol" in txt:
        ctx.user_data["reg"]["looking"] = "ayol"
    elif "Farqi" in txt:
        ctx.user_data["reg"]["looking"] = "farqi_yoq"
    else:
        await update.message.reply_text("❗ Tugmadan tanlang.")
        return REG_LOOKING
    await update.message.reply_text("📍 Shahringizni yozing:", reply_markup=ReplyKeyboardRemove())
    return REG_CITY

async def reg_city(update, ctx):
    city = update.message.text.strip()
    if len(city) < 2:
        await update.message.reply_text("❗ Shahar nomini yozing:")
        return REG_CITY
    ctx.user_data["reg"]["city"] = city
    await update.message.reply_text("💬 O'zingiz haqingizda yozing:")
    return REG_BIO

async def reg_bio(update, ctx):
    bio = update.message.text.strip()
    if len(bio) < 5:
        await update.message.reply_text("❗ Kamida 5 harf yozing:")
        return REG_BIO
    ctx.user_data["reg"]["bio"] = bio
    await update.message.reply_text("📸 Rasmingizni yuboring:", reply_markup=ReplyKeyboardMarkup([["⏭ O'tkazish"]], resize_keyboard=True, one_time_keyboard=True))
    return REG_PHOTO

async def reg_photo(update, ctx):
    uid = update.effective_user.id
    photo_id = update.message.photo[-1].file_id if update.message.photo else None
    reg = ctx.user_data.get("reg", {})
    reg["photo_id"] = photo_id
    con = db()
    con.execute("UPDATE users SET name=?, age=?, gender=?, looking=?, city=?, bio=?, photo_id=? WHERE id=?", (reg["name"], reg["age"], reg["gender"], reg["looking"], reg["city"], reg["bio"], reg["photo_id"], uid))
    con.commit()
    con.close()
    await update.message.reply_text("🎉 Profil tayyor! Qidiruvni boshlang!", reply_markup=main_kb())
    return ConversationHandler.END

async def cb(update, ctx):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    data = q.data
    if data == "menu":
        await q.message.reply_text("Bosh menyu:", reply_markup=main_kb())
        return
    action, cid_str = data.split(":", 1)
    cid = int(cid_str)
    if action == "like":
        matched = add_like(uid, cid)
        if matched:
            other = get_user(cid)
            me = get_user(uid)
            await q.message.reply_text(f"🎉 MATCH! *{other['name']}* ham sizni yoqtirdi!", parse_mode="Markdown", reply_markup=main_kb())
            try:
                await ctx.bot.send_message(cid, f"🎉 MATCH! *{me['name']}* ham sizni yoqtirdi!", parse_mode="Markdown")
            except:
                pass
        await show_next(q, ctx, uid)
    elif action == "skip":
        await show_next(q, ctx, uid)
    elif action == "msg":
        u1, u2 = sorted([uid, cid])
        con = db()
        match = con.execute("SELECT 1 FROM matches WHERE user1=? AND user2=?", (u1, u2)).fetchone()
        con.close()
        if not match:
            await q.answer("❗ Avval match bo'lishi kerak!", show_alert=True)
            return
        ctx.user_data["msg_to"] = cid
        other = get_user(cid)
        await q.message.reply_text(f"✍️ *{other['name']}* ga xabar yozing:", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
        return SEND_MSG
    elif action == "send_msg":
        ctx.user_data["msg_to"] = cid
        other = get_user(cid)
        await q.message.reply_text(f"✍️ *{other['name']}* ga xabar yozing:", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
        return SEND_MSG

async def send_msg(update, ctx):
    uid = update.effective_user.id
    to = ctx.user_data.get("msg_to")
    if not to:
        await update.message.reply_text("❗ Xato.", reply_markup=main_kb())
        return ConversationHandler.END
    me = get_user(uid)
    try:
        await ctx.bot.send_message(to, f"💌 *{me['name']}* dan:\n\n{update.message.text}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💬 Javob", callback_data=f"send_msg:{uid}")]]))
        await update.message.reply_text("✅ Yuborildi!", reply_markup=main_kb())
    except:
        await update.message.reply_text("❗ Xabar yuborib bo'lmadi.", reply_markup=main_kb())
    ctx.user_data.pop("msg_to", None)
    return ConversationHandler.END

async def my_matches(update, ctx):
    uid = update.effective_user.id
    matches = get_matches(uid)
    if not matches:
        await update.message.reply_text("💔 Hozircha match yo'q!", reply_markup=main_kb())
        return
    text = "💕 *Matchlaringiz:*\n\n"
    btns = []
    for m in matches:
        mid, mname, mage, mcity, _ = m
        text += f"• *{mname}*, {mage} yosh — {mcity}\n"
        btns.append([InlineKeyboardButton(f"💌 {mname}ga yoz", callback_data=f"msg:{mid}")])
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(btns))

async def my_profile(update, ctx):
    uid = update.effective_user.id
    u = get_user(uid)
    if not u or not u["name"]:
        await update.message.reply_text("Profil topilmadi. /start bosing.")
        return
    txt = f"👤 *Profilingiz:*\n\n{profile_text(u)}"
    if u["photo_id"]:
        await update.message.reply_photo(u["photo_id"], caption=txt, parse_mode="Markdown", reply_markup=main_kb())
    else:
        await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())

async def settings(update, ctx):
    await update.message.reply_text("⚙️ Sozlamalar:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🚫 Yashirish", callback_data="deactivate")], [InlineKeyboardButton("✅ Ko'rsatish", callback_data="activate")]]))

async def settings_cb(update, ctx):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if q.data == "deactivate":
        save_user(uid, {"active": 0})
        await q.edit_message_text("🚫 Profil yashirildi.")
    elif q.data == "activate":
        save_user(uid, {"active": 1})
        await q.edit_message_text("✅ Profil faollashtirildi!")

async def text_router(update, ctx):
    txt = update.message.text
    if txt == "🔍 Qidirish":
        u = get_user(update.effective_user.id)
        if not u or not u["name"]:
            await update.message.reply_text("Avval /start bosing.")
            return
        await show_next(update, ctx, update.effective_user.id)
    elif txt == "💕 Matchlarim":
        await my_matches(update, ctx)
    elif txt == "👤 Profilim":
        await my_profile(update, ctx)
    elif txt == "⚙️ Sozlamalar":
        await settings(update, ctx)
    else:
        await update.message.reply_text("Menyu tugmalaridan foydalaning 👇", reply_markup=main_kb())

async def cancel(update, ctx):
    await update.message.reply_text("❌ Bekor qilindi.", reply_markup=main_kb())
    return ConversationHandler.END

async def stats(update, ctx):
    if update.effective_user.id != ADMIN_ID:
        return
    con = db()
    u = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    l = con.execute("SELECT COUNT(*) FROM likes").fetchone()[0]
    m = con.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    con.close()
    await update.message.reply_text(f"📊 Foydalanuvchilar: {u}\n❤️ Likelar: {l}\n💕 Matchlar: {m}")

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    reg = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            REG_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_name)],
            REG_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_age)],
            REG_GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_gender)],
            REG_LOOKING: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_looking)],
            REG_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_city)],
            REG_BIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_bio)],
            REG_PHOTO: [MessageHandler(filters.PHOTO | filters.TEXT, reg_photo)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
    msg = ConversationHandler(
        entry_points=[CallbackQueryHandler(cb, pattern="^send_msg:")],
        states={SEND_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_msg)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(reg)
    app.add_handler(msg)
    app.add_handler(CallbackQueryHandler(settings_cb, pattern="^(deactivate|activate)$"))
    app.add_handler(CallbackQueryHandler(cb))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))
    log.info("Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
