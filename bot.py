import os
import sqlite3
import datetime
import telebot

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


# =========================================================
# إعدادات Railway
# =========================================================

BOT_TOKEN = os.getenv("8582451165:AAGVytO4wBe5mRPfkOQaDXhq1WSWmrb7KQs")

if not BOT_TOKEN:
    raise ValueError(
        "❌ BOT_TOKEN غير موجود في Railway Variables"
    )


# =========================================================
# إعدادات المطور
# =========================================================

DEVELOPER_USERNAME = "u_8_y"
DEVELOPER_USERNAMES = ["u_8_y"]


# =========================================================
# قاعدة البيانات
# =========================================================

RAILWAY_VOLUME_PATH = os.getenv(
    "RAILWAY_VOLUME_MOUNT_PATH"
)

if RAILWAY_VOLUME_PATH:
    DB_PATH = os.path.join(
        RAILWAY_VOLUME_PATH,
        "bot_database.db"
    )
else:
    DB_PATH = "bot_database.db"


# =========================================================
# تشغيل البوت
# =========================================================

bot = telebot.TeleBot(
    BOT_TOKEN,
    parse_mode="HTML"
)

user_states = {}


# =========================================================
# رموز الأزرار الافتراضية
# =========================================================

DEFAULT_BUTTON_SYMBOLS = {
    "add": "+",
    "buy": "↗",
    "dev": "↗",
    "panel": "🛠",
    "subscribe": "➕",
    "disable": "🛑",
    "change": "🔄",
    "back": "🔙",
}


# =========================================================
# قاعدة البيانات
# =========================================================

def get_db():
    return sqlite3.connect(
        DB_PATH,
        check_same_thread=False
    )


def init_db():

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            chat_id INTEGER PRIMARY KEY,
            chat_title TEXT,
            owner_id INTEGER,
            is_active INTEGER DEFAULT 0,
            sub_channel TEXT DEFAULT '',
            add_date TEXT,
            added_by INTEGER DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bot_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    try:
        cursor.execute(
            "ALTER TABLE groups ADD COLUMN added_by INTEGER DEFAULT 0"
        )
    except Exception:
        pass

    conn.commit()
    conn.close()


init_db()


# =========================================================
# إعدادات البوت
# =========================================================

def get_setting(key, default=""):

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT value FROM bot_settings WHERE key = ?",
        (key,)
    )

    row = cursor.fetchone()

    conn.close()

    if row:
        return row[0]

    return default


def set_setting(key, value):

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT OR REPLACE INTO bot_settings
        (key, value)
        VALUES (?, ?)
        """,
        (key, str(value))
    )

    conn.commit()
    conn.close()


# =========================================================
# الاشتراك الإجباري العام
# =========================================================

def get_bot_sub_channel():

    return get_setting(
        "bot_sub_channel",
        ""
    )


def set_bot_sub_channel(channel):

    set_setting(
        "bot_sub_channel",
        channel
    )


# =========================================================
# تلوين الأزرار
# =========================================================

def get_button_colors_enabled():

    value = get_setting(
        "button_colors_enabled",
        "1"
    )

    return value == "1"


def set_button_colors_enabled(enabled):

    set_setting(
        "button_colors_enabled",
        "1" if enabled else "0"
    )


def button_style(style):

    if get_button_colors_enabled():
        return {
            "style": style
        }

    return {}


# =========================================================
# رموز الأزرار
# =========================================================

def get_button_symbol(name):

    return get_setting(
        f"symbol_{name}",
        DEFAULT_BUTTON_SYMBOLS.get(name, "")
    )


def set_button_symbol(name, symbol):

    set_setting(
        f"symbol_{name}",
        symbol
    )


# =========================================================
# المطور
# =========================================================

def is_developer(user):

    if not user:
        return False

    if user.username:

        username = user.username.lower()

        for developer in DEVELOPER_USERNAMES:

            if username == developer.lower():
                return True

    return False


# =========================================================
# إدارة المجموعات
# =========================================================

def add_group_to_db(
    chat_id,
    chat_title,
    owner_id
):

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT chat_id FROM groups WHERE chat_id = ?",
        (chat_id,)
    )

    row = cursor.fetchone()

    current_date = datetime.datetime.now().strftime(
        "%d-%m-%Y"
    )

    if not row:

        cursor.execute(
            """
            INSERT INTO groups
            (
                chat_id,
                chat_title,
                owner_id,
                is_active,
                sub_channel,
                add_date,
                added_by
            )
            VALUES (?, ?, ?, 0, '', ?, ?)
            """,
            (
                chat_id,
                chat_title,
                owner_id,
                current_date,
                owner_id
            )
        )

    else:

        cursor.execute(
            """
            UPDATE groups
            SET chat_title = ?
            WHERE chat_id = ?
            """,
            (
                chat_title,
                chat_id
            )
        )

    conn.commit()
    conn.close()


def get_group_info(chat_id):

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            chat_title,
            is_active,
            sub_channel,
            add_date
        FROM groups
        WHERE chat_id = ?
        """,
        (chat_id,)
    )

    row = cursor.fetchone()

    conn.close()

    return row


