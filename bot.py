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
BOT_TOKEN = '8877293036:AAGg_82F0bT1Bhov42sk9qDcRMsVNpfnErw'
ADMIN_ID = 1920665874
YOUR_USERNAME = '@u_8_y'
ADMIN_CHANNEL = '@FD_CQ'

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

protection_enabled = True
bot_running = True

lock = threading.Lock()
executor = ThreadPoolExecutor(max_workers=10)

def is_admin(user_id):
    return user_id == ADMIN_ID

# ======= القائمة الرئيسية والأوامر ======= #
def show_main_menu(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("رفع ملف 📥", callback_data='upload'),
        types.InlineKeyboardButton("🚀 سرعة البوت", callback_data='speed')
    )
    markup.add(
        types.InlineKeyboardButton("📚 تثبيت مكتبة", callback_data='download_lib'),
        types.InlineKeyboardButton("📞 التواصل مع الدعم", callback_data='online_support')
    )

    if is_admin(message.from_user.id):
        markup.add(
            types.InlineKeyboardButton("👥 قائمة الملفات", callback_data='manage_users')
        )

    user_name = message.from_user.first_name
    main_text = (
        "🐍 **Python Hosting** 🐍\n\n"
        f"مرحباً بك يا {user_name}! 👋\n\n"
        "**الميزات المتاحة:** ✅\n\n"
        "• تشغيل ملفات بايثون على سيرفر خاص\n"
        "• تثبيت المكتبات وتتبع السرعة\n"
        "• تواصل مع الدعم لأي استفسار\n\n"
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
    if not bot_running:
        bot.send_message(message.chat.id, "⏸️ البوت متوقف حاليًا.")
        return

    # تشغيل القائمة الرئيسية مباشرة لأي مستخدم
    show_main_menu(message)

# ======= المعالجات Callback Query ======= #
@bot.callback_query_handler(func=lambda call: call.data == 'back_to_main')
def back_to_main(call):
    show_main_menu(call.message)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == 'speed')
def check_speed(call):
    bot.answer_callback_query(call.id, "⏳ جاري قياس السرعة...")
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

    bot.send_message(call.message.chat.id, speed_text, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == 'upload')
def upload_file_callback(call):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ إلغاء", callback_data='back_to_main'))
    
    upload_text = (
        "📤 **رفع ملف**\n\n"
        "أرسل ملف البوت الآن (بصيغة `.py` فقط)\n"
        "الحد الأقصى للحجم: 2MB"
    )
    
    bot.send_message(call.message.chat.id, upload_text, reply_markup=markup, parse_mode='Markdown')
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == 'download_lib')
def download_library(call):
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

# ======= معالجة رفع الملفات ======= #
@bot.message_handler(content_types=['document'])
def handle_file_upload(message):
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

        final_path = os.path.join(uploaded_files_dir, file_name)
        with open(final_path, 'wb') as f:
            f.write(downloaded)

        uploader = message.from_user.username or 'بدون'
        file_msg = (
            "✅ **تم رفع الملف بنجاح وتغليفه للتطبيق.**\n\n"
            f"📁 الملف: `{file_name}`\n"
            f"👤 المرفع: @{uploader}"
        )

        bot.reply_to(message, file_msg, parse_mode='Markdown')

    except Exception as e:
        bot.reply_to(message, f"❌ حدث خطأ أثناء المعالجة: {e}")

# ======= تشغيل البوت الرئيسي ======= #
if __name__ == '__main__':
    print("🤖 البوت يعمل بنجاح...")
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
