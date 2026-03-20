from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from .env import load_project_env
from .pipeline import Pipeline


def resolve_project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="一键完成题解视频流水线")
    parser.add_argument("--problem-file", type=Path, help="题目 markdown 文件路径")
    parser.add_argument("--problem-text", help="直接传入题目内容")
    parser.add_argument("--problem-id", help="题号；未提供题面时会自动抓取 LeetCode 中文站题目")
    parser.add_argument("--title", help="题目标题")
    parser.add_argument("--slug", help="自定义 slug")
    parser.add_argument("--source", default="manual", help="题目来源")
    parser.add_argument("--language", default="zh-CN", help="题目语言")
    parser.add_argument("--run-dir", type=Path, help="已有 run 目录；不传则自动新建")
    parser.add_argument("--force", action="store_true", help="覆盖已有阶段输出")
    parser.add_argument("--target-duration-sec", type=float, help="目标总时长")
    parser.add_argument(
        "--video-input",
        type=Path,
        help="compose 阶段使用的视觉视频路径；默认使用 runs/<run_id>/05_outputs/video/raw_visual.mp4",
    )
    return parser


def run_generated_script(script_path: Path, *, cwd: Path, extra_args: list[str] | None = None) -> None:
    command = [sys.executable, str(script_path)]
    if extra_args:
        command.extend(extra_args)
    subprocess.run(command, cwd=cwd, check=True)


def run_from_args(args: argparse.Namespace) -> Path:
    project_root = resolve_project_root()
    load_project_env(project_root)
    pipeline = Pipeline(project_root)

    print("[1/5] 生成 run、题解、时间轴和脚本")
    run_dir = pipeline.all(
        problem_file=args.problem_file,
        problem_text=args.problem_text,
        problem_id=args.problem_id,
        title=args.title,
        slug=args.slug,
        source=args.source,
        language=args.language,
        run_dir=args.run_dir,
        force=args.force,
        target_duration_sec=args.target_duration_sec,
    )

    render_tts_script = run_dir / "04_codegen" / "render_tts.py"
    render_manim_script = run_dir / "04_codegen" / "render_manim.py"
    compose_script = run_dir / "06_final" / "compose.py"
    video_input = (
        args.video_input.expanduser().resolve()
        if args.video_input
        else run_dir / "05_outputs" / "video" / "raw_visual.mp4"
    )

    print("[2/5] 生成配音")
    run_generated_script(render_tts_script, cwd=project_root)

    print("[3/5] 按真实音频时长回写时间轴")
    pipeline.sync_from_audio(run_dir)

    print("[4/5] 渲染 Manim 视频")
    run_generated_script(render_manim_script, cwd=project_root)

    print("[5/5] 合成最终视频")
    run_generated_script(compose_script, cwd=project_root, extra_args=[str(video_input)])

    final_video = run_dir / "06_final" / "final_video.mp4"
    print(f"run_dir={run_dir}")
    print(f"final_video={final_video}")
    return final_video


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    run_from_args(args)


if __name__ == "__main__":
    main()
