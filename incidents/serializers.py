"""Serializers for the analyst queue (list) and the incident detail card."""
from rest_framework import serializers

from accounts.models import AnalystLabel
from deepanalysis.models import FakeScreenshotDetection
from incidents.models import (
    EvidenceChainEntry,
    Incident,
    PromoCode,
    TelegramLink,
)
from ingestion.models import Platform, SocialAccount, Video

CAPTION_PREVIEW_LEN = 100


# ---------------------------------------------------------------------------
# Shared / compact (list view, C1)
# ---------------------------------------------------------------------------
class VideoCompactSerializer(serializers.ModelSerializer):
    """Minimal video fields for a list row."""

    platform = serializers.CharField(source="platform.code", read_only=True)
    caption = serializers.SerializerMethodField()

    class Meta:
        model = Video
        fields = ("thumbnail_url", "platform", "posted_at", "caption")

    def get_caption(self, obj):
        caption = obj.caption or ""
        if len(caption) > CAPTION_PREVIEW_LEN:
            return caption[:CAPTION_PREVIEW_LEN].rstrip() + "…"
        return caption


class SocialAccountCompactSerializer(serializers.ModelSerializer):
    class Meta:
        model = SocialAccount
        fields = ("username", "followers_count")


class IncidentListSerializer(serializers.ModelSerializer):
    """Compact incident representation for the queue list."""

    video = VideoCompactSerializer(read_only=True)
    social_account = SocialAccountCompactSerializer(
        source="video.social_account", read_only=True
    )

    class Meta:
        model = Incident
        fields = (
            "id",
            "video",
            "social_account",
            "risk_score",
            "priority_score",
            "status",
            "created_at",
        )


# ---------------------------------------------------------------------------
# Detail card (C2)
# ---------------------------------------------------------------------------
class PlatformSerializer(serializers.ModelSerializer):
    class Meta:
        model = Platform
        fields = ("code", "name", "color", "icon")


class VideoDetailSerializer(serializers.ModelSerializer):
    """Full video data, including the fields the player needs."""

    platform = PlatformSerializer(read_only=True)

    class Meta:
        model = Video
        fields = (
            "id",
            "external_id",
            "url",
            "local_file_path",
            "thumbnail_url",
            "caption",
            "hashtags",
            "posted_at",
            "duration_seconds",
            "download_status",
            "source_hash",
            "collected_at",
            "platform",
        )


class SocialAccountDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = SocialAccount
        fields = (
            "id",
            "external_id",
            "username",
            "display_name",
            "followers_count",
            "profile_url",
            "profile_description",
            "linktree_url",
            "is_watchlisted",
            "watchlist_reason",
        )


class TranscriptFlagSerializer(serializers.Serializer):
    """A suspicious phrase flagged on the timeline."""

    phrase = serializers.CharField()
    start_sec = serializers.FloatField(allow_null=True)
    end_sec = serializers.FloatField(allow_null=True)
    category = serializers.CharField()
    severity = serializers.FloatField()


class FakeScreenshotDetectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FakeScreenshotDetection
        fields = (
            "id",
            "frame_timestamp_sec",
            "bank_name",
            "is_fake",
            "confidence",
            "artifacts_found",
        )


class EvidenceChainEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = EvidenceChainEntry
        fields = (
            "id",
            "file_type",
            "file_path",
            "sha256_hash",
            "collected_at",
            "collection_method",
        )


class PromoCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PromoCode
        fields = ("id", "code", "extracted_from")


class TelegramLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelegramLink
        fields = ("id", "url", "extracted_from")


class AnalystLabelSerializer(serializers.ModelSerializer):
    analyst = serializers.CharField(source="analyst.username", read_only=True)

    class Meta:
        model = AnalystLabel
        fields = ("id", "decision", "comment", "analyst", "decided_at")


