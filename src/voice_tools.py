from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Literal, Optional, Callable


logger = logging.getLogger(__name__)


class VoiceDepsMissing(RuntimeError):
    pass


@dataclass(frozen=True)
class VoiceWav:
    wav: "object"  # numpy.ndarray, but keep import optional at import-time
    sr: int
    used_trim_silence: bool


def _require_numpy():
    try:
        import numpy as np  # type: ignore

        return np
    except Exception as e:  # pragma: no cover
        raise VoiceDepsMissing(
            "Voice tools require numpy. Install requirements and restart the server."
        ) from e


def _require_resemblyzer():
    try:
        from resemblyzer import VoiceEncoder, preprocess_wav  # type: ignore

        return VoiceEncoder, preprocess_wav
    except Exception as e:  # pragma: no cover
        raise VoiceDepsMissing(
            "Voice tools require 'resemblyzer' (and torch). Install requirements and restart the server."
        ) from e


@lru_cache(maxsize=1)
def get_encoder():
    VoiceEncoder, _ = _require_resemblyzer()
    return VoiceEncoder()


def load_master_wav(master_wav_path: Path) -> VoiceWav:
    """Load the dojo master WAV as a 16kHz mono float array for VoiceEncoder."""
    _, preprocess_wav = _require_resemblyzer()

    used_trim_silence = False
    try:
        wav = preprocess_wav(str(master_wav_path), trim_silence=False)
    except TypeError:
        # Older resemblyzer versions don't accept trim_silence kwarg.
        wav = preprocess_wav(str(master_wav_path))
        used_trim_silence = True

    # preprocess_wav returns 16kHz by default
    return VoiceWav(wav=wav, sr=16000, used_trim_silence=used_trim_silence)


def _dot(a, b) -> float:
    # Embeddings are typically L2-normalized; dot ~= cosine similarity.
    return float(a @ b)


