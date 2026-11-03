"""Abre la revisión del entorno instalado sin crear túneles temporales nuevos."""
import os,subprocess,socket,time,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];PY=ROOT/'.venv/Scripts/python.exe'
def main():
    subprocess.run([str(PY),'-B','scripts/attention_runtime.py','start'],cwd=ROOT,check=True)
    with socket.socket() as sock:staff_running=sock.connect_ex(('127.0.0.1',8003))==0
    if not staff_running:
        env=os.environ.copy();env.pop('ATTENTION_PUBLIC_ONLY',None);env.pop('DJANGO_SETTINGS_MODULE',None)
        log=open(ROOT/'.tools/stability/runtime/staff-review.log','ab')
        subprocess.Popen([str(PY),'-B','amaru/serve_attention_demo.py'],cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    env=os.environ.copy();private=ROOT/'.tools/stability/registro_local.sql'
    if private.exists():env['AMARU_REVIEW_QUERY_FILE']=str(private)
    subprocess.run([str(PY),'-B','scripts/open_review.py'],cwd=ROOT,env=env,check=True)
    log=open(ROOT/'.tools/stability/runtime/chrome-review.log','ab')
    browser_env=os.environ.copy();browser_env['AMARU_PRESENTATION_PROFILE']=str(ROOT/'.tools/stability/browser-profile')
    browser=subprocess.Popen([str(PY),'-B','scripts/show_attention.py'],cwd=ROOT,env=browser_env,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    ready=ROOT/'.tools/stability/presentation-ready.json'
    for _ in range(45):
        if ready.exists() and json.loads(ready.read_text()).get('opened'):break
        if browser.poll() is not None and browser.returncode!=0:raise RuntimeError('No abrió la presentación de Chrome; revisar el registro privado.')
        time.sleep(1)
    else:raise RuntimeError('No se confirmó la apertura de Chrome dentro del plazo.')
    print('Revisión preparada: origen supervisado, código, base de datos y atención local. No se crea un nuevo Quick Tunnel.')
if __name__=='__main__':main()
