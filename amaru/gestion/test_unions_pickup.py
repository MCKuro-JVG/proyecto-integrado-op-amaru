from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import BytesIO
from pathlib import Path
import base64
import tempfile
from threading import Barrier
from uuid import uuid4

from django.contrib.auth.models import Group, User
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connections
from django.test import Client as Browser, TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.utils import timezone
from reportlab.pdfgen import canvas

from .models import (
    AccessInvitation, Agreement, Audit, Client, Inquiry, Order, PickupCode, Prescription,
    Product, Quote, Receipt, Union, UnionDocument, UnionMembership,
)
from .pickup import READY
from .services import accept_receipt
from .test_api import png

PASSWORD = 'Prueba-Optica.4728-demo'


def pdf():
    stream = BytesIO()
    doc = canvas.Canvas(stream)
    doc.drawString(45, 750, 'DOCUMENTO FICTICIO PARA PRUEBAS. SIN EFECTOS CONTRACTUALES.')
    doc.save()
    return SimpleUploadedFile('demostracion.pdf', stream.getvalue(), content_type='application/pdf')


def post(browser, path, payload):
    return browser.post('/api/' + path, payload, content_type='application/json')


def token(response):
    return response.json()['invitation']['url'].split('#token=', 1)[1]


def account(name, group=None):
    user = User.objects.create_user(name, password=PASSWORD)
    if group:
        user.groups.add(Group.objects.get(name=group))
    browser = Browser()
    browser.force_login(user)
    return browser, user


def private_media(test):
    directory = tempfile.TemporaryDirectory()
    test.addCleanup(directory.cleanup)
    settings = override_settings(MEDIA_ROOT=Path(directory.name))
    settings.enable()
    test.addCleanup(settings.disable)


class UnionFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        private_media(self)
        call_command('configure_roles', verbosity=0)
        self.admin, self.administrator = account('administracion', 'Administrador')
        self.sales, self.seller = account('ventas', 'Vendedor')
        self.customer, self.person = account('cliente-particular', 'Cliente')

    def provision(self, slug='alpha', activate=True):
        today = timezone.localdate()
        payload = {
            'name': 'Sindicato ficticio ' + slug, 'identifier': slug,
            'institutional_details': 'Registro académico', 'contact_name': 'Representante Ficticio',
            'contact_email': slug+'@example.invalid', 'starts_on': today,
            'ends_on': today + timedelta(days=30), 'allow_dependents': True,
        }
        result = post(self.admin, 'unions/', payload)
        self.assertEqual(result.status_code, 201, result.content)
        union = Union.objects.get(identifier=slug)
        invite = token(result)
        stored = AccessInvitation.objects.get(union=union)
        self.assertNotEqual(stored.digest, invite)
        visitor = Browser()
        response = post(visitor, 'invitation/claim/', {'token': invite, 'password': PASSWORD, 'accepted': True})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(post(visitor, 'invitation/claim/', {'token': invite, 'accepted': True}).status_code, 400)
        self.assertEqual(post(visitor, 'login/', {'username': payload['contact_email'], 'password': PASSWORD}).status_code, 200)
        if activate:
            self.activate(union, visitor)
        return union, visitor

    def activate(self, union, representative):
        payload = {'action': 'activate', 'reviewed': True, 'note': 'Revisión ficticia'}
        route = f'unions/{union.pk}/manage/'
        self.assertEqual(post(self.admin, route, payload).status_code, 400)
        upload = self.admin.post(f'/api/unions/{union.pk}/document/', {'file': pdf()})
        self.assertEqual(upload.status_code, 201, upload.content)
        doc = UnionDocument.objects.get(union=union, version=1)
        self.assertEqual(self.sales.get(f'/api/union-documents/{doc.pk}/').status_code, 403)
        download = representative.get(f'/api/union-documents/{doc.pk}/')
        self.assertEqual(download.status_code, 200)
        self.assertTrue(b''.join(download.streaming_content).startswith(b'%PDF-'))
        self.assertEqual(post(representative, 'union/sign/', {'document': doc.pk, 'sha256': 'a'*64, 'accepted': True}).status_code, 400)
        self.assertEqual(post(representative, 'union/sign/', {'document': doc.pk, 'sha256': doc.sha256, 'accepted': True}).status_code, 200)
        self.assertEqual(post(self.sales, route, payload).status_code, 403)
        self.assertEqual(post(self.admin, route, {**payload, 'reviewed': False}).status_code, 400)
        self.assertEqual(post(self.admin, route, payload).status_code, 200)
        union.refresh_from_db()
        self.assertTrue(union.agreement.available)
        doc.refresh_from_db()
        self.assertEqual(doc.signed_by.email, union.agreement.contact_email)
        self.assertEqual(doc.organization_name, union.agreement.name)

    def make_worker(self, representative, **extra):
        form = {'name':'Trabajador Ficticio', 'rut':'12.345.678-5', 'email':'trabajador@example.invalid',
                'phone':'+56900000000', 'role':'titular'}
        return post(representative, 'union/workers/', form | extra)

    def worker(self, representative):
        response = self.make_worker(representative)
        self.assertEqual(response.status_code, 201, response.content)
        invitation = token(response)
        worker = Browser()
        response = post(worker, 'invitation/claim/', {'token': invitation, 'accepted': True, 'password': PASSWORD})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(post(worker, 'login/', {'username':'trabajador@example.invalid','password':PASSWORD}).status_code, 200)
        return worker, Client.objects.get(rut='12345678-5')

    def test_admin_controls_organization_and_representative_is_scoped(self):
        union, representative = self.provision(activate=False)
        self.assertEqual(self.make_worker(representative).status_code, 403)
        self.assertEqual(post(self.sales, 'unions/', {}).status_code, 403)
        self.assertEqual(self.customer.get('/api/union/portal/').status_code, 403)
        self.activate(union, representative)
        second, other = self.provision('beta')
        result = self.make_worker(representative, union=second.pk, is_staff=True)
        self.assertEqual(result.status_code, 201)
        row = UnionMembership.objects.get()
        self.assertEqual(row.union_id, union.pk)
        self.assertEqual(self.make_worker(representative).status_code, 400)
        self.assertEqual(post(other, f'union/workers/{row.pk}/', {'action':'disable'}).status_code, 404)
        self.assertEqual(other.get('/api/union/portal/').json()['workers'], [])
        self.assertEqual(other.get(f'/api/union-documents/{union.documents.get().pk}/').status_code, 404)
        self.assertEqual(representative.get('/api/clients/').status_code, 403)
        self.assertEqual(representative.get('/api/catalog-management/').status_code, 403)

    def test_existing_owner_must_accept_and_admin_approve_without_overwriting_ficha(self):
        _, representative = self.provision()
        client = Client.objects.create(rut='12345678-5', name='Titular original', phone='222222222',
                                       email='original@example.invalid', category='particular', user=self.person)
        invitation = token(self.make_worker(representative))
        payload = {'token':invitation,'accepted':True,'password':PASSWORD}
        self.assertEqual(post(Browser(), 'invitation/claim/', payload).status_code, 403)
        self.assertEqual(post(self.sales, 'invitation/claim/', payload).status_code, 403)
        self.assertEqual(post(self.customer, 'invitation/claim/', payload).json()['state'], 'review')
        row = UnionMembership.objects.get()
        self.assertEqual(row.state, 'pending')
        self.assertEqual(post(representative, f'union/workers/{row.pk}/', {'action':'review','note':'Prueba'}).status_code, 403)
        self.assertEqual(post(self.admin, f'union/workers/{row.pk}/', {'action':'review','note':'Identidad revisada'}).status_code, 200)
        client.refresh_from_db()
        self.assertEqual((client.name, client.email, client.user_id), ('Titular original','original@example.invalid',self.person.pk))
        self.assertIsNone(client.agreement_id)

    def test_mining_catalog_requires_active_affiliation_and_own_recipe(self):
        union, representative = self.provision()
        worker, client = self.worker(representative)
        self.assertFalse(client.user.get_all_permissions())
        self.assertEqual(worker.get('/api/union/portal/').status_code, 403)
        product = Product.objects.create(sku='MIN-QA', name='Modelo ficticio', category='seguridad',
                                         mining_only=True, reference_price=40000, requires_prescription=True,
                                         mining_image=SimpleUploadedFile('demo.png', png()))
        self.assertEqual(self.customer.get('/api/products/?scope=mining').status_code, 403)
        self.assertEqual(self.customer.get(f'/api/products/{product.pk}/image/').status_code, 404)
        self.assertEqual(worker.get('/api/products/').json()['count'], 0)
        self.assertEqual(worker.get('/api/products/?scope=mining').json()['count'], 1)
        for browser, path in [(worker, 'products'), (self.sales, 'catalog-management')]:
            image = browser.get(f'/api/{path}/{product.pk}/image/')
            self.assertEqual(image.status_code, 200)
            self.assertTrue(b''.join(image.streaming_content).startswith(b'\x89PNG'))
        payload = {'items':[{'product':product.pk,'quantity':1}],'mode':'cotizacion','reason':'Solicitud de prueba',
                   'contact_authorized':True, 'idempotency_key':str(uuid4())}
        self.assertEqual(post(worker, 'checkout/', payload).status_code, 400)
        recipe = Prescription.objects.create(client=client, issued_on=timezone.localdate(), file='recetas/fixture.pdf')
        self.assertEqual(post(worker, 'checkout/', payload | {'prescription':recipe.pk}).status_code, 201)
        request = Inquiry.objects.get(kind='compra')
        self.assertEqual(request.agreement_id, union.agreement_id)
        self.assertEqual(request.purchase_lines.get().product_id, product.pk)
        self.assertEqual(post(self.sales, f'purchases/{request.pk}/quote/', {}).status_code, 201)
        request.refresh_from_db()
        self.assertEqual(request.purchase_quote.agreement_id, union.agreement_id)
        row = UnionMembership.objects.get(client=client)
        self.assertEqual(post(representative, f'union/workers/{row.pk}/', {'action':'disable'}).status_code, 200)
        self.assertEqual(worker.get('/api/products/?scope=mining').status_code, 403)
        self.assertEqual(worker.get('/api/my-account/').status_code, 200)
        self.assertTrue(client.prescriptions.exists())
        self.assertTrue(Audit.objects.filter(actor__email='alpha@example.invalid', record_id=row.pk).exists())

    def test_suspension_and_recovery_do_not_transfer_personal_access(self):
        union, representative = self.provision()
        worker, client = self.worker(representative)
        row = UnionMembership.objects.get(client=client)
        self.assertEqual(post(representative, f'union/workers/{row.pk}/', {'action':'reset','note':'Prueba'}).status_code, 403)
        self.assertEqual(post(representative, f'union/workers/{row.pk}/', {'action':'recovery'}).status_code, 200)
        result = post(self.admin, f'union/workers/{row.pk}/', {'action':'reset','note':'Titular verificado'})
        self.assertEqual(result.status_code, 200, result.content)
        link = token(result)
        self.assertEqual(post(representative, 'invitation/claim/', {'token':link,'accepted':True,'password':'Prueba-Nueva!452'}).status_code, 403)
        self.assertEqual(post(Browser(), 'invitation/claim/', {'token':link,'accepted':True,'password':'Prueba-Nueva!452'}).status_code, 200)
        self.assertEqual(post(self.admin, f'unions/{union.pk}/manage/', {'action':'suspend','note':'Prueba suspende'}).status_code, 200)
        self.assertEqual(self.make_worker(representative, rut='11111111-1').status_code, 403)
        self.assertEqual(post(worker, 'login/', {'username':'trabajador@example.invalid','password':'Prueba-Nueva!452'}).status_code, 200)
        self.assertEqual(worker.get('/api/my-account/').status_code, 200)
        self.assertEqual(worker.get('/api/products/?scope=mining').status_code, 403)

    def test_expired_or_revoked_invitation_cannot_be_used(self):
        _, representative = self.provision()
        result = self.make_worker(representative)
        first = token(result)
        row = UnionMembership.objects.get()
        AccessInvitation.objects.filter(membership=row).update(expires_at=timezone.now()-timedelta(seconds=1))
        payload = {'accepted':True,'password':PASSWORD}
        self.assertEqual(post(Browser(), 'invitation/claim/', payload | {'token':first}).status_code, 400)
        second = token(post(representative, f'union/workers/{row.pk}/', {'action':'reissue'}))
        third = token(post(representative, f'union/workers/{row.pk}/', {'action':'reissue'}))
        self.assertEqual(post(Browser(), 'invitation/claim/', payload | {'token':second}).status_code, 400)
        self.assertEqual(post(Browser(), 'invitation/claim/', payload | {'token':third}).status_code, 200)


