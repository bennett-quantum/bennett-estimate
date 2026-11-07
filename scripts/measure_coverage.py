"""Measure Python API and CLI coverage against gate-pinned inputs.

Run with a Python environment containing coverage.py. Production remains
stdlib-only. Four bounded workers use the same suite partition as cargo test.
"""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    directory = Path(os.environ["TMPDIR"]).parent / "coverage"
    directory.mkdir(parents=True, exist_ok=True)
    data = directory / "data"
    for old in directory.glob("data*"):
        old.unlink()
    # The CLI normally runs isolated inside the Rust launcher. Use the same
    # Python source as a coverage entry point to include subprocess CLI paths.
    wrapper = directory / "estimate-covered"
    wrapper.write_text(
        f"#!{sys.executable}\n"
        "import coverage, runpy\n"
        f"cov=coverage.Coverage(data_file={str(data)!r}, data_suffix=True, branch=True, source=[{str(ROOT / 'src')!r}])\n"
        "cov.start()\n"
        f"try: runpy.run_path({str(ROOT / 'src/estimate.py')!r}, run_name='__main__')\n"
        "finally: cov.stop(); cov.save()\n"
    )
    wrapper.chmod(0o755)
    env = dict(os.environ, COVERAGE_FILE=str(data), BENNETT_ESTIMATE_BIN=str(wrapper), PYTHONDONTWRITEBYTECODE="1")

    def group(name):
        with (directory / (name + ".log")).open("w") as log:
            subprocess.run([sys.executable, "-m", "coverage", "run", "--parallel-mode", "--branch", "--source=src",
                            "scripts/record_expectations.py", name, str(directory / (name + ".json"))], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                           timeout=480, check=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(group, ("objects", "accounting", "selectors", "other")))
    subprocess.run([sys.executable, "-I", "-B", "scripts/record_expectations.py", "--combine", str(directory)], cwd=ROOT, env=env, check=True)
    subprocess.run([sys.executable, "-m", "coverage", "combine", str(directory)], cwd=ROOT, env=env, check=True)
    subprocess.run([sys.executable, "-m", "coverage", "json", "-o", str(directory / "report.json")], cwd=ROOT, env=env, check=True)
    subprocess.run([sys.executable, "-m", "coverage", "report", "-m"], cwd=ROOT, env=env, check=True)
    report = json.loads((directory / "report.json").read_text())
    print("Python statement coverage: {:.2f}% ({}/{})".format(
        100 * report["totals"]["covered_lines"] / report["totals"]["num_statements"],
        report["totals"]["covered_lines"], report["totals"]["num_statements"]))


if __name__ == "__main__":
    main()
