import sys
import os
import time
import json
import uuid
import shutil
import signal
import tempfile
import threading
import subprocess
import traceback
import logging
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import telebot
from telebot import types

# ========== Logging ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ========== إعدادات البوت ==========
BOT_TOKEN = '8877293036:AAGg_82F0bT1Bhov42sk9qDcRMsVNpfnErw'
ADMIN_ID = 1920665874
YOUR_USERNAME = '@u_8_y'
ADMIN_CHANNEL = '@FD_CQ'

# ========== متغيرات عامة ==========
bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML')
uploaded_files_dir = "uploaded_files"
suspicious_files_dir = "suspicious_files"
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

bot_scripts = {}          # {chat_id: {file_id: {name, path, process, uploader, started_at}}}
pending_inputs = {}       # {chat_id: file_id}
user_chats = {}
banned_users = set()
lock = threading.Lock()
executor = ThreadPoolExecutor(max_workers=10)

approved_users = set()
pending_requests = {}
approved_users.add(ADMIN_ID)

protection_enabled = True
protection_level = "medium"
bot_running = True

# إنشاء المجلدات
for d in [uploaded_files_dir, suspicious_files_dir]:
    try:
        os.makedirs(d, exist_ok=True)
    except Exception as e:
        logger.error(f"mkdir error: {e}")

logger.info("=" * 55)
logger.info("🐍 Python Hosting Bot")
logger.info(f"👨‍💻 المطور: {YOUR_USERNAME} ({ADMIN_ID})")
logger.info(f"📢 القناة: {ADMIN_CHANNEL}")
logger.info("=" * 55)


# ========== Safe send helper ==========
def safe_send(chat_id, text, **kwargs):
    """إرسال رسالة بأمان مع تجاهل الأخطاء"""
    try:
        return bot.send_message(chat_id, text, **kwargs)
    except Exception as e:
        logger.error(f"send_message failed [{chat_id}]: {e}")
        return None


def safe_edit(chat_id, message_id, text, **kwargs):
    try:
        return bot.edit_message_text(text, chat_id, message_id, **kwargs)
    except Exception as e:
        logger.error(f"edit_message failed: {e}")
        return None


def safe_answer(call_id, text=None, **kwargs):
    try:
        return bot.answer_callback_query(call_id, text, **kwargs)
    except Exception as e:
        logger.error(f"answer_callback failed: {e}")
        return None


# ========== دوال مساعدة ==========
def is_admin(user_id):
    return user_id == ADMIN_ID


def is_approved_user(user_id):
    return user_id in approved_users or user_id == ADMIN_ID


def save_chat_id(chat_id):
    user_chats[chat_id] = True


def request_approval(user_id, user_info):
    pending_requests[user_id] = user_info
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ قبول", callback_data=f'approve_{user_id}'),
        types.InlineKeyboardButton("❌ رفض", callback_data=f'reject_{user_id}')
    )
    safe_send(
        ADMIN_ID,
        f"📋 طلب اشتراك جديد:\n\n"
        f"👤 الاسم: {user_info['first_name']}\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"📌 اليوزر: @{user_info.get('username', 'غير متوفر')}\n"
        f"⏰ الوقت: {user_info['timestamp']}",
        reply_markup=markup
    )


def send_waiting_message(chat_id):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📞 التواصل مع الدعم", callback_data='online_support'))
    safe_send(
        chat_id,
        "⏳ تم إرسال طلب اشتراكك إلى الأدمن.\n"
        "يرجى الانتظار حتى يتم الموافقة.\n\n"
        "للتواصل مع الدعم اضغط على الزر أدناه:",
        reply_markup=markup
    )


# ========== الحماية ==========
def scan_file(file_path, user_id):
    if is_admin(user_id):
        return False, ""
    try:
        with open(file_path, 'rb') as f:
            content = f.read().decode('utf-8', errors='replace')
        patterns = [
            r"rm\s+-rf\s+[\'\"]?/",
            r"import\s+marshal",
        ]
        for p in patterns:
            if re.search(p, content, re.IGNORECASE):
                return True, f"نمط خطير: {p}"
        return False, ""
    except Exception as e:
        return False, ""


# ========== تشغيل/إيقاف الملفات ==========
def start_file(script_path, chat_id, file_id):
    with lock:
        if chat_id not in bot_scripts:
            bot_scripts[chat_id] = {}
        if file_id not in bot_scripts[chat_id]:
            bot_scripts[chat_id][file_id] = {'process': None}

        info = bot_scripts[chat_id][file_id]
        proc = info.get('process')
        if proc and proc.poll() is None:
            safe_send(chat_id, "⚠️ الملف يعمل بالفعل.")
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
            display_name = info.get('name', 'ملف')
            safe_send(
                chat_id,
                f"✅ تم تشغيل الملف: <b>{display_name}</b>\n"
                f"🆔 <code>{file_id}</code>\n\n"
                f"⚡ جارٍ مراقبة المدخلات..."
            )
            t = threading.Thread(
                target=monitor_process_output,
                args=(chat_id, file_id, p),
                daemon=True
            )
            t.start()
        except Exception as e:
            logger.error(f"start_file error: {e}\n{traceback.format_exc()}")
            safe_send(chat_id, f"❌ فشل في تشغيل الملف: {e}")


