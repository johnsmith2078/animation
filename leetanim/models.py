from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ProblemArtifact:
    problem_id: str
    title: str
    slug: str
    source: str
    language: str
    statement_markdown: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProblemArtifact":
        return cls(
            problem_id=str(data.get("problem_id", "")),
            title=str(data.get("title", "")),
            slug=str(data.get("slug", "")),
            source=str(data.get("source", "manual")),
            language=str(data.get("language", "zh-CN")),
            statement_markdown=str(data.get("statement_markdown", "")),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class TimelineSegment:
    id: str
    title: str
    objective: str
    narration: str
    animation_beats: list[str]
    estimated_duration_sec: float
    start_sec: float = 0.0
    end_sec: float = 0.0
    actual_audio_duration_sec: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TimelineSegment":
        beats = data.get("animation_beats", [])
        if not isinstance(beats, list):
            beats = [str(beats)]
        return cls(
            id=str(data.get("id", "")),
            title=str(data.get("title", "")),
            objective=str(data.get("objective", "")),
            narration=str(data.get("narration", "")),
            animation_beats=[str(item) for item in beats],
            estimated_duration_sec=float(data.get("estimated_duration_sec", 0.0) or 0.0),
            start_sec=float(data.get("start_sec", 0.0) or 0.0),
            end_sec=float(data.get("end_sec", 0.0) or 0.0),
            actual_audio_duration_sec=(
                None
                if data.get("actual_audio_duration_sec") in (None, "")
                else float(data.get("actual_audio_duration_sec"))
            ),
        )


@dataclass
class TimelineArtifact:
    video_title: str
    problem_id: str
    problem_title: str
    language: str
    target_duration_sec: float
    segments: list[TimelineSegment]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "video_title": self.video_title,
            "problem_id": self.problem_id,
            "problem_title": self.problem_title,
            "language": self.language,
            "target_duration_sec": self.target_duration_sec,
            "segments": [segment.to_dict() for segment in self.segments],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TimelineArtifact":
        segments = [TimelineSegment.from_dict(item) for item in data.get("segments", [])]
        return cls(
            video_title=str(data.get("video_title", "")),
            problem_id=str(data.get("problem_id", "")),
            problem_title=str(data.get("problem_title", "")),
            language=str(data.get("language", "zh-CN")),
            target_duration_sec=float(data.get("target_duration_sec", 0.0) or 0.0),
            segments=segments,
            metadata=dict(data.get("metadata", {})),
        )
