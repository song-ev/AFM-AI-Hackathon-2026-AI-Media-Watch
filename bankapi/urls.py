"""Bank API routes (mounted at /api/bank/v1/)."""
from django.urls import path

from bankapi.views import BankHealthView, BankRiskCheckView

app_name = "bankapi"

urlpatterns = [
    path("risk-check/", BankRiskCheckView.as_view(), name="risk-check"),
    path("health/", BankHealthView.as_view(), name="health"),
]
