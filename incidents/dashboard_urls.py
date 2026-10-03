"""Leadership dashboard routes (mounted at /api/dashboard/)."""
from django.urls import path

from incidents.dashboard_views import (
    GeographyView,
    GeoPointsView,
    KeywordAnomaliesView,
    KeywordTrendsView,
    RoiView,
    TrendsView,
)

app_name = "dashboard"

urlpatterns = [
    path("trends/", TrendsView.as_view(), name="trends"),
    path("geography/", GeographyView.as_view(), name="geography"),
    path("geo-points/", GeoPointsView.as_view(), name="geo-points"),
    path("keyword-trends/", KeywordTrendsView.as_view(), name="keyword-trends"),
    path("keyword-anomalies/", KeywordAnomaliesView.as_view(), name="keyword-anomalies"),
    path("roi/", RoiView.as_view(), name="roi"),
]
