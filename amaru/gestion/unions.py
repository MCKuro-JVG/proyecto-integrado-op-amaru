"""Gestión de sindicatos y credenciales de acceso de un solo uso."""
from datetime import timedelta
from hashlib import sha256
import secrets

from django.conf import settings
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from rest_framework import permissions, serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from .attention import check_submission_rate
from .models import AccessInvitation, Agreement, AgreementRepresentative, Client, ClientRegistration, Union, UnionDocument, UnionMembership
from .services import audit
from .validators import normalize_rut, validate_document

ADMIN_PERMISSION = 'gestion.change_union'
ACCEPTANCE = 'Acepto expresamente esta versión del convenio en la demostración académica.'


def private(data, status=200):
    return Response(data, status=status, headers={'Cache-Control': 'private, no-store', 'Referrer-Policy': 'no-referrer'})


def admin_only(user):
    if not user.has_perm(ADMIN_PERMISSION):
        raise PermissionDenied()


def agreement_open(union):
    agreement = union.agreement
    today = timezone.localdate()
    return (union.state == Union.State.ACTIVE and agreement.active
            and (not agreement.starts_on or agreement.starts_on <= today)
            and (not agreement.ends_on or today <= agreement.ends_on))


def membership_for(client, *, lock=False):
    rows = UnionMembership.objects.filter(client=client, state=UnionMembership.State.ACTIVE)
    for row in rows.order_by('-changed_at', '-pk'):
        unions = Union.objects.select_for_update() if lock else Union.objects.all()
        union = unions.get(pk=row.union_id)
        if lock and not UnionMembership.objects.filter(pk=row.pk, state=UnionMembership.State.ACTIVE).exists():
            continue
        if agreement_open(union) and (row.role != 'carga' or union.agreement.allow_dependents):
            row.union = union
            return row
    return None


def representative_union(user, lock=False):
    if not user.is_authenticated or user.is_staff or user.is_superuser:
        return None
    rows = Union.objects.filter(agreement__agreementrepresentative__user=user,
                                agreement__agreementrepresentative__active=True)
    if user.get_all_permissions():
        return None
    return (rows.select_for_update() if lock else rows).first()


def summary(union):
    agreement = union.agreement
    document = union.documents.order_by('-version').first()
    return {
        'id': union.pk, 'name': agreement.name, 'identifier': union.identifier,
        'state': union.state, 'available': agreement_open(union), 'starts_on': agreement.starts_on,
        'ends_on': agreement.ends_on, 'contact_name': agreement.contact_name,
        'contact_email': agreement.contact_email, 'institutional_details': union.institutional_details,
        'allow_dependents': agreement.allow_dependents,
        'document': None if not document else {
            'id': document.pk, 'version': document.version, 'sha256': document.sha256,
            'signed_at': document.signed_at, 'signer': document.signer_name,
        },
    }


class OrganizationInput(serializers.Serializer):
    name = serializers.CharField(max_length=180)
    identifier = serializers.SlugField(max_length=40)
    institutional_details = serializers.CharField(max_length=1000, allow_blank=True)
    contact_name = serializers.CharField(max_length=150)
    contact_email = serializers.EmailField(max_length=150)
    starts_on = serializers.DateField()
    ends_on = serializers.DateField()
    allow_dependents = serializers.BooleanField(default=False)

    def validate(self, values):
        if values['ends_on'] < values['starts_on']:
            raise ValidationError('La vigencia de término no puede ser anterior al inicio.')
        return values


def existing_user(email):
    return get_user_model().objects.filter(Q(username__iexact=email) | Q(email__iexact=email)).first()


def issue_invitation(union, actor, purpose, *, user=None, membership=None):
    now = timezone.now()
    scope = AccessInvitation.objects.filter(union=union, purpose=purpose, user=user, membership=membership)
    scope.filter(used_at__isnull=True, revoked_at__isnull=True).update(revoked_at=now)
    token = secrets.token_urlsafe(32)
    invitation = AccessInvitation.objects.create(union=union, purpose=purpose, user=user, membership=membership,
                                                  digest=sha256(token.encode()).hexdigest(), created_by=actor,
                              expires_at=now + timedelta(hours=settings.UNION_INVITE_HOURS))
    audit(actor, 'Invitación individual emitida', invitation)
    return {'url': f'/app/invitacion.html#token={token}', 'expires_at': invitation.expires_at}


