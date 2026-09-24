# R-DISC — Round 7 verification (R-DISC-011, the two audit-found instances, stated_total, A6)

**Reviewer:** R-DISC (fresh instance; did not write this code or `HANDOFF.md`). 2026-08-31.
**Method:** execution only (`AGENT_LOOP.md` §4/§7). Baseline reproduced in a **wiped-and-resynced
scratch copy** (`scratchpad/rdisc7/`, diffed byte-identical to `/root/mailweave` before use):
`.venv`/caches deleted, `uv sync --all-packages --extra dev`, `mailweave.__file__` confirmed
inside the scratch tree before trusting any result. `ruff`/`format --check`/`mypy --strict`
clean (62 files), `pytest -m "not network"` → **775 passed** (stable across re-runs), 7 guards
clean, `rubric_status.py --check` → 8 PASS / 105 NOT TESTED / 10 transitions — matches
`HANDOFF.md` exactly. `RELEASE_RUBRIC.md`, `FINDINGS_LEDGER.md`, `RUBRIC_TRANSITIONS.md` diffed
unchanged, per the work order's constraint. Probes in `scratchpad/rdisc7/probes/`; every
reintroduction applied there, sha256-diffed byte-identical after restore, followed by a clean
full-suite re-run.

## Verdicts

| Finding | Verdict | Evidence |
|---|---|---|
| R-DISC-011 cross-thread disclosed-side borrowing | **CLOSED** | original repro raises naming x1/t5/t1; every route in the brief (row, collapsed run, unthreaded id, mixed-thread map, non-map source, all 4 endpoint pairings) raises; reintroduction breaks exactly the 7 tests HANDOFF claims |
| `ThreadMember.thread_id`/`.position` unchecked | **CLOSED** | both halves independently exploitable pre-fix by construction; both raise now; reintroduction breaks exactly 2 |
| `hit_count_per_rung` never compared | **CLOSED** | parameter genuinely absent from `build`'s signature; envelope-level mismatch and missing-rung checks both raise; reintroduction breaks exactly 2 (envelope) + 30 (builder) |
| `stated_total` bounded below | **CLOSED, as scoped** | isolated from the two pre-existing checks that could mask it; boundary-exact case passes, understate-by-one raises; reintroduction breaks exactly 1 |
| Field order (`partial`/`withheld`/`retrieval_report` before `sources`) | **HOLDS** | rebuilt realistic partial envelope: bytes 258/273/446 of 3667, `sources` at 785; no `computed_field` on any `Envelope` field |
| **The class, closed by field-level derivation alone** | **NO — confirmed by execution, not just by argument** | see "the eighth instance" below |

## R-DISC-011 — every route in the brief, executed

**Original reproduction, rebuilt verbatim.** t1 observed with a1/a2/a3 (real `threads.get`),
x1 genuinely observed under t5 via a separate real `threads.get`, `map_id` set,
`stated_total=4`. Raises `DispositionInvariantError` naming x1, t5 and t1. **Confirmed closed.**

**Collapsed run instead of a row.** a1 real under t1; x2/x3 real under t9; t1's map declares a
collapsed run at positions 1–2 with `member_ids=(x2, x3)`. **Raises**, naming both borrowed ids —
the disclosed check reads `source.disclosed_ids`, which already unions collapsed-run members, so
this was never a separate code path to miss.

**An id observed under no thread at all.** `messages.list` page with `thread_ids=None`; placed
into a `map_id` source. **Raises**: "a thread map counts messages no observation placed in its
thread" — the disclosed twin of `_record_for`'s refusal, confirmed live.

**Non-map source, same borrowing.** The docstring reads as if only a `map_id` source is checked
for the "thread disagrees" case; the code checks it unconditionally. A plain search view
disclosing x1 (real, observed under t5) under `thread_id="t1"` **still raises** — stronger than
the prose suggests, a genuine safety margin against the caller bug the docstring names.

**Mixed threads within one map.** A single map for t1 carrying a1 (real, t1), x1 (real, t5), y1
(real, t9) and z1 (real, no thread). **Raises**, naming x1 and y1 together.

**`threads.get` vs. listing endpoints, all four pairings.** (own-thread endpoint × borrowed-thread
endpoint) `threads.get`×`threads.get`, `threads.get`×`messages.list`, `messages.list`×
`threads.get`, `messages.list`×`history.list`: **4/4 raise**, same message shape each time — the
check reads `HitOrigin.thread_id` regardless of which endpoint wrote it.

