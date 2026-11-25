"""Elegibilidad y cálculo CLP. Se aplica un único beneficio monetario por cotización."""
from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Q
from django.utils import timezone
from .membership import verified_agreement
from .models import AgreementBenefit, UnionMembership


def eligible(client):
    agreement = verified_agreement(client)
    if not agreement:
        return AgreementBenefit.objects.none()
    membership = UnionMembership.objects.filter(client=client, union__agreement=agreement, state='active').first()
    inquiry = client.inquiries.filter(agreement=agreement, verification_state='aprobada').order_by('-created_at').first()
    role = membership.role if membership else (inquiry.agreement_role if inquiry else '')
    today = timezone.localdate()
    return AgreementBenefit.objects.filter(agreement=agreement, active=True).filter(
        Q(starts_on__isnull=True) | Q(starts_on__lte=today)).filter(
        Q(ends_on__isnull=True) | Q(ends_on__gte=today)).filter(role__in=['all', role]).prefetch_related('products')


def applicable_discount(benefit, lines, *, unit_preview=False):
    ids = {product.pk for product in benefit.products.all()}
    applicable = [line for line in lines if (not ids or line['product'].pk in ids)
                  and (not benefit.category_id or line['product'].stock_category_id == benefit.category_id)]
    base = sum(Decimal(str(line['price'])) * line['quantity'] for line in applicable)
    if not applicable:
        return Decimal(0), 'No corresponde a los productos seleccionados.'
    if benefit.value is None or benefit.kind not in ('percent', 'fixed', 'contribution', 'price'):
        return Decimal(0), 'Beneficio de servicio o acceso.'
    if unit_preview and benefit.kind in ('fixed', 'contribution'):
        return Decimal(0), 'El aporte se calcula sobre el carrito.'
    if benefit.kind == 'percent':
        discount = base * benefit.value / 100
    elif benefit.kind in ('fixed', 'contribution'):
        discount = min(base, benefit.value)
    else:
        discount = sum(max(Decimal(0), Decimal(str(line['price'])) - benefit.value) * line['quantity']
                       for line in applicable)
    discount = min(base, discount.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    return discount, 'Compatible' if discount > 0 else 'El precio actual ya es igual o menor.'


def calculate(client, lines, *, available=None, include_options=False, unit_preview=False):
    """lines contiene producto, cantidad y precio unitario ya comprobados por Django."""
    total = sum(Decimal(str(line['price'])) * line['quantity'] for line in lines)
    best = Decimal(0)
    snapshot = {}
    options = []
    if available is None:
        available = eligible(client).order_by('pk')
    for benefit in available:
        discount, reason = applicable_discount(benefit, lines, unit_preview=unit_preview)
        if include_options:
            options.append({'id': benefit.pk, 'name': benefit.name, 'discount': str(discount),
                            'compatible': discount > 0, 'reason': reason})
        if discount > best:
            best = discount
            snapshot = {'id': benefit.pk, 'name': benefit.name, 'kind': benefit.kind,
                        'value': str(benefit.value), 'conditions': benefit.conditions,
                        'discount': str(discount), 'agreement': benefit.agreement_id,
                        'role': benefit.role, 'category': benefit.category_id,
                        'products': sorted(product.pk for product in benefit.products.all()),
                        'starts_on': benefit.starts_on.isoformat() if benefit.starts_on else None,
                        'ends_on': benefit.ends_on.isoformat() if benefit.ends_on else None}
    result = (total, total - best, snapshot)
    return (*result, options) if include_options else result
