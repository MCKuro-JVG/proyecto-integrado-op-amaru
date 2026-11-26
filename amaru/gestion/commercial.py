"""Beneficios, inventario y transferencias académicas con permisos de Django."""
import csv
import hashlib
import re
from decimal import Decimal
from io import BytesIO, StringIO
from pathlib import Path
from django.core.exceptions import ValidationError as ModelValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, serializers, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from reportlab.graphics.barcode import createBarcodeDrawing
from reportlab.pdfgen import canvas
from .api import Records
from .catalog_requests import own_client
from .date_filters import filter_created_dates
from .models import (AgreementBenefit, Brand, Inventory, Order, PaymentReview, PaymentVoucher, Product,
                     ProductModel, ProductVariant, Quote, StockCategory, StockMovement, StockReservation,
                     Supplier, TransferConfiguration, TransferPayment)
from .services import audit, convert_quote
from .unions import private
from . import benefits, stock
from .validators import normalize_rut, validate_document


class BenefitSerializer(serializers.ModelSerializer):
    agreement_name = serializers.CharField(source='agreement.name', read_only=True)

    class Meta:
        model = AgreementBenefit
        fields = ['id', 'name', 'agreement', 'agreement_name', 'description', 'kind', 'value', 'products',
                  'category', 'starts_on', 'ends_on', 'role', 'conditions', 'active', 'public_visible']

    def validate(self, data):
        def value(key):
            return data.get(key, getattr(self.instance, key, None))
        start, end = value('starts_on'), value('ends_on')
        if start and end and end < start:
            raise ValidationError({'ends_on': 'La fecha final debe ser posterior al inicio.'})
        number, kind = value('value'), value('kind')
        if number is not None and (number < 0 or (kind == 'percent' and number > 100)):
            raise ValidationError({'value': 'Usa montos positivos y porcentajes entre 0 y 100.'})
        if kind in ('percent', 'fixed', 'price', 'contribution') and number is None:
            raise ValidationError({'value': 'Indica el porcentaje o monto de este beneficio.'})
        if kind != 'percent' and number is not None and number != number.quantize(Decimal('1')):
            raise ValidationError({'value': 'Los montos CLP deben ser enteros.'})
        return data


class Benefits(Records):
    queryset = AgreementBenefit.objects.select_related('agreement').prefetch_related('products')
    serializer_class = BenefitSerializer

    def get_queryset(self):
        rows = super().get_queryset()
        agreement = self.request.query_params.get('agreement')
        return rows.filter(agreement_id=agreement) if agreement and agreement.isdecimal() else rows


@api_view(['GET'])
def my_benefits(request):
    from .unions import representative_union
    union = representative_union(request.user)
    if union:
        rows = union.agreement.benefits.filter(active=True)
        today = timezone.localdate()
        rows = rows.filter(Q(starts_on__isnull=True) | Q(starts_on__lte=today)).filter(Q(ends_on__isnull=True) | Q(ends_on__gte=today)) if union.agreement.available else rows.none()
    else:
        rows = benefits.eligible(own_client(request.user))
    return private(BenefitSerializer(rows, many=True).data)


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ['id', 'name', 'active']


class ModelSerializer(serializers.ModelSerializer):
    brand_name = serializers.CharField(source='brand.name', read_only=True)
    class Meta:
        model = ProductModel
        fields = ['id', 'name', 'brand', 'brand_name', 'active']


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = StockCategory
        fields = ['id', 'name', 'active']


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ['id', 'name', 'rut', 'phone', 'email', 'address', 'contact', 'notes', 'active']

    def validate_rut(self, value):
        try:
            return normalize_rut(value) if value else ''
        except ModelValidationError as error:
            raise ValidationError(error.messages) from None


class Brands(Records):
    queryset = Brand.objects.all()
    serializer_class = BrandSerializer


