from django.urls import path
from gestion.frontend import interface,favicon
from gestion.health import health
from gestion import agenda, api
from gestion.attention_public import demo_static
urlpatterns=[path('api/agenda/',agenda.availability),path('healthz/',health),path('',interface),path('app/',interface),path('app/<str:page>',interface),path('api/session/',api.session),path('api/inquiries/',api.Inquiries.as_view({'post':'create'})),path('api/products/',api.Products.as_view({'get':'list'})),path('favicon.ico',favicon),path('static/<path:path>',demo_static)]
