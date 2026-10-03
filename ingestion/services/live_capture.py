"""
Live-stream capture (feature: проверка эфиров, акцент на TikTok).

Real-time monitoring works by *chunking* a live broadcast: every N seconds we
grab a short segment of the live stream, register it as a normal Video, run the
existing Stage-1 screening on it, and raise a LiveAlert the moment a chunk trips
the pipeline. So fraud is caught while the стрим is still on air.

Pipeline per session:
    resolve_live(url)         -> (manifest_url, is_live, meta)   [yt-dlp]
    capture_chunk(manifest)   -> mp4 file on disk                [ffmpeg]
    -> register_local_video   -> run_stage1_screening            [existing]
    -> LiveAlert if suspicious

TikTok/Instagram lives almost always need a cookies file (YTDLP_COOKIES_FILE);
YouTube lives are usually open. See LIVE.md for what each platform requires.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import uuid

from django.conf import settings

from ingestion.models import LiveSession
from ingestion.services.downloader import detect_platform_code, get_or_create_platform

logger = logging.getLogger("ingestion")


def _ydl_opts(url: str = "") -> dict:
    from ingestion.services.downloader import apply_ydl_network

    opts = {"quiet": True, "noplaylist": True, "skip_download": True}
    apply_ydl_network(opts, url)
    return opts


def resolve_live(url: str) -> dict:
    """Resolve a live URL to a playable manifest + liveness via yt-dlp.

    Returns {manifest_url, is_live, title, streamer}. Raises RuntimeError with a
    clear message if the stream can't be resolved (e.g. not live, needs cookies).
    """
    try:
        import yt_dlp
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("yt-dlp is not installed") from exc

    with yt_dlp.YoutubeDL(_ydl_opts(url)) as ydl:
        info = ydl.extract_info(url, download=False)

    is_live = bool(info.get("is_live"))
    manifest = info.get("manifest_url") or info.get("url")
    # Prefer an HLS/DASH format URL if a direct manifest wasn't surfaced.
    if not manifest:
        for fmt in info.get("formats", []) or []:
            if fmt.get("protocol", "").startswith(("m3u8", "http_dash")):
                manifest = fmt.get("url")
                break
        if not manifest and info.get("formats"):
            manifest = info["formats"][-1].get("url")
    if not manifest:
        raise RuntimeError(
            "Не удалось получить поток эфира (возможно, нужен cookies-файл или "
            "трансляция недоступна)."
        )
    return {
        "manifest_url": manifest,
        "is_live": is_live,
        "title": info.get("title") or "",
        "streamer": info.get("uploader") or info.get("channel") or "",
    }


def capture_chunk(manifest_url: str, seconds: int, out_path: str) -> str:
    """Capture `seconds` of a live manifest into an mp4 via ffmpeg. ''  on fail."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found on PATH; cannot capture live stream.")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    cmd = [
        ffmpeg, "-y", "-loglevel", "error",
        "-i", manifest_url,
        "-t", str(seconds),
        "-c", "copy",                # remux only — fast, no re-encode
        "-bsf:a", "aac_adtstoasc",
        out_path,
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=seconds + 45, check=False)
    except subprocess.TimeoutExpired:
        logger.warning("ffmpeg chunk capture timed out for %s", manifest_url)
    if os.path.exists(out_path) and os.path.getsize(out_path) > 1024:
        return out_path
    return ""


def start_live_session(url: str, chunk_seconds: int = 30, max_chunks: int = 120) -> LiveSession:
    """Create a LiveSession and kick off the monitor loop."""
    code = detect_platform_code(url)
    if code is None:
        raise ValueError(f"Неподдерживаемый URL эфира: {url}")
    platform = get_or_create_platform(code)

    session = LiveSession.objects.create(
        platform=platform,
        url=url,
        status=LiveSession.Status.PENDING,
        chunk_seconds=max(10, min(chunk_seconds, 120)),
        max_chunks=max(1, min(max_chunks, 500)),
    )
    from ingestion.tasks import monitor_live_session
    try:
        monitor_live_session.delay(session.id)
    except Exception as exc:  # noqa: BLE001
        logger.error("Could not enqueue live monitor for %s: %s", session.id, exc)
        session.status = LiveSession.Status.FAILED
        session.note = f"enqueue failed: {exc}"
        session.save(update_fields=["status", "note", "updated_at"])
    return session


def live_chunk_dir(session_id: int) -> str:
    base = getattr(settings, "MEDIA_ROOT", "")
    path = os.path.join(str(base), "live", str(session_id))
    os.makedirs(path, exist_ok=True)
    return path


def new_chunk_path(session_id: int) -> str:
    return os.path.join(live_chunk_dir(session_id), f"chunk_{uuid.uuid4().hex}.mp4")
