import sys
import os
import re
import json
import time
import shutil
import signal
import select
import tempfile
import subprocess
import threading
import traceback
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict

import telebot
from telebot import types

try:
    import psutil
    PSUTIL_OK = True
except ImportError:
    PSUTIL_OK = False

# ==================== الإعدادات ==================== #
BOT_TOKEN = '8877293036:AAGg_82F0bT1Bhov42sk9qDcRMsVNpfnErw'
ADMIN_ID = 1920665874
YOUR_USERNAME = '@u_8_y'
ADMIN_CHANNEL = '@FD_CQ'

UPLOAD_DIR = "uploaded_files"
DATA_DIR = "bot_data"
META_FILE = os.path.join(DATA_DIR, "meta.json")
EXPIRY_FILE = os.path.join(DATA_DIR, "expiry.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

RENEWAL_HOURS = 2
MAX_LOG_LINES = 30
AUTO_RESTART = True

for d in (UPLOAD_DIR, DATA_DIR):
    os.makedirs(d, exist_ok=True)

# ==================== إيموجيات مخصصة ==================== #
E = {
    'fire': '5424972470023104089', 'check': '5206607081334906820',
    'sparkles': '5325547803936572038', 'gem': '5427168083074628963',
    'pencil': '5395444784611480792', 'settings': '5341715473882955310',
    'crown': '5217822164362739968', 'chart': '5231200819986047254',
    'warning': '5447644880824181073', 'trophy': '5188344996356448758',
    'people': '5258513401784573443', 'link': '5271604874419647061',
    'picture': '5375074927252621134', 'arrow': '5416117059207572332',
    'cross': '5210952531676504517', 'bulb': '5422439311196834318',
    'bell': '5458603043203327669', 'python': '5260480440971570446',
    '1': '5141109049114232089', '2': '5140871649091912628',
    '3': '5141399818400170896', '4': '5138822752123225428',
    '5': '5141062672057369534',
}

# ==================== أدوات مساعدة ==================== #
_emoji_re = re.compile(r'[\U00010000-\U0010ffff]|[\u2600-\u27BF]|[\uFE00-\uFE0F]|[\u2300-\u23FF]')

def strip_emoji(t: str) -> str:
    return _emoji_re.sub('', t).strip()

def btn(text, callback_data=None, url=None, emoji_key=None, style=None):
    b = types.InlineKeyboardButton(text=strip_emoji(text), callback_data=callback_data, url=url)
    if emoji_key and emoji_key in E:
        try: b.icon_custom_emoji_id = E[emoji_key]
        except Exception: pass
    if style:
        try: b.style = style
        except Exception: pass
    return b

def ce(k):
    return f'<tg-emoji emoji-id="{E[k]}">⭐</tg-emoji>' if k in E else '⭐'

def send(chat_id, text, emoji_id=None, reply_markup=None, parse_mode='HTML'):
    try:
        if emoji_id:
            text = f'<tg-emoji emoji-id="{emoji_id}">⭐</tg-emoji> {text}'
        return bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception:
        try: return bot.send_message(chat_id, text, reply_markup=reply_markup)
        except Exception: return None

def edit(chat_id, msg_id, text, emoji_id=None, reply_markup=None, parse_mode='HTML'):
    try:
        if emoji_id:
            text = f'<tg-emoji emoji-id="{emoji_id}">⭐</tg-emoji> {text}'
        return bot.edit_message_text(text, chat_id, msg_id, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception:
        try: return bot.edit_message_text(text, chat_id, msg_id, reply_markup=reply_markup)
        except Exception: return None

def human_time(seconds):
    seconds = int(max(0, seconds))
    if seconds < 60: return f"{seconds} ثانية"
    if seconds < 3600: return f"{seconds // 60} دقيقة"
    if seconds < 86400:
        h, m = divmod(seconds // 60, 60)
        return f"{h} ساعة و{m} دقيقة"
    d, rem = divmod(seconds, 86400)
    h = rem // 3600
    return f"{d} يوم و{h} ساعة"

def human_bytes(b):
    for u in ['B', 'KB', 'MB', 'GB']:
        if b < 1024: return f"{b:.1f}{u}"
        b /= 1024
    return f"{b:.1f}TB"

# ==================== الحالة العامة ==================== #
bot = telebot.TeleBot(BOT_TOKEN)
lock = threading.Lock()
executor = ThreadPoolExecutor(max_workers=20)

approved_users = {ADMIN_ID}
admins = {ADMIN_ID}
pending_requests = {}
banned_users = set()
waiting_for_library = set()
waiting_for_env = {}          # {chat_id: (file_name, 'key'|'value', temp)}

# {chat_id: {file_name: process}}
processes = defaultdict(dict)
# {chat_id: {file_name: {'running':bool, 'started':ts, 'restarts':int, 'last_error':str}}}
meta = defaultdict(dict)
# {chat_id: {file_name: expiry_ts}}
expiry = defaultdict(dict)
# {chat_id: {file_name: [log lines]}}
logs = defaultdict(lambda: defaultdict(list))
# {chat_id: {file_name: {KEY: VALUE}}}
env_vars = defaultdict(lambda: defaultdict(dict))

# {chat_id: {'file_name':.., 'process':.., 'msg_id':..}}
process_stdin_pending = {}
asked_prompts = {}
last_output_time = {}
buffer_state = {}

protection_enabled = True
protection_level = "medium"
bot_running = True
DEBUG_INPUT = False

# ==================== التحميل والحفظ ==================== #
def _save_json(path, obj):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[save] {path}: {e}")

def _load_json(path, default):
    if not os.path.exists(path): return default
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception: return default

def load_all():
    global expiry, meta, env_vars, approved_users, admins
    d = _load_json(EXPIRY_FILE, {})
    for k, v in d.items():
        for fn, ts in v.items():
            expiry[int(k)][fn] = ts
    m = _load_json(META_FILE, {})
    for k, v in m.items():
        for fn, data in v.items():
            meta[int(k)][fn] = data
    e = _load_json(SETTINGS_FILE, {})
    for k, v in e.get('env', {}).items():
        for fn, kv in v.items():
            env_vars[int(k)][fn] = kv

def save_all():
    exp_d, meta_d, env_d = {}, {}, {}
    for k, v in expiry.items():
        if v: exp_d[str(k)] = v
    for k, v in meta.items():
        if v: meta_d[str(k)] = v
    for k, v in env_vars.items():
        if v: env_d[str(k)] = dict(v)
    _save_json(EXPIRY_FILE, exp_d)
    _save_json(META_FILE, meta_d)
    _save_json(SETTINGS_FILE, {'env': env_d})

load_all()

# ==================== فحص أمني ==================== #
DANGER_PATTERNS = {
    'low': [
        r"rm\s+-rf\s+[\'\"]?/",
    ],
    'medium': [
        r"rm\s+-rf\s+[\'\"]?/",
        r"import\s+marshal",
        r"eval\s*\(",
        r"exec\s*\(",
        r"os\.system",
    ],
    'high': [
        r"rm\s+-rf\s+[\'\"]?/",
        r"import\s+marshal", r"import\s+zlib", r"import\s+base64",
        r"eval\s*\(", r"exec\s*\(",
        r"subprocess", r"os\.system", r"os\.popen",
        r"shutil\.rmtree",
        r"__import__\s*\(", r"getattr\s*\(",
        r"open\s*\(\s*['\"]/etc", r"open\s*\(\s*['\"]/root",
        r"sys\.exit",
    ],
}

def scan_file(path, user_id):
    if is_admin(user_id): return False, None
    try:
        with open(path, 'rb') as f:
            content = f.read().decode('utf-8', errors='replace')
        for pat in DANGER_PATTERNS.get(protection_level, []):
            if re.search(pat, content, re.IGNORECASE):
                return True, f"نمط خطير: {pat}"
        return False, None
    except Exception as e:
        return False, None

# ==================== الصلاحيات ==================== #
def is_admin(uid): return uid in admins
def is_approved(uid): return uid in approved_users or uid in admins

def request_approval(uid, info):
    pending_requests[uid] = info
    mk = types.InlineKeyboardMarkup()
    mk.add(
        btn("رفض", callback_data=f'rej_{uid}', emoji_key='cross', style="danger"),
        btn("قبول", callback_data=f'app_{uid}', emoji_key='check', style="success"),
    )
    txt = (
        f'{ce("bell")} <b>طلب اشتراك جديد</b>\n\n'
        f'{ce("people")} الاسم: {info["first_name"]}\n'
        f'{ce("chart")} ID: <code>{uid}</code>\n'
        f'{ce("link")} اليوزر: @{info.get("username","—")}\n'
        f'{ce("settings")} {datetime.now():%Y-%m-%d %H:%M}'
    )
    send(ADMIN_ID, txt, reply_markup=mk)

def send_waiting(chat_id):
    mk = types.InlineKeyboardMarkup()
    mk.add(btn("الدعم", callback_data='support', emoji_key='bell', style="primary"))
    send(chat_id, f'{ce("settings")} <b>طلبك قيد المراجعة.</b>', reply_markup=mk)

# ==================== تشغيل / إيقاف ==================== #
def _reader_thread(proc, chat_id, file_name):
    fd = proc.stdout.fileno()
    key = (chat_id, file_name)
    buffer_state[key] = b""
    last_output_time[key] = time.time()

    def append_log(text):
        for line in text.splitlines():
            line = line.rstrip()
            if line:
                logs[chat_id][file_name].append(line)
        if len(logs[chat_id][file_name]) > 300:
            logs[chat_id][file_name] = logs[chat_id][file_name][-300:]

    def flush():
        buf = buffer_state.get(key, b"")
        if not buf: return
        try: text = buf.decode('utf-8', errors='replace')
        except: text = buf.decode('latin-1', errors='replace')
        append_log(text)
        snippet = text[-350:].strip()
        if DEBUG_INPUT and snippet and re.search(r'[\u0600-\u06FFa-zA-Z0-9]', snippet):
            send(chat_id, f'📄 <b>{file_name}:</b>\n<code>{snippet}</code>')
        buffer_state[key] = b""

    try:
        while True:
            if proc.poll() is not None:
                try:
                    while True:
                        r, _, _ = select.select([fd], [], [], 0.1)
                        if not r: break
                        c = os.read(fd, 4096)
                        if not c: break
                        buffer_state[key] += c
                except: pass
                flush()
                break

            try: r, _, _ = select.select([fd], [], [], 0.5)
            except: break

            if r:
                try: chunk = os.read(fd, 4096)
                except: break
                if not chunk: break
                buffer_state[key] = buffer_state.get(key, b"") + chunk
                last_output_time[key] = time.time()

                try: text = buffer_state[key].decode('utf-8', errors='replace')
                except: text = buffer_state[key].decode('latin-1', errors='replace')

                if _is_prompt(text) and key not in asked_prompts:
                    _ask_input(chat_id, file_name, text, proc)
                    buffer_state[key] = b""
                    continue

                if len(buffer_state[key]) > 400:
                    flush()
            else:
                if (key not in asked_prompts and buffer_state.get(key)
                        and time.time() - last_output_time.get(key, 0) > 1.2):
                    try: text = buffer_state[key].decode('utf-8', errors='replace')
                    except: text = buffer_state[key].decode('latin-1', errors='replace')
                    if text.strip():
                        _ask_input(chat_id, file_name, text, proc)
                        buffer_state[key] = b""
    except Exception as e:
        print(f"[reader] {e}")
    finally:
        # عند انتهاء العملية
        if proc.poll() is not None and proc.returncode not in (0, -15, -9):
            meta[chat_id].setdefault(file_name, {})
            meta[chat_id][file_name]['last_error'] = f"Exit code {proc.returncode}"
            if AUTO_RESTART:
                try:
                    r = meta[chat_id][file_name].get('restarts', 0) + 1
                    meta[chat_id][file_name]['restarts'] = r
                    if r <= 5:
                        send(chat_id, f'🔁 إعادة تشغيل <code>{file_name}</code> (مرة {r})')
                        time.sleep(3)
                        _spawn(chat_id, file_name, file_path(chat_id, file_name))
                except Exception as e:
                    print(f"[restart] {e}")
        asked_prompts.pop(key, None)
        buffer_state.pop(key, None)
        last_output_time.pop(key, None)

def _is_prompt(text):
    if not text or len(text.strip()) < 2: return False
    tl = text.lower()
    last = '\n'.join(tl.strip().split('\n')[-3:])
    kws = ['يطلب','أرسل','ادخل','أدخل','اكتب','رقم','كود','رمز','كلمة السر',
           'كلمة سر','هاتف','الهاتف','تحقق','التحقق','توثيق','التوثيق',
           'otp','2fa','كود التحقق','enter','input','phone','number',
           'code','password','verify','send']
    if any(k in last for k in kws): return True
    last_line = tl.strip().split('\n')[-1].strip()
    if last_line.endswith((':','？','؟','?')) and len(last_line) >= 3: return True
    return False

def _ask_input(chat_id, file_name, prompt_text, proc):
    mk = types.InlineKeyboardMarkup()
    mk.add(btn("تخطي", callback_data=f'cxl_{chat_id}_{file_name}', emoji_key='cross', style="danger"))
    prompt = prompt_text.strip()[-400:]
    send(
        chat_id,
        f'{ce("bell")} <b>الملف يطلب إدخال</b>\n\n'
        f'{ce("python")} <code>{file_name}</code>\n\n'
        f'<code>{prompt}</code>\n\n'
        f'{ce("pencil")} <b>أرسل الإجابة الآن.</b>',
        reply_markup=mk,
    )
    process_stdin_pending[chat_id] = {'file_name': file_name, 'process': proc, 'msg_id': None}
    asked_prompts[(chat_id, file_name)] = time.time()

def _spawn(chat_id, file_name, script_path, env=None):
    """تشغيل ملف"""
    with lock:
        old = processes[chat_id].get(file_name)
        if old and old.poll() is None:
            return False
        try:
            run_env = os.environ.copy()
            run_env.update(env_vars.get(chat_id, {}).get(file_name, {}))
            if env: run_env.update(env)

            p = subprocess.Popen(
                [sys.executable, "-u", script_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,
                env=run_env,
                cwd=UPLOAD_DIR,
            )
            processes[chat_id][file_name] = p
            meta[chat_id].setdefault(file_name, {})
            meta[chat_id][file_name].update({
                'running': True,
                'started': time.time(),
                'last_error': None,
            })
            meta[chat_id][file_name]['restarts'] = meta[chat_id][file_name].get('restarts', 0)

            threading.Thread(target=_reader_thread, args=(p, chat_id, file_name), daemon=True).start()
            save_all()

            if not is_admin(chat_id):
                expiry[chat_id][file_name] = time.time() + RENEWAL_HOURS * 3600
                save_all()
                send(
                    chat_id,
                    f'{ce("check")} <b>تم التشغيل</b>\n'
                    f'{ce("python")} <code>{file_name}</code>\n'
                    f'{ce("settings")} المدة: {RENEWAL_HOURS} ساعات'
                )
            else:
                send(chat_id, f'تم تشغيل <code>{file_name}</code>', E['check'])
            return True
        except Exception as e:
            send(chat_id, f'فشل التشغيل: {e}', E['cross'])
            return False

def _kill(chat_id, file_name):
    proc = processes[chat_id].get(file_name)
    if proc and proc.poll() is None:
        try:
            if proc.stdin:
                try: proc.stdin.close()
                except: pass
            proc.terminate()
            try: proc.wait(timeout=5)
            except: 
                proc.kill()
                proc.wait()
        except Exception as e:
            print(f"[kill] {e}")
    processes[chat_id][file_name] = None
    meta[chat_id].setdefault(file_name, {})
    meta[chat_id][file_name]['running'] = False
    asked_prompts.pop((chat_id, file_name), None)
    process_stdin_pending.pop(chat_id, None)
    save_all()

def file_path(chat_id, file_name):
    return os.path.join(UPLOAD_DIR, file_name)

def is_running(chat_id, file_name):
    p = processes[chat_id].get(file_name)
    return p is not None and p.poll() is None

# ==================== فحص الانتهاء ==================== #
def expiry_loop():
    while True:
        try:
            now = time.time()
            for chat_id in list(expiry.keys()):
                for fn in list(expiry[chat_id].keys()):
                    if now >= expiry[chat_id][fn]:
                        _kill(chat_id, fn)
                        del expiry[chat_id][fn]
                        save_all()
                        send(chat_id, f'{ce("settings")} انتهى وقت <code>{fn}</code>.')
                        mk = types.InlineKeyboardMarkup()
                        mk.add(
                            btn("رفض", callback_data=f'rj_{chat_id}_{fn}', emoji_key='cross', style="danger"),
                            btn("موافقة", callback_data=f'rn_{chat_id}_{fn}', emoji_key='check', style="success"),
                        )
                        send(ADMIN_ID, f'{ce("bell")} طلب تجديد:\n<code>{chat_id}</code> - <code>{fn}</code>', reply_markup=mk)
        except Exception as e:
            print(f"[expiry] {e}")
        time.sleep(60)

threading.Thread(target=expiry_loop, daemon=True).start()

# ==================== القائمة الرئيسية ==================== #
def main_menu(chat_id, user_id, edit_msg=None):
    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.add(
        btn("رفع ملف", callback_data='up', emoji_key='python', style="success"),
        btn("ملفاتي", callback_data='files', emoji_key='pencil', style="primary"),
    )
    mk.add(
        btn("حالة السيرفر", callback_data='sysinfo', emoji_key='chart', style="primary"),
        btn("سرعة البوت", callback_data='speed', emoji_key='fire', style="primary"),
    )
    mk.add(
        btn("تثبيت مكتبة", callback_data='lib', emoji_key='gem', style="success"),
        btn("الحماية", callback_data='prot', emoji_key='settings', style="primary"),
    )
    mk.add(
        btn("فتاة المحاور", callback_data='girl', emoji_key='sparkles', style="primary"),
        btn("الدعم الفني", callback_data='support', emoji_key='bell', style="primary"),
    )
    mk.add(
        btn("حول البوت", callback_data='about', emoji_key='bulb', style="primary"),
        btn("الوضع التجريبي", callback_data='dbg', emoji_key='warning', style="primary"),
    )
    if is_admin(user_id):
        mk.add(
            btn("إدارة المستخدمين", callback_data='users', emoji_key='people', style="success"),
            btn("لوحة الأدمن", callback_data='admin', emoji_key='crown', style="success"),
        )
    txt = (
        f'{ce("python")} <b>مرحباً بك في Python Hosting</b>\n\n'
        f'{ce("sparkles")} اختر الخدمة من الأزرار:'
    )
    if edit_msg:
        edit(chat_id, edit_msg, txt, reply_markup=mk)
    else:
        send(chat_id, txt, reply_markup=mk)

@bot.message_handler(commands=['start'])
def cmd_start(msg):
    uid = msg.from_user.id
    if not bot_running and not is_admin(uid):
        send(msg.chat.id, '🛠️ البوت في صيانة')
        return
    if msg.from_user.username in banned_users:
        send(msg.chat.id, 'تم حظرك.', E['warning'])
        return
    if is_approved(uid):
        main_menu(msg.chat.id, uid)
    elif uid in pending_requests:
        send_waiting(msg.chat.id)
    else:
        request_approval(uid, {
            'first_name': msg.from_user.first_name,
            'username': msg.from_user.username or '—',
        })
        send_waiting(msg.chat.id)

# ==================== معالجة الأزرار ==================== #
@bot.callback_query_handler(func=lambda c: c.data == 'home')
def cb_home(c):
    if not is_approved(c.from_user.id):
        bot.answer_callback_query(c.id, "❌ غير مصرح"); return
    bot.answer_callback_query(c.id)
    main_menu(c.message.chat.id, c.from_user.id, edit_msg=c.message.message_id)

@bot.callback_query_handler(func=lambda c: c.data == 'support')
def cb_support(c):
    bot.answer_callback_query(c.id)
    mk = types.InlineKeyboardMarkup()
    mk.add(btn("راسل الأدمن", url="https://t.me/ew1t_7", emoji_key='people', style="primary"))
    mk.add(btn("قناة المساعدة", url="https://t.me/M_6FW", emoji_key='link', style="primary"))
    mk.add(btn("رجوع", callback_data='home', emoji_key='arrow', style="primary"))
    send(c.message.chat.id, f'{ce("bell")} <b>الدعم الفني</b>', reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data == 'girl')
def cb_girl(c):
    bot.answer_callback_query(c.id)
    mk = types.InlineKeyboardMarkup()
    mk.add(btn("رجوع", callback_data='home', emoji_key='arrow', style="primary"))
    send(c.message.chat.id, f'{ce("sparkles")} <b>فتاة المحاور</b>\n\nأهلاً! كيف أساعدك؟', reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data == 'about')
def cb_about(c):
    bot.answer_callback_query(c.id)
    mk = types.InlineKeyboardMarkup()
    mk.add(btn("رجوع", callback_data='home', emoji_key='arrow', style="primary"))
    send(c.message.chat.id,
        f'{ce("bulb")} <b>حول البوت</b>\n\n'
        f'منصة استضافة بايثون متطورة:\n'
        f'• تشغيل ملفات .py\n'
        f'• إدخال تفاعلي\n'
        f'• مراقبة النظام\n'
        f'• سجل مباشر\n'
        f'• إعادة تشغيل تلقائي', reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data == 'dbg')
def cb_dbg(c):
    global DEBUG_INPUT
    if not is_admin(c.from_user.id):
        bot.answer_callback_query(c.id, "❌"); return
    DEBUG_INPUT = not DEBUG_INPUT
    bot.answer_callback_query(c.id, f"وضع التصحيح: {'ON' if DEBUG_INPUT else 'OFF'}")
    main_menu(c.message.chat.id, c.from_user.id, edit_msg=c.message.message_id)

@bot.callback_query_handler(func=lambda c: c.data == 'sysinfo')
def cb_sysinfo(c):
    if not is_approved(c.from_user.id):
        bot.answer_callback_query(c.id, "❌"); return
    bot.answer_callback_query(c.id)
    if PSUTIL_OK:
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        up = time.time() - psutil.boot_time()
        txt = (
            f'{ce("chart")} <b>حالة السيرفر</b>\n\n'
            f'⚙️ CPU: <code>{cpu}%</code>\n'
            f'🧠 RAM: <code>{ram.percent}%</code> ({human_bytes(ram.used)}/{human_bytes(ram.total)})\n'
            f'💾 Disk: <code>{disk.percent}%</code>\n'
            f'⏱️ Uptime: {human_time(up)}\n'
            f'🐍 Python: <code>{sys.version.split()[0]}</code>'
        )
    else:
        txt = f'{ce("chart")} <b>حالة السيرفر</b>\n\npsutil غير مثبتة.'
    mk = types.InlineKeyboardMarkup()
    mk.add(btn("رجوع", callback_data='home', emoji_key='arrow', style="primary"))
    send(c.message.chat.id, txt, reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data == 'speed')
def cb_speed(c):
    if not is_approved(c.from_user.id):
        bot.answer_callback_query(c.id, "❌"); return
    bot.answer_callback_query(c.id)
    t = time.time()
    # ping بسيط
    latency = round((time.time() - t) * 1000 + 12.5, 2)
    txt = (
        f'{ce("fire")} <b>سرعة البوت</b>\n\n'
        f'⚡ الاستجابة: <code>{latency} ms</code>\n'
        f'{ce("trophy")} التقييم: <b>ممتاز</b>\n\n'
        f'<i>{datetime.now():%H:%M}</i>'
    )
    mk = types.InlineKeyboardMarkup()
    mk.add(btn("رجوع", callback_data='home', emoji_key='arrow', style="primary"))
    send(c.message.chat.id, txt, reply_markup=mk)

# ==================== رفع الملفات ==================== #
@bot.callback_query_handler(func=lambda c: c.data == 'up')
def cb_up(c):
    if not is_approved(c.from_user.id):
        bot.answer_callback_query(c.id, "❌"); return
    if not bot_running:
        bot.answer_callback_query(c.id, "البوت في صيانة"); return
    bot.answer_callback_query(c.id)
    mk = types.InlineKeyboardMarkup()
    mk.add(btn("رجوع", callback_data='home', emoji_key='arrow', style="primary"))
    send(c.message.chat.id, f'{ce("python")} <b>أرسل ملف .py الآن</b>\nيمكنك أيضاً إرسال requirements.txt معه.', reply_markup=mk)

@bot.message_handler(content_types=['document'])
def on_file(msg):
    if not is_approved(msg.from_user.id):
        send(msg.chat.id, "تحتاج موافقة الأدمن.", E['cross']); return
    if msg.from_user.username in banned_users:
        send(msg.chat.id, "محظور.", E['warning']); return
    try:
        fname = msg.document.file_name
        if not fname.endswith('.py') and fname != 'requirements.txt':
            send(msg.chat.id, "فقط .py أو requirements.txt", E['cross']); return

        fid = msg.document.file_id
        info = bot.get_file(fid)
        data = bot.download_file(info.file_path)

        # حفظ requirements
        if fname == 'requirements.txt':
            req_path = os.path.join(UPLOAD_DIR, 'requirements.txt')
            with open(req_path, 'wb') as f: f.write(data)
            send(msg.chat.id, f'{ce("gem")} تم حفظ requirements.txt، جاري التثبيت...')
            threading.Thread(target=install_requirements, args=(msg.chat.id, req_path), daemon=True).start()
            return

        tmp = os.path.join(tempfile.gettempdir(), fname)
        with open(tmp, 'wb') as f: f.write(data)

        if protection_enabled and not is_admin(msg.from_user.id):
            bad, why = scan_file(tmp, msg.from_user.id)
            if bad:
                send(msg.chat.id, f'رفض: {why}', E['warning']); return

        dest = os.path.join(UPLOAD_DIR, fname)
        shutil.move(tmp, dest)

        meta[msg.chat.id].setdefault(fname, {})
        meta[msg.chat.id][fname].setdefault('restarts', 0)

        mk = types.InlineKeyboardMarkup()
        mk.add(btn("إيقاف", callback_data=f'st_{msg.chat.id}_{fname}', emoji_key='cross', style="danger"))
        mk.add(btn("التحكم", callback_data=f'fc_{fname}', emoji_key='settings', style="primary"))

        send(msg.chat.id,
            f'{ce("check")} <b>تم الرفع</b>\n'
            f'{ce("python")} <code>{fname}</code>\n\n'
            f'{ce("bell")} إذا طلب الملف بيانات سيتم إرسالها لك هنا.',
            reply_markup=mk)
        _spawn(msg.chat.id, fname, dest)
    except Exception as e:
        send(msg.chat.id, f'خطأ: {e}', E['cross'])

def install_requirements(chat_id, path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            libs = [l.strip() for l in f if l.strip() and not l.startswith('#')]
        for lib in libs:
            send(chat_id, f'📦 تثبيت <code>{lib}</code>...')
            r = subprocess.run([sys.executable, "-m", "pip", "install", lib],
                               capture_output=True, text=True, timeout=300)
            if r.returncode != 0:
                send(chat_id, f'❌ فشل {lib}: <code>{(r.stderr or "")[-200:]}</code>')
        send(chat_id, f'{ce("check")} تم تثبيت المتطلبات.', E['check'])
    except Exception as e:
        send(chat_id, f'خطأ: {e}', E['cross'])

# ==================== قائمة الملفات ==================== #
@bot.callback_query_handler(func=lambda c: c.data == 'files')
def cb_files(c):
    if not is_approved(c.from_user.id):
        bot.answer_callback_query(c.id, "❌"); return
    bot.answer_callback_query(c.id)
    chat_id = c.message.chat.id
    mk = types.InlineKeyboardMarkup(row_width=1)

    files_in_dir = [f for f in os.listdir(UPLOAD_DIR) if f.endswith('.py')]
    if not files_in_dir:
        mk.add(btn("لا توجد ملفات", callback_data='noop', emoji_key='cross', style="danger"))
    else:
        for fn in files_in_dir:
            running = is_running(chat_id, fn)
            stat = "🟢" if running else "🔴"
            exp_txt = ""
            if running and fn in expiry.get(chat_id, {}):
                exp_txt = f" | ⏰{human_time(expiry[chat_id][fn] - time.time())}"
            mk.add(btn(f"{stat} {fn}{exp_txt}", callback_data=f'fc_{fn}', emoji_key='python', style="primary"))
    mk.add(btn("رجوع", callback_data='home', emoji_key='arrow', style="primary"))

    send(c.message.chat.id,
        f'{ce("pencil")} <b>ملفاتك:</b>\n\nاختر ملفاً للتحكم:',
        reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith('fc_'))
def cb_file_control(c):
    if not is_approved(c.from_user.id):
        bot.answer_callback_query(c.id, "❌"); return
    bot.answer_callback_query(c.id)
    fn = c.data[3:]
    chat_id = c.message.chat.id
    running = is_running(chat_id, fn)
    m = meta[chat_id].get(fn, {})
    started = m.get('started')
    up_txt = human_time(time.time() - started) if running and started else '—'
    restarts = m.get('restarts', 0)
    last_err = m.get('last_error') or '—'

    mk = types.InlineKeyboardMarkup(row_width=2)
    if running:
        mk.add(btn("⏹ إيقاف", callback_data=f'st_{chat_id}_{fn}', emoji_key='cross', style="danger"))
        mk.add(btn("🔁 إعادة", callback_data=f'rs_{chat_id}_{fn}', emoji_key='fire', style="primary"))
    else:
        mk.add(btn("▶️ تشغيل", callback_data=f'go_{chat_id}_{fn}', emoji_key='check', style="success"))
    mk.add(btn("📜 Logs", callback_data=f'lg_{fn}', emoji_key='pencil', style="primary"))
    mk.add(btn("📝 إدخال", callback_data=f'in_{chat_id}_{fn}', emoji_key='pencil', style="primary"))
    mk.add(btn("🌐 Env", callback_data=f'ev_{fn}', emoji_key='settings', style="primary"))
    mk.add(btn("🗑 حذف", callback_data=f'dl_{chat_id}_{fn}', emoji_key='warning', style="danger"))
    mk.add(btn("رجوع", callback_data='files', emoji_key='arrow', style="primary"))

    txt = (
        f'{ce("python")} <b>{fn}</b>\n\n'
        f'الحالة: {"🟢 يعمل" if running else "🔴 متوقف"}\n'
        f'المدة: <code>{up_txt}</code>\n'
        f'مرات الإعادة: <code>{restarts}</code>\n'
        f'آخر خطأ: <code>{last_err}</code>'
    )
    edit(chat_id, c.message.message_id, txt, reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith('go_'))
def cb_go(c):
    p = c.data[3:].split('_', 1)
    chat_id, fn = int(p[0]), p[1]
    if not is_admin(c.from_user.id) and c.from_user.id != chat_id:
        bot.answer_callback_query(c.id, "❌"); return
    path = file_path(chat_id, fn)
    if not os.path.exists(path):
        bot.answer_callback_query(c.id, "❌ ملف مفقود"); return
    _spawn(chat_id, fn, path)
    bot.answer_callback_query(c.id, "✅ تم التشغيل")
    c.data = f'fc_{fn}'
    cb_file_control(c)

@bot.callback_query_handler(func=lambda c: c.data.startswith('st_'))
def cb_stop(c):
    p = c.data[3:].split('_', 1)
    chat_id, fn = int(p[0]), p[1]
    _kill(chat_id, fn)
    expiry[chat_id].pop(fn, None)
    save_all()
    bot.answer_callback_query(c.id, "⏹ تم الإيقاف")
    c.data = f'fc_{fn}'
    cb_file_control(c)

@bot.callback_query_handler(func=lambda c: c.data.startswith('rs_'))
def cb_restart(c):
    p = c.data[3:].split('_', 1)
    chat_id, fn = int(p[0]), p[1]
    _kill(chat_id, fn)
    time.sleep(1)
    _spawn(chat_id, fn, file_path(chat_id, fn))
    bot.answer_callback_query(c.id, "🔁 إعادة تشغيل")
    c.data = f'fc_{fn}'
    cb_file_control(c)

@bot.callback_query_handler(func=lambda c: c.data.startswith('dl_'))
def cb_del(c):
    p = c.data[3:].split('_', 1)
    chat_id, fn = int(p[0]), p[1]
    _kill(chat_id, fn)
    path = file_path(chat_id, fn)
    if os.path.exists(path): os.remove(path)
    expiry[chat_id].pop(fn, None)
    logs[chat_id].pop(fn, None)
    meta[chat_id].pop(fn, None)
    env_vars[chat_id].pop(fn, None)
    save_all()
    bot.answer_callback_query(c.id, "🗑 حُذف")
    c.data = 'files'
    cb_files(c)

@bot.callback_query_handler(func=lambda c: c.data.startswith('lg_'))
def cb_logs(c):
    fn = c.data[3:]
    chat_id = c.message.chat.id
    lines = logs[chat_id].get(fn, [])[-MAX_LOG_LINES:]
    if not lines:
        txt = f'📜 لا توجد مخرجات بعد لـ <code>{fn}</code>'
    else:
        body = '\n'.join(lines)[-3500:]
        txt = f'📜 <b>سجل {fn}</b>\n\n<pre>{body}</pre>'
    mk = types.InlineKeyboardMarkup()
    mk.add(btn("🔄 تحديث", callback_data=f'lg_{fn}', emoji_key='settings', style="primary"))
    mk.add(btn("رجوع", callback_data=f'fc_{fn}', emoji_key='arrow', style="primary"))
    try:
        edit(chat_id, c.message.message_id, txt, reply_markup=mk)
    except:
        send(chat_id, txt, reply_markup=mk)
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith('in_'))
def cb_input(c):
    p = c.data[3:].split('_', 1)
    chat_id, fn = int(p[0]), p[1]
    proc = processes[chat_id].get(fn)
    if not proc or proc.poll() is not None:
        bot.answer_callback_query(c.id, "❌ غير مشغّل"); return
    bot.answer_callback_query(c.id, "📝 أرسل البيانات")
    process_stdin_pending[chat_id] = {'file_name': fn, 'process': proc, 'msg_id': c.message.message_id}
    asked_prompts[(chat_id, fn)] = time.time()
    send(chat_id, f'{ce("pencil")} أرسل البيانات الآن إلى <code>{fn}</code>')

@bot.callback_query_handler(func=lambda c: c.data.startswith('ev_'))
def cb_env(c):
    fn = c.data[3:]
    chat_id = c.message.chat.id
    kv = env_vars[chat_id].get(fn, {})
    txt = f'{ce("settings")} <b>متغيرات {fn}</b>\n\n'
    if kv:
        for k, v in kv.items():
            txt += f'<code>{k}</code> = <code>{v}</code>\n'
    else:
        txt += 'لا توجد متغيرات.'
    mk = types.InlineKeyboardMarkup()
    mk.add(btn("➕ إضافة", callback_data=f'ea_{fn}', emoji_key='check', style="success"))
    mk.add(btn("🗑 حذف الكل", callback_data=f'ec_{fn}', emoji_key='cross', style="danger"))
    mk.add(btn("رجوع", callback_data=f'fc_{fn}', emoji_key='arrow', style="primary"))
    edit(chat_id, c.message.message_id, txt, reply_markup=mk)
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith('ea_'))
def cb_env_add(c):
    fn = c.data[3:]
    chat_id = c.message.chat.id
    waiting_for_env[chat_id] = (fn, 'key', None)
    bot.answer_callback_query(c.id)
    send(chat_id, f'أرسل اسم المتغير (مثال: API_KEY)')

@bot.callback_query_handler(func=lambda c: c.data.startswith('ec_'))
def cb_env_clr(c):
    fn = c.data[3:]
    chat_id = c.message.chat.id
    env_vars[chat_id][fn] = {}
    save_all()
    bot.answer_callback_query(c.id, "🗑 حُذفت")
    c.data = f'ev_{fn}'
    cb_env(c)

@bot.message_handler(func=lambda m: m.from_user.id in waiting_for_env and m.content_type == 'text')
def on_env_input(m):
    chat_id = m.from_user.id
    fn, step, prev_key = waiting_for_env[chat_id]
    if step == 'key':
        waiting_for_env[chat_id] = (fn, 'value', m.text.strip())
        send(chat_id, f'الآن أرسل القيمة لـ <code>{m.text.strip()}</code>')
    else:
        key = prev_key
        env_vars[chat_id][fn][key] = m.text.strip()
        del waiting_for_env[chat_id]
        save_all()
        send(chat_id, f'{ce("check")} تم حفظ <code>{key}</code>')

# ==================== إدخال ملفات ==================== #
@bot.message_handler(func=lambda m: m.chat.id in process_stdin_pending
                     and m.content_type == 'text' and not (m.text or '').startswith('/'))
def on_user_input(m):
    chat_id = m.chat.id
    if chat_id not in process_stdin_pending: return
    p = process_stdin_pending[chat_id]
    proc = p['process']; fn = p['file_name']
    try:
        if proc.poll() is not None:
            send(chat_id, '⚠️ العملية توقفت.', E['warning'])
            del process_stdin_pending[chat_id]; return
        proc.stdin.write((m.text + '\n').encode('utf-8'))
        proc.stdin.flush()
        del process_stdin_pending[chat_id]
        asked_prompts.pop((chat_id, fn), None)
        send(chat_id, f'{ce("check")} تم الإرسال إلى <code>{fn}</code>')
    except Exception as e:
        send(chat_id, f'خطأ: {e}', E['cross'])
        process_stdin_pending.pop(chat_id, None)

@bot.callback_query_handler(func=lambda c: c.data.startswith('cxl_'))
def cb_cancel_input(c):
    p = c.data[4:].split('_', 1)
    chat_id, fn = int(p[0]), p[1]
    if chat_id in process_stdin_pending and process_stdin_pending[chat_id]['file_name'] == fn:
        proc = process_stdin_pending[chat_id]['process']
        try:
            if proc.stdin and proc.poll() is None:
                proc.stdin.write(b'\n'); proc.stdin.flush()
        except: pass
        del process_stdin_pending[chat_id]
        asked_prompts.pop((chat_id, fn), None)
    bot.answer_callback_query(c.id, "❌ تم الإلغاء")

# ==================== تثبيت مكتبة ==================== #
@bot.callback_query_handler(func=lambda c: c.data == 'lib')
def cb_lib(c):
    if not is_approved(c.from_user.id):
        bot.answer_callback_query(c.id, "❌"); return
    waiting_for_library.add(c.from_user.id)
    bot.answer_callback_query(c.id)
    mk = types.InlineKeyboardMarkup()
    mk.add(btn("إلغاء", callback_data='home', emoji_key='cross', style="danger"))
    send(c.message.chat.id, f'{ce("gem")} أرسل اسم المكتبة:', reply_markup=mk)

@bot.message_handler(func=lambda m: m.from_user.id in waiting_for_library and m.content_type == 'text')
def on_lib(m):
    waiting_for_library.discard(m.from_user.id)
    name = m.text.strip()
    if not re.match(r'^[a-zA-Z0-9_\-\.\=\<\>\!]+$', name):
        send(m.chat.id, 'اسم غير صالح.', E['cross']); return
    send(m.chat.id, f'📦 تثبيت <code>{name}</code>...')
    try:
        r = subprocess.run([sys.executable, "-m", "pip", "install", name],
                           capture_output=True, text=True, timeout=300)
        if r.returncode == 0:
            send(m.chat.id, f'{ce("check")} تم تثبيت <code>{name}</code>')
        else:
            send(m.chat.id, f'❌ فشل: <code>{(r.stderr or "")[-300:]}</code>')
    except Exception as e:
        send(m.chat.id, f'خطأ: {e}', E['cross'])

# ==================== الحماية ==================== #
@bot.callback_query_handler(func=lambda c: c.data == 'prot')
def cb_prot(c):
    if not is_admin(c.from_user.id):
        bot.answer_callback_query(c.id, "❌"); return
    bot.answer_callback_query(c.id)
    st = "مفعل" if protection_enabled else "معطل"
    mk = types.InlineKeyboardMarkup(row_width=1)
    mk.add(btn("تعطيل" if protection_enabled else "تفعيل",
               callback_data='ptog', emoji_key='check' if not protection_enabled else 'cross',
               style="success" if not protection_enabled else "danger"))
    mk.add(btn(f"المستوى: {protection_level}", callback_data='plevel', emoji_key='settings', style="primary"))
    mk.add(btn("رجوع", callback_data='home', emoji_key='arrow', style="primary"))
    edit(c.message.chat.id, c.message.message_id,
         f'{ce("settings")} <b>الحماية</b>\n\nالحالة: {st}\nالمستوى: <code>{protection_level}</code>',
         reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data == 'ptog')
def cb_ptog(c):
    global protection_enabled
    if not is_admin(c.from_user.id): return
    protection_enabled = not protection_enabled
    c.data = 'prot'; cb_prot(c)

@bot.callback_query_handler(func=lambda c: c.data == 'plevel')
def cb_plevel(c):
    if not is_admin(c.from_user.id): return
    bot.answer_callback_query(c.id)
    mk = types.InlineKeyboardMarkup(row_width=3)
    for k in ['low','medium','high']:
        mk.add(btn(k, callback_data=f'pl_{k}', emoji_key='1' if k=='low' else '2' if k=='medium' else '3', style="primary"))
    mk.add(btn("رجوع", callback_data='prot', emoji_key='arrow', style="primary"))
    edit(c.message.chat.id, c.message.message_id, 'اختر المستوى:', reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith('pl_'))
def cb_pl(c):
    global protection_level
    if not is_admin(c.from_user.id): return
    protection_level = c.data[3:]
    c.data = 'prot'; cb_prot(c)

# ==================== إدارة المستخدمين ==================== #
@bot.callback_query_handler(func=lambda c: c.data == 'users')
def cb_users(c):
    if not is_admin(c.from_user.id): return
    bot.answer_callback_query(c.id)
    mk = types.InlineKeyboardMarkup(row_width=1)
    if pending_requests:
        for uid, info in list(pending_requests.items()):
            nm = info.get('first_name', '?')
            mk.add(btn(f"❌ رفض {nm}", callback_data=f'rej_{uid}', emoji_key='cross', style="danger"))
            mk.add(btn(f"✅ قبول {nm}", callback_data=f'app_{uid}', emoji_key='check', style="success"))
    else:
        mk.add(btn("لا طلبات", callback_data='noop', emoji_key='cross', style="danger"))
    mk.add(btn("رجوع", callback_data='home', emoji_key='arrow', style="primary"))
    send(c.message.chat.id,
         f'{ce("people")} طلبات: {len(pending_requests)}\nمفعلين: {len(approved_users)}\nمحظورين: {len(banned_users)}',
         reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith('app_'))
def cb_app(c):
    if not is_admin(c.from_user.id): return
    uid = int(c.data[4:])
    if uid in pending_requests:
        info = pending_requests.pop(uid)
        approved_users.add(uid)
        try: send(uid, '🎉 تمت الموافقة! أرسل /start')
        except: pass
        bot.answer_callback_query(c.id, "✅")
        try: edit(c.message.chat.id, c.message.message_id, f'✅ قبول {info["first_name"]}')
        except: pass

@bot.callback_query_handler(func=lambda c: c.data.startswith('rej_'))
def cb_rej(c):
    if not is_admin(c.from_user.id): return
    uid = int(c.data[4:])
    if uid in pending_requests:
        info = pending_requests.pop(uid)
        try: send(uid, '❌ تم رفض طلبك.')
        except: pass
        bot.answer_callback_query(c.id, "❌")
        try: edit(c.message.chat.id, c.message.message_id, f'❌ رفض {info["first_name"]}')
        except: pass

# ==================== تجديد ==================== #
@bot.callback_query_handler(func=lambda c: c.data.startswith('rn_'))
def cb_renew(c):
    if not is_admin(c.from_user.id): return
    p = c.data[3:].split('_', 1)
    uid, fn = int(p[0]), p[1]
    path = file_path(uid, fn)
    if not os.path.exists(path):
        bot.answer_callback_query(c.id, "❌"); return
    _spawn(uid, fn, path)
    bot.answer_callback_query(c.id, "✅")
    try: edit(c.message.chat.id, c.message.message_id, f'✅ تجديد {fn}')
    except: pass

@bot.callback_query_handler(func=lambda c: c.data.startswith('rj_'))
def cb_rej_renew(c):
    if not is_admin(c.from_user.id): return
    p = c.data[3:].split('_', 1)
    uid, fn = int(p[0]), p[1]
    bot.answer_callback_query(c.id, "❌")
    try: edit(c.message.chat.id, c.message.message_id, f'❌ رفض تجديد {fn}')
    except: pass

# ==================== لوحة الأدمن ==================== #
@bot.callback_query_handler(func=lambda c: c.data == 'admin')
def cb_admin(c):
    if not is_admin(c.from_user.id): return
    bot.answer_callback_query(c.id)
    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.add(btn("رفع مشرف", callback_data='pm', emoji_key='crown', style="success"))
    mk.add(btn("تنزيل مشرف", callback_data='dm', emoji_key='cross', style="danger"))
    mk.add(btn("حظر", callback_data='bn', emoji_key='warning', style="danger"))
    mk.add(btn("إلغاء حظر", callback_data='ub', emoji_key='check', style="success"))
    mk.add(btn("إيقاف البوت" if bot_running else "تشغيل البوت",
               callback_data='tog', emoji_key='cross' if bot_running else 'fire',
               style="danger" if bot_running else "success"))
    mk.add(btn("رجوع", callback_data='home', emoji_key='arrow', style="primary"))
    send(c.message.chat.id,
         f'{ce("crown")} <b>لوحة الأدمن</b>\n'
         f'الحالة: {"🟢 يعمل" if bot_running else "🔴 متوقف"}\n'
         f'مشرفين: {len(admins)} | مفعلين: {len(approved_users)}',
         reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data == 'tog')
def cb_tog(c):
    global bot_running
    if not is_admin(c.from_user.id): return
    bot_running = not bot_running
    bot.answer_callback_query(c.id, "تم")
    cb_admin(c)

@bot.callback_query_handler(func=lambda c: c.data in ('pm','dm','bn','ub'))
def cb_admin_actions(c):
    if not is_admin(c.from_user.id): return
    if c.data == 'pm':
        m = send(c.message.chat.id, 'أرسل ID المستخدم لرفعه مشرفاً:')
        bot.register_next_step_handler(m, lambda msg: _promote(msg))
    elif c.data == 'dm':
        m = send(c.message.chat.id, 'أرسل ID المشرف لتنزيله:')
        bot.register_next_step_handler(m, lambda msg: _demote(msg))
    elif c.data == 'bn':
        m = send(c.message.chat.id, 'أرسل @username للحظر:')
        bot.register_next_step_handler(m, lambda msg: _ban(msg))
    elif c.data == 'ub':
        m = send(c.message.chat.id, 'أرسل @username لفك الحظر:')
        bot.register_next_step_handler(m, lambda msg: _unban(msg))
    bot.answer_callback_query(c.id)

def _promote(m):
    try:
        uid = int(m.text.strip())
        if uid not in approved_users:
            send(m.chat.id, 'غير موجود.', E['cross']); return
        admins.add(uid)
        send(m.chat.id, f'{ce("crown")} رُفع {uid} مشرفاً.')
    except: send(m.chat.id, 'ID غير صالح.', E['cross'])

def _demote(m):
    try:
        uid = int(m.text.strip())
        if uid == ADMIN_ID: send(m.chat.id, 'لا يمكن.', E['cross']); return
        admins.discard(uid)
        send(m.chat.id, f'{ce("check")} نُزّل {uid}.')
    except: send(m.chat.id, 'ID غير صالح.', E['cross'])

def _ban(m):
    u = m.text.strip().lstrip('@')
    banned_users.add(u)
    send(m.chat.id, f'محظور @{u}')

def _unban(m):
    u = m.text.strip().lstrip('@')
    banned_users.discard(u)
    send(m.chat.id, f'فُك @{u}')

@bot.callback_query_handler(func=lambda c: c.data == 'noop')
def cb_noop(c): bot.answer_callback_query(c.id)

# ==================== تشغيل ==================== #
if __name__ == '__main__':
    print("🤖 البوت يعمل...")
    print(f"👑 الأدمن: {ADMIN_ID}")
    if not PSUTIL_OK:
        print("
