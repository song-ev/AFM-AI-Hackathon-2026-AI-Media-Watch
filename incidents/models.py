"""
Stage 3 models: incident cards, evidence chain, extracted artifacts.

The connection graph is built on the fly from existing entities
(IdentityFingerprint + SocialAccount + PromoCode + TelegramLink), so no
dedicated graph models live here — only the indexes needed to aggregate them
quickly.
"""
from django.db import models

from core.models import TimeStampedModel
from deepanalysis.models import DeepAnalysisResult
from ingestion.models import Video


class Incident(TimeStampedModel):
    """An incident card synthesising the analysis of one video."""

    class Status(models.TextChoices):
        PENDING_REVIEW = "pending_review", "Pending review"
        CONFIRMED = "confirmed", "Confirmed"
        FALSE_POSITIVE = "false_positive", "False positive"
        BORDERLINE = "borderline", "Borderline"

    video = models.OneToOneField(
        Video,
        on_delete=models.CASCADE,
        related_name="incident",
    )
    deep_analysis_result = models.OneToOneField(
        DeepAnalysisResult,
        on_delete=models.CASCADE,
        related_name="incident",
    )
    summary_text = models.TextField(
        blank=True,
        help_text="Auto-generated 2-3 sentence summary.",
    )
    # Duplicated from deep_analysis_result for cheap indexing/sorting.
    risk_score = models.FloatField(default=0.0, db_index=True)
    # Precomputed: Risk_Score * log(followers+1) * e^(-hours/48).
    # Recomputation lives in a separate function/celery task, not here.
    priority_score = models.FloatField(default=0.0, db_index=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING_REVIEW,
        db_index=True,
    )

    class Meta:
        ordering = ["-priority_score", "-created_at"]
        indexes = [
            models.Index(fields=["status", "priority_score"]),
        ]

    def __str__(self) -> str:
        return f"Incident<{self.video_id}> {self.status} p={self.priority_score:.2f}"

    def recalculate_priority(self, save=True, now=None):
        """Recompute and set priority_score from the formula.

        Reads followers/posted_at from the related video; callers that touch
        many rows should prefetch `video__social_account`.
        """
        from incidents.services import compute_priority_score

        self.priority_score = compute_priority_score(
            self.risk_score,
            self.video.social_account.followers_count,
            self.video.posted_at,
            now=now,
        )
        if save:
            self.save(update_fields=["priority_score", "updated_at"])
        return self.priority_score


class EvidenceChainEntry(TimeStampedModel):
    """A single, immutable entry in an incident's chain of custody.

    Append-only at the application level: updates and deletes are rejected.
    In production this is additionally enforced with PostgreSQL privileges
    (INSERT-only grant on the table); the overrides below are the
    application-level guard rail.
    """

    class FileType(models.TextChoices):
        VIDEO = "video", "Video"
        SCREENSHOT = "screenshot", "Screenshot"
        AUDIO = "audio", "Audio"

    # Evidence is captured at COLLECTION time (doc §3.5), before any incident
    # exists — so incident is nullable and the entry references the video it was
    # collected from. When an incident is later opened for that video, its
    # evidence can be found via the video. Append-only is preserved: we never
    # mutate an existing row to back-fill the incident.
    incident = models.ForeignKey(
        Incident,
        on_delete=models.PROTECT,
        related_name="evidence_entries",
        null=True,
        blank=True,
    )
    video = models.ForeignKey(
        "ingestion.Video",
        on_delete=models.PROTECT,
        related_name="evidence_entries",
        null=True,
        blank=True,
    )
    file_type = models.CharField(max_length=16, choices=FileType.choices)
    file_path = models.CharField(max_length=1024)
    sha256_hash = models.CharField(max_length=64)
    collected_at = models.DateTimeField(help_text="UTC timestamp of collection.")
    collection_method = models.CharField(
        max_length=255,
        help_text='e.g. "yt-dlp automated download".',
    )

    class Meta:
        ordering = ["collected_at"]
        verbose_name_plural = "Evidence chain entries"
        indexes = [
            models.Index(fields=["incident", "file_type"]),
            models.Index(fields=["sha256_hash"]),
        ]

    def save(self, *args, **kwargs):
        # Reject any attempt to modify an existing row — append-only.
        if not self._state.adding:
            raise PermissionError(
                "EvidenceChainEntry is append-only; existing entries cannot "
                "be updated."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError(
            "EvidenceChainEntry is append-only; entries cannot be deleted."
        )

    def __str__(self) -> str:
        return f"{self.file_type} {self.sha256_hash[:12]} (incident {self.incident_id})"


class PromoCode(TimeStampedModel):
    """A promo code extracted from an incident's content."""

    class Source(models.TextChoices):
        CAPTION = "caption", "Caption"
        COMMENT = "comment", "Comment"
        TRANSCRIPT = "transcript", "Transcript"
        OCR = "ocr", "OCR"

    incident = models.ForeignKey(
        Incident,
        on_delete=models.CASCADE,
        related_name="promo_codes",
    )
    # Indexed for fast cross-incident aggregation in the connection graph.
    code = models.CharField(max_length=128, db_index=True)
    extracted_from = models.CharField(max_length=16, choices=Source.choices)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} (from {self.extracted_from})"


class TelegramLink(TimeStampedModel):
    """A Telegram link extracted from an incident's content."""

    class Source(models.TextChoices):
        CAPTION = "caption", "Caption"
        COMMENT = "comment", "Comment"
        TRANSCRIPT = "transcript", "Transcript"
        OCR = "ocr", "OCR"

    incident = models.ForeignKey(
        Incident,
        on_delete=models.CASCADE,
        related_name="telegram_links",
    )
    # Indexed for fast cross-incident aggregation in the connection graph.
    url = models.URLField(max_length=500, db_index=True)
    extracted_from = models.CharField(max_length=16, choices=Source.choices)

    class Meta:
        ordering = ["url"]

    def __str__(self) -> str:
        return f"{self.url} (from {self.extracted_from})"
