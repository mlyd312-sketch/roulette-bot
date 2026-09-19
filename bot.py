# ============================================================
# الاستيرادات الأساسية
# ============================================================
import sys
import os
import re
import ast
import time
import uuid
import queue
import sqlite3
import logging
import threading
import subprocess
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import telebot
from telebot import types

# ============================================================
# ✅ إعدادات Timeouts (حل مشكلة ReadTimeout والاتصال)
# ============================================================
telebot.apihelper.CONNECT_TIMEOUT = 90
telebot.apihelper.READ_TIMEOUT = 90
telebot.apihelper.RETRY_ON_ERROR = True
telebot.apihelper.MAX_RETRIES = 5

# ضبط إعدادات ترميز النظام
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='ignore')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='ignore')
except Exception:
    pass

# ============================================================
# دوال مساعدة
# ============================================================
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

BASE_DIR = os.path.abspath(os.getcwd())
UPLOADED_FILES_DIR = os.path.join(BASE_DIR, "uploaded_files")

# ✅ حد حجم الملف (5MB)
MAX_FILE_SIZE = 5 * 1024 * 1024

bot = telebot.TeleBot(BOT_TOKEN)
executor = ThreadPoolExecutor(max_workers=10)
lock = threading.Lock()
db_lock = threading.Lock()

protection_enabled = False
bot_running = True

os.makedirs(UPLOADED_FILES_DIR, exist_ok=True)

# ============================================================
# قاعدة البيانات
# ============================================================
def init_db():
    with db_lock:
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
    with db_lock:
        with sqlite3.connect('bot_data.db') as conn:
            c = conn.cursor()
            c.execute('SELECT user_id FROM approved_users WHERE user_id = ?', (uid,))
            return c.fetchone() is not None

def is_pending(uid):
    with db_lock:
        with sqlite3.connect('bot_data.db') as conn:
            c = conn.cursor()
            c.execute('SELECT user_id FROM pending_requests WHERE user_id = ?', (uid,))
            return c.fetchone() is not None

def add_approved(uid, username):
    with db_lock:
        with sqlite3.connect('bot_data.db') as conn:
            c = conn.cursor()
            c.execute('INSERT OR REPLACE INTO approved_users (user_id, username) VALUES (?, ?)',
                      (uid, username))
            c.execute('DELETE FROM pending_requests WHERE user_id = ?', (uid,))
            conn.commit()

def add_pending(uid, fname, username):
    with db_lock:
        with sqlite3.connect('bot_data.db') as conn:
            c = conn.cursor()
            c.execute('INSERT OR REPLACE INTO pending_requests (user_id, first_name, username) VALUES (?, ?, ?)',
                      (uid, fname, username))
            conn.commit()

def remove_pending(uid):
    with db_lock:
        with sqlite3.connect('bot_data.db') as conn:
            c = conn.cursor()
            c.execute('DELETE FROM pending_requests WHERE user_id = ?', (uid,))
            conn.commit()

def get_pending():
    with db_lock:
        with sqlite3.connect('bot_data.db') as conn:
            c = conn.cursor()
            c.execute('SELECT user_id, first_name, username FROM pending_requests')
            return c.fetchall()

def get_stats():
    with db_lock:
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

last_prompt_sent = {}

PROMPT_KEYWORDS = [
    'أرسل رمز', 'ارسل رمز', 'أرسل كود', 'ارسل كود', 'أرسل رقم', 'ارسل رقم',
    'أدخل رمز', 'أدخل كود', 'ادخل الرمز', 'ادخل الكود', 'أدخل رقم', 'ادخل رقم',
    'رقم الهاتف', 'الرجاء إدخال', 'رمز التحقق', 'كود التحقق', 'كلمة سر', 'كلمة المرور',
    'التحقق بخطوتين', 'بخطوتين',
    'enter the phone', 'enter phone', 'phone number',
    'enter code', 'enter the code', 'enter the verification',
    'enter password', 'enter your password',
    'two-step', '2fa', 'verification code',
    'please enter', 'enter your'
]

def looks_prompt(text):
    if not text or len(text.strip()) < 3:
        return False
    t = text.lower()
    return any(kw in t for kw in PROMPT_KEYWORDS)

