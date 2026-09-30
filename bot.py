# -*- coding: utf-8 -*-
"""بوت استضافة وتشغيل ملفات Python - bot.py"""
import os, sys, ast, re, time, signal, sqlite3, shutil, subprocess, threading, traceback, importlib.util, platform, select
try:
    import pty
    HAVE_PTY = True
except Exception:
    pty = None
    HAVE_PTY = False
from pathlib import Path
# ---------------- إعدادات ----------------
BOT_TOKEN = "8819348912:AAEuppR7MTSl9dfnMbt3sW_bqSuvwDsoVUs"
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
with sqlite3.connect(DB, timeout=5) as c:
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    c.execute("CREATE TABLE IF NOT EXISTS approved(user_id INTEGER PRIMARY KEY, at INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS pending(user_id INTEGER PRIMARY KEY, at INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS active_files(user_id INTEGER NOT NULL, name TEXT NOT NULL, at INTEGER, PRIMARY KEY(user_id,name))")
approved_cache=set()
with sqlite3.connect(DB, timeout=5) as c:
    approved_cache.update(r[0] for r in c.execute("SELECT user_id FROM approved"))
approved_cache.add(ADMIN_ID)
def approved(uid):
    return int(uid) in approved_cache
def approve(uid):
    uid=int(uid)
    with lock, sqlite3.connect(DB, timeout=5) as c:
        c.execute("INSERT OR REPLACE INTO approved VALUES(?,?)",(uid,int(time.time())))
        c.execute("DELETE FROM pending WHERE user_id=?",(uid,)); c.commit()
    approved_cache.add(uid)
def reject(uid):
    uid=int(uid)
    with lock, sqlite3.connect(DB, timeout=5) as c:
        c.execute("DELETE FROM approved WHERE user_id=?",(uid,)); c.execute("DELETE FROM pending WHERE user_id=?",(uid,)); c.commit()
    approved_cache.discard(uid)
def pending():
    with lock, sqlite3.connect(DB) as c: return [r[0] for r in c.execute("SELECT user_id FROM pending ORDER BY at")]
def add_pending(uid):
    with lock, sqlite3.connect(DB) as c: c.execute("INSERT OR REPLACE INTO pending VALUES(?,?)",(int(uid),int(time.time()))); c.commit()
def mark_active(uid,name):
    with lock, sqlite3.connect(DB, timeout=5) as c:
        c.execute("INSERT OR REPLACE INTO active_files VALUES(?,?,?)",(int(uid),clean_name(name),int(time.time()))); c.commit()
def unmark_active(uid,name):
    with lock, sqlite3.connect(DB, timeout=5) as c:
        c.execute("DELETE FROM active_files WHERE user_id=? AND name=?",(int(uid),clean_name(name))); c.commit()
def active_files():
    with lock, sqlite3.connect(DB, timeout=5) as c:
        return [(int(u),n) for u,n in c.execute("SELECT user_id,name FROM active_files ORDER BY at")]
# ---------------- الملفات ----------------
SUPPORTED_EXTENSIONS = {'.py', '.php'}
def clean_name(name):
    name=os.path.basename(name or "script.py")
    name=re.sub(r"[^\w.\- \u0600-\u06ff]", "_", name, flags=re.UNICODE)
    if Path(name).suffix.lower() not in SUPPORTED_EXTENSIONS:
        name += '.py'
    return name[:120]
def is_supported_file(name):
    return Path(name).suffix.lower() in SUPPORTED_EXTENSIONS
def udir(uid): p=UPLOADS/str(int(uid)); p.mkdir(parents=True,exist_ok=True); return p
def files(uid):
    d=udir(uid)
    return sorted([p.name for p in d.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS])
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
# ---------------- PHP ----------------
def php_binary():
    return shutil.which('php')
