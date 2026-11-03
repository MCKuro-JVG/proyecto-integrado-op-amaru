"""Filtra detalles de solicitudes y excepciones en los registros del origen público."""
import logging
class SafeOperationalFilter(logging.Filter):
    def filter(self,record):
        if record.name.startswith(('django.request','django.server')) or record.exc_info:
            record.msg='Evento operativo del origen público; nivel %s'
            record.args=(record.levelname,)
            record.exc_info=None;record.exc_text=None;record.stack_info=None
        return True
