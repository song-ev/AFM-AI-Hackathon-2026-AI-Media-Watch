"""
Keyword trend-prediction / anomaly detection (всплески ключевых слов).

Two halves:

1. ``record_keyword_observations(video)`` — called after Stage-1 screening to
   log every tracked term in a video (casino brands + gambling terms detected by
   the brand/link module, plus hashtags) dated by the video and tagged with its
   region. This builds the time series the detector runs on.

2. ``detect_anomalies(...)`` — for each term, compares the most recent day's
   frequency against a rolling baseline over the preceding ``baseline_days`` and
   flags statistically significant spikes (percent jump + z-score). Optionally
   per-region, so the alert reads "'Авиатор' +400% за 24 часа в регионе Алматы".

Pure-Python statistics (mean/std) over DB-aggregated daily counts — no numpy
needed, no LLM, fully offline.
"""
from __future__ import annotations

import logging
import math
from datetime import date, timedelta

from django.db.models import Count
from django.utils import timezone

from learning.models import KeywordAnomaly, KeywordObservation

logger = logging.getLogger(__name__)

# Detection defaults.
DEFAULT_BASELINE_DAYS = 7
DEFAULT_MIN_CURRENT = 3        # ignore noise: need a few hits in the spike day
DEFAULT_PCT_THRESHOLD = 100.0  # at least +100% vs baseline to be "a spike"
DEFAULT_Z_THRESHOLD = 2.0
# Terms too generic to be interesting as a trend signal on their own.
_STOPWORD_TERMS = {"бет", "bet", "casino", "казино", "slot", "слот"}


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------
def _video_day(video) -> date:
    dt = video.posted_at or video.collected_at or timezone.now()
    return timezone.localtime(dt).date() if timezone.is_aware(dt) else dt.date()


def record_keyword_observations(video) -> int:
    """(Re)build KeywordObservation rows for one video. Idempotent.

    Reads the brand/link screening signal (brands + gambling_terms) and the
    video hashtags. Returns the number of observations written.
    """
    region = (video.geo_region or "").strip()
    observed_on = _video_day(video)

    terms: list[tuple[str, str, str]] = []  # (term, source, category)
    screening = getattr(video, "screening_result", None)
    if screening is not None:
        sig = screening.signals.filter(module="brand_link").first()
        if sig and sig.raw_output:
            for b in sig.raw_output.get("brands", []) or []:
                terms.append((b, KeywordObservation.Source.BRAND, "brand"))
            for g in sig.raw_output.get("gambling_terms", []) or []:
                terms.append((g, KeywordObservation.Source.GAMBLING_TERM, "gambling"))
    for tag in (video.hashtags or [])[:30]:
        tag = str(tag).lstrip("#").lower().strip()
        if len(tag) >= 3:
            terms.append((tag, KeywordObservation.Source.HASHTAG, "hashtag"))

    # Dedupe by normalized term, keeping the strongest source.
    seen: dict[str, tuple[str, str, str]] = {}
    for term, source, category in terms:
        key = term.lower().strip()
        if not key:
            continue
        seen.setdefault(key, (key, source, category))

    KeywordObservation.objects.filter(video=video).delete()
    rows = [
        KeywordObservation(
            term=term, source=source, category=category,
            region=region, observed_on=observed_on, video=video,
        )
        for term, source, category in seen.values()
    ]
    if rows:
        KeywordObservation.objects.bulk_create(rows, ignore_conflicts=True)
    return len(rows)


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------
def _daily_counts(term: str, region: str | None, start: date, end: date) -> dict[date, int]:
    qs = KeywordObservation.objects.filter(
        term=term, observed_on__gte=start, observed_on__lte=end
    )
    if region:
        qs = qs.filter(region=region)
    rows = qs.values("observed_on").annotate(c=Count("id"))
    return {r["observed_on"]: r["c"] for r in rows}


def _severity(pct: float, z: float) -> str:
    if pct >= 300 or z >= 4:
        return KeywordAnomaly.Severity.HIGH
    if pct >= 150 or z >= 3:
        return KeywordAnomaly.Severity.MEDIUM
    return KeywordAnomaly.Severity.LOW


