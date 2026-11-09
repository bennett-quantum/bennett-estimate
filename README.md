# bennett-estimate

Resource estimation from ISA objects, certificates and target descriptions, without materialising gates.

Partial independent implementation of published ISA 0.9. See [requirements and
coverage](docs/PLAN.md) before relying on an estimate.
Current ecosystem handoff: [bennett/HANDOFF.md](../bennett/HANDOFF.md).
The remaining source, scheduling and verification work is tracked in Beads
under `bennett-estimate-bph`; the complete requested estimator is not yet delivered.

Build with Rust and Python 3.11 or newer (standard library only):

```sh
cargo build --offline --locked -j3
target_data=.tmp/gate/cache/bennett-targets@d2b0813b262d/bennett-targets/targets/ideal-quantum-circuit.json
target/debug/bennett-estimate tests/fixtures/example3.bisa \
  --target "$target_data"
target/debug/bennett-estimate tests/fixtures/example1.bisa \
  --target "$target_data" \
  --region inc8 --budget 1048576,0,0,0 --params '[]'
```

The `ideal-quantum-circuit` target describes an ideal quantum circuit with ideal logical qubits, implementing the standard quantum circuit model.

The CLI writes one deterministic JSON object. Invalid input produces a
diagnostic on stderr, nonzero exit status and empty stdout. A request affected
by a filed contract gap instead emits a `pending evidence` JSON report with
its request bindings and contract code, no resource rows, and exit status 3. `--params` is the complete K13 argument
array, inline or `@file`. Integer arguments are unsigned decimal **strings**,
f64 arguments are binary64 hex bit patterns, and tokens are four-string tuples.
No missing argument becomes zero. `--region` is required for multiple entries.
Oracle and token-taking entries require `--budget B,heap,stack,depth`,
including `--budget 0,0,0,0` when zero is intended. Token-free action and CC/R
entries retain a zero invocation tuple. The variant defaults to `forward` and
inherited control count to zero. All bindings appear in the result.

Consumer reports also expose `target` (the target filename stem),
`object_sha256` (SHA-256 of the exact input file bytes), `budget` (named
`steps`, `heap`, `stack`, `depth` components), and `padded` (the resource rows
for the stated invocation and realisation). These supplement the existing
ISA bindings: `object_hash` excludes schedule, certificate and coverage
sections, whereas `object_sha256` includes every byte. Budget components
below 2^53 are JSON numbers; larger components are decimal strings so their
integer bits survive JSON canonicalisation. `padded` preserves the report's
`exact` or conditional `bound` label; it does not establish correctness or
structure recovery. For an oracle, both B-step passes contribute to the cost,
including inactive rows. A pending-evidence report has request bindings and
exit status 3, with no `padded` or resource rows. Full option names and canonical
LF input files are required.

`--token-aliases '[0,0]'` supplies the published K91 equality partition.
Oracle contexts list their primary token followed by token arguments; actions
and CC/R entries list only token arguments. Equal labels require equal tuples;
distinct labels preserve distinct identities even when tuples agree. Nested
calls, fixed bindings, captures and reversal retain those identities. This
additive feature is pinned separately in SPEC_VERSIONS.toml and remains partial:
strict rejection of every legacy token request and complete certificate contexts
still require implementation. Legacy requests retain the base pinned profile.

`--epsilon` accepts exact decimal accuracy text. Default shares use exact
fractions, including nonterminating values such as 1/30. Matching action and
supported oracle schedules are consumed verbatim, with per-kind selector
resolution, native/scheme choices, rational start times, class capacity,
occupancy, placements and topology checks.

`exact_resources` stores reduced arbitrary-precision rational values.
`resources` contains the K12 upward 34-significant-digit decimal display and
escaped class keys, including zero rows for unused classes. `exact` labels the
resource calculation for the stated realisation; it does not certify
program correctness, optimality, or structure recovery. A
`--classical-step-bound N` report instead labels a **conditional** upper bound
and states the termination assumption. It contains `rational_upper_bounds`,
never a fabricated exact cost. This option applies to purely classical objects.

