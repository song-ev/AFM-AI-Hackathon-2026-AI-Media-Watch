"""Celery tasks for video ingestion."""
import logging
import os

from celery import shared_task
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger("ingestion")


@shared_task(name="ingestion.process_video_download")
def process_video_download(video_id):
    """Download a previously-created pending Video in the background."""
    from ingestion.models import Video
    from ingestion.services.downloader import download_video

    try:
        video = Video.objects.get(pk=video_id)
    except Video.DoesNotExist:
        logger.error("process_video_download: video %s not found", video_id)
        return None

    # Skip work for a cancelled batch (user stopped the parse/batch).
    from ingestion.services.bulk import batch_is_cancelled
    if batch_is_cancelled(video):
        logger.info("Skipping download for video %s - batch cancelled", video_id)
        if video.download_status != Video.DownloadStatus.DOWNLOADED:
            video.download_status = Video.DownloadStatus.FAILED
            video.save(update_fields=["download_status", "updated_at"])
        return video_id

    download_video(video.url, video=video)
    
    # Trigger Stage 1 screening if download was successful (and not cancelled).
    video.refresh_from_db()
    if video.download_status == Video.DownloadStatus.DOWNLOADED and not batch_is_cancelled(video):
        from screening.tasks import run_stage1_screening
        run_stage1_screening.delay(video.id)

    return video_id


# ---------------------------------------------------------------------------
# Live-stream monitoring (эфиры)
# ---------------------------------------------------------------------------
def _screen_chunk_sync(video) -> dict:
    """Synchronously screen one live chunk and return a verdict + reasons.

    Mirrors the Stage-1 aggregation but runs inline (no chord), so a live
    monitor gets an immediate verdict per chunk in any Celery mode. On a
    suspicious chunk it also runs Stage-2 to materialise an incident.
    """
    import time

    from core.exceptions import ModuleDependencyError
    from django.utils import timezone as tz
    from screening.models import ScreeningResult, ScreeningSignal
    from screening.services.audio_analysis import quick_audio_screening
    from screening.services.audio_forensics import analyze_audio_forensics
    from screening.services.brand_link_analysis import analyze_brand_link
    from screening.services.frame_extraction import process_frame_extraction
    from screening.services.metadata_analysis import analyze_metadata
    from screening.services.payment_extraction import analyze_payment
    from screening.services.visual_analysis import analyze_frames

    start = time.time()
    sr, _ = ScreeningResult.objects.get_or_create(
        video=video, defaults={"triggered_at": tz.now()}
    )
    try:
        process_frame_extraction(video)
    except Exception as exc:  # noqa: BLE001
        logger.warning("live frame extraction failed: %s", exc)

    analysers = [
        (ScreeningSignal.Module.FRAME_ANALYSIS, analyze_frames),
        (ScreeningSignal.Module.QUICK_AUDIO, quick_audio_screening),
        (ScreeningSignal.Module.METADATA, analyze_metadata),
        (ScreeningSignal.Module.PAYMENT, analyze_payment),
        (ScreeningSignal.Module.BRAND_LINK, analyze_brand_link),
        (ScreeningSignal.Module.AUDIO_FORENSICS, analyze_audio_forensics),
    ]
    reasons = []
    for module, fn in analysers:
        try:
            sig = fn(video)
        except ModuleDependencyError as exc:
            sig = ScreeningSignal(module=module, is_triggered=False,
                                  confidence=0.0, error=exc.detail)
        except Exception as exc:  # noqa: BLE001
            sig = ScreeningSignal(module=module, is_triggered=False,
                                  confidence=0.0, error=str(exc))
        sig.screening_result = sr
        sr.signals.filter(module=module).delete()
        sig.save()
        if sig.is_triggered:
            reasons.append(module)

    suspicious = bool(reasons)
    sr.status = (ScreeningResult.Status.SUSPICIOUS if suspicious
                 else ScreeningResult.Status.CLEAN)
    sr.processing_time_ms = int((time.time() - start) * 1000)
    sr.save(update_fields=["status", "processing_time_ms"])

    risk = 0.0
    incident_id = None
    if suspicious:
        from deepanalysis.tasks import run_stage2_analysis
        run_stage2_analysis(video.id)  # synchronous — builds DAR + incident
        video.refresh_from_db()
        dar = getattr(video, "deep_analysis_result", None)
        inc = getattr(video, "incident", None)
        risk = (inc.risk_score if inc else None) or (dar.risk_score if dar else 0.0)
        incident_id = inc.id if inc else None

    return {"suspicious": suspicious, "risk": risk or 0.0,
            "reasons": reasons, "incident_id": incident_id}


