#!/usr/bin/env python3

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT_DIR / "Scripts" / "SwiftPackage" / "check_ccache_payload.sh"


def run_script(path: Path, minimum_bytes: int = 262144) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT_PATH), str(path), str(minimum_bytes)],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT_DIR,
    )


class CCachePayloadTests(unittest.TestCase):
    def test_missing_directory_fails_loudly(self) -> None:
        result = run_script(ROOT_DIR / ".missing-ccache")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing ccache directory", result.stderr)

    def test_tiny_payload_reports_non_empty_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_dir = Path(tmp_dir) / ".ccache"
            cache_dir.mkdir()
            (cache_dir / "stats").write_bytes(b"tiny")

            result = run_script(cache_dir, minimum_bytes=1024)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("non_empty=false", result.stdout)
            self.assertIn("file_count=1", result.stdout)

    def test_large_payload_reports_non_empty_true(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_dir = Path(tmp_dir) / ".ccache"
            nested = cache_dir / "a" / "b"
            nested.mkdir(parents=True)
            (nested / "entry.o").write_bytes(b"x" * 4096)

            output_path = Path(tmp_dir) / "github-output.txt"
            env = dict(os.environ)
            env["GITHUB_OUTPUT"] = str(output_path)
            result = subprocess.run(
                [str(SCRIPT_PATH), str(cache_dir), "1024"],
                check=False,
                capture_output=True,
                text=True,
                cwd=ROOT_DIR,
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            output_text = output_path.read_text(encoding="utf-8")
            self.assertIn("non_empty=true", output_text)
            self.assertIn("file_count=1", output_text)
            self.assertIn("total_bytes=4096", output_text)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(CCachePayloadTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
