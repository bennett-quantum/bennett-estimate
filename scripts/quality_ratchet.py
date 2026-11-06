"""Compare tracked Python structure and repository hygiene with docs/quality.md."""
import argparse
import ast
from collections import Counter
from fractions import Fraction
import json
from pathlib import Path
import re
import subprocess
import sys

LITTER = re.compile(r"(?:^|/)(?:__pycache__|\.darc)(?:/|$)|\.(?:pyc|log|darc|lock)$|(?:^|/)(?:LOCK|LAST-RUN[^/]*|PROGRESS[^/]*)$", re.I)
PROCESS = re.compile(r"\b(?:bennett(?:-[a-z]+)?-[a-z0-9]{3}(?:\.\d+)*|(?:quality|sol)-estimate|shift[ -]+\d+|review[ -]+round[ -]+\d+)\b(?![\w-])", re.I)
BASELINE = re.compile(r"<!-- quality-baseline -->\s*```json\n(.*?)\n```\s*<!-- /quality-baseline -->", re.S)
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


class Complexity(ast.NodeVisitor):
    """Nesting-weighted control flow; reset nesting at each function boundary."""
    def __init__(self):
        self.mass = 0
        self.depth = 0

    def visit_FunctionDef(self, node):
        previous, self.depth = self.depth, 0
        self.generic_visit(node)
        self.depth = previous

    visit_AsyncFunctionDef = visit_FunctionDef

    def generic_visit(self, node):
        nested = isinstance(node, (ast.If, ast.IfExp, ast.For, ast.AsyncFor, ast.While,
                                   ast.ExceptHandler, ast.Match, ast.comprehension))
        if nested:
            self.mass += 1 + self.depth
            self.depth += 1
        if isinstance(node, ast.BoolOp):
            self.mass += len(node.values) - 1
        super().generic_visit(node)
        if nested:
            self.depth -= 1


def python_metrics(text):
    tree = ast.parse(text)
    lengths, wrappers = [], 0
    for node in ast.walk(tree):
        if not isinstance(node, FUNCTIONS):
            continue
        lengths.append(node.end_lineno - node.lineno + 1)
        body = node.body
        if isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            body = body[1:]
        if len(body) == 1 and isinstance(body[0], (ast.Return, ast.Expr)):
            call = body[0].value
            if isinstance(call, ast.Call) and all(isinstance(arg, (ast.Name, ast.Attribute)) for arg in call.args) and not call.keywords:
                wrappers += 1
    complexity = Complexity()
    complexity.visit(tree)
    return {"function_lengths": sorted(lengths), "cognitive_complexity": complexity.mass,
            "trivial_wrappers": wrappers}


def measure(root):
    tracked = subprocess.run(["git", "-C", str(root), "ls-files", "-z"],
                             capture_output=True, check=True, timeout=10).stdout.decode().split("\0")
    report = {"files": {}, "litter": [], "process_identifiers": []}
    for name in sorted(set(tracked) - {""}):
        path = root / name
        if not path.is_file():
            continue  # A tracked deletion is absent from the pushed tree.
        if name != "Cargo.lock" and LITTER.search(name):
            report["litter"].append(name)
        if path.suffix == ".py" and path.parts and name.split("/")[0] in {"src", "scripts", "tests"}:
            report["files"][name] = python_metrics(path.read_text())
        product = name.split("/")[0] in {"src", "examples", "data", "scripts"} or name.startswith("tests/fixtures/")
        if product and (path.suffix in {".py", ".rs", ".bisa", ".json", ".sh"} or name.startswith("scripts/") and not path.suffix):
            for number, line in enumerate(path.read_text().splitlines(), 1):
                for match in PROCESS.finditer(line):
                    report["process_identifiers"].append(f"{name}:{number}:{match[0]}")
    return report


def regressions(before, after):
    failures = []
    empty = {"function_lengths": [], "cognitive_complexity": 0, "trivial_wrappers": 0}
    for name, current in after["files"].items():
        old = before["files"].get(name, empty)
        previous, lengths = old["function_lengths"], current["function_lengths"]
        # Compare exact empirical tail probabilities at every observed length:
        # adding short functions cannot conceal an increased maximum length.
        old_counts, new_counts = Counter(previous), Counter(lengths)
        old_tail, new_tail = len(previous), len(lengths)
        for length in sorted(old_counts.keys() | new_counts.keys()):
            if Fraction(new_tail, max(1, len(lengths))) > Fraction(old_tail, max(1, len(previous))):
                failures.append(f"{name}: function lengths regressed at {length} lines")
                break
            old_tail -= old_counts[length]
            new_tail -= new_counts[length]
        for metric in ("cognitive_complexity", "trivial_wrappers"):
            if current[metric] > old[metric]:
                failures.append(f"{name}: {metric.replace('_', ' ')} {old[metric]} -> {current[metric]}")
    for metric in ("litter", "process_identifiers"):
        if len(after[metric]) > len(before[metric]):
            failures.append(f"{metric.replace('_', ' ')}: {after[metric]}")
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--record", action="store_true", help="print measured JSON for a reviewed baseline update")
    args = parser.parse_args()
    report = measure(args.root)
    if args.record:
        print(json.dumps(report, sort_keys=True))
        return 0
    match = BASELINE.search((args.root / "docs/quality.md").read_text())
    if match is None:
        raise ValueError("docs/quality.md: missing quality-baseline JSON block")
    failures = regressions(json.loads(match[1]), report)
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print("Quality baseline: no regression")
    return 0


if __name__ == "__main__":
    sys.exit(main())
