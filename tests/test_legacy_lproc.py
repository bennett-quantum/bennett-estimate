"""Published ISA 0.8 lprocs retain their versioned signature schema.

The mini fixture is the unmodified rung4-mini.bennett extracted from
bennett-dialect-spec 9bbf6dee3ab6ce94030e01a1af98df28fe19e683. ISA 0.8
section 9.1 (220f4e4dd9ea13cf81f3c28651219710897cd79d) declares only
params/result for lprocs; ISA 0.9 additionally requires tokens/args/mem.
"""
import hashlib
import os
import subprocess
import unittest

from test_estimate import ROOT, e, sibling


class LegacyLproc(unittest.TestCase):
    def test_published_rung4_mini_is_admitted_without_changing_its_bytes(self):
        path = ROOT / "tests/fixtures/rung4-mini-08.bisa"
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                         "742ccbaf23ca1b89c93e8fa6e3e6953df99748d45d6ef01cfc9f91f1a89726a8")
        obj = e.Object.read(path.read_text())
        self.assertEqual(obj.versions["isa"], "0.8")
        self.assertEqual(set(obj.symbol("L1")["signature"]),
                         {"abi", "kind", "tier", "params", "result"})
        for symbol in obj.sections["symbols"].values():
            self.assertEqual(obj.identities()[symbol["name"]], symbol["interface_hash"])

    def test_legacy_parameter_and_result_widths_still_match_the_header(self):
        text = (ROOT / "tests/fixtures/rung4-mini-08.bisa").read_text()
        for old, new in [('"params":[64,64,32]', '"params":[64,64,16]'),
                         ('"result":8', '"result":16')]:
            with self.subTest(field=old), self.assertRaisesRegex(e.ContractError, "lproc signature/header mismatch"):
                e.Object.read(text.replace(old, new, 1))

    def test_09_requires_each_lproc_interface_array(self):
        text = (ROOT / "tests/fixtures/example10.bisa").read_text()
        head, rest = text.split("\n\nsection symbols\n", 1)
        symbols, functions = rest.split("\n\nsection functions\n", 1)
        for field in ["tokens", "args", "mem"]:
            records = e.loads(symbols)
            signature = next(s["signature"] for s in records.values() if s["kind"] == "lproc")
            del signature[field]
            with self.subTest(field=field), self.assertRaisesRegex(e.ContractError, "ISA 0.9 lproc signature: missing"):
                e.Object.read(head + "\n\nsection symbols\n" + e.jcs(records) + "\n\nsection functions\n" + functions)

    def test_09_checks_each_lproc_interface_array_against_the_header(self):
        text = (ROOT / "tests/fixtures/example10.bisa").read_text()
        head, rest = text.split("\n\nsection symbols\n", 1)
        symbols, functions = rest.split("\n\nsection functions\n", 1)
        for field in ["tokens", "args", "mem"]:
            records = e.loads(symbols)
            signature = next(s["signature"] for s in records.values() if s["kind"] == "lproc")
            signature[field] = []
            with self.subTest(field=field), self.assertRaisesRegex(e.ContractError, "lproc signature/header mismatch"):
                e.Object.read(head + "\n\nsection symbols\n" + e.jcs(records) + "\n\nsection functions\n" + functions)


class LegacyLprocCLI(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([os.environ["BENNETT_ESTIMATE_BIN"],
                               str(ROOT / "tests/fixtures/rung4-mini-08.bisa"),
                               "--target", str(sibling(ROOT, "bennett-targets") / "targets/ideal-quantum-circuit.json"),
                               *args], capture_output=True, text=True, timeout=30)

    def test_mini_requires_an_explicit_budget_after_admission(self):
        actual = self.run_cli()
        self.assertEqual(actual.returncode, 1)
        self.assertEqual(actual.stdout, "")
        self.assertIn("E_ARG: oracle/token-taking entry requires --budget", actual.stderr)

    def test_mini_does_not_invent_an_unpublished_padded_cost(self):
        actual = self.run_cli("--budget", "1,0,0,0", "--params", '["16"]', "--token-aliases", "[0]")
        self.assertEqual(actual.returncode, 1)
        self.assertEqual(actual.stdout, "")
        self.assertIn("0.8 has no published complete expansion library", actual.stderr)
