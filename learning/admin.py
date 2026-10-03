"""Django admin for self-learning models."""
from django.contrib import admin

from learning.models import (
    FineTuningRun,
    KeywordAnomaly,
    KeywordDictionaryEntry,
    KeywordDictionaryVersion,
    KeywordObservation,
)


@admin.register(KeywordObservation)
class KeywordObservationAdmin(admin.ModelAdmin):
    list_display = ("term", "category", "region", "observed_on", "source", "video")
    list_filter = ("source", "category", "region")
    search_fields = ("term", "region")
    date_hierarchy = "observed_on"
    raw_id_fields = ("video",)


@admin.register(KeywordAnomaly)
class KeywordAnomalyAdmin(admin.ModelAdmin):
    list_display = (
        "term", "region", "observed_on", "pct_change", "z_score",
        "current_count", "baseline_avg", "severity", "status",
    )
    list_filter = ("severity", "status", "region")
    search_fields = ("term", "region")
    date_hierarchy = "observed_on"


@admin.register(KeywordDictionaryEntry)
class KeywordDictionaryEntryAdmin(admin.ModelAdmin):
    list_display = (
        "term",
        "category",
        "status",
        "added_automatically",
        "confirmation_count",
        "added_at",
    )
    list_filter = ("category", "status", "added_automatically")
    search_fields = ("term", "reviewed_by__username")
    raw_id_fields = ("reviewed_by",)
    date_hierarchy = "added_at"


@admin.register(KeywordDictionaryVersion)
class KeywordDictionaryVersionAdmin(admin.ModelAdmin):
    list_display = ("id", "note", "created_at")
    search_fields = ("note",)
    date_hierarchy = "created_at"


@admin.register(FineTuningRun)
class FineTuningRunAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "status",
        "is_active",
        "training_examples_count",
        "precision",
        "recall",
        "false_positive_rate",
        "started_at",
        "completed_at",
    )
    list_filter = ("status", "is_active")
    readonly_fields = ("model_artifact",)
    date_hierarchy = "started_at"
