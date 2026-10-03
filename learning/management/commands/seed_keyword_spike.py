"""Seed a realistic keyword spike so the anomaly feature is demonstrable.

Creates a low, flat baseline for a term over the preceding days and a large
burst on the reference day (default: today) in a chosen region — exactly the
"'Авиатор' +400% за 24 часа в регионе Алматы" scenario. Demo/QA only; these are
synthetic observations with no linked video.

    python manage.py seed_keyword_spike --term авиатор --region Алматы --current 24
"""
import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from learning.models import KeywordObservation


class Command(BaseCommand):
    help = "Insert synthetic observations forming a keyword spike (demo)."

    def add_arguments(self, parser):
        parser.add_argument("--term", default="авиатор")
        parser.add_argument("--region", default="Алматы")
        parser.add_argument("--category", default="brand")
        parser.add_argument("--baseline-days", type=int, default=7)
        parser.add_argument("--baseline-max", type=int, default=3,
                            help="Max daily count in the baseline period.")
        parser.add_argument("--current", type=int, default=24,
                            help="Count on the spike (reference) day.")

    def handle(self, *args, **opts):
        term = opts["term"].lower().strip()
        region = opts["region"].strip()
        today = timezone.localdate()

        rows = []
        for i in range(1, opts["baseline_days"] + 1):
            day = today - timedelta(days=i)
            for _ in range(random.randint(0, opts["baseline_max"])):
                rows.append(KeywordObservation(
                    term=term, category=opts["category"],
                    source=KeywordObservation.Source.BRAND,
                    region=region, observed_on=day,
                ))
        for _ in range(opts["current"]):
            rows.append(KeywordObservation(
                term=term, category=opts["category"],
                source=KeywordObservation.Source.BRAND,
                region=region, observed_on=today,
            ))

        KeywordObservation.objects.bulk_create(rows)
        self.stdout.write(self.style.SUCCESS(
            f"Seeded {len(rows)} observations for '{term}' in {region} "
            f"(spike of {opts['current']} today)."
        ))
