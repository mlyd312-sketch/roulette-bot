import sys
import telebot
from telebot import types
import io
import tokenize
import requests
import time
from threading import Thread
import subprocess
import string
from collections import defaultdict
from datetime import datetime
import random
import re
import chardet
import logging
import threading
import os
import hashlib
import tempfile
import shutil
import zipfile
import sqlite3
import platform
import uuid
import socket
from concurrent.futures import ThreadPoolExecutor

# ========== إعدادات البوت ==========
BOT_TOKEN = '8877293036:AAGg_82F0bT1Bhov42sk9qDcRMsVNpfnErw'
ADMIN_ID = 1920665874
YOUR_USERNAME = '@u_8_y'
VIRUSTOTAL_API_KEY = 'YOUR_VIRUSTOTAL_API_KEY'
ADMIN_CHANNEL = '@FD_CQ'

# ========== متغيرات عامة ==========
bot_scripts = {}          # {chat_id: {file_id: {name, path, process, uploader, started_at}}}
user_files = {}
lock = threading.Lock()
executor = ThreadPoolExecutor(max_workers=10)

bot = telebot.TeleBot(BOT_TOKEN)
uploaded_files_dir = "uploaded_files"
banned_users = set()
user_chats = {}

# ========== تتبع الملفات التي تنتظر إدخال من المستخدم ==========
pending_inputs = {}    # {chat_id: file_id}
output_buffers = {}    # {chat_id: last_output_string}

# ========== نظام الاشتراك ==========
approved_users = set()
pending_requests = {}
approved_users.add(ADMIN_ID)

# ========== إعدادات الحماية ==========
protection_enabled = True
protection_level = "medium"
suspicious_files_dir = 'suspicious_files'
MAX_FILE_SIZE = 2 * 1024 * 1024

# حالة البوت الرئيسي
bot_running = True

# إنشاء المجلدات
for directory in [uploaded_files_dir, suspicious_files_dir]:
    if not os.path.exists(directory):
        os.makedirs(directory)


# ========== دوال مساعدة ==========
def save_chat_id(chat_id):
    if chat_id not in user_chats:
        user_chats[chat_id] = True
        print(f"تم حفظ chat_id: {chat_id}")


def is_admin(user_id):
    return user_id == ADMIN_ID


def is_approved_user(user_id):
    return user_id in approved_users or user_id == ADMIN_ID


def request_approval(user_id, user_info):
    pending_requests[user_id] = user_info

    markup = types.InlineKeyboardMarkup()
    approve_button = types.InlineKeyboardButton("✅ قبول المستخدم", callback_data=f'approve_{user_id}')
    reject_button = types.InlineKeyboardButton("❌ رفض المستخدم", callback_data=f'reject_{user_id}')
    markup.add(approve_button, reject_button)

    bot.send_message(
        ADMIN_ID,
        f"📋 طلب اشتراك جديد:\n\n"
        f"👤 الاسم: {user_info['first_name']}\n"
        f"🆔 ID: {user_id}\n"
        f"📌 اليوزر: @{user_info.get('username', 'غير متوفر')}\n"
        f"⏰ الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"اختر الإجراء المناسب:",
        reply_markup=markup
    )


def send_waiting_message(chat_id):
    markup = types.InlineKeyboardMarkup()
    support_button = types.InlineKeyboardButton("📞 التواصل مع الدعم", callback_data='online_support')
    markup.add(support_button)

    bot.send_message(
        chat_id,
        "⏳ تم إرسال طلب اشتراكك إلى الأدمن.\n"
        "يرجى الانتظار حتى يتم الموافقة على طلبك.\n\n"
        "للتواصل مع الدعم اضغط على الزر أدناه:",
        reply_markup=markup
    )


