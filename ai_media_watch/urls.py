"""
Root URL configuration for AI Media Watch.

Domain endpoints are intentionally absent at this stage — each app will wire
its own routes here in later prompts. For now we expose the admin and the
health-check.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    # Health-check and other shared endpoints live in the `core` app.
    path("api/", include("core.urls")),
    # Authentication (login/refresh/logout/me) for the internal frontend.
    path("api/auth/", include("accounts.urls")),
    # Analyst queue (list + stats).
    path("api/incidents/", include("incidents.urls")),
    # Cross-platform connection graph + autocomplete.
    path("api/connections/", include("incidents.connection_urls")),
    # Leadership trends dashboard (analyst only).
    path("api/dashboard/", include("incidents.dashboard_urls")),
    # External bank API (API-key auth only).
    path("api/bank/v1/", include("bankapi.urls")),
    # Video ingestion (submit URL + poll status).
    path("api/ingestion/", include("ingestion.urls")),
    path("api/learning/", include("learning.urls")),
    path("api/screening/", include("screening.urls")),
]

# Serve captured media (live chunks, frames) in development so the live console
# can play the actual analysed segments. In production a real web server / CDN
# serves MEDIA_ROOT instead.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