class Models(Records):
    queryset = ProductModel.objects.select_related('brand')
    serializer_class = ModelSerializer

    def get_queryset(self):
        rows = super().get_queryset()
        brand = self.request.query_params.get('brand')
        return rows.filter(brand_id=brand) if brand and brand.isdecimal() else rows


class Categories(Records):
    queryset = StockCategory.objects.all()
    serializer_class = CategorySerializer

    def get_permissions(self):
        if self.request.method in ('GET', 'HEAD', 'OPTIONS'):
            return [permissions.AllowAny()]
        return super().get_permissions()

    def get_queryset(self):
        rows = super().get_queryset()
        return rows if self.request.user.has_perm('gestion.view_stockcategory') else rows.filter(active=True)


class Suppliers(Records):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer


class VariantSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True, allow_null=True)
    class Meta:
        model = ProductVariant
        fields = ['id', 'product', 'product_name', 'label', 'sku', 'barcode', 'supplier', 'supplier_name', 'color', 'size', 'active', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

    def validate_barcode(self, value):
        value = value.strip() if value else None
        if value and not re.fullmatch(r'[\x21-\x7e]{1,80}', value):
            raise ValidationError('Usa entre 1 y 80 caracteres ASCII imprimibles para Code 128.')
        return value

    def validate(self, data):
        if self.instance and any(key in data and data[key] != getattr(self.instance, key) for key in ('product', 'label', 'sku')):
            raise ValidationError('Conserva producto, variante y SKU para mantener las referencias históricas.')
        return data


class Variants(Records):
    queryset = ProductVariant.objects.select_related('product', 'supplier')
    serializer_class = VariantSerializer

    def get_queryset(self):
        rows = super().get_queryset()
        pk = self.request.query_params.get('product')
        return rows.filter(product_id=pk) if pk and pk.isdecimal() else rows

    @transaction.atomic
    def perform_create(self, serializer):
        product = Product.objects.select_for_update().get(pk=serializer.validated_data['product'].pk)
        row = serializer.save()
        if row.label and row.label not in product.variants:
            product.variants = [*product.variants, row.label]
            product.save(update_fields=['variants'])
        if not row.label and product.variants:
            raise ValidationError('Selecciona una variante del producto o crea un producto de modelo único.')
        Inventory.objects.create(variant=row, name=f'{product.name} {row.label}'.strip(), category=product.category)
        audit(self.request.user, 'Variante inventariable creada', row)


class StockSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source='variant.sku', read_only=True, default='')
    barcode = serializers.CharField(source='variant.barcode', read_only=True, default='')
    product_name = serializers.CharField(source='variant.product.name', read_only=True, default='')
    product_id = serializers.IntegerField(source='variant.product_id', read_only=True, default=None)
    variant_label = serializers.CharField(source='variant.label', read_only=True, default='')
    color = serializers.CharField(source='variant.color', read_only=True, default='')
    size = serializers.CharField(source='variant.size', read_only=True, default='')
    sale_price = serializers.DecimalField(source='variant.product.reference_price', max_digits=12,
                                          decimal_places=0, read_only=True, default=None, allow_null=True)
    brand_name = serializers.CharField(source='variant.product.brand.name', read_only=True, default='')
    model_name = serializers.CharField(source='variant.product.model.name', read_only=True, default='')
    category_name = serializers.CharField(source='variant.product.stock_category.name', read_only=True, default='')
    supplier_name = serializers.CharField(source='variant.supplier.name', read_only=True, default='')
    reserved = serializers.SerializerMethodField()
    available = serializers.SerializerMethodField()
    active = serializers.BooleanField(source='variant.active', read_only=True, default=True)

    class Meta:
        model = Inventory
        fields = ['id', 'name', 'category', 'variant', 'quantity', 'minimum', 'location', 'unit_cost', 'notes',
                  'sku', 'barcode', 'product_id', 'product_name', 'variant_label', 'color', 'size', 'sale_price',
                  'brand_name', 'model_name', 'category_name', 'supplier_name', 'reserved', 'available', 'active']
        read_only_fields = ['name', 'category', 'variant', 'quantity']

    def get_reserved(self, obj):
        return obj.quantity - obj.available_units if hasattr(obj, 'available_units') else stock.reserved(obj)

    def get_available(self, obj):
        return obj.quantity - self.get_reserved(obj)

    def to_representation(self, obj):
        data = super().to_representation(obj)
        if not self.context['request'].user.has_perm('gestion.change_transferconfiguration'):
            data.pop('unit_cost', None)
        return data

    def validate_unit_cost(self, value):
        if not self.context['request'].user.has_perm('gestion.change_transferconfiguration'):
            raise PermissionDenied('Los costos requieren autorización administrativa.')
        if value is not None and value < 0:
            raise ValidationError('El costo debe ser positivo.')
        return value

    def validate(self, data):
        if 'quantity' in self.initial_data:
            raise ValidationError('Registra las cantidades mediante un movimiento o ajuste con motivo.')
        return data


