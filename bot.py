# ============================================================
# 🚀 التثبيت التلقائي للمكتبات الناقصة
# ============================================================
import sys
import os

try:
    marker = "/tmp/.libs_installed"
    if not os.path.exists(marker):
        print("🚀 تشغيل التثبيت التلقائي...")
        import subprocess as _sp
        _sp.run([sys.executable, "autoinstall.py"], check=False)
        try:
            with open(marker, "w") as f:
                f.write("ok")
        except Exception:
            pass
except Exception as e:
    print(f"⚠️ تخطي التثبيت التلقائي: {e}")

# ============================================================
# الاستيرادات
# ============================================================
import re
import time
import uuid
import sqlite3
import logging
import threading
import subprocess
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import telebot
from telebot import types

# ============================================================
# إيموجيات مخصصة
# ============================================================
E = {
    'fire': '5424972470023104089',
    'check': '5206607081334906820',
    'sparkles': '5325547803936572038',
    'pencil': '5395444784611480792',
    'settings': '5341715473882955310',
    'crown': '5217822164362739968',
    'warning': '5447644880824181073',
    'people': '5258513401784573443',
    'link': '5271604874419647061',
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


def ce(key, default="✨"):
    eid = E.get(key)
    if eid:
        return f'<tg-emoji emoji-id="{eid}">{default}</tg-emoji>'
    return default


def eh(text):
    if text is None:
        return ""
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


# ============================================================
# Logging
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# ============================================================
# الإعدادات
# ============================================================
BOT_TOKEN = os.getenv('BOT_TOKEN', '8877293036:AAGg_82F0bT1Bhov42sk9qDcRMsVNpfnErw')
ADMIN_ID = int(os.getenv('ADMIN_ID', '1920665874'))
YOUR_USERNAME = '@u_8_y'
ADMIN_CHANNEL = '@FD_CQ'

# مهم: استخدام مسار مطلق للمجلد الأساسي
BASE_DIR = os.path.abspath(os.getcwd())
UPLOADED_FILES_DIR = os.path.join(BASE_DIR, "uploaded_files")
MAX_FILE_SIZE = 10 * 1024 * 1024

bot = telebot.TeleBot(BOT_TOKEN)
executor = ThreadPoolExecutor(max_workers=10)
lock = threading.Lock()

protection_enabled = True
bot_running = True

os.makedirs(UPLOADED_FILES_DIR, exist_ok=True)

logging.info(f"📁 Base directory: {BASE_DIR}")
logging.info(f"📁 Uploads directory: {UPLOADED_FILES_DIR}")

# ============================================================
# قاعدة البيانات
# ============================================================
def init_db():
    with sqlite3.connect('bot_data.db') as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS approved_users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            approved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS pending_requests (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('INSERT OR IGNORE INTO approved_users (user_id, username) VALUES (?, ?)',
                  (ADMIN_ID, 'ADMIN'))
        conn.commit()


init_db()


def is_admin(uid):
    return uid == ADMIN_ID


def is_approved(uid):
    if is_admin(uid):
        return True
    with sqlite3.connect('bot_data.db') as conn:
        c = conn.cursor()
        c.execute('SELECT user_id FROM approved_users WHERE user_id = ?', (uid,))
        return c.fetchone() is not None


def is_pending(uid):
    with sqlite3.connect('bot_data.db') as conn:
        c = conn.cursor()
        c.execute('SELECT user_id FROM pending_requests WHERE user_id = ?', (uid,))
        return c.fetchone() is not None


def add_approved(uid, username):
    with sqlite3.connect('bot_data.db') as conn:
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO approved_users (user_id, username) VALUES (?, ?)',
                  (uid, username))
        c.execute('DELETE FROM pending_requests WHERE user_id = ?', (uid,))
        conn.commit()


def add_pending(uid, fname, username):
    with sqlite3.connect('bot_data.db') as conn:
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO pending_requests (user_id, first_name, username) VALUES (?, ?, ?)',
                  (uid, fname, username))
        conn.commit()


def remove_pending(uid):
    with sqlite3.connect('bot_data.db') as conn:
        c = conn.cursor()
        c.execute('DELETE FROM pending_requests WHERE user_id = ?', (uid,))
        conn.commit()


def get_pending():
    with sqlite3.connect('bot_data.db') as conn:
        c = conn.cursor()
        c.execute('SELECT user_id, first_name, username FROM pending_requests')
        return c.fetchall()


