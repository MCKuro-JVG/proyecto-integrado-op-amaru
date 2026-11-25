from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('gestion', '0017_organization_qr')]
    operations = [
        migrations.AlterField(
            model_name='inquiry',
            name='verification_state',
            field=models.CharField(blank=True, max_length=12, choices=[
                ('pendiente', 'Pendiente'), ('aprobada', 'Aprobada'),
                ('rechazada', 'Rechazada'), ('inactiva', 'Inactiva'),
            ]),
        ),
    ]
