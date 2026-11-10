from datetime import timedelta
from io import BytesIO
from uuid import uuid4

from PIL import Image
from django.contrib.auth.models import Permission, User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from tempfile import TemporaryDirectory

from .models import Agreement, Client, Inquiry, Prescription, Product


class CatalogAndAgreementTests(TestCase):
    def setUp(self):
        cache.clear()
        self.product = Product.objects.create(sku="ACA-001", name="Cristal ficticio", category="cristal", requires_prescription=True)
        self.worker = User.objects.create_user("catalog_worker")
        codes = ["view_product", "add_product", "change_product", "change_agreement", "view_agreement", "view_client", "view_inquiry"]
        self.worker.user_permissions.add(*Permission.objects.filter(codename__in=codes))
        self.customer = User.objects.create_user("catalog_customer")
        self.owner = Client.objects.create(user=self.customer, rut="12345678-5", name="Ficha ficticia", phone="+56900000000", category="particular")
        self.agreement = Agreement.objects.create(name="Convenio ficticio")

    def post(self, path, data):
        return self.client.post(path, data, content_type="application/json")

    def request_product(self, **fields):
        data = dict(product=self.product.pk, reason="Necesidad ficticia", contact_authorized=True, idempotency_key=str(uuid4()))
        return self.post("/api/product-requests/", data | fields)

    def register(self, **fields):
        data = dict(kind="registro", name="Nombre nuevo ficticio", phone="+56900000001", service="Convenio", reason="Solicitud académica",
                    source="qr", registration_rut=self.owner.rut, contact_authorized=True, idempotency_key=str(uuid4()),
                    agreement_code=self.agreement.code, agreement_role="titular")
        return self.post("/api/inquiries/", data | fields)

    def test_management_can_deactivate_and_public_filters_active(self):
        path = f"/api/catalog-management/{self.product.pk}/"
        self.assertEqual(self.client.get(path).status_code, 403)
        self.assertEqual(self.client.get("/api/products/?q=Cristal&category=cristal").json()["count"], 1)
        self.client.force_login(self.worker)
        self.assertEqual(self.client.patch(path, {"active": False}, content_type="application/json").status_code, 200)
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.get(f"/api/products/{self.product.pk}/").status_code, 404)
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())

    def test_recipe_required_and_must_belong_to_customer(self):
        self.assertEqual(self.request_product().status_code, 403)
        self.client.force_login(self.customer)
        self.assertEqual(self.request_product().status_code, 400)
        other = Client.objects.create(rut="11111111-1", name="Otro ficticio", phone="+56900000000", category="particular")
        recipe = Prescription.objects.create(client=other, issued_on=timezone.localdate(), file="recetas/ajena.png")
        self.assertEqual(self.request_product(prescription=recipe.pk).status_code, 404)
        expired = Prescription.objects.create(client=self.owner, issued_on=timezone.localdate()-timedelta(days=500), file="recetas/vencida.png")
        self.assertEqual(self.request_product(prescription=expired.pk).status_code, 400)
        self.assertFalse(Inquiry.objects.exists())

    def test_valid_image_upload_and_linked_request(self):
        self.client.force_login(self.customer)
        with TemporaryDirectory() as private, override_settings(MEDIA_ROOT=private):
            url = "/api/my-prescriptions/"
            issued = timezone.localdate().isoformat()
            self.assertEqual(self.client.post(url, {"issued_on": issued, "file": SimpleUploadedFile("bad.png", b"text")}).status_code, 400)
            output = BytesIO()
            Image.new("RGB", (64, 64), "white").save(output, format="PNG")
            response = self.client.post(url, {"issued_on": issued, "file": SimpleUploadedFile("demo.png", output.getvalue())})
            self.assertEqual(response.status_code, 201, response.content)
            response = self.request_product(prescription=response.json()["id"])
            self.assertEqual(response.status_code, 201, response.content)
            row = Inquiry.objects.get()
            self.assertEqual(row.prescription.client_id, self.owner.pk)
            self.assertEqual(row.product_id, self.product.pk)

    def test_convenio_code_does_not_approve_or_change_existing_details(self):
        self.assertEqual(self.register(agreement_role="carga").status_code, 400)
        self.assertEqual(self.register().status_code, 201)
        inquiry = Inquiry.objects.get()
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.name, "Ficha ficticia")
        self.assertIsNone(self.owner.agreement_id)
        self.assertEqual(inquiry.verification_state, "pendiente")
        url = f"/api/agreement-verifications/{inquiry.pk}/"
        data = dict(approved=True, method="presencial", note="Verificación ficticia")
        self.client.force_login(self.customer)
        self.assertEqual(self.post(url, data).status_code, 403)
        self.client.force_login(self.worker)
        self.assertEqual(self.post(url, data).status_code, 200)
        self.assertEqual(self.post(url, data).status_code, 409)
        result = self.client.get(f"/api/clients/{self.owner.pk}/agreement/").json()
        self.assertTrue(result["verified"] and result["available"])
        self.assertEqual(result["role"], "titular")

    @override_settings(ATTENTION_PUBLIC_BASE_URL="https://demo.example.invalid")
    def test_qr_contains_only_public_code_and_https(self):
        url = f"/api/agreements/{self.agreement.pk}/qr/"
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.worker)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["url"], f"https://demo.example.invalid/app/formulario_remoto.html?origen=qr&convenio={self.agreement.code}")
        self.assertTrue(self.client.get(url+"?image=png").content.startswith(b"\x89PNG"))
