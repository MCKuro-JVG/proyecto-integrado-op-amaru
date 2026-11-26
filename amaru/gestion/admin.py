from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils.html import format_html
from django.contrib.auth.models import User,Group
from django.contrib.auth.admin import UserAdmin,GroupAdmin
from .models import *
from .services import audit,record_consent
admin.site.site_header='Administración de Ópticas Amaru'
admin.site.site_title='Ópticas Amaru'
admin.site.index_title='Gestión del sistema'
admin.site.site_url = '/app/dashboard.html'
class LoggedAdmin(admin.ModelAdmin):
    def save_model(self,request,obj,form,change):
        super().save_model(request,obj,form,change);audit(request.user,'Actualización administrativa' if change else 'Registro administrativo',obj)
    def delete_model(self,request,obj):
        audit(request.user,'Eliminación administrativa',obj);super().delete_model(request,obj)
    def delete_queryset(self,request,queryset):
        for obj in queryset:audit(request.user,'Eliminación administrativa',obj)
        super().delete_queryset(request,queryset)
class ClientAdmin(LoggedAdmin):
    list_display=['rut','name','category','consent','consent_at']
    search_fields=['rut','name','email']
    list_filter=['active','category','agreement']
    def save_model(self,request,obj,form,change):
        super().save_model(request,obj,form,change);record_consent(obj,request.user)
class AuditAdmin(admin.ModelAdmin):
    list_display=['at','actor','action','model','record_id']
    def has_add_permission(self,request):return False
    def has_change_permission(self,request,obj=None):return False
    def has_delete_permission(self,request,obj=None):return False
class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self,request):return False
    def has_change_permission(self,request,obj=None):return False
    def has_delete_permission(self,request,obj=None):return False
class PendingAccountFilter(admin.SimpleListFilter):
    title = 'activación de cliente'
    parameter_name = 'activacion'

    def lookups(self, request, model_admin):
        return [('pendiente', 'Pendiente de verificación'), ('activa', 'Activada')]

    def queryset(self, request, queryset):
        if self.value() in ('pendiente', 'activa'):
            return queryset.filter(client_registration__isnull=False,
                                   client_registration__approved_at__isnull=self.value() == 'pendiente')
        return queryset


def permission_label(permission):
    action, _, model = permission.codename.partition('_')
    verbs = {'add': 'Añadir', 'change': 'Modificar', 'delete': 'Eliminar', 'view': 'Ver'}
    if action in verbs and model == permission.content_type.model:
        return f'{verbs[action]} {permission.content_type.name}'
    return permission.name


class LoggedUserAdmin(UserAdmin, LoggedAdmin):
    search_fields = ('username', 'first_name', 'last_name', 'email', 'client__rut', 'client__name')
    list_filter = ('is_active', 'is_staff', 'groups', PendingAccountFilter)

    def get_fieldsets(self, request, obj=None):
        if not request.user.is_superuser:
            return [('Datos de la cuenta', {'fields': ('username', 'first_name', 'last_name', 'email', 'is_active', 'is_staff', 'groups')})]
        return super().get_fieldsets(request, obj)

    def get_readonly_fields(self, request, obj=None):
        if not request.user.is_superuser:
            return ('username', 'email', 'is_active', 'is_staff', 'groups')
        if obj and ClientRegistration.objects.filter(user=obj, approved_at__isnull=True).exists():
            return ('is_active',)
        return ()

    def has_add_permission(self, request):
        return request.user.is_superuser and super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser and super().has_delete_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        if obj and (obj.is_staff or obj.is_superuser) and not request.user.is_superuser:
            return False
        return super().has_change_permission(request, obj)

    def user_change_password(self, request, id, form_url=''):
        if not request.user.is_superuser:
            raise PermissionDenied
        return super().user_change_password(request, id, form_url)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        field = super().formfield_for_manytomany(db_field, request, **kwargs)
        if db_field.name == 'user_permissions' and field:
            field.label_from_instance = permission_label
        return field


class LoggedGroupAdmin(GroupAdmin, LoggedAdmin):
    def has_add_permission(self, request):
        return request.user.is_superuser and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser and super().has_delete_permission(request, obj)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        field = super().formfield_for_manytomany(db_field, request, **kwargs)
        if db_field.name == 'permissions' and field:
            field.label_from_instance = permission_label
        return field
