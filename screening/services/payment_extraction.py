"""
Payment-identifier extraction (new analysis category).

Fraudulent casino/pyramid videos almost always surface a way to pay or contact:
a Kaspi phone number, a card number, an IBAN, or a crypto wallet — in the
caption, on-screen (OCR) or spoken (transcript). Pulling these out turns a vague
"suspicious video" into an actionable identifier the bank API can already check
(bankapi.risk-check keys off ``SocialAccount.linked_payment_identifier``).

Pure-Python/regex — no external dependency, so this module never fails loud; it
simply finds what it finds. Card numbers are Luhn-validated to cut false hits.
"""
from __future__ import annotations

import logging
import re

from ingestion.models import Video
from screening.models import ScreeningSignal

logger = logging.getLogger(__name__)

# Kazakhstan mobile / Kaspi-style numbers: +7 7xx xxx xx xx or 8 7xx ...
_PHONE_RE = re.compile(r"(?:\+7|8)[\s\-]?7\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}")
# 16–19 digit card-like sequences (spaces/dashes allowed).
_CARD_RE = re.compile(r"\b(?:\d[ \-]?){15,18}\d\b")
# Kazakhstan IBAN: KZ + 2 check digits + 16 alnum.
_IBAN_RE = re.compile(r"\bKZ\d{2}[A-Z0-9]{16}\b", re.IGNORECASE)
# Crypto wallets: BTC (legacy/bech32), ETH/USDT-ERC20, TRON.
_CRYPTO_RES = {
    "btc": re.compile(r"\b(?:bc1[a-z0-9]{25,39}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})\b"),
    "eth": re.compile(r"\b0x[a-fA-F0-9]{40}\b"),
    "tron": re.compile(r"\bT[a-zA-Z0-9]{33}\b"),
}
# Spoken-money cues that often accompany a dictated number.
_PAYMENT_CUES = [
    "каспи", "kaspi", "переведи", "перевод", "номер карты", "на карту",
    "реквизиты", "счёт", "счет", "кошелек", "кошелёк", "wallet", "оплата",
    "halyk", "халык", "jusan", "freedom",
]


def _luhn_ok(digits: str) -> bool:
    """Luhn checksum — filters random 16-digit runs that aren't cards."""
    nums = [int(d) for d in digits if d.isdigit()]
    if len(nums) < 13:
        return False
    total = 0
    parity = len(nums) % 2
    for i, n in enumerate(nums):
        if i % 2 == parity:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _gather_text(video: Video) -> str:
    parts = [video.caption or ""]
    if video.hashtags:
        parts.append(" ".join(video.hashtags))
    if video.social_account and video.social_account.profile_description:
        parts.append(video.social_account.profile_description)
    for frame in video.extracted_frames.all():
        ar = getattr(frame, "analysis_result", None)
        if ar and ar.ocr_text:
            parts.append(ar.ocr_text)
    dar = getattr(video, "deep_analysis_result", None)
    if dar:
        for t in dar.transcripts.all():
            parts.append(t.full_text or "")
    return "\n".join(p for p in parts if p)


def extract_payment_identifiers(text: str) -> dict:
    """Return structured payment identifiers found in free text."""
    found = {"phones": [], "cards": [], "ibans": [], "crypto": [], "cues": []}

    for m in _PHONE_RE.findall(text):
        norm = re.sub(r"[\s\-]", "", m)
        if norm not in found["phones"]:
            found["phones"].append(norm)

    for m in _CARD_RE.findall(text):
        digits = re.sub(r"[ \-]", "", m)
        if _luhn_ok(digits) and digits not in found["cards"]:
            found["cards"].append(digits)

    for m in _IBAN_RE.findall(text):
        up = m.upper()
        if up not in found["ibans"]:
            found["ibans"].append(up)

    low = text.lower()
    for kind, rx in _CRYPTO_RES.items():
        for m in rx.findall(text):
            found["crypto"].append({"type": kind, "address": m})

    found["cues"] = sorted({c for c in _PAYMENT_CUES if c in low})
    return found


def _primary_identifier(found: dict) -> str | None:
    """Pick the single best identifier to link to the bank API."""
    if found["phones"]:
        return found["phones"][0]
    if found["cards"]:
        return found["cards"][0]
    if found["ibans"]:
        return found["ibans"][0]
    if found["crypto"]:
        return found["crypto"][0]["address"]
    return None


def analyze_payment(video: Video) -> ScreeningSignal:
    text = _gather_text(video)
    found = extract_payment_identifiers(text)

    total = (
        len(found["phones"]) + len(found["cards"])
        + len(found["ibans"]) + len(found["crypto"])
    )
    # A bare cue (e.g. "kaspi") with no number is a weak signal; a concrete
    # identifier is a strong one.
    has_identifier = total > 0
    is_triggered = has_identifier or len(found["cues"]) >= 2
    confidence = 0.0
    if has_identifier:
        confidence = min(1.0, 0.6 + 0.1 * total)
    elif found["cues"]:
        confidence = min(0.5, 0.15 * len(found["cues"]))

    # Link the strongest identifier to the account for the bank risk-check path.
    primary = _primary_identifier(found)
    if primary and video.social_account and not video.social_account.linked_payment_identifier:
        video.social_account.linked_payment_identifier = primary
        video.social_account.save(update_fields=["linked_payment_identifier", "updated_at"])

    return ScreeningSignal(
        module=ScreeningSignal.Module.PAYMENT,
        is_triggered=is_triggered,
        confidence=round(confidence, 4),
        raw_output={
            "identifiers": found,
            "primary_identifier": primary,
            "count": total,
        },
    )