K86 `gates[].realisation_model` metadata is accepted and included in the
target hash. The estimator reconstructs costs; it does not check phase,
unitarity or accuracy of those models. Supplied models are listed in
`native_model_obligations` as `unchecked`, or `unsupported-model` for an
unknown version. Neither status establishes a numerical certificate claim.

Raw reversal of an expanded call retains its forward ordinals and support
points; source action adjoints are formed separately before expansion.

The Rust binary embeds both the independent Python arithmetic engine and the
published JSON catalog. It needs no installed source tree at runtime. Python
arbitrary-precision integers and `Fraction` implement the cost algebra; integer
costs stay integral and division remains exact. Gates
and state vectors are never materialised. Structured repetitions and padded
oracle budgets use multiplication of cost summaries. Literal words use exact
set-bit counts, including signed words wider than 2^53 bits; data images are
counted in small byte chunks. The catalog
is contract data, not code copied from another implementation. Tests match all
86 published K82 leaf digests and compare every complete literal profile with
its closed-form summary.

Stack copy/store/exchange summaries count address preparation and equality
dispatch algebraically, touching only the low N bits of each K-bit cell.
Tests cover 2^20 physical cells with bounded summary work and compare small
controlled cases against literal expansion. Scheme workspace remains included;
wire aliases that defeat index renaming use literal traversal.

Ten complete CC program differentials agree with the VM on all resource
rows, source steps and terminal status: a paired action, slice/concat register
views, a stale-alias fault, block-image effects, disjoint register inverses,
quantum segment uncall, nested classical uncall, clean measurement and a
measurement-uncall fault and measurement after private workspace cleanup.
CC/R register accounting includes dynamic widths,
aliases, opaque IDs, slices/concat and source-frame history reversal, including quantum calls. Reversed classical
frames are charged separately from forward source steps. Proved-clean registers
measure deterministically and consume their aliases; uncall across a measurement
fails before reversal. Unresolved outcomes and generic cleanliness evidence
remain required.

Current source coverage includes structured gates, allocation/borrowing,
copy/XOR/exchange, predication, loops, local-region images and linear coherent
memory, controlled action/oracle calls and qinplace, plus padded arithmetic/control
oracles, recursive lifted procedure activation with fixed-binding instances,
lifted allocation with all four history slots, lifted free and
location-length bounds checking, lifted oracle/permutation
calls and intrinsic oracle-uncall recompute, and layout-state/global-address
construction. Each nested oracle retains
its own resolved token. Unused resolved arguments retain their typed invocation
bindings. Remaining lifted memory rows and published source-binding gaps, complete cleanup
partitioning, remaining register/effect histories and certificate proof checking still require work.
Unsupported paths fail explicitly; they remain requirements.

Flat actions containing oracle calls and permutation primitives match joint source occurrences
using actual token identities, current target versions and read/control versions.
Their independent cleanup carriers support reverse and fresh T/F recompute,
including nonzero caller targets. Fresh calls have separate occurrence indices;
source adjoints form new pairs while raw inverse retains forward paths. General
release-ended chains, action-call histories and cleanup window validation remain
required; this family does not complete K81.

Default CC/R topology replay reserves vertices for all live registers, checks
native adjacency and scratch capacity, and restores placements during uncall.
The current VM binary rejects the topology field; the differential report
states that limitation and labels its topology rows as forecasts without a VM
match. Potentially applicable nonempty nested quantum schedules still require
integration and report pending implementation. Minted tokens become
invalid when their mint frame is reversed, including surviving aliases.

Full exact source coverage needs the published decisions described in
[CONTRACT_GAPS.md](docs/CONTRACT_GAPS.md): physical wire binding of classical
pseudo-locations and canonical widths for implicit/literal memory lengths.
The source witnesses are admitted by the VM. Return delivery width and
heterogeneous jump widths expose additional published recipe conflicts. Literal
allocator lengths share the existing length-carrier gap. Varying the currently unspecified
length width changes exact workspace costs. Proposed text is queued for the
orchestrator to file in the spec tracker; it has not been adopted here.