# ============================================================
# تشغيل الملفات
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
            try:
                bot.send_message(chat_id, "⚠️ الملف يعمل بالفعل.")
            except Exception:
                pass
            return

        if not os.path.exists(script_path):
            try:
                bot.send_message(chat_id, f"❌ الملف غير موجود:\n<code>{eh(script_path)}</code>", parse_mode='HTML')
            except Exception:
                pass
            return

        try:
            work_dir = os.path.dirname(script_path)
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            env['PYTHONIOENCODING'] = 'utf-8'

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
            markup.add(types.InlineKeyboardButton(f"📂 ملفاتي ({len(active_processes[chat_id])})", callback_data='my_files'))

            bot.send_message(
                chat_id,
                f"✅ <b>تم تشغيل الملف بنجاح</b>\n"
                f"📁 <code>{eh(info['name'])}</code>\n"
                f"🆔 <code>{file_id}</code>\n"
                f"PID: <code>{p.pid}</code>\n\n"
                f"⚡ البوت يعمل الآن ويراقب طلبات الكود والتحقق.",
                reply_markup=markup,
                parse_mode='HTML'
            )

            t = threading.Thread(target=monitor_output, args=(chat_id, file_id, p), daemon=True)
            t.start()

        except Exception as e:
            logging.error(f"start_file error: {e}")
            try:
                bot.send_message(chat_id, f"❌ فشل التشغيل: {eh(str(e))}", parse_mode='HTML')
            except Exception:
                pass

# ============================================================
# مراقبة المخرجات
# ============================================================
def enqueue_output(out, q):
    while True:
        try:
            ch = out.read(1)
            if not ch:
                break
            q.put(ch)
        except Exception:
            break

def monitor_output(chat_id, file_id, process):
    q = queue.Queue()
    t = threading.Thread(target=enqueue_output, args=(process.stdout, q))
    t.daemon = True
    t.start()

    buffer = ""
    last_prompt_sent[file_id] = ("", 0)

    def _normalize(text):
        t = re.sub(r'\d+', '#', text)
        t = re.sub(r'\s+', ' ', t)
        return t.strip()[:200]

    def _send_prompt(line):
        prev_text, prev_time = last_prompt_sent.get(file_id, ("", 0))
        now = time.time()
        normalized = _normalize(line)

        if normalized == prev_text and (now - prev_time) < 60:
            return

        last_prompt_sent[file_id] = (normalized, now)
        pending_inputs[chat_id] = file_id

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ إلغاء الطلب", callback_data=f'ci_{file_id}'))

        try:
            bot.send_message(
                chat_id,
                f"📞 <b>الملف يطلب إدخال:</b>\n\n"
                f"<code>{eh(line[:400])}</code>\n\n"
                f"✍️ <b>أرسل الرقم أو الكود الآن:</b>",
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logging.error(f"send prompt: {e}")

    def process_buffer(force=False):
        nonlocal buffer
        if not buffer.strip():
            return
        if not force and '\n' not in buffer and len(buffer) < 150:
            return

        line = buffer.strip()
        buffer = ""

        if len(line) < 2:
            return
        if set(line) <= {'.', '!', '-', '_', ' ', '*', '=', '~'}:
            return

        if looks_prompt(line):
            _send_prompt(line)

    try:
        while True:
            try:
                ch = q.get(timeout=1.0)
                try:
                    decoded = ch.decode('utf-8', errors='ignore')
                except Exception:
                    decoded = ch
                buffer += decoded

                if '\n' in decoded:
                    process_buffer()
                elif len(buffer) > 500:
                    process_buffer()

            except queue.Empty:
                if buffer.strip() and looks_prompt(buffer):
                    process_buffer(force=True)

                if process.poll() is not None:
                    while not q.empty():
                        try:
                            ch = q.get_nowait()
                            try:
                                decoded = ch.decode('utf-8', errors='ignore')
                            except Exception:
                                decoded = ch
                            buffer += decoded
                        except queue.Empty:
                            break
                    if buffer.strip():
                        process_buffer(force=True)

                    exit_code = process.poll()
                    icon = "✅" if exit_code == 0 else "❌"
                    txt = "انتهى الملف بنجاح" if exit_code == 0 else f"توقف بكود خطأ: {exit_code}"
                    try:
                        bot.send_message(
                            chat_id,
                            f"{icon} <b>{txt}</b>\n🆔 <code>{file_id}</code>",
                            parse_mode='HTML'
                        )
                    except Exception:
                        pass
                    break

            except Exception as e:
                logging.error(f"monitor read error: {e}")
                time.sleep(0.5)

    except Exception as e:
        logging.error(f"monitor error [{chat_id}/{file_id}]: {e}")
    finally:
        if pending_inputs.get(chat_id) == file_id:
            pending_inputs.pop(chat_id, None)
        last_prompt_sent.pop(file_id, None)

def stop_one(chat_id, file_id, delete=False):
    with lock:
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

    last_prompt_sent.pop(file_id, None)

    if delete and info.get('path') and os.path.exists(info['path']):
        try:
            os.remove(info['path'])
        except Exception:
            pass
        with lock:
            active_processes[chat_id].pop(file_id, None)

    return True

# ============================================================
# /start والقوائم
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
                f"📋 <b>طلب اشتراك جديد:</b>\n\n👤 {fname}\n🆔 <code>{uid}</code>\n📌 @{eh(uname)}",
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception:
            pass

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
            f"🐍 <b>Python Hosting</b>\n\nمرحباً، {fname}! ✨\n\n👨‍💻 المطور: {YOUR_USERNAME}\n📢 القناة: {ADMIN_CHANNEL}\n\nاختر الخدمة:",
            reply_markup=markup,
            parse_mode='HTML'
        )
    except Exception:
        pass