class MovementInput(serializers.Serializer):
    kind = serializers.ChoiceField(choices=['entry', 'exit', 'adjustment'])
    quantity = serializers.IntegerField(min_value=0, max_value=1000000)
    reason = serializers.CharField(min_length=5, max_length=240)
    reference = serializers.CharField(max_length=180, required=False, allow_blank=True)
    operation = serializers.UUIDField()
    supplier = serializers.PrimaryKeyRelatedField(queryset=Supplier.objects.filter(active=True), required=False, allow_null=True)
    unit_cost = serializers.DecimalField(max_digits=12, decimal_places=0, min_value=0, required=False, allow_null=True)


PAYMENTS_FOR_REVIEW = ('submitted', 'review')


def stock_with_availability(rows):
    from django.db.models import OuterRef, Subquery, IntegerField, Value, F
    from django.db.models.functions import Coalesce
    reserved = StockReservation.objects.filter(
        inventory_id=OuterRef('pk'), state='active', expires_at__gt=timezone.now(),
    ).values('inventory').annotate(n=Sum('quantity')).values('n')
    return rows.annotate(available_units=F('quantity') - Coalesce(Subquery(reserved, output_field=IntegerField()), Value(0)))


class Stocks(Records):
    queryset = Inventory.objects.select_related('variant__product__brand', 'variant__product__model',
        'variant__product__stock_category', 'variant__supplier')
    serializer_class = StockSerializer
    http_method_names = ['get', 'patch', 'post', 'head', 'options']

    def get_permissions(self):
        if self.action == 'movement':
            return [permissions.IsAuthenticated()]
        return super().get_permissions()

    def create(self, request):
        raise ValidationError('Crea una variante inventariable desde Productos. Registra las unidades mediante Entradas.')

    def get_queryset(self):
        rows = super().get_queryset()
        filters = self.request.query_params
        q = filters.get('q', '').strip()[:180]
        if q:
            query = (Q(name__icontains=q) | Q(variant__sku__icontains=q) | Q(variant__barcode=q)
                     | Q(variant__product__name__icontains=q) | Q(variant__product__brand__name__icontains=q)
                     | Q(variant__product__model__name__icontains=q) | Q(variant__product__stock_category__name__icontains=q)
                     | Q(variant__supplier__name__icontains=q))
            if q.isascii() and q.isdecimal() and len(q) <= 18:
                query |= Q(pk=int(q)) | Q(variant__product_id=int(q))
            rows = rows.filter(query)
        for key, column in [('brand', 'variant__product__brand_id'), ('category_id', 'variant__product__stock_category_id'), ('supplier', 'variant__supplier_id')]:
            value = filters.get(key, '')
            if value.isdecimal():
                rows = rows.filter(**{column: int(value)}) if len(value) <= 18 else rows.none()
        if filters.get('active') in ('true', 'false'):
            rows = rows.filter(variant__active=filters['active'] == 'true')
        from django.db.models import F
        rows = stock_with_availability(rows)
        availability = filters.get('stock')
        if availability == 'empty':
            rows = rows.filter(available_units=0)
        elif availability == 'low':
            rows = rows.filter(available_units__gt=0, available_units__lte=F('minimum'))
        elif availability == 'available':
            rows = rows.filter(available_units__gt=0)
        return rows

    @action(detail=True, methods=['post'])
    def movement(self, request, pk=None):
        if not request.user.has_perms(['gestion.add_stockmovement', 'gestion.view_inventory']):
            raise PermissionDenied()
        form = MovementInput(data=request.data)
        form.is_valid(raise_exception=True)
        if form.validated_data.get('unit_cost') is not None and not request.user.has_perm('gestion.change_transferconfiguration'):
            raise PermissionDenied()
        if form.validated_data['kind'] == 'adjustment' and not request.user.has_perm('gestion.change_inventory'):
            raise PermissionDenied()
        row = stock.move(self.get_object().pk, request.user, **form.validated_data)
        return private({'id': row.pk, 'stock': row.after})

    @action(detail=False, methods=['get'])
    def summary(self, request):
        from django.db.models import Count, F
        from django.db.models.functions import Coalesce
        rows = self.get_queryset()
        data = rows.aggregate(items=Count('pk'), physical=Coalesce(Sum('quantity'), 0), available=Coalesce(Sum('available_units'), 0),
            low=Count('pk',filter=Q(available_units__gt=0,available_units__lte=F('minimum'))),
            empty=Count('pk',filter=Q(available_units=0)))
        data['products'] = Product.objects.count()
        data['reserved'] = data['physical'] - data['available']
        if request.user.has_perm('gestion.change_transferconfiguration'):
            data['value'] = str(rows.aggregate(value=Sum(F('unit_cost')*F('quantity')))['value'] or 0)
        return private(data)

    @action(detail=True, methods=['get'])
    def label(self, request, pk=None):
        item = self.get_object()
        if not item.variant_id:
            raise ValidationError('El artículo histórico necesita una variante antes de imprimir una etiqueta.')
        code = item.variant.barcode or item.variant.sku
        buffer = BytesIO()
        page = canvas.Canvas(buffer, pagesize=(280, 155))
        page.setFont('Helvetica', 10)
        page.drawString(12, 135, item.name[:42])
        drawing = createBarcodeDrawing('Code128', value=code, barHeight=40, humanReadable=True)
        drawing.scale(min(1, 250/drawing.width), 1)
        drawing.drawOn(page, 12, 50)
        page.setFont('Helvetica', 8)
        page.drawString(12, 25, 'Identificador interno Code 128 · SKU ' + item.variant.sku[:35])
        page.save()
        return FileResponse(BytesIO(buffer.getvalue()), filename='etiqueta-interna.pdf', content_type='application/pdf')

    @action(detail=False, methods=['get'])
    def report(self, request):
        if not request.user.has_perm('gestion.view_stockmovement'):
            raise PermissionDenied()
        out = StringIO()
        writer = csv.writer(out)
        writer.writerow(['Artículo', 'SKU', 'Físico', 'Reservado', 'Disponible', 'Mínimo'])
        for row in self.get_queryset().iterator(chunk_size=100):
            name = row.name
            if name.startswith(('=', '+', '-', '@')):
                name = "'" + name
            writer.writerow([name, "'" + row.variant.sku if row.variant_id else '', row.quantity,
                             row.quantity-row.available_units, row.available_units, row.minimum])
        response = HttpResponse('\ufeff'+out.getvalue(), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="inventario.csv"'
        return response


class MovementSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='inventory.name', read_only=True)
    sku = serializers.CharField(source='inventory.variant.sku', read_only=True, default='')
    actor_name = serializers.CharField(source='actor.username', read_only=True)
    class Meta:
        model = StockMovement
        fields = ['id', 'inventory', 'name', 'sku', 'kind', 'delta', 'before', 'after', 'reason', 'reference', 'actor_name', 'created_at']


