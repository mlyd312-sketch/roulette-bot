import sys
import asyncio
import threading
import re
import json
import os
import time
import traceback
import telebot
from telebot import types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from telethon import TelegramClient, functions, errors

# ==============================
# قاموس الإيموجيات المميزة ودوال الإنشاء
# ==============================

E = {
    'fire': '5424972470023104089',
    'check': '5206607081334906820',
    'sparkles': '5325547803936572038',
    'gem': '5427168083074628963',
    'pencil': '5395444784611480792',
    'settings': '5341715473882955310',
    'crown': '5217822164362739968',
    'chart': '5231200819986047254',
    'warning': '5447644880824181073',
    'trophy': '5188344996356448758',
    'people': '5258513401784573443',
    'link': '5271604874419647061',
    'picture': '5375074927252621134',
    'arrow': '5416117059207572332',
    'cross': '5210952531676504517',
    'bulb': '5422439311196834318',
    'bell': '5458603043203327669',
    'python': '5260480440971570446',
    '1': '5141109049114232089',
    '2': '5140871649091912628',
    '3': '5141399818400170896',
    '4': '5138822752123225428',
    '5': '5141062672057369534',
}

def strip_emoji_from_text(text: str) -> str:
    emoji_pattern = re.compile(
        r'[\U00010000-\U0010ffff]|[\u2600-\u27BF]|[\uFE00-\uFE0F]|[\u2300-\u23FF]'
    )
    return emoji_pattern.sub('', text).strip()

def create_emoji_btn(text, callback=None, url=None, emoji_id=None, color=None):
    if emoji_id:
        text = strip_emoji_from_text(text)
        
    btn = InlineKeyboardButton(text=text, callback_data=callback, url=url)
    if emoji_id:
        try:
            btn.icon_custom_emoji_id = emoji_id
        except:
            pass
    if color:
        btn.style = color
    return btn

# ======== بيانات الحساب الشخصي ========
PHONE_NUMBER = '+201103654695'  # <--- تأكد من الرقم
API_ID = 34001399
API_HASH = '4c0b01550fcbe8a6c8ef766408c990be'

# ======== استيراد المكتبات ========
try:
    print("✅ تم تحميل المكتبات بنجاح!")
except Exception as e:
    print(f"❌ خطأ في استيراد المكتبات: {e}")
    sys.exit(1)

# ======== إعدادات البوت ========
BOT_TOKEN = '8591173720:AAH4A4h97gRkm_bK8BCPgRVgJ2zzPSv4bl0'
ADMIN_ID = 1920665874

# ======== إدارة الملفات ========
CONFIG_FILE = 'config.json'
USER_DB = 'users.json'

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f: return json.load(f)
        except: pass
    return {'channel_username': 'FD_CQ'}

def save_config(c):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f: json.dump(c, f, ensure_ascii=False, indent=4)

def load_users():
    if os.path.exists(USER_DB):
        try:
            with open(USER_DB, 'r', encoding='utf-8') as f: return json.load(f)
        except: pass
    return {}

def save_users(u):
    with open(USER_DB, 'w', encoding='utf-8') as f: json.dump(u, f, ensure_ascii=False, indent=4)

config = load_config()
CHANNEL_USERNAME = config.get('channel_username', 'FD_CQ')

# ======== إعداد العملاء ========
telethon_loop = None
client = TelegramClient('session_exchange', API_ID, API_HASH)
bot = telebot.TeleBot(BOT_TOKEN)
admin_states = {}

# متغيرات مؤقتة لاستقبال الكود وكلمة المرور عبر الشات
auth_inputs = {
    'code': None,
    'password': None,
    'waiting_for': None
}

# ======== دوال مساعدة ========
def extract_channel_info(link):
    link = link.strip()
    match_public = re.search(r't\.me/([a-zA-Z0-9_]{5,})', link)
    if match_public and not link.startswith('https://t.me/+') and 'joinchat' not in link: return match_public.group(1)
    match_invite = re.search(r't\.me/(\+|joinchat/)([a-zA-Z0-9_-]+)', link)
    if match_invite: return f"+{match_invite.group(2)}"
    return None

def check_subscription(user_id):
    try:
        member = bot.get_chat_member(chat_id=f"@{CHANNEL_USERNAME}", user_id=user_id)
        if member.status in ['member', 'administrator', 'creator']: return True
        return False
    except Exception as e:
        print(f"⚠️ خطأ في فحص الاشتراك للمستخدم {user_id}: {e}")
        return False

