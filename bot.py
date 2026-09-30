# -*- coding: utf-8 -*-
"""بوت استضافة وتشغيل ملفات Python - bot.py"""
import os, sys, ast, re, time, signal, sqlite3, shutil, subprocess, threading, traceback, importlib.util, platform
from pathlib import Path

# ---------------- إعدادات ----------------
BOT_TOKEN = "8809964582:AAGRNVCAsoQLRa9HfBCdumxPr07HDqE78rc"
ADMIN_ID = int(os.getenv("ADMIN_ID", "1920665874"))
YOUR_USERNAME = os.getenv("YOUR_USERNAME", "@u_8_y")
ADMIN_CHANNEL = os.getenv("ADMIN_CHANNEL", "@FD_CQ")
BASE = Path(__file__).resolve().parent
UPLOADS = BASE / "uploaded_files"; LOGS = BASE / "logs"; DB = BASE / "hosting.sqlite3"
UPLOADS.mkdir(exist_ok=True); LOGS.mkdir(exist_ok=True)
MAX_SIZE = 10 * 1024 * 1024

# متطلبات ملف الحماية
PACKAGE_MAP = {
    "pyrogram":"pyrogram", "tgcrypto":"tgcrypto", "redis":"redis", "requests":"requests",
    "httpx":"httpx[http2]", "aiohttp":"aiohttp", "aiofiles":"aiofiles", "pytz":"pytz",
    "pytio":"pytio", "meval":"meval", "psycopg2":"psycopg2-binary", "cpuinfo":"py-cpuinfo",
    "psutil":"psutil", "hijri_converter":"hijri-converter", "speech_recognition":"SpeechRecognition",
    "wget":"wget", "pytube":"pytube", "shazamio":"shazamio", "telegraph":"telegraph",
    "pydub":"pydub", "PIL":"Pillow", "mutagen":"mutagen", "arq":"Python-ARQ",
    "telethon":"Telethon", "cryptg":"cryptg", "telebot":"pyTelegramBotAPI", "opennsfw2":"opennsfw2",
    "numpy":"numpy", "pandas":"pandas", "bs4":"beautifulsoup4", "lxml":"lxml",
    "chardet":"chardet", "qrcode":"qrcode", "cryptography":"cryptography", "pyaes":"pyaes",
    "rsa":"rsa", "dotenv":"python-dotenv", "colorama":"colorama"
}
STDLIB = set(__import__('sys').stdlib_module_names)

# ---------------- سجل الاستضافة ----------------
log_lock = threading.RLock()
def log(text, file="hosting.log"):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {text}\n"
    print(line, end="")
    try:
        with log_lock, open(LOGS/file, "a", encoding="utf-8", errors="replace") as f: f.write(line)
    except Exception: pass

def script_log(uid, name):
    return LOGS / f"{uid}_{Path(name).stem}.log"

def read_log(p, n=7000):
    try: return p.read_text(encoding="utf-8", errors="replace")[-n:]
    except Exception as e: return f"تعذر قراءة السجل: {e}"

# ---------------- قاعدة البيانات ----------------
lock = threading.RLock()
with sqlite3.connect(DB) as c:
    c.execute("CREATE TABLE IF NOT EXISTS approved(user_id INTEGER PRIMARY KEY, at INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS pending(user_id INTEGER PRIMARY KEY, at INTEGER)")

def approved(uid):
    if int(uid)==ADMIN_ID: return True
    with lock, sqlite3.connect(DB) as c: return c.execute("SELECT 1 FROM approved WHERE user_id=?",(int(uid),)).fetchone() is not None

def approve(uid):
    with lock, sqlite3.connect(DB) as c:
        c.execute("INSERT OR REPLACE INTO approved VALUES(?,?)",(int(uid),int(time.time())))
        c.execute("DELETE FROM pending WHERE user_id=?",(int(uid),)); c.commit()

def reject(uid):
    with lock, sqlite3.connect(DB) as c:
        c.execute("DELETE FROM approved WHERE user_id=?",(int(uid),)); c.execute("DELETE FROM pending WHERE user_id=?",(int(uid),)); c.commit()

