"""Servidor WSGI Windows para la demostración separada, solo en loopback."""
import os
from pathlib import Path
from dotenv import load_dotenv
root=Path(__file__).resolve().parent
os.environ['AMARU_ENV_FILE']=str(root/'.env.qr-demo')
os.environ['DJANGO_SETTINGS_MODULE']='config.attention_demo_settings'
from django.core.wsgi import get_wsgi_application
from waitress import serve
application=get_wsgi_application()
from django.conf import settings
if settings.ATTENTION_PUBLIC_ONLY:
    serve(application,listen='127.0.0.1:8004',threads=4,trusted_proxy='127.0.0.1',trusted_proxy_headers={'x-forwarded-proto'},clear_untrusted_proxy_headers=True,max_request_body_size=65536)
else:
    from django.contrib.staticfiles.handlers import StaticFilesHandler
    serve(StaticFilesHandler(application),listen='127.0.0.1:8003',threads=4,max_request_body_size=65536)
