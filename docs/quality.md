# Quality evidence

The estimator is Python; Cargo packages its stdlib-only interpreter and catalog.
Coverage of the Rust launcher alone does not measure estimator semantics.

## Reproduction

Run headlessly with `TMPDIR=$PWD/.tmp/quality-estimate/tmp` and
`CARGO_TARGET_DIR=$PWD/.tmp/quality-estimate/target` (create both directories).
All test inputs and the VM binary resolve through `gate.toml` using
`scripts/pinned.py`; missing pins and wrong revisions fail loudly. No test
reads a live sibling checkout. The ISA gate pin includes the separately
adopted K86/K91 contracts; `SPEC_VERSIONS.toml` still declares partial adoption.

`timeout 180 cargo test --offline --locked -j3 -- --test-threads=4` passed
240 Python tests through four Rust wrappers in **62.78 s** on the final
implementation. No tests were removed or excluded. The default is below the
180-second limit without a slow suite. Test debug information uses
`line-tables-only`.

## Python coverage

Coverage.py 7.17.2 is a development dependency in a job-local environment;
production still uses only the standard library. Install it in a local Python
environment, then run:

```sh
timeout 600 .tmp/quality-estimate/venv/bin/python -B scripts/measure_coverage.py
```

The script runs the four default groups concurrently, traces API execution
and the CLI Python source in subprocesses, combines their data and writes
`.tmp/quality-estimate/coverage/report.json`. It substitutes a tracing entry
point for the Rust launcher; the default Cargo run separately tests the actual
packaged launcher.

**Statement coverage: 96.20% (4,276 / 4,445 statements)** on the final
implementation. Combined statement/branch coverage is 94.36% (the report
displays 94%); it uses a different denominator. All 240 tests passed under
instrumentation across the four groups. The bounded accounting retry and
combination commands are recorded below. This measurement is separate from
the default Cargo run. Its passing assertions regenerate the literal inventory.

The repository has one Python implementation module. The five lowest-covered
substantial functions are recorded below with their missed-path disposition;
coverage is evidence, not a correctness threshold.

| Region | Statement coverage | Disposition |
| --- | ---: | --- |
| `Catalog.safe_index_fold` | 84.13% | Item7 adds malformed-node propagation and intentional non-affine fallback tests. |
| `Certificate.claim` | 87.50% | Added positive/negative library and translation witness schema tests; parsing never establishes a proof. |
| `Target.read` | 88.89% | Added qram/import/weighted-objective validation, including negative factors. Metadata consumption remains the published resource contract's responsibility. |
| `expression` | 91.43% | Added exact table indexing, out-of-range boundaries and rational division. |
| `Source.oracle_stream` | 91.84% | Remaining initialized-source storage branches overlap pending physical pseudo-location bindings (EST-SOURCE-01, tracked by the source-contract issue). Existing image/adjoint tests cover the supported quantum-image path; no physical carrier is invented to raise coverage. |

These percentages identify the measured pre-refactor areas, before the added
edge tests; the final overall measurement above includes the added tests and phase extraction.

## Oracle independence and literal provenance

`tests/brute_ledger.py` is a third implementation: it imports no estimator
code, enumerates small circuits, and charges each gate against the storage
live at that instant. It uses neither Profile composition nor the production
Ledger's endpoint sweep. `test_brute_accounting.py` compares all four resource
rows with both the algebraic summary and literal recipe traversal across48
small dispatch contexts (empty, non-power-of-two cell counts, zero/nonzero
widths, controls and copy/exchange), with rational control-dependent costs.
Source loops independently compare summary and frame reconstruction for
clean/borrowed lifetimes and0/1/3 repetitions. A deliberately perturbed
summary area is detected. This bounded oracle does not claim complete source,
schedule or model-verification coverage.

Hand derivation for the independent unit-duration witness (S=1,C=1,N=2):
equality has22S+5=27 gates, each dispatch uses two equalities plus two
data gates, giving56 gates/time. Equality scratch area is
(S+1)(22S+5)+54S+3=111. Constant/equality wires add2*56=112;
total area334 and peak2S+5=7. The brute implementation replays allocations
and gates rather than evaluating those formulas.

