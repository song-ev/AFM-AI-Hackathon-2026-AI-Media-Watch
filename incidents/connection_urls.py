"""Connection-graph routes (mounted at /api/connections/)."""
from django.urls import path

from incidents.connection_views import ConnectionGraphView, ConnectionSearchView

app_name = "connections"

urlpatterns = [
    path("graph/", ConnectionGraphView.as_view(), name="graph"),
    path("search/", ConnectionSearchView.as_view(), name="search"),
]
