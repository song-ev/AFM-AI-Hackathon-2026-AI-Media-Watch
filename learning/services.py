from datetime import timedelta
from django.utils import timezone
from learning.models import KeywordDictionaryEntry, KeywordDictionaryVersion
from incidents.models import Incident
from accounts.models import AnalystLabel
import logging

logger = logging.getLogger(__name__)

def collect_weekly_training_candidates() -> dict:
    """
    Collects AnalystLabels from the last week.
    Highlights borderline cases (risk_score 40-60) for priority training.
    """
    one_week_ago = timezone.now() - timedelta(days=7)
    
    labels = AnalystLabel.objects.filter(created_at__gte=one_week_ago)
    
    candidates = {
        "total": 0,
        "confirmed": 0,
        "false_positive": 0,
        "borderline": []
    }
    
    for label in labels:
        candidates["total"] += 1
        if label.decision == AnalystLabel.Decision.CONFIRMED:
            candidates["confirmed"] += 1
        elif label.decision == AnalystLabel.Decision.FALSE_POSITIVE:
            candidates["false_positive"] += 1
            
        incident = label.incident
        if 40 <= incident.risk_score <= 60:
            candidates["borderline"].append(incident.id)
            
    return candidates

def review_dynamic_dictionary_candidates() -> list[KeywordDictionaryEntry]:
    """
    Returns dynamically added entries pending review from the last week.
    """
    one_week_ago = timezone.now() - timedelta(days=7)
    return list(KeywordDictionaryEntry.objects.filter(
        status=KeywordDictionaryEntry.Status.PENDING_REVIEW,
        added_automatically=True,
        created_at__gte=one_week_ago
    ))

def approve_or_reject_dictionary_entry(entry_id: int, decision: str) -> KeywordDictionaryVersion:
    """
    Approves or rejects a pending dictionary entry and creates a snapshot.
    """
    entry = KeywordDictionaryEntry.objects.get(id=entry_id)
    if decision == "approve":
        entry.status = KeywordDictionaryEntry.Status.APPROVED
    elif decision == "reject":
        entry.status = KeywordDictionaryEntry.Status.REJECTED
    else:
        raise ValueError("Invalid decision")
    entry.reviewed_at = timezone.now()
    entry.save(update_fields=["status", "reviewed_at", "updated_at"])

    approved_terms = list(
        KeywordDictionaryEntry.objects.filter(
            status=KeywordDictionaryEntry.Status.APPROVED
        ).values_list("term", flat=True)
    )
    version = KeywordDictionaryVersion.objects.create(
        snapshot=approved_terms,
        note=f"Snapshot after {decision} of entry {entry.term}",
    )

    return version

def rollback_dictionary_version(version_id: int) -> KeywordDictionaryVersion:
    """
    Rolls back the active dictionary to a specific snapshot version.
    """
    target_version = KeywordDictionaryVersion.objects.get(id=version_id)

    approved_terms = target_version.snapshot or []

    KeywordDictionaryEntry.objects.filter(
        status=KeywordDictionaryEntry.Status.APPROVED
    ).exclude(term__in=approved_terms).update(
        status=KeywordDictionaryEntry.Status.REJECTED
    )

    KeywordDictionaryEntry.objects.filter(
        term__in=approved_terms
    ).update(status=KeywordDictionaryEntry.Status.APPROVED)

    new_version = KeywordDictionaryVersion.objects.create(
        snapshot=approved_terms,
        note=f"Rollback to v{target_version.id}",
    )

    return new_version
