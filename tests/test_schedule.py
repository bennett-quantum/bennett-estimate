"""Independent schedule/placement/accounting requirements from ISA 0.9."""
import importlib.util
import hashlib
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


def make_program(text,signatures,data=None,layout=None,ptr=32):
    records={str(i):{"name":name,"kind":sig["kind"],"signature":sig,"interface_hash":"0"*64} for i,(name,sig) in enumerate(signatures.items())}
    header=f"bennett-object isa=0.9 object=0.9 launch=0.9 sched=0.9 cert=0.9 coverage=0.9 target=0.9 ptr_width={ptr}\n\nsection symbols\n"
    def document():return header+e.jcs(records)+"\n\nsection functions\n"+text+"\n"+("\nsection data\n"+"\n".join(n+" "+v for n,v in data.items())+"\n" if data else "")+("\nsection layout\n"+e.jcs(layout)+"\n" if layout else "")
    obj=e.Object.read(document())
    for record in records.values():record["interface_hash"]=obj.identities()[record["name"]]
    return e.Object.read(document())


class Selectors(unittest.TestCase):
    def test_record_fields_capture_wire_ids_and_validate_unvisited_entries(self):
        c=e.Catalog((ROOT/"data/ref-0.9.json").read_text(),target())
        descriptor={"name":"Records","type":"records","fields":["id","width",{"name":"location","type":"wire","width":"width"}],"order":["id"]}
        c.recipes["record-capture"]={"parameters":[{"name":"q","type":"wire","width":4},descriptor],"body":[{"visit":"Records","body":[{"for":"bit","from":0,"to":"width","body":[{"gate":"x","wires":['location["bit"]']}]}]}]}
        env={"f":e.Bundle("allocation",4,"data")}
        records=[{"id":0,"width":2,"location":{"range":"f","from":1,"to":3}}]
        self.assertEqual(c.recipe("record-capture",["f",records],env).gates,{"x":2})
        c.recipes["record-capture"]["body"]=[]
        invalid=[records+records,[{**records[0],"width":3}],[{**records[0],"extra":1}],[{**records[0],"id":True}]]
        for values in invalid:
            with self.assertRaises(e.ContractError):c.recipe("record-capture",["f",values],env)

    def test_fixed_procedure_binding_closure_keeps_entry_positions_distinct(self):
        root={"abi":"0.9","tier":"q","kind":"oracle","in":[1],"tgt":1,"fault":4,"mem":[],"args":["token","token","i1"]}
        worker={"abi":"0.9","tier":"q","kind":"lproc","params":[1],"result":1,"tokens":["token","token"],"args":["i1"],"mem":[]}
        layout={"ptr_width":32,"H":1,"A_tab":0,"S_cells":3,"globals":{},"interface_regions":{},"heap_base":1,"heap_limit_max":1,"null_size":1}
        text="oracle @root (x:wire in) (t:wire) (f:wire[4]) () (a:token, b:token, c:i1)\nregs { r:reg[1], s:reg[1] }\n^entry():\nr = lift.call @worker (x) (a, b) (c) ()\ns = lift.call @worker (x) (b, a) (c) ()\nlift.retval r\nlproc @worker (v:reg[1]) (r:reg[1]) (ta:token token, tb:token token) (c:i1 classical) ()\n^entry():\nr = lift.call @worker (v) (tb, ta) (c) ()\nlift.ret r"
        obj=make_program(text,{"root":root,"worker":worker},layout=layout)
        instances=obj.procedure_instances("root")
        self.assertEqual([(r["function"].name,r["key"]) for r in instances],[("root",()),("worker",(0,1,2)),("worker",(1,0,2))])
        self.assertEqual([r["first"] for r in instances],[0,3,5])
        self.assertEqual([r["arguments"] for r in instances[1:]],[{"ta":0,"tb":1,"c":2},{"ta":1,"tb":0,"c":2}])
        self.assertEqual([r["labels"] for r in instances],[{"entry":0},{"entry":3},{"entry":5}])
        # Fixed argument lists cannot be filled by a register location even
        # when its bit width happens to equal the declared classical type.
        wrong=make_program(text.replace("(a, b) (c) ()","(a, b) (r) ()",1),{"root":root,"worker":worker},layout=layout)
        with self.assertRaisesRegex(e.ContractError,"classical|fixed"):
            wrong.procedure_instances("root")

    def test_region_graph_includes_lproc_closure_but_allows_lproc_recursion(self):
        root={"abi":"0.9","tier":"q","kind":"oracle","in":[1],"tgt":1,"fault":4,"mem":[],"args":["token"]}
        worker={"abi":"0.9","tier":"q","kind":"lproc","params":[1],"result":1,"tokens":["token"],"args":[],"mem":[]}
        layout={"ptr_width":32,"H":1,"A_tab":0,"S_cells":4,"globals":{},"interface_regions":{},"heap_base":1,"heap_limit_max":1,"null_size":1}
        text="oracle @root (x:wire in) (t:wire) (f:wire[4]) () (tk:token)\nregs { r:reg[1] }\n^entry():\nr = lift.call @worker (x) (tk) () ()\nlift.retval r\nlproc @worker (x:reg[1]) (r:reg[1]) (tk:token token) () ()\nregs { u:reg[1], fr:reg[4] }\n^entry():\nlift.oracle_call @root tk (x) u fr () (tk)\nr = lift.mov x\nlift.ret r"
        with self.assertRaisesRegex(e.ContractError,"cycle|acyclic"):
            make_program(text,{"root":root,"worker":worker},layout=layout)
        recursive=text.replace("lift.oracle_call @root tk (x) u fr () (tk)","r = lift.call @worker (x) (tk) () ()")
        obj=make_program(recursive,{"root":root,"worker":worker},layout=layout)
        self.assertEqual(obj.functions["worker"].kind,"lproc")

    def test_region_cycles_are_rejected_even_in_zero_trip_loops(self):
        sig={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1],"in":[],"mem":[],"args":[],"bounds":[0]}
        with self.assertRaisesRegex(e.ContractError,"cycle|acyclic"):
            make_object("perm_action @root (t:wire) () () () ()\nregs {  } bounds {0}\n^entry():\nqloop 0 {\naction_call @root (t) () () ()\n}",sig)

    def test_published_k82_all_86_expansion_digests(self):
        doc=e.loads((ROOT.parent/"bennett-isa-spec/conformance/fixtures/accepted-k82-09/k82.json").read_text())
        count=0
        for edge in doc["edges"]:
            for instance in edge["instances"]:
                digest=hashlib.sha256();digest.update(b"[");labels={};leaves=0;allocations=0
                def emit(op,wires):
                    nonlocal leaves
                    if leaves:digest.update(b",")
                    digest.update(e.jcs([op,wires]).encode());leaves+=1
                class Hashed(e.Catalog):
                    def space_event(self,b,acquire):
                        nonlocal allocations
                        if acquire:labels[b.identity]=f"#{allocations}";allocations+=1
                        emit("alloc" if acquire else "release",[labels[b.identity]])
                        return super().space_event(b,acquire)
                    def gate_event(self,op,wires,controls=(),own=None,params=None):
                        emit(op,[f"{labels.get(w[0],w[0])}[{w[1]}]" for w in e.bits(wires)])
                        return super().gate_event(op,wires,controls,own,params)
                c=Hashed((ROOT/"data/ref-0.9.json").read_text(),target());c.closed_form=False
                env={n:e.Bundle(n,width,"data") for n,width in instance["bundles"].items()}
                literal=c.recipe(edge["caller"],instance["args"],env)
                digest.update(b"]")
                self.assertEqual(leaves,instance["leaves"],(edge["caller"],instance["args"]))
                self.assertEqual(digest.hexdigest(),instance["sha256"],(edge["caller"],instance["args"]))
                summary=e.Catalog((ROOT/"data/ref-0.9.json").read_text(),target()).recipe(edge["caller"],instance["args"],env)
                self.assertEqual(summary,literal,(edge["caller"],instance["args"]))
                count+=1
        self.assertEqual(count,86)

    def test_published_k82_interfaces_and_binding_cases(self):
        doc=e.loads((ROOT.parent/"bennett-isa-spec/conformance/fixtures/accepted-k82-09/k82.json").read_text())
        catalog=e.Catalog((ROOT/"data/ref-0.9.json").read_text(),target())
        names=[n for n,r in catalog.recipes.items() if all(isinstance(f,str) for f in r["parameters"])]
        self.assertEqual(len(names),doc["catalog"]["named_interface_recipes"])
        for name,wires in doc["interfaces"].items():self.assertEqual(sorted(catalog.named_interface(name)),sorted(wires),name)
        for case in doc["cases"]:
            events=[];labels={};serial=0
            class Recorder(e.Ledger):
                def allocate(self,b,**kw):
                    nonlocal serial
                    labels[b.identity]=f"#{serial}";serial+=1
                    events.append(["alloc",[labels[b.identity]]])
                    return super().allocate(b,**kw)
                def release(self,b,**kw):
                    events.append(["release",[labels[b.identity]]])
                    result=super().release(b,**kw);del labels[b.identity];return result
                def gate(self,op,wires,controls=(),**kw):
                    actual=e.bits(wires)
                    events.append([op,[f"{labels.get(b,n)}[{i}]" for b,i,n in [(w[0],w[1],w[0]) for w in actual]]])
                    return super().gate(op,wires,controls,**kw)
            t=target();ledger=Recorder(t,e.Schedule(schedule()))
            env={n:e.Bundle(n,width,"data") for n,width in case["bundles"].items()}
            for i,b in enumerate(env.values()):ledger.interface(f"mut:{i}",b)
            c=e.Catalog((ROOT/"data/ref-0.9.json").read_text(),t);c.ledger=ledger
            c.recipes.update({r["kind"]:r for r in case["recipes"]})
            if case["expect"]=="reject":
                with self.assertRaises(e.ContractError,msg=case["id"]):c.recipe(case["root"],case["args"],env)
            else:
                c.recipe(case["root"],case["args"],env);ledger.finish()
                self.assertEqual(events,case["expect"],case["id"])

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
    def test_native_accounting_resolves_each_live_operand_once(self):
        class Counting(e.Ledger):
            lookups=0
            def _find(self,b):
                self.lookups+=1;return super()._find(b)
        t=target();ledger=Counting(t,e.Schedule(schedule()))
        q=e.Bundle("q",1,"data");ledger.allocate(q)
        ledger.lookups=0;ledger.gate("x",[q]);self.assertEqual(ledger.lookups,1)
        ledger.release(q);ledger.allocate(q)
        ledger.lookups=0;ledger.gate("x",[q]);self.assertEqual(ledger.lookups,1)
        ledger.release(q)
        self.assertEqual(ledger.finish()["qubit_second[data]"],2)
        self.assertEqual(ledger.gates,{"x":2})

    def test_procedure_dynamic_jump_binds_absolute_canonical_end(self):
        obj=e.Object.read((ROOT/"examples/lifted-jump.bisa").read_text());t=target();seen=[];original=e.Catalog
        class Recording(original):
            def recipe(self,name,args,*rest,**kw):
                if name=="qjumpr":seen.append(tuple(args[2:4]))
                return super().recipe(name,args,*rest,**kw)
        with patch.object(e,"Catalog",Recording):e.estimate(obj,t,"root",[],["1","1","8","1"])
        self.assertEqual(seen,[(2,6)])

    def test_lproc_forwards_its_fixed_token_to_nested_oracle_invocations(self):
        obj=e.Object.read((ROOT/"examples/lifted-token-forwarding.bisa").read_text());t=target()
        budget=["1","1","8","1"];nested=["2","0","0","0"]
        baseline=e.estimate(obj,t,"root",[nested],budget)
        result=e.estimate(obj,t,"root",[nested],budget,include_frame=True)
        self.assertEqual(result["exact_resources"],baseline["exact_resources"])
        contexts=result["invocation_contexts"][1:]
        self.assertEqual([c["region"] for c in contexts],["child"]*4)
        self.assertEqual([c["invocation"]["budget"] for c in contexts],[nested]*4)
        self.assertEqual([c["raw_inverse"] for c in contexts],[False,True,False,True])
        self.assertEqual([c["path"][-1]["instance"] for c in contexts],[[0]]*4)
        self.assertEqual([r["width"] for r in result["frame"]["history"]],[21]+[3]*8)
        obj.sections["schedule"]=result["effective_schedule"]
        selector={**point(obj.symbol("worker")["interface_hash"],"entry:1"),"instance":[0]}
        obj.sections["schedule"]["entries"]=[entry(path=[selector],step=2,phase="fwd",realisation="missing")]
        with self.assertRaisesRegex(e.ContractError,"realisation"):
            e.estimate(obj,t,"root",[nested],budget)

    def test_recursive_fixed_instances_keep_separate_row_domains_for_equal_values(self):
        obj=e.Object.read((ROOT/"tests/fixtures/fixed-procedure-instances.bisa").read_text());t=target()
        budget=["1","1","8","1"];args=[["1","0","0","0"],["1","0","0","0"],"0"]
        baseline=e.estimate(obj,t,"root",args,budget)
        events=set();original=e.Ledger;symbol=obj.symbol("worker")["interface_hash"]
        class Recording(original):
            def gate(self,op,wires,controls=(),**kw):
                if kw["chain"][-1]["symbol"]==symbol:events.add((len(kw["chain"]),tuple(kw["chain"][-1]["instance"]),kw["phase"]))
                return super().gate(op,wires,controls,**kw)
        with patch.object(e,"Ledger",Recording):actual=e.estimate(obj,t,"root",args,budget,include_frame=True)
        self.assertEqual(actual["exact_resources"],baseline["exact_resources"])
        self.assertEqual([r["width"] for r in actual["frame"]["history"]],[18])
        self.assertEqual(events,{(1,key,phase) for key in [(0,1,2),(1,0,2)] for phase in ["fwd","rev"]})
        selected={**point(symbol),"instance":[1,0,2]}
        bound=actual["effective_schedule"];bound["entries"]=[entry(path=[selected],realisation="native")]
        e.Schedule(bound,obj,"root")
        selected["instance"]=[999]
        with self.assertRaisesRegex(e.ContractError,"fixed-binding instance"):
            e.Schedule(bound,obj,"root")

    def test_nested_inverse_reacquires_the_captured_scratch_binding(self):
        t=target();ledger=e.Ledger(t,e.Schedule(schedule()))
        q=e.Bundle("q",1,"data");ledger.interface("mut:0",q)
        c=e.Catalog((ROOT/"data/ref-0.9.json").read_text(),t);c.ledger=ledger
        prep=[{"alloc":"address","class":"any","state":"clean","width":1},{"gate":"x","wires":["address[0]"]}]
        compute=[*prep,{"gate":"cx","wires":["address[0]","q[0]"]},{"inverse":True,"body":prep}]
        profile=c.body([*compute,{"inverse":True,"body":compute}],{"q":q})
        self.assertTrue(all(v==0 for v in profile.delta.values()))
        self.assertEqual(ledger.gates,{"x":4,"cx":2})
        self.assertEqual(ledger.finish()["qubit_second[data]"],12)
        self.assertEqual(len(ledger.frame()["scratch"]),2)

    def test_procedure_activation_rows_share_root_dispatch_and_ordered_locations(self):
        root={"abi":"0.9","tier":"q","kind":"oracle","in":[1],"tgt":1,"fault":4,"mem":[],"args":[]}
        worker={"abi":"0.9","tier":"q","kind":"lproc","params":[1],"result":1,"tokens":[],"args":[],"mem":[]}
        layout={"ptr_width":2,"H":1,"A_tab":0,"S_cells":3,"globals":{},"interface_regions":{},"heap_base":1,"heap_limit_max":1,"null_size":1}
        text="oracle @root (x:wire in) (t:wire) (f:wire[4]) () ()\nregs { r:reg[1] }\n^entry():\nr = lift.call @worker (x)\nlift.retval r\nlproc @worker (a:reg[1]) (v:reg[1]) () () ()\n^entry():\nv = lift.mov a\nlift.ret v"
        obj=make_program(text,{"root":root,"worker":worker},layout=layout,ptr=2)
        doc=e.loads(e.jcs(target().doc));doc["ptr_widths_supported"]=[2];t=e.Target.read(e.jcs(doc));budget=["1","1","8","1"]
        baseline=e.estimate(obj,t,"root",[],budget)
        events=[];original=e.Ledger;symbol=obj.symbol("worker")["interface_hash"]
        class Recording(original):
            def gate(self,op,wires,controls=(),**kw):
                if kw["chain"][-1]["symbol"]==symbol:events.append((len(kw["chain"]),kw["chain"][-1]["instance"],kw["step"],kw["phase"]))
                return super().gate(op,wires,controls,**kw)
        with patch.object(e,"Ledger",Recording):streamed=e.estimate(obj,t,"root",[],budget,include_frame=True)
        self.assertEqual(streamed["exact_resources"],baseline["exact_resources"])
        # Four rows give P=3; slots=(capture1,fp4,sp4,depth2),
        # old_pc3/flag1/succ3 give an 18-bit history frame.
        self.assertEqual([r["width"] for r in streamed["frame"]["history"]],[18])
        self.assertEqual([r["width"] for r in streamed["frame"]["scratch"][:16]],[3,3,1,4,1,3,1,4,4,2,16,32,1,1,1,6])
        self.assertTrue(events)
        self.assertEqual(set((length,tuple(instance),step,phase) for length,instance,step,phase in events),{(1,(),1,"fwd"),(1,(),1,"rev")})
        obj.sections["schedule"]=streamed["effective_schedule"]
        obj.sections["schedule"]["entries"]=[entry(path=[point(symbol)],step=1,phase="fwd",generated=0,realisation="missing")]
        with self.assertRaisesRegex(e.ContractError,"realisation"):
            e.estimate(obj,t,"root",[],budget)

    def test_default_summary_matches_replay_with_scheme_workspace_and_accuracy(self):
        sig={"abi":"0.9","tier":"q","kind":"action","mut":[3],"in":[],"mem":[],"args":[],"bounds":[3]}
        obj=make_object("action @root (q:wire[3]) () () () ()\nregs {  } bounds { 3 }\n^entry():\nqloop 3 {\nrz 0.5 q[0]\nmcx (q[0], q[1]) q[2]\n}",sig)
        doc=e.loads(e.jcs(target().doc));doc["classes"]["data"]["capacity"]=5
        doc["gates"]=[g for g in doc["gates"] if g["op"]!="mcx"]
        next(g for g in doc["gates"] if g["op"]=="rz")["epsilon"]={"var":"eps"}
        doc["schemes"]=[{"name":"exact-mcx","realises":{"op":"mcx","controls":{"min":2,"max":2}},"ancillae":{"count":2,"class":"data","state":"clean"},"template":[{"gate":"ccx","wires":["c[0]","c[1]","t"]}]}]
        t=e.Target.read(e.jcs(doc));budget=["0"]*4
        summarized=e.estimate(obj,t,"root",[],budget,epsilon="0.1")
        replay=e.estimate(obj,t,"root",[],budget,epsilon="0.1",include_frame=True)
        for field in ["exact_resources","gates","error_bound","resolved_default_epsilon_share"]:self.assertEqual(summarized[field],replay[field],field)
        self.assertEqual(summarized["resources"]["peak_qubits[data]"],"5")
        self.assertEqual(summarized["resolved_default_epsilon_share"],{"numerator":"1","denominator":"60"})

    def test_capacity_class_fallback_retries_an_unsupported_summary_class(self):
        sig={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1],"in":[],"mem":[],"args":[],"bounds":[]}
        obj=make_object("perm_action @root (q:wire) () () () ()\n^entry():\nx q",sig)
        doc=e.loads(e.jcs(target().doc));desc={"qubit_second":1,"dirty_rate":1}
        doc["classes"]={"A":{**desc,"capacity":0},"B":{**desc,"capacity":1}}
        doc["gates"]=[{**g,"classes":["B"]} for g in doc["gates"] if g["op"]=="x"]
        doc["schemes"]=[]
        result=e.estimate(obj,e.Target.read(e.jcs(doc)),"root",[],["0"]*4)
        self.assertEqual(result["resources"]["peak_qubits[A]"],"0")
        self.assertEqual(result["resources"]["peak_qubits[B]"],"1")
        self.assertEqual(result["resources"]["time"],"1")

    def test_finite_capacity_and_accuracy_keep_trillion_iteration_summaries(self):
        n=2**40
        sig={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1],"in":[],"mem":[],"args":[],"bounds":[n]}
        obj=make_object(f"perm_action @root (q:wire) () () () ()\nregs {{  }} bounds {{ {n} }}\n^entry():\nqloop {n} {{\nx q\n}}",sig)
        doc=e.loads(e.jcs(target().doc));doc["classes"]["data"]["capacity"]=1
        t=e.Target.read(e.jcs(doc));original=e.Catalog
        class BoundedWork(original):
            def body(self,*args,**kw):
                if self.visits>100:raise AssertionError("resource summary grew with loop count")
                return super().body(*args,**kw)
        for epsilon in ["0","0.1"]:
            with patch.object(e,"Catalog",BoundedWork):result=e.estimate(obj,t,"root",[],["0"]*4,epsilon=epsilon)
            self.assertEqual(result["resources"]["time"],str(n))
            self.assertEqual(result["resources"]["gate_count"],str(n))
            self.assertEqual(result["resources"]["peak_qubits[data]"],"1")
            self.assertLess(result["summary_operations"],10)

    def test_approximate_loop_summary_keeps_exact_population_and_error(self):
        n=2**40
        sig={"abi":"0.9","tier":"q","kind":"action","mut":[1],"in":[],"mem":[],"args":[],"bounds":[n]}
        obj=make_object(f"action @root (q:wire) () () () ()\nregs {{  }} bounds {{ {n} }}\n^entry():\nqloop {n} {{\nrz 0.5 q\n}}",sig)
        doc=e.loads(e.jcs(target().doc));doc["classes"]["data"]["capacity"]=1
        gate=next(g for g in doc["gates"] if g["op"]=="rz")
        gate["epsilon"]={"var":"eps"};gate["cost"]["time"]={"var":"eps"}
        original=e.Catalog
        class BoundedWork(original):
            def body(self,*args,**kw):
                if self.visits>100:raise AssertionError("accuracy population was enumerated")
                return super().body(*args,**kw)
        with patch.object(e,"Catalog",BoundedWork):result=e.estimate(obj,e.Target.read(e.jcs(doc)),"root",[],["0"]*4,epsilon="0.1")
        self.assertEqual(result["resolved_default_epsilon_share"],{"numerator":"1","denominator":str(10*n)})
        self.assertEqual(result["exact_resources"]["time"],{"numerator":"1","denominator":"10"})
        self.assertEqual(F(result["error_bound"]),F(1,10))
        self.assertEqual(result["gates"],{"rz":str(n)})

    def test_k58_exact_native_default_is_zero_but_explicit_share_keeps_array_order(self):
        sig={"abi":"0.9","tier":"q","kind":"action","mut":[1],"in":[],"mem":[],"args":[],"bounds":[]}
        obj=make_object("action @root (q:wire) () () () ()\n^entry():\nh q\nh q",sig)
        doc=e.loads(e.jcs(target().doc));doc["gates"]=[{"op":"h","classes":["data"],"controls":{"min":0,"max":0},"epsilon":error,"cost":{"time":cost,"gate_count":1}} for error,cost in [(e.Decimal("0.001"),1),(0,100)]]
        t=e.Target.read(e.jcs(doc));result=e.estimate(obj,t,"root",[],["0"]*4,epsilon="0.01")
        self.assertEqual(result["resources"]["time"],"200")
        self.assertEqual(result["resolved_default_epsilon_share"],{"numerator":"0","denominator":"1"})
        obj.sections["schedule"]=result["effective_schedule"]
        obj.sections["schedule"]["entries"]=[entry(epsilon_share="0.005")]
        explicit=e.estimate(obj,t,"root",[],["0"]*4,epsilon="0.01")
        self.assertEqual(explicit["resources"]["time"],"2")
        self.assertEqual(F(explicit["error_bound"]),F(1,500))

    def test_k58_exact_scheme_still_counts_before_target_expansion(self):
        sig={"abi":"0.9","tier":"q","kind":"action","mut":[3],"in":[],"mem":[],"args":[],"bounds":[]}
        obj=make_object("action @root (q:wire[3]) () () () ()\n^entry():\nh q[0]\nmcx (q[0], q[1]) q[2]",sig)
        doc=e.loads(e.jcs(target().doc));doc["gates"]=[g for g in doc["gates"] if g["op"] not in ["h","mcx"]]
        doc["gates"].append({"op":"h","classes":["data"],"controls":{"min":0,"max":0},"epsilon":e.Decimal("0.01"),"cost":{"time":1,"gate_count":1}})
        doc["schemes"]=[{"name":"exact-mcx","realises":{"op":"mcx","controls":{"min":2,"max":2}},"ancillae":{"count":0,"class":"data","state":"clean"},"template":[{"gate":"ccx","wires":["c[0]","c[1]","t"]}]}]
        t=e.Target.read(e.jcs(doc))
        with self.assertRaisesRegex(e.ContractError,"E_GATE_UNSUPPORTED"):
            e.estimate(obj,t,"root",[],["0"]*4,epsilon="0.01")
        result=e.estimate(obj,t,"root",[],["0"]*4,epsilon="0.02")
        self.assertEqual(result["resolved_default_epsilon_share"],{"numerator":"1","denominator":"100"})
        self.assertEqual(F(result["error_bound"]),F(1,100))

    def test_omitted_expansion_resolves_ref_but_foreign_libraries_reject(self):
        sig={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1],"in":[],"mem":[],"args":[],"bounds":[]}
        obj=make_object("perm_action @root (q:wire) () () () ()\n^entry():\nx q",sig);t=target()
        base=e.estimate(obj,t,"root",[],["0"]*4)
        obj.sections["schedule"]=e.loads(e.jcs(base["effective_schedule"]))
        obj.sections["schedule"]["bindings"].pop("expansion")
        obj.sections["schedule"]["entries"]=[entry("start",generated=0,time=3)]
        omitted=e.estimate(obj,t,"root",[],["0"]*4)
        self.assertEqual(omitted["resources"]["time"],"4")
        for library in [{"name":"other","version":"0.9","hash":"a"*64},{**base["effective_schedule"]["bindings"]["expansion"],"hash":"b"*64}]:
            obj.sections["schedule"]["bindings"]["expansion"]=library
            with self.assertRaisesRegex(e.ContractError,"E_SCHEDULE_INFEASIBLE.*library"):
                e.estimate(obj,t,"root",[],["0"]*4)

    def test_lifted_table_fields_share_packed_storage_and_add_no_history_slots(self):
        sig={"abi":"0.9","tier":"q","kind":"oracle","in":[2,1],"tgt":2,"fault":4,"mem":[],"args":[]}
        layout={"ptr_width":2,"H":1,"A_tab":1,"S_cells":0,"globals":{},"interface_regions":{},"heap_base":1,"heap_limit_max":1,"null_size":1}
        doc=e.loads(e.jcs(target().doc));doc["ptr_widths_supported"]=[2];t=e.Target.read(e.jcs(doc))
        for opcode,operands in [("lift.free","p"),("lift.boundscheck","p n")]:
            obj=make_program("oracle @root (p:wire[2] in, n:wire in) (t:wire[2]) (f:wire[4]) () ()\n^entry():\n"+opcode+" "+operands+"\nlift.retval p",{"root":sig},layout=layout,ptr=2)
            budget=["1","1","0","0"];baseline=e.estimate(obj,t,"root",[],budget)
            touched=set();written=set();original=e.Ledger
            class Recording(original):
                def gate(self,op,wires,controls=(),**kw):
                    if kw["chain"][-1]["point"]=="entry:0":
                        own={"cx":1,"ccx":2,"mcx":len(wires)-1}.get(op,0)
                        touched.update(w.offset for w in wires if w.identity.endswith(":alloctab"))
                        written.update(w.offset for w in wires[own:] if w.identity.endswith(":alloctab"))
                    return super().gate(op,wires,controls,**kw)
            with patch.object(e,"Ledger",Recording):streamed=e.estimate(obj,t,"root",[],budget,include_frame=True)
            self.assertEqual(streamed["exact_resources"],baseline["exact_resources"],opcode)
            self.assertEqual([r["width"] for r in streamed["frame"]["history"]],[5])
            self.assertEqual(touched,{0,1,4,5,6,7,10,11} if opcode=="lift.free" else set(range(12))-{5,11})
            self.assertEqual(written,{4,10} if opcode=="lift.free" else set())

    def test_lifted_oracle_uncall_has_whole_cleanup_recompute_carrier(self):
        root={"abi":"0.9","tier":"q","kind":"oracle","in":[1],"tgt":1,"fault":4,"mem":[],"args":["token"]}
        child={**root,"args":[]}
        obj=make_program("oracle @root (x:wire in) (t:wire) (f:wire[4]) () (tk:token)\nregs { r:reg[1], fr:reg[4] }\n^entry():\nlift.oracle_call @child tk (x) r fr () ()\nlift.oracle_uncall @child tk (x) r fr () ()\nlift.retval x\noracle @child (x:wire in) (t:wire) (f:wire[4]) () ()\n^entry():\nlift.retval x",{"root":root,"child":child})
        t=target();budget=["1","0","0","0"];args=[budget]
        baseline=e.estimate(obj,t,"root",args,budget,include_frame=True)
        selected=entry("cleanup",path=[point(obj.symbol("root")["interface_hash"],"entry:1")],step=1,phase="fwd",generated=0,realisation="recompute")
        obj.sections["schedule"]=baseline["effective_schedule"]
        obj.sections["schedule"]["entries"]=[selected]
        result=e.estimate(obj,t,"root",args,budget)
        one=e.estimate(obj,t,"child",[],budget,inherited_controls=1)
        for key in ["time","gate_count"]:
            self.assertEqual(F(result["resources"][key])-F(baseline["resources"][key]),F(one["resources"][key])+5)
        decisions=result["cleanup_decisions"]
        self.assertEqual([(d["step"],d["phase"],d["ordinal"],d["realisation"]) for d in decisions],[(1,"fwd",0,"recompute"),(1,"rev",0,"reverse")])
        self.assertEqual([c["path"][-1]["call_index"] for c in result["invocation_contexts"][1:]],[0,0,1,0,0])
        self.assertEqual([c["raw_inverse"] for c in result["invocation_contexts"][1:]],[False,False,True,False,True])
        # The carrier owns no leaf: the two fresh allocations occupy the
        # caller's generated ordinals zero and one at the cleanup point.
        doc=e.loads(e.jcs(t.doc));doc["classes"]["special"]=dict(doc["classes"]["data"])
        special=e.Target.read(e.jcs(doc));obj.sections.pop("schedule")
        binding=e.estimate(obj,special,"root",args,budget)
        obj.sections["schedule"]=binding["effective_schedule"]
        obj.sections["schedule"]["entries"]=[selected,entry("alloc",path=selected["path"],step=1,phase="fwd",generated=0,**{"class":"special"})]
        allocations=[];ordinals=[];original=e.Ledger
        class Recording(original):
            def own(self,kw):return len(kw["chain"])==1 and kw["chain"][-1]["point"]=="entry:1" and kw["phase"]=="fwd"
            def allocate(self,b,**kw):
                profile=super().allocate(b,**kw)
                if self.own(kw):allocations.append((kw["ordinal"],b.width,self.resolved_class(b)));ordinals.append(kw["ordinal"])
                return profile
            def gate(self,op,wires,controls=(),**kw):
                if self.own(kw):ordinals.append(kw["ordinal"])
                return super().gate(op,wires,controls,**kw)
            def release(self,b,**kw):
                if self.own(kw):ordinals.append(kw["ordinal"])
                return super().release(b,**kw)
        with patch.object(e,"Ledger",Recording):e.estimate(obj,special,"root",args,budget)
        self.assertEqual(allocations,[(0,1,"special"),(1,4,"data")])
        self.assertEqual(ordinals,list(range(len(ordinals))))

    def test_lifted_region_rows_keep_nested_budget_arguments_and_reverse_context(self):
        root={"abi":"0.9","tier":"q","kind":"oracle","in":[1],"tgt":1,"fault":4,"mem":[],"args":["token","i1"]}
        child={**root,"args":["i1"]}
        flip={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1],"in":[],"mem":[],"args":["i1"],"bounds":[1]}
        text="oracle @root (x:wire in) (t:wire) (f:wire[4]) () (tk:token, a:i1)\nregs { r:reg[1], fr:reg[4] }\n^entry():\nlift.oracle_call @child tk (x) r fr () (a)\nlift.perm_call @flip (r) () () (a)\nlift.retval r\noracle @child (x:wire in) (t:wire) (f:wire[4]) () (a:i1)\n^entry():\nlift.retval x\nperm_action @flip (r:wire) () () (a:i1) ()\nregs {  } bounds { 1 }\n^entry():\nqloop 1 {\nx r\n}"
        obj=make_program(text,{"root":root,"child":child,"flip":flip});t=target()
        budget=["1","0","0","0"];nested=["2","0","0","0"];args=[nested,"1"]
        baseline=e.estimate(obj,t,"root",args,budget)
        events=[];original=e.Ledger;symbol=obj.symbol("child")["interface_hash"]
        class Recording(original):
            def gate(self,op,wires,controls=(),**kw):
                if kw["chain"][-1]["symbol"]==symbol:
                    events.append((kw["step"],kw["phase"],kw["chain"][-2]["point"],kw["chain"][-2]["entered_invocation"]))
                return super().gate(op,wires,controls,**kw)
        with patch.object(e,"Ledger",Recording):actual=e.estimate(obj,t,"root",args,budget,include_frame=True)
        self.assertEqual(actual["exact_resources"],baseline["exact_resources"])
        contexts=actual["invocation_contexts"]
        self.assertEqual([c["region"] for c in contexts],["root","child","flip","flip","child"])
        for context in contexts[1:]:
            self.assertEqual(context["invocation"]["args"],["1"])
            self.assertEqual(context["invocation"]["budget"],nested if context["region"]=="child" else budget)
            self.assertEqual(context["inherited_controls"],1)
        for phase in ["fwd","rev"]:
            for step in [1,2]:self.assertIn((1,phase,"entry:0",[step,"fwd"]),events)
        # Erasing only the two D-row bodies leaves identical outer dispatch,
        # successor, history and construction charges.
        empty=text.replace("lift.oracle_call @child tk (x) r fr () (a)","qjump ^second\n^second():").replace("lift.perm_call @flip (r) () () (a)","qjump ^done\n^done():")
        base=e.estimate(make_program(empty,{"root":root,"child":child,"flip":flip}),t,"root",args,budget)
        nested_cost=e.estimate(obj,t,"child",["1"],nested,inherited_controls=1)
        flip_cost=e.estimate(obj,t,"flip",["1"],budget,inherited_controls=1)
        for key in ["time","gate_count"]:
            self.assertEqual(F(actual["resources"][key])-F(base["resources"][key]),2*(F(nested_cost["resources"][key])+F(flip_cost["resources"][key])))

    def test_raw_inverse_oracle_swaps_support_partition_and_step_traversal(self):
        action={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1,4],"in":[1,1],"mem":[],"args":["token"],"bounds":[]}
        oracle={"abi":"0.9","tier":"q","kind":"oracle","in":[1],"tgt":1,"fault":4,"mem":[],"args":[]}
        text="perm_action @root (t:wire, f:wire[4]) (p:wire in, x:wire in) () (tk:token) ()\n^entry():\nadj action_call @outer (t, f) (p, x) () (tk)\nperm_action @outer (t:wire, f:wire[4]) (p:wire in, x:wire in) () (tk:token) ()\n^entry():\nqif p {\noracle_call @identity tk (x) t f () ()\n} {\noracle_call @identity tk (x) t f () ()\n}\noracle @identity (x:wire in) (t:wire) (f:wire[4]) () ()\n^entry():\nlift.retval x"
        obj=make_program(text,{"root":action,"outer":action,"identity":oracle});t=target()
        args=[["1","0","0","0"]]
        baseline=e.estimate(obj,t,"root",args,["0"]*4)
        events=[];original=e.Ledger;symbol=obj.symbol("identity")["interface_hash"]
        class Recording(original):
            def event(self,kind,kw):
                step,phase=kw["step"],kw["phase"]
                for edge in kw["chain"][:-1]:
                    if "entered_invocation" in edge:step,phase=edge["entered_invocation"]
                if kw["chain"][-1]["symbol"]==symbol:events.append((kind,kw["chain"][-1]["point"],step,phase,kw["ordinal"]))
            def allocate(self,b,**kw):self.event("alloc",kw);return super().allocate(b,**kw)
            def release(self,b,**kw):self.event("release",kw);return super().release(b,**kw)
            def gate(self,op,wires,controls=(),**kw):self.event(op,kw);return super().gate(op,wires,controls,**kw)
        with patch.object(e,"Ledger",Recording):result=e.estimate(obj,t,"root",args,["0"]*4,include_frame=True)
        self.assertEqual(result["exact_resources"],baseline["exact_resources"])
        self.assertEqual(events[0][0:2],("alloc","$release"))
        self.assertEqual(events[-1][0:2],("release","$construct"))
        support=[v for v in events if v[1]=="$step"]
        first=[v for v in support if v[3]=="rev"]
        half=len(first)//2
        self.assertEqual([v[4] for v in first[:half]],list(range(half)))
        forward=[v for v in support if v[3]=="fwd"]
        self.assertEqual([v[4] for v in forward[:half]],list(range(half-1,-1,-1)))
        self.assertEqual(support[0][3],"rev")
        for budget in [0,2]:
            values=[[str(budget),"0","0","0"]];events.clear()
            baseline=e.estimate(obj,t,"root",values,["0"]*4)
            with patch.object(e,"Ledger",Recording):actual=e.estimate(obj,t,"root",values,["0"]*4,include_frame=True)
            self.assertEqual(actual["exact_resources"],baseline["exact_resources"])
            coordinates=[]
            for event in events:
                if event[1]=="$step" and (not coordinates or coordinates[-1]!=event[2:4]):coordinates.append(event[2:4])
            expected=[(step,phase) for phase,steps in [("rev",range(1,budget+1)),("fwd",range(budget,0,-1))] for step in steps]
            self.assertEqual(coordinates,expected*2)

    def test_raw_inverse_calls_keep_forward_ordinals_and_reverse_bit_order(self):
        root={"abi":"0.9","tier":"q","kind":"perm_action","mut":[2],"in":[1,2],"mem":[],"args":[],"bounds":[]}
        leaf={**root,"in":[2]}
        text="perm_action @root (t:wire[2]) (p:wire in, s:wire[2] in) () () ()\n^entry():\nadj action_call @outer (t) (p, s) () ()\nperm_action @outer (t:wire[2]) (p:wire in, s:wire[2] in) () () ()\n^entry():\nqif p {\naction_call @leaf (t) (s) () ()\n} {\naction_call @leaf (t) (s) () ()\n}\nperm_action @leaf (t:wire[2]) (s:wire[2] in) () () ()\n^entry():\nqxor s t"
        obj=make_program(text,{"root":root,"outer":root,"leaf":leaf})
        events=[];original=e.Ledger;symbol=obj.symbol("leaf")["interface_hash"]
        class Recording(original):
            def gate(self,op,wires,controls=(),**kw):
                if kw["chain"][-1]["symbol"]==symbol:events.append((kw["ordinal"],wires[-1].offset))
                return super().gate(op,wires,controls,**kw)
        with patch.object(e,"Ledger",Recording):result=e.estimate(obj,target(),"root",[],["0"]*4,include_frame=True)
        self.assertEqual(events,[(1,1),(0,0),(1,1),(0,0)])
        self.assertEqual(result["gates"],{"cx":"4","x":"2"})

    def test_fresh_mints_keep_identity_even_for_equal_budget_tuples(self):
        cc={"abi":"0.9","tier":"cc","kind":"cc","params":[],"results":[]}
        oracle={"abi":"0.9","tier":"q","kind":"oracle","in":[1],"tgt":1,"fault":4,"mem":[],"args":[]}
        sink={"abi":"0.9","tier":"r","kind":"r","params":["token"],"results":[]}
        text="fn cc @root () () () () ()\n^entry():\none = const.i64 1\nzero = const.i64 0\na = budget.mint @identity one zero zero zero\nb = budget.mint @identity one zero zero zero\ncall @sink a\nuncall @sink (b) ()\nret\noracle @identity (x:wire in) (t:wire) (f:wire[4]) () ()\n^entry():\nlift.retval x\nfn r @sink (tk:token) () () () ()\n^entry():\nret"
        obj=make_program(text,{"root":cc,"identity":oracle,"sink":sink})
        self.assertEqual(e.estimate(obj,target(),"root",[],["0"]*4)["classical_steps"],"7")
        same=make_program(text.replace("uncall @sink (b)","uncall @sink (a)"),{"root":cc,"identity":oracle,"sink":sink})
        self.assertEqual(e.estimate(same,target(),"root",[],["0"]*4)["classical_steps"],"8")

    def test_tuple_only_root_tokens_do_not_guess_unknown_aliases(self):
        cc={"abi":"0.9","tier":"cc","kind":"cc","params":["token","token"],"results":[]}
        sink={"abi":"0.9","tier":"r","kind":"r","params":["token"],"results":[]}
        oracle={"abi":"0.9","tier":"q","kind":"oracle","in":[1],"tgt":1,"fault":4,"mem":[],"args":[]}
        obj=make_program("fn cc @root (a:token, b:token) () () () ()\n^entry():\ncall @sink a\nuncall @sink (b) ()\nret\nfn r @sink (tk:token) () () () ()\n^entry():\nret\noracle @identity (x:wire in) (t:wire) (f:wire[4]) () ()\n^entry():\nlift.retval x",{"root":cc,"sink":sink,"identity":oracle})
        args=[["1","0","0","0"],["1","0","0","0"]]
        with self.assertRaisesRegex(e.ContractError,"token.*alias"):
            e.estimate(obj,target(),"root",args,["0"]*4)
        with self.assertRaisesRegex(e.ContractError,"token.*alias"):
            e.estimate(obj,target(),"root",[args[0],args[0]],["0"]*4)
        bound=e.estimate(obj,target(),"root",args,["0"]*4,step_bound=4)
        self.assertEqual(bound["label"],"bound")

    def test_transitive_permutation_action_rejects_phase_body(self):
        root={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1],"in":[],"mem":[],"args":[],"bounds":[]}
        child={**root,"kind":"action"}
        obj=make_program("perm_action @root (t:wire) () () () ()\n^entry():\naction_call @child (t) () () ()\naction @child (t:wire) () () () ()\n^entry():\nh t",{"root":root,"child":child})
        with self.assertRaisesRegex(e.ContractError,"permutation"):
            e.estimate(obj,target(),"root",[],["0"]*4)

    def test_classical_budget_mint_has_no_quantum_execution_cost(self):
        classical={"abi":"0.9","tier":"cc","kind":"cc","params":[],"results":["i64"]}
        oracle={"abi":"0.9","tier":"q","kind":"oracle","in":[1],"tgt":1,"fault":4,"mem":[],"args":[]}
        obj=make_program("fn cc @root () (answer:i64) () () ()\n^entry():\none = const.i64 1\nzero = const.i64 0\ntk = budget.mint @child one zero zero zero\nret one\noracle @child (x:wire in) (t:wire) (f:wire[4]) () ()\n^entry():\nlift.retval x",{"root":classical,"child":oracle})
        result=e.estimate(obj,target(),"root",[],["0"]*4)
        self.assertEqual(result["classical_steps"],"4")
        self.assertEqual(result["gates"],{})
        bound=e.estimate(obj,target(),"root",[],["0"]*4,step_bound=4)
        self.assertEqual(bound["label"],"bound")
        self.assertEqual(bound["rational_upper_bounds"]["time"],{"numerator":"4","denominator":"1"})

    def test_interface_width_above_2pow53_is_decimal_string_bound(self):
        width=2**53+1
        sig={"abi":"0.9","tier":"q","kind":"perm_action","mut":[str(width)],"in":[],"mem":[],"args":[],"bounds":[0]}
        obj=make_object(f"perm_action @root (t:wire[{width}]) () () () ()\nregs {{  }} bounds {{0}}\n^entry():\nqloop 0 {{\nx t[0]\n}}",sig)
        result=e.estimate(obj,target(),"root",[],["0"]*4,include_frame=True)
        self.assertEqual(result["resources"]["peak_qubits[data]"],str(width))
        self.assertEqual(result["gates"],{})
        self.assertEqual(e.expression(result["frame"]["slots"][0]["width"],{"c":0},{}),width)

    def test_frame_widths_above_json_integer_limit_remain_exact_expressions(self):
        sig={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1],"in":[],"mem":[],"args":[],"bounds":[]}
        obj=make_object("perm_action @root (t:wire) () () () ()\n^entry():\nqregion cells 100 2",sig)
        result=e.estimate(obj,target(),"root",[],["0"]*4,include_frame=True)
        frame=e.loads(e.jcs(result["frame"]))
        e.check_metadata_numbers(frame)
        self.assertEqual(e.expression(frame["scratch"][0]["width"],{"c":F(0)},{}),2**101)
        self.assertEqual(result["resources"]["peak_qubits[data]"],str(2**101+1))

    def test_k12_certificate_production_preserves_supplied_proof_metadata(self):
        fixture=ROOT.parent/"bennett-isa-spec/conformance/fixtures/controlled-action-09"
        obj=e.Object.read((fixture/"controlled.bisa").read_text());t=e.Target.read((fixture/"target.json").read_text())
        result=e.estimate(obj,t,"controlled",[],["0"]*4)
        template=e.Certificate.read((fixture/"certificate.json").read_text())
        produced=template.with_estimate(result)
        cert=e.Certificate.read(e.jcs(produced))
        self.assertIn("frame_verified",cert.check_resource_rows(result))
        root=result["closure_hash"]
        self.assertEqual(produced["regions"][root]["estimate"],{"precision_digits":34,"exact_resources":result["exact_resources"]})
        self.assertEqual(produced["regions"][root]["claims"],template.doc["regions"][root]["claims"])
        self.assertEqual(produced["bindings"],template.doc["bindings"])
        self.assertNotIn("estimate",template.doc["regions"][root])
        changed=e.loads(e.jcs(result));changed["params_hash"]="0"*64
        changed["invocation"]["args"]=["1"]
        with self.assertRaisesRegex(e.ContractError,"invocation"):
            template.with_estimate(changed)

    def test_peak_uses_final_intervals_when_release_is_backdated(self):
        rows=[entry("start",path=[point(point=f"entry:{i}")],time=time) for i,time in [(0,0),(1,5),(2,1),(3,5)]]
        t=target();ledger=e.Ledger(t,e.Schedule(schedule(rows)))
        q=e.Bundle("q",1,"data");s=e.Bundle("s",1,"data");u=e.Bundle("u",1,"data")
        ledger.interface("mut:0",q);ledger.gate("x",[q])
        ledger.allocate(s,chain=[point(point="entry:0")])
        ledger.allocate(u,chain=[point(point="entry:1")])
        ledger.release(s,chain=[point(point="entry:2")])
        ledger.release(u,chain=[point(point="entry:3")])
        result=ledger.finish()
        self.assertEqual(result["time"],5)
        self.assertEqual(result["peak_qubits[data]"],2)
        self.assertEqual(result["qubit_second[data]"],6)

    def test_source_alloc_selector_does_not_override_scheme_ancilla_class(self):
        doc=e.loads(e.jcs(target().doc));doc["classes"]["special"]=dict(doc["classes"]["data"])
        doc["schemes"].append({"name":"workspace-x","realises":{"op":"x","controls":{"min":0,"max":0}},"ancillae":{"count":1,"class":"data","state":"clean"},"template":[{"gate":"x","wires":["t"]}]})
        ledger=e.Ledger(e.Target.read(e.jcs(doc)),e.Schedule(schedule([entry(realisation="workspace-x"),entry("alloc",**{"class":"special"})])))
        ledger.interface("mut:0",e.Bundle("q",1,"data"));ledger.gate("x",[e.Bundle("q",1,"data")],chain=[point()]);ledger.finish()
        self.assertEqual(ledger.frame()["ancillae"][0]["class"],"data")

    def test_budget_components_fit_launch_uint64(self):
        obj=e.Object.read((ROOT/"tests/fixtures/example1.bisa").read_text())
        e.validate_budget([str(2**64-1),"0","0","0"],obj)
        with self.assertRaises(e.ContractError):e.validate_budget([str(2**64),"0","0","0"],obj)

    def test_loop_binding_carries_reallocated_lifetime_to_next_visit(self):
        sig={"abi":"0.9","tier":"q","kind":"perm_action","mut":[],"in":[],"mem":[],"args":[],"bounds":[3]}
        obj=make_object("perm_action @root () () () () ()\nregs {  } bounds { 3 }\n^entry():\nc = qalloc any 1\nqloop 3 {\nqfree c\nc = qalloc any 1\nx c[0]\nx c[0]\n}\nqfree c",sig)
        result=e.estimate(obj,target(),"root",[],["0"]*4,include_frame=True)
        self.assertEqual(result["gates"],{"x":"6"})
        self.assertEqual(result["resources"]["peak_qubits[data]"],"1")
        self.assertEqual(len(result["frame"]["scratch"]),4)
        self.assertEqual(result["resources"]["qubit_second[data]"],"6")
        self.assertEqual(e.estimate(obj,target(),"root",[],["0"]*4)["exact_resources"],result["exact_resources"])

    def test_lifted_allocator_uses_all_four_ordered_history_slots(self):
        sig={"abi":"0.9","tier":"q","kind":"oracle","in":[],"tgt":32,"fault":4,"mem":[],"args":[]}
        layout={"ptr_width":32,"H":1,"A_tab":0,"S_cells":0,"globals":{},"interface_regions":{},"heap_base":1,"heap_limit_max":1,"null_size":1}
        obj=make_program("oracle @root () (t:wire[32]) (f:wire[4]) () ()\nregs { n:reg[1], p:reg[32] }\n^entry():\nn = lift.const.i1 1\np = lift.alloc n\nlift.retval p",{"root":sig},layout=layout)
        t=target();budget=["1","1","0","0"]
        baseline=e.estimate(obj,t,"root",[],budget)
        streamed=e.estimate(obj,t,"root",[],budget,include_frame=True)
        # Pc=2, disp=(ptr32, entry66, heap-used3, atop1), flag1,
        # succ2: exactly 107 retained bits in each step frame.
        self.assertEqual([r["width"] for r in streamed["frame"]["history"]],[107])
        self.assertEqual(streamed["exact_resources"],baseline["exact_resources"])
        self.assertGreater(int(baseline["gates"]["swap"]),0)

    def test_effective_control_identity_and_predicate_depth(self):
        doc=e.loads(e.jcs(target().doc));doc["capabilities"]["max_predicate_depth"]=1
        next(g for g in doc["gates"] if g["op"]=="cx")["cost"]["time"]={"var":"c"}
        t=e.Target.read(e.jcs(doc));q=e.Bundle("q",3,"data")
        ledger=e.Ledger(t,e.Schedule(schedule()));ledger.interface("mut:0",q)
        # Own and effective occurrences of the same physical control count
        # once even when their unresolved class hints differ.
        self.assertEqual(ledger.gate("cx",[q.bit(0),q.bit(2)],controls=(("q",0,"any"),)).time,1)
        with self.assertRaisesRegex(e.ContractError,"predicate"):
            ledger.gate("x",[q.bit(2)],controls=(("q",0,"data"),("q",1,"data")))

    def test_parameter_angle_bits_and_permutation_source_restriction(self):
        sig={"abi":"0.9","tier":"q","kind":"action","mut":[1],"in":[],"mem":[],"args":["f64"],"bounds":[]}
        obj=make_object("action @root (t:wire) () () (theta:f64) ()\n^entry():\nrz theta t",sig)
        result=e.estimate(obj,target(),"root",["0x8000000000000000"],["0"]*4,include_frame=True)
        self.assertEqual(result["gates"],{"rz":"1"})
        with self.assertRaisesRegex(e.ContractError,"nonfinite"):
            e.estimate(obj,target(),"root",["0x7ff0000000000000"],["0"]*4)
        sig={**sig,"kind":"perm_action","args":[]}
        bad=make_object("perm_action @root (t:wire) () () () ()\n^entry():\nh t",sig)
        with self.assertRaisesRegex(e.ContractError,"permutation"):
            e.estimate(bad,target(),"root",[],["0"]*4)

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
        region.update(frame=e.loads(e.jcs(result["frame"])),signature=obj.symbol("borrow_demo")["signature"],kind="perm_action",bounds=[1],resources=result["resources"],estimate={"precision_digits":34,"exact_resources":result["exact_resources"]},gates_used={n:{"count":int(v)} for n,v in result["gates"].items()},claims=[])
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

    def test_certificate_cannot_change_root_signature_or_gate_inventory(self):
        fixture=ROOT.parent/"bennett-isa-spec/conformance/fixtures/controlled-action-09"
        obj=e.Object.read((fixture/"controlled.bisa").read_text());t=e.Target.read((fixture/"target.json").read_text())
        result=e.estimate(obj,t,"controlled",[],["0"]*4)
        doc=e.loads((fixture/"certificate.json").read_text());region=doc["regions"][result["closure_hash"]]
        region["resources"]=result["resources"];region["estimate"]={"precision_digits":34,"exact_resources":result["exact_resources"]}
        e.Certificate.read(e.jcs(doc)).check_resource_rows(result)
        region["gates_used"]={}
        with self.assertRaisesRegex(e.ContractError,"gate"):
            e.Certificate.read(e.jcs(doc)).check_resource_rows(result)
        region["gates_used"]={"x":{"count":1}};region["signature"]["mut"]=[2]
        with self.assertRaisesRegex(e.ContractError,"signature"):
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
