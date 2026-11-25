"""Prepara QR académicos sin modificar convenios ni documentos de organizaciones reales."""
import json
from pathlib import Path
import secrets

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from gestion.models import Agreement, AgreementBenefit, AgreementRepresentative, Union
from gestion.services import audit


class Command(BaseCommand):
    help = 'Prepara dos organizaciones ficticias para demostrar sus QR; reutiliza un sindicato DEMO ya activado.'

    def add_arguments(self, parser):
        parser.add_argument('--academic', action='store_true', required=True)
        parser.add_argument('--credentials-file', type=Path, required=True)
        parser.add_argument('--metadata-file', type=Path, required=True)

    def handle(self, *args, **options):
        for key in ('credentials_file', 'metadata_file'):
            path = options[key].resolve()
            if path.is_relative_to(settings.BASE_DIR.parent.resolve()) and not path.is_relative_to((settings.BASE_DIR.parent/'.tools').resolve()):
                raise CommandError('Guarda los archivos de demostración fuera del código publicado.')
        candidates = Union.objects.select_related('agreement').filter(agreement__name__startswith='DEMO', state='active').order_by('pk')
        union = next((row for row in candidates if row.agreement.available), None)
        if not union:
            raise CommandError('Activa primero un sindicato explícitamente ficticio DEMO con el procedimiento autorizado. Este comando no omite la firma ni activa sindicatos.')
        credentials = options['credentials_file'].resolve()
        values = json.loads(credentials.read_text(encoding='utf-8')) if credentials.exists() else {}
        with transaction.atomic():
            traditional, _ = Agreement.objects.get_or_create(name='DEMO ACADÉMICA · Convenio QR doble', defaults={'allow_dependents': True})
            for agreement in (traditional, union.agreement):
                AgreementBenefit.objects.get_or_create(agreement=agreement, name='DEMO · Orientación de atención QR',
                    defaults={'kind': 'evaluation', 'active': True, 'public_visible': True,
                        'description': 'Información ficticia para comprobar el portal de consultas.',
                        'conditions': 'Ejemplo académico sin beneficios comerciales reales. La pertenencia requiere validación.'})
            username = 'representante_qr_demo'
            representative, created = User.objects.get_or_create(username=username,
                defaults={'email': username+'@example.invalid', 'first_name': 'Representante ficticio QR'})
            if representative.is_staff or representative.is_superuser or representative.get_all_permissions():
                raise CommandError('La cuenta de demostración tiene permisos incompatibles.')
            previous = AgreementRepresentative.objects.filter(user=representative).first()
            if previous and previous.agreement_id != union.agreement_id:
                raise CommandError('La cuenta ya representa otra organización; no se cambia su vinculación.')
            if created:
                password = secrets.token_urlsafe(24)
                representative.set_password(password)
                representative.save(update_fields=['password'])
                values[username] = password
                audit(None, 'Cuenta académica ficticia de representante QR preparada', representative)
            representative.groups.add(Group.objects.get_or_create(name='Sindicato')[0])
            AgreementRepresentative.objects.get_or_create(user=representative, defaults={'agreement': union.agreement})
        credentials.parent.mkdir(parents=True, exist_ok=True)
        credentials.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding='utf-8')
        metadata = options['metadata_file'].resolve()
        metadata.parent.mkdir(parents=True, exist_ok=True)
        metadata.write_text(json.dumps({'traditional': traditional.pk, 'union_agreement': union.agreement_id,
            'union': union.pk, 'representative': username}, indent=2), encoding='utf-8')
        for path in (credentials, metadata):
            try: path.chmod(0o600)
            except OSError: pass
        self.stdout.write('Dos organizaciones ficticias preparadas. Se conservaron los códigos, estados y documentos existentes. Credenciales guardadas solo en el archivo privado.')
