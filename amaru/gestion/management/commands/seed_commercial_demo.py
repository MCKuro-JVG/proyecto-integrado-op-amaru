"""Datos académicos repetibles. Las credenciales nuevas se escriben en una ruta privada explícita."""
from io import BytesIO
import json
from pathlib import Path
import secrets
from uuid import uuid4
from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from PIL import Image, ImageDraw
from rest_framework.test import APIRequestFactory, force_authenticate
from gestion.commercial import confirm_payment, review_payment, submit_voucher
from gestion.models import (Agreement, AgreementBenefit, Brand, Client, Inquiry, Inventory, Product,
    ProductModel, ProductVariant, Quote, QuoteLine, StockCategory, Supplier, TransferPayment)
from gestion.stock import move


class Command(BaseCommand):
    help='Carga una demostración comercial ficticia e idempotente, sin alterar cuentas existentes.'

    def add_arguments(self, parser):
        parser.add_argument('--academic', action='store_true', required=True)
        parser.add_argument('--credentials-file', type=Path, required=True)

    def handle(self, *args, **options):
        from django.conf import settings
        private=options['credentials_file'].resolve()
        if private.is_relative_to(settings.BASE_DIR.parent.resolve()):
            # .tools queda excluido de Git, media y archivos estáticos.
            if not private.is_relative_to((settings.BASE_DIR.parent/'.tools').resolve()):
                raise CommandError('Las credenciales deben quedar fuera del código publicado.')
        values={}
        if private.exists():
            values=json.loads(private.read_text(encoding='utf-8'))
        accounts={}
        with transaction.atomic():
            for username,group in [('cliente_comercial_demo','Cliente'),('vendedor_comercial_demo','Vendedor'),('administrador_comercial_demo','Administrador')]:
                user,created=User.objects.get_or_create(username=username,defaults={'email':username+'@example.invalid'})
                if created:
                    password=secrets.token_urlsafe(20)
                    user.set_password(password)
                    user.is_staff=group=='Administrador'
                    user.save()
                    values[username]=password
                user.groups.add(Group.objects.get(name=group))
                accounts[group]=user
            customer=accounts['Cliente']
            person,created=Client.objects.get_or_create(user=customer,defaults={'rut':'99000000-K','name':'DEMO ACADÉMICA · Cliente comercial ficticio',
                'phone':'+56900000000','email':customer.email,'category':'particular'})
            agreement,_=Agreement.objects.get_or_create(name='DEMO ACADÉMICA · Convenio comercial ficticio')
            if created:
                person.agreement=agreement
                person.save(update_fields=['agreement'])
                Inquiry.objects.create(idempotency_key=uuid4(),client=person,agreement=agreement,kind='registro',name=person.name,phone=person.phone,email=person.email,
                    service='Demostración',reason='Afiliación ficticia preparada para revisión académica',registration_rut=person.rut,
                    verification_state='aprobada',agreement_role='titular')
            for name,kind,value in [('DEMO · Descuento 10 %','percent',10),('DEMO · Aporte ficticio','contribution',1500)]:
                AgreementBenefit.objects.get_or_create(agreement=agreement,name=name,defaults={'kind':kind,'value':value,'active':True,
                    'conditions':'Condición exclusivamente ficticia para demostración académica.'})
            brand,_=Brand.objects.get_or_create(name='Marca Ficticia Amaru Demo')
            model,_=ProductModel.objects.get_or_create(brand=brand,name='Modelo Ficticio A100')
            category,_=StockCategory.objects.get_or_create(name='Accesorios de demostración')
            supplier,_=Supplier.objects.get_or_create(name='Proveedor Ficticio de Demostración',defaults={'email':'proveedor@example.invalid','contact':'Contacto ficticio'})
            for code,qty,minimum in [('DISP',30,5),('BAJO',2,5),('CERO',0,3)]:
                product,_=Product.objects.get_or_create(sku='DEMO-COM-'+code,defaults={'name':'DEMO · Accesorio ficticio '+code,'category':'repuesto',
                    'stock_category':category,'brand':brand,'model':model,'reference_price':10000,
                    'description':'Producto ficticio sin utilización comercial.','variants':['Negro','Azul']})
                for color in product.variants:
                    variant,_=ProductVariant.objects.get_or_create(product=product,label=color,defaults={'sku':product.sku+'-'+color.upper(),
                        'barcode':'INTERNO-'+code+'-'+color.upper(),'color':color,'supplier':supplier})
                    item,new=Inventory.objects.get_or_create(variant=variant,defaults={'name':product.name+' '+color,'category':'repuesto','minimum':minimum,'location':'Estante ficticio A1'})
                    if new and qty:
                        move(item.pk,accounts['Administrador'],kind='entry',quantity=qty,reason='Saldo inicial ficticio',operation=uuid4(),supplier=supplier,unit_cost=5000)
                        if code=='DISP':
                            move(item.pk,accounts['Administrador'],kind='exit',quantity=1,reason='Salida ficticia por muestra',operation=uuid4())
            product=Product.objects.get(sku='DEMO-COM-DISP')
            from django.conf import settings
            factory=APIRequestFactory(HTTP_HOST=settings.ALLOWED_HOSTS[0],HTTP_X_FORWARDED_PROTO='https')
            def invoke(view,user,path,data,format='json',**kwargs):
                req=factory.post(path,data,format=format)
                force_authenticate(req,user=user)
                result=view(req,**kwargs)
                if result.status_code not in (200,201):
                    raise CommandError(f'No se completó la demostración de {path}: {result.status_code}')
                return result.data
            for state in ('pending','submitted','approved','rejected'):
                note='DEMO COMERCIAL · '+state
                if Quote.objects.filter(notes=note,client=person).exists():
                    continue
                quote=Quote.objects.create(client=person,product_type='particular',category='convenio',agreement=agreement,amount=10000,approved=True,
                    notes=note,characteristics={'frame':'Accesorio ficticio','crystal':'No corresponde','focus':'monofocal'})
                QuoteLine.objects.create(quote=quote,product=product,product_name=product.name,variant='Negro',quantity=1,unit_price=10000)
                payment=invoke(confirm_payment,accounts['Vendedor'],'/api/quotes/confirm-payment/',{'confirmed':True},pk=quote.pk)
                if state!='pending':
                    image=Image.new('RGB',(640,240),'white')
                    draw=ImageDraw.Draw(image)
                    draw.text((24,25),'COMPROBANTE FICTICIO - SIN TRANSFERENCIA REAL',fill='black')
                    draw.text((24,75),'DEMOSTRACION ACADEMICA - '+state,fill='black')
                    buffer=BytesIO()
                    image.save(buffer,'PNG')
                    submitted=invoke(submit_voucher,customer,'/api/payments/voucher/',{'declared_amount':payment['amount'],
                        'file':SimpleUploadedFile('comprobante-demo.png',buffer.getvalue(),content_type='image/png')},format='multipart',pk=payment['id'])
                    if state in ('approved','rejected'):
                        invoke(review_payment,accounts['Vendedor'],'/api/payments/review/',{'state':state,'expected_state':'submitted',
                            'voucher':submitted['vouchers'][-1]['id'],'bank_checked':True,'observations':'Revisión ficticia preparada para demostración académica.'},pk=payment['id'])
        private.parent.mkdir(parents=True,exist_ok=True)
        private.write_text(json.dumps(values,ensure_ascii=False,indent=2),encoding='utf-8')
        try:
            private.chmod(0o600)
        except OSError:
            pass
        self.stdout.write('Demostración comercial preparada. Se conservaron cuentas y datos previos. Credenciales nuevas guardadas únicamente en el archivo privado indicado.')
