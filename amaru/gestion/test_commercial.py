from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
from uuid import uuid4
from django.contrib.auth.models import Group, User
from django.core.cache import cache
from django.core.exceptions import ValidationError as ModelValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connections
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from .models import (Agreement, AgreementBenefit, AgreementRepresentative, Brand, Client, Inquiry, Inventory,
                     Order, PaymentVoucher, Product, ProductVariant, Quote, QuoteLine, StockMovement,
                     StockReservation, TransferPayment, Union, UnionMembership)
from .services import accept_receipt, convert_quote
from .stock import move, reserve_quote
from .test_api import png


class CommercialTests(TestCase):
    def setUp(self):
        cache.clear()
        self.media=TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        config=override_settings(MEDIA_ROOT=Path(self.media.name))
        config.enable()
        self.addCleanup(config.disable)
        call_command('configure_roles',verbosity=0)
        self.admin=User.objects.create_superuser('commerce-admin')
        self.seller=User.objects.create_user('commerce-seller')
        self.seller.groups.add(Group.objects.get(name='Vendedor'))
        self.owner=User.objects.create_user('commerce-owner')
        self.other=User.objects.create_user('commerce-other')
        self.person=Client.objects.create(user=self.owner,rut='12345678-5',name='Persona Ficticia',phone='+56900000000',email='owner@example.invalid',category='particular')
        Client.objects.create(user=self.other,rut='11111111-1',name='Otra Persona Ficticia',phone='+56900000001',category='particular')
        self.product=Product.objects.create(sku='DEMO-PARENT',name='Producto Ficticio',category='armazon',reference_price=10000)
        self.variant=ProductVariant.objects.create(product=self.product,sku='DEMO-VAR',barcode='DEMO-128')
        self.item=Inventory.objects.create(variant=self.variant,name=self.product.name,category='armazon',quantity=5,minimum=2)
        self.quote=Quote.objects.create(client=self.person,product_type='particular',category='particular',amount=20000,approved=True)
        QuoteLine.objects.create(quote=self.quote,product=self.product,quantity=2,unit_price=10000)

    def post(self,path,data,user=None):
        self.client.force_login(user or self.admin)
        return self.client.post('/api/'+path,data,content_type='application/json')

    def confirm(self):
        response=self.post(f'quotes/{self.quote.pk}/confirm-payment/',{'confirmed':True},self.seller)
        self.assertEqual(response.status_code,201,response.content)
        return response.json()

    def upload(self,payment,file=None):
        self.client.force_login(self.owner)
        return self.client.post(f'/api/payments/{payment["id"]}/voucher/',{'declared_amount':payment['amount'],
            'file':file or SimpleUploadedFile('demo.png',png(),content_type='image/png')})

    def review(self,payment,state='approved',expected='submitted'):
        voucher=PaymentVoucher.objects.filter(payment_id=payment['id']).latest('pk')
        return self.post(f'payments/{payment["id"]}/review/',{'state':state,'expected_state':expected,
            'voucher':voucher.pk,'observations':'Evidencia ficticia contrastada para prueba','bank_checked':True},self.seller)

    def approve_benefits(self):
        agreement=Agreement.objects.create(name='Convenio Ficticio')
        self.person.agreement=agreement
        self.person.save()
        Inquiry.objects.create(idempotency_key=uuid4(),client=self.person,agreement=agreement,kind='registro',name='Persona Ficticia',
            phone='+56900000000',email='owner@example.invalid',service='Convenio',reason='Prueba ficticia',
            verification_state='aprobada',agreement_role='titular')
        return agreement

    def test_worker_invalid_rut_returns_validation_and_no_membership(self):
        representative=User.objects.create_user('union-rep')
        agreement=Agreement.objects.create(name='Sindicato Ficticio')
        union=Union.objects.create(agreement=agreement,identifier='ficticio',state='active')
        AgreementRepresentative.objects.create(user=representative,agreement=agreement)
        result=self.post('union/workers/',{'name':'Trabajador Ficticio','rut':'12345678-9',
            'email':'worker@example.invalid','phone':'+56900000002','role':'titular'},representative)
        self.assertEqual(result.status_code,400,result.content)
        self.assertFalse(union.memberships.exists())

    def test_worker_registration_list_refresh_payload_and_duplicate(self):
        representative=User.objects.create_user('union-rep')
        agreement=Agreement.objects.create(name='Sindicato Ficticio')
        Union.objects.create(agreement=agreement,identifier='ficticio',state='active')
        AgreementRepresentative.objects.create(user=representative,agreement=agreement)
        payload={'name':'Trabajador Ficticio','rut':'12.345.678-5','email':'worker@example.invalid','phone':'+56900000002','role':'titular'}
        response=self.post('union/workers/',payload,representative)
        self.assertEqual(response.status_code,201,response.content)
        self.assertEqual(response.json()['worker']['account_state'],'Pendiente de activación')
        self.assertIn('created_at',response.json()['worker'])
        self.assertEqual(self.client.get('/api/union/portal/').json()['workers'][0]['name'],'Trabajador Ficticio')
        self.assertEqual(self.post('union/workers/',payload,representative).status_code,400)
        self.person.refresh_from_db()
        self.assertEqual(self.person.user,self.owner)

    def test_benefit_permissions_invalid_percentage_dates_and_decimal(self):
        agreement=Agreement.objects.create(name='Convenio Ficticio')
        data={'agreement':agreement.pk,'name':'Beneficio prueba','kind':'percent','value':'101','active':True}
        self.assertEqual(self.post('benefits/',data).status_code,400)
        data['value']='-1'
        self.assertEqual(self.post('benefits/',data).status_code,400)
        data.update(value='20',starts_on='2026-11-30',ends_on='2026-11-01')
        self.assertEqual(self.post('benefits/',data).status_code,400)
        data.update(starts_on=None,ends_on=None)
        self.assertEqual(self.post('benefits/',data,self.seller).status_code,403)
        self.assertEqual(self.post('benefits/',data).status_code,201)

    def test_single_best_benefit_snapshot_and_immutable_quote(self):
        agreement=self.approve_benefits()
        discount=AgreementBenefit.objects.create(agreement=agreement,name='20 por ciento ficticio',kind='percent',value=20,active=True)
        AgreementBenefit.objects.create(agreement=agreement,name='Fijo ficticio',kind='fixed',value=1000,active=True)
        payment=self.confirm()
        self.assertEqual(payment['amount'],'16000')
        self.assertEqual(payment['benefit']['discount'],'4000')
        discount.value=99
        discount.save()
        self.quote.refresh_from_db()
        self.assertEqual(self.quote.amount,16000)
        self.assertEqual(self.quote.benefit_snapshot['value'],'20.00')
        response=self.client.patch(f'/api/quotes/{self.quote.pk}/',{'amount':1},content_type='application/json')
        self.assertEqual(response.status_code,400)

    def test_expired_and_unverified_benefits_are_ineligible(self):
        agreement=Agreement.objects.create(name='Convenio Ficticio')
        self.person.agreement=agreement
        self.person.save()
        AgreementBenefit.objects.create(agreement=agreement,name='Sin validación',kind='percent',value=90,active=True)
        self.assertEqual(self.confirm()['amount'],'20000')
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get('/api/my-benefits/').json(),[])

    def test_expired_benefit_and_family_restriction(self):
        agreement=self.approve_benefits()
        AgreementBenefit.objects.create(agreement=agreement,name='Vencido',kind='fixed',value=5000,active=True,ends_on=timezone.localdate()-timedelta(days=1))
        AgreementBenefit.objects.create(agreement=agreement,name='Solo cargas',kind='fixed',value=5000,active=True,role='carga')
        self.assertEqual(self.confirm()['amount'],'20000')

    def test_payment_confirmation_requires_approved_quote_and_stock(self):
        self.quote.approved=False
        self.quote.save()
        self.assertEqual(self.post(f'quotes/{self.quote.pk}/confirm-payment/',{'confirmed':True}).status_code,400)
        self.quote.approved=True
        self.quote.save()
        self.item.quantity=1
        self.item.save()
        self.assertEqual(self.post(f'quotes/{self.quote.pk}/confirm-payment/',{'confirmed':True}).status_code,400)
        self.assertFalse(TransferPayment.objects.exists())

    def test_payment_idempotence_reservation_and_no_real_bank(self):
        result=self.confirm()
        again=self.post(f'quotes/{self.quote.pk}/confirm-payment/',{'confirmed':True})
        self.assertEqual(again.json()['id'],result['id'])
        self.assertEqual(TransferPayment.objects.count(),1)
        self.assertEqual(StockReservation.objects.get().quantity,2)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity,5)
        self.assertEqual(result['bank']['account_number'],'DEMO-NO-OPERATIVA')
        with self.assertRaises(ModelValidationError):
            convert_quote(self.quote.pk,self.seller)

    def test_voucher_privacy_validation_and_no_automatic_approval(self):
        payment=self.confirm()
        invalid=SimpleUploadedFile('attack.pdf',b'<html>bad</html>')
        self.assertEqual(self.upload(payment,invalid).status_code,400)
        self.assertEqual(self.upload(payment).status_code,201)
        self.assertEqual(TransferPayment.objects.get().state,'submitted')
        self.assertFalse(Order.objects.exists())
        voucher=PaymentVoucher.objects.get()
        for user in (self.other,):
            self.client.force_login(user)
            self.assertEqual(self.client.get(f'/api/payment-vouchers/{voucher.pk}/file/').status_code,404)
            self.assertEqual(self.client.get(f'/api/payments/{payment["id"]}/').status_code,404)
        self.client.logout()
        self.assertEqual(self.client.get(f'/api/payment-vouchers/{voucher.pk}/file/').status_code,403)
        self.client.force_login(self.owner)
        response=self.client.get(f'/api/payment-vouchers/{voucher.pk}/file/')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response['Cache-Control'],'private, no-store')
        self.assertTrue(b''.join(response.streaming_content))

    def test_rejection_resubmission_and_historical_voucher(self):
        payment=self.confirm()
        self.assertEqual(self.upload(payment).status_code,201)
        self.assertEqual(self.review(payment,'rejected').status_code,200)
        self.assertEqual(self.upload(payment).status_code,400)
        from PIL import Image
        from io import BytesIO
        image=BytesIO()
        Image.new('RGB',(50,50),'blue').save(image,'PNG')
        new=SimpleUploadedFile('nuevo.png',image.getvalue(),content_type='image/png')
        self.assertEqual(self.upload(payment,new).status_code,201)
        self.assertEqual(PaymentVoucher.objects.count(),2)
        self.assertEqual(self.review(payment).status_code,200)
        self.assertEqual(Order.objects.count(),1)
        self.assertEqual(self.review(payment).status_code,400)

    def test_approval_requires_amount_and_bank_check(self):
        payment=self.confirm()
        self.upload(payment)
        voucher=PaymentVoucher.objects.get()
        for data in ({'bank_checked':False},{'voucher':voucher.pk+1}):
            payload={'state':'approved','expected_state':'submitted','voucher':voucher.pk,'observations':'Revisión de ejemplo','bank_checked':True,**data}
            self.assertEqual(self.post(f'payments/{payment["id"]}/review/',payload,self.seller).status_code,400)
        self.assertEqual(TransferPayment.objects.get().state,'submitted')
        self.assertFalse(Order.objects.exists())

    def test_cancel_releases_stock(self):
        payment=self.confirm()
        response=self.post(f'payments/{payment["id"]}/review/',{'state':'cancelled','expected_state':'pending','observations':'Cancelación ficticia solicitada'},self.seller)
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(StockReservation.objects.get().state,'released')

    def test_order_cancellation_releases_reservation_and_is_idempotent(self):
        from django.db import transaction
        with transaction.atomic():
            reserve_quote(self.quote,self.seller)
        order=Order.objects.create(quote=self.quote,client=self.person,product_type='particular',category='particular')
        for _ in range(2):
            result=self.post(f'orders/{order.pk}/cancel/',{'confirmed':True,'reason':'Cancelación académica autorizada'},self.seller)
            self.assertEqual(result.status_code,200,result.content)
        order.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(order.status,'Cancelada')
        self.assertEqual(self.item.quantity,5)
        self.assertEqual(StockReservation.objects.get().state,'released')
        self.assertEqual(self.post(f'orders/{order.pk}/state/',{'status':'En fabricación'},self.seller).status_code,400)

    def test_paid_order_cancellation_requires_admin_and_preserves_payment(self):
        payment=self.confirm()
        self.upload(payment)
        self.assertEqual(self.review(payment).status_code,200)
        order=Order.objects.get()
        data={'confirmed':True,'reason':'Cancelación ficticia por revisión administrativa'}
        self.assertEqual(self.post(f'orders/{order.pk}/cancel/',data,self.seller).status_code,403)
        self.assertEqual(self.post(f'orders/{order.pk}/cancel/',data).status_code,200)
        self.assertEqual(TransferPayment.objects.get().state,'approved')
        self.assertEqual(StockReservation.objects.get().state,'released')

    def test_stock_movements_idempotent_no_negative_and_audit(self):
        key=uuid4()
        a=move(self.item.pk,self.admin,kind='entry',quantity=2,reason='Ingreso ficticio',operation=key)
        b=move(self.item.pk,self.admin,kind='entry',quantity=2,reason='Ingreso ficticio',operation=key)
        self.assertEqual(a.pk,b.pk)
        move(self.item.pk,self.admin,kind='exit',quantity=1,reason='Daño ficticio',operation=uuid4())
        move(self.item.pk,self.admin,kind='adjustment',quantity=3,reason='Conteo físico ficticio',operation=uuid4())
        with self.assertRaises(ValidationError):
            move(self.item.pk,self.admin,kind='exit',quantity=4,reason='Salida excesiva',operation=uuid4())
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity,3)
        self.assertEqual(list(StockMovement.objects.values_list('before','after')),[(5,7),(7,6),(6,3)])

    def test_reserved_stock_and_expiration(self):
        self.confirm()
        with self.assertRaises(ValidationError):
            move(self.item.pk,self.admin,kind='exit',quantity=4,reason='Salida sobre reserva',operation=uuid4())
        StockReservation.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
        move(self.item.pk,self.admin,kind='exit',quantity=4,reason='Reserva expirada',operation=uuid4())
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity,1)

    def test_inventory_search_barcode_sku_filters_and_permissions(self):
        self.client.force_login(self.seller)
        for term in ('DEMO-VAR','DEMO-128','Producto Ficticio',str(self.item.pk)):
            response=self.client.get('/api/stock/',{'q':term})
            self.assertEqual(response.status_code,200,response.content)
            self.assertEqual(response.json()['count'],1)
            self.assertNotIn('unit_cost',response.json()['results'][0])
        self.assertEqual(self.client.get('/api/stock/',{'stock':'low'}).json()['count'],0)
        self.assertEqual(self.client.get(f'/api/stock/{self.item.pk}/label/').status_code,200)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get('/api/stock/').status_code,403)

    def test_variant_duplicate_and_model_brand_validation(self):
        self.assertEqual(self.post('variants/',{'product':self.product.pk,'sku':'DIFFERENT','barcode':'DEMO-128','label':'Otra'}).status_code,400)
        brand=self.post('brands/',{'name':'Marca Ficticia'}).json()
        model=self.post('product-models/',{'name':'Modelo Ficticio','brand':brand['id']}).json()
        response=self.post('catalog-management/',{'sku':'TEST-X','name':'Nuevo ficticio','category':'armazon','model':model['id']})
        self.assertEqual(response.status_code,400)

    def test_seller_movement_permitted_and_cost_private(self):
        payload={'kind':'entry','quantity':2,'reason':'Ingreso de prueba','operation':str(uuid4())}
        self.assertEqual(self.post(f'stock/{self.item.pk}/movement/',payload,self.seller).status_code,200)
        payload.update(operation=str(uuid4()),unit_cost=999)
        self.assertEqual(self.post(f'stock/{self.item.pk}/movement/',payload,self.seller).status_code,403)

    def test_checkout_checks_stock_and_server_prices(self):
        payload={'items':[{'product':self.product.pk,'quantity':6,'variant':''}], 'mode':'compra',
                 'reason':'Solicitud ficticia','contact_authorized':True,'idempotency_key':str(uuid4())}
        self.assertEqual(self.post('checkout/',payload,self.owner).status_code,409)
        payload['items'][0]['quantity']=1
        result=self.post('checkout/',payload,self.owner)
        self.assertEqual(result.status_code,201,result.content)
        self.assertEqual(self.post('checkout/',payload,self.owner).status_code,200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity,5)

    def test_dispatch_updates_once_after_payment_and_receipt(self):
        payment=self.confirm()
        self.upload(payment)
        self.assertEqual(self.review(payment).status_code,200)
        order=Order.objects.get()
        order.status='Disponible para retiro'
        order.save()
        import base64
        signature='data:image/png;base64,'+base64.b64encode(png()).decode()
        receipt=accept_receipt(order.pk,self.seller,True,signature)
        self.assertTrue(receipt.pdf)
        again=accept_receipt(order.pk,self.seller,True,signature)
        self.assertEqual(receipt.pk,again.pk)
        order.refresh_from_db()
        self.assertEqual(order.status,'Entregada')
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity,3)
        self.assertEqual(StockMovement.objects.filter(kind='exit').count(),1)

    def test_existing_order_without_reservations_can_be_delivered(self):
        import base64
        order=Order.objects.create(quote=self.quote,client=self.person,product_type='particular',category='particular',status='Disponible para retiro')
        signature='data:image/png;base64,'+base64.b64encode(png()).decode()
        receipt=accept_receipt(order.pk,self.seller,True,signature)
        self.assertTrue(receipt.pdf)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity,3)
        self.assertEqual(StockReservation.objects.get(quote=self.quote).state,'consumed')


