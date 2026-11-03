"""Instancia acadÃ©mica aislada. Nunca acepta la base habitual del proyecto."""
from .settings import *
if DATABASES['default']['NAME'] != 'opticas_amaru_qr_demo':
    raise RuntimeError('La demostraciÃ³n exige la base opticas_amaru_qr_demo.')
DEBUG=False
R2_ENABLED=False
STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}}
MEDIA_ROOT=BASE_DIR.parent/'.tools/attention/media'
ATTENTION_PUBLIC_ONLY=os.getenv('ATTENTION_PUBLIC_ONLY','false').lower()=='true'
SECURE_SSL_REDIRECT=False  # TLS finaliza en Cloudflare; origen solo en loopback.
SECURE_HSTS_SECONDS=0
SECURE_HSTS_INCLUDE_SUBDOMAINS=SECURE_HSTS_PRELOAD=False
SESSION_COOKIE_SECURE=CSRF_COOKIE_SECURE=ATTENTION_PUBLIC_ONLY
SESSION_COOKIE_NAME='amaru_qr_demo_session'
CSRF_COOKIE_NAME='amaru_qr_demo_csrf'
from urllib.parse import urlsplit
host=urlsplit(ATTENTION_PUBLIC_BASE_URL).hostname
ALLOWED_HOSTS=[host] if ATTENTION_PUBLIC_ONLY and host else ['127.0.0.1','localhost']
CSRF_TRUSTED_ORIGINS=[ATTENTION_PUBLIC_BASE_URL] if ATTENTION_PUBLIC_ONLY and host else []
if ATTENTION_PUBLIC_ONLY:
    SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO','https')
    ROOT_URLCONF='config.attention_public_urls'
    MIDDLEWARE=['gestion.attention_public.PublicBoundaryMiddleware']+MIDDLEWARE
CACHES={'default':{'BACKEND':'django.core.cache.backends.locmem.LocMemCache','LOCATION':'amaru-attention-demo'}}
# Un Ãºnico proceso Waitress; su cachÃ© mantiene lÃ­mites tras reiniciar el origen.
