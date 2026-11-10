from datetime import timedelta
from uuid import uuid4

from django.contrib.auth.models import Permission, User
from django.core.cache import cache
from django.test import Client as Browser, TestCase
from django.utils import timezone

from .models import Agreement, AgreementRepresentative, Client, Inquiry, Prescription, Product, PurchaseLine, Quote


class PurchaseMembershipTests(TestCase):
    def setUp(self):
        cache.clear()
        self.customer = User.objects.create_user('customer_cart')
        self.person = Client.objects.create(user=self.customer, rut='12345678-5', name='Cliente ficticio', phone='+56900000000', category='particular')
        self.product = Product.objects.create(sku='TEST-01', name='Cristales ficticios', category='cristal', variants=['Claro', 'Gris'], reference_price=12300, requires_prescription=True)
        self.recipe = Prescription.objects.create(client=self.person, issued_on=timezone.localdate(), file='recetas/ficticia.pdf')
        self.agreement = Agreement.objects.create(name='Convenio ficticio')
        self.staff = User.objects.create_user('catalog_staff')
        codes = ['view_inquiry','view_quote','add_quote','view_product','change_product']
        self.staff.user_permissions.add(*Permission.objects.filter(codename__in=codes))
        self.representative = User.objects.create_user('representative')
        AgreementRepresentative.objects.create(user=self.representative, agreement=self.agreement)

    def post(self, path, data):
        return self.client.post(path, data, content_type='application/json')

    def purchase(self, **extra):
        return dict(items=[{'product': self.product.pk, 'quantity': 2, 'variant': 'Claro'}], mode='compra',
                    prescription=self.recipe.pk, reason='Solicitud de prueba', contact_authorized=True, idempotency_key=str(uuid4())) | extra

    def membership(self, agreement=None):
        return Inquiry.objects.create(kind='registro', client=self.person, agreement=agreement or self.agreement,
            registration_rut=self.person.rut, agreement_role='titular', verification_state='pendiente',
            idempotency_key=uuid4(), name='Cliente ficticio', phone='+56900000000')

    def test_purchase_uses_current_price_and_keeps_historical_snapshot(self):
        self.client.force_login(self.customer)
        data = self.purchase()
        data['items'][0]['unit_price'] = 1
        response = self.post('/api/checkout/', data)
        self.assertEqual(response.status_code, 201, response.content)
        row = Inquiry.objects.get()
        line = row.purchase_lines.get()
        self.assertEqual((line.quantity, line.variant, line.unit_price), (2, 'Claro', 12300))
        self.product.reference_price=20000
        self.product.name='Otro nombre'
        self.product.active=False
        self.product.save()
        self.assertEqual(self.post('/api/checkout/', data).status_code, 200)
        self.assertEqual(PurchaseLine.objects.get().product_name, 'Cristales ficticios')
        data['items'][0]['quantity'] = 3
        self.assertEqual(self.post('/api/checkout/', data).status_code, 409)
        self.assertEqual(Inquiry.objects.count(), 1)

    def test_requires_valid_owned_recipe_and_supported_variant(self):
        self.client.force_login(self.customer)
        data = self.purchase()
        del data['prescription']
        self.assertEqual(self.post('/api/checkout/', data).status_code, 400)
        self.recipe.issued_on = timezone.localdate()-timedelta(days=500)
        self.recipe.save()
        self.assertEqual(self.post('/api/checkout/', self.purchase()).status_code, 400)
        self.recipe.issued_on = timezone.localdate()
        self.recipe.save()
        unknown = self.purchase(items=[{'product':self.product.pk, 'quantity':1, 'variant':'No existe'}])
        self.assertEqual(self.post('/api/checkout/', unknown).status_code, 409)
        self.assertFalse(Inquiry.objects.exists())

    def test_review_and_draft_quote_keep_variants(self):
        self.client.force_login(self.customer)
        items = [{'product':self.product.pk,'variant':variant,'quantity':1} for variant in ['Claro','Gris']]
        self.assertEqual(self.post('/api/checkout/', self.purchase(items=items)).status_code, 201)
        row = Inquiry.objects.get()
        url = f'/api/purchases/{row.pk}/quote/'
        self.assertEqual(self.post(url, {}).status_code, 403)
        self.client.force_login(self.staff)
        response = self.post(url, {})
        self.assertEqual(response.status_code, 201, response.content)
        quote = Quote.objects.get()
        self.assertFalse(quote.approved)
        self.assertEqual(quote.amount, 24600)
        self.assertEqual(set(quote.lines.values_list('variant',flat=True)), {'Claro','Gris'})
        self.assertEqual(self.post(url, {}).status_code, 200)
        self.assertEqual(Quote.objects.count(), 1)

    def test_only_verified_agreement_is_applied_without_discount(self):
        pending = self.membership()
        self.person.agreement=self.agreement
        self.person.save()
        self.client.force_login(self.customer)
        self.assertEqual(self.post('/api/checkout/', self.purchase()).status_code, 201)
        self.assertIsNone(Inquiry.objects.get(kind='compra').agreement)
        self.client.force_login(self.representative)
        response=self.post(f'/api/membership/queue/{pending.pk}/', {'approved':True,'note':'Verificación de ejemplo'})
        self.assertEqual(response.status_code, 200, response.content)
        self.client.force_login(self.customer)
        self.assertEqual(self.post('/api/checkout/', self.purchase()).status_code, 201)
        newest=Inquiry.objects.filter(kind='compra').latest('pk')
        self.assertEqual(newest.agreement, self.agreement)
        self.assertEqual(newest.purchase_lines.get().unit_price, self.product.reference_price)

    def test_representative_scope_and_minimal_status_lookup(self):
        own=self.membership()
        other=self.membership(Agreement.objects.create(name='Otro convenio ficticio'))
        self.client.force_login(self.representative)
        response=self.client.get('/api/membership/queue/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([r['id'] for r in response.json()['requests']], [own.pk])
        for path in ['/api/clients/','/api/prescriptions/','/api/inquiries/','/api/orders/','/api/receipts/']:
            self.assertEqual(self.client.get(path).status_code, 403, path)
        self.assertEqual(self.post(f'/api/membership/queue/{other.pk}/', {'approved':True,'note':'Verificación de ejemplo'}).status_code, 404)
        self.client.logout()
        result=self.post('/api/membership/status/', {'reference':str(own.token)})
        self.assertEqual(result.json(), {'state':'pendiente','reviewed':None})
        self.assertEqual(self.post('/api/membership/status/', {'reference':str(uuid4())}).status_code, 404)
        no_csrf=Browser(enforce_csrf_checks=True)
        self.assertEqual(no_csrf.post('/api/membership/status/', {'reference':str(own.token)}, content_type='application/json').status_code, 403)
