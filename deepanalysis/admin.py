"""Django admin for deep-analysis models.

The reasoning graph, transcripts and screenshot detections are shown inline on
the DeepAnalysisResult for convenient manual inspection; transcript flags are
inline on the transcript. Identity fingerprints carry their links inline.
"""
from django.contrib import admin

from deepanalysis.models import (
    DeepAnalysisResult,
    FakeScreenshotDetection,
    IdentityFingerprint,
    IdentityLink,
    ReasoningEdge,
    ReasoningNode,
    Transcript,
    TranscriptFlag,
)


# --- Inlines for DeepAnalysisResult -----------------------------------------
class TranscriptInline(admin.TabularInline):
    model = Transcript
    extra = 0
    fields = ("language", "full_text")


class FakeScreenshotDetectionInline(admin.TabularInline):
    model = FakeScreenshotDetection
    extra = 0
    fields = ("frame_timestamp_sec", "bank_name", "is_fake", "confidence")


class ReasoningNodeInline(admin.TabularInline):
    model = ReasoningNode
    extra = 0
    fields = ("node_key", "node_type", "status", "score_contribution", "label")


class ReasoningEdgeInline(admin.TabularInline):
    model = ReasoningEdge
    extra = 0
    fields = ("from_node", "to_node", "weight")
    raw_id_fields = ("from_node", "to_node")


@admin.register(DeepAnalysisResult)
class DeepAnalysisResultAdmin(admin.ModelAdmin):
    list_display = ("video", "status", "risk_score", "processing_time_ms", "started_at")
    list_filter = ("status",)
    search_fields = ("video__external_id",)
    list_select_related = ("video",)
    raw_id_fields = ("video",)
    date_hierarchy = "started_at"
    inlines = (
        TranscriptInline,
        FakeScreenshotDetectionInline,
        ReasoningNodeInline,
        ReasoningEdgeInline,
    )


# --- Transcript & flags ------------------------------------------------------
class TranscriptFlagInline(admin.TabularInline):
    model = TranscriptFlag
    extra = 0
    fields = ("phrase", "category", "severity", "start_sec", "end_sec")


@admin.register(Transcript)
class TranscriptAdmin(admin.ModelAdmin):
    list_display = ("deep_analysis_result", "language", "created_at")
    list_filter = ("language",)
    search_fields = ("full_text", "deep_analysis_result__video__external_id")
    raw_id_fields = ("deep_analysis_result",)
    inlines = (TranscriptFlagInline,)


@admin.register(TranscriptFlag)
class TranscriptFlagAdmin(admin.ModelAdmin):
    list_display = ("transcript", "category", "severity", "start_sec", "end_sec")
    list_filter = ("category",)
    search_fields = ("phrase",)
    raw_id_fields = ("transcript",)


@admin.register(FakeScreenshotDetection)
class FakeScreenshotDetectionAdmin(admin.ModelAdmin):
    list_display = ("deep_analysis_result", "bank_name", "is_fake", "confidence")
    list_filter = ("is_fake", "bank_name")
    search_fields = ("bank_name",)
    raw_id_fields = ("deep_analysis_result",)


# --- Identity ----------------------------------------------------------------
class IdentityLinkInline(admin.TabularInline):
    model = IdentityLink
    extra = 0
    fields = ("social_account", "video", "linked_at")
    raw_id_fields = ("social_account", "video")


@admin.register(IdentityFingerprint)
class IdentityFingerprintAdmin(admin.ModelAdmin):
    list_display = ("fingerprint_type", "embedding_hash", "confidence", "created_at")
    list_filter = ("fingerprint_type",)
    search_fields = ("embedding_hash",)
    inlines = (IdentityLinkInline,)


@admin.register(IdentityLink)
class IdentityLinkAdmin(admin.ModelAdmin):
    list_display = ("identity_fingerprint", "social_account", "video", "linked_at")
    search_fields = ("social_account__username",)
    raw_id_fields = ("identity_fingerprint", "social_account", "video")


# --- Reasoning graph ---------------------------------------------------------
@admin.register(ReasoningNode)
class ReasoningNodeAdmin(admin.ModelAdmin):
    list_display = ("node_key", "deep_analysis_result", "node_type", "status",
                    "score_contribution")
    list_filter = ("node_type", "status")
    search_fields = ("node_key", "label")
    raw_id_fields = ("deep_analysis_result",)


@admin.register(ReasoningEdge)
class ReasoningEdgeAdmin(admin.ModelAdmin):
    list_display = ("deep_analysis_result", "from_node", "to_node", "weight")
    search_fields = ("from_node__node_key", "to_node__node_key")
    raw_id_fields = ("deep_analysis_result", "from_node", "to_node")
