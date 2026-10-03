"""Tests for video ingestion: local registration, API submit/status."""
import hashlib
import os
import shutil
import tempfile
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from incidents.models import EvidenceChainEntry
from ingestion.models import Platform, Video
from ingestion.services.downloader import (
    detect_platform_code,
    register_local_video,
)

_MEDIA = tempfile.mkdtemp(prefix="aimw-media-")


class PlatformDetectionTests(TestCase):
    def test_known_domains(self):
        self.assertEqual(
            detect_platform_code("https://www.youtube.com/watch?v=x"),
            Platform.Code.YOUTUBE,
        )
        self.assertEqual(
            detect_platform_code("https://vt.tiktok.com/abc/"),
            Platform.Code.TIKTOK,
        )
        self.assertEqual(
            detect_platform_code("https://instagram.com/reel/xyz/"),
            Platform.Code.INSTAGRAM,
        )

    def test_unknown_domain(self):
        self.assertIsNone(detect_platform_code("https://example.com/v/1"))


@override_settings(MEDIA_ROOT=_MEDIA)
class RegisterLocalVideoTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(_MEDIA, ignore_errors=True)
        super().tearDownClass()

    def _make_file(self, content=b"fake-video-bytes"):
        fd, path = tempfile.mkstemp(suffix=".mp4")
        with os.fdopen(fd, "wb") as fh:
            fh.write(content)
        return path, hashlib.sha256(content).hexdigest()

    def test_registers_downloaded_video_with_evidence(self):
        path, expected_hash = self._make_file()
        try:
            video = register_local_video(
                path, "youtube",
                {"username": "demo_channel", "caption": "test clip",
                 "hashtags": ["casino"]},
            )
        finally:
            os.remove(path)

        self.assertEqual(video.download_status, Video.DownloadStatus.DOWNLOADED)
        self.assertEqual(video.source_hash, expected_hash)
        self.assertFalse(os.path.isabs(video.local_file_path))
        self.assertTrue(os.path.exists(video.resolved_file_path))
        with open(video.resolved_file_path, "rb") as stored:
            self.assertEqual(hashlib.sha256(stored.read()).hexdigest(), expected_hash)
        self.assertEqual(video.platform.code, Platform.Code.YOUTUBE)
        self.assertEqual(video.social_account.username, "demo_channel")

        # First chain-of-custody entry: linked to the video, no incident yet.
        entry = EvidenceChainEntry.objects.get(video=video)
        self.assertIsNone(entry.incident)
        self.assertEqual(entry.file_type, EvidenceChainEntry.FileType.VIDEO)
        self.assertEqual(entry.sha256_hash, expected_hash)
        self.assertEqual(entry.collection_method, "local file registration")

    def test_missing_file_marks_failed(self):
        video = register_local_video("/no/such/file.mp4", "tiktok", {})
        self.assertEqual(video.download_status, Video.DownloadStatus.FAILED)
        self.assertFalse(EvidenceChainEntry.objects.filter(video=video).exists())


class IngestionApiTests(TestCase):
    def setUp(self):
        self.analyst = User.objects.create_user(
            "analyst_ing", password="pw", role=User.Role.ANALYST
        )

    def _client(self):
        c = APIClient()
        c.force_authenticate(self.analyst)
        return c

    @patch("ingestion.views.process_video_download.delay")
    def test_submit_returns_video_id_immediately(self, mock_delay):
        resp = self._client().post(
            "/api/ingestion/videos/",
            {"url": "https://www.youtube.com/watch?v=abc"},
            format="json",
        )
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(resp.data["status"], Video.DownloadStatus.DOWNLOADING)
        video_id = resp.data["video_id"]
        self.assertTrue(Video.objects.filter(pk=video_id).exists())
        mock_delay.assert_called_once_with(video_id)

    @patch("ingestion.views.process_video_download.delay")
    def test_submit_unsupported_domain_returns_400(self, mock_delay):
        resp = self._client().post(
            "/api/ingestion/videos/",
            {"url": "https://example.com/v/1"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        mock_delay.assert_not_called()

    @patch("ingestion.views.process_video_download.delay")
    def test_status_endpoint(self, mock_delay):
        client = self._client()
        submit = client.post(
            "/api/ingestion/videos/",
            {"url": "https://www.youtube.com/watch?v=abc"},
            format="json",
        )
        video_id = submit.data["video_id"]
        resp = client.get(f"/api/ingestion/videos/{video_id}/status/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["video_id"], video_id)
        self.assertEqual(
            resp.data["download_status"], Video.DownloadStatus.DOWNLOADING
        )

    def test_submit_requires_auth(self):
        resp = APIClient().post(
            "/api/ingestion/videos/",
            {"url": "https://www.youtube.com/watch?v=abc"},
            format="json",
        )
        self.assertIn(resp.status_code, (401, 403))
