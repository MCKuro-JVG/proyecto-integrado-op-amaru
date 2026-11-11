from django.conf import settings
from django.db import migrations


def rename_sales_group(apps, schema_editor, source, target):
    Group = apps.get_model('auth', 'Group')
    User = apps.get_model(*settings.AUTH_USER_MODEL.split('.'))
    alias = schema_editor.connection.alias
    old = Group.objects.using(alias).filter(name=source).first()
    if not old:
        return
    new = Group.objects.using(alias).filter(name=target).first()
    if new is None:
        old.name = target
        old.save(using=alias, update_fields=['name'])
        return
    new.permissions.add(*old.permissions.all())
    for account in User.objects.using(alias).filter(groups=old).iterator():
        account.groups.add(new)
        account.groups.remove(old)
    old.delete(using=alias)


def forward(apps, schema_editor):
    rename_sales_group(apps, schema_editor, 'Personal de atención', 'Vendedor')


def reverse(apps, schema_editor):
    rename_sales_group(apps, schema_editor, 'Vendedor', 'Personal de atención')


class Migration(migrations.Migration):
    dependencies = [('gestion', '0011_union_workers_and_pickup')]
    operations = [migrations.RunPython(forward, reverse)]
