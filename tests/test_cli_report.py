"""Consumer JSON binds the requested file and preserves reference cost evidence."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_estimate import ROOT, sibling

# Hang guard, not a performance assertion: docs/hang-guards.md, short class.
SHORT_HANG_GUARD_SECONDS = 30


class ConsumerReport(unittest.TestCase):
    def setUp(self):
        self.binary = os.environ["BENNETT_ESTIMATE_BIN"]
        self.target = sibling(ROOT, "bennett-targets") / "targets/ideal-quantum-circuit.json"
        self.published = (sibling(ROOT, "bennett-isa-spec") /
                          "conformance/fixtures/controlled-action-09/controlled.bisa")

    def run_cli(self, path, *args):
        return subprocess.run([self.binary, str(path), "--target", str(self.target), *args],
                              capture_output=True, text=True, timeout=SHORT_HANG_GUARD_SECONDS)

    def test_published_object_has_named_target_file_digest_budget_and_padded_cost(self):
        actual = self.run_cli(self.published, "--region", "controlled")
        self.assertEqual(actual.returncode, 0, actual.stderr)
        report = json.loads(actual.stdout)
        self.assertEqual(report["target"], "ideal-quantum-circuit")
        self.assertEqual(report["object_sha256"], hashlib.sha256(self.published.read_bytes()).hexdigest())
        self.assertNotEqual(report["object_sha256"], report["object_hash"])
        self.assertEqual(report["budget"], {"steps": 0, "heap": 0, "stack": 0, "depth": 0})
        self.assertEqual(report["label"], "exact")
        # One CX, two interface wires, unit gate duration and occupancy rate.
        expected = {"gate_count": "1", "time": "1", "peak_qubits[data]": "2", "qubit_second[data]": "2"}
        self.assertEqual(report["padded"], expected)
        self.assertEqual(report["resources"], expected)
        self.assertEqual(report["scope"], "sequential reference realisation")

    def test_unknown_arguments_fail_without_success_json(self):
        actual = self.run_cli(self.published, "--region", "controlled", "--unknown")
        self.assertEqual(actual.returncode, 2)
        self.assertEqual(actual.stdout, "")
        self.assertIn("unrecognized arguments: --unknown", actual.stderr)

    def test_option_prefix_is_not_a_supported_argument(self):
        actual = subprocess.run([self.binary, str(self.published), "--targ", str(self.target)],
                                capture_output=True, text=True, timeout=SHORT_HANG_GUARD_SECONDS)
        self.assertEqual(actual.returncode, 2)
        self.assertEqual(actual.stdout, "")
        self.assertIn("--target", actual.stderr)

    def test_crlf_file_is_rejected_before_estimation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "noncanonical.bisa"
            path.write_bytes(self.published.read_bytes().replace(b"\n", b"\r\n"))
            actual = self.run_cli(path, "--region", "controlled")
        self.assertEqual(actual.returncode, 1)
        self.assertEqual(actual.stdout, "")
        self.assertIn("LF line endings", actual.stderr)

    def test_pending_report_has_request_binding_without_padded_resources(self):
        actual = self.run_cli(ROOT / "tests/fixtures/ret-delivery-source-gap.bisa",
                              "--region", "root", "--budget", "2,0,0,0", "--token-aliases", "[0]")
        self.assertEqual(actual.returncode, 3, actual.stderr)
        report = json.loads(actual.stdout)
        self.assertEqual(report["target"], "ideal-quantum-circuit")
        self.assertEqual(report["budget"], {"steps": 2, "heap": 0, "stack": 0, "depth": 0})
        self.assertEqual(report["label"], "pending evidence")
        self.assertNotIn("padded", report)
        self.assertNotIn("resources", report)

    def test_large_budget_binding_preserves_every_integer_bit(self):
        for steps, expected in [(2**53 - 1, 2**53 - 1), (2**53 + 1, str(2**53 + 1))]:
            with self.subTest(steps=steps):
                actual = self.run_cli(self.published, "--region", "flip", "--budget", f"{steps},0,0,0")
                self.assertEqual(actual.returncode, 0, actual.stderr)
                self.assertEqual(json.loads(actual.stdout)["budget"]["steps"], expected)

    def test_real_compiler_object_does_not_invent_legacy_padded_cost(self):
        path = (sibling(ROOT, "bennett-conformance") /
                "ladder/rung-1/evidence/20261101T135131.872696Z/C/23/r1_popcount/out/ref.bennett")
        actual = self.run_cli(path, "--budget", "100,0,0,0")
        self.assertEqual(actual.returncode, 1)
        self.assertEqual(actual.stdout, "")
        self.assertIn("0.8 has no published complete expansion library", actual.stderr)


if __name__ == "__main__":
    unittest.main()
