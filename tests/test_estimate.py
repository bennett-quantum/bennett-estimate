import importlib.util
import json
import os
from pathlib import Path
import subprocess
import unittest
from fractions import Fraction as F

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("estimate", ROOT / "src/estimate.py")
e = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = e
spec.loader.exec_module(e)


def object_with_signatures(functions, signatures, layout=None, devices=None):
    symbols={str(i):{"name":name,"kind":sig["kind"],"signature":sig,"interface_hash":"0"*64} for i,(name,sig) in enumerate(signatures.items())}
    def text():
        value="bennett-object isa=0.9 object=0.9 launch=0.9 sched=0.9 cert=0.9 coverage=0.9 target=0.9 ptr_width=32\n\nsection symbols\n"+e.jcs(symbols)+"\n\nsection functions\n"+functions+"\n"
        if devices is not None: value+="\nsection devices\n"+e.jcs(devices)+"\n"
        if layout is not None: value+="\nsection layout\n"+e.jcs(layout)+"\n"
        return value
    identities=e.Object.read(text()).identities()
    for symbol in symbols.values(): symbol["interface_hash"]=identities[symbol["name"]]
    return e.Object.read(text())


class Arithmetic(unittest.TestCase):
    def test_jcs_large_integer_and_utf16_class_order(self):
        self.assertEqual(e.jcs(9007199254740993),"9007199254740992")
        doc=e.loads((ROOT.parent/"bennett-targets/targets/ideal-all-to-all.json").read_text())
        desc={"capacity":"unbounded","dirty_rate":1,"qubit_second":1}
        doc["classes"]={"\ue000":desc,"😀":desc}
        c=e.Catalog((ROOT/"data/ref-0.9.json").read_text(),e.Target.read(e.jcs(doc)))
        self.assertEqual(c.default_class,"😀")

    def test_upward_34(self):
        self.assertEqual(e.decimal_up(F(1, 3)), "0." + "3" * 33 + "4")
        self.assertEqual(e.decimal_up(F(2, 3)), "0." + "6" * 33 + "7")
        self.assertEqual(e.decimal_up(F(1, 8)), "0.125")
        self.assertEqual(e.decimal_up(F(10**40 + 1)), str(10**40 + 10**7))
        self.assertEqual(e.decimal_up(F(1, 10**50)), "0." + "0" * 49 + "1")
        self.assertEqual(e.escape("B]%[é"), "B%5D%25%5B%C3%A9")

    def test_expression_epsilon_decades(self):
        for eps, index in [("1", 0), (".1", 1), (".1001", 1), (".0999", 2), (".001", 3), (".000999", 4)]:
            self.assertEqual(e.expression({"table": "t", "index": "eps_decade"}, {"eps": F(eps)}, {"t": list(range(5))}), index)
        self.assertEqual(e.expression({"op": "log2inv_eps", "args": []}, {"eps": F(1, 9)}, {}), 4)
        for eps in [F(0), F(2)]:
            with self.assertRaises(e.ContractError):
                e.expression({"table": "t", "index": "eps_decade"}, {"eps": eps}, {"t": [0]})
        with self.assertRaises(e.ContractError):
            e.expression({"op": "/", "args": [1, 0]}, {}, {})


class Targets(unittest.TestCase):
    def test_published_targets(self):
        paths = sorted((ROOT.parent / "bennett-targets/targets").glob("*.json"))
        self.assertGreaterEqual(len(paths), 3, "published target corpus is required")
        for path in paths:
            t = e.Target.read(path.read_text())
            self.assertEqual(len(t.hash), 64)
            self.assertEqual(t.gate("x", ["data"], 0).counts["gate_count"], 1)

    def test_decimal_text_preserved(self):
        t = e.Target.read((ROOT.parent / "bennett-targets/targets/superconducting-grid-illustrative.json").read_text())
        self.assertEqual(t.gate("cx", ["data", "data"], 1).time, F("0.00019999999999999998"))

    def test_unknown_and_negative(self):
        doc = json.loads((ROOT.parent / "bennett-targets/targets/ideal-all-to-all.json").read_text())
        doc["oops"] = 1
        with self.assertRaises(e.ContractError): e.Target.read(json.dumps(doc), canonical=False)
        del doc["oops"]
        doc["gates"][0]["cost"]["time"] = -1
        with self.assertRaises(e.ContractError): e.Target.read(json.dumps(doc), canonical=False)

    def test_scheme_target_order_and_exact_entry_prohibition(self):
        doc=e.loads((ROOT.parent/"bennett-targets/targets/ideal-all-to-all.json").read_text())
        desc={"capacity":"unbounded","dirty_rate":1,"qubit_second":1}
        doc["classes"]={"alpha":desc,"beta":desc}
        doc["gates"]=[{"op":"cx","classes":pattern,"controls":{"min":1,"max":1},"epsilon":0,"cost":{"gate_count":1,"time":time}} for pattern,time in [(["alpha","beta"],1),(["beta","alpha"],2)]]
        doc["schemes"]=[{"name":"swap-via-cx","realises":{"op":"swap","controls":{"min":0,"max":0}},"ancillae":{"count":0,"state":"clean","class":"alpha"},"template":[{"gate":"cx","wires":w} for w in [["t","t2"],["t2","t"],["t","t2"]]]}]
        t=e.Target.read(e.jcs(doc))
        self.assertEqual(t.gate("swap",["alpha","beta"],0).time,4)
        self.assertEqual(t.gate("swap",["alpha","beta"],0).counts["gate_count"],3)
        doc["gates"][0]["cost"]["time"]={"var":"eps"}
        with self.assertRaises(e.ContractError): e.Target.read(e.jcs(doc))


