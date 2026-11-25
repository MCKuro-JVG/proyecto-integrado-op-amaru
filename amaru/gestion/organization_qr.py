"""Dos QR revocables por organización; el enlace nunca verifica la pertenencia."""
from io import BytesIO
from collections.abc import Mapping
import secrets
import time
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

import qrcode
from django.core import signing
from django.core.exceptions import ValidationError as ModelValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from rest_framework import permissions, serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .attention import check_submission_rate, public_configuration
from .date_filters import filter_created_dates
from .models import Agreement, AgreementRepresentative, Client, Inquiry, Union, UnionMembership
from .registration import PRIVACY_VERSION, RegistrationInput
from .services import audit, receive_inquiry
from .unions import private, safe_personal_user, worker_summary
from .validators import normalize_rut

PURPOSES = {'worker': 'Registro de trabajador asociado', 'inquiry': 'Consulta de convenio'}
SALT = 'gestion.organization_qr.v1'


def validate_qr(agreement, purpose, token):
    if (purpose not in PURPOSES or not getattr(agreement, purpose + '_qr_enabled', False)
            or str(getattr(agreement, purpose + '_qr_token', '')) != str(token) or not agreement.available):
        raise NotFound('El QR no está disponible. Solicita un enlace vigente a Ópticas Amaru.')


def resolve(purpose, token, *, lock=False):
    if purpose not in PURPOSES:
        raise NotFound()
    reference = get_object_or_404(Agreement, **{purpose + '_qr_token': token})
    if lock:
        # Mismo orden que la gestión sindical: sindicato y después convenio.
        union = Union.objects.filter(agreement=reference).first()
        if union:
            Union.objects.select_for_update().get(pk=union.pk)
        reference = Agreement.objects.select_for_update().get(pk=reference.pk)
    validate_qr(reference, purpose, token)
    return reference


def authorized_organization(user, pk):
    agreement = get_object_or_404(Agreement.objects.select_related('union'), pk=pk)
    if not (user.has_perm('gestion.view_agreement') or AgreementRepresentative.objects.filter(
            user=user, agreement=agreement, active=True).exists()):
        raise PermissionDenied()
    return agreement


def can_manage(user, agreement):
    return user.has_perm('gestion.change_union' if agreement.has_managed_union else 'gestion.change_agreement')


def qr_links(request, agreement):
    configured = public_configuration(request)['url']
    parts = urlsplit(configured or '')
    base = f'{parts.scheme}://{parts.netloc}' if configured else ''
    rows = []
    for purpose, title in PURPOSES.items():
        token = getattr(agreement, purpose + '_qr_token')
        route = 'registro_trabajador.html' if purpose == 'worker' else 'consulta_convenio.html'
        rows.append({'purpose': purpose, 'title': title, 'enabled': getattr(agreement, purpose + '_qr_enabled'),
            'url': base + '/app/' + route + '?' + urlencode({'qr': str(token)}) if base else None,
            'image_url': f'/api/organization-qrs/{agreement.pk}/{purpose}/image/?v={token}'})
    today = timezone.localdate()
    benefits = agreement.benefits.filter(active=True).filter(
        Q(starts_on__isnull=True) | Q(starts_on__lte=today),
        Q(ends_on__isnull=True) | Q(ends_on__gte=today))
    staff = request.user.has_perm('gestion.change_agreement') and request.user.has_perm('gestion.view_inquiry')
    return {'id': agreement.pk, 'name': agreement.name, 'type': 'sindicato' if agreement.has_managed_union else 'convenio',
            'available': agreement.available, 'can_manage': can_manage(request.user, agreement),
            'starts_on': agreement.starts_on, 'ends_on': agreement.ends_on,
            'code': agreement.code if request.user.has_perm('gestion.view_agreement') else None,
            'allow_dependents': agreement.allow_dependents, 'benefit_count': benefits.count() if agreement.available else 0,
            'privacy_version': PRIVACY_VERSION,
            'can_edit_workers': staff and not agreement.has_managed_union,
            'can_manage_union_workers': agreement.has_managed_union and request.user.has_perm('gestion.change_union'),
            'can_register_union_workers': agreement.has_managed_union and (
                request.user.has_perm('gestion.change_union') or AgreementRepresentative.objects.filter(
                    user=request.user, agreement=agreement, active=True).exists()),
            'can_view_benefits': request.user.has_perm('gestion.view_agreementbenefit'),
            'union_id': agreement.union.pk if agreement.has_managed_union else None,
            'can_read_inquiries': request.user.has_perm('gestion.view_inquiry'), 'codes': rows}


