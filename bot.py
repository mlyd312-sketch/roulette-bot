import sys
import os
import re
import time
import uuid
import shutil
import sqlite3
import logging
import signal
import atexit
import threading
import subprocess
import tempfile
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import telebot
from telebot import types

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
BOT_TOKEN = '8877293036:AAGg_82F0bT1Bhov42sk9qDcRMsVNpfnErw'
ADMIN_ID = 1920665874
YOUR_USERNAME = '@u_8_y'
ADMIN_CHANNEL = '@FD_CQ'

UPLOADED_FILES_DIR = "uploaded_files"
MAX_FILE_SIZE = 10 * 1024 * 1024

# ✅ threaded=True + num_threads للأداء
bot = telebot.TeleBot(BOT_TOKEN, threaded=True, num_threads=10)
executor = ThreadPoolExecutor(max_workers=10)
lock = threading.Lock()

protection_enabled = True
bot_running = True

os.makedirs(UPLOADED_FILES_DIR, exist_ok=True)

# ============================================================
# قاموس الإيموجيات المميزة
# ============================================================
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


def safe_send(chat_id, text, **kwargs):
    try:
        return bot.send_message(chat_id, text, **kwargs)
    except Exception as e:
        logging.error(f"send error [{chat_id}]: {e}")
        return None


def safe_edit(chat_id, message_id, text, **kwargs):
    try:
        return bot.edit_message_text(text, chat_id, message_id, **kwargs)
    except Exception as e:
        logging.error(f"edit error: {e}")
        return None


def safe_answer(call_id, text=None, **kwargs):
    try:
        return bot.answer_callback_query(call_id, text, **kwargs)
    except Exception as e:
        logging.error(f"answer error: {e}")
        return None


# ============================================================
# قاعدة البيانات
# ============================================================
def init_db():
    with sqlite3.connect('bot_data.db', timeout=15) as conn:
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
    try:
        with sqlite3.connect('bot_data.db', timeout=15) as conn:
            c = conn.cursor()
            c.execute('SELECT user_id FROM approved_users WHERE user_id = ?', (uid,))
            return c.fetchone() is not None
    except:
        return False


def is_pending(uid):
    try:
        with sqlite3.connect('bot_data.db', timeout=15) as conn:
            c = conn.cursor()
            c.execute('SELECT user_id FROM pending_requests WHERE user_id = ?', (uid,))
            return c.fetchone() is not None
    except:
        return False


def add_approved(uid, username):
    try:
        with sqlite3.connect('bot_data.db', timeout=15) as conn:
            c = conn.cursor()
            c.execute('INSERT OR REPLACE INTO approved_users (user_id, username) VALUES (?, ?)', (uid, username))
            c.execute('DELETE FROM pending_requests WHERE user_id = ?', (uid,))
            conn.commit()
    except:
        pass


def add_pending(uid, fname, username):
    try:
        with sqlite3.connect('bot_data.db', timeout=15) as conn:
            c = conn.cursor()
            c.execute('INSERT OR REPLACE INTO pending_requests (user_id, first_name, username) VALUES (?, ?, ?)',
                      (uid, fname, username))
            conn.commit()
    except:
        pass


def remove_pending(uid):
    try:
        with sqlite3.connect('bot_data.db', timeout=15) as conn:
            c = conn.cursor()
            c.execute('DELETE FROM pending_requests WHERE user_id = ?', (uid,))
            conn.commit()
    except:
        pass


def get_pending():
    try:
        with sqlite3.connect('bot_data.db', timeout=15) as conn:
            c = conn.cursor()
            c.execute('SELECT user_id, first_name, username FROM pending_requests')
            return c.fetchall()
    except:
        return []


def get_stats():
    try:
        with sqlite3.connect('bot_data.db', timeout=15) as conn:
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM approved_users')
            a = c.fetchone()[0]
            c.execute('SELECT COUNT(*) FROM pending_requests')
            p = c.fetchone()[0]
            return a, p
    except:
        return 0, 0


