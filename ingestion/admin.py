"""Django admin registrations for ingestion models.

Configured for manual data debugging during the hackathon: useful columns,
filters and search fields on each entity.
"""
from django.contrib import admin

from ingestion.models import Platform, SocialAccount, Video, VideoComment


@admin.register(Platform)
class PlatformAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "color", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "code")


@admin.register(SocialAccount)
class SocialAccountAdmin(admin.ModelAdmin):
    list_display = (
        "username",
        "platform",
        "followers_count",
        "is_watchlisted",
        "last_seen_at",
    )
    list_filter = ("platform", "is_watchlisted")
    search_fields = ("username", "display_name", "external_id", "profile_description")
    list_select_related = ("platform",)
    date_hierarchy = "last_seen_at"


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = (
        "external_id",
        "platform",
        "social_account",
        "download_status",
        "posted_at",
        "collected_at",
    )
    list_filter = ("platform", "download_status", "posted_at")
    search_fields = ("external_id", "caption", "url", "social_account__username")
    list_select_related = ("platform", "social_account")
    date_hierarchy = "posted_at"
    raw_id_fields = ("social_account",)


@admin.register(VideoComment)
class VideoCommentAdmin(admin.ModelAdmin):
    list_display = (
        "video",
        "author",
        "is_pinned",
        "contains_suspicious_link",
        "posted_at",
    )
    list_filter = ("is_pinned", "contains_suspicious_link")
    search_fields = ("author", "text", "video__external_id")
    raw_id_fields = ("video",)
