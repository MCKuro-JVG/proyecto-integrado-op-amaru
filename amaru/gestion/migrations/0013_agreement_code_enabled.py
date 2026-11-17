from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('gestion', '0012_rename_sales_role')]

    operations = [
        migrations.AddField(
            model_name='agreement',
            name='code_enabled',
            field=models.BooleanField(default=True),
        ),
    ]