# ============================================================
# متغيرات عامة
# ============================================================
# {chat_id: {file_id: {name, path, process, started_at}}}
active_processes = {}
pending_inputs = {}
waiting_library = set()
last_prompt_sent = {}
last_error_sent = {}


# ============================================================
# كلمات مفتاحية لطلبات الإدخال
# ============================================================
INPUT_KEYWORDS = [
    'أرسل', 'ارسل', 'ادخل', 'أدخل', 'اكتب', 'رقم', 'كود', 'رمز',
    'otp', 'phone', 'code', 'password', 'pass', '2fa',
    'كلمة السر', 'كلمة سر', 'التحقق', 'الهاتف', 'هاتف',
    'input', 'enter', 'token', 'session', 'api_id', 'api_hash',
    'bot_token', 'user', 'username', 'auth', 'key', 'verify',
    'number', 'account', 'login', 'sign', 'pin', 'secret'
]
PROMPT_END = ('؟', '?', ':', '!', '؛', '،')


def looks_prompt(text):
    if not text or len(text.strip()) < 3:
        return False
    t = text.lower()
    return any(kw.lower() in t for kw in INPUT_KEYWORDS)


def looks_like_error(text):
    if not text:
        return False
    t = text.lower()
    errs = ['error', 'traceback', 'exception', 'failed',
            '429', 'too many', 'floodwait', 'flood wait',
            'retry after', 'connectionerror', 'timeout',
            'unauthorized', 'forbidden', 'importerror',
            'syntaxerror', 'raise ']
    return any(e in t for e in errs)


# ============================================================
# تشغيل/إيقاف/مراقبة الملفات
# ============================================================
def start_file(script_path, chat_id, file_id):
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
        info['path'] = script_path

        proc = info.get('process')
        if proc and proc.poll() is None:
            safe_send(chat_id, "⚠️ الملف يعمل بالفعل.")
            return

        if not os.path.exists(script_path):
            safe_send(chat_id, f"❌ الملف غير موجود:\n<code>{eh(script_path)}</code>",
                      parse_mode='HTML')
            return

        try:
            work_dir = os.path.dirname(script_path)
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            env['PYTHONIOENCODING'] = 'utf-8'

            # ✅ نستخدم start_new_session=True لعزل العمليات
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

            safe_send(
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
            safe_send(chat_id, f"❌ فشل: {eh(str(e))}", parse_mode='HTML')


def monitor_output(chat_id, file_id, process):
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
            safe_send(chat_id, f"📄 <b>إخراج الملف:</b>\n<pre>{eh(text[:3500])}</pre>",
                      parse_mode='HTML')
        except:
            pass
        last_flush = time.time()

    try:
        while True:
            try:
                ch = process.stdout.read(1)
            except:
                break

            if not ch:
                if process.poll() is not None:
                    remaining = buffer.strip()
                    if remaining:
                        pending_batch.append(remaining)
                    flush_batch()

                    exit_code = process.poll()
                    icon = "✅" if exit_code == 0 else "❌"
                    txt = "انتهى بنجاح" if exit_code == 0 else f"توقف بكود: {exit_code}"
                    safe_send(chat_id,
                              f"{icon} <b>الملف {txt}</b>\n🆔 <code>{file_id}</code>",
                              parse_mode='HTML')
                    break

                if pending_batch and (time.time() - last_flush) > 1.5:
                    flush_batch()
                time.sleep(0.03)
                continue

            try:
                decoded = ch.decode('utf-8', errors='replace')
            except:
                continue

            buffer += decoded
            flush = ('\n' in decoded) or (decoded in PROMPT_END and len(buffer.strip()) >= 4)

            if flush:
                line = buffer.strip()
                buffer = ""

                if not line or len(line) < 1:
                    continue

                if looks_like_error(line):
                    prev_text, prev_time = last_error_sent.get(file_id, ("", 0))
                    now = time.time()
                    if line != prev_text or (now - prev_time) > 120:
                        last_error_sent[file_id] = (line, now)
                        safe_send(chat_id,
                                  f"⚠️ <b>خطأ في الملف:</b>\n<pre>{eh(line[:800])}</pre>",
                                  parse_mode='HTML')
                elif looks_prompt(line):
                    prev_text, prev_time = last_prompt_sent.get(file_id, ("", 0))
                    now = time.time()
                    if line != prev_text or (now - prev_time) > 30:
                        last_prompt_sent[file_id] = (line, now)
                        pending_inputs[chat_id] = file_id

                        markup = types.InlineKeyboardMarkup()
                        markup.add(types.InlineKeyboardButton(
                            "❌ إلغاء الطلب",
                            callback_data=f'ci_{file_id}'
                        ))
                        safe_send(chat_id,
                                  f"📨 <b>الملف يطلب إدخال:</b>\n\n"
                                  f"<code>{eh(line[:800])}</code>\n\n"
                                  f"✍️ أرسل الإجابة الآن:",
                                  reply_markup=markup,
                                  parse_mode='HTML')
                else:
                    if shown_lines < MAX_SHOWN:
                        pending_batch.append(line)
                        shown_lines += 1
                    if (time.time() - last_flush) > 1.5 or len(pending_batch) >= 15:
                        flush_batch()

    except Exception as e:
        logging.error(f"monitor error: {e}")
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
        except:
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
        except:
            pass
        active_processes[chat_id].pop(file_id, None)

    return True


def stop_all_for_chat(chat_id):
    if chat_id not in active_processes:
        return 0
    count = 0
    for fid in list(active_processes[chat_id].keys()):
        if stop_one(chat_id, fid, delete=False):
            count += 1
    return count


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
    except:
        return False, ""


# ============================================================
# قائمة الملفات
# ============================================================
def show_my_files(call, edit=False):
    chat_id = call.message.chat.id

    if chat_id not in active_processes or not active_processes[chat_id]:
        txt = "📂 لا توجد ملفات."
        if edit:
            safe_edit(chat_id, call.message.message_id, txt)
        else:
            safe_send(chat_id, txt)
        return

    files = active_processes[chat_id]
    running = sum(1 for f in files.values()
                  if f.get('process') and f['process'].poll() is None)

    text = (f"📂 <b>ملفاتك</b> ({len(files)})\n"
            f"🟢 يعمل: {running} | 🔴 متوقف: {len(files) - running}")

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
        types.InlineKeyboardButton("🔙 القائمة", callback_data='back_to_main')
    )

    if edit:
        res = safe_edit(chat_id, call.message.message_id, text,
                        reply_markup=markup, parse_mode='HTML')
        if not res:
            safe_send(chat_id, text, reply_markup=markup, parse_mode='HTML')
    else:
        safe_send(chat_id, text, reply_markup=markup, parse_mode='HTML')


