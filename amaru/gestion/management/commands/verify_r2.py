"""Prueba explícita con archivos ficticios. No habilita buckets ni modifica permisos."""
import uuid
import urllib.request
import urllib.error
from io import BytesIO
from PIL import Image
from django.conf import settings
from django.core.management.base import BaseCommand,CommandError
from django.core.files.base import ContentFile
from django.db import connection
from gestion.storage import PrivateStorage,PublicStorage
from gestion.models import Product,Client,Prescription
from gestion.services import audit
from django.utils import timezone


class Command(BaseCommand):
    help='Comprueba subidas R2 pública/privada y referencias SQL con datos ficticios. Requiere R2_ENABLED=True.'
    def handle(self,*args,**options):
        if not settings.R2_ENABLED:raise CommandError('R2 no está habilitado. No se ejecutó una prueba remota.')
        if connection.vendor!='mysql':raise CommandError('La prueba requiere la conexión MariaDB configurada.')
        marker=uuid.uuid4().hex
        buffer=BytesIO();Image.new('RGB',(200,80),'white').save(buffer,format='PNG');raw=buffer.getvalue()
        public,private=PublicStorage(),PrivateStorage()
        pkey=f'catalogo/verificacion-{marker}.png';rkey=f'recetas/verificacion-{marker}.png'
        product=None;recipe=None;client=None
        try:
            pkey=public.save(pkey,ContentFile(raw));rkey=private.save(rkey,ContentFile(raw))
            product=Product.objects.create(sku='VERIFY-'+marker,name='Imagen ficticia de verificación R2',category='armazon',image=pkey,active=False)
            # Usar un RUT ficticio reservado de prueba solo si no existe; jamás modificar clientes previos.
            if Client.objects.filter(rut='99999999-9').exists():raise CommandError('RUT de prueba ocupado. No se modificaron clientes existentes.')
            client=Client.objects.create(rut='99999999-9',name='FICTICIO VERIFICACIÓN R2',phone='00000000',category='particular',active=False)
            recipe=Prescription.objects.create(client=client,issued_on=timezone.localdate(),file=rkey)
            assert Prescription.objects.get(pk=recipe.pk).file.name==rkey
            assert private.open(rkey).read()==raw
            assert urllib.request.urlopen(public.url(pkey),timeout=20).read()==raw
            signed=private.url(rkey)
            assert urllib.request.urlopen(signed,timeout=20).read()==raw
            unsigned=settings.R2_ENDPOINT_URL.rstrip('/')+'/'+settings.R2_BUCKET_PRIVADO+'/'+rkey
            try:
                urllib.request.urlopen(unsigned,timeout=20)
                raise CommandError('ALERTA: el objeto privado permitió acceso sin firma.')
            except urllib.error.HTTPError as exc:
                if exc.code not in (401,403):raise CommandError(f'Acceso anónimo no concluyente: HTTP {exc.code}')
            audit(None,'Verificación R2 ficticia con acceso privado restringido',recipe)
            self.stdout.write(self.style.SUCCESS('Subida, recuperación firmada, rechazo de la ruta S3 anónima y referencias MariaDB comprobados. No se imprimieron URLs ni claves.'))
            self.stdout.write('Confirme además en Cloudflare que el bucket privado no tiene r2.dev, dominio público ni reglas de acceso público. El rechazo S3 no verifica esas rutas alternativas.')
        finally:
            # La bitácora conserva la referencia del evento; los datos y objetos ficticios se eliminan.
            if recipe:recipe.delete()
            if client:client.delete()
            if product:product.delete()
            private.delete(rkey);public.delete(pkey)
