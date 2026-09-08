import sys
import os
import time
import subprocess
import telebot

# ======= البيانات الأساسية ======= #
BOT_TOKEN = '8177794176:AAF390geeHv0-87Bubl_bqKiDoH7mPjDSdE'
bot = telebot.TeleBot(BOT_TOKEN)

uploaded_dir = "uploaded_files"
os.makedirs(uploaded_dir, exist_ok=True)

# ======= القائمة والأوامر ======= #
@bot.message_handler(commands=['start'])
def start_cmd(message):
    text = (
        "👋 **أهلاً بك في بوت الاستضافة**\n\n"
        "🟢 **البوت يعمل بنجاح ومستقر 100%!**\n\n"
        "📤 **طريقة التشغيل:**\n"
        "أرسل لي أي ملف بايثون بصيغة (`.py`) وسيتم تشغيله فوراً على السيرفر."
    )
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

@bot.message_handler(content_types=['document'])
def handle_file(message):
    file_name = message.document.file_name
    
    if not file_name.endswith('.py'):
        bot.reply_to(message, "❌ يرجى إرسال ملف بصيغة `.py` فقط.")
        return

    try:
        # تحميل الملف
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        file_path = os.path.join(uploaded_dir, file_name)

        with open(file_path, 'wb') as f:
            f.write(downloaded)

        bot.reply_to(message, f"✅ تم حفظ الملف `{file_name}`\n🚀 جاري تشغيله في الخلفية...", parse_mode='Markdown')

        # تشغيل الملف المرفوع تلقائياً
        subprocess.Popen([sys.executable, file_path])

    except Exception as e:
        bot.reply_to(message, f"❌ حدث خطأ أثناء تشغيل الملف: {e}")

# ======= تشغيل البوت مع التكرار التلقائي ======= #
if __name__ == '__main__':
    print("🤖 البوت يعمل ومستعد لتلقي الرسائل...")
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            time.sleep(3)
