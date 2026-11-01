"""Independent schedule/placement/accounting requirements from ISA 0.9."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
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


def make_object(text,signature):
    return make_program(text,{"root":signature})


def make_program(text,signatures,data=None):
    records={str(i):{"name":name,"kind":sig["kind"],"signature":sig,"interface_hash":"0"*64} for i,(name,sig) in enumerate(signatures.items())}
    header="bennett-object isa=0.9 object=0.9 launch=0.9 sched=0.9 cert=0.9 coverage=0.9 target=0.9 ptr_width=32\n\nsection symbols\n"
    def document():return header+e.jcs(records)+"\n\nsection functions\n"+text+"\n"+("\nsection data\n"+"\n".join(n+" "+v for n,v in data.items())+"\n" if data else "")
    obj=e.Object.read(document())
    for record in records.values():record["interface_hash"]=obj.identities()[record["name"]]
    return e.Object.read(document())


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

    def test_decimal_fields_are_decimal_text(self):
        with self.assertRaises(e.ContractError):e.Schedule(schedule([entry("start",time="1/3")]))
        with self.assertRaises(e.ContractError):e.Schedule(schedule([entry(epsilon_share="1/3")]))


class Accounting(unittest.TestCase):
    def test_qinplace_private_leaf_order_and_call_occurrences(self):
        action={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1],"in":[],"mem":[],"args":["token"],"bounds":[]}
        oracle={"abi":"0.9","tier":"q","kind":"oracle","in":[1],"tgt":1,"fault":4,"mem":[],"args":[]}
        obj=make_program("perm_action @root (x:wire) () () (tk:token) ()\n^entry():\nqinplace @identity @identity tk x\noracle @identity (x:wire in) (t:wire) (f:wire[4]) () ()\nregs { r:reg[1] }\n^entry():\nr = lift.mov x\nlift.retval r",{"root":action,"identity":oracle})
        t=target();budget=["2","0","0","0"]
        one=e.estimate(obj,t,"identity",[],budget)
        result=e.estimate(obj,t,"root",[budget],["0"]*4,include_frame=True)
        self.assertEqual(F(result["resources"]["time"]),2*F(one["resources"]["time"])+1)
        self.assertEqual(F(result["resources"]["qubit_second[data]"]),2*F(one["resources"]["qubit_second[data]"])+6)
        self.assertEqual([c["path"][-1]["call_index"] for c in result["invocation_contexts"][1:]],[0,1])
        self.assertEqual([r["width"] for r in result["frame"]["scratch"][:2]],[1,4])
        # A caller allocation selector has its own ordinal space, excluding
        # every gate and allocation inside either oracle invocation.
        doc=e.loads(e.jcs(t.doc));doc["classes"]["special"]=dict(doc["classes"]["data"])
        special=e.Target.read(e.jcs(doc))
        root=e.estimate(obj,special,"root",[budget],["0"]*4)
        obj.sections["schedule"]=root["effective_schedule"]
        obj.sections["schedule"]["entries"]=[entry("alloc",path=[point(obj.symbol("root")["interface_hash"])],generated=0,**{"class":"special"})]
        result=e.estimate(obj,special,"root",[budget],["0"]*4)
        self.assertEqual([r["class"] for r in result["frame"]["scratch"][:2]],["special","data"])

    def test_two_oracle_call_tokens_are_resolved_per_invocation(self):
        sig={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1,4],"in":[],"mem":[],"args":["token","token"],"bounds":[]}
        oracle={"abi":"0.9","tier":"q","kind":"oracle","in":[],"tgt":1,"fault":4,"mem":[],"args":[]}
        obj=make_program("perm_action @root (t:wire, f:wire[4]) () () (a:token, b:token) ()\n^entry():\noracle_call @child a () t f () ()\noracle_call @child b () t f () ()\noracle @child () (t:wire) (f:wire[4]) () ()\nregs { r:reg[1] }\n^entry():\nr = lift.const.i1 1\nlift.retval r",{"root":sig,"child":oracle})
        t=target();a=["1","0","0","0"];b=["2","0","0","0"]
        first=e.estimate(obj,t,"child",[],a);second=e.estimate(obj,t,"child",[],b)
        result=e.estimate(obj,t,"root",[a,b],["0"]*4,include_frame=True)
        for row in ["time","qubit_second[data]","gate_count"]:
            self.assertEqual(F(result["resources"][row]),F(first["resources"][row])+F(second["resources"][row]),row)
        self.assertEqual([r["width"] for r in result["frame"]["history"]],[6,6,6])
        contexts=result["invocation_contexts"]
        self.assertEqual([c["invocation"]["budget"] for c in contexts],[ ["0"]*4,a,b])
        self.assertEqual([c["path"][-1]["point"] for c in contexts[1:]],["entry:0","entry:1"])
        # A selector through the second edge reads its B=2 oracle level;
        # empty-path selectors would still read the action root (no step).
        obj.sections["schedule"]=result["effective_schedule"]
        obj.sections["schedule"]["entries"]=[entry(path=[point(obj.symbol("root")["interface_hash"],"entry:1")],step=2,phase="rev",realisation="missing")]
        with self.assertRaisesRegex(e.ContractError,"realisation"):
            e.estimate(obj,t,"root",[a,b],["0"]*4)

    def test_whole_intrinsic_cleanup_recompute_and_nonemitting_carrier(self):
        sig={"abi":"0.9","tier":"q","kind":"perm_action","mut":[],"in":[2],"mem":[],"args":[],"bounds":[]}
        obj=make_object("perm_action @root () (s:wire[2] in) () () ()\n^entry():\nd = qcopy s\nquncopy s d",sig)
        t=target();baseline=e.estimate(obj,t,"root",[],["0"]*4)
        obj.sections["schedule"]=baseline["effective_schedule"]
        chosen=entry("cleanup",path=[point(obj.symbol("root")["interface_hash"],"entry:1")],generated=0,realisation="recompute")
        obj.sections["schedule"]["entries"]=[chosen]
        result=e.estimate(obj,t,"root",[],["0"]*4)
        self.assertEqual(result["resources"]["time"],"8")
        self.assertEqual(result["resources"]["peak_qubits[data]"],"6")
        self.assertEqual(result["resources"]["qubit_second[data]"],"44")
        self.assertEqual(result["gates"],{"cx":"8"})
        self.assertEqual(len(result["cleanup_decisions"]),1)
        obj.sections["schedule"]["entries"]=[chosen,chosen]
        with self.assertRaisesRegex(e.ContractError,"multiple maximal matching"):
            e.estimate(obj,t,"root",[],["0"]*4)
        for record in obj.sections["schedule"]["entries"]:record["generated"]=1
        result=e.estimate(obj,t,"root",[],["0"]*4)
        self.assertEqual(result["exact_resources"],baseline["exact_resources"])

    def test_scheduled_action_adjoint_replaces_source_before_expansion(self):
        sig={"abi":"0.9","tier":"q","kind":"perm_action","mut":[2],"in":[2],"mem":[],"args":[],"bounds":[]}
        obj=make_program("perm_action @root (t:wire[2]) (s:wire[2] in) () () ()\n^entry():\nadj action_call @child (t) (s) () ()\nperm_action @child (t:wire[2]) (s:wire[2] in) () () ()\n^entry():\nd = qcopy s\nqxor d t\nquncopy s d",{"root":sig,"child":sig})
        events=[];original=e.Ledger
        class Recording(original):
            def allocate(self,b,**kw):
                events.append(("alloc",kw["chain"][-1]["point"],kw["ordinal"]))
                return super().allocate(b,**kw)
            def release(self,b,**kw):
                events.append(("release",kw["chain"][-1]["point"],kw["ordinal"]))
                return super().release(b,**kw)
            def gate(self,op,wires,controls=(),**kw):
                events.append((op,kw["chain"][-1]["point"],kw["ordinal"],wires[-1].offset))
                return super().gate(op,wires,controls,**kw)
        with patch.object(e,"Ledger",Recording):result=e.estimate(obj,target(),"root",[],["0"]*4,include_frame=True)
        self.assertEqual(events,[("alloc","entry:2",0),("cx","entry:2",1,0),("cx","entry:2",2,1),("cx","entry:1",0,0),("cx","entry:1",1,1),("cx","entry:0",0,0),("cx","entry:0",1,1),("release","entry:0",2)])
        self.assertEqual(result["resources"]["time"],"6")

    def test_callee_local_region_is_allocated_and_restored_at_call(self):
        sig={"abi":"0.9","tier":"q","kind":"perm_action","mut":[8],"in":[],"mem":[],"args":[],"bounds":[]}
        obj=make_program("perm_action @root (t:wire[8]) () () () ()\n^entry():\naction_call @child (t) () () ()\nperm_action @child (t:wire[8]) () () () ()\n^entry():\nqregion db 0 8 @image\nr = qload db ()\nqxor r t\nqunload db () r",{"root":sig,"child":sig},data={"image":"81"})
        baseline=e.estimate(obj,target(),"root",[],["0"]*4)
        streamed=e.estimate(obj,target(),"root",[],["0"]*4,include_frame=True)
        # Each A=0 dispatch still runs two five-gate equality recipes,
        # plus eight data gates. Add eight XORs and four image X gates.
        self.assertEqual(baseline["resources"]["time"],"48")
        self.assertEqual(baseline["gates"],{"cx":"36","x":"12"})
        self.assertEqual(streamed["exact_resources"],baseline["exact_resources"])
        self.assertEqual(streamed["resources"]["peak_qubits[data]"],"27")
        self.assertEqual([r["width"] for r in streamed["frame"]["scratch"]],[8,8,0,1,1,1,1,1,0,1,1,1,1,1])
        self.assertEqual([c["region"] for c in streamed["invocation_contexts"]],["root","child"])
    def test_oracle_schedule_selects_reverse_row_leaf(self):
        sig={"abi":"0.9","tier":"q","kind":"oracle","in":[],"tgt":1,"fault":4,"mem":[],"args":[]}
        obj=make_object("oracle @root () (t:wire) (f:wire[4]) () ()\nregs { r:reg[1] }\n^entry():\nr = lift.const.i1 1\nlift.retval r",sig)
        doc=e.loads(e.jcs(target().doc))
        doc["schemes"].append({"name":"triple-x","realises":{"op":"x","controls":{"min":1,"max":1}},"ancillae":{"count":0,"class":"data","state":"clean"},"template":[{"gate":"cx","wires":["c[0]","t"]}]*3})
        t=e.Target.read(e.jcs(doc));budget=["1","0","0","0"]
        baseline=e.estimate(obj,t,"root",[],budget)
        obj.sections["schedule"]=baseline["effective_schedule"]
        obj.sections["schedule"]["entries"]=[entry(path=[point(obj.symbol("root")["interface_hash"],"entry:0")],step=1,phase="rev",generated=0,realisation="triple-x")]
        result=e.estimate(obj,t,"root",[],budget)
        self.assertEqual(F(result["resources"]["time"])-F(baseline["resources"]["time"]),2)
        self.assertEqual(int(result["gates"]["cx"])-int(baseline["gates"]["cx"]),3)
        self.assertEqual(int(result["gates"]["x"])-int(baseline["gates"]["x"]),-1)
        self.assertEqual(result["frame"]["ancillae"][0]["scheme"],"triple-x")

    def test_scheme_theta_and_template_validation(self):
        doc=e.loads(e.jcs(target().doc))
        # A two-rz identity pair is used here only to test resource
        # realisation, not as a correctness certificate for the scheme.
        doc["schemes"].append({"name":"theta-workspace","realises":{"op":"rz","controls":{"min":0,"max":0},"params":["theta"]},"ancillae":{"count":{"op":"ceil","args":[{"var":"theta"}]},"state":"clean","class":"data"},"template":[{"gate":"rz","wires":["t"],"params":[{"var":"theta"}]}]})
        t=e.Target.read(e.jcs(doc));q=e.Bundle("q",1,"data")
        ledger=e.Ledger(t,e.Schedule(schedule([entry(realisation="theta-workspace")])));ledger.interface("mut:0",q)
        ledger.gate("rz",[q],params=["0x3fe0000000000000"],chain=[point()])
        self.assertEqual(ledger.finish()["peak_qubits[data]"],2)
        self.assertEqual(ledger.frame()["ancillae"][0]["width"],1)
        for change in ["missing-params","bad-gate","unbound-expression","duplicate-scheme"]:
            broken=e.loads(e.jcs(doc));s=broken["schemes"][-1]
            if change=="missing-params":del s["template"][0]["params"]
            if change=="bad-gate":s["template"][0]["gate"]="not-a-gate"
            if change=="unbound-expression":s["template"][0]["params"]=[{"var":"k"}]
            if change=="duplicate-scheme":broken["schemes"].append(s)
            with self.assertRaises(e.ContractError,msg=change):e.Target.read(e.jcs(broken))

    def test_oracle_scheduled_stream_matches_summary_and_reverse_ordinals(self):
        sig={"abi":"0.9","tier":"q","kind":"oracle","in":[],"tgt":1,"fault":4,"mem":[],"args":[]}
        obj=make_object("oracle @root () (t:wire) (f:wire[4]) () ()\nregs { r:reg[1] }\n^entry():\nr = lift.const.i1 1\nlift.retval r",sig)
        t=target();original=e.Ledger
        for B in [0,1,2,3]:
            baseline=e.estimate(obj,t,"root",[],[str(B),"0","0","0"])
            events=[]
            class Recording(original):
                def allocate(self,b,**kw):
                    if kw.get("chain"):events.append(("alloc",kw["chain"][-1]["point"],kw.get("step"),kw.get("phase"),kw["ordinal"]))
                    return super().allocate(b,**kw)
                def release(self,b,**kw):
                    if kw.get("chain"):events.append(("release",kw["chain"][-1]["point"],kw.get("step"),kw.get("phase"),kw["ordinal"]))
                    return super().release(b,**kw)
                def gate(self,op,wires,controls=(),**kw):
                    events.append((op,kw["chain"][-1]["point"],kw.get("step"),kw.get("phase"),kw["ordinal"]))
                    return super().gate(op,wires,controls,**kw)
            with patch.object(e,"Ledger",Recording):
                result=e.estimate(obj,t,"root",[],[str(B),"0","0","0"],include_frame=True)
            self.assertEqual(result["exact_resources"],baseline["exact_resources"],B)
            self.assertEqual(result["gates"],baseline["gates"],B)
            self.assertEqual([r["width"] for r in result["frame"]["history"]],[6]*B)
            for pt in ["$step","entry:0","entry:1"]:
                for step in range(1,B+1):
                    forward=[v[4] for v in events if v[1:4]==(pt,step,"fwd")]
                    reverse=[v[4] for v in events if v[1:4]==(pt,step,"rev")]
                    self.assertEqual(forward,list(range(len(forward))),(pt,step))
                    self.assertEqual(reverse,forward[::-1],(pt,step))
            self.assertTrue(any(v[1]=="$construct" for v in events))
            self.assertTrue(any(v[1]=="$commit" for v in events))
            self.assertTrue(any(v[1]=="$release" for v in events))

    def test_frame_reports_every_lifetime_and_excludes_inherited_controls(self):
        t=target();ledger=e.Ledger(t,e.Schedule(schedule()))
        q=e.Bundle("q",1,"data");control=e.Bundle("c",1,"data")
        ledger.interface("control:0",control);ledger.interface("mut:0",q)
        scratch=e.Bundle("s",2,"data");borrow=e.Bundle("b",1,"data",state="borrowed")
        for i in range(2):
            ledger.allocate(scratch,chain=[point()],ordinal=i*2)
            ledger.release(scratch,chain=[point()],ordinal=i*2+1)
        ledger.allocate(borrow,chain=[point()],ordinal=4)
        ledger.release(borrow,chain=[point()],ordinal=5)
        ledger.finish();frame=ledger.frame()
        self.assertEqual(frame["slots"],[{"id":"mut:0","role":"mut","class":"data","width":1}])
        self.assertEqual([r["width"] for r in frame["scratch"]],[2,2])
        self.assertEqual([r["width"] for r in frame["borrow"]],[1])
        identities=[r["id"] for group in frame.values() for r in group]
        self.assertEqual(len(identities),len(set(identities)))
        e.Certificate.frame(frame)

    def test_certificate_resource_reconstruction_includes_frame(self):
        obj=e.Object.read((ROOT/"tests/fixtures/example3.bisa").read_text());t=target()
        result=e.estimate(obj,t,"borrow_demo",[],["0"]*4,include_frame=True)
        fixture=ROOT.parent/"bennett-isa-spec/conformance/fixtures/controlled-action-09/certificate.json"
        doc=e.loads(fixture.read_text());root=result["closure_hash"]
        region=next(iter(doc["regions"].values()))
        region.update(frame=e.loads(e.jcs(result["frame"])),signature=obj.symbol("borrow_demo")["signature"],kind="perm_action",bounds=[1],resources=result["resources"],estimate={"precision_digits":34,"exact_resources":result["exact_resources"]},claims=[])
        region["verification"].update(oracle=None,unitary=[],channel=[],borrow_frames=[],inverse_pairs=[])
        doc["regions"]={root:region}
        for key in ["object_hash","interface_hash","closure_hash","target_hash","schedule_hash","invocation"]:doc["bindings"][key]=result[key]
        cert=e.Certificate.read(e.jcs(doc))
        self.assertIn("resource",cert.check_resource_rows(result))
        # Producer-chosen non-slot ids may be renamed, but no requirement
        # may disappear merely because the resource rows still agree.
        doc["regions"][root]["frame"]["borrow"][0]["id"]="producer-frame"
        e.Certificate.read(e.jcs(doc)).check_resource_rows(result)
        doc["regions"][root]["frame"]["borrow"][0]["width"]=2
        with self.assertRaisesRegex(e.ContractError,"frame"):
            e.Certificate.read(e.jcs(doc)).check_resource_rows(result)

    def test_default_accuracy_share_is_exact_one_thirtieth(self):
        sig={"abi":"0.9","tier":"q","kind":"action","mut":[1],"in":[],"mem":[],"args":[],"bounds":[]}
        obj=make_object("action @root (t:wire) () () () ()\n^entry():\nrz 0.5 t\nrz 0.5 t\nrz 0.5 t",sig)
        doc=e.loads(e.jcs(target().doc))
        gate=next(g for g in doc["gates"] if g["op"]=="rz")
        gate["epsilon"]={"var":"eps"};gate["cost"]["time"]={"var":"eps"}
        t=e.Target.read(e.jcs(doc))
        result=e.estimate(obj,t,"root",[],["0"]*4,epsilon="0.1")
        self.assertEqual(result["resolved_default_epsilon_share"],{"numerator":"1","denominator":"30"})
        self.assertEqual(result["exact_resources"]["time"],{"numerator":"1","denominator":"10"})
        self.assertEqual(F(result["error_bound"]),F(1,10))
        # Explicit shares are included in N; they do not reduce the default
        # share's denominator or become a less-specific entry's fallback.
        obj.sections["schedule"]=result["effective_schedule"]
        obj.sections["schedule"]["entries"]=[entry(path=[point(obj.symbol("root")["interface_hash"],"entry:1")],epsilon_share="0.01")]
        result=e.estimate(obj,t,"root",[],["0"]*4,epsilon="0.1000")
        self.assertEqual(F(result["error_bound"]),F(23,300))

    def test_default_class_fallback_reaches_source_estimate(self):
        sig={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1],"in":[],"mem":[],"args":[],"bounds":[]}
        obj=make_object("perm_action @root (t:wire) () () () ()\n^entry():\na = qalloc any 1\ncx t a[0]\ncx t a[0]\nqfree a",sig)
        doc=e.loads(e.jcs(target().doc));desc={"capacity":1,"qubit_second":1,"dirty_rate":1}
        doc["classes"]={"A":dict(desc),"B":dict(desc)}
        t=e.Target.read(e.jcs(doc));result=e.estimate(obj,t,"root",[],["0"]*4)
        self.assertEqual(result["resources"]["peak_qubits[A]"],"1")
        self.assertEqual(result["resources"]["peak_qubits[B]"],"1")
    def test_catalog_stream_preserves_nested_scratch_lifetimes(self):
        for name in ["bind.value.add","bind.value.mul","bind.value.icmp.slt"]:
            t=target();ledger=e.Ledger(t,e.Schedule(schedule()))
            env={n:e.Bundle(n,1 if n=="t" and "icmp" in name else 2,"data") for n in ["a","b","t"]}
            for i,b in enumerate(env.values()):ledger.interface(f"mut:{i}",b)
            catalog=e.Catalog((ROOT/"data/ref-0.9.json").read_text(),t);catalog.ledger=ledger
            p=catalog.recipe(name,[2,"a","b","t"],env)
            self.assertEqual(ledger.finish(),p.resources(t,{"data":sum(b.width for b in env.values())}),name)

    def test_published_controlled_schedule_and_topology_reach_estimator(self):
        fixture=ROOT.parent/"bennett-isa-spec/conformance/fixtures/controlled-action-09"
        obj=e.Object.read((fixture/"controlled.bisa").read_text())
        t=e.Target.read((fixture/"target.json").read_text())
        result=e.estimate(obj,t,"controlled",[],["0"]*4)
        self.assertEqual(result["resources"],{"peak_qubits[fast]":"2","qubit_second[fast]":"2","time":"1"})
        self.assertEqual(result["schedule_hash"],e.digest(e.jcs(obj.sections["schedule"])))
        doc=e.loads(e.jcs(t.doc));doc["topology"]={"vertices":[{"class":"fast"} for _ in range(4)],"edges":[[0,1],[0,2],[1,3],[2,3]]}
        grid=e.Target.read(e.jcs(doc))
        obj.sections["schedule"]["bindings"]["target_hash"]=grid.hash
        obj.sections["schedule"]["interface_vertices"]=[[0],[1]]
        self.assertEqual(e.estimate(obj,grid,"controlled",[],["0"]*4)["resources"]["time"],"1")
        obj.sections["schedule"]["interface_vertices"]=[[0],[3]]
        with self.assertRaisesRegex(e.ContractError,"§17 item 15"):
            e.estimate(obj,grid,"controlled",[],["0"]*4)

    def test_loop_iteration_coordinates_select_one_start(self):
        obj=e.Object.read((ROOT/"tests/fixtures/example3.bisa").read_text());t=target()
        original=e.estimate(obj,t,"borrow_demo",[],["0"]*4)
        obj.sections["schedule"]=original["effective_schedule"]
        h=obj.symbol("borrow_demo")["interface_hash"]
        obj.sections["schedule"]["entries"]=[entry("start",path=[point(h,"entry:2",[0])],time="0.5")]
        result=e.estimate(obj,t,"borrow_demo",[],["0"]*4)
        self.assertEqual(result["resources"]["time"],"4.5")
        self.assertEqual(result["resources"]["qubit_second[data]"],"13.5")

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
