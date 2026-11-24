from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from gestion.models import Inventory, StockReservation


class Command(BaseCommand):
    help='Marca como liberadas las reservas vencidas. Las consultas ya excluyen su cantidad al vencer.'

    def handle(self,*args,**options):
        count=0
        ids=StockReservation.objects.filter(state='active',expires_at__lte=timezone.now()).values_list('pk',flat=True)
        for pk in ids.iterator():
            with transaction.atomic():
                ref=StockReservation.objects.get(pk=pk)
                Inventory.objects.select_for_update().get(pk=ref.inventory_id)
                row=StockReservation.objects.select_for_update().get(pk=pk)
                if row.state=='active' and row.expires_at<=timezone.now():
                    row.state='released'
                    row.save(update_fields=['state','updated_at'])
                    count+=1
        self.stdout.write(f'Reservas vencidas liberadas: {count}')
