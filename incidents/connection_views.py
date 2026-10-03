"""Connection-graph and autocomplete endpoints."""
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsAnalystOrAbove
from incidents.models import PromoCode, TelegramLink
from incidents.services import build_connection_graph
from ingestion.models import SocialAccount

SEARCH_LIMIT = 10


class ConnectionGraphView(APIView):
    """GET /api/connections/graph/ — aggregated identity/connection network.

    Optional filters (query params): account, promo_code, telegram_link,
    identity. With a filter, only the connected subnet is returned; without
    one, the graph is capped at the default node limit (highest degree first).
    """

    permission_classes = [IsAnalystOrAbove]

    def get(self, request, *args, **kwargs):
        filters = {
            key: request.query_params.get(key)
            for key in ("account", "promo_code", "telegram_link", "identity")
            if request.query_params.get(key)
        }
        return Response(build_connection_graph(filters))


class ConnectionSearchView(APIView):
    """GET /api/connections/search/?q= — autocomplete over accounts & codes."""

    permission_classes = [IsAnalystOrAbove]

    def get(self, request, *args, **kwargs):
        q = (request.query_params.get("q") or "").strip()
        results = []
        if q:
            # Uses indexes on username / code / url (block A4).
            for username in (
                SocialAccount.objects.filter(username__icontains=q)
                .values_list("username", flat=True)
                .distinct()[:SEARCH_LIMIT]
            ):
                results.append({"type": "account", "value": username, "label": username})
            for code in (
                PromoCode.objects.filter(code__icontains=q)
                .values_list("code", flat=True)
                .distinct()[:SEARCH_LIMIT]
            ):
                results.append({"type": "promo_code", "value": code, "label": code})
            for url in (
                TelegramLink.objects.filter(url__icontains=q)
                .values_list("url", flat=True)
                .distinct()[:SEARCH_LIMIT]
            ):
                results.append({"type": "telegram_link", "value": url, "label": url})
        return Response({"results": results})
