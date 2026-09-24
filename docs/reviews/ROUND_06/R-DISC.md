# R-DISC — Round 6 verification (R-DISC-009, R-DISC-008/R-ARCH-014)

**Reviewer:** R-DISC (fresh instance; did not write this code or `HANDOFF.md`). 2026-08-31.
**Method:** execution only (`AGENT_LOOP.md` §4/§7). Baseline reproduced independently in
`/root/mailweave`: `ruff check`/`format --check`/`mypy` clean (62 files), `pytest -m "not
network"` → **656 passed**, 7 guards clean, `rubric_status.py --check` → 8 PASS / 105 NOT
TESTED / 10 transitions — matches `HANDOFF.md` exactly. All reintroduction/restore work was
done in a **wiped-and-resynced scratch copy** (`.venv`/caches deleted, `uv sync`, editable
install verified to resolve inside the scratch tree, diffed byte-identical against
`/root/mailweave` before use) per the prior reviewer's stale-install warning — the live tree
was never left modified. Probes in `scratchpad/rdisc6/`.

**Operational note.** One tar snapshot of the live tree, taken moments after a full green
run, briefly captured `reasons.py` with `ThreadMember.render()`'s two fields swapped, while
`/root/mailweave`'s own copy (re-checked immediately, both before and after) was correct and
stable across two full-suite reruns. Almost certainly a filesystem race on my snapshot, not
a code defect — the live tree was never observed wrong — but noted because it briefly
produced a false "R-ARCH-018 regressed" signal from a scratch copy, which is exactly the
failure mode the prior reviewer's warning exists to catch. A second snapshot matched exactly.

## Verdicts

| Finding | Verdict | Evidence |
|---|---|---|
| R-DISC-009 cross-thread withheld-record borrowing | **CLOSED** | original repro raises; 6 independent attack routes all held; reintroduction breaks ≥7 tests incl. both property tests |
| R-DISC-008 / R-ARCH-014 stale A4 docstring | **CLOSED** | §D.2 reads `included: 42`; both docstrings cite A4; propagation test fails-first on reintroduction |

## R-DISC-009 — attacked by every route in the brief

**Original reproduction, re-run.** `probe_repro.py` rebuilds R-DISC's exact case (4 real ids
for t1, `t2-only` for t2, `note_withheld` no longer accepting a thread argument at all).
Raises `DispositionInvariantError` naming `t2-only`. **Confirmed closed.**

**Route 1 — thread via the observation, not the note.** Minted a `FetchedIds` for an id
(`fab5`) nothing really fetched, under `thread_id="t1"`, via the *public* constructor
(`probe_route1_fabricated_observation.py`). **This still builds.** It is the residue
`FetchedIds`'s own docstring names — an observation can claim ids nothing fetched, and can
therefore claim threads nothing observed — and it is explicitly out of scope (A1's content
witness). Confirms the disclosed docstring is accurate, not a new gap.

**Route 2 — an id observed under two threads.** All four combinations (`threads.get` ×2,
`messages.list`→`threads.get`, reverse, `history.list`→`messages.list`) **raise**, naming
both disagreeing threads (`probe_route2_two_threads_disagree.py`).

**Route 3 — hand-built `WithheldRecord` attached directly.** (a) Forging the thread on an
otherwise-real certified record and reattaching it to the same certificate: **raises**
("rewritten after certification"). (b) A wholly invented id/record with no ledger backing:
**raises** at the id-set check, before the whole-record compare is even reached
(`probe_route3_hand_built_record.py`).

