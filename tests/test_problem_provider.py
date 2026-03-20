from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from leetanim.models import ProblemArtifact
from leetanim.pipeline import Pipeline
from leetanim.problem_provider import LeetCodeCNProvider, _QuestionSummary, leetcode_html_to_markdown
from leetanim.utils import read_json, read_text


class LeetCodeProblemProviderTests(unittest.TestCase):
    def test_leetcode_html_to_markdown_preserves_examples_lists_and_code(self) -> None:
        html = """
        <p>给定一个整数数组 <code>nums</code> 和一个整数 <code>target</code>。</p>
        <p><strong class="example">示例 1：</strong></p>
        <pre><strong>输入：</strong>nums = [2,7,11,15], target = 9
<strong>输出：</strong>[0,1]</pre>
        <p><strong>提示：</strong></p>
        <ul>
            <li><code>2 &lt;= nums.length &lt;= 10<sup>4</sup></code></li>
            <li>只会存在一个有效答案</li>
        </ul>
        """

        markdown = leetcode_html_to_markdown(html)

        self.assertIn("`nums`", markdown)
        self.assertIn("示例 1：", markdown)
        self.assertIn("```text", markdown)
        self.assertIn("输入：nums = [2,7,11,15], target = 9", markdown)
        self.assertIn("- `2 <= nums.length <= 10^4`", markdown)
        self.assertIn("- 只会存在一个有效答案", markdown)

    def test_fetch_by_frontend_id_builds_problem_artifact(self) -> None:
        provider = LeetCodeCNProvider()
        summary = _QuestionSummary(
            frontend_question_id="1",
            title="Two Sum",
            title_cn="两数之和",
            title_slug="two-sum",
        )
        detail = {
            "questionId": "1",
            "questionFrontendId": "1",
            "title": "Two Sum",
            "titleSlug": "two-sum",
            "translatedTitle": "两数之和",
            "translatedContent": "<p>给定一个整数数组 <code>nums</code> 和目标值 <code>target</code>。</p>",
            "difficulty": "Easy",
            "isPaidOnly": False,
            "topicTags": [
                {
                    "name": "Array",
                    "slug": "array",
                    "translatedName": "数组",
                }
            ],
        }

        with (
            patch.object(provider, "_find_question_summary", return_value=summary) as find_mock,
            patch.object(provider, "_fetch_question_detail", return_value=detail) as detail_mock,
        ):
            problem = provider.fetch_by_frontend_id("001")

        find_mock.assert_called_once_with("1")
        detail_mock.assert_called_once_with("two-sum")
        self.assertEqual(problem.problem_id, "1")
        self.assertEqual(problem.title, "两数之和")
        self.assertEqual(problem.slug, "two-sum")
        self.assertEqual(problem.source, "leetcode.cn")
        self.assertEqual(problem.language, "zh-CN")
        self.assertIn("# 1. 两数之和", problem.statement_markdown)
        self.assertIn("`nums`", problem.statement_markdown)
        self.assertEqual(problem.metadata["difficulty"], "Easy")
        self.assertEqual(problem.metadata["title_slug"], "two-sum")


class PipelineCreateRunTests(unittest.TestCase):
    def test_create_run_auto_fetches_problem_from_leetcode_cn(self) -> None:
        provider = Mock()
        provider.fetch_by_frontend_id.return_value = ProblemArtifact(
            problem_id="1",
            title="两数之和",
            slug="two-sum",
            source="leetcode.cn",
            language="zh-CN",
            statement_markdown="# 1. 两数之和\n\n给定一个整数数组 nums 和一个目标值 target。",
            metadata={"provider": "leetcode.cn/graphql"},
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = Pipeline(Path(tmpdir), problem_provider=provider)
            run_dir = pipeline.create_run(problem_id="1")

            provider.fetch_by_frontend_id.assert_called_once_with("1")
            problem_json = read_json(run_dir / "01_problem" / "problem.json")
            problem_md = read_text(run_dir / "01_problem" / "problem.md")

        self.assertEqual(problem_json["problem_id"], "1")
        self.assertEqual(problem_json["title"], "两数之和")
        self.assertEqual(problem_json["slug"], "two-sum")
        self.assertEqual(problem_json["source"], "leetcode.cn")
        self.assertEqual(problem_json["language"], "zh-CN")
        self.assertEqual(problem_md, "# 1. 两数之和\n\n给定一个整数数组 nums 和一个目标值 target。")
        self.assertEqual(problem_json["metadata"]["provider"], "leetcode.cn/graphql")
        self.assertIsNone(problem_json["metadata"]["original_problem_file"])

    def test_create_run_prefers_manual_problem_text_over_auto_fetch(self) -> None:
        provider = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = Pipeline(Path(tmpdir), problem_provider=provider)
            run_dir = pipeline.create_run(
                problem_text="# 1. 手工题面\n\n这里是手工提供的题目描述。",
                problem_id="1",
                title="手工题面",
            )

            provider.fetch_by_frontend_id.assert_not_called()
            problem_json = read_json(run_dir / "01_problem" / "problem.json")

        self.assertEqual(problem_json["title"], "手工题面")
        self.assertEqual(problem_json["source"], "manual")


if __name__ == "__main__":
    unittest.main()
