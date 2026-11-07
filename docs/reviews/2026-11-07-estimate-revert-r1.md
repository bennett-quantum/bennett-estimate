# Estimate revert review, round 1

**Verdict: CLEAR. P0/P1: none.** Nonblocking aggregate: `bennett-estimate-ks1`.

Reviewed `main..job/quality-estimate` (main `cf63fcdfa3a1771e363e8706d72d48aecfa9dfb7`), focusing on `5cfb30b..a66610d`, at exact head **`a66610d77ea94a04b88e559b84f95d38ae6ca251`**. Read both original checkpoints, the four BLOCK reviews, the CLEAR quality review, laws, amended policy and revert brief. Severity follows COMMON R32. Terminal recompute is explicitly deferred to `bennett-estimate-e9a`; its absence is not a narrowing finding.

The ten reverts target the specified commits in the specified order. Terminal partition/choice/replay, fresh-empty recompute and their wiring are gone. `Source.action_construction` has the pre-`5062ee2` AST; `action_nodes` retains the CLEAR batch's three lowering extractions while restoring the earlier cleanup path. Oracle-pair and intrinsic recompute remain. All earlier review files are byte-identical.

The retained `empty_cleanups` classifier is used only by `ClassicalMachine.identity_body`; it neither selects cleanup nor emits a replacement. Its unchanged measurement regression passes at head and fails at `5062ee2^` with the pending-cleanliness error. The workspace fixture and ten-program VM differential survive. No other capability loss was found.

Compared with `628df14`, every surviving source function except the two cleanup wiring methods has identical AST; every surviving schedule-test function has identical AST and assertions. All other quality-batch paths are byte-identical except README/PLAN recompute claims and the reviewed quality baseline. All 12 deleted test methods were introduced by reverted commits. No unrelated test was removed, weakened or skipped.

Independently parsed the baseline and qualified function ASTs: `a66610d` removes exactly six deleted source-function lengths and eleven deleted test/nested-method lengths. It adds no lengths, raises no surviving function budget and changes no complexity, wrapper, other-file or hygiene limit. Plan items 9–11 remain satisfied: gate ratchet wired and tested, HANDOFF retired with README pointer, all anti-slop rules checked.

Verification was headless, with TMPDIR/CARGO_TARGET_DIR under `.tmp/rev-estimate-revert-r1/{tmp,target}`, three build jobs and four Rust test threads. Focused checks only:

- `timeout 90 cargo build --offline --locked -j3`: passed.
- `timeout 120 python3 -B -m unittest discover -s tests -p test_schedule.py -k cleanup -v`: 4 passed.
- `timeout 90 python3 -B -`: selected remaining primitive/measurement/qinplace/oracle-pair cases, excluding cleanup matches: 13 passed. Separate `timeout 60` run of three source-adjoint/reversal cases: 3 passed.
- `timeout 120 python3 -B -`: unittest modules `test_quality`, `test_fail_fast`, `test_phases`, `test_brute_accounting`, `test_output`, both quality-ratchet modules and `test_gate`: 26 passed.
- With BENNETT_ESTIMATE_BIN set to the reviewer-built binary, `timeout 180 python3 -B -m unittest discover -s tests -p test_estimate.py -k differential_rung3_and_rung2_inventory -v`: 1 passed, including the retained workspace program and all ten exact complete-program VM comparisons at gate pins.
- `timeout 90 python3 -B -`: loaded main and `5062ee2^` in memory, without switching branches. K80 reverse has literal gates/time 4, peak 3, area 12 in summary/frame modes at all three revisions. Head and pre-checkpoint refuse forward terminal/empty recompute loudly; main accepts them. Private-workspace measurement distinguishes head from the pre-checkpoint baseline as described above.
- `timeout 30 python3 -I -B scripts/quality_ratchet.py`: passed. Inline AST/hash/order audits and `git diff --check main...HEAD` / `5cfb30b..HEAD`: passed. No full repo gate, default suite or sibling gate rerun; supplied full-gate PASS is not a reviewer-run claim.

**P2+ nits:** `bennett-estimate-ks1`: P2-1, restored pre-checkpoint source-adjoint cleanup ignores explicit recompute and returns exact reverse costs (`src/estimate.py:4281`; reproduced at head and `5062ee2^`, no demonstrated rung path); P3-2, 240 stale schedule-test inventory hashes, 222 stale assertion locations and older provenance counts (`data/literal-expectations.json`, `data/PROVENANCE.md:30`); P3-3, carry-forward fixture-filename hygiene gap (`scripts/quality_ratchet.py:81`, existing `bennett-estimate-7ue`). Reproductions are in the aggregate bead; none qualifies as P0/P1 under R32.

**Coverage:** read closely original/revert source changes, retained identity/measurement path, cleanup lowering/replay, test preservation and ASTs, baseline arrays/ratchet, gate/retirement wiring and pinned ISA §6.2/§6.4/§11 K65/K80/K81; skimmed unchanged surrounding parser/ledger machinery and historical quality measurements.

**Provenance:** implementer gpt-6.1-sol; reviewer gpt-6.1-sol, fresh session (D9). No production or test changes made.
