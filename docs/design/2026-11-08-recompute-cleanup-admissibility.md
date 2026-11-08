# Terminal recompute cleanup: admissibility definition and execution witnesses

Status: council candidate; steps (1) and (2) of `bennett-estimate-e9a` only.
No production admissibility rule is implemented by this change. The existing
reviewed reverse path remains the running estimator. Council disposition must
precede implementation; recompute remains a promised capability.

## 1. Pinned authority

The authority is ISA **0.9**, `bennett-isa-spec` commit
`fd626d37aba1f719c3b7b2059be46cbfaf462886`,
`spec/Bennett-ISA-Spec-0.9.md`, as pinned by this repository's `gate.toml`.
Its SHA-256 is
`bbd887c7841f4eed40f7b3518270a8f2cf781204c14ac4cc3eabca5c5b4b8c3b`.
The excerpts below are verbatim from that pinned file, including its section
and dependency identifiers. The local pinned cache supplies the text; no
sibling implementation code supplies the definition or simulator.

### 1.1 ISA §5.3: occurrence matching and restored versions

> Two operations form a **matched pair** iff the second is the §5.3
> adjoint of the first, with the same callee(s) (the pair exchanged for
> `qinplace`), identical classical argument values and token identities
> and tuples, the same operand wires with the first's read-only input
> versions and produced target versions current at the second, and equal
> effective control sets including the versions of their wires; order and
> repetition in predicate stacks are irrelevant. [deps: ISA-2-P10, ISA-3.3-P3, ISA-4.5-P5, ISA-4.7, ISA-5.3-P4, ISA-5.4]
> A matched inverse restores preceding wire-version bindings for
> subsequent matching only when the §6.2 cleanup conditions hold; matching
> alone does not discharge an outstanding-reader or phase obligation, and
> a cell write always advances its cell version even when its value is
> restored. [deps: ISA-3.3-P3, ISA-6.1-P1, ISA-6.2]

### 1.2 ISA §6.2: window and obligations

> A perm value g with set S is **in its window** from its computation
> until the first of: a non-diagonal gate on a wire in S or in g; a version
> advance of a cell in S; a non-permutation action call touching a wire in
> S; a permutation change to a wire in S not undone before g's cleanup.
> A permutation change to a wire of S is **undone** when it and its
> undoing form a matched pair (§5.3), and every intervening operation
> leaves the computational-basis values of S and g unchanged; a cell
> version advance still closes the window even if its value is restored.
> [deps: ISA-5.3, ISA-6.1-P1, ISA-14.2]
> Each cleanup is bound to its exact computing sequence and requires the
> external input versions that sequence read (the versions in S for a
> perm value), and the version of g it produced, to be current; g's
> pre-computation target versions are not required to be current.
> [deps: ISA-3.3-P3, ISA-6.1-P1]
> A cleanup runs under the same effective control set, at the same wire
> versions, as its computing sequence. [deps: ISA-2-P10, ISA-3.5, ISA-5.3-P5]
> Every perm value MUST be
> cleaned within its window and before its region exits; otherwise the
> region is **ill-formed** (closed-window measurement-based cleanup is not
> admitted). `other` values are released only by the adjoint of their
> computing sequence, and only while no other live value, interface wire
> or outstanding diagonal phase depends on them, as defined in §6.1.
> [deps: ISA-5.3, ISA-6.1, ISA-6.4]

### 1.3 ISA §6.4: permitted unitary realisations

Excerpt: the remainder of §6.4's paragraph is omitted.

