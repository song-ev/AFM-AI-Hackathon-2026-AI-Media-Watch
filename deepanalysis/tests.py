import os
import tempfile
import numpy as np
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.utils import timezone
from ingestion.models import Video, Platform, SocialAccount
from deepanalysis.models import DeepAnalysisResult, ReasoningNode
from incidents.models import Incident
from screening.models import ScreeningResult, ScreeningSignal
from deepanalysis.tasks import run_stage2_analysis

class Stage2IntegrationTest(TestCase):
    def setUp(self):
        now = timezone.now()
        self.platform = Platform.objects.create(code="test", name="Test")
        self.account = SocialAccount.objects.create(
            platform=self.platform,
            username="test_account",
            external_id="123",
            first_seen_at=now,
            last_seen_at=now,
        )
        self.video = Video.objects.create(
            platform=self.platform,
            social_account=self.account,
            external_id="vid123",
            url="http://test",
            local_file_path=tempfile.mktemp(suffix=".mp4"),
            caption="test",
            download_status="downloaded",
            collected_at=now,
        )
        open(self.video.local_file_path, 'a').close()

        self.screening_result = ScreeningResult.objects.create(
            video=self.video,
            status=ScreeningResult.Status.SUSPICIOUS,
            triggered_at=now,
        )
        ScreeningSignal.objects.create(
            screening_result=self.screening_result,
            module="audio_analysis",
            is_triggered=True
        )

    def tearDown(self):
        if os.path.exists(self.video.local_file_path):
            os.remove(self.video.local_file_path)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    # Patch where the names are looked up: tasks.py imports these directly, so
    # they live in the deepanalysis.tasks namespace. The two embedding helpers
    # are called inside link_video_identity, so they stay in their own module.
    @patch('deepanalysis.tasks.full_transcribe')
    @patch('deepanalysis.tasks.semantic_level_analysis')
    @patch('deepanalysis.tasks.detect_fake_screenshots')
    @patch('deepanalysis.services.identity_fingerprinting.extract_voice_embedding')
    @patch('deepanalysis.services.identity_fingerprinting.extract_face_embedding')
    @patch('deepanalysis.tasks.generate_incident_summary')
    def test_end_to_end_stage2(self, mock_summary, mock_face, mock_voice, mock_fakes, mock_semantic, mock_transcribe):
        mock_transcribe.return_value = {"text": "тест", "language": "ru", "segments": []}
        mock_semantic.return_value = {
            "tone": "aggressive",
            "has_call_to_action": True,
            "call_to_action_type": "explicit",
            "false_urgency_detected": True,
            "false_urgency_phrases": ["быстрее"],
            "referral_scheme_explained": False,
            "referral_scheme_summary": None
        }
        mock_fakes.return_value = []
        mock_voice.return_value = np.zeros(256)
        mock_face.return_value = np.zeros(128)
        mock_summary.return_value = "Mocked summary."
        
        run_stage2_analysis.delay(self.video.id)
        
        self.video.refresh_from_db()
        self.assertTrue(hasattr(self.video, 'deep_analysis_result'))
        dar = self.video.deep_analysis_result
        self.assertEqual(dar.status, DeepAnalysisResult.Status.COMPLETED)

        self.assertTrue(hasattr(self.video, 'incident'))
        inc = self.video.incident
        self.assertEqual(inc.summary_text, "Mocked summary.")
        self.assertTrue(inc.risk_score > 0)

        nodes = ReasoningNode.objects.filter(deep_analysis_result=dar)
        self.assertTrue(nodes.exists())
        self.assertTrue(nodes.filter(node_type="verdict").exists())
        self.assertTrue(nodes.filter(node_type="synthesis").exists())