admin.site.unregister(User);admin.site.register(User,LoggedUserAdmin)
admin.site.unregister(Group);admin.site.register(Group,LoggedGroupAdmin)
admin.site.register(Client,ClientAdmin)
admin.site.register(Inventory,ReadOnlyAdmin)
admin.site.register(SiteConfiguration,LoggedAdmin)
for m in [Brand,ProductModel,StockCategory,Supplier,AgreementBenefit,TransferConfiguration]:
    admin.site.register(m,LoggedAdmin)
for m in [ProductVariant,StockMovement,StockReservation,TransferPayment,PaymentVoucher,PaymentReview]:
    admin.site.register(m,ReadOnlyAdmin)


@admin.register(Agreement)
class AgreementAdmin(LoggedAdmin):
    def has_change_permission(self, request, obj=None):
        return (not obj or not obj.has_managed_union) and super().has_change_permission(request, obj)

for m in [Prescription,Request,Quote,Order,Warranty,Receipt,Consent]:admin.site.register(m,ReadOnlyAdmin)
admin.site.register(Audit,AuditAdmin)
admin.site.register(Product,LoggedAdmin)
for m in [QuoteLine,Inquiry,AppointmentReservation,DeliveryAttempt]:admin.site.register(m,ReadOnlyAdmin)


class RepresentativeForm(forms.ModelForm):
    class Meta:
        model = AgreementRepresentative
        fields = '__all__'

    def clean_user(self):
        user = self.cleaned_data['user']
        if user.is_staff or user.is_superuser or user.get_all_permissions():
            raise forms.ValidationError('Usa una cuenta dedicada sin permisos de personal ni administración.')
        return user


class AgreementRepresentativeAdmin(LoggedAdmin):
    form = RepresentativeForm
    list_display = ['user', 'agreement', 'active']
    autocomplete_fields = ['user']


admin.site.register(AgreementRepresentative, AgreementRepresentativeAdmin)
admin.site.register(PurchaseLine, ReadOnlyAdmin)


@admin.register(Union, UnionDocument, UnionMembership, AccessInvitation, PickupCode)
class UnionEvidenceAdmin(ReadOnlyAdmin):
    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields if field.name not in ('file', 'digest', 'nonce', 'token', 'token_hash')]

    def get_fields(self, request, obj=None):
        return self.get_readonly_fields(request, obj)



class VerifyClientRegistrationForm(forms.Form):
    email_verified = forms.BooleanField(label='Comprobé que la persona controla el correo registrado')
    identity_verified = forms.BooleanField(label='Verifiqué su identidad y su RUT')
    note = forms.CharField(label='Referencia interna de la verificación', min_length=5, max_length=240)


@admin.register(ClientRegistration)
class ClientRegistrationAdmin(ReadOnlyAdmin):
    list_display = ['id', 'name', 'created_at', 'approved_at', 'review_link']
    list_filter = ['approved_at']
    search_fields = ['name', 'rut', 'email']
    readonly_fields = [field.name for field in ClientRegistration._meta.fields]

    @admin.display(description='Revisión')
    def review_link(self, obj):
        if obj.approved_at:
            return 'Activada'
        return format_html('<a href="{}">Revisar activación</a>',
                           reverse('admin:clientregistration_verify', args=[obj.pk]))

    def get_list_display(self, request):
        from .registration import REVIEW_PERMISSION
        return self.list_display if request.user.has_perm(REVIEW_PERMISSION) else self.list_display[:-1]

    def get_urls(self):
        return [path('<int:pk>/verificar/', self.admin_site.admin_view(self.verify),
                     name='clientregistration_verify')] + super().get_urls()

    def verify(self, request, pk):
        from .registration import REVIEW_PERMISSION, approve_registration

        if not request.user.has_perm(REVIEW_PERMISSION):
            raise PermissionDenied
        registration = get_object_or_404(ClientRegistration, pk=pk)
        if registration.approved_at:
            return redirect('admin:gestion_clientregistration_change', registration.pk)
        form = VerifyClientRegistrationForm(request.POST if request.method == 'POST' else None)
        if request.method == 'POST' and form.is_valid():
            try:
                approve_registration(pk, request.user, **form.cleaned_data)
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                self.message_user(request, 'Cuenta de cliente activada.', messages.SUCCESS)
                return redirect('admin:gestion_clientregistration_changelist')
        return render(request, 'admin/gestion/clientregistration/verify.html', {
            **self.admin_site.each_context(request), 'title': 'Verificar solicitud de cuenta',
            'registration': registration, 'client': Client.objects.filter(rut=registration.rut).first(),
            'form': form,
        })
