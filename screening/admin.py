"""Django admin for screening models — signals shown inline on the result."""
from django.contrib import admin

from screening.models import ScreeningResult, ScreeningSignal


class ScreeningSignalInline(admin.TabularInline):
    model = ScreeningSignal
    extra = 0
    fields = ("module", "is_triggered", "confidence", "detected_at_timestamp_sec")


@admin.register(ScreeningResult)
class ScreeningResultAdmin(admin.ModelAdmin):
    list_display = ("video", "status", "processing_time_ms", "triggered_at")
    list_filter = ("status",)
    search_fields = ("video__external_id",)
    list_select_related = ("video",)
    raw_id_fields = ("video",)
    date_hierarchy = "triggered_at"
    inlines = (ScreeningSignalInline,)


@admin.register(ScreeningSignal)
class ScreeningSignalAdmin(admin.ModelAdmin):
    list_display = ("screening_result", "module", "is_triggered", "confidence")
    list_filter = ("module", "is_triggered")
    search_fields = ("screening_result__video__external_id",)
    list_select_related = ("screening_result",)
    raw_id_fields = ("screening_result",)
