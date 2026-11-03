"""Túnel académico temporal. Expone solamente la instancia MariaDB ficticia."""
import json,os,re,shutil,socket,subprocess,sys,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/'.tools/attention'
PY=ROOT/'.venv/Scripts/python.exe'
HIDDEN=getattr(subprocess,'CREATE_NO_WINDOW',0)
def listening(port):
    with socket.socket() as sock: return sock.connect_ex(('127.0.0.1',port))==0
def spawn(args,name,env=None):
    log=open(STATE/name,'ab')
    return subprocess.Popen(args,cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=HIDDEN)
def main():
    STATE.mkdir(parents=True,exist_ok=True)
    if '--stop' in sys.argv:
        (STATE/'stop.flag').touch();print('Se solicitó cerrar únicamente la demostración pública.');return
    if '--supervise' not in sys.argv:
        if (STATE/'public-url.json').exists():
            d=json.loads((STATE/'public-url.json').read_text())
            if d.get('active') and listening(8004): print(d['url']);return
        if not (ROOT/'amaru/.env.qr-demo').exists(): raise RuntimeError('Prepare primero la base y el entorno privados de demostración.')
        spawn([str(PY),str(Path(__file__).resolve()),'--supervise'],'supervisor.log')
        for _ in range(120):
            time.sleep(1)
            path=STATE/'public-url.json'
            if path.exists():
                d=json.loads(path.read_text())
                if d.get('active') and listening(8004):print(d['url']);return
        raise RuntimeError('No inició el túnel. Revise .tools/attention/supervisor.log.')
    if listening(8004):raise RuntimeError('El puerto público ya está ocupado; no se crea un túnel duplicado.')
    (STATE/'stop.flag').unlink(missing_ok=True)
    env=os.environ.copy();env.pop('DJANGO_SETTINGS_MODULE',None);env.pop('ATTENTION_PUBLIC_ONLY',None)
    env['AMARU_ENV_FILE']=str(ROOT/'amaru/.env.qr-demo')
    if not listening(8003):spawn([str(PY),'-B','amaru/serve_attention_demo.py'],'staff.log',env)
    runtime=STATE/'runtime.json'
    command=json.loads(runtime.read_text())['cf_command'] if runtime.exists() else [shutil.which('cf') or 'cf']
    logpath=STATE/'tunnel.log';logpath.write_text('')
    cf=spawn(command+['tunnels','quick-start','http://127.0.0.1:8004'],'tunnel.log')
    public=None
    try:
        url=None
        for _ in range(100):
            if cf.poll() is not None:raise RuntimeError('cf finalizó; consulte tunnel.log.')
            match=re.search(r'https://[a-z0-9-]+\.trycloudflare\.com',logpath.read_text(errors='replace'))
            if match:url=match.group();break
            time.sleep(1)
        if not url:raise RuntimeError('Cloudflare no devolvió una URL temporal.')
        env['ATTENTION_PUBLIC_ONLY']='true';env['ATTENTION_PUBLIC_BASE_URL']=url
        public=spawn([str(PY),'-B','amaru/serve_attention_demo.py'],'public.log',env)
        for _ in range(50):
            if listening(8004):break
            if public.poll() is not None:raise RuntimeError('No inició el origen público.')
            time.sleep(.5)
        data={'url':url,'active':True,'pid':cf.pid,'supervisor_pid':os.getpid(),'expires_at':time.time()+7200,'isolated_database':True}
        temporary=STATE/'public-url.tmp';temporary.write_text(json.dumps(data),encoding='utf-8');temporary.replace(STATE/'public-url.json')
        start=time.monotonic()
        while time.monotonic()-start<7200 and cf.poll() is None and public.poll() is None and not (STATE/'stop.flag').exists():time.sleep(1)
    finally:
        if public and public.poll() is None:public.terminate()
        if cf.poll() is None:
            if os.name=='nt':subprocess.run(['taskkill','/PID',str(cf.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            else:cf.terminate()
        (STATE/'public-url.json').write_text(json.dumps({'active':False}),encoding='utf-8')
if __name__=='__main__':main()
