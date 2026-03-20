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
    path.write_text(text, encoding="utf-8", newline="\n")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_json(path: Path, data: dict[str, Any] | list[Any]) -> None:
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


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


_TABLE_DIVIDER_RE = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$")
_HORIZONTAL_RULE_RE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_SPEECH_CONTENT_RE = re.compile(r"[0-9A-Za-z\u4e00-\u9fff]")
_TERMINAL_PUNCTUATION = "。！？!?；;."


def _strip_inline_markdown(text: str) -> str:
    cleaned = text
    cleaned = re.sub(r"```[a-zA-Z0-9_+-]*", "", cleaned)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"!\[(.*?)\]\((.*?)\)", r"\1", cleaned)
    cleaned = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", cleaned)
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"__(.*?)__", r"\1", cleaned)
    cleaned = re.sub(r"~~(.*?)~~", r"\1", cleaned)
    cleaned = cleaned.replace("\\|", "|")
    cleaned = re.sub(r"值\s*→\s*下标", "值到下标", cleaned)
    cleaned = cleaned.replace("→", "，")
    cleaned = cleaned.replace("=>", "，")
    cleaned = cleaned.replace("->", "，")
    cleaned = cleaned.replace("✅", " ")
    cleaned = cleaned.replace("✔", " ")
    cleaned = cleaned.replace("❌", " ")
    cleaned = re.sub(r"\s*，\s*", "，", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", cleaned)
    return cleaned.strip()


def _split_table_row(line: str) -> list[str]:
    payload = line.strip().strip("|")
    if not payload:
        return []
    return [_strip_inline_markdown(cell) for cell in payload.split("|")]


def _table_to_text_units(lines: list[str]) -> list[str]:
    rows = [_split_table_row(line) for line in lines if line.strip() and not _TABLE_DIVIDER_RE.match(line)]
    rows = [row for row in rows if any(cell for cell in row)]
    if not rows:
        return []
    if len(rows) == 1:
        return [part for part in rows[0] if part]

    headers = rows[0]
    units: list[str] = []
    for row in rows[1:]:
        fragments: list[str] = []
        for index, value in enumerate(row):
            value = value.strip()
            if not value:
                continue
            header = headers[index].strip() if index < len(headers) else ""
            if header in {"步骤", "Step", "step"}:
                fragments.append(f"{value} 时")
            elif header in {"当前数", "当前值"}:
                fragments.append(f"{header} {value}")
            elif header in {"需要的另一半", "补数"}:
                fragments.append(f"补数 {value}")
            elif "哈希表" in header:
                fragments.append(value)
            elif header in {"结果", "Result", "result"}:
                fragments.append(f"结果 {value}")
            elif header:
                fragments.append(f"{header} {value}")
            else:
                fragments.append(value)
        if fragments:
            units.append("，".join(fragments))
    return units


def _split_plain_sentences(text: str) -> list[str]:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return []
    parts = re.split(r"(?<=[。！？!?；;])\s+", compact)
    return [part.strip() for part in parts if part.strip()]


def markdown_to_text_units(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n")
    normalized = re.sub(r"```.*?```", "\n", normalized, flags=re.S)
    normalized = re.sub(r"<!--.*?-->", "\n", normalized, flags=re.S)

    units: list[str] = []
    paragraph_lines: list[str] = []
    table_lines: list[str] = []
    pending_table_lead_in = ""

    def flush_paragraph(for_table: bool = False) -> None:
        nonlocal pending_table_lead_in
        if not paragraph_lines:
            return
        paragraph = " ".join(part for part in paragraph_lines if part).strip()
        paragraph_lines.clear()
        sentences = _split_plain_sentences(paragraph)
        if for_table and len(sentences) == 1 and any(marker in sentences[0] for marker in ("为例", "如下", "见下表")):
            pending_table_lead_in = sentences[0]
            return
        units.extend(sentences)

    def flush_table() -> None:
        nonlocal pending_table_lead_in
        if not table_lines:
            return
        table_units = _table_to_text_units(table_lines)
        if pending_table_lead_in and table_units and len(pending_table_lead_in) <= 16:
            table_units[0] = f"{pending_table_lead_in.rstrip('：:，,')}，{table_units[0]}"
        pending_table_lead_in = ""
        units.extend(table_units)
        table_lines.clear()

    for raw_line in normalized.splitlines():
        stripped = raw_line.strip()
        looks_like_table = (
            "|" in raw_line
            and stripped
            and (
                stripped.startswith("|")
                or stripped.endswith("|")
                or _TABLE_DIVIDER_RE.match(stripped) is not None
            )
        )
        if looks_like_table:
            flush_paragraph(for_table=True)
            table_lines.append(raw_line)
            continue

        flush_table()

        if not stripped:
            flush_paragraph()
            continue

        if _HORIZONTAL_RULE_RE.match(stripped):
            flush_paragraph()
            continue

        if re.match(r"^#{1,6}\s+", stripped):
            flush_paragraph()
            heading = _strip_inline_markdown(re.sub(r"^#{1,6}\s+", "", stripped))
            if heading:
                units.append(heading)
            continue

        line = re.sub(r"^\s*(?:>\s*)+", "", raw_line)
        bullet_match = re.match(r"^\s*[-*+]\s+(.*)$", line)
        if bullet_match:
            flush_paragraph()
            item = _strip_inline_markdown(bullet_match.group(1))
            units.extend(_split_plain_sentences(item))
            continue

        ordered_match = re.match(r"^\s*\d+[.)]\s+(.*)$", line)
        if ordered_match:
            flush_paragraph()
            item = _strip_inline_markdown(ordered_match.group(1))
            units.extend(_split_plain_sentences(item))
            continue

        cleaned = _strip_inline_markdown(line)
        if cleaned:
            paragraph_lines.append(cleaned)

    flush_table()
    flush_paragraph()
    return [unit for unit in units if unit]


def strip_markdown(text: str) -> str:
    return " ".join(markdown_to_text_units(text)).strip()


def _normalize_speech_unit(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip(" \t\r\n,，:：;；")
    if not cleaned:
        return ""
    if cleaned[-1] not in _TERMINAL_PUNCTUATION:
        cleaned += "。"
    return cleaned


def _has_spoken_content(text: str) -> bool:
    return _SPEECH_CONTENT_RE.search(text) is not None


def _split_long_speech_chunks(text: str) -> list[str]:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= 42:
        return [compact]
    if any(keyword in compact for keyword in ("当前数", "当前值", "结果", "哈希表", "补数", "需要的另一半")):
        return [compact]
    if any(keyword in compact for keyword in ("如果", "否则", "当 ", "当`", "当target", "当 target")):
        return [compact]
    clauses = [
        part.strip(" \t\r\n,，:：;；")
        for part in re.split(r"[，,:：]\s*", compact)
        if part.strip(" \t\r\n,，:：;；")
    ]
    if len(clauses) <= 1:
        return [compact]
    return clauses


def _trim_speech_unit(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    normalized = _normalize_speech_unit(text)
    if len(normalized) <= max_chars:
        return normalized

    candidate = normalized[:max_chars].rstrip(" \t\r\n,，:：;；")
    best_cut = -1
    for marks in ("。！？!?；;.", "，,:： "):
        for mark in marks:
            cut = candidate.rfind(mark)
            if cut > best_cut:
                best_cut = cut
        if best_cut >= max(0, max_chars // 2):
            break
    if best_cut >= max(0, max_chars // 2):
        candidate = candidate[: best_cut + 1].strip().rstrip(" \t\r\n,，:：;；")
    else:
        candidate = candidate.rstrip(" \t\r\n,，:：;；")
    if candidate and candidate[-1] not in _TERMINAL_PUNCTUATION:
        candidate += "。"
    return candidate


def markdown_to_speech_text(text: str, max_chars: int | None = None) -> str:
    expanded_units: list[str] = []
    for unit in markdown_to_text_units(text):
        expanded_units.extend(_split_long_speech_chunks(unit))
    if (
        max_chars is not None
        and len(expanded_units) > 1
        and any(marker in expanded_units[0] for marker in ("为例", "如下", "见下表"))
        and any(keyword in expanded_units[1] for keyword in ("当前数", "结果", "哈希表", "补数"))
    ):
        expanded_units = expanded_units[1:]
    units = [_normalize_speech_unit(unit) for unit in expanded_units]
    units = [unit for unit in units if unit and _has_spoken_content(unit)]
    if not units:
        return ""
    if max_chars is None:
        return " ".join(units).strip()

    selected: list[str] = []
    used = 0
    for unit in units:
        sep = 1 if selected else 0
        projected = used + sep + len(unit)
        if projected <= max_chars:
            selected.append(unit)
            used = projected
            continue
        if not selected:
            return _trim_speech_unit(unit, max_chars)
        break
    return " ".join(selected).strip()


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
_FENCED_CODE_RE = re.compile(r"```(?P<lang>[a-zA-Z0-9_+-]*)\s*(?P<code>.*?)```", re.S)


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


def extract_python_block(text: str) -> str:
    blank_fences: list[str] = []
    for match in _FENCED_CODE_RE.finditer(text):
        lang = (match.group("lang") or "").strip().lower()
        code = match.group("code").strip()
        if not code:
            continue
        if lang in {"python", "py"}:
            return code
        if not lang:
            blank_fences.append(code)
    if blank_fences:
        return blank_fences[0]
    return text.strip()


def clamp_text(text: str, max_len: int) -> str:
    compact = strip_markdown(text)
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 1].rstrip() + "…"
