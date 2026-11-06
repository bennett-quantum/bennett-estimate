"""Internal defects must not turn into optimization misses or modeled faults."""
import unittest
from unittest.mock import patch
from test_schedule import ROOT, e, target, make_program


class FailFast(unittest.TestCase):
    def catalog(self):
        return e.Catalog((ROOT / "data/ref-0.9.json").read_text(), target())

    def test_index_fold_propagates_malformed_recipe_errors(self):
        c = self.catalog(); env = {"q": e.Bundle("q", 4, "data")}
        nodes = [{"gate": "x", "wires": ['q["i"]']}]
        for error in [TypeError("malformed node"), KeyError("missing wire"), ValueError("bad expression"), e.ContractError("invalid binding")]:
            with self.subTest(error=type(error).__name__), patch.object(e, "wire", side_effect=error), self.assertRaises(type(error)):
                c.safe_index_fold(nodes, "i", 0, 2, env, ())
        with self.assertRaises(KeyError):
            c.safe_index_fold([{"gate": "x"}], "i", 0, 2, env, ())

    def test_non_affine_optimization_decline_keeps_literal_execution(self):
        c = self.catalog(); env = {"q": e.Bundle("q", 4, "data")}
        nodes = [{"gate": "x", "wires": ['q[["*","i","i"]]']}]
        self.assertFalse(c.safe_index_fold(nodes, "i", 0, 2, env, ()))
        profile = c.body([{"for": "i", "from": 0, "to": 2, "body": nodes}], env)
        self.assertEqual((profile.time, profile.counts["gate_count"]), (2, 2))

    def machine(self, heap):
        root = {"abi": "0.9", "tier": "cc", "kind": "cc", "params": [], "results": []}
        oracle = {"abi": "0.9", "tier": "q", "kind": "oracle", "in": [1], "tgt": 1, "fault": 4, "mem": [], "args": []}
        code = f"fn cc @root () () () () ()\n^entry():\nz = const.i64 0\nn = const.i64 {heap}\ntk = budget.mint @o z n z z\nret\noracle @o (x:wire in) (t:wire) (f:wire[4]) () ()\nregs {{  }}\n^entry():\nlift.retval x"
        obj = make_program(code, {"root": root, "o": oracle}); t = target()
        source = e.Source(obj, t, e.Catalog((ROOT / "data/ref-0.9.json").read_text(), t))
        return e.ClassicalMachine(source, obj.functions["root"], [], None)

    def test_mint_does_not_swallow_internal_budget_validation_errors(self):
        machine = self.machine(0)
        with patch.object(e, "validate_budget", side_effect=e.ContractError("broken validator")), self.assertRaisesRegex(e.ContractError, "broken validator"):
            machine.run()

    def test_invalid_mint_remains_a_modeled_fault_with_its_reason(self):
        machine = self.machine(1)
        profile, steps = machine.run()
        self.assertEqual((machine.source.classical_status, steps, profile.time), ("FAILED", 3, 3))
        self.assertEqual(machine.fault_reason, "§5.4: memoryless budget requires heap=stack=depth=0")
        result = e.estimate(machine.source.obj, machine.source.target, "root", [], ["0"] * 4)
        self.assertEqual(result["classical_fault_reason"], machine.fault_reason)