> Every cleanup in this version is **unitary**: realisation `reverse`
> (the adjoint of g's exact computing sequence, §6.2) or `recompute`
> (legal for `perm` values only: recompute g into a fresh clean bundle by
> the same sequence, `qxor` it into g's wires, uncompute the fresh bundle
> by the adjoint).

### 1.4 ISA §11 K81: source cleanup-pair partition

> **Source cleanup-pair partition (K81).** Consumers MUST form the following
> partition from the source before K65 selection and K80 expansion. Match
> source operation occurrences by §5.3 and §6.2, against the most recent
> still-current computing occurrence on all of the operation's outputs;
> matching restores its captured entry versions. A joint multi-output
> operation and its inverse are indivisible. This is occurrence/version
> matching, not equality of the composed unitary alone.
>
> An intrinsic `quncopy`, `qunload` or `lift.oracle_uncall` pairs only with
> its matching `qcopy`, `qload` or `lift.oracle_call`, respectively. Its
> computing sequence does not absorb subsequent changes to the produced
> targets, and its cleanup consists only of that intrinsic instruction.
> For `qfree` or `qreturn`, instead coalesce the maximal terminal chain of
> matched source inverses restoring the released lifetime to its allocation
> or borrow entry, together with that release. Terminal means that each
> restored version is retained until the next inverse in the chain or the
> release; an intervening new computation on that lifetime breaks the
> chain. Rows acting only on disjoint values do not break it and are not
> included. Intrinsic cleanup instructions remain boundaries and are never
> absorbed. A joint inverse restoring several released lifetimes belongs
> to the first such release in source execution order; later releases do
> not own it again. Each remaining matched adjoint-call or oracle-call
> inverse has its own K65 carrier. A primitive inverse outside a
> release-ended chain has no separate K65 carrier. Thus every explicit
> cleanup inverse occurrence has exactly one owner; pair formation neither
> requires textual adjacency nor depends on the selected realisation.
> Use instantiated source order, including §4.6 controls and iterations,
> without entering semantic callees or K64 support subtrees. K65's private
> constructor cleanups remain excluded, and §6's validity conditions still
> apply; this partition adds no source-program restriction.

### 1.5 ISA §11 K80: replacement trace and leaf ownership

> **Cleanup leaf ownership (K80).** For `reverse`, emitted leaves retain the
> written cleanup's source points and per-point ordinal and semantic-call
> occurrence spaces, including the terminating release. For `recompute`,
> consumers MUST assign the entire replacement's caller-level leaves and
> call edges to the carrier's point and coordinates. The original
> computation is unchanged; replaced inverse rows emit nothing. Materialise
> fresh computation, XOR, fresh uncomputation and releases in §6.4 order;
> number caller leaves contiguously from zero, excluding callee subtrees,
> and number semantic-call occurrences independently from zero (§11.1/K63).
> Fresh uncomputation has separate occurrences from fresh computation;
> neither reuses the original computation's edges or scratch identities.
> Callees retain their own source points, nested chains and ordinal/call
> spaces under these fresh edges. Internal replay does not import the
> original rows' source-qloop coordinates. Raw inverse traversal retains
> forward paths, leaf ordinals, call occurrences and scratch identities;
> step/phase follows §11 and source-adjoint formation remains K62. The carrier's ordinal 0 belongs only to
> cleanup-kind matching; it does not consume emitted-leaf ordinal 0.
> K64's oracle support partition is unchanged.

K65 in §11 additionally makes whole-cleanup selection subject to §6's
validity conditions. K80's multirow witness gives the literal replacement
used here: allocate fresh `u`; `cx x u`; `cx z u`; `cx u d`;
`cx z u`; `cx x u`; release `u`; release `d`. Its caller ordinals are
0 through 7 at the release carrier. The two original computing CXs remain
at their original source points.

## 2. Objects being decided

This note covers terminal release-ended carriers only; non-terminal adjoint-call/oracle-call carriers and K81's independent-call-pair pre-call-history replay and target restoration require separate treatment.

Let `G` be the released lifetime's wires, `C` its exact captured computing
sequence, and `S` the external wire/cell versions read by that sequence,
including effective controls. Allocation/borrow entry, produced target
versions, and captured pre-computation versions are distinct objects.
A joint multi-output computation is one indivisible occurrence; its inputs,
targets, and restored versions must be tracked jointly.
For CX, the control is a read whose basis value and wire version are unchanged; §6.1's permutation-gate row updates the target and includes controls in its dependencies.

Form the K81 partition in instantiated source execution order, before
choosing a cleanup realisation. A release owns the maximal terminal chain
of matched inverses restoring its allocation/borrow entry and the release
itself. Terminal describes retention of restored versions, not proximity
in text. An intrinsic cleanup is a boundary. A joint inverse belongs to
the first release, once; a later release cannot claim it again.
Semantic callee bodies and K64 support subtrees are outside this source
partition. Empty inverse chains retain their K65 carrier.

For a proposed recompute, erase only that carrier's owned inverse
occurrences and put the §6.4 fresh-compute/XOR/uncompute/releases at its
carrier. Every other source operation remains once, at its source position.
The relevant question is whether this particular replacement is legal;
a valid original source can have an invalid recompute choice.

## 3. Derived admissibility rule

A terminal replacement is admissible only when all three obligations hold:

1. **Occurrence and ownership:** K81 and §5.3 establish the exact matched
   occurrences and current versions. Matching must use the same wires,
   callee, classical arguments, token identities/tuples, and effective
   controls. Equality of final bits or of a composed unitary cannot replace
   this occurrence/version obligation. Coalescing and ownership are
   independent of the selected realisation.
2. **Window and replay inputs:** `g` has `perm` provenance; §6.2's window is
   open, the captured external inputs and produced `g` version are current
   at their respective matching/replay points, and effective control sets
   and versions agree. The candidate's replay uses those captured inputs,
   rather than whatever happens to occupy their wires. A dependency wire
   may change and recover its captured version through a qualifying matched
   permutation pair, as defined below. A cell write advances its version
   even if its bits are later restored. The other window-closing events
   in §6.2 retain their stated force. Restoring the pre-computation target
   version before replay is not required.
3. **Composed semantic preservation:** following §6.1's composed-`M`
   dependence criterion and the requirement that the realised unitary
   equal §5.3's reference unitary, the composition of the retained
   operations in candidate order together with the literal K80 replacement
   must have the same full-domain effect on the joint state as the original
   trace, including relative and global phase under control and arbitrary
   external references. The replacement must restore/release the intended
   targets, restore borrowed entry states, and release fresh scratch clean.
   Cancellations within the retained sequence count; identical intermediate
   read values or individual in-context effects are not required.

Per-row commutation/effect checks and §6.1's dependency-set non-dependence test are sufficient proof methods where applicable, not necessary admission conditions; the general checker must establish the composed equality.

These are contract obligations, not an implementation of a new predicate.
For the seven fixed, phase-free X/CX witnesses, full truth-table execution
checks obligation 3 exactly. A future general algorithm must retain
obligations 1 and 2 even when two composed truth tables happen to agree.
It must also handle the contract's joint lifetimes, controls, cells and
intrinsic boundaries; these seven programs do not exhaust those cases.

### 3.1 Basis preservation during a temporary dependency change

Spec gap (council B2): §6.2 clause 1's "non-diagonal" overlaps clause 4's permutation changes; pending spec-owner clarification, this note reads clause 1 as non-diagonal, non-permutation, following §6.1's separate permutation-gate and non-diagonal-gate provenance rows, and applies clause 4 to permutation changes of `S`.

Let `F` change a dependency wire and let `F†` be its proposed matched undo,
before `g`'s cleanup. Between those endpoints every intervening operation
must preserve the computational-basis values of **both `S` and `g`**.
Reads are allowed subject to obligation 2's window-closing events, including a non-permutation action call touching `S` (§6.2 clause 3), even if it only reads and preserves basis values.
Writes to `S` or `g` are forbidden between flip and
undo, apart from the designated endpoints themselves. Here a write means
a basis-changing operation or a cell-version advance; diagonal gates that
preserve basis values are not forbidden merely because they have operands.
Their phases remain part of the declared semantics under §6.3.
The designated `F`/`F†` endpoints themselves write `S`; §6.2 excludes those endpoints from "intervening" operations.

Thus `x x; cx x y; x x` qualifies when `y` is outside `S ∪ G`:
the middle CX reads the temporarily flipped value of `x`, writes only
`y`, and leaves `S` and `g` unchanged. The undo restores the exact captured
wire binding. Requiring the read to equal the region-entry value adds a
restriction absent from §6.2. Conversely, a write to a protected value in
the interval cannot be excused by observing net identity at the end of the
whole program. The matched-pair and every-intervening-operation conditions
still apply, including control versions.

A read of a dependency wire and a read of the postponed cleanup target
are different cases. The former sees the same temporary input in both
traces in the restored-read witness. The latter sees `x` versus `x XOR z`
in the unsafe scratch-read witness. Reads are not globally forbidden or
globally sufficient for safe movement.

### 3.2 Source validity and implementation availability

The K81 partition **adds no source-program restriction**. In particular,
none of textual non-adjacency, temporary matched input writes, or reads of
those temporary inputs invalidates an otherwise valid source program.
The two unsafe witnesses below remain valid under their written reverse
cleanup; only the requested terminal recompute is wrong. An unavailable
implementation mechanism must be reported as pending, rather than called
a source contract violation or silently assigned exact costs. This is a
deferral of mechanics, not removal of the promised capability.

## 4. Four rejected rounds, seven literal programs

Each `.bisa` fixture contains the complete `perm_action @root` and all
source instructions. The corresponding `.recompute.bisa` is a separately
written literal K80 candidate trace, including fresh allocation and both
releases. In every program the common computation is
`d = qalloc any 1; cx x d; cx z d`. The table lists the rest of the source;
semicolons separate distinct instruction rows. Counts cover every interface
basis, in each of forward and raw inverse traversal.
Resource totals below use the gate-pinned `ideal-all-to-all` target (unit gate time and data occupancy rate; zero allocation/release time).

| Review / witness | Source tail after computation | Recompute verdict | Executed evidence |
|---|---|---|---|
| r1 / pjj, between inverses | `cx z d; x y; cx x d; qfree d` | Admit | Both traces map `y → y XOR 1`; 8/8 agree, all scratch clean |
| r1 / pjj, before release | `cx z d; cx x d; x y; qfree d` | Admit | Same 8/8 agreement and clean releases |
| r2 / yak, scratch read | `cx z d; cx d y; cx x d; qfree d` | Refuse this recompute | Reverse: `y → y XOR x`; candidate: `y → y XOR x XOR z`; 4/8 outputs differ, scratch clean |
| r2 / yak, unrestored input | `cx z d; cx x d; x x; qfree d` | Refuse this recompute | Both flip `x`; candidate attempts dirty release `d=1` on 4/4 inputs |
| r3 / tdf | `cx z d; x x; x x; cx x d; qfree d` | Admit | Both preserve `x,z`; 4/4 agree, all scratch clean |
| r4 / w2b | `cx z d; x x; cx x y; x x; cx x d; qfree d` | Admit | Both map `y → y XOR NOT x`, preserve `x,z`; 8/8 agree, all scratch clean |
| Cancelling scratch reads | `cx z d; cx d y; cx d y; cx x d; qfree d` | Admit | Both are identity on `x,z,y`; 8/8 agree, all scratch clean |

### 4.1 Round 1: adjacency rejected pjj

[Review r1](../reviews/2026-11-06-estimate-main-r1.md) reviewed original
checkpoints `5062ee2` and `989dd04` at `c50c662`. Their terminal-chain
availability check required inverse rows to be contiguous with release.
Both pjj placements violate that check while satisfying K81: `x y` changes
neither replay inputs nor `d`. It stays once in source order and does not
belong to the cleanup chain. Removing it or absorbing it into replay would
also be wrong. Correct recompute owns points `entry:3,5,6` for the first
placement and `entry:3,4,6` for the second. Hand-derived resources for each
are gates/time 8, peak 5, qubit-time 37 (`3*4 + 5*5 = 37`).

### 4.2 Round 2: removing adjacency alone admitted yak

[Review r2](../reviews/2026-11-06-estimate-main-r2.md) reviewed `496f3aa`
and its checkpoint `9f8869b`. That fix removed the contiguous requirement
without establishing retained-operation or replay-input validity.
In the scratch-read program the delayed inverse changes what `cx d y`
reads: obligation 3 fails. For `x=0,z=1,y=0`, reverse returns `y=0`,
while the candidate returns `y=1`; its single scratch read does not cancel elsewhere in the composition. In the second program the unpaired
`x x` makes the captured replay input unavailable: obligation 2 fails,
and replay leaves `d=1` for every input. The conflicting source points
are respectively `entry:4` and `entry:5`. Both originals execute cleanly
with reverse cleanup; rejecting the source itself would narrow scope.

### 4.3 Round 3: blanket input-write rejection excluded tdf

[Review r3](../reviews/2026-11-07-estimate-main-r3.md) reviewed
`ecc38f7`, `9a4e7a8`, and `54f98f9`. The new obstruction rule correctly
caught both yak cases but rejected every intervening input write.
The two adjacent `x x` operations are a qualifying matched pair. There is
no intervening operation, and `x`'s captured version is restored before
replay. Therefore obligation 2 holds, and execution verifies obligation 3.
Correct owned points are `entry:3,6,7`; gates/time 9, peak 4, qubit-time 32 (`4*3 + 5*4 = 32`).

### 4.4 Round 4: forbidding reads of changed inputs excluded w2b

[Review r4](../reviews/2026-11-07-estimate-main-r4.md) reviewed
`eeefd06`, `916931a`, and `7fef698`. The pending-write guard allowed the
tdf pair but rejected a read of its temporarily changed input. Its
144-program test had independent scalar arithmetic, then combined it
with `reads_current`, requiring observed input reads to equal region-entry
values. That extra oracle condition repeated the narrowing.

Here `cx x y` between the X pair reads `NOT x` and writes only `y`.
It preserves the computational-basis values of `S={x,z}` and `g=d`;
the second X restores `x`'s captured binding. It must retain that
observable `NOT x` read in both traces. §3.1 therefore admits the pair,
and literal execution establishes the stated result without checking
any read against a region-entry value. Correct owned points are
`entry:3,7,8`; gates/time 10, peak 5, qubit-time 45 (`5*4 + 5*5 = 45`).

### 4.5 Cancelling scratch reads: composed preservation

Sol SOL-1 and Muse B1 propose exactly the same program, including row
order, so one fixture pair covers both. The source's two `cx d y` reads
observe `d=x`; the candidate's observe `d=x XOR z`. Each pair cancels,
giving identity on `x,z,y` for all eight interface bases in both directions,
with `d` and fresh `u` released clean. At `x=0,z=1,y=0`, intermediate `y`
values are `[0,0]` in the source and `[1,0]` in the candidate; obligation 3
allows this difference because the composed effect agrees. Obligations
1–2 still hold: neither read changes `S={x,z}` or `g=d`, replay inputs
remain current, and the source partition is unchanged. The carrier at
`entry:7` owns `entry:3,6,7`; retained readers at `entry:4,5` stay once in
source order. Hand-derived gates/time are 9, peak 5, qubit-time 41
(`4*4 + 5*5 = 41`). The fixture's
[notes](../../tests/fixtures/recompute_witness/cancelling-scratch-reads.md)
derive the identity, clean releases, inverse traversal and resource totals.

## 5. Executable evidence and limits

`tests/recompute_witness.rs` has seven live tests: six execute the source
and literal candidate programs, and one executes the current estimator's
actual reverse leaves for all seven sources. The interpreter supports only
one-bit X, CX, clean allocation, and release observations; unsupported
operations, nonexistent wires, duplicate live allocations, or unreleased
scratch fail loudly. The expected interface maps in §4 are hand-derived.
The exact interpreter and six literal-execution tests use no dependency
sets, matching history, obstruction rule, current-input/read predicate,
or estimator imports. They execute concrete operands and record each
release value. A nonzero release is evidence
of an invalid candidate, not a successful ISA `qfree` execution; no clean
result is inferred from discarding that value.

All 48 basis assignments across the seven fixtures are checked in both
traversal directions for both source and candidate: 192 exact executions.
These X/CX gates have basis phase +1, so complete interface-basis agreement
with clean scratch proves equality on arbitrary superpositions and
external references for these fixtures. This is not a claim about
non-permutation gates, uncancelled phases, general cells or arbitrary
source matching. The two negative candidates are explicitly checked for
the same 4/8 and 4/4 failures in both directions.

The live estimator bridge imports this repo's existing object/schedule
builders, emits the actual ledger operands in each direction, and feeds
those operands to the same exact interpreter: 96 emitted-trace executions,
each compared with a freshly executed source reference.
It reads its target through the existing gate-pin resolver, including
`BENNETT_GATE_LAYOUT`; it never accesses an unpinned sibling. The independent
source/candidate oracle half needs no sibling binary or implementation.
The bridge strips trailing whitespace with `rstrip()` before the existing
object builder, which appends its own terminator.

Five additional Rust tests assert the future estimator verdicts and cite
§§4.1–4.5 in their explicit `#[ignore = "..."]` reasons. Accepted cases
must match the executed source on every basis in both directions, release
all scratch clean, and produce the hand-derived resource totals above.
Refusals must identify recompute and the conflicting source point; a
generic pending-mechanics error does not satisfy them. These tests are
intentionally ignored until council approval and implementation. The live
oracle assertions are never ignored.

Focused verification (headless; job-local TMPDIR/CARGO_TARGET_DIR):

```sh
cargo test --offline --locked --test recompute_witness -- --test-threads=1
```

Result: **7 passed, 5 explicitly ignored**. Running the five future tests
with `--ignored` separately produces five expected failures on today's
pending-mechanics path; those assertions are not satisfied by a generic
unsupported error. The job's local launch wrapper applies its measured
short-command hang-guard class, records wall and CPU seconds, and reports
a trip as UNKNOWN/124.
No full repository or sibling gate is part of this design task. The
orchestrator owns full gating, the definition council, and a later
implementation; `bennett-estimate-e9a` remains open for those steps.
