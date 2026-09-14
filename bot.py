# ============================================================
# الاستيرادات الأساسية
# ============================================================
import sys
import os
import re
import ast
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

# ضبط إعدادات ترميز النظام لمنع أي تداخل
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='ignore')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='ignore')
except Exception:
    pass

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

BASE_DIR = os.path.abspath(os.getcwd())
UPLOADED_FILES_DIR = os.path.join(BASE_DIR, "uploaded_files")
MAX_FILE_SIZE = 2048 * 1024 * 1024  # حجم بلا حدود (حتى 2GB)

bot = telebot.TeleBot(BOT_TOKEN)
executor = ThreadPoolExecutor(max_workers=10)
lock = threading.Lock()

protection_enabled = False
bot_running = True

os.makedirs(UPLOADED_FILES_DIR, exist_ok=True)


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
# كلمات مفتاحية لطلبات الإدخال الشاملة (رقم، كود، تحقق، باسورد)
# ============================================================
INPUT_KEYWORDS = [
    'أرسل رمز', 'ارسل رمز', 'أرسل كود', 'ارسل كود', 'أدخل رمز', 'أدخل كود',
    'ادخل الرمز', 'ادخل الكود', 'أدخل رقم الهواتف', 'أدخل رقم الهاتف',
    'enter the phone', 'enter phone', 'phone number', 'enter code',
    'enter the code', 'enter password', 'two-step', 'verification code',
    'code', 'otp', 'number', 'password', 'please enter', 'enter your',
    'الرجاء إدخال', 'ادخل رقم', 'أدخل رقم', 'الرمز', 'الكود', 'رقم الهاتف'
]


def looks_prompt(text):
    if not text or len(text.strip()) < 2:
        return False
    t = text.lower()
    if 'connection' in t and 'traceback' in t:
        return False
    return any(kw in t for kw in INPUT_KEYWORDS)


# ============================================================
# تشغيل الملفات (يدعم البوتات الحديثة والمتقدمة)
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
            # إجبار البوتات الحديثة على إرسال المخرجات فوراً بدون تخزين مؤقت
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
                f"⚡ جارٍ مراقبة إخراج الملف...",
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
# مراقبة المخرجات وتنظيف الرموز التالفة كلياً
# ============================================================
def monitor_output(chat_id, file_id, process):
    buffer = ""
    shown_lines = 0
    MAX_SHOWN = 30
    pending_batch = []
    last_flush = time.time()

    def flush_batch():
        nonlocal pending_batch, last_flush
        if not pending_batch:
            return
        text = "\n".join(pending_batch[:20])
        pending_batch = []
        
        # تصفية النصوص وتنظيفها نهائياً من أي رموز مربعات أو شيفرات تالفة
        clean_text = "".join(c if ord(c) < 128 or c.isspace() or ('\u0600' <= c <= '\u06FF') else '?' for c in text)
        
        try:
            bot.send_message(
                chat_id,
                f"📄 <b>مخرجات الملف:</b>\n<pre>{eh(clean_text[:3000])}</pre>",
                parse_mode='HTML'
            )
        except Exception as e:
            logging.error(f"send output: {e}")
        last_flush = time.time()

    try:
        while True:
            ch = process.stdout.read(1)
            if not ch:
                if process.poll() is not None:
                    remaining = buffer.strip()
                    if remaining:
                        pending_batch.append(remaining)
                    flush_batch()

                    exit_code = process.poll()
                    status_icon = "✅" if exit_code == 0 else "❌"
                    status_text = "انتهى الملف بنجاح" if exit_code == 0 else f"توقف بكود خطأ: {exit_code}"

                    try:
                        bot.send_message(
                            chat_id,
                            f"{status_icon} <b>{status_text}</b>\n🆔 <code>{file_id}</code>",
                            parse_mode='HTML'
                        )
                    except Exception:
                        pass
                    break

                if pending_batch and (time.time() - last_flush) > 3.0:
                    flush_batch()
                time.sleep(0.1)
                continue

            try:
                # تجاهل الأخطاء بصمت بدلاً من تحويلها إلى رموز تالفة
                decoded = ch.decode('utf-8', errors='ignore')
            except Exception:
                continue

            buffer += decoded
            flush = ('\n' in decoded or '?' in decoded or ':' in decoded)

            if flush and len(buffer.strip()) > 1:
                line = buffer.strip()
                if looks_prompt(line):
                    flush_batch()
                    pending_inputs[chat_id] = file_id
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("❌ إلغاء الطلب", callback_data=f'ci_{file_id}'))
                    try:
                        bot.send_message(
                            chat_id,
                            f"📞 <b>طلب من الملف (رقم / كود / تحقق):</b>\n\n"
                            f"<code>{eh(line[:500])}</code>\n\n"
                            f"✍️ أرسل الرد (الرقم أو الكود) في الشات الآن:",
                            reply_markup=markup,
                            parse_mode='HTML'
                        )
                    except Exception as e:
                        logging.error(f"send prompt: {e}")
                    buffer = ""
                elif '\n' in decoded:
                    buffer = ""
                    if not ('traceback' in line.lower() or 'exception' in line.lower()) and shown_lines < MAX_SHOWN:
                        pending_batch.append(line)
                        shown_lines += 1
                    else:
                        pending_batch.append(line)
                    
                    if (time.time() - last_flush) > 2.0 or len(pending_batch) >= 8:
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
        types.InlineKeyboardButton("📥 رفع ملف (بدون حد)", callback_data='upload')
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


