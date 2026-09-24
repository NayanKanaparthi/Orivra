# R-RETR — Round 4 verification (R-RETR-002, amendment A2)

**Reviewer:** R-RETR (fresh instance; did not write this code or `HANDOFF.md`). 2026-08-31.
**Method:** execution only, `AGENT_LOOP.md` §4/§7. `HANDOFF.md` treated as claims, not
evidence. Baseline reproduced independently: `make check` → lint/format/mypy clean,
`pytest -m "not network"` → **406 passed**, `guards` clean, `rubric_status.py --check` →
9 PASS / 104 NOT TESTED / 9 transitions — matches `HANDOFF.md`. Round 3's own `/tmp/rretr/`
probes re-run **unmodified** against this tree. New probes in
`scratchpad/r4rretr/` (`attack_retr002.py`, `attack_a2.py`). No project source or test
modified.

## Verdicts

| Finding | Verdict |
|---|---|
| **R-RETR-002** — one position, one disposition (occupancy) | **CLOSED** — for the property the work order specifies |
| **A2** — sealed observation, `H-thr` clause, endpoint-checked intake | **CLOSED**; single-writer property preserved, tightening verified |
| **A2 seal regression?** | **No regression.** Every Round-3 attack that was blocked is still blocked. One residual, present since Round 3, now also reachable through the new clause — not new, not wider in effect |
| **Caller-asserted endpoint** | Acceptable residue under A1, not a new gap — see judgment below |

## R-RETR-002 — position occupancy, re-attacked

`Source._one_position_holds_one_disposition` (`server/src/mailweave/envelope/wire.py:492`)
computes occupancy from rows and collapsed-run spans and raises on any clash. Verbatim
round-3 two-run-same-slot shape now raises (`ValueError, "two dispositions claim the same
thread position"`), naming `position 1`.

| # | Attack | Result |
|---|---|---|
| 1 | Two runs, identical `positions=(1,5)`, disjoint ids (round-3 shape) | **Blocked**, names position 1 |
| 2 | Partial overlap `(3,5)` vs `(5,7)` | **Blocked**, names position 5 |
| 3 | Row at position 4 vs run spanning 3–6 | **Blocked**, names `message m4` and the run together |
| 4 | Abutting runs `(1,5)`/`(6,10)`, no shared slot | Builds — correct, not a clash |
| 5 | Run declares `count` disagreeing with `positions` span | **Blocked** at `CollapsedRun` construction |
| 6 | `count=0` | **Blocked** (`Field(gt=0)`); single-position run `(5,5)` count=1 builds — correct |
| 7 | Negative start `(-3,-1)` | **Builds** at the `CollapsedRun` level — see R-RETR-005 |
| 8 | Nested runs, `(1,10)` containing `(3,5)` | **Blocked** |
| 9 | Full `map_id`-bearing `Source` with a run at `positions=(900,904)`, `stated_total=5`, `accounted_for=5` | **Builds.** A "complete" 5-message map sits at positions 900–904 — see R-RETR-005 |

The property test (`tests/test_envelope_contract.py::test_a_source_that_builds_never_holds_two_dispositions_at_one_position`)
was read, not just run: it draws `(start, size)` pairs independently via hypothesis
(300 examples), so runs can overlap by construction — unlike R-RETR-001's generator, which
advanced `start` by each group's own length and could never emit this shape. It asserts
either refusal or that occupied-position-count equals claimed-message-count, and the
refusal branch is checked for cause. The end-to-end reproduction
(`test_the_two_run_same_slot_envelope_no_longer_builds_end_to_end`) runs the verbatim
Round-3 attack through a real ledger and `EnvelopeBuilder.build()`. All match `HANDOFF.md`.

**Verdict: CLOSED.** The work order's acceptance ("R-RETR's two-run same-slot envelope
raises. Property test generates position sets so nothing hands the checker the right
answer") is met exactly. **Adjacent gap confirmed, filed below as R-RETR-005**: nothing
bounds a position's *value*. Attacks 7 and 9 above are independent, executed confirmation of
what `HANDOFF.md` §6.3 already disclosed — the implementer flagged rather than hid this.

## Amendment A2 — sealed observations, re-attacked

`disposition.py`: `ObservedEndpoint` (`MESSAGES_LIST` / `HISTORY_LIST` / `THREADS_GET`),
`CLAUSE_BY_ENDPOINT`, `FetchedIds.endpoint` (required), `_admit(expected=...)`,
`DispositionLedger.record_thread`, `RecordingListTransport.get_thread`. Read in full; matches
`ARCHITECTURE_AMENDMENTS.md`'s A2 text and `docs/ARCHITECTURE_DECISION.md:406`'s `(H-thr)`.

**Round-3 attacks, unmodified, re-run:**

