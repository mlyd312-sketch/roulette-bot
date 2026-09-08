آيديport os
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
MAIN_ADMIN_ID = 1920665874  # آيدي المطور الأساسي
DEV_USERNAME = 'u_8_y'
CHANNEL_USERNAME = 'FD_CQ'

bot = telebot.TeleBot(BOT_TOKEN)

# مجلد حفظ الملفات المرفوعة
uploaded_dir = "uploaded_files"
os.makedirs(uploaded_dir, exist_ok=True)

# قواعد البيانات المؤقتة في الذاكرة
user_points = {}          # {user_id: points}
admins = [MAIN_ADMIN_ID]   # قائمة المشرفين
users_list = set()        # قائمة جميع المستخدمين
running_processes = {}    # {filename: process}
user_states = {}         # لحفظ حالة المدخلات (كتابة آيدي، نقاط...)

def is_admin(user_id):
    return user_id in admins or user_id == MAIN_ADMIN_ID

# ======= القائمة الرئيسية ======= #
def get_main_menu_markup(user_id):
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
    
    # إظهار زر لوحة التحكم للمشرفين فقط
    if is_admin(user_id):
        markup.row(types.InlineKeyboardButton("⚙️ لوحة التحكم (الأدمن)", callback_data='admin_panel'))
        
    markup.row(
        types.InlineKeyboardButton("👨‍💻 تواصل مع المطور", url=f"https://t.me/{DEV_USERNAME}"),
        types.InlineKeyboardButton("📢 قناة التحديثات", url=f"https://t.me/{CHANNEL_USERNAME}")
    )
    return markup

# ======= لوحة تحكم الأدمن ======= #
def get_admin_panel_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton("➕ إضافة نقاط", callback_data='adm_add_pts'),
        types.InlineKeyboardButton("➖ خصم نقاط", callback_data='adm_sub_pts')
    )
    markup.row(
        types.InlineKeyboardButton("👤 رفع مشرف", callback_data='adm_add_admin'),
        types.InlineKeyboardButton("🗑 تنزيل مشرف", callback_data='adm_rem_admin')
    )
    markup.row(
        types.InlineKeyboardButton("📊 الإحصائيات", callback_data='adm_stats'),
        types.InlineKeyboardButton("📢 إذاعة جماعية", callback_data='adm_broadcast')
    )
    markup.row(types.InlineKeyboardButton("⬅️ القائمة الرئيسية", callback_data='back_to_main'))
    return markup

# ======= أمر /start مع دعم نظام التجميع الإحالة ======= #
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    users_list.add(user_id)
    
    # معالجة نظام دعوة الأصدقاء (تجميع النقاط)
    args = message.text.split()
    if len(args) > 1 and user_id not in user_points:
        referrer_id = args[1]
        if referrer_id.isdigit():
            referrer_id = int(referrer_id)
            if referrer_id != user_id and referrer_id in users_list:
                user_points[referrer_id] = user_points.get(referrer_id, 55) + 15
                try:
                    bot.send_message(referrer_id, f"🎉 **قام المستخدم {first_name} بالدخول عبر رابطك!**\n💎 **حصلت على 15 نقطة مجانية.**", parse_mode='Markdown')
                except Exception:
                    pass

    if user_id not in user_points:
        user_points[user_id] = 55

    points = "مفتوح (مالك البوت)" if is_admin(user_id) else user_points[user_id]
    cost_text = "مجاني (مالك/أدمن)" if is_admin(user_id) else "10 نقاط"
    
    welcome_text = (
        f"👋 **أهلاً بك يا {first_name}!**\n\n"
        "🤖 هذا بوت استضافة بوتات تيليجرام.\n"
        "قم برفع ملف `.py` الخاص بك وسيقوم البوت بتشغيله.\n\n"
        f"💎 **نقاطك الحالية:** {points}\n"
        f"💰 **تكلفة الساعة:** {cost_text}\n\n"
        "👇 **اختر من القائمة أدناه:**"
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=get_main_menu_markup(user_id), parse_mode='Markdown')

# ======= أمر /admin السريع ======= #
@bot.message_handler(commands=['admin'])
def admin_command(message):
    if is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⚙️ **أهلاً بك في لوحة تحكم الأدمن:**", reply_markup=get_admin_panel_markup(), parse_mode='Markdown')
    else:
        bot.reply_to(message, "❌ هذا الأمر مخصص للمشرفين فقط.")

