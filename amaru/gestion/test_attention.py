"""Flujo público, protección de fichas existentes y frontera del túnel."""
import uuid
from django.test import TestCase,Client as HTTPClient,override_settings
from django.contrib.auth.models import User,Permission
from django.core.cache import cache
from django.utils import timezone
from .models import Client,Inquiry,AppointmentReservation

class AttentionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.http=HTTPClient()
        self.staff=User.objects.create_user('qr_staff')
        self.staff.user_permissions.add(Permission.objects.get(codename='view_inquiry'),Permission.objects.get(codename='change_inquiry'))
    def data(self,**values):
        data={'kind':'contacto','name':'Persona FICTICIA QR','phone':'+56900000000','email':'ficticio@example.invalid','service':'Orientación','reason':'Solicitud ficticia académica','contact_authorized':True,'idempotency_key':str(uuid.uuid4()),'source':'qr'}
        data.update(values);return data
    def send(self,data):return self.http.post('/api/inquiries/',data,content_type='application/json')
    def test_anonymous_submission_requires_csrf(self):
        guest=HTTPClient(enforce_csrf_checks=True)
        response=guest.post('/api/inquiries/',self.data(),content_type='application/json')
        self.assertEqual(response.status_code,403);self.assertFalse(Inquiry.objects.exists())
    def test_public_contact_does_not_create_client(self):
        self.assertEqual(self.send(self.data()).status_code,201)
        self.assertEqual(Inquiry.objects.get().source,'qr');self.assertEqual(Client.objects.count(),0)
    def test_registration_creates_pending_client_without_account_or_marketing(self):
        self.assertEqual(self.send(self.data(kind='registro',registration_rut='12.345.678-5')).status_code,201)
        row=Client.objects.get();self.assertEqual(row.rut,'12345678-5');self.assertFalse(row.active);self.assertFalse(row.consent);self.assertIsNone(row.user_id)
        self.assertEqual(Inquiry.objects.get().client_id,row.pk)
    def test_existing_rut_is_never_overwritten(self):
        old=Client.objects.create(rut='12345678-5',name='Ficha previa ficticia',phone='00000000',category='particular',consent=True)
        response=self.send(self.data(kind='registro',registration_rut=old.rut))
        self.assertEqual(response.status_code,201);old.refresh_from_db();self.assertEqual(old.name,'Ficha previa ficticia');self.assertTrue(old.consent);self.assertEqual(Client.objects.count(),1)
        self.assertNotIn('client',response.json())
    def test_invalid_or_missing_registration_rut(self):
        for rut in ('','12345678-0'):
            self.assertEqual(self.send(self.data(kind='registro',registration_rut=rut)).status_code,400)
        self.assertFalse(Client.objects.exists());self.assertFalse(Inquiry.objects.exists())
    def test_no_rut_required_for_contact_and_email_optional(self):
        self.assertEqual(self.send(self.data(email='')).status_code,201)
    def test_no_rut_accepted_for_contact(self):
        self.assertEqual(self.send(self.data(registration_rut='12345678-5')).status_code,400)
    def test_invalid_email_phone_and_long_name(self):
        for values in ({'email':'incorrecto'},{'phone':'++++++++'},{'phone':'1234567890123456'},{'name':'x'*181}):
            self.assertEqual(self.send(self.data(**values)).status_code,400)
    def test_consent_required_and_honeypot_rejected(self):
        self.assertEqual(self.send(self.data(contact_authorized=False)).status_code,400)
        self.assertEqual(self.send(self.data(website='bot')).status_code,400)
    def test_bad_dates_and_seconds_rejected(self):
        for values in ({'day':'2001-01-01','slot':'09:00'},{'day':str(timezone.localdate()),'slot':'09:00:01'}):
            self.assertEqual(self.send(self.data(kind='agenda',**values)).status_code,400)
    def test_idempotent_retry_and_changed_payload(self):
        data=self.data();self.assertEqual(self.send(data).status_code,201);self.assertEqual(self.send(data).status_code,200)
        self.assertEqual(self.send(dict(data,name='Otra persona')).status_code,409);self.assertEqual(Inquiry.objects.count(),1)
        # Simular otro envío que termina entre la consulta inicial y get_or_create.
        from unittest.mock import patch
        with patch('gestion.services.Inquiry.objects.filter') as query:
            query.return_value.first.return_value=None
            query.return_value.exclude.return_value.exists.return_value=False
            self.assertEqual(self.send(dict(data,name='Otra persona')).status_code,409)
    def test_equivalent_submission_new_key_is_rejected(self):
        self.assertEqual(self.send(self.data()).status_code,201);self.assertEqual(self.send(self.data()).status_code,409);self.assertEqual(Inquiry.objects.count(),1)
    def test_slot_conflict_rolls_back_inquiry(self):
        data=self.data(kind='agenda',day=str(timezone.localdate()),slot='09:00')
        self.assertEqual(self.send(data).status_code,201)
        self.assertEqual(self.send(self.data(kind='agenda',day=data['day'],slot='09:00',reason='Otro motivo ficticio')).status_code,409)
        self.assertEqual(Inquiry.objects.count(),1);self.assertEqual(AppointmentReservation.objects.count(),1)
    @override_settings(ATTENTION_RATE_LIMIT=2)
    def test_submission_limit(self):
        self.send(self.data(reason='Prueba uno'));self.send(self.data(reason='Prueba dos'))
        self.assertEqual(self.send(self.data(reason='Prueba tres')).status_code,429)
    def test_detail_private_and_staff_filters(self):
        self.send(self.data());pk=Inquiry.objects.get().pk
        self.assertEqual(self.http.get(f'/api/inquiries/{pk}/').status_code,403)
        self.http.force_login(self.staff)
        self.assertEqual(self.http.get(f'/api/inquiries/{pk}/').status_code,200)
        self.assertEqual(self.http.get('/api/inquiries/?status=Nueva').json()['count'],1)
        self.assertEqual(self.http.get('/api/inquiries/?status=Cerrada').json()['count'],0)
        self.assertEqual(self.http.get('/api/inquiries/?day=no-fecha').status_code,400)
    def test_customer_cannot_view_intake_or_qr(self):
        self.http.force_login(User.objects.create_user('cliente_qr'))
        self.assertEqual(self.http.get('/api/inquiries/').status_code,403)
        self.assertEqual(self.http.get('/api/attention-qr/').status_code,403)
    @override_settings(ATTENTION_URL_FILE='nonexistent-demo-file',ATTENTION_PUBLIC_BASE_URL='https://atencion.example.invalid')
    def test_qr_authorized_and_uses_central_url(self):
        self.http.force_login(self.staff)
        self.assertEqual(self.http.get('/api/attention-qr/').json()['url'],'https://atencion.example.invalid/app/formulario_remoto.html?origen=qr')
        response=self.http.get('/api/attention-qr/?image=png');self.assertEqual(response.status_code,200);self.assertTrue(response.content.startswith(b'\x89PNG'))
    @override_settings(ATTENTION_URL_FILE='nonexistent-demo-file',ATTENTION_PUBLIC_BASE_URL='http://127.0.0.1:8001')
    def test_loopback_qr_not_generated(self):
        self.http.force_login(self.staff);self.assertFalse(self.http.get('/api/attention-qr/').json()['scannable'])
        self.assertEqual(self.http.get('/api/attention-qr/?image=png').status_code,400)

