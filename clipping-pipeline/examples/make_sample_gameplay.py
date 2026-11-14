#!/usr/bin/env python3
"""Synthesize a short pseudo-gameplay clip with loud 'highlight' bursts for pipeline demos/tests."""

from __future__ import annotations

import argparse
import math
import struct
import subprocess
import wave
from pathlib import Path


def write_wav(path: Path, duration: float = 45.0, rate: int = 16000) -> list[float]:
    """Create commentary-like bed + applause spikes at known times. Returns peak times."""
    peaks = [8.0, 18.5, 29.0, 38.0]
    n = int(duration * rate)
    frames: list[int] = []
    for i in range(n):
        t = i / rate
        # quiet bed + light noise
        bed = 0.04 * math.sin(2 * math.pi * 220 * t) + 0.02 * math.sin(2 * math.pi * 440 * t)
        spike = 0.0
        for p in peaks:
            # crowd roar envelope ~1.2s
            d = t - p
            if 0 <= d <= 1.2:
                env = math.sin(math.pi * d / 1.2)
                spike += env * 0.55 * math.sin(2 * math.pi * 180 * t)
                spike += env * 0.25 * math.sin(2 * math.pi * 90 * t)
        sample = max(-1.0, min(1.0, bed + spike))
        frames.append(int(sample * 32767))

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(struct.pack("<" + "h" * len(frames), *frames))
    return peaks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("examples/sample_gameplay.mp4"))
    ap.add_argument("--duration", type=float, default=45.0)
    args = ap.parse_args()

    work = args.out.parent / "_sample_work"
    work.mkdir(parents=True, exist_ok=True)
    wav = work / "audio.wav"
    peaks = write_wav(wav, duration=args.duration)

    # Simple moving color bars as stand-in for gameplay video
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"smptebars=size=1280x720:rate=30,format=yuv420p",
        "-i",
        str(wav),
        "-t",
        str(args.duration),
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "28",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-shortest",
        str(args.out),
    ]
    subprocess.run(cmd, check=True)
    print(f"Wrote {args.out}")
    print("Synthetic highlight peaks at:", ", ".join(f"{p:.1f}s" for p in peaks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())