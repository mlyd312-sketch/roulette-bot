import sqlite3
import datetime
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = "8582451165:AAGVytO4wBe5mRPfkOQaDXhq1WSWmrb7KQs"
DEVELOPER_USERNAME = "u_8_y"
DEVELOPER_USERNAMES = ["u_8_y"]
DEVELOPER_IDS = [750000000]

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
user_states = {}


class StyledInlineKeyboardButton(InlineKeyboardButton):
    def __init__(self, text, url=None, callback_data=None, style=None, **kwargs):
        super().__init__(text, url=url, callback_data=callback_data, **kwargs)
        if style:
            self.style = style

    def to_dict(self):
        data = super().to_dict()
        if hasattr(self, 'style') and self.style:
            data['style'] = self.style
        return data


def init_db():
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS groups (
            chat_id INTEGER PRIMARY KEY,
            chat_title TEXT,
            owner_id INTEGER,
            is_active INTEGER DEFAULT 0,
            sub_channel TEXT DEFAULT '',
            add_date TEXT,
            added_by INTEGER DEFAULT 0
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    try:
        cursor.execute("ALTER TABLE groups ADD COLUMN added_by INTEGER DEFAULT 0")
    except:
        pass

    conn.commit()
    conn.close()


init_db()


def get_bot_sub_channel():
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM bot_settings WHERE key = 'bot_sub_channel'")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else ""


def set_bot_sub_channel(channel):
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)", ('bot_sub_channel', channel))
    conn.commit()
    conn.close()


def is_developer(user):
    if user.id in DEVELOPER_IDS:
        return True
    if user.username and user.username.lower() in [d.lower() for d in DEVELOPER_USERNAMES]:
        return True
    return False


def add_group_to_db(chat_id, chat_title, owner_id):
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id FROM groups WHERE chat_id = ?", (chat_id,))
    row = cursor.fetchone()
    current_date = datetime.datetime.now().strftime("%d-%m-%Y")

    if not row:
        cursor.execute('''
            INSERT INTO groups (chat_id, chat_title, owner_id, is_active, sub_channel, add_date, added_by)
            VALUES (?, ?, ?, 0, '', ?, ?)
        ''', (chat_id, chat_title, owner_id, current_date, owner_id))
    else:
        cursor.execute("UPDATE groups SET chat_title = ? WHERE chat_id = ?", (chat_title, chat_id))

    conn.commit()
    conn.close()


def get_group_info(chat_id):
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT chat_title, is_active, sub_channel, add_date FROM groups WHERE chat_id = ?", (chat_id,))
    row = cursor.fetchone()
    conn.close()
    return row


def update_group_channel(chat_id, channel, added_by=0):
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    current_date = datetime.datetime.now().strftime("%d-%m-%Y")
    cursor.execute('''
        UPDATE groups SET sub_channel = ?, is_active = 1, add_date = ?, added_by = ? WHERE chat_id = ?
    ''', (channel, current_date, added_by, chat_id))
    conn.commit()
    conn.close()


def parse_channel_input(message):
    if message.forward_from_chat:
        chat = message.forward_from_chat
        if chat.username:
            return f"@{chat.username}"
        return str(chat.id)

    if message.text:
        text = message.text.strip()
        if "t.me/" in text:
            parts = text.split("t.me/")[-1].split("?")[0].strip("/")
            if parts:
                return f"@{parts}"
        return text
    return None


def main_menu(user=None):
    markup = InlineKeyboardMarkup()

    # زر أزرق
    markup.add(
        StyledInlineKeyboardButton(
            "اضفني الى مجموعتك +",
            url=f"http://t.me/{bot.get_me().username}?startgroup=true",
            style="primary"
        )
    )

    # زر أخضر + زر أزرق
    markup.row(
        StyledInlineKeyboardButton(
            "شراء بوت ↗",
            url="https://t.me/u_8_y",
            style="success"
        ),
        StyledInlineKeyboardButton(
            "المطور ↗",
            url="https://t.me/u_8_y",
            style="primary"
        )
    )

    # زر أحمر للمطور
    if user and is_developer(user):
        markup.add(
            StyledInlineKeyboardButton(
                "لوحة تحكم المطور 🛠",
                callback_data="dev_panel",
                style="danger"
            )
        )

    return markup


