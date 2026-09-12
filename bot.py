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

# ======= ملفات التخزين الدائم ======= #
STORAGE_FILE = 'bot_storage.json'
EXPIRY_FILE = 'file_expiry.json'

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
    'python': '5260480440971570446',
    '1': '5141109049114232089',
    '2': '5140871649091912628',
    '3': '5141399818400170896',
    '4': '5138822752123225428',
    '5': '5141062672057369534',
}

def strip_emoji_from_text(text: str) -> str:
    emoji_pattern = re.compile(r'[\U00010000-\U0010ffff]|[\u2600-\u27BF]|[\uFE00-\uFE0F]|[\u2300-\u23FF]')
    return emoji_pattern.sub('', text).strip()

def btn(text, callback_data=None, url=None, emoji_key=None, style=None):
    clean_text = strip_emoji_from_text(text)
    b = types.InlineKeyboardButton(text=clean_text, callback_data=callback_data, url=url)
    if emoji_key and emoji_key in E:
        try:
            b.icon_custom_emoji_id = E[emoji_key]
        except Exception:
            pass
    if style:
        try:
            b.style = style
        except Exception:
            pass
    return b

def ce(emoji_key):
    if emoji_key in E:
        return f'<tg-emoji emoji-id="{E[emoji_key]}">⭐</tg-emoji>'
    return '⭐'

def send_with_emoji(chat_id, text, emoji_id=None, reply_markup=None, parse_mode='HTML'):
    try:
        if emoji_id:
            full_text = f'<tg-emoji emoji-id="{emoji_id}">⭐</tg-emoji> {text}'
            return bot.send_message(chat_id, full_text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            return bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)
    except:
        return bot.send_message(chat_id, text, reply_markup=reply_markup)

# ======= المتغيرات العامة والتخزين الدائم ======= #
bot = telebot.TeleBot(BOT_TOKEN)
bot_scripts = {}
uploaded_files_dir = "uploaded_files"
banned_users = set()
user_chats = {}
approved_users = {ADMIN_ID}
pending_requests = {}
admins = {ADMIN_ID}
waiting_for_library = set()
pending_inputs = {} # لتخزين انتظار المدخلات (رقم، كود، 2fa)

protection_enabled = True
protection_level = "medium"
bot_running = True
user_file_expiry = {}

if not os.path.exists(uploaded_files_dir):
    os.makedirs(uploaded_files_dir)

