"""
Audio forensics (new analysis category — "проверка аудио").

Goes beyond Stage-1 transcription/keywords to inspect *how* something is said,
using real signal features computed from the waveform (numpy/scipy — no cloud):

* prosody / pressure  — loudness dynamics, speaking rate (zero-crossing rate),
  pause ratio. Scam pitches are typically loud, fast and low-pause ("успей,
  только сегодня, осталось 3 места").
* monotone / synthetic-voice indicator — TTS and cloned voices tend to be
  unusually steady in pitch and energy. We compute a naturalness score from
  pitch (autocorrelation) and energy variance and flag *possible* synthetic
  delivery. This is a heuristic indicator, NOT a deepfake verdict — a dedicated
  classifier is the production path (documented, fail-loud).
* language id        — taken from the Whisper segments produced upstream.

Honest by design: if the audio can't be decoded the module fails loud
(ModuleDependencyError) rather than inventing a clean result.
"""
from __future__ import annotations

import logging
import math
import os

import numpy as np
from django.conf import settings

from core.exceptions import ModuleDependencyError
from ingestion.models import Video
from screening.models import ScreeningSignal
from screening.services.audio_analysis import extract_audio_segment

logger = logging.getLogger(__name__)


def _load_waveform(video_path: str):
    """Return (samples float32 mono [-1,1], sample_rate). Fail loud on error."""
    base_dir = getattr(settings, "MEDIA_ROOT", "")
    temp_dir = os.path.join(str(base_dir), "audio_temp")
    out_path = os.path.join(temp_dir, f"forensic_{os.path.basename(video_path)}.wav")
    wav = extract_audio_segment(video_path, 0, 90, out_path)  # first 90s is plenty
    if not wav or not os.path.exists(wav):
        raise ModuleDependencyError(
            "audio_forensics", "Could not extract an audio track from the video."
        )
    try:
        from scipy.io import wavfile

        sr, data = wavfile.read(wav)
    except Exception as exc:  # noqa: BLE001
        raise ModuleDependencyError(
            "audio_forensics", f"Could not read extracted audio: {exc}"
        ) from exc
    finally:
        try:
            os.remove(wav)
        except OSError:
            pass

    samples = np.asarray(data, dtype=np.float32)
    if samples.ndim > 1:  # stereo -> mono
        samples = samples.mean(axis=1)
    peak = np.max(np.abs(samples)) or 1.0
    return samples / peak, int(sr)


def _frame_features(samples: np.ndarray, sr: int) -> dict:
    """Compute per-frame energy + ZCR and summarise prosody."""
    frame = max(1, int(sr * 0.025))      # 25 ms frames
    hop = max(1, int(sr * 0.010))        # 10 ms hop
    energies, zcrs = [], []
    for start in range(0, max(1, len(samples) - frame), hop):
        seg = samples[start:start + frame]
        if seg.size == 0:
            continue
        energies.append(float(np.sqrt(np.mean(seg ** 2))))
        zcrs.append(float(np.mean(np.abs(np.diff(np.sign(seg)))) / 2.0))
    energies = np.asarray(energies) if energies else np.zeros(1)
    zcrs = np.asarray(zcrs) if zcrs else np.zeros(1)

    speech_thresh = max(0.02, float(np.mean(energies)) * 0.5)
    voiced = energies > speech_thresh
    pause_ratio = float(1.0 - (np.mean(voiced) if voiced.size else 0.0))

    return {
        "energy_mean": float(np.mean(energies)),
        "energy_std": float(np.std(energies)),
        "energy_cv": float(np.std(energies) / (np.mean(energies) + 1e-6)),
        "zcr_mean": float(np.mean(zcrs)),
        "pause_ratio": round(pause_ratio, 3),
    }


