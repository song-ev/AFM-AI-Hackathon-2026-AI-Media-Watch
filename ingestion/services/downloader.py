"""
Video collection (Stage 1, step 0): fetch a video and register it.

`download_video(url)` uses the yt-dlp Python API to download a video and its
metadata, resolves Platform/SocialAccount, stores the file under
MEDIA_ROOT/videos/<id>/, hashes it, and creates the first EvidenceChainEntry
(chain of custody starts at collection, doc §3.5).

`register_local_video(...)` does the same for a file already on disk — so the
demo works even without access to real social networks (see README).

All external calls are wrapped so a failure flips Video.download_status to
"failed" without crashing the caller.
"""
import hashlib
import logging
import os
import re
import shutil
from datetime import datetime, timezone as dt_timezone
from urllib.parse import urlparse
from uuid import uuid4

from django.conf import settings
from django.utils import timezone

from ingestion.models import Platform, SocialAccount, Video

logger = logging.getLogger("ingestion")

# Map known domains to platform codes.
_DOMAIN_TO_CODE = {
    "instagram.com": Platform.Code.INSTAGRAM,
    "instagr.am": Platform.Code.INSTAGRAM,
    "tiktok.com": Platform.Code.TIKTOK,
    "youtube.com": Platform.Code.YOUTUBE,
    "m.youtube.com": Platform.Code.YOUTUBE,
    "youtu.be": Platform.Code.YOUTUBE,
}

_HASHTAG_RE = re.compile(r"#(\w+)")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def detect_platform_code(url):
    """Return a Platform.Code for the URL's domain, or None if unsupported."""
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host in _DOMAIN_TO_CODE:
        return _DOMAIN_TO_CODE[host]
    # Match parent domain (e.g. "vt.tiktok.com" -> "tiktok.com").
    for domain, code in _DOMAIN_TO_CODE.items():
        if host == domain or host.endswith("." + domain):
            return code
    return None


def get_or_create_platform(code):
    """Resolve a Platform from a code string / Platform.Code value."""
    if isinstance(code, Platform):
        return code
    platform, _ = Platform.objects.get_or_create(
        code=code, defaults={"name": Platform(code=code).get_code_display()}
    )
    return platform


def _managed_dir(video_id):
    path = os.path.join(settings.MEDIA_ROOT, "videos", str(video_id))
    os.makedirs(path, exist_ok=True)
    return path


def _apply_impersonation(ydl_opts):
    """Add a browser-impersonation target (needs curl_cffi) to ydl options.

    TikTok / Instagram reject yt-dlp's default TLS fingerprint with HTTP 403;
    impersonating Chrome via curl_cffi gets past it. No-op if curl_cffi isn't
    installed (the request just falls back to the default client).
    """
    target = getattr(settings, "YTDLP_IMPERSONATE", "chrome")
    if not target:
        return
    try:
        from yt_dlp.networking.impersonate import ImpersonateTarget
        ydl_opts["impersonate"] = ImpersonateTarget.from_str(target)
    except Exception as exc:  # noqa: BLE001 - older yt-dlp / missing curl_cffi
        logger.debug("Impersonation unavailable: %s", exc)


def _apply_js_runtimes(ydl_opts):
    """Enable JavaScript runtimes for YouTube signature deciphering.

    yt-dlp only auto-enables "deno"; without an available runtime modern
    YouTube videos fail with "Video unavailable" / missing formats. We add the
    configured runtimes (node by default — usually already installed). The
    Python API expects a dict {runtime: {config}}, unlike the CLI's list.
    """
    runtimes = getattr(settings, "YTDLP_JS_RUNTIMES", ["deno", "node"])
    if runtimes:
        ydl_opts["js_runtimes"] = {name: {} for name in runtimes}


def apply_ydl_network(ydl_opts, url: str = ""):
    """Apply proxy + impersonation + cookies + JS runtimes to yt-dlp options.

    Browser impersonation (curl_cffi) and the residential proxy are workarounds
    for TikTok / Instagram, which return HTTP 403 / need IP rotation. YouTube
    downloads fine over a DIRECT connection; routing its (large) video stream
    through the proxy + curl_cffi instead makes the download fail with
    "curl (56) Connection closed abruptly" or hang. So for YouTube we skip both
    and rely on a JS runtime to solve signatures.

    Cookie/IP binding matters: TikTok returns HTTP 403 when cookies captured on
    one IP are replayed through a different proxy IP. Since a residential proxy
    alone already unlocks public TikTok content, we DON'T attach cookies for
    TikTok when a proxy is set. Other platforms (e.g. Instagram, which needs a
    real login) keep their cookies.
    """
    _apply_js_runtimes(ydl_opts)
    is_youtube = detect_platform_code(url) == Platform.Code.YOUTUBE
    proxy = getattr(settings, "YTDLP_PROXY", "")
    if not is_youtube:
        _apply_impersonation(ydl_opts)
        if proxy:
            ydl_opts["proxy"] = proxy
    cookies = getattr(settings, "YTDLP_COOKIES_FILE", "")
    is_tiktok = "tiktok" in (url or "").lower()
    if cookies and os.path.exists(cookies) and not (is_tiktok and proxy):
        ydl_opts["cookiefile"] = cookies


