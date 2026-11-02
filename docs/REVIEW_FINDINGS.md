# Review findings against the pinned contract

The determining source is ISA 0.9 at `e424d678fa553be5847bf1b53f83703462318b57`,
SHA-256 `021d5df978f293c36174b73de9facc0884f7502a4bc5c0ab7a621b0ca7071c25`.
This adjudicates the findings in `reviews/2026-11-02-design-review.md` against
the published defaults, rather than treating another consumer's answer as a
replacement contract.

| Finding | Published requirement | Result and regression |
|---|---|---|
| E1 / `bst` | K58 and §17 item 9 define exact-native coverage before the accuracy filter. An operation with any exact native match receives default share zero. §8.3 then chooses the first entry satisfying that resolved share. | The two-H omitted-share request costs 200 under the published text. With explicit shares of .005, the first approximate entry costs 2 and charges error .002. `test_k58_exact_native_default_is_zero_but_explicit_share_keeps_array_order` checks both. Changing the default answer to 2 would violate K58. |
| E2 / `4mr` | K58 counts operations before target scheme expansion that lack an exact native match. An exact scheme is not an exact native match. | H plus the scheme-realised MCX gives N=2. Accuracy .01 assigns .005 and cannot admit the .01 H entry; accuracy .02 assigns .01 and succeeds. `test_k58_exact_scheme_still_counts_before_target_expansion` checks the population and achieved error. |
| E3 / `3p2` | K57 and §17 items 7/9 give an omitted expansion the full published ref hash for the object's ISA version. | Omission on a 0.9 schedule is accepted and its explicit start decision is applied. It does not select the old single-QXOR witness. `test_omitted_expansion_resolves_ref_but_foreign_libraries_reject` checks the applied start. |
| E4 / `w8f` | §11 requires a consumer lacking the bound expansion library to report `E_SCHEDULE_INFEASIBLE`; §10.1 forbids silently changing that library. | Reproduced and fixed. Schedule admission rejects a foreign name or a different ref hash before binding fallback. The same regression checks both errors. |
| E5 / `xng` | The estimator must use cost summaries without enumerating repeated gates; capacity and accuracy are part of that same calculation. | Default summaries now prove capacity from the sequential live peak. The pre-scheme inexact population composes through repetition, then exact rational shares cost a second summary. Trillion-iteration finite-capacity/exact and approximate cases have bounded constructor work. A small scheme-workspace case agrees with independent ledger replay on every resource row, error, gate count and share. |

If the sequential peak cannot establish the default class decisions, replay
resolves class fallback. Explicit schedules, topology and requested complete
frame descriptors also retain replay. Thus the default cost summary has the
scaling property above; complete dynamic frame reconstruction can still grow
with the number of allocation occurrences. Large allocation-table scan summaries
and the remaining source/activation families remain required under the main
implementation beads.

Gate adoption is tracked separately in `m6p`: the orchestrator supplied the
pinned sibling manifest, and the owned hook now delegates to the pinned public
tool. The working-tree guard precedes every git command. Tests cover manifest
pins, VM build/output binding, the stub delegation and development-check failure
propagation. Actual pushed-SHA execution and hook chaining verification are
runner responsibilities under this job's prohibition on running git.