def get_stats():
    with sqlite3.connect('bot_data.db') as conn:
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM approved_users')
        a = c.fetchone()[0]
        c.execute('SELECT COUNT(*) FROM pending_requests')
        p = c.fetchone()[0]
        return a, p


# ============================================================
# الحالة العامة
# ============================================================
active_processes = {}
pending_inputs = {}
waiting_library = set()


# ============================================================
# كلمات مفتاحية لطلبات الإدخال
# ============================================================
INPUT_KEYWORDS = [
    'أرسل', 'ارسل', 'ادخل', 'أدخل', 'اكتب', 'رقم', 'كود', 'رمز',
    'otp', 'phone', 'code', 'password', 'pass', '2fa',
    'كلمة السر', 'كلمة سر', 'التحقق', 'الهاتف', 'هاتف',
    'input', 'enter', 'token', 'session', 'api_id', 'api_hash',
    'bot_token', 'user', 'username', 'auth', 'key', 'verify',
    'number', 'account', 'login', 'sign', 'pin', 'secret',
    'text', 'message', 'reply'
]
PROMPT_END = ('؟', '?', ':', '!', '؛')


def looks_prompt(text):
    if not text or len(text.strip()) < 3:
        return False
    t = text.lower()
    return any(kw.lower() in t for kw in INPUT_KEYWORDS)


