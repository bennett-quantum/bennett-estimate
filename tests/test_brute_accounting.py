"""Third-implementation checks: no production Profile/Ledger algebra in the oracle."""
from fractions import Fraction as F
import itertools
import unittest
from unittest.mock import patch

from test_estimate import ROOT, e
from test_schedule import target, make_object
from brute_ledger import BruteLedger, dispatch


class BruteAccounting(unittest.TestCase):
    def test_paper_witness_for_the_independent_dispatch_ledger(self):
        ledger = BruteLedger()
        dispatch(ledger, address_width=1, cells=1, width=2)
        self.assertEqual((ledger.time, ledger.gates, ledger.peak["data"], ledger.area["data"]), (56, 56, 7, 334))

    def test_summary_literal_and_brute_dispatch_agree_on_every_row(self):
        t = target()
        for cells, width, inherited, exchange in itertools.product([0, 1, 3], [0, 2], [0, 1], [False, True]):
            address_width = max(1, cells.bit_length())
            brute = BruteLedger(cost=lambda op, c: F(c + 2, 3))
            dispatch(brute, address_width, cells, width, inherited, exchange)
            doc = e.loads(e.jcs(t.doc))
            for gate in doc["gates"]:
                gate["cost"]["time"] = {"op": "/", "args": [{"op": "+", "args": [{"var": "c"}, 2]}, 3]}
            catalog = e.Catalog((ROOT / "data/ref-0.9.json").read_text(), e.Target.read(e.jcs(doc)))
            env = {"address": e.Bundle("address", address_width, "data"), "stack": e.Bundle("stack", cells * 3, "data"), "v": e.Bundle("v", width, "data")}
            controls = tuple(("external", i, "data") for i in range(inherited))
            recipe = "stack.exchange" if exchange else "stack.copy"
            with self.subTest(cells=cells, width=width, inherited=inherited, exchange=exchange):
                for closed in [True, False]:
                    catalog.closed_form = closed
                    profile = catalog.recipe(recipe, [address_width, cells, 3, width, "address", "stack", "v"], env, controls)
                    rows = profile.resources(catalog.target)
                    self.assertEqual(rows["time"], brute.time)
                    self.assertEqual(rows["gate_count"], brute.gates)
                    self.assertEqual(rows["peak_qubits[data]"], brute.peak.get("data", 0))
                    self.assertEqual(rows["qubit_second[data]"], brute.area.get("data", 0))
                    self.assertTrue(all(v == 0 for v in profile.delta.values()))

    def test_source_loop_summary_frame_and_brute_lifetimes_agree(self):
        signature = {"abi": "0.9", "tier": "q", "kind": "action", "mut": [1], "in": [], "mem": [], "args": [], "bounds": []}
        for repeats, borrowed in itertools.product([0, 1, 3], [False, True]):
            body = f"action @root (q:wire) () () () ()\nregs {{  }} bounds {{{repeats}}}\n^entry():\ns = {'qborrow' if borrowed else 'qalloc'} data 2\nqloop {repeats} {{\nx q\n}}\n{'qreturn' if borrowed else 'qfree'} s"
            obj = make_object(body, {**signature, "bounds": [repeats]})
            brute = BruteLedger()
            brute.allocate("interface", 1)
            brute.allocate("workspace", 2, borrowed=borrowed)
            for _ in range(repeats):
                brute.gate("x", 0)
            brute.release("workspace")
            for frame in [False, True]:
                row = e.estimate(obj, target(), "root", [], ["0"] * 4, include_frame=frame)
                self.assertEqual({k: F(int(v["numerator"]), int(v["denominator"])) for k, v in row["exact_resources"].items()}, brute.resources())

    def test_oracle_detects_a_wrong_summary_area(self):
        brute = BruteLedger(); dispatch(brute, 1, 1, 2)
        c = e.Catalog((ROOT / "data/ref-0.9.json").read_text(), target())
        env = {"address": e.Bundle("a", 1, "data"), "stack": e.Bundle("s", 2, "data"), "v": e.Bundle("v", 2, "data")}
        original = c.dispatch_summary
        def wrong(*args):
            profile = original(*args)
            profile.area[("data", "clean")] += 1
            return profile
        with patch.object(c, "dispatch_summary", wrong):
            profile = c.recipe("stack.copy", [1, 1, 2, 2, "address", "stack", "v"], env)
            with self.assertRaises(AssertionError):
                self.assertEqual(profile.area[("data", "clean")], brute.area["data"])
