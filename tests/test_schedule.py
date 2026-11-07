"""Independent schedule/placement/accounting requirements from ISA 0.9."""
import importlib.util
import hashlib
import json
import os
import re
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from fractions import Fraction as F
from itertools import product
from functools import reduce
from operator import and_

ROOT=Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "scripts"))
from pinned import sibling

spec=importlib.util.spec_from_file_location("scheduled_estimate",ROOT/"src/estimate.py")
e=importlib.util.module_from_spec(spec);sys.modules[spec.name]=e;spec.loader.exec_module(e)


def target():
    return e.Target.read((sibling(ROOT, "bennett-targets") / "targets/ideal-all-to-all.json").read_text())


def point(symbol="a"*64,point="entry:0",iteration=()):
    return {"symbol":symbol,"point":point,"iteration":list(iteration),"instance":[]}


def entry(kind="gate",path=(),step="*",phase="*",generated="*",**payload):
    return {"kind":kind,"path":list(path),"step":step,"phase":phase,"generated":generated,kind:payload}


def schedule(entries=(),target_hash="b"*64):
    return {"bindings":{"closure_hash":"a"*64,"target_hash":target_hash,"region":"root","variant":"forward","inherited_controls":0,"budget":[2,0,0,0],"params_hash":e.digest("[]"),"epsilon":0,"expansion":{"name":"ref","version":"0.9","hash":"5de4e4995350313e50217880ba1b95de39cd043283b726337d4894efb005d197"},"scheduler":{"name":"test","version":"1"}},"entries":list(entries)}


def make_object(text,signature):
    return make_program(text,{"root":signature})