def detect_anomalies(
    *,
    reference_date: date | None = None,
    baseline_days: int = DEFAULT_BASELINE_DAYS,
    min_current: int = DEFAULT_MIN_CURRENT,
    pct_threshold: float = DEFAULT_PCT_THRESHOLD,
    z_threshold: float = DEFAULT_Z_THRESHOLD,
    by_region: bool = True,
    persist: bool = True,
) -> list[dict]:
    """Find terms whose ``reference_date`` frequency spikes over baseline.

    Returns a list of anomaly dicts (also upserted into KeywordAnomaly when
    ``persist``). ``reference_date`` defaults to the latest day that has any
    observation (so it works on historical demo data, not only "today").
    """
    ref = reference_date
    if ref is None:
        latest = KeywordObservation.objects.order_by("-observed_on").values_list(
            "observed_on", flat=True
        ).first()
        ref = latest or timezone.localdate()

    base_start = ref - timedelta(days=baseline_days)
    base_end = ref - timedelta(days=1)

    # Candidate (term, region) pairs that appear on the reference day.
    group_fields = ["term", "category"] + (["region"] if by_region else [])
    current_rows = (
        KeywordObservation.objects.filter(observed_on=ref)
        .values(*group_fields)
        .annotate(c=Count("id"))
        .filter(c__gte=min_current)
    )

    anomalies: list[dict] = []
    for row in current_rows:
        term = row["term"]
        if term in _STOPWORD_TERMS:
            continue
        region = row.get("region", "") if by_region else ""
        current = row["c"]

        daily = _daily_counts(term, region if by_region else None, base_start, base_end)
        # Fill every baseline day (missing day = 0) so a brand-new word reads as
        # a genuine spike from a flat-zero baseline.
        series = [daily.get(base_start + timedelta(days=i), 0) for i in range(baseline_days)]
        n = len(series)
        mean = sum(series) / n if n else 0.0
        var = sum((x - mean) ** 2 for x in series) / n if n else 0.0
        std = math.sqrt(var)

        if mean <= 0:
            pct = 999.9 if current >= min_current else 0.0
        else:
            pct = (current - mean) / mean * 100.0
        z = (current - mean) / std if std > 0 else (3.5 if mean <= 0 else 0.0)

        is_spike = current >= min_current and pct >= pct_threshold and (
            z >= z_threshold or mean <= 0
        )
        if not is_spike:
            continue

        sample_ids = list(
            KeywordObservation.objects.filter(
                term=term, observed_on=ref,
                **({"region": region} if by_region else {}),
            )
            .exclude(video__isnull=True)
            .values_list("video_id", flat=True)[:10]
        )

        anomaly = {
            "term": term,
            "category": row.get("category", ""),
            "region": region,
            "observed_on": ref.isoformat(),
            "window_days": baseline_days,
            "current_count": current,
            "baseline_avg": round(mean, 2),
            "pct_change": round(min(pct, 999.9), 1),
            "z_score": round(z, 2),
            "severity": _severity(pct, z),
            "sample_video_ids": sample_ids,
        }
        anomalies.append(anomaly)

        if persist:
            KeywordAnomaly.objects.update_or_create(
                term=term, region=region, observed_on=ref,
                defaults={
                    "category": anomaly["category"],
                    "window_days": baseline_days,
                    "current_count": current,
                    "baseline_avg": anomaly["baseline_avg"],
                    "pct_change": anomaly["pct_change"],
                    "z_score": anomaly["z_score"],
                    "severity": anomaly["severity"],
                    "sample_video_ids": sample_ids,
                },
            )

    anomalies.sort(key=lambda a: (-a["pct_change"], -a["z_score"]))
    return anomalies


def keyword_series(term: str, *, days: int = 21, region: str | None = None) -> list[dict]:
    """Daily counts for one term over the last ``days`` (for the sparkline)."""
    end = KeywordObservation.objects.filter(term=term).order_by("-observed_on").values_list(
        "observed_on", flat=True
    ).first() or timezone.localdate()
    start = end - timedelta(days=days - 1)
    daily = _daily_counts(term, region, start, end)
    return [
        {"day": (start + timedelta(days=i)).isoformat(),
         "count": daily.get(start + timedelta(days=i), 0)}
        for i in range(days)
    ]
