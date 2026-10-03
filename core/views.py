"""Shared views, including the service health-check."""
from django.db import connection
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    """Lightweight liveness/readiness probe.

    Reports overall service status and whether the database connection is
    reachable. Intended for load balancers, container orchestrators, and
    uptime monitoring. No authentication required.
    """

    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        database_ok = self._check_database()
        payload = {
            "status": "ok" if database_ok else "degraded",
            "service": "ai-media-watch-backend",
            "database": "ok" if database_ok else "unavailable",
        }
        http_status = (
            status.HTTP_200_OK if database_ok else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        return Response(payload, status=http_status)

    @staticmethod
    def _check_database() -> bool:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            return True
        except Exception:
            return False