**Serialisation-time write.** `Source._rows_carry_this_sources_thread` (a `field_serializer`,
not a `computed_field`, so field order is unaffected) writes `self.thread_id` — the Source's own,
already-validated field — onto every row at dump time, in both `python` and `json` modes.
`MessageRow` has no `thread_id` parameter (`'thread_id' not in MessageRow.model_fields`,
confirmed), so there is no second value it could disagree with. A bare `Source.model_dump()`
outside an `Envelope` is unreachable from any production code path (`Source(` constructed nowhere
outside `envelope/wire.py`, `envelope/builder.py` and tests) — the only shippable artifact is an
`Envelope`, and every `Envelope` runs the full validator chain. **No route found for the
serialised value to disagree with the certificate.**

**Reintroduction, independently performed.** Neutering `_disclosed_rows_sit_in_the_thread_
they_were_observed_in` → `return self`: **exactly 5 tests fail** (4 in
`test_disposition_invariant.py`, 1 property test) — matches `HANDOFF.md`. Giving `MessageRow`
back a `thread_id` field → **exactly 2 fail**, and the failure mode is instructive: the
`field_serializer`'s `dumped.items()` update clobbers the source-derived value with the row's own
(`None`), silently wrong rather than merely re-askable — the field must stay removed, not
re-checked, if anyone is tempted to bring it back.

## `ThreadMember.thread_id` / `.position` — the first audit-found instance

Pre-fix, both are independently constructible: a row at position 3 with
`reason=ThreadMember(thread_id="t9", position=41)` builds cleanly (verified by neutering both
checks and re-running: `MessageRow(...)` and `Source(...)` both build with no error). Post-fix,
both raise at construction — the position lie at `MessageRow`, the thread lie at `Source` (the
only layer that knows it). Reintroducing both checks together: **exactly 2 tests fail**, matching
`HANDOFF.md`.

## `hit_count_per_rung` — the second audit-found instance

`inspect.signature(EnvelopeBuilder.build)` confirms `hit_count_per_rung` is genuinely absent —
not defaulted, not optional, gone. Constructing an `Envelope` directly (bypassing the builder)
with a `RetrievalReport.hit_count_per_rung` that disagrees with the ledger's own count **raises**,
naming the rung and both numbers. Reintroducing `EnvelopeBuilder.build` to emit `(0, 0, …)`:
**exactly 30 tests fail** (matches HANDOFF). Neutering only the envelope-level check: **exactly
2 fail** (matches HANDOFF) — one for a misstated value, one for a rung that admitted ids and is
missing from `rungs` entirely. A rung that ran and found nothing (`RungId.L0` in the fixture)
still reports `0` and is not flagged — the "rungs stays a parameter" design holds under test.

## `stated_total`, bounded below — isolated and boundary-tested

