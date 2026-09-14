import os
import sys
import time
import subprocess
import threading
import logging
import telebot
from telebot import types
import html

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
# active_processes: { (chat_id, file_id): subprocess.Popen }
active_processes = {}
# pending_inputs: { chat_id: file_id }
pending_inputs = {}

def eh(text):
    """تجهيز النص للعرض في تليجرام باستخدام HTML"""
    return html.escape(str(text))

# ============================================================
# كلمات مفتاحية مخصصة للتحقق من طلبات الإدخال (الأرقام والرموز)
# ============================================================
INPUT_KEYWORDS = [
    'أرسل', 'ارسل', 'ادخل', 'أدخل', 'اكتب', 'رقم الهاتف', 'كود التحقق',
    'enter phone', 'enter code', 'enter otp', 'enter password', 'enter 2fa',
    'التحقق بخطوتين', 'أدخل الرقم', 'أدخل الكود', 'input phone', 'phone number',
    'passcode', 'verification code', 'login code'
]

def looks_prompt(text):
    """فحص ما إذا كان السطر المطبوع عبارة عن طلب إدخال حقيقي"""
    if not text or len(text.strip()) < 3:
        return False
    t = text.lower()
    # استثناء أسطر الأخطاء البرمجية حتى لا تُعتبر طلب إدخال
    if any(err in t for err in ['traceback', 'exception', 'error', 'failed', 'connection', 'telebot', 'pyrogram']):
        return False
    return any(kw.lower() in t for kw in INPUT_KEYWORDS)

# ============================================================
# دالة مراقبة ومتابعة مخرجات الملفات ولوحة الإدخال
# ============================================================
def monitor_output(chat_id, file_id, process):
    """مراقبة مخرجات الملف وإظهار لوحة طلب الإدخال فور طلب السكربت رقم أو كود"""
    buffer = ""
    shown_lines = 0
    MAX_SHOWN = 50
    pending_batch = []
    last_flush = time.time()

    def flush_batch():
        nonlocal pending_batch, last_flush
        if not pending_batch:
            return
        text = "\n".join(pending_batch[:40])
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

                if pending_batch and (time.time() - last_flush) > 3.0:
                    flush_batch()
                time.sleep(0.05)
                continue

            try:
                decoded = ch.decode('utf-8', errors='replace')
            except Exception:
                continue

            buffer += decoded

            # فحص الأسطر المطبوعة
            if '\n' in decoded or any(symbol in buffer for symbol in [':', '?', '>']):
                line = buffer.strip()
                
                if not line:
                    continue

                # لوحة استقبال طلبات الإدخال (الأرقام والرموز)
                if looks_prompt(line):
                    if pending_inputs.get(chat_id) != file_id:
                        flush_batch()
                        pending_inputs[chat_id] = file_id
                        buffer = ""  # تصفير الموقت لمنع التكرار
                        
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
                    if '\n' in decoded:
                        buffer = ""
                        if shown_lines < MAX_SHOWN:
                            pending_batch.append(line)
                            shown_lines += 1

                        if (time.time() - last_flush) > 3.0 or len(pending_batch) >= 20:
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

        # تشغيل الملف مع تفعيل النمط اللحظي للـ stdout
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
    logging.info("Bot is running...")
    bot.infinity_polling()
