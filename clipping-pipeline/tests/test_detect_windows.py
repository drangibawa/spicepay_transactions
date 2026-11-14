from __future__ import annotations

import unittest

from pipeline.detect import Peak, build_windows, parse_manual_ranges


class DetectWindowTests(unittest.TestCase):
    def test_build_windows_merges_and_ranks(self) -> None:
        peaks = [
            Peak(time=10.0, score=2.0, rms=0.2),
            Peak(time=12.0, score=5.0, rms=0.5),  # near first; higher score wins region
            Peak(time=30.0, score=3.0, rms=0.3),
            Peak(time=50.0, score=1.0, rms=0.1),
        ]
        windows = build_windows(
            peaks,
            duration=60.0,
            clip_cfg={
                "pre_roll": 3.0,
                "post_roll": 5.0,
                "min_duration": 8.0,
                "max_duration": 20.0,
                "merge_gap": 6.0,
                "max_clips": 2,
            },
        )
        self.assertEqual(len(windows), 2)
        # Highest unique regions: ~12s and ~30s
        times = sorted(w.peak_time for w in windows)
        self.assertAlmostEqual(times[0], 12.0, places=1)
        self.assertAlmostEqual(times[1], 30.0, places=1)

    def test_manual_ranges(self) -> None:
        windows = parse_manual_ranges(["5-20", "40-55"], duration=100.0)
        self.assertEqual(len(windows), 2)
        self.assertEqual(windows[0].start, 5.0)
        self.assertEqual(windows[1].end, 55.0)
        self.assertEqual(windows[0].reason, "manual")


if __name__ == "__main__":
    unittest.main()