@api_view(['GET', 'POST'])
def management(request, pk):
    agreement = authorized_organization(request.user, pk)
    if request.method == 'POST':
        if not can_manage(request.user, agreement):
            raise PermissionDenied()
        class Change(serializers.Serializer):
            purpose = serializers.ChoiceField(choices=list(PURPOSES))
            operation = serializers.ChoiceField(choices=['rotate', 'revoke', 'enable'])
            confirmed = serializers.BooleanField()
        form = Change(data=request.data)
        form.is_valid(raise_exception=True)
        values = form.validated_data
        if not values['confirmed']:
            raise ValidationError('Confirma el cambio del QR seleccionado.')
        with transaction.atomic():
            if agreement.has_managed_union:
                Union.objects.select_for_update().get(agreement=agreement)
            agreement = Agreement.objects.select_for_update().get(pk=pk)
            purpose = values['purpose']
            fields = [purpose + '_qr_enabled']
            setattr(agreement, fields[0], values['operation'] != 'revoke')
            if values['operation'] == 'rotate':
                fields.append(purpose + '_qr_token')
                setattr(agreement, fields[-1], uuid4())
            agreement.save(update_fields=fields)
            audit(request.user, f'QR de organización: {purpose} · {values["operation"]}', agreement)
    return private(qr_links(request, agreement))


@api_view(['GET'])
def image(request, pk, purpose):
    agreement = authorized_organization(request.user, pk)
    row = next((r for r in qr_links(request, agreement)['codes'] if r['purpose'] == purpose), None)
    if not row or not row['url']:
        raise ValidationError('Configura una dirección pública HTTPS para generar el QR.')
    output = BytesIO()
    qrcode.make(row['url'], box_size=10, border=4).save(output, format='PNG')
    result = HttpResponse(output.getvalue(), content_type='image/png')
    result['Cache-Control'] = 'private, no-store'
    result['Content-Disposition'] = ('attachment' if request.query_params.get('download') else 'inline') + f'; filename="Amaru-QR-{purpose}-{pk}.png"'
    return result


def metadata(agreement, purpose, token):
    today = timezone.localdate()
    benefits = agreement.benefits.filter(active=True, public_visible=True).filter(
        Q(starts_on__isnull=True) | Q(starts_on__lte=today)).filter(Q(ends_on__isnull=True) | Q(ends_on__gte=today))[:50]
    return {'organization': agreement.name, 'organization_type': 'sindicato' if agreement.has_managed_union else 'convenio',
        'title': PURPOSES[purpose], 'allow_dependents': agreement.allow_dependents, 'privacy_version': PRIVACY_VERSION,
        'challenge': signing.dumps({'issued': time.time(), 'nonce': secrets.token_urlsafe(16),
            'qr': str(token), 'purpose': purpose}, salt=SALT),
        'benefits': [{'name': b.name, 'description': b.description, 'conditions': b.conditions, 'kind': b.kind,
            'type': b.get_kind_display(), 'value': str(b.value) if b.value is not None else None} for b in benefits] if purpose == 'inquiry' else []}


def check_form(request, purpose, token):
    check_submission_rate(request)
    if (not isinstance(request.data, Mapping) or request.data.get('website')
            or not isinstance(request.data.get('challenge'), str) or len(request.data['challenge']) > 500):
        raise ValidationError('No se pudo validar el formulario.')
    try:
        challenge = signing.loads(request.data.get('challenge', ''), salt=SALT, max_age=3600)
        valid = (challenge['qr'] == str(token) and challenge['purpose'] == purpose
                 and 2 <= time.time() - challenge['issued'] <= 3600)
    except (signing.BadSignature, TypeError, KeyError):
        valid = False
    if not valid:
        raise ValidationError('El formulario venció o no corresponde a este QR. Recárgalo e intenta nuevamente.')


class WorkerRegistration(serializers.Serializer):
    name = serializers.CharField(max_length=180)
    rut = serializers.CharField(max_length=18)
    email = serializers.EmailField(max_length=150)
    phone = serializers.CharField(max_length=30)
    role = serializers.ChoiceField(choices=['titular', 'carga'])
    privacy = serializers.BooleanField()
    privacy_version = serializers.CharField(max_length=24)
    idempotency_key = serializers.UUIDField()

    def validate_name(self, value):
        return RegistrationInput().validate_name(value)

    def validate_rut(self, value):
        from .unions import WorkerInput
        return WorkerInput().validate_rut(value)

    def validate_phone(self, value):
        return RegistrationInput().validate_phone(value)

    def validate_email(self, value):
        return value.lower()

    def validate(self, data):
        if not data['privacy'] or data['privacy_version'] != PRIVACY_VERSION:
            raise ValidationError('Acepta la política de privacidad vigente para tramitar tu vinculación.')
        return data