@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.chat.type != 'private':
        return

    user_id = message.from_user.id
    user_name = message.from_user.first_name if message.from_user.first_name else "مستخدم"
    bot_sub_ch = get_bot_sub_channel()

    if bot_sub_ch and not is_developer(message.from_user):
        try:
            member_status = bot.get_chat_member(bot_sub_ch, user_id)
            if member_status.status in ['left', 'kicked']:
                channel_title = bot_sub_ch
                try:
                    ch_info = bot.get_chat(bot_sub_ch)
                    if ch_info.title:
                        channel_title = ch_info.title
                except:
                    pass

                ch_link = bot_sub_ch if "t.me/" in bot_sub_ch else f"https://t.me/{bot_sub_ch.replace('@', '')}"
                warning_text = "• يجب عليك الاشتراك بالقنوات التالية لاستخدام البوت :"
                
                markup = InlineKeyboardMarkup(row_width=1)
                markup.add(
                    StyledInlineKeyboardButton(channel_title, url=ch_link, style="primary")
                )
                markup.add(
                    StyledInlineKeyboardButton("اشتريت ✅", callback_data="check_bot_sub", style="success")
                )

                bot.send_message(message.chat.id, warning_text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)
                return
        except Exception as e:
            print(f"Error checking bot sub: {e}")

    user_states.pop(user_id, None)

    text = (
        f"أهلاً {user_name}\n"
        f"• لاستخدام البوت يجب عليك التالي :-\n\n"
        f"- أضف البوت للمجموعة ورفعه مشرفاً ثم أرسل ( تفعيل ) ثم تابع التعليمات التي يرسلها البوت.\n\n"
        f"- لإيقاف البوت ارسل : ( تعطيل ) في المجموعة."
    )

    bot.send_message(message.chat.id, text, reply_markup=main_menu(message.from_user), parse_mode="HTML")


