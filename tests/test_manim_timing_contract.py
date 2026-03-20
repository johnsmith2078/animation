from __future__ import annotations

import unittest

from leetanim.codegen import build_manim_scene_code
from leetanim.models import ProblemArtifact, TimelineArtifact, TimelineSegment
from leetanim.pipeline import Pipeline
from leetanim.prompts import build_manim_user_prompt


class ManimTimingContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.problem = ProblemArtifact(
            problem_id="1",
            title="两数之和",
            slug="two-sum",
            source="manual",
            language="zh-CN",
            statement_markdown="# 1. 两数之和",
        )
        self.timeline = TimelineArtifact(
            video_title="LeetCode 1. 两数之和题解",
            problem_id="1",
            problem_title="两数之和",
            language="zh-CN",
            target_duration_sec=30.0,
            segments=[
                TimelineSegment(
                    id="s01",
                    title="题目理解",
                    objective="理解输入输出",
                    narration="给定数组 nums 和目标值 target。",
                    animation_beats=["展示数组", "标出目标值"],
                    estimated_duration_sec=5.0,
                ),
                TimelineSegment(
                    id="s02",
                    title="哈希表思路",
                    objective="说明补数查找",
                    narration="遍历数组，用哈希表记录已经见过的数。",
                    animation_beats=["移动指针", "高亮补数"],
                    estimated_duration_sec=6.0,
                ),
            ],
        )

    def test_prompt_requires_segment_timing_helpers(self) -> None:
        prompt = build_manim_user_prompt(self.problem, "解题过程", self.timeline)

        self.assertIn("self.begin_segment(segment)", prompt)
        self.assertIn("self.end_segment()", prompt)
        self.assertIn("run_time=...", prompt)
        self.assertIn("DARK_GREY", prompt)
        self.assertIn("LIGHT_GREY", prompt)
        self.assertIn("烧录字幕", prompt)
        self.assertIn("底部约 20% 的字幕安全区", prompt)
        self.assertIn("FadeOut", prompt)
        self.assertIn("不要让旧标题、旧高亮框、旧指针、旧代码块长期残留在屏幕上", prompt)

    def test_validate_manim_scene_body_rejects_missing_segment_timing(self) -> None:
        missing_timing = """class LeetCodeSolutionScene(Scene):
    def construct(self):
        title = make_text("两数之和")
        self.play(FadeIn(title), run_time=1.0)
"""

        with self.assertRaisesRegex(ValueError, "begin_segment"):
            Pipeline._validate_manim_scene_body(missing_timing)

    def test_validate_manim_scene_body_accepts_segment_timing_contract(self) -> None:
        valid = """class LeetCodeSolutionScene(Scene):
    def construct(self):
        segment = TIMELINE["segments"][0]
        self.begin_segment(segment)
        self.play(FadeIn(make_text("两数之和")), run_time=1.0)
        self.end_segment()
"""

        Pipeline._validate_manim_scene_body(valid)

    def test_extract_valid_manim_scene_body_normalizes_common_color_aliases(self) -> None:
        raw = """```python
class LeetCodeSolutionScene(Scene):
    def construct(self):
        segment = TIMELINE["segments"][0]
        self.begin_segment(segment)
        label = "DARK_GREY"
        accent = GRAY_A
        box = Rectangle().set_fill(DARK_GREY, 0.9).set_stroke(LIGHT_GRAY, 2)
        self.play(FadeIn(box), run_time=1.0)
        self.play(FadeIn(make_text(label, color=accent)), run_time=1.0)
        self.end_segment()
```"""

        scene_body = Pipeline._extract_valid_manim_scene_body(raw)

        self.assertIn('label = "DARK_GREY"', scene_body)
        self.assertIn("accent = GREY_A", scene_body)
        self.assertIn("set_fill(GREY_E, 0.9)", scene_body)
        self.assertIn("set_stroke(GREY_A, 2)", scene_body)
        self.assertNotIn("accent = GRAY_A", scene_body)

    def test_generated_scene_code_compiles_with_latex_backslashes_in_preamble(self) -> None:
        source = build_manim_scene_code(self.problem, self.timeline)

        compile(source, "<generated_manim_scene>", "exec")


if __name__ == "__main__":
    unittest.main()
