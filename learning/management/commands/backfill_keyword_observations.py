"""Backfill KeywordObservation rows from already-screened videos.

The anomaly detector needs a frequency time series; videos screened before this
feature existed have brand/link signals but no observations. This command walks
those videos and (re)builds their observations.

    python manage.py backfill_keyword_observations [--limit N]
"""
from django.core.management.base import BaseCommand

from ingestion.models import Video
from learning.anomaly import record_keyword_observations


class Command(BaseCommand):
    help = "Rebuild keyword observations from existing screened videos."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0,
                            help="Max videos to process (0 = all).")

    def handle(self, *args, **opts):
        qs = (
            Video.objects.filter(screening_result__isnull=False)
            .select_related("screening_result")
            .order_by("-collected_at")
        )
        if opts["limit"]:
            qs = qs[: opts["limit"]]

        total_videos = 0
        total_obs = 0
        for video in qs.iterator():
            written = record_keyword_observations(video)
            total_videos += 1
            total_obs += written
            if total_videos % 100 == 0:
                self.stdout.write(f"  …{total_videos} videos, {total_obs} observations")

        self.stdout.write(self.style.SUCCESS(
            f"Backfilled {total_obs} observations from {total_videos} videos."
        ))
