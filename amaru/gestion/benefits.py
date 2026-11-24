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


def calculate(client, lines):
    """lines contiene producto, cantidad y precio unitario ya comprobados por Django."""
    total = sum(Decimal(str(line['price'])) * line['quantity'] for line in lines)
    best = Decimal(0)
    snapshot = {}
    for benefit in eligible(client).order_by('pk'):
        ids = {p.pk for p in benefit.products.all()}
        applicable = [line for line in lines if (not ids or line['product'].pk in ids)
                      and (not benefit.category_id or line['product'].stock_category_id == benefit.category_id)]
        base = sum(Decimal(str(line['price'])) * line['quantity'] for line in applicable)
        if not applicable or benefit.value is None:
            continue
        discount = Decimal(0)
        if benefit.kind == 'percent':
            discount = base * benefit.value / 100
        elif benefit.kind in ('fixed', 'contribution'):
            discount = min(base, benefit.value)
        elif benefit.kind == 'price':
            discount = sum(max(Decimal(0), Decimal(str(line['price'])) - benefit.value) * line['quantity'] for line in applicable)
        discount = min(base, discount.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        if discount > best:
            best = discount
            snapshot = {'id': benefit.pk, 'name': benefit.name, 'kind': benefit.kind,
                        'value': str(benefit.value), 'conditions': benefit.conditions,
                        'discount': str(discount), 'agreement': benefit.agreement_id}
    return total, total - best, snapshot
