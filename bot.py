import sys
import os
import re
import time
import uuid
import sqlite3
import logging
import threading
import subprocess
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import telebot
from telebot import types

# ضبط إعدادات الترميز لضمان عمل النصوص العربية بشكل سليّم
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='ignore')
except Exception:
    pass

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BOT_TOKEN = os.getenv('BOT_TOKEN', '8877293036:AAGg_82F0bT1Bhov42sk9qDcRMsVNpfnErw')
ADMIN_ID = int(os.getenv('ADMIN_ID', '1920665874'))
YOUR_USERNAME = '@u_8_y'
ADMIN_CHANNEL = '@FD_CQ'

BASE_DIR = os.path.abspath(os.getcwd())
UPLOADED_FILES_DIR = os.path.join(BASE_DIR, "uploaded_files")

bot = telebot.TeleBot(BOT_TOKEN)
executor = ThreadPoolExecutor(max_workers=10)
lock = threading.Lock()

active_processes = {}
pending_inputs = {}  # لتتبع الملفات التي تنتظر إدخال (رقم / كود)
waiting_library = set()

os.makedirs(UPLOADED_FILES_DIR, exist_ok=True)

def eh(text):
    if text is None:
        return ""
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

# قاعدة بيانات الاعتماد البسيطة
def init_db():
    with sqlite3.connect('bot_data.db') as conn:
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS approved_users (user_id INTEGER PRIMARY KEY, username TEXT)')
        c.execute('INSERT OR IGNORE INTO approved_users (user_id, username) VALUES (?, ?)', (ADMIN_ID, 'ADMIN'))
        conn.commit()

init_db()

def is_approved(uid):
    if uid == ADMIN_ID:
        return True
    with sqlite3.connect('bot_data.db') as conn:
        c = conn.cursor()
        c.execute('SELECT user_id FROM approved_users WHERE user_id = ?', (uid,))
        return c.fetchone() is not None

# دالة ذكية لفحص إذا كان سطر المخرجات يطلب إدخال (رقم هاتف، كود، تحقق، كلمة مرور)
def is_auth_prompt(line):
    if not line:
        return False
    l = line.lower()
    keywords = [
        'phone', 'number', 'code', 'otp', 'password', 'login', 'auth',
        'الرقم', 'رقم', 'كود', 'رمز', 'تحقق', 'كلمة المرور', 'ادخل', 'أدخل'
    ]
    return any(k in l for k in keywords)

# تشغيل الملف
def start_file(script_path, chat_id, file_id):
    script_path = os.path.abspath(script_path)
    with lock:
        if chat_id not in active_processes:
            active_processes[chat_id] = {}
        
        active_processes[chat_id][file_id] = {
            'name': os.path.basename(script_path),
            'path': script_path,
            'process': None
        }
        info = active_processes[chat_id][file_id]

        try:
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            env['PYTHONIOENCODING'] = 'utf-8'

            p = subprocess.Popen(
                [sys.executable, "-u", script_path],
                cwd=os.path.dirname(script_path),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                start_new_session=True
            )
            info['process'] = p

            # أزرار تحكم ثابتة ونظيفة
            markup = types.InlineKeyboardMarkup(row_width=3)
            markup.add(
                types.InlineKeyboardButton("🛑 إيقاف", callback_data=f'sf_{file_id}'),
                types.InlineKeyboardButton("🔄 إعادة", callback_data=f'rf_{file_id}'),
                types.InlineKeyboardButton("🗑️ حذف", callback_data=f'df_{file_id}')
            )
            markup.add(types.InlineKeyboardButton("📂 ملفاتي النشطة", callback_data='my_files'))

            bot.send_message(
                chat_id,
                f"✅ <b>تم تشغيل الملف بنجاح</b>\n📁 <code>{eh(info['name'])}</code>\n🆔 <code>{file_id}</code>",
                reply_markup=markup,
                parse_mode='HTML'
            )

            # مراقبة المخرجات بصمت لاكتشاف طلبات الأكواد
            threading.Thread(target=monitor_output, args=(chat_id, file_id, p), daemon=True).start()

        except Exception as e:
            bot.send_message(chat_id, f"❌ خطأ في التشغيل: {eh(str(e))}", parse_mode='HTML')

