
import sqlite3
import datetime
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


# ==============================
# إعدادات البوت
# ==============================

BOT_TOKEN = "8582451165:AAGVytO4wBe5mRPfkOQaDXhq1WSWmrb7KQs"

DEVELOPER_USERNAME = "u_8_y"

DEVELOPER_USERNAMES = [
    "u_8_y"
]

DEVELOPER_IDS = [
    750000000
]


bot = telebot.TeleBot(
    BOT_TOKEN,
    parse_mode="HTML"
)

user_states = {}


# ==============================
# قاعدة البيانات
# ==============================

def init_db():

    conn = sqlite3.connect(
        "bot_database.db",
        check_same_thread=False
    )

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

    except:

        pass

    conn.commit()
    conn.close()


init_db()


# ==============================
# إعدادات الاشتراك
# ==============================

def get_bot_sub_channel():

    conn = sqlite3.connect(
        "bot_database.db",
        check_same_thread=False
    )

    cursor = conn.cursor()

    cursor.execute(
        "SELECT value FROM bot_settings "
        "WHERE key = 'bot_sub_channel'"
    )

    row = cursor.fetchone()

    conn.close()

    return row[0] if row else ""


def set_bot_sub_channel(channel):

    conn = sqlite3.connect(
        "bot_database.db",
        check_same_thread=False
    )

    cursor = conn.cursor()

    cursor.execute(
        "INSERT OR REPLACE INTO bot_settings "
        "(key, value) VALUES (?, ?)",
        (
            "bot_sub_channel",
            channel
        )
    )

    conn.commit()
    conn.close()


# ==============================
# التحقق من المطور
# ==============================

def is_developer(user):

    if user.id in DEVELOPER_IDS:
        return True

    if user.username:

        if user.username.lower() in [
            d.lower()
            for d in DEVELOPER_USERNAMES
        ]:

            return True

    return False


# ==============================
# إعدادات رموز الأزرار
# ==============================

DEFAULT_BUTTON_SYMBOLS = {

    "add": "➕",

    "buy": "↗",

    "dev": "↗",

    "panel": "🛠"

}


def get_button_symbol(button_name):

    conn = sqlite3.connect(
        "bot_database.db",
        check_same_thread=False
    )

    cursor = conn.cursor()

    key = f"button_symbol_{button_name}"

    cursor.execute(
        "SELECT value FROM bot_settings "
        "WHERE key = ?",
        (key,)
    )

    row = cursor.fetchone()

    conn.close()

    if row and row[0]:

        return row[0]

    return DEFAULT_BUTTON_SYMBOLS.get(
        button_name,
        ""
    )


def set_button_symbol(
    button_name,
    symbol
):

    conn = sqlite3.connect(
        "bot_database.db",
        check_same_thread=False
    )

    cursor = conn.cursor()

    key = f"button_symbol_{button_name}"

    cursor.execute(
        "INSERT OR REPLACE INTO bot_settings "
        "(key, value) VALUES (?, ?)",
        (
            key,
            symbol
        )
    )

    conn.commit()
    conn.close()


def reset_button_symbols():

    conn = sqlite3.connect(
        "bot_database.db",
        check_same_thread=False
    )

    cursor = conn.cursor()

    for button_name in DEFAULT_BUTTON_SYMBOLS:

        key = f"button_symbol_{button_name}"

        cursor.execute(
            "DELETE FROM bot_settings "
            "WHERE key = ?",
            (key,)
        )

    conn.commit()
    conn.close()


# ==============================
# المجموعات
# ==============================

