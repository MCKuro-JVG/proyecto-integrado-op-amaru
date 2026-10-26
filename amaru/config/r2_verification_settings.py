"""Configuración exclusiva de verificación R2; no modifica el almacenamiento normal."""
from .settings import *
R2_ENABLED = True
STORAGES = {
    'default': {'BACKEND': 'gestion.storage.PrivateStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}
