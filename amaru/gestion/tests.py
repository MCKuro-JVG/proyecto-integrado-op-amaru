import tempfile,shutil,base64
from io import BytesIO
from datetime import date,timedelta
from django.test import TestCase,Client as WebClient,override_settings
from django.contrib.auth.models import User,Group,Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.db import connection,IntegrityError,transaction
from django.utils import timezone
from pypdf import PdfReader
from PIL import Image,ImageDraw
from .models import *
from .forms import *
from .services import *
def png():
    b=BytesIO();image=Image.new('RGB',(120,60),'white');ImageDraw.Draw(image).line([(5,40),(30,10),(80,45)],fill='black',width=3);image.save(b,format='PNG');return b.getvalue()
class WorkflowTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass();cls.temp=tempfile.mkdtemp();cls.override=override_settings(MEDIA_ROOT=cls.temp);cls.override.enable()
    @classmethod
    def tearDownClass(cls):
        cls.override.disable();shutil.rmtree(cls.temp);super().tearDownClass()
    def setUp(self):
        cache.clear()
        self.staff=User.objects.create_user('test_staff','staff@test.example','Test_password_2026!')
        group=Group.objects.create(name='Personal TEST');group.permissions.set(Permission.objects.filter(content_type__app_label='gestion').exclude(content_type__model='audit'));self.staff.groups.add(group)
        self.cuser=User.objects.create_user('test_client','client@test.example','Test_password_2026!')
        self.person=Client.objects.create(rut='12345678-5',name='TEST Client',phone='00000000',category='particular',user=self.cuser)
        self.p=Prescription.objects.create(client=self.person,issued_on=timezone.localdate(),file=SimpleUploadedFile('test.png',png(),content_type='image/png'),actor=self.staff)
        self.web=WebClient();self.web.force_login(self.staff)
        self.data={'client':self.person.pk,'prescription':self.p.pk,'category':'particular','product_type':'seguridad','security_model':'DEMO Seguridad','security_color':'blanco','focus':'monofocal','amount':'45000','approved':'on','notes':'TEST'}
    def quote(self):
        return Quote.objects.create(client=self.person,prescription=self.p,category='particular',product_type='seguridad',characteristics={'focus':'monofocal'},amount=45000,approved=True,actor=self.staff)
    def test_01_email_login_and_hashed_password(self):
        self.web.logout();r=self.web.post('/login/',{'username':'staff@test.example','password':'Test_password_2026!'})
        self.assertEqual(r.status_code,302);self.assertNotEqual(self.staff.password,'Test_password_2026!');self.assertEqual(self.web.get('/').status_code,200)
    def test_02_roles_and_protected_documents(self):
        guest=WebClient();self.assertEqual(guest.get('/clientes/').status_code,302)
        guest.force_login(self.cuser)
        for url in ['/clientes/','/inventario/','/clientes/nuevo/','/admin/auth/user/']:
            self.assertIn(guest.get(url).status_code,[302,403])
        other=Client.objects.create(rut='11111111-1',name='TEST Other',phone='0000',category='particular')
        self.assertEqual(guest.get(f'/clientes/{other.pk}/').status_code,403)
        self.assertEqual(guest.get(f'/archivos/receta/{self.p.pk}/').status_code,200)
        p=Prescription.objects.create(client=other,issued_on=timezone.localdate(),file=SimpleUploadedFile('other.png',png()))
        self.assertEqual(guest.get(f'/archivos/receta/{p.pk}/').status_code,403)
        self.assertEqual(guest.post('/cotizaciones/1/convertir/').status_code,403)
    def test_03_client_creation_and_consent(self):
        r=self.web.post('/clientes/nuevo/',{'rut':'11.111.111-1','name':'TEST New','phone':'0000','email':'new@test.example','category':'particular'})
        self.assertEqual(r.status_code,302);c=Client.objects.get(rut='11111111-1');self.assertFalse(c.consent);self.assertFalse(c.consents.last().authorized)
        self.web.post(f'/clientes/{c.pk}/editar/',{'rut':c.rut,'name':c.name,'phone':c.phone,'category':'particular','consent':'on'})
        c.refresh_from_db();self.assertTrue(c.consent);self.assertEqual(c.consents.count(),2);self.assertIsNotNone(c.consent_at)
    def test_04_rut_validation(self):
        self.assertEqual(normalize_rut('12.345.678-5'),'12345678-5')
        for value in ['12345678-9','abc','123-4']:
            with self.assertRaises(ValidationError):normalize_rut(value)
        r=self.web.post('/clientes/nuevo/',{'rut':'12345678-9','name':'TEST Invalid','phone':'0','category':'particular'})
        self.assertContains(r,'dígito verificador');self.assertEqual(Client.objects.count(),1)
    def test_05_duplicate_rut(self):
        r=self.web.post('/clientes/nuevo/',{'rut':'12.345.678-5'})
        self.assertRedirects(r,f'/clientes/{self.person.pk}/');self.assertEqual(Client.objects.count(),1)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():Client.objects.create(rut='12345678-5',name='TEST duplicate',phone='0',category='particular')
    def test_06_upload_real_file_validation(self):
        data={'client':self.person.pk,'issued_on':timezone.localdate().isoformat(),'file':SimpleUploadedFile('test.png',png(),content_type='image/png')}
        self.assertEqual(self.web.post('/recetas/nuevo/',data).status_code,302)
        for f in [SimpleUploadedFile('fake.png',b'bad'),SimpleUploadedFile('bad.exe',png()),SimpleUploadedFile('large.pdf',b'x'*(10*1024*1024+1))]:
            with self.assertRaises(ValidationError):validate_document(f)
        pdf=BytesIO();SimpleDocTemplate(pdf).build([Paragraph('TEST',getSampleStyleSheet()['BodyText'])]);validate_document(SimpleUploadedFile('test.pdf',pdf.getvalue()))
    def test_07_expiration_calendar_year(self):
        self.assertTrue(self.p.valid)
        self.p.issued_on=timezone.localdate()-timedelta(days=367);self.assertFalse(self.p.valid)
        self.p.issued_on=date(2024,2,29);self.assertEqual(self.p.expires_on,date(2025,2,28))
    def test_08_dynamic_product_server_validation(self):
        f=ProductForm(self.data);self.assertTrue(f.is_valid(),f.errors);self.assertNotIn('frame',f.characteristics())
        d=dict(self.data,product_type='particular',frame='TEST Frame',crystal='TEST crystal',antireflective='on');f=ProductForm(d);self.assertTrue(f.is_valid(),f.errors);self.assertNotIn('security_model',f.characteristics())
        d.pop('frame');self.assertFalse(ProductForm(d).is_valid())
    def test_09_quote_creation(self):
        self.assertEqual(self.web.post('/cotizaciones/nuevo/',self.data).status_code,302)
        q=Quote.objects.get();self.assertTrue(q.folio.startswith('COT-'));self.assertEqual(q.actor,self.staff)
        self.assertContains(self.web.get('/cotizaciones/?q=12.345.678-5'),q.folio)
    def test_10_convert_idempotent_and_stock(self):
        q=self.quote();item=Inventory.objects.create(name='TEST Stock',category='seguridad',quantity=2)
        o=convert_quote(q.pk,self.staff,item.pk);item.refresh_from_db();self.assertEqual(item.quantity,1)
        self.assertEqual(convert_quote(q.pk,self.staff,item.pk).pk,o.pk);item.refresh_from_db();self.assertEqual(item.quantity,1)
        self.assertEqual(o.actor,self.staff);self.assertEqual(o.prescription,self.p)
    def test_11_conversion_requires_approved_valid_own_recipe(self):
        q=self.quote();q.approved=False;q.save()
        with self.assertRaises(ValidationError):convert_quote(q.pk,self.staff)
        q.approved=True;q.save();self.p.issued_on=timezone.localdate()-timedelta(days=370);self.p.save()
        with self.assertRaises(ValidationError):convert_quote(q.pk,self.staff)
        other=Client.objects.create(rut='11111111-1',name='TEST Other',phone='0',category='particular')
        self.assertFalse(ProductForm(dict(self.data,client=other.pk)).is_valid())
    def test_12_warranty_and_rejection_justification(self):
        o=convert_quote(self.quote().pk,self.staff)
        r=self.web.post('/garantias/nuevo/',{'order':o.pk,'kind':'Reparación','reason':'TEST Varilla','description':'TEST Falla'})
        self.assertEqual(r.status_code,302);w=Warranty.objects.get()
        r=self.web.post(f'/garantias/{w.pk}/estado/',{'status':'Rechazada'})
        self.assertContains(r,'justificación es obligatoria');w.refresh_from_db();self.assertEqual(w.status,'En revisión taller')
        r=self.web.post(f'/garantias/{w.pk}/estado/',{'status':'Rechazada','justification':'TEST Motivo taller'})
        self.assertEqual(r.status_code,302);w.refresh_from_db();self.assertEqual(w.status,'Rechazada');self.assertTrue(Audit.objects.filter(model='warranty',record_id=w.pk,action__contains='Rechazada').exists())
    def test_13_order_states_and_history(self):
        o=convert_quote(self.quote().pk,self.staff)
        for state in ['En fabricación','Control de calidad','Disponible para retiro']:
            self.assertEqual(self.web.post(f'/ordenes/{o.pk}/estado/',{'status':state}).status_code,302)
        o.refresh_from_db();self.assertEqual(o.status,'Disponible para retiro');self.assertEqual(Audit.objects.filter(model='order',record_id=o.pk).count(),4)
    def test_14_checkbox_receipt_pdf(self):
        o=convert_quote(self.quote().pk,self.staff);o.status='Disponible para retiro';o.save()
        r=self.web.post(f'/ordenes/{o.pk}/recepcion/',{'accepted':'on'});self.assertEqual(r.status_code,302)
        rec=Receipt.objects.get();o.refresh_from_db();self.assertEqual(o.status,'Entregada')
        text=' '.join(p.extract_text() for p in PdfReader(rec.pdf.path).pages)
        self.assertIn('Condiciones de garantía',text);self.assertIn(o.folio,text)
        self.assertEqual(accept_receipt(o.pk,self.staff,True,'').pk,rec.pk)
    def test_15_signature_and_reception_validation(self):
        o=convert_quote(self.quote().pk,self.staff)
        with self.assertRaises(ValidationError):accept_receipt(o.pk,self.staff,True,'')
        o.status='Disponible para retiro';o.save()
        with self.assertRaises(ValidationError):accept_receipt(o.pk,self.staff,False,'')
        rec=accept_receipt(o.pk,self.staff,False,'data:image/png;base64,'+base64.b64encode(png()).decode());self.assertTrue(rec.signature);self.assertEqual(rec.method,'Firma en pantalla')
    def test_16_public_lookup_no_medical_data(self):
        o=convert_quote(self.quote().pk,self.staff);guest=WebClient()
        r=guest.post('/consulta/',{'rut':self.person.rut,'folio':o.folio})
        self.assertContains(r,o.status);self.assertNotContains(r,self.person.name);self.assertNotContains(r,'test.png')
        r=guest.post('/consulta/',{'rut':'11111111-1','folio':o.folio});self.assertContains(r,'No se encontró')
        r=guest.post('/consulta/',{'rut':self.person.rut,'folio':o.folio[:9]});self.assertContains(r,'No se encontró')
    def test_17_remote_request_and_existing_rut_privacy(self):
        d={'rut':'11111111-1','name':'TEST Remote','phone':'0000','category':'particular','product_type':'seguridad','security_model':'DEMO Full Face','security_color':'fotocromatico','focus':'multifocal','exam_requested':'on'}
        guest=WebClient();r=guest.post('/solicitar/',d);self.assertEqual(r.status_code,302)
        req=Request.objects.get();self.assertTrue(req.exam_requested);self.assertTrue(req.folio.startswith('SOL-'))
        self.assertContains(guest.get('/solicitar/confirmacion/'),req.folio)
        guest.post('/solicitar/',dict(d,rut=self.person.rut,name='Changed name'))
        self.person.refresh_from_db();self.assertEqual(self.person.name,'TEST Client');self.assertEqual(Client.objects.count(),2)
    def test_18_database_and_csrf(self):
        self.assertIn(connection.vendor,['mysql','postgresql','sqlite'])
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1');self.assertEqual(cursor.fetchone()[0],1)
        secure=WebClient(enforce_csrf_checks=True);self.assertEqual(secure.post('/solicitar/',{}).status_code,403)
    def test_19_client_portal_own_receipt(self):
        o=convert_quote(self.quote().pk,self.staff);o.status='Disponible para retiro';o.save()
        guest=WebClient();guest.force_login(self.cuser)
        self.assertContains(guest.get('/'),self.person.name)
        self.assertEqual(guest.post(f'/ordenes/{o.pk}/recepcion/',{'accepted':'on'}).status_code,302)
    def test_20_agreement_required_and_audit(self):
        self.assertFalse(ProductForm(dict(self.data,category='convenio')).is_valid())
        agreement=Agreement.objects.create(name='TEST Agreement')
        self.assertTrue(ProductForm(dict(self.data,category='convenio',agreement=agreement.pk)).is_valid())
        q=self.quote();audit(self.staff,'TEST operation',q);entry=Audit.objects.get();self.assertEqual(entry.actor,self.staff);self.assertEqual(entry.record_id,q.pk)
    def test_21_remote_opt_out_always_revokes(self):
        self.person.consent=True;self.person.save()
        d={'rut':self.person.rut,'name':'TEST Remote','phone':'0000','category':'particular','product_type':'seguridad','security_model':'DEMO Seguridad','security_color':'blanco','focus':'monofocal','exam_requested':'on'}
        self.assertEqual(WebClient().post('/solicitar/',d).status_code,302)
        self.person.refresh_from_db();self.assertFalse(self.person.consent)
        self.assertFalse(self.person.consents.last().authorized)
