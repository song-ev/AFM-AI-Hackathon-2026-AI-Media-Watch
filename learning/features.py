"""
Feature extraction for the Stage-4 risk classifier.

Turns an :class:`incidents.models.Incident` (with its Stage-1 screening signals
and Stage-2 deep-analysis artifacts) into a fixed-length, ordered numeric
vector. The ground-truth label comes from the analyst's decision.

The feature order is defined once by :data:`FEATURE_NAMES` and must stay stable:
a model is serialised together with this list, so reordering would invalidate
stored artifacts. Add new features at the end.
"""
from __future__ import annotations

import math

from accounts.models import AnalystLabel

_SCREENING_MODULES = ["metadata", "social_context", "quick_audio", "frame_analysis", "adversarial"]
_FLAG_CATEGORIES = ["guarantee", "urgency", "referral", "call_to_action", "keyword"]

FEATURE_NAMES: list[str] = (
    [f"signal_{m}_confidence" for m in _SCREENING_MODULES]
    + ["adversarial_risk_bonus"]
    + ["transcript_flag_count", "transcript_max_severity"]
    + [f"transcript_{c}_count" for c in _FLAG_CATEGORIES]
    + ["fake_screenshot_count", "fake_screenshot_max_confidence"]
    + ["identity_link_count"]
    + ["rule_based_risk_score", "log_followers"]
)


def extract_features(incident) -> list[float]:
    """Build the ordered feature vector for one incident (missing data → zeros)."""
    feats: dict[str, float] = {name: 0.0 for name in FEATURE_NAMES}
    video = getattr(incident, "video", None)

    # --- Stage 1: screening signals (skip errored ones) -------------------
    screening = getattr(video, "screening_result", None) if video else None
    if screening is not None:
        for sig in screening.signals.all():
            if getattr(sig, "error", ""):
                continue
            if sig.module in _SCREENING_MODULES:
                feats[f"signal_{sig.module}_confidence"] = (
                    float(sig.confidence) if sig.is_triggered else 0.0
                )
            if sig.module == "adversarial":
                feats["adversarial_risk_bonus"] = float(
                    (sig.raw_output or {}).get("risk_score_bonus", 0) or 0
                )

    # --- Stage 2: deep-analysis artifacts ---------------------------------
    dar = getattr(incident, "deep_analysis_result", None)
    if dar is not None:
        flag_count = 0
        max_severity = 0.0
        for transcript in dar.transcripts.all():
            for flag in transcript.flags.all():
                flag_count += 1
                max_severity = max(max_severity, float(flag.severity))
                key = f"transcript_{flag.category}_count"
                if key in feats:
                    feats[key] += 1.0
        feats["transcript_flag_count"] = float(flag_count)
        feats["transcript_max_severity"] = max_severity

        fakes = [d for d in dar.fake_screenshots.all() if d.is_fake]
        feats["fake_screenshot_count"] = float(len(fakes))
        feats["fake_screenshot_max_confidence"] = max(
            (float(d.confidence) for d in fakes), default=0.0
        )

    if video is not None:
        feats["identity_link_count"] = float(video.identity_links.count())

    feats["rule_based_risk_score"] = float(getattr(incident, "risk_score", 0.0) or 0.0)
    followers = 0
    if video is not None and getattr(video, "social_account", None) is not None:
        followers = int(video.social_account.followers_count or 0)
    feats["log_followers"] = math.log1p(followers)

    return [feats[name] for name in FEATURE_NAMES]


def incident_label(incident):
    """Ground-truth label from the analyst's most recent decision.

    1.0 = CONFIRMED, 0.0 = FALSE_POSITIVE, None = no usable label (BORDERLINE
    is intentionally excluded from supervised training).
    """
    label = incident.analyst_labels.order_by("-decided_at", "-created_at").first()
    if label is None:
        return None
    if label.decision == AnalystLabel.Decision.CONFIRMED:
        return 1.0
    if label.decision == AnalystLabel.Decision.FALSE_POSITIVE:
        return 0.0
    return None


def build_dataset(incidents=None):
    """Assemble ``(X, y, incident_ids)`` from labelled incidents."""
    if incidents is None:
        from incidents.models import Incident

        incidents = (
            Incident.objects.filter(analyst_labels__isnull=False)
            .distinct()
            .select_related("video", "video__social_account", "deep_analysis_result")
        )

    X: list[list[float]] = []
    y: list[float] = []
    ids: list[int] = []
    for incident in incidents:
        label = incident_label(incident)
        if label is None:
            continue
        X.append(extract_features(incident))
        y.append(label)
        ids.append(incident.id)
    return X, y, ids