class PublicBoundaryTests(TestCase):
    @override_settings(ROOT_URLCONF='config.attention_public_urls',MIDDLEWARE=['gestion.attention_public.PublicBoundaryMiddleware'])
    def test_only_public_routes_exposed(self):
        for path in ('/admin/','/api/clients/','/api/inquiries/','/api/orders/','/api/login/','/app/dashboard.html','/static/demo-credentials.json'):
            self.assertEqual(self.client.get(path).status_code,404,path)
        self.assertEqual(self.client.get('/app/formulario_remoto.html').status_code,200)

    @override_settings(ROOT_URLCONF='config.attention_public_urls',MIDDLEWARE=['gestion.attention_public.PublicBoundaryMiddleware'])
    def test_static_styles_and_bootstrap_available(self):
        for path in ('/static/interfaz/css/styles.css','/static/interfaz/css/actualizacion.css','/static/interfaz/js/bootstrap.js','/static/server.js','/static/attention.css'):
            response=self.client.get(path);self.assertEqual(response.status_code,200,path);response.close()
    @override_settings(ROOT_URLCONF='config.attention_public_urls',MIDDLEWARE=['gestion.attention_public.PublicBoundaryMiddleware'],ATTENTION_PUBLIC_ONLY=True)
    def test_public_origin_rejects_plain_http(self):
        self.assertEqual(self.client.get('/app/formulario_remoto.html').status_code,400)
        self.assertEqual(self.client.get('/app/formulario_remoto.html',secure=True).status_code,200)
