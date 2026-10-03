"""
Stage 4 (self-learning) models.

The dynamic code-word dictionary, its versioned history for rollback, and a
record of fine-tuning runs. Storage only — the learning logic comes later.
"""
from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class KeywordDictionaryEntry(TimeStampedModel):
    """A single term in the dynamic code-word dictionary."""

    class Category(models.TextChoices):
        GUARANTEE = "guarantee", "Guarantee"
        URGENCY = "urgency", "Urgency"
        REFERRAL = "referral", "Referral"
        CASINO_SLANG = "casino_slang", "Casino slang"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PENDING_REVIEW = "pending_review", "Pending review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    term = models.CharField(max_length=255, db_index=True)
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        db_index=True,
    )
    added_automatically = models.BooleanField(default=False)
    confirmation_count = models.IntegerField(default=0)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING_REVIEW,
        db_index=True,
    )
    added_at = models.DateTimeField()
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="reviewed_keyword_entries",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["term"]
        indexes = [
            models.Index(fields=["status", "category"]),
        ]

    def __str__(self) -> str:
        return f"{self.term} ({self.category}, {self.status})"


class KeywordDictionaryVersion(TimeStampedModel):
    """A point-in-time snapshot of the dictionary, for history/rollback."""

    # Full list of terms at this version.
    snapshot = models.JSONField(default=list, blank=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Dictionary version {self.pk} @ {self.created_at:%Y-%m-%d %H:%M}"


class KeywordObservation(TimeStampedModel):
    """One occurrence of a tracked term in a video, dated for trend analysis.

    Populated from the brand/gambling terms detected during screening and from
    video hashtags. The (term, observed_on, region) shape lets the anomaly
    detector compute per-day, per-region frequency baselines cheaply in SQL —
    "частотность слова 'Авиатор' выросла на 400% за 24 часа в этом регионе".
    """

    class Source(models.TextChoices):
        BRAND = "brand", "Casino brand"
        GAMBLING_TERM = "gambling_term", "Gambling term"
        HASHTAG = "hashtag", "Hashtag"
        KEYWORD = "keyword", "Dictionary keyword"

    term = models.CharField(max_length=128, db_index=True)
    category = models.CharField(max_length=32, blank=True, default="")
    region = models.CharField(max_length=128, blank=True, default="", db_index=True)
    observed_on = models.DateField(db_index=True)
    source = models.CharField(
        max_length=16, choices=Source.choices, default=Source.KEYWORD
    )
    video = models.ForeignKey(
        "ingestion.Video",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="keyword_observations",
    )

    class Meta:
        ordering = ["-observed_on", "term"]
        indexes = [
            models.Index(fields=["term", "observed_on"]),
            models.Index(fields=["region", "observed_on"]),
            models.Index(fields=["observed_on"]),
        ]

    def __str__(self) -> str:
        return f"{self.term} @ {self.observed_on} ({self.region or 'all'})"


class KeywordAnomaly(TimeStampedModel):
    """A detected spike in a term's frequency (anomaly / trend prediction).

    One row per (term, region, day) the detector flagged. Persisted so the
    leadership dashboard can show an alerts feed and analysts can acknowledge /
    dismiss them.
    """

    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    class Status(models.TextChoices):
        NEW = "new", "New"
        ACKNOWLEDGED = "acknowledged", "Acknowledged"
        DISMISSED = "dismissed", "Dismissed"

    term = models.CharField(max_length=128, db_index=True)
    category = models.CharField(max_length=32, blank=True, default="")
    region = models.CharField(max_length=128, blank=True, default="")
    observed_on = models.DateField(db_index=True)
    window_days = models.PositiveIntegerField(default=7)
    current_count = models.PositiveIntegerField(default=0)
    baseline_avg = models.FloatField(default=0.0)
    pct_change = models.FloatField(default=0.0, help_text="Percent vs baseline.")
    z_score = models.FloatField(default=0.0)
    severity = models.CharField(
        max_length=8, choices=Severity.choices, default=Severity.LOW, db_index=True
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.NEW, db_index=True
    )
    sample_video_ids = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-observed_on", "-z_score"]
        constraints = [
            models.UniqueConstraint(
                fields=["term", "region", "observed_on"],
                name="uniq_anomaly_per_term_region_day",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "severity"]),
            models.Index(fields=["observed_on", "severity"]),
        ]

    def __str__(self) -> str:
        return f"Anomaly<{self.term}> {self.pct_change:+.0f}% @ {self.observed_on}"


class FineTuningRun(TimeStampedModel):
    """A record of one fine-tuning / self-learning cycle."""

    class Status(models.TextChoices):
        COLLECTING = "collecting", "Collecting"
        TRAINING = "training", "Training"
        VALIDATING = "validating", "Validating"
        DEPLOYED = "deployed", "Deployed"
        ROLLED_BACK = "rolled_back", "Rolled back"

    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.COLLECTING,
        db_index=True,
    )
    training_examples_count = models.PositiveIntegerField(default=0)
    # Validation metrics — null until the run has been validated.
    precision = models.FloatField(null=True, blank=True)
    recall = models.FloatField(null=True, blank=True)
    false_positive_rate = models.FloatField(null=True, blank=True)
    notes = models.TextField(blank=True)
    # Serialised trained model (weights, scaler, feature names, metrics) as JSON
    # so it reloads without binary pickle. Null until a run trains a model.
    model_artifact = models.JSONField(null=True, blank=True)
    # Exactly one run is the active/deployed model used for inference.
    is_active = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self) -> str:
        flag = " *active*" if self.is_active else ""
        return f"FineTuningRun {self.pk} [{self.status}]{flag}"
