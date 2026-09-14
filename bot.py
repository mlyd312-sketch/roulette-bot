import os
import sys
import re
import time
import uuid
import shutil
import sqlite3
import logging
import tempfile
import threading
import subprocess
from datetime import datetime
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import telebot
from telebot import types

# ======= قاموس الإيموجيات المميزة (Custom Emoji IDs) ======= #
E = {
    'fire': '5424972470023104089',
    'check': '5206607081334906820',
    'sparkles': '5325547803936572038',
    'gem': '5427168083074628963',
    'pencil': '5395444784611480792',
    'settings': '5341715473882955310',
    'crown': '5217822164362739968',
    'chart': '5231200819986047254',
    'warning': '5447644880824181073',
    'trophy': '5188344996356448758',
    'people': '5258513401784573443',
    'link': '5271604874419647061',
    'picture': '5375074927252621134',
    'arrow': '5416117059207572332',
    'cross': '5210952531676504517',
    'bulb': '5422439311196834318',
    'bell': '5458603043203327669',
    'python': '5260480440971570446',
    'folder': '5431449001532594346',
    'restart': '5372860804316422072',
    'trash': '5445267414562389170',
    'stop': '5411225014148014586',
    'phone': '5445358775149883195',
    'key': '5424562381729012108',
    'shield': '5217549631293379466',
    'robot': '5258113901106580375',
}


def ce(emoji_key: str, default_icon: str = "✨") -> str:
    """تحويل مفتاح الإيموجي إلى وسم HTML مدعوم في تيليجرام"""
    emoji_id = E.get(emoji_key)
    if emoji_id:
        return f'<tg-emoji emoji-id="{emoji_id}">{default_icon}</tg-emoji>'
    return default_icon


def strip_emoji_from_text(text: str) -> str:
    """تنظيف النصوص المخصصة للأزرار من الإيموجيات العادية"""
    emoji_pattern = re.compile(
        r'[\U00010000-\U0010ffff]|[\u2600-\u27BF]|[\uFE00-\uFE0F]|[\u2300-\u23FF]'
    )
    return emoji_pattern.sub('', text).strip()


def escape_html(text: str) -> str:
    """حماية نصوص HTML من كسر التنسيق"""
    if not text:
        return ""
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def create_emoji_btn(text, callback_data=None, url=None, emoji_id=None, color="primary"):
    """إنشاء زر ملون يحمل إيموجي مميز"""
    clean_text = strip_emoji_from_text(text)
    btn_kwargs = {'text': clean_text}
    if callback_data:
        btn_kwargs['callback_data'] = callback_data
    if url:
        btn_kwargs['url'] = url

    btn = types.InlineKeyboardButton(**btn_kwargs)
    if emoji_id:
        try:
            setattr(btn, 'custom_emoji_id', emoji_id)
            setattr(btn, 'icon_custom_emoji_id', emoji_id)
        except Exception:
            pass
    if color:
        try:
            btn.style = color
        except Exception:
            pass
    return btn


# ======= إعدادات السجلات ======= #
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# ======= الثوابت والإعدادات ======= #
BOT_TOKEN = os.getenv('BOT_TOKEN', '8877293036:AAGg_82F0bT1Bhov42sk9qDcRMsVNpfnErw')
ADMIN_ID = int(os.getenv('ADMIN_ID', 1920665874))
YOUR_USERNAME = '@u_8_y'
ADMIN_CHANNEL = '@FD_CQ'

UPLOADED_FILES_DIR = "uploaded_files"
SUSPICIOUS_FILES_DIR = 'suspicious_files'
MAX_FILE_SIZE = 5 * 1024 * 1024

bot = telebot.TeleBot(BOT_TOKEN)
executor = ThreadPoolExecutor(max_workers=10)
lock = threading.Lock()

# حالة النظام
protection_enabled = True
protection_level = "medium"
bot_running = True

for directory in [UPLOADED_FILES_DIR, SUSPICIOUS_FILES_DIR]:
    os.makedirs(directory, exist_ok=True)


# ======= قاعدة البيانات (SQLite) ======= #
def init_sqlite_db():
    with sqlite3.connect('bot_data.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS approved_users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                approved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pending_requests (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT,
                username TEXT,
                requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute(
            'INSERT OR IGNORE INTO approved_users (user_id, username) VALUES (?, ?)',
            (ADMIN_ID, 'ADMIN')
        )
        conn.commit()


init_sqlite_db()


def is_admin(user_id):
    return user_id == ADMIN_ID


def is_approved_user(user_id):
    if is_admin(user_id):
        return True
    with sqlite3.connect('bot_data.db') as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM approved_users WHERE user_id = ?', (user_id,))
        return cursor.fetchone() is not None


def is_pending_user(user_id):
    with sqlite3.connect('bot_data.db') as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM pending_requests WHERE user_id = ?', (user_id,))
        return cursor.fetchone() is not None


def add_approved_user(user_id, username):
    with sqlite3.connect('bot_data.db') as conn:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT OR REPLACE INTO approved_users (user_id, username) VALUES (?, ?)',
            (user_id, username)
        )
        cursor.execute('DELETE FROM pending_requests WHERE user_id = ?', (user_id,))
        conn.commit()


