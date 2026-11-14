#!/usr/bin/env python3
"""Gameplay → viral Shorts clipping pipeline.

Usage:
  python clip.py /path/to/your_gameplay.mp4 --out out/
  python clip.py gameplay.mp4 --manual-ranges 40-65 120-145 --out out/
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.detect import build_windows, detect_audio_peaks, parse_manual_ranges
from pipeline.hooks import build_hook
from pipeline.render import render_clip, safe_stem
from pipeline.utils import (
    PipelineError,
    deep_merge,
    default_config,
    load_yaml,
    media_duration,
    require_ffmpeg,
    write_json,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Detect highlight peaks in gameplay and export vertical viral shorts."
    )
    p.add_argument("input", type=Path, help="Path to your gameplay video file")
    p.add_argument("--out", type=Path, default=Path("out"), help="Output directory")
    p.add_argument("--config", type=Path, help="Optional YAML config (see config.example.yaml)")
    p.add_argument("--max-clips", type=int, help="Override max clips to export")
    p.add_argument(
        "--manual-ranges",
        nargs="+",
        help="Skip auto-detect; clip these start-end second ranges (e.g. 42-68 120-150)",
    )
    p.add_argument(
        "--layout",
        choices=["blur_fill", "center"],
        help="Vertical layout: blur_fill (default) or center crop",
    )
    p.add_argument("--no-hooks", action="store_true", help="Disable burn-in hook text")
    p.add_argument(
        "--style",
        default=None,
        help="Hook style: cricket24 (default) or generic",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect windows and write manifest only (no ffmpeg renders)",
    )
    p.add_argument(
        "--label",
        default=None,
        help="Optional source label used in suggested titles",
    )
    return p.parse_args(argv)


def build_config(args: argparse.Namespace) -> dict[str, Any]:
    cfg = default_config()
    if args.config:
        cfg = deep_merge(cfg, load_yaml(args.config))
    if args.max_clips is not None:
        cfg["clip"]["max_clips"] = args.max_clips
    if args.layout:
        cfg["render"]["layout"] = args.layout
    if args.no_hooks:
        cfg["render"]["burn_hooks"] = False
    if args.style:
        cfg["hooks"]["style"] = args.style
    return cfg


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        require_ffmpeg()
        src = args.input.expanduser().resolve()
        if not src.exists():
            raise PipelineError(f"Input not found: {src}")

        cfg = build_config(args)
        out_dir = args.out.expanduser().resolve()
        work_dir = out_dir / "_work"
        clips_dir = out_dir / "shorts"
        out_dir.mkdir(parents=True, exist_ok=True)
        work_dir.mkdir(parents=True, exist_ok=True)
        clips_dir.mkdir(parents=True, exist_ok=True)

        duration = media_duration(src)
        if args.manual_ranges:
            windows = parse_manual_ranges(args.manual_ranges, duration)
            peaks = []
        else:
            peaks = detect_audio_peaks(src, work_dir, cfg["detect"])
            windows = build_windows(peaks, duration, cfg["clip"])

        if not windows:
            raise PipelineError(
                "No highlight windows found. Try lowering detect.z_threshold / "
                "min_rms_ratio, or pass --manual-ranges."
            )

        style = cfg["hooks"]["style"]
        extra = list(cfg["hooks"].get("extra") or [])
        label = args.label or src.stem

        manifest: dict[str, Any] = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": str(src),
            "duration": round(duration, 3),
            "config": cfg,
            "peaks": [p.to_dict() for p in peaks],
            "clips": [],
        }

        stem = safe_stem(src.stem)
        for window in windows:
            hook = build_hook(
                window,
                style=style,
                extra=extra,
                source_label=label,
            )
            out_name = f"{stem}_short_{window.index:02d}.mp4"
            out_path = clips_dir / out_name
            entry = {
                "file": str(out_path) if not args.dry_run else None,
                "filename": out_name,
                "window": window.to_dict(),
                "hook": hook.to_dict(),
            }
            if not args.dry_run:
                render_clip(src, window, out_path, cfg["render"], hook=hook)
                entry["file"] = str(out_path)
            manifest["clips"].append(entry)
            print(
                f"[{window.index}/{len(windows)}] "
                f"{window.start:.1f}-{window.end:.1f}s  "
                f"score={window.score:.2f}  hook={hook.hook!r}"
                + ("" if args.dry_run else f"  -> {out_path.name}")
            )

        manifest_path = out_dir / "manifest.json"
        write_json(manifest_path, manifest)

        # Handy posting sheet
        lines = [f"# Shorts posting sheet — {label}", ""]
        for entry in manifest["clips"]:
            h = entry["hook"]
            w = entry["window"]
            lines.append(f"## Clip {w['index']}: {entry['filename']}")
            lines.append(f"- Hook: {h['hook']}")
            lines.append(f"- Title: {h['title']}")
            lines.append(f"- Range: {w['start']:.1f}s → {w['end']:.1f}s")
            lines.append(f"- Caption:\n\n{h['caption']}")
            lines.append("")
        (out_dir / "posting_sheet.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

        print(f"\nWrote {len(manifest['clips'])} clip plan(s) → {manifest_path}")
        print(f"Posting sheet → {out_dir / 'posting_sheet.md'}")
        if not args.dry_run:
            print(f"Shorts folder → {clips_dir}")
        return 0
    except PipelineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())