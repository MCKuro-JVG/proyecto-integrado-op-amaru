from functools import wraps
from io import BytesIO
from django.shortcuts import render,redirect,get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied,ValidationError
from django.db import transaction,IntegrityError
from django.db.models import Q
from django.http import FileResponse,HttpResponse
from django.conf import settings
from django.core.cache import cache
from django.views.decorators.http import require_POST
import qrcode
from .models import *
from .forms import *
from .services import audit,record_consent,convert_quote,accept_receipt
MODULES={'clientes':(Client,ClientForm,'Clientes'),'recetas':(Prescription,PrescriptionForm,'Recetas'),'solicitudes':(Request,RemoteForm,'Solicitudes remotas'),'cotizaciones':(Quote,ProductForm,'Cotizaciones'),'ordenes':(Order,None,'Órdenes de Trabajo'),'garantias':(Warranty,WarrantyForm,'Garantías y reparaciones'),'inventario':(Inventory,InventoryForm,'Inventario'),'recepciones':(Receipt,None,'Recepciones'),'auditoria':(Audit,None,'Bitácora de operaciones')}
def allowed(permission):
    def decorator(fn):
        @login_required
        @wraps(fn)
        def wrapped(request,*args,**kwargs):
            if not request.user.has_perm(permission): raise PermissionDenied
            return fn(request,*args,**kwargs)
        return wrapped
    return decorator
def own(request,client):
    if not request.user.has_perm('gestion.view_client') and client.user_id!=request.user.pk: raise PermissionDenied
def throttle(request,key,limit):
    cachekey=f'{key}:{request.META.get("REMOTE_ADDR","")}'
    count=cache.get(cachekey,0)
    if count>=limit: return True
    cache.set(cachekey,count+1,300)
    return False
@login_required
def dashboard(request):
    if request.user.has_perm('gestion.view_client'):
        today=timezone.localdate()
        prescriptions=list(Prescription.objects.all())
        stats=[('Órdenes pendientes',Order.objects.filter(status='Registrada').count()),('En fabricación',Order.objects.filter(status='En fabricación').count()),('Listas para retiro',Order.objects.filter(status='Disponible para retiro').count()),('Garantías en revisión',Warranty.objects.filter(status='En revisión taller').count()),('Recetas vencidas',sum(not p.valid for p in prescriptions)),('Vencen en 30 días',sum(today<=p.expires_on<=today+timezone.timedelta(days=30) for p in prescriptions))]
        return render(request,'dashboard.html',{'stats':stats,'orders':Order.objects.select_related('client').order_by('-created_at')[:5]})
    client=Client.objects.filter(user=request.user).first()
    return render(request,'portal.html',{'client':client,'requests':Request.objects.filter(client=client),'orders':Order.objects.filter(client=client),'quotes':Quote.objects.filter(client=client),'warranties':Warranty.objects.filter(order__client=client)})
@login_required
def listing(request,module):
    if module not in MODULES: raise PermissionDenied
    model,form,title=MODULES[module]
    if not request.user.has_perm(f'gestion.view_{model._meta.model_name}'): raise PermissionDenied
    qs=model.objects.all().order_by('-pk')
    q=request.GET.get('q','').strip()
    if q:
        normalized=q.replace('.','').upper()
        if model==Client: qs=qs.filter(Q(rut__icontains=normalized)|Q(name__icontains=q))
        elif model==Inventory: qs=qs.filter(Q(name__icontains=q)|Q(category__icontains=q))
        elif model in (Prescription,Quote,Order,Request): qs=qs.filter(Q(client__rut__icontains=normalized)|Q(client__name__icontains=q)) if not normalized.startswith(('OT-','COT-','SOL-')) else qs.filter(pk=int(normalized.split('-')[1])) if normalized.split('-')[1].isdigit() else qs.none()
        elif model in (Warranty,Receipt): qs=qs.filter(Q(order__client__rut__icontains=normalized)|Q(order__client__name__icontains=q))
    if model==Inventory and request.GET.get('available'): qs=qs.filter(quantity__gt=0)
    return render(request,'list.html',{'module':module,'title':title,'items':qs[:200],'can_create':form and module!='solicitudes' and request.user.has_perm(f'gestion.add_{model._meta.model_name}')})
