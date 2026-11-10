import uuid, calendar
from pathlib import Path
from django.db import models
from django.conf import settings
from django.utils import timezone
from .validators import validate_rut,validate_document,normalize_rut
from .storage import private_storage, public_storage
def document_path(instance,filename):
    return f'recetas/{instance.client_id}/{uuid.uuid4().hex}{Path(filename).suffix.lower()}'
class Agreement(models.Model):
    name = models.CharField('empresa / sindicato', max_length=180, unique=True)
    active = models.BooleanField('activo', default=True)
    code = models.CharField(max_length=24, unique=True, null=True, blank=True, editable=False)
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    contact_name = models.CharField(max_length=180, blank=True)
    contact_email = models.EmailField(blank=True)
    allow_dependents = models.BooleanField(default=False)

    @property
    def available(self):
        today = timezone.localdate()
        return self.active and (not self.starts_on or self.starts_on <= today) and (not self.ends_on or self.ends_on >= today)

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = uuid.uuid4().hex[:16]
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {"code"}
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Client(models.Model):
    CATEGORY=[('particular','Particular'),('convenio','Convenio Empresa/Sindicato')]
    rut=models.CharField('RUT',max_length=12,unique=True,validators=[validate_rut])
    name=models.CharField('nombre completo',max_length=180)
    phone=models.CharField('teléfono',max_length=30)
    email=models.EmailField('correo electrónico',blank=True)
    category=models.CharField('tipo de cliente',max_length=20,choices=CATEGORY)
    agreement=models.ForeignKey(Agreement,on_delete=models.PROTECT,null=True,blank=True,verbose_name='empresa / sindicato')
    consent=models.BooleanField('Autorizo el uso de mi teléfono y correo para posventa y promociones',default=False)
    consent_at=models.DateTimeField(default=timezone.now)
    created_at=models.DateTimeField(auto_now_add=True)
    user=models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,blank=True)
    active=models.BooleanField(default=True)
    updated_at=models.DateTimeField(auto_now=True)
    def save(self,*args,**kwargs):
        self.rut=normalize_rut(self.rut)
        super().save(*args,**kwargs)
    def __str__(self): return f'{self.name} · {self.rut}'
class Consent(models.Model):
    client=models.ForeignKey(Client,on_delete=models.PROTECT,related_name='consents')
    authorized=models.BooleanField()
    at=models.DateTimeField(auto_now_add=True)
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True)
class Prescription(models.Model):
    client=models.ForeignKey(Client,on_delete=models.PROTECT,related_name='prescriptions',verbose_name='cliente')
    issued_on=models.DateField('fecha de emisión')
    file=models.FileField('receta JPG / PNG / PDF (máximo 10 MB)',upload_to=document_path,storage=private_storage,validators=[validate_document])
    updated_at=models.DateTimeField(auto_now=True)
    created_at=models.DateTimeField(auto_now_add=True)
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True)
    physical_reference=models.CharField('referencia de archivo físico (si corresponde)',max_length=180,blank=True)
    @property
    def expires_on(self):
        validity_days = getattr(settings, "PRESCRIPTION_VALIDITY_DAYS", None)
        if validity_days is not None:
            from datetime import timedelta
            return self.issued_on + timedelta(days=validity_days)
        d=self.issued_on
        return d.replace(year=d.year+1,day=min(d.day,calendar.monthrange(d.year+1,d.month)[1]))
    @property
    def valid(self): return timezone.localdate()<=self.expires_on
    @property
    def status(self): return 'Vigente' if self.valid else 'Vencida'
    def __str__(self): return f'Receta #{self.pk} · {self.client.rut} · {self.status}'
class Inventory(models.Model):
    CATEGORY=[('seguridad','Armazones de seguridad'),('armazon','Armazones particulares'),('cristal','Cristales'),('repuesto','Repuestos')]
    name=models.CharField('modelo / descripción',max_length=180)
    category=models.CharField('categoría',max_length=20,choices=CATEGORY)
    quantity=models.PositiveIntegerField('stock disponible',default=0)
    notes=models.TextField('observaciones',blank=True)
    def __str__(self): return f'{self.name} · stock {self.quantity}'
