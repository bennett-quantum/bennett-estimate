# bennett-estimate batch review, 2026-11-03 (Opus)

**Range:** `d6646e0^..77bcd07` (46 commits). Reviewed snapshot: `77bcd07408b312067ed80e81bcc7cde9e2a48486`, read in a
detached worktree. Contract: ISA 0.9 at pinned `e424d67` (sha256 `021d5df…`), plus K91 from `fd626d3` as
SPEC_VERSIONS.toml declares. Laws: CLAUDE.md and the code-quality policy (rules 2-6, 9).

**Verdict: CLEAR.** No P0 or P1 finding was confirmed. P2+ items are in one nit bead: `bennett-estimate-1jk`.

## P0/P1 findings

None.

Suspicions checked and refuted against the spec:
- State images loaded without the caller's controls (`src/estimate.py:3012`, `:1308`). This is correct: K21 says image
  X leaves are unconditional.
- First approximate entry overridden by a later exact entry, and exact schemes counted in N. Both are correct under
  K58 / §17 item 9 (already adjudicated: `bst`, `4mr`).
- Step-bound reachability following `call` only. This is safe: `uncall @f` requires an earlier completed call of `@f`.

## What was run

- Focused suites at 77bcd07: `python3 -I -B tests/run_suite.py {objects,accounting,selectors,other}` with
  `BENNETT_ESTIMATE_BIN` set to a debug build. Results: 75 + 115 + 16 + 2 tests, all OK. There are no
  skip decorators. Siblings were symlinked beside the worktree because the tests read `ROOT.parent`.
- Summary path against ledger path, comparing `exact_resources` with and without `--include-frame` for every
  action/oracle region in `examples/` and `tests/fixtures/` (2^20 examples excluded). Run across all four published
  targets, and again with `--inherited-controls 2` on the ideal target. Every comparable pair matched. Every refusal
  was the same on both paths and was loud (`E_SCHEDULE_INFEASIBLE`, `E_GATE_UNSUPPORTED`, or EST-SOURCE pending with exit 3).
- K12 `decimal_up` against all §10.1 witness values, plus 34/35-digit boundary values. All correct.
- K86 probe (`.tmp/opus-rev-estimate/probe/k86.py`): `Target.read` rejects `realisation_model` (nit 7).
- CLI probe: an oracle with `--budget` omitted silently estimates B=0 (nit 4).

## Coverage

**Read closely:** `src/estimate.py` lines 1-980 (numbers, JCS, expressions, Profile algebra, Target read/match,
schemes, Catalog bind/recipe and dispatch/literal summaries), 1100-1330, 2204-2770 (Ledger, Admission, Source.region,
oracle_pairs), 2765-3016 (oracle padded construction), 4014-4586 (`estimate`, Certificate read/check/produce, CLI).
Also `scripts/differential.py`, `tests/run_suite.py`, `tests/python.rs`, and the spec §8, §10.1, K21, K58/§17 item 9
and §9.4 frame schema.

**Skimmed or not read:** Object reader and identities (1522-1972; trusted to the normative §16.3 hash tests),
Schedule (2023-2204; the 2026-11-02 review read it), `Source.classical` (3139-3600), `source_loop`, `conditional_loop`,
`action_nodes` (3611-4013), `oracle_stream` and `oracle_state`, table/global-delivery summaries (980-1100), and
`test_schedule.py` in detail.

## Provenance (policy rule 2 / COMMON R14)

All changes to `src/` and `tests/` in this range come from Codex commits (33 `wip(codex job sol-estimate)` commits by
the sol-estimate runner; these carry a runner `Co-Authored-By: Claude` trailer and no `Agent:` trailer, see nit 3).
The other 13 commits are Claude-only (beads, gate pin, design review, worklogs). This reviewer is Claude Opus 5.5,
which is the opposite-model seat for that Codex work. Per rule 5 the estimator is semantics-bearing, so the Muse call
on the CLEAR round is for the orchestrator to schedule under the Muse quota policy.
