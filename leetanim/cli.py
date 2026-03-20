from __future__ import annotations

import argparse
from pathlib import Path

from .env import load_project_env
from .pipeline import Pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LeetCode 题解动画流水线")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_problem_input_arguments(target: argparse.ArgumentParser) -> None:
        target.add_argument("--problem-file", type=Path, help="题目 markdown 文件路径")
        target.add_argument("--problem-text", help="直接传入题目内容")
        target.add_argument("--problem-id", help="题号")
        target.add_argument("--title", help="题目标题")
        target.add_argument("--slug", help="自定义 slug")
        target.add_argument("--source", default="manual", help="题目来源")
        target.add_argument("--language", default="zh-CN", help="题目语言")
        target.add_argument("--run-dir", type=Path, help="已有 run 目录；不传则自动新建")
        target.add_argument("--force", action="store_true", help="覆盖已有阶段输出")

    ingest = subparsers.add_parser("ingest", help="创建 run 并保存题目")
    add_problem_input_arguments(ingest)

    solution = subparsers.add_parser("solution", help="生成题解")
    solution.add_argument("--run-dir", type=Path, required=True)
    solution.add_argument("--force", action="store_true")

    timeline = subparsers.add_parser("timeline", help="生成时间轴/配音脚本/动画脚本")
    timeline.add_argument("--run-dir", type=Path, required=True)
    timeline.add_argument("--force", action="store_true")
    timeline.add_argument("--target-duration-sec", type=float, help="目标总时长")

    manim = subparsers.add_parser("manim", help="生成 Manim 场景代码")
    manim.add_argument("--run-dir", type=Path, required=True)
    manim.add_argument("--force", action="store_true")

    tts = subparsers.add_parser("tts", help="生成 edge-tts 文本资产与脚本")
    tts.add_argument("--run-dir", type=Path, required=True)
    tts.add_argument("--force", action="store_true")

    sync = subparsers.add_parser("sync", help="按真实音频时长回写时间轴")
    sync.add_argument("--run-dir", type=Path, required=True)

    compose = subparsers.add_parser("compose", help="生成 ffmpeg 合成脚本")
    compose.add_argument("--run-dir", type=Path, required=True)
    compose.add_argument("--force", action="store_true")

    all_cmd = subparsers.add_parser("all", help="一键生成完整流水线骨架")
    add_problem_input_arguments(all_cmd)
    all_cmd.add_argument("--target-duration-sec", type=float, help="目标总时长")

    return parser


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    load_project_env(project_root)
    parser = build_parser()
    args = parser.parse_args()
    pipeline = Pipeline(project_root)

    if args.command == "ingest":
        run_dir = pipeline.create_run(
            problem_file=args.problem_file,
            problem_text=args.problem_text,
            problem_id=args.problem_id,
            title=args.title,
            slug=args.slug,
            source=args.source,
            language=args.language,
            run_dir=args.run_dir,
        )
        print(run_dir)
        return

    if args.command == "solution":
        path = pipeline.generate_solution(args.run_dir, force=args.force)
        print(path)
        return

    if args.command == "timeline":
        path = pipeline.generate_timeline(
            args.run_dir,
            force=args.force,
            target_duration_sec=args.target_duration_sec,
        )
        print(path)
        return

    if args.command == "manim":
        path = pipeline.generate_manim(args.run_dir, force=args.force)
        print(path)
        return

    if args.command == "tts":
        path = pipeline.generate_tts(args.run_dir, force=args.force)
        print(path)
        return

    if args.command == "sync":
        path = pipeline.sync_from_audio(args.run_dir)
        print(path)
        return

    if args.command == "compose":
        path = pipeline.generate_compose(args.run_dir, force=args.force)
        print(path)
        return

    if args.command == "all":
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
        print(run_dir)
        return

    parser.error(f"Unsupported command: {args.command}")