@shared_task(name="ingestion.monitor_live_session")
def monitor_live_session(session_id: int):
    """Capture and screen a live broadcast chunk-by-chunk until it ends/stops."""
    from ingestion.models import LiveAlert, LiveSession, Video
    from ingestion.services.downloader import register_local_video
    from ingestion.services.live_capture import (
        capture_chunk, new_chunk_path, resolve_live,
    )

    try:
        session = LiveSession.objects.get(id=session_id)
    except LiveSession.DoesNotExist:
        return

    if session.status in (LiveSession.Status.STOPPED, LiveSession.Status.ENDED,
                          LiveSession.Status.FAILED):
        return

    # Resolve the live manifest (re-resolved each call: short-lived URLs).
    try:
        live = resolve_live(session.url)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        low = msg.lower()
        # "Not currently live" is not an error — the streamer just isn't on air.
        if "not currently live" in low or "not live" in low or "isn't live" in low:
            session.status = LiveSession.Status.ENDED
            session.note = "Стример сейчас не в эфире."
        else:
            session.status = LiveSession.Status.FAILED
            session.note = msg[:500]
        session.save(update_fields=["status", "note", "updated_at"])
        return

    if session.status == LiveSession.Status.PENDING:
        session.status = LiveSession.Status.LIVE
        session.title = live.get("title", "")[:255]
        session.streamer = live.get("streamer", "")[:255]
        session.save(update_fields=["status", "title", "streamer", "updated_at"])

    if not live.get("is_live"):
        session.status = LiveSession.Status.ENDED
        session.note = "Трансляция завершена."
        session.save(update_fields=["status", "note", "updated_at"])
        return

    # In eager mode (no broker) process a couple of chunks in a loop; with a
    # real broker, process one chunk then re-enqueue the next.
    eager = getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False)
    iterations = 2 if eager else 1

    for _ in range(iterations):
        session.refresh_from_db()
        if session.status != LiveSession.Status.LIVE:
            return
        if session.chunks_captured >= session.max_chunks:
            session.status = LiveSession.Status.ENDED
            session.note = "Достигнут лимит чанков."
            session.save(update_fields=["status", "note", "updated_at"])
            return

        idx = session.chunks_captured
        out_path = new_chunk_path(session.id)
        try:
            chunk = capture_chunk(live["manifest_url"], session.chunk_seconds, out_path)
        except Exception as exc:  # noqa: BLE001
            session.status = LiveSession.Status.FAILED
            session.note = f"capture failed: {exc}"[:500]
            session.save(update_fields=["status", "note", "updated_at"])
            return
        if not chunk:
            # Stream likely dropped; mark ended rather than spin.
            session.status = LiveSession.Status.ENDED
            session.note = "Поток прервался (пустой чанк)."
            session.save(update_fields=["status", "note", "updated_at"])
            return

        video = register_local_video(
            chunk, session.platform, {
                "caption": f"{live.get('title','')} (эфир, чанк {idx})",
                "username": live.get("streamer", "") or "live",
                "url": session.url,
            },
        )
        video.batch_job = None
        video.save(update_fields=["batch_job", "updated_at"])

        verdict = {}
        if video.download_status == Video.DownloadStatus.DOWNLOADED:
            verdict = _screen_chunk_sync(video)

        session.refresh_from_db()
        session.chunks_captured = idx + 1
        session.last_chunk_at = timezone.now()
        if verdict.get("suspicious"):
            session.alerts_count += 1
            session.max_risk_score = max(session.max_risk_score, verdict.get("risk", 0.0))
            LiveAlert.objects.create(
                live_session=session,
                video=video,
                chunk_index=idx,
                risk_score=verdict.get("risk", 0.0),
                reasons=verdict.get("reasons", []),
                incident_id=verdict.get("incident_id"),
            )
        session.save(update_fields=[
            "chunks_captured", "last_chunk_at", "alerts_count",
            "max_risk_score", "updated_at",
        ])
        # Best-effort cleanup of the chunk file (evidence stays in the Video copy).
        try:
            os.remove(chunk)
        except OSError:
            pass

    # Re-enqueue the next chunk (broker mode keeps the loop going).
    session.refresh_from_db()
    if session.status == LiveSession.Status.LIVE and not eager:
        monitor_live_session.apply_async((session.id,), countdown=1)