def add_group_to_db(
    chat_id,
    chat_title,
    owner_id
):

    conn = sqlite3.connect(
        "bot_database.db",
        check_same_thread=False
    )

    cursor = conn.cursor()

    cursor.execute(
        "SELECT chat_id FROM groups "
        "WHERE chat_id = ?",
        (chat_id,)
    )

    row = cursor.fetchone()

    current_date = datetime.datetime.now().strftime(
        "%d-%m-%Y"
    )

    if not row:

        cursor.execute("""
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
        """, (
            chat_id,
            chat_title,
            owner_id,
            current_date,
            owner_id
        ))

    else:

        cursor.execute(
            "UPDATE groups "
            "SET chat_title = ? "
            "WHERE chat_id = ?",
            (
                chat_title,
                chat_id
            )
        )

    conn.commit()
    conn.close()


def get_group_info(chat_id):

    conn = sqlite3.connect(
        "bot_database.db",
        check_same_thread=False
    )

    cursor = conn.cursor()

    cursor.execute(
        "SELECT chat_title, is_active, "
        "sub_channel, add_date "
        "FROM groups "
        "WHERE chat_id = ?",
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

    conn = sqlite3.connect(
        "bot_database.db",
        check_same_thread=False
    )

    cursor = conn.cursor()

    current_date = datetime.datetime.now().strftime(
        "%d-%m-%Y"
    )

    cursor.execute("""
        UPDATE groups
        SET
            sub_channel = ?,
            is_active = 1,
            add_date = ?,
            added_by = ?
        WHERE chat_id = ?
    """, (
        channel,
        current_date,
        added_by,
        chat_id
    ))

    conn.commit()
    conn.close()


# ==============================
# قراءة القناة
# ==============================

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


# ==============================
# القائمة الرئيسية
# ==============================

def main_menu(user=None):

    markup = InlineKeyboardMarkup()

    add_symbol = get_button_symbol("add")
    buy_symbol = get_button_symbol("buy")
    dev_symbol = get_button_symbol("dev")
    panel_symbol = get_button_symbol("panel")


    # إضافة البوت للمجموعة

    markup.add(

        InlineKeyboardButton(

            f"اضفني الى مجموعتك {add_symbol}",

            url=(
                f"http://t.me/"
                f"{bot.get_me().username}"
                f"?startgroup=true"
            ),

            style="primary"
        )
    )


    # شراء + المطور

    markup.row(

        InlineKeyboardButton(

            f"شراء بوت {buy_symbol}",

            url="https://t.me/u_8_y",

            style="success"
        ),

        InlineKeyboardButton(

            f"المطور {dev_symbol}",

            url="https://t.me/u_8_y",

            style="primary"
        )
    )


    # لوحة المطور تظهر للمطور فقط

    if user and is_developer(user):

        markup.add(

            InlineKeyboardButton(

                f"لوحة تحكم المطور {panel_symbol}",

                callback_data="dev_panel",

                style="danger"
            )
        )


    return markup


# ==============================
# قائمة تخصيص الرموز
# ==============================

def symbols_menu():

markup = InlineKeyboardMarkup(
        row_width=1
    )

    markup.add(

        InlineKeyboardButton(
            "➕ تعديل رمز زر الإضافة",
            callback_data="symbol_add",
            style="primary"
        )
    )

    markup.add(

        InlineKeyboardButton(
            "🛒 تعديل رمز شراء البوت",
            callback_data="symbol_buy",
            style="success"
        )
    )

    markup.add(

        InlineKeyboardButton(
            "👤 تعديل رمز المطور",
            callback_data="symbol_dev",
            style="primary"
        )
    )

    markup.add(

        InlineKeyboardButton(
            "🛠 تعديل رمز لوحة المطور",
            callback_data="symbol_panel",
            style="danger"
        )
    )

    markup.add(

        InlineKeyboardButton(
            "♻️ إرجاع الرموز الافتراضية",
            callback_data="reset_symbols",
            style="danger"
        )
    )

    markup.add(

        InlineKeyboardButton(
            "🔙 رجوع",
            callback_data="dev_panel",
            style="primary"
        )
    )

    return markup


# ==============================
# بدء البوت
# ==============================

@bot.message_handler(
    commands=["start"]
)
def send_welcome(message):

    if message.chat.type != "private":
        return

    user_id = message.from_user.id

    user_name = (

        message.from_user.first_name

        if message.from_user.first_name

        else "مستخدم"
    )


    bot_sub_ch = get_bot_sub_channel()


    if (
        bot_sub_ch
        and not is_developer(
            message.from_user
        )
    ):

        try:

            member_status = bot.get_chat_member(
                bot_sub_ch,
                user_id
            )


            if member_status.status in [
                "left",
                "kicked"
            ]:

                channel_title = bot_sub_ch


                try:

                    ch_info = bot.get_chat(
                        bot_sub_ch
                    )

                    if ch_info.title:

                        channel_title = ch_info.title

                except:

                    pass


                ch_link = (

                    bot_sub_ch

                    if "t.me/" in bot_sub_ch

                    else (
                        f"https://t.me/"
                        f"{bot_sub_ch.replace('@', '')}"
                    )
                )


                warning_text = (
                    "• يجب عليك الاشتراك بالقنوات "
                    "التالية لاستخدام البوت :"
                )


                markup = InlineKeyboardMarkup(
                    row_width=1
                )


                markup.add(

                    InlineKeyboardButton(
                        channel_title,
                        url=ch_link,
                        style="primary"
                    )
                )


                markup.add(

                    InlineKeyboardButton(
                        "اشتريت",
                        callback_data="check_bot_sub",
                        style="success"
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
                f"Error checking bot sub: {e}"
            )


    user_states.pop(
        user_id,
        None
    )


    text = (

        f"أهلاً {user_name}\n"

        f"• لاستخدام البوت يجب عليك التالي :-\n\n"

        f"- أضف البوت للمجموعة ورفعه مشرفاً ثم أرسل "
        f"( تفعيل ) ثم تابع التعليمات التي يرسلها البوت.\n\n"

        f"- لإيقاف البوت ارسل : ( تعطيل ) في المجموعة."
    )


    bot.send_message(

        message.chat.id,

        text,

        reply_markup=main_menu(
            message.from_user
        ),

        parse_mode="HTML"
    )


# ==============================
# رسائل المجموعات
# ==============================

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

    except:

        pass


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


    except:

        is_admin_or_creator = False


    if is_admin_or_creator:


        if message.from_user.id in user_states:

            state_data = user_states[
                message.from_user.id
            ]


            if isinstance(
                state_data,
                int
            ):

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

                            "<b>~ تم حفظ الايدي بنجاح</b>",

                            parse_mode="HTML"
                        )

                        return


                    except:

                        bot.reply_to(

                            message,

                            "فشل ربط وتعيين القناة تأكد من وجود "
                            "البوت مشرفاً فيها بالصلاحيات الكاملة",

                            parse_mode="HTML"
                        )

                        return


        # تفعيل

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

                f"~ قم برفع البوت مشرف في قناتك او مجموعتك "
                f"العامة وققم بتوجية منشور من القناة او معرف "
                f"القناة او المجموعة العامة"
            )


            bot.reply_to(

                message,

                success_msg,

                parse_mode="HTML"
            )

            return


        # تعطيل

        if text_content == "تعطيل":

            user_states.pop(

                message.from_user.id,

                None
            )


            conn = sqlite3.connect(

                "bot_database.db",

check_same_thread=False
            )


            cursor = conn.cursor()


            cursor.execute(

                "UPDATE groups SET "
                "is_active = 0, "
                "sub_channel = '' "
                "WHERE chat_id = ?",

                (message.chat.id,)
            )


            conn.commit()

            conn.close()


            bot.reply_to(

                message,

                "<b>تم تعطيل البوت وإيقاف الاشتراك "
                "الإجباري لهذه المجموعة بنجاح</b>",

                parse_mode="HTML"
            )

            return


    if message.from_user.is_bot:
        return


    g_info = get_group_info(
        message.chat.id
    )


    if not g_info:
        return


    g_title, is_active, sub_ch, add_date = g_info


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

                except:

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


                except:

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


                ch_link = (

                    sub_ch

                    if "t.me/" in sub_ch

                    else (
                        f"https://t.me/"
                        f"{sub_ch.replace('@', '')}"
                    )
                )


                warning_text = (

                    f"عذراً عزيزي "
                    f"( {user_mention_link} )\n"

                    f"يجب عليك الاشتراك لارسال الرسائل "
                    f"في القناة التالية:\n"

                    f"👇 <b>{channel_title}</b>\n"

                    f"🔗 المعرف: {channel_username}"
                )


                markup = InlineKeyboardMarkup()


                markup.add(

                    InlineKeyboardButton(

                        channel_title,

                        url=ch_link,

                        style="primary"
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
                f"Error checking sub: {e}"
            )


# ==============================
# رسائل الخاص
# ==============================

@bot.message_handler(

    func=lambda message:
    message.chat.type == "private"
)
def handle_private_messages(message):

    user_id = message.from_user.id


    if user_id not in user_states:
        return


    state_data = user_states[user_id]


    # تعيين قناة البوت

    if state_data == "waiting_bot_sub_channel":

        channel = parse_channel_input(
            message
        )


        if not channel:
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


            markup = InlineKeyboardMarkup()


            markup.add(

                InlineKeyboardButton(

                    "لوحة التحكم 🔙",

                    callback_data="dev_panel",

                    style="primary"
                )
            )


            bot.reply_to(

                message,

                f"<b>✅ تم ضبط قناة الاشتراك الإجباري "
                f"للبوت بنجاح: {channel}</b>",

                reply_markup=markup,

                parse_mode="HTML"
            )

            return


        except:

            markup = InlineKeyboardMarkup()


            markup.add(

                InlineKeyboardButton(

                    "لوحة التحكم 🔙",

                    callback_data="dev_panel",

                    style="primary"
                )
            )


            bot.reply_to(

                message,

                "❌ فشل تعيين القناة. تأكد من أن "
                "البوت مشرف فيها!",

                reply_markup=markup
            )

            return


    # ==============================
    # تخصيص الرموز
    # ==============================

    if isinstance(
        state_data,
        str
    ) and state_data.startswith(
        "waiting_symbol_"
    ):

        if not is_developer(
            message.from_user
        ):

            user_states.pop(
                user_id,
                None
            )

            return


        button_name = state_data.replace(
            "waiting_symbol_",
            ""
        )


        symbol = (
            message.text.strip()
            if message.text
            else ""
        )


        if not symbol:

            bot.reply_to(

                message,

                "❌ أرسل الرمز أو الإيموجي فقط."
            )

            return


        # نأخذ أول رمز/إيموجي مناسب
        # لكن نترك النص كما أرسله المستخدم
        set_button_symbol(
            button_name,
            symbol
        )


        user_states.pop(
            user_id,
            None
        )


        markup = symbols_menu()


        bot.reply_to(

            message,

            f"✅ تم تغيير رمز الزر بنجاح إلى: "
            f"<b>{symbol}</b>\n\n"
            f"اختر زرًا آخر للتعديل:",

            reply_markup=markup,

            parse_mode="HTML"
        )

        return


# ==============================
# الكول باك
# ==============================

@bot.callback_query_handler(
    func=lambda call: True
)
def handle_callbacks(call):


    # ==============================
    # التحقق من الاشتراك
    # ==============================

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

                        "❌ عذراً، لم تقم بالاشتراك "
                        "في القناة بعد!",

                        show_alert=True
                    )

                    return


            except:

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

