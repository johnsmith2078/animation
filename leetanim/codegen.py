from __future__ import annotations

import json
from typing import Iterable

from .models import ProblemArtifact, TimelineArtifact, TimelineSegment
from .utils import clamp_text, estimate_speech_duration_sec, seconds_to_timestamp, strip_markdown


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


def build_fallback_timeline(
    problem: ProblemArtifact,
    solution_text: str,
    target_duration_sec: float,
    source_quality: str,
) -> TimelineArtifact:
    sections = _markdown_sections(solution_text)
    segment_defs: list[tuple[str, str, str, list[str]]] = []

    if sections:
        for title, body in sections[:6]:
            clean_body = clamp_text(body, 180)
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
        narration = strip_markdown(str(item.get("narration", ""))).strip()
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
        lines.append(
            f"## {segment.id} [{seconds_to_timestamp(segment.start_sec)} - {seconds_to_timestamp(segment.end_sec)}] {segment.title}"
        )
        lines.append("")
        lines.append(segment.narration.strip())
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


def build_manim_scene_code(problem: ProblemArtifact, timeline: TimelineArtifact) -> str:
    timeline_json = json.dumps(timeline.to_dict(), ensure_ascii=False, indent=2)
    problem_title = f"{problem.problem_id}. {problem.title}"
    return f'''from manimlib import *
import json
import textwrap

# 如果中文字体显示异常，可把 DEFAULT_FONT 改成你本机可用字体，例如：
# DEFAULT_FONT = "Microsoft YaHei"
# DEFAULT_FONT = "PingFang SC"
DEFAULT_FONT = None

TIMELINE = json.loads(r"""{timeline_json}""")
VIDEO_TITLE = {problem_title!r}


def make_text(content, font_size=34, color=WHITE, width=FRAME_WIDTH - 1.2):
    kwargs = {{"font_size": font_size}}
    if DEFAULT_FONT:
        kwargs["font"] = DEFAULT_FONT
    wrapped = "\\n".join(textwrap.wrap(str(content), width=22, break_long_words=True, break_on_hyphens=False))
    mob = Text(wrapped, **kwargs)
    mob.set_color(color)
    if mob.get_width() > width:
        mob.set_width(width)
    return mob


class LeetCodeSolutionScene(Scene):
    def construct(self):
        title = make_text(VIDEO_TITLE, font_size=42)
        title.to_edge(UP)
        subtitle = make_text("自动生成的题解动画骨架", font_size=26, color=GREY_B)
        subtitle.next_to(title, DOWN, buff=0.25)
        self.play(FadeIn(title, shift=DOWN), FadeIn(subtitle, shift=DOWN))
        self.wait(1.2)
        self.play(FadeOut(subtitle))

        current_group = VGroup(title)
        for index, segment in enumerate(TIMELINE["segments"], start=1):
            seg_title = make_text(f"{{segment['id']}}  {{segment['title']}}", font_size=38, color=YELLOW)
            seg_title.to_edge(UP)

            objective = make_text(segment.get("objective", ""), font_size=30)
            objective.next_to(seg_title, DOWN, buff=0.5)

            beat_lines = [f"- {{item}}" for item in segment.get("animation_beats", [])]
            beats = make_text("\\n".join(beat_lines) if beat_lines else "- 与配音同步停留", font_size=26, color=GREY_B)
            beats.next_to(objective, DOWN, buff=0.5)

            timer = make_text(
                f"{{segment.get('start_sec', 0):.1f}}s -> {{segment.get('end_sec', 0):.1f}}s",
                font_size=22,
                color=GREY_A,
            )
            timer.to_edge(DOWN)

            progress = make_text(f"片段 {{index}} / {{len(TIMELINE['segments'])}}", font_size=22, color=BLUE_B)
            progress.to_corner(DR)

            new_group = VGroup(seg_title, objective, beats, timer, progress)
            self.play(FadeOut(current_group, shift=UP), FadeIn(new_group, shift=UP))
            stay = max(0.8, float(segment.get("end_sec", 0.0)) - float(segment.get("start_sec", 0.0)) - 0.8)
            self.wait(stay)
            current_group = new_group

        ending = make_text("题解结束，可继续接入更细粒度算法动画模板", font_size=30, color=GREEN)
        ending.to_edge(DOWN)
        self.play(FadeIn(ending, shift=UP))
        self.wait(1.5)
'''


