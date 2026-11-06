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
219 Python tests through four Rust wrappers in **71.99 s** before phase
refactoring. No tests were removed or excluded. The default is below the
180-second limit without a slow suite. Test debug information uses
`line-tables-only`.

## Python coverage

Coverage.py 7.17.2 is a development dependency in a job-local environment;
production still uses only the standard library. Install it in a local Python
environment, then run:

```sh
timeout 600 .tmp/quality-estimate/venv/bin/python scripts/measure_coverage.py
```

The script runs the four default groups concurrently, traces API execution
and the CLI Python source in subprocesses, combines their data and writes
`.tmp/quality-estimate/coverage/report.json`. It substitutes a tracing entry
point for the Rust launcher; the default Cargo run separately tests the actual
packaged launcher.

**Statement coverage: 96.17% (4,067 / 4,229 statements)** on the pre-refactor
quality checkpoint. Combined statement/branch coverage rounds to94%; it is a
different denominator. All219 tests passed under instrumentation (slowest
worker239.233s). The normal uninstrumented default remains71.99s.

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
edge tests; the final measurement below supersedes the overall number.

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
identity. `timeout 300 python3 -I -B scripts/record_expectations.py` reruns
the tests and records them as **regenerated baselines**, never independent
answers or retrospective hand derivations. It leaves expected values intact.
Unexecuted conditional branches are labeled unexecuted rather than regenerated.
The implicit-length lift.load triples(66356,345,19648878) and
(66480,376,21484636) are also explicitly regenerated regression expectations.
Independent evidence is confined to published normative witnesses, the named
paper derivations above, the brute oracle and the executed VM differential.