# ============================================================
# تشغيل الملفات
# ============================================================
def start_file(script_path, chat_id, file_id):
    # ✅ إصلاح: تحويل المسار إلى مطلق دائماً
    script_path = os.path.abspath(script_path)

    with lock:
        if chat_id not in active_processes:
            active_processes[chat_id] = {}

        if file_id not in active_processes[chat_id]:
            active_processes[chat_id][file_id] = {
                'name': os.path.basename(script_path),
                'path': script_path,
                'process': None,
                'started_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

        info = active_processes[chat_id][file_id]
        info['path'] = script_path  # تأكد من تحديث المسار

        proc = info.get('process')
        if proc and proc.poll() is None:
            try:
                bot.send_message(chat_id, "⚠️ الملف يعمل بالفعل.")
            except Exception:
                pass
            return

        # تحقق أن الملف موجود فعلاً
        if not os.path.exists(script_path):
            try:
                bot.send_message(
                    chat_id,
                    f"❌ الملف غير موجود على السيرفر:\n<code>{eh(script_path)}</code>",
                    parse_mode='HTML'
                )
            except Exception:
                pass
            return

        try:
            # ✅ إصلاح: cwd = مجلد الملف المطلق
            work_dir = os.path.dirname(script_path)

            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            env['PYTHONIOENCODING'] = 'utf-8'

            logging.info(f"🚀 تشغيل: {script_path}")
            logging.info(f"📁 من: {work_dir}")

            p = subprocess.Popen(
                [sys.executable, "-u", script_path],
                cwd=work_dir,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,
                env=env,
                start_new_session=True
            )
            info['process'] = p
            info['started_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            markup = types.InlineKeyboardMarkup(row_width=3)
            markup.add(
                types.InlineKeyboardButton("🛑 إيقاف", callback_data=f'sf_{file_id}'),
                types.InlineKeyboardButton("🔄 إعادة", callback_data=f'rf_{file_id}'),
                types.InlineKeyboardButton("🗑️ حذف", callback_data=f'df_{file_id}')
            )
            markup.add(types.InlineKeyboardButton(
                f"📂 ملفاتي ({len(active_processes[chat_id])})",
                callback_data='my_files'
            ))

            bot.send_message(
                chat_id,
                f"✅ <b>تم تشغيل الملف بنجاح</b>\n"
                f"📁 <code>{eh(info['name'])}</code>\n"
                f"🆔 <code>{file_id}</code>\n"
                f"PID: <code>{p.pid}</code>\n\n"
                f"⚡ جارٍ مراقبة الإخراج والمدخلات...",
                reply_markup=markup,
                parse_mode='HTML'
            )

            t = threading.Thread(
                target=monitor_output,
                args=(chat_id, file_id, p),
                daemon=True
            )
            t.start()

        except Exception as e:
            logging.error(f"start_file error: {e}")
            try:
                bot.send_message(chat_id, f"❌ فشل: {eh(str(e))}", parse_mode='HTML')
            except Exception:
                pass


def monitor_output(chat_id, file_id, process):
    """يعرض كل إخراج الملف + يكتشف طلبات الإدخال + يخبر عند التوقف"""
    buffer = ""
    shown_lines = 0
    MAX_SHOWN = 50
    pending_batch = []
    last_flush = time.time()

    def flush_batch():
        nonlocal pending_batch, last_flush
        if not pending_batch:
            return
        text = "\n".join(pending_batch[:40])
        pending_batch = []
        try:
            bot.send_message(
                chat_id,
                f"📄 <b>إخراج الملف:</b>\n<pre>{eh(text[:3500])}</pre>",
                parse_mode='HTML'
            )
        except Exception as e:
            logging.error(f"send output: {e}")
        last_flush = time.time()

    try:
        while True:
            try:
                ch = process.stdout.read(1)
            except Exception as e:
                logging.error(f"read error [{chat_id}/{file_id}]: {e}")
                break

            if not ch:
                if process.poll() is not None:
                    remaining = buffer.strip()
                    if remaining:
                        pending_batch.append(remaining)
                    flush_batch()

                    exit_code = process.poll()
                    status_icon = "✅" if exit_code == 0 else "❌"
                    status_text = "انتهى بنجاح" if exit_code == 0 else f"توقف بكود خطأ: {exit_code}"

                    try:
                        bot.send_message(
                            chat_id,
                            f"{status_icon} <b>الملف {status_text}</b>\n"
                            f"🆔 <code>{file_id}</code>\n"
                            f"📊 عدد الأسطر المعروضة: {shown_lines}",
                            parse_mode='HTML'
                        )
                    except Exception:
                        pass
                    break

                if pending_batch and (time.time() - last_flush) > 1.5:
                    flush_batch()
                time.sleep(0.03)
                continue

            try:
                decoded = ch.decode('utf-8', errors='replace')
            except Exception:
                continue

            buffer += decoded
            flush = ('\n' in decoded) or (decoded in PROMPT_END and len(buffer.strip()) >= 4)

            if flush:
                line = buffer.strip()
                buffer = ""

                if not line or len(line) < 1:
                    continue

                if looks_prompt(line):
                    flush_batch()
                    pending_inputs[chat_id] = file_id
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton(
                        "❌ إلغاء الطلب",
                        callback_data=f'ci_{file_id}'
                    ))
                    try:
                        bot.send_message(
                            chat_id,
                            f"📨 <b>الملف يطلب إدخال:</b>\n\n"
                            f"<code>{eh(line[:800])}</code>\n\n"
                            f"✍️ أرسل الإجابة الآن:",
                            reply_markup=markup,
                            parse_mode='HTML'
                        )
                    except Exception as e:
                        logging.error(f"send prompt: {e}")
                else:
                    if shown_lines < MAX_SHOWN:
                        pending_batch.append(line)
                        shown_lines += 1
                    if (time.time() - last_flush) > 1.5 or len(pending_batch) >= 15:
                        flush_batch()

    except Exception as e:
        logging.error(f"monitor error [{chat_id}/{file_id}]: {e}")
    finally:
        if pending_inputs.get(chat_id) == file_id:
            pending_inputs.pop(chat_id, None)


def stop_one(chat_id, file_id, delete=False):
    if chat_id not in active_processes or file_id not in active_processes[chat_id]:
        return False

    info = active_processes[chat_id][file_id]
    proc = info.get('process')

    if proc and proc.poll() is None:
        try:
            proc.stdin.close()
        except Exception:
            pass
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        except Exception as e:
            logging.error(f"stop error: {e}")

    if pending_inputs.get(chat_id) == file_id:
        pending_inputs.pop(chat_id, None)

    if delete and info.get('path') and os.path.exists(info['path']):
        try:
            os.remove(info['path'])
        except Exception:
            pass
        active_processes[chat_id].pop(file_id, None)

    return True


def scan_file(path, uid):
    if is_admin(uid):
        return False, ""
    try:
        with open(path, 'rb') as f:
            content = f.read().decode('utf-8', errors='ignore')
        patterns = [r"rm\s+-rf\s+/", r"import\s+marshal"]
        for p in patterns:
            if re.search(p, content, re.IGNORECASE):
                return True, f"نمط مشبوه: {p}"
        return False, ""
    except Exception:
        return False, ""


# ============================================================
# /start
# ============================================================
@bot.message_handler(commands=['start'])
def cmd_start(message):
    uid = message.from_user.id

    if not bot_running:
        try:
            bot.send_message(message.chat.id, "⏸️ البوت متوقف مؤقتاً.")
        except Exception:
            pass
        return

    if is_approved(uid):
        show_menu(message)
    elif is_pending(uid):
        try:
            bot.send_message(message.chat.id, "⏳ طلبك قيد المراجعة.")
        except Exception:
            pass
    else:
        fname = eh(message.from_user.first_name or 'مستخدم')
        uname = message.from_user.username or 'بدون_يوزر'
        add_pending(uid, message.from_user.first_name or 'مستخدم', uname)

        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("✅ قبول", callback_data=f'ap_{uid}'),
            types.InlineKeyboardButton("❌ رفض", callback_data=f'rj_{uid}')
        )

        try:
            bot.send_message(
                ADMIN_ID,
                f"📋 <b>طلب اشتراك جديد:</b>\n\n"
                f"👤 {fname}\n"
                f"🆔 <code>{uid}</code>\n"
                f"📌 @{eh(uname)}",
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logging.error(f"send to admin: {e}")

        try:
            bot.send_message(message.chat.id, "⏳ تم إرسال طلبك للأدمن.")
        except Exception:
            pass


def show_menu(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🛡️ الحماية", callback_data='protection'),
        types.InlineKeyboardButton("📥 رفع ملف", callback_data='upload')
    )
    markup.add(
        types.InlineKeyboardButton("📂 ملفاتي", callback_data='my_files'),
        types.InlineKeyboardButton("👩‍💼 فتاة المحاور", callback_data='support_girl')
    )
    markup.add(
        types.InlineKeyboardButton("🚀 السرعة", callback_data='speed'),
        types.InlineKeyboardButton("ℹ️ حول البوت", callback_data='about')
    )
    markup.add(
        types.InlineKeyboardButton("🛠️ الدعم الفني", callback_data='tech_support'),
        types.InlineKeyboardButton("📚 تثبيت مكتبة", callback_data='install_lib')
    )
    markup.add(types.InlineKeyboardButton("📞 التواصل مع الدعم", callback_data='support'))

    if is_admin(message.from_user.id):
        markup.add(
            types.InlineKeyboardButton("👥 المستخدمون", callback_data='users'),
            types.InlineKeyboardButton("⚡ حالة البوت", callback_data='bot_status')
        )

    fname = eh(message.from_user.first_name or '')
    try:
        bot.send_message(
            message.chat.id,
            f"🐍 <b>Python Hosting</b>\n\n"
            f"مرحباً، {fname}! ✨\n\n"
            f"👨‍💻 المطور: {YOUR_USERNAME}\n"
            f"📢 القناة: {ADMIN_CHANNEL}\n\n"
            f"✅ يدعم Telethon / Pyrogram / Aiogram\n"
            f"📂 تشغيل عدة ملفات متزامنة\n"
            f"📨 تفاعل ذكي مع الرقم / OTP / 2FA\n\n"
            f"اختر الخدمة:",
            reply_markup=markup,
            parse_mode='HTML'
        )
    except Exception as e:
        logging.error(f"show_menu: {e}")


# ============================================================
# معالج إدخال المستخدم (أعلى أولوية)
# ============================================================
@bot.message_handler(
    func=lambda m: (
        m.chat.id in pending_inputs
        and m.content_type == 'text'
        and not (m.text or '').startswith('/')
    )
)
def handle_input(message):
    chat_id = message.chat.id
    file_id = pending_inputs.get(chat_id)
    if not file_id:
        return
    if chat_id not in active_processes or file_id not in active_processes[chat_id]:
        pending_inputs.pop(chat_id, None)
        return

    proc = active_processes[chat_id][file_id].get('process')
    if not proc or proc.poll() is not None:
        pending_inputs.pop(chat_id, None)
        try:
            bot.reply_to(message, "❌ الملف لم يعد يعمل.")
        except Exception:
            pass
        return

    user_input = message.text.strip()
    try:
        proc.stdin.write((user_input + "\n").encode('utf-8'))
        proc.stdin.flush()

        masked = (user_input[:3] + "*" * (len(user_input) - 6) + user_input[-3:]) \
            if len(user_input) > 8 else \
            (user_input[:2] + "*" * max(0, len(user_input) - 2))

        try:
            bot.reply_to(message, f"✅ تم إرسال: <code>{eh(masked)}</code>\n⏳ جارٍ المتابعة...",
                         parse_mode='HTML')
        except Exception:
            pass

        pending_inputs.pop(chat_id, None)
    except Exception as e:
        try:
            bot.reply_to(message, f"❌ فشل: {eh(str(e))}", parse_mode='HTML')
        except Exception:
            pass


# ============================================================
# تثبيت مكتبة
# ============================================================
@bot.message_handler(
    func=lambda m: m.chat.id in waiting_library and m.content_type == 'text'
)
def handle_library_name(message):
    chat_id = message.chat.id
    waiting_library.discard(chat_id)

    lib_name = (message.text or '').strip()
    if not re.match(r'^[a-zA-Z0-9_\-\.]+(\s*[<>=!]+\s*[0-9a-zA-Z\.\-]+)?$', lib_name):
        try:
            bot.send_message(chat_id, "❌ اسم غير صالح.")
        except Exception:
            pass
        return

    try:
        bot.send_message(chat_id, f"⏳ جاري تثبيت <code>{eh(lib_name)}</code>...", parse_mode='HTML')
    except Exception:
        pass

    def install():
        try:
            r = subprocess.run(
                [sys.executable, "-m", "pip", "install", lib_name],
                capture_output=True, text=True, timeout=300
            )
            if r.returncode == 0:
                msg = f"✅ تم تثبيت <code>{eh(lib_name)}</code> بنجاح"
            else:
                msg = f"❌ فشل:\n<pre>{eh(r.stderr[:500])}</pre>"
        except Exception as e:
            msg = f"❌ خطأ: {eh(str(e))}"
        try:
            bot.send_message(chat_id, msg, parse_mode='HTML')
        except Exception:
            pass

    executor.submit(install)


# ============================================================
# رفع الملفات
# ============================================================
@bot.message_handler(content_types=['document'])
def handle_doc(message):
    uid = message.from_user.id

    if not is_approved(uid):
        try:
            bot.reply_to(message, "❌ غير مصرح")
        except Exception:
            pass
        return

    if not bot_running:
        try:
            bot.reply_to(message, "⏸️ البوت متوقف.")
        except Exception:
            pass
        return

    if message.chat.id in waiting_library:
        waiting_library.discard(message.chat.id)

    try:
        chat_id = message.chat.id
        doc = message.document
        file_name = doc.file_name or f"script_{uuid.uuid4().hex[:6]}.py"

        if not file_name.endswith('.py'):
            try:
                bot.reply_to(message, "❌ فقط ملفات .py مسموحة")
            except Exception:
                pass
            return

        if doc.file_size and doc.file_size > MAX_FILE_SIZE:
            try:
                bot.reply_to(message, f"⛔ الحجم يتجاوز {MAX_FILE_SIZE // (1024*1024)}MB")
            except Exception:
                pass
            return

        file_info = bot.get_file(doc.file_id)
        downloaded = bot.download_file(file_info.file_path)

        file_id = uuid.uuid4().hex[:8]
        user_dir = os.path.join(UPLOADED_FILES_DIR, str(uid))
        os.makedirs(user_dir, exist_ok=True)

        # ✅ إصلاح: مسار مطلق
        save_path = os.path.abspath(os.path.join(user_dir, f"{file_id}_{file_name}"))

        with open(save_path, 'wb') as f:
            f.write(downloaded)

        logging.info(f"💾 تم حفظ الملف في: {save_path}")
        logging.info(f"📊 حجم الملف: {len(downloaded)} bytes")

        if protection_enabled:
            bad, reason = scan_file(save_path, uid)
            if bad:
                try:
                    os.remove(save_path)
                except Exception:
                    pass
                try:
                    bot.reply_to(message, f"⛔ {eh(reason)}", parse_mode='HTML')
                except Exception:
                    pass
                return

        if chat_id not in active_processes:
            active_processes[chat_id] = {}

        active_processes[chat_id][file_id] = {
            'name': file_name,
            'path': save_path,
            'process': None,
            'started_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        total = len(active_processes[chat_id])
        start_file(save_path, chat_id, file_id)

        try:
            bot.send_message(chat_id, f"📊 مجموع ملفاتك: <code>{total}</code>", parse_mode='HTML')
        except Exception:
            pass

    except Exception as e:
        logging.error(f"handle_doc: {e}")
        try:
            bot.reply_to(message, f"❌ خطأ: {eh(str(e))}", parse_mode='HTML')
        except Exception:
            pass


# ============================================================
# أزرار الملفات
# ============================================================
@bot.callback_query_handler(func=lambda c: c.data.startswith('sf_'))
def cb_stop(call):
    fid = call.data.replace('sf_', '')
    cid = call.message.chat.id
    if cid not in active_processes or fid not in active_processes[cid]:
        bot.answer_callback_query(call.id, "❌")
        return
    stop_one(cid, fid, delete=False)
    bot.answer_callback_query(call.id, "✅ تم الإيقاف")
    show_files(call, edit=True)


@bot.callback_query_handler(func=lambda c: c.data.startswith('rf_'))
def cb_restart(call):
    fid = call.data.replace('rf_', '')
    cid = call.message.chat.id
    if cid not in active_processes or fid not in active_processes[cid]:
        bot.answer_callback_query(call.id, "❌")
        return
    info = active_processes[cid][fid]
    stop_one(cid, fid, delete=False)
    time.sleep(0.3)
    start_file(info['path'], cid, fid)
    bot.answer_callback_query(call.id, "🔄")


@bot.callback_query_handler(func=lambda c: c.data.startswith('df_'))
def cb_delete(call):
    fid = call.data.replace('df_', '')
    cid = call.message.chat.id
    if cid not in active_processes or fid not in active_processes[cid]:
        bot.answer_callback_query(call.id, "❌")
        return
    stop_one(cid, fid, delete=True)
    bot.answer_callback_query(call.id, "🗑️")
    show_files(call, edit=True)


@bot.callback_query_handler(func=lambda c: c.data.startswith('ci_'))
def cb_cancel_input(call):
    pending_inputs.pop(call.message.chat.id, None)
    bot.answer_callback_query(call.id, "✅")
    try:
        bot.edit_message_text("🚫 تم الإلغاء.", call.message.chat.id, call.message.message_id)
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data.startswith('nf_'))
def cb_info(call):
    fid = call.data.replace('nf_', '')
    cid = call.message.chat.id
    if cid not in active_processes or fid not in active_processes[cid]:
        bot.answer_callback_query(call.id, "❌")
        return
    info = active_processes[cid][fid]
    proc = info.get('process')
    status = "🟢 يعمل" if (proc and proc.poll() is None) else "🔴 متوقف"
    pid = proc.pid if (proc and proc.poll() is None) else "—"
    bot.answer_callback_query(
        call.id,
        f"📁 {info['name']}\n{status}\nPID: {pid}\n🆔 {fid}\n⏰ {info.get('started_at', '—')}",
        show_alert=True
    )


@bot.callback_query_handler(func=lambda c: c.data == 'stop_all')
def cb_stop_all(call):
    cid = call.message.chat.id
    if cid not in active_processes:
        bot.answer_callback_query(call.id, "لا ملفات")
        return
    count = 0
    for fid in list(active_processes[cid].keys()):
        if stop_one(cid, fid, delete=False):
            count += 1
    bot.answer_callback_query(call.id, f"🛑 {count}")
    show_files(call, edit=True)


# ============================================================
# قائمة الملفات
# ============================================================
@bot.callback_query_handler(func=lambda c: c.data == 'my_files')
def cb_my_files(call):
    show_files(call, edit=False)


def show_files(call, edit=False):
    cid = call.message.chat.id

    if cid not in active_processes or not active_processes[cid]:
        txt = "📂 لا توجد ملفات."
        if edit:
            try:
                bot.edit_message_text(txt, cid, call.message.message_id)
            except Exception:
                bot.send_message(cid, txt)
        else:
            try:
                bot.send_message(cid, txt)
            except Exception:
                pass
        return

    files = active_processes[cid]
    running = sum(1 for f in files.values() if f.get('process') and f['process'].poll() is None)

    text = f"📂 <b>ملفاتك</b> ({len(files)})\n🟢 {running} | 🔴 {len(files) - running}"

    markup = types.InlineKeyboardMarkup(row_width=4)
    for fid, info in files.items():
        proc = info.get('process')
        icon = "🟢" if (proc and proc.poll() is None) else "🔴"
        name = (info.get('name', 'ملف') or 'ملف')[:20]
        markup.row(
            types.InlineKeyboardButton(f"{icon} {name}", callback_data=f'nf_{fid}'),
            types.InlineKeyboardButton("🔄", callback_data=f'rf_{fid}'),
            types.InlineKeyboardButton("🛑", callback_data=f'sf_{fid}'),
            types.InlineKeyboardButton("🗑️", callback_data=f'df_{fid}')
        )

    markup.row(
        types.InlineKeyboardButton("🛑 إيقاف الكل", callback_data='stop_all'),
        types.InlineKeyboardButton("🔙 القائمة", callback_data='back')
    )

    if edit:
        try:
            bot.edit_message_text(text, cid, call.message.message_id,
                                  reply_markup=markup, parse_mode='HTML')
        except Exception:
            try:
                bot.send_message(cid, text, reply_markup=markup, parse_mode='HTML')
            except Exception:
                pass
    else:
        try:
            bot.send_message(cid, text, reply_markup=markup, parse_mode='HTML')
        except Exception:
            pass


# ============================================================
# باقي الأزرار
# ============================================================
@bot.callback_query_handler(func=lambda c: c.data == 'back')
def cb_back(call):
    bot.answer_callback_query(call.id)
    show_menu(call.message)


@bot.callback_query_handler(func=lambda c: c.data == 'upload')
def cb_upload(call):
    if not is_approved(call.from_user.id):
        bot.answer_callback_query(call.id, "❌")
        return
    bot.answer_callback_query(call.id, "📤")
    try:
        bot.send_message(
            call.message.chat.id,
            "📥 <b>أرسل ملف .py الآن</b>\n\n"
            f"• الحد الأقصى: {MAX_FILE_SIZE // (1024*1024)}MB\n"
            f"• يدعم: Telethon / Pyrogram / Aiogram / telebot\n"
            f"• يعرض كل الإخراج + طلبات الإدخال",
            parse_mode='HTML'
        )
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data == 'speed')
def cb_speed(call):
    bot.answer_callback_query(call.id)
    try:
        msg = bot.send_message(call.message.chat.id, "⏳")
        bot.edit_message_text("🚀 السرعة: ممتازة", call.message.chat.id, msg.message_id)
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data == 'about')
def cb_about(call):
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data='back'))
    try:
        bot.send_message(
            call.message.chat.id,
            f"ℹ️ <b>حول البوت</b>\n\n"
            f"🐍 منصة استضافة Python\n"
            f"📂 تشغيل ملفات متعددة\n"
            f"🤖 يدعم Telethon / Pyrogram / Aiogram\n"
            f"📨 تفاعل ذكي (رقم / OTP / 2FA)\n"
            f"📄 عرض كامل للإخراج + Exit code\n\n"
            f"👨‍💻 {YOUR_USERNAME}\n📢 {ADMIN_CHANNEL}",
            reply_markup=markup, parse_mode='HTML'
        )
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data in ['support', 'tech_support', 'support_girl'])
def cb_support(call):
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("👨‍💼 المطور",
                                           url=f"https://t.me/{YOUR_USERNAME.replace('@', '')}"))
    markup.add(types.InlineKeyboardButton("📢 القناة",
                                           url=f"https://t.me/{ADMIN_CHANNEL.replace('@', '')}"))
    markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data='back'))
    try:
        bot.send_message(call.message.chat.id, f"📞 الدعم: {YOUR_USERNAME}",
                         reply_markup=markup)
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data == 'install_lib')
def cb_install(call):
    if not is_approved(call.from_user.id):
        bot.answer_callback_query(call.id, "❌")
        return
    bot.answer_callback_query(call.id)
    waiting_library.add(call.message.chat.id)
    try:
        bot.send_message(
            call.message.chat.id,
            "📚 أرسل اسم المكتبة:\n"
            "مثال: <code>telethon</code> أو <code>pyrogram</code> أو <code>aiogram</code>",
            parse_mode='HTML'
        )
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data == 'protection')
def cb_protection(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌")
        return
    markup = types.InlineKeyboardMarkup()
    if protection_enabled:
        markup.add(types.InlineKeyboardButton("تعطيل", callback_data='prot_off'))
    else:
        markup.add(types.InlineKeyboardButton("تفعيل", callback_data='prot_on'))
    markup.add(types.InlineKeyboardButton("🔙", callback_data='back'))
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text(
            f"🛡️ الحماية: {'✅' if protection_enabled else '❌'}",
            call.message.chat.id, call.message.message_id, reply_markup=markup
        )
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data in ['prot_on', 'prot_off'])
def cb_prot_toggle(call):
    global protection_enabled
    if not is_admin(call.from_user.id):
        return
    protection_enabled = (call.data == 'prot_on')
    bot.answer_callback_query(call.id, "✅")
    cb_protection(call)