class Movements(Records):
    queryset = StockMovement.objects.select_related('inventory__variant', 'actor')
    serializer_class = MovementSerializer
    http_method_names = ['get', 'head', 'options']

    def get_queryset(self):
        rows = super().get_queryset()
        for param, field in [('item', 'inventory_id'), ('kind', 'kind')]:
            value = self.request.query_params.get(param)
            if value:
                if param == 'item' and (not value.isdecimal() or len(value)>18):
                    raise ValidationError('Artículo inválido.')
                rows = rows.filter(**{field: value})
        return filter_created_dates(rows, self.request.query_params)


class BankSerializer(serializers.ModelSerializer):
    class Meta:
        model = TransferConfiguration
        fields = ['recipient', 'bank', 'account_type', 'account_number', 'holder_rut', 'email', 'reserve_hours']

    def validate_reserve_hours(self, value):
        if not 1 <= value <= 720:
            raise ValidationError('Indica entre 1 y 720 horas.')
        return value


@api_view(['GET', 'PATCH'])
def bank_configuration(request):
    if not request.user.has_perm('gestion.change_transferconfiguration'):
        raise PermissionDenied()
    with transaction.atomic():
        row, _ = TransferConfiguration.objects.get_or_create(pk=1)
        row = TransferConfiguration.objects.select_for_update().get(pk=row.pk)
        if request.method == 'PATCH':
            form = BankSerializer(row, data=request.data, partial=True)
            form.is_valid(raise_exception=True)
            form.save()
            audit(request.user, 'Configuración académica de transferencia y reservas actualizada', row)
    return private({**BankSerializer(row).data, 'academic': True})


