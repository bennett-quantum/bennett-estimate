"""Hygiene checks cover upstream tracker names and suffixed runtime locks."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/quality_ratchet.py"


class Hygiene(unittest.TestCase):
    def test_upstream_identifier_and_suffixed_lock_each_fail_the_gate(self):
        with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "docs").mkdir()
            subprocess.run(["git", "init", "-q", str(root)], check=True, timeout=10)
            source = root / "src/main.rs"
            source.write_text("fn main() {}\n")
            subprocess.run(["git", "-C", str(root), "add", "src/main.rs"], check=True, timeout=10)
            command = [sys.executable, "-I", "-B", str(SCRIPT), "--root", str(root)]
            baseline = subprocess.check_output(command + ["--record"], text=True, timeout=10)
            (root / "docs/quality.md").write_text(
                "<!-- quality-baseline -->\n```json\n" + baseline + "```\n<!-- /quality-baseline -->\n")
            source.write_text("fn main() {} // brt-mab\n")
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("process identifiers", result.stderr)
            source.write_text("fn main() {}\n")
            (root / "runtime.gate.lock.123").write_text("runtime lock\n")
            subprocess.run(["git", "-C", str(root), "add", "runtime.gate.lock.123"], check=True, timeout=10)
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("litter", result.stderr)


if __name__ == "__main__":
    unittest.main()
