"""Explicitly regenerate the provenance ledger for historical literal asserts.

This does not rewrite expected values or claim independent derivations.
The tests must pass before the ledger is written. Output is a self-consistency
baseline wherever earlier sessions did not record their source.
"""
import ast
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def main():
    sys.path.insert(0, str(ROOT / "tests"))
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
                "assertion": ast.get_source_segment(source, node), "expected": repr(expected),
                "provenance": "historical origin unrecorded; regenerated estimator/test baseline, not an independent oracle",
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
        result = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.discover(str(ROOT / "tests")))
    finally:
        unittest.TestCase.assertEqual = original
    if not result.wasSuccessful():
        raise SystemExit(1)
    entries = list(sites.values())
    for site in entries:
        if not site["observations"]:
            site["provenance"] = "historical origin unrecorded; branch not executed, no regenerated or independent claim"
    output = {"schema": "literal-expectations/1", "command": "timeout 300 python3 -I -B scripts/record_expectations.py",
              "note": "Expected literals are unchanged. Regeneration labels describe present evidence, never earlier authorship.",
              "catalog_sha256": hashlib.sha256((ROOT / "data/ref-0.9.json").read_bytes()).hexdigest(), "assertions": entries}
    (ROOT / "data/literal-expectations.json").write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    print(f"Recorded {len(entries)} literal assertion sites; {sum(bool(s['observations']) for s in entries)} regenerated.")


if __name__ == "__main__":
    main()
