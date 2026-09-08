import os
import sqlite3
import telebot
from telebot import types

# =========================
# إعدادات البوت
# =========================

BOT_TOKEN = os.getenv("8582451165:AAGVytO4wBe5mRPfkOQaDXhq1WSWmrb7KQs")
DEVELOPER_USERNAME = os.getenv("DEVELOPER_USERNAME", "u_8_y")

# آيدي المطور
DEVELOPER_IDS = {1920665874}

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in Railway Variables")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

DB_NAME = "bot_database.db"

# =========================
# قاعدة البيانات
# =========================

db = sqlite3.connect(DB_NAME, check_same_thread=False)
cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS groups (
    chat_id INTEGER PRIMARY KEY,
    active INTEGER DEFAULT 1
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
""")

db.commit()


# =========================
# دوال قاعدة البيانات
# =========================

def get_setting(key, default=None):
    cursor.execute(
        "SELECT value FROM settings WHERE key = ?",
        (key,)
    )
    result = cursor.fetchone()

    if result:
        return result[0]

    return default


def set_setting(key, value):
    cursor.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, str(value))
    )
    db.commit()


def is_developer(user_id):
    return user_id in DEVELOPER_IDS


def activate_group(chat_id):
    cursor.execute(
        "INSERT OR REPLACE INTO groups (chat_id, active) VALUES (?, 1)",
        (chat_id,)
    )
    db.commit()


def deactivate_group(chat_id):
    cursor.execute(
        "UPDATE groups SET active = 0 WHERE chat_id = ?",
        (chat_id,)
    )
    db.commit()


def is_group_active(chat_id):
    cursor.execute(
        "SELECT active FROM groups WHERE chat_id = ?",
        (chat_id,)
    )
    result = cursor.fetchone()

    return bool(result and result[0] == 1)


# =========================
# لوحة المطور
# =========================

def developer_panel(chat_id):
    markup = types.InlineKeyboardMarkup(row_width=2)

    markup.add(
        types.InlineKeyboardButton(
            "📢 الاشتراك الإجباري",
            callback_data="force_sub"
        ),
        types.InlineKeyboardButton(
            "📊 الإحصائيات",
            callback_data="stats"
        )
    )

    markup.add(
        types.InlineKeyboardButton(
            "❌ تعطيل الاشتراك",
            callback_data="disable_force"
        )
    )

    bot.send_message(
        chat_id,
        "🛠 <b>لوحة تحكم المطور</b>\n\n"
        "اختر الأمر المطلوب:",
        reply_markup=markup
    )


# =========================
# /start
# =========================

@bot.message_handler(commands=["start"])
def start(message):

    user_id = message.from_user.id

    if is_developer(user_id):
        markup = types.InlineKeyboardMarkup()

        markup.add(
            types.InlineKeyboardButton(
                "🛠 لوحة التحكم",
                callback_data="developer_panel"
            )
        )

        bot.send_message(
            message.chat.id,
            f"👋 أهلاً بك مطور البوت.\n\n"
            f"👤 المطور: @{DEVELOPER_USERNAME}\n"
            f"🆔 ID: <code>{user_id}</code>",
            reply_markup=markup
        )
        return

    bot.send_message(
        message.chat.id,
        "👋 أهلاً بك في بوت حماية المجموعات.\n\n"
        "➕ أضفني إلى مجموعتك ثم ارفعني مشرفاً حتى أستطيع الحماية."
    )


# =========================
# إضافة البوت للمجموعة
# =========================

@bot.message_handler(content_types=["new_chat_members"])
def new_member(message):

    for member in message.new_chat_members:

        if member.id == bot.get_me().id:

            activate_group(message.chat.id)

            bot.send_message(
                message.chat.id,
                "✅ تم تفعيل البوت في المجموعة.\n\n"
                "⚡ الآن ارفعني <b>مشرفاً</b> حتى أتمكن من حذف الرسائل "
                "وتطبيق الحماية."
            )


# =========================
# أوامر المجموعة
# =========================

@bot.message_handler(func=lambda message: True, content_types=["text"])
def group_commands(message):

    if message.chat.type not in ["group", "supergroup"]:
        return

    text = (message.text or "").strip()

    # تفعيل
    if text == "تفعيل":

        if not is_developer(message.from_user.id):
            # يسمح فقط للمطور أو مشرف المجموعة
            try:
                member = bot.get_chat_member(
                    message.chat.id,
                    message.from_user.id
                )

                if member.status not in ["administrator", "creator"]:
                    return

            except Exception:
                return

        activate_group(message.chat.id)

        bot.reply_to(
            message,
            "✅ تم تفعيل الحماية في المجموعة."
        )

    # تعطيل
    elif text == "تعطيل":

        if not is_developer(message.from_user.id):

            try:
                member = bot.get_chat_member(
                    message.chat.id,
                    message.from_user.id
                )

                if member.status not in ["administrator", "creator"]:
                    return

            except Exception:
                return

        deactivate_group(message.chat.id)

        bot.reply_to(
            message,
            "❌ تم تعطيل الحماية في المجموعة."
        )


# =========================
# الاشتراك الإجباري
# =========================

def get_force_channel():
    return get_setting("force_channel")


def force_subscription_enabled():
    return get_setting("force_subscription", "0") == "1"


def check_subscription(user_id):

    channel = get_force_channel()

    if not channel or not force_subscription_enabled():
        return True

    try:
        member = bot.get_chat_member(channel, user_id)

        return member.status in [
            "creator",
            "administrator",
            "member"
        ]

    except Exception:
        return False


# =========================
# حذف رسائل غير المشتركين
# =========================

@bot.message_handler(
    func=lambda message: (
        message.chat.type in ["group", "supergroup"]
        and is_group_active(message.chat.id)
    ),
    content_types=[
        "text",
        "photo",
        "video",
        "document",
        "audio",
        "voice",
        "sticker",
        "animation"
    ]
)
def protection(message):

    # لا تطبق الحماية على المطور
    if is_developer(message.from_user.id):
        return

    # الاشتراك الإجباري
    if force_subscription_enabled():

        if not check_subscription(message.from_user.id):

            try:
                bot.delete_message(
                    message.chat.id,
                    message.message_id
                )
            except Exception:
                pass

            channel = get_force_channel()

            markup = types.InlineKeyboardMarkup()

            if channel:
                channel_link = channel

                if not str(channel).startswith("@"):
                    channel_link = "@" + str(channel)

                markup.add(
                    types.InlineKeyboardButton(
                        "📢 اشترك بالقناة",
                        url=f"https://t.me/{channel_link.replace('@', '')}"
                    )
                )

            try:
                bot.send_message(
                    message.chat.id,
                    f"⚠️ <b>{message.from_user.first_name}</b>\n\n"
                    "يجب عليك الاشتراك بالقناة أولاً حتى تتمكن من الكتابة.",
                    reply_markup=markup
                )
            except Exception:
                pass


# =========================
# كول باك لوحة التحكم
# =========================

@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):

    if not is_developer(call.from_user.id):
        bot.answer_callback_query(
            call.id,
            "❌ هذا القسم للمطور فقط.",
            show_alert=True
        )
        return

    # لوحة المطور
    if call.data == "developer_panel":

        bot.answer_callback_query(call.id)

        try:
            bot.edit_message_text(
                "🛠 <b>لوحة تحكم المطور</b>\n\n"
                "اختر الأمر المطلوب:",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=developer_menu()
            )
        except Exception:
            pass

    # الاشتراك الإجباري
    elif call.data == "force_sub":

        bot.answer_callback_query(call.id)

        msg = bot.send_message(
            call.message.chat.id,
            "📢 أرسل الآن يوزر القناة التي تريد تفعيل الاشتراك الإجباري بها.\n\n"
            "مثال:\n"
            "<code>@YourChannel</code>"
        )

        bot.register_next_step_handler(
            msg,
            save_force_channel
        )

    # تعطيل الاشتراك
    elif call.data == "disable_force":

        set_setting("force_subscription", "0")

        bot.answer_callback_query(
            call.id,
            "✅ تم تعطيل الاشتراك الإجباري.",
            show_alert=True
        )

        try:
            bot.edit_message_text(
                "🛠 <b>لوحة تحكم المطور</b>\n\n"
                "اختر الأمر المطلوب:",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=developer_menu()
            )
        except Exception:
            pass

    # الإحصائيات
    elif call.data == "stats":

        cursor.execute(
            "SELECT COUNT(*) FROM groups WHERE active = 1"
        )

        active_groups = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM groups"
        )

        total_groups = cursor.fetchone()[0]

        force_status = (
            "🟢 مفعل"
            if force_subscription_enabled()
            else "🔴 معطل"
        )

        bot.answer_callback_query(call.id)

        bot.send_message(
            call.message.chat.id,
            "📊 <b>إحصائيات البوت</b>\n\n"
            f"👥 مجموع المجموعات: <b>{total_groups}</b>\n"
            f"🟢 المجموعات المفعلة: <b>{active_groups}</b>\n"
            f"📢 الاشتراك الإجباري: <b>{force_status}</b>"
        )


def developer_menu():

    markup = types.InlineKeyboardMarkup(row_width=2)

    markup.add(
        types.InlineKeyboardButton(
            "📢 الاشتراك الإجباري",
            callback_data="force_sub"
        ),
        types.InlineKeyboardButton(
            "📊 الإحصائيات",
            callback_data="stats"
        )
    )

    markup.add(
        types.InlineKeyboardButton(
            "❌ تعطيل الاشتراك",
            callback_data="disable_force"
        )
    )

    return markup


# =========================
# حفظ قناة الاشتراك
# =========================

def save_force_channel(message):

    if not is_developer(message.from_user.id):
        return

    channel = message.text.strip()

    if not channel.startswith("@"):
        channel = "@" + channel

    set_setting("force_channel", channel)
    set_setting("force_subscription", "1")

    bot.send_message(
        message.chat.id,
        "✅ تم تفعيل الاشتراك الإجباري.\n\n"
        f"📢 القناة: <b>{channel}</b>\n\n"
        "⚠️ تأكد أن البوت موجود في القناة ويمكنه التحقق من الأعضاء."
    )


# =========================
# أمر المطور
# =========================

@bot.message_handler(commands=["panel", "admin"])
def admin_panel(message):

    if not is_developer(message.from_user.id):
        bot.reply_to(
            message,
            "❌ هذا الأمر للمطور فقط."
        )
        return

    developer_panel(message.chat.id)


# =========================
# تشغيل البوت
# =========================

print("Bot is running on Railway...")

bot.infinity_polling(
    skip_pending=True,
    timeout=30,
    long_polling_timeout=30
)
