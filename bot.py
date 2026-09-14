import os
import sys
import time
import subprocess
import threading
import logging
import html
import telebot
from telebot import types

# إعداد التسجيل (Logging)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ============================================================
# بيانات البوت والمطور والقناة
# ============================================================
API_TOKEN = '8877293036:AAGg_82F0bT1Bhov42sk9qDcRMsVNpfnErw'
DEV_USERNAME = '@u_8_y'
CHANNEL_USERNAME = '@FD_CQ'

bot = telebot.TeleBot(API_TOKEN)

# تتبع العمليات الشغالة والإدخالات المعلقة
active_processes = {}  # { (chat_id, file_id): subprocess.Popen }
pending_inputs = {}    # { chat_id: file_id }

def eh(text):
    """تجهيز النص للعرض في تليجرام باستخدام HTML"""
    return html.escape(str(text))

# ============================================================
# كلمات مفتاحية دقيقة لطلبات الإدخال (تمت تصفياتها لمنع التكرار)
# ============================================================
INPUT_KEYWORDS = [
    'أرسل', 'ارسل', 'ادخل', 'أدخل', 'اكتب', 'رقم الهاتف', 'كود التحقق',
    'enter phone', 'enter code', 'enter otp', 'enter password', 'enter 2fa',
    'التحقق بخطوتين', 'أدخل الرقم', 'أدخل الكود', 'input phone', 'phone number',
    'passcode', 'verification code', 'login code'
]

def looks_prompt(text):
    """فحص السطر والتأكد التام أنه ليس رسالة خطأ برمجية أو خطأ شبكة"""
    if not text or len(text.strip()) < 4:
        return False
    t = text.lower()
    
    # قائمة الأخطاء الشائعة التي يجب تجاهلها تماماً وعدم اعتبارها طلب إدخال
    ignore_errors = [
        'traceback', 'exception', 'error', 'failed', 'connection', 
        'telebot', 'pyrogram', 'telegram api', 'unsuccessful', 
        'connection reset', 'aborted', 'requests', 'urllib3',
        'sql', 'sqlite', 'database', 'invalid token', 'unauthorized'
    ]
    if any(err in t for err in ignore_errors):
        return False
        
    return any(kw.lower() in t for kw in INPUT_KEYWORDS)

# ============================================================
# دالة مراقبة ومتابعة مخرجات الملفات مع مانع التكرار
# ============================================================
def monitor_output(chat_id, file_id, process):
    """مراقبة مخرجات الملف وإرسال اللوحة مرة واحدة فقط عند طلب السكربت كود أو رقم"""
    buffer = ""
    shown_lines = 0
    MAX_SHOWN = 50
    pending_batch = []
    last_flush = time.time()
    prompt_sent = False  # قفل لمنع تكرار لوحة الإدخال لنفس السكربت

    def flush_batch():
        nonlocal pending_batch, last_flush
        if not pending_batch:
            return
        text = "\n".join(pending_batch[:30])
        pending_batch = []
        try:
            bot.send_message(
                chat_id,
                f"📄 <b>إخراج الملف:</b>\n<pre>{eh(text[:3500])}</pre>",
                parse_mode='HTML'
            )
        except Exception as e:
            logging.error(f"send output error: {e}")
        last_flush = time.time()

    try:
        while True:
            try:
                ch = process.stdout.read(1)
            except Exception as e:
                logging.error(f"read error [{chat_id}/{file_id}]: {e}")
                break

            if not ch:
                if process.poll() is not None:
                    remaining = buffer.strip()
                    if remaining:
                        pending_batch.append(remaining)
                    flush_batch()

                    exit_code = process.poll()
                    status_icon = "✅" if exit_code == 0 else "❌"
                    status_text = "انتهى بنجاح" if exit_code == 0 else f"توقف بكود خطأ: {exit_code}"

                    try:
                        bot.send_message(
                            chat_id,
                            f"{status_icon} <b>الملف {status_text}</b>\n"
                            f"🆔 المعرف: <code>{file_id}</code>\n"
                            f"📊 عدد الأسطر المعروضة: {shown_lines}\n\n"
                            f"📢 القناة: {CHANNEL_USERNAME} | 👨‍💻 المطور: {DEV_USERNAME}",
                            parse_mode='HTML'
                        )
                    except Exception:
                        pass
                    break

                if pending_batch and (time.time() - last_flush) > 4.0:
                    flush_batch()
                time.sleep(0.05)
                continue

            try:
                decoded = ch.decode('utf-8', errors='replace')
            except Exception:
                continue

            buffer += decoded

            # الاعتماد حصراً على أسطر مكتملة فقط لتفادي التقطيع والتكرار
            if '\n' in decoded:
                line = buffer.strip()
                buffer = ""

                if not line:
                    continue

                # التثبت من طلب الإدخال ومنع التكرار نهائياً بواسطة قفل prompt_sent
                if looks_prompt(line):
                    if not prompt_sent and pending_inputs.get(chat_id) != file_id:
                        flush_batch()
                        pending_inputs[chat_id] = file_id
                        prompt_sent = True  # تفعيل القفل
                        
                        markup = types.InlineKeyboardMarkup()
                        markup.add(types.InlineKeyboardButton("❌ إلغاء الإدخال", callback_data=f'ci_{file_id}'))
                        markup.add(types.InlineKeyboardButton("📢 القناة الرسمية", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}"))

                        try:
                            bot.send_message(
                                chat_id,
                                f"🔐 <b>الملف يطلب إدخال بيانات (رقم/كود/رمز):</b>\n\n"
                                f"<code>{eh(line[:800])}</code>\n\n"
                                f"✍️ <b>أرسل المطلوب الآن في المحادثة مباشرة:</b>",
                                reply_markup=markup,
                                parse_mode='HTML'
                            )
                        except Exception as e:
                            logging.error(f"send prompt error: {e}")
                else:
                    if shown_lines < MAX_SHOWN:
                        pending_batch.append(line)
                        shown_lines += 1

                    # رفع مهلة التجميع إلى 4 ثوانٍ أو 25 سطر لمنع غرق الدردشة بالرسائل
                    if (time.time() - last_flush) > 4.0 or len(pending_batch) >= 25:
                        flush_batch()

    except Exception as e:
        logging.error(f"monitor error [{chat_id}/{file_id}]: {e}")
    finally:
        active_processes.pop((chat_id, file_id), None)
        if pending_inputs.get(chat_id) == file_id:
            pending_inputs.pop(chat_id, None)

# ============================================================
# أوامر البوت والتفاعل
# ============================================================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("👨‍💻 المطور", url=f"https://t.me/{DEV_USERNAME.replace('@', '')}"),
        types.InlineKeyboardButton("📢 القناة", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}")
    )
    
    bot.reply_to(
        message,
        f"👋 **أهلاً بك في بوت استضافة وتشغيل السكربتات**\n\n"
        f"🚀 أرسل لي أي ملف بصيغة `.py` لتشغيله مباشرة.\n"
        f"🔑 البوت يدعم استقبال الأرقام والأكواد عند طلب السكربت لها.\n\n"
        f"👨‍💻 المطور: {DEV_USERNAME}\n"
        f"📢 القناة: {CHANNEL_USERNAME}",
        reply_markup=markup,
        parse_mode='Markdown'
    )

