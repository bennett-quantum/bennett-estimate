import importlib.util
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
import tempfile
from fractions import Fraction as F

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("estimate", ROOT / "src/estimate.py")
e = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = e
spec.loader.exec_module(e)


def object_with_signatures(functions, signatures, layout=None, devices=None, data=None):
    symbols={str(i):{"name":name,"kind":sig["kind"],"signature":sig,"interface_hash":"0"*64} for i,(name,sig) in enumerate(signatures.items())}
    def text():
        value="bennett-object isa=0.9 object=0.9 launch=0.9 sched=0.9 cert=0.9 coverage=0.9 target=0.9 ptr_width=32\n\nsection symbols\n"+e.jcs(symbols)+"\n\nsection functions\n"+functions+"\n"
        if data is not None: value+="\nsection data\n"+"\n".join(n+" "+image for n,image in data.items())+"\n"
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
    def test_numeric_target_fields_are_json_numbers(self):
        original=e.loads((ROOT.parent/"bennett-targets/targets/ideal-all-to-all.json").read_text())
        for location in ["class","capability","rate","expression","table"]:
            doc=e.loads(e.jcs(original))
            if location=="class":doc["classes"]["data"]["dirty_rate"]="1"
            if location=="capability":doc["capabilities"]["classical_step_time"]="1"
            if location=="rate":doc["resources"]["qubit_second"]["rate"]={"data":"1"}
            if location=="expression":doc["gates"][0]["cost"]["time"]="1"
            if location=="table":doc["tables"]["bad"]=["1"]
            with self.assertRaises(e.ContractError,msg=location):e.Target.read(e.jcs(doc))

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
    def global_delivery(self,c,count,Did,mixed=False):
        formal=next(f for f in c.recipes["lift.ret"]["parameters"] if f["name"]=="Globals")
        records=[{"id":i,"width":1+i%3 if mixed else 1,"slot":i,"location":e.Bundle(f"loc:{i}",1+i%3 if mixed else 1,"special" if mixed and i%2 else "data")} for i in range(count)]
        captured=c.bind([formal],[records],{},())[0]["Globals"]
        env={"Did":Did,"destination":e.Bundle("dest",Did,"data"),"delivery":e.Bundle("delivery",3,"data"),"Globals":captured}
        def find(nodes):
            for node in nodes:
                if node.get("visit")=="Globals":return node
                if "body" in node:
                    result=find(node["body"])
                    if result:return result
        return find(c.recipes["lift.ret"]["body"]),env

    def test_global_delivery_summary_matches_literal_mixed_groups_and_inverse(self):
        doc=e.loads(e.jcs(self.t.doc));doc["classes"]["special"]=dict(doc["classes"]["data"])
        next(g for g in doc["gates"] if g["op"]=="x")["controls"]["min"]=1
        doc["schemes"]=[{"name":"x-via-hssh","realises":{"op":"x","controls":{"min":0,"max":0}},"ancillae":{"count":2,"class":"special","state":"clean"},"template":[{"gate":g,"wires":["t"]} for g in ["h","s","s","h"]]}]
        c=e.Catalog((ROOT/"data/ref-0.9.json").read_text(),e.Target.read(e.jcs(doc)))
        node,env=self.global_delivery(c,8,3,True);c.stack.append("lift.ret")
        try:
            for controls in [(),(("outside",0,"data"),)]:
                for inverse in [False,True]:
                    c.closed_form=False;literal=c.body([node],env,controls,inverse)
                    c.closed_form=True;self.assertEqual(c.body([node],env,controls,inverse),literal)
        finally:c.stack.pop()

    def test_global_delivery_groups_are_reused_without_scanning_every_return(self):
        class BoundedWork(e.Catalog):
            def body(self,*args,**kw):
                if self.visits>5000:raise AssertionError("global locations were enumerated at each return")
                return super().body(*args,**kw)
        c=BoundedWork((ROOT/"data/ref-0.9.json").read_text(),self.t)
        node,env=self.global_delivery(c,4096,12);c.stack.append("lift.ret")
        try:
            first=c.body([node],env);visits=c.visits
            for _ in range(50):self.assertEqual(c.body([node],env),first)
            self.assertLess(c.visits-visits,100)
            self.assertGreater(first.time,4096)
        finally:c.stack.pop()

    def test_delivery_profile_cache_preserves_target_control_alias_errors(self):
        node,env=self.global_delivery(self.c,4,2);self.c.stack.append("lift.ret")
        try:
            self.c.body([node],env,(("outside",0,"data"),))
            with self.assertRaises(e.ContractError):self.c.body([node],env,(("delivery",0,"data"),))
            with self.assertRaises(e.ContractError):self.c.body([node],env,(("loc:0",0,"data"),))
        finally:self.c.stack.pop()

    def table_arguments(self,C,T):
        P=L=1;E=2;Fwidth=4
        env={n:e.Bundle(n,width,"data") for n,width in [("p",P),("n",L),("base",C*P),("size",C*P),("live",C),("pinned",C),("atop",T),("t",1),("flag",1),("faulted",1),("code",Fwidth)]}
        prefix=[P,L,E,C,T];wires=["p","n","base","size","live","pinned","atop"]
        return env,{"scan.inrange":prefix+wires+["t"],"scan.free.flag":prefix+wires+["t"],"lift.free":prefix+[Fwidth]+wires+["flag","faulted","code"]}

    def test_linear_table_summaries_match_every_literal_resource(self):
        for C in [0,1,3,4]:
            env,arguments=self.table_arguments(C,max(1,C.bit_length()))
            for name,args in arguments.items():
                for controls in [(),(("outer",0,"data"),)]:
                    self.c.closed_form=False;literal=self.c.recipe(name,args,env,controls)
                    self.c.closed_form=True;self.assertEqual(self.c.recipe(name,args,env,controls),literal,(C,name,controls))

    def test_million_entry_table_scan_uses_bounded_summary_work(self):
        class BoundedWork(e.Catalog):
            def body(self,*args,**kw):
                if self.visits>30000:raise AssertionError("allocation table was enumerated")
                return super().body(*args,**kw)
        env,arguments=self.table_arguments(2**20,21)
        for name,args in arguments.items():
            c=BoundedWork((ROOT/"data/ref-0.9.json").read_text(),self.t)
            p=c.recipe(name,args,env)
            self.assertGreater(p.time,2**20);self.assertLess(c.visits,30000)
            self.assertTrue(all(v==0 for v in p.delta.values()))

    def test_table_summary_preserves_packed_fields_schemes_and_alias_guards(self):
        doc=e.loads(e.jcs(self.t.doc));doc["classes"]["special"]=dict(doc["classes"]["data"])
        next(g for g in doc["gates"] if g["op"]=="x")["controls"]["min"]=1
        next(g for g in doc["gates"] if g["op"]=="cx")["cost"]["time"]={"var":"c"}
        doc["schemes"]=[{"name":"x-via-hssh","realises":{"op":"x","controls":{"min":0,"max":0}},"ancillae":{"count":2,"class":"special","state":"clean"},"template":[{"gate":g,"wires":["t"]} for g in ["h","s","s","h"]]}]
        c=e.Catalog((ROOT/"data/ref-0.9.json").read_text(),e.Target.read(e.jcs(doc)))
        env,arguments=self.table_arguments(3,2)
        for offset,name in enumerate(["base","size","live","pinned"]):env[name]=e.RecordField("table",3,"data",offset,element_width=1,record_width=4)
        for name,args in arguments.items():
            for controls in [(),(("table",3,"data"),)]:
                for inverse in [False,True]:
                    c.closed_form=False;literal=c.recipe(name,args,env,controls,inverse)
                    c.closed_form=True;self.assertEqual(c.recipe(name,args,env,controls,inverse),literal,(name,controls,inverse))

    def test_image_inverse_reverses_bits_with_empty_effective_controls(self):
        events=[];original=e.Catalog
        class Recording(original):
            def gate_event(self,op,wires,controls=(),**kw):
                events.append((wires[0].offset,controls));return super().gate_event(op,wires,controls,**kw)
        c=Recording((ROOT/"data/ref-0.9.json").read_text(),self.t);c.closed_form=False
        env={"I":"81","t":e.Bundle("t",8,"data")};body=[{"image":"I","wires":"t"}]
        c.body(body,env,(("control",0,"data"),));self.assertEqual(events,[(0,()),(7,())])
        events.clear();c.body(body,env,(("control",0,"data"),),True)
        self.assertEqual(events,[(7,()),(0,())])

    def test_image_summary_counts_bytes_and_preserves_class_boundaries(self):
        original=e.Catalog
        class BoundedWork(original):
            events=0
            def gate_event(self,*args,**kw):
                self.events+=1
                if self.events>10:raise AssertionError("image gates were enumerated")
                return super().gate_event(*args,**kw)
        image="ff00a5"*4096;c=BoundedWork((ROOT/"data/ref-0.9.json").read_text(),self.t)
        p=c.body([{"image":"I","wires":"t"}],{"I":image,"t":e.Bundle("image",len(image)*4,"data")})
        self.assertEqual(p.gates,{"x":12*4096});self.assertEqual(p.time,12*4096)
        doc=e.loads(e.jcs(self.t.doc));doc["classes"]["special"]=dict(doc["classes"]["data"])
        doc["gates"].insert(0,{"op":"x","classes":["special"],"controls":{"min":0,"max":0},"epsilon":0,"cost":{"time":3,"gate_count":1}})
        c=e.Catalog((ROOT/"data/ref-0.9.json").read_text(),e.Target.read(e.jcs(doc)))
        env={"I":"aa5c","t":[e.Bundle("a",3,"data"),e.Bundle("b",13,"special")]};body=[{"image":"I","wires":"t"}]
        c.closed_form=False;literal=c.body(body,env)
        c.closed_form=True;self.assertEqual(c.body(body,env),literal);self.assertEqual(literal.time,22)

    def test_literal_summary_counts_set_bits_without_visiting_zero_bits(self):
        original=e.Catalog
        class BoundedWork(original):
            def body(self,*args,**kw):
                if self.visits>100:raise AssertionError("literal bit span was enumerated")
                return super().body(*args,**kw)
        c=BoundedWork((ROOT/"data/ref-0.9.json").read_text(),self.t)
        for value in [0,1,(1<<4095)+1]:
            p=c.recipe("value.literal",[4096,value,"t"],{"t":e.Bundle("t",4096,"data")})
            self.assertEqual(p.counts.get("gate_count",0),value.bit_count())
            self.assertLess(c.visits,10)
        for n,value in [(0,0),(3,1025),(8,255),(8,129)]:
            env={"t":e.Bundle("t",n,"data")}
            self.c.closed_form=False;literal=self.c.recipe("value.literal",[n,value,"t"],env)
            self.c.closed_form=True;self.assertEqual(self.c.recipe("value.literal",[n,value,"t"],env),literal)

    def test_implicit_length_width_changes_exact_cost(self):
        wires={n:e.Bundle(n,width,"data") for n,width in [("address",32),("base",32),("size",32),("live",1),("pinned",1),("atop",1),("flag",1),("faulted",1),("code",4),("value",8),("displaced",8),("cells",8)]}
        layout=[{"base":0,"extent":1,"cells":wires["cells"]}]
        profiles=[]
        for L in [1,32]:
            actuals=[32,L,33,1,1,4,8,1]+[wires[n] for n in ["address","base","size","live","pinned","atop","flag","faulted","code","value","displaced"]]+[layout]
            profiles.append(self.c.recipe("lift.load",actuals))
        self.assertGreater(profiles[1].peak[("data","total")],profiles[0].peak[("data","total")])
        self.assertGreater(profiles[1].area[("data","clean")],profiles[0].area[("data","clean")])

    def setUp(self):
        self.t = e.Target.read((ROOT.parent / "bennett-targets/targets/ideal-all-to-all.json").read_text())
        self.c = e.Catalog((ROOT / "data/ref-0.9.json").read_text(), self.t)

    def test_published_identity(self):
        self.assertEqual(self.c.hash, "5de4e4995350313e50217880ba1b95de39cd043283b726337d4894efb005d197")
        self.assertEqual(len(self.c.recipes), 219)

    def test_k82_named_interfaces_do_not_leak_typed_caller_names(self):
        self.c.recipes["closed-test"]={"parameters":[{"name":"N","type":"integer"}],"body":[{"gate":"x","wires":["q[0]"]}]}
        with self.assertRaises(e.ContractError):self.c.recipe("closed-test",[1],{"q":e.Bundle("q",1,"data")})
        self.c.recipes["named-test"]={"parameters":[],"body":[{"gate":"x","wires":["q[0]"]}]}
        self.assertEqual(self.c.recipe("named-test",[],{"q":e.Bundle("q",1,"data")}).time,1)
        with self.assertRaises(e.ContractError):self.c.recipe("named-test",[],{"q":e.Bundle("q",1,"data"),"extra":e.Bundle("extra",1,"data")})

    def test_qxor_and_ripple(self):
        wires = {n: e.Bundle(n, 2, "data") for n in ["a", "b", "t", "s"]}
        with self.assertRaisesRegex(e.ContractError,"K82"):
            self.c.recipe("qxor", [2], wires)
        p = self.c.recipe("qxor", [2], {n:wires[n] for n in ["s","t"]})
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

    def test_stack_summary_preserves_stride_padding_and_controls(self):
        for S,C,K,N in [(0,1,4,2),(2,3,5,2),(3,5,4,0)]:
            env={n:e.Bundle(n,width,"data") for n,width in [("address",S),("stack",C*K),("v",N)]}
            for name in ["stack.copy","stack.store","stack.exchange"]:
                for controls in [(),(("external",0,"data"),)]:
                    self.c.closed_form=False
                    literal=self.c.recipe(name,[S,C,K,N,"address","stack","v"],env,controls)
                    self.c.closed_form=True
                    self.assertEqual(self.c.recipe(name,[S,C,K,N,"address","stack","v"],env,controls),literal,(S,C,K,N,name,controls))

    def test_large_stack_summary_does_not_scan_cells(self):
        class BoundedWork(e.Catalog):
            def body(self,*args,**kw):
                if self.visits>1000:raise AssertionError("stack cells were enumerated")
                return super().body(*args,**kw)
        c=BoundedWork((ROOT/"data/ref-0.9.json").read_text(),self.t)
        S,C,K,N=21,2**20,64,32
        env={n:e.Bundle(n,width,"data") for n,width in [("address",S),("stack",C*K),("v",N)]}
        for name in ["stack.copy","stack.store","stack.exchange"]:
            c.visits=0;p=c.recipe(name,[S,C,K,N,"address","stack","v"],env)
            self.assertGreater(p.time,C*N);self.assertLess(c.visits,500)
            self.assertTrue(all(v==0 for v in p.delta.values()))

    def test_address_popcounts_skip_unused_high_address_bits(self):
        def bounded_range(*args):
            result=range(*args)
            if len(result)>1000:raise AssertionError("unused address bits were enumerated")
            return result
        for width in [100000,2**40]:
            env={n:e.Bundle(n,size,"data") for n,size in [("address",width),("stack",2),("v",1)]}
            with patch.object(e,"range",bounded_range,create=True):
                p=self.c.recipe("stack.copy",[width,2,1,1,"address","stack","v"],env)
            self.assertGreater(p.time,width)

    def test_dispatch_literal_schemes_preserve_workspace_area(self):
        doc=e.loads(e.jcs(self.t.doc))
        doc["classes"]["special"]=dict(doc["classes"]["data"])
        next(g for g in doc["gates"] if g["op"]=="x")["controls"]["min"]=1
        doc["schemes"]=[{"name":"x-via-hssh","realises":{"op":"x","controls":{"min":0,"max":0}},"ancillae":{"count":2,"class":"special","state":"clean"},"template":[{"gate":g,"wires":["t"]} for g in ["h","s","s","h"]]}]
        c=e.Catalog((ROOT/"data/ref-0.9.json").read_text(),e.Target.read(e.jcs(doc)))
        env={"a":e.Bundle("a",2,"data"),"cells":e.Bundle("cells",6,"data"),"v":e.Bundle("v",2,"data")}
        c.closed_form=False;literal=c.recipe("dispatch.copy",[2,3,2,"a","cells","v"],env)
        c.closed_form=True;self.assertEqual(c.recipe("dispatch.copy",[2,3,2,"a","cells","v"],env),literal)

    def test_dispatch_control_aliases_require_literal_fallback(self):
        doc=e.loads(e.jcs(self.t.doc))
        next(g for g in doc["gates"] if g["op"]=="cx")["cost"]["time"]={"var":"c"}
        c=e.Catalog((ROOT/"data/ref-0.9.json").read_text(),e.Target.read(e.jcs(doc)))
        env={"a":e.Bundle("a",2,"data"),"cells":e.Bundle("cells",6,"data"),"v":e.Bundle("v",2,"data")}
        controls=(("cells",2,"data"),)
        c.closed_form=False;literal=c.recipe("dispatch.copy",[2,3,2,"a","cells","v"],env,controls)
        c.closed_form=True;self.assertEqual(c.recipe("dispatch.copy",[2,3,2,"a","cells","v"],env,controls),literal)