# ======== دالة مغادرة القناة ========
async def leave_channel(channel_link):
    try:
        if not client.is_connected(): await client.connect()
        if not await client.is_user_authorized(): return False, "الحساب غير مسجل دخول"
        
        try:
            entity = await client.get_entity(channel_link)
        except:
            entity = channel_link
            
        await client(functions.channels.LeaveChannelRequest(channel=entity))
        return True, "success"
    except errors.UserNotParticipantError:
        return True, "not_participant"
    except errors.FloodWaitError as e:
        return False, f"flood_{e.seconds}"
    except Exception as e:
        return False, str(e)

# ======== دالة الفحص الأساسية ========
def run_leavers_check():
    print("\n🔍 [فحص] جاري فحص المستخدمين المغادرين...")
    current_users = load_users()
    if not current_users:
        print("📭 لا يوجد مستخدمون مسجلون حالياً.")
        return

    print(f"👥 عدد المستخدمين المسجلين: {len(current_users)}")
    for uid_str, data in list(current_users.items()):
        uid = int(uid_str)
        print(f"👤 جاري فحص المستخدم: {uid} | القناة: {data['link']}")
        
        is_subscribed = check_subscription(uid)
        
        if not is_subscribed:
            print(f"⚠️ المستخدم {uid} غادر قناتك! جاري مغادرة قناته...")
            
            leave_success = False
            leave_result = ""
            if telethon_loop:
                try:
                    future = asyncio.run_coroutine_threadsafe(leave_channel(data['link']), telethon_loop)
                    leave_success, leave_result = future.result(timeout=60)
                except Exception as e:
                    leave_success, leave_result = False, f"خطأ في الاتصال: {str(e)}"
            else:
                leave_success, leave_result = False, "الحساب الشخصي غير متصل"
            
            try:
                if leave_success:
                    status_msg = "✅ تم مغادرة قناته تلقائياً."
                else:
                    status_msg = f"❌ فشل مغادرة قناته تلقائياً. السبب: {leave_result}"
                    
                bot.send_message(
                    ADMIN_ID, 
                    f"⚠️ تنبيه هام:\n\n"
                    f"صاحب هاي القناة غادر قناتك!\n"
                    f"🔗 القناة: {data['link']}\n"
                    f"👤 اليوزر: @{data['username']}\n\n"
                    f"{status_msg}\n"
                    f"❌ تم إزالته من نظام التبادل."
                )
                print(f"✅ تم إرسال الإشعار للمالك بخصوص {uid}.")
            except Exception as e:
                print(f"❌ فشل إرسال التنبيه: {e}")
            
            del current_users[uid_str]
            save_users(current_users)
            print(f"🗑️ تم حذف المستخدم {uid} من قاعدة البيانات.")
        else:
            print(f"✅ المستخدم {uid} لا يزال مشتركاً.")
            
    print("🏁 [فحص] انتهى الفحص.\n")

def leavers_checker():
    print("👀 بدأ نظام مراقبة المغادرين (كل دقيقة)...")
    while True:
        try:
            time.sleep(60)
            run_leavers_check()
        except Exception as e:
            print(f"❌ خطأ في خيط المراقبة: {e}")
            traceback.print_exc()

@bot.message_handler(commands=['check'])
def manual_check(message):
    if message.from_user.id != ADMIN_ID: return
    bot.reply_to(message, "⏳ جاري الفحص اليدوي... يرجى الانتظار")
    threading.Thread(target=run_leavers_check, daemon=True).start()