class StockConcurrencyTests(TransactionTestCase):
    @skipUnlessDBFeature('has_select_for_update')
    def test_two_reviewers_cannot_approve_payment_twice(self):
        from rest_framework.test import APIRequestFactory, force_authenticate
        from .commercial import review_payment
        call_command('configure_roles',verbosity=0)
        seller=User.objects.create_user('payment-reviewer')
        seller.groups.add(Group.objects.get(name='Vendedor'))
        seller.get_all_permissions()
        person=Client.objects.create(rut='12345678-5',name='Cliente Ficticio',phone='+56900000000',category='particular')
        product=Product.objects.create(sku='PAY-CONCURRENT',name='Producto Ficticio',category='repuesto')
        variant=ProductVariant.objects.create(product=product,sku='PAY-CONCURRENT-V')
        Inventory.objects.create(variant=variant,name='Producto Ficticio',category='repuesto',quantity=1)
        quote=Quote.objects.create(client=person,product_type='particular',category='particular',amount=100,approved=True)
        QuoteLine.objects.create(quote=quote,product=product,quantity=1,unit_price=100)
        payment=TransferPayment.objects.create(quote=quote,amount=100,state='submitted')
        voucher=PaymentVoucher.objects.create(payment=payment,file='prueba/ficticio.png',sha256='a'*64,declared_amount=100,submitted_by=seller)
        barrier=Barrier(2)
        def approve(_):
            connections.close_all()
            request=APIRequestFactory().post('/api/payments/review/',{'state':'approved','expected_state':'submitted',
                'voucher':voucher.pk,'observations':'Revisión ficticia concurrente','bank_checked':True},format='json')
            force_authenticate(request,user=seller)
            barrier.wait(timeout=10)
            try:
                return review_payment(request,pk=payment.pk).status_code
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(approve,range(2)))
        self.assertCountEqual(results,[200,400])
        self.assertEqual(Order.objects.filter(quote=quote).count(),1)

    @skipUnlessDBFeature('has_select_for_update')
    def test_two_quotes_cannot_reserve_last_unit(self):
        user=User.objects.create_user('reserve-worker')
        person=Client.objects.create(rut='12345678-5',name='Ficticio',phone='+56900000000',category='particular')
        product=Product.objects.create(sku='CONCURRENT',name='Última unidad ficticia',category='armazon')
        variant=ProductVariant.objects.create(product=product,sku='CONCURRENT-VAR')
        item=Inventory.objects.create(variant=variant,name='Última unidad',category='armazon',quantity=1)
        quotes=[Quote.objects.create(client=person,product_type='particular',category='particular',amount=1) for _ in range(2)]
        for q in quotes:
            QuoteLine.objects.create(quote=q,product=product,quantity=1,unit_price=1)
        barrier=Barrier(2)
        def reserve(pk):
            connections.close_all()
            barrier.wait(timeout=10)
            try:
                from django.db import transaction
                with transaction.atomic():
                    q=Quote.objects.select_for_update().get(pk=pk)
                    reserve_quote(q,user)
                return 'reserved'
            except ValidationError:
                return 'conflict'
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(reserve,[q.pk for q in quotes]))
        self.assertCountEqual(results,['reserved','conflict'])
        self.assertEqual(StockReservation.objects.filter(state='active').count(),1)
