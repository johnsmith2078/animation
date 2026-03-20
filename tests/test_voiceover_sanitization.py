from __future__ import annotations

import unittest

from leetanim.codegen import build_fallback_timeline, build_voiceover_markdown
from leetanim.models import ProblemArtifact, TimelineArtifact, TimelineSegment
from leetanim.utils import markdown_to_speech_text


class VoiceoverSanitizationTests(unittest.TestCase):
    def test_markdown_to_speech_text_ignores_horizontal_rules(self) -> None:
        narration = markdown_to_speech_text("前一句。\n\n---\n\n后一句。", max_chars=200)

        self.assertEqual(narration, "前一句。 后一句。")
        self.assertNotIn("---", narration)

    def test_markdown_to_speech_text_converts_table_and_quote(self) -> None:
        source = """
> 遍历数组时，先查补数，再决定是否写入哈希表。

| 步骤 | 当前数 | 结果 |
|------|--------|------|
| i=0 | 2 | 继续 |
| i=1 | 7 | 返回 [0, 1] ✅ |
"""
        narration = markdown_to_speech_text(source, max_chars=200)

        self.assertNotIn("|", narration)
        self.assertNotIn(">", narration)
        self.assertNotIn("✅", narration)
        self.assertIn("结果 继续", narration)
        self.assertIn("返回 [0, 1]", narration)

    def test_fallback_timeline_avoids_mid_sentence_ellipsis(self) -> None:
        problem = ProblemArtifact(
            problem_id="1",
            title="两数之和",
            slug="two-sum",
            source="manual",
            language="zh-CN",
            statement_markdown="# 1. 两数之和",
        )
        solution = """
## 题目理解

给你一个整数数组和一个目标值，要求找出数组中哪两个数加起来等于目标值，返回它们的下标。题目保证答案唯一，而且同一个元素不能用两次。

## 核心思路

更好的做法是用哈希表。

> 遍历数组时，对于当前数 `num`，我需要的另一半是 `target - num`。如果这个另一半之前已经出现过，直接返回；否则把当前数存进哈希表。

## 步骤拆解

1. 创建哈希表。
2. 先查 complement。
3. 再存当前值。

## 例子演示

| 步骤 | 当前数 | 需要的另一半 | 结果 |
|------|--------|-------------|------|
| i=0 | 2 | 7 | 继续 |
| i=1 | 7 | 2 | 返回 [0, 1] |

## 复杂度分析

- 时间复杂度：O(n)
- 空间复杂度：O(n)

## 易错点

1. 先查再存，不能先存再查。
2. 哈希表里存的是下标。
"""
        timeline = build_fallback_timeline(problem, solution, target_duration_sec=90, source_quality="test")

        self.assertGreaterEqual(len(timeline.segments), 5)
        for segment in timeline.segments:
            self.assertNotIn("…", segment.narration)
            self.assertNotIn("|", segment.narration)
            self.assertTrue(segment.narration.strip())

    def test_voiceover_markdown_sanitizes_existing_timeline_narration(self) -> None:
        timeline = TimelineArtifact(
            video_title="Test",
            problem_id="1",
            problem_title="两数之和",
            language="zh-CN",
            target_duration_sec=30.0,
            segments=[
                TimelineSegment(
                    id="s01",
                    title="例子演示",
                    objective="例子演示",
                    narration="| 步骤 | 结果 |\n|---|---|\n| i=1 | 返回 [0, 1] |",
                    animation_beats=["显示数组"],
                    estimated_duration_sec=6.0,
                )
            ],
        )

        markdown = build_voiceover_markdown(timeline)

        self.assertNotIn("|", markdown)
        self.assertIn("返回 [0, 1]", markdown)

    def test_markdown_to_speech_text_strips_broken_fence_tokens(self) -> None:
        narration = markdown_to_speech_text("比如 nums 等```json 于 3、3，target 等于 6。")

        self.assertNotIn("```json", narration)
        self.assertIn("nums 等于 3、3", narration)

    def test_fallback_timeline_replaces_rule_only_section_with_safe_narration(self) -> None:
        problem = ProblemArtifact(
            problem_id="1",
            title="两数之和",
            slug="two-sum",
            source="manual",
            language="zh-CN",
            statement_markdown="# 1. 两数之和",
        )
        solution = """
## 题目理解

一句话说明题意。

## 例子演示

```text
nums = [2, 7, 11, 15], target = 9
```

---

## 复杂度分析

- 时间复杂度：O(n)
"""
        timeline = build_fallback_timeline(problem, solution, target_duration_sec=45, source_quality="test")

        example_segment = next(segment for segment in timeline.segments if segment.title == "例子演示")
        self.assertEqual(example_segment.narration, "这一段我们重点讲 例子演示。")


if __name__ == "__main__":
    unittest.main()