@api_view(['GET', 'POST'])
def organizations(request):
    admin_only(request.user)
    if request.method == 'GET':
        return private([summary(row) for row in Union.objects.select_related('agreement').order_by('agreement__name')[:200]])
    data = OrganizationInput(data=request.data)
    data.is_valid(raise_exception=True)
    values = dict(data.validated_data)
    identifier = values.pop('identifier').lower()
    details = values.pop('institutional_details')
    values['contact_email'] = values['contact_email'].lower()
    email = values['contact_email']
    if existing_user(email):
        raise ValidationError('El correo ya corresponde a una cuenta. Usa un correo institucional dedicado.')
    try:
        with transaction.atomic():
            agreement = Agreement.objects.create(**values)
            union = Union.objects.create(agreement=agreement, identifier=identifier, institutional_details=details)
            user = get_user_model().objects.create_user(username=email, email=email, first_name=agreement.contact_name, is_active=False)
            user.groups.add(Group.objects.get_or_create(name='Sindicato')[0])
            AgreementRepresentative.objects.create(user=user, agreement=agreement)
            invite = issue_invitation(union, request.user, AccessInvitation.Purpose.REPRESENTATIVE, user=user)
            audit(request.user, 'Sindicato registrado como pendiente', union)
    except IntegrityError:
        raise ValidationError('Ya existe ese nombre, identificador o correo de organización.') from None
    return private({'union': summary(union), 'invitation': invite}, 201)


class AdminAction(serializers.Serializer):
    action = serializers.ChoiceField(choices=['activate', 'suspend', 'invite'])
    reviewed = serializers.BooleanField(default=False)
    note = serializers.CharField(max_length=240, min_length=5, required=False)


class OrganizationUpdate(serializers.Serializer):
    starts_on = serializers.DateField(required=False)
    ends_on = serializers.DateField(required=False)
    institutional_details = serializers.CharField(max_length=1000, required=False, allow_blank=True)


@api_view(['POST', 'PATCH'])
@transaction.atomic
def manage_organization(request, pk):
    admin_only(request.user)
    union = get_object_or_404(Union.objects.select_for_update(), pk=pk)
    if request.method == 'PATCH':
        form = OrganizationUpdate(data=request.data)
        form.is_valid(raise_exception=True)
        values = form.validated_data
        agreement = Agreement.objects.select_for_update().get(pk=union.agreement_id)
        start = values.get('starts_on', agreement.starts_on)
        end = values.get('ends_on', agreement.ends_on)
        if start and end and end < start:
            raise ValidationError('La vigencia de término no puede ser anterior al inicio.')
        if start != agreement.starts_on or end != agreement.ends_on:
            document = union.documents.order_by('-version').first()
            if union.state != Union.State.PENDING or (document and document.signed_at):
                raise ValidationError('Asocia una versión nueva del convenio antes de modificar la vigencia aprobada.')
            agreement.starts_on, agreement.ends_on = start, end
            agreement.save(update_fields=['starts_on', 'ends_on'])
        if 'institutional_details' in values:
            union.institutional_details = values['institutional_details']
            union.save(update_fields=['institutional_details'])
        union.agreement = agreement
        audit(request.user, 'Datos administrativos del sindicato actualizados', union)
        return private(summary(union))
    form = AdminAction(data=request.data)
    form.is_valid(raise_exception=True)
    values = form.validated_data
    action = values['action']
    if action == 'invite':
        representative = get_object_or_404(AgreementRepresentative, agreement=union.agreement, active=True,
                                           user__email__iexact=union.agreement.contact_email)
        return private({'invitation': issue_invitation(union, request.user, AccessInvitation.Purpose.REPRESENTATIVE,
                                                     user=representative.user)})
    if not values.get('note'):
        raise ValidationError('Indica la referencia de revisión o suspensión.')
    if action == 'activate':
        document = union.documents.order_by('-version').first()
        if not values['reviewed'] or not document or not document.signed_at or not document_matches(document):
            raise ValidationError('Revisa el documento firmado e íntegro de la versión actual antes de activar.')
        if union.agreement.ends_on and union.agreement.ends_on < timezone.localdate():
            raise ValidationError('El convenio ha vencido.')
        union.state = Union.State.ACTIVE
        union.activated_at = timezone.now()
        union.activated_by = request.user
    else:
        union.state = Union.State.SUSPENDED
    union.review_note = values['note']
    union.save(update_fields=['state', 'activated_at', 'activated_by', 'review_note'])
    event = 'Sindicato activado tras revisión' if action == 'activate' else 'Sindicato suspendido'
    audit(request.user, event + ' · ' + values['note'], union)
    return private(summary(union))


