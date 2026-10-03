"""Analyst-queue and incident-card routes."""
from django.urls import path

from incidents.views import (
    IncidentDecisionView,
    IncidentDetailView,
    IncidentDossierView,
    IncidentEvidenceChainView,
    IncidentListView,
    IncidentReasoningGraphView,
    IncidentStatsView,
)

app_name = "incidents"

urlpatterns = [
    path("", IncidentListView.as_view(), name="list"),
    path("stats/", IncidentStatsView.as_view(), name="stats"),
    path("<int:pk>/", IncidentDetailView.as_view(), name="detail"),
    path("<int:pk>/decision/", IncidentDecisionView.as_view(), name="decision"),
    path("<int:pk>/dossier/", IncidentDossierView.as_view(), name="dossier"),
    path(
        "<int:pk>/evidence-chain/",
        IncidentEvidenceChainView.as_view(),
        name="evidence-chain",
    ),
    path(
        "<int:pk>/reasoning-graph/",
        IncidentReasoningGraphView.as_view(),
        name="reasoning-graph",
    ),
]
