"""
Batch / continuous ingestion (feature: analyse a large stream of videos).

Three entry points, all producing a ``BatchJob`` whose progress the UI polls:

* ``submit_bulk_urls(urls)``      — paste 50–100 links, each downloaded +
  screened independently in the background.
* ``ingest_folder(path)``         — register every video file in a local folder
  (offline: "we collected 50–100 videos and want to analyse them").
* ``enumerate_source(url, limit)``— list recent videos of a channel / @account /
  hashtag page with yt-dlp ``extract_flat`` (no full download), then bulk-submit
  them. This is the robust, dependency-light path that works for YouTube and (with
  a cookies file) TikTok/Instagram. See PARSING.md for the per-platform notes.
"""
from __future__ import annotations

import logging
import os

from django.conf import settings

from ingestion.models import BatchJob, Platform, Video
from ingestion.services.downloader import (
    create_pending_video,
    detect_platform_code,
    register_local_video,
)

logger = logging.getLogger("ingestion")

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".flv"}
MAX_BULK = 200


def _enqueue_download(video_id: int):
    from ingestion.tasks import process_video_download
    try:
        process_video_download.delay(video_id)
    except Exception as exc:  # noqa: BLE001 - broker/eager
        logger.error("enqueue download failed for %s: %s", video_id, exc)


