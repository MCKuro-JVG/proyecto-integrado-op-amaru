"""Presentación en Chrome con perfil local privado, sin credenciales en argumentos."""
import json,os,time,webbrowser
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];STATE=ROOT/'.tools/attention'

def main():
    data=json.loads((STATE/'public-url.json').read_text())
    if not data.get('active'):raise RuntimeError('Inicie la demostración antes de abrir Chrome.')
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        for url in ['http://127.0.0.1:8003/app/dashboard.html?qr=1',data['url']+'/app/formulario_remoto.html?origen=qr','http://127.0.0.1:8003/app/solicitudes.html']:webbrowser.open(url)
        return
    pidfile=STATE/'chrome-presentacion.pid'
    if pidfile.exists() and os.name=='nt':
        import ctypes
        handle=ctypes.windll.kernel32.OpenProcess(0x1000,False,int(pidfile.read_text()))
        if handle:ctypes.windll.kernel32.CloseHandle(handle);return
    pidfile.write_text(str(os.getpid()))
    try:
        with sync_playwright() as p:
            context=p.chromium.launch_persistent_context(str(STATE/'chrome-profile'),channel='chrome',headless=False,viewport=None,no_viewport=True)
            credentials=json.loads((STATE/'demo-credentials.json').read_text())
            base='http://127.0.0.1:8003';session=context.request.get(base+'/api/session/').json()
            if not session['authenticated']:
                result=context.request.post(base+'/api/login/',data={'username':'personal_qr','password':credentials['personal_qr']},headers={'X-CSRFToken':session['csrf'],'Referer':base+'/'})
                if result.status!=200:raise RuntimeError('No se pudo abrir la sesión de demostración.')
            worker=context.new_page();worker.goto(base+'/app/dashboard.html?qr=1')
            public=context.new_page();public.goto(data['url']+'/app/formulario_remoto.html?origen=qr')
            requests=context.new_page();requests.goto(base+'/app/solicitudes.html')
            worker.bring_to_front()
            context.wait_for_event('close',timeout=0)
    finally:pidfile.unlink(missing_ok=True)
if __name__=='__main__':main()
