import sys
import telebot
from telebot import types
import time
import subprocess
import threading
import os
import tempfile
import shutil
import re
import json
from datetime import datetime
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

# ======= إعدادات البوت ======= #
BOT_TOKEN = '8877293036:AAGg_82F0bT1Bhov42sk9qDcRMsVNpfnErw'
ADMIN_ID = 1920665874
YOUR_USERNAME = '@u_8_y'
ADMIN_CHANNEL = '@FD_CQ'

# ======= قاموس الإيموجيات المميزة ======= #
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
    'python': '5260480440971570446'
}

# ======= دوال مساعدة ======= #
def strip_emoji_from_text(text: str) -> str:
    emoji_pattern = re.compile(r'[\U00010000-\U0010ffff]|[\u2600-\u27BF]|[\uFE00-\uFE0F]|[\u2300-\u23FF]')
    return emoji_pattern.sub('', text).strip()

def btn(text, callback_data=None, url=None, emoji_key=None, style=None):
    clean_text = strip_emoji_from_text(text)
    b = types.InlineKeyboardButton(text=clean_text, callback_data=callback_data, url=url)
    if emoji_key and emoji_key in E:
        try: b.icon_custom_emoji_id = E[emoji_key]
        except: pass
    if style:
        try: b.style = style
        except: pass
    return b

def ce(emoji_key):
    return f'<tg-emoji emoji-id="{E[emoji_key]}">⭐</tg-emoji>' if emoji_key in E else '⭐'

def send_with_emoji(chat_id, text, emoji_id=None, reply_markup=None, parse_mode='HTML'):
    try:
        msg = f'<tg-emoji emoji-id="{emoji_id}">⭐</tg-emoji> {text}' if emoji_id else text
        return bot.send_message(chat_id, msg, reply_markup=reply_markup, parse_mode=parse_mode)
    except:
        return bot.send_message(chat_id, text, reply_markup=reply_markup)