except:

            pass


        call.message.from_user = (
            call.from_user
        )


        send_welcome(
            call.message
        )


    # ==============================
    # شراء البوت
    # ==============================

    elif call.data == "buy_bot":

        bot.answer_callback_query(

            call.id,

            "لشراء بوت، تواصل مع المطور: @"
            + DEVELOPER_USERNAME,

            show_alert=True
        )


    # ==============================
    # المطور
    # ==============================

    elif call.data == "dev_info":

        bot.answer_callback_query(

            call.id,

            f"المطور: @{DEVELOPER_USERNAME}",

            show_alert=True
        )


    # ==============================
    # القائمة الرئيسية
    # ==============================

    elif call.data == "main_menu":

        user_name = (

            call.from_user.first_name

            if call.from_user.first_name

            else "مستخدم"
        )


        text = (

            f"أهلاً {user_name}\n"

            f"• لاستخدام البوت يجب عليك التالي :-\n\n"

            f"- أضف البوت للمجموعة ورفعه مشرفاً ثم أرسل "
            f"( تفعيل ) ثم تابع التعليمات التي يرسلها البوت.\n\n"

            f"- لإيقاف البوت ارسل : ( تعطيل ) في المجموعة."
        )


        bot.edit_message_text(

            text,

            call.message.chat.id,

            call.message.message_id,

            reply_markup=main_menu(
                call.from_user
            ),

            parse_mode="HTML"
        )


        bot.answer_callback_query(
            call.id
        )


    # ==============================
    # لوحة المطور
    # ==============================

    elif call.data == "dev_panel":

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


        bot_sub_ch = get_bot_sub_channel()


        sub_status = (

            f"مفعلة ({bot_sub_ch})"

            if bot_sub_ch

            else "معطلة"
        )


        text = (

            f"🛠 <b>لوحة تحكم المطور العامة</b>\n\n"

            f"• حالة الاشتراك الإجباري للبوت: "
            f"<b>{sub_status}</b>"
        )


        markup = InlineKeyboardMarkup(
            row_width=1
        )


        if bot_sub_ch:

            markup.add(

                InlineKeyboardButton(

                    "إيقاف اشتراك البوت الإجباري 🛑",

                    callback_data="disable_bot_sub",

                    style="danger"
                )
            )


            markup.add(

                InlineKeyboardButton(

                    "تغيير قناة اشتراك البوت 🔄",

                    callback_data="set_bot_sub",

                    style="primary"
                )
            )

        else:

            markup.add(

                InlineKeyboardButton(

                    "تعيين قناة اشتراك إجباري للبوت ➕",

                    callback_data="set_bot_sub",

                    style="success"
                )
            )


        # ==============================
        # زر تخصيص الرموز
        # ==============================

        markup.add(

            InlineKeyboardButton(

                "🎨 تخصيص رموز الأزرار",

                callback_data="custom_symbols",

                style="primary"
            )
        )


        markup.add(

            InlineKeyboardButton(

                "القائمة الرئيسية 🔙",

                callback_data="main_menu",

                style="primary"
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


        except:

            bot.send_message(

                call.message.chat.id,

                text,

                reply_markup=markup,

                parse_mode="HTML"
            )


        bot.answer_callback_query(
            call.id
        )


    # ==============================
    # قائمة تخصيص الرموز
    # ==============================

    elif call.data == "custom_symbols":

        if not is_developer(
            call.from_user
        ):

            bot.answer_callback_query(

                call.id,

                "هذه القائمة خاصة بمالك البوت فقط!",

                show_alert=True
            )

            return


        text = (

            "🎨 <b>تخصيص رموز الأزرار</b>\n\n"

            "اختر الزر الذي تريد تغيير رمزه:"
        )


        try:

            bot.edit_message_text(

                text,

                call.message.chat.id,

                call.message.message_id,

                reply_markup=symbols_menu(),

                parse_mode="HTML"
            )

        except:

            bot.send_message(

                call.message.chat.id,

                text,

                reply_markup=symbols_menu(),

                parse_mode="HTML"
            )


        bot.answer_callback_query(
            call.id
        )


    # ==============================
    # اختيار زر الإضافة
    # ==============================

    elif call.data == "symbol_add":

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
        ] = "waiting_symbol_add"


        bot.answer_callback_query(
            call.id
        )


        bot.send_message(

            call.message.chat.id,

            "➕ أرسل الآن الرمز الذي تريده لزر "
            "<b>اضفني الى مجموعتك</b>.\n\n"
            "مثال: ⭐ أو 🚀 أو 𓆩♡𓆪",

            parse_mode="HTML"
        )


    # ==============================
    # اختيار زر شراء البوت
    # ==============================

    elif call.data == "symbol_buy":

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
        ] = "waiting_symbol_buy"


        bot.answer_callback_query(
            call.id
        )


        bot.send_message(

            call.message.chat.id,

            "🛒 أرسل الآن الرمز الذي تريده لزر "
            "<b>شراء بوت</b>.\n\n"
            "مثال: 💎 أو 🛒 أو ⭐",

            parse_mode="HTML"
        )


    # ==============================
    # اختيار زر المطور
    # ==============================

    elif call.data == "symbol_dev":

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
        ] = "waiting_symbol_dev"


        bot.answer_callback_query(
            call.id
        )


        bot.send_message(

            call.message.chat.id,

            "👤 أرسل الآن الرمز الذي تريده لزر "
            "<b>المطور</b>.\n\n"
            "مثال: 👑 أو 💎 أو ⭐",

            parse_mode="HTML"
        )


    # ==============================
    # اختيار زر لوحة المطور
    # ==============================

    elif call.data == "symbol_panel":

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
        ] = "waiting_symbol_panel"


        bot.answer_callback_query(
            call.id
        )


        bot.send_message(

            call.message.chat.id,

"🛠 أرسل الآن الرمز الذي تريده لزر "
            "<b>لوحة تحكم المطور</b>.\n\n"
            "مثال: 👑 أو 🛠 أو ⚙️",

            parse_mode="HTML"
        )


    # ==============================
    # إعادة الرموز الافتراضية
    # ==============================

    elif call.data == "reset_symbols":

        if not is_developer(
            call.from_user
        ):

            bot.answer_callback_query(

                call.id,

                "هذه القائمة خاصة بمالك البوت فقط!",

                show_alert=True
            )

            return


        reset_button_symbols()


        bot.answer_callback_query(

            call.id,

            "✅ تم إرجاع جميع الرموز الافتراضية",

            show_alert=True
        )


        text = (

            "🎨 <b>تخصيص رموز الأزرار</b>\n\n"

            "✅ تم إرجاع جميع الرموز الافتراضية.\n\n"

            "اختر الزر الذي تريد تغيير رمزه:"
        )


        try:

            bot.edit_message_text(

                text,

                call.message.chat.id,

                call.message.message_id,

                reply_markup=symbols_menu(),

                parse_mode="HTML"
            )

        except:

            pass


    # ==============================
    # تعيين قناة الاشتراك
    # ==============================

    elif call.data == "set_bot_sub":

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

            "📢 أرسل الآن يوزر القناة "
            "(مثلاً @ChannelName) أو قم بتوجيه "
            "منشور منها، وتأكد من أن البوت مشرف فيها:"
        )


        markup = InlineKeyboardMarkup()


        markup.add(

            InlineKeyboardButton(

                "إلغاء ❌",

                callback_data="dev_panel",

                style="danger"
            )
        )


        try:

            bot.edit_message_text(

                text,

                call.message.chat.id,

                call.message.message_id,

                reply_markup=markup
            )

        except:

            bot.send_message(

                call.message.chat.id,

                text,

                reply_markup=markup
            )


        bot.answer_callback_query(
            call.id
        )


    # ==============================
    # تعطيل اشتراك البوت
    # ==============================

    elif call.data == "disable_bot_sub":

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

            "تم إيقاف اشتراك البوت الإجباري بنجاح",

            show_alert=True
        )


        call.data = "dev_panel"


        handle_callbacks(
            call
        )


# ==============================
# تشغيل البوت
# ==============================

print(
    "بوت الاشتراك الإجباري يعمل الآن..."
)


bot.infinity_polling(
    skip_pending=True
        )