def _sha256(file_path):
    digest = hashlib.sha256()
    with open(file_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hashtags(info):
    tags = info.get("tags")
    if tags:
        return list(tags)
    text = f"{info.get('description') or ''} {info.get('title') or ''}"
    return _HASHTAG_RE.findall(text)


def _posted_at(info):
    ts = info.get("timestamp")
    if ts:
        return datetime.fromtimestamp(ts, tz=dt_timezone.utc)
    upload_date = info.get("upload_date")  # 'YYYYMMDD'
    if upload_date:
        try:
            return datetime.strptime(upload_date, "%Y%m%d").replace(
                tzinfo=dt_timezone.utc
            )
        except ValueError:
            return None
    return None


def _placeholder_account(platform):
    account, _ = SocialAccount.objects.get_or_create(
        platform=platform,
        external_id="__pending__",
        defaults={
            "username": "__pending__",
            "first_seen_at": timezone.now(),
            "last_seen_at": timezone.now(),
        },
    )
    return account


def _upsert_account(platform, info):
    external_id = str(
        info.get("uploader_id")
        or info.get("channel_id")
        or info.get("uploader")
        or "unknown"
    )
    now = timezone.now()
    account, created = SocialAccount.objects.get_or_create(
        platform=platform,
        external_id=external_id,
        defaults={
            "username": info.get("uploader") or external_id,
            "display_name": info.get("uploader") or "",
            "profile_url": info.get("uploader_url") or "",
            "first_seen_at": now,
            "last_seen_at": now,
        },
    )
    if not created:
        account.last_seen_at = now
        account.save(update_fields=["last_seen_at", "updated_at"])
    return account


def _create_evidence(video, method):
    """Create the first chain-of-custody entry for a collected video."""
    # Imported here to avoid a cross-app import cycle at module load.
    from incidents.models import EvidenceChainEntry

    return EvidenceChainEntry.objects.create(
        incident=None,
        video=video,
        file_type=EvidenceChainEntry.FileType.VIDEO,
        file_path=video.local_file_path or "",
        sha256_hash=video.source_hash or "",
        collected_at=timezone.now(),
        collection_method=method,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def create_pending_video(url):
    """Quickly create a Video stub (status=downloading) for async download.

    Lets the API return a video_id immediately; the heavy download runs later.
    """
    code = detect_platform_code(url)
    if code is None:
        raise ValueError(f"Unsupported video URL / domain: {url}")
    platform = get_or_create_platform(code)
    return Video.objects.create(
        platform=platform,
        social_account=_placeholder_account(platform),
        external_id=f"pending-{uuid4().hex}",
        url=url,
        collected_at=timezone.now(),
        download_status=Video.DownloadStatus.DOWNLOADING,
    )


def download_video(url, video=None):
    """Download a video via yt-dlp and register it. Returns the Video.

    On any failure the Video's download_status is set to "failed" and the
    Video is still returned (the caller/pipeline does not crash).
    """
    code = detect_platform_code(url)
    platform = get_or_create_platform(code) if code else None

    if video is None:
        if platform is None:
            raise ValueError(f"Unsupported video URL / domain: {url}")
        video = Video.objects.create(
            platform=platform,
            social_account=_placeholder_account(platform),
            external_id=f"pending-{uuid4().hex}",
            url=url,
            collected_at=timezone.now(),
            download_status=Video.DownloadStatus.DOWNLOADING,
        )
    else:
        platform = platform or video.platform
        video.download_status = Video.DownloadStatus.DOWNLOADING
        video.save(update_fields=["download_status", "updated_at"])

    try:
        import yt_dlp

        out_dir = _managed_dir(video.id)
        ydl_opts = {
            "outtmpl": os.path.join(out_dir, "%(id)s.%(ext)s"),
            # Prefer a merged mp4 (video+audio): modern YouTube serves HD only as
            # separate streams. Falls back to any progressive/best so it still
            # works if ffmpeg is unavailable.
            "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
            "merge_output_format": "mp4",
            "quiet": True,
            "noprogress": True,
            "noplaylist": True,
            "socket_timeout": 30,
        }
        # Use the configured proxy / impersonation / cookies so TikTok &
        # Instagram (and gated YouTube) actually download, not just enumerate.
        apply_ydl_network(ydl_opts, url)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)

        video.social_account = _upsert_account(platform, info)
        real_external_id = str(info["id"]) if info.get("id") else video.external_id
        # Store the path RELATIVE to MEDIA_ROOT so the record is portable across
        # machines (this DB is shared); resolve back to absolute at read time.
        rel_path = os.path.relpath(file_path, settings.MEDIA_ROOT)
        source_hash = _sha256(file_path)

        # This platform video may already exist (e.g. another machine sharing
        # this DB collected it). Re-attach the freshly downloaded LOCAL file to
        # the existing row instead of violating uniq_video_per_platform.
        existing = (
            Video.objects.filter(platform=platform, external_id=real_external_id)
            .exclude(pk=video.pk)
            .first()
        )
        if existing is not None:
            existing.local_file_path = rel_path
            existing.source_hash = source_hash
            existing.caption = (
                info.get("description") or info.get("title") or existing.caption
            )
            existing.download_status = Video.DownloadStatus.DOWNLOADED
            existing.save(update_fields=[
                "local_file_path", "source_hash", "caption",
                "download_status", "updated_at",
            ])
            Video.objects.filter(pk=video.pk).delete()  # drop the pending stub
            _create_evidence(existing, "yt-dlp automated download (re-attached)")
            logger.info(
                "Re-attached fresh download to existing video %s (%s)",
                existing.id, real_external_id,
            )
            return existing

        video.external_id = real_external_id
        video.caption = info.get("description") or info.get("title") or ""
        video.hashtags = _hashtags(info)
        video.duration_seconds = info.get("duration")
        video.thumbnail_url = info.get("thumbnail") or ""
        video.posted_at = _posted_at(info)
        video.local_file_path = rel_path
        video.source_hash = source_hash
        # Capture any platform-provided location tag for geo analysis later.
        loc_tag = info.get("location") or info.get("location_name")
        if loc_tag:
            video.geo_raw = {**(video.geo_raw or {}), "platform_location": loc_tag}
        video.download_status = Video.DownloadStatus.DOWNLOADED
        video.save()

        _create_evidence(video, "yt-dlp automated download")
        logger.info("Downloaded video %s (%s)", video.id, video.external_id)
        return video

    except Exception as exc:  # noqa: BLE001 — collection must never crash caller
        # Production: a failed download is a failure. We never silently
        # substitute a demo/placeholder video — that would corrupt evidence and
        # the chain of custody. Mark it failed and let the caller/UI surface it.
        logger.exception("Download failed for %s: %s", url, exc)
        video.download_status = Video.DownloadStatus.FAILED
        video.save(update_fields=["download_status", "updated_at"])
        return video


def register_local_video(file_path, platform, metadata=None):
    """Register an on-disk video file as a Video (same effect as download).

    For environments with no access to real social networks. `platform` may be
    a Platform instance or a code string. `metadata` keys (all optional):
    external_id, account_external_id, username, url, caption, hashtags,
    duration_seconds, thumbnail_url, posted_at.
    """
    metadata = metadata or {}
    plat = get_or_create_platform(platform)
    now = timezone.now()

    account, _ = SocialAccount.objects.get_or_create(
        platform=plat,
        external_id=str(metadata.get("account_external_id", "local-account")),
        defaults={
            "username": metadata.get("username", "local_user"),
            "first_seen_at": now,
            "last_seen_at": now,
        },
    )

    video = Video.objects.create(
        platform=plat,
        social_account=account,
        external_id=str(metadata.get("external_id", f"local-{uuid4().hex}")),
        url=metadata.get("url", ""),
        caption=metadata.get("caption", ""),
        hashtags=metadata.get("hashtags", []),
        duration_seconds=metadata.get("duration_seconds"),
        thumbnail_url=metadata.get("thumbnail_url", ""),
        posted_at=metadata.get("posted_at"),
        collected_at=now,
        download_status=Video.DownloadStatus.DOWNLOADING,
    )

    try:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Local file not found: {file_path}")
        dest = os.path.join(_managed_dir(video.id), os.path.basename(file_path))
        shutil.copy2(file_path, dest)
        # Store relative to MEDIA_ROOT (portable across machines).
        video.local_file_path = os.path.relpath(dest, settings.MEDIA_ROOT)
        video.source_hash = _sha256(dest)
        video.download_status = Video.DownloadStatus.DOWNLOADED
        video.save()
        _create_evidence(video, "local file registration")
        logger.info("Registered local video %s", video.id)
        return video
    except Exception as exc:  # noqa: BLE001
        logger.exception("Local registration failed for %s: %s", file_path, exc)
        video.download_status = Video.DownloadStatus.FAILED
        video.save(update_fields=["download_status", "updated_at"])
        return video