@api_view(['POST'])
def upload_document(request, pk):
    admin_only(request.user)
    upload = request.FILES.get('file')
    if not upload or not upload.name.lower().endswith('.pdf'):
        raise ValidationError('Adjunta el PDF autorizado del convenio.')
    try:
        validate_document(upload)
    except DjangoValidationError as error:
        raise ValidationError(error.messages) from None
    checksum = sha256()
    for chunk in upload.chunks():
        checksum.update(chunk)
    upload.seek(0)
    document = None
    try:
        with transaction.atomic():
            union = get_object_or_404(Union.objects.select_for_update(), pk=pk)
            previous = union.documents.order_by('-version').first()
            document = UnionDocument(union=union, version=previous.version + 1 if previous else 1,
                                     sha256=checksum.hexdigest(), uploaded_by=request.user)
            document.file = upload
            document.save()
            union.state = Union.State.PENDING
            union.save(update_fields=['state'])
            audit(request.user, 'Versión privada de convenio incorporada', document)
    except Exception:
        if document is not None and document.file._committed and document.file.name:
            document.file.delete(save=False)
        raise
    return private(summary(union), 201)


def document_matches(document):
    checksum = sha256()
    try:
        with document.file.open('rb') as stream:
            for chunk in iter(lambda: stream.read(65536), b''):
                checksum.update(chunk)
    except OSError:
        return False
    return secrets.compare_digest(checksum.hexdigest(), document.sha256)


@api_view(['GET'])
def download_document(request, pk):
    documents = UnionDocument.objects.select_related('union')
    if not request.user.has_perm(ADMIN_PERMISSION):
        own_union = representative_union(request.user)
        if own_union is None:
            raise PermissionDenied()
        documents = documents.filter(union=own_union)
    document = get_object_or_404(documents, pk=pk)
    audit(request.user, 'Lectura de documento privado de convenio', document)
    response = FileResponse(document.file.open('rb'), as_attachment=True,
                            filename=f'convenio-version-{document.version}.pdf', content_type='application/pdf')
    response['Cache-Control'] = 'private, no-store'
    return response


@api_view(['GET'])
def portal(request):
    union = representative_union(request.user)
    if union is None:
        raise PermissionDenied()
    rows = union.memberships.all()
    counts = {state: rows.filter(state=state).count() for state in UnionMembership.State.values}
    return private({'union': summary(union), 'counts': counts, 'acceptance': ACCEPTANCE,
                    'workers': [worker_summary(row) for row in rows.order_by('-pk')[:200]]})


class SignatureInput(serializers.Serializer):
    document = serializers.IntegerField(min_value=1)
    sha256 = serializers.RegexField(r'^[a-f0-9]{64}$')
    accepted = serializers.BooleanField()


@api_view(['POST'])
@transaction.atomic
def sign_document(request):
    union = representative_union(request.user, lock=True)
    if union is None or union.state == Union.State.SUSPENDED:
        raise PermissionDenied()
    form = SignatureInput(data=request.data)
    form.is_valid(raise_exception=True)
    values = form.validated_data
    document = union.documents.order_by('-version').first()
    if (not values['accepted'] or not document or document.pk != values['document']
            or document.sha256 != values['sha256'] or document.signed_at or not document_matches(document)):
        raise ValidationError('Abre la versión actual del documento y confirma la aceptación expresa.')
    document.signed_by = request.user
    document.signed_at = timezone.now()
    document.signer_name = request.user.get_full_name() or union.agreement.contact_name
    document.organization_name = union.agreement.name
    document.acceptance = ACCEPTANCE
    document.save(update_fields=['signed_by', 'signed_at', 'signer_name', 'organization_name', 'acceptance'])
    audit(request.user, 'Aceptación electrónica simple del convenio académico', document)
    return private(summary(union))


