"""Un solo inicio para revisar código, datos y atención QR en este equipo."""
import json,os,socket,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];PY=ROOT/'.venv/Scripts/python.exe';STATE=ROOT/'.tools/attention';STATE.mkdir(parents=True,exist_ok=True)
HIDDEN=getattr(subprocess,'CREATE_NO_WINDOW',0)
def listening(port):
    with socket.socket() as sock:return sock.connect_ex(('127.0.0.1',port))==0
def background(args,name,env=None):
    log=open(STATE/name,'ab');return subprocess.Popen(args,cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=HIDDEN)
def main():
    if not listening(3306):
        exe=ROOT/'.tools/mariadb/mariadb-11.4.13-winx64/bin/mariadbd.exe'
        if not exe.exists():raise RuntimeError('Inicie su servicio MariaDB local.')
        background([str(exe),'--defaults-file='+str(ROOT/'.tools/mariadb/data/my.ini')],'mariadb.log')
        for _ in range(30):
            if listening(3306):break
            time.sleep(1)
    if not listening(8001):
        env=os.environ.copy();env['AMARU_ENV_FILE']=str(ROOT/'amaru/.env');env.pop('DJANGO_SETTINGS_MODULE',None)
        background([str(PY),'-B','amaru/manage.py','runserver','127.0.0.1:8001','--noreload'],'main.log',env)
    subprocess.run([str(PY),'-B','scripts/attention_demo.py'],cwd=ROOT,check=True)
    subprocess.run([str(PY),'-B','scripts/open_review.py'],cwd=ROOT,check=True)
    background([str(PY),'-B','scripts/show_attention.py'],'chrome.log')
    print('Entorno preparado: código, tablas, QR, formulario y solicitudes. Solo la demostración ficticia tiene acceso público temporal.')
if __name__=='__main__':main()
