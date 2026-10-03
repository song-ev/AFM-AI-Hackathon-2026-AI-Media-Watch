"""
Stage 2 (deep analysis) result models.

Stores deep-analysis outcomes for a video: risk score, transcript and flagged
phrases, fake-screenshot detections, cross-platform identity links, and the
reasoning graph (nodes/edges) that the frontend visualises. Storage only —
no analysis logic here.
"""
from django.db import models

from core.models import TimeStampedModel
from ingestion.models import SocialAccount, Video


class DeepAnalysisResult(TimeStampedModel):
    """Deep-analysis outcome for a single video."""

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    video = models.OneToOneField(
        Video,
        on_delete=models.CASCADE,
        related_name="deep_analysis_result",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.IN_PROGRESS,
        db_index=True,
    )
    risk_score = models.FloatField(
        default=0.0,
        db_index=True,
        help_text="Aggregate risk in [0, 100]; indexed for queue sorting.",
    )
    processing_time_ms = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    # Per-step failures, e.g. {"transcription": "...", "semantic": "..."}.
    # Populated when an analysis step's dependency is unavailable (fail-loud):
    # the step is recorded as errored rather than contributing fabricated data.
    step_errors = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-risk_score", "-started_at"]
        indexes = [
            models.Index(fields=["status", "risk_score"]),
        ]

    def __str__(self) -> str:
        return f"DeepAnalysis<{self.video_id}> {self.status} score={self.risk_score}"


class Transcript(TimeStampedModel):
    """Full transcription produced for a deep-analysis result."""

    deep_analysis_result = models.ForeignKey(
        DeepAnalysisResult,
        on_delete=models.CASCADE,
        related_name="transcripts",
    )
    full_text = models.TextField(blank=True)
    language = models.CharField(max_length=16, blank=True)
    # List of {start, end, text} segments.
    segments = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Transcript<{self.deep_analysis_result_id}> ({self.language or 'n/a'})"


class TranscriptFlag(TimeStampedModel):
    """A suspicious phrase found within a transcript."""

    class Category(models.TextChoices):
        GUARANTEE = "guarantee", "Guarantee"
        URGENCY = "urgency", "Urgency"
        REFERRAL = "referral", "Referral"
        CALL_TO_ACTION = "call_to_action", "Call to action"
        KEYWORD = "keyword", "Keyword"

    transcript = models.ForeignKey(
        Transcript,
        on_delete=models.CASCADE,
        related_name="flags",
    )
    phrase = models.TextField()
    start_sec = models.FloatField(null=True, blank=True)
    end_sec = models.FloatField(null=True, blank=True)
    category = models.CharField(max_length=32, choices=Category.choices, db_index=True)
    severity = models.FloatField(default=0.0)

    class Meta:
        ordering = ["start_sec"]
        indexes = [
            models.Index(fields=["transcript", "category"]),
        ]

    def __str__(self) -> str:
        return f"{self.category}: {self.phrase[:40]}"


class FakeScreenshotDetection(TimeStampedModel):
    """Detection of a forged payout/transfer screenshot in a video frame."""

    deep_analysis_result = models.ForeignKey(
        DeepAnalysisResult,
        on_delete=models.CASCADE,
        related_name="fake_screenshots",
    )
    frame_timestamp_sec = models.FloatField(
        null=True,
        blank=True,
        help_text="Moment in the video the frame was sampled from.",
    )
    bank_name = models.CharField(
        max_length=64,
        blank=True,
        help_text="Detected bank brand, e.g. Kaspi, Halyk.",
    )
    is_fake = models.BooleanField(default=False)
    confidence = models.FloatField(default=0.0, help_text="Confidence in [0, 1].")
    # List of artifact identifiers: font_mismatch, clone_traces, jpeg_artifacts, ...
    artifacts_found = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["frame_timestamp_sec"]
        indexes = [
            models.Index(fields=["deep_analysis_result", "is_fake"]),
        ]

    def __str__(self) -> str:
        verdict = "fake" if self.is_fake else "genuine"
        return f"Screenshot[{verdict}] {self.bank_name or 'unknown'}"