INPUT_KEYWORDS = [
    'أرسل', 'ارسل', 'ادخل', 'أدخل', 'اكتب', 'رقم', 'كود', 'رمز',
    'otp', 'phone', 'code', 'password', 'pass', '2fa',
    'كلمة السر', 'كلمة سر', 'التحقق', 'الهاتف', 'هاتف',
    'input', 'enter', 'token', 'session', 'api_id', 'api_hash',
    'bot_token', 'user', 'username', 'name', 'id', 'auth', 'key'
]
PROMPT_END_CHARS = ('؟', '?', ':', '!', '؛')


def _looks_like_prompt(text):
    if not text or len(text.strip()) < 3:
        return False
    t = text.lower()
    return any(kw.lower() in t for kw in INPUT_KEYWORDS)


def monitor_process_output(chat_id, file_id, process):
    buffer = ""
    try:
        while True:
            try:
                ch = process.stdout.read(1)
            except Exception:
                break

            if not ch:
                if process.poll() is not None:
                    remaining = buffer.strip()
                    if remaining:
                        try:
                            safe_send(chat_id, f"📄 آخر إخراج:\n<code>{remaining[:800]}</code>")
                        except Exception:
                            pass
                    break
                time.sleep(0.05)
                continue

            try:
                decoded = ch.decode('utf-8', errors='replace')
            except Exception:
                continue

            buffer += decoded
            should_flush = '\n' in decoded or (
                decoded in PROMPT_END_CHARS and len(buffer.strip()) >= 4
            )

            if should_flush:
                line = buffer.strip()
                buffer = ""
                if not line:
                    continue

                if _looks_like_prompt(line):
                    pending_inputs[chat_id] = file_id
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton(
                        "❌ إلغاء الطلب",
                        callback_data=f'cancel_input_{file_id}'
                    ))
                    try:
                        safe_send(
                            chat_id,
                            f"📨 <b>الملف يطلب إدخال:</b>\n\n"
                            f"<code>{line[:800]}</code>\n\n"
                            f"✍️ أرسل الإجابة الآن مباشرة:",
                            reply_markup=markup
                        )
                    except Exception:
                        pass
    except Exception as e:
        logger.error(f"monitor error [{chat_id}/{file_id}]: {e}")
    finally:
        if pending_inputs.get(chat_id) == file_id:
            pending_inputs.pop(chat_id, None)


def stop_one_file(chat_id, file_id, delete=False):
    if chat_id not in bot_scripts or file_id not in bot_scripts[chat_id]:
        return False

    info = bot_scripts[chat_id][file_id]
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
        bot_scripts[chat_id].pop(file_id, None)

    return True


def stop_all_for_chat(chat_id):
    if chat_id not in bot_scripts:
        return 0
    count = 0
    for fid in list(bot_scripts[chat_id].keys()):
        if stop_one_file(chat_id, fid, delete=False):
            count += 1
    return count


# ========== القوائم ==========
def show_main_menu(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("التحكم في الحماية 🛡️", callback_data='protection_control'),
        types.InlineKeyboardButton("رفع ملف 📥", callback_data='upload')
    )
    markup.add(
        types.InlineKeyboardButton("📂 ملفاتي", callback_data='my_files'),
        types.InlineKeyboardButton("فتاة المحاور 👩‍💼", callback_data='support_girl')
    )
    markup.add(
        types.InlineKeyboardButton("🚀 سرعة البوت", callback_data='speed'),
        types.InlineKeyboardButton("ℹ️ حول البوت", callback_data='about_bot')
    )
    markup.add(
        types.InlineKeyboardButton("🛠️ الدعم الفني", callback_data='tech_support'),
        types.InlineKeyboardButton("📚 تثبيت مكتبة", callback_data='download_lib')
    )
    markup.add(
        types.InlineKeyboardButton("📞 التواصل مع الدعم", callback_data='online_support')
    )
    if is_admin(message.from_user.id):
        markup.add(
            types.InlineKeyboardButton("👥 إدارة المستخدمين", callback_data='manage_users'),
            types.InlineKeyboardButton("⚡ تشغيل/إيقاف البوت", callback_data='bot_control')
        )

    safe_send(
        message.chat.id,
        f"🐍 <b>Python Hosting</b> 🐍\n\n"
        f"مرحباً، {message.from_user.first_name}! 👋\n\n"
        f"<b>الميزات المتاحة:</b> ✅\n\n"
        f"• تشغيل أكثر من ملف في نفس الوقت\n"
        f"• إدارة كل ملفاتك من زر 📂 ملفاتي\n"
        f"• إيقاف / إعادة تشغيل / حذف أي ملف\n"
        f"• دعم تفاعلي لطلب الرقم/OTP/2FA\n\n"
        f"👨‍💻 المطور: {YOUR_USERNAME}\n"
        f"📢 القناة: {ADMIN_CHANNEL}\n\n"
        f"<b>اختر من الأزرار أدناه:</b>",
        reply_markup=markup
    )


