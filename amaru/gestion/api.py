"""API de sesión y permisos de Django. Ningún identificador sustituye la autorización."""
import logging
from pathlib import Path
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.core import signing
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction, IntegrityError
from django.db.models import Q
from django.http import HttpResponse, FileResponse
from django.shortcuts import get_object_or_404, redirect
from django.middleware.csrf import get_token
from django.views.decorators.csrf import csrf_protect
from django.utils.decorators import method_decorator
from rest_framework import viewsets, serializers, permissions, status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError
from .models import *
from .serializers import *
from .services import audit, record_consent, convert_quote, accept_receipt

logger=logging.getLogger(__name__)


class ModelAccess(permissions.BasePermission):
    def has_permission(self,request,view):
        model=view.queryset.model
        if not request.user.is_authenticated: return False
        operation={'POST':'add','PUT':'change','PATCH':'change','DELETE':'delete'}.get(request.method,'view')
        return request.user.has_perm(f'gestion.{operation}_{model._meta.model_name}')


class Records(viewsets.ModelViewSet):
    permission_classes=[ModelAccess]
    http_method_names=['get','post','patch','head','options']
    def get_queryset(self):
        return self.queryset.order_by('-pk')
    def perform_create(self,serializer):
        with transaction.atomic():
            actor={'actor':self.request.user} if any(f.name=='actor' for f in serializer.Meta.model._meta.fields) else {}
            obj=serializer.save(**actor)
            if isinstance(obj,Client): record_consent(obj,self.request.user)
            audit(self.request.user,'Registro creado mediante API',obj)
    def perform_update(self,serializer):
        with transaction.atomic():
            # Bloqueo real: volver a validar contra la versión actual, no la leída antes del PATCH.
            serializer.instance=serializer.Meta.model.objects.select_for_update().get(pk=serializer.instance.pk)
            serializer.validate(dict(serializer.validated_data))
            obj=serializer.save()
            if isinstance(obj,Client): record_consent(obj,self.request.user)
            audit(self.request.user,'Actualización mediante API',obj)


class Clients(Records):
    queryset=Client.objects.select_related('agreement')
    serializer_class=ClientSerializer
    def get_queryset(self):
        qs=super().get_queryset()
        q=self.request.query_params.get('q','').strip()
        return qs.filter(Q(rut__icontains=q.replace('.','').upper())|Q(name__icontains=q)) if q else qs


class Prescriptions(Records):
    queryset=Prescription.objects.select_related('client')
    serializer_class=PrescriptionSerializer
    http_method_names=['get','post','head','options']


class Products(Records):
    queryset=Product.objects.all()
    serializer_class=ProductSerializer
    def get_permissions(self):
        return [permissions.AllowAny()] if self.request.method in ('GET','HEAD','OPTIONS') else super().get_permissions()
    def get_queryset(self):
        return super().get_queryset().filter(active=True)
    @action(detail=True,methods=['get'])
    def image(self,request,pk=None):
        product=self.get_object()
        if not product.image: return Response(status=404)
        if settings.R2_ENABLED: return redirect(product.image.url)
        return FileResponse(product.image.open('rb'),content_type='image/png' if product.image.name.lower().endswith('.png') else 'image/jpeg')


class Quotes(Records):
    queryset=Quote.objects.select_related('client','prescription').prefetch_related('lines__product')
    serializer_class=QuoteSerializer
    @action(detail=True,methods=['post'],url_path='items')
    def items(self,request,pk=None):
        if not request.user.has_perm('gestion.change_quote'): raise PermissionDenied()
        class LineInput(serializers.Serializer):
            product=serializers.PrimaryKeyRelatedField(queryset=Product.objects.filter(active=True))
            quantity=serializers.IntegerField(min_value=1,max_value=999)
            unit_price=serializers.DecimalField(max_digits=12,decimal_places=0,min_value=0)
        data=LineInput(data=request.data);data.is_valid(raise_exception=True)
        with transaction.atomic():
            q=Quote.objects.select_for_update().get(pk=self.get_object().pk)
            if q.approved or Order.objects.filter(quote=q).exists():raise ValidationError('Solo se pueden incorporar productos a un borrador sin OT.')
            try:
                with transaction.atomic():QuoteLine.objects.create(quote=q,**data.validated_data)
            except IntegrityError:raise ValidationError('Este producto ya pertenece a la cotización.')
            q.amount=sum(line.quantity*line.unit_price for line in q.lines.all());q.save()
            audit(request.user,'Producto incorporado a cotización',q)
        return Response(self.get_serializer(q).data)
    @action(detail=True,methods=['post'],url_path='convert')
    def convert(self,request,pk=None):
        if not request.user.has_perm('gestion.add_order'): raise PermissionDenied()
        q=self.get_object()
        try:
            obj=convert_quote(q.pk,request.user,request.data.get('inventory') or None)
        except (DjangoValidationError,Inventory.DoesNotExist) as exc:
            raise ValidationError(getattr(exc,'messages',['Inventario no válido.']))
        return Response(OrderSerializer(obj).data)


