"""
Casino/bookmaker brand + link analysis (new analysis category).

Three deterministic, high-precision signals folded into one module:

* brand mentions  — a curated list of gambling/betting brands (1xBet, Mostbet,
  Aviator, Lucky Jet, Vavada, …) matched over caption + OCR + transcript.
* links/domains   — URLs and bare domains extracted from text, scored against a
  suspicious-TLD / known-mirror heuristic (1xbet-*, *.bet, *.casino, link
  shorteners that hide the destination, Telegram invite links).
* QR codes        — decoded from extracted frames with OpenCV; the encoded URL
  is run through the same domain heuristic. Gambling ads love on-screen QR.

OpenCV is optional here — if it is missing we still do brand+link analysis and
note QR as unavailable (this is enrichment, not a blocking step).
"""
from __future__ import annotations

import logging
import re

from ingestion.models import Video
from screening.models import ScreeningSignal

logger = logging.getLogger(__name__)

# Curated gambling / betting brands (lowercased). Extend freely.
CASINO_BRANDS = [
    "1xbet", "1хбет", "mostbet", "мостбет", "melbet", "parimatch", "пари матч",
    "vavada", "вавада", "pin-up", "пинап", "пин ап", "1win", "1вин",
    "aviator", "авиатор", "lucky jet", "лаки джет", "jetx", "jet x",
    "olimp", "олимп", "betboom", "fonbet", "фонбет", "leon", "winline",
    "ramenbet", "starda", "drip casino", "gama casino", "selector",
    "888", "bcgame", "stake", "roobet",
]

# Generic gambling / casino indicators (not specific brands). These catch a
# casino stream whose title/speech says "казино/слоты/ставки" without naming a
# brand. Word-boundary matched so "ставка" doesn't hit inside other words.
GAMBLING_TERMS = [
    "казино", "casino", "слот", "слоты", "slot", "slots", "рулетк", "roulette",
    "ставк", "bet365", "букмекер", "blackjack", "блэкджек", "покер", "poker",
    "фриспин", "free spin", "занос", "заносы", "кэшаут", "cashout", "депозит",
    "бонус казино", "игровой автомат", "однорукий бандит", "крупье", "джекпот",
    "jackpot", "бет", "беттинг", "betting", "гэмблинг", "gambling", "казиноонлайн",
    "онлайн казино", "online casino", "вывод средств", "промокод казино",
]

_URL_RE = re.compile(r"https?://[^\s\)\]\"'<>]+", re.IGNORECASE)
# Bare domains like "1xbet.com", "casino.win", "best-stavka.kz".
_DOMAIN_RE = re.compile(
    r"\b(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+"
    r"(?:com|net|org|win|bet|casino|club|vip|top|xyz|live|io|kz|ru|info|link|cc|tg|me"
    r"|ly|gd|co|app|online|site|fun|pro|space|store|games)\b",
    re.IGNORECASE,
)
_SUSPICIOUS_TLDS = {"win", "bet", "casino", "club", "vip", "top", "xyz", "cc"}
_SHORTENERS = {"bit.ly", "tinyurl.com", "cutt.ly", "is.gd", "t.co", "clck.ru", "vk.cc"}
_BRAND_DOMAIN_HINTS = ("1xbet", "mostbet", "melbet", "vavada", "pinup", "pin-up",
                       "1win", "aviator", "parimatch", "fonbet", "stavka", "casino",
                       "bet", "slot")


def _gather_text(video: Video) -> tuple[str, list]:
    parts = [video.caption or ""]
    if video.hashtags:
        parts.append(" ".join(video.hashtags))
    if video.social_account:
        parts.append(video.social_account.profile_description or "")
        parts.append(video.social_account.linktree_url or "")
    for frame in video.extracted_frames.all():
        ar = getattr(frame, "analysis_result", None)
        if ar and ar.ocr_text:
            parts.append(ar.ocr_text)
    dar = getattr(video, "deep_analysis_result", None)
    if dar:
        for t in dar.transcripts.all():
            parts.append(t.full_text or "")
    return "\n".join(p for p in parts if p), list(video.extracted_frames.all())


def find_brands(text: str) -> list[str]:
    low = text.lower()
    return sorted({b for b in CASINO_BRANDS if b in low})