class ProductBase(models.Model):
    TYPES=[('seguridad','Lente de seguridad'),('particular','Lente particular')]
    client=models.ForeignKey(Client,on_delete=models.PROTECT,verbose_name='cliente')
    prescription=models.ForeignKey(Prescription,on_delete=models.PROTECT,null=True,blank=True,verbose_name='receta')
    product_type=models.CharField('tipo de lente',max_length=20,choices=TYPES)
    category=models.CharField('tipo de atención',max_length=20,choices=Client.CATEGORY)
    agreement=models.ForeignKey(Agreement,on_delete=models.PROTECT,null=True,blank=True,verbose_name='empresa / sindicato')
    characteristics=models.JSONField(default=dict)
    notes=models.TextField('observaciones',blank=True)
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    token=models.UUIDField(default=uuid.uuid4,unique=True,editable=False)
    class Meta: abstract=True
    @property
    def folio(self): return f'{self.PREFIX}-{self.pk:06d}-{self.token.hex[:12].upper()}'
    def __str__(self): return self.folio
    @property
    def characteristics_display(self):
        labels={'security_model':'Modelo de seguridad','security_color':'Color de lente','focus':'Tipo de cristal','frame':'Armazón','crystal':'Cristal','antireflective':'Antirreflejo','antiscratch':'Antirrayas'}
        values={'blanco':'Blanco','fotocromatico':'Fotocromático','monofocal':'Monofocal','multifocal':'Multifocal'}
        return [(labels.get(k,k),('Sí' if v else 'No') if isinstance(v,bool) else values.get(v,v)) for k,v in self.characteristics.items()]
class Request(ProductBase):
    PREFIX='SOL'
    status=models.CharField(max_length=50,default='Recibida')
    exam_requested=models.BooleanField('Solicitar nueva receta / examen',default=False)
    submitted_contact=models.JSONField(default=dict)
    submitted_consent=models.BooleanField(default=False)
class Quote(ProductBase):
    PREFIX='COT'
    amount=models.DecimalField('total CLP',max_digits=12,decimal_places=0)
    approved=models.BooleanField('Cotización aprobada por el cliente',default=False)
    request=models.OneToOneField(Request,on_delete=models.PROTECT,null=True,blank=True)
    class Meta:
        constraints=[models.CheckConstraint(condition=models.Q(amount__gte=0),name='quote_amount_nonnegative')]
class Order(ProductBase):
    PREFIX='OT'
    STATES=[(s,s) for s in ['Registrada','En fabricación','Control de calidad','Disponible para retiro','Entregada']]
    quote=models.OneToOneField(Quote,on_delete=models.PROTECT)
    status=models.CharField('estado',max_length=50,choices=STATES,default='Registrada')
    inventory=models.ForeignKey(Inventory,on_delete=models.PROTECT,null=True,blank=True)
    class Meta:
        indexes=[models.Index(fields=['status','created_at'],name='order_status_date')]
        constraints=[models.CheckConstraint(condition=models.Q(status__in=['Registrada','En fabricación','Control de calidad','Disponible para retiro','Entregada']),name='order_valid_state')]