def worker_summary(row):
    return {'id': row.pk, 'name': row.name, 'rut': row.rut, 'email': row.email,
            'phone': row.phone, 'role': row.role, 'state': row.state, 'accepted_at': row.accepted_at,
            'recovery_requested_at': row.recovery_requested_at}


class WorkerInput(serializers.Serializer):
    name = serializers.CharField(max_length=180)
    rut = serializers.CharField(max_length=18)
    email = serializers.EmailField(max_length=150)
    phone = serializers.CharField(max_length=30)
    role = serializers.ChoiceField(choices=['titular', 'carga'])

    def validate_rut(self, value):
        return normalize_rut(normalize_rut(value))

    def validate_phone(self, value):
        from .registration import RegistrationInput
        return RegistrationInput().validate_phone(value)


def worker_access(user, *, lock=False):
    union = representative_union(user, lock=lock)
    if union is None or not agreement_open(union):
        raise PermissionDenied('Esta operación requiere un sindicato habilitado y vigente.')
    return union


@api_view(['POST'])
def create_worker(request):
    form = WorkerInput(data=request.data)
    form.is_valid(raise_exception=True)
    values = form.validated_data
    values['email'] = values['email'].lower()
    try:
        with transaction.atomic():
            union = worker_access(request.user, lock=True)
            if values['role'] == 'carga' and not union.agreement.allow_dependents:
                raise ValidationError('El convenio no permite cargas familiares.')
            if union.memberships.filter(Q(rut=values['rut']) | Q(email=values['email'])).exists():
                raise ValidationError('Ya hay una vinculación para esos datos en tu organización.')
            row = union.memberships.create(**values)
            invite = issue_invitation(union, request.user, AccessInvitation.Purpose.WORKER, membership=row)
            audit(request.user, 'Solicitud de afiliación creada por el sindicato', row)
    except IntegrityError:
        raise ValidationError('Ya existe una solicitud con esos datos.') from None
    return private({'worker': worker_summary(row), 'invitation': invite}, 201)


class WorkerAction(serializers.Serializer):
    action = serializers.ChoiceField(choices=['disable', 'reissue', 'recovery', 'review', 'reset'])
    note = serializers.CharField(max_length=240, min_length=5, required=False)
    name = serializers.CharField(max_length=180, required=False)
    phone = serializers.CharField(max_length=30, required=False)


