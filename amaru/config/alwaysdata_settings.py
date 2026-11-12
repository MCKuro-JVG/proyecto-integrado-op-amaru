"""Perfil académico con una base independiente y un único origen HTTPS."""
import os
import re
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

# La instalación remota requiere un entorno explícito. Evita cargar el .env local.
env_file = os.environ.get("AMARU_ENV_FILE")
if not env_file or not Path(env_file).is_absolute() or not Path(env_file).is_file():
    raise ImproperlyConfigured("AMARU_ENV_FILE debe indicar un archivo privado absoluto.")
load_dotenv(env_file)

required = ("ALWAYSDATA_HOST", "DJANGO_SECRET_KEY", "DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")
if any(not os.getenv(key) for key in required):
    raise ImproperlyConfigured("Faltan variables obligatorias para el perfil alwaysdata.")

host = os.environ["ALWAYSDATA_HOST"]
if not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.alwaysdata\.net", host):
    raise ImproperlyConfigured("ALWAYSDATA_HOST debe ser el subdominio asignado a la cuenta.")
account = host.split(".")[0]
if os.environ["DB_HOST"] != f"mysql-{account}.alwaysdata.net":
    raise ImproperlyConfigured("DB_HOST debe ser el servidor MariaDB de la cuenta alwaysdata.")
if not re.fullmatch(r"[a-z0-9_-]+_amaru_demo", os.environ["DB_NAME"]) or not os.environ["DB_NAME"].startswith(account + "_"):
    raise ImproperlyConfigured("DB_NAME debe pertenecer a la cuenta y terminar en _amaru_demo.")
if os.getenv("DB_ENGINE", "mysql") != "mysql":
    raise ImproperlyConfigured("El perfil alwaysdata requiere MariaDB.")
if len(os.environ["DJANGO_SECRET_KEY"]) < 50:
    raise ImproperlyConfigured("Genera una clave de Django nueva de al menos 50 caracteres.")

from .settings import *  # noqa: E402,F403

# MariaDB exige TLS para el usuario de la aplicación. Comprueba también el hostname.
DATABASES['default']['OPTIONS'].update(
    ssl_mode='VERIFY_IDENTITY',
    ssl={'ca': os.getenv('ALWAYSDATA_DB_CA', '/etc/ssl/certs/ca-certificates.crt')},
)

DEBUG = False
ALLOWED_HOSTS = [host]
PUBLIC_BASE_URL = ATTENTION_PUBLIC_BASE_URL = f"https://{host}"
ATTENTION_URL_FILE = ""
CSRF_TRUSTED_ORIGINS = [PUBLIC_BASE_URL]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True
SESSION_COOKIE_NAME = "amaru_academico_session"
CSRF_COOKIE_NAME = "amaru_academico_csrf"
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_PRELOAD = False
# El subdominio pertenece al proveedor. No se pide HSTS para sus subdominios o preload.
SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W021"]

# Los documentos ficticios se conservan fuera de STATIC_ROOT y del código desplegado.
R2_ENABLED = False
MEDIA_ROOT = Path(env_file).resolve().parent / "media"
if MEDIA_ROOT.is_relative_to(BASE_DIR.parent):
    raise ImproperlyConfigured("El archivo de entorno y media deben quedar fuera del repositorio.")
# Una raíz nueva evita sobrescribir archivos que WhiteNoise ya indexó.
static_release = os.getenv("AMARU_STATIC_RELEASE")
if static_release:
    if not re.fullmatch(r"[a-f0-9]{12}", static_release):
        raise ImproperlyConfigured("AMARU_STATIC_RELEASE debe ser un identificador Git de 12 caracteres.")
    STATIC_ROOT = Path(env_file).resolve().parent / "static-releases" / static_release
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
ROOT_URLCONF = "config.alwaysdata_urls"