# ========== Handlers ==========
@bot.message_handler(commands=['start'])
def start(message):
    save_chat_id(message.chat.id)
    uid = message.from_user.id

    if not bot_running:
        safe_send(message.chat.id, "⏸️ البوت متوقف حالياً.")
        return

    if message.from_user.username in banned_users:
        safe_send(message.chat.id, "⁉️ تم حظرك من البوت.")
        return

    if is_approved_user(uid):
        show_main_menu(message)
    elif uid in pending_requests:
        send_waiting_message(message.chat.id)
    else:
        info = {
            'first_name': message.from_user.first_name,
            'username': message.from_user.username or 'غير متوفر',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        request_approval(uid, info)
        send_waiting_message(message.chat.id)


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
    if chat_id not in bot_scripts or file_id not in bot_scripts[chat_id]:
        pending_inputs.pop(chat_id, None)
        safe_send(chat_id, "❌ العملية لم تعد موجودة.")
        return

    proc = bot_scripts[chat_id][file_id].get('process')
    if not proc or proc.poll() is not None:
        pending_inputs.pop(chat_id, None)
        safe_send(chat_id, "❌ الملف لم يعد يعمل.")
        return

    user_input = message.text.strip()
    try:
        proc.stdin.write((user_input + "\n").encode('utf-8'))
        proc.stdin.flush()

        if len(user_input) > 8:
            masked = user_input[:3] + "*" * (len(user_input) - 6) + user_input[-3:]
        else:
            masked = user_input[:2] + "*" * max(0, len(user_input) - 2)

        safe_send(
            chat_id,
            f"✅ تم إرسال الإجابة للملف: <code>{masked}</code>\n⏳ جارٍ المتابعة..."
        )
        pending_inputs.pop(chat_id, None)
    except Exception as e:
        safe_send(chat_id, f"❌ فشل في إرسال الإدخال: {e}")


@bot.callback_query_handler(func=lambda c: c.data.startswith('cancel_input_'))
def cancel_input_cb(call):
    chat_id = call.message.chat.id
    pending_inputs.pop(chat_id, None)
    safe_answer(call.id, "✅ تم إلغاء الطلب")
    safe_edit(chat_id, call.message.message_id,
              "🚫 تم إلغاء طلب الإدخال.")


@bot.callback_query_handler(func=lambda c: c.data == 'upload')
def upload_cb(call):
    if not is_approved_user(call.from_user.id):
        safe_answer(call.id, "❌ تحتاج موافقة")
        return
    if not bot_running:
        safe_answer(call.id, "⏸️ البوت متوقف")
        return
    safe_answer(call.id, "📤 جاهز للرفع")
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ إلغاء", callback_data='back_to_main'))
    safe_send(
        call.message.chat.id,
        "📤 <b>رفع ملف</b>\n\n"
        "أرسل ملف .py الآن (حد أقصى 5MB)\n"
        "🔔 الملفات التي تطلب رقم/OTP/2FA سيتفاعل معها البوت تلقائياً.",
        reply_markup=markup
    )


@bot.callback_query_handler(func=lambda c: c.data == 'my_files')
def my_files_cb(call):
    show_my_files(call, edit=False)


def show_my_files(call, edit=False):
    chat_id = call.message.chat.id

    if chat_id not in bot_scripts or not bot_scripts[chat_id]:
        txt = "📂 لا توجد ملفات مرفوعة حالياً.\nارفع ملف .py أولاً."
        if edit:
            safe_edit(chat_id, call.message.message_id, txt)
        else:
            safe_send(chat_id, txt)
        return

    files = bot_scripts[chat_id]
    running = sum(1 for f in files.values() if f.get('process') and f['process'].poll() is None)

    text = (
        f"📂 <b>ملفاتك</b> ({len(files)})\n"
        f"🟢 يعمل: {running} | 🔴 متوقف: {len(files) - running}\n\n"
        f"اضغط على اسم الملف للتفاصيل."
    )

    markup = types.InlineKeyboardMarkup(row_width=4)
    for fid, info in files.items():
        proc = info.get('process')
        status = "🟢" if (proc and proc.poll() is None) else "🔴"
        name = info.get('name', 'ملف')[:22]
        markup.row(
            types.InlineKeyboardButton(f"{status} {name}", callback_data=f'nf_{fid}'),
            types.InlineKeyboardButton("🔄", callback_data=f'rf_{fid}'),
            types.InlineKeyboardButton("🛑", callback_data=f'sf_{fid}'),
            types.InlineKeyboardButton("🗑️", callback_data=f'df_{fid}')
        )
    markup.row(
        types.InlineKeyboardButton("🛑 إيقاف الكل", callback_data='stop_all_files'),
        types.InlineKeyboardButton("🔙 القائمة", callback_data='back_to_main')
    )

    if edit:
        res = safe_edit(chat_id, call.message.message_id, text, reply_markup=markup)
        if not res:
            safe_send(chat_id, text, reply_markup=markup)
    else:
        safe_send(chat_id, text, reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith('sf_'))
def stop_specific_cb(call):
    if not is_approved_user(call.from_user.id):
        safe_answer(call.id, "❌ غير مصرح")
        return
    fid = call.data.replace('sf_', '')
    chat_id = call.message.chat.id
    if chat_id not in bot_scripts or fid not in bot_scripts[chat_id]:
        safe_answer(call.id, "❌ غير موجود")
        return
    name = bot_scripts[chat_id][fid].get('name', 'ملف')
    if stop_one_file(chat_id, fid, delete=False):
        safe_answer(call.id, f"✅ تم إيقاف {name}")
        show_my_files(call, edit=True)
    else:
        safe_answer(call.id, "❌ فشل")


@bot.callback_query_handler(func=lambda c: c.data.startswith('df_'))
def delete_specific_cb(call):
    if not is_approved_user(call.from_user.id):
        safe_answer(call.id, "❌ غير مصرح")
        return
    fid = call.data.replace('df_', '')
    chat_id = call.message.chat.id
    if chat_id not in bot_scripts or fid not in bot_scripts[chat_id]:
        safe_answer(call.id, "❌ غير موجود")
        return
    name = bot_scripts[chat_id][fid].get('name', 'ملف')
    if stop_one_file(chat_id, fid, delete=True):
        safe_answer(call.id, f"🗑️ تم حذف {name}")
        show_my_files(call, edit=True)
    else:
        safe_answer(call.id, "❌ فشل")


@bot.callback_query_handler(func=lambda c: c.data.startswith('rf_'))
def restart_cb(call):
    if not is_approved_user(call.from_user.id):
        safe_answer(call.id, "❌ غير مصرح")
        return
    fid = call.data.replace('rf_', '')
    chat_id = call.message.chat.id
    if chat_id not in bot_scripts or fid not in bot_scripts[chat_id]:
        safe_answer(call.id, "❌ غير موجود")
        return
    info = bot_scripts[chat_id][fid]
    stop_one_file(chat_id, fid, delete=False)
    time.sleep(0.3)
    start_file(info['path'], chat_id, fid)
    safe_answer(call.id, "🔄 تم إعادة التشغيل")
    time.sleep(0.5)
    show_my_files(call, edit=True)


@bot.callback_query_handler(func=lambda c: c.data.startswith('nf_'))
def file_info_cb(call):
    fid = call.data.replace('nf_', '')
    chat_id = call.message.chat.id
    if chat_id not in bot_scripts or fid not in bot_scripts[chat_id]:
        safe_answer(call.id, "❌ غير موجود")
        return
    info = bot_scripts[chat_id][fid]
    proc = info.get('process')
    status = "🟢 يعمل" if (proc and proc.poll() is None) else "🔴 متوقف"
    pid = proc.pid if proc and proc.poll() is None else "—"
    safe_answer(
        call.id,
        f"📁 {info['name']}\n"
        f"الحالة: {status}\n"
        f"PID: {pid}\n"
        f"🆔 {fid}\n"
        f"⏰ {info.get('started_at', '—')}",
        show_alert=True
    )


@bot.callback_query_handler(func=lambda c: c.data == 'stop_all_files')
def stop_all_cb(call):
    if not is_approved_user(call.from_user.id):
        safe_answer(call.id, "❌ غير مصرح")
        return
    chat_id = call.message.chat.id
    count = stop_all_for_chat(chat_id)
    safe_answer(call.id, f"🛑 تم إيقاف {count} ملف")
    show_my_files(call, edit=True)


@bot.callback_query_handler(func=lambda c: c.data == 'back_to_main')
def back_to_main_cb(call):
    try:
        show_main_menu(call.message)
        safe_answer(call.id, "🏠 القائمة الرئيسية")
    except Exception:
        safe_answer(call.id, "خطأ")


# ========== رفع الملفات ==========
@bot.message_handler(content_types=['document'])
def handle_file(message):
    if not is_approved_user(message.from_user.id):
        safe_send(message.chat.id, "❌ تحتاج إلى موافقة الأدمن.")
        return
    if not bot_running:
        safe_send(message.chat.id, "⏸️ البوت متوقف.")
        return

    try:
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.from_user.username in banned_users:
            safe_send(chat_id, "⁉️ تم حظرك")
            return

        file_info = bot.get_file(message.document.file_id)
        if file_info.file_size > MAX_FILE_SIZE:
            safe_send(chat_id, "⛔ الحجم يتجاوز 5MB")
            return

        downloaded = bot.download_file(file_info.file_path)
        script_name = message.document.file_name or "script.py"

        if not script_name.endswith('.py'):
            safe_send(chat_id, "❌ فقط ملفات .py مسموحة")
            return

        user_dir = os.path.join(uploaded_files_dir, str(user_id))
        os.makedirs(user_dir, exist_ok=True)

        file_id = uuid.uuid4().hex[:8]
        internal_name = f"{file_id}_{script_name}"
        script_path = os.path.join(user_dir, internal_name)

        tmp = os.path.join(tempfile.gettempdir(), f"{file_id}_{script_name}")
        with open(tmp, 'wb') as f:
            f.write(downloaded)

        if protection_enabled and not is_admin(user_id):
            bad, reason = scan_file(tmp, user_id)
            if bad:
                try:
                    os.remove(tmp)
                except Exception:
                    pass
                safe_send(chat_id, f"⛔ رُفض الملف: {reason}")
                return

        shutil.move(tmp, script_path)

        if chat_id not in bot_scripts:
            bot_scripts[chat_id] = {}

        bot_scripts[chat_id][file_id] = {
            'name': script_name,
            'path': script_path,
            'process': None,
            'uploader': message.from_user.username,
            'started_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        total = len(bot_scripts[chat_id])
        markup = types.InlineKeyboardMarkup(row_width=3)
        markup.add(
            types.InlineKeyboardButton("🛑 إيقاف", callback_data=f'sf_{file_id}'),
            types.InlineKeyboardButton("🔄 إعادة", callback_data=f'rf_{file_id}'),
            types.InlineKeyboardButton("🗑️ حذف", callback_data=f'df_{file_id}')
        )
        markup.add(types.InlineKeyboardButton(
            f"📂 ملفاتي ({total})", callback_data='my_files'
        ))

        safe_send(
            chat_id,
            f"✅ تم رفع الملف بنجاح\n\n"
            f"📁 الاسم: <code>{script_name}</code>\n"
            f"🆔 المُعرّف: <code>{file_id}</code>\n"
            f"👤 المستخدم: @{message.from_user.username}\n"
            f"📊 مجموع ملفاتك: {total}",
            reply_markup=markup
        )

        start_file(script_path, chat_id, file_id)

    except Exception as e:
        logger.error(f"handle_file error: {e}\n{traceback.format_exc()}")
        safe_send(message.chat.id, f"❌ خطأ: {e}")


# ========== أزرار الدعم والمعلومات ==========
@bot.callback_query_handler(func=lambda c: c.data == 'support_girl')
def support_girl_cb(call):
    if not is_approved_user(call.from_user.id):
        safe_answer(call.id, "❌ تحتاج موافقة")
        return
    safe_answer(call.id, "👩‍💼 جاري الاتصال...")
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("إنهاء المحادثة", callback_data='end_chat'))
    safe_send(
        call.message.chat.id,
        "👩‍💼 <b>مرحباً! أنا فتاة المحاور</b>\n\n"
        "كيف يمكنني مساعدتك اليوم؟\n\n"
        "• كيفية استخدام البوت\n"
        "• المشاكل التقنية\n"
        "• استفسارات عامة\n\n"
        "ما الذي تريد معرفته؟ 💬",
        reply_markup=markup
    )


@bot.callback_query_handler(func=lambda c: c.data == 'tech_support')
def tech_support_cb(call):
    if not is_approved_user(call.from_user.id):
        safe_answer(call.id, "❌ تحتاج موافقة")
        return
    safe_answer(call.id, "🛠️ جاري التحويل...")
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔧 المشاكل الشائعة", callback_data='common_issues'))
    markup.add(types.InlineKeyboardButton("👨‍💼 التواصل مع الأدمن", callback_data='online_support'))
    markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data='back_to_main'))
    safe_send(
        call.message.chat.id,
        "🛠️ <b>الدعم الفني</b>\n\n"
        "• حل المشاكل التقنية\n"
        "• استكشاف الأخطاء\n"
        "• دعم في تشغيل الملفات\n"
        "• مساعدة في تثبيت المكتبات\n\n"
        "اختر الخدمة:",
        reply_markup=markup
    )