def pending():
    with lock, sqlite3.connect(DB) as c: return [r[0] for r in c.execute("SELECT user_id FROM pending ORDER BY at")]

def add_pending(uid):
    with lock, sqlite3.connect(DB) as c: c.execute("INSERT OR REPLACE INTO pending VALUES(?,?)",(int(uid),int(time.time()))); c.commit()

# ---------------- الملفات ----------------
def clean_name(name):
    name=os.path.basename(name or "script.py"); name=re.sub(r"[^\w.\- \u0600-\u06ff]", "_", name, flags=re.UNICODE)
    if not name.lower().endswith('.py'): name += '.py'
    return name[:120]

def udir(uid): p=UPLOADS/str(int(uid)); p.mkdir(parents=True,exist_ok=True); return p

def files(uid): return sorted([p.name for p in udir(uid).glob('*.py')])

# ---------------- اكتشاف المتطلبات ----------------
def imports(source):
    out=set()
    try: tree=ast.parse(source)
    except Exception: return out
    for n in ast.walk(tree):
        if isinstance(n,ast.Import): out.update(a.name.split('.')[0] for a in n.names)
        elif isinstance(n,ast.ImportFrom) and n.module: out.add(n.module.split('.')[0])
    return out

def installed(m):
    try: return importlib.util.find_spec(m) is not None
    except Exception: return False

def missing_for(path):
    src=path.read_text(encoding='utf-8',errors='replace'); known=[]; unknown=[]
    for m in sorted(imports(src)):
        if m in STDLIB or installed(m): continue
        if m in PACKAGE_MAP: known.append((m,PACKAGE_MAP[m]))
        elif re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{1,50}',m):
            if not (path.parent/f'{m}.py').exists() and not (path.parent/m).is_dir(): unknown.append(m)
    return known,unknown

install_lock=threading.RLock()
def pip_install(pkg, lp):
    cmd=[sys.executable,'-m','pip','install','--disable-pip-version-check','--no-input',pkg]
    try:
        with install_lock:
            p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',timeout=900)
        out=p.stdout or ''; open(lp,'a',encoding='utf-8').write(f"\n$ {' '.join(cmd)}\n{out}\n[exit={p.returncode}]\n")
        return p.returncode==0
    except Exception as e:
        open(lp,'a',encoding='utf-8').write(f"\n[pip error] {e}\n"); return False

def prepare(path,lp):
    known,unknown=missing_for(path); result=[]
    for m,pkg in known: result.append((m,pkg,pip_install(pkg,lp)))
    for m in unknown: result.append((m,m,pip_install(m,lp)))
    importlib.invalidate_caches(); return result

# ---------------- FFmpeg ----------------
def ffmpeg(): return shutil.which('ffmpeg')
def ensure_ffmpeg(lp):
    if ffmpeg(): return True
    cmds=[]
    if platform.system().lower()=='linux':
        if shutil.which('apt-get') and os.geteuid()==0: cmds.append(['apt-get','update','-y']); cmds.append(['apt-get','install','-y','ffmpeg'])
        elif shutil.which('sudo') and shutil.which('apt-get'): cmds.append(['sudo','-n','apt-get','install','-y','ffmpeg'])
        elif shutil.which('apk') and os.geteuid()==0: cmds.append(['apk','add','ffmpeg'])
    for cmd in cmds:
        try:
            p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=300)
            open(lp,'a',encoding='utf-8').write('\n[ffmpeg]\n'+(p.stdout or ''))
            if ffmpeg(): return True
        except Exception as e: open(lp,'a',encoding='utf-8').write(f'\n[ffmpeg error] {e}\n')
    return bool(ffmpeg())

# ---------------- العمليات ----------------
procs={}; proc_lock=threading.RLock()
def running(p): return p is not None and p.poll() is None

