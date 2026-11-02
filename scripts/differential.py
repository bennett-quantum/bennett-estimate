"""Run published VM binary as a differential oracle; never import its code."""
import json
import os
from pathlib import Path
import subprocess


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
    rung2=workspace/"bennett-conformance/ladder/rung-2"
    if not (rung2/"fixtures/hashtable.c").is_file(): raise RuntimeError("rung-2 data corpus missing")
    objects=sorted([*rung2.rglob("*.bisa"),*rung2.rglob("*.bennett")])
    return {"rung3":{"status":"matched","scope":"resolved classical instruction count and sequential time, including failed prefixes and cancellation-aware history; no coherent gate-count claim","rows":rows,"fault_rows":faults,"history_rows":history},
            "rung2":{"status":"objects_available" if objects else "unavailable","objects":[str(p.relative_to(workspace)) for p in objects],"reason":"rung-2 currently publishes C/LLVM and blocked pipeline reports; no ISA object or gate/step count is present" if not objects else "new ISA artifacts require differential admission"}}


if __name__=="__main__":
    import sys
    print(json.dumps(run(Path(__file__).resolve().parents[1],Path(sys.argv[1]).resolve()),sort_keys=True,separators=(",",":")))
