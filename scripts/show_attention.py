"""Presentación en Chrome con perfil local privado, sin credenciales en argumentos."""
import json,os,time,webbrowser,socket
from dotenv import dotenv_values
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];STATE=ROOT/'.tools/attention'

def main():
    base=dotenv_values(ROOT/'amaru/.env.qr-demo').get('ATTENTION_PUBLIC_BASE_URL','')
    data={'url':base,'active':bool(base)}
    if not base and (STATE/'public-url.json').exists():
        temporary=json.loads((STATE/'public-url.json').read_text())
        if temporary.get('active') and temporary.get('expires_at',0)>time.time():data=temporary
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        urls=['http://127.0.0.1:8003/app/dashboard.html?qr=1','http://127.0.0.1:8003/app/solicitudes.html']
        if data.get('active'):urls.append(data['url']+'/app/formulario_remoto.html?origen=qr')
        for url in urls:webbrowser.open(url)
        return
    profile=Path(os.environ.get('AMARU_PRESENTATION_PROFILE') or (STATE/'chrome-profile'))
    profile.parent.mkdir(parents=True,exist_ok=True)
    pidfile=profile.parent/'presentation.pid' if os.environ.get('AMARU_PRESENTATION_PROFILE') else STATE/'chrome-presentacion.pid'
    if pidfile.exists() and os.name=='nt':
        import ctypes
        handle=ctypes.windll.kernel32.OpenProcess(0x1000,False,int(pidfile.read_text()))
        if handle:ctypes.windll.kernel32.CloseHandle(handle);return
    pidfile.write_text(str(os.getpid()))
    ready=profile.parent/'presentation-ready.json'
    ready.unlink(missing_ok=True)
    try:
        with sync_playwright() as p:
            context=p.chromium.launch_persistent_context(str(profile),channel='chrome',headless=False,viewport=None,no_viewport=True)
            credentials=json.loads((STATE/'demo-credentials.json').read_text())
            base='http://127.0.0.1:8003';session=context.request.get(base+'/api/session/').json()
            if not session['authenticated']:
                result=context.request.post(base+'/api/login/',data={'username':'personal_qr','password':credentials['personal_qr']},headers={'X-CSRFToken':session['csrf'],'Referer':base+'/'})
                if result.status!=200:raise RuntimeError('No se pudo abrir la sesión de demostración.')
            worker=context.new_page();worker.goto(base+'/app/dashboard.html?qr=1')
            if data.get('active'):
                public=context.new_page();public.goto(data['url']+'/app/formulario_remoto.html?origen=qr')
            requests=context.new_page();requests.goto(base+'/app/solicitudes.html')
            worker.get_by_role('heading',name='Resumen de atención',exact=True).wait_for()
            worker.bring_to_front()
            ready.write_text(json.dumps({'opened':True,'pid':os.getpid(),'public_url':data.get('url') if data.get('active') else None}),encoding='utf-8')
            context.wait_for_event('close',timeout=0)
    finally:
        pidfile.unlink(missing_ok=True);ready.unlink(missing_ok=True)
if __name__=='__main__':main()
