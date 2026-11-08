# Terminal recompute cleanup implementation review — round 1

Reviewed `d5df671..5227de58dfa02d31f703172e78b6a02387e3a9d8`
(`ad57863`, `3967f75`, `3dc0897`, `4516847`, `5227de5`) on
`job/est-e9a-impl`. Authority: the council-accepted, frozen
`docs/design/2026-11-08-recompute-cleanup-admissibility.md`, especially
§§2–3.2. Read the implementer brief, full progress and red/green receipts,
COMMON.md, T3CHILD.md, repository instructions, complete implementation/test
diff and all four historical rejected reviews. Reviewer: gpt-6.1-sol, fresh
review session. No production code or tests changed; no bead writes.

Disposition: REVISE

The seven historical witnesses and the reported generated family reproduce.
The composed Boolean/phase checker avoids the earlier blanket read bans.
However, fresh replacement construction conflates two source allocation
occurrences that reuse one descriptor, rejecting an admissible recompute.

## Numbered findings

1. **P1 — valid recompute fails when a released source name is allocated
   again** (`src/estimate.py:3619–3624`, `TerminalCleanups.materialize`).
   The builder scans every acquisition whose bundle intersects the plan's
   target bits. Source lowering deliberately reuses the same descriptor for
   separate equal-shaped lifetimes. Both acquisitions therefore enter each
   replacement prefix, and the fresh identity at line 3621 is identical for
   both: it contains the descriptor and carrier, but no allocation occurrence.
   The second acquire fails with `K27: double acquisition of a live allocation`.
   Selecting the first carrier, the second carrier, or both reproduces this.

   Minimal complete source:

   ```text
   perm_action @root () (x:wire in, z:wire in) () () ()
   ^entry():
   d = qalloc any 1
   cx x d
   cx x d
   qfree d
   d = qalloc any 1
   cx z d
   cx z d
   qfree d
   ```

   Build it with `tests/test_schedule.py`'s `make_object`, signature
   `{'abi':'0.9','tier':'q','kind':'perm_action','mut':[], 'in':[1,1],
   'mem':[],'args':[],'bounds':[]}` and `target()`. Obtain the base
   `effective_schedule` from `e.estimate(obj,t,'root',[],['0']*4)`; replace
   its entries with `[entry('cleanup',realisation='recompute')]`, assign
   `obj.sections['schedule']`, and repeat the estimate. A path selector for
   `entry:3` or `entry:7` alone also fails.

   Written reverse is exact: gates/time 4, peak 3, area 12. Independent
   scalar execution of the source and separately written literal K80
   replacements covers all four x/z bases in both directions (16
   executions): both are identity, every source and fresh release is clean.
   Each lifetime has its own exact CX pair, unchanged replay inputs, and
   an open window. Replacing both has eight gates, peak four, area
   `2*(1*3 + 3*4)=30`. Renaming only the second source lifetime to `b`
   succeeds, with exactly those resources; selecting one then gives six
   gates, peak four, area 21. This isolates occurrence identity from source
   semantics. The failure is neither pending mechanics nor a legitimate
   recompute refusal, and narrows the accepted definition's allocation
   lifetime capability. Bind materialization to each owned allocation
   occurrence and add a same-name lifetime regression; merely changing the
   diagnostic or allocating fresh scratch for unrelated occurrences does
   not establish the literal replacement. Orchestrator must file the P1
   bead; this review job is forbidden to write beads.

2. **P2 — generated coverage stops short of the definition's window
   events and lifetime occurrences** (`tests/recompute_witness.rs:437–472`).
   The generator exhausts at most three retained rows from `x y`, `cx x y`,
   `cx d y`, `x x`, in three gaps around one fixed two-CX lifetime. It reaches
   cancelling scratch reads and `x x; cx x y; x x` between inverses, without
   requiring a temporarily flipped read to equal its entry value. It cannot
   generate cells, §6.2 clause-3 action calls, phases, controls, joint or
   borrowed targets, intrinsic boundaries, or a second allocation occurrence.
   The last omission misses finding 1. The separate fifteen Python tests
   cover several of these mechanisms but do not supply an independent
   generated oracle for them. Extend generated coverage as mechanisms land;
   record the cell/action coverage under existing `bennett-estimate-e9a.1`
   and the repeated-lifetime regression with finding 1. This is a coverage
   limitation, not evidence that the current oracle shares the estimator's
   admissibility logic. No nit finding.

## Re-runs and evidence

All commands ran headless with DISPLAY, WAYLAND_DISPLAY,
DBUS_SESSION_BUS_ADDRESS and BROWSER unset, `PYTHONDONTWRITEBYTECODE=1`,
and job-local `TMPDIR=.tmp/est-e9a-impl-review/tmp` and
`CARGO_TARGET_DIR=.tmp/est-e9a-impl-review/target`. Hang guards use
`docs/hang-guards.md`'s short/moderate/long classes; every recorded run
finished without an UNKNOWN trip. Machine check: 64 CPUs, about 55.6 GiB
available; build width four. Wall/CPU below are seconds. No full push or
sibling gate ran.

