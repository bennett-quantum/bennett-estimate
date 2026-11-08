# Estimate consumer adapter review, round 1

- Reviewer: gpt-6.1-sol
- Date (date -u): 2026-11-08T11:25:58Z
- Reviewed commit: bf002ecd7660dc5f55841d96c841ed14d236cf00
- Base: a05004de10d2d5761baca64478288c65a09be15c
- Implementation commits: 27a0b5f923d4f3c0d7a63e309282d872f40006c0, bf002ecd7660dc5f55841d96c841ed14d236cf00
- Re-run results: baseline RED reproduced; reviewed head focused checks PASS; real rung-4 diagnostic fails loudly as expected. Full gate is owned by the orchestrator and was not run in this review.

Disposition: ACCEPT

## Findings

No P0/P1 findings, no new P2 bead proposals, and no nit.

1. **Estimate labels retain their computed scope.** `src/estimate.py:4858` adds validated request metadata and aliases `padded` to the existing resource rows. It does not change `estimate`'s exact/reference-realisation calculation, conditional classical bound, or assumptions. A direct CLI probe of `example9.bisa --region zero_cc --classical-step-bound 30` reports `label=bound`, time 30, its termination assumption and `rational_upper_bounds`, without `exact_resources`. The new alias equals those conditional resource rows; it never creates a structure-recovery claim. The published controlled-X action independently gives one gate, duration 1, two live interface wires, peak 2 and occupancy 2. Its `exact` label describes that stated reference realisation, without certifying program correctness or structure recovery.

2. **Input bindings are concrete and failures do not fabricate costs.** The raw SHA-256 comes from the same bytes decoded for object parsing. Removing the published object's schedule/certificate sections in an owned scratch copy changes `object_sha256` while preserving `object_hash` and costs. The target name is explicitly the requested filename stem, supplemented by the existing content hash. Named budget order is steps/heap/stack/depth; independent probes preserve all four components, 2^53 exactly, and uint64's maximum as decimal strings when needed. Malformed, negative and overflowing budgets fail with empty stdout. Strict full option names and CRLF rejection reproduce. The pending branch adds the same validated request bindings and exits 3; the direct probe contains none of `padded`, `resources`, `exact_resources` or `rational_upper_bounds`. The existing six contract-gap cases also pass. No new silent default/fallback or north-star scope reduction was found.

3. **The tests, guard classes and documentation support the claimed adapter change.** The seven new CLI tests reproduce three failures and four error subcases on an a05004d archive; unknown-argument rejection already passes there. All seven pass at the reviewed head. The controlled-action expectation is hand-derived from the fixture's controlled call to one X gate and the ideal target's unit duration/rate, rather than harvested from estimator output. All nine pinned-layout tests pass, including the new valid relative layout and malformed/non-directory fallback cases: these permanently retain the coverage requested by `bennett-estimate-0lh`, so its closure is justified. Selected candidates still undergo revision/file-hash validation and cannot fall back on mismatches. The focused guard table names the machine/date and factor: short30 exceeds 10 times 2.44 s; moderate300 exceeds 10 times 19.31 s. Reviewer measurements below also satisfy those margins. The new subprocess constants cite the short class; reviewer shell invocations use the matching classes and record wall/user/sys. The author identified the earlier 30-second whole-CommandLine measurement as calibration; this review reruns it with moderate300. Quality-baseline changes match the diff. README's raw/semantic hash distinction, budget encoding, pending shape, padding scope and incomplete rung status agree with the code and observed artifacts.

4. **The full rung-4 BLOCKED claim is accurate and remains open work.** The named run `/home/tobias/Projects/bennett-workspace/bennett-conformance/.tmp/rung-4/runs/20261108T095801.500599Z` contains only the 5052-byte `rung4-mini.bennett` ISA object: ISA 0.8, four lprocs and a 16-byte data symbol. It has no compiled SQLite ISA launch at any N. Both N1048576 host images are 33,492,992 bytes, requiring 33,554,432 padded bytes and 268,435,456 memory wires; LLVM bitcode is not an ISA launch. Both production stderr files report the pinned bennett-arith bitcode SHA-256 mismatch. The run receipt separately names the missing libc closure (`bcmp`, `localtime`, `realloc`, `strcspn`, `strncmp`, `strrchr`, `strspn`, existing `brt-dj7`) and blocks launch/resource rows. The pinned superconducting target declares data capacity 16 and buffer capacity 4, insufficient for 2^28 wires. The real diagnostic rerun exits 1, stdout empty, with `ISA 0.8 lproc signature: missing` and the missing args/mem/tokens keys. This change adds context to an existing rejection; it does not claim that rejection completes the promised capability. SPEC_VERSIONS.toml pins only the ref 0.9 catalog, not a complete padded 0.8 expansion. No legacy catalog, reduced database, extrapolated launch or recovered structure was invented. `bennett-estimate-b8o` must stay open until an actual full launch with explicit parameters/budgets and suitable published target mechanics yields an honest estimate. Acceptance here covers the adapter commits only.

