# Quality evidence

The estimator is Python; Cargo packages its stdlib-only interpreter and catalog.
Coverage of the Rust launcher alone does not measure estimator semantics.

## Restored terminal cleanup inputs

Implementation `916931a` recognizes a permutation input write followed by
its matched undo. The single `primitive_recompute_obstruction` predicate
implements K81's restored entry versions under §6.2: between the write and
undo, no row may read the changed input or modify the computation's inputs
or targets. Carrier reads/writes, input releases and writes without a
matched undo still obstruct recompute. Diagnostics retain the originating
input-write coordinate. The original contiguous and independent
interleavings remain supported.

The three review source programs were committed verbatim in `eeefd06`
before production changes. At `ed5b9df`,
`timeout 60 python3 -B -m unittest discover -s tests -p test_schedule.py -k test_review_ -v`
passed the independent-row and carrier-read witnesses and failed the
restored-input witness at `entry:4 (x)`. All three pass after the repair.
The restored witness has two original CXs and two input Xs with three live
wires, then five replacement CXs with four: gates/time 9, peak 4, area
`4*3+5*4=32`.

The generated family has 144 programs: X or controlled-X input changes,
with or without undo, interleaved with the remaining inverse and an
independent X, input read, carrier read or another input write. A separate
scalar interpreter enumerates all eight input assignments. Its oracle
compares source and proposed recompute outputs, verifies clean scratch and
restored inputs, and observes input values at reads. It imports no estimator
version or obstruction logic. It classifies 26 programs as admissible and
118 as unsafe. Every case is checked in forward and raw-inverse traversal
(288 subcases); accepted cases also replay actual Ledger operands and
controls and assert every scratch release is zero. In-memory mutation of
only the predicate makes the final generated test fail 52 positive subcases
with the baseline guard, and 118 negative subcases with the guard removed.

Verification at that implementation, in the headless environment below:

- `timeout 900 cargo test -j3 -- --test-threads=4`: 245 Python tests (75 object, 128 accounting, 16 selector, 26 other) and four Rust wrappers passed, no skips; 44.66 s wall, 122,096 KiB peak RSS.
- `BENNETT_ESTIMATE_BIN=$CARGO_TARGET_DIR/debug/bennett-estimate timeout 900 python3 -B -m unittest discover -s tests -v`: all 245 passed in 80.363 s, no skips. Both full runs include the existing ten complete-program resource comparisons against the gate-pinned VM; no topology agreement is claimed.
- `timeout 90 python3 -B -m unittest discover -s tests -p test_schedule.py -k cleanup -v`: 12 passed; `timeout 60 python3 -B -m unittest discover -s tests -p test_schedule.py -k test_k8 -v`: two passed, all 16 fixture/direction subcases.
- `timeout 30 python3 -I -B scripts/quality_ratchet.py`: unchanged baseline passes. Source/test cognitive mass is 6,361/342 against 6,377/344; maximum lengths remain 252/40 and wrappers 6/0. Function distributions pass; litter and process identifiers are empty. Operand-effect parsing, scalar execution and existing budget/ordinal assertions were separated into named phases without removing assertions.
- `cargo fmt --check`, `timeout 60 cargo clippy --offline --locked -j3 --all-targets -- -D warnings`, `bash -n scripts/pre-push scripts/check scripts/install-hooks.sh`, and `git diff --check ed5b9df..HEAD`: passed.

The full gate remains the orchestrator's responsibility. Earlier coverage
and literal-inventory measurements below retain their original scope.

## Terminal cleanup dependency safety

Verified on 2026-11-07 at implementation `9a4e7a8`, after the dependency
repair `ecc38f7`. ISA 0.9 §6.2/§6.4 and §11 K80/K81 at gate pin
`fd626d37aba1f719c3b7b2059be46cbfaf462886` permit moving the owned inverses
past disjoint rows. Checking only writes to the carrier had also admitted
rows reading its partly restored value or changing a replay input.

That implementation retained complete read/write ranges and rejected every
non-owned row that read or wrote a carrier/target or wrote a computation
input. The restored-history repair above replaces the blanket input-write
ban; releasing an input still changes its lifetime and blocks replay.
Explicit recompute fails before suppressing any inverse and names the
non-disjoint source row; reverse remains available. The contiguous and both
independent X placements retain their counts and source positions.

The regression oracle executes the actual `Ledger.gate` wire identities,
offsets and controls with bitwise AND/XOR, independently of estimator version
matching and resource algebra. Each integer bit represents one basis input:
`x=0xC,z=0xA` enumerate four assignments; `x=0xF0,z=0xCC,y=0xAA`
enumerate eight. Expectations are hand-derived: independent X flips y,
a carrier read between the inverses XORs x into y, a read after both inverses
leaves y unchanged, and input X flips that input. Every scratch release must
be zero on every assignment. Forward and raw inverse are checked separately.
Complete positive gate traces also assert operands and controls.

Both original counterexamples failed red first because no error was raised.
The final five non-disjoint cases cover carrier reads between and after the
inverses, input writes between and after them, and input release. Running the
final test against pre-guard `16ebd9e` loaded in memory gives all ten expected
subcase failures, with no test errors. Source partitioning and terminal-plan
construction are separate phases; shared source coordinates and fixture data
remove repeated formatting and test branching.

