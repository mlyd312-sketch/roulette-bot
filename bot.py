import sys
import os
import re
import time
import shutil
import tempfile
import threading
import subprocess
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import telebot
from telebot import types

# ======= إعدادات البوت الأساسية ======= #
BOT_TOKEN = '8177794176:AAF390geeHv0-87Bubl_bqKiDoH7mPjDSdE'
ADMIN_ID = 1920665874
YOUR_USERNAME = '@u_8_y'
ADMIN_CHANNEL = '@FD_CQ'

bot = telebot.TeleBot(BOT_TOKEN)

# إعدادات المجلدات والحدود
uploaded_files_dir = "uploaded_files"
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

if not os.path.exists(uploaded_files_dir):
    os.makedirs(uploaded_files_dir)

# إدارة التزامن والملفات
active_processes = {}
lock = threading.Lock()
executor = ThreadPoolExecutor(max_workers=10)

def is_admin(user_id):
    return user_id == ADMIN_ID

# ======= القائمة الرئيسية ======= #
def show_main_menu(chat_id, user_name):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📤 رفع ملف python", callback_data='upload'),
        types.InlineKeyboardButton("⚡ سرعة البوت", callback_data='speed')
    )
    markup.add(
        types.InlineKeyboardButton("📚 تثبيت مكتبة pip", callback_data='download_lib'),
        types.InlineKeyboardButton("📂 الملفات المرفوعة", callback_data='list_files')
    )
    markup.add(
        types.InlineKeyboardButton("📞 الدعم الفني", callback_data='online_support')
    )

    main_text = (
        "🐍 **سيرفر استضافة بوتات بايثون** 🐍\n\n"
        f"مرحباً بك يا **{user_name}** 👋\n\n"
        "يمكنك رفع وتشغيل ملفاتك بشكل مستمر على السيرفر.\n"
        "اختر الخيار المطلوب من الأزرار أدناه:"
    )

    bot.send_message(chat_id, main_text, reply_markup=markup, parse_mode='Markdown')

@bot.message_handler(commands=['start'])
def start_cmd(message):
    show_main_menu(message.chat.id, message.from_user.first_name)

# ======= الاستجابة للكبسات (Callback Queries) ======= #
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id

    if call.data == 'back_to_main':
        show_main_menu(chat_id, call.from_user.first_name)
        bot.answer_callback_query(call.id)

    elif call.data == 'speed':
        start_time = time.time()
        msg = bot.send_message(chat_id, "⏳ جاري فحص استجابة السيرفر...")
        latency = (time.time() - start_time) * 1000
        bot.edit_message_text(
            f"⚡ **سرعة الاستجابة:** `{latency:.2f} ms`\n🟢 السيرفر يعمل بكفاءة عاليه.",
            chat_id,
            msg.message_id,
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id)

    elif call.data == 'upload':
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 إلغاء", callback_data='back_to_main'))
        bot.send_message(chat_id, "📤 **قم بإرسال ملف البوت الخاص بك بصيغة `.py` الآن:**", reply_markup=markup, parse_mode='Markdown')
        bot.answer_callback_query(call.id)

    elif call.data == 'download_lib':
        bot.send_message(chat_id, "📚 **أرسل اسم المكتبة المراد تثبيتها (مثال: `requests` أو `telebot`):**", parse_mode='Markdown')
        bot.register_next_step_handler(call.message, install_library)
        bot.answer_callback_query(call.id)

    elif call.data == 'list_files':
        files = os.listdir(uploaded_files_dir)
        if not files:
            bot.send_message(chat_id, "📂 لا يوجد ملفات مرفوعة حالياً.")
        else:
            msg_files = "📂 **الملفات المرفوعة:**\n\n" + "\n".join([f"• `{f}`" for f in files])
            bot.send_message(chat_id, msg_files, parse_mode='Markdown')
        bot.answer_callback_query(call.id)

    elif call.data == 'online_support':
        bot.send_message(chat_id, f"📞 للتواصل مع الدعم المباشر: {YOUR_USERNAME}")
        bot.answer_callback_query(call.id)

# ======= تثبيت المكتبات ======= #
def install_library(message):
    lib_name = message.text.strip()
    bot.send_message(message.chat.id, f"🔄 جاري تثبيت المكتبة `{lib_name}`...", parse_mode='Markdown')
    
    def run_pip():
        try:
            res = subprocess.run([sys.executable, "-m", "pip", "install", lib_name], capture_output=True, text=True, timeout=60)
            if res.returncode == 0:
                bot.send_message(message.chat.id, f"✅ تم تثبيت المكتبة `{lib_name}` بنجاح!", parse_mode='Markdown')
            else:
                bot.send_message(message.chat.id, f"❌ فشل التثبيت:\n```\n{res.stderr[:300]}\n```", parse_mode='Markdown')
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ خطأ: {e}")

    executor.submit(run_pip)

# ======= استقبال وتشغيل الملفات ======= #
@bot.message_handler(content_types=['document'])
def handle_docs(message):
    file_name = message.document.file_name
    if not file_name.endswith('.py'):
        bot.reply_to(message, "❌ يرجى إرسال ملفات بصيغة `.py` فقط.")
        return

    if message.document.file_size > MAX_FILE_SIZE:
        bot.reply_to(message, "⚠️ حجم الملف كبير جداً (الأقصى 5 ميجابايت).")
        return

    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        file_path = os.path.join(uploaded_files_dir, file_name)

        with open(file_path, 'wb') as f:
            f.write(downloaded)

        bot.reply_to(message, f"✅ تم حفظ وتجهيز الملف: `{file_name}`\n🚀 جاري تشغيل الملف في الخلفية...", parse_mode='Markdown')

        # تشغيل السكربت كعملية منفصلة
        def run_script():
            proc = subprocess.Popen([sys.executable, file_path])
            with lock:
                active_processes[file_name] = proc

        executor.submit(run_script)

    except Exception as e:
        bot.reply_to(message, f"❌ حدث خطأ أثناء معالجة الملف: {e}")

# ======= تشغيل البوت مع إعادة الاتصال التلقائي ======= #
if __name__ == '__main__':
    print("🤖 البوت شغال وجاهز لاستقبال الأوامر...")
    while True:
        try:
            bot.polling(none_stop=True, interval=1, timeout=30)
        except Exception as e:
            print(f"⚠️ انقطع الاتصال، جاري إعادة المحاولة: {e}")
            time.sleep(3)
