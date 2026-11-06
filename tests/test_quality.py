"""Regressions and independent resource-accounting checks for the quality floor."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

from test_estimate import ROOT, e
import sys
sys.path.insert(0, str(ROOT / "scripts"))
from pinned import sibling


class PinnedInputs(unittest.TestCase):
    def test_cached_checkout_must_match_the_requested_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sha = "a" * 40
            (root / "gate.toml").write_text('[siblings.example]\nsha="' + sha + '"\n')
            checkout = root / ".tmp/gate-siblings" / ("example@" + sha)
            checkout.mkdir(parents=True)
            (checkout / ".gate-pin").write_text("b" * 40)
            with self.assertRaisesRegex(RuntimeError, "revision"):
                sibling(root, "example")
            (checkout / ".gate-pin").write_text(sha)
            self.assertEqual(sibling(root, "example"), checkout)
            (checkout / ".gate-pin").unlink()
            with self.assertRaisesRegex(RuntimeError, "revision"):
                sibling(root, "example")


class CoverageEdges(unittest.TestCase):
    def test_target_qram_import_and_weighted_objective_are_validated(self):
        doc = e.loads((ROOT / "data/ideal-four-clique.json").read_text())
        doc["qram"] = {name: {"cost": {"time": {"var": "w"}}} for name in ["load", "store", "exch"]}
        doc["imports"] = {"sample": {"version": "1", "map": {"duration": ["time", 2]}}}
        doc["objective"] = {"weighted": {"time": 2}}
        self.assertEqual(e.Target.read(e.jcs(doc)).doc, doc)
        for field, value in [("imports", {"sample": {"version": "1", "map": {"duration": ["time", -1]}}}),
                             ("objective", {"weighted": {"time": -1}})]:
            bad = copy.deepcopy(doc); bad[field] = value
            with self.assertRaises(e.ContractError):
                e.Target.read(e.jcs(bad))

    def test_indexed_table_expression_and_exact_division(self):
        from fractions import Fraction
        self.assertEqual(e.expression({"table": "t", "index": "k"}, {"k": 1}, {"t": [2, 5]}), 5)
        self.assertEqual(e.expression({"op": "/", "args": [2, 3]}, {}, {}), Fraction(2, 3))
        for index in [-1, 2]:
            with self.assertRaises(e.ContractError):
                e.expression({"table": "t", "index": "k"}, {"k": index}, {"t": [2, 5]})

    def test_structural_claims_validate_each_witness_schema(self):
        for rule, witness in [("inverse_pair_library", {"library_closure_hash": "a" * 64, "claim_index": 0}),
                              ("translation_lemma", {"V": [], "W": [], "X": [], "B": [], "frame": [0, 1]})]:
            claim = {"kind": "structural", "rule": rule, "subclaims": [0], "witness": witness,
                     "invocation": {"args": "all", "budget": "all"}}
            self.assertIsNone(e.Certificate.claim(claim, 1))
            bad = copy.deepcopy(claim); bad["witness"]["unexpected"] = []
            with self.assertRaises(e.ContractError):
                e.Certificate.claim(bad, 1)


class InheritedReview(unittest.TestCase):
    def test_oracle_and_token_entries_require_explicit_budget(self):
        target = sibling(ROOT, "bennett-targets") / "targets/ideal-all-to-all.json"
        requests = [
            ("ret-delivery-source-gap.bisa", []),
            ("token-alias-source-gap.bisa", ["--params", '[["1","0","0","0"],["1","0","0","0"]]', "--token-aliases", "[0,1]"]),
        ]
        for fixture, options in requests:
            command = [str(ROOT / "tests/fixtures" / fixture), "--target", str(target), "--region", "root", *options]
            with self.subTest(fixture=fixture), contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(e.main(command), 1)
                self.assertEqual(out.getvalue(), "")
                self.assertIn("--budget", err.getvalue())
            with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(e.main(command + ["--budget", "0,0,0,0"]), 0, err.getvalue())
                self.assertEqual(json.loads(out.getvalue())["invocation"]["budget"], ["0"] * 4)

    def test_native_model_is_preserved_hash_bound_and_closed_schema(self):
        doc = e.loads((ROOT / "data/ideal-four-clique.json").read_text())
        # §8.3 K86's X example, with the resolved c=0 operand permutation.
        zero, one = ["0", "1"], ["1", "1"]
        model = {"version": "bennett.native-model/1", "kind": "unitary", "arity": 1,
                 "basis": ["t"], "parameter_bindings": {"k": "k", "c": "c"},
                 "control_models": {"kind": "controlled_U", "controls": "c", "disabled": "identity"},
                 "data": {"matrix": [[[zero, zero], [one, zero]], [[one, zero], [zero, zero]]]},
                 "operand_map": [0]}
        original = e.Target.read(e.jcs(doc))
        doc["gates"][0]["realisation_model"] = model
        supplied = e.Target.read(e.jcs(doc))
        self.assertEqual(supplied.doc["gates"][0]["realisation_model"], model)
        self.assertNotEqual(supplied.hash, original.hash)
        self.assertEqual(supplied.gate("x", ["data"], 0).time, original.gate("x", ["data"], 0).time)
        for bad in [None, {**model, "typo": 0}, {key: value for key, value in model.items() if key != "operand_map"}]:
            with self.subTest(model=bad), self.assertRaises(e.ContractError):
                doc["gates"][0]["realisation_model"] = bad
                e.Target.read(e.jcs(doc))


if __name__ == "__main__":
    unittest.main()
