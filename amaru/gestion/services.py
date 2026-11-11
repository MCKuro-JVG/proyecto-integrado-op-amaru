from io import BytesIO
from pathlib import Path
import base64
import hashlib
import uuid
import logging
from PIL import Image,ImageChops
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
from django.db import transaction
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Image as PDFImage
from xml.sax.saxutils import escape
from .models import *
def audit(user,action,obj):
    Audit.objects.create(actor=user if user and user.is_authenticated else None,action=action[:200],model=obj._meta.model_name,record_id=obj.pk)
def record_consent(client,user):
    client.consent_at=timezone.now();client.save()
    Consent.objects.create(client=client,authorized=client.consent,actor=user if user and user.is_authenticated else None)
    audit(user,'Consentimiento autorizado' if client.consent else 'Consentimiento no autorizado',client)
@transaction.atomic
def convert_quote(quote_id,user,inventory_id=None):
    q=Quote.objects.select_for_update().get(pk=quote_id)
    if Order.objects.filter(quote=q).exists(): return Order.objects.get(quote=q)
    if not q.approved: raise ValidationError('La cotización debe estar aprobada por el cliente.')
    if not q.prescription or not q.prescription.valid or q.prescription.client_id!=q.client_id: raise ValidationError('Adjunte una receta vigente del cliente antes de generar la OT.')
    item=None
    if inventory_id:
        item=Inventory.objects.select_for_update().get(pk=inventory_id)
        if item.quantity<1: raise ValidationError('No hay stock disponible.')
        item.quantity-=1;item.save();audit(user,'Salida de 1 unidad por OT',item)
    o=Order.objects.create(quote=q,client=q.client,prescription=q.prescription,category=q.category,agreement=q.agreement,product_type=q.product_type,characteristics=q.characteristics,notes=q.notes,actor=user,inventory=item)
    if q.request:
        q.request.status='Derivada a Orden de Trabajo';q.request.save();audit(user,'Derivación a OT',q.request)
    audit(user,'Creación de OT · Registrada',o)
    return o
def accept_receipt(order_id,user,accepted,signature,terms=None,expected_updated=None,observations='',pickup_proof=''):
    existing=Receipt.objects.filter(order_id=order_id).first()
    if existing:
        from .pickup import requires_pickup
        if pickup_proof or requires_pickup(existing.order):
            raise ValidationError('La entrega ya está completada.')
        return existing
    key=uuid.uuid4()
    attempt=DeliveryAttempt.objects.create(key=key,order_id=order_id,
        pdf_key=f'comprobantes/{key.hex}.pdf',signature_key=f'firmas/{key.hex}.png' if signature else '')
    try:
        receipt=_accept_receipt_atomic(order_id,user,accepted,signature,attempt,terms,expected_updated,observations,pickup_proof)
    except Exception:
        cleaned=True
        for field,name in [('pdf',attempt.pdf_key),('signature',attempt.signature_key)]:
            if not name:continue
            storage=Receipt._meta.get_field(field).storage
            try:
                if not Receipt.objects.filter(**{field:name}).exists():storage.delete(name)
            except Exception:
                cleaned=False;logging.getLogger(__name__).exception('Compensación pendiente: %s',attempt.key)
        DeliveryAttempt.objects.filter(pk=key).update(state='failed' if cleaned else 'cleanup_pending')
        raise
    try:DeliveryAttempt.objects.filter(pk=key).update(state='complete')
    except Exception:logging.getLogger(__name__).exception('Entrega confirmada; diario pendiente de reconciliación: %s',key)
    return receipt


