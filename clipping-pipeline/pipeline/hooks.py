from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .detect import ClipWindow


@dataclass
class HookPack:
    hook: str
    title: str
    caption: str
    hashtags: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


CRICKET24_HOOKS = [
    "THIS six broke the powerplay",
    "Wait for the crowd on this ball",
    "Wicket out of nowhere",
    "Cover drive. Pure timing.",
    "Bowling change. Instant damage.",
    "That edge... and NO ONE there",
    "Powerplay chaos starts HERE",
    "He picked the gap perfectly",
    "Catch of the over?",
    "CSKvsRCB energy in Cricket 24",
]

GENERIC_HOOKS = [
    "You won't believe this play",
    "Pause at the end",
    "This is the clip",
    "Insane timing",
    "Watch the last second",
]


def _pick(pool: list[str], index: int) -> str:
    if not pool:
        return "Highlight drop"
    return pool[(index - 1) % len(pool)]


def build_hook(
    window: ClipWindow,
    *,
    style: str = "cricket24",
    extra: list[str] | None = None,
    source_label: str | None = None,
) -> HookPack:
    extra = extra or []
    if style == "cricket24":
        pool = extra + CRICKET24_HOOKS
        hashtags = [
            "#Cricket24",
            "#IPL",
            "#GamingShorts",
            "#PS5",
            "#Cricket",
            "#Shorts",
        ]
        base_title = "Cricket 24 Powerplay Highlight"
    else:
        pool = extra + GENERIC_HOOKS
        hashtags = ["#Gaming", "#Shorts", "#Gameplay", "#Viral"]
        base_title = "Gameplay Highlight"

    hook = _pick(pool, window.index)
    title = f"{hook} | {base_title} #{window.index}"
    if source_label:
        title = f"{hook} | {source_label}"

    caption = (
        f"{hook}\n\n"
        f"Peak at {window.peak_time:.1f}s · clip {window.start:.1f}–{window.end:.1f}s\n\n"
        + " ".join(hashtags)
    )
    return HookPack(hook=hook, title=title, caption=caption, hashtags=hashtags)