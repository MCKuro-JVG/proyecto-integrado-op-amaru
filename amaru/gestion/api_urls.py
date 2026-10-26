from django.urls import path,include
from rest_framework.routers import DefaultRouter
from . import api
router=DefaultRouter()
for prefix,view in [('clients',api.Clients),('prescriptions',api.Prescriptions),('products',api.Products),
    ('quotes',api.Quotes),('orders',api.Orders),('warranties',api.Warranties),('inquiries',api.Inquiries),
    ('receipts',api.Receipts),('audit',api.Audits),('inventory',api.Inventories),('agreements',api.Agreements)]:
    router.register(prefix,view,basename=prefix)
urlpatterns=[path('session/',api.session),path('login/',api.sign_in),path('logout/',api.sign_out),
    path('configuration/',api.configuration),path('prescriptions/<int:pk>/file/',api.prescription_file),path('',include(router.urls))]
