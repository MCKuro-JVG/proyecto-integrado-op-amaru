"""Disponibilidad pública y bloqueos administrados, sin exponer reservas."""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import permissions, serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.response import Response

from .models import AgendaBlock, AppointmentReservation, SiteConfiguration, default_agenda_hours


class AgendaConflict(APIException):
    status_code = 409
    default_detail = "El horario ya no está disponible. Selecciona otro."


def lock_agenda():
    config, _ = SiteConfiguration.objects.select_for_update().get_or_create(pk=1)
    return config


def is_open(config, day, slot):
    if day < timezone.localdate() or slot.strftime("%H:%M") not in config.agenda_hours.get(str(day.weekday()), []):
        return False
    return not AgendaBlock.objects.filter(day=day, active=True, slot__in=["", slot.strftime("%H:%M")]).exists()


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def availability(request):
    today = timezone.localdate()
    end = today + timedelta(days=29)
    hours = SiteConfiguration.objects.filter(pk=1).values_list("agenda_hours", flat=True).first()
    if hours is None:
        hours = default_agenda_hours()
    blocked = set(AgendaBlock.objects.filter(day__range=(today, end), active=True).values_list("day", "slot"))
    occupied = {
        (day, slot.strftime("%H:%M"))
        for day, slot in AppointmentReservation.objects.filter(day__range=(today, end)).values_list("day", "slot")
    }
    days = []
    for offset in range(30):
        day = today + timedelta(days=offset)
        slots = [] if (day, "") in blocked else [
            slot for slot in hours.get(str(day.weekday()), [])
            if (day, slot) not in blocked and (day, slot) not in occupied
        ]
        if slots:
            days.append({"day": day.isoformat(), "slots": slots})
    response = Response({"days": days, "timezone": "America/Santiago"})
    response["Cache-Control"] = "no-store"
    return response


class BlockInput(serializers.Serializer):
    day = serializers.DateField()
    slot = serializers.TimeField(required=False, input_formats=["%H:%M"])
    active = serializers.BooleanField(default=True)


@api_view(["GET", "POST"])
def blocks(request):
    if request.method == "GET":
        if not request.user.has_perm("gestion.view_agendablock"):
            raise PermissionDenied()
        rows = AgendaBlock.objects.order_by("-day", "slot").values("day", "slot", "active")[:100]
        return Response(list(rows))
    if not request.user.has_perms(["gestion.add_agendablock", "gestion.change_agendablock"]):
        raise PermissionDenied()
    data = BlockInput(data=request.data)
    data.is_valid(raise_exception=True)
    values = data.validated_data
    day, active = values["day"], values["active"]
    slot = values["slot"].strftime("%H:%M") if "slot" in values else ""
    if day < timezone.localdate():
        raise ValidationError("Solo puedes modificar bloqueos desde hoy.")
    from .services import audit

    with transaction.atomic():
        lock_agenda()
        if active:
            reserved = AppointmentReservation.objects.filter(day=day)
            if slot:
                reserved = reserved.filter(slot=slot)
            if reserved.exists():
                raise AgendaConflict("Cancela primero las solicitudes activas que ocupan ese horario.")
        block, _ = AgendaBlock.objects.update_or_create(day=day, slot=slot, defaults={"active": active})
        audit(request.user, "Bloqueo de agenda" if active else "Liberación de bloqueo de agenda", block)
    return Response({"day": day, "slot": slot, "active": active})
