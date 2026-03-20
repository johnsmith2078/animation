from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .codegen import (
    build_animation_markdown,
    build_compose_script,
    build_fallback_timeline,
    build_manim_scene_code,
    build_render_manim_script,
    build_render_tts_script,
    build_solution_stub,
    build_voiceover_markdown,
    coerce_timeline_from_model,
    rebuild_segment_times,
)
from .llm import OpenAICompatibleLLM
from .models import ProblemArtifact, TimelineArtifact
from .prompts import (
    build_solution_user_prompt,
    build_timeline_user_prompt,
    solution_system_prompt,
    timeline_system_prompt,
)
from .utils import (
    ensure_dir,
    extract_json_block,
    first_heading,
    now_compact,
    now_utc_iso,
    read_json,
    read_text,
    slugify,
    write_json,
    write_text,
)


class Pipeline:
    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()
        self.runs_root = ensure_dir(self.project_root / "runs")
        self.llm = OpenAICompatibleLLM.from_env()
        self.default_target_duration_sec = float(os.getenv("LEETANIM_TARGET_DURATION_SEC", "90"))

    def create_run(
        self,
        *,
        problem_file: Path | None = None,
        problem_text: str | None = None,
        problem_id: str | None = None,
        title: str | None = None,
        slug: str | None = None,
        source: str = "manual",
        language: str = "zh-CN",
        run_dir: Path | None = None,
    ) -> Path:
        content = self._resolve_problem_text(problem_file, problem_text, problem_id, title)
        resolved_title = title or first_heading(content) or f"LeetCode {problem_id or 'unknown'}"
        resolved_problem_id = str(problem_id or self._extract_problem_id_from_title(resolved_title) or "unknown")
        resolved_slug = slug or slugify(resolved_title, fallback=f"p{resolved_problem_id}")

        if run_dir is None:
            run_name = f"{now_compact()}_{resolved_problem_id}_{resolved_slug}"
            run_dir = self.runs_root / run_name
        else:
            run_dir = run_dir.resolve()

        ensure_dir(run_dir)
        ensure_dir(run_dir / "01_problem")
        ensure_dir(run_dir / "02_solution")
        ensure_dir(run_dir / "03_timeline")
        ensure_dir(run_dir / "04_codegen")
        ensure_dir(run_dir / "05_outputs" / "audio" / "text")
        ensure_dir(run_dir / "05_outputs" / "video")
        ensure_dir(run_dir / "06_final")

        problem = ProblemArtifact(
            problem_id=resolved_problem_id,
            title=resolved_title,
            slug=resolved_slug,
            source=source,
            language=language,
            statement_markdown=content,
            metadata={
                "created_at": now_utc_iso(),
                "original_problem_file": str(problem_file) if problem_file else None,
            },
        )
        write_text(run_dir / "01_problem" / "problem.md", content)
        write_json(run_dir / "01_problem" / "problem.json", problem.to_dict())
        self._update_manifest(
            run_dir,
            {
                "run_id": run_dir.name,
                "created_at": now_utc_iso(),
                "problem": {
                    "problem_id": resolved_problem_id,
                    "title": resolved_title,
                    "slug": resolved_slug,
                    "source": source,
                },
                "stages": {
                    "problem": {
                        "status": "ready",
                        "path": "01_problem/problem.json",
                    }
                },
            },
            overwrite=True,
        )
        return run_dir

    def generate_solution(self, run_dir: Path, force: bool = False) -> Path:
        problem = self.load_problem(run_dir)
        output_dir = ensure_dir(run_dir / "02_solution")
        prompt_path = output_dir / "problem_to_solution.prompt.md"
        solution_path = output_dir / "solution.md"

        prompt = build_solution_user_prompt(problem)
        write_text(prompt_path, prompt)
        if solution_path.exists() and not force:
            return solution_path

        if self.llm:
            try:
                content = self.llm.chat(solution_system_prompt(), prompt)
                quality = "llm"
            except Exception as exc:
                content = build_solution_stub(problem, reason=f"LLM 调用失败：{exc}")
                quality = "stub_fallback"
        else:
            content = build_solution_stub(problem, reason="未配置 LEETANIM_LLM_API_KEY / LEETANIM_LLM_MODEL")
            quality = "stub"

        write_text(solution_path, content)
        self._set_stage(run_dir, "solution", quality, "02_solution/solution.md")
        return solution_path

    def generate_timeline(
        self,
        run_dir: Path,
        force: bool = False,
        target_duration_sec: float | None = None,
    ) -> Path:
        problem = self.load_problem(run_dir)
        solution_path = run_dir / "02_solution" / "solution.md"
        if not solution_path.exists():
            self.generate_solution(run_dir)
        solution_text = read_text(solution_path)

        output_dir = ensure_dir(run_dir / "03_timeline")
        prompt_path = output_dir / "solution_to_timeline.prompt.md"
        timeline_path = output_dir / "timeline.json"
        voiceover_path = output_dir / "voiceover_script.md"
        animation_path = output_dir / "animation_script.md"

        target = float(target_duration_sec or self.default_target_duration_sec)
        prompt = build_timeline_user_prompt(problem, solution_text, target)
        write_text(prompt_path, prompt)
        if timeline_path.exists() and not force:
            return timeline_path

        timeline: TimelineArtifact
        quality = "fallback"
        if self.llm:
            try:
                response = self.llm.chat(timeline_system_prompt(), prompt)
                payload = json.loads(extract_json_block(response))
                timeline = coerce_timeline_from_model(problem, payload, target)
                quality = "llm"
            except Exception as exc:
                timeline = build_fallback_timeline(problem, solution_text, target, source_quality=f"fallback_after_llm_error: {exc}")
                quality = "fallback"
        else:
            timeline = build_fallback_timeline(problem, solution_text, target, source_quality="fallback_no_llm")

        timeline = rebuild_segment_times(timeline, use_actual_audio=False)
        write_json(timeline_path, timeline.to_dict())
        write_text(voiceover_path, build_voiceover_markdown(timeline))
        write_text(animation_path, build_animation_markdown(timeline))
        self._set_stage(run_dir, "timeline", quality, "03_timeline/timeline.json")
        return timeline_path

    def generate_manim(self, run_dir: Path, force: bool = False) -> Path:
        problem = self.load_problem(run_dir)
        timeline = self.load_timeline(run_dir)
        output_dir = ensure_dir(run_dir / "04_codegen")
        scene_path = output_dir / "manim_scene.py"
        script_path = output_dir / "render_manim.sh"
        if scene_path.exists() and not force:
            return scene_path
        write_text(scene_path, build_manim_scene_code(problem, timeline))
        write_text(script_path, build_render_manim_script())
        script_path.chmod(0o755)
        self._set_stage(run_dir, "manim", "generated", "04_codegen/manim_scene.py")
        return scene_path

    def generate_tts(self, run_dir: Path, force: bool = False) -> Path:
        timeline = self.load_timeline(run_dir)
        output_dir = ensure_dir(run_dir / "04_codegen")
        audio_text_dir = ensure_dir(run_dir / "05_outputs" / "audio" / "text")
        script_path = output_dir / "render_tts.sh"
        config_path = output_dir / "tts_config.json"

        if script_path.exists() and not force:
            return script_path

        for segment in timeline.segments:
            write_text(audio_text_dir / f"{segment.id}.txt", segment.narration.strip() + "\n")

        write_text(script_path, build_render_tts_script(timeline.segments))
        script_path.chmod(0o755)
        write_json(
            config_path,
            {
                "voice": os.getenv("LEETANIM_VOICE", "zh-CN-XiaoxiaoNeural"),
                "rate": os.getenv("LEETANIM_RATE", "+0%"),
                "volume": os.getenv("LEETANIM_VOLUME", "+0%"),
                "pitch": os.getenv("LEETANIM_PITCH", "+0Hz"),
            },
        )
        self._set_stage(run_dir, "tts", "generated", "04_codegen/render_tts.sh")
        return script_path

    def generate_compose(self, run_dir: Path, force: bool = False) -> Path:
        output_dir = ensure_dir(run_dir / "06_final")
        compose_path = output_dir / "compose.sh"
        if compose_path.exists() and not force:
            return compose_path
        write_text(compose_path, build_compose_script())
        compose_path.chmod(0o755)
        self._set_stage(run_dir, "compose", "generated", "06_final/compose.sh")
        return compose_path

    def sync_from_audio(self, run_dir: Path, force_regenerate_manim: bool = True) -> Path:
        timeline = self.load_timeline(run_dir)
        audio_dir = run_dir / "05_outputs" / "audio"
        found_any = False
        for segment in timeline.segments:
            audio_file = audio_dir / f"{segment.id}.mp3"
            if not audio_file.exists():
                continue
            duration = self._probe_audio_duration(audio_file)
            if duration is None:
                continue
            segment.actual_audio_duration_sec = duration
            found_any = True

        if not found_any:
            raise RuntimeError(f"在 {audio_dir} 下未找到可读取时长的 mp3；请先执行 render_tts.sh，并确保 ffprobe 可用")

        timeline = rebuild_segment_times(timeline, use_actual_audio=True)
        write_json(run_dir / "03_timeline" / "timeline.json", timeline.to_dict())
        write_text(run_dir / "03_timeline" / "voiceover_script.md", build_voiceover_markdown(timeline))
        write_text(run_dir / "03_timeline" / "animation_script.md", build_animation_markdown(timeline))
        if force_regenerate_manim:
            self.generate_manim(run_dir, force=True)
        self._set_stage(run_dir, "sync", "generated", "03_timeline/timeline.json")
        return run_dir / "03_timeline" / "timeline.json"

    def all(
        self,
        *,
        problem_file: Path | None = None,
        problem_text: str | None = None,
        problem_id: str | None = None,
        title: str | None = None,
        slug: str | None = None,
        source: str = "manual",
        language: str = "zh-CN",
        run_dir: Path | None = None,
        force: bool = False,
        target_duration_sec: float | None = None,
    ) -> Path:
        run_dir = self.create_run(
            problem_file=problem_file,
            problem_text=problem_text,
            problem_id=problem_id,
            title=title,
            slug=slug,
            source=source,
            language=language,
            run_dir=run_dir,
        )
        self.generate_solution(run_dir, force=force)
        self.generate_timeline(run_dir, force=force, target_duration_sec=target_duration_sec)
        self.generate_manim(run_dir, force=force)
        self.generate_tts(run_dir, force=force)
        self.generate_compose(run_dir, force=force)
        return run_dir

    def load_problem(self, run_dir: Path) -> ProblemArtifact:
        return ProblemArtifact.from_dict(read_json(run_dir / "01_problem" / "problem.json"))

    def load_timeline(self, run_dir: Path) -> TimelineArtifact:
        path = run_dir / "03_timeline" / "timeline.json"
        if not path.exists():
            self.generate_timeline(run_dir)
        return TimelineArtifact.from_dict(read_json(path))

    def _resolve_problem_text(
        self,
        problem_file: Path | None,
        problem_text: str | None,
        problem_id: str | None,
        title: str | None,
    ) -> str:
        if problem_file:
            return read_text(problem_file)
        if problem_text:
            return problem_text
        resolved_title = title or f"LeetCode {problem_id or 'unknown'}"
        return (
            f"# {resolved_title}\n\n"
            "> [占位题目]\n"
            "> 当前只提供了题号/标题，尚未接入 LeetCode 自动抓题。\n"
            "> 请把真实题面填到本文件，再重新运行 solution/timeline 阶段。\n"
        )

    @staticmethod
    def _extract_problem_id_from_title(title: str) -> str | None:
        digits = "".join(ch for ch in title if ch.isdigit())
        return digits or None

    def _manifest_path(self, run_dir: Path) -> Path:
        return run_dir / "manifest.json"

    def _update_manifest(self, run_dir: Path, payload: dict[str, Any], overwrite: bool = False) -> None:
        path = self._manifest_path(run_dir)
        if overwrite or not path.exists():
            write_json(path, payload)
            return
        current = read_json(path)
        current.update(payload)
        write_json(path, current)

    def _set_stage(self, run_dir: Path, stage_name: str, status: str, relative_path: str) -> None:
        path = self._manifest_path(run_dir)
        manifest = read_json(path) if path.exists() else {"run_id": run_dir.name, "created_at": now_utc_iso(), "stages": {}}
        stages = manifest.setdefault("stages", {})
        stages[stage_name] = {
            "status": status,
            "path": relative_path,
            "updated_at": now_utc_iso(),
        }
        write_json(path, manifest)

    def _probe_audio_duration(self, path: Path) -> float | None:
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            return None
        cmd = [
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
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            value = float(result.stdout.strip())
            return round(value, 1)
        except Exception:
            return None
