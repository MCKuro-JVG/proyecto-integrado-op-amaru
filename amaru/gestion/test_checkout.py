"""Checkout desde el carrito: importes del servidor, privacidad e idempotencia."""
from uuid import uuid4
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client as HttpClient, TestCase
from django.utils import timezone
from .models import Inquiry, Order, PaymentVoucher, Prescription, Quote, StockReservation, TransferPayment
from . import test_commercial
from .test_api import png


class CartCheckoutTests(TestCase):
    setUp = test_commercial.CommercialTests.setUp
    post = test_commercial.CommercialTests.post
    upload = test_commercial.CommercialTests.upload
    review = test_commercial.CommercialTests.review
    approve_benefits = test_commercial.CommercialTests.approve_benefits

    def payload(self, **changes):
        return {'items': [{'product': self.product.pk, 'variant': '', 'quantity': 2}],
            'mode': 'compra', 'reason': 'Compra ficticia desde carrito', 'contact_authorized': True,
            'confirmed': True, 'expected_amount': '20000', 'idempotency_key': str(uuid4()), **changes}

    def checkout(self, data=None, user=None):
        return self.post('checkout-payment/', data or self.payload(), user or self.owner)

    def enable(self):
        self.product.direct_checkout = True
        self.product.save()

    def test_enabled_cart_creates_one_payment_quote_and_reservation_on_retry(self):
        self.enable()
        data = self.payload()
        first = self.checkout(data)
        self.assertEqual(first.status_code, 201, first.content)
        payment = first.json()['payment']
        second = self.checkout(data)
        self.assertEqual(second.status_code, 200, second.content)
        self.assertEqual(second.json()['payment']['id'], payment['id'])
        self.assertEqual(TransferPayment.objects.count(), 1)
        self.assertEqual(Inquiry.objects.filter(kind='compra').count(), 1)
        self.assertEqual(Quote.objects.count(), 2)  # Incluye la cotización previa conservada.
        self.assertEqual(StockReservation.objects.get().quantity, 2)
        self.assertFalse(Order.objects.exists())
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 5)
        self.assertEqual(payment['state'], 'pending')
        self.assertEqual(payment['bank']['account_number'], 'DEMO-NO-OPERATIVA')
        self.assertEqual(payment['method'], 'transferencia')

    def test_price_review_gate_preserves_existing_products_and_rolls_back(self):
        self.assertFalse(self.product.direct_checkout)
        response = self.checkout()
        self.assertEqual(response.status_code, 409, response.content)
        self.assertFalse(Inquiry.objects.filter(kind='compra').exists())
        self.assertFalse(TransferPayment.objects.exists())

    def test_client_cannot_enable_checkout_or_choose_amount(self):
        self.client.force_login(self.owner)
        response = self.client.patch(f'/api/catalog-management/{self.product.pk}/',
            {'direct_checkout': True}, content_type='application/json')
        self.assertEqual(response.status_code, 403)
        self.enable()
        response = self.checkout(self.payload(expected_amount='1', amount='1', approved=True))
        self.assertEqual(response.status_code, 409, response.content)
        self.assertFalse(TransferPayment.objects.exists())
        self.assertFalse(StockReservation.objects.exists())

    def test_recipe_requires_review_even_with_valid_private_upload(self):
        self.enable()
        self.product.requires_prescription = True
        self.product.save()
        self.assertEqual(self.checkout().status_code, 400)
        prescription = Prescription.objects.create(client=self.person, issued_on=timezone.localdate(),
            file=SimpleUploadedFile('demo.png', png(), content_type='image/png'))
        self.assertEqual(self.checkout(self.payload(prescription=prescription.pk)).status_code, 409)
        self.assertFalse(TransferPayment.objects.exists())

    def test_current_benefit_is_calculated_and_frozen_in_checkout(self):
        from .models import AgreementBenefit
        self.enable()
        agreement = self.approve_benefits()
        benefit = AgreementBenefit.objects.create(agreement=agreement, name='Beneficio ficticio', kind='percent', value=10, active=True)
        self.client.force_login(self.owner)
        product = self.client.get(f'/api/products/{self.product.pk}/').json()
        self.assertEqual((product['catalog_price'], product['catalog_benefit'], product['availability']),
                         ('9000', benefit.name, 'available'))
        result = self.checkout(self.payload(expected_amount='18000'))
        self.assertEqual(result.status_code, 201, result.content)
        self.assertEqual(result.json()['payment']['amount'], '18000')
        benefit.value = 90
        benefit.save()
        self.assertEqual(TransferPayment.objects.get().amount, 18000)

    def test_identical_new_purchase_and_voucher_replay_are_independent(self):
        self.enable()
        first_data = self.payload()
        first = self.checkout(first_data).json()['payment']
        self.assertEqual(self.upload(first).status_code, 201)
        self.assertEqual(self.upload(first).status_code, 200)
        changed_amount = {**first_data, 'expected_amount': '1'}
        self.assertEqual(self.checkout(changed_amount).status_code, 409)
        second = self.checkout(self.payload()).json()['payment']
        self.assertNotEqual(first['id'], second['id'])
        self.assertNotEqual(first['folio'], second['folio'])
        self.assertEqual(second['state'], 'pending')
        self.assertEqual(self.upload(second).status_code, 201)
        self.assertEqual(PaymentVoucher.objects.values('payment_id').distinct().count(), 2)
        self.assertEqual(StockReservation.objects.count(), 2)

    def test_unavailable_stock_rolls_back_whole_checkout(self):
        self.enable()
        self.item.quantity = 1
        self.item.save()
        self.assertEqual(self.checkout().status_code, 409)
        self.assertFalse(TransferPayment.objects.exists())
        self.assertFalse(Inquiry.objects.filter(kind='compra').exists())

    def test_retry_reference_cannot_be_reassigned_or_change_selection(self):
        self.enable()
        data = self.payload()
        self.assertEqual(self.checkout(data).status_code, 201)
        changed = {**data, 'items': [{'product': self.product.pk, 'variant': '', 'quantity': 1}]}
        self.assertEqual(self.checkout(changed).status_code, 409)
        self.assertEqual(self.checkout(data, self.other).status_code, 409)
        self.assertEqual(TransferPayment.objects.count(), 1)

    def test_voucher_rejection_reupload_approval_and_private_persistence(self):
        self.enable()
        result = self.checkout()
        payment = result.json()['payment']
        invalid = self.upload(payment, SimpleUploadedFile('fake.pdf', b'not a PDF'))
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(self.upload(payment).status_code, 201)
        self.assertEqual(self.review(payment, 'rejected').status_code, 200)
        retry = SimpleUploadedFile('corregido.png', png() + b'ficticio-corregido', content_type='image/png')
        self.assertEqual(self.upload(payment, retry).status_code, 201)
        self.assertEqual(self.review(payment).status_code, 200)
        self.assertEqual(self.review(payment).status_code, 400)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(PaymentVoucher.objects.count(), 2)
        self.client.logout()
        self.client.force_login(self.owner)
        response = self.client.get(f'/api/payments/{payment["id"]}/')
        self.assertEqual(response.json()['state'], 'approved')
        url = response.json()['vouchers'][-1]['url']
        download = self.client.get(url)
        self.assertEqual(download.status_code, 200)
        # El iterador del cliente Django cierra la respuesta y el archivo al agotarse.
        self.assertTrue(b''.join(download.streaming_content))
        preview = self.client.get(url+'?vista=1')
        self.assertIn('inline', preview['Content-Disposition'])
        self.assertIn('no-store', preview['Cache-Control'])
        preview.close()
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.get(url+'?vista=1').status_code, 404)
        self.assertEqual(self.client.get(f'/api/payments/{payment["id"]}/').status_code, 404)

    def test_reviewed_purchase_can_resume_checkout_without_second_quote(self):
        values = self.payload(mode='cotizacion')
        result = self.post('checkout/', values, self.owner)
        self.assertEqual(result.status_code, 201, result.content)
        pk = result.json()['id']
        quoted = self.post(f'purchases/{pk}/quote/', {}, self.seller)
        quote = Quote.objects.get(pk=quoted.json()['id'])
        quote.approved = True
        quote.save()
        confirmed = self.post(f'quotes/{quote.pk}/confirm-payment/', {'confirmed': True}, self.seller)
        self.assertEqual(confirmed.status_code, 201, confirmed.content)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(f'/api/purchases/{pk}/').json()['payment'], confirmed.json()['id'])

    def test_checkout_requires_session_csrf_and_explicit_consent(self):
        self.enable()
        for changes in ({'confirmed': False}, {'contact_authorized': False}, {'mode': 'cotizacion'}):
            self.assertEqual(self.checkout(self.payload(**changes)).status_code, 400)
        browser = HttpClient(enforce_csrf_checks=True)
        browser.force_login(self.owner)
        self.assertEqual(browser.post('/api/checkout-payment/', self.payload(), content_type='application/json').status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post('/api/checkout-payment/', self.payload(), content_type='application/json').status_code, 403)

    def test_throttle_prevents_unlimited_checkout_attempts(self):
        self.enable()
        statuses = [self.checkout(self.payload(confirmed=False)).status_code for _ in range(13)]
        self.assertEqual(statuses[-1], 429)
        cache.clear()
