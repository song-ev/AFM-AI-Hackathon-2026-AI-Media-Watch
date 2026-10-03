"""Management command: download a video by URL (synchronous, for demos)."""
from django.core.management.base import BaseCommand

from ingestion.services.downloader import download_video


class Command(BaseCommand):
    help = "Download a video by URL via yt-dlp (runs synchronously)."

    def add_arguments(self, parser):
        parser.add_argument("url", help="Video URL to download.")

    def handle(self, *args, **options):
        video = download_video(options["url"])
        if video.download_status == video.DownloadStatus.DOWNLOADED:
            self.stdout.write(self.style.SUCCESS(
                f"Downloaded video #{video.id} ({video.external_id})"
            ))
            self.stdout.write(f"  file:   {video.local_file_path}")
            self.stdout.write(f"  sha256: {video.source_hash}")
        else:
            self.stdout.write(self.style.ERROR(
                f"Video #{video.id} status: {video.download_status} "
                f"(see logs for the error)."
            ))
