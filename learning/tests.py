"""
Tests for the Stage-4 self-learning risk classifier.

Split into pure-Python model tests (no DB) and end-to-end training/inference
tests that build labelled incidents and exercise the real training pipeline.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from accounts.models import AnalystLabel
from deepanalysis.models import (
    DeepAnalysisResult,
    FakeScreenshotDetection,
    Transcript,
    TranscriptFlag,
)
from incidents.models import Incident
from ingestion.models import Platform, SocialAccount, Video
from screening.models import ScreeningResult, ScreeningSignal

from learning.features import FEATURE_NAMES, build_dataset, extract_features
from learning.ml import LogisticRegression, evaluate
from learning.models import FineTuningRun
from learning.training import get_active_model_run, predict_incident_risk, train_risk_model

User = get_user_model()


class LogisticRegressionUnitTest(TestCase):
    def test_learns_separable_pattern(self):
        X = [[0.0, 0.0], [0.1, 0.2], [0.2, 0.0], [5.0, 5.0], [4.8, 5.2], [5.1, 4.9]]
        y = [0, 0, 0, 1, 1, 1]
        model = LogisticRegression(epochs=500).fit(X, y)
        self.assertEqual(model.predict([0.0, 0.0]), 0)
        self.assertEqual(model.predict([5.0, 5.0]), 1)

    def test_serialisation_round_trip(self):
        model = LogisticRegression(epochs=200).fit([[0.0], [1.0], [2.0], [3.0]], [0, 0, 1, 1])
        restored = LogisticRegression.from_dict(model.to_dict())
        self.assertAlmostEqual(model.predict_proba([2.5]), restored.predict_proba([2.5]), places=9)

    def test_evaluate_metrics(self):
        metrics = evaluate([1, 1, 0, 0], [1, 0, 0, 0])
        self.assertEqual(metrics["precision"], 1.0)
        self.assertEqual(metrics["recall"], 0.5)
        self.assertEqual(metrics["false_positive_rate"], 0.0)


def _make_incident(seed, *, fraud, analyst, now):
    platform, _ = Platform.objects.get_or_create(code="youtube", defaults={"name": "YouTube"})
    account = SocialAccount.objects.create(
        platform=platform, external_id=f"acc-{seed}", username=f"u-{seed}",
        followers_count=200_000 if fraud else 500,
        first_seen_at=now - timedelta(days=10), last_seen_at=now,
    )
    video = Video.objects.create(
        platform=platform, social_account=account, external_id=f"vid-{seed}",
        url=f"https://youtube.com/watch?v={seed}", collected_at=now,
        posted_at=now - timedelta(hours=5),
    )
    screening = ScreeningResult.objects.create(
        video=video, status=ScreeningResult.Status.SUSPICIOUS, triggered_at=now,
    )
    for module in ["metadata", "social_context", "quick_audio", "frame_analysis", "adversarial"]:
        ScreeningSignal.objects.create(
            screening_result=screening, module=module, is_triggered=fraud,
            confidence=0.9 if fraud else 0.0,
            raw_output={"risk_score_bonus": 20} if (fraud and module == "adversarial") else {},
        )
    dar = DeepAnalysisResult.objects.create(
        video=video, status=DeepAnalysisResult.Status.COMPLETED,
        risk_score=85.0 if fraud else 15.0, started_at=now, completed_at=now,
    )
    transcript = Transcript.objects.create(deep_analysis_result=dar, full_text="...", language="ru")
    if fraud:
        for _ in range(5):
            TranscriptFlag.objects.create(
                transcript=transcript, phrase="гарантированный доход",
                category="guarantee", severity=3,
            )
        FakeScreenshotDetection.objects.create(deep_analysis_result=dar, is_fake=True, confidence=0.9)
    incident = Incident.objects.create(
        video=video, deep_analysis_result=dar, risk_score=85.0 if fraud else 15.0,
        status=Incident.Status.CONFIRMED if fraud else Incident.Status.FALSE_POSITIVE,
    )
    AnalystLabel.objects.create(
        incident=incident,
        decision=AnalystLabel.Decision.CONFIRMED if fraud else AnalystLabel.Decision.FALSE_POSITIVE,
        analyst=analyst, decided_at=now,
    )
    return incident


class RiskModelTrainingTest(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.analyst = User.objects.create(username="analyst1", role="analyst")
        self.fraud = [_make_incident(f"f{i}", fraud=True, analyst=self.analyst, now=self.now) for i in range(8)]
        self.clean = [_make_incident(f"c{i}", fraud=False, analyst=self.analyst, now=self.now) for i in range(8)]

    def test_feature_vector_shape(self):
        self.assertEqual(len(extract_features(self.fraud[0])), len(FEATURE_NAMES))

    def test_build_dataset_excludes_unlabelled(self):
        X, y, ids = build_dataset()
        self.assertEqual(len(X), 16)
        self.assertEqual(sum(y), 8)

    def test_training_deploys_active_model(self):
        run = train_risk_model(min_examples=10)
        self.assertEqual(run.status, FineTuningRun.Status.DEPLOYED)
        self.assertTrue(run.is_active)
        self.assertEqual(run.training_examples_count, 16)
        self.assertIsNotNone(run.model_artifact)
        self.assertEqual(get_active_model_run().id, run.id)

    def test_prediction_separates_classes(self):
        train_risk_model(min_examples=10)
        fraud_pred = predict_incident_risk(self.fraud[0])
        clean_pred = predict_incident_risk(self.clean[0])
        self.assertIsNotNone(fraud_pred)
        self.assertGreater(fraud_pred["risk_score"], clean_pred["risk_score"])

    def test_only_one_active_model(self):
        train_risk_model(min_examples=10)
        train_risk_model(min_examples=10)
        self.assertEqual(FineTuningRun.objects.filter(is_active=True).count(), 1)


class InsufficientDataTest(TestCase):
    def test_training_skipped_without_enough_labels(self):
        analyst = User.objects.create(username="analyst2", role="analyst")
        _make_incident("only-fraud", fraud=True, analyst=analyst, now=timezone.now())
        run = train_risk_model(min_examples=10)
        self.assertEqual(run.status, FineTuningRun.Status.COLLECTING)
        self.assertFalse(run.is_active)
        self.assertIsNone(run.model_artifact)
        self.assertIn("Not enough", run.notes)
