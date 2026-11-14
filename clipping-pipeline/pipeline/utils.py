from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


class PipelineError(RuntimeError):
    pass


def require_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise PipelineError(f"Required tool not found on PATH: {tool}")


def run(cmd: list[str], *, capture: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        cmd,
        check=False,
        text=True,
        capture_output=capture,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise PipelineError(f"Command failed ({result.returncode}): {' '.join(cmd)}\n{err}")
    return result


def probe(path: Path) -> dict[str, Any]:
    result = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
    )
    return json.loads(result.stdout)


def media_duration(path: Path) -> float:
    info = probe(path)
    fmt = info.get("format") or {}
    if "duration" in fmt:
        return float(fmt["duration"])
    for stream in info.get("streams") or []:
        if stream.get("duration"):
            return float(stream["duration"])
    raise PipelineError(f"Could not determine duration for {path}")


def has_audio(path: Path) -> bool:
    info = probe(path)
    return any(s.get("codec_type") == "audio" for s in info.get("streams") or [])


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def load_yaml(path: Path) -> dict[str, Any]:
    import yaml

    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise PipelineError(f"Config must be a mapping: {path}")
    return data


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def default_config() -> dict[str, Any]:
    return {
        "clip": {
            "min_duration": 12.0,
            "max_duration": 35.0,
            "pre_roll": 3.5,
            "post_roll": 8.0,
            "max_clips": 6,
            "merge_gap": 6.0,
        },
        "detect": {
            "hop_seconds": 0.25,
            "z_threshold": 1.6,
            "min_rms_ratio": 1.8,
            "ignore_head": 5.0,
            "ignore_tail": 5.0,
        },
        "render": {
            "width": 1080,
            "height": 1920,
            "layout": "blur_fill",
            "fps": 30,
            "video_crf": 20,
            "audio_bitrate": "160k",
            "burn_hooks": True,
            "font_size": 64,
            "top_margin": 160,
            "bottom_margin": 220,
        },
        "hooks": {
            "style": "cricket24",
            "extra": [],
        },
    }