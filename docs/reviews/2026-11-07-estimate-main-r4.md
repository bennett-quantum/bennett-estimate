# Estimate main review, round 4

**Verdict: BLOCK. P0: none. P1-1: `bennett-estimate-w2b`.**

Reviewed fix range `ed5b9df..7fef698` (`eeefd06`, `916931a`, `7fef698`)
at exact head **`7fef6987da80dafaf93f1788f9f66eb070b5af9d`**, on
`job/quality-estimate`. Read the full `main..job/quality-estimate` log and
diff summary; semantic review is limited to this fix and its dependencies.
Read the three prior reviews. The referenced `estimate-main.md` is still
absent; read `sol-estimate.md`, as in those reviews. The orchestrator's
pre-review gate on this head PASSED at 08:33Z (supplied evidence, not a
reviewer-run gate).

The exact P1 `bennett-estimate-tdf` witness is fixed: adjacent X/undo
restores the replay input, with literal resources gates/time 9, peak 4,
area 32. Both `bennett-estimate-pjj` disjoint placements remain correct
once each, gates/time 8, peak 5, area 37. Independent scalar interpretation
of actual emitted operands/controls verifies these reverse/recompute
traces over every basis input, forward and raw inverse, with clean
releases. Both `bennett-estimate-yak` witnesses are refused at their
conflicting rows. Loading pre-guard `16ebd9e` in memory independently
reproduces its 4/8 differing outputs and 4/4 dirty releases, respectively.
The tests in `eeefd06` assert the original reviewers' outcomes.

**P1-1 — restored inputs still forbid valid intermediate reads**
(`src/estimate.py:3525`; incorrect oracle condition at
`tests/test_schedule.py:108`; bead **`bennett-estimate-w2b`**).
The new pending-write guard rejects any read of the temporarily changed
input. ISA 0.9 §6.2 requires intervening operations to leave the
computational-basis values of S and g unchanged; reading an input into an
unrelated mutable output does so. The matched undo restores the exact
input version before cleanup. K81 adds no source-program restriction.

Insert `cx x y` between the restored-input witness's two Xs. Both reverse
and recompute preserve x,z and implement `y ^= NOT x`. Independent scalar
replay of actual gate operands confirms equality on **8/8 basis inputs in
both traversal directions**, with every scratch release clean. The head
instead raises `source cleanup-pair recompute crosses non-disjoint row
entry:4 (x)`. Unmodified `16ebd9e`, loaded in memory, accepts this source
as exact (gates/time 10, peak 5, area 45). To inspect the head's refused
replacement for scalar replay, only its obstruction predicate was
suppressed in memory; no production or test file was edited.

Reproduced with `timeout 90 python3 -B -` from this worktree, headless and
with the job-local environment below:

```python
import sys
sys.path.insert(0, "tests")
from test_schedule import e, make_object, target, entry, point
sig = {"abi":"0.9", "tier":"q", "kind":"perm_action", "mut":[1,1],
       "in":[1], "mem":[], "args":[], "bounds":[]}
obj = make_object("""perm_action @root (x:wire, y:wire) (z:wire in) () () ()
^entry():
d = qalloc any 1
cx x d
cx z d
cx z d
x x
cx x y
x x
cx x d
qfree d""", sig)
t = target()
doc = e.estimate(obj, t, "root", [], ["0"]*4)["effective_schedule"]
doc["entries"] = [entry("cleanup", path=[point(
    obj.symbol("root")["interface_hash"], "entry:8")], realisation="recompute")]
obj.sections["schedule"] = doc
e.estimate(obj, t, "root", [], ["0"]*4)
```

The 144-program oracle is computationally independent: its scalar helpers
use no estimator/version/obstruction logic, and all 144 classifications
still run with the production obstruction patched to raise. However, it
includes this source order and wrongly classifies it as unsafe:
`reads_current` requires every observed input read to equal the region-entry
value. The spec requires restored versions at cleanup, while permitting
the intermediate read above. Thus the test encodes the same narrowing
despite independent arithmetic. Repair the predicate and oracle together.

**P2+ nits:** aggregate `bennett-estimate-7c2` (P3): carry-forward opcode-category duplication (`bennett-estimate-c4p`); single-call-site parsing helpers at `src/estimate.py:3468/:3475/:3481` and unrelated assertion extractions at `tests/test_schedule.py:661/:1739/:2075` add indirection under COMMON's delete-don't-wrap rule; no demonstrated hidden bug.

**Verification:** DISPLAY, WAYLAND_DISPLAY, DBUS_SESSION_BUS_ADDRESS and
BROWSER unset; TMPDIR/CARGO_TARGET_DIR under
`.tmp/rev-estimate-main-r4/{tmp,target}`. Focused only; no full or sibling gate:

- `timeout 120 python3 -B -m unittest discover -s tests -p test_schedule.py -k test_review -v`: 3 passed.
- Same focused discovery with `-k test_cleanup_generated`: 1 passed, all 288 forward/raw subcases.
- `timeout 180 python3 -B -m unittest discover -s tests -p test_schedule.py -q`: all 144 passed, 45.741 s.
- `timeout 90 python3 -B -`: independent literal witness constructions and actual-operand scalar replays described above. Loading `git show ed5b9df:src/estimate.py` makes only the restored-input witness error; loading `main:src/estimate.py` rejects both valid witnesses and fails the unsafe witness's diagnostic assertion. No checkout changes.
- `timeout 30 python3 -B -`: oracle independence check, 26 allowed / 118 rejected; the confirmed valid-read case is among the latter.
- `timeout 30 python3 -I -B scripts/quality_ratchet.py`: no regression; `git diff --check ed5b9df..7fef698`: passed.

**Coverage:** read closely: all source/test fix hunks, assertion-preserving
test extractions, partition/version matching, pending-input guard,
cleanup choice/replay and lowering, main/pre-fix code, pinned ISA
§5.3/§6.1–6.4/§11 K81 at `fd626d37aba1f719c3b7b2059be46cbfaf462886`;
skimmed: surrounding unchanged machinery and quality-document diff.
Checked every COMMON anti-slop rule: the narrowing and incorrect oracle
are P1-1; remaining dispatch/helper issues are nits; no weakened/deleted
assertions, new silent defaults, process identifiers or tracked litter.
Gate ratchet and HANDOFF retirement were already checked in round 1.

**Provenance:** implementer gpt-6-astra; reviewer gpt-6.1-sol, fresh session (D9).
