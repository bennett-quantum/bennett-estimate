# Estimate main review, round 2

**Verdict: BLOCK. P0-1: `bennett-estimate-yak`. P1: none.**

Reviewed fix range `cded9253c904a22bcabc17f462a563d6a7afafde..9f8869b6d87010f2011f70da8a90dad27c34126e`
(`496f3aa`, `9f8869b`), at exact head
**`9f8869b6d87010f2011f70da8a90dad27c34126e`**, on
`job/quality-estimate`. Read the complete `main..job/quality-estimate` log
and range summary; semantic review is limited to the round-1 fix and its
dependencies. `estimate-main.md` remains absent; read `sol-estimate.md`,
as identified by the previous review.

The original P1 `bennett-estimate-pjj` is fixed: both independent `x y`
placements survive once, at their original source point, in forward and
raw-inverse traversal. K80's contiguous count is hand-derived as two original
CXs plus five replacement CXs: gates/time 7, peak 4, area `2*3+5*4=26`.
With independent y and X, gates/time are 8, peak 5, area `3*4+5*5=37`.
These follow ISA 0.9 §11 K80/K81 at gate pin
`fd626d37aba1f719c3b7b2059be46cbfaf462886`, without estimator-derived oracles.

**P0-1 — non-disjoint rows now permit an incorrect recompute**
(`src/estimate.py:3455`; output-only skip at `:3439`, replay at `:3503`;
bead `bennett-estimate-yak`). Removing adjacency without a dependency check
also admits rows that read d, or change inputs required by its computation.
The checks of the original reverse execution do not establish that moving
its inverses to the release carrier preserves those rows' semantics.

Insert `cx d y` between K80's inverse CXs. Reverse clears z from d before
that row, so `y ^= x`. Recompute suppresses that inverse, leaving
`d = x XOR z` when the row executes, so `y ^= x XOR z`. For x=0, z=1,
y=0, reverse returns y=0 while recompute returns y=1. An independent
one-bit interpreter of the actual `Ledger.gate` wire operands confirmed
different outputs on **4/8 basis inputs**, with clean releases in both
traces. Nevertheless, the estimator labels this schedule `exact`, charging
8 gates/time, peak 5, area 37. The same request at pre-fix `cded925`, loaded
in memory, fails loudly rather than making that claim.

Reproduced with `timeout 60 python3 -B -` from this worktree, using the
following source and schedule construction; the trace prints the actual
operands whose basis actions were independently replayed:

```python
import sys
sys.path.insert(0, "tests")
from test_schedule import *
sig = {"abi":"0.9", "tier":"q", "kind":"perm_action", "mut":[1],
       "in":[1,1], "mem":[], "args":[], "bounds":[]}
obj = make_object("""perm_action @root (y:wire) (x:wire in, z:wire in) () () ()
^entry():
d = qalloc any 1
cx x d
cx z d
cx z d
cx d y
cx x d
qfree d""", sig)
t = target()
doc = e.estimate(obj,t,"root",[],["0"]*4)["effective_schedule"]
doc["entries"] = [entry("cleanup", path=[point(
    obj.symbol("root")["interface_hash"], "entry:6")], realisation="recompute")]
obj.sections["schedule"] = doc
print(e.estimate(obj,t,"root",[],["0"]*4)["label"])
class Trace(e.Ledger):
    def gate(self,op,wires,controls=(),**kw):
        print(op, [b.identity for b in wires])
        return super().gate(op,wires,controls,**kw)
c = e.Catalog((ROOT/"data/ref-0.9.json").read_text(),t)
c.ledger = Trace(t,e.Schedule(doc,obj,"root"))
e.Source(obj,t,c).region("root",[],["0"]*4)
```

The same root cause has a second confirmed witness: make x mutable, keep z
an input, and place `x x` after both original inverse CXs, immediately before
qfree. Reverse has already cleared d. Recompute instead uses changed x,
XORs the wrong value into d, and **releases d=1 on all 4/4 input bases**.
The estimator again labels it exact (gates/time 8, peak 4, area 29); pre-fix
source refuses it. ISA §6.2 requires current external input versions and
§6.4 requires correct fresh-compute/XOR/uncompute; K81's exception is for
disjoint rows. Preserve the fixed independent interleavings while checking
the full read/write dependencies and replay input versions. Add both
non-disjoint regressions; the blanket adjacency restriction is not a fix.

**P2+ nits:** `bennett-estimate-ibw` (P3, review/nit): `tests/test_schedule.py:286`
omits operands/controls from its exact-leaf trace; carry-forward opcode
category duplication at `src/estimate.py:3405/:3423/:3460/:4250` remains
owned by `bennett-estimate-c4p`.

**Verification:** headless throughout verification; TMPDIR and
CARGO_TARGET_DIR were `.tmp/rev-estimate-main-r2/{tmp,target}`. Focused only:

- `timeout 60 python3 -B -m unittest discover -s tests -p test_schedule.py -k test_k80 -v`: passed all six fixture/direction subcases.
- `timeout 90 python3 -B -m unittest discover -s tests -p test_schedule.py -k cleanup -v`: 8 passed; same command with `-k primitive`: 4 passed.
- `timeout 90 python3 -B -`: final K80 test against `git show main:src/estimate.py` and `git show cded925:src/estimate.py`, each loaded in memory: contiguous cases passed, four interleaving cases raised the expected pending-binding error. Head passed all six. No checkout or tests were changed.
- `timeout 60 python3 -B -`: independent one-bit replay over all basis inputs for both counterexamples, comparing reverse/recompute; results above. Both were refused by pre-fix source and accepted as exact at head.
- `timeout 30 python3 -I -B scripts/quality_ratchet.py`: no regression. `git diff --check cded925..9f8869b`: passed.

**Coverage:** read closely all three fix paths, partition/version matching,
cleanup choice/recompute and lowering wrappers, modified tests, previous
reviews, pinned ISA §6.2/§6.4/§11 K80/K81 and relevant main-side code;
skimmed surrounding unchanged source/ledger machinery and historical quality
evidence. Checked every COMMON anti-slop rule: no new litter, process ids,
silent defaults, wrappers or weakened/skipped tests; the confirmed semantic
bug is the blocker. Full suite, sibling gates and VM differential were not
rerun, and implementer measurements are not reviewer-run claims.

**Provenance:** implementer gpt-6.1-sol; reviewer gpt-6.1-sol, fresh session (D9).
