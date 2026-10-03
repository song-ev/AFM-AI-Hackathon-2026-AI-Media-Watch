"""
Bank-facing API (doc §3.6).

External integration for banks to check the risk of a transfer recipient in
real time. Authentication is via API key only (NOT JWT) — banks are external
systems, not interactive users.

PRIVACY BOUNDARY: responses contain ONLY a binary flag, a risk score, a related
incident count and a generic summary. No internal investigation data
(transcripts, video, evidence chain, analyst identities) is ever exposed.
"""
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from bankapi.authentication import BankApiKeyAuthentication
from bankapi.serializers import RiskCheckRequestSerializer
from bankapi.services import evaluate_risk
from bankapi.throttling import BankApiKeyRateThrottle
from bankapi.timing import log_response_time
from core.permissions import IsBankAdmin


class BankRiskCheckView(APIView):
    """POST /api/bank/v1/risk-check/ — risk verdict for an identifier.

    Auth: required. Header `Authorization: ApiKey <key>`.

    Request body:
        {
          "account_identifier": "<phone | account no | social handle>",
          "identifier_type": "phone" | "account_number" | "social_handle"
        }

    Response (flagged):
        {
          "is_flagged": true,
          "risk_score": 87.0,
          "related_incidents_count": 2,
          "scheme_summary": "Связан с подозрением на ..."
        }

    Response (not flagged):
        {"is_flagged": false}
    """

    # API key only — overrides the global JWT/session authenticators.
    authentication_classes = [BankApiKeyAuthentication]
    permission_classes = [IsBankAdmin]
    throttle_classes = [BankApiKeyRateThrottle]

    @log_response_time
    def post(self, request, *args, **kwargs):
        serializer = RiskCheckRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = evaluate_risk(
            serializer.validated_data["account_identifier"],
            serializer.validated_data["identifier_type"],
        )
        return Response(result, status=status.HTTP_200_OK)


class BankHealthView(APIView):
    """GET /api/bank/v1/health/ — availability probe for bank monitoring.

    No authentication: this only confirms the integration endpoint is up and
    exposes nothing sensitive.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        return Response({"status": "ok", "service": "bank-api", "version": "v1"})