@bot.message_handler(func=lambda m: (m.chat.id in pending_inputs and m.content_type == 'text' and not (m.text or '').startswith('/')))
def handle_input(message):
    if not bot_running:
        return
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

    user_input = (message.text or '').strip()
    if not user_input:
        return

    try:
        proc.stdin.write((user_input + "\n").encode('utf-8'))
        proc.stdin.flush()

        pending_inputs.pop(chat_id, None)
        last_prompt_sent.pop(file_id, None)

        try:
            bot.reply_to(message, "✅ تم إرسال الرد إلى الملف.")
        except Exception:
            pass
    except Exception as e:
        try:
            bot.reply_to(message, f"❌ فشل الإرسال: {eh(str(e))}", parse_mode='HTML')
        except Exception:
            pass

@bot.message_handler(func=lambda m: m.chat.id in waiting_library and m.content_type == 'text')
def handle_library_name(message):
    if not bot_running:
        return
    chat_id = message.chat.id
    waiting_library.discard(chat_id)
    lib_name = (message.text or '').strip()

    try:
        bot.send_message(chat_id, f"⏳ جاري تثبيت المكتبة <code>{eh(lib_name)}</code>...", parse_mode='HTML')
    except Exception:
        pass

    def install():
        try:
            r = subprocess.run([sys.executable, "-m", "pip", "install", lib_name], capture_output=True, text=True, timeout=300)
            if r.returncode == 0:
                msg = f"✅ تم تثبيت المكتبة <code>{eh(lib_name)}</code> بنجاح!"
            else:
                msg = f"❌ فشل التثبيت:\n<pre>{eh(r.stderr[:500])}</pre>"
        except Exception as e:
            msg = f"❌ خطأ: {eh(str(e))}"
        try:
            bot.send_message(chat_id, msg, parse_mode='HTML')
        except Exception:
            pass

    executor.submit(install)

@bot.message_handler(content_types=['document'])
def handle_doc(message):
    uid = message.from_user.id
    if not is_approved(uid):
        try:
            bot.reply_to(message, "❌ غير مصرح لك برفع الملفات.")
        except Exception:
            pass
        return

    if not bot_running:
        try:
            bot.reply_to(message, "⏸️ البوت متوقف حالياً.")
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
                bot.reply_to(message, "❌ مسموح برفع ملفات بصيغة .py فقط.")
            except Exception:
                pass
            return

        if doc.file_size and doc.file_size > MAX_FILE_SIZE:
            try:
                bot.reply_to(message, f"❌ حجم الملف كبير جداً. الحد الأقصى: 5MB")
            except Exception:
                pass
            return

        file_info = bot.get_file(doc.file_id)
        downloaded = bot.download_file(file_info.file_path)

        file_id = uuid.uuid4().hex[:8]
        user_dir = os.path.join(UPLOADED_FILES_DIR, str(uid))
        os.makedirs(user_dir, exist_ok=True)
        save_path = os.path.abspath(os.path.join(user_dir, f"{file_id}_{file_name}"))

        with open(save_path, 'wb') as f:
            f.write(downloaded)

        with lock:
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
            bot.send_message(chat_id, f"📊 إجمالي ملفاتك النشطة: <code>{total}</code>", parse_mode='HTML')
        except Exception:
            pass

    except Exception as e:
        logging.error(f"handle_doc: {e}")
        try:
            bot.reply_to(message, f"❌ حدث خطأ: {eh(str(e))}", parse_mode='HTML')
        except Exception:
            pass

# ============================================================
# أزرار التحكم المعدلة 100% بدون تعليق
# ============================================================

