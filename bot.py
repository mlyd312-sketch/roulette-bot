import sys
import os
import re
import time
import shutil
import tempfile
import threading
import subprocess
from datetime import datetime
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import telebot
from telebot import types

# ======= إعدادات البوت الأساسية ======= #
BOT_TOKEN = '8177794176:AAF390geeHv0-87Bubl_bqKiDoH7mPjDSdE'
ADMIN_ID = 1920665874
YOUR_USERNAME = '@u_8_y'
ADMIN_CHANNEL = '@FD_CQ'
VIRUSTOTAL_API_KEY = 'YOUR_VIRUSTOTAL_API_KEY'

bot = telebot.TeleBot(BOT_TOKEN)

# إعدادات النظام والمجلدات
uploaded_files_dir = "uploaded_files"
suspicious_files_dir = 'suspicious_files'
MAX_FILE_SIZE = 2 * 1024 * 1024

for directory in [uploaded_files_dir, suspicious_files_dir]:
    if not os.path.exists(directory):
        os.makedirs(directory)

# متغيرات النظام
bot_scripts = {}
user_chats = {}
banned_users = set()
approved_users = {ADMIN_ID}
pending_requests = {}

protection_enabled = True
protection_level = "medium"
bot_running = True

lock = threading.Lock()
executor = ThreadPoolExecutor(max_workers=10)

# ======= دوال مساعدة ======= #
def save_chat_id(chat_id):
    if chat_id not in user_chats:
        user_chats[chat_id] = True

def is_admin(user_id):
    return user_id == ADMIN_ID

def is_approved_user(user_id):
    return user_id in approved_users or is_admin(user_id)