def payment_rows(user):
    rows = TransferPayment.objects.select_related('quote__client', 'quote__agreement', 'quote__order').prefetch_related('vouchers', 'reviews', 'quote__lines__product')
    if not user.has_perm('gestion.view_transferpayment'):
        client = own_client(user)
        rows = rows.filter(quote__client=client)
    return rows


def payment_summary(payment):
    q = payment.quote
    order = getattr(q, 'order', None)
    return {'id': payment.pk, 'reference': str(payment.reference), 'quote': q.pk, 'folio': q.folio, 'method': 'transferencia',
        'client_name': q.client.name, 'rut': q.client.rut, 'agreement': q.agreement.name if q.agreement else None,
        'amount': str(payment.amount), 'original_amount': str(q.original_amount or q.amount),
        'benefit': q.benefit_snapshot, 'state': payment.state, 'state_label': payment.get_state_display(),
        'created_at': payment.created_at, 'bank': payment.bank_snapshot, 'academic': True,
        'order': {'folio': order.folio, 'state': order.status} if order else None,
        'items': [{'name': line.product_name or line.product.name, 'variant': line.variant,
                   'quantity': line.quantity, 'unit_price': str(line.unit_price)} for line in q.lines.all()],
        'vouchers': [{'id': v.pk, 'declared_amount': str(v.declared_amount), 'created_at': v.created_at,
                      'url': f'/api/payment-vouchers/{v.pk}/file/'} for v in payment.vouchers.all()],
        'history': [{'before': r.before, 'state': r.after, 'observations': r.observations, 'created_at': r.created_at} for r in payment.reviews.all()]}


