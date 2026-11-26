"""Solicitudes de compra sin cobro y su conversión a cotizaciones en revisión."""
from django.db import transaction
from django.db.models import Prefetch, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.decorators import throttle_classes

from .catalog_requests import own_client
from .membership import verified_agreement
from .models import Client, Inquiry, Prescription, Product, ProductVariant, PurchaseLine, Quote, QuoteLine
from .services import audit


class Conflict(APIException):
    status_code = 409


class Selection(serializers.Serializer):
    product = serializers.IntegerField(min_value=1)
    variant = serializers.CharField(max_length=80, allow_blank=True, default='')
    quantity = serializers.IntegerField(min_value=1, max_value=99)


class CheckoutInput(serializers.Serializer):
    items = Selection(many=True, allow_empty=False, max_length=20)
    prescription = serializers.IntegerField(min_value=1, required=False)
    mode = serializers.ChoiceField(choices=['compra', 'cotizacion'])
    reason = serializers.CharField(max_length=2000, min_length=5)
    contact_authorized = serializers.BooleanField()
    idempotency_key = serializers.UUIDField()

    def validate_items(self, values):
        pairs = {(v['product'], v['variant']) for v in values}
        if len(pairs) != len(values):
            raise serializers.ValidationError('Consolida las cantidades de cada producto y variante.')
        return values


class PaymentCheckoutInput(CheckoutInput):
    confirmed = serializers.BooleanField()
    expected_amount = serializers.DecimalField(max_digits=12, decimal_places=0, min_value=1)


class CheckoutThrottle(UserRateThrottle):
    rate = '12/min'
    scope = 'payment_checkout'


@api_view(['POST'])
@throttle_classes([CheckoutThrottle])
@transaction.atomic
def checkout_payment(request):
    """Checkout académico de precios habilitados; conserva el circuito de revisión."""
    from .commercial import create_payment, payment_summary
    from .unions import private
    client = own_client(request.user)
    form = PaymentCheckoutInput(data=request.data)
    form.is_valid(raise_exception=True)
    values = form.validated_data
    if not values['confirmed'] or not values['contact_authorized'] or values['mode'] != 'compra':
        raise ValidationError('Confirma la selección, el total y el contacto antes de continuar al pago académico.')
    row, created = register(client, request.user, values)
    if row.purchase_quote_id:
        quote = Quote.objects.select_for_update().get(pk=row.purchase_quote_id)
        payment = getattr(quote, 'transfer_payment', None)
        if not payment:
            raise Conflict('Esta solicitud necesita la confirmación de la óptica antes de pagar.')
        if payment.amount != values['expected_amount']:
            raise Conflict('La referencia corresponde a un pago con otro monto confirmado.')
    else:
        lines = list(row.purchase_lines.select_related('product'))
        if any(not line.product.direct_checkout or not line.unit_price for line in lines):
            raise Conflict('Uno de los precios requiere confirmación de la óptica. Solicita revisión previa.')
        if any(line.product.requires_prescription for line in lines):
            raise Conflict('La óptica debe revisar tu receta antes de habilitar el pago. Solicita revisión previa.')
        if any(not line.product.stock_variants.filter(label=line.variant, active=True).exists() for line in lines):
            raise Conflict('La óptica debe confirmar las existencias de esta variante antes del pago.')
        quote = build_quote(row, request.user, approved=True)
        payment = create_payment(quote, request.user, expected_amount=values['expected_amount'])
        audit(request.user, 'Checkout académico confirmado desde el carrito', row)
    return private({'purchase': row.pk, 'payment': payment_summary(payment), 'created': created}, status=201 if created else 200)


@api_view(['GET', 'POST'])
def checkout(request):
    client = own_client(request.user)
    if request.method == 'GET':
        agreement = verified_agreement(client)
        return Response({'name': client.name, 'email': client.email, 'phone': client.phone,
                         'agreement': agreement.name if agreement else None})
    form = CheckoutInput(data=request.data)
    form.is_valid(raise_exception=True)
    values = form.validated_data
    if not values['contact_authorized']:
        raise ValidationError('Autoriza el contacto para gestionar la solicitud.')
    row, created = register(client, request.user, values)
    return Response({'id': row.pk, 'reference': row.token, 'state': row.status, 'created': created}, status=201 if created else 200)


