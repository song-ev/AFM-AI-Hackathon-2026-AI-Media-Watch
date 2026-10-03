"""
Stage-4 model training and inference — the real self-learning step.

``train_risk_model`` turns analysts' confirmed / false-positive decisions into a
trained risk classifier:

  collect labelled incidents → extract features → stratified split → fit
  logistic regression → validate (precision / recall / FPR) → deploy or roll
  back (a new run is promoted only if it does not regress precision vs the
  deployed model).

The trained model is stored as JSON on the winning :class:`FineTuningRun`
(``model_artifact``) and flagged ``is_active``.
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from learning.features import FEATURE_NAMES, build_dataset, extract_features
from learning.ml import LogisticRegression, evaluate
from learning.models import FineTuningRun

logger = logging.getLogger("aimw")

PRECISION_REGRESSION_TOLERANCE = 0.05
DECISION_THRESHOLD = 0.5
MIN_TRAINING_EXAMPLES = 10
MIN_EXAMPLES_FOR_HOLDOUT = 20


def get_active_model_run() -> FineTuningRun | None:
    """The currently deployed model run, or None if none is trained yet."""
    return (
        FineTuningRun.objects.filter(is_active=True)
        .exclude(model_artifact__isnull=True)
        .order_by("-created_at")
        .first()
    )


def _deterministic_split(X, y, ids):
    """Stratified, deterministic (RNG-free) train/validation split."""
    if len(y) < MIN_EXAMPLES_FOR_HOLDOUT:
        return (X, y), (X, y)

    pos = sorted((i for i in range(len(y)) if y[i] >= 0.5), key=lambda i: ids[i])
    neg = sorted((i for i in range(len(y)) if y[i] < 0.5), key=lambda i: ids[i])

    train_idx, val_idx = [], []
    for group in (pos, neg):
        n_val = max(1, len(group) // 4)
        val_idx.extend(group[:n_val])
        train_idx.extend(group[n_val:])

    def take(indices):
        return [X[i] for i in indices], [y[i] for i in indices]

    return take(train_idx), take(val_idx)


@transaction.atomic
def train_risk_model(incidents=None, min_examples: int = MIN_TRAINING_EXAMPLES) -> FineTuningRun:
    """Train, validate and conditionally deploy a new risk model.

    Always returns the FineTuningRun recording the attempt — including the case
    where there is not enough data to train (status stays COLLECTING with a
    note).
    """
    run = FineTuningRun.objects.create(
        status=FineTuningRun.Status.COLLECTING, started_at=timezone.now()
    )

    X, y, ids = build_dataset(incidents)
    run.training_examples_count = len(y)

    n_classes = len({int(round(v)) for v in y})
    if len(y) < min_examples or n_classes < 2:
        run.status = FineTuningRun.Status.COLLECTING
        run.notes = (
            f"Not enough labelled data to train: {len(y)} example(s), "
            f"{n_classes} class(es). Need >= {min_examples} across both "
            f"confirmed and false-positive decisions."
        )
        run.completed_at = timezone.now()
        run.save()
        logger.info("Risk model training skipped: %s", run.notes)
        return run

    run.status = FineTuningRun.Status.TRAINING
    run.save(update_fields=["status", "training_examples_count", "updated_at"])

    (X_train, y_train), (X_val, y_val) = _deterministic_split(X, y, ids)
    model = LogisticRegression().fit(X_train, y_train)

    run.status = FineTuningRun.Status.VALIDATING
    run.save(update_fields=["status", "updated_at"])

    y_pred = [model.predict(x, threshold=DECISION_THRESHOLD) for x in X_val]
    metrics = evaluate(y_val, y_pred)
    run.precision = metrics["precision"]
    run.recall = metrics["recall"]
    run.false_positive_rate = metrics["false_positive_rate"]

    artifact = {
        "model": model.to_dict(),
        "feature_names": FEATURE_NAMES,
        "decision_threshold": DECISION_THRESHOLD,
        "metrics": metrics,
    }

    active = get_active_model_run()
    regresses = (
        active is not None
        and active.precision is not None
        and metrics["precision"] < active.precision - PRECISION_REGRESSION_TOLERANCE
    )

    if regresses:
        run.status = FineTuningRun.Status.ROLLED_BACK
        run.is_active = False
        run.model_artifact = artifact
        run.notes = (
            f"Rolled back: validation precision {metrics['precision']:.3f} "
            f"regressed vs deployed model #{active.id} ({active.precision:.3f}). "
            f"Previous model stays active."
        )
    else:
        FineTuningRun.objects.filter(is_active=True).update(is_active=False)
        run.status = FineTuningRun.Status.DEPLOYED
        run.is_active = True
        run.model_artifact = artifact
        run.notes = (
            f"Deployed. precision={metrics['precision']:.3f} "
            f"recall={metrics['recall']:.3f} "
            f"fpr={metrics['false_positive_rate']:.3f} "
            f"on {len(y_val)} validation example(s)."
        )

    run.completed_at = timezone.now()
    run.save()
    logger.info("Risk model run #%s finished: %s (%s examples)",
                run.id, run.status, run.training_examples_count)
    return run


def predict_incident_risk(incident) -> dict | None:
    """Score one incident with the deployed model, or None if none deployed."""
    active = get_active_model_run()
    if active is None or not active.model_artifact:
        return None

    artifact = active.model_artifact
    model = LogisticRegression.from_dict(artifact["model"])
    threshold = artifact.get("decision_threshold", DECISION_THRESHOLD)
    proba = model.predict_proba(extract_features(incident))
    return {
        "risk_score": round(proba * 100.0, 2),
        "probability": round(proba, 4),
        "is_fraud": proba >= threshold,
        "model_run_id": active.id,
    }


def feature_importances(run: FineTuningRun) -> list[dict]:
    """Standardised-weight importances for a trained run, largest first."""
    if not run.model_artifact:
        return []
    model = run.model_artifact["model"]
    names = run.model_artifact.get("feature_names", FEATURE_NAMES)
    pairs = [
        {"feature": name, "weight": round(w, 4)}
        for name, w in zip(names, model["weights"])
    ]
    pairs.sort(key=lambda p: abs(p["weight"]), reverse=True)
    return pairs