# مراقبة مخرجات السكربت وفتح لوحة تفاعلية فور طلب الرقم/الكود
def monitor_output(chat_id, file_id, process):
    buffer = ""
    try:
        while True:
            ch = process.stdout.read(1)
            if not ch:
                if process.poll() is not None:
                    break
                time.sleep(0.1)
                continue
            
            decoded = ch.decode('utf-8', errors='ignore')
            buffer += decoded

            if '\n' in decoded or len(buffer) > 100:
                line = buffer.strip()
                buffer = ""

                if len(line) > 2 and is_auth_prompt(line):
                    # تسجيل الملف كمحتاج لإدخال
                    pending_inputs[chat_id] = file_id
                    
                    # إنشاء لوحة إدخال تفاعلية (ForceReply) تظهر للمستخدم مباشرة مع الرد
                    markup = types.ForceReply(selective=True)
                    try:
                        bot.send_message(
                            chat_id,
                            f"🔐 <b>الملف يطلب إدخال (رقم / كود / تحقق):</b>\n\n"
                            f"<code>{eh(line[:300])}</code>\n\n"
                            f"👇 <b>قم بالرد على هذه الرسالة واكتب الرقم أو الكود المطلوب:</b>",
                            reply_markup=markup,
                            parse_mode='HTML'
                        )
                    except Exception:
                        pass
    except Exception:
        pass
    finally:
        if pending_inputs.get(chat_id) == file_id:
            pending_inputs.pop(chat_id, None)

@bot.message_handler(commands=['start'])
def cmd_start(message):
    if not is_approved(message.from_user.id):
        bot.send_message(message.chat.id, "❌ غير مصرح لك استخدام البوت.")
        return
    show_menu(message)

def show_menu(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📥 رفع ملف .py", callback_data='upload'),
        types.InlineKeyboardButton("📂 ملفاتي", callback_data='my_files')
    )
    markup.add(types.InlineKeyboardButton("📞 التواصل مع المطور", url=f"https://t.me/{YOUR_USERNAME.replace('@', '')}"))
    
    bot.send_message(
        message.chat.id,
        f"🐍 <b>لوحة استضافة بايثون المتطورة</b>\n\nمرحباً بك! البوت جاهز لإدارة ملفاتك والأكواد والتحقق.\n\nاختر ما تحتاجه:",
        reply_markup=markup,
        parse_mode='HTML'
    )

# استقبال الرد الخاص بطلب الرقم أو الكود وإرساله للملف فوراً وبدقة
@bot.message_handler(func=lambda m: m.chat.id in pending_inputs and m.content_type == 'text' and not m.text.startswith('/'))
def handle_input_response(message):
    chat_id = message.chat.id
    file_id = pending_inputs.get(chat_id)
    if not file_id or chat_id not in active_processes or file_id not in active_processes[chat_id]:
        pending_inputs.pop(chat_id, None)
        return

    proc = active_processes[chat_id][file_id].get('process')
    if not proc or proc.poll() is not None:
        pending_inputs.pop(chat_id, None)
        bot.reply_to(message, "❌ عذراً، الملف متوقف حالياً.")
        return

    user_text = message.text.strip()
    try:
        # إرسال الكود أو الرقم المكتوب إلى مدخلات السكربت مباشرة
        proc.stdin.write((user_text + "\n").encode('utf-8'))
        proc.stdin.flush()
        
        bot.reply_to(message, "✅ تم إرسال الرد (الرقم/الكود) إلى الملف بنجاح!", parse_mode='HTML')
        pending_inputs.pop(chat_id, None)
    except Exception as e:
        bot.reply_to(message, f"❌ فشل إرسال الرد للملف: {eh(str(e))}", parse_mode='HTML')

