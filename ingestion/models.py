"""
Raw ingestion models: platforms, social accounts, videos and comments.

These represent the "raw" entities collected from social networks. They carry
NO analysis logic or risk scoring — that lives in screening/deepanalysis and
will reference Video via ForeignKey in later prompts.
"""
import os

from django.db import models

from core.models import TimeStampedModel


class Platform(TimeStampedModel):
    """Reference table of supported social platforms (instagram/tiktok/youtube)."""

    class Code(models.TextChoices):
        INSTAGRAM = "instagram", "Instagram"
        TIKTOK = "tiktok", "TikTok"
        YOUTUBE = "youtube", "YouTube"

    code = models.SlugField(
        max_length=32,
        unique=True,
        choices=Code.choices,
        help_text="Machine-readable platform identifier.",
    )
    name = models.CharField(max_length=64, help_text="Human-readable display name.")
    # Front-end presentation helpers.
    icon = models.CharField(
        max_length=128,
        blank=True,
        help_text="Icon identifier or URL used by the frontend.",
    )
    color = models.CharField(
        max_length=9,
        blank=True,
        help_text="Brand/accent color as a hex string, e.g. #E1306C.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class SocialAccount(TimeStampedModel):
    """A monitored account on a social platform."""

    platform = models.ForeignKey(
        Platform,
        on_delete=models.PROTECT,
        related_name="accounts",
    )
    external_id = models.CharField(
        max_length=128,
        help_text="Platform-native account ID (stable across renames).",
    )
    username = models.CharField(max_length=255, db_index=True)
    display_name = models.CharField(max_length=255, blank=True)
    followers_count = models.PositiveBigIntegerField(default=0)
    profile_url = models.URLField(max_length=500, blank=True)
    profile_description = models.TextField(blank=True)
    linktree_url = models.URLField(max_length=500, null=True, blank=True)

    # Watchlist flags — set manually or by the screening pipeline later.
    is_watchlisted = models.BooleanField(default=False)
    watchlist_reason = models.TextField(null=True, blank=True)

    follows = models.ManyToManyField("self", symmetrical=False, blank=True)

    # Filled heuristically / manually — there is no precise geolocation in the
    # MVP. Used by the leadership geography dashboard.
    region = models.CharField(max_length=128, null=True, blank=True)

    # Link to a payment identifier (phone / account number) for the bank API.
    # Indexed for the hot-path risk lookup. In production this mapping will be
    # far more involved (fuzzy / multi-source); for the demo it is a direct,
    # exact-match field.
    linked_payment_identifier = models.CharField(
        max_length=128, null=True, blank=True, db_index=True
    )

    first_seen_at = models.DateTimeField(
        help_text="When this account was first observed by the system.",
    )
    last_seen_at = models.DateTimeField(
        help_text="Most recent time this account was observed.",
    )

    class Meta:
        ordering = ["-last_seen_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["platform", "external_id"],
                name="uniq_account_per_platform",
            ),
        ]
        indexes = [
            models.Index(fields=["platform", "is_watchlisted"]),
            models.Index(fields=["username"]),
        ]

    def __str__(self) -> str:
        return f"@{self.username} ({self.platform})"


class BatchJob(TimeStampedModel):
    """A batch ingestion job: bulk URLs, an offline folder, or a parsed source.

    Tracks a group of videos submitted together so the UI can show aggregate
    progress (continuous analysis of a large stream of videos).
    """

    class Kind(models.TextChoices):
        BULK_URLS = "bulk_urls", "Bulk URLs"
        FOLDER = "folder", "Offline folder"
        SOURCE_PARSE = "source_parse", "Source parse (account/hashtag)"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    kind = models.CharField(max_length=16, choices=Kind.choices)
    source = models.TextField(blank=True, help_text="Folder path / channel / hashtag.")
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    total = models.PositiveIntegerField(default=0)
    note = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Batch<{self.id}> {self.kind} ({self.total})"


class LiveSession(TimeStampedModel):
    """A monitored live broadcast (эфир) — TikTok / YouTube / Instagram Live.

    The monitor captures the stream in short chunks; each chunk is registered as
    a Video and screened, and a LiveAlert is raised when a chunk trips the
    screening. Real-time detection of fraud during a live stream.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        LIVE = "live", "Live (monitoring)"
        STOPPED = "stopped", "Stopped by analyst"
        ENDED = "ended", "Broadcast ended"
        FAILED = "failed", "Failed"

    platform = models.ForeignKey(
        Platform, on_delete=models.PROTECT, related_name="live_sessions"
    )
    url = models.URLField(max_length=500)
    title = models.CharField(max_length=255, blank=True, default="")
    streamer = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    chunk_seconds = models.PositiveIntegerField(default=30)
    max_chunks = models.PositiveIntegerField(
        default=120, help_text="Safety cap on chunks per session."
    )
    chunks_captured = models.PositiveIntegerField(default=0)
    alerts_count = models.PositiveIntegerField(default=0)
    max_risk_score = models.FloatField(default=0.0)
    last_chunk_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Live<{self.id}> {self.platform} {self.status}"


class LiveAlert(TimeStampedModel):
    """A suspicious moment detected within a live session's chunk."""

    live_session = models.ForeignKey(
        LiveSession, on_delete=models.CASCADE, related_name="alerts"
    )
    video = models.ForeignKey(
        "Video", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="live_alerts",
    )
    chunk_index = models.PositiveIntegerField(default=0)
    risk_score = models.FloatField(default=0.0)
    reasons = models.JSONField(default=list, blank=True)
    incident = models.ForeignKey(
        "incidents.Incident", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="live_alerts",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["live_session", "created_at"])]

    def __str__(self) -> str:
        return f"Alert<{self.id}> session={self.live_session_id} risk={self.risk_score}"