def stop_proc(p):
    if not p: return
    try:
        if p.poll() is None:
            if os.name=='nt': p.terminate()
            else:
                try: os.killpg(os.getpgid(p.pid),signal.SIGTERM)
                except Exception: p.terminate()
            try: p.wait(timeout=8)
            except Exception:
                try: p.kill()
                except Exception: pass
    except Exception: pass

def reader(uid,name,p,lp):
    try:
        for line in iter(p.stdout.readline,''):
            if not line: break
            with open(lp,'a',encoding='utf-8',errors='replace') as f: f.write(line)
    except Exception as e:
        with open(lp,'a',encoding='utf-8') as f: f.write(f'\n[reader error] {e}\n')
    finally:
        rc=p.poll()
        with open(lp,'a',encoding='utf-8') as f: f.write(f'\n[process exit] {rc}\n')
        with proc_lock: procs.pop((uid,name),None)

def start(uid,name):
    name=clean_name(name); path=udir(uid)/name; lp=script_log(uid,name)
    if not path.exists(): return False,'الملف غير موجود.'
    with proc_lock:
        if running(procs.get((uid,name))): return False,'الملف يعمل حالياً.'
    with open(lp,'a',encoding='utf-8') as f: f.write('\n'+'='*60+f'\n[START {time.ctime()}]\n')
    results=prepare(path,lp); ensure_ffmpeg(lp)
    env=os.environ.copy(); env['PYTHONUNBUFFERED']='1'; env['PYTHONIOENCODING']='utf-8'
    try:
        kw=dict(cwd=str(path.parent),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',env=env)
        if os.name!='nt': kw['start_new_session']=True
        p=subprocess.Popen([sys.executable,'-u',str(path)],**kw)
    except Exception as e:
        with open(lp,'a',encoding='utf-8') as f: f.write(traceback.format_exc())
        return False,f'فشل التشغيل: {e}'
    with proc_lock: procs[(uid,name)]=p
    threading.Thread(target=reader,args=(uid,name,p,lp),daemon=True).start()
    time.sleep(.8)
    if p.poll() is not None: return False,'توقف مباشرة بعد التشغيل.\n\n'+read_log(lp,4000)
    return True,'تم تشغيل الملف بنجاح.'

def stop(uid,name):
    name=clean_name(name)
    with proc_lock: p=procs.get((uid,name))
    if not running(p): return False,'الملف غير شغال.'
    stop_proc(p); return True,'تم إيقاف الملف.'

def restart(uid,name): stop(uid,name); time.sleep(.5); return start(uid,name)

def stop_all(uid=None):
    with proc_lock: items=list(procs.items())
    for (u,n),p in items:
        if uid is None or u==uid: stop_proc(p)

# ---------------- تجهيز telebot ----------------
def ensure_telebot():
    try:
        if importlib.util.find_spec('telebot'): return True
    except Exception: pass
    subprocess.check_call([sys.executable,'-m','pip','install','--disable-pip-version-check','--no-input','pyTelegramBotAPI'])
    importlib.invalidate_caches(); return importlib.util.find_spec('telebot') is not None

if not ensure_telebot(): raise RuntimeError('تعذر تثبيت pyTelegramBotAPI')
import telebot
from telebot import types

if not BOT_TOKEN: raise RuntimeError('ضع BOT_TOKEN كمتغير بيئة قبل تشغيل bot.py')
bot=telebot.TeleBot(BOT_TOKEN,parse_mode='HTML',threaded=True,num_threads=12)

# ---------------- الواجهة ----------------
def home_kb(uid):
    rows=[[types.InlineKeyboardButton('📤 رفع ملف',callback_data='upload'),types.InlineKeyboardButton('📂 ملفاتي',callback_data='files')],
          [types.InlineKeyboardButton('▶️ تشغيل',callback_data='pick:start'),types.InlineKeyboardButton('⏹ إيقاف',callback_data='pick:stop')],
          [types.InlineKeyboardButton('🔄 إعادة تشغيل',callback_data='pick:restart'),types.InlineKeyboardButton('📋 السجل',callback_data='pick:log')],
          [types.InlineKeyboardButton('📦 المتطلبات',callback_data='pick:deps'),types.InlineKeyboardButton('🧰 النظام',callback_data='system')]]
    if uid==ADMIN_ID: rows.append([types.InlineKeyboardButton('👥 طلبات الدخول',callback_data='pending'),types.InlineKeyboardButton('🛑 إيقاف الكل',callback_data='allstop')])
    return types.InlineKeyboardMarkup(rows)

def back(): return types.InlineKeyboardMarkup([[types.InlineKeyboardButton('↩️ رجوع',callback_data='home')]])
def pick_kb(uid,action):
    rows=[[types.InlineKeyboardButton(n[:45],callback_data=f'{action}:{n}')] for n in files(uid)]
    rows.append([types.InlineKeyboardButton('↩️ رجوع',callback_data='home')]); return types.InlineKeyboardMarkup(rows)
def home_text(): return '<b>🤖 بوت الاستضافة\n\n📦 تشغيل ملفات Python تلقائياً\n🧰 تثبيت المتطلبات الناقصة\n🎵 دعم FFmpeg\n📋 سجل الأخطاء لكل ملف</b>'

def send_home(chat,uid,msg=None):
    try:
        if msg: bot.edit_message_text(home_text(),chat,msg,reply_markup=home_kb(uid))
        else: bot.send_message(chat,home_text(),reply_markup=home_kb(uid))
    except Exception:
        try: bot.send_message(chat,home_text(),reply_markup=home_kb(uid))
        except Exception: pass

# ---------------- الأوامر ----------------
@bot.message_handler(commands=['start'])
def start_cmd(m):
    uid=m.from_user.id
    if not approved(uid):
        add_pending(uid); bot.reply_to(m,'<b>⏳ تم إرسال طلبك للإدارة للموافقة.</b>')
        try:
            bot.send_message(ADMIN_ID,f'<b>🔔 طلب دخول جديد\nID: <code>{uid}</code>\nيوزر: @{m.from_user.username or "بدون"}</b>',reply_markup=types.InlineKeyboardMarkup([[types.InlineKeyboardButton('✅ قبول',callback_data=f'approve:{uid}'),types.InlineKeyboardButton('❌ رفض',callback_data=f'reject:{uid}')]]))
        except Exception: pass
        return
    send_home(m.chat.id,uid)

@bot.message_handler(commands=['help'])
def help_cmd(m):
    if approved(m.from_user.id): bot.reply_to(m,'<b>/start — لوحة التحكم\n/files — ملفاتك\n/status — حالة الملفات\n/stopall — إيقاف ملفاتك\n/log — آخر سجل\n/cancel — إلغاء</b>')

@bot.message_handler(commands=['cancel'])
def cancel(m): bot.reply_to(m,'<b>تم إلغاء العملية.</b>')

@bot.message_handler(commands=['files'])
def files_cmd(m):
    if not approved(m.from_user.id): return
    fs=files(m.from_user.id); bot.send_message(m.chat.id,'<b>📂 ملفاتك:</b>' if fs else '<b>لا توجد ملفات.</b>',reply_markup=pick_kb(m.from_user.id,'info') if fs else back())

@bot.message_handler(commands=['status'])
def status_cmd(m):
    if not approved(m.from_user.id): return
    lines=['<b>📊 الحالة:</b>']
    with proc_lock:
        for n in files(m.from_user.id): lines.append(f'• <code>{n}</code> — {"🟢 يعمل" if running(procs.get((m.from_user.id,n))) else "🔴 متوقف"}')
    bot.send_message(m.chat.id,'\n'.join(lines),reply_markup=back())

@bot.message_handler(commands=['stopall'])
def stopall_cmd(m):
    if approved(m.from_user.id): stop_all(m.from_user.id); bot.reply_to(m,'<b>⏹ تم إيقاف كل ملفاتك.</b>')

@bot.message_handler(commands=['log'])
def log_cmd(m):
    if not approved(m.from_user.id): return
    fs=files(m.from_user.id)
    if not fs: return bot.reply_to(m,'<b>لا توجد ملفات.</b>')
    n=fs[-1]; bot.reply_to(m,f'<b>📋 {n}</b>\n<pre>{read_log(script_log(m.from_user.id,n),6000)}</pre>')

# ---------------- رفع ----------------
@bot.message_handler(content_types=['document'])
def upload(m):
    uid=m.from_user.id
    if not approved(uid): return
    d=m.document; name=clean_name(d.file_name)
    if not d.file_name.lower().endswith('.py'): return bot.reply_to(m,'<b>⛔ ارفع ملف .py فقط.</b>')
    if d.file_size and d.file_size>MAX_SIZE: return bot.reply_to(m,'<b>⛔ الحد الأقصى 10MB.</b>')
    try:
        f=bot.get_file(d.file_id); data=bot.download_file(f.file_path); (udir(uid)/name).write_bytes(data)
        src=data.decode('utf-8',errors='replace'); ast.parse(src)
    except SyntaxError as e:
        return bot.reply_to(m,f'<b>⚠️ تم الحفظ لكن يوجد SyntaxError في السطر {e.lineno}: {e.msg}</b>')
    except Exception as e:
        return bot.reply_to(m,f'<b>❌ فشل رفع الملف: <code>{e}</code></b>')
    known,unknown=missing_for(udir(uid)/name)
    deps='\n'.join(f'• {a} → {b}' for a,b in known) or '• لا توجد متطلبات معروفة ناقصة.'
    bot.reply_to(m,f'<b>✅ تم رفع <code>{name}</code>\n\n📦 الناقص قبل التشغيل:\n{deps}\n\nسيتم تثبيته تلقائياً عند التشغيل.</b>',reply_markup=types.InlineKeyboardMarkup([[types.InlineKeyboardButton('▶️ تشغيل',callback_data=f'start:{name}'),types.InlineKeyboardButton('📋 السجل',callback_data=f'log:{name}')],[types.InlineKeyboardButton('↩️ الرئيسية',callback_data='home')]]))

# ---------------- callbacks ----------------
@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    uid=c.from_user.id; d=c.data or ''
    try: bot.answer_callback_query(c.id)
    except Exception: pass
    if d.startswith('approve:') or d.startswith('reject:'):
        if uid!=ADMIN_ID: return
        target=int(d.split(':',1)[1])
        if d.startswith('approve:'): approve(target); msg=f'<b>✅ تم قبول <code>{target}</code>.</b>'
        else: reject(target); msg=f'<b>❌ تم رفض <code>{target}</code>.</b>'
        try: bot.edit_message_text(msg,c.message.chat.id,c.message.message_id)
        except Exception: pass
        if d.startswith('approve:'):
            try: bot.send_message(target,'<b>✅ تمت الموافقة. أرسل /start.</b>')
            except Exception: pass
        return
    if not approved(uid): return
    if d=='home': return send_home(c.message.chat.id,uid,c.message.message_id)
    if d=='upload': return bot.send_message(c.message.chat.id,'<b>📤 أرسل ملف .py الآن (حد 10MB).</b>',reply_markup=back())
    if d=='files':
        fs=files(uid); return bot.send_message(c.message.chat.id,'<b>اختر ملفاً:</b>',reply_markup=pick_kb(uid,'info') if fs else back())
    if d.startswith('pick:'):
        a=d.split(':',1)[1]; fs=files(uid)
        return bot.send_message(c.message.chat.id,'<b>اختر الملف:</b>',reply_markup=pick_kb(uid,a) if fs else back())
    if d=='system':
        return bot.send_message(c.message.chat.id,f'<b>🧰 النظام\nPython: <code>{platform.python_version()}</code>\nFFmpeg: <code>{ffmpeg() or "غير موجود"}</code>\nالمنصة: <code>{platform.system()}</code></b>',reply_markup=back())
    if d=='pending' and uid==ADMIN_ID:
        ps=pending()
        if not ps: return bot.send_message(c.message.chat.id,'<b>لا توجد طلبات.</b>',reply_markup=back())
        for x in ps: bot.send_message(c.message.chat.id,f'<b>👤 <code>{x}</code></b>',reply_markup=types.InlineKeyboardMarkup([[types.InlineKeyboardButton('✅ قبول',callback_data=f'approve:{x}'),types.InlineKeyboardButton('❌ رفض',callback_data=f'reject:{x}')]]))
        return
    if d=='allstop' and uid==ADMIN_ID: stop_all(); return bot.send_message(c.message.chat.id,'<b>⏹ تم إيقاف كل العمليات.</b>',reply_markup=back())
    if ':' not in d: return
    action,name=d.split(':',1); name=clean_name(name); path=udir(uid)/name
    if action=='start': ok,msg=start(uid,name)
    elif action=='stop': ok,msg=stop(uid,name)
    elif action=='restart': ok,msg=restart(uid,name)
    elif action=='log': return bot.send_message(c.message.chat.id,f'<b>📋 سجل {name}</b>\n<pre>{read_log(script_log(uid,name),7000)}</pre>',reply_markup=types.InlineKeyboardMarkup([[types.InlineKeyboardButton('🔄 تحديث',callback_data=f'log:{name}')],[types.InlineKeyboardButton('↩️ رجوع',callback_data='home')]]))
    elif action=='deps':
        if not path.exists(): return bot.send_message(c.message.chat.id,'<b>الملف غير موجود.</b>',reply_markup=back())
        k,u=missing_for(path); txt='\n'.join(f'• {a} → {b}' for a,b in k) or '• لا توجد متطلبات معروفة ناقصة.'
        return bot.send_message(c.message.chat.id,f'<b>📦 المتطلبات الناقصة:\n{txt}</b>',reply_markup=back())
    elif action=='info':
        if not path.exists(): return bot.send_message(c.message.chat.id,'<b>الملف غير موجود.</b>',reply_markup=back())
        with proc_lock: state='🟢 يعمل' if running(procs.get((uid,name))) else '🔴 متوقف'
        return bot.send_message(c.message.chat.id,f'<b>📄 <code>{name}</code>\nالحالة: {state}\nالحجم: {path.stat().st_size/1024:.1f}KB</b>',reply_markup=types.InlineKeyboardMarkup([[types.InlineKeyboardButton('▶️ تشغيل',callback_data=f'start:{name}'),types.InlineKeyboardButton('⏹ إيقاف',callback_data=f'stop:{name}')],[types.InlineKeyboardButton('🔄 إعادة',callback_data=f'restart:{name}'),types.InlineKeyboardButton('📋 سجل',callback_data=f'log:{name}')],[types.InlineKeyboardButton('↩️ رجوع',callback_data='home')]]))
    else: return
    bot.send_message(c.message.chat.id,f'<b>{"✅" if ok else "❌"} {msg}</b>',reply_markup=types.InlineKeyboardMarkup([[types.InlineKeyboardButton('📋 السجل',callback_data=f'log:{name}')],[types.InlineKeyboardButton('↩️ الرئيسية',callback_data='home')]]))

# ---------------- تشغيل ----------------
def cleanup():
    try: stop_all()
    except Exception: pass

def main():
    if not BOT_TOKEN: raise RuntimeError('BOT_TOKEN غير موجود')
    try:
        me=bot.get_me(); log(f'تم تشغيل بوت الاستضافة: @{me.username}')
    except Exception as e:
        log(traceback.format_exc(),'hosting_bot_errors.log'); raise RuntimeError(f'فشل الاتصال بتليگرام: {e}')
    while True:
        try: bot.infinity_polling(timeout=30,long_polling_timeout=30,skip_pending=True,allowed_updates=['message','callback_query'])
        except KeyboardInterrupt: break
        except Exception:
            err=traceback.format_exc(); log(err,'hosting_bot_errors.log'); time.sleep(5)

if __name__=='__main__':
    import atexit; atexit.register(cleanup); main()
