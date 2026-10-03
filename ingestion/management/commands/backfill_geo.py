"""
Backfill geo-position for already-collected videos.

    python manage.py backfill_geo                 # all downloaded videos
    python manage.py backfill_geo --incidents      # only videos with incidents
    python manage.py backfill_geo --limit 50 --only-missing

Best-effort: each video runs the same multi-source geo pipeline used live
(screening.services.geo_analysis.extract_geo).
"""
from django.core.management.base import BaseCommand

from ingestion.models import Video
from screening.services.geo_analysis import extract_geo


class Command(BaseCommand):
    help = "Compute geo-position for existing videos."

    def add_arguments(self, parser):
        parser.add_argument("--incidents", action="store_true",
                            help="Only videos that have an incident.")
        parser.add_argument("--only-missing", action="store_true",
                            help="Skip videos that already have a resolved geo.")
        parser.add_argument("--limit", type=int, default=0)

    def handle(self, *args, **opts):
        qs = Video.objects.filter(download_status=Video.DownloadStatus.DOWNLOADED)
        if opts["incidents"]:
            qs = qs.filter(incident__isnull=False)
        if opts["only_missing"]:
            qs = qs.filter(geo_source=Video.GeoSource.NONE)
        qs = qs.order_by("-collected_at")
        if opts["limit"]:
            qs = qs[: opts["limit"]]

        total = qs.count()
        resolved = 0
        self.stdout.write(f"Processing {total} videos…")
        for v in qs:
            try:
                r = extract_geo(v)
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(f"  video {v.id}: ERROR {exc}")
                continue
            if r.get("source") and r["source"] != Video.GeoSource.NONE:
                resolved += 1
                self.stdout.write(
                    f"  video {v.id}: {r['label']} [{r['source']}] "
                    f"conf={r['confidence']:.2f}"
                )
        self.stdout.write(self.style.SUCCESS(
            f"Done. {resolved}/{total} videos got a location."
        ))
