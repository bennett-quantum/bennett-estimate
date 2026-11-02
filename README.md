# bennett-estimate

Resource estimation from ISA objects, certificates and target descriptions, without materialising gates.

Partial independent implementation of published ISA 0.9. See [requirements and
coverage](docs/PLAN.md) and [handoff](HANDOFF.md) before relying on an estimate.
The remaining source, scheduling and verification work is tracked in Beads
under `bennett-estimate-bph`; the complete requested estimator is not yet delivered.

Build with Rust and Python 3.11 or newer (standard library only):

```sh
cargo build --offline --locked -j4
target/debug/bennett-estimate tests/fixtures/example3.bisa \
  --target ../bennett-targets/targets/ideal-all-to-all.json
target/debug/bennett-estimate tests/fixtures/example1.bisa \
  --target ../bennett-targets/targets/ideal-all-to-all.json \
  --region inc8 --budget 1048576,0,0,0 --params '[]'
```

The CLI writes one deterministic JSON object. Invalid input produces a
diagnostic on stderr, nonzero exit status and empty stdout. A request affected
by a filed contract gap instead emits a `pending evidence` JSON report with
its request bindings and issue code, no resource rows, and exit status 3. `--params` is the complete K13 argument
array, inline or `@file`. Integer arguments are unsigned decimal **strings**,
f64 arguments are binary64 hex bit patterns, and tokens are four-string tuples.
No missing argument becomes zero. `--region` is required for multiple entries.
The CLI's explicit default budget is `0,0,0,0`; its variant is `forward` and
inherited control count is zero. Those values appear in the result.

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

`--certificate-template existing.json --write-certificate output.json` adds
K12 exact resources, native gate counts and the reconstructed root frame to
an existing certificate for the **same bound invocation**. It preserves supplied
reference/proof metadata and rejects changed object, target, schedule or arguments.
The output does not assert a correctness verdict; claims remain unchecked.
Certificate bytes are JCS and deterministic.

Run the local checks headlessly:

```sh
env -u DISPLAY -u WAYLAND_DISPLAY -u DBUS_SESSION_BUS_ADDRESS -u BROWSER \
  TMPDIR="$PWD/.tmp/sol-estimate/tmp" \
  CARGO_TARGET_DIR="$PWD/.tmp/sol-estimate/target" \
  scripts/pre-push --working-tree
```

The tests require the sibling published target/conformance data and the VM
binary at `../bennett-vm/target/debug/bennett-vm` (override with
`BENNETT_VM_BIN`). They never import sibling implementation code. The ordinary
pre-push hook uses the public gate tool pinned in gate.toml. It tests each pushed
SHA in a clean worktree with sibling data and the VM binary at their pinned
commits; the job runner owns git operations. The working-tree form performs no git
operation and is for development, not evidence about a pushed SHA.
