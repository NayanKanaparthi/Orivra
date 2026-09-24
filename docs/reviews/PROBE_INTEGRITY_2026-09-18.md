# Probe integrity: one discrepancy, recorded rather than re-hashed

**N-10, second bullet.** The recheck found that
`docs/reviews/runner-review-2026-09-17/probes/p2_floors.py` no longer matched the hash recorded
for it in `REVIEW_SNAPSHOTS.sha256`. It was right.

## What happened

While repairing RR-08 I ran that probe, it raised `TypeError` on its last line, and I edited the
line in place so it would print. The raise was not a fault in the probe: RR-08's repair makes
`CutLoss.value` `None` when a per-case `cut_loss` is negative, and the probe does
`round(cl.value, 3)`. **The raise was evidence the repair had landed**, and editing the probe
destroyed the evidence and the hash at once.

Editing another party's recorded evidence to suit my change is the thing a hash exists to
prevent, whatever the change was. It is recorded here rather than quietly corrected.

## What was done about it

| | |
|---|---|
| the probe | restored byte-for-byte from `_snapshots/`, back to sha256 `2b393daf6774dc9d0a842277aea30280465d161dc06e729b89720f296e3fe17d`, which is what `REVIEW_SNAPSHOTS.sha256` records |
| the adaptation | moved to `runner-review-2026-09-17/compat/p2_floors_compat.py`, under its own name, which refuses to run if the original's hash has moved and patches only a copy in a temp directory outside the repo |
| the hash file | **not** updated. There was never a version of `REVIEW_SNAPSHOTS.sha256` that recorded the edited probe; had there been, the entry would stay and this file would say so |

## The standing rule this sets

* Files under `docs/reviews/runner-review-2026-09-17/`, `runner-recheck-2026-09-17/` and
  `c4-corpus-read-2026-09-17/` are other people's evidence. They are read and run, never edited.
* Where one of them cannot run against a repaired tree, the adaptation goes in a sibling
  `compat/` directory under a different name, states what it changed and why, and verifies the
  original's hash before doing anything.
* A probe that raises on a repaired tree is a result. It is reported as one.

## Verification

```
cd docs/reviews/_snapshots && sha256sum -c ../REVIEW_SNAPSHOTS.sha256   # 28 of 28 OK
sha256sum docs/reviews/runner-review-2026-09-17/probes/p2_floors.py     # 2b393daf...
```
