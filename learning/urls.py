from django.urls import path
from .views import (
    ActiveRiskModelView,
    DictionaryReviewView,
    DictionaryRollbackView,
    DictionaryVersionListView,
    FineTuningRunListView,
    PendingDictionaryEntriesView,
    PredictIncidentRiskView,
    TrainRiskModelView,
)

urlpatterns = [
    path('dictionary/pending/', PendingDictionaryEntriesView.as_view(), name='dictionary-pending'),
    path('dictionary/versions/', DictionaryVersionListView.as_view(), name='dictionary-versions'),
    path('dictionary/<int:entry_id>/review/', DictionaryReviewView.as_view(), name='dictionary-review'),
    path('dictionary/rollback/<int:version_id>/', DictionaryRollbackView.as_view(), name='dictionary-rollback'),
    path('finetuning-runs/', FineTuningRunListView.as_view(), name='finetuning-runs'),
    path('model/train/', TrainRiskModelView.as_view(), name='model-train'),
    path('model/active/', ActiveRiskModelView.as_view(), name='model-active'),
    path('model/predict/<int:incident_id>/', PredictIncidentRiskView.as_view(), name='model-predict'),
]