| Exact command, from the worktree | Result | Wall / CPU |
|---|---|---|
| `timeout 300 cargo test --offline --locked -j4 --test recompute_witness -- --test-threads=1 --nocapture` | 13 pass, none ignored; 592 generated / 471 valid / 220 admit / 251 refuse / zero findings | 8.97 / 9.63 |
| `timeout 30 python3 -I -B -m unittest discover -s tests -p test_recompute.py -v` | 15 pass | 0.52 / 0.52 |
| `timeout 900 scripts/check` | 264 Python tests across four wrappers, 13 Rust witnesses/family, fmt, strict all-target clippy and shell syntax pass | 56.08 / 119.96 |
| `timeout 30 python3 -I -B scripts/quality_ratchet.py` | No regression | 0.69 / 0.70 |
| `python3 -I -B .tmp/est-e9a-impl-review/prepare_red.py`; `CARGO_MANIFEST_DIR="$PWD" rustc --edition 2024 --test .tmp/est-e9a-impl-review/red_witness.rs -o .tmp/est-e9a-impl-review/red_witness`; `timeout 300 .tmp/est-e9a-impl-review/red_witness --test-threads=1` | Reconstructed red: 7 pass / 5 fail, exit 101 as expected | 5.96 / 6.07 (test execution) |
| `timeout 300 python3 -I -B .tmp/est-e9a-impl-review/random_probe.py` | Seed 2654435769: 323 valid programs, 104 admit / 219 refuse, zero pending or mismatches | 2.19 / 2.23 |
| `timeout 30 python3 -I -B .tmp/est-e9a-impl-review/deferred_probe.py` | Cell-write and non-permutation action-read cases retain exact reverse; selected recompute reports pending/unestablished | 0.37 / 0.37 |
| `timeout 30 python3 -I -B .tmp/est-e9a-impl-review/reallocation_probe.py` | Reproduces finding 1 for three selectors; renamed controls and independent literal execution pass | 0.39 / 0.40 |

Each timed command used `/usr/bin/time -p`; receipts and review-only probe
sources remain under the owned `.tmp/est-e9a-impl-review/` directory.
`git diff --check d5df671..5227de5` passes. No implementation edits were
made to obtain counterexample behavior.

The red rerun compiles the activated tests from `ad57863` into the owned
scratch directory, loads `d5df671:src/estimate.py` into an in-memory module
in the Python bridge, and retains the original oracle and expectations.
All five failures quote
`source cleanup-pair recompute binding remains pending for this carrier`:
the pjj, tdf, w2b and cancelling-read admission tests, plus yak's diagnostic
test. No branch switch or tracked source/test change was needed.

The Rust family has no seed: enumeration is exhaustive within its stated
grammar. For the requested different-seed check, the independent review
probe uses seed 2654435769 and up to six retained rows plus matched flip/read
intervals. It extends coverage to T/TDG, S/SDG, controlled scratch reads,
controlled phases and controlled computing sequences. Its direct integer
bit/phase executor compares source and literal candidate on all sixteen
interface bases, forward and inverse, including phase modulo eight and
dirty release observations. It imports no estimator proof, version or
admissibility helper. Object/schedule construction alone uses existing
test builders. This extension retains the one-lifetime limitation; the
separate repeated-lifetime probe is what reveals finding 1.

## Definition checks and historical witnesses

The frozen definition's diff is empty. A byte-prefix comparison also
confirms that the original live Rust interpreter, bridge, fixed literal
expectations and assertions are unchanged; only the five ignore attributes
are removed, followed by the new generated family. The live oracle parses
and executes X/CX directly, records release values and compares complete
basis results in both directions. It neither calls estimator admissibility
code nor imposes the rejected `reads_current` condition. For its phase-free
grammar, clean all-basis equality establishes superposition/reference
equality.

`CleanupSemantics` compares composed Boolean maps and phase polynomials
modulo eight, retaining the constant term. This includes global phase under
effective controls. Intermediate differences only locate a diagnostic;
they do not themselves trigger semantic refusal. The per-row protected
basis-write checks in `replay_window` implement §3.1's separate interval
obligation. Cancelling scratch reads and cancelling diagonal phases pass;
uncancelled relative and controlled global phase fail. No additional
obligation-3 narrowing was found in those paths. Finding 1 occurs afterward
in replacement construction.

| Witness | Reproduced verdict | Gates/time / peak / area, if admitted |
|---|---|---|
| pjj: disjoint between inverses | Admit | 8 / 5 / 37 |
| pjj: disjoint before release | Admit | 8 / 5 / 37 |
| yak: scratch read | Refuse, conflicting `entry:4` | — |
| yak: unrestored replay input | Refuse, conflicting `entry:5` | — |
| tdf: restored input | Admit | 9 / 4 / 32 |
| w2b: read of temporarily flipped input | Admit | 10 / 5 / 45 |
| Cancelling scratch reads | Admit | 9 / 5 / 41 |

Hand check: pjj retains two computing CXs and one X, at occupancy four,
then emits five replacement CXs at occupancy five: gates/time eight,
peak five, area `3*4+5*5=37`. Restored input retains two computing CXs
and two input Xs at occupancy three, then five replacement CXs at
occupancy four: gates/time nine, peak four, area `4*3+5*4=32`.
Allocation/release time is zero on the pinned ideal target. Actual operand
traces are independently executed by the Rust tests in both directions.
The four historical failures do not recur for their original witnesses.

All explicit `refuse()` paths name a reason and conflicting point and
contain no pending label. Opaque/cell/control-flow/non-monomial proof
mechanisms and exhausted proof allowances remain pending rather than
receiving invented exact costs. Focused tests confirm reverse support for
unavailable mechanisms. Additional direct cell-write and clause-3 action
read probes likewise produce `pending/unestablished: exact computing
occurrences ... unestablished`, preserving exact reverse. Their definitive
window verdicts remain deferred; they are not generated coverage. Finding
1 is an exception to the claimed honest availability behavior: a sound
replacement instead reaches a false K27 contract error.

Open work: `bennett-estimate-e9a`, `bennett-estimate-e9a.1` and the existing
spec clarification `bennett-isa-spec-nuk`. The orchestrator must record
finding 1 as a P1 bead and attach finding 2's coverage requirements. Review
is complete; no follow-on work is taken under the maintainer's stop
direction.