class Profiles(unittest.TestCase):
    def test_sequence_and_repeat(self):
        alloc = e.Profile.allocation("data", "clean", 2)
        gate = e.Profile(time=F(1, 3), counts={"g": F(1)})
        p = alloc.then(gate.repeat(3)).then(e.Profile.allocation("data", "clean", -2))
        self.assertEqual(p.time, 1)
        self.assertEqual(p.area[("data", "clean")], 2)
        self.assertEqual(p.peak[("data", "clean")], 2)
        self.assertEqual(p.repeat(2**40).counts["g"], 3 * 2**40)


class Catalog(unittest.TestCase):
    def setUp(self):
        self.t = e.Target.read((ROOT.parent / "bennett-targets/targets/ideal-all-to-all.json").read_text())
        self.c = e.Catalog((ROOT / "data/ref-0.9.json").read_text(), self.t)

    def test_published_identity(self):
        self.assertEqual(self.c.hash, "5de4e4995350313e50217880ba1b95de39cd043283b726337d4894efb005d197")
        self.assertEqual(len(self.c.recipes), 219)

    def test_qxor_and_ripple(self):
        wires = {n: e.Bundle(n, 2, "data") for n in ["a", "b", "t", "s"]}
        p = self.c.recipe("qxor", [2], wires)
        self.assertEqual(p.counts["gate_count"], 2)
        p = self.c.recipe("bind.value.add", [2, "a", "b", "t"], wires)
        self.assertEqual(p.gates, {"cx": 62, "ccx": 16})
        self.assertEqual(p.time, 158)
        self.assertTrue(all(v == 0 for v in p.delta.values()))

    def test_billion_loop_is_closed_form(self):
        wires = {"t": e.Bundle("t", 1, "data")}
        body = [{"gate": "x", "wires": ["t"]}]
        p = self.c.recipe("qloop", [2**40, body], wires)
        self.assertEqual(p.time, 2**40)
        self.assertLess(self.c.visits, 10)

    def test_nested_captured_loops(self):
        body=[{"invoke":"qloop","args":[3,[{"gate":"x","wires":["t"]}]]}]
        p=self.c.recipe("qloop",[7,body],{"t":e.Bundle("t",1,"data")})
        self.assertEqual(p.time,21)

    def test_indexed_controls_and_middle_alias_are_not_hoisted(self):
        doc=e.loads(e.jcs(self.t.doc))
        next(g for g in doc["gates"] if g["op"]=="cx")["cost"]["time"]={"var":"c"}
        c=e.Catalog((ROOT/"data/ref-0.9.json").read_text(),e.Target.read(e.jcs(doc)))
        env={"s":e.Bundle("s",2,"data"),"t":e.Bundle("t",2,"data")}
        node={"for":"i","from":0,"to":2,"body":[{"gate":"cx","wires":['s["i"]','t["i"]']}]}
        self.assertEqual(c.body([node],env,(("s",0,"data"),)).time,3)
        env={"s":e.Bundle("s",3,"data"),"t":e.Bundle("t",3,"data")}
        bad={"for":"i","from":0,"to":3,"body":[{"gate":"ccx","wires":['s["i"]','s[["-",2,"i"]]','t["i"]']}]}
        with self.assertRaises(e.ContractError): c.body([bad],env)
        each={"each":"v","in":"s","body":[{"gate":"cx","wires":["v","t[0]"]}]}
        self.assertEqual(c.body([each],env,(("s",0,"data"),)).time,5)

    def test_dispatch_closed_form_matches_literal_traversal(self):
        for A in [0,1,2,3]:
            C,W=1<<A,3
            env={"a":e.Bundle("a",A,"data"),"cells":e.Bundle("cells",C*W,"data"),"v":e.Bundle("v",W,"data")}
            for name in ["dispatch.copy","dispatch.store","dispatch.exchange"]:
                self.c.closed_form=False
                scalar=self.c.recipe(name,[A,C,W,"a","cells","v"],env)
                self.c.closed_form=True
                fast=self.c.recipe(name,[A,C,W,"a","cells","v"],env)
                self.assertEqual(fast,scalar,(A,name))
        A,C,W=20,2**20,8
        env={"a":e.Bundle("a",A,"data"),"cells":e.Bundle("cells",C*W,"data"),"v":e.Bundle("v",W,"data")}
        before=self.c.visits
        p=self.c.recipe("dispatch.copy",[A,C,W,"a","cells","v"],env)
        self.assertGreater(p.time,C*W)
        self.assertLess(self.c.visits-before,500)