def find_gambling_terms(text: str) -> list[str]:
    """Generic gambling indicators present in the text (deduped by stem)."""
    low = text.lower()
    return sorted({t for t in GAMBLING_TERMS if t in low})


def _domain_of(url: str) -> str:
    m = re.sub(r"^https?://", "", url, flags=re.IGNORECASE)
    return m.split("/")[0].split("?")[0].lower().strip()


def score_link(url: str) -> dict:
    """Score a single URL/domain for suspiciousness (0-1) with reasons."""
    domain = _domain_of(url)
    tld = domain.rsplit(".", 1)[-1] if "." in domain else ""
    reasons = []
    score = 0.0
    if tld in _SUSPICIOUS_TLDS:
        score += 0.5
        reasons.append(f"подозрительный домен .{tld}")
    if domain in _SHORTENERS:
        score += 0.4
        reasons.append("сократитель ссылок (скрывает адрес)")
    if any(h in domain for h in _BRAND_DOMAIN_HINTS):
        score += 0.6
        reasons.append("домен содержит бренд/термин азартных игр")
    if "t.me/" in url.lower() or domain in ("t.me", "telegram.me"):
        score += 0.3
        reasons.append("ссылка в Telegram")
    return {"url": url, "domain": domain, "score": min(1.0, score), "reasons": reasons}


def extract_links(text: str) -> list[dict]:
    seen = set()
    out = []
    for url in _URL_RE.findall(text):
        d = _domain_of(url)
        if d and d not in seen:
            seen.add(d)
            out.append(score_link(url))
    for dom in _DOMAIN_RE.findall(text):
        d = dom.lower()
        if d not in seen and "." in d:
            seen.add(d)
            out.append(score_link(d))
    return out


def decode_qr_from_frames(frames) -> list[dict]:
    """Decode QR codes from extracted frames via OpenCV. Empty if cv2 missing."""
    try:
        import cv2
    except ImportError:
        return []
    detector = cv2.QRCodeDetector()
    results = []
    for frame in frames:
        try:
            img = cv2.imread(frame.file_path)
            if img is None:
                continue
            data, _, _ = detector.detectAndDecode(img)
            if data:
                entry = {"timestamp_sec": frame.timestamp_sec, "data": data}
                if data.lower().startswith("http") or "." in data:
                    entry["link"] = score_link(data)
                results.append(entry)
        except Exception as exc:  # noqa: BLE001 - per-frame best effort
            logger.debug("QR decode failed on frame %s: %s", frame.id, exc)
    return results


def analyze_brand_link(video: Video) -> ScreeningSignal:
    text, frames = _gather_text(video)
    brands = find_brands(text)
    gambling_terms = find_gambling_terms(text)
    links = extract_links(text)
    qr_codes = decode_qr_from_frames(frames)

    suspicious_links = [l for l in links if l["score"] >= 0.5]
    qr_links = [q["link"] for q in qr_codes if q.get("link")]
    suspicious_qr = [q for q in qr_links if q["score"] >= 0.5]

    # A named brand, or several generic gambling terms, or a suspicious link/QR
    # all flag the video. A single generic term alone is weak (could be an
    # off-hand mention), so require 2+ unless a brand/link is also present.
    strong_gambling = bool(brands) or len(gambling_terms) >= 2
    is_triggered = bool(strong_gambling or suspicious_links or suspicious_qr)

    confidence = 0.0
    if brands:
        confidence = max(confidence, 0.9)
    if len(gambling_terms) >= 2:
        confidence = max(confidence, min(0.95, 0.6 + 0.1 * len(gambling_terms)))
    elif gambling_terms:
        confidence = max(confidence, 0.4)
    if suspicious_links:
        confidence = max(confidence, max(l["score"] for l in suspicious_links))
    if suspicious_qr:
        confidence = max(confidence, 0.9)  # on-screen QR to a betting site

    return ScreeningSignal(
        module=ScreeningSignal.Module.BRAND_LINK,
        is_triggered=is_triggered,
        confidence=round(confidence, 4),
        raw_output={
            "brands": brands,
            "gambling_terms": gambling_terms,
            "links": links,
            "suspicious_links": suspicious_links,
            "qr_codes": qr_codes,
            "qr_available": True,
        },
    )