Two pre-existing checks (`included <= stated_total`; the "phantom remainder" rule for a source
reporting itself complete while holding withheld records) can each independently catch an
understated `stated_total`, which risks the round-7 check looking tested when it is merely
shadowed. Constructed a case that evades both — an **incomplete**, non-map source, locally
consistent (`included=1 <= stated_total=2`), while the thread's true global observed count is 3
(the other two withheld, closing the phantom check's "else" branch) — and confirmed the round-7
check is what fires: *"source t1 states the thread holds 2 messages, but 3 distinct messages
were observed in it."* Boundary: `stated_total == seen` builds; `stated_total == seen - 1`
raises. Reintroduction: **exactly 1** fails, matching HANDOFF.

**Interaction with A3 at the boundaries.** With `stated_total` at the observed floor, a row at
`position == stated_total` (one past the last valid index) raises A3's existing check regardless
of the new one; `position == stated_total - 1` builds. The two checks compose correctly — A3
bounds *where* a position sits inside a thread of the stated length; the round-7 check bounds
*how short* that stated length may honestly be. Neither substitutes for or weakens the other.

## Priority — the eighth instance and amendment A6

**Confirmed buildable, by two routes, both already declared and already tested by the
implementer — not a Round-7 regression.**

1. A `MessageRow` for an id that never entered `H` at all (no `FetchedIds` ever admitted it).
   The disclosed check explicitly skips ids absent from `observed_threads` — by design, per its
   own docstring, because a legitimately-fetched parent/context row outside any recorded
   retrieval is real. `test_a_row_for_an_id_that_never_entered_the_hit_set_is_left_alone`
   already exists in the shipped suite, named exactly as "A1's residue, stated as a test rather
   than as prose." My probe reproduces it: t1 genuinely has 2 real messages; a third row for
   `"ghost123"` (never fetched by anything) is added, `stated_total=3`, `map_id` set. **Builds.
   `accounted_for == stated_total == 3`, `partial=False`.**
2. The same thing through the other open door: `FetchedIds(ids=[...], endpoint=THREADS_GET,
   thread_id="t1")` constructed directly (an ordinary public constructor — A1's residue,
   documented in `disposition.py`'s own docstring since round 3) with a fabricated id folded in.
   Also builds, also `partial=False`.

**Sharper construction: does a correct-looking `stated_total` defend against this?** No. Set
`stated_total` to the *exact* true global count (3), disclose 2 of the 3 real ids plus one
fabricated filler inside the `map_id` source, and disclose the 3rd real id honestly but in a
**separate**, non-map `Source` for the same thread. Every existing check — global bound-below,
local map-accounting total, per-source thread match — passes; none checks *set identity* between
a map's own membership and the ledger's enumeration, only counts and non-contradiction. **Builds**:
the map reports 3-of-3; an agent trusting it alone sees a complete map missing a real message and
containing one that does not exist. Notably, I could **not** get this to succeed with only real,
unfabricated ids: the global bound-below check forces every source naming a thread to declare
`stated_total` at least the true count, and the local map-accounting check then forces that
source's own `accounted_for` to reach it — a real message can only be dropped from a map's own
count by filling its slot with something fabricated. Without fabrication, the round-7 fixes make
map-completeness airtight in everything tried.

**Verdict on the class.** Every attack not requiring a minted id or observation is closed. Every
attack that does succeeds unconditionally, because nothing running inside this process can tell
a real Gmail response from a fabricated one — not because the implementer missed a spot, but
because the claim being checked and the thing checking it are the same untrusted process. **A6
narrows the class of fields with nothing to derive from** (`stated_total`, `position`,
`internal_date`, …) but does not by itself stop fabrication: a caller that can fabricate today's
smaller seal can fabricate A6's larger one identically. Only **A1** (a witness *outside* the
process) closes the fabrication route both successful constructions used. **Build A1; adopt A6
alongside it, not as a substitute for it.** Not a new §4 finding: the same, already-declared,
already-tested residue, executed rather than argued.

## §4 — New findings

None survive verification. Every requested attack route is closed by execution; the one
successful construction is the pre-declared, pre-tested A1 residue addressed above, not a defect
introduced or missed by this round's diff.

## Execution record

```
scratch resync + ruff/format/mypy/guards (server,tests,tools,harness)   clean; matches HANDOFF
pytest -m "not network"                                                 775 passed (3x, stable)
7 attack probes (borrowing: row/collapsed-run/unthreaded/non-map/mixed/4 endpoint pairs)  all RAISED
probe_threadmember_checks.py, probe_hit_count_per_rung_mismatch.py      both RAISED
probe_stated_total_boundaries.py + isolated2.py                        boundary correct, isolated RAISED
build_realistic_r7.py                                                  partial@258 withheld@273 sources@785/3667
3 eighth-instance probes (fabricated row / observation / exact-count ghost)   all BUILT (declared residue)
property test, 5 fresh seeds (20260831/314159265/999999937/42/1337)    clean, all
alphabet disjointness, independently sampled                           5,000/5,000 pairs, 0 collisions
```

| Reintroduction | Observed | HANDOFF claimed |
|---|---|---|
| `_disclosed_rows_...` → `return self` | 5 fail | 5 |
| `MessageRow` regains `thread_id` | 2 fail | 2 |
| `_stated_total_is_not_below_...` → `return self` | 1 fails | 1 |
| both `ThreadMember` checks neutered | 2 fail | 2 |
| envelope-level `hit_count_per_rung` check neutered | 2 fail | 2 |
| `build` emits `(0, 0, …)` | 30 fail | 30 |

All performed in `scratchpad/rdisc7/`, sha256-diffed byte-identical to the untouched original
after each restore. `/root/mailweave` itself was never edited; full suite re-checked clean
(775 passed) after the last restore.

## Criterion recommendations

| Criterion | Recommendation | Why |
|---|---|---|
| PART-05 | **Not promotable — same class, structurally bounded, not code-defective** | Every specific borrowing/mismatch route this round claims to fix is closed by execution. The remaining gap is not a bug in this round's diff: it is fabrication of an observation or a row, which no in-process check can ever catch. PART-05 cannot honestly reach PASS until A1's content witness exists to bound it, regardless of how much further field-level work is done |
| PART-07 | **Unchanged: ThreadMember's reason-vs-payload check strengthens it, P6 remains the blocker** | The two newly-checked halves (position, thread) close a real "decorative reason wearing a mechanical shape" gap, but live selection-provenance labelling (P6) is untouched by this diff |

**On amendment A6:** worth adopting, not sufficient alone. It closes the honestly-scoped
class-O fields (`stated_total`, `position`, `internal_date`, …) that currently have nothing to
derive from, and it converges with A1's own data requirement as the amendment text itself
argues. But both of my successful eighth-instance constructions bypass class O entirely — they
fabricate a row or an observation from nothing, which a wider seal does not prevent, only a
witness outside the process does. **A1 is the one that is load-bearing for PART-05; A6 is a real
improvement riding alongside it, not a substitute for it.**