def order_fixture(owner):
    agreement = Agreement.objects.create(name='Sindicato ficticio de retiro')
    Union.objects.create(agreement=agreement, identifier='retiro-ficticio')
    client = Client.objects.create(rut='12345678-5', name='Titular Ficticio', user=owner,
                                   phone='222222222', category='particular')
    quote = Quote.objects.create(client=client, agreement=agreement, product_type='seguridad',
                                 category='convenio', amount=42000, approved=True)
    return Order.objects.create(client=client, agreement=agreement, quote=quote,
                                product_type='seguridad', category='convenio')


def signature():
    return 'data:image/png;base64,'+base64.b64encode(png()).decode()


class PickupTests(TestCase):
    def setUp(self):
        cache.clear()
        private_media(self)
        call_command('configure_roles', verbosity=0)
        self.sales, self.seller = account('ventas', 'Vendedor')
        self.other_sales, _ = account('ventas2', 'Vendedor')
        self.owner, person = account('titular', 'Cliente')
        self.other, _ = account('otro', 'Cliente')
        self.order = order_fixture(person)

    def path(self, suffix=''):
        return f'orders/{self.order.pk}/{suffix}'

    def show(self):
        return self.owner.get(f'/api/pickup/{self.order.pk}/')

    def check(self, code, browser=None):
        return post(browser or self.sales, 'pickup/validate/', {'code':code,'identity_checked':True})

    def test_issue_reissue_expiry_permissions_and_signed_delivery(self):
        self.assertEqual(self.show().status_code, 400)
        self.assertEqual(post(self.sales, self.path('state/'), {'status':READY}).status_code, 200)
        code = self.show().json()['code']
        self.assertNotEqual(code, PickupCode.objects.get(order=self.order).digest)
        self.assertEqual(self.other.get(f'/api/pickup/{self.order.pk}/').status_code, 404)
        self.assertEqual(self.check(code,self.owner).status_code, 403)
        self.assertEqual(self.check('F'*24).status_code, 400)
        PickupCode.objects.filter(order=self.order).update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.check(code).status_code, 400)
        self.assertEqual(post(self.sales, f'pickup/{self.order.pk}/', {'action':'reissue'}).status_code, 200)
        fresh = self.show().json()['code']
        self.assertNotEqual(fresh, code)
        self.assertEqual(self.check(code).status_code, 400)
        proof = self.check(fresh).json()['proof']
        self.assertFalse(Receipt.objects.exists())
        review = self.sales.get('/api/'+self.path('preview/')).json()['review_token']
        data = {'accepted':True,'review_token':review,'signature':signature()}
        self.assertEqual(post(self.sales, self.path('deliver/'), data).status_code, 400)
        self.assertEqual(post(self.other_sales, self.path('deliver/'), data | {'pickup_proof':proof}).status_code, 400)
        self.assertEqual(post(self.sales, self.path('deliver/'), data | {'pickup_proof':proof,'signature':'invalid'}).status_code, 400)
        self.assertIsNone(PickupCode.objects.get(order=self.order).used_at)
        self.assertEqual(post(self.sales, self.path('deliver/'), data | {'pickup_proof':proof}).status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'Entregada')
        code_record = PickupCode.objects.get(order=self.order)
        self.assertIsNotNone(code_record.used_at)
        self.assertEqual(code_record.used_by, self.seller)
        self.assertEqual(Receipt.objects.count(), 1)
        self.assertEqual(self.check(fresh).status_code, 400)
        self.assertTrue(Audit.objects.filter(action='Código de retiro utilizado',record_id=code_record.pk).exists())

    def test_code_revoked_when_order_leaves_pickup_state(self):
        self.assertEqual(post(self.sales, self.path('state/'), {'status':READY}).status_code, 200)
        code = self.show().json()['code']
        self.assertEqual(post(self.sales, self.path('state/'), {'status':'Control de calidad'}).status_code, 200)
        self.assertEqual(self.check(code).status_code, 400)
        self.assertIsNotNone(PickupCode.objects.get(order=self.order).revoked_at)


