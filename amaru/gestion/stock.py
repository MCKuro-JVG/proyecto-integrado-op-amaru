"""Existencias físicas y reservas, serializadas mediante el bloqueo de Inventory."""
from collections import Counter
from datetime import timedelta
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from .models import Inventory, StockMovement, StockReservation, TransferConfiguration
from .services import audit


def reserved(item):
    return item.reservations.filter(state='active', expires_at__gt=timezone.now()).aggregate(n=Sum('quantity'))['n'] or 0


@transaction.atomic
def move(item_id, user, *, kind, quantity, reason, operation, reference='', supplier=None, unit_cost=None):
    item = Inventory.objects.select_for_update().get(pk=item_id)
    previous = StockMovement.objects.filter(operation=operation).first()
    if previous:
        if (previous.inventory_id != item.pk or previous.kind != kind or previous.reason != reason
                or (previous.after if kind == 'adjustment' else abs(previous.delta)) != quantity):
            raise ValidationError('La referencia de movimiento ya fue utilizada con otros datos.')
        return previous
    delta = quantity - item.quantity if kind == 'adjustment' else quantity * (-1 if kind == 'exit' else 1)
    after = item.quantity + delta
    if after < reserved(item) or after < 0:
        raise ValidationError('Stock insuficiente. Hay unidades reservadas que deben conservarse.')
    row = StockMovement.objects.create(inventory=item, kind=kind, delta=delta, before=item.quantity,
        after=after, reason=reason, operation=operation, reference=reference, supplier=supplier,
        unit_cost=unit_cost, actor=user)
    item.quantity = after
    if unit_cost is not None and kind == 'entry':
        item.unit_cost = unit_cost
    item.save(update_fields=['quantity', 'unit_cost'])
    audit(user, f'Inventario {kind} · {delta:+d} unidades · {reason}', item)
    return row


def quote_requirements(quote):
    requirements = Counter()
    for line in quote.lines.select_related('product'):
        variant = line.product.stock_variants.filter(label=line.variant, active=True).first()
        if variant:
            item = Inventory.objects.filter(variant=variant).first()
            if not item:
                raise ValidationError('La variante no tiene existencias configuradas.')
            requirements[item.pk] += line.quantity
        elif line.product.stock_variants.exists():
            raise ValidationError('Una variante dejó de estar disponible. Revisa la cotización.')
    return requirements


def reserve_quote(quote, user, *, paid=False):
    """El llamador ya tiene bloqueada la cotización."""
    requirements = quote_requirements(quote)
    config = TransferConfiguration.objects.first()
    expiry = timezone.now() + timedelta(hours=config.reserve_hours if config else 48)
    for pk, quantity in sorted(requirements.items()):
        item = Inventory.objects.select_for_update().get(pk=pk)
        current = StockReservation.objects.filter(quote=quote, inventory=item).first()
        if current and current.state == 'consumed':
            continue
        others = item.reservations.filter(state='active', expires_at__gt=timezone.now()).exclude(quote=quote)
        unavailable = others.aggregate(n=Sum('quantity'))['n'] or 0
        if quantity > item.quantity - unavailable:
            raise ValidationError(f'Stock insuficiente para {item.name}. Solicita reposición antes de continuar.')
        # Una aprobación conserva las unidades hasta entrega o cancelación autorizada.
        expires = timezone.now() + timedelta(days=36500) if paid else expiry
        StockReservation.objects.update_or_create(quote=quote, inventory=item,
            defaults={'quantity': quantity, 'state': 'active', 'expires_at': expires})
        audit(user, 'Reserva de existencias confirmada', item)


def release_quote(quote, user):
    for row in quote.stock_reservations.order_by('inventory_id'):
        Inventory.objects.select_for_update().get(pk=row.inventory_id)
        if row.state == 'active':
            row.state = 'released'
            row.save(update_fields=['state', 'updated_at'])
            audit(user, 'Reserva liberada por cancelación', row)


def dispatch_quote(quote, user):
    requirements = quote_requirements(quote)
    rows = list(quote.stock_reservations.order_by('inventory_id'))
    if requirements and not rows:
        raise ValidationError('La orden necesita reserva confirmada antes de entregar.')
    for row in rows:
        item = Inventory.objects.select_for_update().get(pk=row.inventory_id)
        if row.state == 'consumed':
            continue
        if row.state != 'active' or row.expires_at <= timezone.now():
            raise ValidationError('La reserva expiró o fue cancelada. Solicita revisión del vendedor.')
        if item.quantity < row.quantity:
            raise ValidationError('Existencias inconsistentes. Revisa el inventario.')
        row.state = 'consumed'
        row.save(update_fields=['state', 'updated_at'])
        import uuid
        move(item.pk, user, kind='exit', quantity=row.quantity, reason='Entrega de lentes',
             operation=uuid.uuid5(uuid.NAMESPACE_URL, f'amaru-reserva-{row.pk}'), reference=quote.folio)
