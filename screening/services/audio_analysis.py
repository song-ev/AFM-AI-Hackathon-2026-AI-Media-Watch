import os
import re
import logging
from django.conf import settings
from core.exceptions import ModuleDependencyError
from ingestion.models import Video
from screening.models import ScreeningSignal
from screening.services.keywords import match_keywords

logger = logging.getLogger(__name__)

# Cached Whisper model per worker process.
_WHISPER_MODEL = None


def _load_whisper(model_name: str):
    """Load (and cache) a Whisper model, or fail loudly."""
    global _WHISPER_MODEL
    if _WHISPER_MODEL is not None:
        return _WHISPER_MODEL
    try:
        import whisper
    except ImportError as exc:
        raise ModuleDependencyError(
            "quick_audio",
            "openai-whisper is not installed; audio transcription unavailable.",
        ) from exc
    try:
        _WHISPER_MODEL = whisper.load_model(model_name)
    except Exception as exc:  # noqa: BLE001
        raise ModuleDependencyError(
            "quick_audio", f"Could not load Whisper model {model_name!r}: {exc}"
        ) from exc
    return _WHISPER_MODEL


def _video_clip(video_path: str):
    """Open a moviepy VideoFileClip, or fail loudly if moviepy is missing."""
    try:
        from moviepy import VideoFileClip
    except ImportError as exc:
        raise ModuleDependencyError(
            "quick_audio", "moviepy is not installed; cannot extract audio."
        ) from exc
    return VideoFileClip(video_path)


def extract_audio_segment(video_path: str, start_sec: float, duration_sec: float, output_path: str) -> str:
    """
    Extracts an audio segment from a video using moviepy.
    """
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        clip = _video_clip(video_path)
        end_sec = min(start_sec + duration_sec, clip.duration)
        subclip = clip.subclipped(start_sec, end_sec)
        if subclip.audio:
            subclip.audio.write_audiofile(output_path, logger=None)
            clip.close()
            return output_path
        clip.close()
    except Exception as e:
        logger.error(f"Failed to extract audio from {video_path}: {e}")
    return ""

def quick_transcribe(video_path: str) -> dict:
    """
    Transcribes the first 30s and last 30s of the video using Whisper.

    Raises ModuleDependencyError if Whisper/moviepy are unavailable so the
    caller can mark the module errored instead of treating silence as "clean".
    """
    # Fail loudly up-front if the engine is missing.
    model_name = getattr(settings, 'WHISPER_STAGE1_MODEL', 'tiny')
    model = _load_whisper(model_name)

    try:
        clip = _video_clip(video_path)
        duration = clip.duration
        clip.close()

        segments = []
        base_dir = getattr(settings, 'MEDIA_ROOT', os.path.join(settings.BASE_DIR, 'media'))
        temp_dir = os.path.join(base_dir, 'audio_temp')

        if duration <= 60:
            # Transcribe the whole thing
            out_path = os.path.join(temp_dir, f"full_{os.path.basename(video_path)}.wav")
            audio_path = extract_audio_segment(video_path, 0, duration, out_path)
            if audio_path:
                result = model.transcribe(audio_path)
                segments.append({"position": "full", "text": result["text"], "language": result.get("language", "")})
        else:
            # First 30s
            out_start = os.path.join(temp_dir, f"start_{os.path.basename(video_path)}.wav")
            audio_path1 = extract_audio_segment(video_path, 0, 30, out_start)
            if audio_path1:
                res1 = model.transcribe(audio_path1)
                segments.append({"position": "start", "text": res1["text"], "language": res1.get("language", "")})
                
            # Last 30s
            out_end = os.path.join(temp_dir, f"end_{os.path.basename(video_path)}.wav")
            audio_path2 = extract_audio_segment(video_path, duration - 30, 30, out_end)
            if audio_path2:
                res2 = model.transcribe(audio_path2)
                segments.append({"position": "end", "text": res2["text"], "language": res2.get("language", "")})
                
        return {"segments": segments}
    except ModuleDependencyError:
        raise  # propagate: caller marks the module errored
    except Exception as e:
        logger.error(f"Quick transcribe failed for {video_path}: {e}")
        return {"segments": []}

def analyze_promise_tone(text: str) -> dict:
    """
    Heuristic lexical analysis (No LLM here).
    """
    urgency_patterns = [r"только сегодня", r"осталось \d+ мест", r"срочно", r"успей"]
    guarantee_patterns = [r"гарантированный доход", r"100% прибыль", r"без риска", r"обещаю", r"вернем"]
    cta_patterns = [r"переходи по ссылке", r"пиши в директ", r"регистрируйся", r"забирай"]
    
    text_lower = text.lower()
    
    urgency_matches = [p for p in urgency_patterns if re.search(p, text_lower)]
    guarantee_matches = [p for p in guarantee_patterns if re.search(p, text_lower)]
    cta_matches = [p for p in cta_patterns if re.search(p, text_lower)]
    
    severity = 0.0
    if urgency_matches: severity += 0.3
    if guarantee_matches: severity += 0.4
    if cta_matches: severity += 0.2
    
    return {
        "severity": min(1.0, severity),
        "urgency_markers": urgency_matches,
        "guarantee_markers": guarantee_matches,
        "cta_markers": cta_matches
    }

def quick_audio_screening(video: Video) -> ScreeningSignal:
    video_path = video.resolved_file_path
    if not video_path or not os.path.exists(video_path):
        raise ModuleDependencyError(
            "quick_audio",
            "Video has no downloaded local file to analyse.",
        )

    transcribe_result = quick_transcribe(video_path)
    segments = transcribe_result.get("segments", [])

    any_triggered = False
    all_matched_terms = []
    max_severity = 0.0
    max_kw_score = 0.0

    for seg in segments:
        text = seg["text"]
        matches = match_keywords(text)
        tone = analyze_promise_tone(text)

        all_matched_terms.extend(matches)
        max_severity = max(max_severity, tone["severity"])
        max_kw_score = max(
            [max_kw_score] + [m.get("score", 0) / 100.0 for m in matches]
        )

        if matches or tone["severity"] >= 0.5:
            any_triggered = True

    # Real confidence: strongest of (tone severity, keyword match score).
    confidence = max(max_severity, max_kw_score)
    signal = ScreeningSignal(
        module=ScreeningSignal.Module.QUICK_AUDIO,
        is_triggered=any_triggered,
        confidence=round(confidence, 4),
        raw_output={
            "segments": segments,
            "matched_keywords": all_matched_terms,
            "tone_analysis": {"severity": max_severity},
            "triggers_deep_analysis": any_triggered,
        },
    )
    return signal