@bot.callback_query_handler(func=lambda c: c.data == 'common_issues')
def common_issues_cb(call):
    safe_answer(call.id)
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("📁 الملف لا يعمل", callback_data='issue_file'),
        types.InlineKeyboardButton("📚 مشكلة التثبيت", callback_data='issue_install')
    )
    markup.add(types.InlineKeyboardButton("🐌 البوت بطيء", callback_data='issue_speed'))
    markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data='tech_support'))
    safe_edit(
        call.message.chat.id,
        call.message.message_id,
        "🔧 <b>المشاكل الشائعة</b>\n\nاختر نوع المشكلة:",
        reply_markup=markup
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith('issue_'))
def handle_issue_cb(call):
    it = call.data.replace('issue_', '')
    sols = {
        'file': "1. تأكد أن الملف .py\n2. تحقق من الأخطاء\n3. ثبّت المكتبات\n4. أعد الرفع",
        'install': "1. تأكد من اسم المكتبة\n2. جرّب إصدار محدد\n3. تأكد من الإنترنت\n4. حدّث pip",
        'speed': "1. جودة الاتصال\n2. أغلق ملفات غير مستخدمة\n3. أعد التشغيل\n4. تحقق من العمليات الثقيلة"
    }
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data='common_issues'))
    markup.add(types.InlineKeyboardButton("📞 دعم مباشر", callback_data='online_support'))
    safe_edit(
        call.message.chat.id,
        call.message.message_id,
        f"<b>حلول:</b>\n\n{sols.get(it, 'غير متوفر')}",
        reply_markup=markup
    )