def _pitch_stability(samples: np.ndarray, sr: int) -> float:
    """Rough pitch-variability proxy via autocorrelation over short windows.

    Returns a coefficient of variation of estimated pitch; LOW values mean an
    unusually steady pitch (monotone / possible TTS)."""
    win = int(sr * 0.04)
    if win < 64 or len(samples) < win * 4:
        return 1.0
    pitches = []
    for start in range(0, len(samples) - win, win):
        seg = samples[start:start + win]
        if np.sqrt(np.mean(seg ** 2)) < 0.02:
            continue
        seg = seg - np.mean(seg)
        corr = np.correlate(seg, seg, mode="full")[win - 1:]
        # Search plausible human pitch range 70–400 Hz.
        lo, hi = int(sr / 400), int(sr / 70)
        if hi >= len(corr) or lo >= hi:
            continue
        peak = lo + int(np.argmax(corr[lo:hi]))
        if peak > 0:
            pitches.append(sr / peak)
    if len(pitches) < 5:
        return 1.0
    pitches = np.asarray(pitches)
    return float(np.std(pitches) / (np.mean(pitches) + 1e-6))


def _languages(video: Video) -> list[str]:
    langs = set()
    sr = getattr(video, "screening_result", None)
    if sr:
        for s in sr.signals.all():
            if s.module == "quick_audio":
                for seg in (s.raw_output or {}).get("segments", []):
                    if seg.get("language"):
                        langs.add(seg["language"])
    dar = getattr(video, "deep_analysis_result", None)
    if dar:
        for t in dar.transcripts.all():
            if t.language:
                langs.add(t.language)
    return sorted(langs)


def analyze_audio_forensics(video: Video) -> ScreeningSignal:
    video_path = video.resolved_file_path
    if not video_path or not os.path.exists(video_path):
        raise ModuleDependencyError(
            "audio_forensics", "Video has no downloaded local file to analyse."
        )

    samples, sr = _load_waveform(video_path)
    if samples.size < sr:  # < 1s of audio
        raise ModuleDependencyError(
            "audio_forensics", "Audio track too short or silent to analyse."
        )

    feats = _frame_features(samples, sr)
    pitch_cv = _pitch_stability(samples, sr)

    # Pressure: loud + fast (high ZCR) + few pauses.
    pressure = (
        min(1.0, feats["energy_mean"] / 0.25) * 0.4
        + min(1.0, feats["zcr_mean"] / 0.15) * 0.3
        + min(1.0, (1.0 - feats["pause_ratio"]) / 0.85) * 0.3
    )
    # Monotone / synthetic indicator: steady pitch AND steady energy.
    monotone = max(0.0, 1.0 - pitch_cv / 0.18)            # low CV -> high
    steady_energy = max(0.0, 1.0 - feats["energy_cv"] / 0.9)
    synthetic_indicator = round(0.6 * monotone + 0.4 * steady_energy, 3)

    languages = _languages(video)

    # Trigger on a high-pressure delivery or a strong synthetic indicator.
    is_triggered = pressure >= 0.6 or synthetic_indicator >= 0.7
    confidence = round(float(max(pressure, synthetic_indicator)), 4)

    flags = []
    if pressure >= 0.6:
        flags.append("Высокое давление в подаче (громко/быстро/без пауз)")
    if synthetic_indicator >= 0.7:
        flags.append("Возможен синтезированный/клонированный голос (монотонность)")
    if len(languages) > 1:
        flags.append(f"Смешение языков: {', '.join(languages)}")

    return ScreeningSignal(
        module=ScreeningSignal.Module.AUDIO_FORENSICS,
        is_triggered=is_triggered,
        confidence=confidence,
        raw_output={
            "pressure_score": round(float(pressure), 3),
            "synthetic_voice_indicator": synthetic_indicator,
            "pitch_variation_cv": round(pitch_cv, 3),
            "pause_ratio": feats["pause_ratio"],
            "energy_mean": round(feats["energy_mean"], 4),
            "zcr_mean": round(feats["zcr_mean"], 4),
            "languages": languages,
            "flags": flags,
            "note": (
                "Индикатор синтетического голоса — эвристика по стабильности "
                "высоты тона и энергии, не окончательный вердикт о дипфейке."
            ),
        },
    )
