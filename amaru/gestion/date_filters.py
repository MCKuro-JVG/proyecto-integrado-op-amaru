"""Filter timestamps by calendar dates in the application's time zone."""
from datetime import date, datetime, time, timedelta

from django.utils import timezone
from rest_framework.exceptions import ValidationError


def filter_created_dates(rows, query):
    boundaries = {}
    for param in ('desde', 'hasta'):
        value = query.get(param)
        if value:
            try:
                boundaries[param] = date.fromisoformat(value)
            except ValueError:
                raise ValidationError('Ingresa fechas válidas.') from None
    start, end = boundaries.get('desde'), boundaries.get('hasta')
    if start and end and start > end:
        raise ValidationError('La fecha inicial debe ser anterior o igual a la final.')
    tz = timezone.get_current_timezone()
    if start:
        rows = rows.filter(created_at__gte=timezone.make_aware(datetime.combine(start, time.min), tz))
    if end and end < date.max:
        next_day = datetime.combine(end + timedelta(days=1), time.min)
        rows = rows.filter(created_at__lt=timezone.make_aware(next_day, tz))
    return rows