@bot.message_handler(content_types=['document'])
def handle_document(message):
    if not message.document.file_name.endswith('.py'):
        bot.reply_to(message, "⚠️ يرجى إرسال ملف برمجي بصيغة `.py` فقط.")
        return

    chat_id = message.chat.id
    file_id = message.document.file_id[:8]
    file_path = f"./script_{chat_id}_{file_id}.py"

    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        with open(file_path, 'wb') as new_file:
            new_file.write(downloaded_file)

        proc = subprocess.Popen(
            [sys.executable, '-u', file_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1
        )

        active_processes[(chat_id, file_id)] = proc

        t = threading.Thread(
            target=monitor_output,
            args=(chat_id, file_id, proc),
            daemon=True
        )
        t.start()

        bot.reply_to(
            message,
            f"🚀 **تم بدء تشغيل السكربت بنجاح**\n🆔 المعرف: `file_{file_id}`\n\n"
            f"📢 تابع القناة: {CHANNEL_USERNAME}",
            parse_mode='Markdown'
        )
    except Exception as e:
        bot.reply_to(message, f"❌ حدث خطأ أثناء بدء التشغيل:\n`{e}`", parse_mode='Markdown')

# استقبال رد الأرقام والأكواد وتحويلها للسكربت
@bot.message_handler(func=lambda m: m.chat.id in pending_inputs)
def handle_user_input(message):
    chat_id = message.chat.id
    file_id = pending_inputs.get(chat_id)

    if not file_id:
        return

    proc = active_processes.get((chat_id, file_id))
    if proc and proc.poll() is None:
        try:
            inp_text = message.text.strip() + "\n"
            proc.stdin.write(inp_text.encode('utf-8'))
            proc.stdin.flush()
            pending_inputs.pop(chat_id, None)
            bot.reply_to(message, "✅ **تم إرسال الإدخال/الكود إلى السكربت بنجاح.**", parse_mode='Markdown')
        except Exception as e:
            bot.reply_to(message, f"❌ فشل إرسال الإدخال للسكربت: {e}")
    else:
        pending_inputs.pop(chat_id, None)
        bot.reply_to(message, "⚠️ السكربت توقف عن العمل أو غير متاح حالياً.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('ci_'))
def cancel_input(call):
    chat_id = call.message.chat.id
    file_id = call.data.split('_')[1]
    
    if pending_inputs.get(chat_id) == file_id:
        pending_inputs.pop(chat_id, None)
        bot.answer_callback_query(call.id, "تم إلغاء طلب الإدخال.")
        bot.edit_message_text(
            "❌ **تم إلغاء طلب الإدخال.**",
            chat_id,
            call.message.message_id,
            parse_mode='Markdown'
        )

if __name__ == '__main__':
    logging.info("Bot starting up...")
    try:
        bot.remove_webhook()
    except Exception:
        pass
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