# ============================================================
# القائمة الرئيسية
# ============================================================
def show_main_menu(message):
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

    safe_send(
        message.chat.id,
        f"🐍 <b>Python Hosting</b>\n\n"
        f"مرحباً، {eh(message.from_user.first_name or '')}! ✨\n\n"
        f"👨‍💻 المطور: {YOUR_USERNAME}\n"
        f"📢 القناة: {ADMIN_CHANNEL}\n\n"
        f"✅ يدعم Telethon / Pyrogram / Aiogram / telebot\n"
        f"📂 تشغيل عدة ملفات متزامنة\n"
        f"📨 تفاعل ذكي مع الرقم / OTP / 2FA\n\n"
        f"اختر الخدمة:",
        reply_markup=markup,
        parse_mode='HTML'
    )


# ============================================================
# Handlers
# ============================================================
@bot.message_handler(commands=['start'], chat_types=['private'])
def cmd_start(message):
    uid = message.from_user.id

    if not bot_running:
        safe_send(message.chat.id, "⏸️ البوت متوقف مؤقتاً.")
        return

    if message.from_user.username in banned_users if 'banned_users' in dir() else False:
        pass

    if is_approved(uid):
        show_main_menu(message)
    elif is_pending(uid):
        safe_send(message.chat.id, "⏳ طلبك قيد المراجعة.")
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
            logging.error(f"send admin: {e}")

        safe_send(message.chat.id, "⏳ تم إرسال طلبك للأدمن.")


