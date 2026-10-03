"""Django admin for incident models.

Extracted artifacts and evidence entries are shown inline on the incident.
Evidence entries are append-only, so they are read-only in the admin (the
model's save() override would otherwise reject edits).
"""
from django.contrib import admin

from incidents.models import (
    EvidenceChainEntry,
    Incident,
    PromoCode,
    TelegramLink,
)


class EvidenceChainEntryInline(admin.TabularInline):
    model = EvidenceChainEntry
    extra = 0
    can_delete = False
    fields = ("file_type", "file_path", "sha256_hash", "collected_at", "collection_method")
    readonly_fields = fields

    def has_change_permission(self, request, obj=None):
        # Append-only: never allow edits through the admin.
        return False


class PromoCodeInline(admin.TabularInline):
    model = PromoCode
    extra = 0
    fields = ("code", "extracted_from")


class TelegramLinkInline(admin.TabularInline):
    model = TelegramLink
    extra = 0
    fields = ("url", "extracted_from")


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ("video", "status", "risk_score", "priority_score", "created_at")
    list_filter = ("status",)
    search_fields = ("video__external_id", "summary_text")
    list_select_related = ("video", "deep_analysis_result")
    raw_id_fields = ("video", "deep_analysis_result")
    date_hierarchy = "created_at"
    inlines = (PromoCodeInline, TelegramLinkInline, EvidenceChainEntryInline)


@admin.register(EvidenceChainEntry)
class EvidenceChainEntryAdmin(admin.ModelAdmin):
    list_display = ("incident", "file_type", "sha256_hash", "collected_at")
    list_filter = ("file_type",)
    search_fields = ("sha256_hash", "file_path")
    raw_id_fields = ("incident",)
    readonly_fields = (
        "incident", "file_type", "file_path", "sha256_hash",
        "collected_at", "collection_method",
    )

    def has_change_permission(self, request, obj=None):
        # Allow viewing the detail page but never editing.
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "incident", "extracted_from")
    list_filter = ("extracted_from",)
    search_fields = ("code",)
    raw_id_fields = ("incident",)


@admin.register(TelegramLink)
class TelegramLinkAdmin(admin.ModelAdmin):
    list_display = ("url", "incident", "extracted_from")
    list_filter = ("extracted_from",)
    search_fields = ("url",)
    raw_id_fields = ("incident",)