@login_required
def create(request,module):
    if module not in MODULES: raise PermissionDenied
    model,klass,title=MODULES[module]
    if not klass or module=='solicitudes' or not request.user.has_perm(f'gestion.add_{model._meta.model_name}'): raise PermissionDenied
    initial={}
    if request.GET.get('client'): initial['client']=request.GET['client']
    if module=='clientes' and request.method=='POST':
        try: existing=Client.objects.filter(rut=normalize_rut(request.POST.get('rut',''))).first()
        except ValidationError: existing=None
        if existing:
            messages.info(request,'El RUT ya existe. Se abrió su ficha sin crear un duplicado.');return redirect('detail',module='clientes',pk=existing.pk)
    form=klass(request.POST or None,request.FILES or None,initial=initial)
    if module=='cotizaciones' and initial:
        form.fields['prescription'].queryset=Prescription.objects.filter(client_id=initial['client'])
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            obj=form.save(commit=False)
            if hasattr(obj,'actor'):obj.actor=request.user
            if model==Quote:obj.characteristics=form.characteristics()
            obj.save()
            if model==Client:record_consent(obj,request.user)
            audit(request.user,'Registro creado',obj)
        messages.success(request,'Registro guardado correctamente.')
        return redirect('detail',module=module,pk=obj.pk)
    return render(request,'form.html',{'title':f'Nuevo registro · {title}','form':form})
@login_required
def detail(request,module,pk):
    if module not in MODULES:raise PermissionDenied
    model,klass,title=MODULES[module];obj=get_object_or_404(model,pk=pk)
    if not request.user.has_perm(f'gestion.view_{model._meta.model_name}'):
        if model not in (Client,Prescription,Quote,Order,Request,Warranty,Receipt):raise PermissionDenied
        own(request,obj if model==Client else obj.order.client if model==Receipt else obj.client)
    context={'obj':obj,'module':module,'title':title,'history':Audit.objects.filter(model=model._meta.model_name,record_id=pk)}
    if model==Client:
        context.update(recipes=obj.prescriptions.all(),quotes=Quote.objects.filter(client=obj),orders=Order.objects.filter(client=obj),warranties=Warranty.objects.filter(order__client=obj),receipts=Receipt.objects.filter(order__client=obj),requests=Request.objects.filter(client=obj))
    if model==Quote:context['inventory']=Inventory.objects.filter(quantity__gt=0)
    if model==Order:context['receipt']=Receipt.objects.filter(order=obj).first()
    if model==Request:context['quote']=Quote.objects.filter(request=obj).first()
    return render(request,'detail.html',context)
@allowed('gestion.change_client')
def edit_client(request,pk):
    obj=get_object_or_404(Client,pk=pk)
    form=ClientForm(request.POST or None,instance=obj)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():form.save();record_consent(obj,request.user);audit(request.user,'Ficha actualizada',obj)
        return redirect('detail',module='clientes',pk=pk)
    return render(request,'form.html',{'title':'Actualizar ficha y consentimiento','form':form})
@allowed('gestion.change_quote')
def edit_quote(request,pk):
    q=get_object_or_404(Quote,pk=pk)
    if Order.objects.filter(quote=q).exists():raise PermissionDenied
    form=ProductForm(request.POST or None,instance=q,initial=q.characteristics)
    if request.method=='POST' and form.is_valid():
        q=form.save(commit=False);q.characteristics=form.characteristics();q.save();audit(request.user,'Cotización actualizada',q)
        return redirect('detail',module='cotizaciones',pk=pk)
    return render(request,'form.html',{'title':'Editar / aprobar cotización','form':form})
