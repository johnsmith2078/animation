from __future__ import annotations

import unittest

from leetanim.codegen import build_manim_scene_code
from leetanim.models import ProblemArtifact, TimelineArtifact, TimelineSegment


class ManimTextWrapperTests(unittest.TestCase):
    def test_generated_scene_wraps_text_with_safe_helper(self) -> None:
        problem = ProblemArtifact(
            problem_id="1",
            title="两数之和",
            slug="two-sum",
            source="manual",
            language="zh-CN",
            statement_markdown="# 1. 两数之和",
        )
        timeline = TimelineArtifact(
            video_title="LeetCode 1. 两数之和题解",
            problem_id="1",
            problem_title="两数之和",
            language="zh-CN",
            target_duration_sec=30.0,
            segments=[
                TimelineSegment(
                    id="s01",
                    title="题目理解",
                    objective="目标",
                    narration="示例 narration",
                    animation_beats=["显示数组"],
                    estimated_duration_sec=5.0,
                )
            ],
        )

        source = build_manim_scene_code(problem, timeline)

        self.assertIn("_OriginalText = Text", source)
        self.assertIn("def segment_duration_sec(segment_or_index):", source)
        self.assertIn("Scene.begin_segment = _begin_segment", source)
        self.assertIn("Scene.end_segment = _end_segment", source)
        self.assertIn("def sanitize_screen_text(content):", source)
        self.assertIn("def Text(content=", source)
        compile(source, "<generated_manim_scene>", "exec")


if __name__ == "__main__":
    unittest.main()
