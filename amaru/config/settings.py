from pathlib import Path
import os
from dotenv import load_dotenv
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(os.getenv('AMARU_ENV_FILE', str(BASE_DIR / '.env')))
SECRET_KEY = os.environ['DJANGO_SECRET_KEY']
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '127.0.0.1,localhost').split(',')
INSTALLED_APPS = ['django.contrib.admin','django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles','rest_framework','storages','gestion']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware','django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware','django.middleware.csrf.CsrfViewMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware','django.contrib.messages.middleware.MessageMiddleware','django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[BASE_DIR/'templates'],'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages','gestion.context.navigation']}}]
WSGI_APPLICATION = 'config.wsgi.application'
DB_ENGINE = os.getenv('DB_ENGINE', 'mysql')
DATABASES = {'default': {'ENGINE': 'django.db.backends.' + DB_ENGINE,
    'NAME': os.getenv('DB_NAME', 'opticas_amaru'), 'USER': os.getenv('DB_USER', 'amaru_app'),
    'PASSWORD': os.getenv('DB_PASSWORD', ''), 'HOST': os.getenv('DB_HOST', '127.0.0.1'),
    'PORT': os.getenv('DB_PORT', '3306'), 'CONN_HEALTH_CHECKS': True}}
if DB_ENGINE == 'mysql':
    DATABASES['default']['OPTIONS'] = {'charset': 'utf8mb4', 'init_command': "SET sql_mode='STRICT_TRANS_TABLES', default_storage_engine=INNODB", 'connect_timeout': 5}
AUTH_PASSWORD_VALIDATORS = [{'NAME':'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},{'NAME':'django.contrib.auth.password_validation.MinimumLengthValidator'},{'NAME':'django.contrib.auth.password_validation.CommonPasswordValidator'},{'NAME':'django.contrib.auth.password_validation.NumericPasswordValidator'}]
AUTHENTICATION_BACKENDS = ['gestion.auth.EmailBackend']
LANGUAGE_CODE = 'es-cl'
TIME_ZONE = 'America/Santiago'
USE_I18N = True
USE_TZ = True
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR/'static']
STATICFILES_DIRS += [('interfaz', BASE_DIR.parent / 'frontend_amaru')]
STATIC_ROOT = BASE_DIR/'staticfiles'
MEDIA_ROOT = BASE_DIR/'media'
MEDIA_URL = '/archivos/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True
DATA_UPLOAD_MAX_MEMORY_SIZE = 12*1024*1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024*1024
PUBLIC_BASE_URL = os.getenv('PUBLIC_BASE_URL','http://127.0.0.1:8000')

# No se publica MEDIA_ROOT. El acceso siempre pasa por una vista autorizada.
R2_ENABLED = os.getenv('R2_ENABLED', 'false').lower() == 'true'
R2_ACCESS_KEY_ID = os.getenv('R2_ACCESS_KEY_ID', '')
R2_SECRET_ACCESS_KEY = os.getenv('R2_SECRET_ACCESS_KEY', '')
R2_ACCOUNT_ID = os.getenv('R2_ACCOUNT_ID', '')
R2_ENDPOINT_URL = os.getenv('R2_ENDPOINT_URL') or f'https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com'
R2_BUCKET_PUBLICO = os.getenv('R2_BUCKET_PUBLICO', 'amaru-publico')
R2_BUCKET_PRIVADO = os.getenv('R2_BUCKET_PRIVADO', 'amaru-privado')
R2_DOMINIO_PUBLICO = os.getenv('R2_DOMINIO_PUBLICO', '')
R2_URL_SECONDS = int(os.getenv('R2_URL_SECONDS', '600'))
STORAGES = {'default': {'BACKEND': 'gestion.storage.PrivateStorage'},
            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}} if R2_ENABLED else {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}
REST_FRAMEWORK = {
    'EXCEPTION_HANDLER': 'gestion.errors.api_exception_handler',
    'DEFAULT_AUTHENTICATION_CLASSES': ['rest_framework.authentication.SessionAuthentication'],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination', 'PAGE_SIZE': 50,
    'DEFAULT_THROTTLE_CLASSES': ['rest_framework.throttling.AnonRateThrottle'],
    'DEFAULT_THROTTLE_RATES': {'anon': '30/min'},
}
SESSION_COOKIE_AGE = 1800
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', str(not DEBUG)).lower() == 'true'
SECURE_HSTS_SECONDS = 0 if DEBUG else 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
