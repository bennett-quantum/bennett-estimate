"""Explicitly regenerate the provenance ledger for historical literal asserts.

This does not rewrite expected values or claim independent derivations.
The tests must pass before the ledger is written. Output is a self-consistency
baseline wherever earlier sessions did not record their source.
"""
import ast
import concurrent.futures
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


def combine(directory):
    merged = {}
    for name in ("objects", "accounting", "selectors", "other"):
        output = json.loads((directory / (name + ".json")).read_text())
        for site in output["assertions"]:
            key = (site["file"], site["line"])
            if key not in merged:
                merged[key] = site
            elif site["observations"]:
                existing = merged[key]
                existing["observations"] += site["observations"]
                existing["provenance"] = site["provenance"]
                existing["tests"] = sorted(set(existing["tests"] + site["tests"]))
                existing["observed_values"] = sorted(set(existing["observed_values"] + site["observed_values"]))
    output["assertions"] = [merged[key] for key in sorted(merged)]
    (ROOT / "data/literal-expectations.json").write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    print(f"Recorded {len(merged)} literal assertion sites; {sum(bool(s['observations']) for s in merged.values())} regenerated.")


def grouped():
    directory = Path(os.environ["TMPDIR"]).parent / "provenance"
    directory.mkdir(exist_ok=True)
    def worker(name):
        with (directory / (name + ".log")).open("w") as log:
            subprocess.run([sys.executable, "-I", "-B", str(Path(__file__).resolve()), name, str(directory / (name + ".json"))],
                           stdout=log, stderr=subprocess.STDOUT, timeout=480, check=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(worker, ("objects", "accounting", "selectors", "other")))
    combine(directory)


def main():
    if len(sys.argv) == 1:
        grouped()
        return
    if sys.argv[1] == "--combine":
        combine(Path(sys.argv[2]))
        return
    sys.path.insert(0, str(ROOT / "tests"))
    import run_suite
    os.environ.setdefault("BENNETT_ESTIMATE_BIN", str(Path(os.environ["CARGO_TARGET_DIR"]) / "debug/bennett-estimate"))
    sites = {}
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        source = path.read_text()
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr != "assertEqual" or len(node.args) < 2:
                continue
            try:
                expected = ast.literal_eval(node.args[1])
            except (ValueError, TypeError):
                continue
            sites[(str(path), node.lineno)] = {
                "file": str(path.relative_to(ROOT)), "line": node.lineno,
                "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                "assertion": ast.get_source_segment(source, node), "expected": repr(expected),
                "provenance": "regenerated passing-test baseline; no independent derivation claimed by this record",
                "observations": 0, "tests": [], "observed_values": []}
    original = unittest.TestCase.assertEqual

    def record(test, first, second, msg=None):
        caller = inspect.currentframe().f_back
        result = original(test, first, second, msg)
        site = sites.get((caller.f_code.co_filename, caller.f_lineno))
        if site is not None:
            site["observations"] += 1
            if test.id() not in site["tests"]:
                site["tests"].append(test.id())
            if repr(first) not in site["observed_values"]:
                site["observed_values"].append(repr(first))
        return result

    unittest.TestCase.assertEqual = record
    try:
        discovered = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
        selected = unittest.TestSuite(test for test in run_suite.cases(discovered) if run_suite.group(test) == sys.argv[1])
        result = unittest.TextTestRunner(verbosity=2).run(selected)
    finally:
        unittest.TestCase.assertEqual = original
    if not result.wasSuccessful():
        raise SystemExit(1)
    entries = list(sites.values())
    for site in entries:
        if not site["observations"]:
            site["provenance"] = "branch not executed; no regenerated or independent claim"
    output = {"schema": "literal-expectations/1", "command": "timeout 600 python3 -I -B scripts/record_expectations.py",
              "note": "Expected literals are unchanged. Regeneration labels describe present evidence, never earlier authorship.",
              "catalog_sha256": hashlib.sha256((ROOT / "data/ref-0.9.json").read_bytes()).hexdigest(), "assertions": entries}
    Path(sys.argv[2]).write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    print(f"Recorded {len(entries)} literal assertion sites; {sum(bool(s['observations']) for s in entries)} regenerated.")


if __name__ == "__main__":
    main()