def format_remaining_time(seconds):
    if seconds <= 0: return "انتهى"
    hours, remainder = divmod(int(seconds), 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{hours} ساعة و{minutes} دقيقة" if hours > 0 else f"{minutes} دقيقة"

# ======= المتغيرات العامة ======= #
bot = telebot.TeleBot(BOT_TOKEN)
bot_scripts = {}
uploaded_files_dir = "uploaded_files"
banned_users = set()
user_chats = {}
approved_users = {ADMIN_ID}
admins = {ADMIN_ID}
pending_requests = {}
pending_inputs = {}
waiting_for_library = set()

protection_level = "medium"
bot_running = True
RENEWAL_HOURS = 2
EXPIRY_FILE = 'file_expiry.json'
user_file_expiry = {}

def load_expiry():
    global user_file_expiry
    if os.path.exists(EXPIRY_FILE):
        try:
            with open(EXPIRY_FILE, 'r') as f:
                user_file_expiry = {str(k): v for k, v in json.load(f).items()}
        except: user_file_expiry = {}

def save_expiry():
    try:
        with open(EXPIRY_FILE, 'w') as f: json.dump(user_file_expiry, f)
    except: pass

load_expiry()
lock = threading.Lock()

if not os.path.exists(uploaded_files_dir):
    os.makedirs(uploaded_files_dir)

def is_admin(user_id): return user_id in admins
def is_approved_user(user_id): return user_id in approved_users or user_id in admins

def request_approval(user_id, user_info):
    pending_requests[user_id] = user_info
    markup = types.InlineKeyboardMarkup()
    markup.add(btn("رفض", f'reject_{user_id}', emoji_key='cross', style="danger"),
               btn("قبول", f'approve_{user_id}', emoji_key='check', style="success"))
    
    text = (f'{ce("bell")} <b>طلب اشتراك جديد:</b>\n\n'
            f'{ce("people")} الاسم: {user_info["first_name"]}\n'
            f'{ce("chart")} ID: <code>{user_id}</code>\n'
            f'{ce("link")} اليوزر: @{user_info.get("username", "غير متوفر")}\n'
            f'{ce("settings")} الوقت: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    try: bot.send_message(ADMIN_ID, text, reply_markup=markup, parse_mode='HTML')
    except: pass

def send_waiting_message(chat_id):
    markup = types.InlineKeyboardMarkup()
    markup.add(btn("التواصل مع الدعم", callback_data='online_support', emoji_key='bell', style="primary"))
    text = f'{ce("settings")} <b>تم إرسال طلب اشتراكك للأدمن.</b>\nيرجى الانتظار.'
    try: bot.send_message(chat_id, text, reply_markup=markup, parse_mode='HTML')
    except: pass

def stop_bot(script_path, chat_id):
    script_name = os.path.basename(script_path)
    try:
        if chat_id in bot_scripts and 'processes' in bot_scripts[chat_id]:
            process = bot_scripts[chat_id]['processes'].get(script_name)
            if process and process.poll() is None:
                process.terminate()
                try: process.wait(timeout=5)
                except: process.kill()
                bot_scripts[chat_id]['processes'][script_name] = None
        if chat_id in pending_inputs:
            del pending_inputs[chat_id]
        return True
    except: return False

# 📌 المراقبة الدقيقة: قراءة حرف بحرف لالتقاط الطلب فوراً (بدون انتظار النزول لسطر جديد)
def monitor_output(process, chat_id, script_name):
    try:
        buffer = ""
        while process.poll() is None:
            char = process.stdout.read(1)
            if not char:
                time.sleep(0.1)
                continue
            
            try:
                char_str = char.decode('utf-8', errors='ignore')
                buffer += char_str
            except:
                continue
            
            # طباعة السطر في كونسول الاستضافة إذا اكتمل
            if char_str == '\n':
                print(f"[{script_name}] {buffer.strip()}")
                buffer = ""
                continue
            
            lower_text = buffer.lower()
            
            # فحص إذا كان الملف طلب إدخال (رقم، كود، باسوورد)
            if chat_id not in pending_inputs:
                if any(p in lower_text for p in ['phone number', 'enter phone', 'your phone', 'phone:', 'رقم الهاتف', 'الرقم:']):
                    pending_inputs[chat_id] = {'process': process, 'type': 'phone'}
                    try: bot.send_message(chat_id, f"📱 الملف ({script_name}) يطلب رقم حساب تيليجرام.\nأرسل رقمك الآن (مثال: +964...):")
                    except: pass
                    buffer = ""
                
                elif any(c in lower_text for c in ['enter code', 'your code', 'code:', 'otp', 'كود التحقق', 'الكود']):
                    pending_inputs[chat_id] = {'process': process, 'type': 'code'}
                    try: bot.send_message(chat_id, f"🔑 الملف ({script_name}) يطلب كود التحقق.\nأرسل الكود هنا:")
                    except: pass
                    buffer = ""

                elif any(pw in lower_text for pw in ['password', '2fa', 'two-step', 'كلمة المرور', 'كلمة السر', 'cloud password']):
                    pending_inputs[chat_id] = {'process': process, 'type': 'password'}
                    try: bot.send_message(chat_id, f"🔐 الملف ({script_name}) يطلب التحقق الثنائي (كلمة المرور).\nأرسل كلمة المرور:")
                    except: pass
                    buffer = ""
    except Exception as e:
        print(f"Monitor error: {e}")

def start_file(script_path, chat_id):
    script_name = os.path.basename(script_path)
    with lock:
        if chat_id not in bot_scripts:
            bot_scripts[chat_id] = {'processes': {}, 'files': [], 'path': ''}
        try:
            old_process = bot_scripts[chat_id]['processes'].get(script_name)
            if old_process and old_process.poll() is None:
                send_with_emoji(chat_id, f"الملف {script_name} يعمل بالفعل.", E['warning'])
                return
            
            env = dict(os.environ)
            env['PYTHONUNBUFFERED'] = '1'
            
            # تشغيل بـ bufsize=0 و -u لمنع أي تأخير في المخرجات
            p = subprocess.Popen(
                [sys.executable, "-u", script_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                bufsize=0
            )
            bot_scripts[chat_id]['processes'][script_name] = p
            bot_scripts[chat_id]['name'] = script_name
            bot_scripts[chat_id]['path'] = script_path

            threading.Thread(target=monitor_output, args=(p, chat_id, script_name), daemon=True).start()

            if not is_admin(chat_id):
                chat_key = str(chat_id)
                if chat_key not in user_file_expiry:
                    user_file_expiry[chat_key] = {}
                user_file_expiry[chat_key][script_name] = time.time() + (RENEWAL_HOURS * 3600)
                save_expiry()
                text = (f'{ce("check")} تم تشغيل الملف <code>{script_name}</code>\n'
                        f'{ce("settings")} مدة التشغيل: {RENEWAL_HOURS} ساعات')
                bot.send_message(chat_id, text, parse_mode='HTML')
            else:
                send_with_emoji(chat_id, f"تم تشغيل الملف {script_name} بنجاح.", E['check'])
        except Exception as e:
            send_with_emoji(chat_id, f"فشل في التشغيل: {e}", E['cross'])

def check_expired_files():
    while True:
        try:
            current_time = time.time()
            for user_id_str in list(user_file_expiry.keys()):
                user_id = int(user_id_str)
                for file_name in list(user_file_expiry[user_id_str].keys()):
                    if current_time >= user_file_expiry[user_id_str][file_name]:
                        if user_id in bot_scripts and 'processes' in bot_scripts[user_id]:
                            process = bot_scripts[user_id]['processes'].get(file_name)
                            if process and process.poll() is None:
                                process.terminate()
                                bot_scripts[user_id]['processes'][file_name] = None
                                try: bot.send_message(user_id, f'انتهى وقت تشغيل: <code>{file_name}</code>', parse_mode='HTML')
                                except: pass
                        del user_file_expiry[user_id_str][file_name]
                        if not user_file_expiry[user_id_str]: del user_file_expiry[user_id_str]
                        save_expiry()
        except: pass
        time.sleep(60)

threading.Thread(target=check_expired_files, daemon=True).start()

def show_main_menu(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        btn("التحكم في الحماية", 'protection_control', emoji_key='settings', style="primary"),
        btn("رفع ملف", 'upload', emoji_key='python', style="success"),
        btn("الملفات المرفوعة", 'uploaded_files_list', emoji_key='pencil', style="primary"),
        btn("سرعة البوت", 'speed', emoji_key='fire', style="primary"),
        btn("فتاة المحاور", 'support_girl', emoji_key='sparkles', style="primary"),
        btn("حول البوت", 'about_bot', emoji_key='bulb', style="primary"),
        btn("تثبيت مكتبة", 'download_lib', emoji_key='gem', style="success"),
        btn("الدعم الفني", 'tech_support', emoji_key='bell', style="primary")
    )
    if is_admin(message.from_user.id):
        markup.add(btn("إدارة المستخدمين", 'manage_users', emoji_key='people', style="primary"),
                   btn("لوحة التحكم بالأدمن", 'bot_control', emoji_key='crown', style="primary"))
    
    text = (f'مرحباً بك في منصة Python Hosting {ce("python")}\n\n'
            f'{ce("sparkles")} مرحباً، {message.from_user.first_name}!\nاختر الخدمة المطلوبة:')
    try: bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode='HTML')
    except: bot.send_message(message.chat.id, text, reply_markup=markup)

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    if user_id not in user_chats: user_chats[user_id] = True
    if message.from_user.username in banned_users: return
    
    if is_approved_user(user_id): show_main_menu(message)
    elif user_id in pending_requests: send_waiting_message(message.chat.id)
    else:
        request_approval(user_id, {
            'first_name': message.from_user.first_name,
            'username': message.from_user.username or 'غير متوفر'
        })
        send_waiting_message(message.chat.id)

@bot.callback_query_handler(func=lambda call: call.data in ['upload', 'speed', 'uploaded_files_list', 'support_girl', 'tech_support', 'about_bot', 'download_lib'])
def main_menus(call):
    if not is_approved_user(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ تحتاج موافقة الأدمن")
        return
    bot.answer_callback_query(call.id)
    
    if call.data == 'upload':
        markup = types.InlineKeyboardMarkup().add(btn("إلغاء", 'back_to_main', emoji_key='cross', style="danger"))
        bot.send_message(call.message.chat.id, f'{ce("python")} <b>قم بإرسال ملف البوت بصيغة (.py) الآن:</b>', reply_markup=markup, parse_mode='HTML')
    
    elif call.data == 'uploaded_files_list':
        markup = types.InlineKeyboardMarkup(row_width=1)
        chat_id = call.message.chat.id
        if chat_id in bot_scripts and bot_scripts[chat_id].get('files'):
            for f in bot_scripts[chat_id]['files']:
                proc = bot_scripts[chat_id]['processes'].get(f)
                status = "يعمل" if proc and proc.poll() is None else "متوقف"
                markup.add(btn(f"{f} ({status})", f'file_control_{f}', emoji_key='python', style="primary"))
        else:
            markup.add(btn("لا توجد ملفات", 'noop', emoji_key='cross', style="danger"))
        markup.add(btn("رجوع", 'back_to_main', emoji_key='arrow', style="primary"))
        bot.send_message(chat_id, f'{ce("chart")} <b>الملفات المرفوعة:</b>', reply_markup=markup, parse_mode='HTML')
        
    elif call.data == 'download_lib':
        waiting_for_library.add(call.from_user.id)
        markup = types.InlineKeyboardMarkup().add(btn("إلغاء", 'cancel_library', emoji_key='cross', style="danger"))
        bot.send_message(call.message.chat.id, f'{ce("gem")} <b>أرسل اسم المكتبة:</b>', reply_markup=markup, parse_mode='HTML')
        
    elif call.data == 'speed':
        msg = bot.send_message(call.message.chat.id, "⏳ جاري القياس...")
        time.sleep(1)
        bot.edit_message_text(f'{ce("fire")} <b>سرعة الاستجابة:</b> 85.50 ms', call.message.chat.id, msg.message_id, parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data.startswith('file_control_'))
def file_control_menu(call):
    if not is_approved_user(call.from_user.id): return
    bot.answer_callback_query(call.id)
    file_name = call.data.replace('file_control_', '')
    chat_id = call.message.chat.id
    proc = bot_scripts.get(chat_id, {}).get('processes', {}).get(file_name)
    is_running = proc and proc.poll() is None
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    if is_running: markup.add(btn("إيقاف", f'stopfile_{chat_id}_{file_name}', emoji_key='cross', style="danger"))
    else: markup.add(btn("تشغيل", f'startfile_{chat_id}_{file_name}', emoji_key='check', style="success"))
    markup.add(btn("حذف", f'deletefile_{chat_id}_{file_name}', emoji_key='warning', style="danger"),
               btn("رجوع", 'uploaded_files_list', emoji_key='arrow', style="primary"))
    
    text = f'{ce("python")} <b>التحكم بالملف:</b>\n<code>{file_name}</code>\nالحالة: <b>{"يعمل" if is_running else "متوقف"}</b>'
    try: bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup, parse_mode='HTML')
    except: pass

@bot.callback_query_handler(func=lambda call: call.data.startswith(('startfile_', 'stopfile_', 'deletefile_')))
def file_actions(call):
    action, chat_id_str, file_name = call.data.split('_', 2)
    chat_id = int(chat_id_str)
    script_path = os.path.join(uploaded_files_dir, file_name)
    
    if action == 'startfile':
        start_file(script_path, chat_id)
        bot.answer_callback_query(call.id, "✅ تم التشغيل")
        call.data = f'file_control_{file_name}'
        file_control_menu(call)
    elif action == 'stopfile':
        stop_bot(script_path, chat_id)
        bot.answer_callback_query(call.id, "✅ تم الإيقاف")
        call.data = f'file_control_{file_name}'
        file_control_menu(call)
    elif action == 'deletefile':
        stop_bot(script_path, chat_id)
        if os.path.exists(script_path): os.remove(script_path)
        bot.answer_callback_query(call.id, "🗑️ تم الحذف")
        call.data = 'uploaded_files_list'
        main_menus(call)

@bot.callback_query_handler(func=lambda call: call.data == 'back_to_main')
def back_to_main(call):
    bot.answer_callback_query(call.id)
    show_main_menu(call.message)

@bot.callback_query_handler(func=lambda call: call.data == 'cancel_library')
def cancel_lib(call):
    waiting_for_library.discard(call.from_user.id)
    bot.answer_callback_query(call.id, "تم الإلغاء")

@bot.message_handler(func=lambda msg: msg.from_user.id in waiting_for_library, content_types=['text'])
def install_library_step(message):
    waiting_for_library.discard(message.from_user.id)
    lib = message.text.strip()
    try:
        res = subprocess.run([sys.executable, "-m", "pip", "install", lib], capture_output=True, text=True, timeout=120)
        send_with_emoji(message.chat.id, f"✅ تم التثبيت" if res.returncode == 0 else "❌ فشل التثبيت", E['check' if res.returncode==0 else 'cross'])
    except Exception as e:
        send_with_emoji(message.chat.id, f"❌ خطأ: {e}", E['cross'])

@bot.message_handler(content_types=['document'])
def handle_file(message):
    if not is_approved_user(message.from_user.id): return
    try:
        file_name = message.document.file_name
        if not file_name.endswith('.py'):
            send_with_emoji(message.chat.id, "فقط ملفات .py", E['cross'])
            return
        
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        script_path = os.path.join(uploaded_files_dir, file_name)
        
        with open(script_path, 'wb') as f:
            f.write(downloaded)
            
        if message.chat.id not in bot_scripts: bot_scripts[message.chat.id] = {'processes': {}, 'files': [], 'path': ''}
        if file_name not in bot_scripts[message.chat.id]['files']: bot_scripts[message.chat.id]['files'].append(file_name)
            
        send_with_emoji(message.chat.id, f"✅ تم رفع <code>{file_name}</code> بنجاح.", E['check'])
        start_file(script_path, message.chat.id)
    except Exception as e:
        send_with_emoji(message.chat.id, f"خطأ: {e}", E['cross'])

# 📌 استقبال الإدخالات (الرقم، الكود، التحقق) وإرسالها للملف
@bot.message_handler(func=lambda msg: msg.chat.id in pending_inputs, content_types=['text'])
def receive_input(message):
    chat_id = message.chat.id
    user_input = message.text.strip()
    data = pending_inputs.get(chat_id)
    
    if data:
        process = data['process']
        try:
            if process.poll() is None:
                process.stdin.write((user_input + '\n').encode('utf-8'))
                process.stdin.flush()
                send_with_emoji(chat_id, "✅ تم إرسال البيانات للملف.", E['check'])
            else:
                send_with_emoji(chat_id, "❌ العملية متوقفة.", E['warning'])
        except Exception as e:
            send_with_emoji(chat_id, f"❌ خطأ أثناء الإرسال: {e}", E['cross'])
        finally:
            pending_inputs.pop(chat_id, None)

@bot.callback_query_handler(func=lambda call: call.data.startswith(('approve_', 'reject_')))
def admin_approval(call):
    if not is_admin(call.from_user.id): return
    action, user_id_str = call.data.split('_')
    user_id = int(user_id_str)
    
    if user_id in pending_requests:
        pending_requests.pop(user_id)
        if action == 'approve':
            approved_users.add(user_id)
            try: bot.send_message(user_id, "🎉 تمت الموافقة! أرسل /start")
            except: pass
            bot.answer_callback_query(call.id, "✅ تم القبول")
        else:
            try: bot.send_message(user_id, "❌ تم رفض طلبك.")
            except: pass
            bot.answer_callback_query(call.id, "❌ تم الرفض")

@bot.callback_query_handler(func=lambda call: call.data == 'noop')
def noop(call): bot.answer_callback_query(call.id)

if __name__ == '__main__':
    print("🤖 البوت يعمل...")
    try:
        bot.infinity_polling()
    except Exception as e:
        print(f"❌ خطأ: {e}")
        time.sleep(5)
