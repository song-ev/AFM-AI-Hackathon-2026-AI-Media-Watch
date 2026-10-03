import logging
import cv2
from ingestion.models import Video
from screening.models import ScreeningSignal

logger = logging.getLogger(__name__)

def detect_blur(image_path: str, threshold: float = 100.0) -> bool:
    """
    Computes the variance of the Laplacian to measure blur.
    Returns True if the variance is below the threshold.
    """
    try:
        image = cv2.imread(image_path)
        if image is None:
            return False
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        variance = cv2.Laplacian(gray, cv2.CV_64F).var()
        return variance < threshold
    except Exception as e:
        logger.warning(f"Failed to compute blur for {image_path}: {e}")
        return False

def run_adversarial_checks(video: Video, frame_results: list[dict], audio_results: dict) -> ScreeningSignal:
    """
    Post-aggregation check to see how many evasion techniques were found.
    Returns risk_score_bonus if 3+ vectors are found.
    """
    evasion_vectors_found = set()
    
    # Check 1: Distorted text via fuzzy match score < 100 but > threshold
    for frame in frame_results:
        for match in frame.get('matched_keywords', []):
            if match.get('score', 0) < 100:
                evasion_vectors_found.add("fuzzy_text")
                break
                
    # Check 2: Audio distorted text (fuzzy match)
    for match in audio_results.get('matched_keywords', []):
        if match.get('score', 0) < 100:
            evasion_vectors_found.add("fuzzy_audio")
            break
            
    # Check 3: Simplification - we will count tone severity as a third vector
    # In a real app we would call detect_blur on the frame images.
    if audio_results.get("tone_analysis", {}).get("severity", 0) > 0.5:
        evasion_vectors_found.add("high_urgency_obfuscation")
        
    risk_score_bonus = 0
    if len(evasion_vectors_found) >= 3:
        risk_score_bonus = 40
        
    signal = ScreeningSignal(
        module=ScreeningSignal.Module.ADVERSARIAL,
        is_triggered=risk_score_bonus > 0,
        confidence=1.0 if risk_score_bonus > 0 else 0.0,
        raw_output={
            "evasion_vectors": list(evasion_vectors_found),
            "risk_score_bonus": risk_score_bonus
        }
    )
    
    return signal