# ============================================================
# معالج إدخال الملفات (أعلى أولوية)
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
        safe_send(chat_id, "❌ الملف لم يعد يعمل.")
        return

    user_input = (message.text or '').strip()
    try:
        proc.stdin.write((user_input + "\n").encode('utf-8'))
        proc.stdin.flush()

        if len(user_input) > 8:
            masked = user_input[:3] + "*" * (len(user_input) - 6) + user_input[-3:]
        else:
            masked = user_input[:2] + "*" * max(0, len(user_input) - 2)

        safe_send(chat_id, f"✅ تم إرسال: <code>{eh(masked)}</code>\n⏳ جارٍ المتابعة...",
                  parse_mode='HTML')
        pending_inputs.pop(chat_id, None)
    except Exception as e:
        safe_send(chat_id, f"❌ فشل: {eh(str(e))}", parse_mode='HTML')


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
        safe_send(chat_id, "❌ اسم غير صالح.")
        return

    safe_send(chat_id, f"⏳ جاري تثبيت <code>{eh(lib_name)}</code>...", parse_mode='HTML')

    def install():
        try:
            r = subprocess.run(
                [sys.executable, "-m", "pip", "install", lib_name],
                capture_output=True, text=True, timeout=300
            )
            if r.returncode == 0:
                msg = f"✅ تم تثبيت <code>{eh(lib_name)}</code>"
            else:
                msg = f"❌ فشل:\n<pre>{eh(r.stderr[:500])}</pre>"
        except Exception as e:
            msg = f"❌ خطأ: {eh(str(e))}"
        safe_send(chat_id, msg, parse_mode='HTML')

    executor.submit(install)


# ============================================================
# رفع الملفات
# ============================================================
@bot.message_handler(content_types=['document'])
def handle_doc(message):
    uid = message.from_user.id

    if not is_approved(uid):
        safe_send(message.chat.id, "❌ غير مصرح")
        return

    if not bot_running:
        safe_send(message.chat.id, "⏸️ البوت متوقف.")
        return

    if message.chat.id in waiting_library:
        waiting_library.discard(message.chat.id)

    try:
        chat_id = message.chat.id
        doc = message.document
        file_name = doc.file_name or f"script_{uuid.uuid4().hex[:6]}.py"

        if not file_name.endswith('.py'):
            safe_send(chat_id, "❌ فقط ملفات .py")
            return

        if doc.file_size and doc.file_size > MAX_FILE_SIZE:
            safe_send(chat_id, f"⛔ الحجم > {MAX_FILE_SIZE // (1024*1024)}MB")
            return

        file_info = bot.get_file(doc.file_id)
        downloaded = bot.download_file(file_info.file_path)

        file_id = uuid.uuid4().hex[:8]
        user_dir = os.path.join(UPLOADED_FILES_DIR, str(uid))
        os.makedirs(user_dir, exist_ok=True)

        save_path = os.path.abspath(os.path.join(user_dir, f"{file_id}_{file_name}"))

        with open(save_path, 'wb') as f:
            f.write(downloaded)

        if protection_enabled:
            bad, reason = scan_file(save_path, uid)
            if bad:
                try:
                    os.remove(save_path)
                except:
                    pass
                safe_send(chat_id, f"⛔ {eh(reason)}", parse_mode='HTML')
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

        safe_send(chat_id, f"📊 مجموع ملفاتك: <code>{total}</code>", parse_mode='HTML')

    except Exception as e:
        logging.error(f"handle_doc: {e}")
        safe_send(message.chat.id, f"❌ خطأ: {eh(str(e))}", parse_mode='HTML')


# ============================================================
# أزرار الملفات
# ============================================================
@bot.callback_query_handler(func=lambda c: c.data.startswith('sf_'))
def cb_stop(call):
    fid = call.data.replace('sf_', '')
    cid = call.message.chat.id
    if cid not in active_processes or fid not in active_processes[cid]:
        safe_answer(call.id, "❌")
        return
    stop_one(cid, fid, delete=False)
    safe_answer(call.id, "✅ تم الإيقاف")
    show_my_files(call, edit=True)