def php_module_loaded(module):
    """تحقق سريع من توفر إضافة PHP فعلياً، وليس فقط وجود php-cli."""
    php = php_binary()
    if not php:
        return False
    try:
        r = subprocess.run(
            [php, '-m'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace', timeout=15
        )
        mods = {line.strip().lower() for line in (r.stdout or '').splitlines() if line.strip()}
        return module.lower() in mods
    except Exception:
        return False
def php_curl_ready():
    """curl_init() هو الاختبار الحقيقي المطلوب لملفات PHP التي تستخدم cURL."""
    php = php_binary()
    if not php:
        return False
    try:
        r = subprocess.run(
            [php, '-r', 'exit(function_exists("curl_init") ? 0 : 1);'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15
        )
        return r.returncode == 0
    except Exception:
        return False
def _run_php_install(cmd, lp):
    try:
        p = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace', timeout=300
        )
        with open(lp, 'a', encoding='utf-8', errors='replace') as f:
            f.write('\n[php install] $ ' + ' '.join(cmd) + '\n' + (p.stdout or '') + '\n')
        return p.returncode == 0
    except Exception as e:
        with open(lp, 'a', encoding='utf-8', errors='replace') as f:
            f.write(f'\n[php install error] {e}\n')
        return False
def ensure_php(lp):
    """
    تجهيز PHP CLI وإضافاته الشائعة تلقائياً.
    مهم: وجود php-cli وحده لا يكفي؛ مثلاً curl_init() موجودة فقط عند توفر php-curl.
    """
    system = platform.system().lower()
    php = php_binary()
    # Debian/Ubuntu/Railway Docker: ثبّت PHP والإضافات المطلوبة دفعة واحدة.
    if system == 'linux' and shutil.which('apt-get') and os.geteuid() == 0:
        packages = [
            'php-cli', 'php-curl', 'php-mbstring', 'php-xml', 'php-zip',
            'php-gd', 'php-intl', 'php-bcmath', 'php-mysql', 'php-soap',
            'php-opcache'
        ]
        # إذا PHP موجود لكن بعض الإضافات ناقصة، apt سيكمل الناقص فقط.
        if not php:
            _run_php_install(['apt-get', 'update', '-y'], lp)
        _run_php_install(['apt-get', 'install', '-y', '--no-install-recommends'] + packages, lp)
    elif system == 'linux' and shutil.which('apk') and os.geteuid() == 0:
        packages = [
            'php', 'php-curl', 'php-mbstring', 'php-xml', 'php-zip',
            'php-gd', 'php-intl', 'php-bcmath', 'php-mysqli', 'php-soap',
            'php-opcache'
        ]
        _run_php_install(['apk', 'add', '--no-cache'] + packages, lp)
    elif not php:
        with open(lp, 'a', encoding='utf-8', errors='replace') as f:
            f.write('\n[php install] لا يمكن تثبيت PHP تلقائياً: لا يوجد apt/apk بصلاحيات مناسبة.\n')
    # تحقق نهائي حقيقي. لا نعتبر PHP جاهزاً إذا كانت curl_init() ناقصة.
    if not php_binary():
        return False
    if not php_curl_ready():
        with open(lp, 'a', encoding='utf-8', errors='replace') as f:
            f.write('\n[php check] PHP موجود لكن php-curl غير متوفر أو curl_init() غير مفعلة.\n')
        return False
    return True
# ---------------- العمليات ----------------
procs={}; proc_lock=threading.RLock()
# جلسات إدخال تفاعلية للملفات التي تطلب رقم/كود/تحقق عبر input()
input_sessions={}; input_lock=threading.RLock()
last_prompt_sent={}
def running(p): return p is not None and p.poll() is None
def prompt_kind(text):
    t=(text or '').lower()
    # لا نلتقط كل مخرجات البرنامج؛ فقط الأسئلة الشائعة التي تحتاج إدخالاً من المستخدم.
    if re.search(r'(phone|phone number|mobile|رقم الهاتف|رقمك|رقم)', t): return 'phone'
    if re.search(r'(verification code|verify code|login code|confirmation code|كود التحقق|رمز التحقق|رمز الدخول|كود الدخول|الكود|رمز)', t): return 'code'
    if re.search(r'(two.?step|2fa|two factor|password|passcode|كلمة المرور|رمز 2fa|التحقق بخطوتين)', t): return 'password'
    if re.search(r'(verification|verify|تحقق|تأكيد)', t): return 'verify'
    return None
def prompt_message(kind, name):
    labels={
        'phone':'📱 الملف يطلب رقم الهاتف. أرسل الرقم هنا فقط.',
        'code':'🔐 الملف يطلب كود التحقق. أرسل الكود هنا فقط.',
        'password':'🔑 الملف يطلب كلمة مرور التحقق بخطوتين. أرسلها هنا فقط.',
        'verify':'🛡️ الملف يطلب خطوة تحقق. أرسل القيمة المطلوبة هنا.'
    }
    return f'<b>{labels.get(kind, "✏️ الملف يطلب إدخالاً.")}\n\n📄 الملف: <code>{name}</code>\n⚠️ لن يتم عرض الإدخال في السجل.</b>'
def set_input_session(uid,name,p,kind):
    with input_lock:
        input_sessions[int(uid)]={'name':clean_name(name),'pid':p.pid,'proc':p,'kind':kind,'at':time.time()}
def clear_input_session(uid,name=None):
    with input_lock:
        cur=input_sessions.get(int(uid))
        if cur and (name is None or cur.get('name')==clean_name(name)):
            input_sessions.pop(int(uid),None)
def get_input_session(uid):
    with input_lock:
        x=input_sessions.get(int(uid))
        if not x: return None
        if x['proc'].poll() is not None:
            input_sessions.pop(int(uid),None); return None
        return x
def send_input(uid, value):
    sess=get_input_session(uid)
    if not sess: return False,'لا يوجد ملف ينتظر إدخالاً حالياً.'
    p=sess['proc']
    try:
        master = getattr(p, '_hosting_pty_master', None)
        if master is not None and os.name != 'nt':
            os.write(master, (value.rstrip('\n')+'\n').encode('utf-8', errors='replace'))
        else:
            if p.stdin is None: return False,'هذا الملف لا يدعم الإدخال التفاعلي.'
            p.stdin.write(value.rstrip('\n')+'\n')
            p.stdin.flush()
        kind=sess.get('kind')
        # بعد إرسال القيمة ننتظر السؤال التالي؛ إذا كان تحقق/كود نترك الجلسة مفتوحة.
        with input_lock:
            if int(uid) in input_sessions:
                input_sessions[int(uid)]['kind']=None
                input_sessions[int(uid)]['at']=time.time()
        return True,'تم إرسال الإدخال إلى الملف.'
    except Exception as e:
        clear_input_session(uid)
        return False,f'تعذر إرسال الإدخال: {e}'
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
    try:
        master=getattr(p, '_hosting_pty_master', None)
        if master is not None:
            os.close(master)
            p._hosting_pty_master = None
    except Exception: pass
def _handle_output(uid, name, p, lp, text):
    if not text:
        return
    # السجل لا يحتوي أبداً على الإدخال الذي يرسله المستخدم؛ فقط مخرجات البرنامج.
    with open(lp,'a',encoding='utf-8',errors='replace') as f:
        f.write(text)
    kind=prompt_kind(text)
    if kind and running(p):
        now=time.time()
        key=(int(uid),clean_name(name),kind)
        if now-last_prompt_sent.get(key,0)>2:
            last_prompt_sent[key]=now
            set_input_session(uid,name,p,kind)
            try: bot.send_message(uid,prompt_message(kind,name))
            except Exception as e: log(f'prompt notify error {uid}/{name}: {e}')
def reader(uid,name,p,lp):
    master=getattr(p, '_hosting_pty_master', None)
    try:
        if master is not None and os.name != 'nt':
            # PTY يلتقط حتى prompts التي لا تنتهي بسطر جديد، وهي المشكلة
            # الشائعة مع getpass/readline وبرامج Telegram التفاعلية.
            while True:
                try:
                    ready,_,_=select.select([master],[],[],0.5)
                except (OSError,ValueError):
                    break
                if ready:
                    try:
                        data=os.read(master,8192)
                    except OSError:
                        data=b''
                    if data:
                        _handle_output(uid,name,p,lp,data.decode('utf-8',errors='replace'))
                    elif p.poll() is not None:
                        break
                elif p.poll() is not None:
                    # تفريغ ما تبقى قبل الإغلاق.
                    try:
                        while True:
                            data=os.read(master,8192)
                            if not data: break
                            _handle_output(uid,name,p,lp,data.decode('utf-8',errors='replace'))
                    except OSError:
                        pass
                    break
        else:
            for line in iter(p.stdout.readline,''):
                if not line: break
                _handle_output(uid,name,p,lp,line)
    except Exception as e:
        with open(lp,'a',encoding='utf-8') as f: f.write(f'\n[reader error] {e}\n')
    finally:
        try:
            if master is not None:
                os.close(master)
        except Exception:
            pass
        rc=p.poll()
        clear_input_session(uid,name)
        with open(lp,'a',encoding='utf-8') as f: f.write(f'\n[process exit] {rc}\n')
        with proc_lock: procs.pop((uid,name),None)
# ---------------- تشغيل/إيقاف الملفات ----------------
def _launch_process(path, lp):
    """تشغيل Python/PHP مع PTY على Linux لدعم input/getpass/readline."""
    ext=path.suffix.lower()
    if ext=='.php':
        if not ensure_php(lp):
            return None, 'PHP CLI غير متوفر على النظام.'
        cmd=[php_binary(), '-d', 'display_errors=1', '-d', 'log_errors=0', str(path)]
    elif ext=='.py':
        cmd=[sys.executable, '-u', str(path)]
    else:
        return None, 'نوع الملف غير مدعوم.'
    env=os.environ.copy()
    env['PYTHONUNBUFFERED']='1'
    env['PYTHONIOENCODING']='utf-8'
    env['TERM']='xterm'
    if HAVE_PTY and os.name != 'nt':
        master, slave=pty.openpty()
        try:
            def child_setup():
                os.setsid()
                try:
                    os.tcsetpgrp(slave, os.getpid())
                except Exception:
                    pass
            proc=subprocess.Popen(
                cmd, stdin=slave, stdout=slave, stderr=slave,
                cwd=str(path.parent), env=env,
                preexec_fn=child_setup, close_fds=True
            )
        except Exception:
            try: os.close(master)
            except Exception: pass
            try: os.close(slave)
            except Exception: pass
            raise
        finally:
            try: os.close(slave)
            except Exception: pass
        proc._hosting_pty_master=master
        return proc, None
    proc=subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        cwd=str(path.parent), env=env, text=True, bufsize=1
    )
    proc._hosting_pty_master=None
    return proc, None
