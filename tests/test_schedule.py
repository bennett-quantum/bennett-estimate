"""Independent schedule/placement/accounting requirements from ISA 0.9."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
from fractions import Fraction as F

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("scheduled_estimate",ROOT/"src/estimate.py")
e=importlib.util.module_from_spec(spec);sys.modules[spec.name]=e;spec.loader.exec_module(e)


def target():
    return e.Target.read((ROOT.parent/"bennett-targets/targets/ideal-all-to-all.json").read_text())


def point(symbol="a"*64,point="entry:0",iteration=()):
    return {"symbol":symbol,"point":point,"iteration":list(iteration),"instance":[]}


def entry(kind="gate",path=(),step="*",phase="*",generated="*",**payload):
    return {"kind":kind,"path":list(path),"step":step,"phase":phase,"generated":generated,kind:payload}


def schedule(entries=(),target_hash="b"*64):
    return {"bindings":{"closure_hash":"a"*64,"target_hash":target_hash,"region":"root","variant":"forward","inherited_controls":0,"budget":[2,0,0,0],"params_hash":e.digest("[]"),"epsilon":0,"expansion":{"name":"ref","version":"0.9","hash":"5de4e4995350313e50217880ba1b95de39cd043283b726337d4894efb005d197"},"scheduler":{"name":"test","version":"1"}},"entries":list(entries)}


class Selectors(unittest.TestCase):
    def test_specificity_per_kind_ties_and_covered_ties(self):
        broad=entry(realisation="native",epsilon_share="0.125")
        same=entry(realisation="native",epsilon_share="0.25")
        narrow=entry(path=[point()],realisation="native")
        alloc=entry("alloc",path=[point()],**{"class":"data"})
        for rows in [[broad,same,narrow,alloc],[narrow,same,alloc,broad]]:
            selectors=e.Schedule(schedule(rows))
            chosen=selectors.pick("gate",[point()],0)
            self.assertEqual(chosen,{"realisation":"native"})
            self.assertNotIn("epsilon_share",chosen)
            self.assertEqual(selectors.pick("alloc",[point()],0),{"class":"data"})
            self.assertIsNone(selectors.pick("start",[point()],0))
        with self.assertRaisesRegex(e.ContractError,"multiple maximal matching"):
            e.Schedule(schedule([broad,same])).pick("gate",[point()],0)

    def test_root_nested_step_and_call_occurrence_context(self):
        outer=point();outer["call_index"]=1;outer["entered_invocation"]=(3,"fwd")
        inner=point("c"*64,"work:2")
        root=entry(step=1,realisation="native")
        nested=entry(path=[{**point(),"call_index":1}],step=3,realisation="chosen")
        selectors=e.Schedule(schedule([root,nested]))
        self.assertEqual(selectors.pick("gate",[outer,inner],0,1,"fwd"),{"realisation":"chosen"})
        self.assertEqual(selectors.pick("gate",[outer],0,1,"fwd"),{"realisation":"native"})
        other={**outer,"call_index":0}
        self.assertEqual(selectors.pick("gate",[other,inner],0,1,"fwd"),{"realisation":"native"})
        self.assertIsNone(selectors.pick("gate",[point()],0,None,None))

    def test_selector_new_keys_do_not_increase_specificity(self):
        a=entry(path=[{**point(),"instance":"*","call_index":"*"}],realisation="native")
        b=entry(path=[{**point(),"instance":[],"call_index":0}],realisation="native")
        with self.assertRaisesRegex(e.ContractError,"multiple maximal matching"):
            e.Schedule(schedule([a,b])).pick("gate",[{**point(),"call_index":0}],0)

    def test_unknown_schema_and_zero_trip_domains(self):
        bad=entry();bad["typo"]=0
        with self.assertRaises(e.ContractError):e.Schedule(schedule([bad]))
        # No operation in an empty generated domain means no tie witness.
        e.Schedule(schedule([entry(),entry()]))


class Accounting(unittest.TestCase):
    def test_disjoint_overlap_resource_and_dependent_start(self):
        t=target();q=e.Bundle("q",2,"data")
        entries=[entry("start",path=[point(point=f"entry:{i}")],time="0") for i in [0,1]]
        ledger=e.Ledger(t,e.Schedule(schedule(entries)))
        ledger.interface("mut:0",q)
        ledger.gate("x",[q.bit(0)],chain=[point(point="entry:0")],ordinal=0)
        ledger.gate("x",[q.bit(1)],chain=[point(point="entry:1")],ordinal=0)
        rows=ledger.finish()
        self.assertEqual(rows["time"],1)
        self.assertEqual(rows["gate_count"],2)
        self.assertEqual(rows["peak_qubits[data]"],2)
        self.assertEqual(rows["qubit_second[data]"],2)
        with self.assertRaisesRegex(e.ContractError,"dependency"):
            ledger=e.Ledger(t,e.Schedule(schedule(entries)));ledger.interface("mut:0",q)
            ledger.gate("x",[q.bit(0)],chain=[point(point="entry:0")],ordinal=0)
            ledger.gate("x",[q.bit(0)],chain=[point(point="entry:1")],ordinal=0)

    def test_class_capacity_fallback_and_zero_rows(self):
        doc=e.loads(e.jcs(target().doc));doc["classes"]={"A":{"capacity":1,"qubit_second":1,"dirty_rate":1},"B":{"capacity":2,"qubit_second":1,"dirty_rate":e.loads("0.25")},"idle":{"capacity":0,"qubit_second":1,"dirty_rate":1}}
        t=e.Target.read(e.jcs(doc));ledger=e.Ledger(t,e.Schedule(schedule()))
        a=e.Bundle("a",1,"any");b=e.Bundle("b",2,"any",state="borrowed")
        ledger.allocate(a,chain=[point()],ordinal=0)
        ledger.allocate(b,chain=[point()],ordinal=1)
        self.assertEqual(ledger.resolved_class(a),"A")
        self.assertEqual(ledger.resolved_class(b),"B")
        ledger.gate("x",[b.bit(0)],chain=[point()],ordinal=2)
        ledger.release(b,chain=[point()],ordinal=3);ledger.release(a,chain=[point()],ordinal=4)
        rows=ledger.finish()
        self.assertEqual(rows["peak_qubits[B]"],2)
        self.assertEqual(rows["qubit_second[B]"],F(1,2))
        self.assertEqual(rows["peak_qubits[idle]"],0)

    def test_topology_adjacency_and_retained_placements(self):
        doc=e.loads(e.jcs(target().doc))
        doc["topology"]={"vertices":[{"class":"data"} for _ in range(4)],"edges":[[0,1],[0,2],[1,3],[2,3]]}
        t=e.Target.read(e.jcs(doc));q=e.Bundle("q",2,"data")
        good=schedule();good["interface_vertices"]=[[0,1]]
        ledger=e.Ledger(t,e.Schedule(good));ledger.interface("mut:0",q)
        ledger.gate("cx",[q.bit(0),q.bit(1)],chain=[point()],ordinal=0)
        self.assertEqual(ledger.finish()["time"],1)
        bad=schedule();bad["interface_vertices"]=[[0,3]]
        ledger=e.Ledger(t,e.Schedule(bad));ledger.interface("mut:0",q)
        with self.assertRaisesRegex(e.ContractError,"§17 item 15"):
            ledger.gate("cx",[q.bit(0),q.bit(1)],chain=[point()],ordinal=0)

    def test_max_parallel_and_live_peak_concurrency(self):
        doc=e.loads(e.jcs(target().doc));doc["capabilities"]["max_parallel"]=1
        t=e.Target.read(e.jcs(doc));q=e.Bundle("q",2,"data")
        starts=[entry("start",path=[point(point=f"entry:{i}")],time=0) for i in [0,1]]
        ledger=e.Ledger(t,e.Schedule(schedule(starts)));ledger.interface("mut:0",q)
        ledger.gate("x",[q.bit(0)],chain=[point(point="entry:0")],ordinal=0)
        with self.assertRaisesRegex(e.ContractError,"max_parallel"):
            ledger.gate("x",[q.bit(1)],chain=[point(point="entry:1")],ordinal=0)


if __name__=="__main__":unittest.main()
