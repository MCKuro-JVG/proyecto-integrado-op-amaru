"""QR de atención y limitación de envíos, sin datos personales en enlaces."""
import json,os,time
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from rest_framework.decorators import api_view,permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied,Throttled,ValidationError
from rest_framework.response import Response
import qrcode


def check_submission_rate(request):
    # Solo confiar en CF-Connecting-IP dentro del servidor exclusivo del túnel.
    address=request.META.get('REMOTE_ADDR','unknown')
    if getattr(settings,'ATTENTION_PUBLIC_ONLY',False): address=request.META.get('HTTP_CF_CONNECTING_IP',address)
    from django.utils.crypto import salted_hmac
    key='attention-rate:'+salted_hmac('attention',address).hexdigest()
    if cache.add(key,1,600): return
    if cache.incr(key)>getattr(settings,'ATTENTION_RATE_LIMIT',15): raise Throttled(600,'Demasiados envíos. Intente más tarde.')


def public_configuration(request):
    base=getattr(settings,'ATTENTION_PUBLIC_BASE_URL','').rstrip('/')
    demo=False
    path=Path(settings.ATTENTION_URL_FILE)
    if not base and path.is_file():
        try:
            data=json.loads(path.read_text(encoding='utf-8'))
            # El iniciador mantiene este archivo; la URL temporal vence con el proceso.
            if data.get('active') and data.get('pid') and data.get('expires_at',0)>time.time():
                import ctypes
                handle=ctypes.windll.kernel32.OpenProcess(0x1000,False,int(data['pid'])) if os.name=='nt' else None
                if handle:
                    ctypes.windll.kernel32.CloseHandle(handle);base=data['url'].rstrip('/');demo=True
        except (ValueError,OSError,KeyError,AttributeError): pass
    parts=urlsplit(base)
    valid=parts.scheme=='https' and bool(parts.hostname) and not parts.username and not parts.password and not parts.query and not parts.fragment and parts.path in ('','/')
    if parts.hostname in ('localhost','127.0.0.1','::1'):valid=False
    url=base+'/app/formulario_remoto.html?origen=qr' if valid else None
    return {'url':url,'scannable':bool(valid),'demo':demo,'staff_url':'http://127.0.0.1:8003/app/solicitudes.html' if demo else None,
        'warning':'Demostración aislada: solo datos ficticios; solicitudes visibles en el panel local de demostración.' if demo else 'Configure una URL HTTPS accesible desde el celular.' if not valid else ''}


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def attention_qr(request):
    if not request.user.has_perm('gestion.view_inquiry'): raise PermissionDenied()
    data=public_configuration(request)
    if request.query_params.get('image')=='png':
        if not data['scannable']: raise ValidationError('No existe una URL pública HTTPS configurada.')
        image=qrcode.make(data['url'],box_size=12,border=4);buf=BytesIO();image.save(buf,format='PNG')
        response=HttpResponse(buf.getvalue(),content_type='image/png')
        response['Content-Disposition']='attachment; filename="OpticasAmaru-QR-atencion.png"' if request.query_params.get('download') else 'inline'
    else: response=Response(data)
    response['Cache-Control']='no-store';return response