The large stack witness S=21,C=2^20,K=64,N=32 now asserts exact values.
Each equality has22S+5 gates, including4S Toffolis. The pinned ideal target
charges a Toffoli6 time units, so equality time is42S+5. Binary addresses
0..C-1 have10 set bits on average; their prepare/unprepare adds20 gates
per cell. Thus gate_count=986C, time=1826C and peak=47. Comparator scratch
area is(S+1)(22S+5)+54S+3+20S(S+4)=21911. Constant/equal storage
adds(S+1)(2*(42S+5)+N)+2S*10; with two comparator scratch contributions
the total is83974C. The stronger assertion initially caught an omitted
Toffoli duration in this paper calculation; the pinned target resolved it.

The simple borrowed-loop CLI witness has two interface wires and one borrowed
wire live for four unit-duration CX gates:4 gates,time4,peak3,area12.
The fixed-instance selector test now executes `pick` and checks both the
matching instance and a nonmatching instance, rather than only parsing.

Historical numeric literals had no recorded authorship derivation.
`data/literal-expectations.json` explicitly inventories literal assertion
sites, their complete assertion, expected value, observed values and test
identity. `timeout 600 python3 -I -B scripts/record_expectations.py` reruns
the tests and records them as **regenerated baselines**, never independent
answers or retrospective hand derivations. It leaves expected values intact.
Unexecuted conditional branches are labeled unexecuted rather than regenerated.
The implicit-length lift.load triples(66356,345,19648878) and
(66480,376,21484636) are also explicitly regenerated regression expectations.
Independent evidence is confined to published normative witnesses, the named
paper derivations above, the brute oracle and the executed VM differential.

## Phase equivalence

Classical execution now has explicit `ClassicalMachine` state and arithmetic,
register, quantum-call and execution methods. Token/register value types live
at module scope. The estimate entry point initializes and runs that machine;
`action_nodes` delegates action, oracle and in-place calls to named phases.
Five red-first phase unit tests pass. No function in the implementation
exceeds300 lines (the longest is the252-line padded oracle constructor).

Before/after `timeout 180 python3 -I -B scripts/phase_snapshot.py <source>`
compared244 requests across bounded fixtures, the pinned ideal target and the
owned finite-topology target, with and without frame reconstruction. All186
successful result documents and58 failure messages were byte-identical.
Snapshot SHA-256: `c8564ec4f94c76403a6c718d91d429ccc38708688e06598714d3e4cbb8c6f401`.
Scaling fixtures and positive padded budgets remain in the normal unit tests;
they are not repeated by this bounded snapshot. The first wider snapshot
hit its240-second limit and was replaced by this bounded comparison.

Post-refactor default Cargo run:231 Python tests, four Rust wrappers, all
passed in155.74s while other bounded verification ran concurrently.

## Fail-fast and repository hygiene

Index folding catches only its dedicated intentional-decline exception;
malformed node TypeError/KeyError/ValueError/ContractError exceptions now
propagate. A valid nonlinear index still traverses literally and produces
its exact result. Mint validation catches only modeled budget-bound failures,
preserving their diagnostic in `classical_fault_reason`; an internal validator
ContractError propagates. Four red-first regressions exercise both distinctions.

Pending reports retain contract codes/reasons and invocation bindings without
task-tracker IDs. Known native-model metadata has unchecked obligations;
unknown model versions explicitly report unsupported-model. Resource rows
remain cost calculations. All tracked bytecode under owned paths was removed;
ignore rules cover bytecode, caches, logs, Dolt LOCK files and `.darc` archives.

## Final default validation

`timeout 180 cargo test --offline --locked -j3 -- --test-threads=4` passed
all 240 Python tests (75 objects, 123 accounting, 16 selectors, 26 other),
through four Rust wrappers. `/usr/bin/time` measured **62.78 s wall**,
including the build check, with 106,216 KiB peak RSS. Cargo's test interval was
62.64 s. No tests are ignored or skipped. This final run was measured after
our coverage workers finished; the earlier overlapping timeout is recorded
below rather than treated as a pass.

`cargo fmt --check`,
`timeout 60 cargo clippy --offline --locked -j3 --all-targets -- -D warnings`,
and `bash -n scripts/pre-push scripts/check scripts/install-hooks.sh` all
passed. Spec bytes, feature pins and vendored catalog bytes were checked
against the gate-pinned published source. No consumer or full push gate ran.