def update_group_channel(
    chat_id,
    channel,
    added_by=0
):

    conn = get_db()
    cursor = conn.cursor()

    current_date = datetime.datetime.now().strftime(
        "%d-%m-%Y"
    )

    cursor.execute(
        """
        UPDATE groups
        SET
            sub_channel = ?,
            is_active = 1,
            add_date = ?,
            added_by = ?
        WHERE chat_id = ?
        """,
        (
            channel,
            current_date,
            added_by,
            chat_id
        )
    )

    conn.commit()
    conn.close()


# =========================================================
# قراءة القناة
# =========================================================

def parse_channel_input(message):

    if message.forward_from_chat:

        chat = message.forward_from_chat

        if chat.username:
            return f"@{chat.username}"

        return str(chat.id)

    if message.text:

        text = message.text.strip()

        if "t.me/" in text:

            parts = (
                text
                .split("t.me/")[-1]
                .split("?")[0]
                .strip("/")
            )

            if parts:
                return f"@{parts}"

        return text

    return None


# =========================================================
# القائمة الرئيسية
# =========================================================

def main_menu(user=None):

    markup = InlineKeyboardMarkup()

    markup.add(
        InlineKeyboardButton(
            f"اضفني الى مجموعتك {get_button_symbol('add')}",
            url=(
                f"https://t.me/"
                f"{bot.get_me().username}"
                f"?startgroup=true"
            ),
            **button_style("primary")
        )
    )

    markup.row(

        InlineKeyboardButton(
            f"شراء بوت {get_button_symbol('buy')}",
            url="https://t.me/u_8_y",
            **button_style("success")
        ),

        InlineKeyboardButton(
            f"المطور {get_button_symbol('dev')}",
            url="https://t.me/u_8_y",
            **button_style("primary")
        )
    )

    if user and is_developer(user):

        markup.add(
            InlineKeyboardButton(
                f"لوحة تحكم المطور "
                f"{get_button_symbol('panel')}",
                callback_data="dev_panel",
                **button_style("danger")
            )
        )

    return markup


# =========================================================
# الاشتراك الإجباري العام
# =========================================================

def send_bot_subscription(message):

    bot_sub_ch = get_bot_sub_channel()

    if not bot_sub_ch:
        return False

    if is_developer(message.from_user):
        return False

    try:

        member_status = bot.get_chat_member(
            bot_sub_ch,
            message.from_user.id
        )

        if member_status.status not in [
            "left",
            "kicked"
        ]:
            return False

        channel_title = bot_sub_ch

        try:

            ch_info = bot.get_chat(
                bot_sub_ch
            )

            if ch_info.title:
                channel_title = ch_info.title

        except Exception:
            pass

        if "t.me/" in bot_sub_ch:

            ch_link = bot_sub_ch

        else:

            ch_link = (
                "https://t.me/"
                + bot_sub_ch.replace("@", "")
            )

        warning_text = (
            "• يجب عليك الاشتراك بالقناة التالية "
            "لاستخدام البوت :"
        )

        markup = InlineKeyboardMarkup(
            row_width=1
        )

        markup.add(
            InlineKeyboardButton(
                channel_title,
                url=ch_link,
                **button_style("primary")
            )
        )

        markup.add(
            InlineKeyboardButton(
                f"اشتريت "
                f"{get_button_symbol('subscribe')}",
                callback_data="check_bot_sub",
                **button_style("success")
            )
        )

        bot.send_message(
            message.chat.id,
            warning_text,
            reply_markup=markup,
            parse_mode="HTML",
            disable_web_page_preview=True
        )

        return True

    except Exception as e:

        print(
            f"Error checking bot subscription: {e}"
        )

        return False


