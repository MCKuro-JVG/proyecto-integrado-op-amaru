"""Supervisor local del origen duradero; no instala servicios ni crea túneles."""
import argparse,json,os,socket,subprocess,sys,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/'.tools/stability/runtime'
HIDDEN=getattr(subprocess,'CREATE_NO_WINDOW',0)

def atomic_json(path,data):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data),encoding='utf-8');temp.replace(path)

def health(port):
    from dotenv import dotenv_values
    from urllib.parse import urlsplit
    envfile=os.environ.get('AMARU_STABLE_ENV_FILE',str(ROOT/'amaru/.env.qr-demo'))
    base=os.environ.get('ATTENTION_PUBLIC_BASE_URL') or dotenv_values(envfile).get('ATTENTION_PUBLIC_BASE_URL','')
    host=urlsplit(base).netloc if base else '127.0.0.1'
    try:
        request=urllib.request.Request(f'http://127.0.0.1:{port}/healthz/',headers={'Host':host,'X-Forwarded-Proto':'https'})
        with urllib.request.urlopen(request,timeout=8) as response:return response.status==200 and json.load(response)=={'status':'ok'}
    except (OSError,ValueError):return False

def paths(port):return {name:STATE/f'origin-{port}.{suffix}' for name,suffix in [('status','json'),('stop','stop'),('lock','lock'),('worker_stop','worker-stop'),('fault','fault')]}

def acquire_lock(path):
    handle=path.open('a+b');handle.seek(0)
    if path.stat().st_size==0:handle.write(b'0');handle.flush()
    handle.seek(0)
    if os.name=='nt':
        import msvcrt
        msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
    else:
        import fcntl
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
    return handle

def supervise(port):
    STATE.mkdir(parents=True,exist_ok=True);files=paths(port)
    try:lock=acquire_lock(files['lock'])
    except OSError:raise RuntimeError('Ya existe un supervisor de este puerto.')
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1',port))==0:raise RuntimeError('Puerto ocupado; no se reemplaza otro proceso.')
    files['stop'].unlink(missing_ok=True);child=None;restarts=0;failures=0
    try:
        while not files['stop'].exists():
            if child is not None and child.poll() is not None:
                # Contar también las salidas ocurridas durante la espera entre sondeos.
                restarts+=1;child=None
                for _ in range(min(2**min(restarts,6),60)):
                    if files['stop'].exists():break
                    time.sleep(1)
                if files['stop'].exists():break
            if child is None:
                files['worker_stop'].unlink(missing_ok=True);files['fault'].unlink(missing_ok=True)
                env=os.environ.copy();env['AMARU_STABLE_PORT']=str(port);env['AMARU_STABLE_STOP_FILE']=str(files['worker_stop']);env['AMARU_STABLE_FAULT_FILE']=str(files['fault'])
                env.pop('DJANGO_SETTINGS_MODULE',None)
                logfile=STATE/f'origin-{port}-bootstrap.log'
                if logfile.exists() and logfile.stat().st_size>5*1024*1024:logfile.replace(logfile.with_suffix('.previous.log'))
                log=logfile.open('ab')
                child=subprocess.Popen([sys.executable,'-B',str(ROOT/'amaru/serve_attention_stable.py')],cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=HIDDEN)
                log.close()
                deadline=time.monotonic()+35
                while child.poll() is None and time.monotonic()<deadline and not health(port) and not files['stop'].exists():time.sleep(1)
            healthy=health(port)
            atomic_json(files['status'],{'pid':os.getpid(),'worker_pid':child.pid,'port':port,'healthy':healthy,'restarts':restarts,'checked_at':time.time()})
            failures=0 if healthy else failures+1
            if child.poll() is not None or failures>=3:
                files['worker_stop'].touch()
                try:child.wait(timeout=35)
                except subprocess.TimeoutExpired:
                    subprocess.run(['taskkill','/PID',str(child.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                child=None;restarts+=1;failures=0
                for _ in range(min(2**min(restarts,6),60)):
                    if files['stop'].exists():break
                    time.sleep(1)
            else:
                for _ in range(5):
                    if files['stop'].exists():break
                    time.sleep(1)
    finally:
        if child and child.poll() is None:
            files['worker_stop'].touch()
            try:child.wait(timeout=35)
            except subprocess.TimeoutExpired:
                subprocess.run(['taskkill','/PID',str(child.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        atomic_json(files['status'],{'pid':os.getpid(),'port':port,'healthy':False,'stopped':True,'restarts':restarts})
        lock.close()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['start','stop','status','supervise']);parser.add_argument('--port',type=int,default=8005);args=parser.parse_args()
    if not 8005<=args.port<=8999:raise RuntimeError('Puerto de operación fuera del rango dedicado.')
    STATE.mkdir(parents=True,exist_ok=True);files=paths(args.port)
    if args.action=='supervise':supervise(args.port);return
    if args.action=='stop':files['stop'].touch();print('Cierre controlado solicitado.');return
    if args.action=='status':print(json.dumps({'healthy':health(args.port),'state':json.loads(files['status'].read_text()) if files['status'].exists() else None}));return
    if health(args.port):print('El origen ya está saludable; no se duplica.');return
    if os.name=='nt' and args.port==8005:
        installed=subprocess.run(['sc.exe','query','OpticasAmaruAttention'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
        if installed:
            wrapper=ROOT/'.tools/stability/services/OpticasAmaruAttention.exe'
            started=subprocess.run([str(wrapper),'start'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            if started.returncode:raise RuntimeError('El servicio está instalado. Inícielo desde Servicios de Windows con autorización de administrador; no se crea otra instancia.')
            for _ in range(50):
                if health(args.port):print('Servicio de atención saludable.');return
                time.sleep(1)
            raise RuntimeError('El servicio no completó su inicio; revisar los registros.')
    log=(STATE/f'origin-{args.port}-supervisor.log').open('ab')
    subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'supervise','--port',str(args.port)],cwd=ROOT,stdout=log,stderr=log,creationflags=HIDDEN)
    for _ in range(50):
        if health(args.port):print('Origen Waitress saludable en loopback, puerto '+str(args.port));return
        time.sleep(1)
    raise RuntimeError('No inició el origen; revise el registro local de operación.')
if __name__=='__main__':main()
