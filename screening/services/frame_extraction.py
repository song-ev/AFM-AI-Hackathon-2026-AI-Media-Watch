import os
import cv2
import logging
from scenedetect import detect, ContentDetector
from django.conf import settings
from ingestion.models import Video
from screening.models import ExtractedFrame

logger = logging.getLogger(__name__)

def detect_scenes(video_path: str) -> list[float]:
    """
    Returns a list of timestamps (seconds) where scene changes occur.
    Uses PySceneDetect with fallback to fixed interval.
    """
    timestamps = []
    try:
        # The threshold is parameterized via settings
        threshold = getattr(settings, 'SCENEDETECT_THRESHOLD', 27.0)
        scene_list = detect(video_path, ContentDetector(threshold=threshold))
        
        for scene in scene_list:
            # scene[0] is FrameTimecode object
            timestamps.append(scene[0].get_seconds())
            
        logger.info(f"PySceneDetect found {len(timestamps)} scenes in {video_path}")
        
        if not timestamps:
            raise ValueError("No scenes detected")
            
    except Exception as e:
        logger.warning(f"PySceneDetect failed or found no scenes for {video_path} ({e}). Falling back to fixed interval.")
        # Fallback: 1 frame every 3 seconds
        try:
            cap = cv2.VideoCapture(video_path)
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if fps > 0:
                duration = total_frames / fps
                # Every 3 seconds
                for i in range(0, int(duration), 3):
                    timestamps.append(float(i))
            cap.release()
        except Exception as e2:
            logger.error(f"Fallback extraction also failed: {e2}")
            
    return timestamps

def extract_frames(video_path: str, timestamps: list[float], output_dir: str) -> list[dict]:
    """
    Extracts frames at the given timestamps using OpenCV.
    Returns list of dicts: {"timestamp_sec": float, "file_path": str}
    Limits to 8-15 evenly distributed frames.
    """
    if not timestamps:
        return []
        
    # Limit logic: Architecture specifies 8-15 frames. If we have > 15, we sample uniformly.
    MAX_FRAMES = 15
    if len(timestamps) > MAX_FRAMES:
        # Select MAX_FRAMES evenly spaced timestamps
        step = len(timestamps) / MAX_FRAMES
        sampled = [timestamps[int(i * step)] for i in range(MAX_FRAMES)]
        timestamps = sampled
        
    os.makedirs(output_dir, exist_ok=True)
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error(f"Could not open video {video_path} for frame extraction")
        return []
        
    extracted = []
    fps = cap.get(cv2.CAP_PROP_FPS)
    
    for idx, ts in enumerate(timestamps):
        frame_idx = int(ts * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        
        if ret:
            # Save frame
            base_name = os.path.basename(video_path)
            file_name = f"{base_name}_frame_{idx}_{ts:.2f}s.jpg"
            file_path = os.path.join(output_dir, file_name)
            
            cv2.imwrite(file_path, frame)
            extracted.append({
                "timestamp_sec": ts,
                "file_path": file_path
            })
        else:
            logger.warning(f"Failed to read frame at {ts}s for {video_path}")
            
    cap.release()
    return extracted

def process_frame_extraction(video: Video) -> list[ExtractedFrame]:
    """
    Orchestrator for frame extraction.
    Detects scenes, extracts frames, saves to DB.
    """
    video_path = video.resolved_file_path
    if not video_path or not os.path.exists(video_path):
        logger.error(f"Video {video.id} has no local file path or file does not exist")
        return []

    # fallback to a temp directory if MEDIA_ROOT is not set or not usable
    base_dir = getattr(settings, 'MEDIA_ROOT', os.path.join(settings.BASE_DIR, 'media'))
    output_dir = os.path.join(base_dir, 'extracted_frames', str(video.id))

    timestamps = detect_scenes(video_path)
    extracted_data = extract_frames(video_path, timestamps, output_dir)
    
    saved_frames = []
    for data in extracted_data:
        frame = ExtractedFrame.objects.create(
            video=video,
            timestamp_sec=data["timestamp_sec"],
            file_path=data["file_path"]
        )
        saved_frames.append(frame)
        
    return saved_frames
