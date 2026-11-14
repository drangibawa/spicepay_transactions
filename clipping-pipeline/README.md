# Gameplay → Viral Shorts Clipping Pipeline

Turn **your own** long gameplay recordings into vertical 9:16 Shorts/Reels/TikTok clips.

Optimized defaults for **Cricket 24 / IPL-style** powerplay footage (crowd roar + boundary spikes), but works on any gameplay with an audio track.

## What it does

1. Scans audio for highlight peaks (wickets, sixes, crowd bursts)
2. Builds 12–35s windows around the best peaks
3. Renders vertical shorts (`1080×1920`) with blurred background fill
4. Burns a hook line on-screen
5. Writes `manifest.json` + `posting_sheet.md` (titles, captions, hashtags)

## Requirements

- Python 3.10+
- `ffmpeg` + `ffprobe` on PATH
- Your gameplay file locally (MP4/MOV/MKV)

```bash
cd clipping-pipeline
pip install -r requirements.txt
```

## Quick start

```bash
# Auto-detect highlights and export shorts
python clip.py /path/to/your_gameplay.mp4 --out out/ --label "CSK vs RCB Powerplay"

# Manual ranges if you already know the timestamps
python clip.py /path/to/your_gameplay.mp4 --manual-ranges 42-68 185-210 340-365 --out out/

# Detect only (no renders)
python clip.py /path/to/your_gameplay.mp4 --dry-run --out out/
```

Outputs:

```
out/
  shorts/                 # vertical MP4s ready to upload
  manifest.json           # peaks, windows, hooks
  posting_sheet.md        # copy-paste titles/captions
  _work/analysis.wav      # intermediate audio used for detection
```

## Config

Copy `config.example.yaml` → `config.yaml` and pass `--config config.yaml`.

Useful knobs:

| Key | Effect |
|---|---|
| `detect.z_threshold` | Lower (e.g. `1.2`) = more sensitive peaks |
| `detect.min_rms_ratio` | Lower = catch quieter spikes |
| `clip.max_clips` | How many shorts to export |
| `clip.pre_roll` / `post_roll` | Context before/after the peak |
| `render.layout` | `blur_fill` (default) or `center` |
| `hooks.style` | `cricket24` or `generic` |

## Demo on synthetic footage

```bash
python examples/make_sample_gameplay.py --out examples/sample_gameplay.mp4
python clip.py examples/sample_gameplay.mp4 --out examples/sample_out --max-clips 3
```

## Suggested Cricket 24 workflow

1. Record/export **your** match from PS5/PC (not someone else's YouTube upload)
2. Drop the file into this folder
3. Run auto-detect for powerplay chaos, or pass known boundary/wicket timestamps
4. Upload `out/shorts/*.mp4` with the titles from `posting_sheet.md`
5. Lead with the hook in the first line of the caption

## Tests

```bash
cd clipping-pipeline
python -m unittest discover -s tests -v
```

## Notes

- This tool expects **footage you own or have rights to use**.
- Detection quality depends on crowd/SFX levels; quiet menu sections are ignored via `ignore_head` / `ignore_tail`.
- For commentary-heavy tracks, slightly raise `z_threshold` so constant talk doesn't flood peaks.