def _enqueue_screening(video_id: int):
    from screening.tasks import run_stage1_screening
    try:
        run_stage1_screening.delay(video_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("enqueue screening failed for %s: %s", video_id, exc)


def submit_bulk_urls(urls: list[str]) -> BatchJob:
    """Create pending videos for each supported URL and kick off downloads."""
    clean = []
    seen = set()
    for u in urls:
        u = (u or "").strip()
        if not u or u in seen:
            continue
        seen.add(u)
        clean.append(u)
    clean = clean[:MAX_BULK]

    batch = BatchJob.objects.create(
        kind=BatchJob.Kind.BULK_URLS, status=BatchJob.Status.RUNNING
    )
    created = 0
    skipped = []
    for url in clean:
        if detect_platform_code(url) is None:
            skipped.append(url)
            continue
        # Reuse an already-collected video instead of duplicating work.
        existing = (
            Video.objects.filter(url=url)
            .exclude(download_status=Video.DownloadStatus.FAILED)
            .order_by("-collected_at")
            .first()
        )
        if existing is not None:
            existing.batch_job = batch
            existing.save(update_fields=["batch_job", "updated_at"])
            created += 1
            continue
        try:
            video = create_pending_video(url)
        except ValueError:
            skipped.append(url)
            continue
        video.batch_job = batch
        video.save(update_fields=["batch_job", "updated_at"])
        _enqueue_download(video.id)
        created += 1

    batch.total = created
    batch.note = f"submitted={created}; skipped={len(skipped)}"
    if created == 0:
        batch.status = BatchJob.Status.FAILED
    batch.save(update_fields=["total", "note", "status", "updated_at"])
    return batch


def ingest_folder(folder: str, platform: str = "youtube") -> BatchJob:
    """Register every video file in a folder as a Video and screen it."""
    batch = BatchJob.objects.create(
        kind=BatchJob.Kind.FOLDER, source=folder, status=BatchJob.Status.RUNNING
    )
    if not os.path.isdir(folder):
        batch.status = BatchJob.Status.FAILED
        batch.note = f"Folder not found: {folder}"
        batch.save(update_fields=["status", "note", "updated_at"])
        return batch

    files = sorted(
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if os.path.splitext(f)[1].lower() in VIDEO_EXTS
    )[:MAX_BULK]

    created = 0
    for path in files:
        video = register_local_video(
            path, platform, {"caption": os.path.basename(path)}
        )
        video.batch_job = batch
        video.save(update_fields=["batch_job", "updated_at"])
        if video.download_status == Video.DownloadStatus.DOWNLOADED:
            _enqueue_screening(video.id)
            created += 1

    batch.total = created
    batch.note = f"registered={created} of {len(files)} files"
    batch.status = BatchJob.Status.RUNNING if created else BatchJob.Status.FAILED
    batch.save(update_fields=["total", "note", "status", "updated_at"])
    return batch


def enumerate_source(source_url: str, limit: int = 30) -> list[str]:
    """List recent video URLs from a channel / @account / hashtag via yt-dlp.

    Uses ``extract_flat`` so we only pull the index (fast, no media). Returns a
    list of canonical video URLs to feed into ``submit_bulk_urls``.
    """
    try:
        import yt_dlp
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("yt-dlp is not installed") from exc

    opts = {
        "quiet": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "playlistend": limit,
        "noplaylist": False,
    }
    from ingestion.services.downloader import apply_ydl_network
    apply_ydl_network(opts, source_url)

    urls = []
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(source_url, download=False)
        entries = info.get("entries") or []
        for e in entries[:limit]:
            if not e:
                continue
            url = e.get("url") or e.get("webpage_url")
            # extract_flat may return bare IDs for YouTube.
            if url and not url.startswith("http") and e.get("ie_key") == "Youtube":
                url = f"https://www.youtube.com/watch?v={url}"
            if url:
                urls.append(url)
    return urls


def parse_source(source_url: str, limit: int = 30) -> BatchJob:
    """Enumerate a source then bulk-submit its videos as one batch."""
    try:
        urls = enumerate_source(source_url, limit)
    except Exception as exc:  # noqa: BLE001
        batch = BatchJob.objects.create(
            kind=BatchJob.Kind.SOURCE_PARSE, source=source_url,
            status=BatchJob.Status.FAILED, note=f"enumerate failed: {exc}",
        )
        return batch

    batch = submit_bulk_urls(urls)
    batch.kind = BatchJob.Kind.SOURCE_PARSE
    batch.source = source_url
    batch.note = f"{batch.note}; enumerated={len(urls)}"
    batch.save(update_fields=["kind", "source", "note", "updated_at"])
    return batch


def cancel_batch(batch: BatchJob) -> BatchJob:
    """Stop a batch: mark it cancelled and fail its not-yet-finished videos.

    Queued download/screening tasks check the batch status and skip cancelled
    work (see ingestion.tasks / screening guard), so no new heavy work starts.
    Videos already downloaded keep their results.
    """
    if batch.status in (BatchJob.Status.COMPLETED, BatchJob.Status.CANCELLED):
        return batch
    # Set CANCELLED *first*, then fail the pending videos. Doing it in this order
    # closes the race with a concurrent batch_progress poll that would otherwise
    # see RUNNING + done==total (after the videos are failed) and auto-complete.
    batch.status = BatchJob.Status.CANCELLED
    batch.save(update_fields=["status", "updated_at"])
    stopped = batch.videos.filter(
        download_status__in=[Video.DownloadStatus.PENDING,
                             Video.DownloadStatus.DOWNLOADING]
    ).update(download_status=Video.DownloadStatus.FAILED)
    batch.note = (batch.note + f"; cancelled, stopped={stopped}").lstrip("; ")
    batch.save(update_fields=["note", "updated_at"])
    return batch


def batch_is_cancelled(video) -> bool:
    """True if the video belongs to a cancelled batch (task guard)."""
    bj = getattr(video, "batch_job", None)
    return bj is not None and bj.status == BatchJob.Status.CANCELLED


def batch_progress(batch: BatchJob) -> dict:
    """Aggregate per-video status into a progress summary for the UI."""
    videos = batch.videos.select_related(
        "screening_result", "deep_analysis_result", "incident",
        "social_account", "platform",
    )
    counts = {"downloading": 0, "screening": 0, "deep_analysis": 0,
              "completed": 0, "clean": 0, "failed": 0}
    items = []
    for v in videos:
        overall = _video_overall(v)
        counts[overall] = counts.get(overall, 0) + 1
        inc = getattr(v, "incident", None)
        dar = getattr(v, "deep_analysis_result", None)
        items.append({
            "video_id": v.id,
            "url": v.url,
            "overall": overall,
            "risk_score": (inc.risk_score if inc else None)
            or (dar.risk_score if dar else None),
            "incident_id": inc.id if inc else None,
            "thumbnail_url": v.thumbnail_url or "",
            "caption": (v.caption or "")[:80],
            "platform": v.platform.code if v.platform_id else "",
            "username": v.social_account.username if v.social_account_id else "",
        })

    done = counts["completed"] + counts["clean"] + counts["failed"]
    total = batch.total or len(items)
    # Auto-complete the batch once everything reaches a terminal state.
    if total and done >= total and batch.status == BatchJob.Status.RUNNING:
        batch.status = BatchJob.Status.COMPLETED
        batch.save(update_fields=["status", "updated_at"])

    # Weighted progress so the bar visibly moves while videos are mid-pipeline,
    # not only when they reach a terminal state.
    stage_weight = {
        "downloading": 0.1, "screening": 0.45, "deep_analysis": 0.75,
        "completed": 1.0, "clean": 1.0, "failed": 1.0,
    }
    weighted = sum(stage_weight.get(s, 0.0) * n for s, n in counts.items())
    progress = round(100 * weighted / total, 1) if total else 0.0
    in_progress = counts["screening"] + counts["deep_analysis"]

    return {
        "batch_id": batch.id,
        "kind": batch.kind,
        "source": batch.source,
        "status": batch.status,
        "total": total,
        "done": done,
        "progress": progress,
        "in_progress": in_progress,
        "counts": counts,
        "flagged": counts["completed"],
        "items": items,
        "created_at": batch.created_at.isoformat(),
    }


def _video_overall(v: Video) -> str:
    download = v.download_status
    if download in (Video.DownloadStatus.PENDING, Video.DownloadStatus.DOWNLOADING):
        return "downloading"
    if download == Video.DownloadStatus.FAILED:
        return "failed"
    screening = getattr(v, "screening_result", None)
    if screening is None:
        return "screening"
    if screening.status == "error":
        return "failed"
    if screening.status == "clean":
        return "clean"
    if screening.status == "in_progress":
        return "screening"
    dar = getattr(v, "deep_analysis_result", None)
    if dar is None or dar.status == "in_progress":
        return "deep_analysis"
    if dar.status == "completed":
        return "completed"
    if dar.status == "failed":
        return "failed"
    return "deep_analysis"
