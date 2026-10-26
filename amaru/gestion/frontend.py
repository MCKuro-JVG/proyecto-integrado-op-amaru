"""Sirve el HTML y CSS existentes con el cliente de la API en vez del motor DEMO."""
import re
from django.conf import settings
from django.http import HttpResponse, Http404


def interface(request,page='index.html'):
    root=settings.BASE_DIR.parent/'frontend_amaru'
    path=root/page
    if not re.fullmatch(r'[a-z_]+\.html',page) or not path.is_file(): raise Http404
    html=path.read_text(encoding='utf-8')
    html=re.sub(r'<script src="js/(?:storage|app)\.js[^\"]*" defer></script>','',html)
    html=html.replace('</head>','<script src="/static/server.js?v=backend1" defer></script></head>')
    html=re.sub(r'(href|src)="((?:css|img|js)/)',r'\1="/static/interfaz/\2',html)
    html=re.sub(r'<div class="demo-banner">.*?</div>','<div class="demo-banner">APLICACIÓN ACADÉMICA · Datos en el servidor · Sin envíos de correo o mensajes · Use datos ficticios</div>',html)
    html=html.replace('Personal · DEMO ↗','Acceso del personal ↗')
    html=html.replace('Ópticas Amaru · Prototipo académico independiente · Sin reservas ni mensajes reales','Ópticas Amaru · Aplicación académica · Solicitudes sujetas a revisión')
    response=HttpResponse(html)
    response['Cache-Control']='no-store'
    return response


def favicon(request):
    return HttpResponse(status=204)