class Objects(unittest.TestCase):
    def test_controlled_action_call_and_matching_schedule(self):
        path=ROOT.parent/"bennett-isa-spec/conformance/fixtures/controlled-action-09"
        obj=e.Object.read((path/"controlled.bisa").read_text())
        target=e.Target.read((path/"target.json").read_text())
        with self.assertRaisesRegex(e.ContractError,"explicit schedule selectors"):
            e.estimate(obj,target,"controlled",[],["0"]*4)
        ideal=e.Target.read((ROOT.parent/"bennett-targets/targets/ideal-all-to-all.json").read_text())
        result=e.estimate(obj,ideal,"controlled",[],["0"]*4)
        self.assertEqual(result["gates"],{"x":"1"})
        self.assertEqual(result["resources"]["time"],"1")
        self.assertEqual(result["resources"]["peak_qubits[data]"],"2")

    def test_classical_callee_fault_and_effect_validation(self):
        sig={"abi":"0.9","kind":"r","tier":"r","params":[],"results":[]}
        obj=object_with_signatures("fn r @bad () () () () ()\n^entry():\nfault 9\nfn r @outer () () () () ()\n^entry():\ncall @bad\nunused = const.i8 7\nret",{"bad":sig,"outer":sig})
        t=e.Target.read((ROOT/"data/classical-step-16.json").read_text())
        self.assertEqual(e.estimate(obj,t,"outer",[],["0"]*4)["classical_steps"],"2")
        layout={"ptr_width":32,"H":4,"A_tab":2,"S_cells":0,"null_size":1,"heap_base":1,"heap_limit_max":15,"globals":{},"interface_regions":{}}
        obj=object_with_signatures("fn r @bad () () () () ()\n^entry():\np = const.i32 0\nn = const.i32 1\neffect console.write p n\nret",{"bad":sig},layout,{"models":{"console":{"version":"0.9"}},"services":{}})
        self.assertEqual(e.estimate(obj,t,"bad",[],["0"]*4)["classical_steps"],"3")

    def test_normative_objects_and_hashes(self):
        for path in sorted((ROOT / "tests/fixtures").glob("example*.bisa")):
            obj = e.Object.read(path.read_text())
            self.assertTrue(obj.functions)
            hashes = obj.identities()
            for record in obj.sections["symbols"].values():
                self.assertEqual(hashes[record["name"]], record["interface_hash"])

    def test_rung3_read_and_classical_steps(self):
        path = ROOT.parent / "bennett-conformance/ladder/rung-3/fixtures/executor-control.bisa"
        obj = e.Object.read(path.read_text())
        self.assertEqual(len(obj.functions), 12)
        t = e.Target.read((ROOT.parent / "bennett-targets/targets/ideal-all-to-all.json").read_text())
        doc = e.loads(e.jcs(t.doc))
        doc["ptr_widths_supported"] = [16, 32, 64]
        t = e.Target.read(e.jcs(doc))
        result = e.estimate(obj, t, "sum", ["3"], ["0"]*4)
        self.assertEqual(result["resources"]["time"], "21")
        self.assertEqual(result["label"], "exact")
        bound=e.estimate(obj,t,"sum",["3"],["0"]*4,step_bound=30)
        self.assertEqual(bound["label"],"bound")
        self.assertEqual(bound["resources"]["time"],"30")
        self.assertNotIn("exact_resources",bound)
        self.assertTrue(bound["bound_assumptions"])
    def test_borrow_action(self):
        obj = e.Object.read((ROOT / "tests/fixtures/example3.bisa").read_text())
        t = e.Target.read((ROOT.parent / "bennett-targets/targets/ideal-all-to-all.json").read_text())
        result = e.estimate(obj, t, "borrow_demo", [], ["0"]*4)
        self.assertEqual(result["resources"]["gate_count"], "4")
        self.assertEqual(result["resources"]["time"], "4")
        self.assertEqual(result["resources"]["peak_qubits[data]"], "3")
        self.assertEqual(result["resources"]["qubit_second[data]"], "12")

    def test_reader_rejects_noncanonical_and_unknown(self):
        text = (ROOT / "tests/fixtures/example3.bisa").read_text()
        for bad in [text.replace("section symbols", "section mystery"), text.replace("cx x", "cx  x"), text.replace("cx x", "mystery x"), text.replace('"mut":[1]','"mut":[2]'), text.replace("\n", "\r\n"), text+"\nsection symbols\n{}\n"]:
            with self.assertRaises(e.ContractError): e.Object.read(bad)

    def test_padded_oracle_budget_and_large_budget(self):
        obj = e.Object.read((ROOT / "tests/fixtures/example1.bisa").read_text())
        t = e.Target.read((ROOT.parent / "bennett-targets/targets/ideal-all-to-all.json").read_text())
        results = [e.estimate(obj,t,"inc8",[],[str(b),"0","0","0"]) for b in [0,1,2,3,2**40]]
        counts = [int(r["resources"]["gate_count"]) for r in results]
        self.assertGreater(counts[1],counts[0])
        self.assertEqual(counts[2]-counts[1],counts[1]-counts[0])
        self.assertEqual(counts[-1],counts[0]+2**40*(counts[1]-counts[0]))
        self.assertEqual(results[1]["summary_operations"],results[-1]["summary_operations"])
        self.assertEqual(results[-1]["label"],"exact")

    def test_million_cell_source_lookup_without_gate_materialisation(self):
        obj=e.Object.read((ROOT/"examples/memory-lookup-2pow20.bisa").read_text())
        t=e.Target.read((ROOT.parent/"bennett-targets/targets/ideal-all-to-all.json").read_text())
        result=e.estimate(obj,t,"lookup",[],["0"]*4)
        self.assertEqual(result["label"],"exact")
        self.assertGreater(int(result["resources"]["gate_count"]),2**20*1024*8)
        self.assertLess(result["summary_operations"],1000)
        self.assertGreater(int(result["resources"]["peak_qubits[data]"]),2**20*8)


