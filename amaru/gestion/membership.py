"""Consulta con referencia privada y bandeja de representantes por organización."""
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_protect
from rest_framework import permissions, serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .api import VerificationInput, review_membership
from .models import AgreementRepresentative, Inquiry


def verified_agreement(client):
    agreement = client.agreement
    if agreement is None or not agreement.available:
        return None
    approval = client.inquiries.filter(agreement=agreement).exclude(verification_state='').order_by('-created_at', '-pk').first()
    if approval and approval.verification_state == 'aprobada' and (approval.agreement_role != 'carga' or agreement.allow_dependents):
        return agreement
    return None


def representative_for(user):
    return AgreementRepresentative.objects.select_related('agreement').filter(user=user, active=True).first()


class StatusInput(serializers.Serializer):
    reference = serializers.UUIDField()


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
@csrf_protect
def status(request):
    from .attention import check_submission_rate
    check_submission_rate(request)
    form = StatusInput(data=request.data)
    form.is_valid(raise_exception=True)
    row = get_object_or_404(Inquiry.objects.exclude(verification_state=''), token=form.validated_data['reference'])
    response = Response({'state': row.verification_state, 'reviewed': row.verified_at.date() if row.verified_at else None})
    response['Cache-Control'] = 'no-store'
    return response


@api_view(['GET'])
def queue(request):
    representative = representative_for(request.user)
    if representative is None or not representative.agreement.available:
        raise PermissionDenied()
    rows = Inquiry.objects.filter(agreement=representative.agreement).exclude(verification_state='').order_by('-created_at', '-pk')[:100]
    return Response({'organization': representative.agreement.name, 'requests': [summary(row) for row in rows]})


def summary(row):
    return {'id': row.pk, 'name': row.name, 'rut': row.registration_rut, 'role': row.agreement_role,
            'state': row.verification_state, 'received': row.created_at.date()}


@api_view(['POST'])
def decide(request, pk):
    payload = VerificationInput(data={**request.data, 'method': 'responsable'})
    payload.is_valid(raise_exception=True)
    with transaction.atomic():
        representative = AgreementRepresentative.objects.select_for_update().filter(user=request.user, active=True).first()
        if representative is None:
            raise PermissionDenied()
        row = review_membership(request.user, pk, payload.validated_data, representative.agreement_id)
    return Response(summary(row))
