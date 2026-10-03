"""
Stage 1 (screening) result models.

Stores the outcome of the first-pass screening for a video and the individual
signals emitted by the 5 screening microservices. No analysis logic here —
just storage. Risk scoring and deep analysis live in `deepanalysis`.
"""
from django.db import models

from core.models import TimeStampedModel
from ingestion.models import Video


class ScreeningResult(TimeStampedModel):
    """First-pass screening outcome for a single video."""

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In Progress"
        CLEAN = "clean", "Clean"
        SUSPICIOUS = "suspicious", "Suspicious"
        ERROR = "error", "Error"

    video = models.OneToOneField(
        Video,
        on_delete=models.CASCADE,
        related_name="screening_result",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.IN_PROGRESS,
        db_index=True,
    )
    processing_time_ms = models.PositiveIntegerField(default=0)
    triggered_at = models.DateTimeField()

    class Meta:
        ordering = ["-triggered_at"]

    def __str__(self) -> str:
        return f"Screening<{self.video_id}> {self.status}"


class ScreeningSignal(TimeStampedModel):
    """A single signal from one of the 5 screening microservices."""

    class Module(models.TextChoices):
        METADATA = "metadata", "Metadata"
        SOCIAL_CONTEXT = "social_context", "Social context"
        QUICK_AUDIO = "quick_audio", "Quick audio"
        FRAME_ANALYSIS = "frame_analysis", "Frame analysis"
        ADVERSARIAL = "adversarial", "Adversarial"
        # New, more powerful categories.
        PAYMENT = "payment", "Payment identifiers"
        BRAND_LINK = "brand_link", "Casino brands & links"
        AUDIO_FORENSICS = "audio_forensics", "Audio forensics"

    screening_result = models.ForeignKey(
        ScreeningResult,
        on_delete=models.CASCADE,
        related_name="signals",
    )
    module = models.CharField(max_length=32, choices=Module.choices, db_index=True)
    is_triggered = models.BooleanField(default=False)
    confidence = models.FloatField(default=0.0, help_text="Confidence in [0, 1].")
    # Non-empty when the module could not run (missing model/library/asset).
    # An errored signal contributes nothing to the risk score — it is neither
    # clean nor triggered, just unavailable.
    error = models.TextField(blank=True, default="")
    # Flexible per-module detail blob.
    raw_output = models.JSONField(default=dict, blank=True)
    detected_at_timestamp_sec = models.FloatField(
        null=True,
        blank=True,
        help_text="Moment in the video the signal refers to, if applicable.",
    )

    class Meta:
        ordering = ["module"]
        constraints = [
            models.UniqueConstraint(
                fields=["screening_result", "module"],
                name="uniq_signal_per_module",
            ),
        ]
        indexes = [
            models.Index(fields=["screening_result", "is_triggered"]),
        ]

    def __str__(self) -> str:
        state = "triggered" if self.is_triggered else "clean"
        return f"{self.module} [{state}] for {self.screening_result_id}"


class ExtractedFrame(TimeStampedModel):
    """A representative frame extracted from a video."""

    video = models.ForeignKey(
        Video,
        on_delete=models.CASCADE,
        related_name="extracted_frames",
    )
    screening_result = models.ForeignKey(
        ScreeningResult,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="extracted_frames",
    )
    timestamp_sec = models.FloatField()
    file_path = models.CharField(max_length=1024)

    class Meta:
        ordering = ["video", "timestamp_sec"]
        indexes = [
            models.Index(fields=["video", "timestamp_sec"]),
        ]

    def __str__(self) -> str:
        return f"Frame for video {self.video_id} at {self.timestamp_sec}s"


class FrameAnalysisResult(TimeStampedModel):
    """Results of OCR and Logo detection on a single extracted frame."""

    extracted_frame = models.OneToOneField(
        ExtractedFrame,
        on_delete=models.CASCADE,
        related_name="analysis_result",
    )
    ocr_text = models.TextField(blank=True)
    ocr_matched_keywords = models.JSONField(default=list, blank=True)
    detected_objects = models.JSONField(default=list, blank=True)
    is_suspicious = models.BooleanField(default=False)
    analyzed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["is_suspicious"]),
        ]

    def __str__(self) -> str:
        state = "suspicious" if self.is_suspicious else "clean"
        return f"Analysis [{state}] for frame {self.extracted_frame_id}"
