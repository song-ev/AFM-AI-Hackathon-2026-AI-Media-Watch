import os
import cv2
import numpy as np
from PIL import Image, ImageDraw
from django.test import TestCase, override_settings
from django.utils import timezone
from ingestion.models import Video, Platform, SocialAccount, VideoComment
from screening.models import ScreeningResult, ScreeningSignal
from screening.services.frame_extraction import extract_frames
from screening.services.keywords import match_keywords
from screening.services.audio_analysis import analyze_promise_tone
from screening.services.metadata_analysis import analyze_metadata
from screening.services.social_context_analysis import analyze_social_context
from screening.tasks import run_stage1_screening
from deepanalysis.models import DeepAnalysisResult

class Stage1Tests(TestCase):
    def setUp(self):
        self.platform = Platform.objects.create(code="test", name="Test")
        self.account = SocialAccount.objects.create(
            platform=self.platform,
            username="test_account",
            external_id="123",
            first_seen_at=timezone.now(),
            last_seen_at=timezone.now()
        )
        self.video = Video.objects.create(
            platform=self.platform,
            social_account=self.account,
            external_id="vid123",
            url="http://test",
            posted_at=timezone.now(),
            collected_at=timezone.now(),
            caption="осталось 5 мест на гарантированный доход 1xbet",
        )
        
    def test_extract_frames_synthetic(self):
        test_video_path = "test_synth.mp4"
        out = cv2.VideoWriter(test_video_path, cv2.VideoWriter_fourcc(*'mp4v'), 1, (100, 100))
        for i in range(5):
            frame = np.zeros((100, 100, 3), dtype=np.uint8)
            frame[:] = (i*50, 0, 0)
            out.write(frame)
        out.release()
        
        try:
            timestamps = [0.0, 1.0, 2.0]
            output_dir = "test_frames_out"
            extracted = extract_frames(test_video_path, timestamps, output_dir)
            self.assertEqual(len(extracted), 3)
            for item in extracted:
                self.assertTrue(os.path.exists(item["file_path"]))
                os.remove(item["file_path"])
            os.rmdir(output_dir)
        finally:
            if os.path.exists(test_video_path):
                os.remove(test_video_path)
                
    def test_ocr_and_keywords_synthetic(self):
        img = Image.new('RGB', (300, 100), color=(255, 255, 255))
        d = ImageDraw.Draw(img)
        d.text((10,10), "1XBET", fill=(0,0,0))
        img_path = "test_ocr.jpg"
        img.save(img_path)
        
        try:
            matches = match_keywords("1xbet гарантированный доход")
            self.assertTrue(any(m["term"] == "1xbet" for m in matches))
            self.assertTrue(any(m["term"] == "гарантированный доход" for m in matches))
        finally:
            if os.path.exists(img_path):
                os.remove(img_path)
                
    def test_metadata_analysis(self):
        signal = analyze_metadata(self.video)
        self.assertTrue(signal.is_triggered)
        matches = [m["term"] for m in signal.raw_output["matched_keywords"]]
        self.assertIn("1xbet", matches)
        self.assertIn("гарантированный доход", matches)
        
    def test_social_context(self):
        VideoComment.objects.create(
            video=self.video,
            text="спасибо, вывел 100500 на каспи"
        )
        signal = analyze_social_context(self.video)
        self.assertTrue(signal.is_triggered)
        self.assertTrue(len(signal.raw_output["bot_comments"]) > 0)
        
    def test_audio_tone(self):
        tone = analyze_promise_tone("быстрее только сегодня осталось 2 места")
        self.assertTrue(tone["severity"] > 0.2)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
    def test_stage1_orchestration(self):
        run_stage1_screening.delay(self.video.id)
        
        self.video.refresh_from_db()
        self.assertTrue(hasattr(self.video, 'screening_result'))
        result = self.video.screening_result
        self.assertEqual(result.status, ScreeningResult.Status.SUSPICIOUS)
        
        # DeepAnalysisResult should be created (Stage 2 triggered)
        self.assertTrue(DeepAnalysisResult.objects.filter(video=self.video).exists())
