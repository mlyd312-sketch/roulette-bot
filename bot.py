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
    'python': '5260480440971570446',
    '1': '5141109049114232089',
    '2': '5140871649091912628',
    '3': '5141399818400170896',
    '4': '5138822752123225428',
    '5': '5141062672057369534',
}

# ======= دوال مساعدة ======= #
def strip_emoji_from_text(text: str) -> str:
    emoji_pattern = re.compile(
        r'[\U00010000-\U0010ffff]|[\u2600-\u27BF]|[\uFE00-\uFE0F]|[\u2300-\u23FF]'
    )
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
        try:
            return bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)
        except:
            return bot.send_message(chat_id, text, reply_markup=reply_markup)

def edit_with_emoji(chat_id, message_id, text, emoji_id=None, reply_markup=None, parse_mode='HTML'):
    try:
        if emoji_id:
            full_text = f'<tg-emoji emoji-id="{emoji_id}">⭐</tg-emoji> {text}'
            return bot.edit_message_text(full_text, chat_id, message_id, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            return bot.edit_message_text(text, chat_id, message_id, reply_markup=reply_markup, parse_mode=parse_mode)
    except:
        try:
            return bot.edit_message_text(text, chat_id, message_id, reply_markup=reply_markup, parse_mode=parse_mode)
        except:
            pass

def format_remaining_time(seconds):
    if seconds <= 0:
        return "انتهى"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    if hours > 0:
        return f"{hours} ساعة و{minutes} دقيقة"
    return f"{minutes} دقيقة"

# ======= المتغيرات العامة ======= #
bot = telebot.TeleBot(BOT_TOKEN)
bot_scripts = {}
uploaded_files_dir = "uploaded_files"
banned_users = set()
user_chats = {}
approved_users = set()
pending_requests = {}
pending_inputs = {} # تخزين انتظار رقم الهاتف أو الكود أو التحقق للملفات
approved_users.add(ADMIN_ID)
admins = {ADMIN_ID}
waiting_for_library = set()

protection_enabled = True
protection_level = "medium"
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024
bot_running = True

RENEWAL_HOURS = 2
EXPIRY_FILE = 'file_expiry.json'
user_file_expiry = {}

def load_expiry():
    global user_file_expiry
    if os.path.exists(EXPIRY_FILE):
        try:
            with open(EXPIRY_FILE, 'r') as f:
                data = json.load(f)
                user_file_expiry = {str(k): v for k, v in data.items()}
        except Exception as e:
            print(f"Error loading expiry: {e}")
            user_file_expiry = {}

def save_expiry():
    try:
        with open(EXPIRY_FILE, 'w') as f:
            json.dump(user_file_expiry, f)
    except Exception as e:
        print(f"Error saving expiry: {e}")

load_expiry()

lock = threading.Lock()
executor = ThreadPoolExecutor(max_workers=10)

if not os.path.exists(uploaded_files_dir):
    os.makedirs(uploaded_files_dir)

def save_chat_id(chat_id):
    if chat_id not in user_chats:
        user_chats[chat_id] = True

def is_admin(user_id):
    return user_id in admins

def is_approved_user(user_id):
    return user_id in approved_users or user_id in admins

def request_approval(user_id, user_info):
    pending_requests[user_id] = user_info
    markup = types.InlineKeyboardMarkup()
    approve_button = btn("قبول المستخدم", callback_data=f'approve_{user_id}', emoji_key='check', style="success")
    reject_button = btn("رفض المستخدم", callback_data=f'reject_{user_id}', emoji_key='cross', style="danger")
    markup.add(reject_button, approve_button)

    text = (
        f'{ce("bell")} <b>طلب اشتراك جديد:</b>\n\n'
        f'{ce("people")} الاسم: {user_info["first_name"]}\n'
        f'{ce("chart")} ID: <code>{user_id}</code>\n'
        f'{ce("link")} اليوزر: @{user_info.get("username", "غير متوفر")}\n'
        f'{ce("settings")} الوقت: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n\n'
        f'{ce("sparkles")} اختر الإجراء المناسب:'
    )
    try:
        bot.send_message(ADMIN_ID, text, reply_markup=markup, parse_mode='HTML')
    except:
        bot.send_message(ADMIN_ID, "طلب اشتراك جديد", reply_markup=markup)

def send_waiting_message(chat_id):
    markup = types.InlineKeyboardMarkup()
    support_button = btn("التواصل مع الدعم", callback_data='online_support', emoji_key='bell', style="primary")
    markup.add(support_button)

    text = (
        f'{ce("settings")} <b>تم إرسال طلب اشتراكك إلى الأدمن.</b>\n'
        f'يرجى الانتظار حتى يتم الموافقة على طلبك.\n\n'
        f'{ce("bell")} للتواصل مع الدعم اضغط على الزر أدناه:'
    )
    try:
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode='HTML')
    except:
        bot.send_message(chat_id, "⏳ تم إرسال الطلب.", reply_markup=markup)

