"""Salud mínima: no devuelve nombres de bases, usuarios ni documentos."""
from django.db import connection
from django.http import JsonResponse

def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            healthy=cursor.fetchone()[0]==1
    except Exception:
        healthy=False
    response=JsonResponse({'status':'ok' if healthy else 'unavailable'},status=200 if healthy else 503)
    response['Cache-Control']='no-store'
    return response