@bot.callback_query_handler(func=lambda c: True)
def global_callback_handler(call):
    # إنهاء دائرة الانتظار فوراً لكل الضغطات
    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass

    data = call.data
    cid = call.message.chat.id
    uid = call.from_user.id

    if data.startswith('sf_'):
        fid = data.replace('sf_', '')
        if cid not in active_processes or fid not in active_processes[cid]:
            return
        stop_one(cid, fid, delete=False)
        show_files(call, edit=True)

    elif data.startswith('rf_'):
        fid = data.replace('rf_', '')
        if cid not in active_processes or fid not in active_processes[cid]:
            return
        info = active_processes[cid][fid]
        stop_one(cid, fid, delete=False)
        time.sleep(0.3)
        start_file(info['path'], cid, fid)

    elif data.startswith('df_'):
        fid = data.replace('df_', '')
        if cid not in active_processes or fid not in active_processes[cid]:
            return
        stop_one(cid, fid, delete=True)
        show_files(call, edit=True)

    elif data.startswith('ci_'):
        pending_inputs.pop(cid, None)
        try:
            bot.edit_message_text("🚫 تم إلغاء طلب الإدخال.", cid, call.message.message_id)
        except Exception:
            pass

    elif data.startswith('nf_'):
        fid = data.replace('nf_', '')
        if cid not in active_processes or fid not in active_processes[cid]:
            return
        info = active_processes[cid][fid]
        proc = info.get('process')
        status = "🟢 يعمل" if (proc and proc.poll() is None) else "🔴 متوقف"
        pid = proc.pid if (proc and proc.poll() is None) else "—"
        try:
            bot.answer_callback_query(
                call.id,
                f"📁 {info['name']}\n{status}\nPID: {pid}\n🆔 {fid}\n⏰ {info.get('started_at', '—')}",
                show_alert=True
            )
        except Exception:
            pass

    elif data == 'stop_all':
        if cid not in active_processes:
            return
        for fid in list(active_processes[cid].keys()):
            stop_one(cid, fid, delete=False)
        show_files(call, edit=True)

    elif data == 'my_files':
        show_files(call, edit=False)

    elif data == 'back':
        show_menu(call.message)

    elif data == 'upload':
        if not is_approved(uid):
            return
        try:
            bot.send_message(cid, f"📥 <b>أرسل ملف .py الآن</b>", parse_mode='HTML')
        except Exception:
            pass

    elif data == 'speed':
        try:
            bot.send_message(cid, "🚀 سرعة الاستجابة ممتازة ومتصلة 100%.")
        except Exception:
            pass

    elif data == 'about':
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data='back'))
        try:
            bot.send_message(cid, f"ℹ️ <b>حول البوت</b>\n\nمنصة استضافة وتشغيل ملفات بايثون.\n👨‍💻 المطور: {YOUR_USERNAME}", reply_markup=markup, parse_mode='HTML')
        except Exception:
            pass

    elif data in ['support', 'tech_support', 'support_girl']:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("👨‍💼 المطور", url=f"https://t.me/{YOUR_USERNAME.replace('@', '')}"))
        markup.add(types.InlineKeyboardButton("📢 القناة", url=f"https://t.me/{ADMIN_CHANNEL.replace('@', '')}"))
        markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data='back'))
        try:
            bot.send_message(cid, f"📞 للتواصل مع الدعم الفني:", reply_markup=markup)
        except Exception:
            pass

    elif data == 'install_lib':
        if not is_approved(uid):
            return
        waiting_library.add(cid)
        try:
            bot.send_message(cid, "📚 أرسل اسم المكتبة المراد تثبيتها:\nمثال: <code>telethon</code> أو <code>pyrogram</code>", parse_mode='HTML')
        except Exception:
            pass

    elif data == 'protection':
        global protection_enabled
        if not is_admin(uid):
            return
        markup = types.InlineKeyboardMarkup()
        if protection_enabled:
            markup.add(types.InlineKeyboardButton("تعطيل الحماية", callback_data='prot_off'))
        else:
            markup.add(types.InlineKeyboardButton("تفعيل الحماية", callback_data='prot_on'))
        markup.add(types.InlineKeyboardButton("🔙", callback_data='back'))
        try:
            bot.edit_message_text(f"🛡️ حماية الملفات: {'✅ مفعلة' if protection_enabled else '❌ معطلة تماماً'}", cid, call.message.message_id, reply_markup=markup)
        except Exception:
            pass

    elif data in ['prot_on', 'prot_off']:
        global protection_enabled
        if not is_admin(uid):
            return
        protection_enabled = (data == 'prot_on')
        markup = types.InlineKeyboardMarkup()
        if protection_enabled:
            markup.add(types.InlineKeyboardButton("تعطيل الحماية", callback_data='prot_off'))
        else:
            markup.add(types.InlineKeyboardButton("تفعيل الحماية", callback_data='prot_on'))
        markup.add(types.InlineKeyboardButton("🔙", callback_data='back'))
        try:
            bot.edit_message_text(f"🛡️ حماية الملفات: {'✅ مفعلة' if protection_enabled else '❌ معطلة تماماً'}", cid, call.message.message_id, reply_markup=markup)
        except Exception:
            pass

    elif data == 'bot_status':
        global bot_running
        if not is_admin(uid):
            return
        markup = types.InlineKeyboardMarkup()
        if bot_running:
            markup.add(types.InlineKeyboardButton("إيقاف البوت", callback_data='bot_off'))
        else:
            markup.add(types.InlineKeyboardButton("تشغيل البوت", callback_data='bot_on'))
        markup.add(types.InlineKeyboardButton("🔙", callback_data='back'))
        try:
            bot.edit_message_text(f"⚡ حالة البوت: {'✅ يعمل' if bot_running else '⏸️ متوقف'}", cid, call.message.message_id, reply_markup=markup)
        except Exception:
            pass

    elif data in ['bot_on', 'bot_off']:
        global bot_running
        if not is_admin(uid):
            return
        bot_running = (data == 'bot_on')
        markup = types.InlineKeyboardMarkup()
        if bot_running:
            markup.add(types.InlineKeyboardButton("إيقاف البوت", callback_data='bot_off'))
        else:
            markup.add(types.InlineKeyboardButton("تشغيل البوت", callback_data='bot_on'))
        markup.add(types.InlineKeyboardButton("🔙", callback_data='back'))
        try:
            bot.edit_message_text(f"⚡ حالة البوت: {'✅ يعمل' if bot_running else '⏸️ متوقف'}", cid, call.message.message_id, reply_markup=markup)
        except Exception:
            pass

    elif data == 'users':
        if not is_admin(uid):
            return
        a, p = get_stats()
        pending = get_pending()
        markup = types.InlineKeyboardMarkup()
        for p_uid, fname, uname in pending:
            fn = (fname or 'مستخدم')[:15]
            markup.row(
                types.InlineKeyboardButton(f"✅ {fn}", callback_data=f'ap_{p_uid}'),
                types.InlineKeyboardButton(f"❌ {fn}", callback_data=f'rj_{p_uid}')
            )
        markup.add(types.InlineKeyboardButton("🔙", callback_data='back'))
        try:
            bot.edit_message_text(f"👥 المعتمدون: {a}\n⏳ الانتظار: {p}", cid, call.message.message_id, reply_markup=markup)
        except Exception:
            pass

    elif data.startswith('ap_'):
        if not is_admin(uid):
            return
        p_uid = int(data.split('_')[1])
        add_approved(p_uid, 'USER')
        try:
            bot.send_message(p_uid, "🎉 تمت الموافقة على طلبك! أرسل /start للبدء.")
        except Exception:
            pass

    elif data.startswith('rj_'):
        if not is_admin(uid):
            return
        p_uid = int(data.split('_')[1])
        remove_pending(p_uid)

