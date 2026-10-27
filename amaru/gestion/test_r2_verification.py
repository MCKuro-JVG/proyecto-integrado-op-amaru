"""Pruebas aisladas de fallos de verificación; no contactan Cloudflare."""
from io import StringIO
from unittest.mock import MagicMock, patch
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, SimpleTestCase, override_settings
from gestion.models import Client

MODULE = 'gestion.management.commands.verify_r2'


@override_settings(R2_ENABLED=True, R2_BUCKET_PUBLICO='public-test', R2_BUCKET_PRIVADO='private-test')
class R2VerificationCleanupTests(TestCase):
    def setUp(self):
        self.public = MagicMock()
        self.private = MagicMock()
        self.public.save.return_value = 'catalogo/owned.png'
        self.private.save.return_value = 'recetas/owned.png'
        self.vendor = patch(MODULE + '.connection.vendor', 'mysql')
        self.pub = patch(MODULE + '.PublicStorage', return_value=self.public)
        self.priv = patch(MODULE + '.PrivateStorage', return_value=self.private)
        for p in (self.vendor, self.pub, self.priv):
            p.start()
            self.addCleanup(p.stop)

    def test_first_upload_failure_does_not_delete_uncreated_objects(self):
        self.public.save.side_effect = OSError('failure')
        with self.assertRaises(CommandError):
            call_command('verify_r2', stdout=StringIO())
        self.public.delete.assert_not_called()
        self.private.delete.assert_not_called()

    def test_second_upload_failure_cleans_only_first_upload(self):
        self.private.save.side_effect = OSError('failure')
        with self.assertRaises(CommandError):
            call_command('verify_r2', stdout=StringIO())
        self.public.delete.assert_called_once_with('catalogo/owned.png')
        self.private.delete.assert_not_called()

    def test_cleanup_failure_still_attempts_other_bucket_and_reports_no_success(self):
        self.private.open.side_effect = OSError('download failed')
        self.private.delete.side_effect = OSError('cleanup failed')
        output = StringIO()
        with self.assertRaisesMessage(CommandError, 'Limpieza pendiente'):
            call_command('verify_r2', stdout=output)
        self.private.delete.assert_called_once_with('recetas/owned.png')
        self.public.delete.assert_called_once_with('catalogo/owned.png')
        self.assertFalse(Client.objects.filter(rut='99999999-9').exists())
        self.assertNotIn('comprobados', output.getvalue())

    def test_existing_test_rut_is_preserved_before_any_remote_upload(self):
        existing = Client.objects.create(rut='99999999-9', name='Existing test', phone='000', category='particular')
        with self.assertRaisesMessage(CommandError, 'RUT de prueba ocupado'):
            call_command('verify_r2', stdout=StringIO())
        self.public.save.assert_not_called()
        self.private.save.assert_not_called()
        self.assertTrue(Client.objects.filter(pk=existing.pk, name='Existing test').exists())


class AnonymousR2ErrorTests(SimpleTestCase):
    def error(self, status, body):
        from io import BytesIO
        from urllib.error import HTTPError
        return HTTPError('https://storage.example.invalid/object', status, 'Fictitious test', {}, BytesIO(body))

    def test_explicit_missing_authorization_400_is_rejection(self):
        from gestion.management.commands.verify_r2 import anonymous_auth_rejected
        self.assertTrue(anonymous_auth_rejected(self.error(400, b'<Error><Code>InvalidArgument</Code><Message>Authorization</Message></Error>')))

    def test_other_400_is_not_treated_as_privacy_proof(self):
        from gestion.management.commands.verify_r2 import anonymous_auth_rejected
        self.assertFalse(anonymous_auth_rejected(self.error(400, b'<Error><Code>InvalidArgument</Code><Message>Path</Message></Error>')))

    def test_missing_object_is_not_treated_as_privacy_proof(self):
        from gestion.management.commands.verify_r2 import anonymous_auth_rejected
        self.assertFalse(anonymous_auth_rejected(self.error(404, b'<Error><Code>NoSuchKey</Code></Error>')))

    def test_invalid_response_is_not_treated_as_privacy_proof(self):
        from gestion.management.commands.verify_r2 import anonymous_auth_rejected
        self.assertFalse(anonymous_auth_rejected(self.error(400, b'Not XML')))

    def test_forbidden_is_rejection(self):
        from gestion.management.commands.verify_r2 import anonymous_auth_rejected
        self.assertTrue(anonymous_auth_rejected(self.error(403, b'Forbidden')))