@api_view(['GET', 'POST'])
@permission_classes([permissions.AllowAny])
@csrf_protect
def public(request, purpose, token):
    if request.method == 'GET':
        return private(metadata(resolve(purpose, token), purpose, token))
    check_form(request, purpose, token)
    try:
        with transaction.atomic():
            agreement = resolve(purpose, token, lock=True)
            if purpose == 'worker':
                row, created = register_worker(request, agreement, token)
            else:
                row, created = register_query(request, agreement, token)
    except IntegrityError:
        return private({'detail': 'El registro o el horario ya fue recibido. Comprueba tu referencia antes de repetir el envío.'}, 409)
    detail = ('Registro de trabajador recibido y asociado a tu organización. La pertenencia y el acceso quedan pendientes de validación. '
              'No se creó una cuenta ni se enviaron correos. La óptica coordinará el acceso individual.' if purpose == 'worker'
              else 'Consulta recibida y asociada a tu organización. No crea una cuenta ni confirma una reserva de atención.')
    return private({'reference': row.token, 'created': created, 'organization': agreement.name,
        'classification': ('trabajador_sindicato' if agreement.has_managed_union else 'trabajador_convenio') if purpose == 'worker' else 'consulta_organizacion',
        'detail': detail}, 201 if created else 200)


def register_worker(request, agreement, token):
    from .purchases import Conflict
    form = WorkerRegistration(data=request.data)
    form.is_valid(raise_exception=True)
    data = form.validated_data
    if data['role'] == 'carga' and not agreement.allow_dependents:
        raise ValidationError({'role': 'El convenio no admite cargas familiares.'})
    inquiry, created = receive_inquiry({'kind': 'registro', 'source': 'qr', 'name': data['name'], 'phone': data['phone'],
        'email': data['email'], 'service': 'Registro de trabajador asociado', 'reason': 'Solicitud de afiliación mediante QR de organización.',
        'registration_rut': data['rut'], 'agreement': agreement, 'agreement_role': data['role'],
        'privacy_version': data['privacy_version'], 'contact_authorized': True, 'idempotency_key': data['idempotency_key']},
        request.user, organization_qr={'purpose': 'worker', 'token': token})
    if not created:
        return inquiry, False
    own = Client.objects.filter(rut=data['rut'], user=request.user, active=True).first() if request.user.is_authenticated and safe_personal_user(request.user) else None
    if own:
        inquiry.client = own
    if agreement.has_managed_union:
        union = agreement.union
        if union.memberships.filter(Q(rut=data['rut']) | Q(email=data['email'])).exists():
            raise Conflict('Ya existe una vinculación o solicitud para esos datos. Contacta a tu organización.')
        membership = UnionMembership.objects.create(union=union, name=data['name'], rut=data['rut'], email=data['email'],
            phone=data['phone'], role=data['role'], origin='qr_worker', client=own,
            accepted_at=timezone.now() if own else None)
        inquiry.union_membership = membership
        audit(request.user, 'Afiliación sindical pendiente registrada mediante QR', membership)
    inquiry.save(update_fields=['client', 'union_membership'])
    audit(request.user, 'Registro QR asociado; requiere validación de identidad y pertenencia', inquiry)
    return inquiry, True


def register_query(request, agreement, token):
    from .serializers import InquirySerializer
    if request.data.get('kind') not in ('contacto', 'lentes', 'agenda'):
        raise ValidationError('Selecciona consulta, cotización u orientación de lentes, o solicitud de atención.')
    if request.data.get('privacy') is not True or request.data.get('privacy_version') != PRIVACY_VERSION:
        raise ValidationError('Acepta la política de privacidad vigente.')
    fields = ['kind', 'name', 'email', 'phone', 'service', 'reason', 'day', 'slot', 'contact_authorized', 'idempotency_key']
    form = InquirySerializer(data={key: request.data[key] for key in fields if key in request.data})
    form.is_valid(raise_exception=True)
    data = {**form.validated_data, 'agreement': agreement, 'source': 'qr', 'privacy_version': PRIVACY_VERSION}
    return receive_inquiry(data, request.user, organization_qr={'purpose': 'inquiry', 'token': token})


def filter_workers(rows, request, *, union=False):
    rut_field = 'rut' if union else 'registration_rut'
    search = request.query_params.get('q', '').strip()[:180]
    if search:
        try:
            rut = normalize_rut(search)
        except ModelValidationError:
            rows = rows.filter(name__icontains=search)
        else:
            rows = rows.filter(Q(name__icontains=search) | Q(**{rut_field: rut}))
    states = {'pending': ('pending',) if union else ('pendiente',),
              'active': ('active',) if union else ('aprobada',),
              'inactive': ('inactive',) if union else ('inactiva', 'rechazada')}
    state = request.query_params.get('state', '')
    if state:
        if state not in states:
            raise ValidationError('Selecciona un estado de afiliación válido.')
        field = 'state__in' if union else 'verification_state__in'
        rows = rows.filter(**{field: states[state]})
    return filter_created_dates(rows, request.query_params)


