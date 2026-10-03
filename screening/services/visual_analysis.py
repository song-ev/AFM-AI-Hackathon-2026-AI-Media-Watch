"""
Stage-1 visual analysis: OCR (Tesseract) + object/logo detection (YOLO).

Production policy (fail-loud): if a required engine is unavailable, the module
raises ModuleDependencyError rather than returning a fabricated confidence. The
caller records the failure on the ScreeningSignal and contributes nothing to the
risk score.

Logo detection is meaningful only when YOLO_MODEL_PATH points at a model
fine-tuned on gambling/casino logos and YOLO_LOGO_CLASSES lists its positive
class names. With no classes configured, detection runs but never flags on
arbitrary (COCO) objects — OCR keyword matching still applies.
"""
import logging
import os

from django.conf import settings

from core.exceptions import ModuleDependencyError
from ingestion.models import Video
from screening.models import FrameAnalysisResult, ScreeningSignal
from screening.services.frame_extraction import process_frame_extraction
from screening.services.keywords import match_keywords

logger = logging.getLogger(__name__)

# Cache the loaded YOLO model across calls within a worker process.
_YOLO_MODEL = None
# Cache the resolved OCR language string per worker process.
_OCR_LANGS = None


def _resolve_ocr_langs(pytesseract, config: str = "") -> str:
    """Pick the best available Tesseract language string.

    Prefers Russian+English+Kazakh (casino content is largely Russian/Kazakh),
    but falls back to whatever is installed so OCR still runs with only `eng`.
    The `rus`/`kaz` traineddata can be dropped into the (custom) tessdata dir
    with no code change — this picks them up automatically.
    """
    global _OCR_LANGS
    if _OCR_LANGS is not None:
        return _OCR_LANGS
    try:
        available = set(pytesseract.get_languages(config=config))
    except Exception:  # noqa: BLE001 - older pytesseract / odd setups
        available = set()
    preferred = [l for l in ("rus", "eng", "kaz") if l in available]
    _OCR_LANGS = "+".join(preferred) if preferred else "eng"
    return _OCR_LANGS


def get_yolo_model():
    """Load (and cache) the configured YOLO model, or fail loudly."""
    global _YOLO_MODEL
    if _YOLO_MODEL is not None:
        return _YOLO_MODEL
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise ModuleDependencyError(
            "frame_analysis",
            "ultralytics (YOLO) is not installed. Install it and set "
            "YOLO_MODEL_PATH to a logo-detection model.",
        ) from exc

    model_path = getattr(settings, "YOLO_MODEL_PATH", "yolov8n.pt")
    try:
        _YOLO_MODEL = YOLO(model_path)
    except Exception as exc:  # noqa: BLE001 — surface as a dependency error
        raise ModuleDependencyError(
            "frame_analysis",
            f"Could not load YOLO model at {model_path!r}: {exc}",
        ) from exc
    return _YOLO_MODEL


def run_ocr(frame_path: str) -> dict:
    """Run Tesseract OCR on a frame. Raises ModuleDependencyError if missing."""
    try:
        import cv2
        import pytesseract
    except ImportError as exc:
        raise ModuleDependencyError(
            "frame_analysis",
            "pytesseract/opencv not installed.",
        ) from exc

    tesseract_cmd = getattr(settings, "TESSERACT_CMD", "tesseract")
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    img = cv2.imread(frame_path)
    if img is None:
        return {"raw_text": "", "words": []}

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    adjusted = cv2.convertScaleAbs(gray, alpha=1.5, beta=0)
    _, thresh = cv2.threshold(
        adjusted, 150, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU
    )

    min_conf = getattr(settings, "OCR_MIN_WORD_CONFIDENCE", 40.0)
    # A custom tessdata dir (extra language packs). Pass it via TESSDATA_PREFIX
    # (robust to spaces, unlike pytesseract's space-split config string).
    tessdata_dir = getattr(settings, "TESSDATA_DIR", "")
    if tessdata_dir:
        os.environ["TESSDATA_PREFIX"] = tessdata_dir
    ocr_config = ""
    langs = _resolve_ocr_langs(pytesseract, ocr_config)
    try:
        raw_text = pytesseract.image_to_string(thresh, lang=langs, config=ocr_config)
        data = pytesseract.image_to_data(
            thresh, lang=langs, config=ocr_config, output_type=pytesseract.Output.DICT
        )
    except pytesseract.TesseractNotFoundError as exc:
        raise ModuleDependencyError(
            "frame_analysis",
            f"Tesseract binary not found at {tesseract_cmd!r}. Install it or "
            "set TESSERACT_CMD.",
        ) from exc

    words = []
    for i in range(len(data["text"])):
        conf = float(data["conf"][i])
        token = data["text"][i].strip()
        if conf >= min_conf and token:
            words.append({
                "text": token,
                "confidence": conf,
                "bbox": [data["left"][i], data["top"][i],
                         data["width"][i], data["height"][i]],
            })
    return {"raw_text": raw_text, "words": words}


