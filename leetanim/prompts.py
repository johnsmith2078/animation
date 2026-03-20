from __future__ import annotations

import json

from .models import ProblemArtifact


def solution_system_prompt() -> str:
    return (
        "你是一名资深算法讲解作者。"
        "请把题目转成适合视频讲解的中文题解，结构要清晰、简洁、可直接用于后续生成动画与配音。"
    )


def build_solution_user_prompt(problem: ProblemArtifact) -> str:
    return f'''请根据下面的 LeetCode 题目生成一份中文题解 markdown。

要求：
1. 面向视频讲解，语言自然、口语化，但不要太啰嗦
2. 必须包含以下章节：
   - 题目理解
   - 核心思路
   - 步骤拆解
   - 复杂度分析
   - 易错点
   - Python 代码
3. 如果有必要，可以补充一个简短例子演示
4. 输出必须是 markdown，不要输出 JSON

题目元信息：
- 题号: {problem.problem_id}
- 标题: {problem.title}
- 语言: {problem.language}
- 来源: {problem.source}

题目内容：

{problem.statement_markdown}
'''


def timeline_system_prompt() -> str:
    return (
        "你是一名算法动画导演。"
        "请把题解拆成一个可用于配音和动画同步的时间轴 JSON。"
        "只输出 JSON，不要输出额外解释。"
    )


_TIMELINE_SCHEMA_EXAMPLE = json.dumps(
    {
        "video_title": "LeetCode 1. 两数之和题解",
        "target_duration_sec": 90,
        "segments": [
            {
                "id": "s01",
                "title": "题目目标",
                "objective": "先明确题目到底要我们返回什么",
                "narration": "这道题会给我们一个数组和一个目标值，我们需要找到两个数，让它们的和等于目标值，并返回下标。",
                "animation_beats": [
                    "展示题号与标题",
                    "显示 nums 与 target",
                    "高亮 返回下标 这个关键点"
                ],
                "estimated_duration_sec": 8
            }
        ]
    },
    ensure_ascii=False,
    indent=2,
)


def build_timeline_user_prompt(
    problem: ProblemArtifact,
    solution_markdown: str,
    target_duration_sec: float,
) -> str:
    return f'''请把下面的题解改写成适合生成题解动画的视频时间轴。

目标：
- 生成一个统一的时间轴 JSON
- 每个 segment 同时服务于配音和动画
- narration 是配音文案
- animation_beats 是动画提示
- objective 是当前片段的视觉目标，必须短小

硬性要求：
1. 总时长目标约为 {target_duration_sec} 秒
2. segment 数量控制在 4 到 8 个
3. narration 适合口播
4. animation_beats 每段 2 到 5 条
5. 不要输出 markdown，只能输出 JSON
6. JSON 结构参考下面 schema

参考 schema：
{_TIMELINE_SCHEMA_EXAMPLE}

题目：
- 题号: {problem.problem_id}
- 标题: {problem.title}

题目内容：
{problem.statement_markdown}

题解内容：
{solution_markdown}
'''
