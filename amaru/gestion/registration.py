"""Registro público y activación por verificación administrativa."""
from collections.abc import Mapping
import re
import secrets
import time

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.views.decorators.csrf import csrf_protect
from rest_framework import permissions, serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .catalog_requests import own_client
from .membership import verified_agreement
from .models import Client, ClientRegistration
from .services import audit, record_consent
from .validators import normalize_rut

PRIVACY_VERSION = 'academica-1'
CHALLENGE_SALT = 'gestion.client_registration.v1'
REVIEW_PERMISSION = 'gestion.change_clientregistration'
PENDING_MESSAGE = (
    'Si los datos pueden procesarse, la cuenta queda pendiente de revisión. '
    'El equipo debe verificar tu correo e identidad antes de habilitar el acceso. '
    'Este sitio no envía correos automáticos de activación.'
)


class RegistrationInput(serializers.Serializer):
    name = serializers.CharField(max_length=180)
    rut = serializers.CharField(max_length=18)
    email = serializers.EmailField(max_length=150)
    phone = serializers.CharField(max_length=30)
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)
    password_confirmation = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)
    privacy = serializers.BooleanField()
    privacy_version = serializers.CharField(max_length=24)
    promotions = serializers.BooleanField(default=False)
    challenge = serializers.CharField(max_length=300)
    website = serializers.CharField(max_length=100, allow_blank=True, required=False)

    def validate_name(self, value):
        if len(value.split()) < 2:
            raise serializers.ValidationError('Ingresa tu nombre y apellido.')
        return ' '.join(value.split())

    def validate_rut(self, value):
        return normalize_rut(normalize_rut(value))

    def validate_email(self, value):
        return value.lower()

    def validate_phone(self, value):
        digits = re.sub(r'[^0-9]', '', value)
        if (not re.fullmatch(r'\+?[0-9 ()-]+', value)
                or len(digits) not in (9, 11)
                or (len(digits) == 11 and not digits.startswith('56'))
                or (value.startswith('+') and len(digits) != 11)):
            raise serializers.ValidationError('Ingresa un teléfono chileno de 9 dígitos, con +56 opcional.')
        return '+56' + digits[-9:]

    def validate(self, data):
        if not data['privacy'] or data['privacy_version'] != PRIVACY_VERSION:
            raise serializers.ValidationError({'privacy': 'Lee y acepta la política de privacidad vigente.'})
        if data['password'] != data['password_confirmation']:
            raise serializers.ValidationError({'password_confirmation': 'Las contraseñas no coinciden.'})
        candidate = get_user_model()(username=data['email'], email=data['email'], first_name=data['name'][:150])
        try:
            validate_password(data['password'], candidate)
        except ValidationError as exc:
            raise serializers.ValidationError({'password': exc.messages}) from exc
        return data


def challenge_valid(token):
    if not isinstance(token, str) or len(token) > 300:
        return False
    try:
        payload = signing.loads(token, salt=CHALLENGE_SALT, max_age=3600)
        return time.time() - payload['issued'] >= 2
    except (signing.BadSignature, KeyError, TypeError):
        return False


def registration_exists(email, rut):
    return (
        ClientRegistration.objects.filter(Q(email=email) | Q(rut=rut)).exists()
        or get_user_model().objects.filter(Q(email__iexact=email) | Q(username__iexact=email)).exists()
    )


def create_pending(data):
    email, rut = data['email'], data['rut']
    if registration_exists(email, rut):
        return
    try:
        with transaction.atomic():
            user = get_user_model().objects.create_user(
                username=email, email=email, first_name=data['name'][:150],
                password=data['password'], is_active=False,
            )
            registration = ClientRegistration.objects.create(
                user=user, rut=rut, email=email, name=data['name'], phone=data['phone'],
                privacy_version=PRIVACY_VERSION, promotions=data['promotions'],
            )
            audit(None, 'Solicitud pública de cuenta de cliente', registration)
    except IntegrityError:
        # Una petición concurrente puede haber reservado el RUT o correo.
        if not registration_exists(email, rut):
            raise


