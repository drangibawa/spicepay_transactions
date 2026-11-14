from __future__ import annotations

import struct
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .utils import PipelineError, has_audio, media_duration, run


@dataclass
class Peak:
    time: float
    score: float
    rms: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ClipWindow:
    index: int
    start: float
    end: float
    peak_time: float
    score: float
    reason: str

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["duration"] = round(self.duration, 3)
        return data


def _extract_mono_wav(src: Path, wav_path: Path, sample_rate: int = 16000) -> None:
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-sample_fmt",
            "s16",
            str(wav_path),
        ]
    )


def _read_wav_rms(wav_path: Path, hop_seconds: float) -> tuple[np.ndarray, np.ndarray, int]:
    with wave.open(str(wav_path), "rb") as wf:
        channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        rate = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    if sample_width != 2:
        raise PipelineError(f"Expected 16-bit PCM wav, got sample_width={sample_width}")
    if channels != 1:
        raise PipelineError(f"Expected mono wav, got channels={channels}")

    samples = np.array(struct.unpack("<" + "h" * (len(raw) // 2), raw), dtype=np.float64)
    samples /= 32768.0

    hop = max(1, int(rate * hop_seconds))
    if samples.size < hop:
        raise PipelineError("Audio is too short to analyze")

    n_windows = samples.size // hop
    trimmed = samples[: n_windows * hop].reshape(n_windows, hop)
    rms = np.sqrt(np.mean(trimmed * trimmed, axis=1))
    times = (np.arange(n_windows) + 0.5) * hop_seconds
    return times, rms, rate


def detect_audio_peaks(src: Path, work_dir: Path, detect_cfg: dict[str, Any]) -> list[Peak]:
    if not has_audio(src):
        raise PipelineError(
            "Input has no audio track. Viral highlight detection needs crowd/hit audio; "
            "add audio or pass --manual-ranges."
        )

    hop = float(detect_cfg["hop_seconds"])
    wav_path = work_dir / "analysis.wav"
    _extract_mono_wav(src, wav_path)
    times, rms, _rate = _read_wav_rms(wav_path, hop)

    duration = media_duration(src)
    head = float(detect_cfg["ignore_head"])
    tail = float(detect_cfg["ignore_tail"])
    mask = (times >= head) & (times <= max(head, duration - tail))
    if not np.any(mask):
        raise PipelineError("Nothing left to analyze after ignore_head/ignore_tail")

    usable = rms[mask]
    mean = float(np.mean(usable))
    std = float(np.std(usable)) + 1e-9
    z = (rms - mean) / std
    ratio = rms / (mean + 1e-9)

    z_thr = float(detect_cfg["z_threshold"])
    ratio_thr = float(detect_cfg["min_rms_ratio"])
    candidates: list[Peak] = []
    for t, r, z_val, rat in zip(times, rms, z, ratio, strict=True):
        if t < head or t > duration - tail:
            continue
        if z_val >= z_thr or rat >= ratio_thr:
            score = float(max(z_val, 0.0) + max(rat - 1.0, 0.0))
            candidates.append(Peak(time=float(t), score=score, rms=float(r)))

    # Keep local maxima only (non-maximum suppression)
    if not candidates:
        # Fallback: top absolute loudness windows
        order = np.argsort(rms)[::-1]
        for idx in order[:12]:
            t = float(times[idx])
            if t < head or t > duration - tail:
                continue
            candidates.append(Peak(time=t, score=float(rms[idx]), rms=float(rms[idx])))
            if len(candidates) >= 8:
                break

    candidates.sort(key=lambda p: p.time)
    suppressed: list[Peak] = []
    for peak in candidates:
        if suppressed and abs(peak.time - suppressed[-1].time) < hop * 3:
            if peak.score > suppressed[-1].score:
                suppressed[-1] = peak
            continue
        suppressed.append(peak)

    suppressed.sort(key=lambda p: p.score, reverse=True)
    return suppressed


def build_windows(
    peaks: list[Peak],
    duration: float,
    clip_cfg: dict[str, Any],
) -> list[ClipWindow]:
    pre = float(clip_cfg["pre_roll"])
    post = float(clip_cfg["post_roll"])
    min_dur = float(clip_cfg["min_duration"])
    max_dur = float(clip_cfg["max_duration"])
    merge_gap = float(clip_cfg["merge_gap"])
    max_clips = int(clip_cfg["max_clips"])

    ranked = sorted(peaks, key=lambda p: p.score, reverse=True)
    selected: list[Peak] = []
    for peak in ranked:
        if any(abs(peak.time - s.time) < merge_gap for s in selected):
            continue
        selected.append(peak)
        if len(selected) >= max_clips:
            break

    selected.sort(key=lambda p: p.time)
    windows: list[ClipWindow] = []
    for i, peak in enumerate(selected, start=1):
        start = max(0.0, peak.time - pre)
        end = min(duration, peak.time + post)
        # Pad to min duration if possible
        if end - start < min_dur:
            deficit = min_dur - (end - start)
            start = max(0.0, start - deficit / 2)
            end = min(duration, start + min_dur)
        # Clamp to max duration around the peak
        if end - start > max_dur:
            start = max(0.0, peak.time - max_dur * 0.35)
            end = min(duration, start + max_dur)
        windows.append(
            ClipWindow(
                index=i,
                start=round(start, 3),
                end=round(end, 3),
                peak_time=round(peak.time, 3),
                score=round(peak.score, 3),
                reason="audio_energy_peak",
            )
        )
    return windows


def parse_manual_ranges(ranges: list[str], duration: float) -> list[ClipWindow]:
    windows: list[ClipWindow] = []
    for i, item in enumerate(ranges, start=1):
        if "-" not in item:
            raise PipelineError(f"Invalid range '{item}'. Use start-end seconds, e.g. 42-68")
        a, b = item.split("-", 1)
        start = max(0.0, float(a))
        end = min(duration, float(b))
        if end <= start:
            raise PipelineError(f"Invalid range '{item}': end must be > start")
        windows.append(
            ClipWindow(
                index=i,
                start=round(start, 3),
                end=round(end, 3),
                peak_time=round((start + end) / 2, 3),
                score=1.0,
                reason="manual",
            )
        )
    return windows