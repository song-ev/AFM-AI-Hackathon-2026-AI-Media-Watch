"""Ingestion routes (mounted at /api/ingestion/)."""
from django.urls import path

from ingestion.views import (
    BatchDetailView,
    BatchListView,
    BulkSubmitView,
    CapabilitiesView,
    FolderIngestView,
    LiveDetailView,
    LiveListView,
    LiveStartView,
    ParseSourceView,
    VideoStatusView,
    VideoSubmitView,
    VideoUploadView,
)

app_name = "ingestion"

urlpatterns = [
    path("videos/", VideoSubmitView.as_view(), name="video-submit"),
    path("videos/upload/", VideoUploadView.as_view(), name="video-upload"),
    path("videos/<int:pk>/status/", VideoStatusView.as_view(), name="video-status"),
    # Batch / continuous ingestion.
    path("capabilities/", CapabilitiesView.as_view(), name="capabilities"),
    path("bulk/", BulkSubmitView.as_view(), name="bulk-submit"),
    path("parse/", ParseSourceView.as_view(), name="parse-source"),
    path("folder/", FolderIngestView.as_view(), name="folder-ingest"),
    path("batches/", BatchListView.as_view(), name="batch-list"),
    path("batches/<int:pk>/", BatchDetailView.as_view(), name="batch-detail"),
    # Live-stream monitoring (эфиры).
    path("live/", LiveStartView.as_view(), name="live-start"),
    path("live/list/", LiveListView.as_view(), name="live-list"),
    path("live/<int:pk>/", LiveDetailView.as_view(), name="live-detail"),
]