@bot.callback_query_handler(func=lambda c: c.data.startswith('rf_'))
def cb_restart(call):
    fid = call.data.replace('rf_', '')
    cid = call.message.chat.id
    if cid not in active_processes or fid not in active_processes[cid]:
        safe_answer(call.id, "❌")
        return
    info = active_processes[cid][fid]
    stop_one(cid, fid, delete=False)
    time.sleep(0.3)
    start_file(info['path'], cid, fid)
    safe_answer(call.id, "🔄")


@bot.callback_query_handler(func=lambda c: c.data.startswith('df_'))
def cb_delete(call):
    fid = call.data.replace('df_', '')
    cid = call.message.chat.id
    if cid not in active_processes or fid not in active_processes[cid]:
        safe_answer(call.id, "❌")
        return
    stop_one(cid, fid, delete=True)
    safe_answer(call.id, "🗑️")
    show_my_files(call, edit=True)


@bot.callback_query_handler(func=lambda c: c.data.startswith('ci_'))
def cb_cancel_input(call):
    pending_inputs.pop(call.message.chat.id, None)
    safe_answer(call.id, "✅")
    safe_edit(call.message.chat.id, call.message.message_id, "🚫 تم الإلغاء.")


@bot.callback_query_handler(func=lambda c: c.data.startswith('nf_'))
def cb_info(call):
    fid = call.data.replace('nf_', '')
    cid = call.message.chat.id
    if cid not in active_processes or fid not in active_processes[cid]:
        safe_answer(call.id, "❌")
        return
    info = active_processes[cid][fid]
    proc = info.get('process')
    status = "🟢 يعمل" if (proc and proc.poll() is None) else "🔴 متوقف"
    pid = proc.pid if (proc and proc.poll() is None) else "—"
    safe_answer(call.id,
                f"📁 {info['name']}\n{status}\nPID: {pid}\n🆔 {fid}",
                show_alert=True)


@bot.callback_query_handler(func=lambda c: c.data == 'stop_all')
def cb_stop_all(call):
    cid = call.message.chat.id
    if cid not in active_processes:
        safe_answer(call.id, "لا ملفات")
        return
    count = 0
    for fid in list(active_processes[cid].keys()):
        if stop_one(cid, fid, delete=False):
            count += 1
    safe_answer(call.id, f"🛑 {count}")
    show_my_files(call, edit=True)


# ============================================================
# القوائم والأزرار
# ============================================================
@bot.callback_query_handler(func=lambda c: c.data == 'my_files')
def cb_my_files(call):
    show_my_files(call, edit=False)


@bot.callback_query_handler(func=lambda c: c.data == 'back_to_main')
def cb_back(call):
    safe_answer(call.id)
    show_main_menu(call.message)


@bot.callback_query_handler(func=lambda c: c.data == 'upload')
def cb_upload(call):
    if not is_approved(call.from_user.id):
        safe_answer(call.id, "❌")
        return
    safe_answer(call.id, "📤")
    safe_send(call.message.chat.id,
              "📥 <b>أرسل ملف .py الآن</b>",
              parse_mode='HTML')


@bot.callback_query_handler(func=lambda c: c.data == 'speed')
def cb_speed(call):
    safe_answer(call.id)
    msg = safe_send(call.message.chat.id, "⏳")
    if msg:
        safe_edit(call.message.chat.id, msg.message_id, "🚀 السرعة: ممتازة")


@bot.callback_query_handler(func=lambda c: c.data == 'about')
def cb_about(call):
    safe_answer(call.id)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data='back_to_main'))
    safe_send(call.message.chat.id,
              f"ℹ️ <b>حول البوت</b>\n\n"
              f"🐍 منصة استضافة Python\n"
              f"📂 دعم ملفات متعددة\n"
              f"📞 تفاعل ذكي (رقم/OTP)\n\n"
              f"👨‍💻 {YOUR_USERNAME}\n📢 {ADMIN_CHANNEL}",
              reply_markup=markup, parse_mode='HTML')