# ============================================================
# معالج إدخال الرقم والكود وكلمة المرور من المستخدم
# ============================================================
@bot.message_handler(func=lambda m: (m.chat.id in pending_inputs and m.content_type == 'text' and not (m.text or '').startswith('/')))
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
        try:
            bot.reply_to(message, "✅ تم إرسال الرد بنجاح إلى الملف، تابع المخرجات.", parse_mode='HTML')
        except Exception:
            pass
        pending_inputs.pop(chat_id, None)
    except Exception as e:
        try:
            bot.reply_to(message, f"❌ فشل إرسال الرد: {eh(str(e))}", parse_mode='HTML')
        except Exception:
            pass


@bot.message_handler(func=lambda m: m.chat.id in waiting_library and m.content_type == 'text')
def handle_library_name(message):
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


# ============================================================
# استقبال الملفات (.py) بلا حدود
# ============================================================
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

        file_info = bot.get_file(doc.file_id)
        downloaded = bot.download_file(file_info.file_path)

        file_id = uuid.uuid4().hex[:8]
        user_dir = os.path.join(UPLOADED_FILES_DIR, str(uid))
        os.makedirs(user_dir, exist_ok=True)
        save_path = os.path.abspath(os.path.join(user_dir, f"{file_id}_{file_name}"))

        with open(save_path, 'wb') as f:
            f.write(downloaded)

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
# أزرار التحكم بالملفات
# ============================================================
@bot.callback_query_handler(func=lambda c: c.data.startswith('sf_'))
def cb_stop(call):
    fid = call.data.replace('sf_', '')
    cid = call.message.chat.id
    if cid not in active_processes or fid not in active_processes[cid]:
        bot.answer_callback_query(call.id, "❌ الملف غير موجود")
        return
    stop_one(cid, fid, delete=False)
    bot.answer_callback_query(call.id, "✅ تم إيقاف الملف")
    show_files(call, edit=True)


@bot.callback_query_handler(func=lambda c: c.data.startswith('rf_'))
def cb_restart(call):
    fid = call.data.replace('rf_', '')
    cid = call.message.chat.id
    if cid not in active_processes or fid not in active_processes[cid]:
        bot.answer_callback_query(call.id, "❌ الملف غير موجود")
        return
    info = active_processes[cid][fid]
    stop_one(cid, fid, delete=False)
    time.sleep(0.3)
    start_file(info['path'], cid, fid)
    bot.answer_callback_query(call.id, "🔄 تم إعادة التشغيل")


@bot.callback_query_handler(func=lambda c: c.data.startswith('df_'))
def cb_delete(call):
    fid = call.data.replace('df_', '')
    cid = call.message.chat.id
    if cid not in active_processes or fid not in active_processes[cid]:
        bot.answer_callback_query(call.id, "❌ الملف غير موجود")
        return
    stop_one(cid, fid, delete=True)
    bot.answer_callback_query(call.id, "🗑️ تم حذف الملف")
    show_files(call, edit=True)


@bot.callback_query_handler(func=lambda c: c.data.startswith('ci_'))
def cb_cancel_input(call):
    pending_inputs.pop(call.message.chat.id, None)
    bot.answer_callback_query(call.id, "✅ تم إلغاء الطلب")
    try:
        bot.edit_message_text("🚫 تم إلغاء طلب الإدخال.", call.message.chat.id, call.message.message_id)
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
        bot.answer_callback_query(call.id, "لا توجد ملفات")
        return
    count = 0
    for fid in list(active_processes[cid].keys()):
        if stop_one(cid, fid, delete=False):
            count += 1
    bot.answer_callback_query(call.id, f"🛑 تم إيقاف {count} ملفات")
    show_files(call, edit=True)


