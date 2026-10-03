"""
Geo-position extraction for a video (feature: where was this filmed / posted).

Multi-source, best available first:

1. ``file_gps``     — GPS embedded in the container metadata (ffprobe). Present
                      on originals shot with a phone; usually stripped by social
                      platforms, but the offline-upload path keeps it.
2. ``platform_tag`` — the platform's own location tag captured at download time
                      (yt-dlp ``location``), stored in ``Video.geo_raw``.
3. ``ai_inference`` — inferred from content: a fast offline gazetteer scan of
                      caption + hashtags + OCR + transcript, then (if nothing
                      matched and an LLM is configured) a single LLM call that
                      names the most likely region. Coordinates always come from
                      the gazetteer, never from the model, so they can't be
                      hallucinated.

The result is saved onto the Video (geo_* fields) and returned as a dict. This
function never raises for a missing dependency — geo is best-effort enrichment,
not a blocking analysis step; a failure simply yields source="none".
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess

from screening.services import geo_gazetteer as gz

logger = logging.getLogger(__name__)

# ISO 6709 like "+43.2389+076.8897/" used by Apple/Android video metadata.
_ISO6709_RE = re.compile(r"([+-]\d+\.?\d*)([+-]\d+\.?\d*)")
# Kazakhstan mobile codes -> country hint.
_KZ_PHONE_RE = re.compile(r"\+7\s?7\d{2}|8\s?7\d{2}")


def _ffprobe_gps(path: str):
    """Return (lat, lon) from container GPS metadata via ffprobe, or None."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe or not path:
        return None
    try:
        out = subprocess.run(
            [ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", path],
            capture_output=True, text=True, timeout=20,
        )
        data = json.loads(out.stdout or "{}")
        tags = (data.get("format") or {}).get("tags") or {}
        for key in ("location", "com.apple.quicktime.location.ISO6709",
                    "location-eng", "QuickTime.GPSCoordinates"):
            raw = tags.get(key)
            if raw:
                m = _ISO6709_RE.search(raw)
                if m:
                    return float(m.group(1)), float(m.group(2))
    except Exception as exc:  # noqa: BLE001 - best effort
        logger.debug("ffprobe GPS failed for %s: %s", path, exc)
    return None


def _gather_text(video) -> str:
    """Concatenate every textual signal we have about a video."""
    parts = [video.caption or ""]
    if video.hashtags:
        parts.append(" ".join(video.hashtags))
    if video.social_account:
        parts.append(video.social_account.profile_description or "")
        parts.append(video.social_account.region or "")
    # OCR keywords / text from extracted frames.
    for frame in video.extracted_frames.all():
        ar = getattr(frame, "analysis_result", None)
        if ar and ar.ocr_text:
            parts.append(ar.ocr_text)
    # Transcript(s) from deep analysis, if present.
    dar = getattr(video, "deep_analysis_result", None)
    if dar:
        for t in dar.transcripts.all():
            parts.append(t.full_text or "")
    return "\n".join(p for p in parts if p)[:6000]


def _llm_region(text: str):
    """Ask the LLM for the most likely region NAME (coords come from gazetteer)."""
    from core.llm import call_llm_json, active_backend

    if active_backend() == "none":
        return None
    try:
        result = call_llm_json(
            f"Текст из видео (описание, субтитры, OCR):\n\"\"\"\n{text[:3000]}\n\"\"\"",
            system=(
                "Ты гео-аналитик. По тексту определи, из какого города/региона "
                "вероятнее всего снято или к какому региону относится видео. "
                "Опирайся на упоминания городов, ориентиров, телефонных кодов, "
                "сленга и языка. Верни ТОЛЬКО JSON: "
                '{"city": "string|null", "region": "string|null", '
                '"country": "string|null", "confidence": 0.0-1.0, '
                '"reasoning": "краткое обоснование на русском"}. '
                "Если данных нет — все поля null и confidence 0."
            ),
            max_tokens=300,
            module="geo_inference",
            default={"city": None, "region": None, "country": None,
                     "confidence": 0.0, "reasoning": ""},
        )
        return result
    except Exception as exc:  # noqa: BLE001 - best effort
        logger.info("Geo LLM inference unavailable: %s", exc)
        return None


def extract_geo(video) -> dict:
    """Compute the best-available geo for a video and persist it. Returns a dict."""
    path = video.resolved_file_path
    raw = dict(video.geo_raw or {})

    # 1) Embedded GPS (highest trust).
    gps = _ffprobe_gps(path) if path else None
    if gps:
        lat, lon = gps
        place = None
        # Reverse to a known city if very close (offline, coarse).
        for token, entry in gz._CITIES.items():  # noqa: SLF001 - intentional
            if abs(entry[3] - lat) < 0.4 and abs(entry[4] - lon) < 0.4:
                place = entry
                break
        label = place[0] if place else f"{lat:.4f}, {lon:.4f}"
        region = place[1] if place else ""
        country = place[2] if place else ""
        return _save(video, lat, lon, label, region, country,
                     video.GeoSource.FILE_GPS, 0.99,
                     {**raw, "method": "file_gps"})

    # 2) Platform location tag captured at download.
    tag = raw.get("platform_location")
    if tag:
        entry = gz.lookup(tag) or gz.scan_text(tag)
        if entry:
            label, region, country, lat, lon = entry
            return _save(video, lat, lon, label, region, country,
                         video.GeoSource.PLATFORM_TAG, 0.9,
                         {**raw, "method": "platform_tag", "tag": tag})

    # 3) Content inference.
    text = _gather_text(video)
    entry = gz.scan_text(text)
    if entry:
        label, region, country, lat, lon = entry
        conf = 0.7
        return _save(video, lat, lon, label, region, country,
                     video.GeoSource.AI_INFERENCE, conf,
                     {**raw, "method": "gazetteer_scan", "matched": label})

    # Phone-code country hint before spending an LLM call.
    country_hint = "Казахстан" if _KZ_PHONE_RE.search(text) else None

    llm = _llm_region(text) if text.strip() else None
    if llm:
        name = llm.get("city") or llm.get("region") or llm.get("country")
        entry = gz.lookup(name or "") or gz.scan_text(name or "")
        if not entry and llm.get("country"):
            entry = gz.country_fallback(llm["country"])
        if entry:
            label, region, country, lat, lon = entry
            conf = float(llm.get("confidence") or 0.5)
            return _save(video, lat, lon,
                         llm.get("city") or label, region or (llm.get("region") or ""),
                         country, video.GeoSource.AI_INFERENCE, max(0.3, min(conf, 0.85)),
                         {**raw, "method": "llm_inference",
                          "reasoning": llm.get("reasoning", ""), "llm": llm})

    if country_hint:
        fb = gz.country_fallback(country_hint)
        if fb:
            label, region, country, lat, lon = fb
            return _save(video, lat, lon, label, region, country,
                         video.GeoSource.AI_INFERENCE, 0.25,
                         {**raw, "method": "phone_code"})

    # Nothing found — record explicitly (source stays "none").
    return _save(video, None, None, "", "", "", video.GeoSource.NONE, 0.0,
                 {**raw, "method": "none"})


def _save(video, lat, lon, label, region, country, source, confidence, raw) -> dict:
    video.geo_latitude = lat
    video.geo_longitude = lon
    video.geo_label = label or ""
    video.geo_region = region or ""
    video.geo_country = country or ""
    video.geo_source = source
    video.geo_confidence = round(float(confidence), 3)
    video.geo_raw = raw
    video.save(update_fields=[
        "geo_latitude", "geo_longitude", "geo_label", "geo_region",
        "geo_country", "geo_source", "geo_confidence", "geo_raw", "updated_at",
    ])
    return {
        "latitude": lat, "longitude": lon, "label": label, "region": region,
        "country": country, "source": source, "confidence": confidence,
    }