@bot.callback_query_handler(func=lambda c: c.data == 'end_chat')
def end_chat_cb(call):
    safe_answer(call.id, "تم الإنهاء")
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("🔄 محادثة جديدة", callback_data='support_girl'),
        types.InlineKeyboardButton("🏠 القائمة", callback_data='back_to_main')
    )
    safe_edit(
        call.message.chat.id,
        call.message.message_id,
        "👋 تم إنهاء المحادثة. شكراً لك!",
        reply_markup=markup
    )


@bot.callback_query_handler(func=lambda c: c.data == 'about_bot')
def about_cb(call):
    safe_answer(call.id)
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("🌟 الميزات", callback_data='features_list'),
        types.InlineKeyboardButton("🔙 رجوع", callback_data='back_to_main')
    )
    safe_send(
        call.message.chat.id,
        "ℹ️ <b>حول البوت</b>\n\n"
        "🐍 <b>Python Hosting Bot</b>\n\n"
        "✅ تشغيل عدة ملفات\n"
        "✅ تفاعل ذكي (رقم/OTP/2FA)\n"
        "✅ نظام حماية متقدم\n"
        "✅ إدارة مستخدمين\n\n"
        f"👨‍💻 <b>المطور:</b> {YOUR_USERNAME}\n"
        f"📢 <b>القناة:</b> {ADMIN_CHANNEL}",
        reply_markup=markup
    )


