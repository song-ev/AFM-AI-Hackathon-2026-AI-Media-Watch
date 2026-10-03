"""
Offline batch ingestion: analyse every video in a local folder.

    python manage.py ingest_folder "C:/collected_videos"
    python manage.py ingest_folder /data/videos --platform tiktok

Use this for the offline scenario — "we collected 50–100 videos and want to
analyse them" — with no access to social networks. Each file is registered
(hash + evidence chain) and pushed through the same Stage-1 pipeline.
"""
from django.core.management.base import BaseCommand

from ingestion.services.bulk import batch_progress, ingest_folder


class Command(BaseCommand):
    help = "Register and analyse every video file in a folder."

    def add_arguments(self, parser):
        parser.add_argument("folder", type=str)
        parser.add_argument("--platform", type=str, default="youtube")

    def handle(self, *args, **opts):
        batch = ingest_folder(opts["folder"], opts["platform"])
        prog = batch_progress(batch)
        self.stdout.write(self.style.SUCCESS(
            f"Batch #{batch.id}: {prog['total']} videos registered "
            f"({batch.note}). Status: {batch.status}."
        ))
        self.stdout.write(
            "Poll progress at /api/ingestion/batches/%d/ or the Очередь UI." % batch.id
        )