@bot.callback_query_handler(func=lambda c: c.data == 'my_files')
def cb_my_files(call):
    show_files(call, edit=False)


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


@bot.callback_query_handler(func=lambda c: c.data == 'back')
def cb_back(call):
    bot.answer_callback_query(call.id)
    show_menu(call.message)


@bot.callback_query_handler(func=lambda c: c.data == 'upload')
def cb_upload(call):
    if not is_approved(call.from_user.id):
        bot.answer_callback_query(call.id, "❌")
        return
    bot.answer_callback_query(call.id)
    try:
        bot.send_message(call.message.chat.id, f"📥 <b>أرسل ملف .py الآن (الحجم بلا حدود)</b>", parse_mode='HTML')
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data == 'speed')
def cb_speed(call):
    bot.answer_callback_query(call.id)
    try:
        bot.send_message(call.message.chat.id, "🚀 سرعة الاستجابة ممتازة ومتصلة 100%.")
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data == 'about')
def cb_about(call):
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data='back'))
    try:
        bot.send_message(call.message.chat.id, f"ℹ️ <b>حول البوت</b>\n\nمنصة استضافة وتشغيل جميع ملفات بايثون بلا حدود.\n👨‍💻 المطور: {YOUR_USERNAME}", reply_markup=markup, parse_mode='HTML')
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data in ['support', 'tech_support', 'support_girl'])
def cb_support(call):
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("👨‍💼 المطور", url=f"https://t.me/{YOUR_USERNAME.replace('@', '')}"))
    markup.add(types.InlineKeyboardButton("📢 القناة", url=f"https://t.me/{ADMIN_CHANNEL.replace('@', '')}"))
    markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data='back'))
    try:
        bot.send_message(call.message.chat.id, f"📞 للتواصل مع الدعم الفني والمطور:", reply_markup=markup)
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
        bot.send_message(call.message.chat.id, "📚 أرسل اسم المكتبة المراد تثبيتها:\nمثال: <code>telethon</code> أو <code>pyrogram</code>", parse_mode='HTML')
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data == 'protection')
def cb_protection(call):
    global protection_enabled
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌")
        return
    markup = types.InlineKeyboardMarkup()
    if protection_enabled:
        markup.add(types.InlineKeyboardButton("تعطيل الحماية", callback_data='prot_off'))
    else:
        markup.add(types.InlineKeyboardButton("تفعيل الحماية", callback_data='prot_on'))
    markup.add(types.InlineKeyboardButton("🔙", callback_data='back'))
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text(f"🛡️ حماية الملفات: {'✅ مفعلة' if protection_enabled else '❌ معطلة تماماً (بدون قيود)'}", call.message.chat.id, call.message.message_id, reply_markup=markup)
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data in ['prot_on', 'prot_off'])
def cb_prot_toggle(call):
    global protection_enabled
    if not is_admin(call.from_user.id):
        return
    protection_enabled = (call.data == 'prot_on')
    bot.answer_callback_query(call.id, "✅ تم التغيير")
    cb_protection(call)


@bot.callback_query_handler(func=lambda c: c.data == 'bot_status')
def cb_bot_status(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌")
        return
    markup = types.InlineKeyboardMarkup()
    if bot_running:
        markup.add(types.InlineKeyboardButton("إيقاف البوت", callback_data='bot_off'))
    else:
        markup.add(types.InlineKeyboardButton("تشغيل البوت", callback_data='bot_on'))
    markup.add(types.InlineKeyboardButton("🔙", callback_data='back'))
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text(f"⚡ حالة البوت: {'✅ يعمل' if bot_running else '⏸️ متوقف'}", call.message.chat.id, call.message.message_id, reply_markup=markup)
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
        bot.edit_message_text(f"👥 المعتمدون: {a}\n⏳ الانتظار: {p}", call.message.chat.id, call.message.message_id, reply_markup=markup)
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data.startswith('ap_'))
def cb_approve(call):
    if not is_admin(call.from_user.id):
        return
    uid = int(call.data.split('_')[1])
    add_approved(uid, 'USER')
    bot.answer_callback_query(call.id, "✅ تمت الموافقة")
    try:
        bot.send_message(uid, "🎉 تمت الموافقة على طلبك! أرسل /start للبدء.")
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data.startswith('rj_'))
def cb_reject(call):
    if not is_admin(call.from_user.id):
        return
    uid = int(call.data.split('_')-1 if False else call.data.split('_')[1])
    remove_pending(uid)
    bot.answer_callback_query(call.id, "❌ تم الرفض")


# ============================================================
# التشغيل
# ============================================================
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
            logging.error(f"Polling error: {err}")
            time.sleep(3)