# ======== لوحة التحكم ========
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    if user_id == ADMIN_ID:
        markup = InlineKeyboardMarkup()
        btn1 = create_emoji_btn("✏️ تغيير قناة الاشتراك", callback="change_channel", emoji_id=E['pencil'], color="primary")
        btn2 = create_emoji_btn("📊 حالة البوت", callback="bot_status", emoji_id=E['chart'], color="success")
        btn3 = create_emoji_btn("👥 عدد المستخدمين", callback="users_count", emoji_id=E['people'], color="primary")

        markup.add(btn1)
        markup.add(btn2)
        markup.add(btn3)
        bot.reply_to(message, f"👑 أهلاً بك يا مالك البوت\n\n📌 القناة الحالية: @{CHANNEL_USERNAME}\n\nاختر الإجراء:", reply_markup=markup)
        return

    if check_subscription(user_id):
        bot.reply_to(message, "✅ تم التحقق!\n❌ دز رابط قناتك:")
    else:
        markup = InlineKeyboardMarkup()
        btn_join = create_emoji_btn("📣 دخول القناة", url=f"https://t.me/{CHANNEL_USERNAME}", emoji_id=E['link'], color="primary")
        btn_check = create_emoji_btn("✅ تحقق من الاشتراك", callback="check_sub", emoji_id=E['check'], color="success")

        markup.add(btn_join)
        markup.add(btn_check)
        text = "هلا بيك! 👋\nخطوات الاشتراك:\n\n1️⃣ اضغط زر [دخول القناة]\n2️⃣ اشترك بقناة @" + CHANNEL_USERNAME + "\n3️⃣ ارجع للبوت واضغط [تحقق]\n4️⃣ دز رابط قناتك\n\n⚠️ إذا تغادر قناتنا، الحساب يغادر قناتك"
        bot.send_message(message.chat.id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "change_channel")
def ask_for_new_channel(call):
    if call.from_user.id != ADMIN_ID: return
    admin_states[call.from_user.id] = 'awaiting_channel'
    bot.send_message(call.message.chat.id, "📝 الرجاء إرسال يوزر القناة الجديدة:")

@bot.callback_query_handler(func=lambda call: call.data == "bot_status")
def show_bot_status(call):
    if call.from_user.id != ADMIN_ID: return
    status = "✅ يعمل" if telethon_loop and telethon_loop.is_running() else "⚠️ غير متصل"
    bot.answer_callback_query(call.id, f"حالة الحساب الشخصي: {status}\nعدد المستخدمين: {len(load_users())}", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "users_count")
def show_users_count(call):
    if call.from_user.id != ADMIN_ID: return
    bot.answer_callback_query(call.id, f"👥 عدد المستخدمين: {len(load_users())}", show_alert=True)

@bot.message_handler(func=lambda message: admin_states.get(message.from_user.id) == 'awaiting_channel')
def set_new_channel(message):
    global CHANNEL_USERNAME, config
    if message.from_user.id != ADMIN_ID: return
    new_channel = message.text.strip().replace('https://t.me/', '').replace('http://t.me/', '').replace('@', '')
    if not new_channel: return bot.reply_to(message, "❌ يوزر غير صالح.")
    CHANNEL_USERNAME = new_channel
    config['channel_username'] = new_channel
    save_config(config)
    admin_states[message.from_user.id] = None
    bot.reply_to(message, f"✅ تم التحديث!\n\n📌 القناة الجديدة: @{new_channel}")

@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def callback_check(call):
    user_id = call.from_user.id
    if check_subscription(user_id):
        bot.answer_callback_query(call.id, "✅ تم التحقق بنجاح!")
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="✅ تم التحقق!\n❌ دز رابط قناتك:")
    else:
        bot.answer_callback_query(call.id, "❌ لازم تنضم للقناة أولاً!", show_alert=True)

# استقبال كود التحقق أو كلمة المرور من الأدمن عبر البوت
@bot.message_handler(func=lambda message: message.from_user.id == ADMIN_ID and auth_inputs['waiting_for'] is not None)
def handle_auth_input(message):
    val = message.text.strip()
    w_for = auth_inputs['waiting_for']
    if w_for == 'code':
        auth_inputs['code'] = val
        auth_inputs['waiting_for'] = None
        bot.reply_to(message, "✅ تم استلام الكود، جاري المتابعة...")
    elif w_for == 'password':
        auth_inputs['password'] = val
        auth_inputs['waiting_for'] = None
        bot.reply_to(message, "✅ تم استلام كلمة المرور، جاري المتابعة...")