class Warranty(models.Model):
    TYPES=[(s,s) for s in ['Garantía','Reparación','Cambio de armazón']]
    STATES=[(s,s) for s in ['En revisión taller','Aprobada','Rechazada','Lista para entrega']]
    order=models.ForeignKey(Order,on_delete=models.PROTECT,verbose_name='Orden de Trabajo')
    kind=models.CharField('tipo de solicitud',max_length=30,choices=TYPES)
    reason=models.CharField('motivo',max_length=200)
    description=models.TextField('descripción de la falla')
    status=models.CharField('estado',max_length=50,choices=STATES,default='En revisión taller')
    justification=models.TextField('justificación del rechazo',blank=True)
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True)
    created_at=models.DateTimeField(auto_now_add=True)
    token=models.UUIDField(default=uuid.uuid4,unique=True,editable=False)
    updated_at=models.DateTimeField(auto_now=True)
    damaged_frame_destination=models.CharField(max_length=200,blank=True)
    class Meta:
        indexes=[models.Index(fields=['status','created_at'],name='warranty_status_date')]
    @property
    def client(self): return self.order.client
    @property
    def folio(self): return f'GAR-{self.pk:06d}-{self.token.hex[:12].upper()}'
    def __str__(self): return self.folio
class Receipt(models.Model):
    order=models.OneToOneField(Order,on_delete=models.PROTECT)
    method=models.CharField(max_length=30)
    signature=models.FileField(upload_to='firmas/',storage=private_storage,blank=True)
    pdf=models.FileField(upload_to='comprobantes/',storage=private_storage,blank=True)
    sha256=models.CharField(max_length=64,blank=True)
    observations=models.TextField(blank=True)
    terms=models.TextField()
    created_at=models.DateTimeField(auto_now_add=True)
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True)
    def __str__(self): return f'Recepción · {self.order.folio}'
def default_agenda_hours():
    """Horario académico inicial. Cada día usa el índice de date.weekday()."""
    return {str(day): ["09:00", "10:00", "11:00", "15:00", "16:00"] for day in range(7)}


def validate_agenda_hours(value):
    from django.core.exceptions import ValidationError
    from datetime import time

    if not isinstance(value, dict):
        raise ValidationError("Indica los días de la semana y sus horarios.")
    for day, hours in value.items():
        if day not in {str(index) for index in range(7)} or not isinstance(hours, list):
            raise ValidationError("Usa índices 0 a 6 y listas de horas HH:MM.")
        if any(not isinstance(hour, str) for hour in hours) or len(hours) != len(set(hours)):
            raise ValidationError("Usa horas de texto sin duplicados.")
        for hour in hours:
            try:
                parsed = time.fromisoformat(hour)
            except ValueError as exc:
                raise ValidationError("Usa horas HH:MM válidas.") from exc
            if parsed.strftime("%H:%M") != hour:
                raise ValidationError("Usa horas HH:MM válidas.")


class SiteConfiguration(models.Model):
    warranty_terms=models.TextField('condiciones de garantía',default='DEMO ACADÉMICO: Las condiciones comerciales, plazos y exclusiones de garantía deben ser confirmados por Ópticas Amaru. Este comprobante registra la recepción del producto. Las solicitudes de garantía se ingresan para evaluación del taller. No se establece una cobertura comercial definitiva en este prototipo.')
    agenda_hours = models.JSONField(default=default_agenda_hours, validators=[validate_agenda_hours])


class AgendaBlock(models.Model):
    day = models.DateField()
    slot = models.CharField(max_length=5, blank=True, default="")
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["day", "slot"]
        constraints = [models.UniqueConstraint(fields=["day", "slot"], name="agenda_block_unique")]


class Audit(models.Model):
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True)
    action=models.CharField(max_length=200)
    model=models.CharField(max_length=80)
    record_id=models.PositiveBigIntegerField()
    at=models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=['-at']
        indexes=[models.Index(fields=['model','record_id','at'],name='audit_record_date')]
    def __str__(self): return f'{self.at} · {self.actor or "Formulario remoto"} · {self.action} · {self.model} #{self.record_id}'


def public_image_path(instance,filename):
    return f'catalogo/{uuid.uuid4().hex}{Path(filename).suffix.lower()}'