def make_program(text,signatures,data=None,layout=None,ptr=32,devices=None):
    signatures={**signatures,**{name:{"abi":"0.9","tier":"-","kind":"data","size":len(image)//2} for name,image in (data or {}).items() if name not in signatures}}
    records={str(i):{"name":name,"kind":sig["kind"],"signature":sig,"interface_hash":"0"*64} for i,(name,sig) in enumerate(signatures.items())}
    header=f"bennett-object isa=0.9 object=0.9 launch=0.9 sched=0.9 cert=0.9 coverage=0.9 target=0.9 ptr_width={ptr}\n\nsection symbols\n"
    def document():return header+e.jcs(records)+"\n\nsection functions\n"+text+"\n"+("\nsection data\n"+"\n".join(n+" "+v for n,v in data.items())+"\n" if data else "")+("\nsection devices\n"+e.jcs(devices)+"\n" if devices else "")+("\nsection layout\n"+e.jcs(layout)+"\n" if layout else "")
    obj=e.Object.read(document())
    for record in records.values():record["interface_hash"]=obj.identities()[record["name"]]
    return e.Object.read(document())


def wire_key(bundle):return bundle.identity,bundle.offset


def basis_outputs(ledger):return {slot:ledger.values[key] for slot,key in ledger.slots.items()}


class BasisLedger(e.Ledger):
    """One bit per basis assignment, using only the emitted wire operands."""
    def __init__(self,*args,basis,mask,**kw):super().__init__(*args,**kw);self.basis,self.mask=basis,mask;self.values={};self.slots={};self.leaves=[]
    def interface(self,slot,b,vertices=None):assert b.width==1;self.slots[slot]=wire_key(b);self.values[self.slots[slot]]=self.basis[slot];return super().interface(slot,b,vertices)
    def allocate(self,b,**kw):assert b.width==1;self.values[wire_key(b)]=0;self.leaves.append(("allocate",kw["chain"][-1]["point"],kw["ordinal"]));return super().allocate(b,**kw)
    def release(self,b,**kw):assert self.values.pop(wire_key(b))==0,"dirty release on at least one basis input";self.leaves.append(("release",kw["chain"][-1]["point"],kw["ordinal"]));return super().release(b,**kw)

    def gate(self,op,wires,controls=(),**kw):
        assert len(wires)=={"x":1,"cx":2}[op]
        operands=tuple(map(wire_key,wires))
        predicates=operands[:-1]+tuple((identity,offset) for identity,offset,cls in controls)
        self.values[operands[-1]]^=reduce(and_,(self.values[key] for key in predicates),self.mask)
        self.leaves.append((op,kw["chain"][-1]["point"],kw["ordinal"],tuple((identity.rsplit(":",1)[-1],offset) for identity,offset in operands),tuple(controls)))
        return super().gate(op,wires,controls,**kw)


class Selectors(unittest.TestCase):
    def test_large_source_coordinates_have_distinct_ordinals_and_lossless_keys(self):
        c=e.Catalog((ROOT/"data/ref-0.9.json").read_text(),target())
        c.source_context={"symbol":"a"*64,"point":"entry:0","depth":1}
        large=2**80
        addresses=[]
        for value in [large,large+1]:
            c.loop_coordinates=[value]
            addresses.append(c.leaf_address())
        self.assertEqual([a["ordinal"] for a in addresses],[0,0])
        self.assertEqual([a["chain"][0]["iteration"] for a in addresses],[[str(large)],[str(large+1)]])
        self.assertNotEqual(c.address_key([point(iteration=[large])],None,None),c.address_key([point(iteration=[large+1])],None,None))
        self.assertEqual(c.address_key([point()],large,"fwd"),c.address_key([point()],str(large),"fwd"))

    def test_decimal_string_path_coordinates_match_exact_integer_values(self):
        large=2**80+1
        selected=entry(path=[{**point(iteration=[str(large)]),"instance":["3"],"call_index":"1"}],step="2",phase="fwd",generated="3",realisation="native")
        s=e.Schedule(schedule([selected]))
        actual=[{**point(iteration=[large]),"instance":[3],"call_index":1}]
        self.assertEqual(s.pick("gate",actual,3,2,"fwd"),{"realisation":"native"})
        actual[0]["iteration"]=[large-1]
        self.assertIsNone(s.pick("gate",actual,3,2,"fwd"))
        selected=entry(path=[point()],step=str(large),phase="rev",realisation="native")
        s=e.Schedule(schedule([selected]))
        actual=[{**point(),"call_index":0,"entered_invocation":[str(large),"rev"]},point("b"*64)]
        self.assertEqual(s.pick("gate",actual,0,999,"fwd"),{"realisation":"native"})

    def test_fixed_instance_path_accepts_decimal_string_entry_positions(self):
        root={"abi":"0.9","tier":"q","kind":"oracle","in":[1],"tgt":1,"fault":4,"mem":[],"args":["i1"]}
        worker={"abi":"0.9","tier":"q","kind":"lproc","params":[1],"result":1,"tokens":[],"args":["i1"],"mem":[]}
        code="oracle @root (x:wire in) (t:wire) (f:wire[4]) () (a:i1)\nregs { r:reg[1] }\n^entry():\nr = lift.call @worker (x) () (a) ()\nlift.retval r\nlproc @worker (v:reg[1]) (r:reg[1]) () (a:i1 classical) ()\n^entry():\nlift.ret v"
        obj=make_program(code,{"root":root,"worker":worker})
        doc=schedule([entry(path=[{**point(obj.symbol("worker")["interface_hash"]),"instance":["0"]}],realisation="native")])
        parsed=e.Schedule(doc,obj,"root")
        self.assertEqual(parsed.pick("gate",[{**point(obj.symbol("worker")["interface_hash"]),"instance":[0]}],0),{"realisation":"native"})
        self.assertIsNone(parsed.pick("gate",[{**point(obj.symbol("worker")["interface_hash"]),"instance":[1]}],0))

    def test_captured_record_arrays_reuse_validation_without_rebinding_fields(self):
        class Counting(e.Catalog):
            field_bindings=0
            def bind(self,formals,*args,**kw):
                if len(formals)==1 and isinstance(formals[0],dict) and formals[0].get("name")=="location":self.field_bindings+=1
                return super().bind(formals,*args,**kw)
        c=Counting((ROOT/"data/ref-0.9.json").read_text(),target())
        descriptor={"name":"Records","type":"records","fields":["id","width",{"name":"location","type":"wire","width":"width"}],"order":["id"]}
        q=e.Bundle("original",3,"data");records=[{"id":0,"width":3,"location":"q"}]
        bound,_=c.bind([descriptor],[records],{"q":q},())
        captured=bound["Records"];self.assertEqual(c.field_bindings,1)
        with self.assertRaises(TypeError):captured[0]["id"]=1
        with self.assertRaises(TypeError):captured[0]["location"][0]=e.Bundle("replacement",3,"data")
        records[0]["width"]=1
        for _ in range(20):
            forwarded,_=c.bind([descriptor],[captured],{"q":e.Bundle("other",3,"data")},())
            self.assertEqual(e.bits(e.wire(forwarded["Records"][0]["location"],{})),e.bits([q]))
        self.assertEqual(c.field_bindings,1)
        changed={**descriptor,"fields":["id","width",{"name":"location","type":"wire","width":2}]}
        with self.assertRaises(e.ContractError):c.bind([changed],[captured],{},())
        descriptor["fields"][-1]["width"]=2
        with self.assertRaises(e.ContractError):c.bind([descriptor],[captured],{},())
        dependent={"name":"R","type":"records","fields":["id",{"name":"location","type":"wire","width":"N"}],"order":["id"]}
        N={"name":"N","type":"integer"}
        captured=c.bind([N,dependent],[3,[{"id":0,"location":q}]],{},())[0]["R"]
        with self.assertRaises(e.ContractError):c.bind([N,dependent],[2,captured],{},())

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
        doc=e.loads((sibling(ROOT, "bennett-isa-spec") / "conformance/fixtures/accepted-k82-09/k82.json").read_text())
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
        doc=e.loads((sibling(ROOT, "bennett-isa-spec") / "conformance/fixtures/accepted-k82-09/k82.json").read_text())
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
    def review_witness(self,code,inputs,release):
        sig={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1],"in":inputs,"mem":[],"args":[],"bounds":[]}
        obj=make_object(code,sig);t=target()
        doc=e.estimate(obj,t,"root",[],["0"]*4)["effective_schedule"]
        doc["entries"]=[entry("cleanup",path=[point(obj.symbol("root")["interface_hash"],release)],realisation="recompute")]
        obj.sections["schedule"]=doc
        return obj,t

    def test_review_pjj_nonadjacent_independent_cleanup(self):
        obj,t=self.review_witness("""perm_action @root (y:wire) (x:wire in, z:wire in) () () ()
^entry():
d = qalloc any 1
cx x d
cx z d
cx z d
x y
cx x d
qfree d""",[1,1],"entry:6")
        result=e.estimate(obj,t,"root",[],["0"]*4,include_frame=True)
        self.assertEqual(result["cleanup_decisions"][0]["realisation"],"recompute")
        self.assertEqual(result["resources"]["gate_count"],"8")

    def test_review_yak_non_disjoint_cleanup(self):
        obj,t=self.review_witness("""perm_action @root (y:wire) (x:wire in, z:wire in) () () ()
^entry():
d = qalloc any 1
cx x d
cx z d
cx z d
cx d y
cx x d
qfree d""",[1,1],"entry:6")
        with self.assertRaisesRegex(e.ContractError,r"non-disjoint row entry:4 \(cx\)"):
            e.estimate(obj,t,"root",[],["0"]*4)

    def test_review_tdf_restored_input_cleanup(self):
        obj,t=self.review_witness("""perm_action @root (x:wire) (z:wire in) () () ()
^entry():
d = qalloc any 1
cx x d
cx z d
cx z d
x x
x x
cx x d
qfree d""",[1],"entry:7")
        result=e.estimate(obj,t,"root",[],["0"]*4)
        self.assertEqual(result["label"],"exact")
        self.assertEqual(result["resources"],{"gate_count":"9","time":"9","peak_qubits[data]":"4","qubit_second[data]":"32"})

    terminal_signature={"abi":"0.9","tier":"q","kind":"perm_action","mut":[],"in":[1,1],"mem":[],"args":[],"bounds":[]}
    terminal_source="perm_action @root () (x:wire in, z:wire in) () () ()\n^entry():\nd = qalloc any 1\ncx x d\ncx z d\ncx z d\ncx x d\nqfree d"
    disjoint_source=terminal_source.replace("@root ()", "@root (y:wire)")
    # K80: two original CXs with three live wires, five replacement CXs with
    # four: gates/time = 7, peak = 4, area = 2*3+5*4 = 26.
    # K81 interleavings: the independent X adds one gate and y stays live;
    # gates/time = 2+1+5 = 8, peak = 5, area = 3*4+5*5 = 37.
    terminal_cases=[
        (terminal_signature,terminal_source,"entry:5",["entry:3","entry:4","entry:5"],[],{"gate_count":"7","time":"7","peak_qubits[data]":"4","qubit_second[data]":"26"}),
        ({**terminal_signature,"mut":[1]},disjoint_source.replace("cx z d\ncx x d", "cx z d\nx y\ncx x d"),"entry:6",["entry:3","entry:5","entry:6"],[("x","entry:4",0)],{"gate_count":"8","time":"8","peak_qubits[data]":"5","qubit_second[data]":"37"}),
        ({**terminal_signature,"mut":[1]},disjoint_source.replace("qfree d", "x y\nqfree d"),"entry:6",["entry:3","entry:4","entry:6"],[("x","entry:5",0)],{"gate_count":"8","time":"8","peak_qubits[data]":"5","qubit_second[data]":"37"}),
    ]

    terminal_inputs=[{"in:0":0xC,"in:1":0xA},{"mut:0":0xAA,"in:0":0xF0,"in:1":0xCC},{"mut:0":0xAA,"in:0":0xF0,"in:1":0xCC}]
    terminal_outputs=[terminal_inputs[0],{**terminal_inputs[1],"mut:0":0x55},{**terminal_inputs[2],"mut:0":0x55}]
    terminal_gates=[("cx",(("x",0),("d",0)),()),("cx",(("z",0),("d",0)),())]
    terminal_replay=[("cx",((a,0),(b,0)),()) for a,b in [("x","terminal_recompute"),("z","terminal_recompute"),("terminal_recompute","d"),("z","terminal_recompute"),("x","terminal_recompute")]]
    terminal_gate_cases=[terminal_gates+terminal_replay,terminal_gates+[("x",(("y",0),),())]+terminal_replay,terminal_gates+[("x",(("y",0),),())]+terminal_replay]
    terminal_fixtures=list(zip(terminal_cases,terminal_inputs,terminal_outputs,[0xF,0xFF,0xFF],terminal_gate_cases))

    def test_k80_primitive_terminal_chain_recompute_has_exact_published_leaves(self):
        for ((sig,code,release,owned,disjoint,resources),basis,expected_basis,mask,gates),raw in product(self.terminal_fixtures,[False,True]):
            with self.subTest(disjoint=disjoint,raw_inverse=raw):
                obj=make_object(code,sig);t=target()
                doc=e.estimate(obj,t,"root",[],["0"]*4)["effective_schedule"]
                carrier=point(obj.symbol("root")["interface_hash"],release)
                doc["entries"]=[entry("cleanup",path=[carrier],generated=0,realisation="recompute"),entry("gate",path=[{**carrier,"point":owned[0]}],realisation="missing-scheme"),entry("gate",path=[carrier],generated=0,realisation="missing-scheme")]
                obj.sections["schedule"]=doc
                result=e.estimate(obj,t,"root",[],["0"]*4,include_frame=True)
                self.assertEqual(result["resources"],resources)
                self.assertEqual(result["cleanup_decisions"][0]["owned_points"],owned)
                expected=[("allocate","entry:0",0),("cx","entry:1",0),("cx","entry:2",0),*disjoint,("allocate",release,0),*(("cx",release,n) for n in range(1,6)),("release",release,6),("release",release,7)]
                c=e.Catalog((ROOT/"data/ref-0.9.json").read_text(),t)
                c.ledger=BasisLedger(t,e.Schedule(doc,obj,"root"),basis=(basis,expected_basis)[raw],mask=mask)
                e.Source(obj,t,c).region("root",[],["0"]*4,raw_inverse=raw)
                self.assertEqual(basis_outputs(c.ledger),(expected_basis,basis)[raw])
                self.assertEqual([(leaf[0],*leaf[3:]) for leaf in c.ledger.leaves if len(leaf)>3],(gates,gates[::-1])[raw])
                stride,ops=[(1,{"allocate":"allocate","release":"release","cx":"cx","x":"x"}),(-1,{"allocate":"release","release":"allocate","cx":"cx","x":"x"})][raw]
                actual=[(ops[op],p,n) for op,p,n in expected[::stride]]
                self.assertEqual([leaf[:3] for leaf in c.ledger.leaves],actual)
                self.assertEqual(c.ledger.finish(),{k:int(v) for k,v in resources.items()})

    non_disjoint_cases=[
        ({**terminal_signature,"mut":[1]},disjoint_source.replace("cx z d\ncx x d","cx z d\ncx d y\ncx x d"),"entry:4 (cx)",{"mut:0":0xAA,"in:0":0xF0,"in:1":0xCC},{"mut:0":0xAA^0xF0,"in:0":0xF0,"in:1":0xCC},0xFF),
        ({**terminal_signature,"mut":[1],"in":[1]},terminal_source.replace("@root () (x:wire in, z:wire in)","@root (x:wire) (z:wire in)").replace("qfree d","x x\nqfree d"),"entry:5 (x)",{"mut:0":0xC,"in:0":0xA},{"mut:0":0x3,"in:0":0xA},0xF),
        ({**terminal_signature,"mut":[1]},disjoint_source.replace("qfree d","cx d y\nqfree d"),"entry:5 (cx)",{"mut:0":0xAA,"in:0":0xF0,"in:1":0xCC},{"mut:0":0xAA,"in:0":0xF0,"in:1":0xCC},0xFF),
        ({**terminal_signature,"mut":[1],"in":[1]},terminal_source.replace("@root () (x:wire in, z:wire in)","@root (z:wire) (x:wire in)").replace("cx z d\ncx x d","cx z d\nx z\ncx x d"),"entry:4 (x)",{"mut:0":0xC,"in:0":0xA},{"mut:0":0x3,"in:0":0xA},0xF),
        ({**terminal_signature,"in":[]},"perm_action @root () () () () ()\n^entry():\na = qalloc any 1\nd = qalloc any 1\ncx a d\ncx a d\nqfree a\nqfree d","entry:4 (qfree)",{},{},1),
    ]

    def test_k81_non_disjoint_rows_refuse_recompute_and_reverse_all_basis_inputs(self):
        for (sig,code,row,basis,expected,mask),raw in product(self.non_disjoint_cases,[False,True]):
            with self.subTest(row=row,raw_inverse=raw):
                obj=make_object(code,sig);t=target()
                obj.sections["schedule"]=doc=e.estimate(obj,t,"root",[],["0"]*4)["effective_schedule"]
                c=e.Catalog((ROOT/"data/ref-0.9.json").read_text(),t)
                c.ledger=BasisLedger(t,e.Schedule(doc,obj,"root"),basis=(basis,expected)[raw],mask=mask)
                e.Source(obj,t,c).region("root",[],["0"]*4,raw_inverse=raw)
                self.assertEqual(basis_outputs(c.ledger),(expected,basis)[raw])
                doc["entries"]=[entry("cleanup",path=[point(obj.symbol("root")["interface_hash"],f"entry:{len(obj.functions['root'].code)-1}")],realisation="recompute")]
                with self.assertRaisesRegex(e.ContractError,"non-disjoint row "+re.escape(row)):e.estimate(obj,t,"root",[],["0"]*4)
                c.ledger=BasisLedger(t,e.Schedule(doc,obj,"root"),basis=basis,mask=mask)
                with self.assertRaisesRegex(e.ContractError,"non-disjoint row "+re.escape(row)):e.Source(obj,t,c).region("root",[],["0"]*4,raw_inverse=raw)

    def test_primitive_joint_inverse_has_only_first_release_owner(self):
        sig={"abi":"0.9","tier":"q","kind":"perm_action","mut":[],"in":[],"mem":[],"args":[],"bounds":[]}
        for first,last in [("a","b"),("b","a")]:
            code=f"perm_action @root () () () () ()\n^entry():\na = qalloc any 1\nb = qalloc any 1\nswap a b\nswap a b\nqfree {first}\nqfree {last}"
            obj=make_object(code,sig)
            doc=e.estimate(obj,target(),"root",[],["0"]*4)["effective_schedule"]
            symbol=obj.symbol("root")["interface_hash"]
            doc["entries"]=[entry("cleanup",path=[point(symbol,"entry:4")],realisation="recompute")]
            obj.sections["schedule"]=doc
            result=e.estimate(obj,target(),"root",[],["0"]*4,include_frame=True)
            self.assertEqual(result["resources"],{"gate_count":"5","time":"5","peak_qubits[data]":"4","qubit_second[data]":"18"})
            self.assertEqual([(d["chain"][-1]["point"],d["owned_points"]) for d in result["cleanup_decisions"]],[("entry:4",["entry:3","entry:4"]),("entry:5",["entry:5"])])

    def test_primitive_cleanup_choice_is_lazy_and_does_not_replay_missing_history(self):
        sig={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1],"in":[],"mem":[],"args":[],"bounds":[]}
        obj=make_object("perm_action @root (x:wire) () () () ()\n^entry():\ng = qalloc any 1\nswap x g\nswap x g\nqfree g",sig);t=target()
        doc=e.estimate(obj,t,"root",[],["0"]*4)["effective_schedule"]
        chosen=entry("cleanup",path=[point(obj.symbol("root")["interface_hash"],"entry:3")],realisation="reverse")
        doc["entries"]=[chosen,chosen]
        c=e.Catalog((ROOT/"data/ref-0.9.json").read_text(),t);c.ledger=e.Ledger(t,e.Schedule(doc,obj,"root"))
        with patch.object(t,"native_gate",wraps=t.native_gate) as native,self.assertRaisesRegex(e.ContractError,"multiple maximal"):
            e.Source(obj,t,c).region("root",[],["0"]*4)
        self.assertEqual(native.call_count,1)  # computing call, before cleanup
        doc["entries"]=[{**chosen,"cleanup":{"realisation":"recompute"}}];obj.sections["schedule"]=doc
        with self.assertRaisesRegex(e.ContractError,"recompute binding remains pending"):
            e.estimate(obj,t,"root",[],["0"]*4)

    def test_general_source_adjoint_cleanup_never_silently_ignores_recompute(self):
        sig={"abi":"0.9","tier":"q","kind":"perm_action","mut":[],"in":[1],"mem":[],"args":[],"bounds":[]}
        code="perm_action @root () (x:wire in) () () ()\n^entry():\nadj action_call @child () (x) () ()\nperm_action @child () (x:wire in) () () ()\n^entry():\ng = qalloc any 1\ncx x g\ncx x g\nqfree g"
        obj=make_program(code,{"root":sig,"child":sig});t=target()
        doc=e.estimate(obj,t,"root",[],["0"]*4)["effective_schedule"]
        doc["entries"]=[entry("cleanup",path=[point(obj.symbol("root")["interface_hash"]),point(obj.symbol("child")["interface_hash"])],realisation="recompute")]
        obj.sections["schedule"]=doc
        with self.assertRaisesRegex(e.ContractError,"recompute binding remains pending"):
            e.estimate(obj,t,"root",[],["0"]*4)

    def test_empty_clean_allocation_cleanup_supports_whole_recompute(self):
        sig={"abi":"0.9","tier":"q","kind":"perm_action","mut":[],"in":[],"mem":[],"args":["i64"],"bounds":[]}
        obj=make_object("perm_action @root () () () (n:i64) ()\n^entry():\ng = qalloc data n\nqfree g",sig)
        for n in [1,3]:
            doc=e.estimate(obj,target(),"root",[str(n)],["0"]*4)["effective_schedule"]
            doc["entries"]=[entry("cleanup",path=[point(obj.symbol("root")["interface_hash"],"entry:1")],generated=0,realisation="recompute")]
            obj.sections["schedule"]=doc
            result=e.estimate(obj,target(),"root",[str(n)],["0"]*4,include_frame=True)
            self.assertEqual(result["resources"],{"gate_count":str(n),"time":str(n),"peak_qubits[data]":str(2*n),"qubit_second[data]":str(2*n*n)})
            self.assertEqual([(d["chain"][-1]["point"],d["ordinal"],d["realisation"]) for d in result["cleanup_decisions"]],[("entry:1",0,"recompute")])
        del obj.sections["schedule"]
        result=e.estimate(obj,target(),"root",[str(2**40)],["0"]*4)
        self.assertEqual(result["resources"],{"gate_count":"0","time":"0","peak_qubits[data]":str(2**40),"qubit_second[data]":"0"})
        self.assertLess(result["summary_operations"],20)

    def test_empty_cleanup_adjoint_and_raw_inverse_keep_correct_carriers(self):
        sig={"abi":"0.9","tier":"q","kind":"perm_action","mut":[],"in":[],"mem":[],"args":[],"bounds":[]}
        obj=make_object("perm_action @root () () () () ()\n^entry():\ng = qalloc data 2\nqfree g",sig);t=target()
        doc=e.estimate(obj,t,"root",[],["0"]*4)["effective_schedule"]
        doc["entries"]=[entry("cleanup",realisation="recompute")]
        for adjoint,raw,where in [(False,False,"entry:1"),(False,True,"entry:1"),(True,False,"entry:0")]:
            with self.subTest(adjoint=adjoint,raw=raw):
                c=e.Catalog((ROOT/"data/ref-0.9.json").read_text(),t);c.ledger=e.Ledger(t,e.Schedule(doc,obj,"root"))
                e.Source(obj,t,c).region("root",[],["0"]*4,adjoint=adjoint,raw_inverse=raw)
                self.assertEqual(c.ledger.finish(),{"gate_count":2,"time":2,"peak_qubits[data]":4,"qubit_second[data]":8})
                self.assertEqual([d["chain"][-1]["point"] for d in c.ledger.cleanup_decisions],[where])

    def test_empty_recompute_carrier_zero_is_separate_from_fresh_leaf_zero(self):
        sig={"abi":"0.9","tier":"q","kind":"perm_action","mut":[],"in":[],"mem":[],"args":[],"bounds":[]}
        obj=make_object("perm_action @root () () () () ()\n^entry():\ng = qalloc data 2\nqfree g",sig)
        model=e.loads(e.jcs(target().doc));model["classes"]["buffer"]={**model["classes"]["data"],"capacity":3};t=e.Target.read(e.jcs(model))
        doc=e.estimate(obj,t,"root",[],["0"]*4,inherited_controls=1)["effective_schedule"]
        path=[point(obj.symbol("root")["interface_hash"],"entry:1")]
        doc["entries"]=[entry("cleanup",path=path,generated=0,realisation="recompute"),entry("alloc",path=path,generated=0,**{"class":"buffer"}),entry("gate",path=path,generated=0,realisation="missing-scheme")]
        obj.sections["schedule"]=doc
        result=e.estimate(obj,t,"root",[],["0"]*4,inherited_controls=1,include_frame=True)
        self.assertEqual(result["resources"],{"gate_count":"2","time":"2","peak_qubits[data]":"2","peak_qubits[buffer]":"3","qubit_second[data]":"4","qubit_second[buffer]":"6"})
        self.assertEqual([r["class"] for r in result["frame"]["scratch"]],["data","buffer"])
        self.assertEqual(len(result["cleanup_decisions"]),1)

    def test_proved_clean_measurement_survives_private_workspace_identity_call(self):
        cc={"abi":"0.9","tier":"cc","kind":"cc","params":[],"results":[]}
        action={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1],"in":[],"mem":[],"args":[],"bounds":[]}
        obj=make_program("fn cc @root () () () () ()\n^entry():\nq = qreg.new data 1\naction_call @work (q) () () ()\nr = measure q\nret\nperm_action @work (q:wire) () () () ()\n^entry():\ns = qalloc data 1\nqfree s",{"root":cc,"work":action})
        result=e.estimate(obj,target(),"root",[],["0"]*4)
        self.assertEqual(result["classical_status"],"COMPLETED")
        self.assertEqual(result["resources"],{"gate_count":"0","time":"4","peak_qubits[data]":"2","qubit_second[data]":"2"})

    def test_schedule_binding_matches_decimal_string_control_count(self):
        sig={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1],"in":[],"mem":[],"args":[],"bounds":[]}
        obj=make_object("perm_action @root (q:wire) () () () ()\n^entry():\nx q",sig)
        doc=e.estimate(obj,target(),"root",[],["0"]*4)["effective_schedule"]
        doc["bindings"]["inherited_controls"]="0";doc["entries"]=[entry("start",time="5")]
        obj.sections["schedule"]=doc
        self.assertEqual(e.estimate(obj,target(),"root",[],["0"]*4)["resources"]["time"],"6")

    def oracle_pair_object(self, tokens=("a","b"), wrapped=False):
        root={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1,4],"in":[1],"mem":[],"args":["token","token"],"bounds":[]}
        oracle={"abi":"0.9","tier":"q","kind":"oracle","in":[1],"tgt":1,"fault":4,"mem":[],"args":[]}
        calls=[("adj " if wrapped and i%2 else "")+f"oracle_call @identity {tk} (x) t f () ()" for i,tk in enumerate(tokens)]
        code="perm_action @root (t:wire, f:wire[4]) (x:wire in) () (a:token, b:token) ()\n^entry():\n"+"\n".join(calls)+"\noracle @identity (x:wire in) (t:wire) (f:wire[4]) () ()\nregs {  }\n^entry():\nlift.retval x"
        return make_program(code,{"root":root,"identity":oracle})

    def test_oracle_cleanup_pairs_use_token_identity_and_current_joint_versions(self):
        args=[["1","0","0","0"]]*2
        for tokens,partition,expected in [(("a","b"),[0,0],["entry:1"]),(("a","b"),[0,1],[]),(("a","b","b","a"),[0,1],["entry:2","entry:3"]),(("a","b","b","a"),[0,0],["entry:1","entry:3"])]:
            with self.subTest(tokens=tokens,partition=partition):
                obj=self.oracle_pair_object(tokens,wrapped=True)
                result=e.estimate(obj,target(),"root",args,["0"]*4,token_aliases=partition,include_frame=True)
                self.assertEqual([d["chain"][-1]["point"] for d in result["cleanup_decisions"]],expected)
                self.assertTrue(all(d["ordinal"]==0 and d["realisation"]=="reverse" for d in result["cleanup_decisions"]))
                single=e.estimate(obj,target(),"identity",[],["1","0","0","0"],token_aliases=[0])
                self.assertEqual(result["resources"]["gate_count"],str(len(tokens)*int(single["resources"]["gate_count"])))

    def test_oracle_pair_recompute_keeps_caller_targets_and_owns_fresh_calls(self):
        obj=self.oracle_pair_object();args=[["1","0","0","0"]]*2
        base=e.estimate(obj,target(),"root",args,["0"]*4,token_aliases=[0,0],include_frame=True)
        doc=base["effective_schedule"]
        doc["entries"]=[entry("cleanup",path=[point(obj.symbol("root")["interface_hash"],"entry:1")],generated=0,realisation="recompute")]
        obj.sections["schedule"]=doc
        result=e.estimate(obj,target(),"root",args,["0"]*4,token_aliases=[0,0],include_frame=True)
        one=e.estimate(obj,target(),"identity",[],["1","0","0","0"],token_aliases=[0])["resources"]
        T,G,P,A=(int(one[k]) for k in ["time","gate_count","peak_qubits[data]","qubit_second[data]"])
        self.assertEqual(result["resources"],{"time":str(3*T+5),"gate_count":str(3*G+5),"peak_qubits[data]":str(P+5),"qubit_second[data]":str(3*A+10*T+55)})
        self.assertEqual([context["path"][-1]["call_index"] for context in result["invocation_contexts"][1:]],[0,0,1])
        self.assertEqual([context["path"][-1]["point"] for context in result["invocation_contexts"][1:]],["entry:0","entry:1","entry:1"])
        self.assertEqual([d["realisation"] for d in result["cleanup_decisions"]],["recompute"])

    def test_oracle_pair_carrier_ties_check_before_target_realisation(self):
        args=[["1","0","0","0"]]*2
        for partition,has_pair in [([0,0],True),([0,1],False)]:
            obj=self.oracle_pair_object()
            doc=e.estimate(obj,target(),"root",args,["0"]*4,token_aliases=partition)["effective_schedule"]
            chosen=entry("cleanup",path=[point(obj.symbol("root")["interface_hash"],"entry:1")],generated=0,realisation="reverse")
            doc["entries"]=[chosen,chosen];obj.sections["schedule"]=doc
            if has_pair:
                with patch.object(e.Target,"native_gate",side_effect=AssertionError("realized before carrier admission")),self.assertRaisesRegex(e.ContractError,"multiple maximal"):
                    e.estimate(obj,target(),"root",args,["0"]*4,token_aliases=partition)
            else:
                result=e.estimate(obj,target(),"root",args,["0"]*4,token_aliases=partition,include_frame=True)
                self.assertEqual(result["cleanup_decisions"],[])

    def test_oracle_cleanup_call_indices_follow_selected_expansion(self):
        args=[["1","0","0","0"]]*2
        for realisation in ["reverse","recompute"]:
            obj=self.oracle_pair_object()
            doc=e.estimate(obj,target(),"root",args,["0"]*4,token_aliases=[0,0])["effective_schedule"]
            carrier=point(obj.symbol("root")["interface_hash"],"entry:1")
            child=point(obj.symbol("identity")["interface_hash"],"$commit")
            doc["entries"]=[entry("cleanup",path=[carrier],realisation=realisation),entry("gate",path=[{**carrier,"call_index":1},child],realisation="native")]
            obj.sections["schedule"]=doc
            if realisation=="reverse":
                with patch.object(e.Target,"native_gate",side_effect=AssertionError("realized before occurrence validation")),self.assertRaisesRegex(e.ContractError,"semantic call occurrence outside expansion"):
                    e.estimate(obj,target(),"root",args,["0"]*4,token_aliases=[0,0])
            else:
                result=e.estimate(obj,target(),"root",args,["0"]*4,token_aliases=[0,0],include_frame=True)
                self.assertEqual([c["path"][-1]["call_index"] for c in result["invocation_contexts"][1:]],[0,0,1])

    def test_oracle_pair_source_adjoint_and_raw_inverse_keep_distinct_paths(self):
        obj=self.oracle_pair_object();t=target();args=[["1","0","0","0"]]*2
        doc=e.estimate(obj,t,"root",args,["0"]*4,token_aliases=[0,0])["effective_schedule"]
        doc["entries"]=[entry("cleanup",realisation="recompute")]
        rows=[]
        for adjoint,raw,points,indices in [(False,False,["entry:0","entry:1","entry:1"],[0,0,1]),(False,True,["entry:1","entry:1","entry:0"],[1,0,0]),(True,False,["entry:1","entry:0","entry:0"],[0,0,1])]:
            with self.subTest(adjoint=adjoint,raw=raw):
                c=e.Catalog((ROOT/"data/ref-0.9.json").read_text(),t)
                c.ledger=e.Ledger(t,e.Schedule(doc,obj,"root"),exact=True)
                source=e.Source(obj,t,c)
                source.region("root",args,["0"]*4,adjoint=adjoint,raw_inverse=raw,token_context=("same","same"))
                rows.append(c.ledger.finish())
                contexts=source.invocations[1:]
                self.assertEqual([ctx["path"][-1]["point"] for ctx in contexts],points)
                self.assertEqual([ctx["path"][-1]["call_index"] for ctx in contexts],indices)
                self.assertEqual([d["chain"][-1]["point"] for d in c.ledger.cleanup_decisions],["entry:0" if adjoint else "entry:1"])
        self.assertEqual(rows[0],rows[1]);self.assertEqual(rows[0],rows[2])

    def test_oracle_pair_matches_control_sets_and_indivisible_outputs(self):
        root={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1,4,4],"in":[1,2],"mem":[],"args":["token"],"bounds":[]}
        oracle={"abi":"0.9","tier":"q","kind":"oracle","in":[1],"tgt":1,"fault":4,"mem":[],"args":[]}
        prefix="perm_action @root (t:wire, f:wire[4], h:wire[4]) (x:wire in, c:wire[2] in) () (tk:token) ()\n^entry():\n"
        suffix="\noracle @identity (x:wire in) (t:wire) (f:wire[4]) () ()\nregs {  }\n^entry():\nlift.retval x"
        cases=[("ctl c[0] ctl c[1] oracle_call @identity tk (x) t f () ()\nctl c[1] ctl c[0] oracle_call @identity tk (x) t f () ()",["entry:1"]),("oracle_call @identity tk (x) t f () ()\noracle_call @identity tk (x) t h () ()\noracle_call @identity tk (x) t f () ()",[]),("oracle_call @identity tk (x) t f () ()\noracle_call @identity tk (x) t h () ()\noracle_call @identity tk (x) t h () ()\noracle_call @identity tk (x) t f () ()",["entry:2","entry:3"])]
        for body,expected in cases:
            with self.subTest(body=body):
                obj=make_program(prefix+body+suffix,{"root":root,"identity":oracle})
                result=e.estimate(obj,target(),"root",[["1","0","0","0"]],["0"]*4,token_aliases=[0],include_frame=True)
                self.assertEqual([d["chain"][-1]["point"] for d in result["cleanup_decisions"]],expected)

    def test_oracle_pairs_survive_disjoint_rows_and_restored_primitive_versions(self):
        root={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1,4,1,1],"in":[],"mem":[],"args":["token"],"bounds":[]}
        oracle={"abi":"0.9","tier":"q","kind":"oracle","in":[1],"tgt":1,"fault":4,"mem":[],"args":[]}
        prefix="perm_action @root (t:wire, f:wire[4], x:wire, spare:wire) () () (tk:token) ()\n^entry():\n"
        suffix="\noracle @identity (x:wire in) (t:wire) (f:wire[4]) () ()\nregs {  }\n^entry():\nlift.retval x"
        call="oracle_call @identity tk (x) t f () ()"
        for middle,expected in [("x spare",["entry:2"]),("x x",[]),("x x\nx x",["entry:3"]),("x t",[]),("x t\nx t",["entry:3"]),("cx x spare\nx x\nx x\ncx x spare",["entry:5"])]:
            with self.subTest(middle=middle):
                obj=make_program(prefix+call+"\n"+middle+"\n"+call+suffix,{"root":root,"identity":oracle})
                result=e.estimate(obj,target(),"root",[["1","0","0","0"]],["0"]*4,token_aliases=[0],include_frame=True)
                self.assertEqual([d["chain"][-1]["point"] for d in result["cleanup_decisions"]],expected)

    def test_oracle_pair_matching_keeps_large_integer_and_f64_bit_values_exact(self):
        oracle={"abi":"0.9","tier":"q","kind":"oracle","in":[1],"tgt":1,"fault":4,"mem":[],"args":[]}
        for ty,left,right,expected in [("i128",str(2**100),str(2**100+1),[]),("i128",str(2**100+1),str(2**100+1),["entry:1"]),("f64","0x0000000000000000","0x8000000000000000",[]),("f64","0x7ff8000000000001","0x7ff8000000000002",[])]:
            with self.subTest(ty=ty,left=left,right=right):
                root={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1,4],"in":[1],"mem":[],"args":["token",ty,ty],"bounds":[]}
                code=f"perm_action @root (t:wire, f:wire[4]) (x:wire in) () (tk:token, a:{ty}, b:{ty}) ()\n^entry():\noracle_call @identity tk (x) t f () (a)\noracle_call @identity tk (x) t f () (b)\noracle @identity (x:wire in) (t:wire) (f:wire[4]) () (v:{ty})\nregs {{  }}\n^entry():\nlift.retval x"
                obj=make_program(code,{"root":root,"identity":{**oracle,"args":[ty]}})
                result=e.estimate(obj,target(),"root",[["1","0","0","0"],left,right],["0"]*4,token_aliases=[0],include_frame=True)
                self.assertEqual([d["chain"][-1]["point"] for d in result["cleanup_decisions"]],expected)

    def test_cc_register_ids_are_opaque_except_equality_and_zero(self):
        sig={"abi":"0.9","tier":"cc","kind":"cc","params":[],"results":[]}
        body="fn cc @root () () () () ()\n^entry():\nq = qreg.new data 1\nid = qreg.id q\nc = const.i64 {literal}\np = icmp.eq id c\nbr p ^yes() ^no()\n^yes():\ntrap\n^no():\nqreg.free q\nret"
        obj=make_object(body.format(literal=1),sig)
        with self.assertRaisesRegex(e.ContractError,"opaque register id"):
            e.estimate(obj,target(),"root",[],["0"]*4)
        result=e.estimate(make_object(body.format(literal=0),sig),target(),"root",[],["0"]*4)
        self.assertEqual(result["classical_steps"],"7")
        self.assertEqual(result["resources"]["qubit_second[data]"],"5")

    def test_cc_register_id_memory_roundtrip_and_freshness_after_uncall(self):
        root={"abi":"0.9","tier":"cc","kind":"cc","params":[],"results":[]}
        create={**root,"results":["qreg[2]"]}
        layout={"ptr_width":32,"H":5,"A_tab":2,"S_cells":0,"globals":{},"interface_regions":{},"heap_base":1,"heap_limit_max":16,"null_size":1}
        text="fn cc @root () () () () ()\n^entry():\nn = const.i64 8\np = alloc n\nq = call @create\nold = qreg.id q\nuncall @create () (q)\na = call @create\nnew = qreg.id a\nsame = icmp.eq old new\nbr same ^bad() ^good()\n^bad():\ntrap\n^good():\nstore.i64 p new\nloaded = load.i64 p\nb = qreg.from_id loaded\nqreg.free b\nstale = qreg.width a\nret\nfn cc @create () (q:qreg[2]) () () ()\n^entry():\nq = qreg.new data 2\nret q"
        obj=make_program(text,{"root":root,"create":create},layout=layout)
        result=e.estimate(obj,target(),"root",[],["0"]*4)
        self.assertEqual(result["classical_steps"],"18")
        self.assertEqual(result["resources"]["peak_qubits[data]"],"2")
        self.assertEqual(result["resources"]["qubit_second[data]"],"26")

    def test_reader_checks_register_result_and_operand_arities(self):
        sig={"abi":"0.9","tier":"cc","kind":"cc","params":[],"results":[]}
        for row in ["qreg.new data 2","qreg.width q","qreg.id q","qreg.from_id id","qreg.slice q 0 1","qreg.concat q q", "x = qreg.free q"]:
            with self.subTest(row=row),self.assertRaisesRegex(e.ContractError,"result arity"):
                make_object("fn cc @root () () () () ()\n^entry():\n"+row+"\nret",sig)
        for row in ["q = qreg.new data", "q = qreg.new data 0", "x = qreg.slice q 0 0"]:
            with self.subTest(row=row),self.assertRaises(e.ContractError):
                make_object("fn cc @root () () () () ()\n^entry():\n"+row+"\nret",sig)

    def test_cc_matching_region_inverse_restores_register_entry_versions(self):
        cc={"abi":"0.9","tier":"cc","kind":"cc","params":[],"results":[]}
        action={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1],"in":[],"mem":[],"args":[],"bounds":[]}
        main="fn cc @root () () () () ()\n^entry():\nq = qreg.new data 1\naction_call @flip (q) () () ()\nadj action_call @flip (q) () () ()\nqreg.free q\nret"
        flip="\nperm_action @flip (t:wire) () () () ()\n^entry():\nx t"
        obj=make_program(main+flip,{"root":cc,"flip":action})
        result=e.estimate(obj,target(),"root",[],["0"]*4)
        self.assertEqual(result["resources"],{"gate_count":"2","peak_qubits[data]":"1","qubit_second[data]":"5","time":"7"})
        obj=make_program(main.replace("adj action_call @flip (q) () () ()\n","")+flip,{"root":cc,"flip":action})
        with self.assertRaisesRegex(e.ContractError,"cleanliness.*evidence"):
            e.estimate(obj,target(),"root",[],["0"]*4)

    def test_reader_enforces_the_published_static_register_view_rules(self):
        cc={"abi":"0.9","tier":"cc","kind":"cc","params":[],"results":[]}
        identity={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1],"in":[],"mem":[],"args":[],"bounds":[]}
        child="\nperm_action @identity (t:wire) () () () ()\n^entry():\nx t\nx t"
        prefix="fn cc @root () () () () ()\n^entry():\nq = qreg.new data 2\ns = qreg.slice q 0 1\n"
        cases=["n = qreg.width s\naction_call @identity (s) () () ()\nret", "n = qreg.width q\naction_call @identity (s) () () ()\nret", "ret", "br ^work(s)\n^work(v:qreg[1]):\naction_call @identity (v) () () ()\nret", "action_call @identity (s) () () ()\naction_call @identity (s) () () ()\nret", "br ^work()\n^work():\nbr ^end()\n^end():\nret"]
        for body in cases:
            with self.subTest(body=body),self.assertRaisesRegex(e.ContractError,"§3.3.*view"):
                make_program(prefix+body+child,{"root":cc,"identity":identity})
        obj=make_program(prefix+"br ^work()\n^work():\naction_call @identity (s) () () ()\nqreg.free q\nret"+child,{"root":cc,"identity":identity})
        result=e.estimate(obj,target(),"root",[],["0"]*4)
        self.assertEqual((result["classical_steps"],result["resources"]["qubit_second[data]"]),("6","12"))

    def test_cc_control_views_are_consumed_once_by_wrapped_region_calls(self):
        cc={"abi":"0.9","tier":"cc","kind":"cc","params":[],"results":[]}
        identity={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1],"in":[],"mem":[],"args":[],"bounds":[]}
        template="fn cc @root () () () () ()\n^entry():\nq = qreg.new data 2\nt = qreg.new data 1\ns = qreg.slice q 0 1\n{wrapper} action_call @identity (t) () () ()\nqreg.free q\nqreg.free t\nret\nperm_action @identity (t:wire) () () () ()\n^entry():\nx t\nx t"
        for wrapper in ["ctl s","adj ctl s","ctl s adj"]:
            obj=make_program(template.format(wrapper=wrapper),{"root":cc,"identity":identity})
            result=e.estimate(obj,target(),"root",[],["0"]*4)
            self.assertEqual(result["classical_status"],"COMPLETED")
            self.assertEqual(result["classical_steps"],"7")
            self.assertEqual(result["resources"],{"gate_count":"2","peak_qubits[data]":"3","qubit_second[data]":"18","time":"9"})

    def test_block_effects_bind_images_zero_sectors_and_segment_reversal(self):
        r={"abi":"0.9","tier":"r","kind":"r","params":[],"results":[]}
        layout={"ptr_width":32,"H":11,"A_tab":2,"S_cells":0,"globals":{},"interface_regions":{},"heap_base":1,"heap_limit_max":1024,"null_size":1}
        devices={"models":{"block":{"version":"0.9"}},"services":{}}
        code="fn r @root () () () () ()\n^entry():\nn = const.i64 512\np = alloc n\ns = const.i64 {sector}\neffect block.read s p\nv = load.i8 p\nz = const.i8 0\nc = icmp.eq v z\nbr c ^zero() ^nonzero()\n^zero():\nret\n^nonzero():\nx = const.i8 1\nret"
        for sector,steps in [(0,10),(1,9)]:
            obj=make_program(code.format(sector=sector),{"root":r},layout={**layout,"block_image":"disk"},data={"disk":"ff"*512},devices=devices)
            result=e.estimate(obj,target(),"root",[],["0"]*4)
            self.assertEqual((result["classical_status"],result["classical_steps"],result["resources"]["time"]),("COMPLETED",str(steps),str(steps)))
        writer={**r,"params":["i64","ptr"]}
        code="fn r @root () () () () ()\n^entry():\nn = const.i64 512\np = alloc n\ns = const.i64 0\nv = const.i8 9\nstore.i8 p v\ncall @writer s p\nuncall @writer (s, p) ()\neffect block.read s p\nx = load.i8 p\nz = const.i8 0\nc = icmp.eq x z\nbr c ^zero() ^nonzero()\n^zero():\nret\n^nonzero():\nbad = const.i8 1\nret\nfn r @writer (s:i64, p:ptr) () () () ()\n^entry():\neffect block.write s p\nret"
        obj=make_program(code,{"root":r,"writer":writer},layout=layout,devices=devices)
        self.assertEqual(e.estimate(obj,target(),"root",[],["0"]*4)["classical_steps"],"15")

    def test_reader_rejects_partial_block_sector_images_before_execution(self):
        r={"abi":"0.9","tier":"r","kind":"r","params":[],"results":[]}
        layout={"ptr_width":32,"H":0,"A_tab":0,"S_cells":0,"globals":{},"interface_regions":{},"heap_base":0,"heap_limit_max":0,"null_size":1,"block_image":"disk"}
        for size in [1,511,513,1023]:
            with self.subTest(size=size),self.assertRaisesRegex(e.ContractError,"K10.*512"):
                make_program("fn r @root () () () () ()\n^entry():\nret",{"root":r},layout=layout,data={"disk":"00"*size})

    def test_reader_requires_each_data_line_to_have_its_own_symbol(self):
        r={"abi":"0.9","tier":"r","kind":"r","params":[],"results":[]}
        obj=make_program("fn r @root () () () () ()\n^entry():\nret",{"root":r},data={"image":"01"})
        symbols=e.jcs({key:value for key,value in obj.sections["symbols"].items() if value["kind"]!="data"})
        text=obj.text.replace(e.jcs(obj.sections["symbols"]),symbols)
        with self.assertRaisesRegex(e.ContractError,"data.*symbols"):
            e.Object.read(text)

    def test_reader_checks_device_declarations_and_zero_entropy_needs_no_tape(self):
        r={"abi":"0.9","tier":"r","kind":"r","params":[],"results":[]}
        layout={"ptr_width":32,"H":2,"A_tab":1,"S_cells":0,"globals":{},"interface_regions":{},"heap_base":1,"heap_limit_max":1,"null_size":1}
        code="fn r @root () () () () ()\n^entry():\nn = const.i64 1\np = alloc n\nz = const.i64 0\neffect entropy.read p z\nret"
        with self.assertRaisesRegex(e.ContractError,"§9.1.*model"):
            make_program(code,{"root":r},layout=layout)
        with self.assertRaisesRegex(e.ContractError,"§9.1.*model"):
            make_program(code,{"root":r},layout=layout,devices={"models":{"unknown":{"version":"0.9"}},"services":{}})
        obj=make_program(code,{"root":r},layout=layout,devices={"models":{"entropy":{"version":"0.9"}},"services":{}})
        result=e.estimate(obj,target(),"root",[],["0"]*4)
        self.assertEqual((result["classical_status"],result["classical_steps"]),("COMPLETED","5"))
        with self.assertRaisesRegex(e.ContractError,"§9.1.*service"):
            make_program("fn cc @root () () () () ()\n^entry():\np = const.i32 0\nn = const.i64 0\nr = hostcall example.service p n\nret",{"root":{**r,"tier":"cc","kind":"cc"}},layout=layout)

    def test_source_releases_match_local_clean_or_borrowed_allocations(self):
        sig={"abi":"0.9","tier":"q","kind":"perm_action","mut":[],"in":[1],"mem":[],"args":[],"bounds":[]}
        for body in ["b = qborrow any 1\nqfree b", "b = qalloc any 1\nqreturn b", "b = qborrow any 1\nquncopy s b", "qreturn s", "qfree s"]:
            obj=make_object("perm_action @root () (s:wire in) () () ()\n^entry():\n"+body,sig)
            with self.subTest(body=body),self.assertRaisesRegex(e.ContractError,"§4.3.*release"):
                e.estimate(obj,target(),"root",[],["0"]*4)

    def test_cc_inverse_pairs_on_disjoint_slices_restore_independent_versions(self):
        cc={"abi":"0.9","tier":"cc","kind":"cc","params":[],"results":[]}
        action={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1],"in":[],"mem":[],"args":[],"bounds":[]}
        text="fn cc @root () () () () ()\n^entry():\nq = qreg.new data 2\na = qreg.slice q 0 1\naction_call @flip (a) () () ()\nb = qreg.slice q 1 1\naction_call @flip (b) () () ()\na = qreg.slice q 0 1\nadj action_call @flip (a) () () ()\nb = qreg.slice q 1 1\nadj action_call @flip (b) () () ()\nqreg.free q\nret\nperm_action @flip (t:wire) () () () ()\n^entry():\nx t"
        for n in [2,1<<40]:
            obj=make_program(text.replace("qreg.new data 2",f"qreg.new data {n}"),{"root":cc,"flip":action})
            result=e.estimate(obj,target(),"root",[],["0"]*4)
            self.assertEqual((result["classical_status"],result["classical_steps"]),("COMPLETED","11"))
            self.assertEqual(result["resources"],{"gate_count":"4","peak_qubits[data]":str(n),"qubit_second[data]":str(13*n),"time":"15"})
            self.assertLess(result["summary_operations"],1000)

    def test_cc_joint_call_inverse_requires_every_current_output_version(self):
        cc={"abi":"0.9","tier":"cc","kind":"cc","params":[],"results":[]}
        action={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1],"in":[],"mem":[],"args":[],"bounds":[]}
        joint={**action,"mut":[1,1]}
        text="fn cc @root () () () () ()\n^entry():\na = qreg.new data 1\nb = qreg.new data 1\naction_call @joint (a, b) () () ()\naction_call @flip (a) () () ()\nadj action_call @flip (a) () () ()\nadj action_call @joint (a, b) () () ()\nqreg.free a\nqreg.free b\nret\nperm_action @joint (a:wire, b:wire) () () () ()\n^entry():\nswap a b\nperm_action @flip (a:wire) () () () ()\n^entry():\nx a"
        obj=make_program(text,{"root":cc,"joint":joint,"flip":action})
        result=e.estimate(obj,target(),"root",[],["0"]*4)
        self.assertEqual(result["resources"],{"gate_count":"4","peak_qubits[data]":"2","qubit_second[data]":"20","time":"13"})
        text=text.replace("adj action_call @flip (a) () () ()\nadj action_call @joint (a, b) () () ()", "adj action_call @joint (a, b) () () ()\nadj action_call @flip (a) () () ()")
        obj=make_program(text,{"root":cc,"joint":joint,"flip":action})
        with self.assertRaisesRegex(e.ContractError,"cleanliness.*evidence"):
            e.estimate(obj,target(),"root",[],["0"]*4)

    def test_cc_region_inverse_pair_keeps_classical_token_identities(self):
        cc={"abi":"0.9","tier":"cc","kind":"cc","params":[],"results":[]}
        action={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1],"in":[],"mem":[],"args":["token"],"bounds":[]}
        oracle={"abi":"0.9","tier":"q","kind":"oracle","in":[1],"tgt":1,"fault":4,"mem":[],"args":[]}
        body="fn cc @root () () () () ()\n^entry():\nz = const.i64 0\na = budget.mint @o z z z z\nb = budget.mint @o z z z z\nq = qreg.new data 1\naction_call @flip (q) () () (a)\nadj action_call @flip (q) () () ({token})\nqreg.free q\nret\nperm_action @flip (q:wire) () () (tk:token) ()\n^entry():\nx q\noracle @o (x:wire in) (t:wire) (f:wire[4]) () ()\nregs {{  }}\n^entry():\nlift.retval x"
        signatures={"root":cc,"flip":action,"o":oracle}
        obj=make_program(body.format(token="b"),signatures)
        with self.assertRaisesRegex(e.ContractError,"cleanliness.*evidence"):
            e.estimate(obj,target(),"root",[],["0"]*4)
        result=e.estimate(make_program(body.format(token="a"),signatures),target(),"root",[],["0"]*4)
        self.assertEqual(result["resources"],{"gate_count":"2","peak_qubits[data]":"1","qubit_second[data]":"5","time":"10"})

    def test_wire_version_ranges_scale_with_source_boundaries(self):
        states=e.WireVersions();q=e.Bundle("allocation",1<<70,"data")
        states.acquire(q);initial=states.capture([q]);saved=dict(states.ranges)
        states.assign([q.bit(0)],1,False)
        states.assign([q.bit(q.width-1)],2,False)
        self.assertEqual(len(states.ranges[q.identity]),3)
        self.assertEqual(saved[q.identity],((0,1<<70,0,True),))
        self.assertEqual(states.capture([q.bit(0),q.slice(0,2)]),((q.identity,0,1,1,False),(q.identity,1,2,0,True)))
        states.restore(initial)
        self.assertEqual(states.ranges,saved)
        with self.assertRaisesRegex(e.ContractError,"inactive wire range"):
            states.capture([e.Bundle(q.identity,1,"data",q.width)])

    def test_nested_uncall_skips_cancelled_register_frames_and_pure_id_queries(self):
        cc={"abi":"0.9","tier":"cc","kind":"cc","params":[],"results":[]}
        create={**cc,"results":["qreg[1]"]}
        code="fn cc @root () () () () ()\n^entry():\ncall @outer\nuncall @outer () ()\nret\nfn cc @outer () () () () ()\n^entry():\nq = call @create\nw = qreg.width q\nuncall @create () (q)\nret\nfn cc @create () (q:qreg[1]) () () ()\n^entry():\nq = qreg.new data 1\nret q"
        result=e.estimate(make_program(code,{"root":cc,"outer":cc,"create":create}),target(),"root",[],["0"]*4)
        self.assertEqual((result["classical_steps"],result["reversed_classical_steps"]),("9","6"))
        self.assertEqual(result["resources"],{"gate_count":"0","peak_qubits[data]":"1","qubit_second[data]":"5","time":"15"})

    def test_classical_and_quantum_segment_reversal_charge_active_frames(self):
        obj=e.Object.read((ROOT/"examples/quantum-uncall-program.bisa").read_text())
        result=e.estimate(obj,target(),"main",[],["0"]*4)
        self.assertEqual((result["classical_steps"],result["reversed_classical_steps"]),("6","4"))
        self.assertEqual(result["resources"],{"gate_count":"2","peak_qubits[data]":"1","qubit_second[data]":"8","time":"12"})
        cc={"abi":"0.9","tier":"cc","kind":"cc","params":[],"results":[]}
        obj=make_program("fn cc @root () () () () ()\n^entry():\ncall @worker\nuncall @worker () ()\nret\nfn cc @worker () () () () ()\n^entry():\nz = const.i8 1\nret",{"root":cc,"worker":cc})
        result=e.estimate(obj,target(),"root",[],["0"]*4)
        self.assertEqual((result["classical_steps"],result["reversed_classical_steps"]),("5","3"))
        self.assertEqual(result["resources"]["time"],"8")
        bound=e.estimate(obj,target(),"root",[],["0"]*4,step_bound=5)
        self.assertEqual(bound["resources"]["time"],"10")
        self.assertIn("reversed", " ".join(bound["bound_assumptions"]))

    def test_quantum_segment_reversal_uses_adjoint_target_cost_and_lifetime_order(self):
        obj=e.Object.read((ROOT/"examples/quantum-uncall-program.bisa").read_text())
        cc=obj.symbol("main")["signature"];worker=obj.symbol("worker")["signature"]
        phase={**obj.symbol("flip")["signature"],"kind":"action"}
        code=obj.functions["main"].raw+"\n"+obj.functions["worker"].raw+"\n"+obj.functions["flip"].raw.replace("perm_action @flip","action @flip").replace("x q","t q")
        obj=make_program(code,{"main":cc,"worker":worker,"flip":phase})
        doc=e.loads(e.jcs(target().doc))
        next(g for g in doc["gates"] if g["op"]=="t")["cost"]["time"]=2
        next(g for g in doc["gates"] if g["op"]=="tdg")["cost"]["time"]=7
        result=e.estimate(obj,e.Target.read(e.jcs(doc)),"main",[],["0"]*4)
        self.assertEqual(result["gates"],{"t":"1","tdg":"1"})
        self.assertEqual(result["resources"],{"gate_count":"2","peak_qubits[data]":"1","qubit_second[data]":"15","time":"19"})
        for n in [1,1<<40]:
            cc={"abi":"0.9","tier":"cc","kind":"cc","params":[],"results":[]}
            code=f"fn cc @root () () () () ()\n^entry():\ncall @worker\nuncall @worker () ()\nret\nfn cc @worker () () () () ()\n^entry():\nq = qreg.new data {n}\nqreg.free q\nret"
            result=e.estimate(make_program(code,{"root":cc,"worker":cc}),target(),"root",[],["0"]*4)
            self.assertEqual((result["classical_steps"],result["reversed_classical_steps"]),("6","4"))
            self.assertEqual(result["resources"],{"gate_count":"0","peak_qubits[data]":str(n),"qubit_second[data]":str(2*n),"time":"10"})

    def test_classical_minted_token_validity_follows_active_history(self):
        cc={"abi":"0.9","tier":"cc","kind":"cc","params":[],"results":[]}
        mint={**cc,"tier":"r","kind":"r","results":["token"]}
        oracle={"abi":"0.9","tier":"q","kind":"oracle","in":[1],"tgt":1,"fault":4,"mem":[],"args":[]}
        action={"abi":"0.9","tier":"q","kind":"perm_action","mut":[],"in":[],"mem":[],"args":["token"],"bounds":[]}
        template="fn cc @root () () () () ()\n^entry():\ntk = call @mint\nbr ^next(tk)\n^next(alias:token):\n{undo}x = qreg.new data 1\nt = qreg.new data 1\nf = qreg.new data 4\n{call}\nret\nfn r @mint () (tk:token) () () ()\n^entry():\nz = const.i64 0\ntk = budget.mint @origin z z z z\nret tk\noracle @origin (x:wire in) (t:wire) (f:wire[4]) () ()\nregs {{  }}\n^entry():\nlift.retval x\noracle @other (x:wire in) (t:wire) (f:wire[4]) () ()\nregs {{  }}\n^entry():\nlift.retval x\nperm_action @sink () () () (tk:token) ()\n^entry():\nscratch = qalloc any 1\nqfree scratch"
        signatures={"root":cc,"mint":mint,"origin":oracle,"other":oracle,"sink":action}
        for call in ["oracle_call @other alias (x) t f () ()","action_call @sink () () () (alias)"]:
            obj=make_program(template.format(undo="uncall @mint () (tk)\n",call=call),signatures)
            result=e.estimate(obj,target(),"root",[],["0"]*4)
            self.assertEqual((result["classical_status"],result["classical_steps"],result["reversed_classical_steps"]),("FAILED","10","4"))
            self.assertEqual(result["resources"],{"gate_count":"0","peak_qubits[data]":"6","qubit_second[data]":"9","time":"14"})
            live=make_program(template.format(undo="",call=call),signatures)
            # §5.4 explicitly permits a token minted for another oracle.
            self.assertEqual(e.estimate(live,target(),"root",[],["0"]*4)["classical_status"],"COMPLETED")

    def test_cc_default_topology_replay_and_selected_callee_schedule(self):
        obj=e.Object.read((ROOT/"examples/native-pair-program.bisa").read_text())
        doc=e.loads(e.jcs(target().doc));doc["topology"]={"vertices":[{"class":"data"} for _ in range(4)],"edges":[]}
        with self.assertRaisesRegex(e.ContractError,"native leaf is not adjacent"):
            e.estimate(obj,e.Target.read(e.jcs(doc)),"main",[],["0"]*4)
        doc["topology"]["edges"]=[[i,j] for i in range(4) for j in range(i+1,4)]
        realised=e.estimate(obj,e.Target.read(e.jcs(doc)),"main",[],["0"]*4)
        self.assertEqual(realised["resources"],{"gate_count":"8","peak_qubits[data]":"4","qubit_second[data]":"84","time":"25"})
        doc["topology"]={"vertices":[{"class":"data"} for _ in range(2)],"edges":[[0,1]]}
        failed=e.estimate(obj,e.Target.read(e.jcs(doc)),"main",[],["0"]*4)
        self.assertEqual((failed["classical_status"],failed["classical_steps"]),("FAILED","3"))
        self.assertEqual(failed["resources"],{"gate_count":"0","peak_qubits[data]":"2","qubit_second[data]":"2","time":"3"})
        action=e.estimate(obj,target(),"pair",[],["0"]*4)
        root=obj.symbol("pair")["interface_hash"]
        obj.sections["schedule"]={"bindings":action["effective_schedule"]["bindings"],"entries":[entry("gate",path=[point(root,"entry:0")],realisation="missing-scheme")]}
        with self.assertRaisesRegex(e.ContractError,"CC/R.*schedule.*pending"):
            e.estimate(obj,target(),"main",[],["0"]*4)
        obj.sections["schedule"]["bindings"]["inherited_controls"]="0"
        with self.assertRaisesRegex(e.ContractError,"CC/R.*schedule.*pending"):
            e.estimate(obj,target(),"main",[],["0"]*4)
        obj.sections["schedule"]["bindings"]={**obj.sections["schedule"]["bindings"],"budget":["1","0","0","0"]}
        # An unmatched tuple does not select that schedule.
        self.assertEqual(e.estimate(obj,target(),"main",[],["0"]*4)["resources"]["time"],"25")

    def test_cc_topology_reserves_uncalled_registers_and_restores_vertex_lifetimes(self):
        cc={"abi":"0.9","tier":"cc","kind":"cc","params":[],"results":[]}
        work={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1],"in":[],"mem":[],"args":[],"bounds":[]}
        code="fn cc @root () () () () ()\n^entry():\nunused = qreg.new data 1\nq = qreg.new data 1\naction_call @work (q) () () ()\nret\nperm_action @work (q:wire) () () () ()\n^entry():\ns = qalloc any 1\ncx q s\ncx q s\nqfree s"
        obj=make_program(code,{"root":cc,"work":work})
        doc=e.loads(e.jcs(target().doc));doc["topology"]={"vertices":[{"class":"data"} for _ in range(3)],"edges":[[0,1]]}
        with self.assertRaisesRegex(e.ContractError,"native leaf is not adjacent"):
            e.estimate(obj,e.Target.read(e.jcs(doc)),"root",[],["0"]*4)
        doc["topology"]["edges"]=[[0,1],[0,2],[1,2]];t=e.Target.read(e.jcs(doc))
        result=e.estimate(obj,t,"root",[],["0"]*4)
        self.assertEqual(result["resources"],{"gate_count":"2","peak_qubits[data]":"3","qubit_second[data]":"11","time":"6"})
        for fixture in ["quantum-uncall-program","register-views-program","register-disjoint-pairs"]:
            obj=e.Object.read((ROOT/"examples"/(fixture+".bisa")).read_text())
            self.assertEqual(e.estimate(obj,t,"main",[],["0"]*4)["resources"],e.estimate(obj,target(),"main",[],["0"]*4)["resources"])

    def test_classical_explicit_alias_partitions_distinguish_equal_token_tuples(self):
        obj=e.Object.read((ROOT/"tests/fixtures/token-alias-source-gap.bisa").read_text())
        params=[["1","0","0","0"]]*2
        shared=e.estimate(obj,target(),"root",params,["0"]*4,token_aliases=[0,0])
        distinct=e.estimate(obj,target(),"root",params,["0"]*4,token_aliases=[0,1])
        self.assertEqual((shared["classical_status"],shared["classical_steps"],shared["reversed_classical_steps"],shared["resources"]["time"]),("COMPLETED","4","2","6"))
        self.assertEqual((distinct["classical_status"],distinct["classical_steps"],distinct["resources"]["time"]),("FAILED","3","3"))
        self.assertEqual(shared["params_hash"],distinct["params_hash"])
        self.assertNotEqual(shared["schedule_hash"],distinct["schedule_hash"])
        self.assertEqual(shared["invocation"]["token_aliases"],[0,0])
        self.assertEqual(distinct["effective_schedule"]["bindings"]["token_aliases"],[0,1])

    def test_classical_alias_partitions_reject_noncanonical_or_inconsistent_bindings(self):
        obj=e.Object.read((ROOT/"tests/fixtures/token-alias-source-gap.bisa").read_text())
        params=[["1","0","0","0"]]*2
        for partition in [[1,1],[0,2],[0],[],[False,False],["0","0"],[0,-1]]:
            with self.subTest(partition=partition),self.assertRaisesRegex(e.ContractError,"E_ARG.*token_aliases"):
                e.estimate(obj,target(),"root",params,["0"]*4,token_aliases=partition)
        with self.assertRaisesRegex(e.ContractError,"E_ARG.*token_aliases"):
            e.estimate(obj,target(),"root",[["1","0","0","0"],["2","0","0","0"]],["0"]*4,token_aliases=[0,0])

    def test_classical_alias_schedule_schema_checks_arity_and_missing_upgrade(self):
        obj=e.Object.read((ROOT/"tests/fixtures/token-alias-source-gap.bisa").read_text())
        params=[["1","0","0","0"]]*2
        result=e.estimate(obj,target(),"root",params,["0"]*4,token_aliases=[0,0])
        doc=e.loads(e.jcs(result["effective_schedule"]))
        e.Schedule(doc,obj,"root")
        doc["bindings"]["token_aliases"]=[0,1,2]
        with self.assertRaisesRegex(e.ContractError,"E_ARG.*token_aliases"):
            e.Schedule(doc,obj,"root")
        doc=e.loads(e.jcs(result["effective_schedule"]))
        del doc["bindings"]["token_aliases"]
        doc["entries"]=[entry("start",path=[point(obj.symbol("root")["interface_hash"],"entry:0")],time=100)]
        obj.sections["schedule"]=doc
        with self.assertRaisesRegex(e.ContractError,"E_ARG.*token_aliases"):
            e.estimate(obj,target(),"root",params,["0"]*4,token_aliases=[0,0])

    def test_cc_and_q_alias_contexts_forward_without_an_action_primary(self):
        action={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1,4],"in":[1],"mem":[],"args":["token","token"],"bounds":[]}
        leaf={"abi":"0.9","tier":"q","kind":"oracle","in":[1],"tgt":1,"fault":4,"mem":[],"args":["token"]}
        text="perm_action @root (t:wire, f:wire[4]) (x:wire in) () (a:token, b:token) ()\n^entry():\naction_call @bridge (t, f) (x) () (b, a)\nperm_action @bridge (t:wire, f:wire[4]) (x:wire in) () (u:token, v:token) ()\n^entry():\noracle_call @leaf u (x) t f () (v)\noracle @leaf (x:wire in) (t:wire) (f:wire[4]) () (extra:token)\nregs {  }\n^entry():\nlift.retval x"
        obj=make_program(text,{"root":action,"bridge":action,"leaf":leaf})
        args=[["1","0","0","0"]]*2
        for partition in [[0,0],[0,1]]:
            result=e.estimate(obj,target(),"root",args,["0"]*4,token_aliases=partition,include_frame=True)
            contexts=result["invocation_contexts"]
            self.assertEqual([(r["region"],r["invocation"]["token_aliases"]) for r in contexts],[("root",partition),("bridge",partition),("leaf",partition)])
            self.assertEqual(contexts[-1]["invocation"]["budget"],["1","0","0","0"])
        # Private source context ids preserve global equality even when each
        # callee renumbers its local partition by first occurrence.
        seen=[]
        class Trace(e.Source):
            def region(self,*args,**kwargs):
                seen.append((args[0],kwargs.get("token_context")))
                return super().region(*args,**kwargs)
        for adjoint,inverse in [(False,False),(True,False),(False,True)]:
            seen.clear()
            source=Trace(obj,target(),e.Catalog((ROOT/"data/ref-0.9.json").read_text(),target()))
            source.region("root",args,["0"]*4,token_context=("A","B"),adjoint=adjoint,raw_inverse=inverse)
            self.assertEqual(seen,[("root",("A","B")),("bridge",("B","A")),("leaf",("B","A"))])

    def test_q_oracle_aliases_prepend_only_the_actual_primary_token(self):
        root={"abi":"0.9","tier":"q","kind":"oracle","in":[1],"tgt":1,"fault":4,"mem":[],"args":["token","token"]}
        leaf={**root,"args":["token"]}
        code="oracle @root (x:wire in) (t:wire) (f:wire[4]) () (a:token, b:token)\nregs { r:reg[1], g:reg[4] }\n^entry():\nlift.oracle_call @leaf a (x) r g () (b)\nlift.retval x\noracle @leaf (x:wire in) (t:wire) (f:wire[4]) () (extra:token)\nregs {  }\n^entry():\nlift.retval x"
        obj=make_program(code,{"root":root,"leaf":leaf})
        result=e.estimate(obj,target(),"root",[["1","0","0","0"]]*2,["2","0","0","0"],token_aliases=[0,1,1],include_frame=True)
        contexts=result["invocation_contexts"]
        self.assertEqual(contexts[0]["invocation"]["token_aliases"],[0,1,1])
        self.assertEqual(len(contexts),5)
        for context in contexts[1:]:
            self.assertEqual(context["invocation"]["token_aliases"],[0,0])
            self.assertEqual(context["invocation"]["budget"],["1","0","0","0"])
        with self.assertRaisesRegex(e.ContractError,"E_ARG.*token_aliases"):
            e.estimate(obj,target(),"root",[["1","0","0","0"]]*2,["2","0","0","0"],token_aliases=[0,0,0])

    def test_q_aliases_survive_fixed_lproc_bindings_and_lexical_captures(self):
        root={"abi":"0.9","tier":"q","kind":"oracle","in":[1],"tgt":4,"fault":4,"mem":[],"args":["token","token"]}
        worker={"abi":"0.9","tier":"q","kind":"lproc","params":[1],"result":4,"tokens":["token","token"],"args":[],"mem":[]}
        leaf={**root,"tgt":1,"args":["token"]}
        layout={"ptr_width":32,"H":1,"A_tab":0,"S_cells":3,"globals":{},"interface_regions":{},"heap_base":1,"heap_limit_max":1,"null_size":1}
        code="oracle @root (x:wire in) (t:wire[4]) (f:wire[4]) () (a:token, b:token)\nregs { r:reg[4] }\n^entry():\nr = lift.call @worker (x) (b, a) () ()\nlift.retval r\nlproc @worker (v:reg[1]) (w:reg[4]) (u:token token, z:token token) () ()\nregs { tmp:reg[1] }\n^entry():\nlift.oracle_call @leaf u (v) tmp w () (z)\nlift.ret w\noracle @leaf (x:wire in) (t:wire) (f:wire[4]) () (extra:token)\nregs {  }\n^entry():\nlift.retval x"
        obj=make_program(code,{"root":root,"worker":worker,"leaf":leaf},layout=layout)
        seen=[]
        class Trace(e.Source):
            def region(self,*args,**kwargs):
                seen.append((args[0],kwargs.get("token_context")))
                return super().region(*args,**kwargs)
        source=Trace(obj,target(),e.Catalog((ROOT/"data/ref-0.9.json").read_text(),target()))
        source.region("root",[["1","0","0","0"]]*2,["1","1","8","1"],token_context=("P","A","B"))
        self.assertEqual(seen,[("root",("P","A","B")),("leaf",("B","A"))])

    def test_classical_request_copies_alias_arguments_budget_and_selected_schedule(self):
        obj=e.Object.read((ROOT/"tests/fixtures/token-alias-source-gap.bisa").read_text())
        params=[["1","0","0","0"]]*2;budget=["0"]*4;aliases=[0,0]
        result=e.estimate(obj,target(),"root",params,budget,token_aliases=aliases)
        params[0][0]="2";params.append("3");budget[0]="4";aliases[0]=1
        self.assertEqual(result["invocation"],{"args":[["1","0","0","0"]]*2,"budget":["0"]*4,"token_aliases":[0,0]})
        fixture=sibling(ROOT, "bennett-isa-spec") / "conformance/fixtures/controlled-action-09"
        obj=e.Object.read((fixture/"controlled.bisa").read_text());t=e.Target.read((fixture/"target.json").read_text())
        result=e.estimate(obj,t,"controlled",[],["0"]*4)
        saved=e.jcs(result["effective_schedule"])
        obj.sections["schedule"]["entries"][0]["gate"]["realisation"]="missing-scheme"
        self.assertEqual(e.jcs(result["effective_schedule"]),saved)

    def test_q_aliases_survive_qinplace_templates_and_source_loop_captures(self):
        action={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1],"in":[],"mem":[],"args":["token"],"bounds":[2]}
        oracle={"abi":"0.9","tier":"q","kind":"oracle","in":[1],"tgt":1,"fault":4,"mem":[],"args":[]}
        code="perm_action @root (x:wire) () () (tk:token) ()\nregs {  } bounds { 2 }\n^entry():\nqloop 2 {\nqinplace @identity @identity tk x\n}\noracle @identity (x:wire in) (t:wire) (f:wire[4]) () ()\nregs {  }\n^entry():\nlift.retval x"
        obj=make_program(code,{"root":action,"identity":oracle})
        result=e.estimate(obj,target(),"root",[["1","0","0","0"]],["0"]*4,token_aliases=[0],include_frame=True)
        contexts=result["invocation_contexts"]
        self.assertEqual(len(contexts),5)
        self.assertTrue(all(context["invocation"]["token_aliases"]==[0] for context in contexts))
        self.assertEqual([c["path"][0]["iteration"] for c in contexts[1:]],[[0],[0],[1],[1]])
        # The action's budget holder contributes no identity slot.
        source=e.Source(obj,target(),e.Catalog((ROOT/"data/ref-0.9.json").read_text(),target()))
        source.region("root",[["1","0","0","0"]],["0"]*4,token_context=("argument",))
        source.region("root",[["1","0","0","0"]],["2","0","0","0"],token_context=("argument",))
        with self.assertRaisesRegex(e.ContractError,"changed its tuple"):
            source.region("root",[["2","0","0","0"]],["0"]*4,token_context=("argument",))

    def test_classical_step_bound_cannot_relabel_a_quantum_entry(self):
        obj=e.Object.read((ROOT/"examples/native-pair-program.bisa").read_text())
        with self.assertRaisesRegex(e.ContractError,"E_ARG.*classical.*CC/R"):
            e.estimate(obj,target(),"pair",[],["0"]*4,step_bound=1)

    def test_reader_rejects_empty_blocks_in_actions_as_the_text_grammar_requires(self):
        signature={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1],"in":[],"mem":[],"args":[],"bounds":[]}
        for body in ["^entry():", "^entry():\nx q\n^empty():"]:
            with self.subTest(body=body),self.assertRaisesRegex(e.ContractError,"§16.2.*instruction"):
                make_object("perm_action @root (q:wire) () () () ()\n"+body,signature)

    def test_reader_rejects_empty_present_structured_scopes_even_at_zero_trips(self):
        loop={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1],"in":[],"mem":[],"args":[],"bounds":[0]}
        with self.assertRaisesRegex(e.ContractError,"§16.2.*instruction"):
            make_object("perm_action @root (t:wire) () () () ()\nregs {  } bounds { 0 }\n^entry():\nqloop 0 {\n}",loop)
        branch={**loop,"in":[1],"bounds":[]}
        for body in ["qif c {\n} {\nx t\n}","qif c {\nx t\n} {\n}"]:
            with self.subTest(body=body),self.assertRaisesRegex(e.ContractError,"§16.2.*instruction"):
                make_object("perm_action @root (t:wire) (c:wire in) () () ()\n^entry():\n"+body,branch)

    def test_cc_register_program_matches_complete_native_vm_ledger(self):
        obj=e.Object.read((ROOT/"examples/native-pair-program.bisa").read_text())
        result=e.estimate(obj,target(),"main",[],["0"]*4)
        self.assertEqual(result["label"],"exact")
        self.assertEqual(result["classical_steps"],"7")
        self.assertEqual(result["resources"],{"gate_count":"8","peak_qubits[data]":"4","qubit_second[data]":"84","time":"25"})

    def test_cc_measurement_of_proved_clean_register_consumes_all_aliases(self):
        sig={"abi":"0.9","tier":"cc","kind":"cc","params":[],"results":[]}
        for width in [1,2,128]:
            obj=make_object(f"fn cc @root () () () () ()\n^entry():\nq = qreg.new data {width}\nr = measure q\nz = const.i{width} 0\nc = icmp.eq r z\nbr c ^ok() ^bad()\n^ok():\nret\n^bad():\ntrap",sig)
            result=e.estimate(obj,target(),"root",[],["0"]*4)
            self.assertEqual((result["classical_status"],result["classical_steps"]),("COMPLETED","6"))
            self.assertEqual(result["resources"],{"gate_count":"0","peak_qubits[data]":str(width),"qubit_second[data]":str(width),"time":"6"})
        obj=make_object("fn cc @root () () () () ()\n^entry():\nq = qreg.new data 2\nid = qreg.id q\nr = measure q\nstale = qreg.from_id id\nret",sig)
        result=e.estimate(obj,target(),"root",[],["0"]*4)
        self.assertEqual((result["classical_status"],result["classical_steps"]),("FAILED","4"))
        self.assertEqual(result["resources"]["qubit_second[data]"],"4")

    def test_cc_measurement_width_fault_and_segment_uncall_preflight(self):
        sig={"abi":"0.9","tier":"cc","kind":"cc","params":[],"results":[]}
        for measured,status,steps,area in [(1,"FAILED","3","2"),(2,"COMPLETED","5","2")]:
            code=f"fn cc @root () () () () ()\n^entry():\nn = const.i64 2\nq = qreg.new data n\nr = measure.i{measured} q\nz = const.i{measured} 0\nret"
            result=e.estimate(make_object(code,sig),target(),"root",[],["0"]*4)
            self.assertEqual((result["classical_status"],result["classical_steps"]),(status,steps))
            self.assertEqual((result["resources"]["time"],result["resources"]["qubit_second[data]"]),(steps,area))
        take={**sig,"params":["qreg[2]"],"results":["i2"]}
        obj=make_program("fn cc @root () () () () ()\n^entry():\nq = qreg.new data 2\nr = call @take q\nuncall @take (q) (r)\nret\nfn cc @take (q:qreg[2]) (r:i2) () () ()\n^entry():\nr = measure q\nret r",{"root":sig,"take":take})
        result=e.estimate(obj,target(),"root",[],["0"]*4)
        self.assertEqual((result["classical_status"],result["classical_steps"],result["reversed_classical_steps"]),("FAILED","5","0"))
        self.assertEqual(result["resources"],{"gate_count":"0","peak_qubits[data]":"2","qubit_second[data]":"4","time":"5"})

    def test_reader_checks_measurement_static_width_and_dynamic_spelling(self):
        sig={"abi":"0.9","tier":"cc","kind":"cc","params":[],"results":[]}
        cases=[("q = qreg.new data 2\nr = measure.i1 q",sig),("n = const.i64 2\nq = qreg.new data n\nr = measure q",sig),("q = qreg.new data 129\nr = measure q",sig),("r = measure.i2 q",{**sig,"params":["qreg[3]"]}),("r = measure q",{**sig,"params":["qreg[*]"]})]
        for body,signature in cases:
            params="q:"+signature["params"][0] if signature["params"] else ""
            with self.subTest(body=body),self.assertRaisesRegex(e.ContractError,"§3.3.*measure"):
                make_object(f"fn cc @root ({params}) () () () ()\n^entry():\n{body}\nret",signature)

    def test_measurement_width_analysis_defers_unknown_dominating_definitions(self):
        sig={"abi":"0.9","tier":"cc","kind":"cc","params":[],"results":[]}
        obj=make_object("fn cc @root () () () () ()\n^entry():\na = qreg.new data 2\nbr ^join()\n^join():\nb = qreg.new data 1\nq = qreg.concat a b\nr = measure q\nret",sig)
        result=e.estimate(obj,target(),"root",[],["0"]*4)
        self.assertEqual((result["classical_status"],result["classical_steps"]),("COMPLETED","6"))
        self.assertEqual(result["resources"],{"gate_count":"0","peak_qubits[data]":"3","qubit_second[data]":"10","time":"6"})

    def test_cc_dynamic_register_width_zero_capacity_and_alias_lifetimes(self):
        sig={"abi":"0.9","tier":"cc","kind":"cc","params":["i64"],"results":[]}
        obj=make_object("fn cc @root (n:i64) () () () ()\n^entry():\nq = qreg.new data n\nid = qreg.id q\na = qreg.from_id id\nw = qreg.width a\nqreg.free q\nstale = qreg.width a\nret",sig)
        for n in [0,2,1<<40]:
            result=e.estimate(obj,target(),"root",[str(n)],["0"]*4)
            self.assertEqual(result["classical_steps"],"6")  # stale alias traps before ret
            self.assertEqual(result["resources"]["time"],"6")
            self.assertEqual(result["resources"]["peak_qubits[data]"],str(n))
            self.assertEqual(result["resources"]["qubit_second[data]"],str(4*n))
        doc=e.loads(e.jcs(target().doc));doc["classes"]["data"]["capacity"]=1
        result=e.estimate(obj,e.Target.read(e.jcs(doc)),"root",["2"],["0"]*4)
        self.assertEqual(result["classical_steps"],"1")
        self.assertEqual(result["resources"]["peak_qubits[data]"],"0")

    def test_cc_register_call_alias_and_uncall_restores_ledger_without_reusing_ids(self):
        root={"abi":"0.9","tier":"cc","kind":"cc","params":[],"results":[]}
        create={**root,"results":["qreg[2]"]}
        text="fn cc @root () () () () ()\n^entry():\nq = call @create\nid = qreg.id q\nuncall @create () (q)\nstale = qreg.from_id id\nret\nfn cc @create () (q:qreg[2]) () () ()\n^entry():\nq = qreg.new data 2\nret q"
        obj=make_program(text,{"root":root,"create":create})
        result=e.estimate(obj,target(),"root",[],["0"]*4)
        self.assertEqual(result["classical_steps"],"6")
        self.assertEqual(result["resources"],{"gate_count":"0","peak_qubits[data]":"2","qubit_second[data]":"10","time":"9"})
        echo={**root,"params":["qreg[*]"],"results":["qreg[*]"]}
        obj=make_program("fn cc @root () () () () ()\n^entry():\nq = qreg.new data 2\na = call @echo q\nqreg.free a\nstale = qreg.width q\nret\nfn cc @echo (q:qreg[*]) (r:qreg[*]) () () ()\n^entry():\nret q",{"root":root,"echo":echo})
        result=e.estimate(obj,target(),"root",[],["0"]*4)
        self.assertEqual(result["classical_steps"],"5")
        self.assertEqual(result["resources"]["qubit_second[data]"],"6")

    def test_cc_register_slice_concat_and_transfer_width_faults(self):
        root={"abi":"0.9","tier":"r","kind":"r","params":[],"results":[]}
        identity={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1],"in":[],"mem":[],"args":[],"bounds":[]}
        code="fn r @root () () () () ()\n^entry():\na = qreg.new data 2\nb = qreg.new data 1\nq = qreg.concat a b\ns = qreg.slice q 1 1\naction_call @identity (s) () () ()\nn = qreg.width q\nqreg.free q\nret\nperm_action @identity (x:wire) () () () ()\n^entry():\nx x\nx x"
        obj=make_program(code,{"root":root,"identity":identity})
        result=e.estimate(obj,target(),"root",[],["0"]*4)
        self.assertEqual(result["classical_steps"],"8")
        self.assertEqual(result["resources"],{"gate_count":"2","peak_qubits[data]":"3","qubit_second[data]":"23","time":"10"})
        # A dynamic width mismatch is a terminal failed prefix, before the call.
        dynamic={**root,"params":["i64"]}
        obj=make_program("fn r @root (n:i64) () () () ()\n^entry():\nq = qreg.new data n\naction_call @identity (q) () () ()\nret\nperm_action @identity (x:wire) () () () ()\n^entry():\nx x\nx x",{"root":dynamic,"identity":identity})
        result=e.estimate(obj,target(),"root",["2"],["0"]*4)
        self.assertEqual((result["classical_steps"],result["gates"]),("2",{}))
        self.assertEqual(result["resources"]["qubit_second[data]"],"2")


    def test_trillion_visit_while_summary_preserves_class_and_flag_timing(self):
        n=2**40
        sig={"abi":"0.9","tier":"q","kind":"perm_action","mut":[],"in":[n],"mem":[],"args":[],"bounds":[n]}
        body=f"perm_action @child () (cond:wire[{n}] in) () () ()\nregs {{  }} bounds {{ {n} }}\n^entry():\nc = qalloc data 1\nqloop {n} while cond {{\nx c[0]\nx c[0]\nqfree c\nc = qalloc special 1\n}}\nqfree c"
        doc=e.loads(e.jcs(target().doc));doc["classes"]["special"]=dict(doc["classes"]["data"]);t=e.Target.read(e.jcs(doc));original=e.Catalog
        class BoundedWork(original):
            def body(self,*args,**kw):
                if self.visits>1000:raise AssertionError("while iterations were enumerated")
                return super().body(*args,**kw)
        duration=14*n-10
        for adjoint,data_extra,special_area in [(False,3,duration-3),(True,6*n-3,8*n-7)]:
            text=f"perm_action @root () (cond:wire[{n}] in) () () ()\n^entry():\n"+("adj " if adjoint else "")+"action_call @child () (cond) () ()\n"+body
            obj=make_program(text,{"root":{**sig,"bounds":[]},"child":sig})
            with patch.object(e,"Catalog",BoundedWork):result=e.estimate(obj,t,"root",[],["0"]*4)
            self.assertEqual(result["resources"]["time"],str(duration))
            self.assertEqual(result["resources"]["qubit_second[data]"],str(2*n*duration+data_extra))
            self.assertEqual(result["resources"]["qubit_second[special]"],str(special_area))
            self.assertEqual(result["gates"],{"ccx":str(2*(n-1)),"cx":"2","x":str(2*n)})
            self.assertLess(result["summary_operations"],1000)

    def test_while_loop_carries_bindings_and_keeps_its_adjoint_flag_order(self):
        sig={"abi":"0.9","tier":"q","kind":"perm_action","mut":[],"in":[3],"mem":[],"args":[],"bounds":[3]}
        body="perm_action @child () (cond:wire[3] in) () () ()\nregs {  } bounds { 3 }\n^entry():\nc = qalloc data 1\nqloop 3 while cond {\nx c[0]\nx c[0]\nqfree c\nc = qalloc special 1\n}\nqfree c"
        doc=e.loads(e.jcs(target().doc));doc["classes"]["special"]=dict(doc["classes"]["data"]);t=e.Target.read(e.jcs(doc))
        for adjoint,data_area,special_area in [(False,"195","29"),(True,"207","17")]:
            root="perm_action @root () (cond:wire[3] in) () () ()\n^entry():\n"+("adj " if adjoint else "")+"action_call @child () (cond) () ()\n"
            obj=make_program(root+body,{"root":{**sig,"bounds":[]},"child":sig})
            analytic=e.estimate(obj,t,"root",[],["0"]*4);actual=e.estimate(obj,t,"root",[],["0"]*4,include_frame=True)
            self.assertEqual(actual["exact_resources"],analytic["exact_resources"])
            self.assertEqual(actual["resources"]["time"],"32")
            self.assertEqual(actual["resources"]["qubit_second[data]"],data_area)
            self.assertEqual(actual["resources"]["qubit_second[special]"],special_area)
            self.assertEqual(actual["gates"],{"ccx":"4","cx":"2","x":"6"})
        c=e.Catalog((ROOT/"data/ref-0.9.json").read_text(),t);ledger=e.Ledger(t,e.Schedule(schedule()));c.ledger=ledger
        e.Source(obj,t,c).region("child",[],["0"]*4,{"cond":e.Bundle("condition",3,"data")},raw_inverse=True)
        rows=ledger.finish();self.assertEqual(rows["qubit_second[data]"],195)
        c=e.Catalog((ROOT/"data/ref-0.9.json").read_text(),t)
        profile=e.Source(obj,t,c).region("child",[],["0"]*4,{"cond":e.Bundle("condition",3,"data")},raw_inverse=True)
        self.assertEqual(profile.resources(t,{"data":3}),rows)

    def test_while_summary_counts_scheme_workspace_borrow_and_accuracy(self):
        sig={"abi":"0.9","tier":"q","kind":"perm_action","mut":[],"in":[3],"mem":[],"args":[],"bounds":[3]}
        obj=make_object("perm_action @root () (cond:wire[3] in) () () ()\nregs {  } bounds { 3 }\n^entry():\nqloop 3 while cond {\nb = qborrow special 1\nx b\nx b\nqreturn b\n}",sig)
        doc=e.loads(e.jcs(target().doc));doc["classes"]["special"]={**doc["classes"]["data"],"dirty_rate":2}
        next(g for g in doc["gates"] if g["op"]=="x")["controls"]["min"]=2
        doc["schemes"]=[{"name":"controlled-x","realises":{"op":"x","controls":{"min":1,"max":1}},"ancillae":{"count":2,"class":"special","state":"clean"},"template":[{"gate":"cx","wires":["c[0]","t"]}]}]
        t=e.Target.read(e.jcs(doc))
        summary=e.estimate(obj,t,"root",[],["0"]*4,epsilon="0.1")
        replay=e.estimate(obj,t,"root",[],["0"]*4,epsilon="0.1",include_frame=True)
        self.assertEqual(summary["exact_resources"],replay["exact_resources"])
        self.assertEqual(summary["gates"],replay["gates"])
        self.assertEqual(summary["resources"]["qubit_second[data]"],"192")
        self.assertEqual(summary["resources"]["qubit_second[special]"],"24")
        self.assertEqual(summary["resources"]["peak_qubits[special]"],"3")
        self.assertEqual(summary["resolved_default_epsilon_share"],{"numerator":"1","denominator":"60"})

    def test_qif_reallocations_keep_each_arm_and_outer_lifetime_bindings(self):
        sig={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1],"in":[],"mem":[],"args":[],"bounds":[]}
        body="perm_action @child (q:wire) () () () ()\n^entry():\nc = qalloc data 1\nqif q {\nqfree c\nc = qalloc special 2\nx c[1]\nx c[1]\n} {\nqfree c\nc = qalloc data 3\nx c[2]\nx c[2]\n}\nqfree c"
        doc=e.loads(e.jcs(target().doc));doc["classes"]["special"]=dict(doc["classes"]["data"]);t=e.Target.read(e.jcs(doc))
        for adjoint in [False,True]:
            text="perm_action @root (q:wire) () () () ()\n^entry():\n"+("adj " if adjoint else "")+"action_call @child (q) () () ()\n"+body
            obj=make_program(text,{"root":sig,"child":sig});analytic=e.estimate(obj,t,"root",[],["0"]*4)
            actual=e.estimate(obj,t,"root",[],["0"]*4,include_frame=True)
            self.assertEqual(actual["exact_resources"],analytic["exact_resources"])
            self.assertEqual(actual["resources"]["time"],"6")
            self.assertEqual(actual["resources"]["qubit_second[data]"],"15")
            self.assertEqual(actual["resources"]["qubit_second[special]"],"6")
            widths=[r["width"] for r in actual["frame"]["scratch"]]
            self.assertEqual(widths,[3,2,1] if adjoint else [1,2,3])

    def test_analytic_predicate_depth_matches_replay_admission(self):
        sig={"abi":"0.9","tier":"q","kind":"action","mut":[1,1,1],"in":[],"mem":[],"args":[],"bounds":[]}
        obj=make_object("action @root (a:wire, b:wire, t:wire) () () () ()\n^entry():\nqpred a\nqpred b\nx t\nqunpred b\nqunpred a",sig)
        doc=e.loads(e.jcs(target().doc));doc["capabilities"]["max_predicate_depth"]=1;t=e.Target.read(e.jcs(doc))
        for replay in [False,True]:
            with self.assertRaisesRegex(e.ContractError,"max_predicate_depth"):
                e.estimate(obj,t,"root",[],["0"]*4,include_frame=replay)

    def test_many_procedure_returns_validate_global_locations_only_linearly(self):
        count=32
        root={"abi":"0.9","tier":"q","kind":"oracle","in":[1],"tgt":1,"fault":4,"mem":[],"args":[]}
        child={"abi":"0.9","tier":"q","kind":"lproc","params":[1],"result":1,"tokens":[],"args":[],"mem":[]}
        text="oracle @root (x:wire in) (t:wire) (f:wire[4]) () ()\nregs { "+", ".join(f"r{i}:reg[1]" for i in range(count))+" }\n^entry():\n"+"\n".join(f"r{i} = lift.call @f{i} (x) () () ()" for i in range(count))+f"\nlift.retval r{count-1}\n"+"\n".join(f"lproc @f{i} (a:reg[1]) (r:reg[1]) () () ()\n^entry():\nlift.ret a" for i in range(count))
        layout={"ptr_width":32,"H":1,"A_tab":0,"S_cells":4,"globals":{},"interface_regions":{},"heap_base":1,"heap_limit_max":0,"null_size":1}
        obj=make_program(text,{"root":root,**{f"f{i}":child for i in range(count)}},layout=layout)
        original=e.Catalog;bindings=[]
        class Counting(original):
            def bind(self,formals,*args,**kw):
                if len(formals)==1 and isinstance(formals[0],dict) and formals[0].get("name")=="location":bindings.append(1)
                return super().bind(formals,*args,**kw)
        with patch.object(e,"Catalog",Counting):result=e.estimate(obj,target(),"root",[],["1","0","16","1"])
        self.assertEqual(result["label"],"exact")
        self.assertLessEqual(len(bindings),4*(3*count))

    def test_known_domain_ties_reject_before_any_realisation(self):
        sig={"abi":"0.9","tier":"q","kind":"action","mut":[1],"in":[],"mem":[],"args":[],"bounds":[]}
        full=target();doc=e.loads(e.jcs(full.doc));doc["gates"]=[g for g in doc["gates"] if g["op"]!="h"];limited=e.Target.read(e.jcs(doc))
        for kind,body,at,payload in [
            ("gate","h q\nx q","entry:1",{"realisation":"native"}),
            ("start","h q\nx q","entry:1",{"time":0}),
            ("alloc","h q\nd = qalloc any 1\nqfree d","entry:1",{"class":"data"}),
            ("cleanup","h q\nd = qcopy q\nquncopy q d","entry:2",{"realisation":"reverse"})]:
            with self.subTest(kind=kind):
                obj=make_object("action @root (q:wire) () () () ()\n^entry():\n"+body,sig)
                bound=e.estimate(obj,full,"root",[],["0"]*4)["effective_schedule"]
                bound["bindings"]["target_hash"]=limited.hash
                selected=entry(kind,path=[point(obj.symbol("root")["interface_hash"],at)],**payload)
                bound["entries"]=[selected,selected];obj.sections["schedule"]=bound
                attempts=[];original=e.Ledger
                class Recording(original):
                    def gate(self,*args,**kw):attempts.append(args[0]);return super().gate(*args,**kw)
                with patch.object(e,"Ledger",Recording):
                    with self.assertRaisesRegex(e.ContractError,"E_SCHEDULE_INFEASIBLE:.*multiple maximal matching"):
                        e.estimate(obj,limited,"root",[],["0"]*4)
                self.assertEqual(attempts,[])

    def test_nested_token_ties_keep_the_concrete_validation_stage(self):
        sig={"abi":"0.9","tier":"q","kind":"action","mut":[1,1,4],"in":[],"mem":[],"args":["token"],"bounds":[]}
        child={"abi":"0.9","tier":"q","kind":"oracle","in":[1],"tgt":1,"fault":4,"mem":[],"args":[]}
        text="action @root (q:wire, t:wire, f:wire[4]) () () (tk:token) ()\n^entry():\nh q\noracle_call @child tk (q) t f () ()\noracle @child (x:wire in) (t:wire) (f:wire[4]) () ()\nregs {  }\n^entry():\nlift.retval x"
        obj=make_program(text,{"root":sig,"child":child});full=target();args=[["3","0","0","0"]]
        bound=e.estimate(obj,full,"root",args,["0"]*4)["effective_schedule"]
        selected=entry(path=[point(obj.symbol("root")["interface_hash"],"entry:1"),point(obj.symbol("child")["interface_hash"])],step=3,phase="fwd",realisation="native")
        bound["entries"]=[selected,selected];obj.sections["schedule"]=bound
        doc=e.loads(e.jcs(full.doc));doc["gates"]=[g for g in doc["gates"] if g["op"]!="h"];limited=e.Target.read(e.jcs(doc))
        bound["bindings"]["target_hash"]=limited.hash
        with self.assertRaisesRegex(e.ContractError,"E_GATE_UNSUPPORTED"):
            e.estimate(obj,limited,"root",args,["0"]*4)
        bound["bindings"]["target_hash"]=full.hash
        with self.assertRaisesRegex(e.ContractError,"multiple maximal matching"):
            e.estimate(obj,full,"root",args,["0"]*4)
        args=[["2","0","0","0"]];bound["bindings"]["params_hash"]=e.digest(e.jcs(args))
        self.assertEqual(e.estimate(obj,full,"root",args,["0"]*4)["label"],"exact")

    def test_admission_checks_nested_actions_and_respects_covering_entries(self):
        sig={"abi":"0.9","tier":"q","kind":"action","mut":[1],"in":[],"mem":[],"args":[],"bounds":[]}
        text="action @root (q:wire) () () () ()\n^entry():\naction_call @child (q) () () ()\naction @child (q:wire) () () () ()\n^entry():\nh q\nx q"
        obj=make_program(text,{"root":sig,"child":sig});full=target()
        bound=e.estimate(obj,full,"root",[],["0"]*4)["effective_schedule"]
        low=entry(realisation="native");path=[point(obj.symbol("root")["interface_hash"]),point(obj.symbol("child")["interface_hash"])]
        first=entry(path=path,realisation="native")
        second=entry(path=[path[0],point(path[1]["symbol"],"entry:1")],realisation="native")
        bound["entries"]=[low,low,first,second];obj.sections["schedule"]=bound
        self.assertEqual(e.estimate(obj,full,"root",[],["0"]*4)["gates"],{"h":"1","x":"1"})
        bound["entries"].pop()
        doc=e.loads(e.jcs(full.doc));doc["gates"]=[g for g in doc["gates"] if g["op"]!="h"];limited=e.Target.read(e.jcs(doc))
        bound["bindings"]["target_hash"]=limited.hash
        with self.assertRaisesRegex(e.ContractError,"multiple maximal matching"):
            e.estimate(obj,limited,"root",[],["0"]*4)

    def test_loop_reallocation_carries_changed_class_to_the_next_visit(self):
        sig={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1],"in":[],"mem":[],"args":[],"bounds":[3]}
        text="perm_action @root (q:wire) () () () ()\nregs {  } bounds { 3 }\n^entry():\nc = qalloc data 1\nqloop 3 {\nx c[0]\nx c[0]\nqfree c\nc = qalloc special 1\n}\nqfree c"
        obj=make_object(text,sig);doc=e.loads(e.jcs(target().doc));doc["classes"]["special"]=dict(doc["classes"]["data"]);t=e.Target.read(e.jcs(doc))
        analytic=e.estimate(obj,t,"root",[],["0"]*4);actual=e.estimate(obj,t,"root",[],["0"]*4,include_frame=True)
        self.assertEqual(actual["exact_resources"],analytic["exact_resources"])
        self.assertEqual(actual["gates"],{"x":"6"})
        self.assertEqual(actual["resources"]["qubit_second[data]"],"8")
        self.assertEqual(actual["resources"]["qubit_second[special]"],"4")
        self.assertEqual([r["class"] for r in actual["frame"]["scratch"]],["data","special","special","special"])
        huge=2**40;large=make_object(text.replace('3',str(huge)),{**sig,"bounds":[huge]})
        summary=e.estimate(large,t,"root",[],["0"]*4)
        self.assertEqual(int(summary["resources"]["qubit_second[data]"]),2*huge+2)
        self.assertEqual(int(summary["resources"]["qubit_second[special]"]),2*huge-2)
        self.assertEqual(summary["resources"]["peak_qubits[data]"],"2")
        self.assertLess(summary["summary_operations"],100)

    def test_zero_visit_loop_keeps_the_entry_binding(self):
        sig={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1],"in":[],"mem":[],"args":[],"bounds":[0]}
        obj=make_object("perm_action @root (q:wire) () () () ()\nregs {  } bounds { 0 }\n^entry():\nc = qalloc data 1\nqloop 0 {\nqfree c\nc = qalloc special 1\n}\nqfree c",sig)
        doc=e.loads(e.jcs(target().doc));doc["classes"]["special"]=dict(doc["classes"]["data"]);t=e.Target.read(e.jcs(doc));actual=e.estimate(obj,t,"root",[],["0"]*4,include_frame=True)
        self.assertEqual([r["width"] for r in actual["frame"]["scratch"]],[1])
        self.assertEqual(actual["resources"]["peak_qubits[data]"],"2")

    def test_changed_class_loop_keeps_iteration_addresses_and_inverse_lifetimes(self):
        sig={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1],"in":[],"mem":[],"args":[],"bounds":[3]}
        text="perm_action @child (q:wire) () () () ()\nregs {  } bounds { 3 }\n^entry():\nc = qalloc data 1\nqloop 3 {\nx c[0]\nx c[0]\nqfree c\nc = qalloc special 1\n}\nqfree c"
        doc=e.loads(e.jcs(target().doc));doc["classes"]["special"]=dict(doc["classes"]["data"]);t=e.Target.read(e.jcs(doc));events=[];original=e.Ledger
        class Recording(original):
            def gate(self,op,wires,controls=(),**kw):
                events.append((kw["chain"][-1]["point"],kw["chain"][-1]["iteration"]))
                return super().gate(op,wires,controls,**kw)
        root="perm_action @root (q:wire) () () () ()\n^entry():\nadj action_call @child (q) () () ()\n"
        obj=make_program(root+text,{"root":{**sig,"bounds":[]},"child":sig})
        analytic=e.estimate(obj,t,"root",[],["0"]*4)
        with patch.object(e,"Ledger",Recording):actual=e.estimate(obj,t,"root",[],["0"]*4,include_frame=True)
        self.assertEqual(actual["exact_resources"],analytic["exact_resources"])
        self.assertEqual(actual["resources"]["qubit_second[data]"],"8")
        self.assertEqual(actual["resources"]["qubit_second[special]"],"4")
        self.assertEqual([r["class"] for r in actual["frame"]["scratch"]],["special","special","special","data"])
        self.assertEqual(events,[(point,[i]) for i in [0,1,2] for point in ["entry:3","entry:2"]])
        events.clear()
        c=e.Catalog((ROOT/"data/ref-0.9.json").read_text(),t);ledger=Recording(t,e.Schedule(schedule()))
        c.ledger=ledger;q=e.Bundle("input",1,"data")
        e.Source(obj,t,c).region("child",[],["0"]*4,{"q":q},raw_inverse=True)
        self.assertEqual(ledger.finish()["qubit_second[data]"],8)
        self.assertEqual([r["class"] for r in ledger.frame()["scratch"]],["special","special","special","data"])
        self.assertEqual(events,[(point,[i]) for i in [2,1,0] for point in ["entry:3","entry:2"]])

    def test_loop_entry_exit_live_names_and_types_must_agree(self):
        sig={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1],"in":[],"mem":[],"args":[],"bounds":[3]}
        for n in [0,3,2**40]:
            for body in ["qfree c\nc = qalloc any 2","qfree c","d = qalloc any 1"]:
                text=f"perm_action @root (q:wire) () () () ()\nregs {{  }} bounds {{ {n} }}\n^entry():\nc = qalloc any 1\nqloop {n} {{\n{body}\n}}\nqfree c"
                obj=make_object(text,{**sig,"bounds":[n]})
                with self.assertRaisesRegex(e.ContractError,"entry/exit live names and types"):
                    e.estimate(obj,target(),"root",[],["0"]*4)

    def test_reallocated_source_name_keeps_each_lifetime_shape_inside_loops(self):
        sig={"abi":"0.9","tier":"q","kind":"action","mut":[2],"in":[],"mem":[],"args":[],"bounds":[2]}
        obj=make_object("action @root (x:wire[2]) () () () ()\nregs {  } bounds { 2 }\n^entry():\nqloop 2 {\nd = qalloc any 1\nx d[0]\nx d[0]\nqfree d\nd = qcopy x\nquncopy x d\n}",sig)
        t=target();analytic=e.estimate(obj,t,"root",[],["0"]*4)
        actual=e.estimate(obj,t,"root",[],["0"]*4,include_frame=True)
        self.assertEqual(actual["exact_resources"],analytic["exact_resources"])
        self.assertEqual(analytic["gates"],{"cx":"8","x":"4"})
        self.assertEqual(analytic["resources"]["qubit_second[data]"],"44")
        self.assertEqual(analytic["resources"]["peak_qubits[data]"],"4")
        self.assertEqual([r["width"] for r in actual["frame"]["scratch"]],[1,2,1,2])

    def test_reallocated_class_and_state_survive_source_adjoint(self):
        sig={"abi":"0.9","tier":"q","kind":"perm_action","mut":[1],"in":[],"mem":[],"args":[],"bounds":[]}
        child="perm_action @child (q:wire) () () () ()\n^entry():\nd = qalloc data 1\nx d[0]\nx d[0]\nqfree d\nd = qborrow special 2\nx d[1]\nx d[1]\nqreturn d"
        doc=e.loads(e.jcs(target().doc));doc["classes"]["special"]={**doc["classes"]["data"],"dirty_rate":3};t=e.Target.read(e.jcs(doc))
        for adjoint in [False,True]:
            obj=make_program("perm_action @root (q:wire) () () () ()\n^entry():\n"+("adj " if adjoint else "")+"action_call @child (q) () () ()\n"+child,{"root":sig,"child":sig})
            analytic=e.estimate(obj,t,"root",[],["0"]*4);actual=e.estimate(obj,t,"root",[],["0"]*4,include_frame=True)
            self.assertEqual(actual["exact_resources"],analytic["exact_resources"])
            self.assertEqual(actual["gates"],{"x":"4"})
            self.assertEqual(actual["resources"]["qubit_second[data]"],"6")
            self.assertEqual(actual["resources"]["qubit_second[special]"],"12")
            self.assertEqual([r["width"] for r in actual["frame"]["scratch"]],[1])
            self.assertEqual([r["width"] for r in actual["frame"]["borrow"]],[2])

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
        fixture=sibling(ROOT, "bennett-isa-spec") / "conformance/fixtures/controlled-action-09"
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
        fixture=sibling(ROOT, "bennett-isa-spec") / "conformance/fixtures/controlled-action-09/certificate.json"
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
        fixture=sibling(ROOT, "bennett-isa-spec") / "conformance/fixtures/controlled-action-09"
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
        fixture=sibling(ROOT, "bennett-isa-spec") / "conformance/fixtures/controlled-action-09"
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
