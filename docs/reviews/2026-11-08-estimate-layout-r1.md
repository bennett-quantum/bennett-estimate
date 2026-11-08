# Estimate layout review, round 1

**Verdict: CLEAR. P0/P1: none.**

Reviewed `main..job/estimate-layout`, base
`6e2cabf65a72ed04cdbfeaa32f1bcd18c7e931ad`, exact implementation head
**`d6cab23d47ba2df32ce16eb74b6e346c3183e30c`** (one commit; all three
changed files reviewed). Provenance: implementer gpt-6.1-sol; reviewer
gpt-6.1-sol, fresh session (D9).

The layout candidate enters the existing validation loop before the cache
candidates. Every selected candidate still checks the full revision and
configured file hashes; a mismatch or missing pinned file cannot fall back.
Unset/empty/missing layouts retain the existing candidate order, and an
exhausted search names every candidate. Live branch HEAD and wrong detached
HEAD are rejected, including when a valid fallback exists.

Verified the original failure using the implementer's existing actual Git
worktree at `.tmp/estimate-layout/e2e/gate-root/.tmp/gate/runs/run/bennett-estimate`:
its HEAD matches the reviewed SHA, its commondir points to `e2e/main`, and
neither that checkout nor the run checkout contains a pin cache. The layout
symlink reaches the exact targets pin. Loading `git show main:scripts/pinned.py`
in memory makes the unchanged large-coordinate selector fail with the
original missing-pin error; restoring the head resolver makes it pass.
No new worktree, branch switch, production edit or gate run was needed.

Focused verification, headless with job-local TMPDIR/CARGO_TARGET_DIR under
`.tmp/rev-estimate-layout-r1/{tmp,target}`:

- `timeout 30s python3 -I -B -m unittest discover -s tests -p test_pinned.py -v`: **7 passed**, 0.17 s wall.
- From the existing run worktree, with its absolute `BENNETT_GATE_LAYOUT`,
  `timeout 30s python3 -I -B -m unittest discover -s tests -p test_schedule.py -k test_large_source_coordinates_have_distinct_ordinals_and_lossless_keys -v`: **1 passed**, 0.47 s wall.
- `timeout 30s python3 -B -`: independent in-memory main/head selector
  comparison above passed (0.28 s); supplementary fixture probes passed
  **13 assertions** for relative layouts, missing paths, regular-file,
  whitespace and garbage-style values, revision/hash checks and diagnostics
  (0.11 s).
- `timeout 30s python3 -I -B scripts/quality_ratchet.py`: **no regression**, 0.74 s.
- `timeout 30s cargo fmt --check`, `timeout 30s cargo clippy --offline --locked -j3 --all-targets -- -D warnings`,
  and bounded shell syntax / `git diff --check main...job/estimate-layout`
  checks passed (0.06 / 0.32 / 0.00 s).

Read the implementation's red/green/default-suite/static evidence; the
default suite and full gate were not rerun in this focused review. The
seven added tests are included by the existing default discovery runner.
Their literal fixtures and independently computed hashes can detect the
claimed failures; no assertion was weakened, skipped or deleted.

**P2+ nits:** aggregate P3 bead **`bennett-estimate-0lh`**: retain permanent relative/malformed-layout regression cases at `tests/test_pinned.py:85`; reviewer probes pass today. No repair round required.

**Coverage:** read closely: full diff, resolver and tests, main-side resolver,
gate layout/materialisation, test discovery and affected baseline rows;
skimmed: historical quality/review evidence and surrounding gate tooling.
Checked every COMMON anti-slop rule: no new hidden bug class, silent default,
process identifier, needless wrapper, long semantic function or tracked litter.
No north-star capability was narrowed. Plan items 9–11: `gate.toml` retains
the single quality ratchet, only the two affected baseline rows changed,
HANDOFF.md is absent, and README points to `bennett/HANDOFF.md`.