@transaction.atomic
def register(client, user, values):
    agreement = verified_agreement(client, lock=True)
    client = Client.objects.select_for_update().get(pk=client.pk)
    if not client.active or client.user_id != user.pk:
        raise PermissionDenied()
    selections = values['items']
    existing = Inquiry.objects.filter(idempotency_key=values['idempotency_key']).first()
    if existing:
        confirm_retry(existing, client, values)
        return existing, False
    products = Product.objects.select_for_update().filter(pk__in={x['product'] for x in selections}, active=True).order_by('pk').in_bulk()
    if len(products) != len({x['product'] for x in selections}):
        raise Conflict('Un producto dejó de estar disponible. Revisa el carrito.')
    if any(product.mining_only for product in products.values()) and not (agreement and hasattr(agreement, 'union')):
        raise PermissionDenied('Se requiere una afiliación sindical vigente para estos productos.')
    recipe = None
    if values.get('prescription'):
        recipe = get_object_or_404(Prescription, pk=values['prescription'], client=client)
        if not recipe.valid or not recipe.file:
            raise ValidationError({'prescription': 'La receta debe estar vigente y tener archivo.'})
    if any(p.requires_prescription for p in products.values()) and recipe is None:
        raise ValidationError({'prescription': 'Una selección requiere receta vigente del cliente.'})
    lines = []
    for selection in selections:
        product = products[selection['product']]
        if selection['variant'] not in (product.variants or ['']):
            raise Conflict('Una variante cambió. Revisa el producto en el catálogo.')
        from .stock import reserved
        variant = product.stock_variants.filter(label=selection['variant'], active=True).first()
        if product.stock_variants.exists():
            from .models import Inventory
            item = Inventory.objects.select_for_update().filter(variant=variant).first() if variant else None
            if not item or selection['quantity'] > item.quantity - reserved(item):
                raise Conflict('No hay stock suficiente para una de las variantes. Revisa las cantidades.')
        lines.append(PurchaseLine(product=product, product_name=product.name, variant=selection['variant'],
            quantity=selection['quantity'], unit_price=product.reference_price,
            characteristics={field: getattr(product, field) for field in ('sku', 'category', 'lens_type', 'crystal', 'color', 'treatments', 'requires_prescription')}))
    row, created = Inquiry.objects.get_or_create(idempotency_key=values['idempotency_key'], defaults={
        'kind': 'compra', 'client': client, 'name': client.name, 'phone': client.phone, 'email': client.email,
        'purchase_mode': values['mode'], 'prescription': recipe, 'agreement': agreement,
        'reason': values['reason'], 'service': 'Solicitud de catálogo', 'contact_authorized': True, 'actor': user,
    })
    if not created:
        confirm_retry(row, client, values)
        return row, False
    for line in lines:
        line.inquiry = row
    PurchaseLine.objects.bulk_create(lines)
    audit(user, 'Carrito registrado para revisión', row)
    return row, True


@api_view(['POST'])
def preview(request):
    from .benefits import calculate
    client = own_client(request.user)
    form = CheckoutInput(data=request.data)
    form.is_valid(raise_exception=True)
    lines = []
    selections = form.validated_data['items']
    variants = ProductVariant.objects.select_related('stock').annotate(
        reserved_quantity=Sum('stock__reservations__quantity', filter=Q(
            stock__reservations__state='active', stock__reservations__expires_at__gt=timezone.now(),
        ), default=0),
    )
    products = Product.objects.filter(active=True).prefetch_related(
        Prefetch('stock_variants', queryset=variants, to_attr='checkout_variants'),
    ).in_bulk({item['product'] for item in selections})
    blockers, review = [], []
    for selected in selections:
        product = products.get(selected['product'])
        if product is None:
            raise Conflict('Un producto dejó de estar disponible. Revisa el carrito.')
        if product.mining_only:
            from .unions import membership_for
            if not membership_for(client):
                raise PermissionDenied()
        if selected['variant'] not in (product.variants or ['']):
            raise ValidationError('La variante no corresponde al producto.')
        variant = next((row for row in product.checkout_variants if row.label == selected['variant'] and row.active), None)
        stock = getattr(variant, 'stock', None)
        label = f"{product.name} · {selected['variant']}" if selected['variant'] else product.name
        if product.checkout_variants and not stock:
            blockers.append(f'{label}: la variante seleccionada no está disponible.')
        elif stock and selected['quantity'] > stock.quantity - variant.reserved_quantity:
            blockers.append(f'{label}: stock insuficiente para la cantidad seleccionada.')
        elif not stock:
            review.append(f'{label}: la óptica debe confirmar las existencias.')
        if not product.direct_checkout or not product.reference_price:
            review.append(f'{label}: la óptica debe confirmar el precio.')
        if product.requires_prescription:
            review.append(f'{label}: adjunta una receta vigente para que la óptica la revise.')
        lines.append({'product': product, 'price': product.reference_price, 'quantity': selected['quantity']})
    result = {'blockers': blockers, 'review': review, 'pending': any(line['price'] is None for line in lines)}
    if result['pending']:
        return Response(result)
    original, final, snapshot, options = calculate(client, lines, include_options=True)
    return Response({**result, 'original': str(original), 'amount': str(final), 'benefit': snapshot, 'benefits': options})