class OwnedRead(permissions.BasePermission):
    def has_permission(self,request,view):
        return request.user.is_authenticated


class Orders(viewsets.ReadOnlyModelViewSet):
    queryset=Order.objects.select_related('client','prescription','quote')
    serializer_class=OrderSerializer
    permission_classes=[OwnedRead]
    def get_queryset(self):
        qs=self.queryset.order_by('-pk')
        u=self.request.user
        if not u.has_perm('gestion.view_order'): qs=qs.filter(client__user=u)
        state=self.request.query_params.get('status')
        return qs.filter(status=state) if state else qs
    @action(detail=True,methods=['post'])
    def state(self,request,pk=None):
        if not request.user.has_perm('gestion.change_order'): raise PermissionDenied()
        with transaction.atomic():
            obj=Order.objects.select_for_update().get(pk=self.get_object().pk)
            value=request.data.get('status')
            if obj.status=='Entregada' or not isinstance(value,str) or value not in dict(Order.STATES) or value=='Entregada':
                raise ValidationError('Estado inválido. La entrega se registra desde el documento.')
            before=obj.status;obj.status=value;obj.save()
            audit(request.user,f'{before} → {value}',obj)
        return Response(self.get_serializer(obj).data)
    @action(detail=True,methods=['get'])
    def preview(self,request,pk=None):
        obj=self.get_object()
        if not request.user.has_perm('gestion.add_receipt') and obj.client.user_id!=request.user.pk:
            raise PermissionDenied()
        config=SiteConfiguration.objects.first()
        terms=config.warranty_terms if config else SiteConfiguration._meta.get_field('warranty_terms').get_default()
        payload={'order':obj.pk,'terms':terms,'client':obj.client.name,'rut':obj.client.rut,
                 'product':obj.characteristics,'status':obj.status,'updated':obj.updated_at.isoformat()}
        # Sello del servidor: evita confirmar condiciones distintas de las revisadas.
        return Response({**payload,'review_token':signing.dumps(payload,salt='delivery-review')})
    @action(detail=True,methods=['post'])
    def deliver(self,request,pk=None):
        obj=self.get_object()
        if not request.user.has_perm('gestion.add_receipt') and obj.client.user_id!=request.user.pk:
            raise PermissionDenied()
        token=request.data.get('review_token','')
        if not isinstance(token,str) or len(token)>16000:raise ValidationError('La revisión del documento no es válida.')
        try:
            reviewed=signing.loads(token,salt='delivery-review',max_age=600)
        except (signing.BadSignature,TypeError): raise ValidationError('Vuelva a revisar el documento; la revisión expiró o no es válida.')
        if reviewed['order']!=obj.pk: raise ValidationError('La revisión corresponde a otro pedido.')
        if request.data.get('accepted') is not True: raise ValidationError('Debe confirmar la recepción.')
        signature=request.data.get('signature','')
        if not signature: raise ValidationError('Dibuje la firma simple de recepción.')
        try:
            receipt=accept_receipt(obj.pk,request.user,True,signature,terms=reviewed['terms'],
                expected_updated=reviewed['updated'],observations=request.data.get('observations',''))
        except DjangoValidationError as exc: raise ValidationError(exc.messages)
        except Exception:
            logger.exception('Entrega no completada para OT %s',obj.pk)
            return Response({'detail':'No se pudo confirmar la respuesta de entrega. Consulte el estado antes de reintentar.'},status=503)
        return Response(ReceiptSerializer(receipt).data)


class Warranties(Records):
    queryset=Warranty.objects.select_related('order__client')
    serializer_class=WarrantySerializer


class Inquiries(viewsets.GenericViewSet):
    queryset=Inquiry.objects.all()
    serializer_class=InquirySerializer
    permission_classes=[ModelAccess]
    def get_permissions(self):
        return [permissions.AllowAny()] if self.action=='create' else super().get_permissions()
    def list(self,request):
        rows=self.paginate_queryset(self.queryset.order_by('-created_at'))
        return self.get_paginated_response(self.get_serializer(rows,many=True).data)
    @method_decorator(csrf_protect)
    def create(self,request):
        s=self.get_serializer(data=request.data);s.is_valid(raise_exception=True)
        data=s.validated_data
        try:
            with transaction.atomic():
                obj,created=Inquiry.objects.get_or_create(idempotency_key=data['idempotency_key'],defaults=data)
                if created:
                    if obj.kind=='agenda': AppointmentReservation.objects.create(inquiry=obj,day=obj.day,slot=obj.slot)
                    audit(request.user,'Solicitud pública recibida',obj)
        except IntegrityError: return Response({'detail':'Ese horario ya tiene una solicitud. Seleccione otro.'},status=409)
        # No devolver contactos existentes a quien adivine/reutilice un identificador.
        return Response({'reference':str(obj.token),'created':created,'detail':'Solicitud registrada para revisión; no confirma una atención ni envía mensajes.'},status=201 if created else 200)
    def partial_update(self,request,pk=None):
        with transaction.atomic():
            obj=Inquiry.objects.select_for_update().get(pk=self.get_object().pk)
            value=request.data.get('status')
            if not isinstance(value,str) or value not in dict(Inquiry.STATES): raise ValidationError('Estado inválido.')
            if value in ('Cerrada','Cancelada'): AppointmentReservation.objects.filter(inquiry=obj).delete()
            elif obj.kind=='agenda':
                try:
                    with transaction.atomic(): AppointmentReservation.objects.get_or_create(inquiry=obj,defaults={'day':obj.day,'slot':obj.slot})
                except IntegrityError: raise ValidationError('No se puede reabrir: horario ocupado.')
            obj.status=value;obj.actor=request.user;obj.save();audit(request.user,'Solicitud: '+value,obj)
        return Response(self.get_serializer(obj).data)