One conditional assertion remains unexecuted in the provenance inventory:
VM topology matching. The pinned VM rejects the topology field with
`§8: unknown field topology`; the differential reports unavailable forecasts,
keeps that matched-status branch and makes no topology-match claim.

## Final coverage dispositions

The final five least-covered substantial functions (at least30 executable
statements) are below. Each has unit coverage; these are remaining branch
gaps, not missing implementation declarations.

| Function | Statement coverage | Tests and remaining evidence |
| --- | ---: | --- |
| `Source.lower_action_call` | 86.49% | Positive callee binding/expansion phase test and existing nested-call tests. Additional memory-interface forwarding combinations remain part of full linked-source coverage. |
| `Catalog.safe_index_fold` | 87.30% | New malformed-node propagation and valid nonlinear-literal tests, plus existing middle-index/control-alias regressions. Remaining declines retain literal validation. |
| `ClassicalMachine.__init__` | 87.50% | All classical phase tests initialize independent machines; block-image programs exercise persistent device state. Remaining global-image layout variants belong to the existing complete classical-source work. |
| `ClassicalMachine.arithmetic` | 87.80% | Direct signed-division and zero-divisor unit tests, plus existing resolved arithmetic/opaque-ID programs. Complete per-op boundaries remain useful follow-up coverage. |
| `Source.lower_qinplace` | 89.47% | Arity phase test and existing positive private-leaf/call-occurrence tests. Extra memory/classical capture combinations remain part of full context coverage. |

The final inventory contains 358 literal assertion sites, 357 regenerated and
one explicitly unexecuted topology-match branch. Every entry includes a hash
of its test source; all hashes were checked against the final files.

## Quality ratchet

`python3 -I -B scripts/quality_ratchet.py` is the single quality gate check.
`--record` prints a candidate baseline for review; the check never rewrites it.
The baseline below measures tracked Python under `src/`, `scripts/` and
`tests/` (including nested functions). Rust remains the small packaging launcher;
this AST metric measures the Python implementation and its tooling/tests.

Function lengths are physical definition-to-end spans, including nested
function bodies. The sorted lists are exact empirical distributions, without
size buckets or a fixed length limit. For each file the gate rejects an increase
in the fraction of functions at or above any observed length. It also rejects
increased cognitive-complexity mass or trivial-wrapper count per file. New files
start at zero; moving code or changing the baseline requires explicit review.
Complexity adds `1 + nesting depth` for if/conditional expressions, loops,
exception handlers, matches and comprehensions, and one per extra boolean
operand. Function boundaries reset nesting; this is a documented AST proxy,
not an external analyser's cognitive-complexity score. A trivial wrapper has
only one returned/executed call with simple name/attribute arguments and no
keywords, after excluding its docstring. Pairing these metrics discourages
splitting into delegating functions just to improve length or nesting.

The script also greps tracked paths for bytecode/cache/log/lock/backup/progress
litter (`Cargo.lock` is the intentional dependency manifest), and source,
tooling, example, fixture and data text for bead/job/shift/review identifiers.
Test code and documentation may discuss the process. Both match lists are
empty. These are the `LITTER` and `PROCESS` expressions in the same script;
they are hygiene checks, not semantic evidence. The gate rejects increased
match counts. No coverage threshold or dashboard is introduced.

Red-first evidence: the new scratch-repository test initially failed because
the script did not exist; after implementation it passed. It records a
three-line function in `TMPDIR`, accepts the unchanged file, then requires
exit 1 for longer code, added control flow, a trivial wrapper, a process
identifier and tracked log litter. All deliberately worse files stay outside
the source tree. `timeout 30 python3 -I -B -m unittest discover -s tests -p
test_quality_ratchet.py -v` passed. The hook-configuration test was also seen
red before adding the one new `gate.toml` check, then passed.

Two further scratch probes initially returned exit 0 for an upstream tracker
identifier and a suffixed runtime lock. The grep now recognises the ecosystem's
upstream prefixes, job/shift/review/session labels and suffixed lock files.
Both probes now return exit 1; `test_quality_ratchet_hygiene.py` independently
checks each case. Both quality-check test methods pass.

