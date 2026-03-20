from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping


_TIMESTAMP_RE = re.compile(r"^(?P<start>\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(?P<end>\d{2}:\d{2}:\d{2},\d{3})(?:\s+.*)?$")


@dataclass(frozen=True)
class SubtitleCue:
    start_ms: int
    end_ms: int
    text: str


def parse_srt_timestamp(value: str) -> int:
    hours, minutes, seconds_ms = value.split(":", maxsplit=2)
    seconds, millis = seconds_ms.split(",", maxsplit=1)
    total_ms = (
        int(hours) * 3_600_000
        + int(minutes) * 60_000
        + int(seconds) * 1_000
        + int(millis)
    )
    return total_ms


def format_srt_timestamp(total_ms: int) -> str:
    total_ms = max(0, int(total_ms))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def parse_srt(text: str) -> list[SubtitleCue]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff").strip()
    if not normalized:
        return []

    cues: list[SubtitleCue] = []
    for block in re.split(r"\n\s*\n", normalized):
        lines = [line.rstrip() for line in block.split("\n") if line.strip()]
        if len(lines) < 2:
            continue

        timestamp_line_index = 1 if lines[0].isdigit() else 0
        if len(lines) <= timestamp_line_index:
            continue

        match = _TIMESTAMP_RE.match(lines[timestamp_line_index])
        if match is None:
            raise ValueError(f"无效的 SRT 时间轴行：{lines[timestamp_line_index]!r}")

        start_ms = parse_srt_timestamp(match.group("start"))
        end_ms = parse_srt_timestamp(match.group("end"))
        text_lines = lines[timestamp_line_index + 1 :]
        if not text_lines:
            continue
        cues.append(SubtitleCue(start_ms=start_ms, end_ms=end_ms, text="\n".join(text_lines)))

    return cues


def render_srt(cues: Iterable[SubtitleCue]) -> str:
    blocks: list[str] = []
    for index, cue in enumerate(cues, start=1):
        blocks.append(
            "\n".join(
                [
                    str(index),
                    f"{format_srt_timestamp(cue.start_ms)} --> {format_srt_timestamp(cue.end_ms)}",
                    cue.text,
                ]
            )
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def merge_srt_payloads(
    payloads: Iterable[tuple[str, str]],
    *,
    duration_lookup: Mapping[str, float] | None = None,
) -> str:
    merged: list[SubtitleCue] = []
    offset_ms = 0
    lookup = duration_lookup or {}

    for segment_id, srt_text in payloads:
        cues = parse_srt(srt_text)
        merged.extend(
            SubtitleCue(
                start_ms=cue.start_ms + offset_ms,
                end_ms=cue.end_ms + offset_ms,
                text=cue.text,
            )
            for cue in cues
        )

        duration_sec = lookup.get(segment_id)
        if duration_sec is None:
            duration_sec = max((cue.end_ms for cue in cues), default=0) / 1000.0
        offset_ms += max(0, int(round(float(duration_sec) * 1000)))

    return render_srt(merged)


def merge_srt_files(
    paths: Iterable[Path],
    *,
    duration_lookup: Mapping[str, float] | None = None,
) -> str:
    payloads: list[tuple[str, str]] = []
    for path in paths:
        try:
            payloads.append((path.stem, path.read_text(encoding="utf-8")))
        except Exception as exc:
            raise RuntimeError(f"读取字幕文件失败：{path}") from exc
    return merge_srt_payloads(payloads, duration_lookup=duration_lookup)


def load_segment_duration_lookup(timeline_path: Path) -> dict[str, float]:
    if not timeline_path.exists():
        return {}

    try:
        payload = json.loads(timeline_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    lookup: dict[str, float] = {}
    for segment in payload.get("segments", []):
        if not isinstance(segment, dict):
            continue

        segment_id = str(segment.get("id", "")).strip()
        if not segment_id:
            continue

        value = segment.get("actual_audio_duration_sec")
        if value in (None, ""):
            try:
                value = float(segment.get("end_sec", 0.0) or 0.0) - float(segment.get("start_sec", 0.0) or 0.0)
            except Exception:
                value = None

        try:
            duration = round(max(0.0, float(value)), 3)
        except (TypeError, ValueError):
            continue
        lookup[segment_id] = duration

    return lookup


def build_ffmpeg_subtitles_filter(path: Path) -> str:
    escaped = str(path.resolve()).replace("\\", "/")
    escaped = escaped.replace(":", r"\:")
    escaped = escaped.replace("'", r"\'")
    escaped = escaped.replace("[", r"\[")
    escaped = escaped.replace("]", r"\]")
    style = "Alignment=2,MarginV=28,Outline=1,Shadow=0,BorderStyle=1"
    return f"subtitles='{escaped}':force_style='{style}'"