def start(uid,name):
    uid=int(uid); name=clean_name(name); path=udir(uid)/name; lp=script_log(uid,name)
    if not path.exists(): return False, 'الملف غير موجود.'
    key=(uid,name)
    with proc_lock:
        old=procs.get(key)
        if running(old): return True, 'الملف يعمل بالفعل.'
    try:
        lp.parent.mkdir(parents=True,exist_ok=True)
        with open(lp,'w',encoding='utf-8') as f:
            f.write(f'[START {time.strftime("%Y-%m-%d %H:%M:%S")}] {name}\n')
        if path.suffix.lower()=='.py':
            try:
                src=path.read_text(encoding='utf-8',errors='replace')
                ast.parse(src)
            except SyntaxError as e:
                return False, f'خطأ SyntaxError في السطر {e.lineno}: {e.msg}'
            results=prepare(path,lp)
            failed=[f'{m} → {pkg}' for m,pkg,ok in results if not ok]
            if failed:
                return False, 'تعذر تثبيت بعض المتطلبات:\n'+'\n'.join(failed)
        else:
            # PHP لا يحتاج pip؛ جهّز PHP CLI والإضافات تلقائياً، ومنها cURL.
            if not ensure_php(lp):
                return False, 'PHP غير جاهز: تأكد من توفر php-cli و php-curl (curl_init()). راجع سجل الملف للتفاصيل.'
        proc,err=_launch_process(path,lp)
        if proc is None: return False, err or 'تعذر تشغيل الملف.'
        with proc_lock: procs[key]=proc
        threading.Thread(target=reader,args=(uid,name,proc,lp),daemon=True).start()
        # مهلة قصيرة فقط لاكتشاف فشل فوري مثل import/fatal error.
        time.sleep(0.20)
        rc=proc.poll()
        if rc is not None:
            tail=read_log(lp,2500)
            with proc_lock: procs.pop(key,None)
            return False, f'توقف مباشرة بعد التشغيل.\n<pre>{tail}</pre>'
        mark_active(uid,name)
        return True, f'تم تشغيل <code>{name}</code> بنجاح.'
    except Exception as e:
        log(traceback.format_exc(),'hosting_bot_errors.log')
        return False, f'فشل تشغيل الملف: {e}'