@api_view(['GET'])
def payments(request):
    rows = payment_rows(request.user).order_by('-pk')
    query = request.query_params
    q = query.get('q', '').strip()[:180]
    if q:
        rows = rows.filter(Q(quote__client__name__icontains=q) | Q(reference__icontains=q) | Q(quote__client__rut__icontains=q.replace('.', '')))
    if query.get('rut'):
        try:
            rows = rows.filter(quote__client__rut=normalize_rut(query['rut']))
        except ModelValidationError:
            raise ValidationError('El RUT no es válido.') from None
    if query.get('folio'):
        match = re.fullmatch(r'(COT|OT)-([0-9]{6,18})(?:-([0-9A-F]{12}))?', query['folio'].strip().upper())
        if not match:
            raise ValidationError('Utiliza un folio COT de cotización u OT de pedido.')
        prefix, number, token = match.groups()
        field = 'quote' if prefix == 'COT' else 'quote__order'
        rows = rows.filter(**{field+'__pk': int(number)})
        if token:
            rows = rows.filter(**{field+'__token__istartswith': token})
    if query.get('state') == 'for_review':
        rows = rows.filter(state__in=PAYMENTS_FOR_REVIEW)
    elif query.get('state'):
        rows = rows.filter(state=query['state'])
    rows = filter_created_dates(rows, query)
    pagination = PageNumberPagination()
    selected = pagination.paginate_queryset(rows, request)
    return pagination.get_paginated_response([payment_summary(p) for p in selected])


@api_view(['POST'])
@transaction.atomic
def confirm_payment(request, pk):
    if not request.user.has_perms(['gestion.change_quote', 'gestion.add_transferpayment']):
        raise PermissionDenied()
    q = get_object_or_404(Quote.objects.select_for_update(), pk=pk)
    existing = TransferPayment.objects.filter(quote=q).first()
    if existing:
        return private(payment_summary(existing))
    if Order.objects.filter(quote=q).exists() or not q.approved or not q.client.active:
        raise ValidationError('Requiere una cotización aprobada de cliente activo y sin orden previa.')
    lines = list(q.lines.select_related('product'))
    if not lines or any(not line.product.active for line in lines):
        raise ValidationError('Revisa el detalle y la disponibilidad de los productos antes de confirmar el monto.')
    if any(not line.product.stock_variants.filter(label=line.variant, active=True).exists() for line in lines):
        raise ValidationError('Configura la variante y sus existencias antes de solicitar una transferencia.')
    if any(line.product.mining_only for line in lines):
        from .unions import membership_for
        if not membership_for(q.client):
            raise ValidationError('El catálogo minero requiere una afiliación vigente al confirmar la operación.')
    needs_recipe = any(line.product.requires_prescription for line in lines)
    if needs_recipe and (not q.prescription or not q.prescription.valid or not q.prescription.file
                         or q.prescription.client_id != q.client_id or request.data.get('prescription_reviewed') is not True):
        raise ValidationError('Revisa y confirma una receta vigente del cliente.')
    if request.data.get('confirmed') is not True:
        raise ValidationError('Confirma precios, disponibilidad y condiciones antes de solicitar el pago.')
    return private(payment_summary(create_payment(q, request.user)), status=201)


def create_payment(q, user, *, expected_amount=None):
    """Se invoca dentro de una transacción con la cotización bloqueada y validada."""
    existing = TransferPayment.objects.filter(quote=q).first()
    if existing:
        return existing
    lines = list(q.lines.select_related('product'))
    original, final, snapshot = benefits.calculate(q.client, [{'product': l.product, 'price': l.unit_price, 'quantity': l.quantity} for l in lines])
    if expected_amount is not None and final != expected_amount:
        from .purchases import Conflict
        raise Conflict('El precio o beneficio cambió. Actualiza el carrito y confirma el nuevo total.')
    if final <= 0:
        raise ValidationError('El total no requiere una transferencia. Solicita una revisión administrativa del beneficio.')
    q.original_amount, q.amount, q.benefit_snapshot = original, final, snapshot
    q.confirmed_at, q.confirmed_by = timezone.now(), user
    q.save(update_fields=['original_amount', 'amount', 'benefit_snapshot', 'confirmed_at', 'confirmed_by', 'updated_at'])
    stock.reserve_quote(q, user)
    config, _ = TransferConfiguration.objects.get_or_create(pk=1)
    bank = BankSerializer(config).data
    # Campos operativos quedan preparados en configuración; la demostración entrega datos inoperativos.
    bank.update(bank='Banco ficticio · SIN OPERACIÓN', account_number='DEMO-NO-OPERATIVA', holder_rut='DEMO-SIN-RUT-BANCARIO')
    payment = TransferPayment.objects.create(quote=q, amount=final, bank_snapshot=dict(bank))
    audit(user, 'Monto confirmado y transferencia académica solicitada', payment)
    return payment


