from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from leetanim.codegen import build_render_manim_script


class RenderManimScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.project_root = Path(self.temp_dir.name) / "project"
        self.run_dir = self.project_root / "runs" / "20260321_test"
        self.script_path = self.run_dir / "04_codegen" / "render_manim.py"
        self.script_path.parent.mkdir(parents=True, exist_ok=True)

        self.namespace = {
            "__file__": str(self.script_path),
            "__name__": "generated_render_manim_test",
        }
        source = build_render_manim_script()
        exec(compile(source, str(self.script_path), "exec"), self.namespace)

    def test_find_rendered_video_accepts_temp_mp4(self) -> None:
        temp_video = self.run_dir / "videos" / "LeetCodeSolutionScene_temp.mp4"
        temp_video.parent.mkdir(parents=True, exist_ok=True)
        temp_video.write_bytes(b"temp-video")

        found = self.namespace["find_rendered_video"](allow_temp=True)

        self.assertEqual(found, temp_video)
        self.assertTrue(self.namespace["is_temp_video"](found))

    def test_find_rendered_video_prefers_recent_outputs_from_current_run(self) -> None:
        videos_dir = self.run_dir / "videos"
        videos_dir.mkdir(parents=True, exist_ok=True)
        final_video = videos_dir / "LeetCodeSolutionScene.mp4"
        temp_video = videos_dir / "LeetCodeSolutionScene_temp.mp4"
        final_video.write_bytes(b"old-final")
        temp_video.write_bytes(b"new-temp")
        os.utime(final_video, (10, 10))
        os.utime(temp_video, (20, 20))

        found = self.namespace["find_rendered_video"](since_time=15, allow_temp=True)

        self.assertEqual(found, temp_video)

    def test_recover_from_temp_video_accepts_windows_minus_one_exit_code(self) -> None:
        temp_video = self.run_dir / "videos" / "LeetCodeSolutionScene_temp.mp4"
        temp_video.parent.mkdir(parents=True, exist_ok=True)
        temp_video.write_bytes(b"temp-video")
        os.utime(temp_video, (100, 100))
        error = subprocess.CalledProcessError(4294967295, ["manim"])

        recovered = self.namespace["recover_from_temp_video"](error, started_at=100)

        self.assertEqual(self.namespace["normalize_returncode"](4294967295), -1)
        self.assertEqual(recovered, temp_video)


if __name__ == "__main__":
    unittest.main()
