"""Exercise the quality gate on isolated repositories, including regressions."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/quality_ratchet.py"


class QualityRatchet(unittest.TestCase):
    def test_recorded_baseline_accepts_unchanged_code_and_rejects_regressions(self):
        original = "def calculate(value):\n    result = value + 1\n    return result\n"
        mutations = {
            "function lengths": original.replace("    return result", "    result += 1\n    return result"),
            "cognitive complexity": "def calculate(value):\n    if value:\n        return value\n",
            "trivial wrappers": "def calculate(value):\n    return abs(value)\n",
            "process identifiers": original + "# shift 42\n",
        }
        with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True, timeout=10)
            (root / "src").mkdir()
            (root / "docs").mkdir()
            (root / "docs/quality.md").write_text("# Quality evidence\n")
            source = root / "src/calculation.py"
            source.write_text(original)
            subprocess.run(["git", "-C", str(root), "add", "src/calculation.py"], check=True, timeout=10)
            command = [sys.executable, "-I", "-B", str(SCRIPT), "--root", str(root)]
            recorded = subprocess.run(command + ["--record"], capture_output=True, text=True, timeout=10)
            self.assertEqual(recorded.returncode, 0, recorded.stderr)
            baseline = json.loads(recorded.stdout)
            self.assertEqual(baseline["files"]["src/calculation.py"],
                             {"function_lengths": [3], "cognitive_complexity": 0, "trivial_wrappers": 0})
            with (root / "docs/quality.md").open("a") as doc:
                doc.write("\n<!-- quality-baseline -->\n```json\n" + recorded.stdout + "```\n<!-- /quality-baseline -->\n")
            unchanged = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(unchanged.returncode, 0, unchanged.stderr)
            for metric, mutation in mutations.items():
                with self.subTest(metric=metric):
                    source.write_text(mutation)
                    result = subprocess.run(command, capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 1, result.stderr)
                    self.assertIn(metric, result.stderr)
            source.write_text(original)
            litter = root / "src/trace.log"
            litter.write_text("scratch output\n")
            subprocess.run(["git", "-C", str(root), "add", "src/trace.log"], check=True, timeout=10)
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("litter", result.stderr)


if __name__ == "__main__":
    unittest.main()
