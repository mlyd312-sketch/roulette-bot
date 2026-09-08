import os
import sys
import time
import subprocess
import signal
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
running_processes = {}  # قاموس لتتبع عمليات الملفات المشغلة PID

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
        types.InlineKeyboardButton("🛑 إيقاف ملف", callback_data='stop_file'),
        types.InlineKeyboardButton("📦 المتجر 🛒", callback_data='store')
    )
    markup.row(
        types.InlineKeyboardButton("🟠 حسابي 📊", callback_data='my_account'),
        types.InlineKeyboardButton("💎 نقاطي 💰", callback_data='my_points')
    )
    markup.row(types.InlineKeyboardButton("📖 التعليمات", callback_data='instructions'))
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

    elif call.data == 'stop_file':
        files = [f for f in os.listdir(uploaded_dir) if f.endswith('.py')]
        if not files:
            bot.send_message(chat_id, "📁 لا توجد ملفات مشغلة حالياً لإيقافها.")
            bot.answer_callback_query(call.id)
            return

        markup = types.InlineKeyboardMarkup()
        for f in files:
            markup.add(types.InlineKeyboardButton(f"🛑 إيقاف {f}", callback_data=f"kill_{f}"))
        markup.add(types.InlineKeyboardButton("⬅️ رجوع", callback_data='back_to_main'))

        bot.send_message(chat_id, "🛑 **اختر الملف الذي تريد إيقافه وتشغيله:**", reply_markup=markup, parse_mode='Markdown')
        bot.answer_callback_query(call.id)

    elif call.data.startswith('kill_'):
        file_to_kill = call.data.replace('kill_', '')
        file_path = os.path.join(uploaded_dir, file_to_kill)

        # إنهاء العملية إذا كانت مسجلة
        if file_to_kill in running_processes:
            try:
                process = running_processes[file_to_kill]
                process.terminate()
                del running_processes[file_to_kill]
            except Exception:
                pass

        # حذف الملف من السيرفر
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

        bot.send_message(chat_id, f"✅ **تم إيقاف وحذف الملف `{file_to_kill}` بنجاح!**", parse_mode='Markdown')
        bot.answer_callback_query(call.id)

    elif call.data == 'my_points':
        pts_text = "👑 أنت مالك البوت، استخدامك مجاني وغير محدود!" if is_admin(user_id) else f"💎 رصيدك الحالي هو: **{user_points.get(user_id, 55)} نقطة**"
        bot.send_message(chat_id, pts_text, parse_mode='Markdown')
        bot.answer_callback_query(call.id)

    elif call.data == 'daily_gift':
        user_points[user_id] = user_points.get(user_id, 55) + 10
        bot.answer_callback_query(call.id, "🎁 حصلت على 10 نقاط هدية يومية!", show_alert=True)

# ======= استقبال وتشغيل الملف المرفوع ======= #
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

        # 2. تثبيت المكتبات الأساسية تلقائياً
        subprocess.run([sys.executable, "-m", "pip", "install", "pyTelegramBotAPI", "requests", "aiohttp"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # 3. إيقاف أي نسخة قديمة بنفس الاسم إن وجدت
        if file_name in running_processes:
            try:
                running_processes[file_name].terminate()
            except Exception:
                pass

        # 4. تشغيل الملف الجديد وتسجيل عمليته
        proc = subprocess.Popen([sys.executable, file_path], start_new_session=True)
        running_processes[file_name] = proc

        if not is_admin(user_id):
            user_points[user_id] -= 10

        bot.edit_message_text(
            f"✅ **تم تشغيل الملف `{file_name}` بنجاح!**\n\n"
            "💡 يمكنك إيقاف هذا الملف في أي وقت عبر زر **🛑 إيقاف ملف** من القائمة الرئيسية.",
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
