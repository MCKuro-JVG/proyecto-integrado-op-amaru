from django.contrib import admin
from django.urls import path,include
from gestion.frontend import interface,favicon
from gestion.auth import LimitedLoginView
from django.contrib.auth import views as auth
from gestion import views as v
urlpatterns=[path('admin/',admin.site.urls),path('login/',LimitedLoginView.as_view(template_name='login.html'),name='login'),path('logout/',auth.LogoutView.as_view(),name='logout'),path('',v.dashboard,name='dashboard'),path('solicitar/',v.remote,name='remote'),path('solicitar/confirmacion/',v.remote_success,name='remote_success'),path('consulta/',v.lookup,name='lookup'),path('qr/',v.qr,name='qr'),path('archivos/<str:kind>/<int:pk>/',v.file_view,name='file'),path('clientes/<int:pk>/editar/',v.edit_client,name='edit_client'),path('clientes/<int:pk>/examen/',v.exam,name='exam'),path('cotizaciones/<int:pk>/editar/',v.edit_quote,name='edit_quote'),path('cotizaciones/<int:pk>/convertir/',v.convert,name='convert'),path('solicitudes/<int:pk>/cotizar/',v.request_quote,name='request_quote'),path('ordenes/<int:pk>/recepcion/',v.receipt,name='receipt'),path('<str:module>/nuevo/',v.create,name='create'),path('<str:module>/<int:pk>/estado/',v.state,name='state'),path('<str:module>/<int:pk>/',v.detail,name='detail'),path('<str:module>/',v.listing,name='listing')]

urlpatterns = [path('favicon.ico',favicon), path('api/', include('gestion.api_urls')), path('app/', interface), path('app/<str:page>', interface)] + urlpatterns