@bot.callback_query_handler(func=lambda c: c.data == 'features_list')
def features_cb(call):
    safe_answer(call.id)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data='about_bot'))
    safe_edit(
        call.message.chat.id,
        call.message.message_id,
        "🌟 <b>الميزات:</b>\n\n"
        "🛡️ فحص تلقائي للملفات\n"
        "⚡ تشغيل متزامن\n"
        "📂 إدارة كاملة للملفات\n"
        "🔔 تفاعل ذكي\n"
        "🛠️ دعم متكامل",
        reply_markup=markup
    )


@bot.callback_query_handler(func=lambda c: c.data == 'download_lib')
def dl_lib_cb(call):
    if not is_approved_user(call.from_user.id):
        safe_answer(call.id, "❌ تحتاج موافقة")
        return
    safe_send(call.message.chat.id, "📚 أرسل اسم المكتبة:")
    bot.register_next_step_handler(call.message, install_lib_step)


def install_lib_step(message):
    lib = message.text.strip()
    safe_send(message.chat.id, f"🔄 جاري تثبيت {lib}...")
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", lib],
            capture_output=True, text=True, timeout=180
        )
        if r.returncode == 0:
            safe_send(message.chat.id, f"✅ تم تثبيت {lib}")
        else:
            safe_send(message.chat.id, f"❌ فشل: {r.stderr[:300]}")
    except Exception as e:
        safe_send(message.chat.id, f"❌ خطأ: {e}")