<!-- quality-baseline -->
```json
{"files": {
  "scripts/differential.py": {"cognitive_complexity": 76, "function_lengths": [18, 71], "trivial_wrappers": 0},
  "scripts/measure_coverage.py": {"cognitive_complexity": 2, "function_lengths": [5, 36], "trivial_wrappers": 0},
  "scripts/phase_snapshot.py": {"cognitive_complexity": 50, "function_lengths": [33], "trivial_wrappers": 0},
  "scripts/pinned.py": {"cognitive_complexity": 23, "function_lengths": [11, 28], "trivial_wrappers": 0},
  "scripts/quality_ratchet.py": {"cognitive_complexity": 63, "function_lengths": [3, 4, 11, 18, 18, 18, 23], "trivial_wrappers": 0},
  "scripts/record_expectations.py": {"cognitive_complexity": 38, "function_lengths": [4, 10, 11, 17, 58], "trivial_wrappers": 0},
  "src/estimate.py": {"cognitive_complexity": 6377, "function_lengths": [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 8, 8, 8, 8, 8, 8, 8, 9, 9, 9, 9, 10, 10, 10, 10, 10, 10, 10, 10, 11, 11, 11, 12, 12, 12, 12, 13, 13, 13, 13, 13, 13, 14, 14, 14, 14, 15, 15, 15, 15, 16, 16, 17, 17, 17, 17, 17, 17, 18, 18, 18, 18, 18, 18, 19, 19, 20, 21, 21, 21, 22, 22, 23, 23, 24, 24, 24, 25, 25, 26, 26, 26, 26, 26, 27, 29, 29, 30, 31, 32, 35, 36, 36, 36, 37, 37, 38, 40, 42, 45, 45, 48, 49, 52, 55, 57, 57, 59, 59, 60, 60, 62, 63, 66, 69, 69, 70, 71, 71, 80, 85, 88, 97, 121, 147, 166, 176, 207, 248, 252], "trivial_wrappers": 6},
  "tests/brute_ledger.py": {"cognitive_complexity": 39, "function_lengths": [2, 5, 5, 6, 7, 17, 32], "trivial_wrappers": 0},
  "tests/run_suite.py": {"cognitive_complexity": 14, "function_lengths": [4, 8, 10], "trivial_wrappers": 0},
  "tests/test_brute_accounting.py": {"cognitive_complexity": 24, "function_lengths": [4, 4, 13, 14, 23], "trivial_wrappers": 0},
  "tests/test_estimate.py": {"cognitive_complexity": 157, "function_lengths": [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 3, 3, 3, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 5, 5, 5, 5, 6, 6, 6, 6, 6, 6, 6, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 8, 8, 8, 8, 8, 8, 8, 8, 9, 9, 9, 10, 10, 10, 10, 10, 10, 10, 10, 11, 11, 11, 11, 11, 11, 12, 12, 12, 12, 12, 13, 13, 13, 14, 14, 14, 14, 15, 15, 16, 16, 16, 16, 16, 16, 16, 17, 18, 19, 19, 19, 21, 23], "trivial_wrappers": 0},
  "tests/test_fail_fast.py": {"cognitive_complexity": 1, "function_lengths": [2, 4, 6, 7, 7, 8], "trivial_wrappers": 0},
  "tests/test_gate.py": {"cognitive_complexity": 8, "function_lengths": [12, 26], "trivial_wrappers": 0},
  "tests/test_output.py": {"cognitive_complexity": 0, "function_lengths": [9, 12], "trivial_wrappers": 0},
  "tests/test_phases.py": {"cognitive_complexity": 4, "function_lengths": [5, 5, 6, 7, 7, 8, 11, 14], "trivial_wrappers": 0},
  "tests/test_quality.py": {"cognitive_complexity": 9, "function_lengths": [7, 9, 11, 15, 15, 27], "trivial_wrappers": 0},
  "tests/test_quality_ratchet.py": {"cognitive_complexity": 2, "function_lengths": [40], "trivial_wrappers": 0},
  "tests/test_quality_ratchet_hygiene.py": {"cognitive_complexity": 1, "function_lengths": [23], "trivial_wrappers": 0},
  "tests/test_schedule.py": {"cognitive_complexity": 344, "function_lengths": [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 5, 5, 5, 5, 5, 5, 6, 6, 6, 6, 6, 6, 6, 6, 6, 7, 7, 7, 7, 7, 7, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 9, 9, 9, 9, 9, 9, 9, 10, 10, 10, 10, 10, 10, 10, 10, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 14, 14, 14, 14, 14, 14, 14, 14, 15, 15, 15, 15, 15, 15, 15, 15, 16, 16, 16, 16, 16, 17, 17, 17, 17, 17, 17, 17, 17, 17, 18, 19, 19, 19, 19, 19, 19, 20, 20, 21, 23, 23, 24, 24, 25, 26, 29, 31, 31, 32, 38, 40], "trivial_wrappers": 0}
}, "litter": [], "process_identifiers": []}
```
<!-- /quality-baseline -->