@api_view(['POST', 'PATCH'])
@transaction.atomic
def manage_worker(request, pk):
    user = request.user
    admin = user.has_perm(ADMIN_PERMISSION)
    if admin:
        ref = get_object_or_404(UnionMembership, pk=pk)
        union = Union.objects.select_for_update().get(pk=ref.union_id)
    else:
        union = representative_union(user, lock=True)
        if union is None:
            raise PermissionDenied()
    row = get_object_or_404(UnionMembership.objects.select_for_update(), union=union, pk=pk)
    if request.method == 'PATCH':
        if not agreement_open(union):
            raise PermissionDenied()
        form = WorkerAction(data={**request.data, 'action': 'review'})
        form.is_valid(raise_exception=True)
        values = form.validated_data
        for field in ('name', 'phone'):
            if field in values:
                setattr(row, field, WorkerInput().validate_phone(values[field]) if field == 'phone' else values[field])
        row.save(update_fields=['name', 'phone', 'changed_at'])
        audit(user, 'Datos administrativos de afiliación actualizados', row)
        return private(worker_summary(row))
    form = WorkerAction(data=request.data)
    form.is_valid(raise_exception=True)
    values = form.validated_data
    action = values['action']
    if action in ('review', 'reset') and not admin:
        raise PermissionDenied()
    if action not in ('disable', 'recovery') and not agreement_open(union):
        raise PermissionDenied('El convenio no está vigente.')
    if action == 'disable':
        row.state = UnionMembership.State.INACTIVE
        row.accepted_at = None
        row.verified_by = None
        row.verification_note = ''
        row.save(update_fields=['state', 'accepted_at', 'verified_by', 'verification_note', 'changed_at'])
        row.invitations.filter(used_at__isnull=True, revoked_at__isnull=True).update(revoked_at=timezone.now())
    elif action == 'reissue':
        if row.state == UnionMembership.State.ACTIVE:
            raise ValidationError('La afiliación ya está activa.')
        if row.state == UnionMembership.State.INACTIVE:
            row.state = UnionMembership.State.PENDING
            row.save(update_fields=['state', 'changed_at'])
        return private({'worker': worker_summary(row), 'invitation': issue_invitation(
            union, user, AccessInvitation.Purpose.WORKER, membership=row)})
    elif action == 'recovery':
        if not row.client_id or not row.client.user_id:
            raise ValidationError('La cuenta todavía no está asociada. Reemite su invitación.')
        row.recovery_requested_at = timezone.now()
        row.save(update_fields=['recovery_requested_at', 'changed_at'])
    elif action == 'review':
        if not values.get('note') or row.state != UnionMembership.State.PENDING or not row.client_id or not row.accepted_at:
            raise ValidationError('Se requiere la aceptación de la cuenta titular y la referencia de verificación.')
        row.verified_by = user
        row.verification_note = values['note']
        activate_membership(row)
    elif action == 'reset':
        if not values.get('note') or not row.recovery_requested_at or not row.client_id:
            raise ValidationError('Comprueba al titular por un canal independiente e indica la referencia.')
        account = row.client.user
        if not account or not safe_personal_user(account):
            raise ValidationError('No se puede recuperar la cuenta mediante esta solicitud.')
        row.recovery_requested_at = None
        row.save(update_fields=['recovery_requested_at', 'changed_at'])
        audit(user, 'Recuperación de cuenta personal verificada · ' + values['note'], row)
        return private({'invitation': issue_invitation(union, user, AccessInvitation.Purpose.RECOVERY,
                                                      user=account, membership=row)})
    audit(user, f'Afiliación sindical: {action}', row)
    return private(worker_summary(row))


def safe_personal_user(user):
    return (user.is_active and not user.is_staff and not user.is_superuser
            and not user.get_all_permissions()
            and not AgreementRepresentative.objects.filter(user=user).exists())


def activate_membership(row):
    Client.objects.select_for_update().get(pk=row.client_id)
    if UnionMembership.objects.filter(client_id=row.client_id, state=UnionMembership.State.ACTIVE).exclude(pk=row.pk).exists():
        raise ValidationError('El titular ya tiene una afiliación activa. Revisa el traslado antes de activar.')
    row.state = UnionMembership.State.ACTIVE
    row.save(update_fields=['client', 'state', 'accepted_at', 'verified_by', 'verification_note', 'changed_at'])


class ClaimInput(serializers.Serializer):
    token = serializers.RegexField(r'^[A-Za-z0-9_-]{43}$', max_length=43, write_only=True)
    password = serializers.CharField(required=False, max_length=128, trim_whitespace=False, write_only=True)
    accepted = serializers.BooleanField(default=False)


def set_password(user, password):
    try:
        validate_password(password, user)
    except DjangoValidationError as error:
        raise ValidationError({'password': error.messages}) from None
    user.set_password(password)
    user.is_active = True
    if user.pk:
        user.save(update_fields=['password', 'is_active'])
    else:
        user.save()


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
@csrf_protect
def claim(request):
    check_submission_rate(request)
    form = ClaimInput(data=request.data)
    form.is_valid(raise_exception=True)
    values = form.validated_data
    digest = sha256(values['token'].encode()).hexdigest()
    try:
        with transaction.atomic():
            ref = AccessInvitation.objects.filter(digest=digest).first()
            if ref is None:
                raise ValidationError('La invitación no está vigente.')
            union = Union.objects.select_for_update().get(pk=ref.union_id)
            invitation = AccessInvitation.objects.select_for_update().get(pk=ref.pk)
            now = timezone.now()
            if invitation.used_at or invitation.revoked_at or invitation.expires_at <= now:
                raise ValidationError('La invitación no está vigente.')
            if not values['accepted']:
                raise ValidationError('Confirma la aceptación de la invitación.')
            if invitation.purpose == AccessInvitation.Purpose.WORKER:
                outcome = accept_worker(request, union, invitation, values, now)
            else:
                account = get_user_model().objects.select_for_update().get(pk=invitation.user_id)
                if invitation.purpose == AccessInvitation.Purpose.REPRESENTATIVE:
                    permitted = (not account.is_staff and not account.is_superuser and not account.get_all_permissions()
                                 and AgreementRepresentative.objects.filter(user=account, agreement=union.agreement, active=True).exists())
                else:
                    permitted = (safe_personal_user(account) and
                                 UnionMembership.objects.filter(pk=invitation.membership_id, union=union, client__user=account).exists())
                if not permitted or (request.user.is_authenticated and request.user.pk != account.pk):
                    raise PermissionDenied()
                set_password(account, values.get('password', ''))
                outcome = 'activated'
            invitation.used_at = now
            invitation.save(update_fields=['used_at'])
            audit(request.user, 'Invitación individual utilizada', invitation)
    except IntegrityError:
        raise ValidationError('La cuenta cambió durante la activación. Solicita revisión antes de reintentar.') from None
    return private({'state': outcome})


