import base64
import tempfile
import shutil
import uuid
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from PIL import Image,ImageDraw
from django.test import TestCase,TransactionTestCase,Client as HTTPClient,override_settings
from django.core.management import call_command
from django.contrib.auth.models import User,Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.db import IntegrityError,transaction,connection
from django.utils import timezone
from django.core.cache import cache
from .models import *
from .services import convert_quote,accept_receipt
from .storage import PrivateStorage,PublicStorage


def png():
    b=BytesIO();image=Image.new('RGB',(200,80),'white')
    ImageDraw.Draw(image).line([(5,50),(30,10),(80,60),(150,20)],fill='black',width=3)
    image.save(b,format='PNG');return b.getvalue()


class APITests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass();cls.temp=tempfile.mkdtemp(prefix='amaru-test-')
        cls.override=override_settings(MEDIA_ROOT=cls.temp);cls.override.enable()
    @classmethod
    def tearDownClass(cls):
        cls.override.disable();shutil.rmtree(cls.temp);super().tearDownClass()
    def setUp(self):
        cache.clear();call_command('configure_roles',verbosity=0)
        self.staff=User.objects.create_user('staff_api',password='fictitious-test-password')
        self.staff.groups.add(Group.objects.get(name='Personal de atención'))
        self.owner=User.objects.create_user('owner_api',password='fictitious-test-password')
        self.stranger=User.objects.create_user('stranger_api',password='fictitious-test-password')
        self.clientrow=Client.objects.create(rut='12345678-5',name='Cliente ficticio API',phone='00000000',category='particular',user=self.owner)
        self.recipe=Prescription.objects.create(client=self.clientrow,issued_on=timezone.localdate(),file=SimpleUploadedFile('fake.png',png()))
        self.http=HTTPClient();self.http.force_login(self.staff)
        self.quote_data={'client':self.clientrow.pk,'prescription':self.recipe.pk,'product_type':'particular','category':'particular','amount':25000,'approved':True,'characteristics':{'frame':'Ficticio','crystal':'Ficticio','focus':'monofocal'}}
    def post(self,url,data):return self.http.post('/api/'+url,data,content_type='application/json')
    def patch(self,url,data):return self.http.patch('/api/'+url,data,content_type='application/json')
    def order(self):
        q=Quote.objects.create(client=self.clientrow,prescription=self.recipe,amount=25000,approved=True,product_type='particular',category='particular',characteristics={'frame':'Ficticio','crystal':'Ficticio','focus':'monofocal'})
        return convert_quote(q.pk,self.staff)
    def inquiry(self,**kwargs):
        d={'kind':'agenda','name':'Visitante ficticio','phone':'+56900000000','email':'ficticio@example.invalid','service':'Orientación','reason':'Consulta de prueba','day':timezone.localdate().isoformat(),'slot':'09:00','contact_authorized':True,'idempotency_key':str(uuid.uuid4())};d.update(kwargs);return d
    def test_session_login_logout_and_csrf(self):
        secure=HTTPClient(enforce_csrf_checks=True)
        self.assertEqual(secure.post('/api/login/',{},content_type='application/json').status_code,403)
        session=secure.get('/api/session/').json();token=session['csrf']
        r=secure.post('/api/login/',{'username':'staff_api','password':'fictitious-test-password'},content_type='application/json',HTTP_X_CSRFTOKEN=token)
        self.assertEqual(r.status_code,200)
        self.assertEqual(secure.get('/api/clients/').status_code,200)
        self.assertEqual(secure.post('/api/logout/',{},content_type='application/json',HTTP_X_CSRFTOKEN=r.json()['csrf']).status_code,200)
    def test_login_rate_limit(self):
        guest=HTTPClient()
        for _ in range(10):self.assertEqual(guest.post('/api/login/',{'username':'bad','password':'bad'},content_type='application/json').status_code,400)
        self.assertEqual(guest.post('/api/login/',{},content_type='application/json').status_code,429)
    def test_register_search_update_and_deactivate_client(self):
        r=self.post('clients/',{'rut':'11.111.111-1','name':'Nuevo ficticio','phone':'00000000','email':'new@example.invalid','category':'particular','consent':True})
        self.assertEqual(r.status_code,201,r.content);pk=r.json()['id']
        self.assertEqual(self.http.get('/api/clients/?q=11.111.111-1').json()['count'],1)
        self.assertEqual(self.patch(f'clients/{pk}/',{'active':False,'consent':False}).status_code,200)
        obj=Client.objects.get(pk=pk);self.assertFalse(obj.active);self.assertEqual(obj.consents.count(),2)
    def test_reject_invalid_and_duplicate_rut(self):
        d={'rut':'12345678-5','name':'Duplicado','phone':'00000000','category':'particular'}
        self.assertEqual(self.post('clients/',d).status_code,400)
        d['rut']='12345678-9';self.assertEqual(self.post('clients/',d).status_code,400)
    def test_no_anonymous_personal_data(self):
        guest=HTTPClient()
        for route in ['clients/','prescriptions/','orders/','receipts/','inquiries/','audit/']:
            self.assertIn(guest.get('/api/'+route).status_code,[401,403])
    def test_own_orders_only_and_idor(self):
        o=self.order();self.http.force_login(self.stranger)
        self.assertEqual(self.http.get('/api/orders/').json()['count'],0)
        self.assertEqual(self.http.get(f'/api/orders/{o.pk}/').status_code,404)
        self.http.force_login(self.owner);self.assertEqual(self.http.get('/api/orders/').json()['count'],1)
    def test_workshop_permissions(self):
        workshop=User.objects.create_user('workshop');workshop.groups.add(Group.objects.get(name='Taller'));self.http.force_login(workshop)
        self.assertEqual(self.http.get('/api/orders/').status_code,200)
        self.assertEqual(self.http.get('/api/clients/').status_code,403)
        self.assertEqual(self.http.get(f'/api/prescriptions/{self.recipe.pk}/file/').status_code,403)
    def test_prescription_upload_and_invalid_bytes(self):
        r=self.http.post('/api/prescriptions/',{'client':self.clientrow.pk,'issued_on':timezone.localdate(),'file':SimpleUploadedFile('test.png',png(),content_type='image/png')})
        self.assertEqual(r.status_code,201,r.content);self.assertNotIn('file',r.json())
        r=self.http.post('/api/prescriptions/',{'client':self.clientrow.pk,'issued_on':timezone.localdate(),'file':SimpleUploadedFile('test.png',b'invalid')})
        self.assertEqual(r.status_code,400)
    def test_authorized_file_and_audit(self):
        self.http.force_login(self.owner)
        r=self.http.get(f'/api/prescriptions/{self.recipe.pk}/file/');self.assertEqual(r.status_code,200)
        self.assertTrue(b''.join(r.streaming_content))
        self.assertTrue(Audit.objects.filter(action='Acceso a documento privado',actor=self.owner).exists())
        self.http.force_login(self.stranger);self.assertEqual(self.http.get(f'/api/prescriptions/{self.recipe.pk}/file/').status_code,403)
    def test_quote_convert_idempotent_and_update_lock(self):
        r=self.post('quotes/',self.quote_data);self.assertEqual(r.status_code,201,r.content);pk=r.json()['id']
        a=self.post(f'quotes/{pk}/convert/',{});b=self.post(f'quotes/{pk}/convert/',{})
        self.assertEqual(a.json()['id'],b.json()['id'])
        self.assertEqual(self.patch(f'quotes/{pk}/',{'amount':1}).status_code,400)
    def test_reject_other_clients_recipe(self):
        other=Client.objects.create(rut='11111111-1',name='Otro ficticio',phone='00000000',category='particular')
        self.assertEqual(self.post('quotes/',dict(self.quote_data,client=other.pk)).status_code,400)
    def test_unapproved_quote_cannot_convert(self):
        r=self.post('quotes/',dict(self.quote_data,approved=False));pk=r.json()['id']
        self.assertEqual(self.post(f'quotes/{pk}/convert/',{}).status_code,400)
    def test_public_inquiry_persists_and_duplicate_retry(self):
        self.http.logout();d=self.inquiry();a=self.post('inquiries/',d);b=self.post('inquiries/',d)
        self.assertEqual(a.status_code,201,a.content);self.assertEqual(b.status_code,200)
        self.assertEqual(Inquiry.objects.count(),1);self.assertEqual(AppointmentReservation.objects.count(),1)
        self.http.force_login(self.staff);self.assertEqual(self.http.get('/api/inquiries/').json()['count'],1)
    def test_appointment_conflict_and_cancellation(self):
        d=self.inquiry();self.assertEqual(self.post('inquiries/',d).status_code,201)
        self.assertEqual(self.post('inquiries/',self.inquiry()).status_code,409)
        pk=Inquiry.objects.get().pk
        self.assertEqual(self.patch(f'inquiries/{pk}/',{'status':'Cancelada'}).status_code,200)
        self.assertEqual(self.post('inquiries/',self.inquiry()).status_code,201)
        self.assertEqual(self.patch(f'inquiries/{pk}/',{'status':'Nueva'}).status_code,400)
    def test_bad_public_inquiry(self):
        self.assertEqual(self.post('inquiries/',self.inquiry(contact_authorized=False)).status_code,400)
        self.assertEqual(self.post('inquiries/',self.inquiry(day='2001-01-01')).status_code,400)
    def test_receipt_full_workflow_and_retry(self):
        o=self.order();o.status='Disponible para retiro';o.save()
        preview=self.http.get(f'/api/orders/{o.pk}/preview/').json()
        d={'review_token':preview['review_token'],'accepted':True,'signature':'data:image/png;base64,'+base64.b64encode(png()).decode(),'observations':'Prueba ficticia'}
        r=self.post(f'orders/{o.pk}/deliver/',d);self.assertEqual(r.status_code,200,r.content)
        self.assertEqual(self.post(f'orders/{o.pk}/deliver/',d).json()['id'],r.json()['id'])
        o.refresh_from_db();self.assertEqual(o.status,'Entregada');receipt=Receipt.objects.get(order=o)
        self.assertEqual(len(receipt.sha256),64);self.assertTrue(receipt.pdf.storage.exists(receipt.pdf.name))
        self.assertTrue(Audit.objects.filter(model='receipt',record_id=receipt.pk).exists())
    def test_delivery_without_acceptance_signature_or_review(self):
        o=self.order();o.status='Disponible para retiro';o.save()
        token=self.http.get(f'/api/orders/{o.pk}/preview/').json()['review_token']
        for d in [{},{'review_token':token,'accepted':False},{'review_token':token,'accepted':True,'signature':''}]:
            self.assertEqual(self.post(f'orders/{o.pk}/deliver/',d).status_code,400)
        o.refresh_from_db();self.assertEqual(o.status,'Disponible para retiro')
    def test_upload_failure_rolls_back_and_cleans_signature(self):
        o=self.order();o.status='Disponible para retiro';o.save()
        storage=Receipt._meta.get_field('pdf').storage
        with patch.object(storage,'save',side_effect=OSError('Simulación sin conexión')):
            with self.assertRaises(OSError):accept_receipt(o.pk,self.staff,True,'data:image/png;base64,'+base64.b64encode(png()).decode())
        o.refresh_from_db();self.assertEqual(o.status,'Disponible para retiro');self.assertFalse(Receipt.objects.filter(order=o).exists())
        attempt=DeliveryAttempt.objects.get();self.assertEqual(attempt.state,'failed')
        self.assertFalse(Receipt._meta.get_field('signature').storage.exists(attempt.signature_key))
    def test_stale_review_and_forbidden_state(self):
        o=self.order();o.status='Disponible para retiro';o.save()
        preview=self.http.get(f'/api/orders/{o.pk}/preview/').json();o.notes='Cambio';o.save()
        r=self.post(f'orders/{o.pk}/deliver/',{'review_token':preview['review_token'],'accepted':True,'signature':'data:image/png;base64,'+base64.b64encode(png()).decode()})
        self.assertEqual(r.status_code,400)
        self.assertEqual(self.post(f'orders/{o.pk}/state/',{'status':'Entregada'}).status_code,400)
    def test_protected_foreign_keys_and_unique_constraints(self):
        o=self.order()
        from django.db.models.deletion import ProtectedError
        with self.assertRaises(ProtectedError):self.clientrow.delete()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():Client.objects.create(rut=self.clientrow.rut,name='Duplicado',phone='0',category='particular')
    def test_catalog_public_and_admin_only_upload(self):
        Product.objects.create(sku='TEST-1',name='Catálogo ficticio',category='armazon')
        guest=HTTPClient();self.assertEqual(guest.get('/api/products/').json()['count'],1)
        self.assertIn(guest.post('/api/products/',{}).status_code,[401,403])
    def test_quote_items_total_and_no_duplicate(self):
        product=Product.objects.create(sku='TEST-1',name='Catálogo ficticio',category='armazon')
        q=self.post('quotes/',dict(self.quote_data,approved=False)).json()['id']
        d={'product':product.pk,'quantity':2,'unit_price':10000}
        r=self.post(f'quotes/{q}/items/',d);self.assertEqual(r.status_code,200,r.content);self.assertEqual(r.json()['amount'],'20000')
        self.assertEqual(self.post(f'quotes/{q}/items/',d).status_code,400)
        self.assertEqual(self.patch(f'quotes/{q}/',{'amount':1}).status_code,400)
    def test_warranty_and_audit_permissions(self):
        o=self.order();d={'order':o.pk,'kind':'Reparación','reason':'Varilla','description':'Falla ficticia','status':'Rechazada','justification':''}
        self.assertEqual(self.post('warranties/',d).status_code,400)
        d['justification']='Fuera de condiciones de prueba';self.assertEqual(self.post('warranties/',d).status_code,201)
        self.assertEqual(self.http.get('/api/audit/').status_code,403)
    def test_all_frontend_shells_keep_design_without_demo_storage(self):
        root=Path(settings.BASE_DIR).parent/'frontend_amaru'
        for html in root.glob('*.html'):
            r=self.http.get('/app/'+html.name);self.assertEqual(r.status_code,200)
            self.assertContains(r,'/static/server.js');self.assertNotContains(r,'src="js/storage.js')
    @override_settings(R2_ACCESS_KEY_ID='fictitious',R2_SECRET_ACCESS_KEY='fictitious',R2_ACCOUNT_ID='fictitious',R2_ENDPOINT_URL='https://fictitious.r2.cloudflarestorage.com',R2_BUCKET_PRIVADO='amaru-privado',R2_BUCKET_PUBLICO='amaru-publico',R2_DOMINIO_PUBLICO='pub-fictitious.r2.dev',R2_URL_SECONDS=600)
    def test_r2_configuration_and_signed_url_offline(self):
        from urllib.parse import urlsplit,parse_qs
        private=PrivateStorage();public=PublicStorage()
        self.assertEqual(private.bucket_name,'amaru-privado');self.assertEqual(public.bucket_name,'amaru-publico')
        self.assertIsNone(private.custom_domain);self.assertTrue(private.querystring_auth);self.assertFalse(public.querystring_auth)
        url=private.url('recetas/ficticia.png');query=parse_qs(urlsplit(url).query)
        self.assertEqual(query['X-Amz-Expires'],['600']);self.assertIn('X-Amz-Signature',query)
    def test_status_index_exists(self):
        constraints=connection.introspection.get_constraints(connection.cursor(),Order._meta.db_table)
        self.assertIn('order_status_date',constraints)

    def test_blank_signature_is_rejected_on_server(self):
        o=self.order();o.status='Disponible para retiro';o.save()
        buffer=BytesIO();Image.new('RGB',(200,80),'white').save(buffer,format='PNG')
        with self.assertRaises(ValidationError):accept_receipt(o.pk,self.staff,True,'data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode())
        self.assertFalse(Receipt.objects.filter(order=o).exists())

    def test_malformed_json_fields_return_validation_errors(self):
        guest=HTTPClient()
        self.assertEqual(guest.post('/api/login/',{'username':[],'password':{}},content_type='application/json').status_code,400)
        o=self.order()
        self.assertEqual(self.post(f'orders/{o.pk}/state/',{'status':[]}).status_code,400)
        self.assertEqual(self.post(f'orders/{o.pk}/deliver/',{'review_token':[]}).status_code,400)


class ConcurrencyTests(TransactionTestCase):
    def test_simultaneous_delivery_has_one_receipt(self):
        if connection.vendor!='mysql':self.skipTest('La concurrencia real se comprueba con MariaDB.')
        from concurrent.futures import ThreadPoolExecutor
        from django.db import close_old_connections
        folder=tempfile.mkdtemp(prefix='amaru-concurrency-')
        with override_settings(MEDIA_ROOT=folder):
            user=User.objects.create_user('fictitious-concurrency')
            c=Client.objects.create(rut='12345678-5',name='FICTICIO concurrencia',phone='00000000',category='particular')
            p=Prescription.objects.create(client=c,issued_on=timezone.localdate(),file='recetas/ficticia.png')
            q=Quote.objects.create(client=c,prescription=p,category='particular',product_type='particular',amount=10000,approved=True)
            o=convert_quote(q.pk,user);o.status='Disponible para retiro';o.save()
            signature='data:image/png;base64,'+base64.b64encode(png()).decode()
            def deliver():
                close_old_connections()
                try:return accept_receipt(o.pk,User.objects.get(pk=user.pk),True,signature).pk
                finally:connection.close()
            with ThreadPoolExecutor(max_workers=2) as pool:
                ids=list(pool.map(lambda _:deliver(),range(2)))
            self.assertEqual(ids[0],ids[1]);self.assertEqual(Receipt.objects.filter(order=o).count(),1)
            o.refresh_from_db();self.assertEqual(o.status,'Entregada')
        shutil.rmtree(folder)
