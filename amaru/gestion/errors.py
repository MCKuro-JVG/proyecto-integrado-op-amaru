"""Respuestas de API sin mensajes internos de SQL, claves o rutas privadas."""
import logging
from django.db import IntegrityError,OperationalError
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.views import exception_handler
from rest_framework.response import Response
from botocore.exceptions import BotoCoreError,ClientError


def api_exception_handler(exc,context):
    response=exception_handler(exc,context)
    if response is not None:return response
    if isinstance(exc,DjangoValidationError):return Response({'detail':exc.messages},status=400)
    if isinstance(exc,IntegrityError):return Response({'detail':'El registro entra en conflicto con datos existentes. Actualice antes de reintentar.'},status=409)
    if isinstance(exc,(OperationalError,OSError,BotoCoreError,ClientError)):
        logging.getLogger(__name__).exception('Servicio no disponible en API')
        return Response({'detail':'No se pudo completar la operación con el servicio de datos o archivos.'},status=503)
    return None