class Video(TimeStampedModel):
    """A single video collected from a social account."""

    class DownloadStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        DOWNLOADING = "downloading", "Downloading"
        DOWNLOADED = "downloaded", "Downloaded"
        FAILED = "failed", "Failed"

    platform = models.ForeignKey(
        Platform,
        on_delete=models.PROTECT,
        related_name="videos",
    )
    social_account = models.ForeignKey(
        SocialAccount,
        on_delete=models.CASCADE,
        related_name="videos",
    )
    batch_job = models.ForeignKey(
        "BatchJob",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="videos",
    )
    external_id = models.CharField(
        max_length=128,
        help_text="Platform-native video ID.",
    )
    url = models.URLField(max_length=500)
    caption = models.TextField(blank=True)
    # JSONField (not ArrayField) for portability; stores a list of strings.
    hashtags = models.JSONField(default=list, blank=True)
    posted_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="When the video was published on the platform.",
    )
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    thumbnail_url = models.URLField(max_length=500, blank=True)

    # Download bookkeeping.
    local_file_path = models.CharField(max_length=1024, null=True, blank=True)
    download_status = models.CharField(
        max_length=16,
        choices=DownloadStatus.choices,
        default=DownloadStatus.PENDING,
        db_index=True,
    )
    collected_at = models.DateTimeField(
        help_text="When the system collected the video metadata.",
    )
    source_hash = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text="SHA-256 of the downloaded file; null until downloaded.",
    )

    # ----- Geolocation (feature: geo-position of a video) -------------------
    # Filled by screening.services.geo_analysis from multiple sources, best
    # available first: embedded file GPS > platform location tag > AI inference
    # from caption/OCR/transcript. Null until a geo pass runs.
    class GeoSource(models.TextChoices):
        NONE = "none", "None"
        FILE_GPS = "file_gps", "File GPS metadata"
        PLATFORM_TAG = "platform_tag", "Platform location tag"
        AI_INFERENCE = "ai_inference", "AI content inference"

    geo_latitude = models.FloatField(null=True, blank=True)
    geo_longitude = models.FloatField(null=True, blank=True)
    geo_label = models.CharField(
        max_length=255, blank=True, help_text="Human-readable place, e.g. 'Алматы, Казахстан'."
    )
    geo_region = models.CharField(
        max_length=128, blank=True, db_index=True,
        help_text="Region/oblast for geography aggregation, e.g. 'Алматы'.",
    )
    geo_country = models.CharField(max_length=64, blank=True, default="")
    geo_source = models.CharField(
        max_length=16, choices=GeoSource.choices, default=GeoSource.NONE, db_index=True,
    )
    geo_confidence = models.FloatField(default=0.0, help_text="Confidence in [0, 1].")
    # Candidate places + signals + reasoning behind the chosen location.
    geo_raw = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-posted_at", "-collected_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["platform", "external_id"],
                name="uniq_video_per_platform",
            ),
        ]
        indexes = [
            models.Index(fields=["platform", "download_status"]),
            models.Index(fields=["download_status"]),
            models.Index(fields=["posted_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.platform} video {self.external_id}"

    @property
    def resolved_file_path(self):
        """Best-effort absolute path to the local media file.

        ``local_file_path`` is stored relative to ``MEDIA_ROOT`` so records are
        portable across machines (this DB is shared). Legacy rows may hold an
        absolute path from another developer's machine; for those we re-root the
        ``videos/<id>/<file>`` tail under the current ``MEDIA_ROOT`` so a file
        that exists locally is still found. Returns ``None`` when no path is
        recorded; the caller's ``os.path.exists`` check then fails loudly.
        """
        from django.conf import settings

        raw = self.local_file_path
        if not raw:
            return None
        # Already-relative path: resolve against this machine's MEDIA_ROOT.
        if not os.path.isabs(raw):
            return os.path.join(settings.MEDIA_ROOT, raw)
        # Absolute path that exists here (downloaded on this machine).
        if os.path.exists(raw):
            return raw
        # Absolute path from another machine: re-root the videos/<id>/<file>
        # tail under the local MEDIA_ROOT in case the file exists here.
        parts = raw.replace("\\", "/").split("/")
        if "videos" in parts:
            candidate = os.path.join(settings.MEDIA_ROOT, *parts[parts.index("videos"):])
            if os.path.exists(candidate):
                return candidate
        return raw


class VideoComment(TimeStampedModel):
    """A pinned or top-level comment attached to a video."""

    video = models.ForeignKey(
        Video,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    author = models.CharField(max_length=255, blank=True)
    text = models.TextField()
    is_pinned = models.BooleanField(default=False)
    posted_at = models.DateTimeField(null=True, blank=True)
    contains_suspicious_link = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_pinned", "-posted_at"]
        indexes = [
            models.Index(fields=["video", "is_pinned"]),
        ]

    def __str__(self) -> str:
        kind = "pinned" if self.is_pinned else "comment"
        return f"{kind} on video {self.video_id} by {self.author or 'unknown'}"
