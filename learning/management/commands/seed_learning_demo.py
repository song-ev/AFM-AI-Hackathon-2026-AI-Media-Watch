"""
Seed synthetic, analyst-labelled incidents so the Stage-4 classifier has data
to train on in a local/dev environment.

DEV ONLY — refuses to run when DEBUG is False, so synthetic data can never be
injected into a production database.

    python manage.py seed_learning_demo --count 40
"""
import random
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
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

User = get_user_model()

_MODULES = ["metadata", "social_context", "quick_audio", "frame_analysis", "adversarial"]
_FLAG_CATEGORIES = ["guarantee", "urgency", "referral", "call_to_action", "keyword"]


class Command(BaseCommand):
    help = "Create synthetic labelled incidents for training the risk model (DEV ONLY)."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=40)
        parser.add_argument("--seed", type=int, default=42)

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "Refusing to seed synthetic data with DEBUG=False (production)."
            )

        rng = random.Random(options["seed"])
        count = options["count"]
        now = timezone.now()

        platform, _ = Platform.objects.get_or_create(code="youtube", defaults={"name": "YouTube"})
        analyst, _ = User.objects.get_or_create(
            username="seed_analyst",
            defaults={"role": getattr(User.Role, "ANALYST", "analyst")},
        )

        created = 0
        for i in range(count):
            is_fraud = i % 2 == 0
            suffix = f"seed-{options['seed']}-{i}"

            account = SocialAccount.objects.create(
                platform=platform,
                external_id=f"acc-{suffix}",
                username=f"demo_{suffix}",
                followers_count=rng.randint(50_000, 500_000) if is_fraud else rng.randint(100, 20_000),
                first_seen_at=now - timedelta(days=30),
                last_seen_at=now,
            )
            video = Video.objects.create(
                platform=platform, social_account=account,
                external_id=f"vid-{suffix}", url=f"https://youtube.com/watch?v={suffix}",
                collected_at=now, posted_at=now - timedelta(hours=rng.randint(1, 72)),
            )

            screening = ScreeningResult.objects.create(
                video=video, status=ScreeningResult.Status.SUSPICIOUS, triggered_at=now,
            )
            for module in _MODULES:
                if is_fraud:
                    triggered = rng.random() < 0.8
                    confidence = rng.uniform(0.6, 0.99) if triggered else 0.0
                else:
                    triggered = rng.random() < 0.2
                    confidence = rng.uniform(0.3, 0.6) if triggered else 0.0
                raw = {"risk_score_bonus": rng.randint(10, 30)} if (module == "adversarial" and triggered) else {}
                ScreeningSignal.objects.create(
                    screening_result=screening, module=module,
                    is_triggered=triggered, confidence=confidence, raw_output=raw,
                )

            rule_risk = rng.uniform(60, 95) if is_fraud else rng.uniform(5, 45)
            dar = DeepAnalysisResult.objects.create(
                video=video, status=DeepAnalysisResult.Status.COMPLETED,
                risk_score=rule_risk, started_at=now, completed_at=now,
            )
            transcript = Transcript.objects.create(
                deep_analysis_result=dar,
                full_text="Гарантированный доход!" if is_fraud else "Обычное видео.",
                language="ru",
            )
            for _ in range(rng.randint(3, 7) if is_fraud else rng.randint(0, 1)):
                TranscriptFlag.objects.create(
                    transcript=transcript,
                    phrase="гарантированный доход" if is_fraud else "интересно",
                    category=rng.choice(_FLAG_CATEGORIES),
                    severity=rng.choice([2, 3, 3]) if is_fraud else 1,
                )
            for _ in range(rng.randint(1, 3) if (is_fraud and rng.random() < 0.7) else 0):
                FakeScreenshotDetection.objects.create(
                    deep_analysis_result=dar, is_fake=True, confidence=rng.uniform(0.7, 0.98),
                    artifacts_found=["font_mismatch", "jpeg_artifacts"],
                )

            incident = Incident.objects.create(
                video=video, deep_analysis_result=dar, risk_score=rule_risk,
                status=Incident.Status.CONFIRMED if is_fraud else Incident.Status.FALSE_POSITIVE,
            )
            AnalystLabel.objects.create(
                incident=incident,
                decision=AnalystLabel.Decision.CONFIRMED if is_fraud else AnalystLabel.Decision.FALSE_POSITIVE,
                analyst=analyst, decided_at=now,
            )
            created += 1

        self.stdout.write(self.style.SUCCESS(
            f"Created {created} labelled demo incidents. "
            f"Run `python manage.py train_risk_model` to train on them."
        ))