@bot.callback_query_handler(func=lambda c: c.data == 'bot_status')
def cb_bot_status(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌")
        return
    markup = types.InlineKeyboardMarkup()
    if bot_running:
        markup.add(types.InlineKeyboardButton("🛑 إيقاف", callback_data='bot_off'))
    else:
        markup.add(types.InlineKeyboardButton("⚡ تشغيل", callback_data='bot_on'))
    markup.add(types.InlineKeyboardButton("🔙", callback_data='back'))
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text(
            f"⚡ البوت: {'✅ يعمل' if bot_running else '⏸️ متوقف'}",
            call.message.chat.id, call.message.message_id, reply_markup=markup
        )
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data in ['bot_on', 'bot_off'])
def cb_bot_toggle(call):
    global bot_running
    if not is_admin(call.from_user.id):
        return
    bot_running = (call.data == 'bot_on')
    bot.answer_callback_query(call.id, "✅")
    cb_bot_status(call)


# ============================================================
# إدارة المستخدمين
# ============================================================
@bot.callback_query_handler(func=lambda c: c.data == 'users')
def cb_users(call):
    if not is_admin(call.from_user.id):
        return
    a, p = get_stats()
    pending = get_pending()

    markup = types.InlineKeyboardMarkup()
    for uid, fname, uname in pending:
        fn = (fname or 'مستخدم')[:15]
        markup.row(
            types.InlineKeyboardButton(f"✅ {fn}", callback_data=f'ap_{uid}'),
            types.InlineKeyboardButton(f"❌ {fn}", callback_data=f'rj_{uid}')
        )
    markup.add(types.InlineKeyboardButton("🔙", callback_data='back'))

    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text(
            f"👥 المعتمدون: {a}\n⏳ الانتظار: {p}",
            call.message.chat.id, call.message.message_id,
            reply_markup=markup
        )
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data.startswith('ap_'))
def cb_approve(call):
    if not is_admin(call.from_user.id):
        return
    uid = int(call.data.split('_')[1])
    add_approved(uid, 'USER')
    bot.answer_callback_query(call.id, "✅")
    try:
        bot.send_message(uid, "🎉 تمت الموافقة! أرسل /start")
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data.startswith('rj_'))
def cb_reject(call):
    if not is_admin(call.from_user.id):
        return
    uid = int(call.data.split('_')[1])
    remove_pending(uid)
    bot.answer_callback_query(call.id, "❌")


