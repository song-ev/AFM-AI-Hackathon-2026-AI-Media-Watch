"""
Risk-evaluation logic for the bank API.

PRIVACY: banks receive only a binary flag, a risk score, a count and a generic
summary — never any internal investigation detail (transcripts, video, evidence
chain, analyst names). This is a deliberate confidentiality boundary.
"""
from django.db.models import Count, Max

from incidents.models import Incident

# Generic, non-sensitive summary returned when an identifier is flagged.
# Intentionally vague — no investigation specifics.
SCHEME_SUMMARY = (
    "Связан с подозрением на финансовое мошенничество / нелицензированную "
    "деятельность (гемблинг, инвест-схемы)."
)


def evaluate_risk(account_identifier, identifier_type):
    """Look up an identifier and return the bank-facing risk verdict.

    Single aggregate query over Incident, joining through the (indexed)
    SocialAccount link — the hot path stays at one SQL query.
    """
    if identifier_type == "social_handle":
        lookup = {"video__social_account__username": account_identifier}
    else:  # phone | account_number
        lookup = {"video__social_account__linked_payment_identifier": account_identifier}

    agg = Incident.objects.filter(**lookup).aggregate(
        max_risk=Max("risk_score"), count=Count("id")
    )

    # Not flagged if the identifier is unknown OR known but tied to no incident.
    if not agg["count"]:
        return {"is_flagged": False}

    return {
        "is_flagged": True,
        "risk_score": agg["max_risk"],
        "related_incidents_count": agg["count"],
        "scheme_summary": SCHEME_SUMMARY,
    }
