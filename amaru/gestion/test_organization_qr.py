from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import time
from threading import Barrier
from uuid import uuid4

from django.contrib.auth.models import Group, User
from django.core import signing
from django.core.cache import cache
from django.core.management import call_command
from django.db import connections
from django.test import Client as Browser, TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from .models import (Agreement, AgreementBenefit, AgreementRepresentative, AppointmentReservation,
    Audit, Client, Inquiry, Union, UnionMembership)
from .organization_qr import SALT, public


def challenge(agreement, purpose, issued=None):
    return signing.dumps({'issued': issued if issued is not None else time.time()-3,
        'qr': str(getattr(agreement, purpose+'_qr_token')), 'purpose': purpose, 'nonce': 'test-only'}, salt=SALT)


def worker_payload(organization, **changes):
    return {'name': 'Trabajador Ficticio', 'rut': '12.345.678-5', 'email': 'worker@example.invalid',
        'phone': '+56900000000', 'role': 'titular', 'privacy': True, 'privacy_version': 'academica-1',
        'idempotency_key': str(uuid4()), 'challenge': challenge(organization, 'worker'), **changes}


def url(agreement, purpose='worker'):
    return f'/api/organization-qr/{purpose}/{getattr(agreement, purpose+"_qr_token")}/'


@override_settings(ATTENTION_PUBLIC_BASE_URL='https://opticaamaru.alwaysdata.net', ATTENTION_URL_FILE='')
class OrganizationQRTests(TestCase):
    def setUp(self):
        cache.clear()
        call_command('configure_roles', verbosity=0)
        self.admin = User.objects.create_superuser('qr_admin')
        self.seller = User.objects.create_user('qr_seller')
        self.seller.groups.add(Group.objects.get(name='Vendedor'))
        self.owner = User.objects.create_user('qr_owner')
        self.rep = User.objects.create_user('qr_rep')
        self.traditional = Agreement.objects.create(name='DEMO Convenio QR')
        self.agreement = Agreement.objects.create(name='DEMO Sindicato QR')
        self.union = Union.objects.create(agreement=self.agreement, identifier='demo-qr', state='active')
        AgreementRepresentative.objects.create(user=self.rep, agreement=self.agreement)

    def post(self, agreement=None, data=None, purpose='worker', user=None):
        if user:
            self.client.force_login(user)
        else:
            self.client.logout()
        agreement = agreement or self.agreement
        return self.client.post(url(agreement, purpose), data or worker_payload(agreement), content_type='application/json')

    def change(self, purpose, operation, user=None):
        self.client.force_login(user or self.admin)
        return self.client.post(f'/api/organization-qrs/{self.agreement.pk}/',
            {'purpose': purpose, 'operation': operation, 'confirmed': True}, content_type='application/json')

    def query(self, organization=None, **changes):
        agreement = organization or self.agreement
        return {'kind': 'contacto', 'name': 'Visitante Ficticio', 'email': 'visitor@example.invalid',
            'phone': '+56900000000', 'service': 'Beneficios', 'reason': 'Consulta ficticia de la organización',
            'contact_authorized': True, 'privacy': True, 'privacy_version': 'academica-1',
            'idempotency_key': str(uuid4()), 'challenge': challenge(agreement, 'inquiry'), **changes}

    def test_two_distinct_qr_urls_and_real_pngs_for_each_organization(self):
        self.client.force_login(self.admin)
        for agreement in (self.traditional, self.agreement):
            data = self.client.get(f'/api/organization-qrs/{agreement.pk}/').json()
            self.assertEqual(len(data['codes']), 2)
            links = [row['url'] for row in data['codes']]
            self.assertNotEqual(*links)
            self.assertIn('/app/registro_trabajador.html?qr=', links[0])
            self.assertIn('/app/consulta_convenio.html?qr=', links[1])
            self.assertNotIn('localhost', ' '.join(links))
            for row in data['codes']:
                result = self.client.get(row['image_url']+'&download=1')
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result['Content-Type'], 'image/png')
                self.assertTrue(result.content.startswith(b'\x89PNG\r\n'))
                self.assertIn('attachment', result['Content-Disposition'])

    def test_management_and_roster_are_private(self):
        for suffix in ('', 'registrations/', 'worker/image/'):
            self.assertEqual(self.client.get(f'/api/organization-qrs/{self.agreement.pk}/'+suffix).status_code, 403)

    def test_representative_can_only_share_own_codes_and_cannot_rotate(self):
        self.client.force_login(self.rep)
        self.assertEqual(self.client.get(f'/api/organization-qrs/{self.agreement.pk}/').status_code, 200)
        self.assertEqual(self.client.get(f'/api/organization-qrs/{self.traditional.pk}/').status_code, 403)
        self.assertEqual(self.client.get(f'/api/organization-qrs/{self.traditional.pk}/registrations/').status_code, 403)
        self.assertEqual(self.change('worker', 'rotate', self.rep).status_code, 403)
        self.assertEqual(self.change('worker', 'revoke', self.seller).status_code, 403)

    def test_revocation_and_rotation_are_independent_and_audited(self):
        previous = url(self.agreement)
        self.assertEqual(self.change('worker', 'revoke').status_code, 200)
        self.client.logout()
        self.assertEqual(self.client.get(previous).status_code, 404)
        self.assertEqual(self.client.get(url(self.agreement, 'inquiry')).status_code, 200)
        self.assertEqual(self.change('worker', 'rotate').status_code, 200)
        self.agreement.refresh_from_db()
        self.client.logout()
        self.assertEqual(self.client.get(previous).status_code, 404)
        self.assertEqual(self.client.get(url(self.agreement)).status_code, 200)
        self.assertEqual(Audit.objects.filter(action__startswith='QR de organización:').count(), 2)

    def test_qr_purpose_cannot_be_swapped(self):
        token = self.agreement.worker_qr_token
        self.assertEqual(self.client.get(f'/api/organization-qr/inquiry/{token}/').status_code, 404)
        data = worker_payload(self.agreement, challenge=challenge(self.agreement, 'inquiry'))
        self.assertEqual(self.post(data=data).status_code, 400)

    def test_inactive_expired_future_and_suspended_organizations_reject_registration(self):
        for changes in ({'active': False}, {'ends_on': timezone.localdate()-timedelta(days=1)},
                        {'starts_on': timezone.localdate()+timedelta(days=1)}):
            for key, value in changes.items():setattr(self.agreement, key, value)
            self.agreement.save()
            self.assertEqual(self.post().status_code, 404)
            self.agreement.active, self.agreement.starts_on, self.agreement.ends_on = True, None, None
        self.agreement.save()
        for state in ('pending', 'suspended'):
            self.union.state = state; self.union.save()
            self.assertEqual(self.post().status_code, 404)
        self.assertFalse(UnionMembership.objects.exists())

    def test_traditional_registration_has_worker_classification_and_no_automatic_account(self):
        count = User.objects.count()
        result = self.post(self.traditional)
        self.assertEqual(result.status_code, 201, result.content)
        self.assertEqual(result.json()['classification'], 'trabajador_convenio')
        row = Inquiry.objects.get()
        self.assertEqual((row.kind, row.origin, row.agreement), ('registro', 'qr_worker', self.traditional))
        self.assertEqual(row.verification_state, 'pendiente')
        self.assertIsNotNone(row.privacy_accepted_at)
        self.assertIsNone(row.client_id)
        self.assertEqual(User.objects.count(), count)
        self.assertFalse(Client.objects.exists())
        self.client.force_login(self.admin)
        roster = self.client.get(f'/api/organization-qrs/{self.traditional.pk}/registrations/').json()
        self.assertEqual(roster['counts']['pending'], 1)

    def test_union_registration_creates_pending_membership_and_ignores_other_org_ids(self):
        result = self.post(data=worker_payload(self.agreement, agreement=self.traditional.pk, is_staff=True))
        self.assertEqual(result.status_code, 201, result.content)
        row = UnionMembership.objects.get()
        self.assertEqual((row.union, row.origin, row.state), (self.union, 'qr_worker', 'pending'))
        self.assertEqual(Inquiry.objects.get().union_membership, row)
        self.assertIsNone(row.client_id)
        self.client.force_login(self.rep)
        self.assertEqual(self.client.get('/api/union/portal/').json()['counts']['pending'], 1)

    def test_retries_and_duplicates_do_not_create_more_rows(self):
        data = worker_payload(self.agreement)
        self.assertEqual(self.post(data=data).status_code, 201)
        self.assertEqual(self.post(data=data).status_code, 200)
        self.assertEqual(self.post(data={**data, 'name': 'Otra Persona'}).status_code, 409)
        self.assertEqual(self.post(data=worker_payload(self.agreement)).status_code, 409)
        self.assertEqual((Inquiry.objects.count(), UnionMembership.objects.count()), (1, 1))

    def test_invalid_fields_and_unpermitted_dependents_are_rejected(self):
        for changes in ({'rut': '12345678-9'}, {'email': 'invalid'}, {'phone': '123'}, {'privacy': False},
                        {'name': 'Nombre'}, {'role': 'carga'}):
            self.assertEqual(self.post(data=worker_payload(self.agreement, **changes)).status_code, 400)
        self.assertFalse(Inquiry.objects.exists())

    def test_existing_client_is_not_claimed_or_overwritten(self):
        person = Client.objects.create(user=self.owner, rut='12345678-5', name='Ficha anterior ficticia',
            phone='+56911111111', email='original@example.invalid', category='particular')
        result = self.post(self.traditional)
        self.assertEqual(result.status_code, 201)
        self.assertIsNone(Inquiry.objects.get().client_id)
        person.refresh_from_db()
        self.assertEqual((person.name, person.email, person.category), ('Ficha anterior ficticia', 'original@example.invalid', 'particular'))
        self.assertEqual(person.user, self.owner)

    def test_approval_requires_explicit_identity_review_and_creates_one_verified_client(self):
        self.assertEqual(self.post(self.traditional).status_code, 201)
        row = Inquiry.objects.get()
        self.client.force_login(self.admin)
        data = {'approved': True, 'method': 'presencial', 'note': 'Verificación académica ficticia'}
        path = f'/api/agreement-verifications/{row.pk}/'
        self.assertEqual(self.client.post(path, data, content_type='application/json').status_code, 400)
        data['identity_verified'] = True
        self.assertEqual(self.client.post(path, data, content_type='application/json').status_code, 200)
        row.refresh_from_db()
        self.assertEqual(row.client.category, 'convenio')
        self.assertEqual(row.client.agreement, self.traditional)
        self.assertIsNone(row.client.user_id)
        self.assertEqual(row.verification_state, 'aprobada')

    def test_qr_invitation_acceptance_stays_pending_until_admin_validation(self):
        self.assertEqual(self.post().status_code, 201)
        member = UnionMembership.objects.get()
        self.client.force_login(self.admin)
        path = f'/api/union/workers/{member.pk}/'
        invite = self.client.post(path, {'action': 'reissue'}, content_type='application/json').json()['invitation']
        self.client.logout()
        result = self.client.post('/api/invitation/claim/', {'token': invite['url'].split('#token=')[1],
            'password': 'Prueba-ficticia-Acceso-2026!', 'accepted': True}, content_type='application/json')
        self.assertEqual(result.status_code, 200, result.content)
        member.refresh_from_db()
        self.assertEqual(member.state, 'pending')
        self.assertIsNotNone(member.client_id)
        self.client.force_login(member.client.user)
        self.assertEqual(self.client.get('/api/my-benefits/').json(), [])
        self.assertEqual(self.client.get('/api/products/?scope=mining').status_code, 403)
        self.client.force_login(self.admin)
        reviewed = self.client.post(path, {'action': 'review', 'note': 'Titular ficticio verificado'}, content_type='application/json')
        self.assertEqual(reviewed.status_code, 200, reviewed.content)
        self.assertEqual(Inquiry.objects.get().verification_state, 'aprobada')
        self.client.force_login(member.client.user)
        self.assertEqual(self.client.get('/api/products/?scope=mining').status_code, 200)

    def test_existing_union_worker_must_authenticate_as_the_owner_to_link(self):
        person = Client.objects.create(user=self.owner, rut='12345678-5', name='Titular anterior ficticio',
            phone='+56911111111', email='owner@example.invalid', category='particular')
        self.assertEqual(self.post().status_code, 201)
        member = UnionMembership.objects.get()
        self.client.force_login(self.admin)
        path = f'/api/union/workers/{member.pk}/'
        invite = self.client.post(path, {'action': 'reissue'}, content_type='application/json').json()['invitation']
        claim = {'token': invite['url'].split('#token=')[1], 'password': 'No-cambiar-clave-2026!', 'accepted': True}
        self.client.logout()
        self.assertEqual(self.client.post('/api/invitation/claim/', claim, content_type='application/json').status_code, 403)
        member.refresh_from_db()
        self.assertIsNone(member.client_id)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post('/api/invitation/claim/', claim, content_type='application/json').status_code, 200)
        member.refresh_from_db(); person.refresh_from_db()
        self.assertEqual(member.client, person)
        self.assertEqual(member.state, 'pending')
        self.assertEqual(person.email, 'owner@example.invalid')
        self.assertEqual(person.category, 'particular')

    def test_query_is_associated_but_does_not_create_worker_client_or_account(self):
        count = User.objects.count()
        result = self.post(data=self.query(agreement=self.traditional.pk, registration_rut='12345678-5'), purpose='inquiry')
        self.assertEqual(result.status_code, 201, result.content)
        row = Inquiry.objects.get()
        self.assertEqual((row.origin, row.agreement, row.kind, row.verification_state), ('qr_inquiry', self.agreement, 'contacto', ''))
        self.assertFalse(UnionMembership.objects.exists())
        self.assertFalse(Client.objects.exists())
        self.assertEqual(User.objects.count(), count)

    def test_only_authorized_public_benefits_are_shown(self):
        for name, visible, dates in [('Público ficticio', True, {}), ('Privado ficticio', False, {}),
                                    ('Vencido ficticio', True, {'ends_on': timezone.localdate()-timedelta(days=1)})]:
            AgreementBenefit.objects.create(agreement=self.agreement, name=name, public_visible=visible, active=True, kind='percent', value=10, **dates)
        result = self.client.get(url(self.agreement, 'inquiry')).json()
        self.assertEqual([r['name'] for r in result['benefits']], ['Público ficticio'])
        self.assertNotIn('workers', result)

    def test_query_can_request_available_calendar_slot_and_reject_occupied_slot(self):
        available = self.client.get('/api/agenda/').json()['days'][0]
        data = self.query(kind='agenda', day=available['day'], slot=available['slots'][0])
        self.assertEqual(self.post(data=data, purpose='inquiry').status_code, 201)
        self.assertEqual(AppointmentReservation.objects.count(), 1)
        data.update(idempotency_key=str(uuid4()), reason='Otra consulta ficticia')
        self.assertEqual(self.post(data=data, purpose='inquiry').status_code, 409)

    def test_bad_challenges_honeypot_and_malformed_payload_are_rejected(self):
        for data in ([], {'challenge': []}, worker_payload(self.agreement, website='bot'),
                     worker_payload(self.agreement, challenge=challenge(self.agreement, 'worker', time.time()-7200)),
                     worker_payload(self.agreement, challenge=challenge(self.traditional, 'worker'))):
            self.client.logout()
            self.assertEqual(self.client.post(url(self.agreement), data, content_type='application/json').status_code, 400)
        self.assertFalse(Inquiry.objects.exists())

    def test_public_post_requires_csrf(self):
        browser = Browser(enforce_csrf_checks=True)
        self.assertEqual(browser.post(url(self.agreement), worker_payload(self.agreement), content_type='application/json').status_code, 403)


class ConcurrentOrganizationQRTests(TransactionTestCase):
    def test_simultaneous_retries_create_one_registration(self):
        cache.clear()
        agreement = Agreement.objects.create(name='DEMO concurrencia QR')
        data = worker_payload(agreement)
        barrier = Barrier(2)
        def send():
            connections.close_all()
            try:
                request = APIRequestFactory().post(url(agreement), data, format='json')
                barrier.wait(timeout=10)
                return public(request, 'worker', agreement.worker_qr_token).status_code
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: send(), range(2)))
        self.assertEqual(sorted(results), [200, 201])
        self.assertEqual(Inquiry.objects.filter(agreement=agreement).count(), 1)
