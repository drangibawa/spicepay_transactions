from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .detect import ClipWindow
from .hooks import HookPack
from .utils import run


def _escape_drawtext(text: str) -> str:
    # ffmpeg drawtext escaping for special chars
    text = text.replace("\\", "\\\\")
    text = text.replace(":", "\\:")
    text = text.replace("'", "\\'")
    text = text.replace("%", "%%")
    return text


def _wrap_hook(hook: str, max_chars: int = 22) -> str:
    words = hook.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        trial = (" ".join(current + [word])).strip()
        if len(trial) <= max_chars:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines[:3])


def _find_font() -> str | None:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return path
    return None


def render_clip(
    src: Path,
    window: ClipWindow,
    out_path: Path,
    render_cfg: dict[str, Any],
    hook: HookPack | None = None,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    width = int(render_cfg["width"])
    height = int(render_cfg["height"])
    fps = int(render_cfg["fps"])
    crf = int(render_cfg["video_crf"])
    audio_br = str(render_cfg["audio_bitrate"])
    layout = str(render_cfg.get("layout", "blur_fill"))
    burn = bool(render_cfg.get("burn_hooks", True)) and hook is not None
    font_size = int(render_cfg.get("font_size", 64))
    top_margin = int(render_cfg.get("top_margin", 160))

    duration = max(0.1, window.end - window.start)

    if layout == "center":
        # Center-crop to 9:16
        vf = (
            f"scale=-2:{height},"
            f"crop={width}:{height},"
            f"fps={fps}"
        )
        fc = None
    else:
        # Blurred full-bleed background + centered gameplay
        # Works for landscape gameplay → vertical shorts.
        fc = (
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},boxblur=20:5,setsar=1[bg];"
            f"[0:v]scale={width}:-2:force_original_aspect_ratio=decrease,setsar=1[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,fps={fps}[base]"
        )
        vf = None

    draw = ""
    font = _find_font()
    if burn and hook is not None:
        wrapped = _wrap_hook(hook.hook)
        # drawtext does not love real newlines in -vf easily; stack lines
        lines = wrapped.split("\n")
        filters: list[str] = []
        for i, line in enumerate(lines):
            y = top_margin + i * int(font_size * 1.15)
            escaped = _escape_drawtext(line)
            fontfile = f"fontfile={font}:" if font else ""
            filters.append(
                f"drawtext={fontfile}text='{escaped}':"
                f"fontsize={font_size}:fontcolor=white:borderw=4:bordercolor=black@0.85:"
                f"x=(w-text_w)/2:y={y}"
            )
        draw = ",".join(filters)

    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{window.start:.3f}",
        "-i",
        str(src),
        "-t",
        f"{duration:.3f}",
    ]

    if fc:
        if draw:
            filter_complex = fc + f";[base]{draw}[vout]"
            cmd += ["-filter_complex", filter_complex, "-map", "[vout]"]
        else:
            cmd += ["-filter_complex", fc, "-map", "[base]"]
        cmd += ["-map", "0:a?"]
    else:
        full_vf = vf if not draw else f"{vf},{draw}"
        cmd += ["-vf", full_vf]

    cmd += [
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        audio_br,
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    run(cmd)


def safe_stem(name: str) -> str:
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "_", name).strip("._")
    return stem or "clip"