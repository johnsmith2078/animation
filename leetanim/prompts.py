from __future__ import annotations

import json

from .models import ProblemArtifact, TimelineArtifact


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
4. 结尾请用 1 到 2 句做自然的总结收尾，不要突然中断
5. 输出必须是 markdown，不要输出 JSON

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
4. narration 里不要出现 markdown 语法、表格、代码块、项目符号
5. animation_beats 每段 2 到 5 条
6. 不要输出 markdown，只能输出 JSON
7. JSON 结构参考下面 schema

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


def manim_system_prompt() -> str:
    return (
        "你是一名资深 Manim 动画工程师。"
        "请使用 manimlib/manimgl 风格 API 生成真正的动画代码。"
        "默认按无 LaTeX 环境处理，不要使用 Tex/MathTex/Brace 等依赖 LaTeX 的对象。"
        "不要把动画指导文本原样渲染到屏幕上。"
        "只输出 Python 代码，不要输出解释。"
    )


def build_manim_user_prompt(
    problem: ProblemArtifact,
    solution_markdown: str,
    timeline: TimelineArtifact,
) -> str:
    timeline_json = json.dumps(timeline.to_dict(), ensure_ascii=False, indent=2)
    return f'''请根据下面的题目、题解和时间轴，为 `manimlib` 生成真正的动画场景代码。

输出要求：
1. 只输出 Python 代码，不要输出解释
2. 第一行必须是：`class LeetCodeSolutionScene(Scene):`
3. 不要写任何 import
4. 不要写 `TIMELINE = ...`、`VIDEO_TITLE = ...`、`make_text(...)` 等公共前导代码；这些已经预置好了
5. 允许在类里定义辅助方法

你可以直接使用的全局对象 / helper：
- `TIMELINE`: dict，包含 video_title、segments、每段的 title/objective/narration/animation_beats/start_sec/end_sec
- `TIMELINE_SEGMENTS`: list，等价于 `TIMELINE["segments"]`
- `VIDEO_TITLE`: str
- `get_segment(segment_or_index)`
- `segment_duration_sec(segment_or_index)`
- `total_timeline_duration_sec()`
- `make_text(content, font_size=34, color=WHITE, width=FRAME_WIDTH - 1.2)`
- `make_paragraph(lines, font_size=28, color=WHITE, width=FRAME_WIDTH - 1.4, line_buff=0.18)`
- `make_array_row(values, highlight_indices=None, cell_width=1.2, cell_height=0.72, highlight_color=YELLOW)`
- `make_pointer(label, target_mobject, direction=UP, color=YELLOW)`
- `self.begin_segment(segment_or_index)`: 开始记录当前片段已消耗时长
- `self.segment_time_left(reserve_sec=0.0)`: 返回当前片段剩余预算时长
- `self.end_segment()`: 自动补足当前片段剩余时长，避免动画比配音快
- 所有屏幕文字优先调用 `make_text(...)` / `make_paragraph(...)`，不要直接写原始 `Text(...)`
- 默认按无 LaTeX 环境处理：不要使用 `Tex` / `MathTex` / `TexText` / `Brace` / `BraceLabel` / `BraceText`
- `make_array_row(...)` 返回一维 `VGroup`，单元格访问方式是 `row[i]`，不要写 `row[0][i]`

强约束：
1. 不要把 `animation_beats`、`objective`、`narration` 原样整段显示在屏幕上
2. 屏幕文字只保留短标题、关键词、数组值、索引、复杂度、极少量代码行等必要视觉元素
3. 主要通过真实动画表达：数组格子、高亮框、指针移动、哈希表写入、流程图、复杂度对比、代码框高亮等
4. 使用 manimlib/manimgl 常见 API，避免依赖 Manim Community 专属类或第三方插件
   - 画轮廓请用 `ShowCreation(...)`，不要用 `Create(...)`
   - 颜色只能使用 `manimlib.constants` 里真实存在的常量；优先用 `WHITE` / `BLACK` / `GREY` / `GREY_A`~`GREY_E` / `BLUE` / `BLUE_A`~`BLUE_E` / `GREEN` / `GREEN_A`~`GREEN_E` / `YELLOW` / `YELLOW_A`~`YELLOW_E` / `RED` / `RED_A`~`RED_E` / `ORANGE`
   - 不要使用 `GRAY`、`GRAY_A`~`GRAY_E`、`DARK_GREY`、`DARK_GRAY`、`LIGHT_GREY`、`LIGHT_GRAY` 这类别名
   - `Axes` 请优先传 `width` / `height`，不要依赖 Community 版的 `x_length` / `y_length`
   - 屏幕文本优先用 `make_text(...)` / `make_paragraph(...)`，避免直接 `Text(...)`
   - 不要使用任何 LaTeX 依赖对象，包括 `Tex` / `MathTex` / `TexText` / `Brace`；复杂度、公式、标签都用普通文本或图形表示
5. Scene 类名必须是 `LeetCodeSolutionScene`
6. 代码必须能被 Python `compile(..., "exec")` 解析
7. 每个 segment 都应该有明确的视觉变化，而不是纯文字轮播
8. 如果题型不适合复杂图形，就退回到“少量关键词 + 图形/框/箭头/流程”这种表达，而不是整段说明文字
9. 每个 segment 开始时都要调用 `self.begin_segment(segment)`，结束前调用 `self.end_segment()`
10. 片段内部如果有 `self.play(...)`，请尽量显式传 `run_time=...`，让总时长更稳定
11. 最终成片会根据 `05_outputs/audio/*.srt` 在画面底部烧录字幕；请把主要视觉元素、数组、代码框、说明文字放在中上区域，避免长期占用底部字幕安全区，不要频繁使用 `to_edge(DOWN)` 摆放核心内容
12. 已经讲完、且后续不再需要的 mobject，要及时用 `FadeOut(...)`、`Transform(...)`、`ReplacementTransform(...)` 或整体场景切换移除；不要让旧标题、旧高亮框、旧指针、旧代码块长期残留在屏幕上

实现建议：
- `construct()` 中按 `TIMELINE["segments"]` 的顺序组织片段
- 用标题切换、对象变换、局部高亮来表达“当前在讲什么”
- 推荐写法是：`segment = TIMELINE["segments"][i]` -> `self.begin_segment(segment)` -> 若干 `self.play(..., run_time=...)` / `self.wait(...)` -> `self.end_segment()`
- 可根据题型选择合适的视觉语言：数组/哈希、双指针、树、图、DP 表、递归栈、代码框等
- 对时长的把握以 segment 的 `start_sec` / `end_sec` 为硬约束；如果中间动画提前结束，必须用 `self.end_segment()` 补足剩余停留
- 默认预留画面底部约 20% 的字幕安全区；必要的辅助元素可以短暂经过下方，但不要让核心讲解信息与字幕长期重叠
- 每个 segment 结束前检查画面，只保留下一段还会复用的核心对象；其余元素应淡出或被替换，避免视觉堆积
- 当题目是“两数之和”这类数组题时，应优先展示数组、补数查找、哈希表写入、复杂度对比，而不是字幕墙
- 算法状态请保存在普通 Python 变量里，例如 list / dict / set；不要依赖读取 `VGroup` 子节点结构来判断业务状态

题目元信息：
- 题号: {problem.problem_id}
- 标题: {problem.title}
- 语言: {problem.language}

题目内容：
{problem.statement_markdown}

题解内容：
{solution_markdown}

时间轴 JSON：
{timeline_json}
'''


