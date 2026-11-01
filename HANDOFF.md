# Handoff

Status: partial implementation, ISA 0.9 pinned in SPEC_VERSIONS.toml. The runner
owns commits; no git command was run by this job. Worklog is orchestrator-owned.

Implemented: exact rational expressions and K9/K12 arithmetic; independent
object and certificate readers; all ten normative object identity vectors;
published catalog traversal into composable cost summaries; structured source
primitives; zero-argument memoryless padded oracle summaries; pure classical
control-path costing and conditional step bounds; deterministic JSON CLI.

Verified: headless `timeout 180 scripts/pre-push --working-tree` exited 0:
26 estimator tests, one hook orchestration test, Rust formatting, Clippy with
warnings denied and shell syntax checks passed. The hook test uses an explicit
VCS double; no git process was invoked. It verifies pushed-SHA selection,
deduplication, deletion-only pushes and failed-check cleanup. The runner must
still invoke the normal hook against a real committed SHA.

Additional scaling evidence: the source object in
`examples/memory-lookup-2pow20.bisa` has 2^20 eight-bit cells and 1024 repeated
load/XOR/unload operations. Its summary uses fewer than 1000 constructor visits.
The dispatch formula agrees exactly with literal catalog traversal on small
address spaces. This is a reference-cost scaling fixture, not the full Grover
or SQLite rung. Indexed-control/middle-alias tests guard loop folding, and the
published controlled-action fixture exercises default controlled action calls.

Differential: the published rung-3 `executor-control.bisa` with `sum` arguments
0, 1, 3, 7, 255 matches the VM's 6, 11, 21, 41, 1281 source steps and sequential
time exactly. This is a classical count comparison. Rung 2 currently has no ISA
object or stated gate/step count; its reports record pipeline blockers.
`scripts/differential.py` reports that unavailability explicitly.

Open requirements: `bennett-estimate-bph` and children `.1` (all source bindings),
`.2` (schedule/topology/certification) and `.3` (remaining differential evidence).
Structure recovery stays in scope, with upstream `b-isa-spec-r51` as the
efficiency work item; there is no claimed meaningful full Grover/SQLite estimate
at 2^20 rows yet. Do not label a padded step-machine estimate structure-recovered.

The exported upstream `bennett-vm-hsd`/`b-isa-spec-c15` records were read because
their databases are read-only under this job's sandbox. Published 0.9 K12 fixes
the requested parameter vector, escaped per-class rows and upward decimal
contract; no decision was guessed. There is no newly established normative gap
in those rules. Upstream Beads writes would require an orchestrator with write
access; local follow-up work is in this repository's Beads database/export.