**Route 4 — exploiting the whole-record compare.** (a) A *non*-`map_id` source claiming
another thread's withheld id via `withheld_here`: **raises** — `_map_accounting_is_backed_
by_real_withheld_records` (`response.py:152`) applies regardless of `map_id`, so this path
was never map-only. (b) Tampering only a nested field (`affordance.args`) while leaving
top-level `id`/`thread_id`/`cap`/`why` untouched: pydantic equality is a real recursive value
compare (`tampered == rec` → `False`), and the mutation is caught
(`probe_route4_whole_compare.py`). No way found to match wholly and still be wrong.

**Route 5 — id observed under no thread.** `note_withheld` + `certify` **raises**, naming the
id and the endpoint that recorded no `threadId`; the same ledger certifies cleanly when both
ids are disclosed instead (`probe_route5_no_thread.py`).

**Route 6 — `threads.get` vs. listing endpoints, separately.** Five constructor-level attacks
(thread for an unreturned id, partial map on `messages.list`, partial map on `history.list`,
`threads.get` carrying both `thread_id` and a per-id map, `threads.get` with no thread at
all) **all raise** with the documented fragment (`probe_route6_endpoints.py`).

**Reintroduction, independently performed.** In the scratch copy: `_record_for` changed to
take *any* observed thread (first non-`None` thread found in `self._origins`, not the id's
own) → **8 tests fail**: the 5 named in `HANDOFF.md`
(`test_a_cap_that_records_its_reason_produces_a_derived_withheld_record`,
`test_a_map_cannot_account_for_itself_with_another_threads_withheld_message`,
`test_the_thread_on_a_withheld_record_is_the_one_the_observation_recorded`,
`test_the_same_derivation_holds_for_an_id_observed_through_a_listing_page`,
`test_a_withheld_record_rewritten_after_certification_is_refused`), both property tests, and
**one HANDOFF did not enumerate** — `test_envelope_serialisation.py::test_the_withheld_
record_carries_its_cap_reason_and_executable_call`, which asserts the record's `thread_id`
matches its own `affordance.args.thread_id`; a two-thread fixture makes this fail too once
"any thread" is wrong. **7 vs. 8 is a HANDOFF undercount, not a code defect** — restored
byte-identical, verified clean. Separately, neutering the envelope-side whole-record compare
back to an id-only check reproduces exactly the claimed single failure
(`test_a_withheld_record_rewritten_after_certification_is_refused`, `DID NOT RAISE`).

**Property test alphabets, checked, not trusted.** `message_ids = [a-z0-9]{1,8}` (lowercase/
digits only) and `thread_ids = T[A-Z]{1,4}` (all-uppercase) are disjoint by character class,
confirmed by 5,000 generated pairs with zero overlap. Both property tests re-run clean on
three reviewer-picked fresh seeds (`20260831`, `314159265`, `999999937`).

## R-DISC-008 / R-ARCH-014 — propagation, verified rather than read

`ARCHITECTURE_DECISION.md:1069` reads `"included": 42` with an inline `AMENDED by A4`
comment; `wire.py:518` cites A4 by name; the pinning test's docstring
(`test_envelope_contract.py:1528`) states the ruling exists. The new
`test_the_ruling_is_visible_everywhere_the_amendment_says_it_changed` reads both markdown
files and both docstrings and asserts all four. **Reintroduced the exact round-5 wording**
in the scratch copy's `wire.py` docstring (restored round-1-handoff phrasing, no "A4"
mention) — the propagation test fails with `"a reader here is not told the question was
settled"`; the pinning test itself is unaffected, matching the claimed failure isolation.
Restored, diffed clean.

## §4 — New findings

```
ID:            R-DISC-011
Severity:      HIGH
Rubric:        PART-05, contract R-06
Location:      wire.py:311 (MessageRow.thread_id, unconstrained); wire.py:566-571
               (Source._counts_match_the_payload — checks row.thread_id == self.thread_id
               only, never against HitOrigin); disposition.py:710-712 (.origins — read
               nowhere outside disposition.py); builder.py:76-77 (add_source — no check)
Reproduction:  probe_disclosed_side_borrowing.py — t1 genuinely observed with 3 ids
               (a1,a2,a3); a real, distinct id x1 genuinely observed under thread t5 via a
               real threads.get (kit.observed_thread(["x1"], "t5")). Built a map_id-bearing
               Source(thread_id="t1", stated_total=4, messages=[a1,a2,a3,row(x1,
               thread_id="t1", position=3)]). The row simply asserts thread_id="t1"; nothing
               reads HitOrigin["x1"].thread_id ("t5") to check it.
Expected:      Round 6 derives a withheld record's thread from HitOrigin so a map cannot
               borrow another thread's message to reach completeness (R-DISC-009). The same
               guarantee is expected for a DISCLOSED row: PART-05 requires that "wherever a
               thread map is present, every message of that thread appears" — a message
               genuinely observed under a different thread is not a message of this thread.
Actual:        Builds cleanly. env.sources[0].accounted_for == stated_total == 4,
               env.partial == False. The response asserts thread t1's map is complete using
               x1, a real message that was never part of t1 — the disclosed twin of the
               exact bug R-DISC-009 closed on the withheld side. Not adversarial-only: a
               caller bug that puts a real cross-thread context/reply row under the wrong
               source produces this silently, identically to R-DISC-009's original framing.
Required fix:  Apply the same derivation used for withheld records to disclosed rows: a
               MessageRow's thread_id must equal HitOrigin[row.id].thread_id whenever an
               origin with a recorded thread exists (checked in an Envelope-level validator,
               since Source has no ledger access) — or, if the row's id was never observed
               with a thread at all, refuse it in a map_id-bearing source the same way
               _record_for refuses an unthreaded withheld id.

ID:            R-DISC-012
Severity:      LOW
Rubric:        none — HANDOFF claim precision (AGENT_LOOP §7 rule 7 spirit)
Location:      docs/reviews/ROUND_06/HANDOFF.md, R-DISC-009 section, "Failing-test-first"
Reproduction:  Independently reintroduced the described defect (_record_for takes any
               observed thread) in a resynced scratch copy; full suite → 8 failures, not 7
               (see execution record above).
Expected:      A stated test-breakage count for a verified fix is exact.
Actual:        HANDOFF names 7 failing tests; an 8th genuinely fails under the same
               reintroduction (test_envelope_serialisation.py::test_the_withheld_record_
               carries_its_cap_reason_and_executable_call). Does not change the CLOSED
               verdict — more of the suite protects the invariant than claimed, not less.
Required fix:  None functional; a future HANDOFF listing a reintroduction blast radius
               should re-run the full suite rather than the targeted files.
```

