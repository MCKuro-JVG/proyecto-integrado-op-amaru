from django.contrib.auth.models import Group, Permission, User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from .models import Agreement, Client, Order, Quote, Union


class ExperienceTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_admin_link_requires_staff_and_model_permission(self):
        permission = Permission.objects.get(content_type__app_label='gestion', codename='change_siteconfiguration')
        group = Group.objects.create(name='Administrador')
        group.permissions.add(permission)
        non_staff = User.objects.create_user('functional_admin')
        non_staff.groups.add(group)
        seller = User.objects.create_user('seller_staff', is_staff=True)
        authorized = User.objects.create_user('system_admin', is_staff=True)
        authorized.user_permissions.add(permission)
        for user, allowed in ((non_staff, False), (seller, False), (authorized, True)):
            self.client.force_login(user)
            self.assertIs(self.client.get('/api/session/').json()['django_admin'], allowed)
            result = self.client.get(reverse('admin:index'))
            if not user.is_staff:
                self.assertEqual(result.status_code, 302)
            if allowed:
                self.assertContains(result, 'Volver a la aplicación')
                self.assertContains(result, '/app/dashboard.html')
        self.client.logout()
        self.assertFalse(self.client.get('/api/session/').json()['django_admin'])

    def test_converted_quote_retains_folio_and_named_customer(self):
        staff = User.objects.create_superuser('staff_quote')
        client = Client.objects.create(rut='12345678-5', name='Cliente prueba', phone='+56900000000',
                                       category='particular')
        quote = Quote.objects.create(client=client, product_type='particular', category='particular',
                                     amount=100, approved=True)
        Order.objects.create(client=client, quote=quote, product_type='particular', category='particular')
        self.client.force_login(staff)
        result = self.client.get('/api/quotes/', {'rut': '123456785'}).json()['results']
        self.assertEqual((result[0]['folio'], result[0]['client_name'], result[0]['client_rut']),
                         (quote.folio, client.name, client.rut))
        self.assertTrue(result[0]['converted'])

    def test_traditional_listing_is_separate_from_managed_unions(self):
        self.client.force_login(User.objects.create_superuser('staff_organizations'))
        traditional = Agreement.objects.create(name='Convenio por código')
        managed = Agreement.objects.create(name='Sindicato de prueba')
        Union.objects.create(agreement=managed, identifier='sindicato-prueba')
        listing = self.client.get('/api/agreements/', {'tipo': 'tradicional'}).json()['results']
        self.assertEqual([row['id'] for row in listing], [traditional.pk])
        self.assertEqual(self.client.get('/api/agreements/').json()['count'], 2)