## Continuation cleanup verification

The inherited diff was re-read against COMMON.md's anti-slop rules. Classical
instruction families are now classified once at construction into an enum,
and execution matches on that enum. This removes duplicated arithmetic and
register dispatch predicates. The unused arithmetic/quantum-call locals,
unused action-call region map, single-use classical forwarding method and
single-iteration budget/control loops in the snapshot tool were deleted.
The source wrapper count fell from seven to six; no source function exceeds
252 lines. The recorded initial baseline above includes this final cleanup
and its classifier test before review handover.

The classifier test was observed red (missing dispatch-family field), then
all six phase tests passed; all four fail-fast tests also passed. The final
before/after snapshot compared 244 requests byte for byte, including result
documents and failures. Commands:

    timeout 180 python3 -I -B scripts/phase_snapshot.py "$TMPDIR/before_cleanup.py"
    timeout 180 python3 -I -B scripts/phase_snapshot.py
    cmp .tmp/quality-estimate/cleanup-before.json .tmp/quality-estimate/cleanup-after.json

The outputs matched; both SHA-256 values are
`8e9dd95c95a8bc6cce24a50b39292db6dac293197caace983a55e2a1dc14d4f2`.
The source copy and snapshots remain in the ignored job directory.
The default test run immediately before deleting the forwarding wrapper passed
239 Python tests through four Rust wrappers in 72.81 seconds; the final run
and fresh coverage measurement are recorded below.

## Current coverage reproduction and runtime limits

The first `timeout 600 .tmp/quality-estimate/venv/bin/python -B
scripts/measure_coverage.py` run failed loudly at its accounting worker's
480-second timeout. Objects (75 tests, 450.709 s), selectors (16 tests,
352.919 s) and the original other group passed. The successful groups were
retained. The stale accounting JSON was deleted, and all 123 accounting tests
were rerun successfully in 395.017 s (400.54 s including tracing teardown).
The other group was rerun after adding the hygiene regression: 26 tests,
3.775 s. Estimator source and the existing test sources did not change between
these measurements. The final inventory has 358 assertion sites, 357
regenerated and one explicitly unexecuted topology-match branch; all recorded
source hashes match the final files.

After the initial measurement, reproduce the bounded group retry and combine
with the same headless environment and job-local coverage.py installation:

```sh
evidence="$PWD/.tmp/quality-estimate/coverage"
export COVERAGE_FILE="$evidence/data" PYTHONDONTWRITEBYTECODE=1
export BENNETT_ESTIMATE_BIN="$evidence/estimate-covered"
python=.tmp/quality-estimate/venv/bin/python
rm -f "$evidence/accounting.json"
timeout 900 "$python" -m coverage run --parallel-mode --branch --source=src \
  scripts/record_expectations.py accounting "$evidence/accounting.json"
timeout 60 "$python" -m coverage run --parallel-mode --branch --source=src \
  scripts/record_expectations.py other "$evidence/other.json"
"$python" -I -B scripts/record_expectations.py --combine "$evidence"
"$python" -m coverage combine "$evidence"
"$python" -m coverage json -o "$evidence/report.json"
```

An overlapping final-source default run also reached its 180-second limit
with no assertion failure before termination. That is a timeout, not a green
run. The final default timing below is measured after coverage workers finish.
Neither test selection nor the default 180-second limit was changed.

Final checkpoint: the unchanged default command passed all 240 Python tests
and four Rust wrappers in 62.78 s wall (62.64 s test interval, 106,216 KiB
peak RSS). The standalone quality check, formatting, strict Clippy and shell
syntax checks passed. All four gate pins, both adopted feature document hashes,
vendored catalog bytes and all literal-inventory source hashes were verified.
No full push gate or consumer gate ran; those remain merge-time work.
