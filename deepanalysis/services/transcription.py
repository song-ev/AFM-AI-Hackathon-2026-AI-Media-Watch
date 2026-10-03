import os
import json
import logging
from functools import lru_cache
from django.conf import settings
from core.exceptions import ModuleDependencyError
from deepanalysis.models import DeepAnalysisResult, Transcript, TranscriptFlag
from learning.models import KeywordDictionaryEntry
from datetime import timedelta
from django.utils import timezone

logger = logging.getLogger(__name__)


@lru_cache(maxsize=2)
def _load_whisper_model(model_name: str):
    """Load (and cache) a Whisper model. Loading is expensive, so the model is
    kept in memory and reused across videos — a pure speedup, same quality."""
    import whisper
    return whisper.load_model(model_name)


def full_transcribe(video_path: str) -> dict:
    """
    Transcribes the entire video using Whisper (word-level timestamps).

    Fail-loud: raises ModuleDependencyError if Whisper is unavailable so the
    caller records a transcription failure rather than treating an empty
    transcript as "nothing suspicious was said".
    """
    if not video_path or not os.path.exists(video_path):
        raise ModuleDependencyError(
            "transcription",
            f"Video file not found on this machine: {video_path!r}.",
        )

    model_name = getattr(settings, "WHISPER_STAGE2_MODEL", "base")
    try:
        model = _load_whisper_model(model_name)
    except ImportError as exc:
        raise ModuleDependencyError(
            "transcription",
            "openai-whisper is not installed; cannot transcribe audio.",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise ModuleDependencyError(
            "transcription", f"Could not load Whisper model {model_name!r}: {exc}"
        ) from exc

    # ffmpeg (invoked by Whisper) or a corrupt file raise raw errors; wrap them
    # so a transcription failure is recorded as a step error, not a crash that
    # fails the whole Stage-2 pipeline.
    try:
        result = model.transcribe(video_path, word_timestamps=True)
    except Exception as exc:  # noqa: BLE001
        raise ModuleDependencyError(
            "transcription", f"Whisper failed to transcribe {video_path!r}: {exc}"
        ) from exc
    return {
        "text": result.get("text", ""),
        "language": result.get("language", "ru"),
        "segments": result.get("segments", []),
    }

def lexical_level_analysis(transcript_text: str) -> list[dict]:
    """
    Heuristic proximity-based dictionary analysis.
    Looks for combination of words within a token window.
    """
    text = transcript_text.lower()
    words = text.split()
    
    keywords = KeywordDictionaryEntry.objects.filter(status=KeywordDictionaryEntry.Status.APPROVED)
    found_flags = []
    
    # Basic check against the dictionary
    for kw in keywords:
        if kw.term.lower() in text:
            found_flags.append({
                "phrase": kw.term,
                "category": kw.category,
                "severity": 1,
                "level": "lexical"
            })
            
    # Proximity check (e.g. "ставка" and "доход" within 5 words)
    proximity_rules = [
        ({"ставка", "ставки"}, {"доход", "возврат", "гарантия"}),
    ]
    
    window_size = 5
    for i, w in enumerate(words):
        window = set(words[i:i+window_size])
        for base_set, target_set in proximity_rules:
            if w in base_set:
                if window.intersection(target_set):
                    found_flags.append({
                        "phrase": f"Proximity match: {w} + {list(window.intersection(target_set))[0]}",
                        "category": "urgency",
                        "severity": 2,
                        "level": "lexical"
                    })
                    
    return found_flags

_SEMANTIC_SCHEMA_DEFAULTS = {
    "tone": "neutral",
    "has_call_to_action": False,
    "call_to_action_type": "none",
    "false_urgency_detected": False,
    "false_urgency_phrases": [],
    "referral_scheme_explained": False,
    "referral_scheme_summary": None,
}


def semantic_level_analysis(transcript_text: str) -> dict:
    """
    Structured semantic analysis of the transcript via the configured LLM.

    Uses the unified LLM client (core.llm) — OpenAI-compatible endpoint
    (OpenRouter/Qwen) or Anthropic, whichever is configured. Fail-loud: raises
    ModuleDependencyError if no backend is configured, so the caller records a
    step error instead of injecting a fabricated "neutral" verdict. Empty
    transcript text legitimately returns the neutral defaults.
    """
    if not transcript_text.strip():
        return dict(_SEMANTIC_SCHEMA_DEFAULTS)

    from core.llm import call_llm_json

    system_prompt = (
        "You are an expert fraud detection analyst for the financial regulator "
        "of Kazakhstan (illegal casinos, betting, financial pyramids, investment "
        "fraud). Analyze the given video transcript (Russian/Kazakh/English) and "
        "output ONLY a valid JSON object matching this schema:\n"
        "{"
        '"tone": "aggressive"|"soft"|"neutral", '
        '"has_call_to_action": true|false, '
        '"call_to_action_type": "explicit"|"hidden"|"none", '
        '"false_urgency_detected": true|false, '
        '"false_urgency_phrases": ["string"], '
        '"referral_scheme_explained": true|false, '
        '"referral_scheme_summary": "string"|null'
        "}"
    )

    parsed = call_llm_json(
        transcript_text,
        system=system_prompt,
        max_tokens=500,
        module="semantic_analysis",
    )
    for k, v in _SEMANTIC_SCHEMA_DEFAULTS.items():
        parsed.setdefault(k, v)
    return parsed

def check_dynamic_dictionary_promotion():
    """
    Periodic check to promote repeated neutral terms into pending dictionary.
    Called via Celery Beat (learning.tasks.weekly_finetuning_cycle).
    """
    from incidents.models import Incident
    
    recent_confirmed = Incident.objects.filter(
        status=Incident.Status.CONFIRMED
    ).order_by('-created_at')[:5]
    
    if len(recent_confirmed) < 5:
        return
        
    term_counts = {}
    for inc in recent_confirmed:
        dar = getattr(inc, "deep_analysis_result", None)
        if dar is None:
            continue
        # related_name is `transcripts` (a DAR can have several).
        for transcript in dar.transcripts.all():
            for flag in transcript.flags.all():
                phrase = flag.phrase.lower()
                term_counts[phrase] = term_counts.get(phrase, 0) + 1
                
    for term, count in term_counts.items():
        if count >= 5:
            exists = KeywordDictionaryEntry.objects.filter(term__iexact=term).exists()
            if not exists and len(term.split()) <= 3:
                KeywordDictionaryEntry.objects.create(
                    term=term,
                    category=KeywordDictionaryEntry.Category.OTHER,
                    status=KeywordDictionaryEntry.Status.PENDING_REVIEW,
                    added_automatically=True,
                    added_at=timezone.now(),
                )