class VoucherInput(serializers.Serializer):
    file = serializers.FileField()
    declared_amount = serializers.DecimalField(max_digits=12, decimal_places=0, min_value=0)

    def validate_file(self, value):
        if value.size > 5 * 1024 * 1024:
            raise ValidationError('El comprobante admite hasta 5 MB.')
        try:
            validate_document(value)
        except ModelValidationError as error:
            raise ValidationError(error.messages) from None
        return value


@api_view(['POST'])
def submit_voucher(request, pk):
    client = own_client(request.user)
    form = VoucherInput(data=request.data)
    form.is_valid(raise_exception=True)
    saved = None
    try:
        with transaction.atomic():
            ref = get_object_or_404(TransferPayment, pk=pk, quote__client=client)
            q = Quote.objects.select_for_update().get(pk=ref.quote_id)
            payment = TransferPayment.objects.select_for_update().get(pk=pk)
            upload = form.validated_data['file']
            digest = hashlib.sha256()
            for chunk in upload.chunks():
                digest.update(chunk)
            upload.seek(0)
            previous = payment.vouchers.filter(sha256=digest.hexdigest()).first()
            if (previous and payment.state in ('submitted', 'review')
                    and previous.declared_amount == form.validated_data['declared_amount']
                    and previous.pk == payment.vouchers.order_by('-pk').values_list('pk', flat=True).first()):
                return private(payment_summary(payment))
            if payment.state not in ('pending', 'rejected'):
                raise ValidationError('El pago ya tiene un comprobante pendiente o está cerrado.')
            if previous:
                raise ValidationError('Este comprobante ya fue enviado. Selecciona un archivo corregido.')
            stock.reserve_quote(q, request.user)
            voucher = PaymentVoucher(payment=payment, declared_amount=form.validated_data['declared_amount'], sha256=digest.hexdigest(), submitted_by=request.user)
            voucher.file.save(upload.name, upload, save=False)
            saved = voucher.file
            voucher.save()
            before = payment.state
            payment.state = 'submitted'
            payment.save(update_fields=['state', 'updated_at'])
            PaymentReview.objects.create(payment=payment, voucher=voucher, before=before, after=payment.state, actor=request.user, observations='Comprobante académico recibido para revisión.')
            audit(request.user, 'Comprobante privado enviado', payment)
    except Exception:
        if saved:
            saved.storage.delete(saved.name)
        raise
    return private(payment_summary(payment), status=201)