@bot.callback_query_handler(func=lambda c: c.data in ['support', 'tech_support', 'support_girl'])
def cb_support(call):
    safe_answer(call.id)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("👨‍💼 المطور",
                                           url=f"https://t.me/{YOUR_USERNAME.replace('@', '')}"))
    markup.add(types.InlineKeyboardButton("📢 القناة",
                                           url=f"https://t.me/{ADMIN_CHANNEL.replace('@', '')}"))
    markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data='back_to_main'))
    safe_send(call.message.chat.id, f"📞 الدعم: {YOUR_USERNAME}", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data == 'install_lib')
def cb_install(call):
    if not is_approved(call.from_user.id):
        safe_answer(call.id, "❌")
        return
    safe_answer(call.id)
    waiting_library.add(call.message.chat.id)
    safe_send(call.message.chat.id, "📚 أرسل اسم المكتبة:")


@bot.callback_query_handler(func=lambda c: c.data == 'protection')
def cb_protection(call):
    if not is_admin(call.from_user.id):
        safe_answer(call.id, "❌")
        return
    markup = types.InlineKeyboardMarkup()
    if protection_enabled:
        markup.add(types.InlineKeyboardButton("تعطيل", callback_data='prot_off'))
    else:
        markup.add(types.InlineKeyboardButton("تفعيل", callback_data='prot_on'))
    markup.add(types.InlineKeyboardButton("🔙", callback_data='back_to_main'))
    safe_answer(call.id)
    safe_edit(call.message.chat.id, call.message.message_id,
              f"🛡️ الحماية: {'✅' if protection_enabled else '❌'}",
              reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data in ['prot_on', 'prot_off'])
def cb_prot_toggle(call):
    global protection_enabled
    if not is_admin(call.from_user.id):
        return
    protection_enabled = (call.data == 'prot_on')
    safe_answer(call.id, "✅")
    cb_protection(call)


@bot.callback_query_handler(func=lambda c: c.data == 'bot_status')
def cb_bot_status(call):
    if not is_admin(call.from_user.id):
        safe_answer(call.id, "❌")
        return
    markup = types.InlineKeyboardMarkup()
    if bot_running:
        markup.add(types.InlineKeyboardButton("🛑 إيقاف", callback_data='bot_off'))
    else:
        markup.add(types.InlineKeyboardButton("⚡ تشغيل", callback_data='bot_on'))
    markup.add(types.InlineKeyboardButton("🔙", callback_data='back_to_main'))
    safe_answer(call.id)
    safe_edit(call.message.chat.id, call.message.message_id,
              f"⚡ البوت: {'✅ يعمل' if bot_running else '⏸️ متوقف'}",
              reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data in ['bot_on', 'bot_off'])
def cb_bot_toggle(call):
    global bot_running
    if not is_admin(call.from_user.id):
        return
    bot_running = (call.data == 'bot_on')

    if not bot_running:
        for cid in list(active_processes.keys()):
            stop_all_for_chat(cid)

    safe_answer(call.id, "✅")
    cb_bot_status(call)


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
    markup.add(types.InlineKeyboardButton("🔙", callback_data='back_to_main'))

    safe_answer(call.id)
    safe_edit(call.message.chat.id, call.message.message_id,
              f"👥 المعتمدون: {a}\n⏳ الانتظار: {p}",
              reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith('ap_'))
def cb_approve(call):
    if not is_admin(call.from_user.id):
        return
    uid = int(call.data.split('_')[1])
    add_approved(uid, 'USER')
    safe_answer(call.id, "✅")
    try:
        bot.send_message(uid, "🎉 تمت الموافقة! أرسل /start")
    except:
        pass


@bot.callback_query_handler(func=lambda c: c.data.startswith('rj_'))
def cb_reject(call):
    if not is_admin(call.from_user.id):
        return
    uid = int(call.data.split('_')[1])
    remove_pending(uid)
    safe_answer(call.id, "❌")


