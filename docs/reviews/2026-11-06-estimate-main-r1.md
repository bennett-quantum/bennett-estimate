# Estimate main review, round 1

**Verdict: BLOCK.** P0: none. P1-1: `bennett-estimate-pjj`.

Reviewed commits `5062ee2`, `989dd04` (`77f32b3..989dd04`), following their
hunks into **`c50c662dfb273f50ecc975d12552b221752ab954`** on
`job/quality-estimate`. This head differs from requested `628df14` only by
review documentation. The separate quality batch is outside this review.
The referenced `estimate-main.md` brief is absent; `sol-estimate.md` supplies
the original estimator requirements.

**P1-1 — disjoint source rows wrongly prevent terminal cleanup recompute**
(`src/estimate.py:3446`, consumed at `:3456`; bead `bennett-estimate-pjj`).
The new partition requires inverse rows to be textually contiguous with
`qfree`. Insert `x y` on an independent mutable wire between the two inverse
CXs of the published K80 fixture, or immediately before its release:
recompute raises `ContractError: source cleanup-pair recompute binding remains
pending for this carrier`. The unchanged contiguous chain succeeds with
seven gates. These are still flat, supported primitive instructions with
unchanged cleanup input versions. ISA 0.9 §11 K81 explicitly excludes disjoint
rows from the chain and says pair formation does not require textual
adjacency. This is a narrowing of the new primitive family. Preserve the
disjoint operation once while replacing the owned inverses at the carrier;
add both interleaving regressions.

Reproduced at the reviewed head with `timeout 60 python3 -B -` and the
following inline program (from this worktree, headless, with job-local TMPDIR):

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
x y
cx x d
qfree d""", sig)
t = target()
doc = e.estimate(obj, t, "root", [], ["0"]*4)["effective_schedule"]
doc["entries"] = [entry("cleanup", path=[point(
    obj.symbol("root")["interface_hash"], "entry:6")], realisation="recompute")]
obj.sections["schedule"] = doc
e.estimate(obj, t, "root", [], ["0"]*4, include_frame=True)
```

**P2+ nits:** P3-1, `bennett-estimate-c4p`: the added classifier repeats string
opcode dispatch already present in lowering (`src/estimate.py:3405`, `:3423`,
`:3461`, `:4251`); give those categories one parsed representation/owner.

**Verification:** all commands unset DISPLAY, WAYLAND_DISPLAY,
DBUS_SESSION_BUS_ADDRESS and BROWSER; TMPDIR and CARGO_TARGET_DIR were
`.tmp/rev-estimate-main-r1/{tmp,target}`. Focused checks only, no full gate:

- `timeout 150 python3 -B -m unittest discover -s tests -p test_schedule.py -k cleanup -v`: 8 passed.
- Same focused discovery with `-k primitive`: 4 passed; `timeout 120` with
  `-k empty_`: 5 passed; `-k proved_clean_measurement`: 1 passed.
- `timeout 90 python3 -B -` explicitly ran the eight added tests: all passed
  at head. Loading `git show 77f32b3:src/estimate.py` into an isolated in-memory
  module made every test fail/error, including subtests. No checkout changed.
  Current `main` already contains both reviewed commits, so the pre-change
  parent is the meaningful red baseline.
- `timeout 90 cargo build --offline --locked -j3`: passed. With
  BENNETT_ESTIMATE_BIN pointing to that job-local debug binary,
  `timeout 180 python3 -B -m unittest discover -s tests -p test_estimate.py -k differential_rung3_and_rung2_inventory -v`:
  1 passed in 26.005 s, including the new private-workspace fixture and all
  ten complete CC-program resource comparisons against the gate-pinned VM.
- `timeout 30 python3 -I -B scripts/quality_ratchet.py`: no regression.
  Plan items 9–11 checked: gate.toml invokes the recorded metric/hygiene
  ratchet; HANDOFF.md is retired and README points to the ecosystem handoff;
  every COMMON anti-slop rule was checked. No additional blocker found.

**Coverage:** read closely: all eight changed paths, final cleanup partition,
selection/replay, empty-cleanup and identity proof code, touched tests and
differential, pinned ISA §6/§11 K62/K65/K80/K81, ratchet and retirement wiring;
skimmed: surrounding pre-existing source/ledger machinery and unchanged docs.
Tests have independent literal/spec expectations; none were weakened or skipped.

**Provenance:** implementer gpt-6.1-sol; reviewer gpt-6.1-sol, fresh session (D9).
