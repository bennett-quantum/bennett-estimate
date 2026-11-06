"""Unit contracts for the interpreter and source-lowering phases."""
import unittest
from unittest.mock import patch
from test_schedule import ROOT, e, target, make_program


class ClassicalPhases(unittest.TestCase):
    def test_instruction_classifies_classical_dispatch_at_construction(self):
        families = {
            "ARITHMETIC": ["const.i8", "add", "sdiv", "icmp.eq", "sext.i64", "inttoptr", "select"],
            "REGISTER": ["qreg.new", "qreg.free", "qreg.slice", "qreg.from_id"],
            "QUANTUM": ["action_call", "oracle_call", "adj", "ctl"],
            "BRANCH": ["br"], "RETURN": ["ret"], "FAULT": ["trap", "fault"],
            "CALL": ["call"], "UNCALL": ["uncall"], "ALLOCATE": ["alloc"], "FREE": ["free"],
            "MEMORY": ["load.i64", "store.i8"], "MINT": ["budget.mint"],
            "MEASURE": ["measure", "measure.i128"], "EFFECT": ["effect"], "OTHER": ["qloop", "hostcall"],
        }
        for family, opcodes in families.items():
            for opcode in opcodes:
                with self.subTest(opcode=opcode):
                    self.assertEqual(e.Instruction(opcode, [], []).classical_kind.name, family)

    def machine(self):
        obj = e.Object.read((ROOT / "examples/native-pair-program.bisa").read_text())
        t = target()
        source = e.Source(obj, t, e.Catalog((ROOT / "data/ref-0.9.json").read_text(), t))
        return e.ClassicalMachine(source, obj.functions["main"], [], None)

    def test_arithmetic_resolves_signed_values_and_faults(self):
        machine = self.machine()
        values = {"minus7": (249, 8), "two": (2, 8), "zero": (0, 8)}
        result, failed = machine.arithmetic(e.Instruction("sdiv", ["minus7", "two"], ["r"]), values.__getitem__)
        self.assertEqual((result, failed), ((253, 8), False))
        result, failed = machine.arithmetic(e.Instruction("sdiv", ["minus7", "zero"], ["r"]), values.__getitem__)
        self.assertEqual((result, failed), (None, True))

    def test_register_phase_and_snapshot_restore_lifetimes(self):
        machine = self.machine()
        original = machine.register_snapshot()
        p, result, failed = machine.register_operation(e.Instruction("qreg.new", ["data", "3"], ["q"]),
                                                      lambda name: None, lambda name: None, lambda n, minimum=0: int(n))
        self.assertFalse(failed)
        self.assertEqual(p.delta[("data", "clean")], 3)
        self.assertEqual(machine.register_width(machine.registers[result[0].identity]), 3)
        restored = machine.restore_registers(original)
        self.assertEqual(restored.delta[("data", "clean")], -3)
        self.assertEqual(machine.physical, {})

    def test_execution_combines_quantum_and_classical_phases(self):
        machine = self.machine()
        with patch.object(machine, "quantum_call", wraps=machine.quantum_call) as calls:
            profile, steps = machine.run()
        self.assertEqual(calls.call_count, 1)
        self.assertEqual((steps, machine.source.classical_status), (7, "COMPLETED"))
        self.assertEqual(profile.resources(machine.source.target),
                         {"gate_count": 8, "time": 25, "peak_qubits[data]": 4, "qubit_second[data]": 84})


class SourcePhases(unittest.TestCase):
    def source(self):
        sig = {"abi": "0.9", "tier": "q", "kind": "perm_action", "mut": [1], "in": [], "mem": [], "args": [], "bounds": []}
        obj = make_program("perm_action @root (q:wire) () () () ()\n^entry():\naction_call @child (q) () () ()\nperm_action @child (q:wire) () () () ()\n^entry():\nx q", {"root": sig, "child": sig})
        t = target(); catalog = e.Catalog((ROOT / "data/ref-0.9.json").read_text(), t)
        source = e.Source(obj, t, catalog)
        source.calls = ["root"]; source.budgets = [["0"] * 4]
        return source

    def test_action_call_phase_binds_and_expands_the_callee(self):
        source = self.source(); env = {"q": e.Bundle("q", 1, "data")}
        node = source.lower_action_call(source.obj.functions["root"].code[0], env, {}, (), False)
        self.assertEqual(source.catalog.body([node], env).resources(source.target, {"data": 1}),
                         {"gate_count": 1, "time": 1, "peak_qubits[data]": 1, "qubit_second[data]": 1})

    def test_oracle_and_inplace_phases_reject_incomplete_bindings(self):
        source = self.source()
        with self.assertRaisesRegex(e.ContractError, "oracle_call needs"):
            source.lower_oracle_call(e.Instruction("oracle_call", [], []), {}, {}, (), "root")
        with self.assertRaisesRegex(e.ContractError, "qinplace needs"):
            source.lower_qinplace(e.Instruction("qinplace", [], []), {}, {}, (), False, "root", {})


if __name__ == "__main__":
    unittest.main()