def accept_worker(request, union, invitation, values, now):
    if not agreement_open(union):
        raise PermissionDenied('El sindicato no está habilitado o su convenio no está vigente.')
    row = get_object_or_404(UnionMembership.objects.select_for_update(), pk=invitation.membership_id, union=union)
    if row.state != UnionMembership.State.PENDING or (row.role == 'carga' and not union.agreement.allow_dependents):
        raise PermissionDenied()
    client = Client.objects.select_for_update().filter(rut=row.rut).first()
    if client:
        if (not client.active or not request.user.is_authenticated or client.user_id != request.user.pk
                or not safe_personal_user(request.user)):
            raise PermissionDenied('Si ya tienes ficha, ingresa con tu cuenta personal antes de aceptar. Si aún no tienes acceso, solicita la verificación de tu ficha.')
        row.client = client
        row.accepted_at = now
        row.save(update_fields=['client', 'accepted_at', 'changed_at'])
        return 'review'
    if request.user.is_authenticated:
        raise PermissionDenied('Cierra la sesión para crear el acceso de un titular nuevo.')
    if existing_user(row.email) or ClientRegistration.objects.filter(Q(rut=row.rut) | Q(email=row.email)).exists():
        raise ValidationError('La invitación requiere una revisión de identidad por Ópticas Amaru.')
    account = get_user_model()(username=row.email, email=row.email, first_name=row.name[:150])
    set_password(account, values.get('password', ''))
    account.groups.add(Group.objects.get_or_create(name='Cliente')[0])
    row.client = Client.objects.create(rut=row.rut, name=row.name, email=row.email, phone=row.phone,
                                       category='particular', user=account)
    row.accepted_at = now
    row.verified_by = invitation.created_by
    activate_membership(row)
    return 'activated'


class PasswordInput(serializers.Serializer):
    current = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)


@api_view(['POST'])
def account(request):
    if representative_union(request.user) is None:
        raise PermissionDenied()
    check_submission_rate(request)
    form = PasswordInput(data=request.data)
    form.is_valid(raise_exception=True)
    if not request.user.check_password(form.validated_data['current']):
        raise ValidationError('La contraseña actual no es válida.')
    set_password(request.user, form.validated_data['password'])
    update_session_auth_hash(request, request.user)
    audit(request.user, 'Contraseña institucional actualizada', representative_union(request.user))
    return private({'detail': 'Contraseña actualizada.'})


@api_view(['GET'])
def admin_workers(request, pk):
    admin_only(request.user)
    union = get_object_or_404(Union.objects.select_related('agreement'), pk=pk)
    return private({'union': summary(union),
                    'workers': [worker_summary(row) for row in union.memberships.order_by('-pk')[:200]]})


@api_view(['GET'])
def review_queue(request):
    admin_only(request.user)
    rows = UnionMembership.objects.filter(
        Q(state=UnionMembership.State.PENDING, accepted_at__isnull=False) | Q(recovery_requested_at__isnull=False)
    ).select_related('union__agreement').order_by('-changed_at')[:200]
    return private([{**worker_summary(row), 'organization': row.union.agreement.name} for row in rows])