class Receipts(viewsets.ReadOnlyModelViewSet):
    queryset=Receipt.objects.select_related('order__client')
    serializer_class=ReceiptSerializer
    permission_classes=[OwnedRead]
    def get_queryset(self):
        qs=self.queryset.order_by('-created_at')
        return qs if self.request.user.has_perm('gestion.view_receipt') else qs.filter(order__client__user=self.request.user)
    @action(detail=True,methods=['get'],url_path='pdf')
    def pdf(self,request,pk=None):
        obj=self.get_object()
        return private_file(request,obj,obj.pdf)


def private_file(request,obj,file):
    if not file: return Response(status=404)
    audit(request.user,'Acceso a documento privado',obj)
    if settings.R2_ENABLED:
        response=Response({'url':file.url,'expires_in':settings.R2_URL_SECONDS})
    else: response=FileResponse(file.open('rb'),as_attachment=True,filename=Path(file.name).name)
    response['Cache-Control']='private, no-store'
    response['Referrer-Policy']='no-referrer'
    return response


@api_view(['GET'])
def prescription_file(request,pk):
    obj=get_object_or_404(Prescription,pk=pk)
    if not request.user.has_perm('gestion.view_prescription') and obj.client.user_id!=request.user.pk: raise PermissionDenied()
    return private_file(request,obj,obj.file)


class Audits(viewsets.ReadOnlyModelViewSet):
    queryset=Audit.objects.all()
    serializer_class=AuditSerializer
    permission_classes=[ModelAccess]


class Inventories(Records):
    queryset=Inventory.objects.all()
    serializer_class=InventorySerializer


class Agreements(Records):
    queryset=Agreement.objects.all()
    serializer_class=AgreementSerializer


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def session(request):
    token=get_token(request)
    user=request.user
    client=Client.objects.filter(user=user).first() if user.is_authenticated else None
    response=Response({'authenticated':user.is_authenticated,'username':user.get_username() if user.is_authenticated else None,
        'client_id':client.pk if client else None,'permissions':sorted(user.get_all_permissions()) if user.is_authenticated else [],
        'csrf':token,'storage':'r2' if settings.R2_ENABLED else 'local-private'})
    response['Cache-Control']='no-store'
    return response


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
@csrf_protect
def sign_in(request):
    key='login:'+request.META.get('REMOTE_ADDR','')
    attempts=cache.get(key,0)
    if attempts>=10: return Response({'detail':'Demasiados intentos. Espere cinco minutos.'},status=429)
    cache.set(key,attempts+1,300)
    class Credentials(serializers.Serializer):
        username=serializers.CharField(max_length=254)
        password=serializers.CharField(max_length=1024,trim_whitespace=False)
    credentials=Credentials(data=request.data);credentials.is_valid(raise_exception=True)
    user=authenticate(request,**credentials.validated_data)
    if not user: return Response({'detail':'Credenciales inválidas.'},status=400)
    login(request,user);cache.delete(key)
    return Response({'detail':'Sesión iniciada.','csrf':get_token(request)})


@api_view(['POST'])
def sign_out(request):
    logout(request)
    return Response({'detail':'Sesión cerrada.'})


@api_view(['GET','PATCH'])
def configuration(request):
    if not request.user.has_perm('gestion.change_siteconfiguration'): raise PermissionDenied()
    obj=SiteConfiguration.objects.first()
    if request.method=='PATCH':
        terms=request.data.get('warranty_terms','')
        if not isinstance(terms,str):raise ValidationError('Las condiciones deben ser texto.')
        terms=terms.strip()
        if not terms or len(terms)>12000: raise ValidationError('Condiciones requeridas, máximo 12000 caracteres.')
        with transaction.atomic():
            obj=obj or SiteConfiguration()
            obj.warranty_terms=terms;obj.save();audit(request.user,'Condiciones de garantía actualizadas',obj)
    return Response({'warranty_terms':obj.warranty_terms if obj else SiteConfiguration._meta.get_field('warranty_terms').get_default()})