def show_files(call, edit=False):
    cid = call.message.chat.id
    if cid not in active_processes or not active_processes[cid]:
        txt = "📂 لا توجد ملفات مرفوعة حالياً."
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
    text = f"📂 <b>ملفاتك النشطة</b> ({len(files)})\n🟢 يعمل: {running} | 🔴 متوقف: {len(files) - running}"

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
        types.InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data='back')
    )

    if edit:
        try:
            bot.edit_message_text(text, cid, call.message.message_id, reply_markup=markup, parse_mode='HTML')
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
# التشغيل المستمر
# ============================================================
if __name__ == '__main__':
    logging.info("=" * 55)
    logging.info("🤖 Bot starting...")
    logging.info("=" * 55)

    try:
        bot.remove_webhook()
        time.sleep(1)
        logging.info("✅ Webhook removed")
    except Exception as e:
        logging.warning(f"⚠️ remove_webhook: {e}")

    while True:
        try:
            bot.polling(
                none_stop=True,
                interval=0,
                timeout=90,
                long_polling_timeout=90,
            )
        except Exception as err:
            err_str = str(err)
            logging.error(f"Polling error: {err_str}")

            if '429' in err_str or 'flood' in err_str.lower() or 'retry after' in err_str.lower():
                match = re.search(r'(\d+)', err_str)
                wait = int(match.group(1)) if match else 30
                logging.warning(f"⏳ FloodWait: {wait}s")
                time.sleep(wait + 5)
            else:
                time.sleep(5)
