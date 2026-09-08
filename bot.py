import os
import sys
import time
import subprocess
from threading import Thread
from flask import Flask
import telebot
from telebot import types

# ======= إعداد السيرفر الوهمي لإبقاء البوت شغال 24 ساعة ======= #
app = Flask('')

@app.route('/')
def home():
    return "Server is running perfectly!"

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

# ======= القائمة الرئيسية المطابقة للصورة ======= #
def get_main_menu_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    btn_files = types.InlineKeyboardButton("🔵 ملفاتي", callback_data='my_files')
    btn_upload = types.InlineKeyboardButton("🔴 رفع ملف", callback_data='upload_file')
    markup.row(btn_files, btn_upload)
    
    btn_account = types.InlineKeyboardButton("🟠 حسابي 📊", callback_data='my_account')
    btn_store = types.InlineKeyboardButton("📦 المتجر 🛒", callback_data='store')
    markup.row(btn_account, btn_store)
    
    btn_points = types.InlineKeyboardButton("💎 نقاطي 💰", callback_data='my_points')
    btn_guide = types.InlineKeyboardButton("📖 التعليمات", callback_data='instructions')
    markup.row(btn_points, btn_guide)
    
    btn_vip = types.InlineKeyboardButton("💎 الاشتراك المميز", callback_data='vip_sub')
    markup.row(btn_vip)
    
    btn_free_points = types.InlineKeyboardButton("👥 ربح نقاط مجاناً 🔗", callback_data='free_points')
    markup.row(btn_free_points)
    
    btn_daily_gift = types.InlineKeyboardButton("🎁 الهدية اليومية", callback_data='daily_gift')
    markup.row(btn_daily_gift)
    
    btn_inquiry = types.InlineKeyboardButton("💬 استفسار", callback_data='inquiry')
    markup.row(btn_inquiry)
    
    btn_dev = types.InlineKeyboardButton("👨‍💻 تواصل مع المطور", url=f"https://t.me/{DEV_USERNAME}")
    btn_channel = types.InlineKeyboardButton("📢 قناة التحديثات", url=f"https://t.me/{CHANNEL_USERNAME}")
    markup.row(btn_dev, btn_channel)
    
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

# ======= معالجة ضغطات الأزرار ======= #
@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    
    if call.data == 'upload_file':
        if is_admin(user_id):
            pts_info = "👑 **الوضع: مالك البوت (الرفع مجاني بدون نقاط)**"
        else:
            pts_info = f"⚠️ **كل ساعة تشغيل = 10 نقطة.**\n💎 **نقاطك الحالية:** {user_points.get(user_id, 55)}"

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
        msg = "📂 **الملفات المرفوعة والمشغلة:**\n\n" + "\n".join([f"• `{f}`" for f in files]) if files else "📁 لا توجد ملفات مرفوعة حالياً."
        bot.send_message(chat_id, msg, parse_mode='Markdown')
        bot.answer_callback_query(call.id)

    elif call.data == 'my_points':
        if is_admin(user_id):
            bot.send_message(chat_id, "👑 أنت مالك البوت، استخدامك مجاني وغير محدود!")
        else:
            pts = user_points.get(user_id, 55)
            bot.send_message(chat_id, f"💎 رصيدك الحالي هو: **{pts} نقطة**", parse_mode='Markdown')
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

    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        file_path = os.path.join(uploaded_dir, file_name)

        with open(file_path, 'wb') as f:
            f.write(downloaded)

        if is_admin(user_id):
            msg_reply = f"👑 **مرحباً بالمالك! تم استلام وتفعيل الملف `{file_name}` بنجاح!**\n🚀 **جاري تشغيل البوت في الخلفية (مجاناً)...**"
        else:
            user_points[user_id] -= 10
            msg_reply = f"✅ **تم استلام الملف `{file_name}` بنجاح!**\n🚀 **جاري تشغيله في الخلفية...**\n\n💎 **باقي نقاطك:** {user_points[user_id]} نقطة."

        bot.reply_to(message, msg_reply, parse_mode='Markdown')
        
        # تشغيل الملف
        subprocess.Popen([sys.executable, file_path])

    except Exception as e:
        bot.reply_to(message, f"❌ حدث خطأ أثناء رفع وتفعيل الملف: {e}")

# ======= التشغيل الرئيسي ======= #
if __name__ == '__main__':
    keep_alive()
    print("🤖 البوت يعمل بنجاح ومستقر...")
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            time.sleep(3)