@bot.message_handler(content_types=['document'])
def handle_document(message):
    uid = message.from_user.id
    if not is_approved(uid):
        return

    doc = message.document
    if not doc.file_name.endswith('.py'):
        bot.reply_to(message, "❌ مسموح برفع ملفات بايثون (.py) فقط.")
        return

    try:
        chat_id = message.chat.id
        file_info = bot.get_file(doc.file_id)
        downloaded = bot.download_file(file_info.file_path)

        file_id = uuid.uuid4().hex[:8]
        user_dir = os.path.join(UPLOADED_FILES_DIR, str(uid))
        os.makedirs(user_dir, exist_ok=True)
        save_path = os.path.abspath(os.path.join(user_dir, f"{file_id}_{doc.file_name}"))

        with open(save_path, 'wb') as f:
            f.write(downloaded)

        start_file(save_path, chat_id, file_id)
    except Exception as e:
        bot.reply_to(message, f"❌ حدث خطأ أثناء الحفظ: {eh(str(e))}")

@bot.callback_query_handler(func=lambda c: c.data.startswith('sf_'))
def cb_stop(call):
    fid = call.data.replace('sf_', '')
    cid = call.message.chat.id
    if cid in active_processes and fid in active_processes[cid]:
        proc = active_processes[cid][fid].get('process')
        if proc:
            try:
                proc.terminate()
            except Exception:
                pass
    bot.answer_callback_query(call.id, "🛑 تم إيقاف الملف")

@bot.callback_query_handler(func=lambda c: c.data.startswith('rf_'))
def cb_restart(call):
    fid = call.data.replace('rf_', '')
    cid = call.message.chat.id
    if cid in active_processes and fid in active_processes[cid]:
        info = active_processes[cid][fid]
        path = info['path']
        proc = info.get('process')
        if proc:
            try:
                proc.terminate()
            except Exception:
                pass
        start_file(path, cid, fid)
    bot.answer_callback_query(call.id, "🔄 تم إعادة التشغيل")

@bot.callback_query_handler(func=lambda c: c.data.startswith('df_'))
def cb_delete(call):
    fid = call.data.replace('df_', '')
    cid = call.message.chat.id
    if cid in active_processes and fid in active_processes[cid]:
        info = active_processes[cid][fid]
        if os.path.exists(info['path']):
            try:
                os.remove(info['path'])
            except Exception:
                pass
        active_processes[cid].pop(fid, None)
    bot.answer_callback_query(call.id, "🗑️ تم حذف الملف نهائياً")

@bot.callback_query_handler(func=lambda c: c.data == 'my_files')
def cb_my_files(call):
    cid = call.message.chat.id
    if cid not in active_processes or not active_processes[cid]:
        bot.answer_callback_query(call.id, "لا توجد ملفات نشطة")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=3)
    for fid, info in active_processes[cid].items():
        markup.row(
            types.InlineKeyboardButton(f"📁 {info['name'][:15]}", callback_data=f'nf_{fid}'),
            types.InlineKeyboardButton("🔄", callback_data=f'rf_{fid}'),
            types.InlineKeyboardButton("🛑", callback_data=f'sf_{fid}'),
            types.InlineKeyboardButton("🗑️", callback_data=f'df_{fid}')
        )
    markup.add(types.InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data='back'))
    bot.edit_message_text("📂 <b>إدارة ملفاتك النشطة:</b>", cid, call.message.message_id, reply_markup=markup, parse_mode='HTML')

@bot.callback_query_handler(func=lambda c: c.data == 'upload')
def cb_upload(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "📥 أرسل ملف البايثون (`.py`) الآن وسأقوم بتشغيله وإدارته فوراً.")

@bot.callback_query_handler(func=lambda c: c.data == 'back')
def cb_back(call):
    bot.answer_callback_query(call.id)
    show_menu(call.message)

if __name__ == '__main__':
    bot.infinity_polling()
