from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_json(path: Path, data: dict[str, Any] | list[Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def now_compact() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def slugify(text: str, fallback: str = "run") -> str:
    normalized = text.lower().strip()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    normalized = normalized.strip("-")
    return normalized or fallback


def strip_markdown(text: str) -> str:
    cleaned = text
    cleaned = re.sub(r"```.*?```", " ", cleaned, flags=re.S)
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    cleaned = re.sub(r"^#{1,6}\s+", "", cleaned, flags=re.M)
    cleaned = re.sub(r"^[\-*+]\s+", "", cleaned, flags=re.M)
    cleaned = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", cleaned)
    cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"__(.*?)__", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def first_heading(markdown_text: str) -> str | None:
    for line in markdown_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
        return stripped
    return None


def estimate_speech_duration_sec(text: str, chars_per_second: float = 4.2, base_pause_sec: float = 1.0) -> float:
    payload = re.sub(r"\s+", "", text)
    effective_chars = max(1, len(payload))
    return round(base_pause_sec + effective_chars / chars_per_second, 1)


def seconds_to_timestamp(seconds: float) -> str:
    total_ms = int(round(seconds * 1000))
    total_sec, ms = divmod(total_ms, 1000)
    minute, sec = divmod(total_sec, 60)
    hour, minute = divmod(minute, 60)
    if hour:
        return f"{hour:02d}:{minute:02d}:{sec:02d}.{ms:03d}"
    return f"{minute:02d}:{sec:02d}.{ms:03d}"


_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", re.S | re.I)


def extract_json_block(text: str) -> str:
    match = _FENCED_JSON_RE.search(text)
    if match:
        return match.group(1).strip()

    start_obj = text.find("{")
    end_obj = text.rfind("}")
    if start_obj != -1 and end_obj != -1 and end_obj > start_obj:
        return text[start_obj : end_obj + 1].strip()

    start_arr = text.find("[")
    end_arr = text.rfind("]")
    if start_arr != -1 and end_arr != -1 and end_arr > start_arr:
        return text[start_arr : end_arr + 1].strip()

    raise ValueError("No JSON block found in model response")


def clamp_text(text: str, max_len: int) -> str:
    compact = strip_markdown(text)
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 1].rstrip() + "…"