def voice_filter_segments(
    *,
    wav: VoiceWav,
    segments_ms: list[tuple[float, float]],
    ref_ms: tuple[float, float],
    threshold: float,
    mode: Literal["keep", "remove"],
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> tuple[list[tuple[float, float]], int]:
    encoder = get_encoder()

    ref_start_ms, ref_end_ms = ref_ms
    if ref_end_ms - ref_start_ms < 500:
        raise ValueError("Reference selection must be at least 0.5s.")

    sr = wav.sr
    ref_start_idx = int((ref_start_ms / 1000.0) * sr)
    ref_end_idx = int((ref_end_ms / 1000.0) * sr)
    ref_start_idx = max(0, ref_start_idx)
    ref_end_idx = min(len(wav.wav), ref_end_idx)
    if ref_end_idx <= ref_start_idx:
        raise ValueError("Reference selection is out of bounds.")

    ref_embed = encoder.embed_utterance(wav.wav[ref_start_idx:ref_end_idx])

    kept: list[tuple[float, float]] = []
    kept_count = 0
    total = len(segments_ms)

    for i, (start_ms, end_ms) in enumerate(segments_ms):
        if progress_callback:
            progress_callback(i + 1, total)
        
        start_idx = int((start_ms / 1000.0) * sr)
        end_idx = int((end_ms / 1000.0) * sr)
        start_idx = max(0, start_idx)
        end_idx = min(len(wav.wav), end_idx)
        if end_idx <= start_idx:
            continue

        emb = encoder.embed_utterance(wav.wav[start_idx:end_idx])
        sim = _dot(ref_embed, emb)
        match = sim > float(threshold)

        keep = False
        if mode == "keep" and match:
            keep = True
        if mode == "remove" and not match:
            keep = True

        if keep:
            kept.append((float(start_ms), float(end_ms)))
            kept_count += 1

    return kept, kept_count


def voice_filter_segments_by_ref_audio(
    *,
    wav: VoiceWav,
    segments_ms: list[tuple[float, float]],
    ref_audio_path: str,
    threshold: float,
    mode: Literal["keep", "remove"],
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> tuple[list[tuple[float, float]], int, bool]:
    """Filter segments by similarity to an external reference audio file.

    This matches the Python Tkinter slicer's behavior where the reference voice can come
    from a separate audio file, not only a selection within the master audio.

    Returns: (kept_segments, kept_count, used_trim_silence)
    """

    encoder = get_encoder()
    _, preprocess_wav = _require_resemblyzer()

    used_trim_silence = False
    try:
        ref_wav = preprocess_wav(ref_audio_path, trim_silence=False)
    except TypeError:
        ref_wav = preprocess_wav(ref_audio_path)
        used_trim_silence = True

    # resemblyzer uses 16kHz internally; preprocess_wav should yield that.
    if ref_wav is None or len(ref_wav) < int(0.5 * 16000):
        raise ValueError("Reference audio must be at least 0.5s.")

    ref_embed = encoder.embed_utterance(ref_wav)

    kept: list[tuple[float, float]] = []
    kept_count = 0
    total = len(segments_ms)

    sr = wav.sr
    for i, (start_ms, end_ms) in enumerate(segments_ms):
        if progress_callback:
            progress_callback(i + 1, total)

        start_idx = int((start_ms / 1000.0) * sr)
        end_idx = int((end_ms / 1000.0) * sr)
        start_idx = max(0, start_idx)
        end_idx = min(len(wav.wav), end_idx)
        if end_idx <= start_idx:
            continue

        emb = encoder.embed_utterance(wav.wav[start_idx:end_idx])
        sim = _dot(ref_embed, emb)
        match = sim > float(threshold)

        keep = False
        if mode == "keep" and match:
            keep = True
        if mode == "remove" and not match:
            keep = True

        if keep:
            kept.append((float(start_ms), float(end_ms)))
            kept_count += 1

    return kept, kept_count, used_trim_silence


def voice_split_by_changes(
    *,
    wav: VoiceWav,
    base_segments_ms: list[tuple[float, float]],
    win_s: float,
    hop_s: float,
    thresh: float,
    min_seg_s: float,
) -> list[tuple[float, float]]:
    if hop_s > win_s:
        raise ValueError("hop_s must be <= win_s")

    encoder = get_encoder()
    sr = wav.sr
    win_n = int(float(win_s) * sr)
    hop_n = int(float(hop_s) * sr)
    min_len_ms = float(min_seg_s) * 1000.0

    if win_n <= 0 or hop_n <= 0:
        raise ValueError("win_s and hop_s must be > 0")

    out: list[tuple[float, float]] = []
    for seg_start_ms, seg_end_ms in base_segments_ms:
        start_idx = int((seg_start_ms / 1000.0) * sr)
        end_idx = int((seg_end_ms / 1000.0) * sr)
        start_idx = max(0, start_idx)
        end_idx = min(len(wav.wav), end_idx)
        if end_idx <= start_idx:
            continue

        seg_wav = wav.wav[start_idx:end_idx]
        if len(seg_wav) < win_n:
            out.append((float(seg_start_ms), float(seg_end_ms)))
            continue

        embeddings = []
        centers_ms = []
        pos = 0
        while pos + win_n <= len(seg_wav):
            window = seg_wav[pos : pos + win_n]
            emb = encoder.embed_utterance(window)
            embeddings.append(emb)
            center_ms = seg_start_ms + (((pos + (win_n / 2.0)) / sr) * 1000.0)
            centers_ms.append(center_ms)
            pos += hop_n

        if len(embeddings) < 2:
            out.append((float(seg_start_ms), float(seg_end_ms)))
            continue

        boundaries = []
        last_boundary_ms = float(seg_start_ms)
        for j in range(1, len(embeddings)):
            sim = _dot(embeddings[j - 1], embeddings[j])
            t_ms = float(centers_ms[j])
            if sim < float(thresh) and (t_ms - last_boundary_ms) >= min_len_ms:
                boundaries.append(t_ms)
                last_boundary_ms = t_ms

        points = [float(seg_start_ms)] + boundaries + [float(seg_end_ms)]
        segs = [(a, b) for a, b in zip(points, points[1:]) if b > a]

        merged: list[list[float]] = []
        for a, b in segs:
            if not merged:
                merged.append([a, b])
                continue
            if (b - a) < min_len_ms:
                merged[-1][1] = b
            else:
                merged.append([a, b])

        out.extend([(float(a), float(b)) for a, b in merged if b > a])

    return out


def voice_label_segments(
    *,
    wav: VoiceWav,
    segments_ms: list[tuple[float, float]],
    k: int,
) -> list[int]:
    np = _require_numpy()
    encoder = get_encoder()

    if k < 2:
        raise ValueError("k must be >= 2")

    sr = wav.sr
    min_embed_ms = 0.6 * 1000.0

    embeds = []
    embed_seg_indices: list[int] = []
    voice_ids: list[int | None] = [None] * len(segments_ms)

    for i, (start_ms, end_ms) in enumerate(segments_ms):
        if (float(end_ms) - float(start_ms)) < min_embed_ms:
            continue
        start_idx = int((float(start_ms) / 1000.0) * sr)
        end_idx = int((float(end_ms) / 1000.0) * sr)
        start_idx = max(0, start_idx)
        end_idx = min(len(wav.wav), end_idx)
        if end_idx <= start_idx:
            continue
        emb = encoder.embed_utterance(wav.wav[start_idx:end_idx])
        embeds.append(emb)
        embed_seg_indices.append(i)

    if not embeds:
        raise ValueError("All segments are too short for reliable voice labeling (< 0.6s).")

    X = np.array(embeds, dtype=np.float32)
    norms = np.linalg.norm(X, axis=1, keepdims=True) + 1e-8
    X = X / norms

    k_eff = int(min(int(k), X.shape[0]))
    rng = np.random.default_rng(0)
    init_idx = rng.choice(X.shape[0], size=k_eff, replace=False)
    C = X[init_idx].copy()

    for _ in range(20):
        sims = X @ C.T
        labels = np.argmax(sims, axis=1)

        new_C = np.zeros_like(C)
        for ci in range(k_eff):
            mask = labels == ci
            if not np.any(mask):
                new_C[ci] = X[rng.integers(0, X.shape[0])]
            else:
                v = np.mean(X[mask], axis=0)
                v = v / (np.linalg.norm(v) + 1e-8)
                new_C[ci] = v
        if np.allclose(C, new_C, atol=1e-4):
            C = new_C
            break
        C = new_C

    for seg_i, lab in zip(embed_seg_indices, labels):
        voice_ids[seg_i] = int(lab)

    last = None
    for i in range(len(voice_ids)):
        if voice_ids[i] is None:
            voice_ids[i] = last
        else:
            last = voice_ids[i]

    first = next((v for v in voice_ids if v is not None), 0)
    voice_ids = [first if v is None else v for v in voice_ids]

    first_pos: dict[int, int] = {}
    for i, v in enumerate(voice_ids):
        first_pos.setdefault(int(v), i)
    order = [v for v, _ in sorted(first_pos.items(), key=lambda t: t[1])]
    remap = {v: idx + 1 for idx, v in enumerate(order)}

    return [int(remap.get(int(v), 1)) for v in voice_ids]
