"""Origen Waitress supervisable, sin runserver ni exposición del panel administrativo."""
import os,sys,time,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parent
os.environ['AMARU_ENV_FILE']=os.environ.get('AMARU_STABLE_ENV_FILE',str(ROOT/'.env.qr-demo'))
os.environ['DJANGO_SETTINGS_MODULE']='config.attention_stable_settings'
from django.core.wsgi import get_wsgi_application
from waitress import create_server
application=get_wsgi_application()
server=create_server(application,listen='127.0.0.1:'+os.environ.get('AMARU_STABLE_PORT','8005'),threads=4,
      trusted_proxy='127.0.0.1',trusted_proxy_headers={'x-forwarded-proto'},
      clear_untrusted_proxy_headers=True,max_request_body_size=65536,channel_timeout=60)

stop=os.environ.get('AMARU_STABLE_STOP_FILE')
fault=os.environ.get('AMARU_STABLE_FAULT_FILE')
runner=threading.Thread(target=server.run,daemon=True);runner.start()
try:
    while runner.is_alive():
        if stop and Path(stop).exists():break
        if fault and Path(fault).exists():os._exit(17)  # Fallo controlado solicitado solo desde el equipo local.
        time.sleep(.25)
finally:
    server.close()
    server.task_dispatcher.shutdown(cancel_pending=False,timeout=25)
