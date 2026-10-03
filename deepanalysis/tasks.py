import logging

from celery import shared_task
from django.utils import timezone

from core.exceptions import ModuleDependencyError
from deepanalysis.models import DeepAnalysisResult, Transcript, TranscriptFlag
from deepanalysis.services.fake_screenshot_detection import detect_fake_screenshots
from deepanalysis.services.identity_fingerprinting import link_video_identity
from deepanalysis.services.synthesis import (
    build_and_save_reasoning_graph,
    compute_risk_score,
    extract_promos_and_links,
    generate_incident_summary,
)
from deepanalysis.services.transcription import (
    full_transcribe,
    lexical_level_analysis,
    semantic_level_analysis,
)
from incidents.models import Incident
from ingestion.models import Video

logger = logging.getLogger(__name__)


@shared_task
def run_stage2_analysis(video_id: int):
    """Execute the Stage-2 deep-analysis pipeline.

    Each step is fail-loud: if a dependency (model/library/key) is missing, the
    step records an entry in ``DeepAnalysisResult.step_errors`` and is skipped —
    it never contributes fabricated data to the risk score. The pipeline as a
    whole still completes (with whatever signals succeeded) so analysts see a
    transparent, partial result rather than nothing.
    """
    try:
        video = Video.objects.get(id=video_id)
        dar, created = DeepAnalysisResult.objects.get_or_create(
            video=video,
            defaults={"status": DeepAnalysisResult.Status.IN_PROGRESS, "started_at": timezone.now()},
        )
        if not created and dar.status == DeepAnalysisResult.Status.COMPLETED:
            return

        dar.status = DeepAnalysisResult.Status.IN_PROGRESS
        dar.step_errors = {}
        dar.save(update_fields=["status", "step_errors"])

        step_errors = {}

        # --- E1: Transcription + lexical + semantic ---------------------------
        transcript = None
        video_path = video.resolved_file_path
        if video_path:
            try:
                trans_data = full_transcribe(video_path)
                transcript = Transcript.objects.create(
                    deep_analysis_result=dar,
                    full_text=trans_data["text"],
                    language=trans_data["language"],
                    segments=trans_data["segments"],
                )
                for flag in lexical_level_analysis(trans_data["text"]):
                    TranscriptFlag.objects.create(
                        transcript=transcript,
                        phrase=flag["phrase"],
                        category=flag.get("category", TranscriptFlag.Category.KEYWORD),
                        severity=flag.get("severity", 1),
                        start_sec=0.0, end_sec=0.0,
                    )
                try:
                    semantic_flags = semantic_level_analysis(trans_data["text"])
                    if semantic_flags.get("false_urgency_detected"):
                        for phrase in semantic_flags.get("false_urgency_phrases", []):
                            TranscriptFlag.objects.create(
                                transcript=transcript,
                                phrase=phrase,
                                category=TranscriptFlag.Category.URGENCY,
                                severity=3, start_sec=0.0, end_sec=0.0,
                            )
                except ModuleDependencyError as exc:
                    step_errors["semantic_analysis"] = exc.detail
                    logger.warning("Stage2 semantic analysis skipped (video %s): %s", video_id, exc.detail)
            except ModuleDependencyError as exc:
                step_errors["transcription"] = exc.detail
                logger.warning("Stage2 transcription skipped (video %s): %s", video_id, exc.detail)
        else:
            step_errors["transcription"] = "No local video file available."

        # --- E2: Fake screenshot detection ------------------------------------
        try:
            detect_fake_screenshots(video, dar)
        except ModuleDependencyError as exc:
            step_errors["fake_screenshot"] = exc.detail
            logger.warning("Stage2 fake-screenshot skipped (video %s): %s", video_id, exc.detail)

        # --- E3: Identity fingerprinting --------------------------------------
        try:
            link_video_identity(video)
        except ModuleDependencyError as exc:
            step_errors["identity"] = exc.detail
            logger.warning("Stage2 identity skipped (video %s): %s", video_id, exc.detail)

        # --- E4: Synthesis + risk score + reasoning graph ---------------------
        risk_data = compute_risk_score(video, dar)
        dar.risk_score = risk_data["score"]
        build_and_save_reasoning_graph(video, dar, risk_data)

        dar.status = DeepAnalysisResult.Status.COMPLETED
        dar.completed_at = timezone.now()
        dar.step_errors = step_errors
        dar.save(update_fields=["status", "completed_at", "risk_score", "step_errors"])

        # --- Incident creation ------------------------------------------------
        incident, inc_created = Incident.objects.get_or_create(
            video=video,
            defaults={
                "deep_analysis_result": dar,
                "risk_score": dar.risk_score,
                "status": Incident.Status.PENDING_REVIEW,
            },
        )

        if inc_created or not incident.summary_text:
            first_transcript = dar.transcripts.first()
            text = first_transcript.full_text if first_transcript else video.caption
            try:
                incident.summary_text = generate_incident_summary(text or "", risk_data)
            except ModuleDependencyError as exc:
                step_errors["summary"] = exc.detail
                dar.step_errors = step_errors
                dar.save(update_fields=["step_errors"])
                logger.warning("Stage2 summary skipped (video %s): %s", video_id, exc.detail)

            if first_transcript:
                extract_promos_and_links(incident, first_transcript.full_text, "transcript")
            if video.caption:
                extract_promos_and_links(incident, video.caption, "caption")

            incident.recalculate_priority(save=False)
            incident.save()

    except Exception as e:
        logger.exception("Failed Stage 2 for video %s: %s", video_id, e)
        DeepAnalysisResult.objects.filter(video_id=video_id).update(
            status=DeepAnalysisResult.Status.FAILED
        )