# =========================================================
# /start
# =========================================================

@bot.message_handler(
    commands=["start"]
)
def send_welcome(message):

    if message.chat.type != "private":
        return

    if send_bot_subscription(message):
        return

    user_id = message.from_user.id

    user_name = (
        message.from_user.first_name
        if message.from_user.first_name
        else "مستخدم"
    )

    user_states.pop(
        user_id,
        None
    )

    text = (
        f"أهلاً {user_name}\n"
        f"• لاستخدام البوت يجب عليك التالي :-\n\n"
        f"- أضف البوت للمجموعة ورفعه مشرفاً "
        f"ثم أرسل ( تفعيل ) ثم تابع التعليمات "
        f"التي يرسلها البوت.\n\n"
        f"- لإيقاف البوت ارسل : ( تعطيل ) "
        f"في المجموعة."
    )

    bot.send_message(
        message.chat.id,
        text,
        reply_markup=main_menu(
            message.from_user
        ),
        parse_mode="HTML"
    )


# =========================================================
# رسائل المجموعات
# =========================================================

@bot.message_handler(
    func=lambda message:
        message.chat.type in [
            "group",
            "supergroup"
        ],
    content_types=[
        "text",
        "audio",
        "document",
        "photo",
        "sticker",
        "video",
        "video_note",
        "voice",
        "forward"
    ]
)
def check_group_messages(message):

    text_content = (
        message.text.strip()
        if message.text
        else ""
    )

    try:

        add_group_to_db(
            message.chat.id,
            message.chat.title,
            message.from_user.id
        )

    except Exception as e:

        print(
            f"Database group error: {e}"
        )

    # -----------------------------------------------------
    # معرفة هل المرسل أدمن
    # -----------------------------------------------------

    try:

        chat_member = bot.get_chat_member(
            message.chat.id,
            message.from_user.id
        )

        is_admin_or_creator = (
            chat_member.status
            in [
                "creator",
                "administrator"
            ]
        )

    except Exception:

        is_admin_or_creator = False

    # -----------------------------------------------------
    # أوامر الأدمن
    # -----------------------------------------------------

    if is_admin_or_creator:

        if message.from_user.id in user_states:

            state_data = user_states[
                message.from_user.id
            ]

            # ---------------------------------------------
            # انتظار قناة المجموعة
            # ---------------------------------------------

            if isinstance(state_data, int):

                chat_id = state_data

                channel_target = parse_channel_input(
                    message
                )

                if channel_target:

                    bot_info = bot.get_me()

                    try:

                        member = bot.get_chat_member(
                            channel_target,
                            bot_info.id
                        )

                        if member.status in [
                            "left",
                            "kicked"
                        ]:
                            raise Exception(
                                "BOT_NOT_ADMIN"
                            )

                        update_group_channel(
                            chat_id,
                            str(channel_target),
                            message.from_user.id
                        )

                        user_states.pop(
                            message.from_user.id,
                            None
                        )

                        bot.reply_to(
                            message,
                            "<b>~ تم حفظ القناة "
                            "وتفعيل الاشتراك الإجباري "
                            "بنجاح ✅</b>",
                            parse_mode="HTML"
                        )

                        return

                    except Exception as e:

                        print(
                            f"Channel error: {e}"
                        )

                        bot.reply_to(
                            message,
                            "❌ فشل ربط القناة.\n"
                            "تأكد أن البوت مشرف في القناة "
                            "أو المجموعة العامة.",
                            parse_mode="HTML"
                        )

                        return

        # ---------------------------------------------
        # تفعيل
        # ---------------------------------------------

        if text_content == "تفعيل":

            user_states[
                message.from_user.id
            ] = message.chat.id

            user_name = (
                message.from_user.first_name
                if message.from_user.first_name
                else "مستخدم"
            )

            user_id = message.from_user.id

            user_mention = (
                f'<a href="tg://user?id={user_id}">'
                f'{user_name}</a>'
            )

            success_msg = (
                f"• حسناً ~ {user_mention}.\n"
                f"~ قم برفع البوت مشرف في قناتك "
                f"او مجموعتك العامة، ثم قم بتوجيه "
                f"منشور من القناة أو أرسل معرف القناة."
            )

            bot.reply_to(
                message,
                success_msg,
                parse_mode="HTML"
            )

            return

        # ---------------------------------------------
        # تعطيل
        # ---------------------------------------------

        if text_content == "تعطيل":

            user_states.pop(
                message.from_user.id,
                None
            )

            conn = get_db()
            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE groups
                SET
                    is_active = 0,
                    sub_channel = ''
                WHERE chat_id = ?
                """,
                (message.chat.id,)
            )

            conn.commit()
            conn.close()

            bot.reply_to(
                message,
                "<b>تم تعطيل البوت وإيقاف "
                "الاشتراك الإجباري لهذه المجموعة "
                "بنجاح ✅</b>",
                parse_mode="HTML"
            )

            return

    # -----------------------------------------------------
    # تجاهل البوتات
    # -----------------------------------------------------

    if message.from_user.is_bot:
        return

    # -----------------------------------------------------
    # معلومات المجموعة
    # -----------------------------------------------------

    g_info = get_group_info(
        message.chat.id
    )

    if not g_info:
        return

    g_title, is_active, sub_ch, add_date = g_info

    # -----------------------------------------------------
    # فحص الاشتراك
    # -----------------------------------------------------

    if is_active == 1 and sub_ch:

        try:

            member_status = bot.get_chat_member(
                sub_ch,
                message.from_user.id
            )

            if member_status.status in [
                "left",
                "kicked"
            ]:

                try:
                    bot.delete_message(
                        message.chat.id,
                        message.message_id
                    )
                except Exception:
                    pass

                channel_title = sub_ch
                channel_username = sub_ch

                try:

                    ch_info = bot.get_chat(
                        sub_ch
                    )

                    if ch_info.title:
                        channel_title = ch_info.title

                    if ch_info.username:
                        channel_username = (
                            f"@{ch_info.username}"
                        )

                    elif str(sub_ch).startswith("@"):
                        channel_username = sub_ch

                except Exception:
                    pass

                user_id = message.from_user.id

                user_name = (
                    message.from_user.first_name
                    if message.from_user.first_name
                    else "مستخدم"
                )

                user_mention_link = (
                    f'<a href="tg://user?id={user_id}">'
                    f'{user_name}</a>'
                )

                if "t.me/" in sub_ch:

                    ch_link = sub_ch

                else:

                    ch_link = (
                        "https://t.me/"
                        + sub_ch.replace("@", "")
                    )

                warning_text = (
                    f"عذراً عزيزي "
                    f"( {user_mention_link} )\n"
                    f"يجب عليك الاشتراك لإرسال "
                    f"الرسائل في القناة التالية:\n"
                    f"👇 <b>{channel_title}</b>\n"
                    f"🔗 المعرف: {channel_username}"
                )

                markup = InlineKeyboardMarkup()

                markup.add(
                    InlineKeyboardButton(
                        channel_title,
                        url=ch_link,
                        **button_style("primary")
                    )
                )

                bot.send_message(
                    message.chat.id,
                    warning_text,
                    reply_markup=markup,
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )

                return

        except Exception as e:

            print(
                f"Error checking group sub: {e}"
            )


# =========================================================
# رسائل الخاص
# =========================================================

@bot.message_handler(
    func=lambda message:
        message.chat.type == "private"
)
def handle_private_messages(message):

    user_id = message.from_user.id

    if user_id not in user_states:
        return

    state_data = user_states[user_id]

    # -----------------------------------------------------
    # تعيين قناة الاشتراك الإجباري للبوت
    # -----------------------------------------------------

    if state_data == "waiting_bot_sub_channel":

        if not is_developer(
            message.from_user
        ):
            user_states.pop(
                user_id,
                None
            )
            return

        channel = parse_channel_input(
            message
        )

        if not channel:

            bot.reply_to(
                message,
                "❌ أرسل معرف القناة مثل:\n"
                "@ChannelName"
            )

            return

        bot_info = bot.get_me()

        try:

            member = bot.get_chat_member(
                channel,
                bot_info.id
            )

            if member.status in [
                "left",
                "kicked"
            ]:
                raise Exception(
                    "BOT_NOT_ADMIN"
                )

            set_bot_sub_channel(
                str(channel)
            )

            user_states.pop(
                user_id,
                None
            )

            bot.reply_to(
                message,
                f"<b>✅ تم ضبط قناة الاشتراك "
                f"الإجباري بنجاح:</b>\n"
                f"{channel}",
                reply_markup=dev_panel_keyboard(),
                parse_mode="HTML"
            )

        except Exception as e:

            print(
                f"Bot subscription channel error: {e}"
            )

            bot.reply_to(
                message,
                "❌ فشل تعيين القناة.\n"
                "تأكد أن البوت مشرف فيها.",
                reply_markup=dev_panel_keyboard(),
                parse_mode="HTML"
            )

        return

    # -----------------------------------------------------
    # تغيير رمز زر
    # -----------------------------------------------------

    if isinstance(state_data, str) and state_data.startswith(
        "waiting_symbol:"
    ):

        symbol_name = state_data.split(
            ":",
            1
        )[1]

        if not is_developer(
            message.from_user
        ):
            user_states.pop(
                user_id,
                None
            )
            return

        symbol = (
            message.text.strip()
            if message.text
            else ""
        )

        if not symbol:

            bot.reply_to(
                message,
                "❌ أرسل رمزاً أو إيموجي."
            )

            return

        set_button_symbol(
            symbol_name,
            symbol
        )

        user_states.pop(
            user_id,
            None
        )

        bot.reply_to(
            message,
            "✅ تم تغيير رمز الزر بنجاح.",
            reply_markup=dev_panel_keyboard(),
            parse_mode="HTML"
        )

        return


# =========================================================
# لوحة رموز الأزرار
# =========================================================

def symbols_keyboard():

    markup = InlineKeyboardMarkup(
        row_width=1
    )

    symbols = [
        ("add", "زر إضافة البوت"),
        ("buy", "زر شراء بوت"),
        ("dev", "زر المطور"),
        ("panel", "زر لوحة المطور"),
        ("subscribe", "زر اشتريت"),
        ("disable", "زر التعطيل"),
        ("change", "زر تغيير القناة"),
        ("back", "زر الرجوع"),
    ]

    for key, title in symbols:

        markup.add(
            InlineKeyboardButton(
                f"{title}: {get_button_symbol(key)}",
                callback_data=f"symbol:{key}",
                **button_style("primary")
            )
        )

    markup.add(
        InlineKeyboardButton(
            "إعادة الرموز الافتراضية 🔄",
            callback_data="reset_symbols",
            **button_style("danger")
        )
    )

    markup.add(
        InlineKeyboardButton(
            f"القائمة الرئيسية "
            f"{get_button_symbol('back')}",
            callback_data="dev_panel",
            **button_style("primary")
        )
    )

    return markup


# =========================================================
# لوحة المطور
# =========================================================

def dev_panel_keyboard():

    markup = InlineKeyboardMarkup(
        row_width=1
    )

    bot_sub_ch = get_bot_sub_channel()

    if bot_sub_ch:

        markup.add(
            InlineKeyboardButton(
                f"إيقاف اشتراك البوت الإجباري "
                f"{get_button_symbol('disable')}",
                callback_data="disable_bot_sub",
                **button_style("danger")
            )
        )

        markup.add(
            InlineKeyboardButton(
                f"تغيير قناة الاشتراك "
                f"{get_button_symbol('change')}",
                callback_data="set_bot_sub",
                **button_style("primary")
            )
        )

    else:

        markup.add(
            InlineKeyboardButton(
                f"تعيين قناة اشتراك إجباري للبوت "
                f"{get_button_symbol('subscribe')}",
                callback_data="set_bot_sub",
                **button_style("success")
            )
        )

    # ألوان الأزرار

    if get_button_colors_enabled():

        markup.add(
            InlineKeyboardButton(
                "🎨 إيقاف تلوين الأزرار",
                callback_data="disable_button_colors",
                **button_style("danger")
            )
        )

    else:

        markup.add(
            InlineKeyboardButton(
                "🎨 تشغيل تلوين الأزرار",
                callback_data="enable_button_colors",
                **button_style("success")
            )
        )

    markup.add(
        InlineKeyboardButton(
            "🔤 تخصيص رموز الأزرار",
            callback_data="button_symbols",
            **button_style("primary")
        )
    )

    markup.add(
        InlineKeyboardButton(
            f"القائمة الرئيسية "
            f"{get_button_symbol('back')}",
            callback_data="main_menu",
            **button_style("primary")
        )
    )

    return markup


def build_dev_panel():

    bot_sub_ch = get_bot_sub_channel()

    if bot_sub_ch:

        sub_status = (
            f"مفعلة ({bot_sub_ch})"
        )

    else:

        sub_status = "معطلة"

    color_status = (
        "مفعلة 🎨"
        if get_button_colors_enabled()
        else "معطلة"
    )

    text = (
        "🛠 <b>لوحة تحكم المطور العامة</b>\n\n"
        f"• حالة الاشتراك الإجباري للبوت: "
        f"<b>{sub_status}</b>\n\n"
        f"• ألوان الأزرار: "
        f"<b>{color_status}</b>"
    )

    return text, dev_panel_keyboard()


# =========================================================
# Callbacks
# =========================================================

@bot.callback_query_handler(
    func=lambda call: True
)
def handle_callbacks(call):

    # -----------------------------------------------------
    # فحص الاشتراك
    # -----------------------------------------------------

    if call.data == "check_bot_sub":

        bot_sub_ch = get_bot_sub_channel()

        if bot_sub_ch:

            try:

                member_status = bot.get_chat_member(
                    bot_sub_ch,
                    call.from_user.id
                )

                if member_status.status in [
                    "left",
                    "kicked"
                ]:

                    bot.answer_callback_query(
                        call.id,
                        "❌ لم تقم بالاشتراك في القناة بعد!",
                        show_alert=True
                    )

                    return

            except Exception:
                pass

        bot.answer_callback_query(
            call.id,
            "✅ شكراً لاشتراكك!"
        )

        try:

            bot.delete_message(
                call.message.chat.id,
                call.message.message_id
            )

        except Exception:
            pass

        call.message.from_user = (
            call.from_user
        )

        send_welcome(
            call.message
        )

        return

    # -----------------------------------------------------
    # القائمة الرئيسية
    # -----------------------------------------------------

    if call.data == "main_menu":

        user_name = (
            call.from_user.first_name
            if call.from_user.first_name
            else "مستخدم"
        )

        text = (
            f"أهلاً {user_name}\n"
            f"• لاستخدام البوت يجب عليك التالي :-\n\n"
            f"- أضف البوت للمجموعة ورفعه مشرفاً "
            f"ثم أرسل ( تفعيل ) ثم تابع التعليمات "
            f"التي يرسلها البوت.\n\n"
            f"- لإيقاف البوت ارسل : ( تعطيل ) "
            f"في المجموعة."
        )

        try:

            bot.edit_message_text(
                text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=main_menu(
                    call.from_user
                ),
                parse_mode="HTML"
            )

        except Exception:

            bot.send_message(
                call.message.chat.id,
                text,
                reply_markup=main_menu(
                    call.from_user
                ),
                parse_mode="HTML"
            )

        bot.answer_callback_query(
            call.id
        )

        return

    # -----------------------------------------------------
    # لوحة المطور
    # -----------------------------------------------------

    if call.data == "dev_panel":

        if not is_developer(
            call.from_user
        ):

            bot.answer_callback_query(
                call.id,
                "هذه القائمة خاصة بالمطور فقط!",
                show_alert=True
            )

            return

        user_states.pop(
            call.from_user.id,
            None
        )

        text, markup = build_dev_panel()

        try:

            bot.edit_message_text(
                text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup,
                parse_mode="HTML"
            )

        except Exception:

            bot.send_message(
                call.message.chat.id,
                text,
                reply_markup=markup,
                parse_mode="HTML"
            )

        bot.answer_callback_query(
            call.id
        )

        return

    # -----------------------------------------------------
    # تعيين قناة البوت
    # -----------------------------------------------------

    if call.data == "set_bot_sub":

        if not is_developer(
            call.from_user
        ):

            bot.answer_callback_query(
                call.id,
                "مرفوض!",
                show_alert=True
            )

            return

        user_states[
            call.from_user.id
        ] = "waiting_bot_sub_channel"

        text = (
            "📢 <b>أرسل الآن معرف القناة</b>\n\n"
            "مثال:\n"
            "<code>@ChannelName</code>\n\n"
            "أو قم بتوجيه منشور من القناة.\n\n"
            "⚠️ يجب أن يكون البوت مشرفاً في القناة."
        )

        markup = InlineKeyboardMarkup()

        markup.add(
            InlineKeyboardButton(
                "إلغاء ❌",
                callback_data="dev_panel",
                **button_style("danger")
            )
        )

        try:

            bot.edit_message_text(
                text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup,
                parse_mode="HTML"
            )

        except Exception:

            bot.send_message(
                call.message.chat.id,
                text,
                reply_markup=markup,
                parse_mode="HTML"
            )

        bot.answer_callback_query(
            call.id
        )

        return

    # -----------------------------------------------------
    # إيقاف اشتراك البوت
    # -----------------------------------------------------

    if call.data == "disable_bot_sub":

        if not is_developer(
            call.from_user
        ):

            bot.answer_callback_query(
                call.id,
                "مرفوض!",
                show_alert=True
            )

            return

        set_bot_sub_channel("")

        bot.answer_callback_query(
            call.id,
            "✅ تم إيقاف الاشتراك الإجباري",
            show_alert=True
        )

        text, markup = build_dev_panel()

        try:

            bot.edit_message_text(
                text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup,
                parse_mode="HTML"
            )

        except Exception:
            pass

        return

    # -----------------------------------------------------
    # تشغيل الألوان
    # -----------------------------------------------------

    if call.data == "enable_button_colors":

        if not is_developer(
            call.from_user
        ):
            return

        set_button_colors_enabled(
            True
        )

        bot.answer_callback_query(
            call.id,
            "🎨 تم تشغيل ألوان الأزرار"
        )

        text, markup = build_dev_panel()

        try:

            bot.edit_message_text(
                text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup,
                parse_mode="HTML"
            )

        except Exception:
            pass

        return

    # -----------------------------------------------------
    # إيقاف الألوان
    # -----------------------------------------------------

    if call.data == "disable_button_colors":

        if not is_developer(
            call.from_user
        ):
            return

        set_button_colors_enabled(
            False
        )

        bot.answer_callback_query(
            call.id,
            "🎨 تم إيقاف ألوان الأزرار"
        )

        text, markup = build_dev_panel()

        try:

            bot.edit_message_text(
                text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup,
                parse_mode="HTML"
            )

        except Exception:
            pass

        return

    # -----------------------------------------------------
    # قائمة الرموز
    # -----------------------------------------------------

    if call.data == "button_symbols":

        if not is_developer(
            call.from_user
        ):
            return

        user_states.pop(
            call.from_user.id,
            None
        )

        text = (
            "🔤 <b>تخصيص رموز الأزرار</b>\n\n"
            "اختر الزر الذي تريد تغيير رمزه:"
        )

        try:

            bot.edit_message_text(
                text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=symbols_keyboard(),
                parse_mode="HTML"
            )

        except Exception:
            pass

        bot.answer_callback_query(
            call.id
        )

        return

    # -----------------------------------------------------
    # اختيار رمز
    # -----------------------------------------------------

    if call.data.startswith("symbol:"):

        if not is_developer(
            call.from_user
        ):
            return

        symbol_name = call.data.split(
            ":",
            1
        )[1]

        user_states[
            call.from_user.id
        ] = f"waiting_symbol:{symbol_name}"

        text = (
            "🔤 <b>تغيير رمز الزر</b>\n\n"
            f"الرمز الحالي: "
            f"<code>{get_button_symbol(symbol_name)}</code>\n\n"
            "أرسل الآن الرمز الجديد."
        )

        markup = InlineKeyboardMarkup()

        markup.add(
            InlineKeyboardButton(
                "إلغاء 🔙",
                callback_data="button_symbols",
                **button_style("danger")
            )
        )

        try:

            bot.edit_message_text(
                text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup,
                parse_mode="HTML"
            )

        except Exception:
            pass

        bot.answer_callback_query(
            call.id
        )

        return

    # -----------------------------------------------------
    # إعادة الرموز الافتراضية
    # -----------------------------------------------------

    if call.data == "reset_symbols":

        if not is_developer(
            call.from_user
        ):
            return

        for key, value in DEFAULT_BUTTON_SYMBOLS.items():

            set_button_symbol(
                key,
                value
            )

        bot.answer_callback_query(
            call.id,
            "✅ تم إعادة الرموز الافتراضية"
        )

        try:

            bot.edit_message_reply_markup(
                call.message.chat.id,
                call.message.message_id,
                reply_markup=symbols_keyboard()
            )

        except Exception:
            pass

        return


# =========================================================
# تشغيل البوت
# =========================================================

print(
    "🤖 البوت يعمل الآن على Railway..."
)

bot.infinity_polling(
    skip_pending=True,
    timeout=10,
    long_polling_timeout=5
        )