@bot.callback_query_handler(func=lambda c: c.data == 'online_support')
def online_support_cb(call):
    safe_answer(call.id, "جارٍ الإرسال...")
    u = call.from_user
    safe_send(
        ADMIN_ID,
        f"📞 طلب دعم:\n\n"
        f"👤 {u.first_name}\n"
        f"🆔 <code>{u.id}</code>\n"
        f"📌 @{u.username or '—'}\n"
        f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    safe_send(call.message.chat.id, "✅ تم الإرسال للأدمن")


@bot.callback_query_handler(func=lambda c: c.data == 'speed')
def speed_cb(call):
    if not is_approved_user(call.from_user.id):
        safe_answer(call.id, "❌ تحتاج موافقة")
        return
    safe_answer(call.id, "⏳ قياس...")
    msg = safe_send(call.message.chat.id, "⏳ <b>قياس سرعة البوت...</b>")
    start = time.time()
    times = []
    for _ in range(3):
        t = time.time()
        time.sleep(0.1)
        times.append((time.time() - t) * 1000)
    avg = sum(times) / len(times)
    total = (time.time() - start) * 1000
    if avg < 50:
        r, e = "ممتازة!", "⚡"
    elif avg < 100:
        r, e = "جيدة جداً", "🚀"
    else:
        r, e = "جيدة", "👍"
    if msg:
        safe_edit(
            call.message.chat.id,
            msg.message_id,
            f"{e} <b>سرعة البوت:</b>\n\n"
            f"• الاستجابة: <code>{avg:.2f} ms</code>\n"
            f"• الكلي: <code>{total:.2f} ms</code>\n"
            f"• التقييم: <b>{r}</b>"
        )


# ========== التحكم بالبوت ==========
@bot.callback_query_handler(func=lambda c: c.data == 'bot_control')
def bot_control_cb(call):
    if not is_admin(call.from_user.id):
        safe_answer(call.id, "❌")
        return
    global bot_running
    markup = types.InlineKeyboardMarkup()
    status = "✅ يعمل" if bot_running else "⏸️ متوقف"
    if bot_running:
        markup.add(types.InlineKeyboardButton("🛑 إيقاف", callback_data='stop_bot_main'))
    else:
        markup.add(types.InlineKeyboardButton("⚡ تشغيل", callback_data='start_bot_main'))
    markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data='back_to_main'))
    res = safe_edit(
        call.message.chat.id,
        call.message.message_id,
        f"⚡ <b>تحكم البوت</b>\n\nالحالة: {status}",
        reply_markup=markup
    )
    if not res:
        safe_send(
            call.message.chat.id,
            f"⚡ <b>تحكم البوت</b>\n\nالحالة: {status}",
            reply_markup=markup
        )


@bot.callback_query_handler(func=lambda c: c.data == 'stop_bot_main')
def stop_main_cb(call):
    if not is_admin(call.from_user.id):
        return
    global bot_running
    bot_running = False
    for cid in list(bot_scripts.keys()):
        stop_all_for_chat(cid)
    safe_answer(call.id, "🛑 تم الإيقاف")
    bot_control_cb(call)


@bot.callback_query_handler(func=lambda c: c.data == 'start_bot_main')
def start_main_cb(call):
    if not is_admin(call.from_user.id):
        return
    global bot_running
    bot_running = True
    safe_answer(call.id, "⚡ تم التشغيل")
    bot_control_cb(call)


@bot.callback_query_handler(func=lambda c: c.data == 'protection_control')
def prot_cb(call):
    if not is_admin(call.from_user.id):
        safe_answer(call.id, "❌")
        return
    status = "✅ مفعل" if protection_enabled else "❌ معطل"
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("تفعيل", callback_data='enable_protection'),
        types.InlineKeyboardButton("تعطيل", callback_data='disable_protection')
    )
    markup.add(
        types.InlineKeyboardButton("منخفض", callback_data='protection_low'),
        types.InlineKeyboardButton("متوسط", callback_data='protection_medium'),
        types.InlineKeyboardButton("عالي", callback_data='protection_high')
    )
    markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data='back_to_main'))
    safe_edit(
        call.message.chat.id,
        call.message.message_id,
        f"⚙️ الحماية: {status}\nالمستوى: {protection_level}",
        reply_markup=markup
    )


@bot.callback_query_handler(func=lambda c: c.data in [
    'enable_protection', 'disable_protection',
    'protection_low', 'protection_medium', 'protection_high'
])
def prot_set_cb(call):
    global protection_enabled, protection_level
    if not is_admin(call.from_user.id):
        return
    if call.data == 'enable_protection':
        protection_enabled = True
    elif call.data == 'disable_protection':
        protection_enabled = False
    elif call.data == 'protection_low':
        protection_level = 'low'
    elif call.data == 'protection_medium':
        protection_level = 'medium'
    elif call.data == 'protection_high':
        protection_level = 'high'
    safe_answer(call.id, "✅ تم")
    prot_cb(call)


