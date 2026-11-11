"""Solicitudes de compra sin cobro y su conversión a cotizaciones en revisión."""
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.response import Response

from .catalog_requests import own_client
from .membership import verified_agreement
from .models import Client, Inquiry, Prescription, Product, PurchaseLine, Quote, QuoteLine
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
    return Response({'reference': row.token, 'state': row.status, 'created': created}, status=201 if created else 200)


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
    return Response({'mode': row.purchase_mode, 'state': row.status, 'prescription': row.prescription_id,
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
        lines = list(row.purchase_lines.all())
        submitted = form.validated_data['prices']
        if submitted.keys() - {str(line.pk) for line in lines}:
            raise ValidationError('Una referencia de precio no corresponde al detalle.')
        prices = [submitted.get(str(line.pk), line.unit_price) for line in lines]
        if not lines or any(price is None for price in prices):
            raise ValidationError('Indica un precio para cada producto sin valor de referencia.')
        total = sum(line.quantity * price for line, price in zip(lines, prices))
        if total > 999999999999:
            raise ValidationError('El monto supera el máximo de una cotización.')
        # La afiliación se comprobó al enviar la solicitud. Su referencia histórica se conserva.
        agreement = row.agreement
        if agreement and not hasattr(agreement, 'union'):
            current = verified_agreement(row.client)
            agreement = agreement if current and current.pk == agreement.pk else None
        mode = 'seguridad' if all(line.characteristics['category']=='seguridad' for line in lines) else 'particular'
        quote = Quote.objects.create(client=row.client, prescription=row.prescription, actor=request.user,
            agreement=agreement, category='convenio' if agreement else 'particular', product_type=mode,
            amount=total, approved=False, notes=f'Solicitud de catálogo #{row.pk}. Requiere revisión y aprobación.')
        QuoteLine.objects.bulk_create([QuoteLine(quote=quote, product=line.product, product_name=line.product_name,
            variant=line.variant, quantity=line.quantity, unit_price=price) for line, price in zip(lines, prices)])
        row.purchase_quote = quote
        row.status = 'En revisión'
        row.save(update_fields=['purchase_quote','status','updated_at'])
        audit(request.user, 'Cotización en borrador creada desde carrito', row)
    return Response({'id': quote.pk, 'folio': quote.folio}, status=201)