# ============================================================
# أمر البث
# ============================================================
@bot.message_handler(commands=['rck'])
def cmd_broadcast(message):
    if not is_admin(message.from_user.id):
        return
    try:
        msg = message.text.split(' ', 1)[1]
        with sqlite3.connect('bot_data.db') as conn:
            c = conn.cursor()
            c.execute('SELECT user_id FROM approved_users')
            users = [r[0] for r in c.fetchall()]
        ok, fail = 0, 0
        for uid in users:
            try:
                bot.send_message(uid, msg)
                ok += 1
            except Exception:
                fail += 1
        bot.send_message(message.chat.id, f"📊 نجح: {ok}, فشل: {fail}")
    except Exception:
        bot.send_message(message.chat.id, "❌ استخدم: /rck الرسالة")


# ============================================================
# التشغيل
# ============================================================
if __name__ == '__main__':
    logging.info("=" * 55)
    logging.info("🤖 Bot starting...")
    logging.info(f"👨‍💻 Admin: {ADMIN_ID}")
    logging.info(f"📢 Channel: {ADMIN_CHANNEL}")
    logging.info(f"📁 BASE_DIR: {BASE_DIR}")
    logging.info(f"📁 UPLOADS: {UPLOADED_FILES_DIR}")
    logging.info("=" * 55)

    while True:
        try:
            bot.polling(none_stop=True, interval=1, timeout=60)
        except Exception as err:
            logging.error(f"Polling error: {err}")
            time.sleep(3)