@api_view(['GET'])
def voucher_file(request, pk):
    voucher = get_object_or_404(PaymentVoucher, pk=pk, payment__in=payment_rows(request.user))
    audit(request.user, 'Consulta autorizada de comprobante bancario', voucher)
    suffix = Path(voucher.file.name).suffix.lower()
    content_type = {'.pdf': 'application/pdf', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg'}[suffix]
    preview = request.query_params.get('vista') == '1'
    response = FileResponse(voucher.file.open('rb'), as_attachment=not preview,
                            filename='comprobante-academico'+suffix, content_type=content_type)
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Referrer-Policy'] = 'no-referrer'
    if preview:
        response['Content-Security-Policy'] = "default-src 'none'; frame-ancestors 'none'; form-action 'none'"
    return response


@api_view(['GET'])
def payment_detail(request, pk):
    return private(payment_summary(get_object_or_404(payment_rows(request.user), pk=pk)))


class ReviewInput(serializers.Serializer):
    state = serializers.ChoiceField(choices=['review', 'approved', 'rejected', 'cancelled'])
    expected_state = serializers.ChoiceField(choices=TransferPayment.STATES)
    voucher = serializers.IntegerField(min_value=1, required=False)
    observations = serializers.CharField(min_length=5, max_length=1000)
    bank_checked = serializers.BooleanField(default=False)


@api_view(['POST'])
@transaction.atomic
def review_payment(request, pk):
    if not request.user.has_perm('gestion.change_transferpayment'):
        raise PermissionDenied()
    form = ReviewInput(data=request.data)
    form.is_valid(raise_exception=True)
    data = form.validated_data
    ref = get_object_or_404(TransferPayment, pk=pk)
    q = Quote.objects.select_for_update().get(pk=ref.quote_id)
    payment = TransferPayment.objects.select_for_update().get(pk=pk)
    before = payment.state
    if before != data['expected_state'] or before in ('approved', 'cancelled'):
        raise ValidationError('El pago cambió o ya está cerrado. Actualiza la pantalla.')
    voucher = payment.vouchers.order_by('-pk').first()
    if data['state'] != 'cancelled' and (before not in ('submitted', 'review') or not voucher or voucher.pk != data.get('voucher')):
        raise ValidationError('Abre el comprobante vigente antes de revisarlo.')
    if data['state'] == 'approved':
        if not data['bank_checked'] or voucher.declared_amount != payment.amount:
            raise ValidationError('Confirma el contraste bancario y verifica que el monto declarado coincida.')
        stock.reserve_quote(q, request.user, paid=True)
        convert_quote(q.pk, request.user, payment_approval=True)
    if data['state'] == 'cancelled':
        if Order.objects.filter(quote=q).exists():
            raise ValidationError('La cotización ya tiene una orden. Requiere revisión administrativa para cancelarla.')
        stock.release_quote(q, request.user)
    payment.state = data['state']
    payment.save(update_fields=['state', 'updated_at'])
    PaymentReview.objects.create(payment=payment, voucher=voucher, before=before, after=payment.state, observations=data['observations'], actor=request.user)
    audit(request.user, f'Pago {before} → {payment.state}', payment)
    return private(payment_summary(payment))


@api_view(['POST'])
@transaction.atomic
def cancel_order(request, pk):
    if not request.user.has_perm('gestion.change_order'):
        raise PermissionDenied()
    class CancellationInput(serializers.Serializer):
        reason = serializers.CharField(min_length=5, max_length=240)
        confirmed = serializers.BooleanField()
    form = CancellationInput(data=request.data)
    form.is_valid(raise_exception=True)
    order = get_object_or_404(Order.objects.select_for_update(), pk=pk)
    quote = Quote.objects.select_for_update().get(pk=order.quote_id)
    payment = TransferPayment.objects.select_for_update().filter(quote=quote).first()
    if payment and payment.state == 'approved' and not request.user.has_perm('gestion.change_transferconfiguration'):
        raise PermissionDenied('La cancelación de una orden pagada requiere revisión administrativa.')
    if not form.validated_data['confirmed'] or order.status == 'Entregada':
        raise ValidationError('Confirma la cancelación de una orden que aún no se haya entregado.')
    if order.status == 'Cancelada':
        return private({'state': order.status})
    if quote.stock_reservations.filter(state='consumed').exists():
        raise ValidationError('La orden ya tiene una salida física. Requiere revisar la devolución de inventario.')
    stock.release_quote(quote, request.user)
    before = order.status
    order.status = 'Cancelada'
    order.save(update_fields=['status','updated_at'])
    from .pickup import sync_order_state
    sync_order_state(order,before,request.user)
    if payment and payment.state not in ('approved','cancelled'):
        PaymentReview.objects.create(payment=payment,before=payment.state,after='cancelled',actor=request.user,observations=form.validated_data['reason'])
        payment.state='cancelled'
        payment.save(update_fields=['state','updated_at'])
    audit(request.user,'Orden cancelada · '+form.validated_data['reason'],order)
    return private({'state':order.status,'detail':'Reservas liberadas. Los pagos recibidos conservan su historial y requieren revisar la devolución por un canal autorizado.'})
