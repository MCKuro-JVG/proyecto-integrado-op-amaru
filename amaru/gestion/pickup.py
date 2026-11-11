"""Emisión y validación de credenciales de retiro, sin persistir el código en claro."""
from datetime import timedelta
import hashlib
import secrets
import uuid

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.http import Http404
from django.utils import timezone
from django.utils.crypto import salted_hmac
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied, Throttled, ValidationError
from rest_framework.response import Response

from .models import Order, PickupCode, Receipt

READY = 'Disponible para retiro'
PROOF_SALT = 'gestion.pickup.review.v1'


def code_value(order_id, nonce):
    value = salted_hmac('gestion.pickup.code.v1', f'{order_id}:{nonce.hex}', algorithm='sha256').hexdigest()
    return value[:24].upper()


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def audit_action(user, action, target):
    from .services import audit
    audit(user, action, target)


def requires_pickup(order):
    return bool(order.agreement_id and hasattr(order.agreement, 'union'))


def usable(code, now):
    return code and not code.used_at and not code.revoked_at and code.expires_at > now


def issue_locked(order, actor):
    """El llamador mantiene bloqueada la orden durante toda la operación."""
    if order.status != READY or Receipt.objects.filter(order=order).exists():
        raise ValidationError('La orden no está disponible para retiro.')
    now = timezone.now()
    nonce = uuid.uuid4()
    code, _ = PickupCode.objects.update_or_create(order=order, defaults={
        'nonce': nonce, 'digest': digest(code_value(order.pk, nonce)),
        'generated_at': now, 'expires_at': now + timedelta(hours=settings.PICKUP_CODE_HOURS),
        'used_at': None, 'used_by': None, 'revoked_at': None,
    })
    audit_action(actor, 'Código de retiro emitido', code)
    return code


def sync_order_state(order, previous, actor):
    if order.status == READY and previous != READY:
        issue_locked(order, actor)
    elif previous == READY and order.status != READY:
        revoke_locked(order, actor)


def revoke_locked(order, actor):
    code = PickupCode.objects.filter(order=order, revoked_at__isnull=True, used_at__isnull=True).first()
    if code:
        code.revoked_at = timezone.now()
        code.save(update_fields=['revoked_at'])
        audit_action(actor, 'Código de retiro revocado', code)


def staff_only(user):
    if not user.has_perms(['gestion.view_order', 'gestion.add_receipt']):
        raise PermissionDenied()


def consume_locked(order, user, proof):
    """Marca el código dentro de la misma transacción que el comprobante."""
    code = PickupCode.objects.select_for_update().filter(order=order).first()
    required = requires_pickup(order)
    if required or proof:
        if not user.has_perms(['gestion.view_order', 'gestion.add_receipt']):
            raise DjangoValidationError('El vendedor debe validar el código y la identidad.')
        try:
            payload = signing.loads(proof or '', salt=PROOF_SALT, max_age=600)
        except (signing.BadSignature, TypeError):
            raise DjangoValidationError('Valida nuevamente el código de retiro con el vendedor.') from None
        if (not usable(code, timezone.now()) or payload !=
                {'order': order.pk, 'actor': user.pk, 'nonce': code.nonce.hex}):
            raise DjangoValidationError('El código de retiro ya no es válido para esta entrega.')
    if code and not code.used_at and not code.revoked_at:
        code.used_at = timezone.now()
        code.used_by = user
        code.save(update_fields=['used_at', 'used_by'])
        audit_action(user, 'Código de retiro utilizado', code)


@api_view(['GET', 'POST'])
@transaction.atomic
def manage(request, pk):
    owner = request.method == 'GET'
    orders = Order.objects.select_for_update()
    if owner:
        orders = orders.filter(client__user=request.user, client__active=True)
    else:
        staff_only(request.user)
    try:
        order = orders.get(pk=pk)
    except Order.DoesNotExist:
        raise Http404
    if order.status != READY or Receipt.objects.filter(order=order).exists():
        raise ValidationError('La orden no está disponible para retiro.')
    if not owner:
        action = request.data.get('action')
        if action == 'reissue':
            issue_locked(order, request.user)
        elif action == 'revoke':
            revoke_locked(order, request.user)
        else:
            raise ValidationError('Selecciona reemitir o revocar.')
        return Response({'state': action}, headers={'Cache-Control': 'no-store'})
    code = PickupCode.objects.filter(order=order).first() or issue_locked(order, request.user)
    value = code_value(order.pk, code.nonce)
    if not usable(code, timezone.now()) or not secrets.compare_digest(digest(value), code.digest):
        raise ValidationError('El código no está vigente. Solicita su reemisión a Ópticas Amaru.')
    return Response({'code': value, 'expires_at': code.expires_at}, headers={'Cache-Control': 'no-store'})


class CheckInput(serializers.Serializer):
    code = serializers.RegexField(r'^[0-9A-Fa-f]{24}$')
    identity_checked = serializers.BooleanField(default=False)


@api_view(['POST'])
@transaction.atomic
def validate(request):
    staff_only(request.user)
    key = f'pickup-attempts:{request.user.pk}'
    cache.add(key, 0, 300)
    try:
        if cache.incr(key) > 20:
            raise Throttled(wait=300)
    except ValueError:
        cache.set(key, 1, 300)
    data = CheckInput(data=request.data)
    data.is_valid(raise_exception=True)
    lookup = digest(data.validated_data['code'].upper())
    order_id = PickupCode.objects.filter(digest=lookup).values_list('order_id', flat=True).first()
    if order_id:
        order = Order.objects.select_for_update().get(pk=order_id)
        code = PickupCode.objects.select_for_update().filter(order=order, digest=lookup).first()
        if usable(code, timezone.now()) and order.status == READY and not Receipt.objects.filter(order=order).exists():
            if not data.validated_data['identity_checked']:
                return Response({'order': order.pk, 'folio': order.folio, 'client': order.client.name, 'rut': order.client.rut},
                                headers={'Cache-Control': 'no-store'})
            proof = signing.dumps({'order': order.pk, 'actor': request.user.pk, 'nonce': code.nonce.hex}, salt=PROOF_SALT)
            audit_action(request.user, 'Código e identidad de retiro validados por vendedor', code)
            return Response({'order': order.pk, 'folio': order.folio, 'proof': proof},
                            headers={'Cache-Control': 'no-store'})
    raise ValidationError('El código no está vigente para una orden disponible.')