Verification in the headless environment below, with no source edits afterward:

- `timeout 60 python3 -B -m unittest discover -s tests -p test_schedule.py -k test_k8 -v`: two tests, all 16 fixture/direction subcases passed.
- `timeout 90 python3 -B -m unittest discover -s tests -p test_schedule.py -k cleanup -v`: eight tests passed in 4.831 s.
- `timeout 180 cargo test --offline --locked -j3 -- --test-threads=4`: 241 Python tests and four Rust wrappers passed, no skips; 118.40 s wall, 117.58 s Cargo interval, 124,196 KiB peak RSS.
- `BENNETT_ESTIMATE_BIN=$CARGO_TARGET_DIR/debug/bennett-estimate timeout 180 python3 -B -m unittest discover -s tests -p test_estimate.py -k differential_rung3_and_rung2_inventory -v`: passed in 18.628 s, 19.01 s wall. This includes all ten complete CC-program comparisons against VM pin `d9cb68433c08f4db8f7d8c90f121a8adae51759b`. The VM still reports topology unavailable; no topology match is claimed.
- `timeout 30 python3 -I -B scripts/quality_ratchet.py`: no regression against the unchanged baseline. Source cognitive-complexity mass is 6,367 against 6,377; test_schedule is 343 against 344. Maximum function lengths remain 252 and 40. Function-length distributions and wrapper counts pass; litter and process-identifier lists remain empty.
- `cargo fmt --check`, `timeout 60 cargo clippy --offline --locked -j3 --all-targets -- -D warnings`, `bash -n scripts/pre-push scripts/check scripts/install-hooks.sh`, and `git diff --check 16ebd9e..HEAD`: passed.

Coverage and the literal inventory below remain earlier snapshots, scoped by
their recorded source hashes. The following interleaving section records the
earlier repair and its measurements.

## Terminal cleanup interleavings

The K80 witness now also covers an independent `x y` between the two inverse
CX rows and immediately before `qfree`. ISA 0.9 §11 K81 at gate-pinned
`fd626d37aba1f719c3b7b2059be46cbfaf462886` excludes disjoint rows from the
terminal chain and does not require textual adjacency. The partition keeps
its occurrence ownership; recompute suppresses only the owned inverse rows,
preserves the independent X once at its original point, and emits replacement
leaves at the release carrier. No other textual-adjacency condition was found
in the partition, ownership wrappers, cleanup selection or primitive replay.

Both interleavings failed with the pending recompute-binding error before the
fix. The shared witness retains the contiguous case and checks exact complete
leaf traces in forward and raw-inverse traversal. Running the final test
against the pre-fix source in memory passes both contiguous traversals and
produces the four expected interleaving errors. Its expectations are hand
derived: the contiguous case has two CXs with three live wires and five fresh
compute/XOR/uncompute CXs with four, giving 7 gates, time 7, peak 4 and area
26. With independent y, the two original CXs and X use four wires; the five
replacement CXs use five, giving 8 gates, time 8, peak 5 and area 37.

Verification after the repair, using the headless environment below:

- `timeout 60 python3 -B -m unittest discover -s tests -p test_schedule.py -k test_k80 -v`: passed all six fixture/direction subcases.
- `timeout 90 python3 -B -m unittest discover -s tests -p test_schedule.py -k cleanup -v`: 8 tests passed in 9.079 s.
- `timeout 180 cargo test --offline --locked -j3 -- --test-threads=4`: all 240 Python tests and four Rust wrappers passed, no skips; 156.87 s wall, 156.17 s Cargo test interval, 123,748 KiB peak RSS.
- `BENNETT_ESTIMATE_BIN=$CARGO_TARGET_DIR/debug/bennett-estimate timeout 180 python3 -B -m unittest discover -s tests -p test_estimate.py -k differential_rung3_and_rung2_inventory -v`: passed in 24.925 s (25.60 s wall), using VM pin `d9cb68433c08f4db8f7d8c90f121a8adae51759b`. This includes all ten complete CC-program resource comparisons. The pinned VM still reports topology unavailable, so no topology match is claimed.
- `timeout 30 python3 -I -B scripts/quality_ratchet.py`: no regression, with the recorded baseline unchanged. Source cognitive-complexity mass decreased 6,377 → 6,376; test_schedule decreased 344 → 338, with maximum function lengths unchanged. The tests share one fixture table and dispatch trace inversion through a mapping.
- `cargo fmt --check`, `timeout 60 cargo clippy --offline --locked -j3 --all-targets -- -D warnings`, and `bash -n scripts/pre-push scripts/check scripts/install-hooks.sh`: passed.

The remaining sections record the earlier quality-baseline measurements.
Coverage and the literal-inventory snapshot were not regenerated for this
repair; their source hashes describe that earlier snapshot. The new witness
expectations have the independent derivation above. The gate verifier
materialised the missing pinned ISA checkout and rebuilt the pinned VM; it
noted that the existing ISA pin is not reachable from `origin/main`.

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
