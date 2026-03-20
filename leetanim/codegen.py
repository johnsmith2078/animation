from __future__ import annotations

import json
from typing import Iterable

from .models import ProblemArtifact, TimelineArtifact, TimelineSegment
from .utils import (
    clamp_text,
    estimate_speech_duration_sec,
    markdown_to_speech_text,
    seconds_to_timestamp,
    strip_markdown,
)


def build_solution_stub(problem: ProblemArtifact, reason: str | None = None) -> str:
    notice = ""
    if reason:
        notice = (
            "> [自动题解未完成]\n"
            f"> 原因：{reason}\n"
            "> 你可以手动编辑本文件后继续执行后续阶段。\n\n"
        )
    excerpt = clamp_text(problem.statement_markdown, 400)
    return f'''{notice}# {problem.problem_id}. {problem.title} 题解

## 题目理解

这道题的原始题意如下：

{excerpt}

我们最终需要明确：输入是什么、输出是什么、有没有唯一解、能不能重复使用元素，以及数据规模会不会影响算法选择。

## 核心思路

TODO: 在这里补充真正的核心思路，比如哈希表、双指针、二分、DFS、DP 等。

## 步骤拆解

1. 先说明如何从题意抽象出问题模型
2. 再说明关键数据结构或不变量
3. 最后说明算法如何一步步得到答案

## 复杂度分析

- 时间复杂度：TODO
- 空间复杂度：TODO

## 易错点

- 是否会重复使用同一个元素
- 返回的是值还是下标
- 边界情况是否需要单独处理

## Python 代码

```python
class Solution:
    def solve(self, *args, **kwargs):
        raise NotImplementedError("请补充本题代码")
```
'''


def _markdown_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_title: str | None = None
    current_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## ") or stripped.startswith("### "):
            if current_title:
                sections.append((current_title, "\n".join(current_lines).strip()))
            current_title = stripped.lstrip("#").strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_title:
        sections.append((current_title, "\n".join(current_lines).strip()))
    return [(title, body) for title, body in sections if body]


def _default_segment_plan(problem: ProblemArtifact) -> list[tuple[str, str, str]]:
    return [
        ("题目目标", "先明确输入输出与限制", f"先快速看一下这道题。{problem.title} 这类题，最重要的是先搞清楚输入是什么，输出又要求什么。"),
        ("核心思路", "提炼解决问题的关键方法", "接下来我们不急着写代码，而是先想一个最核心的思路，找到题目中最值得利用的信息。"),
        ("步骤演示", "把算法执行过程拆开讲清楚", "有了思路之后，我们再用一个小例子，把算法执行过程一步一步走一遍。"),
        ("复杂度分析", "说明时间和空间代价", "最后再看复杂度，判断这个做法在题目的数据范围下是否足够高效。"),
        ("代码总结", "把思路映射成最终代码", "理解完流程以后，再把它翻译成代码，实现时重点关注边界和细节。"),
    ]


def _allocate_narration_char_budgets(section_bodies: list[str], target_duration_sec: float) -> list[int]:
    if not section_bodies:
        return []

    raw_lengths = [max(1, len(strip_markdown(body))) for body in section_bodies]
    min_per_segment = 30
    total_budget = max(min_per_segment * len(section_bodies), int(max(0.0, target_duration_sec - len(section_bodies)) * 4.8))

    budgets = [min(length, min_per_segment) for length in raw_lengths]
    remaining = max(0, total_budget - sum(budgets))

    while remaining > 0:
        capacities = [raw - budget for raw, budget in zip(raw_lengths, budgets)]
        total_capacity = sum(capacity for capacity in capacities if capacity > 0)
        if total_capacity <= 0:
            break

        distributed = 0
        for index, capacity in enumerate(capacities):
            if capacity <= 0:
                continue
            extra = max(1, int(remaining * capacity / total_capacity))
            extra = min(extra, capacity, remaining)
            budgets[index] += extra
            remaining -= extra
            distributed += extra
            if remaining == 0:
                break
        if distributed == 0:
            break

    return budgets


def build_fallback_timeline(
    problem: ProblemArtifact,
    solution_text: str,
    target_duration_sec: float,
    source_quality: str,
) -> TimelineArtifact:
    sections = _markdown_sections(solution_text)
    segment_defs: list[tuple[str, str, str, list[str]]] = []

    if sections:
        chosen_sections = sections[:6]
        budgets = _allocate_narration_char_budgets([body for _, body in chosen_sections], target_duration_sec)
        for (title, body), budget in zip(chosen_sections, budgets):
            narration_budget = budget + 28 if body.count("|") >= 4 else budget
            clean_body = markdown_to_speech_text(body, max_chars=narration_budget)
            segment_defs.append(
                (
                    title,
                    clamp_text(title, 28),
                    clean_body or f"这一段我们重点讲 {title}。",
                    [
                        f"显示标题：{title}",
                        "逐条呈现这一段的关键点",
                        "与配音保持同步停留",
                    ],
                )
            )

    if not segment_defs:
        for title, objective, narration in _default_segment_plan(problem):
            segment_defs.append(
                (
                    title,
                    objective,
                    narration,
                    [
                        f"显示标题：{title}",
                        "展示当前阶段的核心结论",
                        "保留足够停留时间匹配配音",
                    ],
                )
            )

    raw_durations = [estimate_speech_duration_sec(narration) for _, _, narration, _ in segment_defs]
    total_raw = sum(raw_durations) or 1.0
    scale = target_duration_sec / total_raw if target_duration_sec > 0 else 1.0

    segments: list[TimelineSegment] = []
    cursor = 0.0
    for index, (title, objective, narration, beats) in enumerate(segment_defs, start=1):
        duration = max(4.0, round(raw_durations[index - 1] * scale, 1))
        segment = TimelineSegment(
            id=f"s{index:02d}",
            title=title,
            objective=objective,
            narration=narration,
            animation_beats=beats,
            estimated_duration_sec=duration,
            start_sec=round(cursor, 1),
            end_sec=round(cursor + duration, 1),
        )
        cursor = segment.end_sec
        segments.append(segment)

    return TimelineArtifact(
        video_title=f"LeetCode {problem.problem_id}. {problem.title} 题解",
        problem_id=problem.problem_id,
        problem_title=problem.title,
        language=problem.language,
        target_duration_sec=target_duration_sec,
        segments=segments,
        metadata={"timeline_source": source_quality},
    )


