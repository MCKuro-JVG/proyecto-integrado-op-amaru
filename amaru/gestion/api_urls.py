from django.urls import path,include
from rest_framework.routers import DefaultRouter
from . import agenda, api, catalog_requests, membership, pickup, purchases, registration, unions
from .attention import attention_qr
router=DefaultRouter()
for prefix,view in [('clients',api.Clients),('prescriptions',api.Prescriptions),('products',api.Products),
    ('catalog-management',api.CatalogManagement),('quotes',api.Quotes),('orders',api.Orders),('warranties',api.Warranties),('inquiries',api.Inquiries),
    ('receipts',api.Receipts),('audit',api.Audits),('inventory',api.Inventories),('agreements',api.Agreements)]:
    router.register(prefix,view,basename=prefix)
urlpatterns=[path('register/',registration.register,name='client-register'),path('my-account/',registration.my_account),path('checkout/',purchases.checkout),path('purchases/<int:pk>/',purchases.detail),path('purchases/<int:pk>/quote/',purchases.quote),path('membership/status/',membership.status),path('membership/queue/',membership.queue),path('membership/queue/<int:pk>/',membership.decide),path('clients/<int:pk>/agreement/',api.client_agreement),path('agreement-verifications/<int:pk>/',api.verify_agreement),path('my-prescriptions/',catalog_requests.my_prescriptions),path('product-requests/',catalog_requests.request_product),path('agenda/',agenda.availability),path('agenda/blocks/',agenda.blocks),path('attention-qr/',attention_qr),path('session/',api.session),path('login/',api.sign_in),path('logout/',api.sign_out),
    path('unions/', unions.organizations), path('unions/<int:pk>/manage/', unions.manage_organization),
    path('unions/<int:pk>/workers/', unions.admin_workers), path('unions/<int:pk>/document/', unions.upload_document), path('union-documents/<int:pk>/', unions.download_document),
    path('union/portal/', unions.portal), path('union/sign/', unions.sign_document), path('union/account/', unions.account),
    path('union/workers/', unions.create_worker), path('union/workers/<int:pk>/', unions.manage_worker),
    path('union/reviews/', unions.review_queue), path('invitation/claim/', unions.claim),
    path('pickup/validate/', pickup.validate), path('pickup/<int:pk>/', pickup.manage),
    path('configuration/',api.configuration),path('prescriptions/<int:pk>/file/',api.prescription_file),path('',include(router.urls))]
