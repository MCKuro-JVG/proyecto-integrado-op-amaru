from django import forms
from django.utils import timezone
from .models import *
from .validators import normalize_rut,validate_document
class ClientForm(forms.ModelForm):
    class Meta:
        model=Client
        fields=['rut','name','phone','email','category','agreement','consent']
    def clean_rut(self): return normalize_rut(self.cleaned_data['rut'])
    def clean(self):
        d=super().clean()
        if d.get('category')=='convenio' and not d.get('agreement'): self.add_error('agreement','Seleccione la empresa o sindicato.')
        if d.get('category')=='particular': d['agreement']=None
        return d
class PrescriptionForm(forms.ModelForm):
    class Meta:
        model=Prescription
        fields=['client','issued_on','file','physical_reference']
        widgets={'issued_on':forms.DateInput(attrs={'type':'date'})}
    def clean_issued_on(self):
        d=self.cleaned_data['issued_on']
        if d>timezone.localdate(): raise forms.ValidationError('La fecha no puede estar en el futuro.')
        return d
class ProductForm(forms.ModelForm):
    security_model=forms.ChoiceField(label='Modelo de seguridad',choices=[('DEMO Seguridad','DEMO · Modelo de seguridad'),('DEMO Full Face','DEMO · Clip Full Face')],required=False)
    security_color=forms.ChoiceField(label='Color de lente',choices=[('blanco','Blanco'),('fotocromatico','Fotocromático')],required=False)
    focus=forms.ChoiceField(label='Tipo de cristal',choices=[('monofocal','Monofocal'),('multifocal','Multifocal')])
    frame=forms.CharField(label='Armazón particular / referencia',required=False,max_length=180)
    crystal=forms.CharField(label='Cristal / especificación',required=False,max_length=180)
    antireflective=forms.BooleanField(label='Antirreflejo',required=False)
    antiscratch=forms.BooleanField(label='Antirrayas',required=False)
    class Meta:
        model=Quote
        fields=['client','prescription','category','agreement','product_type','amount','approved','notes']
    def clean(self):
        d=super().clean()
        if d.get('category')=='convenio' and not d.get('agreement'): self.add_error('agreement','Seleccione empresa / sindicato.')
        if d.get('category')=='particular': d['agreement']=None
        if d.get('prescription') and d.get('client') and d['prescription'].client_id!=d['client'].pk: self.add_error('prescription','La receta no pertenece al cliente.')
        if d.get('amount',0)<0: self.add_error('amount','El total no puede ser negativo.')
        if d.get('product_type')=='seguridad':
            for field in ['security_model','security_color']:
                if not d.get(field): self.add_error(field,'Campo obligatorio para seguridad.')
        elif d.get('product_type')=='particular':
            for field in ['frame','crystal']:
                if not d.get(field): self.add_error(field,'Campo obligatorio para lente particular.')
        return d
    def characteristics(self):
        keys=['security_model','security_color','focus'] if self.cleaned_data['product_type']=='seguridad' else ['frame','crystal','focus','antireflective','antiscratch']
        return {k:self.cleaned_data[k] for k in keys}
class RemoteForm(ProductForm):
    rut=forms.CharField(label='RUT')
    name=forms.CharField(label='Nombre completo',max_length=180)
    phone=forms.CharField(label='Teléfono',max_length=30)
    email=forms.EmailField(label='Correo electrónico',required=False)
    consent=forms.BooleanField(label='Autorizo el uso de mi teléfono y correo para posventa y promociones',required=False,help_text='Si no marca esta casilla, quedará registrado como No autorizado.')
    issued_on=forms.DateField(label='Fecha de emisión de la receta',required=False,widget=forms.DateInput(attrs={'type':'date'}))
    file=forms.FileField(label='Receta JPG / PNG / PDF (máximo 10 MB)',required=False,validators=[validate_document])
    exam_requested=forms.BooleanField(label='Solicitar nueva receta / examen',required=False)
    class Meta(ProductForm.Meta):
        model=Request
        fields=['category','agreement','product_type','notes','exam_requested']
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.order_fields(['rut','name','phone','email','category','agreement','consent','issued_on','file','exam_requested','product_type','security_model','security_color','focus','frame','crystal','antireflective','antiscratch','notes'])
        self.fields['phone'].widget.attrs.update({'inputmode':'tel','autocomplete':'tel'})
    def clean_rut(self): return normalize_rut(self.cleaned_data['rut'])
    def clean(self):
        d=super().clean()
        if d.get('file') and not d.get('issued_on'): self.add_error('issued_on','Ingrese la fecha de emisión.')
        if d.get('issued_on') and d['issued_on']>timezone.localdate(): self.add_error('issued_on','La fecha no puede estar en el futuro.')
        if not d.get('file') and not d.get('exam_requested'): self.add_error('exam_requested','Adjunte su receta o solicite nueva receta / examen.')
        return d
class WarrantyForm(forms.ModelForm):
    class Meta:
        model=Warranty
        fields=['order','kind','reason','description']
class InventoryForm(forms.ModelForm):
    class Meta:
        model=Inventory
        fields=['name','category','quantity','notes']
class StateForm(forms.Form):
    status=forms.ChoiceField(label='Nuevo estado')
    justification=forms.CharField(label='Observación / justificación',required=False,widget=forms.Textarea)
    def __init__(self,*args,choices,**kwargs):
        super().__init__(*args,**kwargs);self.fields['status'].choices=choices
    def clean(self):
        d=super().clean()
        if d.get('status')=='Rechazada' and not d.get('justification'): self.add_error('justification','La justificación es obligatoria para rechazar.')
        return d
class LookupForm(forms.Form):
    rut=forms.CharField(label='RUT')
    folio=forms.CharField(label='Folio completo de solicitud / OT / garantía',max_length=80)
    def clean_rut(self): return normalize_rut(self.cleaned_data['rut'])