# ========== إدارة المستخدمين ==========
@bot.callback_query_handler(func=lambda c: c.data == 'manage_users')
def manage_users_cb(call):
    if not is_admin(call.from_user.id):
        return
    markup = types.InlineKeyboardMarkup()
    if pending_requests:
        markup.add(types.InlineKeyboardButton(
            f"📋 الانتظار ({len(pending_requests)})", callback_data='show_pending'
        ))
    markup.add(types.InlineKeyboardButton(
        f"✅ المعتمدون ({len(approved_users)})", callback_data='show_approved'
    ))
    markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data='back_to_main'))
    safe_edit(
        call.message.chat.id,
        call.message.message_id,
        f"👥 <b>إدارة المستخدمين</b>\n\n"
        f"✅ المعتمدون: {len(approved_users)}\n"
        f"⏳ الانتظار: {len(pending_requests)}",
        reply_markup=markup
    )


@bot.callback_query_handler(func=lambda c: c.data == 'show_pending')
def show_pending_cb(call):
    if not is_admin(call.from_user.id):
        return
    if not pending_requests:
        safe_answer(call.id, "لا توجد طلبات")
        return
    for uid, info in list(pending_requests.items())[:5]:
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("✅", callback_data=f'approve_{uid}'),
            types.InlineKeyboardButton("❌", callback_data=f'reject_{uid}')
        )
        safe_send(
            call.message.chat.id,
            f"👤 {info['first_name']}\n"
            f"🆔 <code>{uid}</code>\n"
            f"📌 @{info['username']}\n"
            f"⏰ {info['timestamp']}",
            reply_markup=markup
        )


@bot.callback_query_handler(func=lambda c: c.data.startswith('approve_'))
def approve_cb(call):
    if not is_admin(call.from_user.id):
        return
    uid = int(call.data.split('_')[1])
    if uid in pending_requests:
        info = pending_requests.pop(uid)
        approved_users.add(uid)
        try:
            bot.send_message(uid, "🎉 تمت الموافقة! أرسل /start")
        except Exception:
            pass
        safe_answer(call.id, "✅ تم القبول")
        safe_edit(
            call.message.chat.id,
            call.message.message_id,
            f"✅ تم قبول: {info['first_name']} ({uid})"
        )


@bot.callback_query_handler(func=lambda c: c.data.startswith('reject_'))
def reject_cb(call):
    if not is_admin(call.from_user.id):
        return
    uid = int(call.data.split('_')[1])
    if uid in pending_requests:
        info = pending_requests.pop(uid)
        try:
            bot.send_message(uid, "❌ تم رفض طلبك.")
        except Exception:
            pass
        safe_answer(call.id, "❌ تم الرفض")
        safe_edit(
            call.message.chat.id,
            call.message.message_id,
            f"❌ تم رفض: {info['first_name']} ({uid})"
        )


@bot.message_handler(commands=['rck'])
def broadcast_cmd(message):
    if not is_admin(message.from_user.id):
        return
    try:
        msg = message.text.split(' ', 1)[1]
        ok = 0
        fail = 0
        for uid in approved_users:
            try:
                bot.send_message(uid, msg)
                ok += 1
            except Exception:
                fail += 1
        safe_send(message.chat.id, f"📊 نجح: {ok}, فشل: {fail}")
    except Exception:
        safe_send(message.chat.id, "❌ استخدم: /rck الرسالة")


# ========== Global exception handler ==========
def global_exception_handler(exc_type, exc_value, exc_tb):
    logger.error("=" * 55)
    logger.error("UNCAUGHT EXCEPTION")
    logger.error("".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
    logger.error("=" * 55)


sys.excepthook = global_exception_handler


# ========== Signal handling ==========
def _signal_handler(signum, frame):
    logger.info(f"📴 Received signal {signum}, shutting down gracefully...")
    for cid in list(bot_scripts.keys()):
        stop_all_for_chat(cid)
    logger.info("👋 Goodbye")
    sys.exit(0)


try:
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
except Exception:
    pass


# ========== التشغيل الرئيسي ==========
if __name__ == '__main__':
    logger.info("🚀 Starting polling loop...")

    restart_count = 0
    while True:
        try:
            restart_count += 1
            logger.info(f"🔄 Polling attempt #{restart_count}")
            bot.infinity_polling(
                timeout=60,
                long_polling_timeout=60,
                skip_pending=True
            )
        except KeyboardInterrupt:
            logger.info("⏹️ Stopped by user")
            break
        except SystemExit:
            break
        except Exception as e:
            logger.error(f"❌ Polling crash: {e}")
            logger.error(traceback.format_exc())
            logger.info("🔁 Restarting in 5 seconds...")
            time.sleep(5)
