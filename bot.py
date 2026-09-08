import os
import sys
import time
import subprocess
from threading import Thread
from flask import Flask
import telebot
from telebot import types

# ======= إعداد السيرفر الوهمي لإبقاء الاستضافة تعمل 24 ساعة ======= #
app = Flask('')

@app.route('/')
def home():
    return "Hosting Server is Active!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# ======= البيانات الأساسية ======= #
BOT_TOKEN = '8877293036:AAGg_82F0bT1Bhov42sk9qDcRMsVNpfnErw'
ADMIN_ID = 1920665874  # آيدي حسابك
DEV_USERNAME = 'u_8_y'
CHANNEL_USERNAME = 'FD_CQ'

bot = telebot.TeleBot(BOT_TOKEN)

# مجلد حفظ الملفات المرفوعة
uploaded_dir = "uploaded_files"
os.makedirs(uploaded_dir, exist_ok=True)

user_points = {}

def is_admin(user_id):
    return user_id == ADMIN_ID

# ======= القائمة الرئيسية ======= #
def get_main_menu_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    markup.row(
        types.InlineKeyboardButton("🔵 ملفاتي", callback_data='my_files'),
        types.InlineKeyboardButton("🔴 رفع ملف", callback_data='upload_file')
    )
    markup.row(
        types.InlineKeyboardButton("🟠 حسابي 📊", callback_data='my_account'),
        types.InlineKeyboardButton("📦 المتجر 🛒", callback_data='store')
    )
    markup.row(
        types.InlineKeyboardButton("💎 نقاطي 💰", callback_data='my_points'),
        types.InlineKeyboardButton("📖 التعليمات", callback_data='instructions')
    )
    markup.row(types.InlineKeyboardButton("💎 الاشتراك المميز", callback_data='vip_sub'))
    markup.row(types.InlineKeyboardButton("👥 ربح نقاط مجاناً 🔗", callback_data='free_points'))
    markup.row(types.InlineKeyboardButton("🎁 الهدية اليومية", callback_data='daily_gift'))
    markup.row(types.InlineKeyboardButton("💬 استفسار", callback_data='inquiry'))
    markup.row(
        types.InlineKeyboardButton("👨‍💻 تواصل مع المطور", url=f"https://t.me/{DEV_USERNAME}"),
        types.InlineKeyboardButton("📢 قناة التحديثات", url=f"https://t.me/{CHANNEL_USERNAME}")
    )
    return markup

# ======= أمر /start ======= #
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    
    if user_id not in user_points:
        user_points[user_id] = 55

    points = "مفتوح (مالك البوت)" if is_admin(user_id) else user_points[user_id]
    cost_text = "مجاني (مالك)" if is_admin(user_id) else "10 نقطة"
    
    welcome_text = (
        f"👋 **أهلاً بك يا {first_name}!**\n\n"
        "🤖 هذا بوت استضافة بوتات تيليجرام.\n"
        "قم برفع ملف `.py` الخاص بك وسيقوم البوت بتشغيله.\n\n"
        f"💎 **نقاطك الحالية:** {points}\n"
        f"💰 **تكلفة الساعة:** {cost_text}\n\n"
        "👇 **اختر من القائمة أدناه:**"
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=get_main_menu_markup(), parse_mode='Markdown')

# ======= معالجة الأزرار ======= #
@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    
    if call.data == 'upload_file':
        pts_info = "👑 **الوضع: مالك البوت (الرفع مجاني بدون نقاط)**" if is_admin(user_id) else f"⚠️ **كل ساعة تشغيل = 10 نقطة.**\n💎 **نقاطك الحالية:** {user_points.get(user_id, 55)}"
        upload_text = f"📬 **أرسل ملف بايثون (.py) الآن.**\n\n{pts_info}"
        
        back_markup = types.InlineKeyboardMarkup()
        back_markup.add(types.InlineKeyboardButton("⬅️ رجوع", callback_data='back_to_main'))
        bot.send_message(chat_id, upload_text, reply_markup=back_markup, parse_mode='Markdown')
        bot.answer_callback_query(call.id)

    elif call.data == 'back_to_main':
        send_welcome(call.message)
        bot.answer_callback_query(call.id)

    elif call.data == 'my_files':
        files = os.listdir(uploaded_dir)
        py_files = [f for f in files if f.endswith('.py')]
        msg = "📂 **الملفات المرفوعة والمشغلة:**\n\n" + "\n".join([f"• `{f}`" for f in py_files]) if py_files else "📁 لا توجد ملفات مرفوعة حالياً."
        bot.send_message(chat_id, msg, parse_mode='Markdown')
        bot.answer_callback_query(call.id)

# ======= استقبال وتشغيل الملف المرفوع بشكل مستقل ======= #
@bot.message_handler(content_types=['document'])
def handle_docs(message):
    user_id = message.from_user.id
    file_name = message.document.file_name
    
    if not file_name.endswith('.py'):
        bot.reply_to(message, "❌ يُسمح فقط برفع ملفات بايثون بصيغة `.py`.")
        return

    if not is_admin(user_id):
        pts = user_points.get(user_id, 55)
        if pts < 10:
            bot.reply_to(message, "❌ ليس لديك نقاط كافية لتشغيل الملف (تحتاج 10 نقاط على الأقل).")
            return

    status_msg = bot.reply_to(message, "⏳ **جاري حفظ الملف وتثبيت المكاتب المطلوبة...**", parse_mode='Markdown')

    try:
        # 1. تنزيل الملف وحفظه
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        file_path = os.path.join(uploaded_dir, file_name)

        with open(file_path, 'wb') as f:
            f.write(downloaded)

        # 2. تثبيت المكتبات الأساسية للبوت المرفوع تلقائياً
        subprocess.run([sys.executable, "-m", "pip", "install", "pyTelegramBotAPI", "requests", "aiohttp"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # 3. تشغيل الملف المرفوع في عملية مستقلة تماماً مع تسجيل الخرج
        log_path = os.path.join(uploaded_dir, f"{file_name}.log")
        log_file = open(log_path, "a")
        
        # start_new_session يمنع توقف البوت المرفوع عند توقف البوت الرئيسي
        subprocess.Popen([sys.executable, file_path], stdout=log_file, stderr=log_file, start_new_session=True)

        if not is_admin(user_id):
            user_points[user_id] -= 10

        bot.edit_message_text(
            f"✅ **تم تشغيل الملف `{file_name}` بنجاح في الخلفية!**\n\n"
            "⚠️ **ملاحظة هامة جداً:**\n"
            "• تأكد أن البوت المرفوع غير شغال في مكان آخر (على جهازك مثلاً) لتجنب التعارض.\n"
            "• تأكد أن التوكن المكتوب داخل الملف المرفوع صحيح وليس محظوراً.",
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            parse_mode='Markdown'
        )

    except Exception as e:
        bot.edit_message_text(f"❌ حدث خطأ أثناء تشغيل الملف:\n`{e}`", chat_id=message.chat.id, message_id=status_msg.message_id, parse_mode='Markdown')

# ======= التشغيل الرئيسي ======= #
if __name__ == '__main__':
    keep_alive()
    print("🤖 بوت الاستضافة يعمل بنجاح ومستعد لاستقبال الملفات...")
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            time.sleep(3)
