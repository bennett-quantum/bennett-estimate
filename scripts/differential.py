"""Run published VM binary as a differential oracle; never import its code."""
import json
import os
from pathlib import Path
import subprocess
from decimal import Decimal
from fractions import Fraction


def run(root, estimator):
    workspace=root.parent
    vm=Path(os.environ.get("BENNETT_VM_BIN",workspace/"bennett-vm/target/debug/bennett-vm"))
    if not vm.is_file(): raise RuntimeError(f"required differential VM binary missing: {vm}")
    fixture=workspace/"bennett-conformance/ladder/rung-3/fixtures/executor-control.bisa"
    rows=[]
    for n in [0,1,3,7,255]:
        vm_result=subprocess.run([str(vm),"run-cc",str(fixture),"sum","--args",str(n)],capture_output=True,text=True,timeout=30,check=True)
        actual=json.loads(vm_result.stdout)
        estimate=subprocess.run([str(estimator),str(fixture),"--target",str(root/"data/classical-step-16.json"),"--region","sum","--params",json.dumps([str(n)])],capture_output=True,text=True,timeout=30,check=True)
        predicted=json.loads(estimate.stdout)
        if actual["status"]!="COMPLETED" or predicted["label"]!="exact" or int(predicted["classical_steps"])!=actual["steps"] or predicted["resources"]["time"]!=str(actual["steps"]):
            raise AssertionError(f"rung-3 step/time differential mismatch at n={n}")
        rows.append({"n":n,"steps":actual["steps"],"estimate_time":predicted["resources"]["time"],"match":True})
    faults=[];history=[]
    for name in ["divzero","memfault","unknown_effect","nested","impure"]:
        actual=json.loads(subprocess.run([str(vm),"run-cc",str(fixture),name],capture_output=True,text=True,timeout=30,check=True).stdout)
        predicted=json.loads(subprocess.run([str(estimator),str(fixture),"--target",str(root/"data/classical-step-16.json"),"--region",name],capture_output=True,text=True,timeout=30,check=True).stdout)
        if actual["status"]!=("COMPLETED" if name=="nested" else "FAILED") or predicted["label"]!="exact" or int(predicted["classical_steps"])!=actual["steps"] or predicted["resources"]["time"]!=str(actual["steps"]):
            raise AssertionError(f"rung-3 failed-prefix step/time differential mismatch: {name}")
        (history if name in ["nested","impure"] else faults).append({"region":name,"status":actual["status"],"fault":actual["fault"],"steps":actual["steps"],"estimate_time":predicted["resources"]["time"],"match":True})
    native_fixture=root/"examples/native-pair-program.bisa"
    target_path=workspace/"bennett-targets/targets/ideal-all-to-all.json"
    admitted=json.loads(subprocess.run([str(vm),"check",str(native_fixture)],capture_output=True,text=True,timeout=30,check=True).stdout)
    actual=json.loads(subprocess.run([str(vm),"run-program",str(native_fixture),"main","--target",str(target_path)],capture_output=True,text=True,timeout=30,check=True).stdout)
    predicted=json.loads(subprocess.run([str(estimator),str(native_fixture),"--target",str(target_path),"--region","pair"],capture_output=True,text=True,timeout=30,check=True).stdout)
    target=json.loads(target_path.read_text(),parse_float=Decimal)
    charged=actual["target_resources"];classical_time=Fraction(target["capabilities"]["classical_step_time"])*actual["steps"]
    quantum_time=Fraction(charged["time"])-classical_time
    if admitted["object_hash"]!=predicted["object_hash"] or actual["status"]!="COMPLETED" or predicted["label"]!="exact" or Fraction(charged["gate_count"])!=Fraction(predicted["resources"]["gate_count"]) or quantum_time!=Fraction(predicted["resources"]["time"]) or Fraction(actual["target_error"])!=0 or Fraction(predicted["error_bound"])!=0:
        raise AssertionError("native action pair gate-count/time differential mismatch")
    for row in ["peak_qubits","qubit_second"]:
        if Fraction(predicted["resources"][row+"[data]"])>Fraction(charged[row]["data"]):raise AssertionError("action-only resource exceeds its complete program ledger")
    native={"status":"matched","scope":"pair contains every quantum gate of this wrapper; gate counts match exactly, and action duration equals program time minus the stated classical instruction time; action peak/occupancy are lower bounds on the complete program ledger",
            "object_hash":predicted["object_hash"],"target_hash":predicted["target_hash"],"vm_native_gate_count":charged["gate_count"],"estimate_native_gate_count":predicted["resources"]["gate_count"],
            "vm_program_time":charged["time"],"vm_classical_steps":actual["steps"],"vm_nonclassical_time":str(quantum_time),"estimate_action_time":predicted["resources"]["time"],
            "vm_program_occupancy":charged["qubit_second"]["data"],"estimate_action_occupancy":predicted["resources"]["qubit_second[data]"],"space_relation":"action <= program"}
    programs=[]
    for name,status in [("native-pair-program","COMPLETED"),("register-views-program","COMPLETED"),("register-alias-fault","FAILED"),("block-image-program","COMPLETED"),("register-disjoint-pairs","COMPLETED")]:
        fixture=root/"examples"/(name+".bisa")
        actual=json.loads(subprocess.run([str(vm),"run-program",str(fixture),"main","--target",str(target_path)],capture_output=True,text=True,timeout=30,check=True).stdout)
        predicted=json.loads(subprocess.run([str(estimator),str(fixture),"--target",str(target_path),"--region","main"],capture_output=True,text=True,timeout=30,check=True).stdout)
        charged=actual["target_resources"];flat={}
        for row,value in charged.items():
            if isinstance(value,dict):
                for cls,amount in value.items():
                    escaped="".join(c if c.isascii() and (c.isalnum() or c in "-._~") else "".join("%"+format(b,"02X") for b in c.encode()) for c in cls)
                    flat[row+"["+escaped+"]"]=Fraction(amount)
            else:flat[row]=Fraction(value)
        exact={row:Fraction(int(q["numerator"]),int(q["denominator"])) for row,q in predicted["exact_resources"].items()}
        if actual["status"]!=status or predicted["classical_status"]!=status or predicted["label"]!="exact" or int(predicted["classical_steps"])!=actual["steps"] or flat!=exact or Fraction(predicted["error_bound"])!=Fraction(actual["target_error"]):
            raise AssertionError("complete register-program differential mismatch: "+name)
        programs.append({"fixture":name,"status":status,"steps":actual["steps"],"object_hash":predicted["object_hash"],"target_hash":predicted["target_hash"],"resources":predicted["resources"],"match":True})
    rung2=workspace/"bennett-conformance/ladder/rung-2"
    if not (rung2/"fixtures/hashtable.c").is_file(): raise RuntimeError("rung-2 data corpus missing")
    objects=sorted([*rung2.rglob("*.bisa"),*rung2.rglob("*.bennett")])
    return {"native_action":native,"native_programs":programs,"rung3":{"status":"matched","scope":"resolved classical instruction count and sequential time, including failed prefixes and cancellation-aware history; no coherent gate-count claim","rows":rows,"fault_rows":faults,"history_rows":history},
            "rung2":{"status":"objects_available" if objects else "unavailable","objects":[str(p.relative_to(workspace)) for p in objects],"reason":"rung-2 currently publishes C/LLVM and blocked pipeline reports; no ISA object or gate/step count is present" if not objects else "new ISA artifacts require differential admission"}}


if __name__=="__main__":
    import sys
    print(json.dumps(run(Path(__file__).resolve().parents[1],Path(sys.argv[1]).resolve()),sort_keys=True,separators=(",",":")))
