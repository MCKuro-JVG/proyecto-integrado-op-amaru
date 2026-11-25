import uuid
import django.db.models.deletion
from django.db import migrations, models


ORIGINS = [('web', 'Sitio web'), ('qr_general', 'QR de atención general'),
    ('qr_worker', 'Registro mediante QR'), ('qr_inquiry', 'Consulta mediante QR'),
    ('administrative', 'Registro administrativo'), ('manual_code', 'Código manual')]


def assign_codes(apps, schema_editor):
    Agreement = apps.get_model('gestion', 'Agreement')
    for row in Agreement.objects.using(schema_editor.connection.alias).iterator():
        row.worker_qr_token, row.inquiry_qr_token = uuid.uuid4(), uuid.uuid4()
        row.save(using=schema_editor.connection.alias, update_fields=['worker_qr_token', 'inquiry_qr_token'])
    # El origen QR previo se conserva sin atribuirle una finalidad nueva.
    apps.get_model('gestion', 'Inquiry').objects.using(schema_editor.connection.alias).filter(source='qr').update(origin='qr_general')


class Migration(migrations.Migration):
    dependencies = [('gestion', '0016_precio_checkout_academico')]
    operations = [
        migrations.AddField(model_name='agreement', name='worker_qr_token', field=models.UUIDField(unique=True, null=True, editable=False)),
        migrations.AddField(model_name='agreement', name='inquiry_qr_token', field=models.UUIDField(unique=True, null=True, editable=False)),
        migrations.AddField(model_name='agreement', name='worker_qr_enabled', field=models.BooleanField(default=True)),
        migrations.AddField(model_name='agreement', name='inquiry_qr_enabled', field=models.BooleanField(default=True)),
        migrations.AddField(model_name='inquiry', name='origin', field=models.CharField(max_length=20, choices=ORIGINS, default='web')),
        migrations.AddField(model_name='inquiry', name='privacy_version', field=models.CharField(max_length=24, blank=True)),
        migrations.AddField(model_name='inquiry', name='privacy_accepted_at', field=models.DateTimeField(null=True, blank=True)),
        migrations.AddField(model_name='inquiry', name='union_membership', field=models.OneToOneField(to='gestion.unionmembership', on_delete=django.db.models.deletion.PROTECT, null=True, blank=True, related_name='registration_inquiry')),
        migrations.AddField(model_name='unionmembership', name='origin', field=models.CharField(max_length=20, choices=ORIGINS, default='administrative')),
        migrations.AddField(model_name='agreementbenefit', name='public_visible', field=models.BooleanField(default=False, verbose_name='Autorizado para publicación en QR de consultas')),
        migrations.AddIndex(model_name='inquiry', index=models.Index(fields=['agreement','origin','kind','created_at'], name='inquiry_org_origin')),
        migrations.RunPython(assign_codes, migrations.RunPython.noop),
        migrations.AlterField(model_name='agreement', name='worker_qr_token', field=models.UUIDField(default=uuid.uuid4, unique=True, editable=False)),
        migrations.AlterField(model_name='agreement', name='inquiry_qr_token', field=models.UUIDField(default=uuid.uuid4, unique=True, editable=False)),
    ]
