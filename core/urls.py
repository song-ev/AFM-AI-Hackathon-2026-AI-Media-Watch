"""Core app URLs — shared, cross-cutting endpoints."""
from django.urls import path

from core.views import HealthCheckView

app_name = "core"

urlpatterns = [
    path("health/", HealthCheckView.as_view(), name="health"),
]