## What an agent actually sees (field order, rebuilt against Round 6 code)

`build_realistic_r6.py`: a decision-thread source (3 messages, `stated_total=3`, complete)
plus a capped second thread (`t2-only` withheld, `max_hit_threads`), `outcome=inconclusive`
with an untried `L6`. Byte offsets in the real JSON (3,251 bytes total): `partial` **258**,
`withheld` **273**, `retrieval_report` **499**, `sources` **1119** (34% in). The withheld
record correctly carries `"thread_id":"t2"` — the observed thread, never a borrowed one.
**Round 5's field-order improvement survives Round 6's changes unchanged.**

## Execution record

```
make-equivalent (ruff/format/mypy/guards/gate)     → clean; matches HANDOFF exactly
pytest -m "not network"                            → 656 passed (re-run twice, stable)
probe_repro.py                                      → RAISED (original repro closed)
probe_route1_fabricated_observation.py              → BUILT (acknowledged A1 residue, not new)
probe_route2_two_threads_disagree.py                → 4/4 combinations RAISED
probe_route3_hand_built_record.py                   → 2/2 forged/fabricated records RAISED
probe_route4_whole_compare.py                       → 2/2 RAISED; whole-record compare sound
probe_route5_no_thread.py                           → RAISED; clean when disclosed instead
probe_route6_endpoints.py                            → 5/5 constructor attacks RAISED
probe_disclosed_side_borrowing.py                   → BUILT (NEW: R-DISC-011)
probe_disclosed_wholly_fictitious.py                → BUILT (A1's existing residue, disclosed side)
Scratch-copy reintroduction (_record_for, "any thread")   → 8 tests fail (HANDOFF claimed 7)
Scratch-copy reintroduction (response.py record compare)  → 1 test fails, exactly as claimed
Property-test alphabet disjointness                 → 5,000/5,000 generated pairs, zero overlap
Property tests on 3 fresh seeds                     → clean (20260831, 314159265, 999999937)
test_the_ruling_is_visible_everywhere... reintroduction   → fails as expected; pinning test unaffected
build_realistic_r6.py                               → partial@258, withheld@273, sources@1119/3251
```
All probes: `scratchpad/rdisc6/`. Every scratch-copy reintroduction restored and diffed
byte-identical before the next step; `/root/mailweave` itself was never edited by this
review. Post-probe full suite in `/root/mailweave`: 656 passed, clean.

## Criterion recommendations

| Criterion | Recommendation | Why |
|---|---|---|
| PART-05 | **Not promotable — same blocker class, new location** | R-DISC-009's withheld-side borrowing is closed; R-DISC-011 shows the identical borrowing still open on the disclosed side of a `map_id`-bearing source. Do not promote until a disclosed row's thread is derived from `HitOrigin` the same way a withheld record's is |
| PART-07 | **Unchanged from Round 5: structural (P4) half ready, full PASS needs P6** | Nothing in this round's diff touched `reasons.py`/role-reason correctness; `test_reason_coverage.py` re-verified green in the live tree. P6 (live selection-provenance labelling) remains the sole blocker, unrelated to R-DISC-009's fix |
