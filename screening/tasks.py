"""
Stage-1 screening orchestration (Celery).

Each of the four module tasks runs one screening microservice and persists a
ScreeningSignal. Production "fail-loud" policy: if a module cannot run (missing
model / library / asset) it raises ModuleDependencyError; we persist a signal
with `error` set, `is_triggered=False`, `confidence=0` — it contributes nothing
to the verdict. A module must never fabricate a clean/triggered result.

`run_stage1_screening` fans the four modules out in a chord, then
`aggregate_stage1_results` runs the adversarial cross-check and the verdict.
"""
import logging
import time

from celery import chord, group, shared_task
from django.utils import timezone

from core.exceptions import ModuleDependencyError
from ingestion.models import Video
from screening.models import ScreeningResult, ScreeningSignal
from screening.services.adversarial_defense import run_adversarial_checks
from screening.services.audio_analysis import quick_audio_screening
from screening.services.audio_forensics import analyze_audio_forensics as _audio_forensics_analyser
from screening.services.brand_link_analysis import analyze_brand_link as _brand_link_analyser
from screening.services.frame_extraction import process_frame_extraction
from screening.services.metadata_analysis import analyze_metadata
from screening.services.payment_extraction import analyze_payment as _payment_analyser
from screening.services.social_context_analysis import analyze_social_context
from screening.services.visual_analysis import analyze_frames

logger = logging.getLogger(__name__)


def _run_module(video_id: int, module: str, analyser) -> dict:
    """Run one screening module and persist its signal (fail-loud).

    Returns a small summary dict for the chord callback.
    """
    video = Video.objects.get(id=video_id)
    screening_result = video.screening_result
    try:
        signal = analyser(video)
    except ModuleDependencyError as exc:
        logger.warning("Module %s unavailable for video %s: %s", module, video_id, exc.detail)
        signal = ScreeningSignal(
            module=module, is_triggered=False, confidence=0.0,
            error=exc.detail, raw_output={"error": exc.detail},
        )
    except Exception as exc:  # noqa: BLE001 — record, never fabricate a verdict
        logger.exception("Module %s failed for video %s", module, video_id)
        signal = ScreeningSignal(
            module=module, is_triggered=False, confidence=0.0,
            error=str(exc), raw_output={"error": str(exc)},
        )

    signal.screening_result = screening_result
    signal.save()
    return {
        "module": signal.module,
        "is_triggered": signal.is_triggered,
        "confidence": signal.confidence,
        "errored": bool(signal.error),
        "raw_output": signal.raw_output,
    }


@shared_task
def extract_frames_task(video_id: int):
    try:
        video = Video.objects.get(id=video_id)
        process_frame_extraction(video)
    except Exception as e:
        logger.error(f"extract_frames_task failed for video {video_id}: {e}")


@shared_task
def geo_extraction_task(video_id: int):
    """Best-effort geo enrichment (file GPS / platform tag / AI inference)."""
    try:
        from screening.services.geo_analysis import extract_geo
        video = Video.objects.get(id=video_id)
        result = extract_geo(video)
        logger.info("Geo for video %s: %s (%s)", video_id,
                    result.get("label"), result.get("source"))
    except Exception as e:  # noqa: BLE001 - geo is enrichment, never fatal
        logger.error(f"geo_extraction_task failed for video {video_id}: {e}")


@shared_task
def analyze_frames_task(video_id: int):
    return _run_module(video_id, ScreeningSignal.Module.FRAME_ANALYSIS, analyze_frames)


@shared_task
def quick_audio_task(video_id: int):
    return _run_module(video_id, ScreeningSignal.Module.QUICK_AUDIO, quick_audio_screening)


@shared_task
def metadata_analysis_task(video_id: int):
    return _run_module(video_id, ScreeningSignal.Module.METADATA, analyze_metadata)


@shared_task
def social_context_task(video_id: int):
    return _run_module(video_id, ScreeningSignal.Module.SOCIAL_CONTEXT, analyze_social_context)


