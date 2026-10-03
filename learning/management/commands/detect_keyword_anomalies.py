"""Run the keyword anomaly detector and print/persist the spikes.

    python manage.py detect_keyword_anomalies [--no-region] [--baseline-days 7]

Intended to run on a schedule (Celery beat / cron) so the alerts feed stays
fresh; the dashboard endpoint also runs it live with a short cache.
"""
from django.core.management.base import BaseCommand

from learning.anomaly import detect_anomalies


class Command(BaseCommand):
    help = "Detect keyword frequency spikes (trend prediction)."

    def add_arguments(self, parser):
        parser.add_argument("--baseline-days", type=int, default=7)
        parser.add_argument("--no-region", action="store_true",
                            help="Aggregate across all regions.")

    def handle(self, *args, **opts):
        anomalies = detect_anomalies(
            baseline_days=opts["baseline_days"],
            by_region=not opts["no_region"],
            persist=True,
        )
        if not anomalies:
            self.stdout.write("No anomalies detected.")
            return
        for a in anomalies:
            region = f" / {a['region']}" if a["region"] else ""
            self.stdout.write(
                f"  [{a['severity'].upper():6}] '{a['term']}'{region}: "
                f"{a['pct_change']:+.0f}% (now={a['current_count']}, "
                f"baseline={a['baseline_avg']:.1f}, z={a['z_score']:.1f})"
            )
        self.stdout.write(self.style.SUCCESS(f"{len(anomalies)} anomalies."))
