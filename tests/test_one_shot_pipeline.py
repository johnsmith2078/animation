from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path
from unittest.mock import call, patch

from leetanim.one_shot import build_parser, run_from_args


class OneShotPipelineTests(unittest.TestCase):
    def test_build_parser_accepts_expected_arguments(self) -> None:
        parser = build_parser()

        args = parser.parse_args(
            [
                "--problem-file",
                "examples/1-two_sum.md",
                "--problem-id",
                "1",
                "--title",
                "两数之和",
                "--force",
                "--target-duration-sec",
                "75",
                "--video-input",
                "custom/raw_visual.mp4",
            ]
        )

        self.assertEqual(args.problem_file, Path("examples/1-two_sum.md"))
        self.assertEqual(args.problem_id, "1")
        self.assertEqual(args.title, "两数之和")
        self.assertTrue(args.force)
        self.assertEqual(args.target_duration_sec, 75.0)
        self.assertEqual(args.video_input, Path("custom/raw_visual.mp4"))

    @patch("leetanim.one_shot.resolve_project_root")
    @patch("leetanim.one_shot.Pipeline")
    @patch("leetanim.one_shot.subprocess.run")
    @patch("leetanim.one_shot.load_project_env")
    @patch("leetanim.one_shot.print")
    def test_run_from_args_executes_full_pipeline_in_order(
        self,
        _print_mock,
        load_project_env_mock,
        subprocess_run_mock,
        pipeline_cls_mock,
        resolve_project_root_mock,
    ) -> None:
        project_root = Path("/repo")
        run_dir = project_root / "runs" / "20260320_120000_1_two-sum"
        resolve_project_root_mock.return_value = project_root
        pipeline = pipeline_cls_mock.return_value
        pipeline.all.return_value = run_dir

        args = argparse.Namespace(
            problem_file=Path("examples/1-two_sum.md"),
            problem_text=None,
            problem_id="1",
            title="两数之和",
            slug=None,
            source="manual",
            language="zh-CN",
            run_dir=None,
            force=False,
            target_duration_sec=None,
            video_input=None,
        )

        final_video = run_from_args(args)

        load_project_env_mock.assert_called_once_with(project_root)
        pipeline_cls_mock.assert_called_once_with(project_root)
        pipeline.all.assert_called_once_with(
            problem_file=Path("examples/1-two_sum.md"),
            problem_text=None,
            problem_id="1",
            title="两数之和",
            slug=None,
            source="manual",
            language="zh-CN",
            run_dir=None,
            force=False,
            target_duration_sec=None,
        )
        pipeline.sync_from_audio.assert_called_once_with(run_dir)
        self.assertEqual(
            subprocess_run_mock.call_args_list,
            [
                call([sys.executable, str(run_dir / "04_codegen" / "render_tts.py")], cwd=project_root, check=True),
                call([sys.executable, str(run_dir / "04_codegen" / "render_manim.py")], cwd=project_root, check=True),
                call(
                    [
                        sys.executable,
                        str(run_dir / "06_final" / "compose.py"),
                        str(run_dir / "05_outputs" / "video" / "raw_visual.mp4"),
                    ],
                    cwd=project_root,
                    check=True,
                ),
            ],
        )
        self.assertEqual(final_video, run_dir / "06_final" / "final_video.mp4")


if __name__ == "__main__":
    unittest.main()