def coerce_timeline_from_model(problem: ProblemArtifact, payload: dict, target_duration_sec: float) -> TimelineArtifact:
    segments_raw = payload.get("segments", [])
    if not isinstance(segments_raw, list) or not segments_raw:
        raise ValueError("timeline JSON 中缺少 segments")

    segments: list[TimelineSegment] = []
    cursor = 0.0
    for index, item in enumerate(segments_raw, start=1):
        if not isinstance(item, dict):
            raise ValueError("timeline segment 必须是对象")
        narration = markdown_to_speech_text(str(item.get("narration", ""))).strip()
        if not narration:
            narration = f"这一段我们讲 {item.get('title', f'片段 {index}')}。"
        beats = item.get("animation_beats", [])
        if not isinstance(beats, list):
            beats = [str(beats)]
        duration = float(item.get("estimated_duration_sec", 0.0) or 0.0)
        if duration <= 0:
            duration = estimate_speech_duration_sec(narration)
        duration = max(3.5, round(duration, 1))
        segment = TimelineSegment(
            id=str(item.get("id") or f"s{index:02d}"),
            title=str(item.get("title") or f"片段 {index}"),
            objective=str(item.get("objective") or str(item.get("title") or f"片段 {index}")),
            narration=narration,
            animation_beats=[str(beat) for beat in beats[:5]] or ["显示当前片段的重点", "与配音同步停留"],
            estimated_duration_sec=duration,
            start_sec=round(cursor, 1),
            end_sec=round(cursor + duration, 1),
        )
        cursor = segment.end_sec
        segments.append(segment)

    return TimelineArtifact(
        video_title=str(payload.get("video_title") or f"LeetCode {problem.problem_id}. {problem.title} 题解"),
        problem_id=problem.problem_id,
        problem_title=problem.title,
        language=problem.language,
        target_duration_sec=float(payload.get("target_duration_sec", target_duration_sec) or target_duration_sec),
        segments=segments,
        metadata={"timeline_source": "llm"},
    )


def rebuild_segment_times(timeline: TimelineArtifact, use_actual_audio: bool = False) -> TimelineArtifact:
    cursor = 0.0
    for segment in timeline.segments:
        duration = segment.estimated_duration_sec
        if use_actual_audio and segment.actual_audio_duration_sec is not None:
            duration = float(segment.actual_audio_duration_sec)
        duration = max(0.5, round(duration, 1))
        segment.start_sec = round(cursor, 1)
        segment.end_sec = round(cursor + duration, 1)
        segment.estimated_duration_sec = duration
        cursor = segment.end_sec
    return timeline