class IdentityFingerprint(TimeStampedModel):
    """A cross-platform identity fingerprint (voice or face).

    Stores only a hash of the embedding; the raw vector is persisted separately
    (e.g. a vector store) and is intentionally not held in this relational model.
    """

    class FingerprintType(models.TextChoices):
        VOICE = "voice", "Voice"
        FACE = "face", "Face"

    fingerprint_type = models.CharField(
        max_length=16,
        choices=FingerprintType.choices,
        db_index=True,
    )
    embedding_hash = models.CharField(
        max_length=128,
        db_index=True,
        help_text="Hash of the embedding vector (not the vector itself).",
    )
    confidence = models.FloatField(default=0.0)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.fingerprint_type} fp {self.embedding_hash[:16]}"


class IdentityLink(TimeStampedModel):
    """Links a recognised identity to an account and optionally a video."""

    identity_fingerprint = models.ForeignKey(
        IdentityFingerprint,
        on_delete=models.CASCADE,
        related_name="links",
    )
    social_account = models.ForeignKey(
        SocialAccount,
        on_delete=models.CASCADE,
        related_name="identity_links",
    )
    video = models.ForeignKey(
        Video,
        on_delete=models.CASCADE,
        related_name="identity_links",
        null=True,
        blank=True,
    )
    linked_at = models.DateTimeField()

    class Meta:
        ordering = ["-linked_at"]
        indexes = [
            models.Index(fields=["identity_fingerprint", "social_account"]),
        ]

    def __str__(self) -> str:
        return f"link {self.identity_fingerprint_id} -> account {self.social_account_id}"


class ReasoningNode(TimeStampedModel):
    """A node in the reasoning graph for a deep-analysis result."""

    class NodeType(models.TextChoices):
        STAGE1_SIGNAL = "stage1_signal", "Stage 1 signal"
        STAGE2_SIGNAL = "stage2_signal", "Stage 2 signal"
        SYNTHESIS = "synthesis", "Synthesis"
        VERDICT = "verdict", "Verdict"

    class Status(models.TextChoices):
        TRIGGERED = "triggered", "Triggered"
        CLEAN = "clean", "Clean"
        NOT_APPLICABLE = "not_applicable", "Not applicable"

    deep_analysis_result = models.ForeignKey(
        DeepAnalysisResult,
        on_delete=models.CASCADE,
        related_name="reasoning_nodes",
    )
    node_key = models.CharField(
        max_length=128,
        help_text='Stable id within the graph, e.g. "audio_quick_scan".',
    )
    node_type = models.CharField(max_length=20, choices=NodeType.choices, db_index=True)
    label = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NOT_APPLICABLE,
    )
    score_contribution = models.FloatField(
        default=0.0,
        help_text="Contribution to the risk score; may be negative or zero.",
    )
    timestamp_sec = models.FloatField(null=True, blank=True)
    explanation = models.TextField(blank=True)

    class Meta:
        ordering = ["node_key"]
        constraints = [
            models.UniqueConstraint(
                fields=["deep_analysis_result", "node_key"],
                name="uniq_node_key_per_graph",
            ),
        ]
        indexes = [
            models.Index(fields=["deep_analysis_result", "node_type"]),
        ]

    def __str__(self) -> str:
        return f"{self.node_key} ({self.status})"


class ReasoningEdge(TimeStampedModel):
    """A directed edge between two reasoning nodes."""

    deep_analysis_result = models.ForeignKey(
        DeepAnalysisResult,
        on_delete=models.CASCADE,
        related_name="reasoning_edges",
    )
    from_node = models.ForeignKey(
        ReasoningNode,
        on_delete=models.CASCADE,
        related_name="outgoing_edges",
    )
    to_node = models.ForeignKey(
        ReasoningNode,
        on_delete=models.CASCADE,
        related_name="incoming_edges",
    )
    weight = models.FloatField(default=1.0)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["deep_analysis_result"]),
        ]

    def __str__(self) -> str:
        return f"{self.from_node_id} -> {self.to_node_id} (w={self.weight})"