class Certificates(unittest.TestCase):
    def test_published_reader_and_frame_negatives(self):
        text = (ROOT.parent / "bennett-isa-spec/conformance/fixtures/controlled-action-09/certificate.json").read_text()
        cert = e.Certificate.read(text)
        self.assertEqual(cert.doc["versions"]["cert"],"0.9")
        bad=e.loads(text)
        root=next(iter(bad["regions"].values()))
        root["frame"]["scratch"].append({"id":"s","class":"fast","state":"clean","width":{"var":"k"}})
        with self.assertRaises(e.ContractError): e.Certificate.read(e.jcs(bad))
        bad=e.loads(text);bad["bindings"]["closure_hash"]="0"*63
        with self.assertRaises(e.ContractError): e.Certificate.read(e.jcs(bad))

    def test_reduced_resource_rows(self):
        with self.assertRaises(e.ContractError): e.Certificate.exact_rows({"x":{"numerator":"2","denominator":"6"}})
        with self.assertRaises(e.ContractError): e.Certificate.exact_rows({"x":{"numerator":"0","denominator":"2"}})
        self.assertEqual(e.Certificate.exact_rows({"x":{"numerator":"1","denominator":"3"}}),{"x":F(1,3)})


class CommandLine(unittest.TestCase):
    def test_deterministic_and_failure(self):
        binary=os.environ["BENNETT_ESTIMATE_BIN"]
        command=[binary,str(ROOT/"tests/fixtures/example3.bisa"),"--target",str(ROOT.parent/"bennett-targets/targets/ideal-all-to-all.json")]
        a=subprocess.run(command,capture_output=True,text=True,timeout=30)
        b=subprocess.run(command,capture_output=True,text=True,timeout=30)
        self.assertEqual(a.returncode,0,a.stderr)
        self.assertEqual(a.stdout,b.stdout)
        self.assertEqual(json.loads(a.stdout)["resources"]["gate_count"],"4")
        bad=subprocess.run(command+["--params",'["1"]'],capture_output=True,text=True,timeout=30)
        self.assertNotEqual(bad.returncode,0)
        self.assertEqual(bad.stdout,"")

    def test_differential_rung3_and_rung2_inventory(self):
        spec=importlib.util.spec_from_file_location("differential",ROOT/"scripts/differential.py")
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        report=module.run(ROOT,Path(os.environ["BENNETT_ESTIMATE_BIN"]))
        self.assertEqual([r["steps"] for r in report["rung3"]["rows"]],[6,11,21,41,1281])
        self.assertIn(report["rung2"]["status"],["unavailable","objects_available"])


if __name__ == "__main__":
    unittest.main()
