from django.contrib import admin
from django.contrib.auth.models import User,Group
from django.contrib.auth.admin import UserAdmin,GroupAdmin
from .models import *
from .services import audit,record_consent
admin.site.site_header='Ópticas Amaru · Administración'
admin.site.site_title='Ópticas Amaru'
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
    search_fields=['rut','name']
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
class LoggedUserAdmin(UserAdmin,LoggedAdmin):pass
class LoggedGroupAdmin(GroupAdmin,LoggedAdmin):pass
admin.site.unregister(User);admin.site.register(User,LoggedUserAdmin)
admin.site.unregister(Group);admin.site.register(Group,LoggedGroupAdmin)
admin.site.register(Client,ClientAdmin)
for m in [Agreement,Inventory,SiteConfiguration]:admin.site.register(m,LoggedAdmin)
for m in [Prescription,Request,Quote,Order,Warranty,Receipt,Consent]:admin.site.register(m,ReadOnlyAdmin)
admin.site.register(Audit,AuditAdmin)
admin.site.register(Product,LoggedAdmin)
for m in [QuoteLine,Inquiry,AppointmentReservation,DeliveryAttempt]:admin.site.register(m,ReadOnlyAdmin)