| Attack | Result |
|---|---|
| `/tmp/rretr/attack_h1_shortlist_hole.py` — 50 fabricated ids via `record_shortlist` | **Blocked**, `DispositionInvariantError`, names all 50 |
| `/tmp/rretr/attack_h2_via_shortlist.py` — 5 real + 37 fabricated, 5-of-42 dishonest map | **Blocked** at `record_shortlist`, before any `Source` is built |

**New attacks, this round, against the new shape:**

| # | Attack | Result |
|---|---|---|
| 1 | Bare list `["thr-1","thr-2"]` into `record_thread` | **Blocked** (`AttributeError`, `H` stays empty) — same shape the other two intakes already reject; consistent, not a new hole |
| 2 | Subclass `FetchedIds`, override `_release` to ignore `_RECORD_TOKEN`, feed into `record_thread` | **Bypasses the token**, as it does for `record_list_page` since Round 3 — documented residual, unchanged by A2 |
| 3 | Relabel a `threads.get` observation as `messages.list` (`record_list_page`) | **Blocked**, names both endpoints and cites A2 |
| 4 | Relabel a `messages.list` observation as `threads.get` (`record_thread`) | **Blocked** |
| 5 | Relabel `history.list` → `threads.get` and the reverse | **Blocked**, both directions |
| 6 | Clause-label integrity: an id admitted via H-thr keeps `clause="H-thr"`, `endpoint=THREADS_GET` | Confirmed, no laundering |
| 7 | Same id admitted first via H-lex, then offered again via H-thr in a different observation | First origin wins (`H-lex`); no clause gets overwritten — mixing clauses cannot relabel an already-admitted id |
| 8 | 37-ID / 5-of-42 dishonest map, laundered through `record_thread` (H-thr) instead of `record_shortlist` | **Builds** — `FetchedIds` is still an ordinary public constructor under every endpoint, so the documented residual (`test_a_hand_built_page_is_accepted_and_that_is_the_documented_residual`) now reproduces via the new clause too. Not a new vector: it is the same 2-line fabrication R-RETR named in Round 3, now reachable through one more of three symmetric intakes |
| 9 | The full 3×3 endpoint×intake matrix | `tests/test_disposition_invariant.py::test_each_intake_admits_its_own_endpoint_and_no_other` — read, not just run: all 6 off-diagonal cells raise and leave `H`/`scan_scope` empty; all 3 diagonal cells admit and set the matching clause |

**AST single-writer test:** `test_the_hit_set_has_exactly_one_writer_and_it_demands_a_sealed_page`
re-read and re-run: walks `disposition.py`'s `DispositionLedger` class body with `ast`,
asserts the only method mutating `self._origins` is `_admit`, and that `_admit`'s signature
names `FetchedIds`. Passes, and by inspection covers `record_thread` (which calls `_admit`,
writes nothing itself) — the property genuinely extends to the new intake, not merely to the
two old ones.

**Verdict: CLOSED, no regression.** Every Round-3 seal attack is still blocked. The 3×3
matrix shows the tightening claim is real: an intake accepts only its own endpoint, so
`record_thread` cannot be used to mint a `scan_scope` entry for a query that never ran, and
`record_list_page`/`record_history_additions` cannot absorb a `threads.get` response either.
The one attack that succeeds (row 8) is the pre-existing, explicitly documented residual —
`FetchedIds.__doc__` states it, a dedicated test pins it — now confirmed present under all
three clauses rather than just one. That is symmetry, not widening: the seal never claimed
to close over-recording anywhere, so a residual becoming uniform across three equally-strong
intakes is not weaker than a residual sitting on one of them.

### Judgment — caller-asserted endpoint under A1

A1 already establishes the ceiling: `FetchedIds` is an ordinary constructor in the same
interpreter as any checker, so *no* field on it — not `ids`, not now `endpoint` — can be
trusted without a witness outside the process. Attack 2 (subclass bypass) and attack 8
(2-line fabrication) both confirm the *entire object*, not just its new field, is
caller-asserted; that was already true in Round 3 for `ids`, `page_size`, `more_pages`.
Adding `endpoint` gives an in-process attacker one more thing they could already do anyway —
before A2, forging a `messages.list` page with arbitrary ids was already unconstrained; A2's
only change is that the same forger can now also choose which of three equally-forgeable
labels to wear. **This is not a new attack surface**: full authority over `H`'s contents was
already implied by unconstrained `ids`. A capability that adds no new reachable bad outcome
is not a regression, even though it is, honestly, one more caller-asserted field.

