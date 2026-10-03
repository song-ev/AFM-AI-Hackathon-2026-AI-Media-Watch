"""Ingestion API: submit a video URL or upload a local file, poll status."""
import os
import re
import tempfile

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsAnalystOrAbove, IsSystemAdmin
from ingestion.models import Video
from ingestion.serializers import VideoSubmitSerializer
from ingestion.services.downloader import create_pending_video, register_local_video
from ingestion.tasks import process_video_download

import logging

logger = logging.getLogger("ingestion")


def _safe_enqueue(task, *args):
    """Enqueue a Celery task without letting a broker outage 500 the request.

    With CELERY_TASK_ALWAYS_EAGER (dev default) this runs in-process; if a real
    broker is configured but unreachable, we log and continue rather than crash.
    """
    try:
        task.delay(*args)
        return True
    except Exception as exc:  # noqa: BLE001 — broker/connection errors
        logger.error("Failed to enqueue %s%s: %s", task.name, args, exc)
        return False


class VideoSubmitView(APIView):
    """POST /api/ingestion/videos/ — submit a URL; download runs async.

    Returns immediately with {video_id, status: "downloading"}; the actual
    download happens in a Celery task.
    """

    permission_classes = [IsAnalystOrAbove]

    def post(self, request, *args, **kwargs):
        serializer = VideoSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        url = serializer.validated_data["url"]

        # Cache: if this URL was already collected (or is being processed),
        # return the existing video instead of re-running the pipeline. Only a
        # previously FAILED video is re-submitted.
        existing = (
            Video.objects.filter(url=url)
            .exclude(download_status=Video.DownloadStatus.FAILED)
            .order_by("-collected_at")
            .first()
        )
        if existing is not None:
            return Response(
                {
                    "video_id": existing.id,
                    "status": existing.download_status,
                    "cached": True,
                },
                status=status.HTTP_200_OK,
            )

        try:
            video = create_pending_video(url)
        except ValueError as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST
            )

        _safe_enqueue(process_video_download, video.id)

        return Response(
            {"video_id": video.id, "status": video.download_status, "cached": False},
            status=status.HTTP_202_ACCEPTED,
        )