@api_view(['GET', 'POST'])
@permission_classes([permissions.AllowAny])
@csrf_protect
def register(request):
    if request.method == 'GET':
        result = Response({
            'challenge': signing.dumps({'issued': time.time(), 'nonce': secrets.token_urlsafe(16)}, salt=CHALLENGE_SALT),
            'privacy_version': PRIVACY_VERSION,
        })
    else:
        key = 'signup:' + salted_hmac(CHALLENGE_SALT, request.META.get('REMOTE_ADDR', '')).hexdigest()
        if cache.add(key, 1, 900):
            attempts = 1
        else:
            try:
                attempts = cache.incr(key)
            except ValueError:
                cache.add(key, 1, 900)
                attempts = 1
        if attempts > 10:
            return Response({'detail': 'Demasiados intentos. Inténtalo de nuevo en 15 minutos.'},
                            status=429, headers={'Retry-After': '900'})
        if request.user.is_authenticated:
            return Response({'detail': 'Cierra la sesión antes de solicitar otra cuenta.'}, status=403)
        if (not isinstance(request.data, Mapping) or request.data.get('website')
                or not challenge_valid(request.data.get('challenge'))):
            return Response({'detail': 'No se pudo validar el formulario. Vuelve a intentarlo.'}, status=400)
        form = RegistrationInput(data=request.data)
        form.is_valid(raise_exception=True)
        create_pending(form.validated_data)
        result = Response({'detail': PENDING_MESSAGE}, status=202)
    result['Cache-Control'] = 'no-store'
    return result


@transaction.atomic
def approve_registration(registration_id, reviewer, *, email_verified, identity_verified, note):
    if not reviewer.is_active or not reviewer.is_staff or not reviewer.has_perm(REVIEW_PERMISSION):
        raise PermissionDenied
    note = note.strip()
    if not (email_verified and identity_verified and 5 <= len(note) <= 240):
        raise ValidationError('Confirma ambas verificaciones e indica una referencia interna breve.')
    registration = ClientRegistration.objects.select_for_update().get(pk=registration_id)
    if registration.approved_at:
        raise ValidationError('Esta cuenta ya fue activada.')
    user = get_user_model().objects.select_for_update().get(pk=registration.user_id)
    if (user.is_active or user.is_staff or user.is_superuser or user.groups.exists()
            or user.user_permissions.exists() or user.username != registration.email
            or user.email != registration.email or not user.has_usable_password()):
        raise ValidationError('La cuenta pendiente tiene cambios que requieren revisión separada.')

    client = Client.objects.select_for_update().filter(rut=registration.rut).first()
    if (client and (client.user_id or not client.active)) or Client.objects.filter(user=user).exists():
        raise ValidationError('No se puede vincular la ficha: está inactiva, ya tiene cuenta o hay un vínculo previo.')
    if client:
        # No cambia el contacto, los convenios ni las preferencias históricas.
        client.user = user
        client.save(update_fields=['user', 'updated_at'])
        audit(reviewer, 'Vinculación de ficha tras verificar identidad', client)
    else:
        client = Client.objects.create(
            rut=registration.rut, name=registration.name, phone=registration.phone,
            email=registration.email, category='particular', user=user,
        )
        record_consent(client, reviewer)

    registration.approved_at = timezone.now()
    registration.approved_by = reviewer
    registration.verification_note = note
    registration.save(update_fields=['approved_at', 'approved_by', 'verification_note'])
    user.is_active = True
    user.save(update_fields=['is_active'])
    from django.contrib.auth.models import Group
    user.groups.add(Group.objects.get_or_create(name='Cliente')[0])
    audit(reviewer, 'Activación de cuenta con correo e identidad verificados', registration)
    return client


@api_view(['GET'])
def my_account(request):
    client = own_client(request.user)
    agreement = verified_agreement(client)
    from .models import Quote
    from .unions import agreement_open
    memberships = client.union_memberships.select_related('union__agreement').order_by('-changed_at')[:30]
    quotes = Quote.objects.filter(client=client).order_by('-pk')[:50]
    # Solo el estado de solicitudes creadas desde esta cuenta, no formularios anónimos que citan el RUT.
    inquiries = client.inquiries.filter(actor=request.user).order_by('-created_at', '-pk')[:50]
    result = Response({
        'inquiries': [
            {'reference': row.token, 'kind': row.get_kind_display(), 'status': row.status, 'created_at': row.created_at}
            for row in inquiries
        ],
        'agreement': str(agreement) if agreement else None,
        'memberships': [{'organization': row.union.agreement.name, 'state': row.state,
                         'role': row.role, 'available': row.state == 'active' and agreement_open(row.union)
                         and (row.role != 'carga' or row.union.agreement.allow_dependents)} for row in memberships],
        'quotes': [{'folio': row.folio, 'amount': row.amount, 'approved': row.approved} for row in quotes],
    })
    result['Cache-Control'] = 'no-store'
    return result
