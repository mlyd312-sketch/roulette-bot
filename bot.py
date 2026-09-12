import os
import subprocess
import threading
from telebot import TeleBot

# ضع الرمز الخاص ببوتك هنا أو استخدم المتغير الحالي لديك
TOKEN = 'YOUR_BOT_TOKEN'
bot = TeleBot(TOKEN)

# قاموس لتتبع العمليات والمدخلات المعلقة لكل مستخدم
pending_inputs = {}

# قاموس الوجوه التعبيرية (لتجنب أي خطأ في نقص المتغيرات)
E = {
    'check': '🟢',
    'cross': '🔴',
    'gear': '⚙️'
}

def send_with_emoji(chat_id, text, emoji=""):
    bot.send_message(chat_id, f"{emoji} {text}".strip())

def monitor_process(process, chat_id):
    """مراقبة المخرجات قراءةً وكتابةً لمنع تعليق العملية"""
    try:
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                cleaned_output = output.strip()
                # يمكنك إرسال المخرجات للمستخدم إذا رغبت بذلك لتتبع الحالة
                print(f"[Process {chat_id}]: {cleaned_output}")
    except Exception as e:
        print(f"Monitoring error for {chat_id}: {e}")
    finally:
        # تنظيف القاموس عند انتهاء العملية
        pending_inputs.pop(chat_id, None)

@bot.message_handler(commands=['run'])
def start_process(message):
    chat_id = message.chat.id
    
    # التأكد من عدم وجود عملية تعمل بالفعل لنفس المستخدم
    if chat_id in pending_inputs:
        send_with_emoji(chat_id, "لديك عملية قائمة بالفعل، يرجى إكمالها أو انتظار انتهائها.", E['cross'])
        return

    try:
        # تشغيل الملف أو السكريبت الخارجي مع إتاحة التفاعل عبر stdin
        # استبدل 'script.py' باسم الملف الذي تريد تشغيله
        proc = subprocess.Popen(
            ['python', 'script.py'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding='utf-8'
        )

        # حفظ العملية في القاموس بانتظار الإدخال التالي (مثل رقم الهاتف أو الرمز)
        pending_inputs[chat_id] = {
            'process': proc
        }

        # بدء خيط لمراقبة مخرجات العملية في الخلفية
        threading.Thread(target=monitor_process, args=(proc, chat_id), daemon=True).start()

        send_with_emoji(chat_id, "✅ تم بدء العملية بنجاح. يرجى إرسال المطلوب (مثل رقم الهاتف أو الرمز):", E['check'])

    except Exception as e:
        send_with_emoji(chat_id, f"❌ حدث خطأ أثناء تشغيل العملية: {e}", E['cross'])


@bot.message_handler(func=lambda message: message.chat.id in pending_inputs, content_types=['text'])
def handle_subprocess_inputs(message):
    chat_id = message.chat.id
    user_input = message.text.strip()
    data = pending_inputs.get(chat_id)
    
    if data:
        proc = data['process']
        try:
            if proc.poll() is None:
                # كتابة البيانات وإرسالها فوراً للعملية عبر stdin دون إغلاق المجرى
                proc.stdin.write(user_input + '\n')
                proc.stdin.flush()
                send_with_emoji(chat_id, "✅ تم إرسال الرمز/الرقم بنجاح، جاري التحقق...", E['check'])
            else:
                send_with_emoji(chat_id, "❌ العملية توقفت أو انتهت بالفعل.", E['cross'])
                pending_inputs.pop(chat_id, None)
        except Exception as e:
            send_with_emoji(chat_id, f"❌ خطأ في الإرسال: {e}", E['cross'])
            pending_inputs.pop(chat_id, None)

# تشغيل البوت
if __name__ == '__main__':
    print("Bot is running...")
    bot.infinity_polling()
