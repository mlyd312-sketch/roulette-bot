import sys
import os
import re
import time
import uuid
import sqlite3
import logging
import signal
import atexit
import threading
import subprocess
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import telebot
from telebot import types

logging.basicConfig(level=logging.CRITICAL, handlers=[logging.NullHandler()])
for name in ['telebot', 'urllib3', 'requests', 'telegram', 'pyrogram',
             'asyncio', 'PIL', 'matplotlib', 'numba']:
    logging.getLogger(name).setLevel(logging.CRITICAL)
    logging.getLogger(name).propagate = False

# ============================================================
# الإعدادات
# ============================================================
BOT_TOKEN = '8877293036:AAGg_82F0bT1Bhov42sk9qDcRMsVNpfnErw'
ADMIN_ID = 1920665874
YOUR_USERNAME = '@u_8_y'
ADMIN_CHANNEL = '@FD_CQ'
UPLOADED_FILES_DIR = "uploaded_files"
MAX_FILE_SIZE = 10 * 1024 * 1024

bot = telebot.TeleBot(BOT_TOKEN, threaded=True, num_threads=10)
executor = ThreadPoolExecutor(max_workers=10)
lock = threading.Lock()
protection_enabled = True
bot_running = True
os.makedirs(UPLOADED_FILES_DIR, exist_ok=True)

REQUIRED_PACKAGES = [
    ("pyrogram", "pyrogram"), ("tgcrypto", "tgcrypto"),
    ("Telethon", "telethon"), ("cryptg", "cryptg"),
    ("pyTelegramBotAPI", "telebot"), ("aiogram", "aiogram"),
    ("requests", "requests"), ("aiohttp", "aiohttp"),
    ("httpx", "httpx"), ("beautifulsoup4", "bs4"),
    ("lxml", "lxml"), ("chardet", "chardet"),
    ("Pillow", "PIL"), ("qrcode", "qrcode"),
    ("numpy", "numpy"), ("pandas", "pandas"),
    ("cryptography", "cryptography"), ("pyaes", "pyaes"),
    ("rsa", "rsa"), ("python-dotenv", "dotenv"),
    ("psutil", "psutil"), ("colorama", "colorama"),
]

def auto_install_packages():
    import importlib
    missing = []
    for pip_name, import_name in REQUIRED_PACKAGES:
        try:
            importlib.import_module(import_name)
        except ImportError:
            missing.append(pip_name)
        except:
            pass
    for pip_name in missing:
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "--quiet",
                            "--no-cache-dir", pip_name], capture_output=True, timeout=300)
        except:
            pass

E = {
    'fire': '5424972470023104089', 'check': '5206607081334906820',
    'sparkles': '5325547803936572038', 'gem': '5427168083074628963',
    'pencil': '5395444784611480792', 'settings': '5341715473882955310',
    'crown': '5217822164362739968', 'chart': '5231200819986047254',
    'warning': '5447644880824181073', 'people': '5258513401784573443',
    'link': '5271604874419647061', 'arrow': '5416117059207572332',
    'cross': '5210952531676504517', 'bulb': '5422439311196834318',
    'bell': '5458603043203327669', 'python': '5260480440971570446',
    'folder': '5431449001532594346', 'restart': '5372860804316422072',
    'trash': '5445267414562389170', 'stop': '5411225014148014586',
    'phone': '5445358775149883195', 'key': '5424562381729012108',
    'shield': '5217549631293379466', 'robot': '5258113901106580375',
}

def eh(text):
    if text is None: return ""
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def safe_send(cid, text, **kwargs):
    try: return bot.send_message(cid, text, **kwargs)
    except: return None

def safe_edit(cid, mid, text, **kwargs):
    try: return bot.edit_message_text(text, cid, mid, **kwargs)
    except: return None

def safe_answer(cid, text=None, **kwargs):
    try: return bot.answer_callback_query(cid, text, **kwargs)
    except: return None