# ============================================================
# أمر البث
# ============================================================
@bot.message_handler(commands=['rck'])
def cmd_broadcast(message):
    if not is_admin(message.from_user.id):
        return
    try:
        msg = message.text.split(' ', 1)[1]
        with sqlite3.connect('bot_data.db', timeout=15) as conn:
            c = conn.cursor()
            c.execute('SELECT user_id FROM approved_users')
            users = [r[0] for r in c.fetchall()]
        ok, fail = 0, 0
        for uid in users:
            try:
                bot.send_message(uid, msg)
                ok += 1
            except:
                fail += 1
        safe_send(message.chat.id, f"📊 نجح: {ok}, فشل: {fail}")
    except:
        safe_send(message.chat.id, "❌ استخدم: /rck الرسالة")


# ============================================================
# معالجة أخطاء عامة + handlers إضافية
# ============================================================
@bot.message_handler(content_types=[
    'audio', 'voice', 'video', 'video_note', 'sticker',
    'contact', 'location', 'venue', 'animation', 'poll',
    'photo'
])
def handle_other_content(message):
    """✅ يستقبل أنواع إضافية من الرسائل (للتوافق مع البوتات المتطورة)"""
    # نتجاهل بهدوء — لا نرسل رد
    pass


# ============================================================
# Signal handling + Cleanup
# ============================================================
def cleanup_all_processes():
    print("🧹 تنظيف العمليات...")
    try:
        for chat_id in list(active_processes.keys()):
            for file_id in list(active_processes[chat_id].keys()):
                info = active_processes[chat_id].get(file_id, {})
                proc = info.get('process')
                if proc and proc.poll() is None:
                    try:
                        proc.terminate()
                        proc.wait(timeout=3)
                    except:
                        try:
                            proc.kill()
                        except:
                            pass
        print("✅ تم التنظيف")
    except Exception as e:
        print(f"cleanup error: {e}")


def signal_handler(sig, frame):
    print(f"\n📴 إشارة {sig}")
    cleanup_all_processes()
    sys.exit(0)


atexit.register(cleanup_all_processes)
try:
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
except:
    pass


# ============================================================
# ✅ Global Exception Handler
# ============================================================
def global_exception_handler(exc_type, exc_value, exc_tb):
    import traceback
    logging.error("=" * 55)
    logging.error("EXCEPTION:")
    logging.error("".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
    logging.error("=" * 55)


sys.excepthook = global_exception_handler


# ============================================================
# ✅ التشغيل الرئيسي — مع دعم كل التحديثات
# ============================================================
if __name__ == "__main__":
    print("=" * 55)
    print("🚀 Bot starting...")
    print("=" * 55)

    # ✅ 1) امسح webhook أول شي (حل مشكلة الأزرار)
    print("🧹 مسح webhook...")
    for attempt in range(5):
        try:
            bot.remove_webhook()
            print("✅ تم مسح webhook")
            break
        except Exception as e:
            print(f"⚠️ محاولة {attempt + 1}: {e}")
            time.sleep(2)

    # ✅ 2) امسح التحديثات المتراكمة
    try:
        bot.get_updates(offset=-1, timeout=2)
        print("✅ تم تنظيف التحديثات")
    except Exception as e:
        print(f"⚠️ {e}")

    # ✅ 3) حلقة التشغيل مع كل التحديثات المدعومة
    ALLOWED_UPDATES = [
        "message",
        "edited_message",
        "channel_post",
        "edited_channel_post",
        "inline_query",
        "chosen_inline_result",
        "callback_query",
        "shipping_query",
        "pre_checkout_query",
        "poll",
        "poll_answer",
        "my_chat_member",
        "chat_member",
        "chat_join_request",
        "new_chat_members",
    ]

    restart_count = 0
    while True:
        try:
            restart_count += 1
            print(f"🔄 محاولة تشغيل #{restart_count}")

            bot.infinity_polling(
                timeout=60,
                long_polling_timeout=60,
                skip_pending=False,
                allowed_updates=ALLOWED_UPDATES
            )
        except KeyboardInterrupt:
            print("⏹️ تم الإيقاف")
            cleanup_all_processes()
            break
        except SystemExit:
            break
        except Exception as e:
            logging.error(f"Polling error: {e}")
            import traceback
            logging.error(traceback.format_exc())
            print(f"⚠️ إعادة التشغيل بعد 5 ثواني...")
            time.sleep(5)