def run_logo_detection(frame_path: str) -> list[dict]:
    """Run YOLO and return only configured logo-class detections above threshold."""
    model = get_yolo_model()
    conf_threshold = getattr(settings, "YOLO_CONFIDENCE_THRESHOLD", 0.5)
    iou_threshold = getattr(settings, "YOLO_IOU_THRESHOLD", 0.5)
    logo_classes = {c.lower() for c in getattr(settings, "YOLO_LOGO_CLASSES", [])}

    results = model.predict(
        source=frame_path, iou=iou_threshold, conf=conf_threshold, verbose=False
    )

    detected = []
    for result in results:
        for box in result.boxes:
            cls_name = model.names[int(box.cls[0])]
            conf = float(box.conf[0])
            # Only configured gambling-logo classes count as a signal.
            if logo_classes and cls_name.lower() not in logo_classes:
                continue
            if conf < conf_threshold:
                continue
            detected.append({
                "class": cls_name,
                "confidence": conf,
                "bbox": box.xywh[0].tolist(),
            })
    return detected


def analyze_frames(video: Video) -> ScreeningSignal:
    """Extract frames, run OCR + YOLO, aggregate into a ScreeningSignal.

    Confidence is the real maximum signal strength observed: OCR keyword match
    score (0-1) or YOLO detection confidence. Never a hardcoded constant.
    """
    frames = video.extracted_frames.all()
    if not frames.exists():
        frames = process_frame_extraction(video)

    if not frames:
        raise ModuleDependencyError(
            "frame_analysis",
            "No frames could be extracted from the video.",
        )

    signal = ScreeningSignal(
        module=ScreeningSignal.Module.FRAME_ANALYSIS,
        is_triggered=False,
        confidence=0.0,
        raw_output={"frames": []},
    )

    any_suspicious = False
    max_confidence = 0.0
    logo_classes_configured = bool(getattr(settings, "YOLO_LOGO_CLASSES", []))

    for frame in frames:
        ocr_result = run_ocr(frame.file_path)
        matched_keywords = match_keywords(ocr_result["raw_text"])
        detected_objects = run_logo_detection(frame.file_path) if logo_classes_configured else []

        # Real confidence: best keyword match (score is 0-100) / best logo conf.
        kw_conf = max((m.get("score", 0) / 100.0 for m in matched_keywords), default=0.0)
        logo_conf = max((d["confidence"] for d in detected_objects), default=0.0)
        frame_conf = max(kw_conf, logo_conf)

        is_suspicious = bool(matched_keywords or detected_objects)
        if is_suspicious:
            any_suspicious = True
            max_confidence = max(max_confidence, frame_conf)

        FrameAnalysisResult.objects.create(
            extracted_frame=frame,
            ocr_text=ocr_result["raw_text"],
            ocr_matched_keywords=matched_keywords,
            detected_objects=detected_objects,
            is_suspicious=is_suspicious,
        )

        signal.raw_output["frames"].append({
            "timestamp_sec": frame.timestamp_sec,
            "is_suspicious": is_suspicious,
            "matched_keywords": matched_keywords,
            "detected_objects": len(detected_objects),
            "confidence": round(frame_conf, 4),
        })

    signal.is_triggered = any_suspicious
    signal.confidence = round(max_confidence, 4)
    return signal