@require_POST
@allowed('gestion.add_order')
def convert(request,pk):
    try:
        o=convert_quote(pk,request.user,request.POST.get('inventory') or None)
        messages.success(request,'Orden de Trabajo creada.');return redirect('detail',module='ordenes',pk=o.pk)
    except (ValidationError,Inventory.DoesNotExist) as e:messages.error(request,' '.join(e.messages) if isinstance(e,ValidationError) else 'Seleccione un insumo válido.')
    return redirect('detail',module='cotizaciones',pk=pk)
@allowed('gestion.add_quote')
def request_quote(request,pk):
    source=get_object_or_404(Request,pk=pk)
    existing=Quote.objects.filter(request=source).first()
    if existing:return redirect('detail',module='cotizaciones',pk=existing.pk)
    initial={k:getattr(source,k) for k in ['client','prescription','category','agreement','product_type','notes']};initial.update(source.characteristics)
    form=ProductForm(request.POST or None,initial=initial)
    if request.method=='POST' and form.is_valid():
        if form.cleaned_data['client']!=source.client:form.add_error('client','Debe conservar el cliente de la solicitud.')
        else:
            with transaction.atomic():
                q=form.save(commit=False);q.actor=request.user;q.request=source;q.characteristics=form.characteristics();q.save()
                source.status='Cotizada';source.save();audit(request.user,'Cotización desde solicitud',q);audit(request.user,'Solicitud cotizada',source)
            return redirect('detail',module='cotizaciones',pk=q.pk)
    return render(request,'form.html',{'title':'Cotizar solicitud remota','form':form})
@login_required
def state(request,module,pk):
    model=Order if module=='ordenes' else Warranty if module=='garantias' else None
    if not model or not request.user.has_perm(f'gestion.change_{model._meta.model_name}'):raise PermissionDenied
    obj=get_object_or_404(model,pk=pk)
    choices=model.STATES
    if model==Order:choices=[x for x in choices if x[0]!='Entregada']
    form=StateForm(request.POST or None,choices=choices,initial={'status':obj.status})
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            obj=model.objects.select_for_update().get(pk=pk);before=obj.status
            if model==Order and obj.status=='Entregada':form.add_error('status','Una OT entregada conserva su estado de recepción.')
            else:
                obj.status=form.cleaned_data['status']
                if model==Warranty:obj.justification=form.cleaned_data['justification']
                obj.save();audit(request.user,f'{before} → {obj.status} · {form.cleaned_data["justification"]}',obj)
                return redirect('detail',module=module,pk=pk)
    return render(request,'form.html',{'title':f'Actualizar estado · {obj.folio}','form':form})
def remote(request):
    form=RemoteForm(request.POST or None,request.FILES or None)
    if request.method=='POST' and throttle(request,'remote',20):return HttpResponse('Demasiadas solicitudes. Intente en cinco minutos.',status=429)
    if request.method=='POST' and form.is_valid():
        d=form.cleaned_data
        with transaction.atomic():
            # El formulario público no revela ni modifica la ficha de un RUT existente.
            client,created=Client.objects.get_or_create(rut=d['rut'],defaults={k:d[k] for k in ['name','phone','email','category','agreement','consent']})
            if created:record_consent(client,request.user)
            elif request.user.is_authenticated and client.user_id==request.user.pk:
                for key in ['name','phone','email','category','agreement','consent']:setattr(client,key,d[key])
                record_consent(client,request.user)
            elif not d['consent']:
                # Una negativa desactiva siempre las comunicaciones; una nueva autorización
                # pública para un RUT existente se verifica durante la atención.
                client.consent=False;record_consent(client,request.user)
            p=None
            if d.get('file'):
                p=Prescription.objects.create(client=client,issued_on=d['issued_on'],file=d['file'],actor=request.user if request.user.is_authenticated else None)
                audit(request.user,'Carga remota de receta',p)
            obj=Request.objects.create(client=client,prescription=p,category=d['category'],agreement=d['agreement'],product_type=d['product_type'],characteristics=form.characteristics(),notes=d['notes'],exam_requested=d['exam_requested'],submitted_contact={k:d[k] for k in ['name','phone','email']},submitted_consent=d['consent'],actor=request.user if request.user.is_authenticated else None)
            # Se conserva la decisión del envío sin alterar autorización previa desde un enlace público.
            Consent.objects.create(client=client,authorized=d['consent'],actor=request.user if request.user.is_authenticated else None)
            audit(request.user,'Solicitud remota recibida',obj)
            if p and not p.valid:obj.exam_requested=True;obj.save()
        request.session['last_request']=obj.pk
        return redirect('remote_success')
    return render(request,'form.html',{'title':'Solicita tus lentes','subtitle':'Completa tu atención desde tu teléfono. Conserva el folio al finalizar.','form':form,'remote':True})
