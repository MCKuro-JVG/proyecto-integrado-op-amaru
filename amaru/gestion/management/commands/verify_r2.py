"""Verificación remota explícita con datos ficticios y limpieza independiente."""
import uuid
import urllib.request
import urllib.error
import urllib.parse
import xml.etree.ElementTree as XML
from io import BytesIO
from PIL import Image
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.files.base import ContentFile
from django.db import connection
from django.utils import timezone
from gestion.storage import PrivateStorage, PublicStorage
from gestion.models import Product, Client, Prescription
from gestion.services import audit


def open_verification_url(url):
    request = urllib.request.Request(url, headers={
        'User-Agent': 'OpticasAmaru-R2-Verification/1.0',
        'Accept': 'image/png,application/pdf,*/*;q=0.8',
    })
    return urllib.request.urlopen(request, timeout=20)


def anonymous_auth_rejected(error):
    if error.code in (401, 403):
        return True
    if error.code != 400:
        return False
    try:
        response = XML.fromstring(error.read(65536))
    except (XML.ParseError, ValueError):
        return False
    # R2 responde así cuando falta Authorization; no aceptar otros errores 400.
    return (response.tag == 'Error' and response.findtext('Code') == 'InvalidArgument'
            and response.findtext('Message') == 'Authorization')


class Command(BaseCommand):
    help = 'Verifica objetos R2 ficticios, acceso firmado y referencias MariaDB; limpia sus datos temporales.'

    def handle(self, *args, **options):
        if not settings.R2_ENABLED:
            raise CommandError('R2 no está habilitado. No se ejecutó una prueba remota.')
        if connection.vendor != 'mysql':
            raise CommandError('La prueba requiere la conexión MariaDB configurada.')
        if Client.objects.filter(rut='99999999-9').exists():
            raise CommandError('RUT de prueba ocupado. No se modificaron clientes existentes.')

        marker = uuid.uuid4().hex
        buffer = BytesIO()
        Image.new('RGB', (200, 80), 'white').save(buffer, format='PNG')
        raw = buffer.getvalue()
        public, private = PublicStorage(), PrivateStorage()
        objects = []
        product = recipe = client = None
        failure = None
        cleanup_errors = []
        stage = 'consultar los buckets'
        try:
            public.connection.meta.client.head_bucket(Bucket=settings.R2_BUCKET_PUBLICO)
            private.connection.meta.client.head_bucket(Bucket=settings.R2_BUCKET_PRIVADO)
            stage = 'subir la imagen pública'
            pkey = public.save(f'catalogo/verificacion-{marker}.png', ContentFile(raw))
            objects.append((public, pkey, 'objeto público ficticio'))
            stage = 'subir la receta privada'
            rkey = private.save(f'recetas/verificacion-{marker}.png', ContentFile(raw))
            objects.append((private, rkey, 'objeto privado ficticio'))
            stage = 'guardar referencias en MariaDB'
            product = Product.objects.create(
                sku='VERIFY-' + marker, name='Imagen ficticia de verificación R2',
                category='armazon', image=pkey, active=False,
            )
            client = Client.objects.create(
                rut='99999999-9', name='FICTICIO VERIFICACIÓN R2',
                phone='00000000', category='particular', active=False,
            )
            recipe = Prescription.objects.create(client=client, issued_on=timezone.localdate(), file=rkey)
            if Prescription.objects.get(pk=recipe.pk).file.name != rkey:
                raise CommandError('La referencia de receta no coincide con el objeto privado.')
            if Product.objects.get(pk=product.pk).image.name != pkey:
                raise CommandError('La referencia de catálogo no coincide con el objeto público.')
            stage = 'recuperar la receta privada por S3'
            with private.open(rkey) as stored:
                if stored.read() != raw:
                    raise CommandError('El archivo privado recuperado no coincide con el original.')
            stage = 'descargar la imagen pública'
            with open_verification_url(public.url(pkey)) as response:
                if response.read() != raw:
                    raise CommandError('La imagen pública recuperada no coincide con el original.')
            stage = 'descargar la receta mediante URL firmada'
            signed_url = private.url(rkey)
            with open_verification_url(signed_url) as response:
                if response.read() != raw:
                    raise CommandError('La descarga firmada no coincide con el archivo privado original.')
            stage = 'comprobar el rechazo anónimo privado'
            unsigned = urllib.parse.urlunsplit(urllib.parse.urlsplit(signed_url)._replace(query='', fragment=''))
            try:
                with open_verification_url(unsigned):
                    raise CommandError('ALERTA: el objeto privado permitió acceso sin firma.')
            except urllib.error.HTTPError as exc:
                if not anonymous_auth_rejected(exc):
                    raise CommandError(f'Acceso anónimo no concluyente: HTTP {exc.code}') from exc
            audit(None, 'Verificación R2 ficticia con acceso privado restringido', recipe)
        except Exception as exc:
            failure = exc
        finally:
            # Un fallo de limpieza no debe impedir los demás intentos ni anunciar un éxito falso.
            for obj, label in ((recipe, 'receta ficticia'), (client, 'cliente ficticio'), (product, 'producto ficticio')):
                if obj is not None:
                    try:
                        obj.delete()
                    except Exception:
                        cleanup_errors.append(label)
            # Solo objetos cuya subida devolvió una clave; nunca nombres calculados pero no creados.
            for storage, key, label in reversed(objects):
                try:
                    storage.delete(key)
                except Exception:
                    cleanup_errors.append(label)

        if cleanup_errors:
            raise CommandError(
                'La verificación no se considera completada. Limpieza pendiente de: '
                + ', '.join(cleanup_errors) + '. Conserve el registro de esta ejecución para revisarla.'
            ) from failure
        if failure is not None:
            if isinstance(failure, CommandError):
                raise failure
            # No imprimir excepciones que puedan incorporar una URL firmada o parámetros privados.
            detail = f'HTTP {failure.code}' if isinstance(failure, urllib.error.HTTPError) else type(failure).__name__
            raise CommandError(f'La verificación R2 falló al {stage} ({detail}); se limpió lo creado.') from failure
        self.stdout.write(self.style.SUCCESS(
            'Buckets, subidas, descargas, referencias MariaDB, acceso firmado y rechazo S3 anónimo comprobados. '
            'Objetos y registros temporales eliminados. No se imprimieron URLs ni credenciales.'
        ))
        self.stdout.write(
            'Compruebe además mediante la API o el panel que el bucket privado no tiene r2.dev ni dominios públicos. '
            'El rechazo S3 por sí solo no verifica esas rutas alternativas.'
        )
