"""Solicitudes de catálogo vinculadas a la cuenta y a una receta privada."""
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from .models import Client, Inquiry, Prescription, Product
from .serializers import PrescriptionSerializer
from .services import audit


def own_client(user):
    client = Client.objects.filter(user=user, active=True).first()
    if client is None:
        raise PermissionDenied("Se requiere una cuenta vinculada a una ficha activa.")
    return client


@api_view(["GET", "POST"])
def my_prescriptions(request):
    client = own_client(request.user)
    if request.method == "GET":
        recipes = client.prescriptions.order_by("-issued_on", "-pk")[:100]
        return Response(PrescriptionSerializer([p for p in recipes if p.valid], many=True).data)
    data = {"client": client.pk, "issued_on": request.data.get("issued_on"), "file": request.FILES.get("file")}
    serializer = PrescriptionSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    with transaction.atomic():
        recipe = serializer.save(actor=request.user)
        audit(request.user, "Receta privada cargada por cliente", recipe)
    return Response(PrescriptionSerializer(recipe).data, status=201)


class ProductRequestInput(serializers.Serializer):
    product = serializers.IntegerField(min_value=1)
    prescription = serializers.IntegerField(min_value=1, required=False)
    reason = serializers.CharField(max_length=2000, min_length=5)
    contact_authorized = serializers.BooleanField()
    idempotency_key = serializers.UUIDField()


@api_view(["POST"])
def request_product(request):
    client = own_client(request.user)
    form = ProductRequestInput(data=request.data)
    form.is_valid(raise_exception=True)
    values = form.validated_data
    if not values["contact_authorized"]:
        raise ValidationError("Autoriza el contacto para gestionar esta solicitud.")
    with transaction.atomic():
        from .membership import verified_agreement
        agreement = verified_agreement(client, lock=True)
        client = Client.objects.select_for_update().get(pk=client.pk)
        if not client.active or client.user_id != request.user.pk:
            raise PermissionDenied()
        product = get_object_or_404(Product.objects.select_for_update(), pk=values["product"], active=True)
        if product.mining_only and not (agreement and hasattr(agreement, 'union')):
            raise PermissionDenied('Se requiere una afiliación sindical vigente para este producto.')
        recipe = None
        if values.get("prescription"):
            recipe = get_object_or_404(Prescription, pk=values["prescription"], client=client)
            if not recipe.valid or not recipe.file:
                raise ValidationError({"prescription": "Selecciona una receta vigente con un archivo privado."})
        if product.requires_prescription and recipe is None:
            raise ValidationError({"prescription": "Este producto requiere una receta vigente."})
        inquiry, created = Inquiry.objects.get_or_create(idempotency_key=values["idempotency_key"], defaults={
            "kind": "lentes", "client": client, "product": product, "prescription": recipe, "agreement": agreement,
            "name": client.name, "email": client.email, "phone": client.phone,
            "service": "Solicitud de producto", "reason": values["reason"],
            "contact_authorized": True, "actor": request.user,
        })
        if not created and (inquiry.client_id != client.pk or inquiry.product_id != product.pk
            or inquiry.prescription_id != (recipe.pk if recipe else None) or inquiry.reason != values["reason"]):
            raise ValidationError("La referencia ya fue utilizada para otro envío.")
        if created:
            audit(request.user, "Solicitud de catálogo para revisión", inquiry)
    return Response({"reference": inquiry.token, "created": created}, status=201 if created else 200)