# ======= معالجة الأزرار Inline ======= #
@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    
    if call.data == 'back_to_main':
        user_states.pop(user_id, None)
        send_welcome(call.message)
        bot.answer_callback_query(call.id)

    elif call.data == 'upload_file':
        pts_info = "👑 **الوضع: أدمن (الرفع مجاني بدون نقاط)**" if is_admin(user_id) else f"⚠️ **كل ساعة تشغيل = 10 نقطة.**\n💎 **نقاطك الحالية:** {user_points.get(user_id, 55)}"
        upload_text = f"📬 **أرسل ملف بايثون (.py) الآن.**\n\n{pts_info}"
        
        back_markup = types.InlineKeyboardMarkup()
        back_markup.add(types.InlineKeyboardButton("⬅️ رجوع", callback_data='back_to_main'))
        bot.send_message(chat_id, upload_text, reply_markup=back_markup, parse_mode='Markdown')
        bot.answer_callback_query(call.id)

    elif call.data == 'free_points':
        bot_info = bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
        msg = (
            "🔗 **نظام تجميع النقاط المجاني:**\n\n"
            "قم بنسخ رابط الدعوة الخاص بك وشاركه مع أصدقائك أو في المجموعات.\n"
            "لكل شخص يدخل البوت عبر رابطك ستكسب **15 نقطة مجاناً!**\n\n"
            f"📍 **رابطك الخاص:**\n`{ref_link}`"
        )
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

        bot.send_message(chat_id, "🛑 **اختر الملف الذي تريد إيقافه:**", reply_markup=markup, parse_mode='Markdown')
        bot.answer_callback_query(call.id)

    elif call.data.startswith('kill_'):
        file_to_kill = call.data.replace('kill_', '')
        file_path = os.path.join(uploaded_dir, file_to_kill)

        if file_to_kill in running_processes:
            try:
                running_processes[file_to_kill].terminate()
                del running_processes[file_to_kill]
            except Exception:
                pass

        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

        bot.send_message(chat_id, f"✅ **تم إيقاف وحذف الملف `{file_to_kill}` بنجاح!**", parse_mode='Markdown')
        bot.answer_callback_query(call.id)

    # ===== أحداث لوحة تحكم الأدمن =====
    elif call.data == 'admin_panel' and is_admin(user_id):
        bot.send_message(chat_id, "⚙️ **لوحة التحكم الخاص بالمشرفين:**", reply_markup=get_admin_panel_markup(), parse_mode='Markdown')
        bot.answer_callback_query(call.id)

    elif call.data == 'adm_stats' and is_admin(user_id):
        active_files = len([f for f in os.listdir(uploaded_dir) if f.endswith('.py')])
        stats = (
            "📊 **إحصائيات البوت الحالية:**\n\n"
            f"👤 عدد المستخدمين الكلي: `{len(users_list)}`\n"
            f"👑 عدد المشرفين: `{len(admins)}`\n"
            f"🚀 عدد الملفات المشغلة: `{active_files}`"
        )
        bot.send_message(chat_id, stats, parse_mode='Markdown')
        bot.answer_callback_query(call.id)

    elif call.data == 'adm_add_pts' and is_admin(user_id):
        user_states[user_id] = 'awaiting_add_pts'
        bot.send_message(chat_id, "✏️ **أرسل آيدي الشخص وعدد النقاط بالشكل التالي:**\n`ID POINTS`\n\nمثال:\n`1920665874 100`", parse_mode='Markdown')
        bot.answer_callback_query(call.id)

    elif call.data == 'adm_sub_pts' and is_admin(user_id):
        user_states[user_id] = 'awaiting_sub_pts'
        bot.send_message(chat_id, "✏️ **أرسل آيدي الشخص وعدد النقاط المراد خصمها:**\n`ID POINTS`\n\nمثال:\n`1920665874 50`", parse_mode='Markdown')
        bot.answer_callback_query(call.id)

    elif call.data == 'adm_add_admin' and is_admin(user_id):
        user_states[user_id] = 'awaiting_add_admin'
        bot.send_message(chat_id, "✏️ **أرسل آيدي الشخص الذي تريد رفعه مشرفاً:**", parse_mode='Markdown')
        bot.answer_callback_query(call.id)

    elif call.data == 'adm_rem_admin' and is_admin(user_id):
        user_states[user_id] = 'awaiting_rem_admin'
        bot.send_message(chat_id, "✏️ **أرسل آيدي المشرف الذي تريد تنزيله:**", parse_mode='Markdown')
        bot.answer_callback_query(call.id)

    elif call.data == 'adm_broadcast' and is_admin(user_id):
        user_states[user_id] = 'awaiting_broadcast'
        bot.send_message(chat_id, "📢 **أرسل نص الرسالة التي تريد إرسالها لجميع مستخدمي البوت:**", parse_mode='Markdown')
        bot.answer_callback_query(call.id)

    elif call.data == 'daily_gift':
        user_points[user_id] = user_points.get(user_id, 55) + 10
        bot.answer_callback_query(call.id, "🎁 حصلت على 10 نقاط هدية يومية!", show_alert=True)