def build_voiceover_markdown(timeline: TimelineArtifact) -> str:
    lines = [f"# {timeline.video_title} 配音脚本", ""]
    for segment in timeline.segments:
        narration = markdown_to_speech_text(segment.narration).strip() or f"这一段我们讲 {segment.title}。"
        lines.append(
            f"## {segment.id} [{seconds_to_timestamp(segment.start_sec)} - {seconds_to_timestamp(segment.end_sec)}] {segment.title}"
        )
        lines.append("")
        lines.append(narration)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def build_animation_markdown(timeline: TimelineArtifact) -> str:
    lines = [f"# {timeline.video_title} 动画脚本", ""]
    for segment in timeline.segments:
        lines.append(
            f"## {segment.id} [{seconds_to_timestamp(segment.start_sec)} - {seconds_to_timestamp(segment.end_sec)}] {segment.title}"
        )
        lines.append("")
        lines.append(f"- 目标：{segment.objective}")
        for beat in segment.animation_beats:
            lines.append(f"- {beat}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _build_manim_scene_preamble(problem: ProblemArtifact, timeline: TimelineArtifact) -> str:
    timeline_json = json.dumps(timeline.to_dict(), ensure_ascii=False, indent=2)
    problem_title = f"{problem.problem_id}. {problem.title}"
    return f'''from manimlib import *
import json
import math
import os
import re
import textwrap
import unicodedata
import numpy as np

try:
    import manimpango
except Exception:
    manimpango = None

# 如果中文字体显示异常，可通过环境变量 LEETANIM_MANIM_FONT 强制指定字体，
# 例如：Microsoft YaHei / PingFang SC / Noto Sans CJK SC
DEFAULT_FONT = os.getenv("LEETANIM_MANIM_FONT", "").strip() or None
FONT_CANDIDATES = [
    "Microsoft YaHei",
    "Microsoft YaHei UI",
    "SimHei",
    "PingFang SC",
    "Hiragino Sans GB",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "WenQuanYi Micro Hei",
    "Sarasa Gothic SC",
    "Arial Unicode MS",
]
FONT_HINTS = (
    "yahei",
    "heiti",
    "hei",
    "pingfang",
    "hiragino",
    "noto sans cjk",
    "source han",
    "wenquanyi",
    "sarasa",
    "unicode",
    "song",
    "kai",
    "sc",
)
WINDOWS_CJK_FALLBACK = "Microsoft YaHei"

TIMELINE = json.loads(r"""{timeline_json}""")
TIMELINE_SEGMENTS = TIMELINE.get("segments", [])
VIDEO_TITLE = {problem_title!r}


def pick_font():
    if DEFAULT_FONT:
        return DEFAULT_FONT
    if manimpango is None:
        return WINDOWS_CJK_FALLBACK if os.name == "nt" else "sans"
    try:
        fonts = list(manimpango.list_fonts())
    except Exception:
        return WINDOWS_CJK_FALLBACK if os.name == "nt" else "sans"

    if os.name == "nt" and WINDOWS_CJK_FALLBACK in fonts:
        return WINDOWS_CJK_FALLBACK

    available = set(fonts)
    for candidate in FONT_CANDIDATES:
        if candidate in available:
            return candidate

    for font_name in fonts:
        lowered = font_name.lower()
        if any(hint in lowered for hint in FONT_HINTS):
            return font_name
    return "sans"


ACTIVE_FONT = pick_font()
print(f"[manim] ACTIVE_FONT={{ACTIVE_FONT}}")

# LLM 偶尔会写出 Manim Community 风格的名字，这里做最小兼容层。
Create = ShowCreation
GRAY = GREY
_OriginalText = Text
_OriginalAxes = Axes
_OriginalScenePlay = Scene.play
_OriginalSceneWait = Scene.wait


def _coerce_non_negative_seconds(value, fallback=0.0):
    try:
        seconds = float(value)
    except Exception:
        seconds = fallback
    return max(0.0, seconds)


def get_segment(segment_or_index):
    if isinstance(segment_or_index, int):
        return TIMELINE_SEGMENTS[segment_or_index]
    return segment_or_index


def segment_duration_sec(segment_or_index):
    segment = get_segment(segment_or_index)
    if not isinstance(segment, dict):
        return 0.5
    start = _coerce_non_negative_seconds(segment.get("start_sec", 0.0))
    end = _coerce_non_negative_seconds(segment.get("end_sec", start), fallback=start)
    return max(0.5, round(end - start, 3))


def total_timeline_duration_sec():
    if not TIMELINE_SEGMENTS:
        return 0.0
    return round(sum(segment_duration_sec(segment) for segment in TIMELINE_SEGMENTS), 3)


def _record_segment_elapsed(scene, seconds):
    if not getattr(scene, "_leetanim_segment_timing_active", False):
        return
    elapsed = _coerce_non_negative_seconds(seconds)
    scene._leetanim_segment_elapsed_sec = round(
        _coerce_non_negative_seconds(getattr(scene, "_leetanim_segment_elapsed_sec", 0.0)) + elapsed,
        3,
    )


def _tracked_scene_play(self, *animations, **kwargs):
    result = _OriginalScenePlay(self, *animations, **kwargs)
    _record_segment_elapsed(self, kwargs.get("run_time", 1.0))
    return result


def _tracked_scene_wait(self, *args, **kwargs):
    result = _OriginalSceneWait(self, *args, **kwargs)
    duration = args[0] if args else kwargs.get("duration", 1.0)
    _record_segment_elapsed(self, duration)
    return result


def _begin_segment(self, segment_or_index):
    segment = get_segment(segment_or_index)
    self._leetanim_current_segment = segment
    self._leetanim_segment_target_sec = segment_duration_sec(segment)
    self._leetanim_segment_elapsed_sec = 0.0
    self._leetanim_segment_timing_active = True
    return self._leetanim_segment_target_sec


def _segment_time_left(self, reserve_sec=0.0):
    if not getattr(self, "_leetanim_segment_timing_active", False):
        return 0.0
    reserve = _coerce_non_negative_seconds(reserve_sec)
    target = _coerce_non_negative_seconds(getattr(self, "_leetanim_segment_target_sec", 0.0))
    elapsed = _coerce_non_negative_seconds(getattr(self, "_leetanim_segment_elapsed_sec", 0.0))
    return round(max(0.0, target - elapsed - reserve), 3)


def _end_segment(self):
    if not getattr(self, "_leetanim_segment_timing_active", False):
        return 0.0
    remaining = self.segment_time_left()
    self._leetanim_segment_timing_active = False
    self._leetanim_current_segment = None
    if remaining > 0:
        _OriginalSceneWait(self, remaining)
    return remaining


if not getattr(Scene, "_leetanim_timing_helpers_installed", False):
    Scene.play = _tracked_scene_play
    Scene.wait = _tracked_scene_wait
    Scene.begin_segment = _begin_segment
    Scene.segment_time_left = _segment_time_left
    Scene.end_segment = _end_segment
    Scene._leetanim_timing_helpers_installed = True

SCREEN_TEXT_REPLACEMENTS = (
    ("```json", " "),
    ("```python", " "),
    ("```", " "),
    ("`", ""),
    ("→", " -> "),
    ("←", " <- "),
    ("✓", " OK "),
    ("✔", " OK "),
    ("✕", " X "),
    ("✗", " X "),
    ("✅", " OK "),
    ("❌", " X "),
    ("—", " - "),
    ("–", " - "),
)


def sanitize_screen_text(content):
    text = unicodedata.normalize("NFKC", str(content))
    text = re.sub(r"<[^>]+>", " ", text)
    for old, new in SCREEN_TEXT_REPLACEMENTS:
        text = text.replace(old, new)
    text = re.sub(r"\\s+", " ", text).strip()
    return text or " "


class Axes(_OriginalAxes):
    def __init__(self, *args, x_length=None, y_length=None, **kwargs):
        if x_length is not None and "width" not in kwargs:
            kwargs["width"] = x_length
        if y_length is not None and "height" not in kwargs:
            kwargs["height"] = y_length
        super().__init__(*args, **kwargs)

    def get_axis_labels(self, x_label="x", y_label="y", **kwargs):
        color = kwargs.pop("color", WHITE)
        x_mob = make_text(str(kwargs.pop("x_label_tex", x_label)), font_size=24, color=color, width=1.6)
        y_mob = make_text(str(kwargs.pop("y_label_tex", y_label)), font_size=24, color=color, width=1.6)
        x_mob.next_to(self.get_x_axis().get_right(), DR, buff=0.15)
        y_mob.next_to(self.get_y_axis().get_top(), UR, buff=0.15)
        return VGroup(x_mob, y_mob)

    def get_graph_label(self, graph, label="f(x)", x=None, direction=RIGHT, buff=SMALL_BUFF, color=None, **kwargs):
        x = kwargs.pop("x_val", x)
        label_mob = label if isinstance(label, Mobject) else make_text(str(label), font_size=24, width=2.0)
        if color is None and hasattr(label_mob, "match_color"):
            label_mob.match_color(graph)
        elif color is not None and hasattr(label_mob, "set_color"):
            label_mob.set_color(color)
        if x is None:
            x = self.x_range[1]
        point = self.input_to_graph_point(x, graph)
        label_mob.next_to(point, direction, buff=buff)
        label_mob.shift_onto_screen()
        return label_mob


def make_text(content, font_size=34, color=WHITE, width=FRAME_WIDTH - 1.2, **kwargs):
    resolved_font_size = kwargs.pop("font_size", font_size)
    resolved_color = kwargs.pop("color", color)
    resolved_font = kwargs.pop("font", ACTIVE_FONT)
    clean_text = sanitize_screen_text(content)
    wrapped = "\\n".join(textwrap.wrap(clean_text, width=22, break_long_words=True, break_on_hyphens=False))
    mob = _OriginalText(wrapped, font_size=resolved_font_size, font=resolved_font, **kwargs)
    mob.set_color(resolved_color)
    if width is not None and mob.get_width() > width:
        mob.set_width(width)
    return mob


def Text(content="", font_size=34, color=WHITE, width=FRAME_WIDTH - 1.2, **kwargs):
    return make_text(content, font_size=font_size, color=color, width=width, **kwargs)


def _normalize_vector(vector, fallback=DOWN):
    arr = np.array(vector, dtype=float)
    if arr.shape == (2,):
        arr = np.array([arr[0], arr[1], 0.0])
    norm = np.linalg.norm(arr)
    if norm < 1e-8:
        arr = np.array(fallback, dtype=float)
        norm = np.linalg.norm(arr)
    return arr / (norm or 1.0)


class Brace(VGroup):
    """
    LaTeX-free brace fallback.

    manimlib.Brace internally renders ``\\underbrace{{\\qquad}}`` via LaTeX.
    In this project we prefer a pure vector fallback so generated scenes do not
    depend on a TeX environment just to draw a brace shape.
    """

    def __init__(
        self,
        mobject,
        direction=DOWN,
        buff=0.2,
        color=WHITE,
        stroke_width=4,
        sharpness=0.18,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.brace_direction = _normalize_vector(direction)

        angle = -math.atan2(*self.brace_direction[:2]) + PI
        proxy = mobject.copy()
        proxy.rotate(-angle, about_point=ORIGIN)
        left = proxy.get_corner(DL)
        right = proxy.get_corner(DR)
        target_width = max(0.4, right[0] - left[0])
        depth = max(0.14, min(0.34, target_width * sharpness))

        half = target_width / 2.0
        quarter = target_width / 4.0
        eighth = target_width / 8.0
        points = [
            np.array([-half, 0.0, 0.0]),
            np.array([-half, -depth * 0.35, 0.0]),
            np.array([-quarter * 1.1, -depth * 0.35, 0.0]),
            np.array([-eighth, -depth, 0.0]),
            np.array([0.0, -depth, 0.0]),
            np.array([eighth, -depth, 0.0]),
            np.array([quarter * 1.1, -depth * 0.35, 0.0]),
            np.array([half, -depth * 0.35, 0.0]),
            np.array([half, 0.0, 0.0]),
        ]

        body = VMobject()
        body.set_points_smoothly(points)
        body.set_stroke(color=color, width=stroke_width)
        body.set_fill(opacity=0)
        self.body = body
        self.add(body)

        self.shift(left - self.get_corner(UL) + buff * DOWN)
        self.rotate(angle, about_point=ORIGIN)

    def get_direction(self):
        return self.brace_direction

    def get_tip(self):
        points = self.get_all_points()
        if len(points) == 0:
            return self.get_center() + 0.1 * self.get_direction()
        scores = np.dot(points, self.get_direction())
        return points[int(np.argmax(scores))]

    def put_at_tip(self, mob, use_next_to=True, **kwargs):
        if use_next_to:
            mob.next_to(
                self.get_tip(),
                np.round(self.get_direction()),
                **kwargs,
            )
        else:
            mob.move_to(self.get_tip())
            buff = kwargs.get("buff", DEFAULT_MOBJECT_TO_MOBJECT_BUFF)
            shift_distance = mob.get_width() / 2.0 + buff
            mob.shift(self.get_direction() * shift_distance)
        return self

    def get_text(self, text, **kwargs):
        buff = kwargs.pop("buff", SMALL_BUFF)
        font_size = kwargs.pop("font_size", 24)
        color = kwargs.pop("color", WHITE)
        width = kwargs.pop("width", 3.0)
        text_mob = make_text(str(text), font_size=font_size, color=color, width=width)
        self.put_at_tip(text_mob, buff=buff)
        return text_mob

    def get_tex(self, *tex, **kwargs):
        return self.get_text(" ".join(str(part) for part in tex), **kwargs)


class BraceLabel(VGroup):
    def __init__(
        self,
        obj,
        text,
        brace_direction=DOWN,
        label_scale=1.0,
        label_buff=DEFAULT_MOBJECT_TO_MOBJECT_BUFF,
        **kwargs,
    ):
        super().__init__(**kwargs)
        target = VGroup(*obj) if isinstance(obj, list) else obj
        self.brace_direction = brace_direction
        self.label_scale = label_scale
        self.label_buff = label_buff
        self.brace = Brace(target, brace_direction, **kwargs)
        self.label = self.brace.get_text(text, buff=label_buff, **kwargs)
        if self.label_scale != 1:
            self.label.scale(self.label_scale)
            self.brace.put_at_tip(self.label, buff=self.label_buff)
        self.add(self.brace, self.label)

    def creation_anim(self, label_anim=FadeIn, brace_anim=GrowFromCenter):
        return AnimationGroup(brace_anim(self.brace), label_anim(self.label))

    def shift_brace(self, obj, **kwargs):
        target = VGroup(*obj) if isinstance(obj, list) else obj
        self.remove(self.brace)
        self.brace = Brace(target, self.brace_direction, **kwargs)
        self.brace.put_at_tip(self.label, buff=self.label_buff)
        self.add_to_back(self.brace)
        return self

    def change_label(self, *text, **kwargs):
        self.remove(self.label)
        self.label = self.brace.get_text(" ".join(str(part) for part in text), buff=self.label_buff, **kwargs)
        if self.label_scale != 1:
            self.label.scale(self.label_scale)
            self.brace.put_at_tip(self.label, buff=self.label_buff)
        self.add(self.label)
        return self

    def change_brace_label(self, obj, *text):
        self.shift_brace(obj)
        self.change_label(*text)
        return self


class BraceText(BraceLabel):
    pass


def make_paragraph(lines, font_size=28, color=WHITE, width=FRAME_WIDTH - 1.4, line_buff=0.18):
    if isinstance(lines, str):
        items = [line.strip() for line in lines.splitlines() if line.strip()]
    else:
        items = [str(line).strip() for line in lines if str(line).strip()]
    if not items:
        items = [" "]
    group = VGroup(*[
        make_text(item, font_size=font_size, color=color, width=width)
        for item in items
    ])
    group.arrange(DOWN, aligned_edge=LEFT, buff=line_buff)
    return group


class ArrayCell(VGroup):
    # 规范访问方式是 row[i]。这里兼容历史生成代码里常见的 row[0][i]。
    def __init__(self, *submobjects, row_ref=None, row_index=None, **kwargs):
        super().__init__(*submobjects, **kwargs)
        self.row_ref = row_ref
        self.row_index = row_index

    def __getitem__(self, value):
        if (
            isinstance(value, int)
            and self.row_ref is not None
            and self.row_index == 0
            and 0 <= value < len(self.row_ref.submobjects)
        ):
            return self.row_ref.submobjects[value]
        return super().__getitem__(value)


def make_array_row(values, highlight_indices=None, cell_width=1.2, cell_height=0.72, highlight_color=YELLOW):
    highlight_set = set(highlight_indices or [])
    cells = VGroup()
    for index, value in enumerate(values):
        stroke_color = highlight_color if index in highlight_set else GREY_B
        box = Rectangle(width=cell_width, height=cell_height, stroke_color=stroke_color)
        box.set_fill(BLACK, opacity=0.0)
        label = make_text(str(value), font_size=28, width=cell_width - 0.1)
        label.move_to(box)
        index_label = make_text(str(index), font_size=16, color=GREY_A, width=cell_width - 0.1)
        index_label.next_to(box, DOWN, buff=0.1)
        cells.add(ArrayCell(box, label, index_label, row_index=index))
    cells.arrange(RIGHT, buff=0.08)
    for index, cell in enumerate(cells):
        if isinstance(cell, ArrayCell):
            cell.row_ref = cells
            cell.row_index = index
    return cells


def make_pointer(label, target_mobject, direction=UP, color=YELLOW):
    text = make_text(label, font_size=22, color=color, width=2.2)
    text.next_to(target_mobject, direction, buff=0.35)
    arrow = Arrow(
        text.get_edge_center(-direction),
        target_mobject.get_edge_center(direction),
        buff=0.08,
        color=color,
        stroke_width=4,
    )
    return VGroup(text, arrow)
'''


def _build_manim_scene_fallback_body() -> str:
    return '''class LeetCodeSolutionScene(Scene):
    def construct(self):
        title = make_text(VIDEO_TITLE, font_size=42, color=YELLOW)
        title.to_edge(UP)
        subtitle = make_text("LLM Manim 代码不可用，当前为兜底动画骨架", font_size=24, color=GREY_B)
        subtitle.next_to(title, DOWN, buff=0.25)
        self.play(FadeIn(title, shift=DOWN), FadeIn(subtitle, shift=DOWN))
        self.wait(1.2)
        self.play(FadeOut(subtitle))

        current_group = VGroup(title)
        for index, segment in enumerate(TIMELINE["segments"], start=1):
            seg_title = make_text(f"{{segment['id']}}  {{segment['title']}}", font_size=38, color=YELLOW)
            seg_title.to_edge(UP)

            objective = make_text(segment.get("objective", ""), font_size=28)
            objective.next_to(seg_title, DOWN, buff=0.5)

            cards = VGroup()
            for card_index, raw in enumerate(segment.get("animation_beats", [])[:3], start=1):
                short = str(raw).replace("展示", "").replace("显示", "").replace("画面", "").strip()
                short = short.split("，")[0].split("：")[-1].strip()
                if len(short) > 10:
                    short = short[:10] + "…"
                label = make_text(short or f"步骤 {{card_index}}", font_size=22, width=2.2)
                box = RoundedRectangle(corner_radius=0.12, width=2.5, height=1.2, stroke_color=BLUE_B)
                label.move_to(box)
                cards.add(VGroup(box, label))
            if len(cards) == 0:
                placeholder = RoundedRectangle(corner_radius=0.12, width=3.0, height=1.2, stroke_color=BLUE_B)
                cards = VGroup(VGroup(placeholder, make_text("动画占位", font_size=22).move_to(placeholder)))
            cards.arrange(RIGHT, buff=0.25)
            cards.next_to(objective, DOWN, buff=0.65)

            timer = make_text(
                f"{{segment.get('start_sec', 0):.1f}}s -> {{segment.get('end_sec', 0):.1f}}s",
                font_size=22,
                color=GREY_A,
            )
            timer.next_to(cards, DOWN, buff=0.45)

            progress = make_text(f"片段 {{index}} / {{len(TIMELINE['segments'])}}", font_size=22, color=BLUE_B)
            progress.to_corner(UR)

            new_group = VGroup(seg_title, objective, cards, timer, progress)
            self.play(FadeOut(current_group, shift=UP), FadeIn(new_group, shift=UP))
            stay = max(0.8, float(segment.get("end_sec", 0.0)) - float(segment.get("start_sec", 0.0)) - 0.8)
            self.wait(stay)
            current_group = new_group

        ending = make_text("题解结束，可继续接入更细粒度算法动画模板", font_size=30, color=GREEN)
        ending.shift(DOWN * 0.8)
        self.play(FadeIn(ending, shift=UP))
        self.wait(1.5)
'''


def build_manim_scene_code(problem: ProblemArtifact, timeline: TimelineArtifact, scene_body: str | None = None) -> str:
    body = (scene_body or _build_manim_scene_fallback_body()).strip()
    return _build_manim_scene_preamble(problem, timeline) + "\n" + body + "\n"


def build_render_manim_script() -> str:
    return '''#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import shlex
import subprocess
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


RUN_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = RUN_DIR.parents[1]
SCENE_FILE = RUN_DIR / "04_codegen" / "manim_scene.py"
SCENE_CLASS = "LeetCodeSolutionScene"
OUTPUT_VIDEO = RUN_DIR / "05_outputs" / "video" / "raw_visual.mp4"
TEMP_VIDEO_EXIT_CODES = {-1}


def iter_commands() -> list[list[str]]:
    commands: list[list[str]] = []
    explicit = os.getenv("MANIM_CMD", "").strip()
    if explicit:
        commands.append(shlex.split(explicit, posix=os.name != "nt"))

    for python_path in (
        PROJECT_ROOT / ".venv" / "Scripts" / "python.exe",
        PROJECT_ROOT / ".venv" / "bin" / "python",
    ):
        if python_path.exists():
            commands.append([str(python_path), "-m", "manimlib"])

    commands.append([sys.executable, "-m", "manimlib"])

    for script_path in (
        PROJECT_ROOT / ".venv" / "Scripts" / "manim-render.exe",
        PROJECT_ROOT / ".venv" / "Scripts" / "manimgl.exe",
        PROJECT_ROOT / ".venv" / "bin" / "manim-render",
        PROJECT_ROOT / ".venv" / "bin" / "manimgl",
    ):
        if script_path.exists():
            commands.append([str(script_path)])

    commands.extend([["manim-render"], ["manimgl"]])
    return commands


def normalize_returncode(returncode: int | None) -> int | None:
    if returncode is None:
        return None

    normalized = int(returncode)
    if normalized > 0x7FFFFFFF:
        normalized -= 0x100000000
    return normalized


def candidate_video_patterns(*, allow_temp: bool = True) -> list[str]:
    patterns = [f"{SCENE_CLASS}.mp4"]
    if allow_temp:
        patterns.append(f"{SCENE_CLASS}_temp.mp4")
    return patterns


def find_rendered_video(*, since_time: float | None = None, allow_temp: bool = True) -> Path | None:
    matches: dict[str, Path] = {}
    for pattern in candidate_video_patterns(allow_temp=allow_temp):
        direct = RUN_DIR / "videos" / pattern
        if direct.exists():
            matches[str(direct.resolve())] = direct
        for path in RUN_DIR.rglob(pattern):
            if path.exists():
                matches[str(path.resolve())] = path

    candidates = list(matches.values())
    if since_time is not None:
        candidates = [path for path in candidates if path.stat().st_mtime >= since_time - 1.0]
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def is_temp_video(path: Path | None) -> bool:
    return path is not None and path.stem.endswith("_temp")


def recover_from_temp_video(exc: subprocess.CalledProcessError, *, started_at: float) -> Path | None:
    rendered_video = find_rendered_video(since_time=started_at, allow_temp=True)
    normalized = normalize_returncode(exc.returncode)
    if rendered_video is None or normalized not in TEMP_VIDEO_EXIT_CODES:
        return None

    print()
    print(f"[manim] 进程以 {exc.returncode} 退出，但检测到候选输出：{rendered_video}")
    if is_temp_video(rendered_video):
        print("[manim] 这通常是 Windows 上 ManimGL 在最终重命名阶段失败，继续使用临时视频。")
    return rendered_video


def persist_rendered_video(source: Path) -> Path:
    OUTPUT_VIDEO.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != OUTPUT_VIDEO.resolve():
        shutil.copy2(source, OUTPUT_VIDEO)
    return OUTPUT_VIDEO


def main() -> None:
    if load_dotenv is not None:
        load_dotenv(PROJECT_ROOT / ".env", override=False)

    last_error: subprocess.CalledProcessError | None = None
    for command in iter_commands():
        started_at = time.time()
        try:
            print(f"[manim] 使用命令: {' '.join(shlex.quote(part) for part in command)}")
            subprocess.run(
                command + [str(SCENE_FILE), SCENE_CLASS, "-w"],
                cwd=RUN_DIR,
                check=True,
            )
            rendered_video = find_rendered_video(since_time=started_at, allow_temp=True)
            print()
            if rendered_video is not None:
                archived_video = persist_rendered_video(rendered_video)
                if is_temp_video(rendered_video):
                    print(f"Manim 渲染完成，但只找到临时视频：{rendered_video}")
                else:
                    print(f"Manim 渲染完成：{rendered_video}")
                print(f"已归档到：{archived_video}")
            else:
                print("Manim 渲染完成，但未自动定位到输出 mp4。")
                print(f"请检查并手动移动到：{OUTPUT_VIDEO}")
            return
        except FileNotFoundError:
            continue
        except subprocess.CalledProcessError as exc:
            recovered_video = recover_from_temp_video(exc, started_at=started_at)
            if recovered_video is not None:
                archived_video = persist_rendered_video(recovered_video)
                print(f"已归档到：{archived_video}")
                return
            last_error = exc
            break

    if last_error is not None:
        normalized = normalize_returncode(last_error.returncode)
        print(f"[manim] 渲染失败，退出码={last_error.returncode}", file=sys.stderr)
        if normalized != last_error.returncode:
            print(f"[manim] 标准化退出码={normalized}", file=sys.stderr)
        candidate = find_rendered_video(allow_temp=True)
        if candidate is not None:
            print(f"[manim] 检测到候选输出文件：{candidate}", file=sys.stderr)
        raise SystemExit(last_error.returncode)

    raise SystemExit("未找到可用的 Manim 命令。可通过 MANIM_CMD 指定，例如 MANIM_CMD='python -m manimlib'。")


if __name__ == "__main__":
    main()
'''


def build_render_tts_script(segments: Iterable[TimelineSegment]) -> str:
    segments_json = json.dumps(
        [{"id": segment.id, "title": segment.title} for segment in segments],
        ensure_ascii=False,
        indent=2,
    )
    template = '''#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

try:
    import edge_tts
    from edge_tts import SubMaker
except ImportError as exc:
    raise SystemExit("未安装 edge-tts。请先安装项目依赖。") from exc


RUN_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = RUN_DIR.parents[1]
AUDIO_DIR = RUN_DIR / "05_outputs" / "audio"
TEXT_DIR = AUDIO_DIR / "text"
CONFIG_PATH = RUN_DIR / "04_codegen" / "tts_config.json"
SEGMENTS = json.loads(r"""__SEGMENTS_JSON__""")
DEFAULT_CONFIG = {
    "voice": "zh-CN-XiaoxiaoNeural",
    "rate": "+0%",
    "volume": "+0%",
    "pitch": "+0Hz",
}


def load_config() -> dict[str, str]:
    config = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            for key in DEFAULT_CONFIG:
                value = payload.get(key)
                if value not in (None, ""):
                    config[key] = str(value)

    env_overrides = {
        "voice": os.getenv("LEETANIM_VOICE", "").strip(),
        "rate": os.getenv("LEETANIM_RATE", "").strip(),
        "volume": os.getenv("LEETANIM_VOLUME", "").strip(),
        "pitch": os.getenv("LEETANIM_PITCH", "").strip(),
    }
    for key, value in env_overrides.items():
        if value:
            config[key] = value
    return config


async def render_segment(segment: dict[str, str], config: dict[str, str]) -> None:
    text_path = TEXT_DIR / f"{segment['id']}.txt"
    if not text_path.exists():
        raise FileNotFoundError(f"未找到配音文本：{text_path}")

    text = text_path.read_text(encoding="utf-8").strip()
    if not text:
        raise RuntimeError(f"配音文本为空：{text_path}")

    audio_path = AUDIO_DIR / f"{segment['id']}.mp3"
    subtitle_path = AUDIO_DIR / f"{segment['id']}.srt"
    segment_label = f"{segment['id']} {segment['title']}"
    communicate = edge_tts.Communicate(
        text=text,
        voice=config["voice"],
        rate=config["rate"],
        volume=config["volume"],
        pitch=config["pitch"],
        boundary="SentenceBoundary",
    )
    submaker = SubMaker()

    try:
        with audio_path.open("wb") as audio_file:
            async for chunk in communicate.stream():
                chunk_type = chunk["type"]
                if chunk_type == "audio":
                    audio_file.write(chunk["data"])
                elif chunk_type in {"WordBoundary", "SentenceBoundary"}:
                    submaker.feed(chunk)
    except Exception as exc:
        if audio_path.exists():
            audio_path.unlink()
        if subtitle_path.exists():
            subtitle_path.unlink()
        if exc.__class__.__name__ == "NoAudioReceived":
            preview = text[:120].replace("\\n", " ")
            raise RuntimeError(
                f"edge-tts 未返回音频：{segment_label}。请检查配音文本或语音参数。文本预览：{preview}"
            ) from exc
        raise

    subtitle_path.write_text(submaker.get_srt(), encoding="utf-8", newline="\\n")


async def render_all() -> None:
    config = load_config()
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    TEXT_DIR.mkdir(parents=True, exist_ok=True)

    for segment in SEGMENTS:
        print(f"[edge-tts] {segment['id']} {segment['title']}")
        await render_segment(segment, config)


def main() -> None:
    if load_dotenv is not None:
        load_dotenv(PROJECT_ROOT / ".env", override=False)

    asyncio.run(render_all())
    print("配音生成完成。")
    print(f"下一步建议执行：python main.py sync --run-dir {RUN_DIR}")


if __name__ == "__main__":
    main()
'''
    return template.replace("__SEGMENTS_JSON__", segments_json)


def build_compose_script() -> str:
    return '''#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


RUN_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = RUN_DIR.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from leetanim.subtitles import (
    build_ffmpeg_subtitles_filter,
    load_segment_duration_lookup,
    merge_srt_files,
)


FINAL_DIR = RUN_DIR / "06_final"
AUDIO_DIR = RUN_DIR / "05_outputs" / "audio"
TIMELINE_PATH = RUN_DIR / "03_timeline" / "timeline.json"
DEFAULT_VIDEO_INPUT = RUN_DIR / "05_outputs" / "video" / "raw_visual.mp4"
AUDIO_LIST = FINAL_DIR / "audio_concat.txt"
FULL_AUDIO = FINAL_DIR / "full_audio.mp3"
FINAL_SUBTITLES = FINAL_DIR / "final_subtitles.srt"
FINAL_VIDEO = FINAL_DIR / "final_video.mp4"


def resolve_ffmpeg() -> str | None:
    explicit = os.getenv("LEETANIM_FFMPEG_BIN", "").strip() or os.getenv("FFMPEG_BIN", "").strip()
    if explicit:
        return explicit

    for candidate in (
        PROJECT_ROOT / ".venv" / "Scripts" / "ffmpeg.exe",
        PROJECT_ROOT / ".venv" / "bin" / "ffmpeg",
    ):
        if candidate.exists():
            return str(candidate)

    return shutil.which("ffmpeg")


def resolve_ffprobe(ffmpeg: str | None) -> str | None:
    explicit = os.getenv("LEETANIM_FFPROBE_BIN", "").strip() or os.getenv("FFPROBE_BIN", "").strip()
    if explicit:
        return explicit

    if ffmpeg:
        ffmpeg_path = Path(ffmpeg)
        sibling = ffmpeg_path.with_name("ffprobe.exe" if ffmpeg_path.suffix.lower() == ".exe" else "ffprobe")
        if sibling.exists():
            return str(sibling)

    for candidate in (
        PROJECT_ROOT / ".venv" / "Scripts" / "ffprobe.exe",
        PROJECT_ROOT / ".venv" / "bin" / "ffprobe",
    ):
        if candidate.exists():
            return str(candidate)

    return shutil.which("ffprobe")


def concat_line(path: Path) -> str:
    escaped = path.resolve().as_posix().replace("'", "'\\\\''")
    return f"file '{escaped}'\\n"


def resolve_subtitle_files(audio_files: list[Path]) -> list[Path]:
    available = {path.stem: path for path in AUDIO_DIR.glob("*.srt")}
    if not available:
        return []

    missing = [audio_path.stem for audio_path in audio_files if audio_path.stem not in available]
    if missing:
        joined = ", ".join(missing)
        raise SystemExit(f"检测到部分字幕缺失，请补齐这些 segment 的 .srt 文件：{joined}")

    return [available[audio_path.stem] for audio_path in audio_files]


def probe_audio_duration(ffprobe: str | None, path: Path) -> float | None:
    if not ffprobe:
        return None

    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except Exception:
        return None


def build_duration_lookup(audio_files: list[Path], ffprobe: str | None) -> dict[str, float]:
    lookup = load_segment_duration_lookup(TIMELINE_PATH)
    for audio_path in audio_files:
        duration = probe_audio_duration(ffprobe, audio_path)
        if duration is not None:
            lookup[audio_path.stem] = duration
    return lookup


def main() -> None:
    if load_dotenv is not None:
        load_dotenv(PROJECT_ROOT / ".env", override=False)

    ffmpeg = resolve_ffmpeg()
    if not ffmpeg:
        raise SystemExit("未找到 ffmpeg，请先安装 ffmpeg，或通过 LEETANIM_FFMPEG_BIN / FFMPEG_BIN 指定路径。")
    ffprobe = resolve_ffprobe(ffmpeg)

    video_input = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else DEFAULT_VIDEO_INPUT
    if not video_input.exists():
        raise SystemExit(f"未找到视觉视频：{video_input}")

    audio_files = sorted(AUDIO_DIR.glob("*.mp3"))
    if not audio_files:
        raise SystemExit("未找到任何 mp3，请先运行 04_codegen/render_tts.py")
    subtitle_files = resolve_subtitle_files(audio_files)

    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_LIST.write_text("".join(concat_line(path) for path in audio_files), encoding="utf-8", newline="\\n")
    if subtitle_files:
        duration_lookup = build_duration_lookup(audio_files, ffprobe)
        FINAL_SUBTITLES.write_text(
            merge_srt_files(subtitle_files, duration_lookup=duration_lookup),
            encoding="utf-8",
            newline="\\n",
        )
    elif FINAL_SUBTITLES.exists():
        FINAL_SUBTITLES.unlink()

    subprocess.run(
        [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(AUDIO_LIST), "-c", "copy", str(FULL_AUDIO)],
        check=True,
    )
    video_command = [
        ffmpeg,
        "-y",
        "-i",
        str(video_input),
        "-i",
        str(FULL_AUDIO),
    ]
    if subtitle_files:
        video_command.extend(
            [
                "-vf",
                build_ffmpeg_subtitles_filter(FINAL_SUBTITLES),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
            ]
        )
    else:
        video_command.extend(["-c:v", "copy"])
    video_command.extend(["-c:a", "aac", "-shortest", "-movflags", "+faststart", str(FINAL_VIDEO)])
    subprocess.run(video_command, check=True)

    if subtitle_files:
        print(f"字幕已合并并烧录：{FINAL_SUBTITLES}")
    else:
        print("未找到 .srt 字幕文件，本次仅合成音频与视觉视频。")
    print(f"最终视频已生成：{FINAL_VIDEO}")


if __name__ == "__main__":
    main()
'''
