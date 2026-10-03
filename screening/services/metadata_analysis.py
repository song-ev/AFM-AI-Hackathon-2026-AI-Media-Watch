import unicodedata
import logging
from ingestion.models import Video
from screening.models import ScreeningSignal
from screening.services.keywords import match_keywords

logger = logging.getLogger(__name__)

def analyze_metadata(video: Video) -> ScreeningSignal:
    """
    Analyzes video caption, hashtags, and social account linktree/profile descriptions.
    """
    text_to_analyze = video.caption or ""
    
    # Add hashtags
    if video.hashtags:
        text_to_analyze += " " + " ".join(video.hashtags)
        
    # Add profile descriptions
    if video.social_account:
        if video.social_account.profile_description:
            text_to_analyze += " " + video.social_account.profile_description
        if video.social_account.linktree_url:
            text_to_analyze += " " + video.social_account.linktree_url

    matches = match_keywords(text_to_analyze)
    is_triggered = len(matches) > 0
    # Real confidence: strongest fuzzy keyword match score (0-100 → 0-1).
    confidence = max((m.get("score", 0) / 100.0 for m in matches), default=0.0)

    signal = ScreeningSignal(
        module=ScreeningSignal.Module.METADATA,
        is_triggered=is_triggered,
        confidence=round(confidence, 4),
        raw_output={
            "analyzed_text": text_to_analyze[:500] + "..." if len(text_to_analyze) > 500 else text_to_analyze,
            "matched_keywords": matches
        }
    )
    
    return signal
