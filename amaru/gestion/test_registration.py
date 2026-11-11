import time
from uuid import uuid4

from django.contrib.auth.models import Group, User
from django.core import signing
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client as Browser, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Agreement, Audit, Client, ClientRegistration, Inquiry, Prescription
from .registration import CHALLENGE_SALT, PRIVACY_VERSION


class ClientRegistrationTests(TestCase):
    password = 'Bosque-nublado_42!Arco'

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        call_command('configure_roles', verbosity=0)
        self.reviewer = User.objects.create_user('administracion', is_staff=True)
        self.reviewer.groups.add(Group.objects.get(name='Administrador'))
        self.staff = User.objects.create_user('personal', is_staff=True)
        self.staff.groups.add(Group.objects.get(name='Vendedor'))

    def challenge(self, issued=None):
        return signing.dumps({'issued': time.time()-3 if issued is None else issued}, salt=CHALLENGE_SALT)

    def signup(self, browser=None, token=None, **extra):
        data = dict(name='Cliente de Prueba', rut='12.345.678-5', email='CUENTA@example.invalid',
                    phone='+56 9 0000 0000', password=self.password, password_confirmation=self.password,
                    privacy=True, privacy_version=PRIVACY_VERSION, challenge=self.challenge())
        if token is not None:
            extra['challenge'] = token
        return (browser or self.client).post('/api/register/', data | extra, content_type='application/json')

    def sign_in(self, browser=None, **headers):
        return (browser or self.client).post('/api/login/', {
            'username': 'cuenta@example.invalid', 'password': self.password,
        }, content_type='application/json', **headers)

    def review(self, reviewer=None, **overrides):
        admin = Browser()
        admin.force_login(reviewer or self.reviewer)
        return admin.post(reverse('admin:clientregistration_verify', args=[ClientRegistration.objects.get().pk]),
                          dict(email_verified='on', identity_verified='on', note='Verificación ficticia') | overrides)

    def test_new_account_persists_inactive_without_staff_access_until_verified(self):
        result = self.signup(promotions=True, is_staff=True, is_superuser=True, groups=['Administrador'])
        self.assertEqual(result.status_code, 202, result.content)
        self.assertIn('no envía correos automáticos', result.json()['detail'])
        row = ClientRegistration.objects.select_related('user').get()
        self.assertEqual((row.rut, row.email, row.phone), ('12345678-5', 'cuenta@example.invalid', '+56900000000'))
        self.assertEqual(row.privacy_version, PRIVACY_VERSION)
        self.assertFalse(row.user.is_active)
        self.assertNotEqual(row.user.password, self.password)
        self.assertTrue(row.user.check_password(self.password))
        self.assertFalse(Client.objects.exists())
        self.assertEqual(self.sign_in().status_code, 400)
        self.assertEqual(self.review().status_code, 302)
        row.refresh_from_db()
        self.assertEqual(row.approved_by, self.reviewer)
        self.assertIsNotNone(row.approved_at)
        self.assertTrue(row.user.is_active)
        self.assertFalse(row.user.is_staff or row.user.is_superuser)
        self.assertFalse(row.user.get_all_permissions())
        client = Client.objects.get(user=row.user)
        self.assertTrue(row.promotions)
        self.assertFalse(client.consents.get().authorized)
        self.assertTrue(Audit.objects.filter(record_id=row.pk, model='clientregistration', actor=self.reviewer).exists())
        new_browser = Browser()
        self.assertEqual(self.sign_in(new_browser).status_code, 200)
        self.assertEqual(new_browser.get('/api/session/').json()['client_id'], client.pk)
        self.assertEqual(new_browser.get('/api/clients/').status_code, 403)
        self.assertEqual(new_browser.get('/admin/').status_code, 302)
        self.assertEqual(new_browser.post('/api/logout/').status_code, 200)
        self.assertFalse(new_browser.get('/api/session/').json()['authenticated'])

    def test_invalid_data_and_weak_passwords_are_rejected_without_writes(self):
        for key, invalid, field in [
            ('rut', '12.345.678-0', 'rut'), ('email', 'correo-invalido', 'email'),
            ('phone', '+57 987654321', 'phone'), ('password_confirmation', 'distinta', 'password_confirmation'),
            ('privacy', False, 'privacy'), ('privacy_version', 'anterior', 'privacy'),
            ('name', 'Solo', 'name'),
        ]:
            with self.subTest(key=key):
                result = self.signup(**{key: invalid})
                self.assertEqual(result.status_code, 400)
                self.assertIn(field, result.json())
        result = self.signup(password='12345678', password_confirmation='12345678')
        self.assertEqual(result.status_code, 400)
        self.assertIn('password', result.json())
        self.assertFalse(ClientRegistration.objects.exists())
        self.assertEqual(User.objects.count(), 2)

    def test_duplicate_email_rut_and_existing_identifier_return_same_generic_message(self):
        first = self.signup()
        User.objects.create_user('legado', email='LEGADO@example.invalid')
        User.objects.create_user('identificador@example.invalid')
        for data in [
            {'email': 'cuenta@example.invalid', 'rut': '11.111.111-1'},
            {'email': 'otra@example.invalid', 'rut': '12345678-5'},
            {'email': 'legado@example.invalid', 'rut': '11.111.111-1'},
            {'email': 'IDENTIFICADOR@example.invalid', 'rut': '11.111.111-1'},
        ]:
            result = self.signup(**data)
            self.assertEqual((result.status_code, result.json()), (202, first.json()))
        self.assertEqual(ClientRegistration.objects.count(), 1)
        self.assertEqual(User.objects.count(), 5)

    def test_existing_unlinked_client_is_unchanged_until_authorized_identity_check(self):
        existing = Client.objects.create(rut='12345678-5', name='Ficha histórica', phone='222222222',
                                         email='original@example.invalid', consent=False, category='particular')
        self.assertEqual(self.signup(promotions=True).status_code, 202)
        existing.refresh_from_db()
        self.assertIsNone(existing.user_id)
        self.assertEqual(self.review(self.staff).status_code, 403)
        self.assertEqual(self.review(identity_verified='').status_code, 200)
        existing.refresh_from_db()
        self.assertIsNone(existing.user_id)
        self.assertEqual(self.review().status_code, 302)
        existing.refresh_from_db()
        self.assertEqual(existing.user, ClientRegistration.objects.get().user)
        self.assertEqual((existing.name, existing.email, existing.phone, existing.consent),
                         ('Ficha histórica', 'original@example.invalid', '222222222', False))
        self.assertEqual(Client.objects.count(), 1)

    def test_existing_link_cannot_be_taken_over(self):
        owner = User.objects.create_user('titular-original')
        existing = Client.objects.create(rut='12345678-5', user=owner, name='Titular ficticio',
                                         phone='222222222', category='particular')
        self.assertEqual(self.signup().status_code, 202)
        response = self.review()
        self.assertContains(response, 'ya tiene cuenta')
        existing.refresh_from_db()
        self.assertEqual(existing.user, owner)
        self.assertFalse(ClientRegistration.objects.get().user.is_active)

    def test_challenge_csrf_honeypot_and_throttle(self):
        browser = Browser(enforce_csrf_checks=True)
        setup = browser.get('/api/register/')
        self.assertEqual(setup.status_code, 200)
        self.assertEqual(setup['Cache-Control'], 'no-store')
        csrf = browser.get('/api/session/').json()['csrf']
        self.assertEqual(self.signup(browser).status_code, 403)
        payload = dict(name='Cuenta ficticia', rut='12345678-5', email='cuenta@example.invalid',
                       phone='900000000', password=self.password, password_confirmation=self.password,
                       privacy=True, privacy_version=PRIVACY_VERSION)
        for invalid in [dict(challenge='alterado'), dict(challenge=self.challenge(issued=time.time()+30)),
                        dict(challenge=self.challenge(), website='bot.invalid'), dict(challenge=['inválido'])]:
            result = browser.post('/api/register/', payload | invalid, content_type='application/json', HTTP_X_CSRFTOKEN=csrf)
            self.assertEqual(result.status_code, 400)
        for _ in range(6):
            self.assertEqual(self.signup(token='alterado').status_code, 400)
        self.assertEqual(self.signup().status_code, 429)
        self.assertFalse(ClientRegistration.objects.exists())

    def test_staff_toggle_does_not_bypass_pending_registration(self):
        self.assertEqual(self.signup().status_code, 202)
        User.objects.filter(client_registration__isnull=False).update(is_active=True)
        self.assertEqual(self.sign_in().status_code, 400)

    def test_activated_client_account_does_not_expose_other_records(self):
        self.assertEqual(self.signup().status_code, 202)
        self.assertEqual(self.review().status_code, 302)
        self.assertEqual(self.sign_in().status_code, 200)
        mine = Client.objects.get(rut='12345678-5')
        self.assertFalse(mine.consents.get().authorized)
        other = Client.objects.create(rut='11111111-1', name='Otra persona ficticia', phone='222222222', category='particular')
        recipe = Prescription.objects.create(client=other, issued_on=timezone.localdate(), file='recetas/ficticia.pdf')
        self.assertEqual(self.client.get('/api/my-prescriptions/').json(), [])
        self.assertEqual(self.client.get(f'/api/prescriptions/{recipe.pk}/file/').status_code, 403)
        agreement = Agreement.objects.create(name='Convenio ficticio')
        mine.agreement = agreement
        mine.save()
        base = dict(kind='contacto', name='Ficticio', phone='222222222')
        foreign = Inquiry.objects.create(client=other, idempotency_key=uuid4(), **base)
        anonymous = Inquiry.objects.create(client=mine, idempotency_key=uuid4(), **base)
        own = Inquiry.objects.create(client=mine, actor=mine.user, idempotency_key=uuid4(), **base)
        response = self.client.get('/api/my-account/')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['agreement'])
        self.assertEqual([row['reference'] for row in response.json()['inquiries']], [str(own.token)])
        self.assertNotContains(response, str(foreign.token))
        self.assertNotContains(response, str(anonymous.token))
        Inquiry.objects.create(client=mine, agreement=agreement, agreement_role='titular',
                               verification_state='aprobada', idempotency_key=uuid4(), **base)
        self.assertEqual(self.client.get('/api/my-account/').json()['agreement'], str(agreement))

    def test_public_shells_include_official_logo_and_registration_link(self):
        for url in ('/app/registro.html', '/app/privacidad.html', '/app/'):
            self.assertContains(self.client.get(url), 'logo-amaru-oficial.jpg')
        self.assertContains(self.client.get('/app/'), 'data-signup-nav')
        self.assertContains(self.client.get('/login/'), 'Regístrate aquí')