@api_view(['GET', 'POST'])
def registrations(request, pk):
    agreement = authorized_organization(request.user, pk)
    if request.method == 'POST':
        if agreement.has_managed_union or not request.user.has_perms(
                ['gestion.change_agreement', 'gestion.view_inquiry']):
            raise PermissionDenied()
        form = WorkerRegistration(data=request.data)
        form.is_valid(raise_exception=True)
        data = form.validated_data
        row, created = receive_inquiry({
            'kind': 'registro', 'source': 'web', 'name': data['name'], 'registration_rut': data['rut'],
            'email': data['email'], 'phone': data['phone'], 'agreement_role': data['role'],
            'agreement': agreement, 'service': 'Registro de trabajador asociado',
            'reason': 'Registro administrativo para validar afiliación.', 'contact_authorized': True,
            'privacy_version': PRIVACY_VERSION, 'idempotency_key': data['idempotency_key'],
        }, request.user, staff_registration=True)
        return private({'id': row.pk, 'state': row.verification_state}, 201 if created else 200)
    pagination = PageNumberPagination()
    if agreement.has_managed_union:
        rows = agreement.union.memberships.select_related('union__agreement', 'client__user').order_by('-pk')
        counts = rows.aggregate(total=Count('pk'), pending=Count('pk', filter=Q(state='pending')),
            active=Count('pk', filter=Q(state='active')), inactive=Count('pk', filter=Q(state='inactive')))
        selected = [worker_summary(row) for row in pagination.paginate_queryset(filter_workers(rows, request, union=True), request)]
    else:
        rows = Inquiry.objects.filter(agreement=agreement, kind='registro').exclude(
            verification_state='').select_related('client__user').order_by('-pk')
        counts = rows.aggregate(total=Count('pk'), pending=Count('pk', filter=Q(verification_state='pendiente')),
            active=Count('pk', filter=Q(verification_state='aprobada')),
            inactive=Count('pk', filter=Q(verification_state__in=('inactiva', 'rechazada'))))
        page = pagination.paginate_queryset(filter_workers(rows, request), request)
        selected = [{'id': row.pk, 'name': row.name, 'rut': row.registration_rut, 'email': row.email, 'phone': row.phone,
            'role': row.agreement_role, 'state': row.verification_state, 'created_at': row.created_at,
            'origin': row.origin, 'origin_label': row.get_origin_display(),
            'account_state': 'Activa' if row.client and row.client.active and row.client.user and row.client.user.is_active
                             else 'Sin acceso activo',
            'client': row.client_id if request.user.has_perm('gestion.view_client') else None} for row in page]
    response = pagination.get_paginated_response(selected)
    response.data['counts'] = counts
    response.data['organization'] = agreement.name
    response['Cache-Control'] = 'private, no-store'
    return response


@api_view(['POST'])
@transaction.atomic
def affiliation_state(request, pk, registration_id):
    from .api import VerificationInput, review_membership
    from .purchases import Conflict
    if not request.user.has_perms(['gestion.change_agreement', 'gestion.view_inquiry']):
        raise PermissionDenied()
    if not isinstance(request.data, Mapping):
        raise ValidationError('Selecciona una acción de afiliación válida.')
    agreement = Agreement.objects.select_for_update().get(pk=authorized_organization(request.user, pk).pk)
    if agreement.has_managed_union:
        raise ValidationError('Gestiona esta afiliación desde el panel del sindicato.')
    row = get_object_or_404(Inquiry.objects.select_for_update(), pk=registration_id, agreement=agreement, kind='registro')
    if request.data.get('action') == 'reactivate':
        form = VerificationInput(data={**request.data, 'approved': True})
        form.is_valid(raise_exception=True)
        if not form.validated_data['identity_verified']:
            raise ValidationError('Confirma la verificación del titular.')
        row = review_membership(request.user, row.pk, form.validated_data, agreement.pk, expected='inactiva')
    elif request.data.get('action') == 'disable':
        note = serializers.CharField(min_length=5, max_length=500).run_validation(request.data.get('note'))
        if row.verification_state != 'aprobada':
            raise Conflict('La afiliación debe estar activa para desactivarla.')
        row.verification_state = 'inactiva'
        row.verification_note = note
        row.verified_by, row.verified_at = request.user, timezone.now()
        row.save(update_fields=['verification_state', 'verification_note', 'verified_by', 'verified_at', 'updated_at'])
        audit(request.user, 'Afiliación de convenio desactivada', row)
    else:
        raise ValidationError('Selecciona una acción de afiliación válida.')
    return private({'id': row.pk, 'state': row.verification_state})
