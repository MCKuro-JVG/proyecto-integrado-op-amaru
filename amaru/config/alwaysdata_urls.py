"""Interfaz académica y API existentes con los permisos de Django."""
from django.http import HttpResponse
from django.urls import path
from django.views.generic import RedirectView
from .urls import urlpatterns as application_urls
from gestion.health import health


def robots(request):
    return HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain")


urlpatterns = [
    path("", RedirectView.as_view(url="/app/", permanent=False)),
    path("healthz/", health),
    path("robots.txt", robots),
    *application_urls,
]
