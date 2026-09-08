import sys
import os
import time
import subprocess
import telebot
from telebot import types

# ======= البيانات الأساسية ======= #
BOT_TOKEN = '8177794176:AAF390geeHv0-87Bubl_bqKiDoH7mPjDSdE'
ADMIN_ID = 1920665874  # آيدي المالك
DEV_USERNAME = 'u_8_y'
CHANNEL_USERNAME = 'FD_CQ'

bot = telebot.TeleBot(BOT_TOKEN)

# مجلد حفظ الملفات المرفوعة
uploaded_dir = "uploaded_files"
os.makedirs(uploaded_dir, exist_ok=True)

# قاعدة بيانات النقاط والحالات
user_points = {}
user_states = {}

def is_admin(user_id):
    return user_id == ADMIN_ID

# ======= القائمة الرئيسية ======= #
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
    
    user_states[user_id] = None
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
    
    bot.send_message(
        message.chat.id, 
        welcome_text, 
        reply_markup=get_main_menu_markup(), 
        parse_mode='Markdown'
    )

# ======= معالجة الأزرار (Callback Queries) ======= #
@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    
    if call.data == 'upload_file':
        user_states[user_id] = 'waiting_for_file'
        
        if is_admin(user_id):
            pts_info = "👑 **الوضع: مالك البوت (الرفع مجاني بدون نقاط)**"
        else:
            pts_info = f"⚠️ **كل ساعة تشغيل = 10 نقطة.**\n💎 **نقاطك الحالية:** {user_points.get(user_id, 55)}"

        upload_text = (
            "📬 **أرسل ملف بايثون (.py) الآن.**\n\n"
            f"{pts_info}"
        )
        
        back_markup = types.InlineKeyboardMarkup()
        back_markup.add(types.InlineKeyboardButton("⬅️ رجوع", callback_data='back_to_main'))
        
        bot.send_message(chat_id, upload_text, reply_markup=back_markup, parse_mode='Markdown')
        bot.answer_callback_query(call.id)

    elif call.data == 'back_to_main':
        user_states[user_id] = None
        send_welcome(call.message)
        bot.answer_callback_query(call.id)

    elif call.data == 'my_files':
        files = os.listdir(uploaded_dir)
        if not files:
            bot.send_message(chat_id, "📁 لا توجد ملفات مرفوعة حالياً.")
        else:
            msg = "📂 **الملفات المرفوعة والمشغلة:**\n\n" + "\n".join([f"• `{f}`" for f in files])
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

    # التحقق من النقاط فقط إذا لم يكن مالك البوت
    if not is_admin(user_id):
        pts = user_points.get(user_id, 55)
        if pts < 10:
            bot.reply_to(message, "❌ ليس لديك نقاط كافية لتشغيل الملف (تحتاج 10 نقاط على الأقل).")
            return

    try:
        # تحميل وتخزين الملف
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        file_path = os.path.join(uploaded_dir, file_name)

        with open(file_path, 'wb') as f:
            f.write(downloaded)

        user_states[user_id] = None

        if is_admin(user_id):
            msg_reply = (
                f"👑 **مرحباً بالمالك! تم استلام وتفعيل الملف `{file_name}` بنجاح!**\n"
                "🚀 **جاري تشغيل البوت في الخلفية (مجاناً بدون خصم)...**"
            )
        else:
            user_points[user_id] -= 10
            msg_reply = (
                f"✅ **تم استلام الملف `{file_name}` بنجاح!**\n"
                "🚀 **جاري تشغيل البوت المرفوع في الخلفية الآن...**\n\n"
                f"💎 **باقي نقاطك:** {user_points[user_id]} نقطة."
            )

        bot.reply_to(message, msg_reply, parse_mode='Markdown')
        
        # تشغيل ملف بايثون كعملية جديدة مستمرة
        subprocess.Popen([sys.executable, file_path])

    except Exception as e:
        bot.reply_to(message, f"❌ حدث خطأ أثناء رفع وتفعيل الملف: {e}")

# ======= تشغيل البوت المستمر ======= #
if __name__ == '__main__':
    print("🤖 البوت يعمل بنجاح...")
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            time.sleep(3)