def build_manim_repair_user_prompt(candidate_code: str, error: str) -> str:
    return f'''下面是一段需要修复的 Manim scene 代码。它已经接近可用，但当前不能通过 Python 编译或不满足输出约束。

当前错误：
{error}

修复要求：
1. 只输出 Python 代码，不要解释
2. 第一行必须是：`class LeetCodeSolutionScene(Scene):`
3. 不要写 import
4. 保持“真正的动画代码”方向，不要退化成把指导文字整段显示到屏幕上
5. 优先修复语法错误、括号/缩进问题和明显不兼容的 manimlib 用法
6. `make_array_row(...)` 返回一维 `VGroup`，访问数组格子时请使用 `row[i]`，不要写 `row[0][i]`
7. 屏幕文本优先使用 `make_text(...)` / `make_paragraph(...)`，避免直接 `Text(...)`
8. 默认按无 LaTeX 环境处理，不要使用 `Tex` / `MathTex` / `TexText` / `Brace` / `BraceLabel` / `BraceText`
9. 每个 segment 都要调用 `self.begin_segment(segment)` 和 `self.end_segment()`，按时间轴对齐片段时长
10. 有 `self.play(...)` 时尽量显式传 `run_time=...`
11. 颜色只能使用 `manimlib.constants` 中真实存在的常量；不要输出 `GRAY` / `DARK_GREY` / `LIGHT_GREY` / `DARK_GRAY` / `LIGHT_GRAY`
12. 最终成片会在底部烧录 `.srt` 字幕，修复时也要保留底部字幕安全区，不要把标题、数组、代码框等核心元素长期贴在底边
13. 已经讲完、后续不再使用的旧元素要及时淡出或替换，避免多个 segment 的标题、高亮框、指针、代码块长期残留在屏幕上

待修复代码：
```python
{candidate_code}
```
'''