def stop(uid,name):
    uid=int(uid); name=clean_name(name); key=(uid,name)
    with proc_lock: proc=procs.get(key)
    if not proc or not running(proc):
        with proc_lock: procs.pop(key,None)
        unmark_active(uid,name)
        return False, 'الملف متوقف أصلاً.'
    stop_proc(proc)
    with proc_lock: procs.pop(key,None)
    clear_input_session(uid,name)
    unmark_active(uid,name)
    return True, f'تم إيقاف <code>{name}</code>.'
def delete_file(uid,name):
    uid=int(uid); name=clean_name(name); key=(uid,name); path=udir(uid)/name
    with proc_lock: proc=procs.get(key)
    if proc and running(proc): stop_proc(proc)
    with proc_lock: procs.pop(key,None)
    clear_input_session(uid,name); unmark_active(uid,name)
    try:
        if path.exists(): path.unlink()
        lp=script_log(uid,name)
        if lp.exists(): lp.unlink()
        return True, f'تم حذف <code>{name}</code> نهائياً.'
    except Exception as e:
        return False, f'تعذر حذف الملف: {e}'
def restart(uid,name):
    stop(uid,name)
    return start(uid,name)
def stop_all(uid=None):
    with proc_lock:
        items=list(procs.items())
    for (pu,pn),proc in items:
        if uid is None or int(pu)==int(uid):
            stop_proc(proc)
            clear_input_session(pu,pn)
            with proc_lock: procs.pop((pu,pn),None)
            unmark_active(pu,pn)