class VideoUploadView(APIView):
    """POST /api/ingestion/videos/upload/ — analyze an already-downloaded file.

    Multipart: `file` (the video), optional `platform` (default youtube).
    Registers the local file as a Video and kicks off Stage 1 screening.
    """

    permission_classes = [IsAnalystOrAbove]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, *args, **kwargs):
        upload = request.FILES.get("file")
        if upload is None:
            return Response(
                {"detail": "Файл не передан (поле 'file')."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        platform = request.data.get("platform") or "youtube"

        suffix = os.path.splitext(upload.name)[1] or ".mp4"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            for chunk in upload.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        try:
            video = register_local_video(
                tmp_path, platform, {"caption": upload.name}
            )
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

        if video.download_status == Video.DownloadStatus.DOWNLOADED:
            # Run the same Stage 1 pipeline as a downloaded video.
            from screening.tasks import run_stage1_screening
            _safe_enqueue(run_stage1_screening, video.id)

        return Response(
            {"video_id": video.id, "status": video.download_status, "cached": False},
            status=status.HTTP_202_ACCEPTED,
        )


class CapabilitiesView(APIView):
    """GET /api/ingestion/capabilities/ — what's configured (for UI readiness)."""

    permission_classes = [IsAnalystOrAbove]

    def get(self, request, *args, **kwargs):
        import shutil

        from django.conf import settings
        from core.llm import active_backend

        cookies = bool(getattr(settings, "YTDLP_COOKIES_FILE", ""))
        proxy = bool(getattr(settings, "YTDLP_PROXY", ""))
        return Response({
            "youtube": True,                    # works without secrets
            "tiktok": cookies or proxy,         # residential proxy unlocks public TikTok
            "instagram": cookies,               # needs a real login (cookies)
            "proxy": proxy,
            "llm": active_backend() != "none",
            "ocr": bool(shutil.which("tesseract") or getattr(settings, "TESSERACT_CMD", "")),
            "ffmpeg": bool(shutil.which("ffmpeg")),
        })


class BulkSubmitView(APIView):
    """POST /api/ingestion/bulk/ — submit many URLs at once as one batch.

    Body: {"urls": ["...", "..."]}  OR  {"text": "newline/space separated"}.
    Returns {batch_id, total}. Each video downloads + screens in the background.
    """

    permission_classes = [IsAnalystOrAbove]

    def post(self, request, *args, **kwargs):
        from ingestion.services.bulk import submit_bulk_urls

        urls = request.data.get("urls")
        if not urls:
            text = request.data.get("text", "") or ""
            urls = [u for u in re.split(r"[\s,]+", text) if u.strip()]
        if not isinstance(urls, list) or not urls:
            return Response(
                {"detail": "Передайте 'urls' (список) или 'text' со ссылками."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        batch = submit_bulk_urls(urls)
        return Response(
            {"batch_id": batch.id, "total": batch.total, "note": batch.note},
            status=status.HTTP_202_ACCEPTED,
        )


class ParseSourceView(APIView):
    """POST /api/ingestion/parse/ — enumerate a channel/@account/hashtag and analyse.

    Body: {"source_url": "...", "limit": 30}. Uses yt-dlp to list recent videos
    (no full download), then bulk-submits them.
    """

    permission_classes = [IsAnalystOrAbove]

    def post(self, request, *args, **kwargs):
        from ingestion.services.bulk import parse_source

        source_url = (request.data.get("source_url") or "").strip()
        if not source_url:
            return Response(
                {"detail": "Передайте 'source_url' (канал/аккаунт/хэштег)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            limit = max(1, min(int(request.data.get("limit", 30)), 100))
        except (TypeError, ValueError):
            limit = 30
        batch = parse_source(source_url, limit)
        return Response(
            {"batch_id": batch.id, "total": batch.total, "status": batch.status,
             "note": batch.note},
            status=status.HTTP_202_ACCEPTED,
        )


class FolderIngestView(APIView):
    """POST /api/ingestion/folder/ — register & analyse every video in a folder.

    Body: {"path": "C:/path/to/videos", "platform": "youtube"}. The path is on
    the SERVER. System-admin only (it touches the server filesystem).
    """

    permission_classes = [IsSystemAdmin]

    def post(self, request, *args, **kwargs):
        from ingestion.services.bulk import ingest_folder

        path = (request.data.get("path") or "").strip()
        platform = request.data.get("platform") or "youtube"
        if not path:
            return Response(
                {"detail": "Передайте 'path' к папке с видео на сервере."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        batch = ingest_folder(path, platform)
        return Response(
            {"batch_id": batch.id, "total": batch.total, "status": batch.status,
             "note": batch.note},
            status=status.HTTP_202_ACCEPTED,
        )


class BatchListView(APIView):
    """GET /api/ingestion/batches/ — recent batch jobs with progress."""

    permission_classes = [IsAnalystOrAbove]

    def get(self, request, *args, **kwargs):
        from ingestion.models import BatchJob
        from ingestion.services.bulk import batch_progress

        batches = BatchJob.objects.all()[:25]
        return Response({"batches": [batch_progress(b) for b in batches]})


class BatchDetailView(APIView):
    """GET /api/ingestion/batches/{id}/ — progress; DELETE — stop the batch."""

    permission_classes = [IsAnalystOrAbove]

    def get(self, request, pk, *args, **kwargs):
        from ingestion.models import BatchJob
        from ingestion.services.bulk import batch_progress

        batch = get_object_or_404(BatchJob, pk=pk)
        return Response(batch_progress(batch))

    def delete(self, request, pk, *args, **kwargs):
        """Stop a running batch / parse: no new downloads or analysis start."""
        from ingestion.models import BatchJob
        from ingestion.services.bulk import batch_progress, cancel_batch

        batch = get_object_or_404(BatchJob, pk=pk)
        cancel_batch(batch)
        return Response(batch_progress(batch))


def _live_session_payload(session, request=None) -> dict:
    # Latest captured chunk (a real mp4 on the server) — what the analyst should
    # actually watch, since the platform's live page can't be embedded.
    last_chunk_url = ""
    chunk = (
        Video.objects.filter(url=session.url,
                             download_status=Video.DownloadStatus.DOWNLOADED)
        .exclude(local_file_path__isnull=True).exclude(local_file_path="")
        .order_by("-id").first()
    )
    if chunk and chunk.local_file_path:
        from django.conf import settings
        rel = chunk.local_file_path.replace("\\", "/")
        media_url = settings.MEDIA_URL + rel
        last_chunk_url = request.build_absolute_uri(media_url) if request else media_url

    alerts = [
        {
            "id": a.id,
            "chunk_index": a.chunk_index,
            "risk_score": round(a.risk_score, 1),
            "reasons": a.reasons,
            "incident_id": a.incident_id,
            "created_at": a.created_at.isoformat(),
        }
        for a in session.alerts.all()[:50]
    ]
    return {
        "id": session.id,
        "url": session.url,
        "platform": session.platform.code if session.platform_id else "",
        "title": session.title,
        "streamer": session.streamer,
        "status": session.status,
        "chunk_seconds": session.chunk_seconds,
        "chunks_captured": session.chunks_captured,
        "alerts_count": session.alerts_count,
        "max_risk_score": round(session.max_risk_score, 1),
        "last_chunk_at": session.last_chunk_at.isoformat() if session.last_chunk_at else None,
        "last_chunk_url": last_chunk_url,
        "note": session.note,
        "created_at": session.created_at.isoformat(),
        "alerts": alerts,
    }


class LiveStartView(APIView):
    """POST /api/ingestion/live/ — start monitoring a live broadcast.

    Body: {"url": "...", "chunk_seconds": 30, "max_chunks": 120}. Special focus
    on TikTok lives (needs a cookies file on the server — see LIVE.md).
    """

    permission_classes = [IsAnalystOrAbove]

    def post(self, request, *args, **kwargs):
        from ingestion.services.live_capture import start_live_session

        url = (request.data.get("url") or "").strip()
        if not url:
            return Response({"detail": "Передайте 'url' эфира."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            chunk_seconds = int(request.data.get("chunk_seconds", 30))
            max_chunks = int(request.data.get("max_chunks", 120))
        except (TypeError, ValueError):
            chunk_seconds, max_chunks = 30, 120
        try:
            session = start_live_session(url, chunk_seconds, max_chunks)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_live_session_payload(session, request), status=status.HTTP_202_ACCEPTED)


class LiveListView(APIView):
    """GET /api/ingestion/live/ — recent live sessions."""

    permission_classes = [IsAnalystOrAbove]

    def get(self, request, *args, **kwargs):
        from ingestion.models import LiveSession

        sessions = LiveSession.objects.select_related("platform").prefetch_related(
            "alerts"
        )[:25]
        return Response({"sessions": [_live_session_payload(s, request) for s in sessions]})


class LiveDetailView(APIView):
    """GET /api/ingestion/live/{id}/ — one session; DELETE stops it."""

    permission_classes = [IsAnalystOrAbove]

    def get(self, request, pk, *args, **kwargs):
        from ingestion.models import LiveSession

        session = get_object_or_404(
            LiveSession.objects.select_related("platform").prefetch_related("alerts"),
            pk=pk,
        )
        return Response(_live_session_payload(session, request))

    def delete(self, request, pk, *args, **kwargs):
        from ingestion.models import LiveSession

        session = get_object_or_404(LiveSession, pk=pk)
        if session.status in (LiveSession.Status.PENDING, LiveSession.Status.LIVE):
            session.status = LiveSession.Status.STOPPED
            session.note = "Остановлено аналитиком."
            session.save(update_fields=["status", "note", "updated_at"])
        return Response(_live_session_payload(session, request))


class VideoStatusView(APIView):
    """GET /api/ingestion/videos/{id}/status/ — poll pipeline progress.

    Returns the download/screening/deep-analysis state plus a compact per-stage
    summary, so the demo page can render a live stepper and explain what each
    stage found.
    """

    permission_classes = [IsAnalystOrAbove]

    def get(self, request, pk, *args, **kwargs):
        video = get_object_or_404(
            Video.objects.select_related(
                "screening_result", "deep_analysis_result", "incident"
            ),
            pk=pk,
        )
        screening = getattr(video, "screening_result", None)
        dar = getattr(video, "deep_analysis_result", None)
        incident = getattr(video, "incident", None)
        download = video.download_status

        # Derive a single "overall" stage for the stepper.
        if download in (Video.DownloadStatus.PENDING, Video.DownloadStatus.DOWNLOADING):
            overall = "downloading"
        elif download == Video.DownloadStatus.FAILED:
            overall = "failed"
        elif screening is None:
            overall = "screening"
        elif screening.status == "error":
            overall = "failed"
        elif screening.status == "clean":
            overall = "clean"  # filtered out at Stage 1 — a valid end state
        elif screening.status == "in_progress":
            overall = "screening"
        else:  # suspicious -> Stage 2
            if dar is None or dar.status == "in_progress":
                overall = "deep_analysis"
            elif dar.status == "completed":
                overall = "completed"
            elif dar.status == "failed":
                overall = "failed"
            else:
                overall = "deep_analysis"

        # Per-stage summary.
        frames = list(video.extracted_frames.all())
        ocr_keywords = sorted(
            {
                kw
                for f in frames
                if getattr(f, "analysis_result", None)
                for kw in (f.analysis_result.ocr_matched_keywords or [])
            }
        )
        signals = []
        audio_triggered = False
        categories = {}
        if screening is not None:
            for s in screening.signals.all():
                signals.append({
                    "module": s.module,
                    "is_triggered": s.is_triggered,
                    "confidence": s.confidence,
                })
                if "audio" in s.module and s.is_triggered:
                    audio_triggered = True
                # Surface rich detail for the new, high-value categories so the
                # UI can render identifiers / brands / links / audio forensics.
                if s.module in ("payment", "brand_link", "audio_forensics", "social_context"):
                    categories[s.module] = {
                        "is_triggered": s.is_triggered,
                        "confidence": s.confidence,
                        "error": s.error,
                        "detail": s.raw_output,
                    }

        processing_ms = (screening.processing_time_ms if screening else 0) + (
            dar.processing_time_ms if dar else 0
        )

        geo = None
        if video.geo_source and video.geo_source != Video.GeoSource.NONE:
            geo = {
                "lat": video.geo_latitude,
                "lon": video.geo_longitude,
                "label": video.geo_label,
                "region": video.geo_region,
                "country": video.geo_country,
                "source": video.geo_source,
                "confidence": round(video.geo_confidence, 2),
                "reasoning": (video.geo_raw or {}).get("reasoning", ""),
            }

        return Response({
            "video_id": video.id,
            "download_status": download,
            "screening_status": screening.status if screening else None,
            "stage2_status": dar.status if dar else None,
            "overall": overall,
            "incident_id": incident.id if incident else None,
            "risk_score": dar.risk_score if dar else None,
            "processing_time_ms": processing_ms,
            "geo": geo,
            "categories": categories,
            "summary": {
                "frames_extracted": len(frames),
                "ocr_keywords": ocr_keywords,
                "audio_triggered": audio_triggered,
                "signals": signals,
            },
        })