class IncidentDetailSerializer(serializers.ModelSerializer):
    """Everything the incident card needs, in one response.

    All nested data is read from prefetched relations (see the view's
    queryset) — the SerializerMethodFields call `.all()` on already-prefetched
    managers and must NOT trigger new queries.
    """

    video = VideoDetailSerializer(read_only=True)
    social_account = SocialAccountDetailSerializer(
        source="video.social_account", read_only=True
    )
    risk_breakdown = serializers.SerializerMethodField()
    transcript_flags = serializers.SerializerMethodField()
    fake_screenshots = serializers.SerializerMethodField()
    evidence_chain = serializers.SerializerMethodField()
    geo = serializers.SerializerMethodField()
    categories = serializers.SerializerMethodField()
    promo_codes = PromoCodeSerializer(many=True, read_only=True)
    telegram_links = TelegramLinkSerializer(many=True, read_only=True)
    analyst_labels = AnalystLabelSerializer(many=True, read_only=True)

    class Meta:
        model = Incident
        fields = (
            "id",
            "status",
            "summary_text",
            "risk_score",
            "priority_score",
            "created_at",
            "video",
            "social_account",
            "risk_breakdown",
            "transcript_flags",
            "fake_screenshots",
            "evidence_chain",
            "geo",
            "categories",
            "promo_codes",
            "telegram_links",
            "analyst_labels",
        )

    def get_geo(self, obj):
        v = obj.video
        if not v.geo_source or v.geo_source == "none":
            return None
        return {
            "lat": v.geo_latitude,
            "lon": v.geo_longitude,
            "label": v.geo_label,
            "region": v.geo_region,
            "country": v.geo_country,
            "source": v.geo_source,
            "confidence": round(v.geo_confidence, 2),
            "reasoning": (v.geo_raw or {}).get("reasoning", ""),
        }

    def get_categories(self, obj):
        """Rich detail for the new high-value categories (same shape as the
        analyze-page status endpoint)."""
        out = {}
        screening = getattr(obj.video, "screening_result", None)
        if screening is None:
            return out
        for s in screening.signals.all():
            if s.module in ("payment", "brand_link", "audio_forensics", "social_context"):
                out[s.module] = {
                    "is_triggered": s.is_triggered,
                    "confidence": s.confidence,
                    "error": s.error,
                    "detail": s.raw_output,
                }
        return out

    def get_risk_breakdown(self, obj):
        """Unified per-source score contributions.

        Aggregated from ReasoningNode (has explicit score_contribution) and
        ScreeningSignal (stage-1 module signals; confidence as their weight).
        """
        items = []
        dar = obj.deep_analysis_result
        for node in dar.reasoning_nodes.all():
            items.append({
                "source": node.node_key,
                "label": node.label,
                "node_type": node.node_type,
                "status": node.status,
                "score_contribution": node.score_contribution,
                "confidence": None,
            })
        screening = getattr(obj.video, "screening_result", None)
        if screening is not None:
            for signal in screening.signals.all():
                items.append({
                    "source": f"screening_{signal.module}",
                    "label": signal.get_module_display(),
                    "node_type": "stage1_signal",
                    "status": "triggered" if signal.is_triggered else "clean",
                    "score_contribution": None,
                    "confidence": signal.confidence,
                })
        return items

    def get_transcript_flags(self, obj):
        flags = []
        for transcript in obj.deep_analysis_result.transcripts.all():
            for flag in transcript.flags.all():
                flags.append(flag)
        return TranscriptFlagSerializer(flags, many=True).data

    def get_fake_screenshots(self, obj):
        qs = obj.deep_analysis_result.fake_screenshots.all()
        return FakeScreenshotDetectionSerializer(qs, many=True).data

    def get_evidence_chain(self, obj):
        return EvidenceChainEntrySerializer(
            obj.evidence_entries.all(), many=True
        ).data


class AnalystDecisionSerializer(serializers.Serializer):
    """Request body for POST .../decision/."""

    decision = serializers.ChoiceField(choices=AnalystLabel.Decision.choices)
    comment = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
