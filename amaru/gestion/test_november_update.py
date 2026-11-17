from datetime import timedelta
from uuid import uuid4

from django.contrib.auth.models import Permission, User
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from .models import Agreement, Audit, Client, Inquiry, Quote


class NovemberUpdateTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_superuser('test_admin')
        self.sales = User.objects.create_user('test_sales')
        self.sales.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='gestion', codename__in=['view_quote', 'view_agreement']
        ))
        self.customer = User.objects.create_user('test_customer')
        self.owner = Client.objects.create(user=self.customer, rut='12345678-5', name='Cliente de prueba',
                                           phone='+56900000000', category='particular')
        self.other = Client.objects.create(rut='11111111-1', name='Otro cliente de prueba',
                                           phone='+56900000001', category='particular')
        self.first = self.quote(self.owner, 6000)
        self.second = self.quote(self.owner, 7000)
        self.third = self.quote(self.other, 8000)
        Quote.objects.filter(pk=self.first.pk).update(created_at=timezone.now()-timedelta(days=2))

    def quote(self, client, amount):
        return Quote.objects.create(client=client, product_type='particular', category='particular', amount=amount)

    def get_quotes(self, **filters):
        return self.client.get('/api/quotes/', filters)

    def post(self, url, **fields):
        return self.client.post(url, fields, content_type='application/json')

    def register(self, code):
        return self.post('/api/inquiries/', kind='registro', name='Prueba ficticia', phone='+56900000002',
                         service='Convenio', reason='Prueba ficticia por código', registration_rut=self.owner.rut,
                         contact_authorized=True, idempotency_key=str(uuid4()), agreement_code=code, agreement_role='titular')

    def test_rut_format_filters_order_and_permissions(self):
        self.assertEqual(self.get_quotes(rut=self.owner.rut).status_code, 403)
        self.client.force_login(self.customer)
        self.assertEqual(self.get_quotes(rut=self.other.rut).status_code, 403)
        self.client.force_login(self.sales)
        for rut in ('12.345.678-5', '12345678-5', '123456785'):
            res = self.get_quotes(rut=rut, orden='folio-asc')
            self.assertEqual(res.status_code, 200, res.content)
            self.assertEqual([q['folio'] for q in res.json()['results']], [self.first.folio,self.second.folio])
            self.assertTrue(all(q['client_rut']==self.owner.rut for q in res.json()['results']))
        self.assertEqual(self.get_quotes(rut=self.other.rut).json()['count'], 1)
        self.assertEqual(self.get_quotes(rut='22222222-2').json()['count'], 0)
        self.assertEqual(self.get_quotes(rut='12345678-1').status_code, 400)
        day = timezone.localdate().isoformat()
        res = self.get_quotes(rut=self.owner.rut, desde=day, hasta=day)
        self.assertEqual([q['id'] for q in res.json()['results']], [self.second.pk])
        self.assertEqual(self.get_quotes(folio=self.first.folio).json()['count'], 1)
        self.assertEqual(self.get_quotes(folio=self.first.folio[:-12]+'0'*12).json()['count'], 0)
        self.assertEqual(self.get_quotes(rut=self.owner.rut, orden='fecha-desc').json()['results'][0]['id'], self.second.pk)
        self.assertEqual(self.client.get(f'/api/quotes/{self.first.pk}/').json()['folio'], self.first.folio)

    def test_code_lifecycle_and_membership_review(self):
        self.client.force_login(self.admin)
        res = self.post('/api/agreements/', name='Convenio sin correo')
        self.assertEqual(res.status_code, 201, res.content)
        agreement = Agreement.objects.get(pk=res.json()['id'])
        self.assertEqual(agreement.contact_email,'')
        old = agreement.code
        route = f'/api/agreements/{agreement.pk}/manage-code/'
        history = f'/api/agreements/{agreement.pk}/code-history/'
        self.assertEqual(self.post(route, operation='disable').status_code, 200)
        self.client.logout()
        self.assertEqual(self.register(old).status_code,400)
        self.client.force_login(self.sales)
        self.assertEqual(self.post(route, operation='enable').status_code,403)
        self.assertEqual(self.client.get(history).status_code,403)
        self.client.force_login(self.admin)
        self.assertEqual(self.post(route, operation='enable').status_code,200)
        res = self.post(route, operation='rotate')
        self.assertEqual(res.status_code,200,res.content)
        agreement.refresh_from_db()
        new = agreement.code
        self.assertNotEqual(new,old)
        self.assertGreaterEqual(len(new),20)
        self.assertEqual(self.client.get(history).json()['count'],4)
        self.client.logout()
        self.assertEqual(self.register(old).status_code,400)
        self.assertEqual(self.register(new).status_code,201)
        inquiry = Inquiry.objects.get()
        self.assertEqual(inquiry.verification_state,'pendiente')
        self.owner.refresh_from_db()
        self.assertIsNone(self.owner.agreement_id)
        self.client.force_login(self.admin)
        self.assertEqual(self.post(f'/api/agreement-verifications/{inquiry.pk}/',approved=True,
                                   method='presencial',note='Verificación ficticia').status_code,200)
        self.assertEqual(self.post(route, operation='revoke').status_code,200)
        agreement.refresh_from_db()
        self.assertIsNone(agreement.code)
        agreement.save()
        agreement.refresh_from_db()
        self.assertIsNone(agreement.code)
        self.assertTrue(Audit.objects.filter(model='agreement',record_id=agreement.pk,action__endswith='revocado').exists())
        self.client.logout()
        self.assertEqual(self.register(new).status_code,400)

    def test_expired_code_and_database_uniqueness(self):
        from django.db import IntegrityError, transaction

        agreement = Agreement.objects.create(name='Vencido', ends_on=timezone.localdate()-timedelta(days=1))
        self.assertEqual(self.register(agreement.code).status_code,400)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Agreement.objects.create(name='Duplicado',code=agreement.code)
