# bennett-estimate design review — 2026-11-02 (PARTIAL)

Review against ISA 0.9 §8, §10.1, §11 at pinned revision `519b045`. Stopped early for a
network outage. Source has since moved (at least `066229a`); findings were re-verified at
HEAD `d32ef4f` (below) and filed as beads. Only the schedule, ledger and
top-level `estimate` code was read closely; `Catalog`, `Source` and `Certificate` were not.
EST-SOURCE (`b-isa-spec-9y4`) was read but not independently assessed beyond confirming that
its affected examples fail loudly.

Probes: `.tmp/opus-reviews/probe/test_probe.py` (not committed; `.tmp` is ignored), 12 run,
6 fail. Repo tests via `unittest discover`: 83 run, 3 errors, all `KeyError:
BENNETT_ESTIMATE_BIN` from how I invoked them, not defects. `scripts/check` was not run.

**Re-verified 2026-11-02 at HEAD `d32ef4f`** (`python3 -W ignore -m unittest test_probe` against a worktree at that sha): same 6 of 12 fail (E1-E4 and the tracked e7/e8). E5 re-measured: `loopmil.bisa` (qloop 10^5) 1.4 s and 2 summary operations unbounded, 39.8 s and 100001 with capacity 100. One bead per finding, ids in the headings.

## Findings

### E1 (bennett-estimate-bst P1). Later exact entry overrides the first matching approximate entry
Two `h`, entries `[eps .001, time 1]` then `[eps 0, time 100]`, `--epsilon 0.01`: time 200,
error 0. §8.3 selects the first entry with epsilon ≤ share, giving time 2; sched gives 2.
Cause: `Ledger.gate` uses share 0 whenever `exact_native` finds any exact entry.
Probe: `test_e1_*`.

### E2 (bennett-estimate-4mr P2). Exact scheme counted as an ε>0 operation
One approximate `h` (eps .01) plus one `mcx` through an exact scheme, `--epsilon 0.01`:
`E_GATE_UNSUPPORTED`. Only one operation has ε>0 (§8.1), so the share should be .01; sched
returns OK. A valid request is refused. Probe: `test_e2_*`.

### E3 (bennett-estimate-3p2 P2). Schedule without `bindings.expansion` is selected
§11's schema requires the field; `binding_equal` treats its absence as a match for ISA 0.9.
Probe: `test_e5_*`.

### E4 (bennett-estimate-w8f P2, contestable). Foreign expansion binding silently falls back to defaults
A schedule bound to library `other` yields an estimate under `ref`. §10.1 says non-matching
bindings use defaults, but also that silently changing the expansion library is not an
estimate and a consumer lacking the library reports `E_SCHEDULE_INFEASIBLE`. May need a spec
ruling. Probe: `test_e6_*`.

### E5 (bennett-estimate-xng P2). Any finite capacity or ε>0 forces literal replay
Measured once by an ad-hoc script, not a red test. `qloop` of 10^12: 1.5 s when unbounded, over
120 s (timed out) with capacity 100. `qloop` of 10^5: 1.4 s unbounded, 69 s with capacity, 94 s
with ε=0.1. `summary_operations` goes from 2 to 100001. Three of the four published targets in
bennett-targets have finite capacity, so the no-materialisation aim and EST-18 fail on them.

## Known gaps, already tracked
`test_e7_*`: the K80 recompute witness fails loudly ("recompute binding remains pending"); the
PLAN records K81 as open. Lproc oracles and pseudo-location reads fail loudly (EST-SOURCE-01,
`b-isa-spec-9y4`). `test_e8_*` records the disagreement filed under sched S3; estimate's
behaviour there matches §11 defaults.

## Checked, no defect found
Zero-trip loop peak, replay versus summary peak, non-canonical argument rejection, K12 row order
and zero rows, and `qif` differential against sched.
