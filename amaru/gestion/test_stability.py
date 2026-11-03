"""Salud y seguridad del origen público sin modificar el esquema."""
from unittest.mock import patch
from django.test import TestCase,override_settings
from gestion.health import health
from django.test import RequestFactory

class HealthTests(TestCase):
    def test_healthy_database(self):
        response=health(RequestFactory().get('/healthz/'))
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.content,b'{"status": "ok"}')
        self.assertEqual(response['Cache-Control'],'no-store')
    def test_database_error_is_generic(self):
        with patch('gestion.health.connection.cursor',side_effect=RuntimeError('private detail')):
            response=health(RequestFactory().get('/healthz/'))
        self.assertEqual(response.status_code,503);self.assertNotIn(b'private detail',response.content)
    @override_settings(ROOT_URLCONF='config.attention_public_urls',MIDDLEWARE=['gestion.attention_public.PublicBoundaryMiddleware'],ATTENTION_PUBLIC_ONLY=True)
    def test_https_health_and_boundary(self):
        self.assertEqual(self.client.get('/healthz/',secure=True).status_code,200)
        self.assertEqual(self.client.get('/healthz/').status_code,400)
        for path in ('/admin/','/api/clients/','/api/inquiries/','/app/dashboard.html'):
            self.assertEqual(self.client.get(path,secure=True).status_code,404)


class DeploymentPreparationTests(TestCase):
    def test_service_plan_uses_limited_accounts_and_restarts(self):
        import importlib.util
        from pathlib import Path
        root=Path(__file__).resolve().parents[2]
        spec=importlib.util.spec_from_file_location('prepare_services',root/'scripts/prepare_windows_services.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        for name in ('OpticasAmaruDatabase','OpticasAmaruAttention'):
            xml=module.definition(name,root)
            self.assertEqual(xml.findtext('serviceaccount/user'),'LocalService')
            self.assertEqual(xml.findtext('startmode'),'Automatic')
            self.assertTrue(all(node.get('action')=='restart' for node in xml.findall('onfailure')))
            self.assertIsNone(xml.find('serviceaccount/password'))
        self.assertEqual(module.definition('OpticasAmaruAttention',root).findtext('depend'),'OpticasAmaruDatabase')
    def test_operational_logging_discards_exception_and_request_details(self):
        import logging
        from .operational_logging import SafeOperationalFilter
        record=logging.LogRecord('django.request',logging.ERROR,'',1,'Private supplied value',(),None)
        self.assertTrue(SafeOperationalFilter().filter(record))
        self.assertNotIn('Private supplied value',record.getMessage())