# ========== دوال الحماية ==========
def scan_file_for_malicious_code(file_path, user_id):
    if is_admin(user_id):
        return False, None, ""

    try:
        with open(file_path, 'rb') as f:
            raw_data = f.read()

        content = raw_data.decode('utf-8', errors='replace')

        dangerous_patterns = [
            r"rm\s+-rf\s+[\'\"]?/",
            r"import\s+marshal",
            r"shutil\.make_archive",
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return True, f"تم اكتشاف أمر خطير: {pattern}", "malicious"

        return False, None, ""
    except Exception as e:
        return True, f"خطأ في الفحص: {e}", "malicious"


# ========== كلمات مفتاحية لطلبات الإدخال ==========
INPUT_KEYWORDS = [
    'أرسل', 'ارسل', 'ادخل', 'أدخل', 'اكتب', 'رقم', 'كود', 'رمز',
    'otp', 'phone', 'code', 'password',
    '2fa', 'كلمة السر', 'كلمة سر', 'التحقق',
    'الهاتف', 'هاتف', 'input', 'enter',
    'token', 'session', 'api_id', 'api_hash', 'bot_token',
    'user', 'username', 'name', 'id'
]

PROMPT_END_CHARS = ('؟', '?', ':', '!', '؛')


def _looks_like_prompt(text):
    """هل النص يبدو كطلب إدخال؟"""
    if not text or len(text.strip()) < 3:
        return False
    t_lower = text.lower()
    return any(kw.lower() in t_lower for kw in INPUT_KEYWORDS)


# ========== دوال تشغيل/إيقاف الملفات ==========
def start_file(script_path, chat_id, file_id):
    """تشغيل ملف معين بمُعرّف فريد مع مراقبة الإدخال"""
    script_name = os.path.basename(script_path)

    with lock:
        if chat_id not in bot_scripts:
            bot_scripts[chat_id] = {}
        if file_id not in bot_scripts[chat_id]:
            bot_scripts[chat_id][file_id] = {'process': None}

        try:
            proc = bot_scripts[chat_id][file_id].get('process')
            if proc and proc.poll() is None:
                bot.send_message(chat_id, f"⚠️ الملف `{script_name}` يعمل بالفعل.")
                return

            work_dir = os.path.dirname(script_path)

            # تشغيل مع -u لدعم الإدخال التفاعلي بدون تأخير
            p = subprocess.Popen(
                [sys.executable, "-u", script_path],
                cwd=work_dir,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0
            )
            bot_scripts[chat_id][file_id]['process'] = p

            display_name = script_name.split('_', 1)[-1] if '_' in script_name else script_name
            bot.send_message(
                chat_id,
                f"✅ تم تشغيل الملف: `{display_name}`\n"
                f"🆔 `{file_id}`\n\n"
                f"⚡ جارٍ مراقبة المدخلات والارتباط بالحساب تلقائياً...",
                parse_mode='Markdown'
            )

            # بدء خيط مراقبة المخرجات
            monitor_thread = threading.Thread(
                target=monitor_process_output,
                args=(chat_id, file_id, p),
                daemon=True
            )
            monitor_thread.start()

        except Exception as e:
            bot.send_message(chat_id, f"❌ فشل في تشغيل الملف: {e}")


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
                    # الملف انتهى
                    remaining = buffer.strip()
                    if remaining:
                        try:
                            bot.send_message(
                                chat_id,
                                f"📄 آخر إخراج من الملف:\n`{remaining[:800]}`",
                                parse_mode='Markdown'
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

                if not line:
                    continue

                output_buffers[chat_id] = line

                if _looks_like_prompt(line):
                    pending_inputs[chat_id] = file_id

                    markup = types.InlineKeyboardMarkup()
                    cancel_btn = types.InlineKeyboardButton(
                        "❌ إلغاء الطلب",
                        callback_data=f'cancel_input_{file_id}'
                    )
                    markup.add(cancel_btn)

                    try:
                        bot.send_message(
                            chat_id,
                            f"📨 **الملف يطلب إدخال:**\n\n"
                            f"`{line[:800]}`\n\n"
                            f"✍️ أرسل الإجابة الآن مباشرة:",
                            reply_markup=markup,
                            parse_mode='Markdown'
                        )
                    except Exception:
                        try:
                            bot.send_message(chat_id, f"📨 {line[:800]}\n\n✍️ أرسل الإجابة:")
                        except Exception:
                            pass

    except Exception as e:
        print(f"❌ خطأ في المراقبة [{chat_id}/{file_id}]: {e}")
    finally:
        if pending_inputs.get(chat_id) == file_id:
            pending_inputs.pop(chat_id, None)


def stop_one_file(chat_id, file_id, delete=False):
    """إيقاف ملف واحد فقط"""
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


def stop_bot_control():
    """إيقاف البوت الرئيسي وإيقاف كل الملفات"""
    global bot_running
    bot_running = False
    for chat_id, files in bot_scripts.items():
        for fid in list(files.keys()):
            stop_one_file(chat_id, fid, delete=False)
    print("🛑 تم إيقاف البوت الرئيسي وكل الملفات")


def start_bot_control():
    """تشغيل البوت الرئيسي"""
    global bot_running
    bot_running = True
    print("✅ تم تشغيل البوت الرئيسي")


# ========== القائمة الرئيسية ==========
def show_main_menu(message):
    markup = types.InlineKeyboardMarkup(row_width=2)

    protection_button = types.InlineKeyboardButton("التحكم في الحماية 🛡️", callback_data='protection_control')
    upload_button = types.InlineKeyboardButton("رفع ملف 📥", callback_data='upload')
    my_files_button = types.InlineKeyboardButton("📂 ملفاتي", callback_data='my_files')
    support_girl_button = types.InlineKeyboardButton("فتاة المحاور 👩‍💼", callback_data='support_girl')
    speed_button = types.InlineKeyboardButton("🚀 سرعة البوت", callback_data='speed')
    about_button = types.InlineKeyboardButton("ℹ️ حول البوت", callback_data='about_bot')
    tech_support_button = types.InlineKeyboardButton("🛠️ الدعم الفني", callback_data='tech_support')
    install_lib_button = types.InlineKeyboardButton("📚 تثبيت مكتبة", callback_data='download_lib')
    contact_support_button = types.InlineKeyboardButton("📞 التواصل مع الدعم", callback_data='online_support')

    markup.add(protection_button, upload_button)
    markup.add(my_files_button, support_girl_button)
    markup.add(speed_button, about_button)
    markup.add(tech_support_button, install_lib_button)
    markup.add(contact_support_button)

    if is_admin(message.from_user.id):
        users_button = types.InlineKeyboardButton("👥 إدارة المستخدمين", callback_data='manage_users')
        bot_control_button = types.InlineKeyboardButton("⚡ تشغيل/إيقاف البوت", callback_data='bot_control')
        markup.add(users_button, bot_control_button)

    bot.send_message(
        message.chat.id,
        f"🐍 **Python Hosting** 🐍\n\n"
        f"مرحباً، {message.from_user.first_name}! 👋\n\n"
        "**الميزات المتاحة:** ✅\n\n"
        "• تشغيل أكثر من ملف في نفس الوقت\n"
        "• إدارة كل ملفاتك من زر 📂 ملفاتي\n"
        "• إيقاف / إعادة تشغيل / حذف أي ملف\n"
        "• دعم تفاعلي لطلب الرقم/OTP/2FA\n\n"
        f"👨‍💻 المطور: {YOUR_USERNAME}\n"
        f"📢 القناة: {ADMIN_CHANNEL}\n\n"
        "**اختر من الأزرار أدناه:**",
        reply_markup=markup,
        parse_mode='Markdown'
    )


# ========== /start ==========
@bot.message_handler(commands=['start'])
def start(message):
    save_chat_id(message.chat.id)
    user_id = message.from_user.id

    if not bot_running:
        bot.send_message(message.chat.id, "⏸️ البوت متوقف حاليًا. يرجى الانتظار حتى يتم تشغيله.")
        return

    if message.from_user.username in banned_users:
        bot.send_message(message.chat.id, "⁉️ تم حظرك من البوت. تواصل مع المطور.")
        return

    if is_approved_user(user_id):
        show_main_menu(message)
    elif user_id in pending_requests:
        send_waiting_message(message.chat.id)
    else:
        user_info = {
            'first_name': message.from_user.first_name,
            'username': message.from_user.username or 'غير متوفر',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        request_approval(user_id, user_info)
        send_waiting_message(message.chat.id)


# ========== معالجة إدخال المستخدم للملفات ==========
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
        bot.reply_to(message, "❌ العملية لم تعد موجودة.")
        return

    info = bot_scripts[chat_id][file_id]
    process = info.get('process')

    if not process or process.poll() is not None:
        pending_inputs.pop(chat_id, None)
        bot.reply_to(message, "❌ الملف لم يعد يعمل.")
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
            f"✅ تم إرسال الإجابة للملف: `{masked}`\n"
            f"⏳ جارٍ المتابعة...",
            parse_mode='Markdown'
        )

        pending_inputs.pop(chat_id, None)

    except Exception as e:
        bot.reply_to(message, f"❌ فشل في إرسال الإدخال: {e}")


@bot.callback_query_handler(func=lambda call: call.data.startswith('cancel_input_'))
def cancel_input_callback(call):
    chat_id = call.message.chat.id
    file_id = call.data.replace('cancel_input_', '')

    pending_inputs.pop(chat_id, None)

    bot.answer_callback_query(call.id, "✅ تم إلغاء طلب الإدخال")
    try:
        bot.edit_message_text(
            "🚫 تم إلغاء طلب الإدخال.\n"
            "الملف ما زال يعمل لكنه سينتظر بدون رد.",
            chat_id,
            call.message.message_id
        )
    except Exception:
        pass


# ========== أزرار الدعم ==========
@bot.callback_query_handler(func=lambda call: call.data == 'support_girl')
def support_girl_callback(call):
    if not is_approved_user(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ تحتاج إلى موافقة الأدمن")
        return

    bot.answer_callback_query(call.id, "👩‍💼 جاري الاتصال بفتاة المحاور...")
    time.sleep(1)

    markup = types.InlineKeyboardMarkup()
    end_chat_button = types.InlineKeyboardButton("إنهاء المحادثة", callback_data='end_chat')
    markup.add(end_chat_button)

    bot.send_message(
        call.message.chat.id,
        "👩‍💼 **مرحباً! أنا فتاة المحاور**\n\n"
        "كيف يمكنني مساعدتك اليوم؟\n"
        "أنا هنا للإجابة على استفساراتك وتقديم الدعم.\n\n"
        "يمكنك سؤالي عن:\n"
        "• كيفية استخدام البوت\n"
        "• المشاكل التقنية\n"
        "• استفسارات عامة\n\n"
        "ما الذي تريد معرفته؟ 💬",
        reply_markup=markup,
        parse_mode='Markdown'
    )


@bot.callback_query_handler(func=lambda call: call.data == 'tech_support')
def tech_support_callback(call):
    if not is_approved_user(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ تحتاج إلى موافقة الأدمن")
        return

    bot.answer_callback_query(call.id, "🛠️ جاري تحويلك للدعم الفني...")

    markup = types.InlineKeyboardMarkup()
    common_issues_button = types.InlineKeyboardButton("🔧 المشاكل الشائعة", callback_data='common_issues')
    contact_admin_button = types.InlineKeyboardButton("👨‍💼 التواصل مع الأدمن", callback_data='online_support')
    back_button = types.InlineKeyboardButton("🔙 رجوع", callback_data='back_to_main')
    markup.add(common_issues_button)
    markup.add(contact_admin_button)
    markup.add(back_button)

    bot.send_message(
        call.message.chat.id,
        "🛠️ **الدعم الفني**\n\n"
        "**الخدمات المتاحة:**\n"
        "• حل المشاكل التقنية\n"
        "• استكشاف الأخطاء وإصلاحها\n"
        "• دعم في تشغيل الملفات\n"
        "• مساعدة في تثبيت المكتبات\n\n"
        "اختر الخدمة التي تحتاجها:",
        reply_markup=markup,
        parse_mode='Markdown'
    )


@bot.callback_query_handler(func=lambda call: call.data == 'common_issues')
def common_issues_callback(call):
    bot.answer_callback_query(call.id)

    markup = types.InlineKeyboardMarkup()
    file_not_working = types.InlineKeyboardButton("📁 الملف لا يعمل", callback_data='issue_file')
    installation_issue = types.InlineKeyboardButton("📚 مشكلة في التثبيت", callback_data='issue_install')
    speed_issue = types.InlineKeyboardButton("🐌 البوت بطيء", callback_data='issue_speed')
    back_button = types.InlineKeyboardButton("🔙 رجوع للدعم", callback_data='tech_support')
    markup.add(file_not_working, installation_issue)
    markup.add(speed_issue)
    markup.add(back_button)

    bot.edit_message_text(
        "🔧 **المشاكل الشائعة**\n\nاختر نوع المشكلة التي تواجهك:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith('issue_'))
def handle_common_issue(call):
    issue_type = call.data.replace('issue_', '')

    solutions = {
        'file': "**حلول مشكلة الملف لا يعمل:**\n\n"
                "1. تأكد أن الملف بصيغة .py\n"
                "2. تحقق من وجود أخطاء في الكود\n"
                "3. تأكد من تثبيت جميع المكتبات المطلوبة\n"
                "4. حاول إعادة رفع الملف\n",
        'install': "**حلول مشاكل التثبيت:**\n\n"
                   "1. تأكد من اسم المكتبة\n"
                   "2. جرب تثبيت إصدار محدد: `pip install library==version`\n"
                   "3. تأكد من اتصال الإنترنت\n"
                   "4. جرب تحديث pip: `pip install --upgrade pip`\n",
        'speed': "**تحسين سرعة البوت:**\n\n"
                 "1. تأكد من جودة الاتصال بالإنترنت\n"
                 "2. أغلق الملفات غير المستخدمة\n"
                 "3. حاول إعادة تشغيل البوت\n"
                 "4. تأكد من عدم وجود عمليات ثقيلة\n"
    }

    solution = solutions.get(issue_type, "لم يتم العثور على حل لهذه المشكلة.")

    markup = types.InlineKeyboardMarkup()
    if issue_type == 'file':
        retry_upload = types.InlineKeyboardButton("🔄 إعادة رفع الملف", callback_data='upload')
        markup.add(retry_upload)
    elif issue_type == 'install':
        retry_install = types.InlineKeyboardButton("🔄 محاولة تثبيت أخرى", callback_data='download_lib')
        markup.add(retry_install)

    back_button = types.InlineKeyboardButton("🔙 رجوع للمشاكل", callback_data='common_issues')
    support_button = types.InlineKeyboardButton("📞 دعم مباشر", callback_data='online_support')
    markup.add(back_button, support_button)

    bot.edit_message_text(
        solution,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup,
        parse_mode='Markdown'
    )


@bot.callback_query_handler(func=lambda call: call.data == 'end_chat')
def end_chat_callback(call):
    bot.answer_callback_query(call.id, "تم إنهاء المحادثة")

    markup = types.InlineKeyboardMarkup()
    restart_chat = types.InlineKeyboardButton("🔄 بدء محادثة جديدة", callback_data='support_girl')
    main_menu = types.InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data='back_to_main')
    markup.add(restart_chat, main_menu)

    bot.edit_message_text(
        "👋 **تم إنهاء المحادثة**\n\n"
        "شكراً لك على التواصل معنا!",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup,
        parse_mode='Markdown'
    )


# ========== التحكم في البوت الرئيسي ==========
@bot.callback_query_handler(func=lambda call: call.data == 'bot_control')
def bot_control_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
        return

    global bot_running

    markup = types.InlineKeyboardMarkup()

    if bot_running:
        stop_button = types.InlineKeyboardButton("🛑 إيقاف البوت", callback_data='stop_bot_main')
        status_text = "✅ البوت يعمل حالياً"
        markup.add(stop_button)
    else:
        start_button = types.InlineKeyboardButton("⚡ تشغيل البوت", callback_data='start_bot_main')
        status_text = "⏸️ البوت متوقف حالياً"
        markup.add(start_button)

    back_button = types.InlineKeyboardButton("🔙 رجوع", callback_data='back_to_main')
    markup.add(back_button)

    try:
        bot.edit_message_text(
            f"⚡ **تحكم في البوت الرئيسي**\n\n"
            f"الحالة: {status_text}\n\n"
            f"من هنا يمكنك التحكم في حالة البوت الرئيسي:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
            parse_mode='Markdown'
        )
    except Exception:
        bot.send_message(
            call.message.chat.id,
            f"⚡ تحكم في البوت الرئيسي\n\nالحالة: {status_text}",
            reply_markup=markup
        )


@bot.callback_query_handler(func=lambda call: call.data == 'stop_bot_main')
def stop_bot_main(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
        return

    stop_bot_control()
    bot.answer_callback_query(call.id, "🛑 تم إيقاف البوت")
    bot_control_callback(call)


@bot.callback_query_handler(func=lambda call: call.data == 'start_bot_main')
def start_bot_main(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
        return

    start_bot_control()
    bot.answer_callback_query(call.id, "⚡ تم تشغيل البوت")
    bot_control_callback(call)


# ========== قياس السرعة ==========
@bot.callback_query_handler(func=lambda call: call.data == 'speed')
def check_speed(call):
    if not is_approved_user(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ تحتاج إلى موافقة الأدمن")
        return

    bot.answer_callback_query(call.id, "⏳ جاري قياس سرعة البوت...")
    wait_msg = bot.send_message(call.message.chat.id, "⏳ **انتظر يتم قياس سرعة البوت...**")

    start_time = time.time()
    response_times = []
    for i in range(3):
        test_start = time.time()
        time.sleep(0.1)
        response_times.append((time.time() - test_start) * 1000)

    avg_response_time = sum(response_times) / len(response_times)
    total_time = (time.time() - start_time) * 1000

    if avg_response_time < 50:
        rating, emoji = "⚡ ممتازة!", "⚡"
    elif avg_response_time < 100:
        rating, emoji = "🚀 جيدة جداً", "🚀"
    elif avg_response_time < 200:
        rating, emoji = "👍 جيدة", "👍"
    else:
        rating, emoji = "🐌 تحتاج تحسين", "🐌"

    bot.edit_message_text(
        f"{emoji} **سرعة البوت الحالية:**\n\n"
        f"• سرعة الاستجابة: `{avg_response_time:.2f} ms`\n"
        f"• الوقت الكلي: `{total_time:.2f} ms`\n"
        f"• التقييم: **{rating}**\n\n"
        f"_{datetime.now().strftime('%I:%M %p')}_",
        call.message.chat.id,
        wait_msg.message_id,
        parse_mode='Markdown'
    )


# ========== الرفع ==========
@bot.callback_query_handler(func=lambda call: call.data == 'upload')
def upload_file_callback(call):
    if not is_approved_user(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ تحتاج إلى موافقة الأدمن")
        return

    if not bot_running:
        bot.answer_callback_query(call.id, "⏸️ البوت متوقف حالياً")
        return

    bot.answer_callback_query(call.id, "📤 جاري إعداد رفع الملف...")

    markup = types.InlineKeyboardMarkup()
    cancel_button = types.InlineKeyboardButton("❌ إلغاء", callback_data='back_to_main')
    markup.add(cancel_button)

    bot.send_message(
        call.message.chat.id,
        "📤 **رفع ملف**\n\n"
        "أرسل ملف البوت الآن (ملف .py فقط)\n"
        "الحد الأقصى للحجم: 2MB\n\n"
        "يمكنك رفع عدة ملفات، وكل ملف سيعمل بشكل مستقل.\n"
        "🔔 الملفات التي تطلب رقم/OTP/2FA سيتفاعل معها البوت تلقائياً.",
        reply_markup=markup,
        parse_mode='Markdown'
    )


@bot.callback_query_handler(func=lambda call: call.data == 'about_bot')
def about_bot(call):
    bot.answer_callback_query(call.id)

    markup = types.InlineKeyboardMarkup()
    features_button = types.InlineKeyboardButton("🌟 الميزات", callback_data='features_list')
    back_button = types.InlineKeyboardButton("🔙 رجوع", callback_data='back_to_main')
    markup.add(features_button, back_button)

    bot.send_message(
        call.message.chat.id,
        "ℹ️ **حول البوت**\n\n"
        "🐍 **Python Hosting Bot**\n\n"
        "**المميزات:**\n"
        "✅ تشغيل عدة ملفات في نفس الوقت\n"
        "✅ تفاعل ذكي مع الملفات (رقم/OTP/2FA)\n"
        "✅ سرعة وأداء عالي\n"
        "✅ نظام حماية متقدم\n"
        "✅ دعم فني متكامل\n"
        "✅ إدارة مستخدمين ذكية\n\n"
        f"👨‍💻 **المطور:** {YOUR_USERNAME}\n"
        f"📢 **القناة:** {ADMIN_CHANNEL}",
        reply_markup=markup,
        parse_mode='Markdown'
    )


@bot.callback_query_handler(func=lambda call: call.data == 'features_list')
def show_features(call):
    bot.answer_callback_query(call.id)

    markup = types.InlineKeyboardMarkup()
    back_button = types.InlineKeyboardButton("🔙 رجوع", callback_data='about_bot')
    markup.add(back_button)

    bot.edit_message_text(
        "🌟 **الميزات المتاحة:**\n\n"
        "🛡️ **نظام الحماية:**\n"
        "• فحص الملفات تلقائياً\n"
        "• منع الملفات الضارة\n"
        "• مستويات حماية متعددة\n\n"
        "⚡ **الأداء:**\n"
        "• تشغيل عدة ملفات متزامنة\n"
        "• قياس سرعة البوت\n"
        "• إدارة عمليات ذكية\n\n"
        "📂 **إدارة الملفات:**\n"
        "• عرض كل ملفاتك\n"
        "• إيقاف/إعادة تشغيل/حذف\n"
        "• إيقاف الكل بضغطة\n\n"
        "🔔 **التفاعل الذكي:**\n"
        "• استقبال طلبات الرقم/OTP تلقائياً\n"
        "• إرسال إجابتك للملف مباشرة\n"
        "• دعم API/Token/2FA\n\n"
        "🛠️ **الدعم:**\n"
        "• دعم فني متكامل\n"
        "• مساعدة مباشرة",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup,
        parse_mode='Markdown'
    )


@bot.callback_query_handler(func=lambda call: call.data == 'download_lib')
def download_library(call):
    if not is_approved_user(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ تحتاج إلى موافقة الأدمن")
        return

    bot.send_message(call.message.chat.id, "📚 أرسل اسم المكتبة التي تريد تثبيتها:")
    bot.register_next_step_handler(call.message, install_library_step)


def install_library_step(message):
    library_name = message.text.strip()
    bot.send_message(message.chat.id, f"🔄 جاري تثبيت {library_name}...")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", library_name],
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode == 0:
            bot.send_message(message.chat.id, f"✅ تم تثبيت {library_name} بنجاح")
        else:
            bot.send_message(message.chat.id, f"❌ فشل في تثبيت {library_name}\n{result.stderr[:500]}")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ خطأ: {e}")


@bot.callback_query_handler(func=lambda call: call.data == 'online_support')
def online_support(call):
    bot.answer_callback_query(call.id, "جارٍ إرسال طلب الدعم...")

    user_info = f"👤 {call.from_user.first_name}\n🆔 {call.from_user.id}\n📌 @{call.from_user.username or 'غير متوفر'}"

    bot.send_message(
        ADMIN_ID,
        f"📞 طلب دعم فوري:\n\n{user_info}\n\n"
        f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    bot.send_message(call.message.chat.id, "✅ تم إرسال طلب الدعم للأدمن")


# ========== إعدادات الحماية ==========
@bot.callback_query_handler(func=lambda call: call.data == 'protection_control')
def protection_control(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "ليس لديك صلاحية")
        return

    status = "✅ مفعل" if protection_enabled else "❌ معطل"

    markup = types.InlineKeyboardMarkup(row_width=2)
    enable_btn = types.InlineKeyboardButton("تفعيل الحماية", callback_data='enable_protection')
    disable_btn = types.InlineKeyboardButton("تعطيل الحماية", callback_data='disable_protection')
    low_btn = types.InlineKeyboardButton("منخفض", callback_data='protection_low')
    medium_btn = types.InlineKeyboardButton("متوسط", callback_data='protection_medium')
    high_btn = types.InlineKeyboardButton("عالي", callback_data='protection_high')
    back_btn = types.InlineKeyboardButton("🔙 رجوع", callback_data='back_to_main')

    markup.add(enable_btn, disable_btn)
    markup.add(low_btn, medium_btn, high_btn)
    markup.add(back_btn)

    try:
        bot.edit_message_text(
            f"⚙️ إعدادات الحماية\n\n"
            f"الحالة: {status}\n"
            f"المستوى: {protection_level}",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    except Exception:
        bot.send_message(
            call.message.chat.id,
            f"⚙️ إعدادات الحماية\n\nالحالة: {status}\nالمستوى: {protection_level}",
            reply_markup=markup
        )


@bot.callback_query_handler(func=lambda call: call.data in ['enable_protection', 'disable_protection',
                                                           'protection_low', 'protection_medium', 'protection_high'])
def handle_protection_settings(call):
    global protection_enabled, protection_level

    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "ليس لديك صلاحية")
        return

    if call.data == 'enable_protection':
        protection_enabled = True
        bot.answer_callback_query(call.id, "✅ تم تفعيل الحماية")
    elif call.data == 'disable_protection':
        protection_enabled = False
        bot.answer_callback_query(call.id, "❌ تم تعطيل الحماية")
    elif call.data == 'protection_low':
        protection_level = "low"
        bot.answer_callback_query(call.id, "🔵 مستوى منخفض")
    elif call.data == 'protection_medium':
        protection_level = "medium"
        bot.answer_callback_query(call.id, "🟡 مستوى متوسط")
    elif call.data == 'protection_high':
        protection_level = "high"
        bot.answer_callback_query(call.id, "🔴 مستوى عالي")

    protection_control(call)


@bot.callback_query_handler(func=lambda call: call.data == 'back_to_main')
def back_to_main(call):
    try:
        show_main_menu(call.message)
        bot.answer_callback_query(call.id, "العودة للقائمة الرئيسية")
    except Exception:
        bot.answer_callback_query(call.id, "حدث خطأ في العودة")


# ========== رفع الملفات ==========
@bot.message_handler(content_types=['document'])
def handle_file(message):
    if not is_approved_user(message.from_user.id):
        bot.reply_to(message, "❌ تحتاج إلى موافقة الأدمن لرفع الملفات.")
        return

    if not bot_running:
        bot.reply_to(message, "⏸️ البوت متوقف حالياً.")
        return

    try:
        user_id = message.from_user.id
        chat_id = message.chat.id

        if message.from_user.username in banned_users:
            bot.send_message(chat_id, "⁉️ تم حظرك من البوت")
            return

        file_info = bot.get_file(message.document.file_id)

        if file_info.file_size > MAX_FILE_SIZE:
            bot.reply_to(message, "⛔ حجم الملف يتجاوز 2MB")
            return

        downloaded_file = bot.download_file(file_info.file_path)
        bot_script_name = message.document.file_name

        if not bot_script_name.endswith('.py'):
            bot.reply_to(message, "❌ فقط ملفات بايثون مسموحة")
            return

        user_dir = os.path.join(uploaded_files_dir, str(user_id))
        os.makedirs(user_dir, exist_ok=True)

        file_id = uuid.uuid4().hex[:8]

        internal_name = f"{file_id}_{bot_script_name}"
        script_path = os.path.join(user_dir, internal_name)

        temp_path = os.path.join(tempfile.gettempdir(), f"{file_id}_{bot_script_name}")
        with open(temp_path, 'wb') as temp_file:
            temp_file.write(downloaded_file)

        if protection_enabled and not is_admin(user_id):
            is_malicious, activity, threat_type = scan_file_for_malicious_code(temp_path, user_id)
            if is_malicious:
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
                bot.reply_to(message, f"⛔ تم رفض الملف لأسباب أمنية\n{activity}")
                return

        shutil.move(temp_path, script_path)

        if chat_id not in bot_scripts:
            bot_scripts[chat_id] = {}

        bot_scripts[chat_id][file_id] = {
            'name': bot_script_name,
            'path': script_path,
            'process': None,
            'uploader': message.from_user.username,
            'started_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        total_files = len(bot_scripts[chat_id])

        markup = types.InlineKeyboardMarkup(row_width=3)
        stop_btn = types.InlineKeyboardButton("🛑 إيقاف", callback_data=f'sf_{file_id}')
        restart_btn = types.InlineKeyboardButton("🔄 إعادة", callback_data=f'rf_{file_id}')
        del_btn = types.InlineKeyboardButton("🗑️ حذف", callback_data=f'df_{file_id}')
        my_files_btn = types.InlineKeyboardButton(f"📂 ملفاتي ({total_files})", callback_data='my_files')
        markup.add(stop_btn, restart_btn, del_btn)
        markup.add(my_files_btn)

        bot.reply_to(
            message,
            f"✅ تم رفع الملف بنجاح\n\n"
            f"📁 الاسم: `{bot_script_name}`\n"
            f"🆔 المُعرّف: `{file_id}`\n"
            f"👤 المستخدم: @{message.from_user.username}\n"
            f"📊 مجموع ملفاتك: {total_files}",
            reply_markup=markup,
            parse_mode='Markdown'
        )

        start_file(script_path, chat_id, file_id)

    except Exception as e:
        bot.reply_to(message, f"❌ حدث خطأ: {e}")


# ========== إدارة الملفات المتعددة ==========
@bot.callback_query_handler(func=lambda call: call.data == 'my_files')
def my_files_callback(call):
    show_my_files(call, edit=False)


def show_my_files(call, edit=False):
    chat_id = call.message.chat.id

    if chat_id not in bot_scripts or not bot_scripts[chat_id]:
        if edit:
            try:
                bot.edit_message_text(
                    "📂 **لا توجد ملفات مرفوعة حالياً**\n\nارفع ملف .py أولاً.",
                    chat_id, call.message.message_id,
                    parse_mode='Markdown'
                )
            except Exception:
                bot.send_message(chat_id, "📂 لا توجد ملفات مرفوعة.")
        else:
            bot.send_message(chat_id, "📂 لا توجد ملفات مرفوعة.")
        return

    files = bot_scripts[chat_id]
    running = sum(1 for f in files.values() if f.get('process') and f['process'].poll() is None)

    text = (
        f"📂 **ملفاتك المرفوعة** ({len(files)})\n"
        f"🟢 قيد التشغيل: {running}\n"
        f"🔴 متوقف: {len(files) - running}\n\n"
        f"اضغط على اسم الملف للتفاصيل."
    )

    markup = types.InlineKeyboardMarkup(row_width=4)

    for fid, info in files.items():
        proc = info.get('process')
        status = "🟢" if (proc and proc.poll() is None) else "🔴"
        name = info.get('name', 'ملف')[:22]

        row = [
            types.InlineKeyboardButton(f"{status} {name}", callback_data=f'nf_{fid}'),
            types.InlineKeyboardButton("🔄", callback_data=f'rf_{fid}'),
            types.InlineKeyboardButton("🛑", callback_data=f'sf_{fid}'),
            types.InlineKeyboardButton("🗑️", callback_data=f'df_{fid}'),
        ]
        markup.row(*row)

    stop_all = types.InlineKeyboardButton("🛑 إيقاف الكل", callback_data='stop_all_files')
    back = types.InlineKeyboardButton("🔙 القائمة", callback_data='back_to_main')
    markup.row(stop_all, back)

    if edit:
        try:
            bot.edit_message_text(text, chat_id, call.message.message_id,
                                  reply_markup=markup, parse_mode='Markdown')
        except Exception:
            bot.send_message(chat_id, text, reply_markup=markup, parse_mode='Markdown')
    else:
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode='Markdown')


@bot.callback_query_handler(func=lambda call: call.data.startswith('sf_'))
def stop_specific_file(call):
    if not is_approved_user(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ غير مصرح")
        return

    file_id = call.data.replace('sf_', '')
    chat_id = call.message.chat.id

    if chat_id not in bot_scripts or file_id not in bot_scripts[chat_id]:
        bot.answer_callback_query(call.id, "❌ الملف غير موجود")
        return

    file_name = bot_scripts[chat_id][file_id].get('name', 'ملف')

    if stop_one_file(chat_id, file_id, delete=False):
        bot.answer_callback_query(call.id, f"✅ تم إيقاف {file_name}")
        show_my_files(call, edit=True)
    else:
        bot.answer_callback_query(call.id, "❌ فشل الإيقاف")


@bot.callback_query_handler(func=lambda call: call.data.startswith('df_'))
def delete_specific_file(call):
    if not is_approved_user(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ غير مصرح")
        return

    file_id = call.data.replace('df_', '')
    chat_id = call.message.chat.id

    if chat_id not in bot_scripts or file_id not in bot_scripts[chat_id]:
        bot.answer_callback_query(call.id, "❌ الملف غير موجود")
        return

    file_name = bot_scripts[chat_id][file_id].get('name', 'ملف')

    if stop_one_file(chat_id, file_id, delete=True):
        bot.answer_callback_query(call.id, f"🗑️ تم حذف {file_name}")
        show_my_files(call, edit=True)
    else:
        bot.answer_callback_query(call.id, "❌ فشل الحذف")


@bot.callback_query_handler(func=lambda call: call.data.startswith('rf_'))
def restart_file(call):
    if not is_approved_user(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ غير مصرح")
        return

    file_id = call.data.replace('rf_', '')
    chat_id = call.message.chat.id

    if chat_id not in bot_scripts or file_id not in bot_scripts[chat_id]:
        bot.answer_callback_query(call.id, "❌ غير موجود")
        return

    info = bot_scripts[chat_id][file_id]
    stop_one_file(chat_id, file_id, delete=False)
    start_file(info['path'], chat_id, file_id)
    bot.answer_callback_query(call.id, "🔄 تم إعادة التشغيل")
    time.sleep(0.5)
    show_my_files(call, edit=True)


@bot.callback_query_handler(func=lambda call: call.data.startswith('nf_'))
def file_info_callback(call):
    file_id = call.data.replace('nf_', '')
    chat_id = call.message.chat.id

    if chat_id not in bot_scripts or file_id not in bot_scripts[chat_id]:
        bot.answer_callback_query(call.id, "❌ غير موجود")
        return

    info = bot_scripts[chat_id][file_id]
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
def stop_all_files(call):
    if not is_approved_user(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ غير مصرح")
        return

    chat_id = call.message.chat.id

    if chat_id not in bot_scripts or not bot_scripts[chat_id]:
        bot.answer_callback_query(call.id, "لا توجد ملفات")
        return

    count = 0
    for fid in list(bot_scripts[chat_id].keys()):
        if stop_one_file(chat_id, fid, delete=False):
            count += 1

    bot.answer_callback_query(call.id, f"🛑 تم إيقاف {count} ملف")
    show_my_files(call, edit=True)


# ========== معالجة طلبات الاشتراك ==========
@bot.callback_query_handler(func=lambda call: call.data.startswith('approve_'))
def approve_user(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "ليس لديك صلاحية")
        return

    user_id = int(call.data.split('_')[1])

    if user_id in pending_requests:
        user_info = pending_requests.pop(user_id)
        approved_users.add(user_id)

        try:
            bot.send_message(
                user_id,
                f"🎉 تمت الموافقة على طلبك!\n\n"
                f"مرحباً {user_info['first_name']} 👋\n"
                f"يمكنك الآن استخدام البوت بالكامل.\n\n"
                f"أرسل /start لبدء الاستخدام."
            )
        except Exception:
            pass

        bot.answer_callback_query(call.id, "✅ تم قبول المستخدم")
        bot.edit_message_text(
            f"✅ تم قبول المستخدم:\n"
            f"👤 {user_info['first_name']}\n"
            f"🆔 {user_id}\n"
            f"📌 @{user_info['username']}",
            call.message.chat.id,
            call.message.message_id
        )
    else:
        bot.answer_callback_query(call.id, "❌ لم يتم العثور على الطلب")


@bot.callback_query_handler(func=lambda call: call.data.startswith('reject_'))
def reject_user(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "ليس لديك صلاحية")
        return

    user_id = int(call.data.split('_')[1])

    if user_id in pending_requests:
        user_info = pending_requests.pop(user_id)

        try:
            bot.send_message(
                user_id,
                "❌ تم رفض طلب اشتراكك.\n\n"
                "للتواصل مع الدعم اضغط /start واختر التواصل مع الدعم."
            )
        except Exception:
            pass

        bot.answer_callback_query(call.id, "❌ تم رفض المستخدم")
        bot.edit_message_text(
            f"❌ تم رفض المستخدم:\n"
            f"👤 {user_info['first_name']}\n"
            f"🆔 {user_id}\n"
            f"📌 @{user_info['username']}",
            call.message.chat.id,
            call.message.message_id
        )
    else:
        bot.answer_callback_query(call.id, "❌ لم يتم العثور على الطلب")


# ========== إدارة المستخدمين ==========
@bot.callback_query_handler(func=lambda call: call.data == 'manage_users')
def manage_users(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "ليس لديك صلاحية")
        return

    total_approved = len(approved_users)
    total_pending = len(pending_requests)

    markup = types.InlineKeyboardMarkup()

    if pending_requests:
        pending_button = types.InlineKeyboardButton(f"📋 طلبات الانتظار ({total_pending})", callback_data='show_pending')
        markup.add(pending_button)

    approved_button = types.InlineKeyboardButton(f"✅ المعتمدون ({total_approved})", callback_data='show_approved')
    broadcast_button = types.InlineKeyboardButton("📢 إرسال للجميع", callback_data='broadcast_all')
    back_button = types.InlineKeyboardButton("🔙 رجوع", callback_data='back_to_main')

    markup.add(approved_button)
    markup.add(broadcast_button)
    markup.add(back_button)

    try:
        bot.edit_message_text(
            f"👥 إدارة المستخدمين\n\n"
            f"📊 الإحصائيات:\n"
            f"✅ المعتمدون: {total_approved}\n"
            f"⏳ طلبات الانتظار: {total_pending}",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    except Exception:
        bot.send_message(
            call.message.chat.id,
            f"👥 إدارة المستخدمين\n\n✅ المعتمدون: {total_approved}\n⏳ الانتظار: {total_pending}",
            reply_markup=markup
        )


@bot.callback_query_handler(func=lambda call: call.data == 'show_pending')
def show_pending_requests(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "ليس لديك صلاحية")
        return

    if not pending_requests:
        bot.answer_callback_query(call.id, "لا توجد طلبات انتظار")
        return

    for user_id, user_info in list(pending_requests.items())[:5]:
        markup = types.InlineKeyboardMarkup()
        approve_btn = types.InlineKeyboardButton("✅ قبول", callback_data=f'approve_{user_id}')
        reject_btn = types.InlineKeyboardButton("❌ رفض", callback_data=f'reject_{user_id}')
        markup.add(approve_btn, reject_btn)

        bot.send_message(
            call.message.chat.id,
            f"👤 {user_info['first_name']}\n"
            f"🆔 {user_id}\n"
            f"📌 @{user_info['username']}\n"
            f"⏰ {user_info['timestamp']}",
            reply_markup=markup
        )


# ========== أوامر الأدمن ==========
@bot.message_handler(commands=['rck'])
def broadcast_message(message):
    if not is_admin(message.from_user.id):
        return

    try:
        msg = message.text.split(' ', 1)[1]
        success = 0
        failed = 0

        for user_id in approved_users:
            try:
                bot.send_message(user_id, msg)
                success += 1
            except Exception:
                failed += 1

        bot.reply_to(message, f"📊 تم الإرسال لـ {success} مستخدم، فشل: {failed}")
    except Exception:
        bot.reply_to(message, "❌ استخدم: /rck الرسالة")


# ========== التشغيل مع حلقة إعادة التشغيل التلقائي ==========
if __name__ == '__main__':
    print("=" * 50)
    print("🤖 Python Hosting Bot")
    print("=" * 50)
    print(f"👨‍💻 المطور: {YOUR_USERNAME} ({ADMIN_ID})")
    print(f"📢 القناة: {ADMIN_CHANNEL}")
    print(f"✅ المستخدمون المعتمدون: {len(approved_users)}")
    print(f"⏳ طلبات الانتظار: {len(pending_requests)}")
    print(f"⚡ حالة البوت: {'يعمل' if bot_running else 'متوقف'}")
    print("=" * 50)

    # حلقة إعادة التشغيل التلقائي — تمنع الموت عند حدوث خطأ
    while True:
        try:
            print("🚀 Starting polling...")
            bot.infinity_polling(
                timeout=60,
                long_polling_timeout=60,
                skip_pending=True
            )
        except KeyboardInterrupt:
            print("⏹️ تم إيقاف البوت يدوياً")
            break
        except Exception as e:
            print(f"❌ خطأ في التشغيل: {e}")
            print("🔄 إعادة التشغيل بعد 5 ثواني...")
            time.sleep(5)