`examples/memory-lookup-2pow20.bisa` exercises 1024 linear lookups into 2^20
eight-bit cells using fewer than 1000 constructor visits. This verifies scaling
of the reference cost calculation; the full rung-4 Grover estimate is pending.
The available rung-4 diagnostic is an ISA 0.8 reduced object, for which this
estimator has no published complete padded expansion catalog. It cannot supply
the real N=2^20 SQLite launch estimate. That estimate requires the actual
compiled launch with its full image, oracle closure and k=7 calls, resolved
invocation parameters and budgets, and a published target whose capacities
admit the full memory register. The illustrative superconducting target's
16 data and 4 buffer qubits cannot hold the required 2^28-wire register.

Allocation-table scans also use exact address-popcount summaries. The
VM-admitted lifted-free-2pow20 example estimates a complete 2^20-entry table
in 2940 constructor visits. The target is `ideal-quantum-circuit`: an ideal quantum circuit with ideal logical qubits, implementing the standard quantum circuit model.
With budget 1,0,0,0 its reference construction costs 23,657,972,470 gates and peaks at 70,254,784
qubits. The VM checks one logical faulting step; it supplies no native gate
count for this fixture.

`--include-frame` reconstructs a B5 descriptor with distinct allocation
lifetimes and nested invocation records. Concrete schedule/frame reconstruction
visits dynamic leaves and retains allocation endpoints, never a gate list;
its work can grow with the budget. Root oracle results expose `padded_steps` for both passes. VM logical execution
steps can stop earlier; the lifted-call witness agrees at its B=4 boundary and
stays below the padded count at B=5.

The default analytic path retains its
closed-form scaling on finite-capacity targets whenever its sequential peak
proves that the default class choices fit. It also counts the default accuracy
population algebraically, before target scheme expansion. Class fallback,
explicit schedules, topology and requested frame reconstruction use replay.

`--certificate file` reads a JCS 0.9 certificate and checks K12 bindings,
resource rows and root frame requirements against a rebuilt supported estimate.
Producer-chosen non-slot identities may be renamed; altered widths, classes,
states or omitted lifetimes reject. Schema parsing and resource agreement do
**not** verify correctness/error claims, nested certificate composition or
shared-storage permissions.

The certificate reader validates nested invocation and claim payloads, domain
ranges, table tuple encodings, sampler words, error decimals and composition
keys. Positional control/borrow labels remain annotations, and legal large
widths or sample counts have no host-size cap. A requested claim label is
preserved without assigning a verification verdict.
Inverse-pair token metadata validates canonical equality partitions; linked
tuple/budget coverage requires declaration order and preserves that partition.
This metadata check discharges no proof or argument-domain obligation.

`--certificate-template existing.json --write-certificate output.json` adds
K12 exact resources, native gate counts and the reconstructed root frame to
an existing certificate for the **same bound invocation**. It preserves supplied
reference/proof metadata and rejects changed object, target, schedule or arguments.
The output does not assert a correctness verdict; claims remain unchecked.
Certificate bytes are JCS and deterministic.

Run the default tests headlessly (create the two job directories first):

```sh
env -u DISPLAY -u WAYLAND_DISPLAY -u DBUS_SESSION_BUS_ADDRESS -u BROWSER \
  TMPDIR="$PWD/.tmp/quality-estimate/tmp" \
  CARGO_TARGET_DIR="$PWD/.tmp/quality-estimate/target" \
  timeout 180 cargo test --offline --locked -j3 -- --test-threads=4
```

Tests and the differential resolve published target/spec/conformance data and
VM binaries only from the `gate.toml` revisions in the immutable gate cache.
The cache must be populated by the pinned gate tool; missing or mismatched
pins fail with the required commit. No live sibling checkout or arbitrary VM
binary override supplies test evidence. The ordinary pre-push hook tests the
pushed SHA in a clean worktree; the orchestrator owns that merge-time gate.

See [quality evidence](docs/quality.md) for default runtime, Python coverage,
independent brute-force accounting, literal provenance and phase equivalence.
