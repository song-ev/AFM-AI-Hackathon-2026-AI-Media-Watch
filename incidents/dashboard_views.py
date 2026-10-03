"""
Leadership dashboard aggregations (doc §3.7), for the analyst role.

All aggregation is done in the database (Trunc* + annotate); rows are never
pulled into Python to be summed. Results are cached for 5 minutes since the
data is not real-time critical and the aggregation can be heavy.
"""
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, Sum
from django.db.models.functions import TruncDay, TruncWeek
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsAfmLeadOrAbove, IsAnalystOrAbove
from deepanalysis.models import TranscriptFlag
from incidents.models import Incident
from ingestion.models import SocialAccount
from learning.models import FineTuningRun, KeywordDictionaryEntry
from screening.models import ScreeningResult

CACHE_TTL_SECONDS = 5 * 60
DEFAULT_TREND_DAYS = 7
DEFAULT_ROI_DAYS = 30
MAX_DAYS = 365


def _days_param(request, default):
    """Parse & clamp the `days` query param."""
    raw = request.query_params.get("days")
    try:
        days = int(raw) if raw is not None else default
    except (TypeError, ValueError):
        days = default
    return max(1, min(days, MAX_DAYS))


def _cached(key, producer):
    data = cache.get(key)
    if data is None:
        data = producer()
        cache.set(key, data, CACHE_TTL_SECONDS)
    return data


class _DashboardView(APIView):
    permission_classes = [IsAfmLeadOrAbove]


class TrendsView(_DashboardView):
    """GET /api/dashboard/trends/?days=7 — scheme growth by reach."""

    def get(self, request, *args, **kwargs):
        days = _days_param(request, DEFAULT_TREND_DAYS)
        return Response(_cached(f"dash:trends:{days}", lambda: self._compute(days)))

    @staticmethod
    def _compute(days):
        since = timezone.now() - timedelta(days=days)

        per_day = (
            Incident.objects.filter(created_at__gte=since)
            .annotate(day=TruncDay("created_at"))
            .values("day")
            .annotate(
                incidents=Count("id"),
                followers_reach=Sum("video__social_account__followers_count"),
            )
            .order_by("day")
        )

        # Scheme type proxied by TranscriptFlag.category, counted per incident/day.
        by_category = (
            TranscriptFlag.objects.filter(
                transcript__deep_analysis_result__incident__created_at__gte=since
            )
            .annotate(
                day=TruncDay("transcript__deep_analysis_result__incident__created_at")
            )
            .values("day", "category")
            .annotate(
                count=Count(
                    "transcript__deep_analysis_result__incident", distinct=True
                )
            )
            .order_by("day")
        )

        series = {}
        for row in per_day:
            key = row["day"].date().isoformat()
            series[key] = {
                "day": key,
                "incidents": row["incidents"],
                "followers_reach": row["followers_reach"] or 0,
                "by_category": {},
            }
        for row in by_category:
            key = row["day"].date().isoformat()
            entry = series.setdefault(
                key,
                {"day": key, "incidents": 0, "followers_reach": 0, "by_category": {}},
            )
            entry["by_category"][row["category"]] = row["count"]

        return {
            "days": days,
            "since": since.date().isoformat(),
            "series": [series[k] for k in sorted(series)],
        }


class GeographyView(_DashboardView):
    """GET /api/dashboard/geography/ — accounts by region."""

    def get(self, request, *args, **kwargs):
        return Response(_cached("dash:geography", self._compute))

    @staticmethod
    def _compute():
        rows = (
            SocialAccount.objects.values("region")
            .annotate(
                account_count=Count("id"),
                followers=Sum("followers_count"),
            )
            .order_by("-account_count")
        )
        return {
            "distribution": [
                {
                    "region": row["region"] or "unknown",
                    "account_count": row["account_count"],
                    "followers": row["followers"] or 0,
                }
                for row in rows
            ]
        }


class GeoPointsView(_DashboardView):
    """GET /api/dashboard/geo-points/ — geolocated videos for the map.

    Returns one point per video that has resolved coordinates, plus a
    region-level aggregation for the heatmap/choropleth. Analyst+ access (the
    map lives on the leadership dashboard).
    """

    permission_classes = [IsAnalystOrAbove]

    def get(self, request, *args, **kwargs):
        return Response(_cached("dash:geo-points", self._compute))

    @staticmethod
    def _compute():
        from ingestion.models import Video

        qs = (
            Video.objects.exclude(geo_source=Video.GeoSource.NONE)
            .filter(geo_latitude__isnull=False, geo_longitude__isnull=False)
            .select_related("social_account", "incident", "deep_analysis_result",
                            "platform")
            .order_by("-collected_at")[:500]
        )
        points = []
        regions: dict = {}
        for v in qs:
            inc = getattr(v, "incident", None)
            dar = getattr(v, "deep_analysis_result", None)
            risk = (inc.risk_score if inc else None) or (dar.risk_score if dar else 0.0)
            points.append({
                "video_id": v.id,
                "incident_id": inc.id if inc else None,
                "lat": v.geo_latitude,
                "lon": v.geo_longitude,
                "label": v.geo_label,
                "region": v.geo_region or "Неизвестно",
                "country": v.geo_country,
                "source": v.geo_source,
                "confidence": round(v.geo_confidence, 2),
                "risk_score": round(risk or 0.0, 1),
                "platform": v.platform.code if v.platform_id else "",
                "username": v.social_account.username if v.social_account_id else "",
                "caption": (v.caption or "")[:120],
            })
            r = regions.setdefault(
                v.geo_region or "Неизвестно",
                {"region": v.geo_region or "Неизвестно", "count": 0,
                 "lat": v.geo_latitude, "lon": v.geo_longitude, "max_risk": 0.0},
            )
            r["count"] += 1
            r["max_risk"] = max(r["max_risk"], round(risk or 0.0, 1))
        return {
            "points": points,
            "regions": sorted(regions.values(), key=lambda x: -x["count"]),
            "total": len(points),
        }