class Product(models.Model):
    """Catálogo público. Las características clínicas siguen en cada cotización/OT."""
    sku=models.CharField(max_length=60,unique=True)
    name=models.CharField(max_length=180)
    category=models.CharField(max_length=20,choices=Inventory.CATEGORY)
    description=models.TextField(blank=True)
    crystal=models.CharField(max_length=100,blank=True)
    treatments=models.CharField(max_length=200,blank=True)
    color=models.CharField(max_length=80,blank=True)
    lens_type = models.CharField(max_length=80, blank=True)
    reference_price = models.PositiveIntegerField(null=True, blank=True)
    requires_prescription = models.BooleanField(default=False)
    image=models.ImageField(upload_to=public_image_path,storage=public_storage,blank=True,validators=[validate_document])
    active=models.BooleanField(default=True)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)


class QuoteLine(models.Model):
    quote=models.ForeignKey(Quote,on_delete=models.PROTECT,related_name='lines')
    product=models.ForeignKey(Product,on_delete=models.PROTECT)
    quantity=models.PositiveIntegerField(default=1)
    unit_price=models.DecimalField(max_digits=12,decimal_places=0)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['quote','product'],name='quote_product_once'),
            models.CheckConstraint(condition=models.Q(quantity__gt=0),name='line_positive_quantity'),
            models.CheckConstraint(condition=models.Q(unit_price__gte=0),name='line_nonnegative_price')]


class Inquiry(models.Model):
    TYPES=[('agenda','Solicitud de atención'),('contacto','Contacto'),('lentes','Orientación de lentes'),('registro','Registro de cliente')]
    STATES=[(s,s) for s in ['Nueva','En revisión','Contactada','Cerrada','Cancelada']]
    token=models.UUIDField(default=uuid.uuid4,unique=True,editable=False)
    idempotency_key=models.UUIDField(unique=True)
    source=models.CharField(max_length=10,choices=[('web','Sitio web'),('qr','Código QR')],default='web')
    registration_rut=models.CharField(max_length=12,blank=True)
    client=models.ForeignKey(Client,on_delete=models.PROTECT,null=True,blank=True,related_name='inquiries')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, null=True, blank=True)
    prescription = models.ForeignKey(Prescription, on_delete=models.PROTECT, null=True, blank=True)
    agreement = models.ForeignKey(Agreement, on_delete=models.PROTECT, null=True, blank=True)
    agreement_role = models.CharField(max_length=10, choices=[("titular", "Titular"), ("carga", "Carga familiar")], blank=True)
    verification_state = models.CharField(max_length=12, choices=[("pendiente", "Pendiente"), ("aprobada", "Aprobada"), ("rechazada", "Rechazada")], blank=True)
    verification_method = models.CharField(max_length=12, blank=True)
    verification_note = models.CharField(max_length=500, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="verified_agreements")
    kind=models.CharField(max_length=20,choices=TYPES)
    name=models.CharField(max_length=180)
    phone=models.CharField(max_length=30)
    email=models.EmailField()
    service=models.CharField(max_length=120)
    reason=models.TextField(max_length=2000)
    contact_authorized=models.BooleanField(default=False)
    day=models.DateField(null=True,blank=True)
    slot=models.TimeField(null=True,blank=True)
    status=models.CharField(max_length=20,choices=STATES,default='Nueva')
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        indexes=[models.Index(fields=['status','created_at'],name='inquiry_status_date')]


class AppointmentReservation(models.Model):
    """Una plaza de demostración por horario; UNIQUE funciona también en MariaDB."""
    inquiry=models.OneToOneField(Inquiry,on_delete=models.PROTECT)
    day=models.DateField()
    slot=models.TimeField()
    class Meta:
        constraints=[models.UniqueConstraint(fields=['day','slot'],name='appointment_slot_unique')]


class DeliveryAttempt(models.Model):
    """Diario persistente de compensación para archivos fuera de la transacción SQL."""
    key=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    order=models.ForeignKey(Order,on_delete=models.PROTECT)
    state=models.CharField(max_length=20,default='pending')
    pdf_key=models.CharField(max_length=250)
    signature_key=models.CharField(max_length=250,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
