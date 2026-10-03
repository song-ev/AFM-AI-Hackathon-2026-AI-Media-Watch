import os
import cv2
import numpy as np
import logging
from django.conf import settings
from PIL import Image, ExifTags
from core.exceptions import ModuleDependencyError
from deepanalysis.models import FakeScreenshotDetection, DeepAnalysisResult
from ingestion.models import Video
from screening.models import ExtractedFrame

logger = logging.getLogger(__name__)

def find_payment_screenshot_candidates(video: Video) -> list[ExtractedFrame]:
    """
    Filters extracted frames for payment screenshot candidates using heuristics.
    """
    candidates = []
    frames = ExtractedFrame.objects.filter(video=video).select_related("analysis_result")

    for frame in frames:
        if not os.path.exists(frame.file_path):
            continue

        img = cv2.imread(frame.file_path)
        if img is None:
            continue

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, 100, minLineLength=100, maxLineGap=10)

        has_ui_elements = lines is not None and len(lines) > 5

        analysis = getattr(frame, "analysis_result", None)
        text = analysis.ocr_text.lower() if analysis and analysis.ocr_text else ""
        payment_keywords = ["₸", "тенге", "перевод", "kaspi", "halyk", "kzt"]
        has_payment_text = any(kw in text for kw in payment_keywords)

        if has_ui_elements and has_payment_text:
            candidates.append(frame)
            
    return candidates

def check_font_consistency(frame_path: str, bank_name: str) -> dict:
    """
    Detect inconsistent text rendering — a common forgery tell.

    Genuine bank UIs render their primary text in a single, uniform typeface, so
    word glyph heights cluster tightly. Pasted/edited amounts usually break that
    uniformity. We OCR the word boxes and measure the coefficient of variation
    (std/mean) of their heights; an unusually high CoV is flagged as suspicious.

    Fail-loud: raises ModuleDependencyError if the OCR engine is unavailable.
    """
    try:
        import pytesseract
    except ImportError as exc:
        raise ModuleDependencyError(
            "fake_screenshot", "pytesseract is not installed; cannot analyse fonts."
        ) from exc

    tesseract_cmd = getattr(settings, "TESSERACT_CMD", "tesseract")
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    img = cv2.imread(frame_path)
    if img is None:
        return {"is_suspicious": False, "details": "Frame could not be read."}

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    min_conf = getattr(settings, "OCR_MIN_WORD_CONFIDENCE", 40.0)
    try:
        data = pytesseract.image_to_data(
            gray, lang="eng+rus", output_type=pytesseract.Output.DICT
        )
    except pytesseract.TesseractNotFoundError as exc:
        raise ModuleDependencyError(
            "fake_screenshot",
            f"Tesseract binary not found at {tesseract_cmd!r}.",
        ) from exc

    heights = [
        float(data["height"][i])
        for i in range(len(data["text"]))
        if float(data["conf"][i]) >= min_conf
        and data["text"][i].strip()
        and float(data["height"][i]) > 0
    ]

    # Not enough text to judge consistency — inconclusive, not suspicious.
    if len(heights) < 6:
        return {
            "is_suspicious": False,
            "details": f"Too few text tokens ({len(heights)}) to assess font consistency.",
            "word_count": len(heights),
        }

    mean_h = float(np.mean(heights))
    cov = float(np.std(heights) / mean_h) if mean_h > 0 else 0.0
    # Empirical threshold: uniform UI text typically sits well below ~0.35.
    is_suspicious = cov > 0.35
    return {
        "is_suspicious": bool(is_suspicious),
        "coefficient_of_variation": round(cov, 4),
        "word_count": len(heights),
        "details": (
            f"Font-height CoV={cov:.3f} over {len(heights)} tokens "
            f"({'inconsistent' if is_suspicious else 'consistent'})."
        ),
    }

def detect_clone_artifacts(frame_path: str) -> dict:
    """
    Detects clone artifacts using Error Level Analysis (ELA).
    """
    try:
        original = Image.open(frame_path).convert('RGB')
        temp_path = frame_path + ".temp.jpg"
        
        original.save(temp_path, 'JPEG', quality=90)
        compressed = Image.open(temp_path)
        
        ela_image = np.abs(np.array(original, dtype=np.int16) - np.array(compressed, dtype=np.int16))
        ela_image = np.clip(ela_image * 10, 0, 255).astype(np.uint8)
        
        max_diff = np.max(ela_image)
        os.remove(temp_path)
        
        is_suspicious = max_diff > 100
        
        return {
            "is_suspicious": bool(is_suspicious),
            "max_ela_diff": float(max_diff),
            "details": f"ELA max difference: {max_diff}"
        }
    except Exception as e:
        logger.error(f"Error in detect_clone_artifacts: {e}")
        return {"is_suspicious": False, "details": str(e)}

def check_image_metadata(frame_path: str) -> dict:
    """
    Checks EXIF metadata.
    Для кадров, извлечённых из видео, EXIF почти всегда пуст — эта проверка 
    релевантна для отдельно загруженных скриншотов.
    """
    try:
        img = Image.open(frame_path)
        exif = img._getexif()
        if exif is None:
            return {
                "is_suspicious": False,
                "details": "No EXIF data found (expected for video frames)."
            }
            
        suspicious_software = ["photoshop", "gimp", "lightroom", "canva"]
        for tag_id, value in exif.items():
            tag = ExifTags.TAGS.get(tag_id, tag_id)
            if tag == "Software" and any(sw in str(value).lower() for sw in suspicious_software):
                return {
                    "is_suspicious": True,
                    "details": f"Suspicious software detected in EXIF: {value}"
                }
                
        return {"is_suspicious": False, "details": "EXIF data looks normal."}
    except Exception as e:
        return {"is_suspicious": False, "details": str(e)}

def detect_fake_screenshots(video: Video, deep_analysis_result: DeepAnalysisResult) -> list[FakeScreenshotDetection]:
    """
    Orchestrates fake screenshot detection on candidates.
    """
    candidates = find_payment_screenshot_candidates(video)
    detections = []
    
    for frame in candidates:
        font_res = check_font_consistency(frame.file_path, "kaspi")
        clone_res = detect_clone_artifacts(frame.file_path)
        meta_res = check_image_metadata(frame.file_path)

        # Confidence scales with how many independent checks agree (each ~0.33),
        # rather than a single hardcoded value.
        checks = [font_res, clone_res, meta_res]
        positives = sum(1 for c in checks if c.get("is_suspicious"))
        is_fake = positives > 0
        confidence = round(positives / len(checks), 4)

        detection = FakeScreenshotDetection.objects.create(
            deep_analysis_result=deep_analysis_result,
            is_fake=is_fake,
            confidence=confidence,
            artifacts_found={
                "font_consistency": font_res,
                "clone_artifacts": clone_res,
                "metadata_check": meta_res,
            },
        )
        detections.append(detection)

    return detections