def add_pending_request(user_id, first_name, username):
    with sqlite3.connect('bot_data.db') as conn:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT OR REPLACE INTO pending_requests (user_id, first_name, username) VALUES (?, ?, ?)',
            (user_id, first_name, username)
        )
        conn.commit()


def remove_pending_request(user_id):
    with sqlite3.connect('bot_data.db') as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM pending_requests WHERE user_id = ?', (user_id,))
        conn.commit()


def get_pending_requests():
    with sqlite3.connect('bot_data.db') as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, first_name, username FROM pending_requests')
        return cursor.fetchall()


def get_stats():
    with sqlite3.connect('bot_data.db') as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM approved_users')
        approved_count = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM pending_requests')
        pending_count = cursor.fetchone()[0]
        return approved_count, pending_count


# ======= تتبع العمليات المتعددة ======= #
# بنية: {chat_id: {file_id: {'name', 'path', 'process', 'uploader', 'started_at'}}}
active_processes = {}
pending_inputs = {}  # {chat_id: file_id}


# ======= كلمات مفتاحية للطلبات التفاعلية ======= #
INPUT_KEYWORDS = [
    'أرسل', 'ارسل', 'ادخل', 'أدخل', 'اكتب', 'رقم', 'كود', 'رمز',
    'otp', 'phone', 'code', 'password', 'pass', '2fa',
    'كلمة السر', 'كلمة سر', 'التحقق', 'الهاتف', 'هاتف',
    'input', 'enter', 'token', 'session', 'api_id', 'api_hash',
    'bot_token', 'user', 'username', 'name', 'id', 'auth', 'key',
    'verify', 'verification', 'security'
]
PROMPT_END_CHARS = ('؟', '?', ':', '!', '؛')


def _looks_like_prompt(text):
    """هل النص يبدو كطلب إدخال؟"""
    if not text or len(text.strip()) < 3:
        return False
    t_lower = text.lower()
    return any(kw.lower() in t_lower for kw in INPUT_KEYWORDS)


