"""R2 explícito: documentos privados por defecto; imágenes públicas por campo."""
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import FileSystemStorage
from storages.backends.s3 import S3Storage


class PrivateStorage(S3Storage):
    def __init__(self, **kwargs):
        if settings.R2_BUCKET_PUBLICO==settings.R2_BUCKET_PRIVADO:
            raise ImproperlyConfigured('Los buckets público y privado deben ser distintos.')
        if not all((settings.R2_ACCESS_KEY_ID, settings.R2_SECRET_ACCESS_KEY, settings.R2_ACCOUNT_ID)):
            raise ImproperlyConfigured('Configure las credenciales R2 en el entorno del servidor.')
        super().__init__(access_key=settings.R2_ACCESS_KEY_ID, secret_key=settings.R2_SECRET_ACCESS_KEY,
            endpoint_url=settings.R2_ENDPOINT_URL, region_name='auto', signature_version='s3v4',
            bucket_name=settings.R2_BUCKET_PRIVADO, default_acl=None, custom_domain=None,
            querystring_auth=True, querystring_expire=settings.R2_URL_SECONDS,
            file_overwrite=False, object_parameters={'CacheControl': 'private, no-store'}, **kwargs)


class PublicStorage(S3Storage):
    def __init__(self, **kwargs):
        if settings.R2_BUCKET_PUBLICO==settings.R2_BUCKET_PRIVADO:
            raise ImproperlyConfigured('Los buckets público y privado deben ser distintos.')
        if not settings.R2_DOMINIO_PUBLICO:
            raise ImproperlyConfigured('Configure R2_DOMINIO_PUBLICO para imágenes del catálogo.')
        super().__init__(access_key=settings.R2_ACCESS_KEY_ID, secret_key=settings.R2_SECRET_ACCESS_KEY,
            endpoint_url=settings.R2_ENDPOINT_URL, region_name='auto', signature_version='s3v4',
            bucket_name=settings.R2_BUCKET_PUBLICO, default_acl=None,
            custom_domain=settings.R2_DOMINIO_PUBLICO, querystring_auth=False, file_overwrite=False, **kwargs)


def private_storage():
    return PrivateStorage() if settings.R2_ENABLED else FileSystemStorage()


def public_storage():
    # En local tampoco se expone MEDIA_ROOT: se entrega solo la imagen pública solicitada.
    return PublicStorage() if settings.R2_ENABLED else FileSystemStorage()
