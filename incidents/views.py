"""Analyst-queue and incident-card API."""
from datetime import timedelta

from django.db.models import Avg, Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status as http_status
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.renderers import BrowsableAPIRenderer, JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from core.pagination import DefaultPageNumberPagination
from core.permissions import IsAnalystOrAbove
from core.renderers import PlainTextRenderer
from deepanalysis.serializers import ReasoningGraphSerializer
from incidents.filters import IncidentFilter
from incidents.models import Incident
from incidents.serializers import (
    AnalystDecisionSerializer,
    EvidenceChainEntrySerializer,
    IncidentDetailSerializer,
    IncidentListSerializer,
)

STATS_WINDOW_HOURS = 24


def detail_queryset():
    """Incident queryset with everything the detail card needs prefetched.

    This is an N+1-prone endpoint; load all relations up front so the number
    of SQL queries stays flat regardless of how much nested data exists.
    """
    return Incident.objects.select_related(
        "video",
        "video__platform",
        "video__social_account",
        "video__screening_result",
        "deep_analysis_result",
    ).prefetch_related(
        "deep_analysis_result__reasoning_nodes",
        "deep_analysis_result__transcripts__flags",
        "deep_analysis_result__fake_screenshots",
        "video__screening_result__signals",
        "evidence_entries",
        "promo_codes",
        "telegram_links",
        "analyst_labels__analyst",
    )


class IncidentListView(ListAPIView):
    """GET /api/incidents/ — paginated, filterable, searchable queue.

    Default ordering: priority_score DESC.
    """

    serializer_class = IncidentListSerializer
    permission_classes = [IsAnalystOrAbove]
    pagination_class = DefaultPageNumberPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = IncidentFilter
    search_fields = ["video__social_account__username", "video__caption"]
    ordering_fields = ["priority_score", "risk_score", "created_at"]
    ordering = ["-priority_score"]

    def get_queryset(self):
        return Incident.objects.select_related(
            "video", "video__platform", "video__social_account"
        )


class IncidentStatsView(APIView):
    """GET /api/incidents/stats/ — aggregates for the queue badge."""

    permission_classes = [IsAnalystOrAbove]

    def get(self, request, *args, **kwargs):
        qs = Incident.objects.all()

        breakdown = {value: 0 for value, _ in Incident.Status.choices}
        for row in qs.values("status").annotate(count=Count("id")):
            breakdown[row["status"]] = row["count"]

        since = timezone.now() - timedelta(hours=STATS_WINDOW_HOURS)
        avg_recent = qs.filter(created_at__gte=since).aggregate(
            avg=Avg("risk_score")
        )["avg"]

        return Response({
            "queue_total": breakdown.get(Incident.Status.PENDING_REVIEW, 0),
            "total": qs.count(),
            "status_breakdown": breakdown,
            "avg_risk_score_24h": round(avg_recent, 2) if avg_recent is not None else 0.0,
        })


class IncidentDetailView(RetrieveAPIView):
    """GET /api/incidents/{id}/ — the full incident card."""

    serializer_class = IncidentDetailSerializer
    permission_classes = [IsAnalystOrAbove]

    def get_queryset(self):
        return detail_queryset()


class IncidentDecisionView(APIView):
    """POST /api/incidents/{id}/decision/ — record an analyst decision."""

    permission_classes = [IsAnalystOrAbove]

    def post(self, request, pk, *args, **kwargs):
        incident = get_object_or_404(Incident, pk=pk)
        serializer = AnalystDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        decision = serializer.validated_data["decision"]
        comment = serializer.validated_data.get("comment") or None

        # Create the label (the post_save signal bumps cases_reviewed_count).
        incident.analyst_labels.create(
            decision=decision,
            comment=comment,
            analyst=request.user,
            decided_at=timezone.now(),
        )

        # The decision values map 1:1 onto incident statuses.
        incident.status = decision
        incident.save(update_fields=["status", "updated_at"])

        # Re-fetch with full prefetch for the returned card.
        incident = detail_queryset().get(pk=pk)
        return Response(
            IncidentDetailSerializer(incident).data,
            status=http_status.HTTP_200_OK,
        )


