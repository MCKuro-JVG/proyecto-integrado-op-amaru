"""Contratos de la API; los identificadores de archivos privados no son URLs públicas."""
from django.utils import timezone
from rest_framework import serializers
from .models import *
from .validators import normalize_rut


class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model=Client
        fields=['id','rut','name','phone','email','category','agreement','consent','active','created_at','updated_at']
        read_only_fields=['created_at','updated_at']
    def validate_rut(self,value):
        try: value=normalize_rut(value)
        except Exception as exc: raise serializers.ValidationError('RUT inválido.') from exc
        qs=Client.objects.filter(rut=value)
        if self.instance: qs=qs.exclude(pk=self.instance.pk)
        if qs.exists(): raise serializers.ValidationError('El RUT ya está registrado.')
        return value
    def validate(self,data):
        category=data.get('category',getattr(self.instance,'category',None))
        if category=='convenio' and not data.get('agreement',getattr(self.instance,'agreement_id',None)):
            raise serializers.ValidationError({'agreement':'Seleccione un convenio.'})
        if category=='particular': data['agreement']=None
        return data


class PrescriptionSerializer(serializers.ModelSerializer):
    status=serializers.CharField(read_only=True)
    file=serializers.FileField(write_only=True,required=True)
    class Meta:
        model=Prescription
        fields=['id','client','issued_on','file','physical_reference','status','created_at']
        read_only_fields=['created_at']
    def validate_issued_on(self,value):
        if value>timezone.localdate(): raise serializers.ValidationError('La fecha no puede ser futura.')
        return value
    def validate_file(self,value):
        from .validators import validate_document
        validate_document(value)
        return value


class ProductSerializer(serializers.ModelSerializer):
    image_url=serializers.SerializerMethodField()
    image=serializers.ImageField(write_only=True,required=False)
    class Meta:
        model=Product
        fields=['id','sku','name','category','description','crystal','treatments','color','image','image_url','active']
    def get_image_url(self,obj):
        return f'/api/products/{obj.pk}/image/' if obj.image else None
    def validate_image(self,value):
        from .validators import validate_document
        validate_document(value)
        return value


class QuoteSerializer(serializers.ModelSerializer):
    folio=serializers.CharField(read_only=True)
    lines=serializers.SerializerMethodField()
    class Meta:
        model=Quote
        fields=['id','folio','client','prescription','product_type','category','agreement','characteristics','amount','approved','notes','created_at','updated_at','lines']
        read_only_fields=['created_at','updated_at']
    def get_lines(self,obj):
        return [{'product':l.product_id,'name':l.product.name,'quantity':l.quantity,'unit_price':str(l.unit_price)} for l in obj.lines.all()]
    def validate(self,data):
        if self.instance and Order.objects.filter(quote=self.instance).exists():
            raise serializers.ValidationError('La cotización ya tiene una OT; conserva su versión.')
        client=data.get('client',getattr(self.instance,'client',None))
        if client and not client.active:raise serializers.ValidationError('El cliente está inactivo.')
        p=data.get('prescription',getattr(self.instance,'prescription',None))
        if p and p.client_id!=client.pk: raise serializers.ValidationError('La receta pertenece a otro cliente.')
        if data.get('amount',getattr(self.instance,'amount',0))<0: raise serializers.ValidationError('Monto negativo.')
        if self.instance and self.instance.lines.exists() and 'amount' in data:
            expected=sum(line.quantity*line.unit_price for line in self.instance.lines.all())
            if data['amount']!=expected:raise serializers.ValidationError('El monto debe coincidir con el detalle de productos.')
        category=data.get('category',getattr(self.instance,'category',None))
        if category=='convenio' and not data.get('agreement',getattr(self.instance,'agreement',None)):
            raise serializers.ValidationError('Seleccione convenio.')
        if category=='particular': data['agreement']=None
        chars=data.get('characteristics',getattr(self.instance,'characteristics',{}))
        if not isinstance(chars,dict) or len(str(chars))>4000: raise serializers.ValidationError('Características inválidas.')
        product_type=data.get('product_type',getattr(self.instance,'product_type',None))
        required=['frame','crystal','focus'] if product_type=='particular' else ['security_model','security_color','focus']
        if any(not isinstance(chars.get(k),str) or not chars[k].strip() or len(chars[k])>180 for k in required):
            raise serializers.ValidationError('Complete las características del producto: '+', '.join(required))
        return data


class OrderSerializer(serializers.ModelSerializer):
    folio=serializers.CharField(read_only=True)
    client_name=serializers.CharField(source='client.name',read_only=True)
    class Meta:
        model=Order
        fields=['id','folio','client','client_name','prescription','quote','product_type','characteristics','status','created_at','updated_at']
        read_only_fields=fields


class WarrantySerializer(serializers.ModelSerializer):
    folio=serializers.CharField(read_only=True)
    class Meta:
        model=Warranty
        fields=['id','folio','order','kind','reason','description','status','justification','damaged_frame_destination','created_at','updated_at']
        read_only_fields=['created_at','updated_at']
    def validate(self,data):
        status=data.get('status',getattr(self.instance,'status',None))
        if status in ('Aprobada','Rechazada') and not data.get('justification',getattr(self.instance,'justification','')).strip():
            raise serializers.ValidationError('Registre la resolución de la revisión.')
        if self.instance and 'order' in data and data['order']!=self.instance.order:
            raise serializers.ValidationError('No se puede reasignar una garantía.')
        return data


class InquirySerializer(serializers.ModelSerializer):
    class Meta:
        model=Inquiry
        fields=['id','token','idempotency_key','kind','name','phone','email','service','reason','contact_authorized','day','slot','status','created_at']
        read_only_fields=['token','status','created_at']
        extra_kwargs={'idempotency_key':{'validators':[]}}
    def validate(self,data):
        if data['kind']=='agenda':
            if not data.get('day') or not data.get('slot'): raise serializers.ValidationError('Seleccione fecha y horario.')
            if data['day']<timezone.localdate(): raise serializers.ValidationError('La fecha no puede ser pasada.')
            if data['slot'].strftime('%H:%M') not in ('09:00','10:00','11:00','15:00','16:00'):
                raise serializers.ValidationError('Horario fuera de la agenda académica.')
        else: data.update(day=None,slot=None)
        if len(data['name'].strip())<3 or len(data['reason'].strip())<5:
            raise serializers.ValidationError('Complete nombre y motivo de la consulta.')
        import re
        if not re.fullmatch(r'[+0-9 ()-]{8,30}',data['phone']): raise serializers.ValidationError('Teléfono inválido.')
        if not data.get('contact_authorized'): raise serializers.ValidationError('Debe autorizar el contacto para gestionar esta solicitud.')
        return data


class ReceiptSerializer(serializers.ModelSerializer):
    order_folio=serializers.CharField(source='order.folio',read_only=True)
    client_name=serializers.CharField(source='order.client.name',read_only=True)
    class Meta:
        model=Receipt
        fields=['id','order','order_folio','client_name','method','terms','observations','sha256','created_at']


class AuditSerializer(serializers.ModelSerializer):
    class Meta:
        model=Audit
        fields=['id','actor','action','model','record_id','at']


class InventorySerializer(serializers.ModelSerializer):
    class Meta:
        model=Inventory
        fields=['id','name','category','quantity','notes']


class AgreementSerializer(serializers.ModelSerializer):
    class Meta:
        model=Agreement
        fields=['id','name','active']