def confirm_retry(row, client, values):
    if (row.client_id != client.pk or row.kind != 'compra' or row.prescription_id != values.get('prescription')
            or row.purchase_mode != values['mode'] or row.reason != values['reason']):
        raise Conflict('La referencia ya pertenece a otra solicitud.')
    previous = set(row.purchase_lines.values_list('product_id', 'variant', 'quantity'))
    if previous != {(x['product'], x['variant'], x['quantity']) for x in values['items']}:
        raise Conflict('La referencia ya pertenece a otra selección.')


@api_view(['GET'])
def detail(request, pk):
    rows = Inquiry.objects.filter(kind='compra').select_related('agreement', 'purchase_quote').prefetch_related('purchase_lines')
    if not request.user.has_perm('gestion.view_inquiry'):
        rows = rows.filter(client__user=request.user, client__active=True)
    row = get_object_or_404(rows, pk=pk)
    from .models import TransferPayment
    payment = TransferPayment.objects.filter(quote_id=row.purchase_quote_id).first() if row.purchase_quote_id else None
    return Response({'id': row.pk, 'reference': row.token, 'payment': payment.pk if payment else None, 'mode': row.purchase_mode, 'state': row.status, 'prescription': row.prescription_id,
        'agreement': row.agreement.name if row.agreement else None, 'quote': row.purchase_quote_id,
        'items': list(row.purchase_lines.values('id','product_id','product_name','variant','quantity','unit_price','characteristics'))})


class QuoteInput(serializers.Serializer):
    prices = serializers.DictField(child=serializers.IntegerField(min_value=0, max_value=999999999), default=dict)


@api_view(['POST'])
def quote(request, pk):
    if not request.user.has_perms(['gestion.view_inquiry', 'gestion.add_quote', 'gestion.view_quote']):
        raise PermissionDenied()
    form = QuoteInput(data=request.data)
    form.is_valid(raise_exception=True)
    with transaction.atomic():
        row = get_object_or_404(Inquiry.objects.select_for_update(), pk=pk, kind='compra')
        if row.purchase_quote_id:
            return Response({'id': row.purchase_quote_id, 'folio': row.purchase_quote.folio})
        if row.status in ('Cancelada', 'Cerrada') or not row.client.active:
            raise Conflict('La solicitud o la ficha no permite generar una cotización.')
        quote = build_quote(row, request.user, form.validated_data['prices'])
        audit(request.user, 'Cotización en borrador creada desde carrito', row)
    return Response({'id': quote.pk, 'folio': quote.folio}, status=201)


def build_quote(row, user, submitted=None, *, approved=False):
    """El llamador mantiene el bloqueo de la solicitud; un folio por selección."""
    lines = list(row.purchase_lines.all())
    submitted = submitted or {}
    if submitted.keys() - {str(line.pk) for line in lines}:
        raise ValidationError('Una referencia de precio no corresponde al detalle.')
    prices = [submitted.get(str(line.pk), line.unit_price) for line in lines]
    if not lines or any(price is None for price in prices):
        raise ValidationError('Indica un precio para cada producto sin valor de referencia.')
    total = sum(line.quantity * price for line, price in zip(lines, prices))
    if total > 999999999999:
        raise ValidationError('El monto supera el máximo de una cotización.')
    current = verified_agreement(row.client)
    agreement = row.agreement if current and row.agreement_id == current.pk else None
    mode = 'seguridad' if all(line.characteristics['category']=='seguridad' for line in lines) else 'particular'
    quote = Quote.objects.create(client=row.client, prescription=row.prescription, actor=user,
        agreement=agreement, category='convenio' if agreement else 'particular', product_type=mode,
        amount=total, approved=approved, notes=f'Solicitud de catálogo #{row.pk}. '+(
            'Selección y precio académico habilitado aceptados por el cliente.' if approved else 'Requiere revisión y aprobación.'))
    QuoteLine.objects.bulk_create([QuoteLine(quote=quote, product=line.product, product_name=line.product_name,
        variant=line.variant, quantity=line.quantity, unit_price=price) for line, price in zip(lines, prices)])
    row.purchase_quote = quote
    row.status = 'En revisión'
    row.save(update_fields=['purchase_quote','status','updated_at'])
    return quote