# ---------------- تجهيز telebot ----------------
def restore_active_files():
    for uid,name in active_files():
        if not (udir(uid)/name).exists():
            unmark_active(uid,name); continue
        try:
            ok,msg=start(uid,name)
            if not ok: log(f'استعادة {uid}/{name} فشلت: {msg}','hosting_bot_errors.log')
        except Exception: log(traceback.format_exc(),'hosting_bot_errors.log')
def watchdog_loop():
    while True:
        try:
            for uid,name in active_files():
                path=udir(uid)/name
                if not path.exists(): unmark_active(uid,name); continue
                with proc_lock: proc=procs.get((uid,name))
                if not running(proc):
                    ok,msg=start(uid,name)
                    if not ok: log(f'إعادة تشغيل {uid}/{name} فشلت: {msg}','hosting_bot_errors.log')
        except Exception: log(traceback.format_exc(),'hosting_bot_errors.log')
        time.sleep(8)
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
bot=telebot.TeleBot(BOT_TOKEN,parse_mode='HTML',threaded=True,num_threads=32,skip_pending=True)
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
def home_text(): return '<b>🤖 بوت الاستضافة\n\n📦 تشغيل ملفات Python تلقائياً\n🧰 تثبيت المتطلبات الناقصة\n🎵 دعم FFmpeg\n📋 سجل الأخطاء لكل ملف\n🔐 دعم الإدخال التفاعلي للرقم والكود والتحقق</b>'
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
# ---------------- الإدخال التفاعلي ----------------
@bot.message_handler(content_types=['text'])
def interactive_text(m):
    # الأوامر تمر إلى handlers الخاصة بها أولاً في telebot؛ هنا نعالج فقط جلسة ملف تنتظر إدخالاً.
    uid=m.from_user.id
    if not approved(uid): return
    if (m.text or '').startswith('/'):
        return
    sess=get_input_session(uid)
    if not sess: return
    value=m.text.strip()
    if not value: return bot.reply_to(m,'<b>⚠️ أرسل قيمة غير فارغة.</b>')
    ok,msg=send_input(uid,value)
    if ok:
        # لا نعرض القيمة حتى لو كانت كوداً أو كلمة مرور.
        bot.reply_to(m,f'<b>✅ {msg}</b>')
    else:
        bot.reply_to(m,f'<b>❌ {msg}</b>')
