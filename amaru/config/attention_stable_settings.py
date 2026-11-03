"""Origen duradero de atención, aislado de la base habitual y sin dominio inventado."""
from .attention_demo_settings import *
from django.core.exceptions import ImproperlyConfigured
from urllib.parse import urlsplit
ATTENTION_PUBLIC_ONLY=True
DEBUG=False
ROOT_URLCONF='config.attention_public_urls'
if 'gestion.attention_public.PublicBoundaryMiddleware' not in MIDDLEWARE:
    MIDDLEWARE=['gestion.attention_public.PublicBoundaryMiddleware']+MIDDLEWARE
SESSION_COOKIE_SECURE=CSRF_COOKIE_SECURE=True
SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO','https')
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
# No solicitar inclusión en listas preload para un dominio que aún no se administra.
SECURE_HSTS_PRELOAD=False
SILENCED_SYSTEM_CHECKS=['security.W021']
if ATTENTION_PUBLIC_BASE_URL:
    parsed=urlsplit(ATTENTION_PUBLIC_BASE_URL)
    if (parsed.scheme!='https' or not parsed.hostname or parsed.hostname in ('127.0.0.1','localhost','::1')
        or parsed.username or parsed.password or parsed.port not in (None,443) or parsed.query or parsed.fragment or parsed.path not in ('','/')):
        raise ImproperlyConfigured('ATTENTION_PUBLIC_BASE_URL debe ser un origen HTTPS válido.')
    ALLOWED_HOSTS=[parsed.hostname]
    CSRF_TRUSTED_ORIGINS=[ATTENTION_PUBLIC_BASE_URL.rstrip('/')]
else:
    # Solo preflight local hasta disponer de un dominio real.
    ALLOWED_HOSTS=['127.0.0.1','localhost']
    CSRF_TRUSTED_ORIGINS=[]
ATTENTION_URL_FILE=str(BASE_DIR.parent/'.tools/stability/no-quick-tunnel.json')

OPERATIONAL_LOG_DIR=BASE_DIR.parent/'.tools/stability/runtime'
OPERATIONAL_LOG_DIR.mkdir(parents=True,exist_ok=True)
LOGGING={'version':1,'disable_existing_loggers':False,
    'filters':{'safe':{'()':'gestion.operational_logging.SafeOperationalFilter'}},
    'formatters':{'brief':{'format':'{asctime} {levelname} {name} {message}','style':'{'}},
    'handlers':{'operational':{'class':'logging.handlers.RotatingFileHandler','filename':str(OPERATIONAL_LOG_DIR/'origin.log'),'maxBytes':5242880,'backupCount':4,'encoding':'utf-8','formatter':'brief','filters':['safe']}},
    'root':{'handlers':['operational'],'level':'WARNING'},
    'loggers':{'django':{'handlers':['operational'],'level':'WARNING','propagate':False}}}