# ======= تشغيل/إيقاف/مراقبة الملفات ======= #
def start_script_process(script_path, chat_id, file_id):
    """تشغيل ملف معين بمُعرّف فريد مع مراقبة الإدخال"""
    with lock:
        if chat_id not in active_processes:
            active_processes[chat_id] = {}

        if file_id not in active_processes[chat_id]:
            active_processes[chat_id][file_id] = {
                'name': os.path.basename(script_path),
                'path': script_path,
                'process': None,
                'uploader': '',
                'started_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

        info = active_processes[chat_id][file_id]
        proc = info.get('process')

        if proc and proc.poll() is None:
            bot.send_message(
                chat_id,
                f"{ce('warning')} الملف <code>{escape_html(info['name'])}</code> يعمل بالفعل.",
                parse_mode='HTML'
            )
            return

        try:
            work_dir = os.path.dirname(script_path)
            p = subprocess.Popen(
                [sys.executable, "-u", script_path],
                cwd=work_dir,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0
            )
            info['process'] = p
            info['started_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            display_name = info['name']
            markup = types.InlineKeyboardMarkup(row_width=3)
            markup.add(
                create_emoji_btn("إيقاف", callback_data=f'stop_process_{file_id}',
                                 emoji_id=E['stop'], color="danger"),
                create_emoji_btn("إعادة تشغيل", callback_data=f'restart_process_{file_id}',
                                 emoji_id=E['restart'], color="success"),
                create_emoji_btn("حذف", callback_data=f'delete_process_{file_id}',
                                 emoji_id=E['trash'], color="danger")
            )
            markup.add(create_emoji_btn(
                f"📂 ملفاتي ({len(active_processes[chat_id])})",
                callback_data='my_files', emoji_id=E['folder'], color="primary"
            ))

            bot.send_message(
                chat_id,
                f"{ce('check')} <b>تم تشغيل الملف بنجاح:</b>\n"
                f"{ce('python')} الاسم: <code>{escape_html(display_name)}</code>\n"
                f"{ce('key')} المُعرّف: <code>{file_id}</code>\n\n"
                f"{ce('robot')} جارٍ مراقبة المدخلات والارتباط بالحساب تلقائياً...",
                reply_markup=markup,
                parse_mode='HTML'
            )

            monitor_thread = threading.Thread(
                target=monitor_process_output,
                args=(chat_id, file_id, p),
                daemon=True
            )
            monitor_thread.start()

        except Exception as e:
            logging.error(f"Failed to start script: {e}")
            bot.send_message(
                chat_id,
                f"{ce('cross')} فشل في تشغيل الملف: {escape_html(str(e))}",
                parse_mode='HTML'
            )


def monitor_process_output(chat_id, file_id, process):
    """مراقبة مخرجات الملف وإرسال طلبات الإدخال للمستخدم"""
    buffer = ""

    try:
        while True:
            try:
                char_bytes = process.stdout.read(1)
            except Exception:
                break

            if not char_bytes:
                if process.poll() is not None:
                    remaining = buffer.strip()
                    if remaining and len(remaining) > 5:
                        try:
                            bot.send_message(
                                chat_id,
                                f"{ce('bell')} <b>آخر إخراج من الملف:</b>\n"
                                f"<code>{escape_html(remaining[:800])}</code>",
                                parse_mode='HTML'
                            )
                        except Exception:
                            pass
                    break
                time.sleep(0.02)
                continue

            try:
                decoded = char_bytes.decode('utf-8', errors='replace')
            except Exception:
                continue

            buffer += decoded

            should_flush = False
            if '\n' in decoded:
                should_flush = True
            elif decoded in PROMPT_END_CHARS and len(buffer.strip()) >= 4:
                should_flush = True

            if should_flush:
                line = buffer.strip()
                buffer = ""

                if not line or len(line) < 3:
                    continue

                if _looks_like_prompt(line):
                    pending_inputs[chat_id] = file_id

                    markup = types.InlineKeyboardMarkup()
                    markup.add(create_emoji_btn(
                        "إلغاء الطلب",
                        callback_data=f'cancel_input_{file_id}',
                        emoji_id=E['cross'], color="danger"
                    ))

                    try:
                        bot.send_message(
                            chat_id,
                            f"{ce('phone')} <b>الملف يطلب إدخال بيانات:</b>\n\n"
                            f"<code>{escape_html(line[:800])}</code>\n\n"
                            f"{ce('pencil')} <b>أرسل الإجابة الآن مباشرة:</b>",
                            reply_markup=markup,
                            parse_mode='HTML'
                        )
                    except Exception:
                        try:
                            bot.send_message(chat_id, f"📨 {line[:800]}\n\n✍️ أرسل الإجابة:")
                        except Exception:
                            pass

    except Exception as e:
        logging.error(f"monitor error [{chat_id}/{file_id}]: {e}")
    finally:
        if pending_inputs.get(chat_id) == file_id:
            pending_inputs.pop(chat_id, None)


def stop_one_file(chat_id, file_id, delete=False):
    """إيقاف ملف واحد فقط"""
    if chat_id not in active_processes or file_id not in active_processes[chat_id]:
        return False

    info = active_processes[chat_id][file_id]
    proc = info.get('process')

    if proc and proc.poll() is None:
        try:
            proc.stdin.close()
        except Exception:
            pass
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

    if pending_inputs.get(chat_id) == file_id:
        pending_inputs.pop(chat_id, None)

    if delete and info.get('path') and os.path.exists(info['path']):
        try:
            os.remove(info['path'])
        except Exception:
            pass
        active_processes[chat_id].pop(file_id, None)

    return True


def stop_all_for_chat(chat_id):
    if chat_id not in active_processes:
        return 0
    count = 0
    for fid in list(active_processes[chat_id].keys()):
        if stop_one_file(chat_id, fid, delete=False):
            count += 1
    return count


# ======= فحص الأمان ======= #
def scan_file_for_malicious_code(file_path, user_id):
    if is_admin(user_id):
        return False, "مسؤول"

    try:
        with open(file_path, 'rb') as f:
            raw_data = f.read()

        content = raw_data.decode('utf-8', errors='ignore')

        dangerous_patterns = [
            r"rm\s+-rf\s+/",
            r"import\s+marshal",
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return True, f"تم اكتشاف نمط مشبوه: {pattern}"

        return False, ""
    except Exception as e:
        return False, ""


# ======= أوامر /start ======= #
@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id

    if not bot_running:
        bot.send_message(
            message.chat.id,
            f"{ce('warning')} البوت متوقف حاليًا لإجراء الصيانات.",
            parse_mode='HTML'
        )
        return

    if is_approved_user(user_id):
        show_main_menu(message)
    elif is_pending_user(user_id):
        bot.send_message(
            message.chat.id,
            f"{ce('bell')} طلبك قيد المراجعة من الإدارة. يرجى الانتظار.",
            parse_mode='HTML'
        )
    else:
        first_name = escape_html(message.from_user.first_name or 'مستخدم')
        raw_username = message.from_user.username or 'بدون_يوزر'
        username = escape_html(raw_username)

        add_pending_request(user_id, message.from_user.first_name or 'مستخدم', raw_username)

        markup = types.InlineKeyboardMarkup()
        markup.add(
            create_emoji_btn("قبول", callback_data=f'approve_{user_id}',
                             emoji_id=E['check'], color="success"),
            create_emoji_btn("رفض", callback_data=f'reject_{user_id}',
                             emoji_id=E['cross'], color="danger")
        )

        try:
            bot.send_message(
                ADMIN_ID,
                f"{ce('pencil')} <b>طلب اشتراك جديد:</b>\n\n"
                f"{ce('people')} الاسم: {first_name}\n"
                f"{ce('link')} ID: <code>{user_id}</code>\n"
                f"{ce('sparkles')} اليوزر: @{username}",
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logging.error(f"Failed to send request to admin: {e}")

        bot.send_message(
            message.chat.id,
            f"{ce('bell')} <b>تم إرسال طلب اشتراكك إلى الأدمن.</b>\n"
            f"يرجى الانتظار لحين الموافقة عليه.",
            parse_mode='HTML'
        )


def show_main_menu(message):
    markup = types.InlineKeyboardMarkup(row_width=2)

    markup.add(
        create_emoji_btn("التحكم في الحماية", callback_data='protection_control',
                         emoji_id=E['shield'], color="primary"),
        create_emoji_btn("رفع ملف", callback_data='upload',
                         emoji_id=E['python'], color="success")
    )
    markup.add(
        create_emoji_btn("ملفاتي", callback_data='my_files',
                         emoji_id=E['folder'], color="primary"),
        create_emoji_btn("فتاة المحاور", callback_data='support_girl',
                         emoji_id=E['sparkles'], color="primary")
    )
    markup.add(
        create_emoji_btn("سرعة البوت", callback_data='speed',
                         emoji_id=E['fire'], color="primary"),
        create_emoji_btn("حول البوت", callback_data='about_bot',
                         emoji_id=E['bulb'], color="primary")
    )
    markup.add(
        create_emoji_btn("الدعم الفني", callback_data='tech_support',
                         emoji_id=E['bell'], color="primary"),
        create_emoji_btn("تثبيت مكتبة", callback_data='download_lib',
                         emoji_id=E['pencil'], color="success")
    )
    markup.add(
        create_emoji_btn("التواصل مع الدعم", callback_data='online_support',
                         emoji_id=E['link'], color="primary")
    )

    if is_admin(message.from_user.id):
        markup.add(
            create_emoji_btn("إدارة المستخدمين", callback_data='manage_users',
                             emoji_id=E['people'], color="primary"),
            create_emoji_btn("حالة البوت الرئيسي", callback_data='bot_control',
                             emoji_id=E['crown'], color="primary")
        )

    first_name = escape_html(message.from_user.first_name or '')
    bot.send_message(
        message.chat.id,
        f"{ce('python')} <b>مرحباً بك في منصة Python Hosting</b>\n\n"
        f"مرحباً، {first_name}! {ce('sparkles')}\n\n"
        f"{ce('people')} المطور: {YOUR_USERNAME}\n"
        f"{ce('link')} القناة: {ADMIN_CHANNEL}\n\n"
        f"اختر الخدمة المطلوبة من الأزرار أدناه:",
        reply_markup=markup,
        parse_mode='HTML'
    )


# ======= معالج إدخال المستخدم للملفات ======= #
@bot.message_handler(
    func=lambda m: (
        m.chat.id in pending_inputs
        and m.content_type == 'text'
        and not m.text.startswith('/')
    )
)
def handle_process_input(message):
    chat_id = message.chat.id
    file_id = pending_inputs.get(chat_id)

    if not file_id:
        return

    if chat_id not in active_processes or file_id not in active_processes[chat_id]:
        pending_inputs.pop(chat_id, None)
        bot.reply_to(message, f"{ce('cross')} العملية لم تعد موجودة.", parse_mode='HTML')
        return

    info = active_processes[chat_id][file_id]
    process = info.get('process')

    if not process or process.poll() is not None:
        pending_inputs.pop(chat_id, None)
        bot.reply_to(message, f"{ce('cross')} الملف لم يعد يعمل.", parse_mode='HTML')
        return

    user_input = message.text.strip()

    try:
        process.stdin.write((user_input + "\n").encode('utf-8'))
        process.stdin.flush()

        if len(user_input) > 8:
            masked = user_input[:3] + "*" * (len(user_input) - 6) + user_input[-3:]
        else:
            masked = user_input[:2] + "*" * max(0, len(user_input) - 2)

        bot.reply_to(
            message,
            f"{ce('check')} تم إرسال الإجابة للملف: <code>{masked}</code>\n"
            f"{ce('robot')} جارٍ المتابعة...",
            parse_mode='HTML'
        )

        pending_inputs.pop(chat_id, None)

    except Exception as e:
        bot.reply_to(
            message,
            f"{ce('cross')} فشل في إرسال الإدخال: {escape_html(str(e))}",
            parse_mode='HTML'
        )


@bot.callback_query_handler(func=lambda call: call.data.startswith('cancel_input_'))
def cancel_input_callback(call):
    chat_id = call.message.chat.id
    file_id = call.data.replace('cancel_input_', '')

    pending_inputs.pop(chat_id, None)

    bot.answer_callback_query(call.id, "✅ تم إلغاء طلب الإدخال")
    try:
        bot.edit_message_text(
            f"{ce('cross')} تم إلغاء طلب الإدخال.\nالملف ما زال يعمل لكن بدون رد.",
            chat_id,
            call.message.message_id,
            parse_mode='HTML'
        )
    except Exception:
        pass


# ======= القائمة الرئيسية ======= #
@bot.callback_query_handler(func=lambda call: call.data == 'back_to_main')
def back_to_main(call):
    bot.answer_callback_query(call.id)
    show_main_menu(call.message)


@bot.callback_query_handler(func=lambda call: call.data == 'speed')
def speed_test(call):
    start_time = time.time()
    msg = bot.send_message(
        call.message.chat.id,
        f"{ce('fire')} جاري قياس استجابة السيرفر...",
        parse_mode='HTML'
    )
    end_time = time.time()

    latency = (end_time - start_time) * 1000
    bot.edit_message_text(
        f"{ce('fire')} <b>سرعة استجابة البوت:</b> <code>{latency:.2f} ms</code>",
        call.message.chat.id,
        msg.message_id,
        parse_mode='HTML'
    )


@bot.callback_query_handler(func=lambda call: call.data == 'upload')
def upload_prompt(call):
    if not is_approved_user(call.from_user.id):
        bot.answer_callback_query(call.id, "غير مصرح لك")
        return

    bot.send_message(
        call.message.chat.id,
        f"{ce('pencil')} <b>قم بإرسال ملف البوت بصيغة (.py) الآن:</b>\n\n"
        f"{ce('robot')} يمكنك رفع عدة ملفات وكل ملف سيعمل بشكل مستقل.\n"
        f"{ce('phone')} الملفات التي تطلب رقم/OTP/2FA سيتفاعل معها البوت تلقائياً.",
        parse_mode='HTML'
    )


# ======= رفع الملفات (يدعم متعدد) ======= #
@bot.message_handler(content_types=['document'])
def handle_incoming_file(message):
    user_id = message.from_user.id
    if not is_approved_user(user_id):
        bot.reply_to(
            message,
            f"{ce('cross')} ليس لديك صلاحية لاستخدام هذه الخدمة.",
            parse_mode='HTML'
        )
        return

    if not message.document.file_name.endswith('.py'):
        bot.reply_to(
            message,
            f"{ce('cross')} يُقبل ملفات بصيغة <code>.py</code> فقط!",
            parse_mode='HTML'
        )
        return

    if message.document.file_size > MAX_FILE_SIZE:
        bot.reply_to(
            message,
            f"{ce('warning')} حجم الملف يتجاوز الحد الأقصى المسموح به (5MB).",
            parse_mode='HTML'
        )
        return

    try:
        chat_id = message.chat.id
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        original_name = message.document.file_name
        file_id = uuid.uuid4().hex[:8]

        # مجلد خاص لكل مستخدم
        user_dir = os.path.join(UPLOADED_FILES_DIR, str(user_id))
        os.makedirs(user_dir, exist_ok=True)

        internal_name = f"{file_id}_{original_name}"
        save_path = os.path.join(user_dir, internal_name)

        with open(save_path, 'wb') as new_file:
            new_file.write(downloaded_file)

        if protection_enabled:
            is_dangerous, reason = scan_file_for_malicious_code(save_path, user_id)
            if is_dangerous:
                os.remove(save_path)
                bot.reply_to(
                    message,
                    f"{ce('warning')} <b>تم رفض الملف لاحتوائه على كود خطير:</b>\n"
                    f"<code>{escape_html(reason)}</code>",
                    parse_mode='HTML'
                )
                return

        # تهيئة القاموس
        if chat_id not in active_processes:
            active_processes[chat_id] = {}

        active_processes[chat_id][file_id] = {
            'name': original_name,
            'path': save_path,
            'process': None,
            'uploader': message.from_user.username or '',
            'started_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        total = len(active_processes[chat_id])

        # تشغيل الملف
        start_script_process(save_path, chat_id, file_id)

        # إشعار العدد الإجمالي
        bot.send_message(
            chat_id,
            f"{ce('chart')} <b>مجموع ملفاتك الآن:</b> <code>{total}</code>",
            parse_mode='HTML'
        )

    except Exception as e:
        logging.error(f"Error handling file upload: {e}")
        bot.reply_to(
            message,
            f"{ce('cross')} حدث خطأ أثناء معالجة الملف: {escape_html(str(e))}",
            parse_mode='HTML'
        )


# ======= إيقاف/إعادة/حذف ملف محدد ======= #
@bot.callback_query_handler(func=lambda call: call.data.startswith('stop_process_'))
def handle_stop_process(call):
    file_id = call.data.replace('stop_process_', '')
    chat_id = call.message.chat.id

    if chat_id not in active_processes or file_id not in active_processes[chat_id]:
        bot.answer_callback_query(call.id, "❌ الملف غير موجود")
        return

    name = active_processes[chat_id][file_id].get('name', 'ملف')

    if stop_one_file(chat_id, file_id, delete=False):
        bot.answer_callback_query(call.id, f"✅ تم إيقاف {name}")
        show_my_files(call, edit=True)
    else:
        bot.answer_callback_query(call.id, "❌ فشل الإيقاف")


@bot.callback_query_handler(func=lambda call: call.data.startswith('restart_process_'))
def handle_restart_process(call):
    file_id = call.data.replace('restart_process_', '')
    chat_id = call.message.chat.id

    if chat_id not in active_processes or file_id not in active_processes[chat_id]:
        bot.answer_callback_query(call.id, "❌ الملف غير موجود")
        return

    info = active_processes[chat_id][file_id]
    stop_one_file(chat_id, file_id, delete=False)
    time.sleep(0.3)
    start_script_process(info['path'], chat_id, file_id)
    bot.answer_callback_query(call.id, "🔄 تم إعادة التشغيل")


@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_process_'))
def handle_delete_process(call):
    file_id = call.data.replace('delete_process_', '')
    chat_id = call.message.chat.id

    if chat_id not in active_processes or file_id not in active_processes[chat_id]:
        bot.answer_callback_query(call.id, "❌ الملف غير موجود")
        return

    name = active_processes[chat_id][file_id].get('name', 'ملف')

    if stop_one_file(chat_id, file_id, delete=True):
        bot.answer_callback_query(call.id, f"🗑️ تم حذف {name}")
        show_my_files(call, edit=True)
    else:
        bot.answer_callback_query(call.id, "❌ فشل الحذف")


# ======= لوحة "ملفاتي" ======= #
@bot.callback_query_handler(func=lambda call: call.data == 'my_files')
def my_files_callback(call):
    show_my_files(call, edit=False)


def show_my_files(call, edit=False):
    chat_id = call.message.chat.id

    if chat_id not in active_processes or not active_processes[chat_id]:
        txt = (
            f"{ce('folder')} <b>لا توجد ملفات مرفوعة حالياً</b>\n\n"
            f"ارفع ملف .py أولاً من زر (رفع ملف)."
        )
        if edit:
            try:
                bot.edit_message_text(txt, chat_id, call.message.message_id, parse_mode='HTML')
            except Exception:
                bot.send_message(chat_id, txt, parse_mode='HTML')
        else:
            bot.send_message(chat_id, txt, parse_mode='HTML')
        return

    files = active_processes[chat_id]
    running = sum(1 for f in files.values() if f.get('process') and f['process'].poll() is None)

    text = (
        f"{ce('folder')} <b>ملفاتك المرفوعة</b> ({len(files)})\n"
        f"{ce('check')} قيد التشغيل: <code>{running}</code>\n"
        f"{ce('stop')} متوقف: <code>{len(files) - running}</code>\n\n"
        f"{ce('arrow')} اضغط على اسم الملف لعرض التفاصيل."
    )

    markup = types.InlineKeyboardMarkup(row_width=4)

    for fid, info in files.items():
        proc = info.get('process')
        is_running = bool(proc and proc.poll() is None)
        status_icon = "🟢" if is_running else "🔴"
        name = info.get('name', 'ملف')[:20]

        markup.row(
            types.InlineKeyboardButton(f"{status_icon} {name}", callback_data=f'nf_{fid}'),
            types.InlineKeyboardButton("🔄", callback_data=f'restart_process_{fid}'),
            types.InlineKeyboardButton("🛑", callback_data=f'stop_process_{fid}'),
            types.InlineKeyboardButton("🗑️", callback_data=f'delete_process_{fid}')
        )

    markup.add(
        create_emoji_btn("إيقاف الكل", callback_data='stop_all_files',
                         emoji_id=E['stop'], color="danger"),
        create_emoji_btn("رجوع", callback_data='back_to_main',
                         emoji_id=E['arrow'], color="primary")
    )

    if edit:
        try:
            bot.edit_message_text(text, chat_id, call.message.message_id,
                                  reply_markup=markup, parse_mode='HTML')
        except Exception:
            bot.send_message(chat_id, text, reply_markup=markup, parse_mode='HTML')
    else:
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode='HTML')


@bot.callback_query_handler(func=lambda call: call.data.startswith('nf_'))
def file_info_callback(call):
    file_id = call.data.replace('nf_', '')
    chat_id = call.message.chat.id

    if chat_id not in active_processes or file_id not in active_processes[chat_id]:
        bot.answer_callback_query(call.id, "❌ غير موجود")
        return

    info = active_processes[chat_id][file_id]
    proc = info.get('process')
    status = "🟢 يعمل" if (proc and proc.poll() is None) else "🔴 متوقف"
    pid = proc.pid if proc and proc.poll() is None else "—"

    bot.answer_callback_query(
        call.id,
        f"📁 {info['name']}\n"
        f"الحالة: {status}\n"
        f"PID: {pid}\n"
        f"🆔 {file_id}\n"
        f"⏰ {info.get('started_at', '—')}",
        show_alert=True
    )


@bot.callback_query_handler(func=lambda call: call.data == 'stop_all_files')
def stop_all_files_cb(call):
    chat_id = call.message.chat.id
    count = stop_all_for_chat(chat_id)
    bot.answer_callback_query(call.id, f"🛑 تم إيقاف {count} ملف")
    show_my_files(call, edit=True)


# ======= التحكم بالحماية ======= #
@bot.callback_query_handler(func=lambda call: call.data == 'protection_control')
def protection_control_handler(call):
    markup = types.InlineKeyboardMarkup()
    global protection_enabled

    if protection_enabled:
        status_text = f"{ce('check')} نظام الحماية مفعل"
        toggle_btn = create_emoji_btn("تعطيل الحماية", callback_data='toggle_prot_off',
                                       emoji_id=E['cross'], color="danger")
    else:
        status_text = f"{ce('cross')} نظام الحماية معطل"
        toggle_btn = create_emoji_btn("تفعيل الحماية", callback_data='toggle_prot_on',
                                       emoji_id=E['check'], color="success")

    markup.add(toggle_btn)
    markup.add(create_emoji_btn("رجوع", callback_data='back_to_main',
                                 emoji_id=E['arrow'], color="primary"))

    try:
        bot.edit_message_text(
            f"{ce('settings')} <b>إعدادات الحماية والأمان</b>\n\n"
            f"حالة الحماية: {status_text}\n"
            f"مستوى الفحص: <code>{protection_level}</code>",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
            parse_mode='HTML'
        )
    except Exception:
        pass


@bot.callback_query_handler(func=lambda call: call.data in ['toggle_prot_on', 'toggle_prot_off'])
def toggle_protection_status(call):
    global protection_enabled
    protection_enabled = (call.data == 'toggle_prot_on')
    msg = "تم تفعيل الحماية" if protection_enabled else "تم تعطيل الحماية"
    bot.answer_callback_query(call.id, msg)
    protection_control_handler(call)


# ======= التحكم بالبوت ======= #
@bot.callback_query_handler(func=lambda call: call.data == 'bot_control')
def bot_control_handler(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "هذه الخاصية مخصصة للأدمن فقط.", show_alert=True)
        return

    markup = types.InlineKeyboardMarkup()
    if bot_running:
        status_text = f"{ce('check')} البوت يعمل حالياً"
        toggle_btn = create_emoji_btn("إيقاف البوت مؤقتاً", callback_data='toggle_bot_off',
                                       emoji_id=E['warning'], color="danger")
    else:
        status_text = f"{ce('cross')} البوت متوقف حالياً"
        toggle_btn = create_emoji_btn("تشغيل البوت", callback_data='toggle_bot_on',
                                       emoji_id=E['check'], color="success")

    back_btn = create_emoji_btn("رجوع", callback_data='back_to_main',
                                 emoji_id=E['arrow'], color="primary")
    markup.add(toggle_btn)
    markup.add(back_btn)

    try:
        bot.edit_message_text(
            f"{ce('crown')} <b>لوحة التحكم بحالة البوت الرئيسي</b>\n\n"
            f"الحالة الحالية: {status_text}",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
            parse_mode='HTML'
        )
    except Exception:
        pass


@bot.callback_query_handler(func=lambda call: call.data in ['toggle_bot_on', 'toggle_bot_off'])
def toggle_bot_status(call):
    global bot_running
    if not is_admin(call.from_user.id):
        return

    bot_running = (call.data == 'toggle_bot_on')
    msg = "تم تشغيل البوت" if bot_running else "تم إيقاف البوت مؤقتاً"
    bot.answer_callback_query(call.id, msg)
    bot_control_handler(call)


# ======= الأزرار الأخرى ======= #
@bot.callback_query_handler(func=lambda call: call.data == 'support_girl')
def support_girl_handler(call):
    markup = types.InlineKeyboardMarkup()
    markup.add(create_emoji_btn("رجوع", callback_data='back_to_main',
                                 emoji_id=E['arrow'], color="primary"))

    try:
        bot.edit_message_text(
            f"{ce('sparkles')} <b>فتاة المحاور</b>\n\n"
            f"أهلاً بك! يمكنك الاستفسار عن كيفية رفع البوتات وتحديثها أو حل المشاكل البرمجية الشائعة.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
            parse_mode='HTML'
        )
    except Exception:
        pass


@bot.callback_query_handler(func=lambda call: call.data == 'about_bot')
def about_bot_handler(call):
    markup = types.InlineKeyboardMarkup()
    markup.add(create_emoji_btn("رجوع", callback_data='back_to_main',
                                 emoji_id=E['arrow'], color="primary"))

    try:
        bot.edit_message_text(
            f"{ce('bulb')} <b>حول البوت:</b>\n\n"
            f"{ce('python')} منصة لرفع واستضافة ملفات بايثون\n"
            f"{ce('folder')} تشغيل عدة ملفات في وقت واحد\n"
            f"{ce('phone')} تفاعل ذكي مع طلبات الرقم/OTP/2FA\n"
            f"{ce('shield')} نظام حماية متقدم\n\n"
            f"{ce('people')} <b>المطور:</b> {YOUR_USERNAME}\n"
            f"{ce('link')} <b>القناة:</b> {ADMIN_CHANNEL}",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
            parse_mode='HTML'
        )
    except Exception:
        pass


@bot.callback_query_handler(func=lambda call: call.data in ['tech_support', 'online_support'])
def support_handler(call):
    markup = types.InlineKeyboardMarkup()
    markup.add(create_emoji_btn("راسل المسؤول",
                                 url=f"https://t.me/{YOUR_USERNAME.replace('@', '')}",
                                 emoji_id=E['people'], color="primary"))
    markup.add(create_emoji_btn("قناة المساعدة",
                                 url=f"https://t.me/{ADMIN_CHANNEL.replace('@', '')}",
                                 emoji_id=E['link'], color="primary"))
    markup.add(create_emoji_btn("رجوع", callback_data='back_to_main',
                                 emoji_id=E['arrow'], color="primary"))

    try:
        bot.edit_message_text(
            f"{ce('bell')} <b>الدعم الفني والخدمات</b>\n\n"
            f"للتواصل المباشر مع الإدارة: {YOUR_USERNAME}\n"
            f"القناة الرسمية: {ADMIN_CHANNEL}",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
            parse_mode='HTML'
        )
    except Exception:
        pass


# ======= معالجة القبول والرفض ======= #
@bot.callback_query_handler(func=lambda call: call.data.startswith(('approve_', 'reject_')))
def handle_user_approval(call):
    if not is_admin(call.from_user.id):
        return

    action, target_user_id = call.data.split('_')
    target_user_id = int(target_user_id)

    if action == 'approve':
        add_approved_user(target_user_id, 'USER')
        bot.answer_callback_query(call.id, "تم قبول المستخدم")
        try:
            bot.edit_message_text(
                f"{ce('check')} تم القبول بنجاح لـ ID: <code>{target_user_id}</code>",
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML'
            )
        except Exception:
            pass
        try:
            bot.send_message(
                target_user_id,
                f"{ce('sparkles')} <b>تمت الموافقة على اشتراكك!</b>\n"
                f"يمكنك الآن استخدام البوت عبر /start",
                parse_mode='HTML'
            )
        except Exception:
            pass
    else:
        remove_pending_request(target_user_id)
        bot.answer_callback_query(call.id, "تم رفض المستخدم")
        try:
            bot.edit_message_text(
                f"{ce('cross')} تم رفض الطلب لـ ID: <code>{target_user_id}</code>",
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML'
            )
        except Exception:
            pass


# ======= إدارة المستخدمين ======= #
@bot.callback_query_handler(func=lambda call: call.data == 'manage_users')
def manage_users_view(call):
    if not is_admin(call.from_user.id):
        return

    approved_count, pending_count = get_stats()
    pending_list = get_pending_requests()

    markup = types.InlineKeyboardMarkup()

    for uid, fname, uname in pending_list:
        clean_fname = escape_html(fname or 'مستخدم')[:15]
        markup.add(
            create_emoji_btn(f"قبول {clean_fname}", callback_data=f'approve_{uid}',
                             emoji_id=E['check'], color="success"),
            create_emoji_btn(f"رفض {clean_fname}", callback_data=f'reject_{uid}',
                             emoji_id=E['cross'], color="danger")
        )

    markup.add(create_emoji_btn("رجوع", callback_data='back_to_main',
                                 emoji_id=E['arrow'], color="primary"))

    try:
        bot.edit_message_text(
            f"{ce('people')} <b>إدارة المستخدمين والطلبات:</b>\n\n"
            f"{ce('check')} عدد المعتمدين: <code>{approved_count}</code>\n"
            f"{ce('bell')} طلبات الانتظار: <code>{pending_count}</code>",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
            parse_mode='HTML'
        )
    except Exception:
        pass


# ======= تثبيت مكتبة ======= #
@bot.callback_query_handler(func=lambda call: call.data == 'download_lib')
def prompt_install_lib(call):
    bot.send_message(
        call.message.chat.id,
        f"{ce('pencil')} <b>أرسل اسم المكتبة المراد تثبيتها (مثال: requests):</b>",
        parse_mode='HTML'
    )
    bot.register_next_step_handler(call.message, process_install_lib)


def process_install_lib(message):
    lib_name = message.text.strip()
    if not re.match(r'^[a-zA-Z0-9_\-]+$', lib_name):
        bot.send_message(message.chat.id, f"{ce('cross')} اسم المكتبة غير صالح.", parse_mode='HTML')
        return

    bot.send_message(
        message.chat.id,
        f"{ce('fire')} جاري تثبيت المكتبة <code>{escape_html(lib_name)}</code>...",
        parse_mode='HTML'
    )

    def install():
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", lib_name],
                capture_output=True, text=True, timeout=180
            )
            if result.returncode == 0:
                bot.send_message(
                    message.chat.id,
                    f"{ce('check')} تم تثبيت المكتبة <code>{escape_html(lib_name)}</code> بنجاح!",
                    parse_mode='HTML'
                )
            else:
                bot.send_message(
                    message.chat.id,
                    f"{ce('cross')} فشل تثبيت المكتبة:\n"
                    f"<pre>{escape_html(result.stderr[:500])}</pre>",
                    parse_mode='HTML'
                )
        except Exception as e:
            bot.send_message(
                message.chat.id,
                f"{ce('cross')} حدث خطأ أثناء التثبيت: {escape_html(str(e))}",
                parse_mode='HTML'
            )

    executor.submit(install)


# ======= التشغيل الرئيسي ======= #
if __name__ == '__main__':
    logging.info("=" * 55)
    logging.info("🤖 Bot starting...")
    logging.info(f"👨‍💻 Admin: {ADMIN_ID}")
    logging.info(f"📢 Channel: {ADMIN_CHANNEL}")
    logging.info("=" * 55)

    while True:
        try:
            bot.polling(none_stop=True, interval=1, timeout=60)
        except Exception as err:
            logging.error(f"Polling Exception: {err}")
            time.sleep(3)