# ============================================================
# قاعدة البيانات
# ============================================================
def init_db():
    with sqlite3.connect('bot_data.db', timeout=15) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS approved_users (
            user_id INTEGER PRIMARY KEY, username TEXT,
            approved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS pending_requests (
            user_id INTEGER PRIMARY KEY, first_name TEXT, username TEXT,
            requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('INSERT OR IGNORE INTO approved_users (user_id, username) VALUES (?, ?)',
                  (ADMIN_ID, 'ADMIN'))
        conn.commit()

init_db()

def is_admin(uid): return uid == ADMIN_ID
def is_approved(uid):
    if is_admin(uid): return True
    try:
        with sqlite3.connect('bot_data.db', timeout=15) as conn:
            c = conn.cursor()
            c.execute('SELECT user_id FROM approved_users WHERE user_id = ?', (uid,))
            return c.fetchone() is not None
    except: return False

def is_pending(uid):
    try:
        with sqlite3.connect('bot_data.db', timeout=15) as conn:
            c = conn.cursor()
            c.execute('SELECT user_id FROM pending_requests WHERE user_id = ?', (uid,))
            return c.fetchone() is not None
    except: return False

def add_approved(uid, username):
    try:
        with sqlite3.connect('bot_data.db', timeout=15) as conn:
            c = conn.cursor()
            c.execute('INSERT OR REPLACE INTO approved_users (user_id, username) VALUES (?, ?)', (uid, username))
            c.execute('DELETE FROM pending_requests WHERE user_id = ?', (uid,))
            conn.commit()
    except: pass

def add_pending(uid, fname, username):
    try:
        with sqlite3.connect('bot_data.db', timeout=15) as conn:
            c = conn.cursor()
            c.execute('INSERT OR REPLACE INTO pending_requests (user_id, first_name, username) VALUES (?, ?, ?)',
                      (uid, fname, username))
            conn.commit()
    except: pass

def remove_pending(uid):
    try:
        with sqlite3.connect('bot_data.db', timeout=15) as conn:
            c = conn.cursor()
            c.execute('DELETE FROM pending_requests WHERE user_id = ?', (uid,))
            conn.commit()
    except: pass

def get_pending():
    try:
        with sqlite3.connect('bot_data.db', timeout=15) as conn:
            c = conn.cursor()
            c.execute('SELECT user_id, first_name, username FROM pending_requests')
            return c.fetchall()
    except: return []

def get_stats():
    try:
        with sqlite3.connect('bot_data.db', timeout=15) as conn:
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM approved_users')
            a = c.fetchone()[0]
            c.execute('SELECT COUNT(*) FROM pending_requests')
            p = c.fetchone()[0]
            return a, p
    except: return 0, 0

# ============================================================
# متغيرات عامة
# ============================================================
active_processes = {}
pending_inputs = {}
waiting_library = set()
error_tracker = {}
prompt_tracker = {}

# ============================================================
# ✅ الفلتر النهائي — دقيق جداً
# ============================================================
VERBS_AR = [r'أرسل', r'ارسل', r'أدخل', r'ادخل', r'اكتب', r'قم\s+بإرسال',
            r'قم\s+بإدخال', r'الرجاء\s+إدخال', r'الرجاء\s+ادخال',
            r'من\s+فضلك\s+أرسل', r'من\s+فضلك\s+ارسل']
VERBS_EN = [r'\benter\b', r'\binput\b', r'\bsend\b', r'\bprovide\b',
            r'\btype\b', r'please\s+enter', r'please\s+send', r'please\s+provide']

TARGETS_GENERAL = [r'\bرقم\b', r'\bكود\b', r'\bرمز\b', r'\bهاتف\b',
                   r'\bphone\b', r'\bnumber\b', r'\bcode\b', r'\botp\b',
                   r'\bpassword\b', r'\bpass\b']

TARGETS_SPECIFIC = [
    r'رقم\s+الهاتف', r'رقم\s+هاتف', r'كود\s+التحقق', r'رمز\s+التحقق',
    r'كلمة\s+السر', r'كلمة\s+المرور',
    r'التحقق\s+بخطوتين', r'التحقق\s+بخطوتي',
    r'phone\s+number', r'verification\s+code', r'login\s+code',
    r'auth\s+code', r'2fa\s+code', r'otp\s+code',
    r'\bapi_id\b', r'\bapi_hash\b', r'\bbot_token\b',
    r'session\s+string', r'string\s+session',
]

FALSE_POSITIVES = [
    'traceback', 'error', 'exception', 'warning', 'failed', 'fail',
    'success', 'connected', 'connection', 'loading', 'loaded',
    'starting', 'started', 'ready', 'listening', 'sending',
    'received', 'file path', 'config', 'setting', 'opening',
    'closing', 'saved', 'stored', 'checked', 'verifying',
    'checking', 'processing', 'looking', 'searching', 'waiting',
    'timeout', 'retry', 'deprecated', 'debug', 'info:', 'warn:',
    'note:', 'auth key exchange', 'session initialized',
    'session created', 'session loaded', 'session saved',
    'session file', 'key exchange', 'initialized', 'initializing',
    'reading', 'listening on', 'connection established',
    'connection lost', 'connection failed', 'run ok', 'ready to',
]

def looks_prompt(text):
    if not text: return False
    t = text.strip()
    if len(t) < 4 or len(t) > 200: return False
    t_lower = t.lower()

    if re.match(r'^\d{2}:\d{2}', t): return False
    if re.match(r'^\d{4}[-/]\d{2}', t): return False

    log_markers = [
        ' - info - ', ' - warning - ', ' - debug - ', ' - error - ',
        ' - critical - ', '::info', '::warning', '::debug', '::error',
        '[info]', '[warning]', '[debug]', '[error]',
    ]
    for lm in log_markers:
        if lm in t_lower: return False

    for fp in FALSE_POSITIVES:
        if fp in t_lower: return False

    for p in TARGETS_SPECIFIC:
        if re.search(p, t, re.IGNORECASE): return True

    has_verb = any(re.search(v, t, re.IGNORECASE) for v in (VERBS_AR + VERBS_EN))
    has_target = any(re.search(tg, t, re.IGNORECASE) for tg in TARGETS_GENERAL)

    return has_verb and has_target

# ============================================================
# فلتر الأخطاء
# ============================================================
REAL_ERRORS = [
    'traceback (most recent call last)', 'modulenotfounderror',
    'syntaxerror', 'indentationerror', 'nameerror', 'typeerror',
    'valueerror', 'keyerror', 'attributeerror', 'filenotfounderror',
    'permissionerror', 'runtimeerror', 'zerodivisionerror',
    'indexerror', 'importerror', 'apiidinvalid', 'apihashinvalid',
    'phone_number_invalid', 'phonecodeinvalid', 'sessionpasswordneeded',
    'authkeyunregistered',
]

IGNORE_SIGS = [
    'warning', 'warn:', 'deprecat', 'futurewarning', 'userwarning',
    'info:', 'debug:', 'rate limit', 'floodwait', 'flood wait',
    'retry after', 'too many requests', 'connection reset',
    'connection error', 'persistent timestamp', 'read timeout',
    'connect timeout', 'proxyerror', 'ssl error', 'urllib3',
    'requests.exceptions', 'asyncio', 'runtimewarning',
]

def is_real_error(text):
    if not text: return False
    t = text.lower().strip()
    if len(t) < 10: return False
    for w in IGNORE_SIGS:
        if w in t: return False
    for sig in REAL_ERRORS:
        if sig in t: return True
    return False

def send_error_once(chat_id, file_id, error_text):
    now = time.time()
    if file_id not in error_tracker:
        error_tracker[file_id] = {'last_error': '', 'last_time': 0, 'count': 0}
    tracker = error_tracker[file_id]
    if tracker['last_error'] == error_text and (now - tracker['last_time']) < 300:
        return
    if tracker['count'] >= 10:
        return
    tracker['last_error'] = error_text
    tracker['last_time'] = now
    tracker['count'] += 1
    safe_send(chat_id, f"⚠️ <b>خطأ ({tracker['count']}/10):</b>\n<pre>{eh(error_text[:1200])}</pre>",
              parse_mode='HTML')

def send_prompt_once(chat_id, file_id, prompt_text):
    now = time.time()
    if file_id not in prompt_tracker:
        prompt_tracker[file_id] = {'last_prompt': '', 'last_time': 0}
    tracker = prompt_tracker[file_id]
    if tracker['last_prompt'] == prompt_text and (now - tracker['last_time']) < 120:
        return False
    tracker['last_prompt'] = prompt_text
    tracker['last_time'] = now
    return True

# ============================================================
# تشغيل/مراقبة/إيقاف
# ============================================================
def start_file(script_path, chat_id, file_id):
    script_path = os.path.abspath(script_path)
    with lock:
        if chat_id not in active_processes:
            active_processes[chat_id] = {}
        if file_id not in active_processes[chat_id]:
            active_processes[chat_id][file_id] = {
                'name': os.path.basename(script_path), 'path': script_path,
                'process': None, 'started_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        info = active_processes[chat_id][file_id]
        info['path'] = script_path
        proc = info.get('process')
        if proc and proc.poll() is None:
            safe_send(chat_id, "⚠️ الملف يعمل بالفعل.")
            return
        if not os.path.exists(script_path):
            safe_send(chat_id, "❌ الملف غير موجود.")
            return
        try:
            work_dir = os.path.dirname(script_path)
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            env['PYTHONIOENCODING'] = 'utf-8'
            env['PYTHONDONTWRITEBYTECODE'] = '1'
            env['PYTHONWARNINGS'] = 'ignore'
            p = subprocess.Popen(
                [sys.executable, "-u", script_path],
                cwd=work_dir, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, bufsize=0, env=env, start_new_session=True
            )
            info['process'] = p
            info['started_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            error_tracker[file_id] = {'last_error': '', 'last_time': 0, 'count': 0}
            prompt_tracker[file_id] = {'last_prompt': '', 'last_time': 0}
            markup = types.InlineKeyboardMarkup(row_width=3)
            markup.add(
                types.InlineKeyboardButton("🛑 إيقاف", callback_data=f'sf_{file_id}'),
                types.InlineKeyboardButton("🔄 إعادة", callback_data=f'rf_{file_id}'),
                types.InlineKeyboardButton("🗑️ حذف", callback_data=f'df_{file_id}')
            )
            markup.add(types.InlineKeyboardButton(
                f"📂 ملفاتي ({len(active_processes[chat_id])})", callback_data='my_files'))
            safe_send(chat_id,
                      f"✅ <b>تم تشغيل الملف</b>\n📁 <code>{eh(info['name'])}</code>\n"
                      f"🆔 <code>{file_id}</code>\nPID: <code>{p.pid}</code>",
                      reply_markup=markup, parse_mode='HTML')
            t = threading.Thread(target=monitor_output, args=(chat_id, file_id, p), daemon=True)
            t.start()
        except Exception as e:
            safe_send(chat_id, f"❌ فشل: {eh(str(e))}", parse_mode='HTML')

def monitor_output(chat_id, file_id, process):
    buffer = ""
    traceback_buffer = []
    try:
        while True:
            try:
                ch = process.stdout.read(1)
            except:
                break
            if not ch:
                if process.poll() is not None:
                    if traceback_buffer:
                        full_error = "\n".join(traceback_buffer)
                        if is_real_error(full_error):
                            send_error_once(chat_id, file_id, full_error)
                        traceback_buffer = []
                    exit_code = process.poll()
                    if exit_code != 0:
                        safe_send(chat_id, f"❌ <b>توقف بكود: {exit_code}</b>", parse_mode='HTML')
                    else:
                        safe_send(chat_id, "✅ <b>انتهى بنجاح</b>", parse_mode='HTML')
                    break
                time.sleep(0.03)
                continue
            try:
                decoded = ch.decode('utf-8', errors='replace')
            except:
                continue
            buffer += decoded
            flush = False
            if '\n' in decoded:
                flush = True
            elif decoded in ('؟', '?', ':', '!', '؛', '،') and len(buffer.strip()) >= 4:
                flush = True
            if not flush:
                continue
            line = buffer.strip()
            buffer = ""
            if not line:
                continue
            if 'traceback (most recent call last)' in line.lower():
                traceback_buffer = [line]
                continue
            if traceback_buffer:
                traceback_buffer.append(line)
                if len(traceback_buffer) >= 8:
                    full_error = "\n".join(traceback_buffer)
                    if is_real_error(full_error):
                        send_error_once(chat_id, file_id, full_error)
                    traceback_buffer = []
                continue
            if is_real_error(line):
                send_error_once(chat_id, file_id, line)
                continue
            if looks_prompt(line):
                if send_prompt_once(chat_id, file_id, line):
                    pending_inputs[chat_id] = file_id
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton(
                        "❌ إلغاء الطلب", callback_data=f'ci_{file_id}'))
                    safe_send(chat_id,
                              f"📨 <b>الملف يطلب إدخال:</b>\n\n"
                              f"<code>{eh(line[:600])}</code>\n\n✍️ أرسل الإجابة:",
                              reply_markup=markup, parse_mode='HTML')
                continue
    except:
        pass
    finally:
        if pending_inputs.get(chat_id) == file_id:
            pending_inputs.pop(chat_id, None)

def stop_one(chat_id, file_id, delete=False):
    if chat_id not in active_processes or file_id not in active_processes[chat_id]:
        return False
    info = active_processes[chat_id][file_id]
    proc = info.get('process')
    if proc and proc.poll() is None:
        try: proc.stdin.close()
        except: pass
        try:
            proc.terminate()
            try: proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill(); proc.wait()
        except: pass
    if pending_inputs.get(chat_id) == file_id:
        pending_inputs.pop(chat_id, None)
    error_tracker.pop(file_id, None)
    prompt_tracker.pop(file_id, None)
    if delete and info.get('path') and os.path.exists(info['path']):
        try: os.remove(info['path'])
        except: pass
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
    if is_admin(uid): return False, ""
    try:
        with open(path, 'rb') as f:
            content = f.read().decode('utf-8', errors='ignore')
        for p in [r"rm\s+-rf\s+/", r"import\s+marshal"]:
            if re.search(p, content, re.IGNORECASE):
                return True, "نمط مشبوه"
        return False, ""
    except: return False, ""

# ============================================================
# قائمة الملفات
# ============================================================
def show_my_files(call, edit=False):
    chat_id = call.message.chat.id
    if chat_id not in active_processes or not active_processes[chat_id]:
        txt = "📂 لا توجد ملفات."
        if edit: safe_edit(chat_id, call.message.message_id, txt)
        else: safe_send(chat_id, txt)
        return
    files = active_processes[chat_id]
    running = sum(1 for f in files.values() if f.get('process') and f['process'].poll() is None)
    text = f"📂 <b>ملفاتك</b> ({len(files)})\n🟢 يعمل: {running} | 🔴 متوقف: {len(files) - running}"
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
        types.InlineKeyboardButton("🔙 القائمة", callback_data='back_to_main'))
    if edit:
        res = safe_edit(chat_id, call.message.message_id, text, reply_markup=markup, parse_mode='HTML')
        if not res: safe_send(chat_id, text, reply_markup=markup, parse_mode='HTML')
    else:
        safe_send(chat_id, text, reply_markup=markup, parse_mode='HTML')

# ============================================================
# القائمة الرئيسية
# ============================================================
def show_main_menu(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🛡️ الحماية", callback_data='protection'),
        types.InlineKeyboardButton("📥 رفع ملف", callback_data='upload'))
    markup.add(
        types.InlineKeyboardButton("📂 ملفاتي", callback_data='my_files'),
        types.InlineKeyboardButton("👩‍💼 فتاة المحاور", callback_data='support_girl'))
    markup.add(
        types.InlineKeyboardButton("🚀 السرعة", callback_data='speed'),
        types.InlineKeyboardButton("ℹ️ حول البوت", callback_data='about'))
    markup.add(
        types.InlineKeyboardButton("🛠️ الدعم الفني", callback_data='tech_support'),
        types.InlineKeyboardButton("📚 تثبيت مكتبة", callback_data='install_lib'))
    markup.add(types.InlineKeyboardButton("📞 التواصل مع الدعم", callback_data='support'))
    if is_admin(message.from_user.id):
        markup.add(
            types.InlineKeyboardButton("👥 المستخدمون", callback_data='users'),
            types.InlineKeyboardButton("⚡ حالة البوت", callback_data='bot_status'))
    safe_send(message.chat.id,
              f"🐍 <b>Python Hosting</b>\n\nمرحباً، {eh(message.from_user.first_name or '')}! ✨\n\n"
              f"👨‍💻 {YOUR_USERNAME}\n📢 {ADMIN_CHANNEL}\n\n"
              f"✅ Telethon • Pyrogram • Aiogram • telebot\n\n"
              f"📂 تشغيل عدة ملفات\n📨 تفاعل ذكي\n\nاختر الخدمة:",
              reply_markup=markup, parse_mode='HTML')

# ============================================================
# Handlers
# ============================================================
@bot.message_handler(commands=['start'], chat_types=['private'])
def cmd_start(message):
    uid = message.from_user.id
    if not bot_running:
        safe_send(message.chat.id, "⏸️ البوت متوقف مؤقتاً.")
        return
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
            types.InlineKeyboardButton("❌ رفض", callback_data=f'rj_{uid}'))
        try:
            bot.send_message(ADMIN_ID,
                             f"📋 <b>طلب اشتراك:</b>\n\n👤 {fname}\n🆔 <code>{uid}</code>\n📌 @{eh(uname)}",
                             reply_markup=markup, parse_mode='HTML')
        except: pass
        safe_send(message.chat.id, "⏳ تم إرسال طلبك للأدمن.")

@bot.message_handler(
    func=lambda m: (m.chat.id in pending_inputs and m.content_type == 'text'
                    and not (m.text or '').startswith('/')))
def handle_input(message):
    chat_id = message.chat.id
    file_id = pending_inputs.get(chat_id)
    if not file_id: return
    if chat_id not in active_processes or file_id not in active_processes[chat_id]:
        pending_inputs.pop(chat_id, None); return
    proc = active_processes[chat_id][file_id].get('process')
    if not proc or proc.poll() is not None:
        pending_inputs.pop(chat_id, None)
        safe_send(chat_id, "❌ الملف لم يعد يعمل."); return
    user_input = (message.text or '').strip()
    try:
        proc.stdin.write((user_input + "\n").encode('utf-8'))
        proc.stdin.flush()
        if len(user_input) > 8:
            masked = user_input[:3] + "*" * (len(user_input) - 6) + user_input[-3:]
        else:
            masked = user_input[:2] + "*" * max(0, len(user_input) - 2)
        safe_send(chat_id, f"✅ <code>{eh(masked)}</code>", parse_mode='HTML')
        pending_inputs.pop(chat_id, None)
    except:
        safe_send(chat_id, "❌ فشل الإرسال")

@bot.message_handler(func=lambda m: m.chat.id in waiting_library and m.content_type == 'text')
def handle_library_name(message):
    chat_id = message.chat.id
    waiting_library.discard(chat_id)
    lib_name = (message.text or '').strip()
    if not re.match(r'^[a-zA-Z0-9_\-\.]+(\s*[<>=!]+\s*[0-9a-zA-Z\.\-]+)?$', lib_name):
        safe_send(chat_id, "❌ اسم غير صالح."); return
    safe_send(chat_id, f"⏳ جاري تثبيت <code>{eh(lib_name)}</code>...", parse_mode='HTML')
    def install():
        try:
            r = subprocess.run([sys.executable, "-m", "pip", "install", lib_name],
                               capture_output=True, text=True, timeout=300)
            msg = f"✅ تم تثبيت <code>{eh(lib_name)}</code>" if r.returncode == 0 else "❌ فشل"
        except: msg = "❌ خطأ"
        safe_send(chat_id, msg, parse_mode='HTML')
    executor.submit(install)

@bot.message_handler(content_types=['document'])
def handle_doc(message):
    uid = message.from_user.id
    if not is_approved(uid):
        safe_send(message.chat.id, "❌ غير مصرح"); return
    if not bot_running:
        safe_send(message.chat.id, "⏸️ البوت متوقف."); return
    if message.chat.id in waiting_library:
        waiting_library.discard(message.chat.id)
    try:
        chat_id = message.chat.id
        doc = message.document
        # ✅ إصلاح أمني: تنظيف اسم الملف لمنع Path Traversal
        raw_name = doc.file_name or f"script_{uuid.uuid4().hex[:6]}.py"
        file_name = os.path.basename(raw_name)
        
        if not file_name.endswith('.py'):
            safe_send(chat_id, "❌ فقط ملفات .py"); return
        if doc.file_size and doc.file_size > MAX_FILE_SIZE:
            safe_send(chat_id, f"⛔ الحجم > {MAX_FILE_SIZE // (1024*1024)}MB"); return
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
                try: os.remove(save_path)
                except: pass
                safe_send(chat_id, f"⛔ {eh(reason)}", parse_mode='HTML'); return
        if chat_id not in active_processes:
            active_processes[chat_id] = {}
        active_processes[chat_id][file_id] = {
            'name': file_name, 'path': save_path, 'process': None,
            'started_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        total = len(active_processes[chat_id])
        start_file(save_path, chat_id, file_id)
        safe_send(chat_id, f"📊 مجموع ملفاتك: <code>{total}</code>", parse_mode='HTML')
    except Exception as e:
        safe_send(message.chat.id, f"❌ خطأ في الرفع: {eh(str(e))}", parse_mode='HTML')

# ============================================================
# أزرار الملفات
# ============================================================
@bot.callback_query_handler(func=lambda c: c.data.startswith('sf_'))
def cb_stop(call):
    fid = call.data.replace('sf_', '')
    cid = call.message.chat.id
    if cid not in active_processes or fid not in active_processes[cid]:
        safe_answer(call.id, "❌"); return
    stop_one(cid, fid, delete=False); safe_answer(call.id, "✅")
    show_my_files(call, edit=True)

@bot.callback_query_handler(func=lambda c: c.data.startswith('rf_'))
def cb_restart(call):
    fid = call.data.replace('rf_', '')
    cid = call.message.chat.id
    if cid not in active_processes or fid not in active_processes[cid]:
        safe_answer(call.id, "❌"); return
    info = active_processes[cid][fid]
    stop_one(cid, fid, delete=False); time.sleep(0.3)
    start_file(info['path'], cid, fid); safe_answer(call.id, "🔄")

@bot.callback_query_handler(func=lambda c: c.data.startswith('df_'))
def cb_delete(call):
    fid = call.data.replace('df_', '')
    cid = call.message.chat.id
    if cid not in active_processes or fid not in active_processes[cid]:
        safe_answer(call.id, "❌"); return
    stop_one(cid, fid, delete=True); safe_answer(call.id, "🗑️")
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
        safe_answer(call.id, "❌"); return
    info = active_processes[cid][fid]
    proc = info.get('process')
    status = "🟢 يعمل" if (proc and proc.poll() is None) else "🔴 متوقف"
    pid = proc.pid if (proc and proc.poll() is None) else "—"
    safe_answer(call.id, f"📁 {info['name']}\n{status}\nPID: {pid}\n🆔 {fid}", show_alert=True)

@bot.callback_query_handler(func=lambda c: c.data == 'stop_all')
def cb_stop_all(call):
    cid = call.message.chat.id
    if cid not in active_processes:
        safe_answer(call.id, "لا ملفات"); return
    count = 0
    for fid in list(active_processes[cid].keys()):
        if stop_one(cid, fid, delete=False): count += 1
    safe_answer(call.id, f"🛑 {count}")
    show_my_files(call, edit=True)

@bot.callback_query_handler(func=lambda c: c.data == 'my_files')
def cb_my_files(call): show_my_files(call, edit=False)

@bot.callback_query_handler(func=lambda c: c.data == 'back_to_main')
def cb_back(call):
    safe_answer(call.id); show_main_menu(call.message)

@bot.callback_query_handler(func=lambda c: c.data == 'upload')
def cb_upload(call):
    if not is_approved(call.from_user.id):
        safe_answer(call.id, "❌"); return
    safe_answer(call.id, "📤")
    safe_send(call.message.chat.id, "📥 <b>أرسل ملف .py</b>", parse_mode='HTML')

@bot.callback_query_handler(func=lambda c: c.data == 'speed')
def cb_speed(call):
    safe_answer(call.id)
    msg = safe_send(call.message.chat.id, "⏳")
    if msg: safe_edit(call.message.chat.id, msg.message_id, "🚀 السرعة: ممتازة")

@bot.callback_query_handler(func=lambda c: c.data == 'about')
def cb_about(call):
    safe_answer(call.id)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data='back_to_main'))
    safe_send(call.message.chat.id,
              f"ℹ️ <b>حول البوت</b>\n\n🐍 منصة استضافة Python\n📂 ملفات متعددة\n📞 تفاعل ذكي\n\n"
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
        safe_answer(call.id, "❌"); return
    safe_answer(call.id)
    waiting_library.add(call.message.chat.id)
    safe_send(call.message.chat.id, "📚 أرسل اسم المكتبة:", parse_mode='HTML')

@bot.callback_query_handler(func=lambda c: c.data == 'protection')
def cb_protection(call):
    if not is_admin(call.from_user.id):
        safe_answer(call.id, "❌"); return
    markup = types.InlineKeyboardMarkup()
    if protection_enabled:
        markup.add(types.InlineKeyboardButton("تعطيل", callback_data='prot_off'))
    else:
        markup.add(types.InlineKeyboardButton("تفعيل", callback_data='prot_on'))
    markup.add(types.InlineKeyboardButton("🔙", callback_data='back_to_main'))
    safe_answer(call.id)
    safe_edit(call.message.chat.id, call.message.message_id,
              f"🛡️ الحماية: {'✅' if protection_enabled else '❌'}", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data in ['prot_on', 'prot_off'])
def cb_prot_toggle(call):
    global protection_enabled
    if not is_admin(call.from_user.id): return
    protection_enabled = (call.data == 'prot_on')
    safe_answer(call.id, "✅"); cb_protection(call)

@bot.callback_query_handler(func=lambda c: c.data == 'bot_status')
def cb_bot_status(call):
    if not is_admin(call.from_user.id):
        safe_answer(call.id, "❌"); return
    markup = types.InlineKeyboardMarkup()
    if bot_running:
        markup.add(types.InlineKeyboardButton("🛑 إيقاف", callback_data='bot_off'))
    else:
        markup.add(types.InlineKeyboardButton("⚡ تشغيل", callback_data='bot_on'))
    markup.add(types.InlineKeyboardButton("🔙", callback_data='back_to_main'))
    safe_answer(call.id)
    safe_edit(call.message.chat.id, call.message.message_id,
              f"⚡ البوت: {'✅' if bot_running else '⏸️'}", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data in ['bot_on', 'bot_off'])
def cb_bot_toggle(call):
    global bot_running
    if not is_admin(call.from_user.id): return
    bot_running = (call.data == 'bot_on')
    if not bot_running:
        for cid in list(active_processes.keys()):
            stop_all_for_chat(cid)
    safe_answer(call.id, "✅"); cb_bot_status(call)

@bot.callback_query_handler(func=lambda c: c.data == 'users')
def cb_users(call):
    if not is_admin(call.from_user.id): return
    a, p = get_stats()
    pending = get_pending()
    markup = types.InlineKeyboardMarkup()
    for uid, fname, uname in pending:
        fn = (fname or 'مستخدم')[:15]
        markup.row(
            types.InlineKeyboardButton(f"✅ {fn}", callback_data=f'ap_{uid}'),
            types.InlineKeyboardButton(f"❌ {fn}", callback_data=f'rj_{uid}'))
    markup.add(types.InlineKeyboardButton("🔙", callback_data='back_to_main'))
    safe_answer(call.id)
    safe_edit(call.message.chat.id, call.message.message_id,
              f"👥 المعتمدون: {a}\n⏳ الانتظار: {p}", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data.startswith('ap_'))
def cb_approve(call):
    if not is_admin(call.from_user.id): return
    try:
        uid = int(call.data.split('_')[1])
        add_approved(uid, 'USER'); safe_answer(call.id, "✅")
        try: bot.send_message(uid, "🎉 تمت الموافقة! أرسل /start")
        except: pass
    except: pass

@bot.callback_query_handler(func=lambda c: c.data.startswith('rj_'))
def cb_reject(call):
    if not is_admin(call.from_user.id): return
    try:
        uid = int(call.data.split('_')[1])
        remove_pending(uid); safe_answer(call.id, "❌")
    except: pass

@bot.message_handler(commands=['rck'])
def cmd_broadcast(message):
    if not is_admin(message.from_user.id): return
    try:
        msg = message.text.split(' ', 1)[1]
        with sqlite3.connect('bot_data.db', timeout=15) as conn:
            c = conn.cursor()
            c.execute('SELECT user_id FROM approved_users')
            users = [r[0] for r in c.fetchall()]
        ok, fail = 0, 0
        for uid in users:
            try: bot.send_message(uid, msg); ok += 1
            except: fail += 1
        safe_send(message.chat.id, f"📊 نجح: {ok}, فشل: {fail}")
    except:
        safe_send(message.chat.id, "❌ استخدم: /rck الرسالة")

# ============================================================
# Cleanup
# ============================================================
def cleanup_all_processes():
    try:
        for chat_id in list(active_processes.keys()):
            for file_id in list(active_processes[chat_id].keys()):
                info = active_processes[chat_id].get(file_id, {})
                proc = info.get('process')
                if proc and proc.poll() is None:
                    try:
                        proc.terminate(); proc.wait(timeout=3)
                    except:
                        try: proc.kill()
                        except: pass
    except: pass

def signal_handler(sig, frame):
    cleanup_all_processes(); sys.exit(0)

atexit.register(cleanup_all_processes)
try:
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
except: pass

# ============================================================
# التشغيل
# ============================================================
if __name__ == "__main__":
    print("=" * 55)
    print("🚀 Bot starting...")
    
    # ✅ تحذير بخصوص إصدار بايثون
    if sys.version_info >= (3, 13):
        print("⚠️ WARNING: Python 3.13 detected. Pyrogram may have compatibility issues!")
        print("⚠️ Please consider using Python 3.10 or 3.11 for the host environment.")
    
    print("=" * 55)

    auto_install_packages()

    for _ in range(3):
        try: bot.remove_webhook(); break
        except: time.sleep(1)

    try: bot.get_updates(offset=-1, timeout=1)
    except: pass

    ALLOWED_UPDATES = [
        "message", "edited_message", "channel_post", "edited_channel_post",
        "inline_query", "callback_query", "pre_checkout_query", "poll",
        "poll_answer", "my_chat_member", "chat_member", "chat_join_request",
    ]

    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60,
                                 skip_pending=False, allowed_updates=ALLOWED_UPDATES)
        except KeyboardInterrupt:
            cleanup_all_processes(); break
        except: time.sleep(5)