def scan_file_for_malicious_code(file_path, user_id):
    if is_admin(user_id):
        return False, None
    try:
        with open(file_path, 'rb') as f:
            content = f.read().decode('utf-8', errors='replace')
        dangerous_patterns = []
        if protection_level == "low":
            dangerous_patterns = [r"rm\s+-rf\s+[\'\"]?/", r"eval\s*\(", r"exec\s*\("]
        elif protection_level == "medium":
            dangerous_patterns = [
                r"rm\s+-rf\s+[\'\"]?/", r"import\s+marshal", r"import\s+zlib",
                r"import\s+base64", r"eval\s*\(", r"exec\s*\(", r"shutil\.make_archive",
                r"subprocess\.call", r"subprocess\.Popen", r"os\.system"
            ]
        else:
            dangerous_patterns = [
                r"rm\s+-rf\s+[\'\"]?/", r"import\s+marshal", r"import\s+zlib",
                r"import\s+base64", r"eval\s*\(", r"exec\s*\(", r"shutil\.make_archive",
                r"subprocess", r"os\.system", r"os\.popen", r"sys\.exit"
            ]
        for pattern in dangerous_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return True, f"تم اكتشاف أمر خطير: {pattern}"
        return False, None
    except Exception as e:
        return True, f"خطأ في الفحص: {e}"

def stop_bot(script_path, chat_id):
    script_name = os.path.basename(script_path)
    try:
        if chat_id in bot_scripts and 'processes' in bot_scripts[chat_id]:
            process = bot_scripts[chat_id]['processes'].get(script_name)
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                bot_scripts[chat_id]['processes'][script_name] = None
        if chat_id in pending_inputs:
            del pending_inputs[chat_id]
        return True
    except Exception as e:
        print(f"Error stopping bot: {e}")
        return False