@shared_task
def aggregate_stage1_results(results, video_id: int, start_time: float):
    """Chord callback: adversarial cross-check + verdict.

    A module that errored is neither clean nor triggered. If every module
    errored, the screening result is ERROR (incomplete) rather than CLEAN —
    so a broken pipeline can never silently pass a video.
    """
    try:
        video = Video.objects.get(id=video_id)
        screening_result = video.screening_result

        frame_results = []
        audio_results = {}
        for res in results:
            if not res:
                continue
            if res.get("module") == "frame_analysis":
                frame_results = res.get("raw_output", {}).get("frames", [])
            elif res.get("module") == "quick_audio":
                audio_results = res.get("raw_output", {})

        adversarial_signal = run_adversarial_checks(video, frame_results, audio_results)
        adversarial_signal.screening_result = screening_result
        adversarial_signal.save()

        # New high-value categories run here (after frames/OCR are ready):
        # payment-identifier extraction and casino-brand/link/QR analysis.
        for module, analyser in (
            (ScreeningSignal.Module.PAYMENT, _payment_analyser),
            (ScreeningSignal.Module.BRAND_LINK, _brand_link_analyser),
            (ScreeningSignal.Module.AUDIO_FORENSICS, _audio_forensics_analyser),
        ):
            try:
                extra = analyser(video)
            except ModuleDependencyError as exc:
                extra = ScreeningSignal(
                    module=module, is_triggered=False, confidence=0.0,
                    error=exc.detail, raw_output={"error": exc.detail},
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Module %s failed for video %s", module, video_id)
                extra = ScreeningSignal(
                    module=module, is_triggered=False, confidence=0.0,
                    error=str(exc), raw_output={"error": str(exc)},
                )
            extra.screening_result = screening_result
            # Replace any prior row for this module (idempotent re-runs).
            screening_result.signals.filter(module=module).delete()
            extra.save()

        all_signals = list(screening_result.signals.all())
        is_suspicious = any(s.is_triggered for s in all_signals)
        # Domain modules (exclude the derived adversarial signal).
        domain = [s for s in all_signals if s.module != ScreeningSignal.Module.ADVERSARIAL]
        all_errored = bool(domain) and all(s.error for s in domain)

        if all_errored:
            screening_result.status = ScreeningResult.Status.ERROR
        else:
            screening_result.status = (
                ScreeningResult.Status.SUSPICIOUS if is_suspicious
                else ScreeningResult.Status.CLEAN
            )

        processing_time_ms = int((time.time() - start_time) * 1000)
        screening_result.processing_time_ms = processing_time_ms
        screening_result.save(update_fields=["status", "processing_time_ms"])

        # Geo enrichment for every video (best-effort, never blocks the verdict).
        try:
            geo_extraction_task.delay(video_id)
        except Exception as exc:  # noqa: BLE001 - broker/eager errors
            logger.warning("Could not enqueue geo for video %s: %s", video_id, exc)

        # Record keyword observations (casino brands / gambling terms / hashtags)
        # for the trend-anomaly detector. Best-effort enrichment.
        try:
            from learning.anomaly import record_keyword_observations
            record_keyword_observations(video)
        except Exception as exc:  # noqa: BLE001 - enrichment, never fatal
            logger.warning("Keyword observations failed for video %s: %s", video_id, exc)

        if processing_time_ms > 5000:
            logger.warning(f"Stage 1 for video {video_id} took {processing_time_ms}ms.")

        if is_suspicious:
            logger.info(f"Video {video_id} flagged suspicious. Triggering Stage 2.")
            from deepanalysis.tasks import run_stage2_analysis
            run_stage2_analysis.delay(video_id)

    except Exception as e:
        logger.error(f"Failed to aggregate stage 1 results for video {video_id}: {e}")
        try:
            video = Video.objects.get(id=video_id)
            if hasattr(video, "screening_result"):
                video.screening_result.status = ScreeningResult.Status.ERROR
                video.screening_result.save(update_fields=["status"])
        except Exception:
            pass


@shared_task
def run_stage1_screening(video_id: int):
    try:
        video = Video.objects.get(id=video_id)

        screening_result, created = ScreeningResult.objects.get_or_create(
            video=video,
            defaults={"triggered_at": timezone.now()},
        )
        if not created:
            screening_result.triggered_at = timezone.now()
            screening_result.save(update_fields=["triggered_at"])

        start_time = time.time()

        workflow = chord(
            group(
                analyze_frames_task.s(video_id),
                quick_audio_task.s(video_id),
                metadata_analysis_task.s(video_id),
                social_context_task.s(video_id),
            ),
            aggregate_stage1_results.s(video_id, start_time),
        )
        workflow.apply_async()

    except Exception as e:
        logger.error(f"Failed to start Stage 1 screening for video {video_id}: {e}")
