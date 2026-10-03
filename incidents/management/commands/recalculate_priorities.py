"""
Recalculate priority_score for all pending_review incidents.

priority_score decays with time (freshness decay), so this should be run
periodically (e.g. via cron / celery beat).
"""
from django.core.management.base import BaseCommand

from incidents.services import recalculate_pending_priorities


class Command(BaseCommand):
    help = "Recompute priority_score for pending_review incidents."

    def handle(self, *args, **options):
        updated = recalculate_pending_priorities()
        self.stdout.write(self.style.SUCCESS(
            f"Recalculated priority_score for {updated} pending_review incident(s)."
        ))