def load_storage():
    global approved_users, admins, banned_users, bot_scripts
    if os.path.exists(STORAGE_FILE):
        try:
            with open(STORAGE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                approved_users = set(data.get('approved_users', [ADMIN_ID]))
                admins = set(data.get('admins', [ADMIN_ID]))
                banned_users = set(data.get('banned_users', []))
                saved_scripts = data.get('bot_scripts', {})
                for cid_str, info in saved_scripts.items():
                    cid = int(cid_str)
                    bot_scripts[cid] = {
                        'processes': {},
                        'files': info.get('files', []),
                        'path': info.get('path', '')
                    }
        except Exception as e:
            print(f"Error loading storage: {e}")

def save_storage():
    try:
        data = {
            'approved_users': list(approved_users),
            'admins': list(admins),
            'banned_users': list(banned_users),
            'bot_scripts': {str(k): {'files': v.get('files', []), 'path': v.get('path', '')} for k, v in bot_scripts.items()}
        }
        with open(STORAGE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Error saving storage: {e}")

def load_expiry():
    global user_file_expiry
    if os.path.exists(EXPIRY_FILE):
        try:
            with open(EXPIRY_FILE, 'r') as f:
                data = json.load(f)
                user_file_expiry = {str(k): v for k, v in data.items()}
        except Exception as e:
            user_file_expiry = {}

def save_expiry():
    try:
        with open(EXPIRY_FILE, 'w') as f:
            json.dump(user_file_expiry, f)
    except Exception as e:
        print(f"Error saving expiry: {e}")

load_storage()
load_expiry()

lock = threading.Lock()
RENEWAL_HOURS = 2

def is_admin(user_id):
    return user_id in admins

def is_approved_user(user_id):
    return user_id in approved_users or user_id in admins

# ======= مراقبة مخرج العمليات (Subprocess Output & Interaction) ======= #
process_objects = {} # تخزين مراجع الـ Popen للتحكم بكتابة الـ stdin

def monitor_process_output(process, chat_id, script_name):
    while process.poll() is None:
        output = process.stdout.readline()
        if not output:
            break
        try:
            line = output.decode('utf-8', errors='ignore').strip()
            if not line:
                continue
            
            # فحص طلب رقم الهاتف
            if any(k in line.lower() for k in ['phone', 'number', 'رقم الهاتف', 'الرقم']):
                pending_inputs[chat_id] = {'process': process, 'type': 'phone', 'file': script_name}
                text = f"🔔 الملف (<code>{script_name}</code>) يطلب رقم الهاتف!\nأرسل رقم الهاتف مع رمز الدولة (مثال: <code>9647700000000+</code>):"
                bot.send_message(chat_id, text, parse_mode='HTML')
            
            # فحص طلب رمز التحقق OTP
            elif any(k in line.lower() for k in ['otp', 'code', 'كود', 'الرمز']):
                pending_inputs[chat_id] = {'process': process, 'type': 'otp', 'file': script_name}
                text = f"✨ الملف (<code>{script_name}</code>) يطلب كود التحقق (OTP)!\nأرسل الكود الواصل لك هنا مباشرة:"
                bot.send_message(chat_id, text, parse_mode='HTML')
            
            # فحص طلب كلمة سر التحقق بخطوتين 2FA
            elif any(k in line.lower() for k in ['2fa', 'password', 'كلمة سر', 'التحقق بخطوتين']):
                pending_inputs[chat_id] = {'process': process, 'type': '2fa', 'file': script_name}
                text = f"🔥 الملف (<code>{script_name}</code>) يطلب كلمة سر التحقق بخطوتين (2FA):"
                bot.send_message(chat_id, text, parse_mode='HTML')
        except Exception as e:
            print(f"Monitor error: {e}")

@bot.message_handler(func=lambda message: message.chat.id in pending_inputs, content_types=['text'])
def handle_subprocess_inputs(message):
    chat_id = message.chat.id
    user_input = message.text.strip()
    data = pending_inputs.get(chat_id)
    if data:
        proc = data['process']
        try:
            if proc.poll() is None:
                proc.stdin.write((user_input + '\n').encode('utf-8'))
                proc.stdin.flush()
                send_with_emoji(chat_id, "✅ تم إرسال المدخلات إلى الملف بنجاح.", E['check'])
            else:
                send_with_emoji(chat_id, "❌ العملية متوقفة ولا تستقبل مدخلات.", E['cross'])
        except Exception as e:
            send_with_emoji(chat_id, f"❌ خطأ في إرسال المدخلات: {e}", E['cross'])
        finally:
            pending_inputs.pop(chat_id, None)

# ======= دوال التشغيل والإيقاف ======= #
def stop_bot(script_path, chat_id):
    script_name = os.path.basename(script_path)
    try:
        if chat_id in bot_scripts and 'processes' in bot_scripts[chat_id]:
            process = bot_scripts[chat_id]['processes'].get(script_name)
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except:
                    process.kill()
                bot_scripts[chat_id]['processes'][script_name] = None
        return True
    except Exception as e:
        return False

def start_file(script_path, chat_id):
    script_name = os.path.basename(script_path)
    with lock:
        if chat_id not in bot_scripts:
            bot_scripts[chat_id] = {'processes': {}, 'files': [], 'path': ''}
        if 'processes' not in bot_scripts[chat_id]:
            bot_scripts[chat_id]['processes'] = {}
        try:
            old_process = bot_scripts[chat_id]['processes'].get(script_name)
            if old_process and old_process.poll() is None:
                return
            
            # تشغيل مع دعم الـ stdin و stdout للتقاط المدخلات والمخرجات
            p = subprocess.Popen(
                [sys.executable, script_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT
            )
            bot_scripts[chat_id]['processes'][script_name] = p
            
            # تشغيل خيط مراقبة مخرجات الملف
            threading.Thread(target=monitor_process_output, args=(p, chat_id, script_name), daemon=True).start()
            
            save_storage()
            send_with_emoji(chat_id, f"تم تشغيل الملف {script_name} بنجاح وربط نظام الإدخال التلقائي.", E['check'])
        except Exception as e:
            send_with_emoji(chat_id, f"فشل في تشغيل الملف: {e}", E['cross'])

# ======= استعادة وتشغيل الملفات المخزنة عند الإقلاع ======= #
def restore_saved_bots():
    for chat_id, info in bot_scripts.items():
        for file_name in info.get('files', []):
            script_path = os.path.join(uploaded_files_dir, file_name)
            if os.path.exists(script_path):
                try:
                    start_file(script_path, chat_id)
                except Exception as e:
                    print(f"Failed to restore {file_name}: {e}")

threading.Thread(target=restore_saved_bots, daemon=True).start()

# ======= القائمة الرئيسية ======= #
def show_main_menu(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        btn("التحكم في الحماية", callback_data='protection_control', emoji_key='settings', style="primary"),
        btn("رفع ملف", callback_data='upload', emoji_key='python', style="success")
    )
    markup.add(
        btn("الملفات المرفوعة", callback_data='uploaded_files_list', emoji_key='pencil', style="primary"),
        btn("سرعة البوت", callback_data='speed', emoji_key='fire', style="primary")
    )
    markup.add(
        btn("فتاة المحاور", callback_data='support_girl', emoji_key='sparkles', style="primary"),
        btn("حول البوت", callback_data='about_bot', emoji_key='bulb', style="primary")
    )
    markup.add(
        btn("تثبيت مكتبة", callback_data='download_lib', emoji_key='gem', style="success"),
        btn("الدعم الفني", callback_data='tech_support', emoji_key='bell', style="primary")
    )

    if is_admin(message.from_user.id):
        markup.add(
            btn("إدارة المستخدمين", callback_data='manage_users', emoji_key='people', style="primary"),
            btn("لوحة التحكم بالأدمن", callback_data='bot_control', emoji_key='crown', style="primary")
        )

    user_name = message.from_user.first_name or "مستخدم"
    text = f'مرحباً بك في منصة Python Hosting {ce("python")}\n\n{ce("sparkles")} مرحباً، {user_name}!\nاختر الخدمة المطلوبة:'
    try:
        bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode='HTML')
    except:
        bot.send_message(message.chat.id, text, reply_markup=markup)

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    if message.from_user.username in banned_users:
        send_with_emoji(message.chat.id, "تم حظرك من البوت.", E['warning'])
        return
    if is_approved_user(user_id):
        show_main_menu(message)
    else:
        send_with_emoji(message.chat.id, "⏳ تم إرسال طلبك للأدمن بانتظار الموافقة.", E['bell'])

# ======= استقبال الملفات المرفوعة وحفظها ======= #
@bot.message_handler(content_types=['document'])
def handle_file(message):
    if not is_approved_user(message.from_user.id):
        send_with_emoji(message.chat.id, "تحتاج إلى موافقة الأدمن", E['cross'])
        return
    try:
        chat_id = message.chat.id
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        bot_script_name = message.document.file_name
        if not bot_script_name.endswith('.py'):
            send_with_emoji(message.chat.id, "فقط ملفات .py مسموحة", E['cross'])
            return
        
        script_path = os.path.join(uploaded_files_dir, bot_script_name)
        with open(script_path, 'wb') as f:
            f.write(downloaded_file)
            
        if chat_id not in bot_scripts:
            bot_scripts[chat_id] = {'processes': {}, 'files': [], 'path': uploaded_files_dir}
        if bot_script_name not in bot_scripts[chat_id]['files']:
            bot_scripts[chat_id]['files'].append(bot_script_name)
            
        save_storage()
        send_with_emoji(chat_id, f"✅ تم رفع الملف <code>{bot_script_name}</code> وتخزينه بنجاح.", E['check'])
        start_file(script_path, chat_id)
    except Exception as e:
        send_with_emoji(message.chat.id, f"خطأ: {e}", E['cross'])

# ======= تشغيل البوت الأساسي ======= #
if __name__ == '__main__':
    print("🤖 البوت يعمل مع نظام التخزين والتحقق التفاعلي...")
    bot.infinity_polling()
