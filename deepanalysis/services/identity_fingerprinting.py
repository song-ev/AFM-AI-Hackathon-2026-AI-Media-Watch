"""
Cross-platform identity fingerprinting (Stage 2, E3).

Extracts a voice embedding (Resemblyzer) and/or a face embedding
(face_recognition), matches against the stored fingerprint bank by cosine
similarity, and links the video's account to the matched (or a newly created)
identity. This is what powers "recidivist" detection across accounts/platforms.

Production policy (fail-loud): the embedding extractors raise
ModuleDependencyError if their library is unavailable — we never fabricate a
random embedding (that would create junk fingerprints and break matching). If
no real biometric signal can be extracted from a video, no fingerprint/link is
created for it.
"""
import logging
import os
import uuid

import numpy as np
from django.conf import settings
from django.utils import timezone
from scipy.spatial.distance import cosine

from core.exceptions import ModuleDependencyError
from deepanalysis.models import IdentityFingerprint, IdentityLink
from ingestion.models import Video

logger = logging.getLogger(__name__)


def extract_voice_embedding(video_path: str) -> np.ndarray | None:
    """Voice embedding via Resemblyzer, or None if no usable audio.

    Raises ModuleDependencyError if Resemblyzer is not installed.
    """
    try:
        from pathlib import Path

        from resemblyzer import VoiceEncoder, preprocess_wav
    except ImportError as exc:
        raise ModuleDependencyError(
            "identity",
            "resemblyzer is not installed; cannot extract voice fingerprint.",
        ) from exc

    try:
        encoder = VoiceEncoder()
        wav = preprocess_wav(Path(video_path))
        return encoder.embed_utterance(wav)
    except Exception as e:  # noqa: BLE001 — no audio / decode failure is not fatal
        logger.warning("Voice embedding unavailable for %s: %s", video_path, e)
        return None


def extract_face_embedding(video_path: str, sample_frames: int = 5) -> np.ndarray | None:
    """Face embedding via face_recognition on sampled frames, or None if no face.

    Raises ModuleDependencyError if face_recognition is not installed.
    """
    try:
        import cv2
        import face_recognition
    except ImportError as exc:
        raise ModuleDependencyError(
            "identity",
            "face_recognition is not installed; cannot extract face fingerprint.",
        ) from exc

    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if frame_count == 0:
            return None
        step = max(1, frame_count // sample_frames)

        best_embedding = None
        for i in range(0, frame_count, step):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ret, frame = cap.read()
            if not ret:
                break
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            face_locations = face_recognition.face_locations(rgb_frame)
            if face_locations:
                largest = max(
                    face_locations,
                    key=lambda loc: (loc[2] - loc[0]) * (loc[1] - loc[3]),
                )
                encodings = face_recognition.face_encodings(rgb_frame, [largest])
                if encodings:
                    best_embedding = encodings[0]
                    break
        cap.release()
        return best_embedding
    except Exception as e:  # noqa: BLE001
        logger.warning("Face embedding unavailable for %s: %s", video_path, e)
        return None


def _usable(embedding) -> bool:
    return embedding is not None and np.any(embedding)


def find_matching_identity(voice_embedding, face_embedding) -> IdentityFingerprint | None:
    """Find a stored fingerprint matching either embedding by cosine similarity."""
    threshold_voice = getattr(settings, "IDENTITY_VOICE_THRESHOLD", 0.75)
    threshold_face = getattr(settings, "IDENTITY_FACE_THRESHOLD", 0.6)

    embeddings_dir = os.path.join(settings.MEDIA_ROOT, "embeddings")
    os.makedirs(embeddings_dir, exist_ok=True)

    for fp in IdentityFingerprint.objects.all():
        v_path = os.path.join(embeddings_dir, f"{fp.embedding_hash}_voice.npy")
        f_path = os.path.join(embeddings_dir, f"{fp.embedding_hash}_face.npy")

        if os.path.exists(v_path) and _usable(voice_embedding):
            stored = np.load(v_path)
            if _usable(stored) and cosine(voice_embedding, stored) < (1 - threshold_voice):
                return fp

        if os.path.exists(f_path) and _usable(face_embedding):
            stored = np.load(f_path)
            if _usable(stored) and cosine(face_embedding, stored) < (1 - threshold_face):
                return fp

    return None


def link_video_identity(video: Video) -> IdentityLink | None:
    """Extract identity from the video and link its account to a fingerprint.

    Returns None (without creating anything) when there is no real biometric
    signal to fingerprint — so we never pollute the fingerprint bank with junk.
    """
    video_path = video.resolved_file_path
    if not video_path or not os.path.exists(video_path):
        return None

    v_emb = extract_voice_embedding(video_path)
    f_emb = extract_face_embedding(video_path)

    # No real biometric content extracted → nothing to fingerprint.
    if not _usable(v_emb) and not _usable(f_emb):
        logger.info("No usable voice/face embedding for video %s; skipping identity link.", video.id)
        return None

    match = find_matching_identity(v_emb, f_emb)

    if match is None:
        embeddings_dir = os.path.join(settings.MEDIA_ROOT, "embeddings")
        os.makedirs(embeddings_dir, exist_ok=True)
        emb_hash = str(uuid.uuid4())
        if _usable(v_emb):
            np.save(os.path.join(embeddings_dir, f"{emb_hash}_voice.npy"), v_emb)
        if _usable(f_emb):
            np.save(os.path.join(embeddings_dir, f"{emb_hash}_face.npy"), f_emb)

        fp_type = (
            IdentityFingerprint.FingerprintType.VOICE if _usable(v_emb)
            else IdentityFingerprint.FingerprintType.FACE
        )
        match = IdentityFingerprint.objects.create(
            embedding_hash=emb_hash,
            fingerprint_type=fp_type,
            confidence=0.9,
        )

    return IdentityLink.objects.create(
        identity_fingerprint=match,
        social_account=video.social_account,
        video=video,
        linked_at=timezone.now(),
    )