@bot.message_handler(func=lambda message: message.chat.type in ['group', 'supergroup'], content_types=['text', 'audio', 'document', 'photo', 'sticker', 'video', 'video_note', 'voice', 'forward'])
def check_group_messages(message):
    text_content = message.text.strip() if message.text else ""

    try:
        add_group_to_db(message.chat.id, message.chat.title, message.from_user.id)
    except:
        pass

    try:
        chat_member = bot.get_chat_member(message.chat.id, message.from_user.id)
        is_admin_or_creator = chat_member.status in ['creator', 'administrator']
    except:
        is_admin_or_creator = False

    if is_admin_or_creator:
        if message.from_user.id in user_states:
            state_data = user_states[message.from_user.id]
            if isinstance(state_data, int):
                chat_id = state_data
                channel_target = parse_channel_input(message)
                if channel_target:
                    bot_info = bot.get_me()
                    try:
                        member = bot.get_chat_member(channel_target, bot_info.id)
                        if member.status in ['left', 'kicked']:
                            raise Exception("BOT_NOT_ADMIN")

                        update_group_channel(chat_id, str(channel_target), message.from_user.id)
                        user_states.pop(message.from_user.id, None)
                        bot.reply_to(message, "<b>~ تم حفظ الايدي بنجاح</b>", parse_mode="HTML")
                        return
                    except Exception:
                        bot.reply_to(message, "فشل ربط وتعيين القناة تأكد من وجود البوت مشرفاً فيها بالصلاحيات الكاملة", parse_mode="HTML")
                        return

        if text_content == "تفعيل":
            user_states[message.from_user.id] = message.chat.id
            user_name = message.from_user.first_name if message.from_user.first_name else "مستخدم"
            user_id = message.from_user.id
            user_mention = f'<a href="tg://user?id={user_id}">{user_name}</a>'

            success_msg = (
                f"• حسناً ~ {user_mention}.\n"
                f"~ قم برفع البوت مشرف في قناتك او مجموعتك العامة وققم بتوجية منشور من القناة او معرف القناة او المجموعة العامة"
            )
            bot.reply_to(message, success_msg, parse_mode="HTML")
            return

        if text_content == "تعطيل":
            user_states.pop(message.from_user.id, None)
            conn = sqlite3.connect('bot_database.db', check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("UPDATE groups SET is_active = 0, sub_channel = '' WHERE chat_id = ?", (message.chat.id,))
            conn.commit()
            conn.close()
            bot.reply_to(message, "<b>تم تعطيل البوت وإيقاف الاشتراك الإجباري لهذه المجموعة بنجاح</b>", parse_mode="HTML")
            return

    if message.from_user.is_bot:
        return

    g_info = get_group_info(message.chat.id)
    if not g_info:
        return

    g_title, is_active, sub_ch, add_date = g_info

    if is_active == 1 and sub_ch:
        try:
            member_status = bot.get_chat_member(sub_ch, message.from_user.id)
            if member_status.status in ['left', 'kicked']:
                try:
                    bot.delete_message(message.chat.id, message.message_id)
                except:
                    pass

                channel_title = sub_ch
                channel_username = sub_ch
                try:
                    ch_info = bot.get_chat(sub_ch)
                    if ch_info.title:
                        channel_title = ch_info.title
                    if ch_info.username:
                        channel_username = f"@{ch_info.username}"
                except:
                    pass

                user_id = message.from_user.id
                user_name = message.from_user.first_name if message.from_user.first_name else "مستخدم"
                user_mention_link = f'<a href="tg://user?id={user_id}">{user_name}</a>'
                ch_link = sub_ch if "t.me/" in sub_ch else f"https://t.me/{sub_ch.replace('@', '')}"

                warning_text = (
                    f"عذراً عزيزي ( {user_mention_link} )\n"
                    f"يجب عليك الاشتراك لارسال الرسائل في القناة التالية:\n"
                    f"👇 <b>{channel_title}</b>\n"
                    f"🔗 المعرف: {channel_username}"
                )

                markup = InlineKeyboardMarkup()
                markup.add(
                    StyledInlineKeyboardButton(channel_title, url=ch_link, style="primary")
                )

                bot.send_message(message.chat.id, warning_text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)
                return
        except Exception as e:
            print(f"Error checking sub: {e}")


@bot.message_handler(func=lambda message: message.chat.type == 'private')
def handle_private_messages(message):
    user_id = message.from_user.id

    if user_id in user_states:
        state_data = user_states[user_id]
        if state_data == "waiting_bot_sub_channel":
            channel = parse_channel_input(message)
            bot_info = bot.get_me()

            try:
                member = bot.get_chat_member(channel, bot_info.id)
                if member.status in ['left', 'kicked']:
                    raise Exception("BOT_NOT_ADMIN")

                set_bot_sub_channel(str(channel))
                user_states.pop(user_id, None)

                markup = InlineKeyboardMarkup()
                markup.add(
                    StyledInlineKeyboardButton("لوحة التحكم 🔙", callback_data="dev_panel", style="primary")
                )

                bot.reply_to(message, f"<b>✅ تم ضبط قناة الاشتراك الإجباري للبوت بنجاح: {channel}</b>", reply_markup=markup, parse_mode="HTML")
                return
            except Exception:
                markup = InlineKeyboardMarkup()
                markup.add(
                    StyledInlineKeyboardButton("لوحة التحكم 🔙", callback_data="dev_panel", style="primary")
                )

                bot.reply_to(message, "❌ فشل تعيين القناة. تأكد من أن البوت مشرف فيها!", reply_markup=markup)
                return


@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    if call.data == "check_bot_sub":
        bot_sub_ch = get_bot_sub_channel()
        if bot_sub_ch:
            try:
                member_status = bot.get_chat_member(bot_sub_ch, call.from_user.id)
                if member_status.status in ['left', 'kicked']:
                    bot.answer_callback_query(call.id, "❌ عذراً، لم تقم بالاشتراك في القناة بعد!", show_alert=True)
                    return
            except:
                pass

        bot.answer_callback_query(call.id, "✅ شكراً لاشتراكك!")
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        call.message.from_user = call.from_user
        send_welcome(call.message)

    elif call.data == "dev_panel":
        if not is_developer(call.from_user):
            bot.answer_callback_query(call.id, "هذه القائمة خاصة بالمطور فقط!", show_alert=True)
            return

        user_states.pop(call.from_user.id, None)
        bot_sub_ch = get_bot_sub_channel()
        sub_status = f"مفعلة ({bot_sub_ch})" if bot_sub_ch else "معطلة"

        text = f"🛠 <b>لوحة تحكم المطور العامة</b>\n\n• حالة الاشتراك الإجباري للبوت: <b>{sub_status}</b>"
        markup = InlineKeyboardMarkup(row_width=1)

        if bot_sub_ch:
            markup.add(
                StyledInlineKeyboardButton("إيقاف اشتراك البوت الإجباري 🛑", callback_data="disable_bot_sub", style="danger")
            )
            markup.add(
                StyledInlineKeyboardButton("تغيير قناة اشتراك البوت 🔄", callback_data="set_bot_sub", style="primary")
            )
        else:
            markup.add(
                StyledInlineKeyboardButton("تعيين قناة اشتراك إجباري للبوت ➕", callback_data="set_bot_sub", style="success")
            )

        markup.add(
            StyledInlineKeyboardButton("القائمة الرئيسية 🔙", callback_data="main_menu", style="primary")
        )

        try:
            bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="HTML")
        except:
            bot.send_message(call.message.chat.id, text, reply_markup=markup, parse_mode="HTML")

        bot.answer_callback_query(call.id)

    elif call.data == "set_bot_sub":
        if not is_developer(call.from_user):
            bot.answer_callback_query(call.id, "مرفوض!", show_alert=True)
            return

        user_states[call.from_user.id] = "waiting_bot_sub_channel"
        text = "📢 أرسل الآن يوزر القناة (مثلاً @ChannelName) أو قم بتوجيه منشور منها، وتأكد من أن البوت مشرف فيها:"
        
        markup = InlineKeyboardMarkup()
        markup.add(
            StyledInlineKeyboardButton("إلغاء ❌", callback_data="dev_panel", style="danger")
        )

        try:
            bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
        except:
            bot.send_message(call.message.chat.id, text, reply_markup=markup)

        bot.answer_callback_query(call.id)

    elif call.data == "disable_bot_sub":
        if not is_developer(call.from_user):
            bot.answer_callback_query(call.id, "مرفوض!", show_alert=True)
            return

        set_bot_sub_channel("")
        bot.answer_callback_query(call.id, "تم إيقاف اشتراك البوت الإجباري بنجاح", show_alert=True)
        call.data = "dev_panel"
        handle_callbacks(call)


print("بوت الاشتراك الإجباري يعمل الآن...")
bot.infinity_polling(skip_pending=True, timeout=10, long_polling_timeout=5)
