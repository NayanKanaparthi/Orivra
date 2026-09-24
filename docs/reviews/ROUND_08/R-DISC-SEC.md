# R-DISC / R-SEC — Round 8 verification of amendment A6

**Reviewers:** R-DISC and R-SEC, one combined pass (fresh instance; did not write this code,
`HANDOFF.md`, or A6's text). 2026-08-31. Scope: Part 3 of `ROUND_08/WORK_ORDER.md` — A6's final
form — both domains, per this round's shared-subject assignment. `HANDOFF.md` claims not
trusted; every verdict below is reproduced by execution (`AGENT_LOOP.md` §4/§7).

## Execution record

`mailweave.__file__` confirmed as `server/src/mailweave/__init__.py` inside `/root/mailweave` —
an editable install pointing at the source tree, so no stale-copy risk; no scratch resync
needed or done. `make install` clean. Baseline reproduced directly against the tree:

| Check | Result | Matches HANDOFF |
|---|---|---|
| `ruff check` / `format --check` | clean, 91 files | yes |
| `mypy` | clean, 65 source files | yes |
| `pytest -q -m "not network"` | **823 passed** | yes, exactly |
| `python -m tools.guards` | 7 guards clean over `server/src` | yes |
| `tools/rubric_status.py --check` | 8 PASS / 105 NOT TESTED / 10 transitions | yes, exactly |

`RELEASE_RUBRIC.md`, `FINDINGS_LEDGER.md`, `RUBRIC_TRANSITIONS.md` not written to (no criterion
marked PASS, no rows added). `tests/test_sealed_scalars_a6.py` (17 tests) run standalone, all
genuinely pass. Every adversarial probe below is original — not a re-run of the shipped tests —
executed against the live tree via `PYTHONPATH=.`, scripts kept under this session's
`scratchpad/`; no project source or test modified.

---

# Section 1 — R-DISC: is A6 correct?

## Verdicts

| Claim | Verdict | Evidence |
|---|---|---|
| `MessageRow.internal_date` / `Source.history_id` genuinely removed | **CONFIRMED** | not in `model_fields`; `extra="forbid"` refuses the keyword with `ValidationError`; no `model_construct` anywhere in `server/src` to bypass it; values reach the wire only via `Envelope._sources_carry_the_scalars_the_observation_recorded`, a `field_serializer` reading the certificate |
| `stated_total`/`position`/`fetched_at` "stayed, now exact" | **REASONING SOUND, PROTECTS NOTHING IN PRODUCTION YET** | exact-match validators correctly implemented and scoped (below); with no Gmail client, every production thread is in the "observation recorded nothing" branch, so the practical protection today is still the pre-A6 lower/format bound. HANDOFF's own "weakest" §3 says as much — not hidden, but the round's headline table reads stronger than the current reach |
| Class-O fields still misstatable when observed | **NO**, for all five, once the seal actually carries a value | per-field attacks below |
| Composes with A3 (position bounds) | **YES** | `Source._every_position_lies_inside_the_thread` (wire.py:723) is untouched and still runs first; A6 layers an *exact* check on top only where observed — confirmed by `test_a_row_moved_off_its_observed_position_is_refused` and by probing a collapsed run directly |
| Composes with A4 (`included` arithmetic) | **YES, trivially** | A6 touches neither `included` nor `included_as_stub`; no shared state |
| Composes with round 6/7 thread derivation (R-DISC-009/011) | **YES** | `_record_thread_facts`/`_merge_scalars` apply R-DISC-009's "fill a gap, refuse a conflict" rule to A6's scalars; R-DISC-011 already forces a disclosed row's thread to match its observation, which is what makes A6's id-keyed `observed_positions` lookup safe to trust without re-deriving the thread itself |
| Fabrication boundary test exists and asserts what it claims | **CONFIRMED** | `test_a6_closes_misstatement_and_does_nothing_about_fabrication` (line 407) builds a wholly invented `threads.get` observation (`ghost-1`, `ghost-2`, `t-invented`), discloses it entirely, asserts `envelope.partial is False`. Runs and passes — the ledger admits any `FetchedIds` a caller constructs, so a fabricated-but-internally-consistent observation is indistinguishable from a real one, in-process |

## Per-field misstatement attacks (fresh, not the shipped tests)

- **`stated_total` on a `NotIncludedSource`** — the one A6 branch the shipped suite never
  exercises. Built a thread genuinely observed at `stated_total=9`, split it off claiming
  `stated_total=3`. **Correctly refused**. Code is right; coverage isn't — R-DISC-013 below.
- **`position` via a collapsed run** whose span excludes an observed member's real position —
  refused (reconfirmed). **`history_id`/`fetched_at` disagreement** across two `threads.get`
  observations of one thread — refused; **`fetched_at` first-wins** on genuine re-fetch (no
  false conflict) — both reconfirmed by direct execution.

No route was found to make an *observed* class-O field disagree with what it renders on the
wire. The residual gap is not misstatement — it's the R-SEC finding below, a different failure
mode (a field being observed but wrong-shaped).

## §4 — New findings

```
ID:            R-DISC-013
Severity:      LOW
Rubric:        none — documentation accuracy (AGENT_LOOP §7 rule 7 spirit) and test-coverage
               completeness
Location:      disposition.py:104-110 (module docstring, "What that does not close, because
               field-level derivation cannot"); test_sealed_scalars_a6.py (no
               NotIncludedSource.stated_total case); response.py:629-637 (that branch)
Reproduction:  Docstring: read in place, contrasted against the FetchedIds constructor ~180
               lines below, which now accepts all five named scalars. Coverage: grep -rn
               "NotIncludedSource" tests/*.py | grep stated_total -> no output; the branch was
               independently exercised (Section 1 above) and is correct.
Expected:      A docstring later implementers trust as current; every A6 branch backed by a
               test that fails if the branch is deleted.
Actual:        The docstring still says these fields "have no observed value to be derived
               from" — true pre-round-8, false now, and exactly the failure
               `ARCHITECTURE_AMENDMENTS.md` exists to prevent a reader from inheriting.
               Separately, reverting response.py:629-637's NotIncludedSource half to a no-op
               would not fail any shipped test.
Required fix:  Point the docstring at A6 and the residual gap that actually remains (R-SEC
               findings below). Add a NotIncludedSource-flavoured sibling of
               test_a_stated_total_the_observation_did_not_state_is_refused.
```

---

# Section 2 — R-SEC: is A6 safe?

## Verdicts

| Claim | Verdict | Evidence |
|---|---|---|
| No whole response body reaches the seal | **CONFIRMED** | no field accepts an unbounded multi-line string; nothing is shaped to hold a body |
| "The newline refusal ... is what stops the interesting attempt" (A6 docstring) | **FALSE, executed** | five non-ASCII line-terminator code points bypass it entirely — R-SEC-029 |
| Reflection test proves "a future field of the wrong shape fails here" | **OVERSTATED** | the test's own check shares the newline blind spot, and explicitly exempts three string-bearing slots from any bound at all — R-SEC-031 |
| `history_id`/`internal_date` cannot carry real prose | **FALSE, executed** | both accept any <=64-char single-line string with zero format check; real English reaches the wire under a metadata field name — R-SEC-030 |
| Depth-based disclosure ceiling (STUB = no content) holds under A6 | **FALSE, executed** | a STUB row's `internal_date` is written regardless of depth — R-SEC-030 |
| No new write path | **CONFIRMED** | `tools.guards` clean (`unaudited-disk-write` included); manual read of the changed files finds no `open`/`.write_*`/socket/buffer; the seal stays in-memory for one `DispositionLedger`, as before |
| Seal's growth reopens the misstatement class it exists to close | **NO** — every *observed* scalar is exact-checked (Section 1). It opens a **different** class instead: observed-but-wrong-shaped, below |

## The central finding, reproduced end-to-end

A single sentence, one line, 49 characters, no `\n`/`\r`, passed as `history_id` **and**
`internal_dates={"m1": ...}` on a real `threads.get` observation reaches the JSON wire verbatim
under both keys:

```python
SNIPPET = "Please review the attached NDA before end of day."
observation = FetchedIds(ids=["m1"], endpoint=ObservedEndpoint.THREADS_GET, thread_id="t1",
                          stated_total=1, positions={"m1": 0},
                          internal_dates={"m1": SNIPPET}, history_id=SNIPPET,
                          fetched_at=kit.FETCHED_AT)
# record_thread -> build envelope -> model_dump_json():
#   sources[0]["history_id"]                       == SNIPPET
#   sources[0]["messages"][0]["internal_date"]      == SNIPPET
```

Repeated with `depth=Depth.STUB` (a row whose `content` is `None` by construction, specifically
because a stub discloses nothing): `content` is correctly `None`; `internal_date` on that same
row is still the full sentence. `fetched_at` alone resists this — `parse_instant` rejects the
snippet (raising a bare `ValueError`, not `DispositionInvariantError` — a minor type
inconsistency, not filed separately) — because it is the only A6 scalar checked against a real
shape rather than length and a character class.

## §4 — New findings

```
ID:            R-SEC-029
Severity:      HIGH
Rubric:        none — A6's retention claim (OD-4, SCOPE_CORRECTION A.3); bears on SEC-05/SEC-06
Location:      disposition.py:209 (_sealed_scalar: "\n" in value or "\r" in value);
               test_sealed_scalars_a6.py:117,125-128 (reflection test's own check shares it)
Reproduction:  history_id="Line one" + chr(0x2028) + "Line two - the real second sentence"
               -> accepted, 54 chars, no literal \n/\r present. Same for U+2029 (PARAGRAPH
               SEPARATOR), U+0085 (NEL), U+000B (VT), U+000C (FF) in place of U+2028. Python's
               own str.splitlines() reports 2 lines for every one of these five inputs; U+2028/
               U+2029 are recognised line terminators in JavaScript and HTML/CSS rendering.
Expected:      The stated mechanism ("a value containing \n or \r is refused outright, which
               is what stops the interesting attempt") stops multi-line content, matching a
               renderer's or the language's own notion of "a line."
Actual:        Five other Unicode line-boundary code points are unchecked, so a genuinely
               two-line value (two real sentences) is accepted as "a single line."
Required fix:  Check `len(value.splitlines()) <= 1` instead of two literal characters, in both
               the constructor and the reflection test, so the test stops sharing the blind spot.

ID:            R-SEC-030
Severity:      HIGH
Rubric:        none — A6's retention claim (OD-4, SCOPE_CORRECTION A.3); depth-disclosure
               guarantee (contract R-04, "declared reduced depth")
Location:      disposition.py:369-370,413-418 (history_id/internal_dates: length + newline
               only), contrast :371-372 (fetched_at additionally runs parse_instant);
               response.py:60-82 (_rows_with_internal_dates writes internal_date onto every
               row in `messages`, unconditional on `depth`)
Reproduction:  See "central finding" above. STUB-row variant: kit.row("stub1", "t1", 0,
               nonce=nonce, depth=Depth.STUB) with internal_dates={"stub1": <49-char real
               sentence>} -> wire row has content=None, depth="stub", internal_date=<the
               sentence, verbatim>.
Expected:      A `historyId`/`internalDate` has a real shape (Gmail: all-digits) a sealed
               scalar could check, as `fetched_at` is checked as a real instant. A STUB row —
               the tier the architecture defines as disclosing nothing — should disclose
               nothing, not "nothing except <=64 characters via a differently-named field."
Actual:        Any string clearing the length/newline bar is accepted regardless of
               resemblance to a Gmail id or timestamp, and reaches the wire unconditionally,
               including on rows whose whole purpose is to carry no content. A coding-mistake
               surface as much as an adversarial one: a future Gmail-client wrapper that
               accidentally threads `msg['snippet']` into `internal_dates=` would be accepted
               silently, with no test able to catch it beyond length.
Required fix:  Add a shape check (digits) for history_id and internal_date, as fetched_at
               already gets via parse_instant. Separately: withhold internal_date from STUB
               rows, or document explicitly why a bookkeeping scalar is exempt from the depth
               ceiling — the code currently does neither.

ID:            R-SEC-031
Severity:      MEDIUM
Rubric:        none — A6's retention claim (OD-4, SCOPE_CORRECTION A.3)
Location:      disposition.py:283-297 (__slots__), :333,:339 (_ids/_thread_ids constructed
               with no _sealed_scalar call anywhere); test_sealed_scalars_a6.py:109-110
               (id_holding exemption)
Reproduction:  FetchedIds(ids=[MAIL_TEXT], endpoint=THREADS_GET, thread_id="t1") accepted,
               MAIL_TEXT (5 lines, 140 chars) stored verbatim as the message id; same for
               thread_id=MAIL_TEXT, and for thread_ids={"m1": MAIL_TEXT} on a MESSAGES_LIST
               observation.
Expected:      test_the_seal_retains_nothing_but_bounded_scalars_and_the_ids_it_always_held
               states its purpose as "a future field of the wrong shape fails here rather than
               in a review six rounds on" (a round-8, not inherited, claim) — read literally
               that should include the seal's own id fields.
Actual:        `_ids`, `_thread_id`, `_thread_ids` carry zero bound: no length limit, no
               newline refusal. Not new to A6 (A2/round 4 gave FetchedIds these fields), and
               reachable only through the same in-process construction A1's residual already
               covers — not a new hole A6 opened. But the round-8 test's docstring claims a
               broader guarantee than its exemption delivers, for exactly the fields most
               naturally shaped to carry text.
Required fix:  Either narrow the docstring to state id-holding fields are out of scope
               (matching what A1 already discloses about fabrication), or extend the bound to
               them too — Gmail ids and thread ids are short, fixed-shape strings in practice.
```

---

# Combined recommendation

**A6 is architecturally correct on the R-DISC axis.** The two removals are real and route-free;
the three fields that stayed are a defensible, honestly-documented trade-off (avoiding a
"parallel structure" duplication) rather than a partial fix hiding behind exactness language,
though their protection is currently theoretical pending a real Gmail client; composition with
A3/A4/R-DISC-009/011 holds under direct attack; the fabrication boundary is real and correctly
scoped to A1. R-DISC-013 is LOW and does not block.

**A6 is not yet safe on the R-SEC axis.** The work order's exit condition — "A6 landed with mail
text provably excluded" — does not hold under execution: R-SEC-029 shows the newline-exclusion
mechanism has a five-character-wide hole, and R-SEC-030 shows why that hole matters — a real,
human-readable sentence reaches the disclosed wire response under a metadata field name,
including on a STUB row architecturally committed to disclosing nothing. Both are HIGH,
reproduced by direct execution against the live tree, not inherited from a prior round.

**Gate: do not close Round 8.** Per `AGENT_LOOP.md` §6, zero open HIGH is required; R-SEC-029 and
R-SEC-030 are both open and HIGH. Return Part 3 to the implementer with the two required fixes
(Unicode-aware line-boundary check; shape check on `history_id`/`internal_date`, plus a
fix-or-document decision on the STUB depth-ceiling bypass), re-verified by R-SEC before the
round closes. R-DISC's findings may ride along but do not themselves block.
