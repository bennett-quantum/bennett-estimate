# Estimate quality review, round 1 — 2026-11-06

Range: `main..job/quality-estimate`, base `989dd04504497defc7b41ec8fbb05890bf6913ff`, reviewed head **`628df14e8ec7418c2f99e533606d3339bf010817`** (eight commits, including the runner attempt and continuation).

**Verdict: CLEAR. No P0/P1 findings; no blocking beads.**

Reviewed the complete batch against CLAUDE.md, the amended review policy, COMMON anti-slop rules, the implementation brief and programme items 9–11. The two inherited issues have executable regressions: omitted oracle/token budgets fail, and native-model metadata is accepted, hash-bound and reported as unchecked/unsupported. Resource calculation is not presented as model verification.

## Verification

All commands ran headlessly with reviewer-local TMPDIR and CARGO_TARGET_DIR; only focused tests ran.

- `timeout 60 cargo build --offline --locked -j3`: passed.
- `timeout 60 python3 -I -B -c ...`, loading `test_quality`, `test_fail_fast`, `test_phases`, `test_brute_accounting`, `test_output`, both quality-ratchet modules and `test_gate` through unittest: **26 passed in 2.012 s**.
- `timeout 120 python3 -I -B -`, selecting existing test names containing classical/uncall/quantum/qinplace/oracle_call/action_call/register/large_stack/implicit_length/decimal_string_entry/differential/deterministic_and_failure from test_estimate and test_schedule: **39 passed in 25.694 s**, including the pinned VM differential.
- `timeout 120 python3 -I -B -`, importing main directly from `git show main:src/estimate.py` in memory and comparing with head: **64 byte-identical bounded requests** across 16 fixtures, two targets and both frame modes; 52 successes and 12 matching loud refusals. This is regression evidence, not an independent correctness oracle.
- `timeout 30 python3 -I -B scripts/quality_ratchet.py`: passed. Independently remeasured the entire recorded baseline: exact match; maximum source function length 252, versus three functions over 300 lines at main. HANDOFF.md is deleted and README links the ecosystem handoff.
- Inventory audit: all **358** assertion entries match current source hashes and assertion text; 357 are observed, one honestly unexecuted. The independent brute ledger imports no estimator algebra and detects the deliberate summary-area mutation.
- Read the new regressions against main-side code: the broad index-fold catch swallows the injected defects, missing-budget calls succeed, model metadata is rejected, and pending output includes a bead field there. These assertions distinguish the intended changes. No existing test was removed, skipped or weakened. `git diff --check main...job/quality-estimate` passed.

The full default suite, coverage instrumentation and merge-time gate were not rerun; their documented measurements are not reviewer-run claims.

P2+ nits: **bennett-estimate-7ue** (priority 3, review/nit): stale final provenance counts at data/PROVENANCE.md:30; fixture-path identifiers escape the content-only hygiene scan at scripts/quality_ratchet.py:81 (confirmed with a temporary tracked quality-estimate.bisa fixture). Neither blocks.

Coverage: read closely all changed semantic code, scripts, tests, gate/pin changes and quality documentation; skimmed unchanged parser/scheduler/certificate internals and historical handoff deletion; checked all inventory records structurally rather than reading every serialized observation.

Provenance: implementer gpt-6.1-sol; reviewer gpt-6.1-sol, fresh session under D9.
