from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from leetanim.subtitles import (
    build_ffmpeg_subtitles_filter,
    load_segment_duration_lookup,
    merge_srt_payloads,
    parse_srt,
)


class SubtitleHelpersTests(unittest.TestCase):
    def test_merge_srt_payloads_offsets_following_segments_by_duration_lookup(self) -> None:
        merged = merge_srt_payloads(
            [
                (
                    "s01",
                    "1\n00:00:00,000 --> 00:00:01,000\n第一段字幕\n",
                ),
                (
                    "s02",
                    "1\n00:00:00,100 --> 00:00:00,600\n第二段字幕\n",
                ),
            ],
            duration_lookup={"s01": 1.5, "s02": 0.6},
        )

        cues = parse_srt(merged)
        self.assertEqual(len(cues), 2)
        self.assertEqual(cues[0].start_ms, 0)
        self.assertEqual(cues[0].end_ms, 1000)
        self.assertEqual(cues[1].start_ms, 1600)
        self.assertEqual(cues[1].end_ms, 2100)
        self.assertEqual(cues[1].text, "第二段字幕")

    def test_load_segment_duration_lookup_prefers_actual_audio_duration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            timeline_path = Path(tmp_dir) / "timeline.json"
            timeline_path.write_text(
                json.dumps(
                    {
                        "segments": [
                            {
                                "id": "s01",
                                "start_sec": 0.0,
                                "end_sec": 1.0,
                                "actual_audio_duration_sec": 1.23,
                            },
                            {
                                "id": "s02",
                                "start_sec": 1.0,
                                "end_sec": 2.8,
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            lookup = load_segment_duration_lookup(timeline_path)

        self.assertEqual(lookup["s01"], 1.23)
        self.assertEqual(lookup["s02"], 1.8)

    def test_build_ffmpeg_subtitles_filter_escapes_special_characters(self) -> None:
        filter_arg = build_ffmpeg_subtitles_filter(Path("/tmp/sub titles/part's[1]:2.srt"))

        self.assertIn("subtitles='", filter_arg)
        self.assertIn(r"part\'s\[1\]\:2.srt", filter_arg)
        self.assertIn("force_style='Alignment=2,MarginV=28", filter_arg)


if __name__ == "__main__":
    unittest.main()