@bot.message_handler(func=lambda message: "t.me/" in message.text)
def handle_channel_link(message):
    if admin_states.get(message.from_user.id) == 'awaiting_channel': return
    user_link = message.text.strip()
    user_id = message.from_user.id
    username = message.from_user.username if message.from_user.username else 'لا يوجد'
    channel_info = extract_channel_info(user_link)
    print(f"📥 تم استلام رابط: {user_link} | تم استخراج: {channel_info}")

    if not channel_info: return bot.reply_to(message, "❌ الرابط غير صحيح.")

    bot.reply_to(message, "⏳ جاري انضمام الحساب للقناة...")

    def run_join():
        try:
            future = asyncio.run_coroutine_threadsafe(join_channel(channel_info), telethon_loop)
            return future.result(timeout=60)
        except Exception as e:
            return False, f"خطأ في الاتصال: {str(e)}"

    if telethon_loop is None:
        return bot.reply_to(message, "❌ الحساب الشخصي غير متصل. حاول لاحقاً.")

    success, result = run_join()

    if success:
        if result == "already": bot.reply_to(message, "✅ الحساب موجود بالفعل في القناة!")
        else: bot.reply_to(message, "✅ تم انضمام الحساب للقناة بنجاح!")
        users_data = load_users()
        users_data[str(user_id)] = {'link': user_link, 'username': username}
        save_users(users_data)
        try:
            bot.send_message(ADMIN_ID, f"📥 مستخدم أرسل قناته:\n{user_link}\n\n✅ تم الانضمام تلقائياً.")
        except: pass
    else:
        if "flood" in result:
            seconds = result.split('_')[1]
            bot.reply_to(message, f"❌ فشل الانضمام. انتظر {seconds} ثانية.")
        else:
            bot.reply_to(message, f"❌ فشل الانضمام: {result}")
        try:
            bot.send_message(ADMIN_ID, f"⚠️ فشل الانضمام:\n{user_link}\n\nالسبب: {result}")
        except: pass

async def join_channel(channel_info):
    try:
        if not client.is_connected(): await client.connect()
        if not await client.is_user_authorized(): return False, "الحساب غير مسجل دخول"
        await client(functions.channels.JoinChannelRequest(channel=channel_info))
        return True, "success"
    except errors.FloodWaitError as e: return False, f"flood_{e.seconds}"
    except errors.UserAlreadyParticipantError: return True, "already"
    except errors.ChatWriteForbiddenError: return False, "لا يمكن الانضمام (القناة تمنع)"
    except Exception as e: return False, str(e)

def start_telethon_thread():
    global telethon_loop
    telethon_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(telethon_loop)
    async def main():
        print("⏳ جاري الاتصال بالحساب...")
        try:
            await client.connect()
            if not await client.is_user_authorized():
                print("📤 جاري إرسال طلب كود التحقق...")
                await client.send_code_request(PHONE_NUMBER)
                
                try:
                    bot.send_message(ADMIN_ID, "🔑 تم إرسال طلب تسجيل الدخول.\n\nالرجاء إرسال **كود التحقق** الواصل لك هنا في الشات:")
                except Exception as ex:
                    print(f"❌ لم يتم إرسال رسالة التليجرام للأدمن: {ex}")
                    
                auth_inputs['waiting_for'] = 'code'
                
                while auth_inputs['code'] is None:
                    await asyncio.sleep(1)
                
                code = auth_inputs['code']
                auth_inputs['code'] = None
                
                try:
                    await client.sign_in(PHONE_NUMBER, code)
                except errors.SessionPasswordNeededError:
                    bot.send_message(ADMIN_ID, "🔒 الحساب محمي بكلمة مرور التحقق بخطوتين.\n\nالرجاء إرسال **كلمة المرور** هنا:")
                    auth_inputs['waiting_for'] = 'password'
                    
                    while auth_inputs['password'] is None:
                        await asyncio.sleep(1)
                        
                    password = auth_inputs['password']
                    auth_inputs['password'] = None
                    await client.sign_in(password=password)
            
            print("✅ تم تسجيل الدخول للحساب الشخصي بنجاح!")
            try:
                bot.send_message(ADMIN_ID, "✅ تم تسجيل الدخول للحساب الشخصي بنجاح وتفعيل البوت بالكامل!")
            except: pass
            await asyncio.Event().wait()
        except Exception as e:
            print(f"❌ خطأ في الحساب الشخصي: {e}")
            try:
                bot.send_message(ADMIN_ID, f"❌ خطأ أثناء تسجيل الدخول بالحساب الشخصي:\n{e}")
            except: pass
            traceback.print_exc()
    telethon_loop.run_until_complete(main())

if __name__ == "__main__":
    threading.Thread(target=start_telethon_thread, daemon=True).start()
    threading.Thread(target=leavers_checker, daemon=True).start()
    print("🚀 تشغيل البوت...")
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"❌ خطأ في البوت: {e}")
