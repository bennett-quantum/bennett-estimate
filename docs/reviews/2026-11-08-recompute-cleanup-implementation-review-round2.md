# Terminal recompute cleanup implementation review — round 2

Reviewed repair `51c3434..98ed8ec4118dd6130c0c8467a1fceb6c7d63ee04`
on `job/est-e9a-impl`, together with the scoped baseline and frozen-definition
checks over `d5df671..98ed8ec`. Reviewer: gpt-6.1-sol, fresh review session.
Read the brief, COMMON.md, T3CHILD.md, CLAUDE.md, AGENTS.md, implementer
PROGRESS.md, repair red/green receipts, round-1 review, accepted definition,
repair diff and relevant occurrence, window, composed-proof and materialisation
code. No production code, tests or beads changed.

Disposition: ACCEPT with P2 beads

The reused-allocation-name counterexample is repaired for first-only,
second-only and both-carrier selection. Independent execution and exact
resource assertions pass. No new P0/P1 finding or narrowing refusal was found.
The existing P2 `bennett-estimate-mxc` remains outside this repair round.

## Re-runs

Commands ran from
`/home/tobias/Projects/bennett-workspace/bennett-estimate-job-est-e9a-impl`,
with DISPLAY, WAYLAND_DISPLAY, DBUS_SESSION_BUS_ADDRESS and BROWSER unset,
`TMPDIR=$PWD/.tmp/est-e9a-impl-review2/tmp`, and
`CARGO_TARGET_DIR=$PWD/.tmp/est-e9a-impl-review2/target`. Python commands and
bridges used `-I -B`. The machine had 64 logical CPUs, approximately 53 GiB
available and load 7.25 at inspection. Build widths follow
`docs/hang-guards.md`'s maximum four; the existing check script uses three.
The table's short/moderate/long classes supply the guards below. Every timed
command used `/usr/bin/time -p`; wall and user+system CPU are seconds.
No guard tripped. No full push gate or sibling gate ran.

| Exact command | Result | Wall / CPU |
| --- | --- | --- |
| `timeout 300 .tmp/est-e9a-impl-review2/red_witness --test-threads=1` | Pre-repair reconstruction: 14 pass, 3 expected failures, exit 101; all three failures are K27 double acquisition | 12.79 / 13.02 |
| `timeout 300 cargo test --offline --locked -j4 --test recompute_witness -- --test-threads=1 --nocapture` | 17 pass, zero fail/ignored; generated family: 592 generated, 471 valid, 220 admit, 251 refuse, zero findings | 10.47 / 11.19 |
| `timeout 300 python3 -I -B .tmp/est-e9a-impl-review2/random_probe.py` | Original seed 2654435769: 323 valid, 104 admit, 219 refuse; zero mismatches/pending | 2.59 / 2.63 |
| `timeout 300 python3 -I -B .tmp/est-e9a-impl-review2/random_probe_second.py` | Second seed 608135816: 323 valid, 85 admit, 238 refuse; zero mismatches/pending | 2.46 / 2.50 |
| `timeout 900 scripts/check` | 264 Python tests across four wrappers, 17 Rust witness tests, formatting, strict all-target Clippy and shell syntax PASS | 62.18 / 129.44 |
| `timeout 30 python3 -I -B scripts/quality_ratchet.py` | No regression, exit 0 | 0.70 / 0.70 |
| `python3 -I -B .tmp/est-e9a-impl-review2/verify_invariants.py` | Definition, original oracle/fixtures, scoped baseline and diff checks PASS | — |

Receipts and review-only harnesses remain in
`.tmp/est-e9a-impl-review2/`. The red harness copies the current Rust
module into that directory, resolves fixture includes to the worktree and
injects `git show 51c3434:src/estimate.py` into the Python bridges as an
in-memory module. It preserves the independent interpreter and all test
expectations. Compilation used
`CARGO_MANIFEST_DIR="$PWD" rustc --edition 2024 --test .tmp/est-e9a-impl-review2/red_witness.rs -o .tmp/est-e9a-impl-review2/red_witness`.
No tracked file or branch switch was needed.

The original seeded probe is a byte-for-byte copy of round 1's probe; the
second changes only its seed. Its concrete bit/phase executor imports no
estimator proof helper. It compares source and literal candidate on all
sixteen interface bases, forward and inverse, including phase modulo eight
and release observations. The generated programs include cancelling
scratch reads, matched flip/read intervals, T/TDG, S/SDG, controlled reads,
controlled phases and controlled computing sequences.

