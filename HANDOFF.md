# Handoff

Status: partial implementation, ISA 0.9 pinned in SPEC_VERSIONS.toml. The runner
owns commits; no git command was run by this job. Worklog is orchestrator-owned.

Implemented: exact rational expressions and K9/K12 arithmetic; independent
object and certificate readers; all ten normative object identity vectors;
published catalog traversal into composable cost summaries; structured source
primitives; zero-argument memoryless padded oracle summaries; pure classical
control-path costing and conditional step bounds; deterministic JSON CLI.

The first full working-tree gate ran all 18 tests successfully, then failed on
Rust formatting. `cargo fmt` corrected that failure. The final gate result is
recorded in the current `.tmp/PROGRESS.md` Resume block. Do not infer a clean
pushed-SHA result: the runner must invoke the normal hook after committing.

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