def reasoning_graph_queryset():
    """Incident queryset with everything the reasoning graph may read."""
    return Incident.objects.select_related(
        "video",
        "video__screening_result",
        "deep_analysis_result",
    ).prefetch_related(
        "video__screening_result__signals",
        "deep_analysis_result__reasoning_nodes",
        "deep_analysis_result__reasoning_edges__from_node",
        "deep_analysis_result__reasoning_edges__to_node",
        "deep_analysis_result__transcripts__flags",
        "deep_analysis_result__fake_screenshots",
        "video__identity_links",
    )


class IncidentReasoningGraphView(APIView):
    """GET /api/incidents/{id}/reasoning-graph/ — graph for vis-network.

    Returns explicit ReasoningNode/Edge data when present, otherwise a graph
    built on the fly from signals (Stage-2 nodes shown as not_applicable when
    Stage 2 didn't run). This GET is read-only and does not persist a cache.
    """

    permission_classes = [IsAnalystOrAbove]

    def get(self, request, pk, *args, **kwargs):
        incident = get_object_or_404(reasoning_graph_queryset(), pk=pk)
        return Response(ReasoningGraphSerializer(incident).data)


class IncidentDossierView(APIView):
    """GET /api/incidents/{id}/dossier/ — generate the PDF dossier ("Собрать досье").

    Returns a ready-to-share PDF with the verdict, risk factors, geo, category
    findings (payment / brands / QR / audio / comment накрутка), screenshots and
    the SHA-256 chain of custody.
    """

    permission_classes = [IsAnalystOrAbove]

    def get(self, request, pk, *args, **kwargs):
        incident = get_object_or_404(
            detail_queryset().prefetch_related(
                "video__extracted_frames__analysis_result",
            ),
            pk=pk,
        )
        try:
            from incidents.dossier import build_incident_dossier
            pdf_bytes = build_incident_dossier(incident)
        except Exception as exc:  # noqa: BLE001 - report generation failure
            return Response(
                {"error": f"Не удалось сформировать досье: {exc}"},
                status=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        resp = HttpResponse(pdf_bytes, content_type="application/pdf")
        resp["Content-Disposition"] = (
            f'attachment; filename="dossier_incident_{incident.id}.pdf"'
        )
        return resp


class IncidentEvidenceChainView(APIView):
    """GET /api/incidents/{id}/evidence-chain/ — the chain of custody.

    JSON by default; `?format=text` returns a human-readable report suitable
    for printing / legal export.
    """

    permission_classes = [IsAnalystOrAbove]
    # PlainTextRenderer makes `format=text` a valid negotiated format.
    renderer_classes = [JSONRenderer, BrowsableAPIRenderer, PlainTextRenderer]

    def get(self, request, pk, *args, **kwargs):
        incident = get_object_or_404(
            Incident.objects.select_related(
                "video", "video__platform"
            ).prefetch_related("evidence_entries"),
            pk=pk,
        )
        entries = list(incident.evidence_entries.all())

        if request.query_params.get("format") == "text":
            report = self._render_text_report(incident, entries)
            return HttpResponse(
                report, content_type="text/plain; charset=utf-8"
            )

        return Response({
            "incident_id": incident.id,
            "entries": EvidenceChainEntrySerializer(entries, many=True).data,
        })

    @staticmethod
    def _render_text_report(incident, entries):
        lines = [
            "EVIDENCE CHAIN OF CUSTODY",
            "=" * 60,
            f"Incident ID : {incident.id}",
            f"Video       : {incident.video.platform.code} / "
            f"{incident.video.external_id}",
            f"Generated   : {timezone.now().isoformat()}",
            f"Entries     : {len(entries)}",
            "=" * 60,
            "",
        ]
        if not entries:
            lines.append("(no evidence entries recorded)")
        for i, entry in enumerate(entries, start=1):
            lines += [
                f"[{i}] {entry.file_type.upper()}",
                f"    SHA-256    : {entry.sha256_hash}",
                f"    Collected  : {entry.collected_at.isoformat()}",
                f"    Method     : {entry.collection_method}",
                f"    File path  : {entry.file_path}",
                "",
            ]
        return "\n".join(lines)
