"""Serialize bounded fixture results for a byte-for-byte refactor comparison.

The snapshot is regression evidence, not an independent correctness oracle.
Pass an unchanged source copy as argv[1] to record the pre-refactor side.
"""
import importlib.util
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pinned import sibling

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "src/estimate.py"
    spec = importlib.util.spec_from_file_location("snapshot_estimate", source)
    e = importlib.util.module_from_spec(spec); sys.modules[spec.name] = e
    e.CATALOG_TEXT = (ROOT / "data/ref-0.9.json").read_text()
    spec.loader.exec_module(e)
    results = []
    paths = sorted((ROOT / "examples").glob("*.bisa")) + sorted((ROOT / "tests/fixtures").glob("*.bisa"))
    for path in paths:
        # These named scaling witnesses have millions of allocation events in
        # explicit frame mode; their default summaries remain in unit tests.
        if "2pow20" in path.name or path.name == "fixed-procedure-instances.bisa":
            continue
        obj = e.Object.read(path.read_text())
        for target_path in [sibling(ROOT, "bennett-targets") / "targets/ideal-quantum-circuit.json", ROOT / "data/ideal-four-clique.json"]:
            target = e.Target.read(target_path.read_text())
            for fn in obj.functions.values():
                if fn.kind == "lproc":
                    continue
                types = fn.groups[0] if fn.kind in ["cc", "r"] else fn.groups[4] if fn.kind == "oracle" else fn.groups[3]
                args = [["0"] * 4 if ty == "token" else "0x0000000000000000" if ty == "f64" else "0" for _, ty, _ in types]
                aliases = list(range((fn.kind == "oracle") + sum(ty == "token" for _, ty, _ in types)))
                budget = ["0"] * 4
                for frame in [False, True]:
                    key = [str(path.relative_to(ROOT)), target_path.name, fn.name, budget, frame, 0]
                    print(key, file=sys.stderr, flush=True)
                    try:
                        value = e.estimate(obj, target, fn.name, args, budget, include_frame=frame, token_aliases=aliases)
                        result = ["ok", e.jcs(value)]
                    except e.ContractError as error:
                        result = ["error", str(error)]
                    results.append([key, result])
    print(json.dumps(results, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
