# bennett-estimate

Resource estimation from ISA objects, certificates and target descriptions, without materialising gates.

Partial independent implementation of published ISA 0.9. See [requirements and
coverage](docs/PLAN.md) and [handoff](HANDOFF.md) before relying on an estimate.
The remaining source, scheduling and verification work is tracked in Beads
under `bennett-estimate-bph`; the complete requested estimator is not yet delivered.

Build with Rust and Python 3.10 or newer (standard library only):

```sh
cargo build --offline --locked -j4
target/debug/bennett-estimate tests/fixtures/example3.bisa \
  --target ../bennett-targets/targets/ideal-all-to-all.json
target/debug/bennett-estimate tests/fixtures/example1.bisa \
  --target ../bennett-targets/targets/ideal-all-to-all.json \
  --region inc8 --budget 1048576,0,0,0 --params '[]'
```

The CLI writes one deterministic JSON object, or a diagnostic on stderr with
nonzero exit status and empty stdout. `--params` is the complete K13 argument
array, inline or `@file`. Integer arguments are unsigned decimal **strings**,
f64 arguments are binary64 hex bit patterns, and tokens are four-string tuples.
No missing argument becomes zero. `--region` is required for multiple entries.
The CLI's explicit default budget is `0,0,0,0`; its variant is `forward` and
inherited control count is zero. Those values appear in the result.

`exact_resources` stores reduced arbitrary-precision rational values.
`resources` contains the K12 upward 34-significant-digit decimal display and
escaped class keys, including zero rows for unused classes. `exact` labels the
resource calculation for the stated sequential realisation; it does not certify
program correctness, optimality, or structure recovery. A
`--classical-step-bound N` report instead labels a **conditional** upper bound
and states the termination assumption. It contains `rational_upper_bounds`,
never a fabricated exact cost. This option applies to purely classical objects.

The Rust binary embeds both the independent Python arithmetic engine and the
published JSON catalog. It needs no installed source tree at runtime. Python
arbitrary-precision integers and `Fraction` implement the cost algebra; gates
and state vectors are never materialised. Structured repetitions and padded
memoryless oracle budgets use multiplication of cost summaries. The catalog
is contract data, not code copied from another implementation.

Current source coverage includes structured gates, allocation/borrowing,
copy/XOR/exchange, predication, loops, local-region images and linear coherent
memory, basic controlled action calls, plus padded arithmetic/control oracles
and layout-state/global-address construction. Unused resolved arguments retain
their typed invocation bindings. Full memory/activation rows, complete semantic
calls and cleanup, explicit schedules, topology,
full parameter lowering and certificate production still require work.
Unsupported paths fail explicitly; they remain requirements.

Full exact source coverage needs the published decisions described in
[CONTRACT_GAPS.md](docs/CONTRACT_GAPS.md): physical wire binding of classical
pseudo-locations and canonical widths for implicit/literal memory lengths.
The source witnesses are admitted by the VM; varying the currently unspecified
length width changes exact workspace costs. Proposed text is queued for the
orchestrator to file in the spec tracker; it has not been adopted here.

`examples/memory-lookup-2pow20.bisa` exercises 1024 linear lookups into 2^20
eight-bit cells using fewer than 1000 constructor visits. This verifies scaling
of the reference cost calculation; the full rung-4 Grover estimate is pending.

`--certificate file` reads a JCS 0.9 certificate and checks K12 bindings and
resource rows against a rebuilt supported estimate. Schema parsing and resource
agreement do **not** verify the certificate's correctness/error claims.

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
pre-push hook tests each pushed SHA in a clean detached worktree beside the
repo; the job runner owns git operations. The working-tree form performs no git
operation and is for development, not evidence about a pushed SHA.
