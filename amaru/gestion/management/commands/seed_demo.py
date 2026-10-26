import secrets
import json
from io import BytesIO
from datetime import date
from pathlib import Path
from PIL import Image
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User,Group,Permission
from django.core.files.base import ContentFile
from django.conf import settings
from gestion.models import *
from gestion.services import audit,record_consent,convert_quote
class Command(BaseCommand):
    help='Crear grupos y datos DEMO; no restablece contraseñas existentes.'
    def handle(self,*args,**kwargs):
        admin,_=Group.objects.get_or_create(name='Administrador')
        admin.permissions.set(Permission.objects.filter(content_type__app_label__in=['gestion','auth','admin']))
        staff,_=Group.objects.get_or_create(name='Personal de atención')
        staff.permissions.set(Permission.objects.filter(content_type__app_label='gestion').exclude(codename__startswith='delete_').exclude(content_type__model__in=['audit','siteconfiguration','consent','agreement']))
        clientgroup,_=Group.objects.get_or_create(name='Cliente')
        creds={}
        for username,group in [('admin_demo',admin),('personal_demo',staff),('cliente_demo',clientgroup)]:
            u,created=User.objects.get_or_create(username=username,defaults={'email':username+'@demo.example','first_name':'DEMO','last_name':group.name,'is_staff':group==admin})
            if created:
                password=secrets.token_urlsafe(15);u.set_password(password);u.save();creds[username]=password
            u.groups.add(group)
        if creds:
            p=settings.BASE_DIR/'demo-credentials.json'
            p.write_text(json.dumps(creds),encoding='utf-8')
        agreement,_=Agreement.objects.get_or_create(name='DEMO · Convenio de prueba')
        c,created=Client.objects.get_or_create(rut='12345678-5',defaults={'name':'DEMO Cliente de prueba','phone':'+56 9 0000 0000','email':'cliente@demo.example','category':'particular','consent':False,'user':User.objects.get(username='cliente_demo')})
        actor=User.objects.get(username='personal_demo')
        if created:record_consent(c,actor);audit(actor,'Cliente DEMO creado',c)
        if not c.prescriptions.exists():
            img=Image.new('RGB',(900,500),'white');from PIL import ImageDraw
            draw=ImageDraw.Draw(img);draw.text((40,40),'DEMO - RECETA DE PRUEBA - SIN DATOS MEDICOS REALES',fill='black')
            b=BytesIO();img.save(b,format='PNG')
            p=Prescription(client=c,issued_on=timezone.localdate(),actor=actor);p.file.save('demo.png',ContentFile(b.getvalue()));audit(actor,'Receta DEMO cargada',p)
        Inventory.objects.get_or_create(name='DEMO · Armazón de seguridad',defaults={'category':'seguridad','quantity':10})
        Inventory.objects.get_or_create(name='DEMO · Repuesto varilla',defaults={'category':'repuesto','quantity':5})
        for sku,name,category,description in [
            ('DEMO-PARTICULAR','DEMO · Lentes particulares','armazon','Referencia académica de armazón y lentes ópticos; sin disponibilidad comercial confirmada.'),
            ('DEMO-SEGURIDAD','DEMO · Lentes de seguridad','seguridad','Referencia académica para orientación de lentes de seguridad.'),
            ('DEMO-CRISTAL','DEMO · Cristales','cristal','Referencia académica de cristales monofocales o multifocales.')]:
            Product.objects.get_or_create(sku=sku,defaults={'name':name,'category':category,'description':description})
        SiteConfiguration.objects.get_or_create(pk=1)
        if not Quote.objects.filter(client=c).exists():
            quote=Quote.objects.create(client=c,prescription=c.prescriptions.order_by('-issued_on').first(),category='particular',product_type='seguridad',characteristics={'security_model':'DEMO Seguridad','security_color':'blanco','focus':'monofocal'},amount=30000,approved=True,notes='DEMO · Cotización de prueba académica, valor ficticio.',actor=actor)
            audit(actor,'Cotización DEMO creada',quote)
            convert_quote(quote.pk,actor)
        from django.core.management import call_command
        call_command('configure_roles')
        self.stdout.write(self.style.SUCCESS('Datos ficticios preparados. Las nuevas credenciales están en demo-credentials.json (excluido de Git).'))