# ---------------- رفع ----------------
@bot.message_handler(content_types=['document'])
def upload(m):
    uid=m.from_user.id
    if not approved(uid): return
    d=m.document; name=clean_name(d.file_name)
    if not is_supported_file(d.file_name):
        return bot.reply_to(m,'<b>⛔ الملفات المدعومة حالياً: .py و .php فقط.</b>')
    if d.file_size and d.file_size>MAX_SIZE: return bot.reply_to(m,'<b>⛔ الحد الأقصى 10MB.</b>')
    try:
        f=bot.get_file(d.file_id); data=bot.download_file(f.file_path); (udir(uid)/name).write_bytes(data)
        if Path(name).suffix.lower()=='.py':
            src=data.decode('utf-8',errors='replace'); ast.parse(src)
        elif Path(name).suffix.lower()=='.php' and php_binary():
            chk=subprocess.run([php_binary(),'-l',str(udir(uid)/name)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',timeout=30)
            if chk.returncode!=0:
                return bot.reply_to(m,f'<b>⚠️ تم الحفظ لكن PHP فيه خطأ:<br><pre>{chk.stdout[-3000:]}</pre></b>')
    except SyntaxError as e:
        return bot.reply_to(m,f'<b>⚠️ تم الحفظ لكن يوجد SyntaxError في السطر {e.lineno}: {e.msg}</b>')
    except Exception as e:
        return bot.reply_to(m,f'<b>❌ فشل رفع الملف: <code>{e}</code></b>')
    path=udir(uid)/name
    if path.suffix.lower()=='.php':
        deps=f'• PHP CLI: {"🟢 موجود" if php_binary() else "🟡 سيتم محاولة تثبيته عند التشغيل"}'
    else:
        known,unknown=missing_for(path)
        deps='\n'.join(f'• {a} → {b}' for a,b in known) or '• لا توجد متطلبات معروفة ناقصة.'
    bot.reply_to(m,f'<b>✅ تم رفع <code>{name}</code>\n\n📦 المتطلبات:\n{deps}\n\nسيتم تجهيزها تلقائياً عند التشغيل. وإذا طلب الملف رقم/كود/تحقق، سيظهر لك الطلب هنا وتقدر ترسله مباشرة.</b>',reply_markup=types.InlineKeyboardMarkup([[types.InlineKeyboardButton('▶️ تشغيل',callback_data=f'start:{name}'),types.InlineKeyboardButton('📋 السجل',callback_data=f'log:{name}')],[types.InlineKeyboardButton('↩️ الرئيسية',callback_data='home')]]))
# تنفيذ التشغيل بالخلفية حتى لا تتجمد واجهة البوت أثناء تثبيت مكتبة ناقصة
action_lock = threading.RLock()
busy_actions = set()
def async_start_action(uid, name, chat_id, message_id=None, restart_mode=False):
    key=(int(uid), clean_name(name), 'restart' if restart_mode else 'start')
    with action_lock:
        if key in busy_actions:
            return
        busy_actions.add(key)
    def worker():
        try:
            ok,msg = restart(uid,name) if restart_mode else start(uid,name)
            markup=types.InlineKeyboardMarkup([[types.InlineKeyboardButton('📋 السجل',callback_data=f'log:{clean_name(name)}')],[types.InlineKeyboardButton('↩️ الرئيسية',callback_data='home')]])
            bot.send_message(chat_id,f'<b>{"✅" if ok else "❌"} {msg}</b>',reply_markup=markup)
        except Exception as e:
            try: bot.send_message(chat_id,f'<b>❌ خطأ: <code>{e}</code></b>')
            except Exception: pass
        finally:
            with action_lock: busy_actions.discard(key)
    threading.Thread(target=worker,daemon=True).start()
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
    if d=='upload': return bot.send_message(c.message.chat.id,'<b>📤 أرسل ملف .py أو .php الآن (حد 10MB).</b>',reply_markup=back())
    if d=='files':
        fs=files(uid); return bot.send_message(c.message.chat.id,'<b>اختر ملفاً:</b>',reply_markup=pick_kb(uid,'info') if fs else back())
    if d.startswith('pick:'):
        a=d.split(':',1)[1]; fs=files(uid)
        return bot.send_message(c.message.chat.id,'<b>اختر الملف:</b>',reply_markup=pick_kb(uid,a) if fs else back())
    if d=='system':
        return bot.send_message(c.message.chat.id,f'<b>🧰 النظام\nPython: <code>{platform.python_version()}</code>\nPHP: <code>{php_binary() or "غير موجود"}</code>\nFFmpeg: <code>{ffmpeg() or "غير موجود"}</code>\nالمنصة: <code>{platform.system()}</code></b>',reply_markup=back())
    if d=='pending' and uid==ADMIN_ID:
        ps=pending()
        if not ps: return bot.send_message(c.message.chat.id,'<b>لا توجد طلبات.</b>',reply_markup=back())
        for x in ps: bot.send_message(c.message.chat.id,f'<b>👤 <code>{x}</code></b>',reply_markup=types.InlineKeyboardMarkup([[types.InlineKeyboardButton('✅ قبول',callback_data=f'approve:{x}'),types.InlineKeyboardButton('❌ رفض',callback_data=f'reject:{x}')]]))
        return
    if d=='allstop' and uid==ADMIN_ID: stop_all(); return bot.send_message(c.message.chat.id,'<b>⏹ تم إيقاف كل العمليات.</b>',reply_markup=back())
    if ':' not in d: return
    action,name=d.split(':',1); name=clean_name(name); path=udir(uid)/name
    if action=='delete':
        ok,msg=delete_file(uid,name)
        return bot.send_message(c.message.chat.id,f'<b>{"✅" if ok else "❌"} {msg}</b>',reply_markup=back())
    if action=='start':
        bot.send_message(c.message.chat.id,f'<b>⏳ جاري تشغيل <code>{name}</code>...</b>')
        return async_start_action(uid,name,c.message.chat.id,c.message.message_id,False)
    elif action=='stop': ok,msg=stop(uid,name)
    elif action=='restart':
        bot.send_message(c.message.chat.id,f'<b>⏳ جاري إعادة تشغيل <code>{name}</code>...</b>')
        return async_start_action(uid,name,c.message.chat.id,c.message.message_id,True)
    elif action=='log': return bot.send_message(c.message.chat.id,f'<b>📋 سجل {name}</b>\n<pre>{read_log(script_log(uid,name),7000)}</pre>',reply_markup=types.InlineKeyboardMarkup([[types.InlineKeyboardButton('🔄 تحديث',callback_data=f'log:{name}')],[types.InlineKeyboardButton('↩️ رجوع',callback_data='home')]]))
    elif action=='deps':
        if not path.exists(): return bot.send_message(c.message.chat.id,'<b>الملف غير موجود.</b>',reply_markup=back())
        if path.suffix.lower()=='.php':
            txt=f'• PHP CLI → {"🟢 مثبت" if php_binary() else "🔴 غير مثبت"}'
        else:
            k,u=missing_for(path); txt='\n'.join(f'• {a} → {b}' for a,b in k) or '• لا توجد متطلبات معروفة ناقصة.'
        return bot.send_message(c.message.chat.id,f'<b>📦 المتطلبات:\n{txt}</b>',reply_markup=back())
    elif action=='delete':
        if not path.exists(): return bot.send_message(c.message.chat.id,'<b>الملف غير موجود.</b>',reply_markup=back())
        kb=types.InlineKeyboardMarkup([[types.InlineKeyboardButton('✅ نعم، احذف',callback_data=f'delete:{name}'),types.InlineKeyboardButton('❌ إلغاء',callback_data='home')]])
        return bot.send_message(c.message.chat.id,f'<b>⚠️ هل تريد حذف <code>{name}</code> نهائياً؟</b>',reply_markup=kb)
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
        try: bot.infinity_polling(timeout=8,long_polling_timeout=8,skip_pending=True,allowed_updates=['message','callback_query'])
        except KeyboardInterrupt: break
        except Exception:
            err=traceback.format_exc(); log(err,'hosting_bot_errors.log'); time.sleep(1)
if __name__=='__main__':
    threading.Thread(target=watchdog_loop,daemon=True).start()
    threading.Thread(target=restore_active_files,daemon=True).start()
    main()