@transaction.atomic
def _accept_receipt_atomic(order_id,user,accepted,signature,attempt,terms,expected_updated,observations,pickup_proof):
    order=Order.objects.select_for_update().get(pk=order_id)
    from .pickup import consume_locked, requires_pickup
    if Receipt.objects.filter(order=order).exists():
        if pickup_proof or requires_pickup(order):
            raise ValidationError('La entrega ya está completada.')
        return Receipt.objects.get(order=order)
    if expected_updated and order.updated_at.isoformat()!=expected_updated: raise ValidationError('El pedido cambió. Revise nuevamente el documento.')
    if order.status!='Disponible para retiro': raise ValidationError('La OT debe estar disponible para retiro.')
    if not accepted and not signature: raise ValidationError('Dibuje su firma o marque Recibí Conforme.')
    content=None
    if signature:
        try:
            prefix,data=signature.split(',',1)
            if prefix!='data:image/png;base64' or len(data)>300000: raise ValueError()
            raw=base64.b64decode(data,validate=True)
            image=Image.open(BytesIO(raw)); image.verify()
            if image.format!='PNG': raise ValueError()
            image=Image.open(BytesIO(raw))
            if image.width>2048 or image.height>2048:raise ValueError()
            white=Image.new('RGBA',image.size,'white');white.alpha_composite(image.convert('RGBA'))
            bounds=ImageChops.difference(white.convert('RGB'),Image.new('RGB',image.size,'white')).getbbox()
            if not bounds or bounds[2]-bounds[0]<8 or bounds[3]-bounds[1]<3:raise ValueError()
            content=raw
        except Exception: raise ValidationError('La firma no es una imagen PNG válida.')
    consume_locked(order, user, pickup_proof)
    config=SiteConfiguration.objects.first() or SiteConfiguration.objects.create()
    receipt=Receipt.objects.create(order=order,method='Firma en pantalla' if content else 'Recibí Conforme',terms=terms if terms is not None else config.warranty_terms,observations=str(observations)[:2000],actor=user)
    if content:
        receipt.signature.save(Path(attempt.signature_key).name,ContentFile(content))
        if receipt.signature.name!=attempt.signature_key:raise ValidationError('Colisión de archivo; reintente la entrega.')
    buffer=BytesIO();styles=getSampleStyleSheet()
    logo = settings.BASE_DIR.parent / 'frontend_amaru' / 'img' / 'logo-amaru-oficial.jpg'
    title = PDFImage(str(logo), width=142, height=142*488/948) if logo.is_file() else Paragraph('Ópticas Amaru', styles['Title'])
    story = [title, Paragraph('Comprobante de recepción conforme', styles['Heading2']), Spacer(1, 18)]
    lines=[f'Orden: {order.folio}',f'Cliente: {order.client.name}',f'RUT: {order.client.rut}',f'Producto: {order.get_product_type_display()}',* [f'{k}: {v}' for k,v in order.characteristics_display],f'Fecha: {timezone.localtime(receipt.created_at).strftime("%d/%m/%Y %H:%M:%S")}',f'Método de aceptación: {receipt.method}']
    for line in lines: story += [Paragraph(escape(line),styles['BodyText']),Spacer(1,8)]
    story += [Paragraph('Condiciones de garantía aceptadas',styles['Heading2']),Paragraph(escape(receipt.terms).replace('\n','<br/>'),styles['BodyText'])]
    story += [Spacer(1,10),Paragraph('Observaciones: '+escape(receipt.observations),styles['BodyText']),Spacer(1,10),Paragraph('Firma electrónica simple. No corresponde a firma electrónica avanzada.',styles['BodyText'])]
    if content: story += [Spacer(1,14),PDFImage(BytesIO(content),width=240,height=100)]
    SimpleDocTemplate(buffer,pagesize=A4,rightMargin=45,leftMargin=45,topMargin=45,bottomMargin=45).build(story)
    receipt.pdf.save(Path(attempt.pdf_key).name,ContentFile(buffer.getvalue()))
    if receipt.pdf.name!=attempt.pdf_key:raise ValidationError('Colisión de archivo; reintente la entrega.')
    receipt.sha256=hashlib.sha256(buffer.getvalue()).hexdigest();receipt.save()
    order.status='Entregada';order.save();audit(user,'Recepción conforme · Entregada',order);audit(user,'Comprobante generado',receipt)
    return receipt


@transaction.atomic
def receive_inquiry(data,actor):
    """Entrada pública: no cambia fichas existentes ni crea cuentas de usuario."""
    from datetime import timedelta
    from rest_framework.exceptions import APIException
    class Conflict(APIException):
        status_code=409
    previous=Inquiry.objects.filter(idempotency_key=data['idempotency_key']).first()
    if previous:
        for key,value in data.items():
            if getattr(previous,key)!=value:
                raise Conflict('La referencia de envío ya fue utilizada con otros datos. Recargue el formulario.')
        return previous,False
    if data['kind'] == 'agenda':
        from .agenda import AgendaConflict, is_open, lock_agenda
        if not is_open(lock_agenda(), data['day'], data['slot']):
            raise AgendaConflict()
    fields={key:data.get(key,'') for key in ('kind','name','phone','email','service','reason','registration_rut')}
    fields.update(day=data.get('day'),slot=data.get('slot'),agreement=data.get('agreement'))
    if Inquiry.objects.filter(**fields,created_at__gte=timezone.now()-timedelta(minutes=5)).exclude(status__in=['Cerrada','Cancelada']).exists():
        raise Conflict('Ya se recibió una solicitud equivalente recientemente. Espere antes de repetirla.')
    defaults = dict(data)
    if data.get("agreement"):
        agreement = Agreement.objects.select_for_update().get(pk=data["agreement"].pk)
        if agreement.has_managed_union or not agreement.available or (data.get("agreement_role") == "carga" and not agreement.allow_dependents):
            raise Conflict("El convenio ya no está disponible para este registro.")
        defaults["verification_state"] = "pendiente"
    obj,created=Inquiry.objects.get_or_create(idempotency_key=data['idempotency_key'],defaults=defaults)
    if not created:
        if any(getattr(obj,key)!=value for key,value in data.items()):
            raise Conflict('La referencia de envío ya fue utilizada con otros datos. Recargue el formulario.')
        return obj,False
    if obj.kind=='registro':
        client,new=Client.objects.get_or_create(rut=obj.registration_rut,defaults={
            'name':obj.name,'phone':obj.phone,'email':obj.email,'category':'particular','consent':False,'active':False})
        obj.client=client;obj.save(update_fields=['client'])
        if new: audit(actor,'Ficha pública pendiente de revisión; sin cuenta autenticada',client)
    if obj.kind=='agenda': AppointmentReservation.objects.create(inquiry=obj,day=obj.day,slot=obj.slot)
    audit(actor,'Solicitud pública recibida: '+obj.source,obj)
    return obj,True