## Numbered findings

1. **Resolved P1 — `bennett-estimate-cfb`: source allocation occurrence
   now determines fresh scratch.** `TerminalCleanups.materialize` reads
   each target bit's captured entry version at its carrier. `CleanupVersions`
   assigns allocation row `i` entry version `-(i+1)`, so decoding
   `-entry-1` selects that exact acquisition. Deduplication allocates one
   fresh bundle per occurrence, and fresh identity now includes the row
   index. It no longer collects every acquisition sharing the descriptor.

   The round-1 witness is present verbatim as
   `tests/fixtures/recompute_witness/reused-lifetime.bisa`: two successive
   lifetimes named `d`, each with its own self-cancelling CX pair.
   The tests select `entry:3`, `entry:7`, both and written reverse.
   Ownership remains exactly `[entry:2,entry:3]` and
   `[entry:6,entry:7]`.

   The unchanged Rust interpreter independently executes the source,
   separately written first/second/both literal replacements and actual
   emitted forward/raw-inverse operands. All four x/z bases give identity
   in both directions; every source and fresh release is clean, with the
   exact release count checked. Hand derivation: reverse has four unit
   gates at occupancy three, hence gates=time 4, peak 3, area 12.
   A replaced lifetime retains one CX at occupancy three and emits three
   at occupancy four, costing area `3+3*4=15`. One replacement therefore
   has gates=time 6, peak 4, area 21; two have gates=time 8, peak 4,
   area 30. The estimator asserts precisely these values.

   The repair changes no `replay_window`, `composed` or `refuse`
   logic and adds no per-row semantic admission condition. Its entry
   check reports unavailable local allocation evidence as
   pending/unestablished, retaining the existing materialisation
   requirement that all replay outputs have locally allocated target
   bundles. A supported local acquisition always supplies a negative
   entry version. Interface/enclosing entries without that evidence
   already lacked the fresh-target mapping needed by the old builder.
   The repaired same-name lifetimes now reach the intended replacement,
   rather than a false source-contract error.

2. **Existing P2 — `bennett-estimate-mxc` remains a coverage limitation.**
   The fixed repeated-lifetime regression closes the discovered
   counterexample. The generated family still lacks the broader cell,
   action-call, joint/borrowed-target and intrinsic-boundary coverage
   described in round 1. This repair neither claims that coverage nor
   weakens the oracle to compensate. No new bead or repair round is
   requested; retain mxc and the existing deferred-mechanism work under
   `bennett-estimate-e9a.1`. No nit finding.

## Frozen authority, oracle and baseline receipts

`git diff d5df671..98ed8ec -- docs/design/2026-11-08-recompute-cleanup-admissibility.md`
is empty. Direct byte comparison against both revisions and the working
file passes; note SHA-256:
`932a00b9f5b7f2c84eba81e492aba5f470978967c0a3451dea78a837757e28ff`.

The original `d5df671` Rust module is an identical byte prefix after
removing exactly its five future-test ignore attributes. The entire
20,529-byte round-1 module prefix is unchanged by the repair. All fifteen
original fixture/note files are byte-identical. The live interpreter
executes X/CX operands and records dirty release values directly; its
assertions impose no current-read predicate and use no estimator
admissibility machinery. Full basis equality with clean releases is
sufficient for these phase-free permutation fixtures, including
superpositions and external references.

`git diff d5df671..98ed8ec -- docs/quality.md` was inspected and its
baseline parsed independently. Only `src/estimate.py` and
`tests/test_recompute.py` have changed baseline values; every other file
row and all non-file baseline data are unchanged. The identical
`tests/test_pinned.py` row merely moves past `tests/test_phases.py`.
Within `51c3434..98ed8ec`, only the source row changes: complexity +4,
one method-length allowance 17→21, unchanged wrapper allowance.
`git diff --check d5df671..98ed8ec` passes.

Review complete. Existing open work remains `bennett-estimate-mxc`,
`bennett-estimate-e9a`, `bennett-estimate-e9a.1` and
`bennett-isa-spec-nuk`; none is newly introduced by this repair.
The orchestrator owns its same-head gate and landing. No follow-on work
was taken.