def remote_success(request):
    obj=get_object_or_404(Request,pk=request.session.get('last_request'))
    return render(request,'success.html',{'obj':obj})
def lookup(request):
    form=LookupForm(request.POST or None);found=None
    if request.method=='POST' and throttle(request,'lookup',30):return HttpResponse('Demasiados intentos. Intente en cinco minutos.',status=429)
    if request.method=='POST' and form.is_valid():
        for model in (Order,Request,Warranty):
            folio=form.cleaned_data['folio'].upper();parts=folio.split('-')
            if len(parts)!=3 or not parts[1].isdigit():continue
            obj=model.objects.filter(pk=int(parts[1])).first()
            if obj and obj.folio==folio and obj.client.rut==form.cleaned_data['rut']:found=obj;break
        if not found:form.add_error(None,'No se encontró una solicitud con esos datos.')
    steps=[x[0] for x in Order.STATES]
    return render(request,'lookup.html',{'form':form,'found':found,'steps':steps,'step_index':steps.index(found.status) if found and found.status in steps else -1})
@login_required
def receipt(request,pk):
    order=get_object_or_404(Order,pk=pk);own(request,order.client)
    if request.user.has_perm('gestion.view_client') and not request.user.has_perm('gestion.add_receipt'):raise PermissionDenied
    existing=Receipt.objects.filter(order=order).first()
    if existing:return redirect('detail',module='recepciones',pk=existing.pk)
    terms=(SiteConfiguration.objects.first() or SiteConfiguration.objects.create()).warranty_terms
    if request.method=='POST':
        try:
            rec=accept_receipt(pk,request.user,request.POST.get('accepted')=='on',request.POST.get('signature',''))
            return redirect('detail',module='recepciones',pk=rec.pk)
        except ValidationError as e:messages.error(request,' '.join(e.messages))
    return render(request,'receipt.html',{'obj':order,'terms':terms})
@login_required
def file_view(request,kind,pk):
    if kind not in ('receta','pdf','firma'):raise PermissionDenied
    if kind=='receta':obj=get_object_or_404(Prescription,pk=pk);own(request,obj.client);file=obj.file
    else:
        obj=get_object_or_404(Receipt,pk=pk);own(request,obj.order.client);file=obj.pdf if kind=='pdf' else obj.signature
    if not file:raise PermissionDenied
    audit(request.user,'Acceso a documento privado',obj)
    response=FileResponse(file.open('rb'),as_attachment=kind=='pdf',filename=file.name.split('/')[-1]);response['Cache-Control']='private, no-store'
    return response
@allowed('gestion.view_request')
def qr(request):
    buffer=BytesIO();qrcode.make(settings.PUBLIC_BASE_URL+'/solicitar/').save(buffer,format='PNG');buffer.seek(0)
    return FileResponse(buffer,content_type='image/png')
@login_required
def exam(request,pk):
    client=get_object_or_404(Client,pk=pk);own(request,client)
    if request.method=='POST':
        obj=Request.objects.create(client=client,product_type='particular',category=client.category,agreement=client.agreement,exam_requested=True,notes='Solicitud de nueva receta / examen',actor=request.user)
        audit(request.user,'Solicitud de examen',obj);return redirect('detail',module='solicitudes',pk=obj.pk)
    return render(request,'confirm.html',{'title':'Solicitar nueva receta / examen','text':f'Confirmar solicitud para {client.name}.'})