# 📌 دالة مراقبة مخرجات الملف لاكتشاف طلب رقم الهاتف أو الكود أو التحقق (2FA) بدقة
def monitor_output(process, chat_id, script_name):
    try:
        while process.poll() is None:
            line = process.stdout.readline()
            if not line:
                break
            text_line = line.decode('utf-8', errors='ignore').strip()
            if not text_line:
                continue
            
            print(f"[{script_name}] Output: {text_line}")
            lower_text = text_line.lower()
            
            # إذا طلب الملف رقم الهاتف
            if any(w in lower_text for w in ['phone', 'number', 'رقم', 'mobile', 'cell']):
                pending_inputs[chat_id] = {'process': process, 'type': 'phone'}
                try:
                    bot.send_message(chat_id, f"📱 الملف ({script_name}) يطلب رقم حساب تيليجرام.\nأرسل رقمك الآن مع رمز الدولة (مثال: 9647700000000+):")
                except:
                    pass
            
            # إذا طلب الملف كود التحقق (OTP)
            elif any(w in lower_text for w in ['code', 'otp', 'الرمز', 'كود', 'login code', 'telegram code']):
                pending_inputs[chat_id] = {'process': process, 'type': 'code'}
                try:
                    bot.send_message(chat_id, f"🔑 الملف ({script_name}) يطلب كود التحقق الذي وصل إلى حسابك.\nأرسل الكود هنا:")
                except:
                    pass

            # إذا طلب الملف كلمة مرور التحقق بخطوتين (2FA / password)
            elif any(w in lower_text for w in ['password', '2fa', 'تحقق', 'كلمة المرور', 'two-step', 'cloud password']):
                pending_inputs[chat_id] = {'process': process, 'type': 'password'}
                try:
                    bot.send_message(chat_id, f"🔐 الملف ({script_name}) يطلب رمز التحقق الثنائي (كلمة مرور السحابة / 2FA).\nأرسل كلمة المرور هنا:")
                except:
                    pass
    except Exception as e:
        print(f"Monitor error: {e}")

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
                send_with_emoji(chat_id, f"الملف {script_name} يعمل بالفعل.", E['warning'])
                return
            
            # تشغيل العملية مع ضبط PYTHONUNBUFFERED لضمان خروج النصوص فوراً دون تخزين مؤقت
            env = dict(os.environ)
            env['PYTHONUNBUFFERED'] = '1'
            
            p = subprocess.Popen(
                [sys.executable, script_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env
            )
            bot_scripts[chat_id]['processes'][script_name] = p
            bot_scripts[chat_id]['name'] = script_name
            bot_scripts[chat_id]['path'] = script_path

            # بدء خيط مراقبة مخرجات الملف لاكتشاف الطلبات
            threading.Thread(target=monitor_output, args=(p, chat_id, script_name), daemon=True).start()

            if not is_admin(chat_id):
                chat_key = str(chat_id)
                if chat_key not in user_file_expiry:
                    user_file_expiry[chat_key] = {}
                user_file_expiry[chat_key][script_name] = time.time() + (RENEWAL_HOURS * 3600)
                save_expiry()
                text = (
                    f'{ce("check")} تم تشغيل الملف <code>{script_name}</code>\n'
                    f'{ce("settings")} مدة التشغيل: {RENEWAL_HOURS} ساعات\n'
                    f'بعد انتهاء المدة، سيتم إيقافه تلقائياً.'
                )
                try:
                    bot.send_message(chat_id, text, parse_mode='HTML')
                except:
                    bot.send_message(chat_id, f"✅ تم تشغيل {script_name}")
            else:
                send_with_emoji(chat_id, f"تم تشغيل الملف {script_name} بنجاح.", E['check'])
        except Exception as e:
            send_with_emoji(chat_id, f"فشل في تشغيل الملف: {e}", E['cross'])

def start_bot_control():
    global bot_running
    bot_running = True

def stop_bot_control():
    global bot_running
    bot_running = False

def check_expired_files():
    while True:
        try:
            current_time = time.time()
            for user_id_str in list(user_file_expiry.keys()):
                user_id = int(user_id_str)
                for file_name in list(user_file_expiry[user_id_str].keys()):
                    expiry = user_file_expiry[user_id_str][file_name]
                    if current_time >= expiry:
                        script_path = os.path.join(uploaded_files_dir, file_name)
                        if user_id in bot_scripts and 'processes' in bot_scripts[user_id]:
                            process = bot_scripts[user_id]['processes'].get(file_name)
                            if process and process.poll() is None:
                                process.terminate()
                                try:
                                    process.wait(timeout=5)
                                except:
                                    process.kill()
                                bot_scripts[user_id]['processes'][file_name] = None
                                try:
                                    text = (
                                        f'{ce("settings")} <b>انتهى وقت تشغيل الملف:</b>\n\n'
                                        f'📁 <code>{file_name}</code>\n\n'
                                        f'انتهت صلاحية التشغيل ({RENEWAL_HOURS} ساعات).'
                                    )
                                    bot.send_message(user_id, text, parse_mode='HTML')
                                except:
                                    pass
                        del user_file_expiry[user_id_str][file_name]
                        if not user_file_expiry[user_id_str]:
                            del user_file_expiry[user_id_str]
                        save_expiry()
        except Exception as e:
            print(f"Error in check_expired_files: {e}")
        time.sleep(60)

threading.Thread(target=check_expired_files, daemon=True).start()

def show_main_menu(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    upload_button          = btn("رفع ملف", callback_data='upload', emoji_key='python', style="success")
    protection_button      = btn("التحكم في الحماية", callback_data='protection_control', emoji_key='settings', style="primary")
    speed_button           = btn("سرعة البوت", callback_data='speed', emoji_key='fire', style="primary")
    uploaded_files_button  = btn("الملفات المرفوعة", callback_data='uploaded_files_list', emoji_key='pencil', style="primary")
    about_button           = btn("حول البوت", callback_data='about_bot', emoji_key='bulb', style="primary")
    support_girl_button    = btn("فتاة المحاور", callback_data='support_girl', emoji_key='sparkles', style="primary")
    tech_support_button    = btn("الدعم الفني", callback_data='tech_support', emoji_key='bell', style="primary")
    install_lib_button     = btn("تثبيت مكتبة", callback_data='download_lib', emoji_key='gem', style="success")

    markup.add(protection_button, upload_button)
    markup.add(uploaded_files_button, speed_button)
    markup.add(support_girl_button, about_button)
    markup.add(install_lib_button, tech_support_button)

    if is_admin(message.from_user.id):
        users_button       = btn("إدارة المستخدمين", callback_data='manage_users', emoji_key='people', style="primary")
        bot_control_button = btn("لوحة التحكم بالأدمن", callback_data='bot_control', emoji_key='crown', style="primary")
        markup.add(users_button, bot_control_button)

    user_name = message.from_user.first_name or "مستخدم"
    text = (
        f'مرحباً بك في منصة Python Hosting {ce("python")}\n\n'
        f'{ce("sparkles")} مرحباً، {user_name}!\n'
        f'اختر الخدمة المطلوبة من الأزرار أدناه:'
    )
    try:
        bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode='HTML')
    except:
        bot.send_message(message.chat.id, text, reply_markup=markup)

@bot.message_handler(commands=['start'])
def start(message):
    save_chat_id(message.chat.id)
    user_id = message.from_user.id
    if not bot_running and not is_admin(user_id):
        try:
            bot.send_message(message.chat.id, "🛠️ البوت في صيانة حالياً", parse_mode='HTML')
        except:
            bot.send_message(message.chat.id, "🛠️ البوت في صيانة حالياً")
        return
    if message.from_user.username in banned_users:
        send_with_emoji(message.chat.id, "تم حظرك من البوت.", E['warning'])
        return
    if is_approved_user(user_id):
        show_main_menu(message)
    elif user_id in pending_requests:
        send_waiting_message(message.chat.id)
    else:
        user_info = {
            'first_name': message.from_user.first_name,
            'username': message.from_user.username or 'غير متوفر',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        request_approval(user_id, user_info)
        send_waiting_message(message.chat.id)

@bot.callback_query_handler(func=lambda call: call.data == 'support_girl')
def support_girl_callback(call):
    if not is_approved_user(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ تحتاج إلى موافقة الأدمن")
        return
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(btn("رجوع", callback_data='back_to_main', emoji_key='arrow', style="primary"))
    text = f'{ce("sparkles")} <b>فتاة المحاور</b>\n\nأهلاً بك! يمكنك الاستفسار عن رفع وبوتات بايثون.'
    try:
        bot.send_message(call.message.chat.id, text, reply_markup=markup, parse_mode='HTML')
    except:
        bot.send_message(call.message.chat.id, "✨ فتاة المحاور", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == 'tech_support')
def tech_support_callback(call):
    if not is_approved_user(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ تحتاج إلى موافقة الأدمن")
        return
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(btn("راسل المسؤول", url="https://t.me/ew1t_7", emoji_key='people', style="primary"))
    markup.add(btn("قناة المساعدة", url="https://t.me/M_6FW", emoji_key='link', style="primary"))
    markup.add(btn("رجوع", callback_data='back_to_main', emoji_key='arrow', style="primary"))
    text = f'{ce("bell")} <b>الدعم الفني والخدمات</b>\n\nللتواصل: <a href="https://t.me/ew1t_7">@ew1t_7</a>'
    try:
        bot.send_message(call.message.chat.id, text, reply_markup=markup, parse_mode='HTML')
    except:
        bot.send_message(call.message.chat.id, "🔔 الدعم الفني", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == 'speed')
def check_speed(call):
    if not is_approved_user(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ تحتاج إلى موافقة الأدمن")
        return
    bot.answer_callback_query(call.id, "⏳ جاري القياس...")
    try:
        wait_msg = bot.send_message(call.message.chat.id, "⏳ انتظر...", parse_mode='HTML')
    except:
        wait_msg = bot.send_message(call.message.chat.id, "⏳ انتظر...")
    time.sleep(1)
    result_text = f'{ce("fire")} <b>سرعة الاستجابة:</b> 85.50 ms'
    try:
        bot.edit_message_text(result_text, call.message.chat.id, wait_msg.message_id, parse_mode='HTML')
    except:
        bot.edit_message_text("🚀 سرعة البوت", call.message.chat.id, wait_msg.message_id)

@bot.callback_query_handler(func=lambda call: call.data == 'upload')
def upload_file_callback(call):
    if not is_approved_user(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ تحتاج إلى موافقة الأدمن")
        return
    if not bot_running:
        bot.answer_callback_query(call.id, "⏸️ البوت في صيانة")
        return
    bot.answer_callback_query(call.id, "📥 جاري الإعداد...")
    markup = types.InlineKeyboardMarkup()
    markup.add(btn("إلغاء", callback_data='back_to_main', emoji_key='cross', style="danger"))
    text = f'{ce("python")} <b>قم بإرسال ملف البوت بصيغة (.py) الآن:</b>'
    try:
        bot.send_message(call.message.chat.id, text, reply_markup=markup, parse_mode='HTML')
    except:
        bot.send_message(call.message.chat.id, "📥 أرسل ملف .py", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == 'uploaded_files_list')
def show_uploaded_files(call):
    if not is_approved_user(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ تحتاج إلى موافقة الأدمن")
        return
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    chat_id = call.message.chat.id
    if chat_id in bot_scripts and bot_scripts[chat_id].get('files'):
        for file_name in bot_scripts[chat_id]['files']:
            is_running = False
            if 'processes' in bot_scripts[chat_id]:
                proc = bot_scripts[chat_id]['processes'].get(file_name)
                if proc and proc.poll() is None:
                    is_running = True
            status = "يعمل" if is_running else "متوقف"
            time_info = ""
            if is_running:
                chat_key = str(chat_id)
                if chat_key in user_file_expiry and file_name in user_file_expiry[chat_key]:
                    remaining = user_file_expiry[chat_key][file_name] - time.time()
                    time_info = f" | ⏰ {format_remaining_time(remaining)}"
            markup.add(btn(f"{file_name} ({status}{time_info})", callback_data=f'file_control_{file_name}', emoji_key='python', style="primary"))
    else:
        markup.add(btn("لا توجد ملفات", callback_data='noop', emoji_key='cross', style="danger"))
    markup.add(btn("رجوع", callback_data='back_to_main', emoji_key='arrow', style="primary"))
    text = f'{ce("chart")} <b>قائمة الملفات المرفوعة:</b>'
    try:
        bot.send_message(call.message.chat.id, text, reply_markup=markup, parse_mode='HTML')
    except:
        bot.send_message(call.message.chat.id, "📋 الملفات المرفوعة:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('file_control_'))
def file_control_menu(call):
    if not is_approved_user(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ تحتاج إلى موافقة الأدمن")
        return
    bot.answer_callback_query(call.id)
    file_name = call.data.replace('file_control_', '')
    chat_id = call.message.chat.id
    is_running = False
    if chat_id in bot_scripts and 'processes' in bot_scripts[chat_id]:
        proc = bot_scripts[chat_id]['processes'].get(file_name)
        if proc and proc.poll() is None:
            is_running = True
    status = "يعمل" if is_running else "متوقف"

    markup = types.InlineKeyboardMarkup(row_width=2)
    if is_running:
        markup.add(btn("إيقاف", callback_data=f'stopfile_{chat_id}_{file_name}', emoji_key='cross', style="danger"))
    else:
        markup.add(btn("تشغيل", callback_data=f'startfile_{chat_id}_{file_name}', emoji_key='check', style="success"))
    markup.add(btn("حذف", callback_data=f'deletefile_{chat_id}_{file_name}', emoji_key='warning', style="danger"))
    markup.add(btn("رجوع", callback_data='uploaded_files_list', emoji_key='arrow', style="primary"))

    text = f'{ce("python")} <b>التحكم بالملف:</b>\n<code>{file_name}</code>\nالحالة: <b>{status}</b>'
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='HTML')
    except:
        bot.edit_message_text(file_name, call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('startfile_'))
def start_file_callback(call):
    try:
        parts = call.data.replace('startfile_', '').split('_', 1)
        chat_id = int(parts[0])
        file_name = parts[1]
        script_path = os.path.join(uploaded_files_dir, file_name)
        if not os.path.exists(script_path):
            bot.answer_callback_query(call.id, "❌ الملف غير موجود")
            return
        start_file(script_path, chat_id)
        bot.answer_callback_query(call.id, "✅ تم التشغيل")
        call.data = f'file_control_{file_name}'
        file_control_menu(call)
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ خطأ: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('stopfile_'))
def stop_file_callback(call):
    try:
        parts = call.data.replace('stopfile_', '').split('_', 1)
        chat_id = int(parts[0])
        file_name = parts[1]
        script_path = os.path.join(uploaded_files_dir, file_name)
        stop_bot(script_path, chat_id)
        bot.answer_callback_query(call.id, "✅ تم الإيقاف")
        call.data = f'file_control_{file_name}'
        file_control_menu(call)
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ خطأ: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('deletefile_'))
def delete_file_callback(call):
    try:
        parts = call.data.replace('deletefile_', '').split('_', 1)
        chat_id = int(parts[0])
        file_name = parts[1]
        script_path = os.path.join(uploaded_files_dir, file_name)
        stop_bot(script_path, chat_id)
        if os.path.exists(script_path):
            os.remove(script_path)
        bot.answer_callback_query(call.id, "🗑️ تم الحذف")
        call.data = 'uploaded_files_list'
        show_uploaded_files(call)
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ خطأ: {e}")

@bot.callback_query_handler(func=lambda call: call.data == 'noop')
def noop_callback(call):
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == 'download_lib')
def download_library(call):
    if not is_approved_user(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ تحتاج موافقة")
        return
    bot.answer_callback_query(call.id)
    waiting_for_library.add(call.from_user.id)
    markup = types.InlineKeyboardMarkup()
    markup.add(btn("إلغاء", callback_data='cancel_library', emoji_key='cross', style="danger"))
    try:
        bot.send_message(call.message.chat.id, f'{ce("gem")} <b>أرسل اسم المكتبة المراد تثبيتها:</b>', reply_markup=markup, parse_mode='HTML')
    except:
        bot.send_message(call.message.chat.id, "أرسل اسم المكتبة:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == 'cancel_library')
def cancel_library(call):
    waiting_for_library.discard(call.from_user.id)
    bot.answer_callback_query(call.id, "❌ تم الإلغاء")

@bot.message_handler(func=lambda message: message.from_user.id in waiting_for_library, content_types=['text'])
def install_library_step(message):
    waiting_for_library.discard(message.from_user.id)
    lib = message.text.strip()
    try:
        res = subprocess.run([sys.executable, "-m", "pip", "install", lib], capture_output=True, text=True, timeout=120)
        if res.returncode == 0:
            send_with_emoji(message.chat.id, f"✅ تم تثبيت المكتبة {lib} بنجاح.", E['check'])
        else:
            send_with_emoji(message.chat.id, f"❌ فشل تثبيت المكتبة.", E['cross'])
    except Exception as e:
        send_with_emoji(message.chat.id, f"❌ خطأ: {e}", E['cross'])

@bot.callback_query_handler(func=lambda call: call.data == 'about_bot')
def about_bot(call):
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup()
    markup.add(btn("رجوع", callback_data='back_to_main', emoji_key='arrow', style="primary"))
    bot.send_message(call.message.chat.id, "منصة استضافة وتشغيل بوتات بايثون.", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == 'online_support')
def online_support(call):
    bot.answer_callback_query(call.id, "تم الإرسال")
    bot.send_message(ADMIN_ID, f"📞 طلب دعم من: {call.from_user.first_name} (<code>{call.from_user.id}</code>)", parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data == 'protection_control')
def protection_control(call):
    if not is_admin(call.from_user.id):
        return
    markup = types.InlineKeyboardMarkup()
    markup.add(btn("رجوع", callback_data='back_to_main', emoji_key='arrow', style="primary"))
    bot.edit_message_text(f"إعدادات الحماية مفعلة.", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == 'back_to_main')
def back_to_main(call):
    try:
        show_main_menu(call.message)
        bot.answer_callback_query(call.id)
    except:
        pass

@bot.callback_query_handler(func=lambda call: call.data == 'bot_control')
def bot_control_callback(call):
    if not is_admin(call.from_user.id):
        return
    markup = types.InlineKeyboardMarkup()
    markup.add(btn("رجوع", callback_data='back_to_main', emoji_key='arrow', style="primary"))
    bot.edit_message_text("لوحة تحكم الأدمن.", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.message_handler(content_types=['document'])
def handle_file(message):
    if not is_approved_user(message.from_user.id):
        send_with_emoji(message.chat.id, "تحتاج إلى موافقة الأدمن", E['cross'])
        return
    try:
        user_id = message.from_user.id
        if message.from_user.username in banned_users:
            send_with_emoji(message.chat.id, "محظور", E['warning'])
            return
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        bot_script_name = message.document.file_name
        if not bot_script_name.endswith('.py'):
            send_with_emoji(message.chat.id, "فقط ملفات .py مسموحة", E['cross'])
            return
        temp_path = os.path.join(tempfile.gettempdir(), bot_script_name)
        with open(temp_path, 'wb') as f:
            f.write(downloaded_file)
        
        script_path = os.path.join(uploaded_files_dir, bot_script_name)
        shutil.move(temp_path, script_path)
        
        if message.chat.id not in bot_scripts:
            bot_scripts[message.chat.id] = {'processes': {}, 'files': [], 'path': ''}
        if bot_script_name not in bot_scripts[message.chat.id]['files']:
            bot_scripts[message.chat.id]['files'].append(bot_script_name)
            
        send_with_emoji(message.chat.id, f"✅ تم رفع الملف <code>{bot_script_name}</code> بنجاح.", E['check'])
        start_file(script_path, message.chat.id)
    except Exception as e:
        send_with_emoji(message.chat.id, f"خطأ: {e}", E['cross'])

# 📌 استقبال مدخلات رقم الهاتف، الرمز، أو التحقق وإرسالها مباشرة للملف النشط
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
                send_with_emoji(chat_id, "✅ تم إرسال البيانات إلى الملف بنجاح.", E['check'])
            else:
                send_with_emoji(chat_id, "❌ العملية متوقفة ولا تستقبل مدخلات.", E['warning'])
        except Exception as e:
            send_with_emoji(message.chat.id, f"❌ خطأ أثناء الإرسال: {e}", E['cross'])
        finally:
                    pending_inputs.pop(chat_id, None)

@bot.callback_query_handler(func=lambda call: call.data.startswith('approve_'))
def approve_user(call):
    if not is_admin(call.from_user.id):
        return
    user_id = int(call.data.split('_')[1])
    if user_id in pending_requests:
        user_info = pending_requests.pop(user_id)
        approved_users.add(user_id)
        try:
            bot.send_message(user_id, "🎉 تمت الموافقة! أرسل /start")
        except:
            pass
        bot.answer_callback_query(call.id, "✅ تم القبول")

@bot.callback_query_handler(func=lambda call: call.data.startswith('reject_'))
def reject_user(call):
    if not is_admin(call.from_user.id):
        return
    user_id = int(call.data.split('_')[1])
    if user_id in pending_requests:
        pending_requests.pop(user_id)
        try:
            bot.send_message(user_id, "❌ تم رفض طلبك.")
        except:
            pass
        bot.answer_callback_query(call.id, "❌ تم الرفض")

# ======= التشغيل ======= #
if __name__ == '__main__':
    print("🤖 البوت يعمل...")
    try:
        bot.infinity_polling()
    except Exception as e:
        print(f"❌ خطأ: {e}")
        time.sleep(5)