def build_render_manim_script() -> str:
    return '''#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MANIM_CMD="${MANIM_CMD:-manim-render}"
SCENE_FILE="04_codegen/manim_scene.py"
SCENE_CLASS="LeetCodeSolutionScene"

"$MANIM_CMD" "$SCENE_FILE" "$SCENE_CLASS" -w

echo
echo "Manim 渲染完成。请根据你的 manimgl 配置确认输出 mp4 路径。"
echo "建议将视觉视频移动到：$ROOT/05_outputs/video/raw_visual.mp4"
'''


def build_render_tts_script(segments: Iterable[TimelineSegment]) -> str:
    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "",
        'ROOT="$(cd "$(dirname "$0")/.." && pwd)"',
        'AUDIO_DIR="$ROOT/05_outputs/audio"',
        'TEXT_DIR="$AUDIO_DIR/text"',
        'VOICE="${LEETANIM_VOICE:-zh-CN-XiaoxiaoNeural}"',
        'RATE="${LEETANIM_RATE:-+0%}"',
        'VOLUME="${LEETANIM_VOLUME:-+0%}"',
        'PITCH="${LEETANIM_PITCH:-+0Hz}"',
        'mkdir -p "$AUDIO_DIR" "$TEXT_DIR"',
        "",
    ]
    for segment in segments:
        lines.extend(
            [
                f'echo "[edge-tts] {segment.id} {segment.title}"',
                (
                    f'edge-tts --voice "$VOICE" --rate "$RATE" --volume "$VOLUME" --pitch "$PITCH" '
                    f'--text "$(cat \"$TEXT_DIR/{segment.id}.txt\")" '
                    f'--write-media "$AUDIO_DIR/{segment.id}.mp3" '
                    f'--write-subtitles "$AUDIO_DIR/{segment.id}.srt"'
                ),
                "",
            ]
        )
    lines.extend(
        [
            'echo "配音生成完成。"',
            'echo "下一步建议执行：python3 main.py sync --run-dir $ROOT"',
        ]
    )
    return "\n".join(lines) + "\n"


def build_compose_script() -> str:
    return '''#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FINAL_DIR="$ROOT/06_final"
AUDIO_DIR="$ROOT/05_outputs/audio"
VIDEO_INPUT="${1:-$ROOT/05_outputs/video/raw_visual.mp4}"
AUDIO_LIST="$FINAL_DIR/audio_concat.txt"
FULL_AUDIO="$FINAL_DIR/full_audio.mp3"
FINAL_VIDEO="$FINAL_DIR/final_video.mp4"

mkdir -p "$FINAL_DIR"

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "未找到 ffmpeg，请先安装 ffmpeg" >&2
  exit 1
fi

shopt -s nullglob
files=("$AUDIO_DIR"/*.mp3)
if [ ${#files[@]} -eq 0 ]; then
  echo "未找到任何 mp3，请先运行 04_codegen/render_tts.sh" >&2
  exit 1
fi

: > "$AUDIO_LIST"
for f in "${files[@]}"; do
  printf "file '%s'\n" "$f" >> "$AUDIO_LIST"
done

ffmpeg -y -f concat -safe 0 -i "$AUDIO_LIST" -c copy "$FULL_AUDIO"
ffmpeg -y -i "$VIDEO_INPUT" -i "$FULL_AUDIO" -c:v copy -c:a aac -shortest "$FINAL_VIDEO"

echo "最终视频已生成：$FINAL_VIDEO"
'''
