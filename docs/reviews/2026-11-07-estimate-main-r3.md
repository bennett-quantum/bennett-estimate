# Estimate main review, round 3

**Verdict: BLOCK. P0: none. P1-1: `bennett-estimate-tdf`.**

Reviewed fix range `16ebd9e..54f98f9` (`ecc38f7`, `9a4e7a8`,
`54f98f9`) at exact head
**`54f98f9876a28ee9428b6183ad81ce3ed3677976`**, on
`job/quality-estimate`. Read the full `main..job/quality-estimate` log
and range summary; closely reviewed the round-2 fix and its dependencies.
The referenced `estimate-main.md` remains absent; read `sol-estimate.md`,
as in earlier rounds.

The earlier P0 `bennett-estimate-yak` is fixed for both confirmed witnesses:
the `cx d y` interleaving now fails naming `entry:4 (cx)`, and the
unrestored replay-input write fails naming `entry:5 (x)`. Independent scalar
replay of actual gate operands at the pre-fix head reproduces 4/8 differing
outputs and 4/4 dirty releases, respectively. Both round-1 disjoint
placements remain accepted with their literal K80/K81 leaf, operand,
resource and all-basis expectations, forward and raw inverse. The earlier
operand-trace nit is repaired. No accepted semantics mismatch was found
in the reviewed head's directed cases.

**P1-1 — restored replay inputs are incorrectly forbidden**
(`src/estimate.py:3504`, enforced at `:3514`;
bead **`bennett-estimate-tdf`**). The new obstruction predicate rejects
every intervening write to a replay input, including a write whose exact
matched inverse restores that input before cleanup. This narrows valid
recompute schedules. ISA 0.9 §6.2 explicitly permits a permutation input
change undone by a matched pair when intervening operations leave the
input and g unchanged. K81 requires matching to restore captured entry
versions, and says the partition adds no source-program restriction.
An unconditional ban on input writes does not implement those conditions.

Make x mutable and insert two adjacent `x x` rows between K80's inverse
CXs. They restore x's exact entry version; neither reads or changes d.
Reverse and recompute both implement identity on x,z and release all
scratch clean on **4/4 basis inputs**, in **both traversal directions**,
as verified by a separate scalar interpreter of the actual emitted
`Ledger.gate` identities/offsets. Pre-fix `16ebd9e`, loaded in memory,
accepts this exact recompute (gates/time 9, peak 4, area 32). The reviewed
head preserves reverse but rejects recompute at the first X. Recognize
restored input histories while retaining the unsafe-interleaving checks;
add this missing regression.

Reproduced headless from this worktree with `timeout 60 python3 -B -`;
minimal refusal input:

```python
import sys
sys.path.insert(0, "tests")
from test_schedule import *
sig = {"abi":"0.9", "tier":"q", "kind":"perm_action", "mut":[1],
       "in":[1], "mem":[], "args":[], "bounds":[]}
obj = make_object("""perm_action @root (x:wire) (z:wire in) () () ()
^entry():
d = qalloc any 1
cx x d
cx z d
cx z d
x x
x x
cx x d
qfree d""", sig)
t = target()
doc = e.estimate(obj, t, "root", [], ["0"]*4)["effective_schedule"]
doc["entries"] = [entry("cleanup", path=[point(
    obj.symbol("root")["interface_hash"], "entry:7")],
    realisation="recompute")]
obj.sections["schedule"] = doc
e.estimate(obj, t, "root", [], ["0"]*4)
# ContractError: source cleanup-pair recompute crosses non-disjoint row entry:4 (x)
```

**P2+ nits:** `bennett-estimate-rjn` (P3 aggregate): carry-forward opcode-category duplication, existing owner `bennett-estimate-c4p`, at `src/estimate.py:3405/:3455/:3463/:4273/:4348`; no additional demonstrated bug.

**Verification:** DISPLAY, WAYLAND_DISPLAY, DBUS_SESSION_BUS_ADDRESS and
BROWSER unset; job-local `TMPDIR` and `CARGO_TARGET_DIR` under
`.tmp/rev-estimate-main-r3/{tmp,target}`. Focused only:

- `timeout 120 python3 -B -m unittest discover -s tests -p test_schedule.py -k test_k8 -v`: 2 tests, all 16 fixture/direction subcases passed.
- Same focused command with `-k cleanup`: 8 passed; with `-k primitive`: 4 passed.
- `timeout 90 python3 -B -`, loading source from `git show` in memory:
  current K80/K81 tests pass at HEAD; main rejects all four disjoint
  direction subcases, and its K81 failures are diagnostic differences;
  `16ebd9e` accepts the unsafe input/output interleavings, so the new
  rejection assertions fail there. No branch switches or checkout edits.
- `timeout 90 python3 -B -`: independent scalar actual-operand replay
  reproduces both prior P0 witnesses, then checks eight CX/CCX/MCX/qxor
  interleaving patterns across all basis inputs, with/without inherited
  controls and forward/raw traversal; accepted reverse/recompute outputs
  agree and all releases are clean.
- `timeout 60 python3 -B -`: P1-1 all-basis scalar replay and head refusal,
  described above.
- `timeout 30 python3 -I -B scripts/quality_ratchet.py`: no regression;
  `git diff --check 16ebd9e..54f98f9`: passed. No full gate, sibling gate,
  Rust suite or VM differential rerun.

**Coverage:** read closely: complete source/test fix diff, partition,
version matching, obstruction predicate, cleanup choice/replay and lowering
wrappers, previous reviews, laws, and gate-pinned ISA §6.2/§6.4/§11 K80/K81
at `fd626d37aba1f719c3b7b2059be46cbfaf462886`; skimmed: unchanged
surrounding source/ledger machinery and quality-document diff. Checked every
COMMON anti-slop rule: tests strengthened with independent expectations,
no weakened/skipped tests, new silent defaults, process identifiers or
tracked litter found. Plan items 9–11 were checked in round 1.

**Provenance:** implementer gpt-6.1-sol; reviewer gpt-6.1-sol fresh session, D9.

