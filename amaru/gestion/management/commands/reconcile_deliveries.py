from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q
from gestion.models import DeliveryAttempt,Receipt


class Command(BaseCommand):
    help='Revisa archivos huérfanos de entregas fallidas. Solo lectura salvo --apply; espera mínima de una hora.'
    def add_arguments(self,parser): parser.add_argument('--apply',action='store_true')
    def handle(self,*args,**options):
        rows=DeliveryAttempt.objects.exclude(state='complete').filter(created_at__lt=timezone.now()-timedelta(hours=1))
        for attempt in rows:
            self.stdout.write(f'{attempt.key}: {attempt.state}')
            if not options['apply']:continue
            referenced=False
            for field,name in [('pdf',attempt.pdf_key),('signature',attempt.signature_key)]:
                if not name:continue
                if Receipt.objects.filter(**{field:name}).exists():referenced=True;continue
                Receipt._meta.get_field(field).storage.delete(name)
            attempt.state='complete' if referenced else 'failed';attempt.save()