class Objects(unittest.TestCase):
    def test_lifted_free_million_entry_source_object_uses_table_summaries(self):
        obj=e.Object.read((ROOT/"examples/lifted-free-2pow20.bisa").read_text())
        t=e.Target.read((ROOT.parent/"bennett-targets/targets/ideal-all-to-all.json").read_text())
        original=e.Catalog
        class BoundedWork(original):
            def body(self,*args,**kw):
                if self.visits>200000:raise AssertionError("source allocation table was enumerated")
                return super().body(*args,**kw)
        with patch.object(e,"Catalog",BoundedWork):result=e.estimate(obj,t,"root",[],["1","0","0","0"])
        self.assertEqual(result["label"],"exact")
        self.assertEqual(result["padded_steps"],{"forward":"1","inverse":"1"})
        self.assertGreater(int(result["resources"]["peak_qubits[data]"]),2**20*66)
        self.assertGreater(int(result["resources"]["gate_count"]),2**20)
        self.assertLess(result["summary_operations"],200000)

    def test_literal_allocator_length_uses_the_existing_length_binding_gap(self):
        obj=e.Object.read((ROOT/"tests/fixtures/literal-alloc-source-gap.bisa").read_text())
        t=e.Target.read((ROOT.parent/"bennett-targets/targets/ideal-all-to-all.json").read_text())
        with self.assertRaisesRegex(e.ContractError,"EST-SOURCE-02"):
            e.estimate(obj,t,"root",[],["2","1","0","0"])

    def test_wide_zero_and_signed_words_keep_constant_summary_work(self):
        n=2**53+1
        sig={"abi":"0.9","tier":"q","kind":"oracle","in":[1],"tgt":1,"fault":4,"mem":[],"args":[]}
        t=e.Target.read((ROOT.parent/"bennett-targets/targets/ideal-all-to-all.json").read_text());original=e.Catalog
        class BoundedWork(original):
            def body(self,*args,**kw):
                if self.visits>500:raise AssertionError("wide constant was enumerated")
                return super().body(*args,**kw)
        results=[]
        for value in [0,-1]:
            obj=object_with_signatures(f"oracle @root (x:wire in) (t:wire) (f:wire[4]) () ()\nregs {{ w:reg[{n}] }}\n^entry():\nw = lift.const.i{n} {value}\nlift.retval x",{"root":sig})
            with patch.object(e,"Catalog",BoundedWork):result=e.estimate(obj,t,"root",[],["1","0","0","0"])
            self.assertLess(result["summary_operations"],500)
            self.assertEqual(int(result["gates"]["swap"]),2*n+8)
            results.append(result)
        self.assertEqual(int(results[1]["gates"]["x"])-int(results[0]["gates"]["x"]),2*n)

    def test_signed_lifted_literals_match_unsigned_encoding(self):
        sig={"abi":"0.9","tier":"q","kind":"oracle","in":[],"tgt":8,"fault":4,"mem":[],"args":[]}
        def obj(value):return object_with_signatures(f"oracle @root () (t:wire[8]) (f:wire[4]) () ()\nregs {{ w:reg[8] }}\n^entry():\nw = lift.const.i8 {value}\nlift.retval w",{"root":sig})
        t=e.Target.read((ROOT.parent/"bennett-targets/targets/ideal-all-to-all.json").read_text());budget=["1","0","0","0"]
        for signed,unsigned in [(-1,255),(-128,128),(-3,253)]:
            first=e.estimate(obj(signed),t,"root",[],budget);second=e.estimate(obj(unsigned),t,"root",[],budget)
            self.assertEqual(first["exact_resources"],second["exact_resources"])
            self.assertEqual(first["gates"],second["gates"])
            if signed==-1:self.assertEqual(e.estimate(obj(signed),t,"root",[],budget,include_frame=True)["exact_resources"],first["exact_resources"])
        for invalid in [-129,256]:
            with self.assertRaisesRegex(e.ContractError,"literal"):
                e.estimate(obj(invalid),t,"root",[],budget)

    def test_distinct_legal_jump_widths_expose_ref_binding_gap(self):
        obj=e.Object.read((ROOT/"tests/fixtures/jump-width-source-gap.bisa").read_text())
        t=e.Target.read((ROOT.parent/"bennett-targets/targets/ideal-all-to-all.json").read_text())
        with self.assertRaisesRegex(e.ContractError,"EST-SOURCE-04"):
            e.estimate(obj,t,"root",[],["3","0","0","0"])
        self.assertEqual(e.estimate(obj,t,"root",[],["0"]*4)["label"],"exact")

    def test_wide_unwritten_location_exposes_ret_delivery_contract_gap(self):
        obj=e.Object.read((ROOT/"tests/fixtures/ret-delivery-source-gap.bisa").read_text())
        t=e.Target.read((ROOT.parent/"bennett-targets/targets/ideal-all-to-all.json").read_text())
        with self.assertRaisesRegex(e.ContractError,"EST-SOURCE-03"):
            e.estimate(obj,t,"root",[],["4","1","8","1"])
        self.assertEqual(e.estimate(obj,t,"root",[],["0","1","8","1"])["label"],"exact")

    def test_location_and_interface_roles_are_not_width_only(self):
        oracle=(ROOT/"tests/fixtures/example1.bisa").read_text()
        action=(ROOT/"tests/fixtures/example3.bisa").read_text()
        for text in [oracle.replace("one:reg[8]","one:ptr"),oracle.replace("x:wire[8] in","x:i8"),oracle.replace("x:wire[8] in","x:wire[8] mut"),action.replace("regs {  }","regs { ghost:wire }"),action.replace('"tier":"q"','"tier":"r"')]:
            with self.assertRaises(e.ContractError):e.Object.read(text)

    def test_instruction_tiers_and_terminators_are_checked_at_admission(self):
        oracle=(ROOT/"tests/fixtures/example1.bisa").read_text()
        action=(ROOT/"tests/fixtures/example3.bisa").read_text()
        for text in [oracle.replace("one = lift.const.i8 1","one = budget.mint @inc8 one one one one"),oracle.replace("lift.retval r","lift.ret r"),oracle.replace("lift.retval r","r = lift.add x one"),action.replace("cx x b[0]","br ^entry()",1)]:
            with self.assertRaises(e.ContractError):e.Object.read(text)

    def test_r_to_cc_call_edge_rejected(self):
        sig=lambda kind:{"abi":"0.9","tier":kind,"kind":kind,"params":[],"results":[]}
        symbols={str(i):{"name":name,"kind":kind,"signature":sig(kind),"interface_hash":"0"*64} for i,(name,kind) in enumerate([("root","r"),("child","cc")])}
        header=(ROOT/"tests/fixtures/example1.bisa").read_text().split("\n\nsection symbols",1)[0]
        text=header+"\n\nsection symbols\n"+e.jcs(symbols)+"\n\nsection functions\nfn r @root () () () () ()\n^entry():\ncall @child\nret\nfn cc @child () () () () ()\n^entry():\nret\n"
        with self.assertRaisesRegex(e.ContractError,"tier"):
            e.Object.read(text)

    def test_rung3_nested_uncall_and_impure_fault_prefix(self):
        obj=e.Object.read((ROOT.parent/"bennett-conformance/ladder/rung-3/fixtures/executor-control.bisa").read_text())
        target=e.Target.read((ROOT/"data/classical-step-16.json").read_text())
        for name,steps,reverse in [("nested",11,5),("impure",8,0)]:
            result=e.estimate(obj,target,name,[],["0"]*4)
            self.assertEqual(result["classical_steps"],str(steps))
            self.assertEqual(result["reversed_classical_steps"],str(reverse))
            self.assertEqual(result["resources"]["time"],str(steps+reverse))

    def test_unused_resolved_parameters_preserve_binding_without_extra_wires(self):
        sig={"abi":"0.9","tier":"q","kind":"oracle","in":[1],"tgt":1,"fault":4,"mem":[],"args":["i128","f64","token"]}
        obj=object_with_signatures("oracle @unused (x:wire in) (t:wire) (f:wire[4]) () (a:i128, b:f64, tk:token)\nregs {  }\n^entry():\nlift.retval x",{"unused":sig})
        target=e.Target.read((ROOT.parent/"bennett-targets/targets/ideal-all-to-all.json").read_text())
        a=["0","0x0000000000000000",["2","0","0","0"]]
        b=[str(1<<100),"0x8000000000000000",["3","0","0","0"]]
        first=e.estimate(obj,target,"unused",a,["1","0","0","0"])
        second=e.estimate(obj,target,"unused",b,["1","0","0","0"])
        self.assertEqual(first["resources"],second["resources"])
        self.assertEqual(second["invocation"]["args"],b)
        self.assertNotEqual(first["params_hash"],second["params_hash"])

    def test_published_source_binding_gaps_have_concrete_witnesses(self):
        target=e.Target.read((ROOT.parent/"bennett-targets/targets/ideal-all-to-all.json").read_text())
        parameter=e.Object.read((ROOT/"tests/fixtures/parameter-source-gap.bisa").read_text())
        self.assertEqual(parameter.symbol("parameter")["signature"]["args"],["i1"])
        for value in ["0","1"]:
            self.assertEqual(e.resolved_arguments(["i1"],[value],parameter),[int(value)])
            with self.assertRaisesRegex(e.ContractError,"EST-SOURCE-01"):
                e.estimate(parameter,target,"parameter",[value],["2","0","0","0"])
        catalog=e.Catalog((ROOT/"data/ref-0.9.json").read_text(),target)
        with self.assertRaises(e.ContractError):
            catalog.bind([{"name":"b","type":"wire","width":1}],["a"],{"a":1},())
        memory=e.Object.read((ROOT/"tests/fixtures/implicit-length-source-gap.bisa").read_text())
        with self.assertRaisesRegex(e.ContractError,"EST-SOURCE-02"):
            e.estimate(memory,target,"read_byte",[],["3","0","0","0"])

    def test_layout_construction_order_and_image_occupancy(self):
        fn="oracle @address () (t:wire[32]) (f:wire[4]) () ()\nregs { p:reg[32] }\n^entry():\np = lift.addr @g\nlift.retval p"
        sig={"abi":"0.9","tier":"q","kind":"oracle","in":[],"tgt":32,"fault":4,"mem":[],"args":[]}
        data_sig={"abi":"0.9","tier":"-","kind":"data","size":1}
        layout={"ptr_width":32,"H":3,"A_tab":1,"S_cells":0,"null_size":1,"heap_base":2,"heap_limit_max":6,"globals":{"g":{"base":1,"size":1,"image":"g"}},"interface_regions":{}}
        target=e.Target.read((ROOT.parent/"bennett-targets/targets/ideal-all-to-all.json").read_text())
        results=[]
        for image in ["00","80"]:
            obj=object_with_signatures(fn,{"address":sig,"g":data_sig},layout,data={"g":image})
            catalog=e.Catalog((ROOT/"data/ref-0.9.json").read_text(),target)
            source=e.Source(obj,target,catalog)
            source.region("address",[],["2","0","0","0"])
            state=source.last_state
            self.assertEqual([r["name"] for r in state],["pc","pc_prime","faulted","code","result_val","heap_used","atop","sp","fp","depth","mem","stack","p","alloctab","frames"])
            widths={r["name"]:r["storage"].width for r in state}
            self.assertEqual({n:widths[n] for n in ["heap_used","atop","sp","fp","depth","mem","stack","alloctab","frames"]},{"heap_used":5,"atop":2,"sp":1,"fp":1,"depth":1,"mem":64,"stack":32,"alloctab":132,"frames":74})
            results.append(e.estimate(obj,target,"address",[],["2","0","0","0"]))
        self.assertEqual(int(results[1]["resources"]["gate_count"])-int(results[0]["resources"]["gate_count"]),2)
        self.assertEqual(int(results[1]["resources"]["qubit_second[data]"])-int(results[0]["resources"]["qubit_second[data]"]),302)

    def test_controlled_action_call_and_matching_schedule(self):
        path=ROOT.parent/"bennett-isa-spec/conformance/fixtures/controlled-action-09"
        obj=e.Object.read((path/"controlled.bisa").read_text())
        target=e.Target.read((path/"target.json").read_text())
        scheduled=e.estimate(obj,target,"controlled",[],["0"]*4)
        self.assertEqual(scheduled["resources"],{"peak_qubits[fast]":"2","qubit_second[fast]":"2","time":"1"})
        original=obj.sections["schedule"]["entries"][0]["gate"]["realisation"]
        obj.sections["schedule"]["entries"][0]["gate"]["realisation"]="missing-scheme"
        with self.assertRaisesRegex(e.ContractError,"selected realisation"):
            e.estimate(obj,target,"controlled",[],["0"]*4)
        obj.sections["schedule"]["entries"][0]["gate"]["realisation"]=original
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
    def certificate_document(self):
        return e.loads((ROOT.parent/"bennett-isa-spec/conformance/fixtures/controlled-action-09/certificate.json").read_text())

    def test_nested_certificate_types_and_claim_bindings_reject(self):
        def bad_index(doc,region):region["verification"]["unitary"]=[True]
        def bad_subject(doc,region):region["claims"][0]["subject"]["closure_hash"]="wrong"
        def negative_controls(doc,region):region["claims"][0]["subject"]["inherited_controls"]=-1
        def bad_budget(doc,region):region["claims"][0]["invocation"]={"args":[],"budget":["0"]*3}
        def bad_arg(doc,region):doc["bindings"]["invocation"]["args"]=["-1"]
        def missing_invocation(doc,region):region["claims"][0]["subject"].pop("schedule_hash")
        def invalid_table(doc,region):region["claims"][0]["expected"]["table"][0]["before"]["bundles"]=["01"]
        def duplicate_domain(doc,region):region["claims"][0]["domain"]["bundles"]*=2
        def too_wide_range(doc,region):region["claims"][0]["domain"]["bundles"][0]["hi"]=2
        def negative_error(doc,region):region["error"]["forward:0"]["local"]["operator_norm"]="-0.1"
        def fractional_error(doc,region):region["error"]["forward:0"]["local"]["operator_norm"]="1/3"
        def unknown_metric(doc,region):region["error"]["forward:0"]["inclusive"]["other"]=0
        def negative_total(doc,region):doc["composition"]["epsilon_total"]["diamond"]=-1
        def bad_composition_key(doc,region):doc["composition"]["multiplicities"]={"wrong":1}
        def unknown_cleanup(doc,region):region["cleanup"]["forward:0"]=[{"path":[],"realisation":"measurement"}]
        def wrong_precision(doc,region):region["claims"][1]["precision_bits"]=True
        for change in [bad_index,bad_subject,negative_controls,bad_budget,bad_arg,missing_invocation,invalid_table,duplicate_domain,too_wide_range,negative_error,fractional_error,unknown_metric,negative_total,bad_composition_key,unknown_cleanup,wrong_precision]:
            with self.subTest(change=change.__name__):
                doc=self.certificate_document();region=doc["regions"][doc["bindings"]["closure_hash"]];change(doc,region)
                with self.assertRaises(e.ContractError):e.Certificate.read(e.jcs(doc))

    def test_sampled_proof_request_is_parsed_without_a_verdict(self):
        doc=self.certificate_document();region=doc["regions"][doc["bindings"]["closure_hash"]]
        claim=region["claims"][0];claim.update(kind="sampled",sampler={"algorithm":"xoshiro256**","seed":["1","0","0","0"],"count":"18446744073709551616"})
        read=e.Certificate.read(e.jcs(doc));self.assertEqual(read.doc["regions"][doc["bindings"]["closure_hash"]]["claims"][0]["label"],"proof")
        for seed,count in [(["18446744073709551616","0","0","0"],1),(["1","0","0","0"],True)]:
            claim["sampler"].update(seed=seed,count=count)
            with self.assertRaises(e.ContractError):e.Certificate.read(e.jcs(doc))

    def test_reference_and_uniform_structural_invocations_remain_distinct(self):
        doc=self.certificate_document();region=doc["regions"][doc["bindings"]["closure_hash"]];claim=region["claims"][0]
        claim["subject"].pop("schedule_hash");claim["invocation"]={"args":[],"budget":["0"]*4}
        e.Certificate.read(e.jcs(doc))
        region["claims"].append({"kind":"structural","rule":"adjoint_table","subclaims":[],"witness":{},"invocation":{"args":"all","budget":"all"}})
        e.Certificate.read(e.jcs(doc))
        region["claims"][-1]["invocation"]["budget"]=["0"]*4
        with self.assertRaises(e.ContractError):e.Certificate.read(e.jcs(doc))

    def test_certificate_domains_keep_positional_labels_and_unbounded_widths(self):
        doc=self.certificate_document();region=doc["regions"][doc["bindings"]["closure_hash"]];claim=region["claims"][0]
        component={"name":"t","width":1,"lo":0,"hi":1}
        claim["subject"]["inherited_controls"]=2
        claim["domain"]["bundles"]=[dict(component),dict(component),dict(component)]
        claim["domain"]["borrowed"]=[dict(component),dict(component)]
        e.Certificate.read(e.jcs(doc))
        claim["domain"]["bundles"][2]["width"]="9007199254740993"
        e.Certificate.read(e.jcs(doc))
        claim["domain"]["bundles"].append(dict(component))
        with self.assertRaises(e.ContractError):e.Certificate.read(e.jcs(doc))

    def test_certificate_claim_payloads_are_typed_without_replay(self):
        changes=[lambda c:c.update(metric="diamond"),lambda c:c.update(precision_bits=0),lambda c:c.update(bound="1/3"),lambda c:c.update(subject={**c["subject"],"variant":""})]
        for change in changes:
            doc=self.certificate_document();region=doc["regions"][doc["bindings"]["closure_hash"]];change(region["claims"][1])
            with self.assertRaises(e.ContractError):e.Certificate.read(e.jcs(doc))
        doc=self.certificate_document();region=doc["regions"][doc["bindings"]["closure_hash"]];claim=region["claims"][1]
        claim.update(kind="channel",metric="diamond",dual=[{"Y":[["1","1","0","0"]],"mu":"1"}],bound="1")
        e.Certificate.read(e.jcs(doc))
        claim["dual"][0]["Y"][0]=["2","1","0","0"]
        with self.assertRaises(e.ContractError):e.Certificate.read(e.jcs(doc))
        for controls,width in [(3,1),(1,2)]:
            doc=self.certificate_document();claim=doc["regions"][doc["bindings"]["closure_hash"]]["claims"][0]
            claim["subject"]["inherited_controls"]=controls;claim["domain"]["bundles"][0]["width"]=width
            with self.assertRaises(e.ContractError):e.Certificate.read(e.jcs(doc))

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
    def test_vm_and_reader_admit_published_dynamic_register_width_form(self):
        vm=Path(os.environ.get("BENNETT_VM_BIN",ROOT.parent/"bennett-vm/target/debug/bennett-vm"))
        path=ROOT/"tests/fixtures/dynamic-qreg-width.bisa"
        admitted=json.loads(subprocess.run([str(vm),"check",str(path)],capture_output=True,text=True,timeout=30,check=True).stdout)
        self.assertEqual(admitted["object_hash"],e.Object.read(path.read_text()).hash)
        self.assertEqual(admitted["status"],"ok")

    def test_vm_admits_large_table_fixture_and_reports_the_padded_boundary(self):
        vm=Path(os.environ.get("BENNETT_VM_BIN",ROOT.parent/"bennett-vm/target/debug/bennett-vm"))
        path=ROOT/"examples/lifted-free-2pow20.bisa";obj=e.Object.read(path.read_text())
        checked=json.loads(subprocess.run([str(vm),"check",str(path)],capture_output=True,text=True,timeout=30,check=True).stdout)
        self.assertEqual(checked["object_hash"],obj.hash)
        actual=json.loads(subprocess.run([str(vm),"run-oracle",str(path),"root","--input","0,1","--budget","1,0,0,0"],capture_output=True,text=True,timeout=30,check=True).stdout)
        self.assertEqual(actual,{"payload":0,"code":7,"steps":1})
        target=e.Target.read((ROOT.parent/"bennett-targets/targets/ideal-all-to-all.json").read_text())
        predicted=e.estimate(obj,target,"root",[],["1","0","0","0"])
        self.assertEqual(int(predicted["padded_steps"]["forward"]),actual["steps"])

    def test_vm_admits_lifted_call_and_source_step_boundary(self):
        vm=Path(os.environ.get("BENNETT_VM_BIN",ROOT.parent/"bennett-vm/target/debug/bennett-vm"))
        path=ROOT/"examples/lifted-call.bisa";obj=e.Object.read(path.read_text())
        checked=json.loads(subprocess.run([str(vm),"check",str(path)],capture_output=True,text=True,timeout=30,check=True).stdout)
        self.assertEqual(checked["object_hash"],obj.hash)
        self.assertEqual(checked["symbols"]["root"]["closure_hash"],obj.identities(closure=True)["root"])
        t=e.Target.read((ROOT.parent/"bennett-targets/targets/ideal-all-to-all.json").read_text())
        for budget in [3,4,5]:
            actual=json.loads(subprocess.run([str(vm),"run-oracle",str(path),"root","--input","1","--budget",f"{budget},1,8,1"],capture_output=True,text=True,timeout=30,check=True).stdout)
            predicted=e.estimate(obj,t,"root",[],[str(budget),"1","8","1"])
            self.assertEqual(predicted["padded_steps"],{"forward":str(budget),"inverse":str(budget)})
            self.assertLessEqual(actual["steps"],int(predicted["padded_steps"]["forward"]))
            if budget==4:self.assertEqual(actual["steps"],int(predicted["padded_steps"]["forward"]))
            self.assertEqual((actual["payload"],actual["code"]),(0,1) if budget==3 else (1,0))

    def test_contract_dependent_outputs_are_pending_evidence(self):
        binary=os.environ["BENNETT_ESTIMATE_BIN"]
        target=str(ROOT.parent/"bennett-targets/targets/ideal-all-to-all.json")
        cases=[("parameter-source-gap.bisa","parameter",'["0"]',"EST-SOURCE-01"),("implicit-length-source-gap.bisa","read_byte","[]","EST-SOURCE-02"),("token-alias-source-gap.bisa","root",'[["1","0","0","0"],["1","0","0","0"]]',"EST-CONTEXT-03"),("ret-delivery-source-gap.bisa","root","[]","EST-SOURCE-03"),("jump-width-source-gap.bisa","root","[]","EST-SOURCE-04"),("literal-alloc-source-gap.bisa","root","[]","EST-SOURCE-02")]
        for file,region,args,code in cases:
            command=[binary,str(ROOT/"tests/fixtures"/file),"--target",target,"--region",region,"--params",args,"--budget","2,0,0,0"]
            actual=subprocess.run(command,capture_output=True,text=True,timeout=30)
            self.assertEqual(actual.returncode,3,actual.stderr)
            result=json.loads(actual.stdout)
            self.assertEqual(result["label"],"pending evidence")
            self.assertEqual(result["pending"][0]["code"],code)
            self.assertNotIn("resources",result)
            self.assertNotIn("exact_resources",result)
            self.assertIn(code,actual.stderr)
            repeated=subprocess.run(command,capture_output=True,text=True,timeout=30)
            self.assertEqual(repeated.stdout,actual.stdout)

    def test_k12_certificate_write_and_independent_recheck(self):
        fixture=ROOT.parent/"bennett-isa-spec/conformance/fixtures/controlled-action-09"
        binary=os.environ["BENNETT_ESTIMATE_BIN"]
        with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as directory:
            output=Path(directory)/"estimate.cert.json"
            command=[binary,str(fixture/"controlled.bisa"),"--target",str(fixture/"target.json"),"--region","controlled"]
            made=subprocess.run(command+["--certificate-template",str(fixture/"certificate.json"),"--write-certificate",str(output)],capture_output=True,text=True,timeout=30,check=True)
            result=json.loads(made.stdout)
            self.assertIn("correctness_claims_not_checked",result["certificate_status"])
            certificate=e.Certificate.read(output.read_text())
            self.assertEqual(certificate.doc["regions"][result["closure_hash"]]["estimate"]["exact_resources"],result["exact_resources"])
            rebuilt=subprocess.run(command+["--certificate",str(output)],capture_output=True,text=True,timeout=30,check=True)
            self.assertIn("frame_verified",json.loads(rebuilt.stdout)["certificate_status"])
            first=output.read_bytes()
            subprocess.run(command+["--certificate-template",str(fixture/"certificate.json"),"--write-certificate",str(output)],capture_output=True,text=True,timeout=30,check=True)
            self.assertEqual(first,output.read_bytes())

    def test_vm_admits_and_runs_lifted_allocator_witness(self):
        vm=Path(os.environ.get("BENNETT_VM_BIN",ROOT.parent/"bennett-vm/target/debug/bennett-vm"))
        path=ROOT/"examples/lift-allocator.bisa"
        checked=json.loads(subprocess.run([str(vm),"check",str(path)],capture_output=True,text=True,timeout=30,check=True).stdout)
        self.assertEqual(checked["object_hash"],e.Object.read(path.read_text()).hash)
        actual=json.loads(subprocess.run([str(vm),"run-oracle",str(path),"root","--input","","--budget","3,1,0,0"],capture_output=True,text=True,timeout=30,check=True).stdout)
        self.assertEqual(actual,{"payload":1,"code":0,"steps":3})

    def test_vm_admits_contract_witnesses_and_runs_reference_payload(self):
        vm=Path(os.environ.get("BENNETT_VM_BIN",ROOT.parent/"bennett-vm/target/debug/bennett-vm"))
        for name in ["parameter-source-gap.bisa","implicit-length-source-gap.bisa"]:
            path=ROOT/"tests/fixtures"/name
            result=subprocess.run([str(vm),"check",str(path)],capture_output=True,text=True,timeout=30,check=True)
            checked=json.loads(result.stdout)
            self.assertEqual(checked["status"],"ok")
            self.assertEqual(checked["object_hash"],e.Object.read(path.read_text()).hash)
        path=ROOT/"tests/fixtures/parameter-source-gap.bisa"
        for arg in [0,1]:
            for x in [0,1]:
                result=subprocess.run([str(vm),"run-oracle",str(path),"parameter","--input",str(x),"--arg",str(arg),"--budget","2,0,0,0"],capture_output=True,text=True,timeout=30,check=True)
                self.assertEqual(json.loads(result.stdout),{"code":0,"payload":(x+arg)%2,"steps":2})

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
        self.assertEqual([(r["region"],r["status"],r["steps"]) for r in report["rung3"]["fault_rows"]],[("divzero","FAILED",3),("memfault","FAILED",3),("unknown_effect","FAILED",3)])
        self.assertEqual([(r["region"],r["status"],r["steps"]) for r in report["rung3"]["history_rows"]],[("nested","COMPLETED",11),("impure","FAILED",8)])
        native=report["native_action"]
        self.assertEqual((native["vm_native_gate_count"],native["estimate_native_gate_count"]),("8","8"))
        self.assertEqual((native["vm_program_time"],native["vm_classical_steps"],native["vm_nonclassical_time"],native["estimate_action_time"]),("25",7,"18","18"))
        self.assertEqual((native["estimate_action_occupancy"],native["vm_program_occupancy"],native["space_relation"]),("72","84","action <= program"))
        self.assertEqual([(r["status"],r["steps"],r["resources"]["time"],r["resources"]["qubit_second[data]"]) for r in report["native_programs"]],[("COMPLETED",7,"25","84"),("COMPLETED",7,"9","20"),("FAILED",5,"5","6"),("COMPLETED",12,"12","0"),("COMPLETED",11,"15","26"),("COMPLETED",6,"12","8"),("COMPLETED",11,"16","0")])
        self.assertEqual([r["reversed_classical_steps"] for r in report["native_programs"]],["0","0","0","0","0","4","5"])
        self.assertIn(report["rung2"]["status"],["unavailable","objects_available"])


if __name__ == "__main__":
    unittest.main()