# ======= استقبال النصوص والإدخالات من الأدمن ======= #
@bot.message_handler(func=lambda msg: msg.from_user.id in user_states)
def handle_admin_inputs(message):
    user_id = message.from_user.id
    state = user_states.get(user_id)
    text = message.text.strip()

    if state == 'awaiting_add_pts':
        try:
            target_id, pts = map(int, text.split())
            user_points[target_id] = user_points.get(target_id, 55) + pts
            bot.reply_to(message, f"✅ **تمت إضافة {pts} نقطة إلى المستخدم `{target_id}` بنجاح!**", parse_mode='Markdown')
            try:
                bot.send_message(target_id, f"🎁 **تمت إضافة {pts} نقطة إلى حسابك من قبل الأدمن!**")
            except Exception:
                pass
        except Exception:
            bot.reply_to(message, "❌ **صيغة خاطئة.** يرجى كتابة الآيدي ثم مسافة ثم عدد النقاط.")

    elif state == 'awaiting_sub_pts':
        try:
            target_id, pts = map(int, text.split())
            user_points[target_id] = max(0, user_points.get(target_id, 55) - pts)
            bot.reply_to(message, f"✅ **تم خصم {pts} نقطة من المستخدم `{target_id}` بنجاح!**", parse_mode='Markdown')
        except Exception:
            bot.reply_to(message, "❌ **صيغة خاطئة.** يرجى كتابة الآيدي ثم مسافة ثم عدد النقاط.")

    elif state == 'awaiting_add_admin':
        if text.isdigit():
            new_admin = int(text)
            if new_admin not in admins:
                admins.append(new_admin)
                bot.reply_to(message, f"✅ **تم رفع المستخدم `{new_admin}` مشرفاً بنجاح!**", parse_mode='Markdown')
            else:
                bot.reply_to(message, "⚠️ هذا المستخدم مشرف بالفعل.")
        else:
            bot.reply_to(message, "❌ يرجى إرسال آيدي رقمي صحيح.")

    elif state == 'awaiting_rem_admin':
        if text.isdigit():
            rem_admin = int(text)
            if rem_admin == MAIN_ADMIN_ID:
                bot.reply_to(message, "❌ لا يمكنك تنزيل المطور الأساسي للبوت.")
            elif rem_admin in admins:
                admins.remove(rem_admin)
                bot.reply_to(message, f"✅ **تم تنزيل المشرف `{rem_admin}` بنجاح!**", parse_mode='Markdown')
            else:
                bot.reply_to(message, "⚠️ هذا المستخدم ليس مشرفاً.")
        else:
            bot.reply_to(message, "❌ يرجى إرسال آيدي رقمي صحيح.")

    elif state == 'awaiting_broadcast':
        sent_count = 0
        for uid in list(users_list):
            try:
                bot.send_message(uid, f"📢 **إشعار عام:**\n\n{text}", parse_mode='Markdown')
                sent_count += 1
            except Exception:
                pass
        bot.reply_to(message, f"✅ **تمت الإذاعة بنجاح إلى `{sent_count}` مستخدم!**", parse_mode='Markdown')

    user_states.pop(user_id, None)

# ======= استقبال وتشغيل الملفات المرفوعة ======= #
@bot.message_handler(content_types=['document'])
def handle_docs(message):
    user_id = message.from_user.id
    file_name = message.document.file_name
    users_list.add(user_id)
    
    if not file_name.endswith('.py'):
        bot.reply_to(message, "❌ يُسمح فقط برفع ملفات بايثون بصيغة `.py`.")
        return

    if not is_admin(user_id):
        pts = user_points.get(user_id, 55)
        if pts < 10:
            bot.reply_to(message, "❌ ليس لديك نقاط كافية لتشغيل الملف (تحتاج 10 نقاط على الأقل).")
            return

    status_msg = bot.reply_to(message, "⏳ **جاري حفظ الملف وتثبيت المكاتب...**", parse_mode='Markdown')

    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        file_path = os.path.join(uploaded_dir, file_name)

        with open(file_path, 'wb') as f:
            f.write(downloaded)

        subprocess.run([sys.executable, "-m", "pip", "install", "pyTelegramBotAPI", "requests", "aiohttp"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if file_name in running_processes:
            try:
                running_processes[file_name].terminate()
            except Exception:
                pass

        proc = subprocess.Popen([sys.executable, file_path], start_new_session=True)
        running_processes[file_name] = proc

        if not is_admin(user_id):
            user_points[user_id] -= 10

        bot.edit_message_text(
            f"✅ **تم تشغيل الملف `{file_name}` بنجاح!**\n\n"
            "💡 يمكنك إيقاف هذا الملف في أي وقت عبر زر **🛑 إيقاف ملف**.",
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            parse_mode='Markdown'
        )

    except Exception as e:
        bot.edit_message_text(f"❌ حدث خطأ أثناء تشغيل الملف:\n`{e}`", chat_id=message.chat.id, message_id=status_msg.message_id, parse_mode='Markdown')

# ======= التشغيل الرئيسي ======= #
if __name__ == '__main__':
    keep_alive()
    print("🤖 البوت يعمل بنجاح...")
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception:
            time.sleep(3)