## Reproduction

All runs unset DISPLAY, WAYLAND_DISPLAY, DBUS_SESSION_BUS_ADDRESS and BROWSER. TMPDIR is `/home/tobias/Projects/bennett-workspace/bennett-estimate-job-est-b8o/.tmp/est-b8o-review/tmp`; CARGO_TARGET_DIR is `/home/tobias/Projects/bennett-workspace/bennett-estimate-job-est-b8o/.tmp/est-b8o-review/target`. Build width 4 and one focused test process follow `docs/hang-guards.md` on this 64-CPU host. BENNETT_ESTIMATE_BIN is `$CARGO_TARGET_DIR/debug/bennett-estimate`; test siblings resolve only through gate.toml pins.

The archive lives at `.tmp/est-b8o-review/red`, contains `git archive a05004d` plus the reviewed `tests/test_cli_report.py`, and has a symlink to the existing pinned cache, used only for reads. Build each source tree with `timeout 30 cargo build --offline --locked -j 4`, then run the identical CLI-test command below in that tree. Shared Cargo output initially reused the archive binary for the first head attempt; that attempt is explicitly invalidated in `reruns.json`. Running `cargo clean -p bennett-estimate --offline` in the owned target directory and rebuilding the actual head resolved the harness contamination. Only the subsequent head run counts as green evidence. A supplementary multi-entry probe initially omitted `--region`; its corrected invocation explicitly selects `main`.

Shell guards in this table cite `docs/hang-guards.md`: short = 30 seconds; moderate = 300 seconds; exit 124 would be UNKNOWN. No guard tripped. CPU seconds are user + sys from `/usr/bin/time -p`.

| Command | Result | Wall / CPU seconds |
| --- | --- | --- |
| archive: `timeout 30 cargo build --offline --locked -j 4` | PASS | 0.41 / 0.51 |
| archive: `timeout 30 python3 -I -B -m unittest discover -s tests -p test_cli_report.py -v` | expected RED: 3 failures, 4 error subcases across 7 methods | 2.42 / 2.41 |
| head: `timeout 30 cargo build --offline --locked -j 4` after owned-target package clean | PASS | 0.30 / 0.40 |
| head: `timeout 30 python3 -I -B -m unittest discover -s tests -p test_cli_report.py -v` | 7 PASS | 2.21 / 2.22 |
| head: `timeout 30 python3 -I -B -m unittest discover -s tests -p test_pinned.py -v` | 9 PASS | 0.23 / 0.22 |
| head: `timeout 300 python3 -I -B -m unittest discover -s tests -p test_estimate.py -k CommandLine -v` | 12 PASS | 19.45 / 19.35 |
| head: `timeout 30 python3 -I -B -m unittest discover -s tests -p test_estimate.py -k test_padded_oracle_budget_and_large_budget -v` | 1 PASS | 0.45 / 0.45 |
| head: `timeout 30 python3 -I -B -m unittest discover -s tests -p test_output.py -v` | 2 PASS | 0.36 / 0.36 |
| head: `timeout 30 python3 -I -B -m unittest discover -s tests -p test_fail_fast.py -v` | 4 PASS | 0.38 / 0.38 |
| head: `timeout 30 cargo fmt --check` | PASS | 0.05 / 0.05 |
| head: `timeout 30 cargo clippy --offline --locked -j 4 --all-targets -- -D warnings` | PASS | 0.23 / 0.38 |
| head: `timeout 30 python3 -I -B scripts/quality_ratchet.py` | PASS, no regression | 0.65 / 0.65 |
| head: `timeout 30 git diff --check` | PASS | 0.00 / 0.00 |

The author's three evidence.json commands were repeated with the freshly rebuilt review binary (short class). The rung4-mini/superconducting diagnostic reproduced its expected failure (0.18 s wall / 0.18 s CPU); the supported B=1,000,000 inc8 oracle and published controlled action matched the author's entire parsed JSON (0.35 / 0.35 s and 0.32 / 0.31 s). The inc8 oracle's padded gate/time/peak/occupancy rows remain 1574000119 / 2854000199 / 13000101 / 37102231521012136; this is explicitly a supported fixture, not the full Grover program. Eight independent CLI probes passed their assertions for bound scope, all budget components, the 2^53 boundary, three invalid budgets, pending resource absence and raw/semantic digest separation.

Uncommitted exact argv/stdout/stderr/timing receipts: `.tmp/est-b8o-review/reruns.json`, `direct-evidence.json`, `independent-probes.json`. No full gate, sibling gate, source edit, bead write or bead export was performed. Merge still requires the orchestrator's full gate PASS on the reviewed implementation tree under standing rule 4.