class KeywordTrendsView(_DashboardView):
    """GET /api/dashboard/keyword-trends/ — new dictionary terms by week."""

    def get(self, request, *args, **kwargs):
        return Response(_cached("dash:keyword-trends", self._compute))

    @staticmethod
    def _compute():
        rows = (
            KeywordDictionaryEntry.objects.filter(added_at__isnull=False)
            .annotate(week=TruncWeek("added_at"))
            .values("week", "category")
            .annotate(count=Count("id"))
            .order_by("week")
        )
        series = {}
        for row in rows:
            key = row["week"].date().isoformat()
            entry = series.setdefault(key, {"week": key, "total": 0, "by_category": {}})
            entry["by_category"][row["category"]] = row["count"]
            entry["total"] += row["count"]

        # The actual recently-learned terms (for the term cloud / list).
        recent = (
            KeywordDictionaryEntry.objects.order_by("-added_at", "-id")[:40]
        )
        terms = [
            {
                "term": e.term,
                "category": e.category,
                "status": e.status,
                "added_automatically": e.added_automatically,
                "added_at": e.added_at.date().isoformat() if e.added_at else None,
            }
            for e in recent
        ]
        return {
            "series": [series[k] for k in sorted(series)],
            "terms": terms,
            "total_terms": KeywordDictionaryEntry.objects.count(),
            "auto_learned": KeywordDictionaryEntry.objects.filter(
                added_automatically=True
            ).count(),
        }


class KeywordAnomaliesView(_DashboardView):
    """GET /api/dashboard/keyword-anomalies/ — keyword frequency spikes.

    Runs the anomaly detector over the keyword observation time series (cached
    a few minutes) and returns the alert feed plus a short per-term sparkline.
    Example alert: "'Авиатор' +400% за 24 часа в регионе Алматы".
    """

    def get(self, request, *args, **kwargs):
        by_region = request.query_params.get("by_region", "1") != "0"
        key = f"dash:kw-anomalies:{int(by_region)}"
        return Response(_cached(key, lambda: self._compute(by_region)))

    @staticmethod
    def _compute(by_region):
        from learning.anomaly import detect_anomalies, keyword_series

        anomalies = detect_anomalies(by_region=by_region, persist=True)
        # Attach a sparkline to the top spikes for the UI.
        for a in anomalies[:12]:
            a["series"] = keyword_series(
                a["term"], region=a["region"] or None
            )
        return {
            "anomalies": anomalies,
            "total": len(anomalies),
            "high": sum(1 for a in anomalies if a["severity"] == "high"),
        }


class RoiView(_DashboardView):
    """GET /api/dashboard/roi/?days=30 — model metrics + time saved (doc §4.4)."""

    def get(self, request, *args, **kwargs):
        days = _days_param(request, DEFAULT_ROI_DAYS)
        return Response(_cached(f"dash:roi:{days}", lambda: self._compute(days)))

    @staticmethod
    def _compute(days):
        since = timezone.now() - timedelta(days=days)

        last_run = FineTuningRun.objects.order_by("-started_at").first()
        model = None
        if last_run is not None:
            model = {
                "run_id": last_run.id,
                "status": last_run.status,
                "precision": last_run.precision,
                "recall": last_run.recall,
                "false_positive_rate": last_run.false_positive_rate,
            }

        confirmed = Incident.objects.filter(
            status=Incident.Status.CONFIRMED, created_at__gte=since
        ).count()

        # Videos auto-cleared at Stage 1 = manual reviews avoided.
        auto_rejected = ScreeningResult.objects.filter(
            status=ScreeningResult.Status.CLEAN, triggered_at__gte=since
        ).count()
        seconds = settings.ANALYST_AVG_REVIEW_SECONDS_PER_VIDEO
        saved_hours = round(auto_rejected * seconds / 3600.0, 1)

        return {
            "period_days": days,
            "model": model,
            "confirmed_incidents": confirmed,
            "auto_rejected_stage1": auto_rejected,
            "analyst_time_saved_hours": saved_hours,
            "assumptions": {
                "avg_manual_review_seconds_per_video": seconds,
                "note": "Demo assumption — not measured.",
            },
        }