**Call: acceptable residue under A1, not a new gap.** It would become a *new* gap only if
some downstream check trusted `endpoint` differentially — e.g., treated `H-thr` ids as
lower-risk than `H-lex` ones, or exempted them from a future control — while both remain
equally forgeable. Nothing in this diff does that (attack 6/7 show clause labels are kept
honest but never leveraged for differential trust). The residue closes the same way A1
already names: WS-13/WS-16's content witness, when it lands, must record the id set *and*
the endpoint of every observed response, not just the id set — otherwise a witnessed
`messages.list` call could be relabelled `threads.get` after the fact with nothing to catch
it. Worth stating explicitly in WS-13's eventual acceptance line; not a Round 4 defect.

## New findings

```
ID:            R-RETR-005
Severity:      MEDIUM
Rubric:        PART-05, contract R-06
Location:      server/src/mailweave/envelope/wire.py:345 (CollapsedRun.positions),
               server/src/mailweave/envelope/wire.py:278 (MessageRow.position)
Reproduction:  scratchpad/r4rretr/attack_retr002.py, attacks 7 and 9
Expected:      A position reported for a message should be answerable against the thread
               it claims to describe — R-RETR-002's own rationale, "one position, one
               disposition," presumes the position denotes a real place in the thread.
Actual:        CollapsedRun.positions carries no lower bound at all (negative starts
               build). Neither CollapsedRun.positions nor MessageRow.position is bounded
               against the Source's own stated_total. A map_id-bearing Source with
               stated_total=5 and a single collapsed run at positions=(900,904) builds
               cleanly: accounted_for == stated_total == 5, occupancy has no clash (nothing
               else claims 900-904), and the response declares itself a complete map of a
               5-message thread while naming positions no 5-message thread has.
Required fix:  Not purely mechanical — the implementer's HANDOFF correctly flags that the
               codebase does not yet settle whether `position` is 0- or 1-based
               (envelope_kit/contract tests are 0-based; R-RETR's own Round-3 reproduction
               was 1-based; both build today). Bounding position to [0, stated_total) or
               [1, stated_total] requires that decision first. Escalate per AGENT_LOOP §8:
               an architecture-owner call on the position convention, then a bound added to
               Source (not to CollapsedRun/MessageRow in isolation, since the bound is
               relative to stated_total, a sibling field).
```

No other new findings. R-RETR-003 (unchecked `_consumed` double-release) was out of scope
this round and not re-verified; it is unaffected by A2 per `HANDOFF.md`'s own argument
(`record_thread` appends no scan-scope entry, `_origins.setdefault` is idempotent), which
this review did not need to re-derive since the round's diff does not touch `_release`.

## Execution record

```
uv run ruff check .                                          → clean
uv run ruff format --check .                                 → 87 files formatted
uv run mypy                                                   → clean, 61 files
uv run pytest -q -m "not network"                             → 406 passed
uv run python -m tools.guards                                 → clean, 6 sweeps
uv run python tools/rubric_status.py --check                  → 9 PASS / 104 NOT TESTED / 9 transitions
uv run python /tmp/rretr/attack_h1_shortlist_hole.py          → DispositionInvariantError, unmodified probe
uv run python /tmp/rretr/attack_h2_via_shortlist.py           → DispositionInvariantError, unmodified probe
uv run python scratchpad/r4rretr/attack_retr002.py            → 10 sub-attacks, table above
uv run python scratchpad/r4rretr/attack_a2.py                 → 9 sub-attacks, table above
```
Probes under `/tmp/claude-0/.../scratchpad/r4rretr/`; none of `server/`, `tests/`, `tools/`
modified. `docs/reviews/ROUND_04/R-RETR.md` is the only file this review wrote.

## Criterion recommendations

| Criterion | Recommendation | Why |
|---|---|---|
| **EV-01** (bounded-below half only) | **PASS** | H1b/A2 together: `H` is now accumulated from three sealed, endpoint-checked intakes, all mutating `self._origins` only through `_admit` (AST-verified), and no shortlist or bare list can grow it (hypothesis-verified over all three clauses at once). The bounded-below half — every id the ledger knows is accounted for — holds against every attack tried, including the ones new this round. Bounded-above stays out of reach in-process per A1; not this half |
| **EV-03** | **NOT YET PASS**, unchanged | Not touched this round. `note_withheld` still accepts a note for any id in `H` regardless of whether a cap really dropped it (attack 8 above files 37 self-issued notes against 37 self-minted H-thr ids without complaint); the residual A1 names is the same one that keeps this open |
| **PART-05** | **NOT YET PASS** | R-RETR-002's occupancy defect is closed (recommend crediting that sub-property), but R-RETR-005 is a live gap in the same criterion's "position" field, and PART-05's behavioural half (stub rows with correct sender/date/reply-parent, agent-solvable split evidence) is still untested — no rungs exist yet this round, per the work order's own constraint |
| **DISC-06** | **Not re-verified this round** — out of scope, R-MCP/R-ARCH's gating criterion; nothing in this diff touches `response.py`'s self-truncation path | Consistent with Round 2 and Round 3 also deferring it |
