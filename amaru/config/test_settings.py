"""Pruebas aisladas: SQLite en memoria y archivos ficticios temporales, nunca datos existentes."""
import os
os.environ.setdefault('DJANGO_SECRET_KEY', 'only-test-not-a-production-secret')
from .settings import *
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
R2_ENABLED = False
STORAGES = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}
DEBUG = True
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = SECURE_SSL_REDIRECT = False
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