class PickupConcurrencyTests(TransactionTestCase):
    @skipUnlessDBFeature('has_select_for_update')
    def test_two_vendors_cannot_consume_one_code(self):
        cache.clear()
        private_media(self)
        call_command('configure_roles', verbosity=0)
        first, first_user = account('ventas', 'Vendedor')
        second, second_user = account('ventas2', 'Vendedor')
        owner, customer = account('titular', 'Cliente')
        order = order_fixture(customer)
        self.assertEqual(post(first, f'orders/{order.pk}/state/', {'status':READY}).status_code, 200)
        code = owner.get(f'/api/pickup/{order.pk}/').json()['code']
        proofs = [post(b, 'pickup/validate/', {'code':code,'identity_checked':True}).json()['proof'] for b in (first,second)]
        barrier = Barrier(2, timeout=10)
        image = signature()

        def deliver(item):
            actor, proof = item
            try:
                barrier.wait()
                accept_receipt(order.pk, actor, True, image, pickup_proof=proof)
                return True
            except ValidationError:
                return False
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            result = list(pool.map(deliver, zip((first_user,second_user),proofs)))
        self.assertEqual(result.count(True), 1)
        self.assertEqual(Receipt.objects.count(), 1)
        self.assertEqual(PickupCode.objects.get(order=order).used_by_id, Receipt.objects.get().actor_id)
