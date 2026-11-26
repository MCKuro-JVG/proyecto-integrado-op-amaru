"""Inventario ficticio para probar el pago de lentes particulares."""
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from gestion.models import Inventory, Product, ProductVariant
from gestion.stock import move


class Command(BaseCommand):
    help = 'Agrega dos armazones ficticios para probar la compra particular.'

    def add_arguments(self, parser):
        parser.add_argument('--academic', action='store_true', required=True)
        parser.add_argument('--actor', required=True, help='Usuario autorizado para registrar la entrada ficticia de stock.')

    @transaction.atomic
    def handle(self, *args, **options):
        actor = get_user_model().objects.filter(username=options['actor'], is_active=True).first()
        if not actor or not actor.has_perm('gestion.add_stockmovement'):
            raise CommandError('Se requiere un usuario autorizado para registrar movimientos de stock.')
        fixtures = (
            ('DEMO-PART-PAGO', 'DEMO · Lentes particulares Niebla', 'Carey', 19990, False),
            ('DEMO-PART-RECETA', 'DEMO · Armazón particular Trébol', 'Negro', 24990, True),
        )
        for sku, name, color, price, recipe in fixtures:
            product, created = Product.objects.get_or_create(sku=sku, defaults={
                'name': name, 'category': 'armazon', 'color': color, 'variants': [color],
                'description': 'Producto ficticio para demostración académica. Sin venta comercial.',
                'reference_price': price, 'direct_checkout': not recipe, 'requires_prescription': recipe,
            })
            if not created:
                continue
            variant = ProductVariant.objects.create(product=product, label=color, sku=f'{sku}-01', color=color)
            item = Inventory.objects.create(variant=variant, name=name, category='armazon', minimum=2)
            move(item.pk, actor, kind='entry', quantity=15, reason='Stock ficticio para demostración académica', operation=uuid4())
            self.stdout.write(self.style.SUCCESS(f'{sku}: armazón ficticio creado.'))