def request_approval(user_id, user_info):
    pending_requests[user_id] = user_info
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ قبول المستخدم", callback_data=f'approve_{user_id}'),
        types.InlineKeyboardButton("❌ رفض المستخدم", callback_data=f'reject_{user_id}')
    )
    
    username_val = user_info.get('username', 'غير متوفر')
    msg_text = (
        "📋 **طلب اشتراك جديد:**\n\n"
        f"👤 الاسم: {user_info['first_name']}\n"
        f"🆔 ID: `{user_id}`\n"
        f"📌 اليوزر: @{username_val}\n"
        f"⏰ الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    bot.send_message(ADMIN_ID, msg_text, reply_markup=markup, parse_mode='Markdown')

def send_waiting_message(chat_id):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📞 التواصل مع الدعم", callback_data='online_support'))
    msg_text = (
        "⏳ **تم إرسال طلب اشتراكك إلى الأدمن.**\n"
        "يرجى الانتظار حتى يتم قبول طلبك.\n\n"
        "للتواصل مع الدعم اضغط على الزر أدناه:"
    )
    bot.send_message(chat_id, msg_text, reply_markup=markup, parse_mode='Markdown')

# ======= دوال الفحص والتشغيل ======= #
def scan_file_for_malicious_code(file_path, user_id):
    if is_admin(user_id):
        return False, None, ""

    try:
        with open(file_path, 'rb') as f:
            content = f.read().decode('utf-8', errors='replace')

        dangerous_patterns = [
            r"rm\s+-rf\s+[\'\"]?/",
            r"import\s+marshal",
            r"import\s+zlib",
            r"import\s+base64",
            r"eval\s*\(",
            r"exec\s*\(",
            r"shutil\.make_archive",
            r"bot\.send_document",
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return True, f"تم اكتشاف أمر خطير: {pattern}", "malicious"

        return False, None, ""
    except Exception as e:
        return True, f"خطأ في الفحص: {e}", "malicious"

def run_script_task(script_path, chat_id):
    try:
        p = subprocess.Popen([sys.executable, script_path])
        with lock:
            if chat_id in bot_scripts:
                bot_scripts[chat_id]['process'] = p
        p.wait()
    except Exception as e:
        print(f"Error running script: {e}")

def start_file(script_path, chat_id):
    script_name = os.path.basename(script_path)
    with lock:
        if chat_id not in bot_scripts:
            bot_scripts[chat_id] = {'process': None, 'path': script_path}

        if bot_scripts[chat_id].get('process') and bot_scripts[chat_id]['process'].poll() is None:
            bot.send_message(chat_id, f"⚠️ الملف {script_name} يعمل بالفعل.")
            return

    executor.submit(run_script_task, script_path, chat_id)
    bot.send_message(chat_id, f"✅ تم تشغيل الملف `{script_name}` بنجاح.", parse_mode='Markdown')

def stop_bot_process(script_path, chat_id, delete=False):
    try:
        if chat_id in bot_scripts and bot_scripts[chat_id].get('process'):
            proc = bot_scripts[chat_id]['process']
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()

        if delete and os.path.exists(script_path):
            os.remove(script_path)

        return True
    except Exception as e:
        print(f"Error stopping bot: {e}")
        return False

# ======= القائمة الرئيسية والأوامر ======= #
def show_main_menu(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("التحكم في الحماية 🛡️", callback_data='protection_control'),
        types.InlineKeyboardButton("رفع ملف 📥", callback_data='upload')
    )
    markup.add(
        types.InlineKeyboardButton("فتاة المحاور 👩‍💼", callback_data='support_girl'),
        types.InlineKeyboardButton("🚀 سرعة البوت", callback_data='speed')
    )
    markup.add(
        types.InlineKeyboardButton("ℹ️ حول البوت", callback_data='about_bot'),
        types.InlineKeyboardButton("🛠️ الدعم الفني", callback_data='tech_support')
    )
    markup.add(
        types.InlineKeyboardButton("📚 تثبيت مكتبة", callback_data='download_lib'),
        types.InlineKeyboardButton("📞 التواصل مع الدعم", callback_data='online_support')
    )

    if is_admin(message.from_user.id):
        markup.add(
            types.InlineKeyboardButton("👥 إدارة المستخدمين", callback_data='manage_users'),
            types.InlineKeyboardButton("⚡ تشغيل/إيقاف البوت", callback_data='bot_control')
        )

    user_name = message.from_user.first_name
    main_text = (
        "🐍 **Python Hosting** 🐍\n\n"
        f"مرحباً، {user_name}! 👋\n\n"
        "**الميزات المتاحة:** ✅\n\n"
        "• تشغيل الملف على سيرفر خاص\n"
        "• تشغيل الملفات بكل سهولة وسرعة\n"
        "• تواصل مع الدعم لأي إستفسار\n\n"
        "**اختر من الأزرار أدناه:**"
    )

    bot.send_message(
        message.chat.id,
        main_text,
        reply_markup=markup,
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['start'])
def start_cmd(message):
    save_chat_id(message.chat.id)
    user_id = message.from_user.id

    if not bot_running:
        bot.send_message(message.chat.id, "⏸️ البوت متوقف حاليًا. يرجى الانتظار حتى يتم تشغيله.")
        return

    if message.from_user.username in banned_users:
        bot.send_message(message.chat.id, "⁉️ تم حظرك من استخدام البوت.")
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

# ======= المعالجات Callback Query ======= #
@bot.callback_query_handler(func=lambda call: call.data == 'back_to_main')
def back_to_main(call):
    show_main_menu(call.message)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == 'speed')
def check_speed(call):
    if not is_approved_user(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ تحتاج إلى موافقة الأدمن")
        return

    bot.answer_callback_query(call.id, "⏳ جاري قياس السرعة...")
    wait_msg = bot.send_message(call.message.chat.id, "⏳ **جاري قياس استجابة السيرفر...**")

    start_time = time.time()
    time.sleep(0.05)
    response_time = (time.time() - start_time) * 1000

    rating = "⚡ ممتازة!" if response_time < 100 else "🚀 جيدة"
    current_time = datetime.now().strftime('%I:%M %p')
    
    speed_text = (
        "⚡ **سرعة البوت الحالية:**\n\n"
        f"• سرعة الاستجابة: `{response_time:.2f} ms`\n"
        f"• التقييم: **{rating}**\n\n"
        f"_{current_time}_"
    )

    bot.edit_message_text(
        speed_text,
        call.message.chat.id,
        wait_msg.message_id,
        parse_mode='Markdown'
    )

@bot.callback_query_handler(func=lambda call: call.data == 'upload')
def upload_file_callback(call):
    if not is_approved_user(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ تحتاج إلى موافقة الأدمن")
        return

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ إلغاء", callback_data='back_to_main'))
    
    upload_text = (
        "📤 **رفع ملف**\n\n"
        "أرسل ملف البوت الآن (بصيغة `.py` فقط)\n"
        "الحد الأقصى للحجم: 2MB"
    )
    
    bot.send_message(
        call.message.chat.id,
        upload_text,
        reply_markup=markup,
        parse_mode='Markdown'
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == 'download_lib')
def download_library(call):
    if not is_approved_user(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ تحتاج إلى موافقة الأدمن")
        return

    bot.send_message(call.message.chat.id, "📚 أرسل اسم المكتبة التي تريد تثبيتها (مثال: `requests`):", parse_mode='Markdown')
    bot.register_next_step_handler(call.message, install_library_step)
    bot.answer_callback_query(call.id)

def install_library_step(message):
    library_name = message.text.strip()
    bot.send_message(message.chat.id, f"🔄 جاري تثبيت `{library_name}`...", parse_mode='Markdown')

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", library_name],
            capture_output=True,
            text=True,
            timeout=40
        )
        if result.returncode == 0:
            bot.send_message(message.chat.id, f"✅ تم تثبيت `{library_name}` بنجاح", parse_mode='Markdown')
        else:
            bot.send_message(message.chat.id, f"❌ فشل التثبيت:\n```\n{result.stderr[:300]}\n```", parse_mode='Markdown')
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ خطأ أثناء التثبيت: {e}")

@bot.callback_query_handler(func=lambda call: call.data == 'online_support')
def online_support(call):
    username_val = call.from_user.username or 'غير متوفر'
    user_info = f"👤 {call.from_user.first_name}\n🆔 `{call.from_user.id}`\n📌 @{username_val}"
    bot.send_message(ADMIN_ID, f"📞 **طلب دعم فوري:**\n\n{user_info}", parse_mode='Markdown')
    bot.answer_callback_query(call.id, "✅ تم إرسال طلبك للإدارة")

@bot.callback_query_handler(func=lambda call: call.data.startswith(('approve_', 'reject_')))
def handle_approval_action(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
        return

    action, user_id_str = call.data.split('_')
    target_id = int(user_id_str)

    if target_id in pending_requests:
        user_info = pending_requests.pop(target_id)
        if action == 'approve':
            approved_users.add(target_id)
            bot.send_message(target_id, "🎉 تمت الموافقة على طلبك! أرسل /start لبدء الاستخدام.")
            bot.edit_message_text(f"✅ تم قبول المستخدم: {user_info['first_name']} (`{target_id}`)", call.message.chat.id, call.message.message_id, parse_mode='Markdown')
        else:
            bot.send_message(target_id, "❌ تم رفض طلب اشتراكك.")
            bot.edit_message_text(f"❌ تم رفض المستخدم: {user_info['first_name']} (`{target_id}`)", call.message.chat.id, call.message.message_id, parse_mode='Markdown')
    else:
        bot.answer_callback_query(call.id, "❌ الطلب غير موجود أو تم معالجته سابقاً")

# ======= معالجة رفع الملفات ======= #
@bot.message_handler(content_types=['document'])
def handle_file_upload(message):
    if not is_approved_user(message.from_user.id):
        bot.reply_to(message, "❌ تحتاج إلى موافقة الأدمن لرفع الملفات.")
        return

    if message.document.file_size > MAX_FILE_SIZE:
        bot.reply_to(message, "⛔ حجم الملف يتجاوز الحد المسموح (2MB).")
        return

    file_name = message.document.file_name
    if not file_name.endswith('.py'):
        bot.reply_to(message, "❌ يُسمح فقط برفع ملفات بايثون (`.py`).", parse_mode='Markdown')
        return

    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)

        temp_path = os.path.join(tempfile.gettempdir(), file_name)
        with open(temp_path, 'wb') as f:
            f.write(downloaded)

        if protection_enabled and not is_admin(message.from_user.id):
            is_malicious, activity, _ = scan_file_for_malicious_code(temp_path, message.from_user.id)
            if is_malicious:
                bot.reply_to(message, f"⛔ تم رفض الملف للأسباب الأمنية التالية:\n`{activity}`", parse_mode='Markdown')
                os.remove(temp_path)
                return

        final_path = os.path.join(uploaded_files_dir, file_name)
        shutil.move(temp_path, final_path)

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(f"🛑 إيقاف {file_name}", callback_data=f'stop_{message.chat.id}_{file_name}'))

        uploader = message.from_user.username or 'بدون'
        file_msg = (
            "✅ **تم رفع الملف بنجاح**\n\n"
            f"📁 الملف: `{file_name}`\n"
            f"👤 المرفع: @{uploader}"
        )

        bot.reply_to(
            message,
            file_msg,
            reply_markup=markup,
            parse_mode='Markdown'
        )

        start_file(final_path, message.chat.id)

    except Exception as e:
        bot.reply_to(message, f"❌ حدث خطأ أثناء المعالجة: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('stop_'))
def handle_stop_script(call):
    try:
        parts = call.data.split('_')
        chat_id = int(parts[1])
        script_name = '_'.join(parts[2:])

        script_path = os.path.join(uploaded_files_dir, script_name)
        if stop_bot_process(script_path, chat_id):
            bot.answer_callback_query(call.id, "✅ تم إيقاف الملف")
            bot.edit_message_text(f"🛑 تم إيقاف التشغيل للملف: `{script_name}`", call.message.chat.id, call.message.message_id, parse_mode='Markdown')
        else:
            bot.answer_callback_query(call.id, "❌ فشل في الإيقاف")
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ خطأ: {e}")

# ======= أداء الإذاعة للبرودكاست ======= #
@bot.message_handler(commands=['rck'])
def broadcast_cmd(message):
    if not is_admin(message.from_user.id):
        return

    text = message.text.replace('/rck', '').strip()
    if not text:
        bot.reply_to(message, "❌ الاستخدام: `/rck الرسالة`", parse_mode='Markdown')
        return

    success, failed = 0, 0
    for uid in approved_users:
        try:
            bot.send_message(uid, text)
            success += 1
        except:
            failed += 1

    bot.reply_to(message, f"📊 **نتيجة الإذاعة:**\n✅ تم الإرسال: {success}\n❌ فشل: {failed}", parse_mode='Markdown')

# ======= تشغيل السيرفر الرئيسي ======= #
if __name__ == '__main__':
    print("🤖 البوت يعمل بنجاح...")
    print(f"👑 آيدي المطور: {ADMIN_ID}")
    print(f"📢 القناة الرسمية: {ADMIN_CHANNEL}")

    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            print(f"❌ خطأ في الاتصال، جاري إعادة التشغيل: {e}")
            time.sleep(3)
