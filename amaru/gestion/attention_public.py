"""Frontera pública de la demostración: no publica el panel, login ni lecturas privadas."""
import os
from django.conf import settings
from django.http import HttpResponse
from django.contrib.staticfiles.views import serve

class PublicBoundaryMiddleware:
    def __init__(self,get_response): self.get_response=get_response
    def __call__(self,request):
        path=request.path
        allowed=(request.method in ('GET','HEAD') and (path in ['/healthz/','/', '/app/', '/app/index.html','/app/catalogo.html','/app/formulario_remoto.html','/api/session/','/api/products/','/favicon.ico'] or path.startswith('/static/')))
        allowed=allowed or (request.method=='POST' and path=='/api/inquiries/')
        if not allowed: return HttpResponse('Ruta no disponible en la demostración pública.',status=404,content_type='text/plain')
        if getattr(settings,'ATTENTION_PUBLIC_ONLY',False) and not request.is_secure():
            return HttpResponse('HTTPS requerido.',status=400)
        response=self.get_response(request)
        response['Referrer-Policy']='same-origin'
        return response


def demo_static(request,path):
    if path in ('server.js','attention.css','interfaz/js/bootstrap.js') or path.startswith(('interfaz/css/','interfaz/img/')):
        return serve(request,os.path.normpath(path),insecure=True)
    return HttpResponse(status=404)
