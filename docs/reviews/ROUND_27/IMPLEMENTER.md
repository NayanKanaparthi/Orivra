# ROUND 27 — three things, then real mail

**Implementer:** orchestrator, 2026-09-07
**Work order:** `docs/reviews/ROUND_27/WORK_ORDER.md`
**Scope:** R-MCP-023, R-MCP-024 (with R-MCP-030), R-MCP-025. Nothing else.

Two findings were **created** by doing this work and are recorded below: **R-MCP-032**, fixed
here because the R-MCP-024 correction made it reachable on ordinary searches, and
**R-MCP-033**, *not fixed* — it needs a decision about what a response carries, and OD-7 says a
defect that blocks the live demonstration is reported before another fix round starts.

---

## R-MCP-023 — an ordinary message crashed the server

### The defect, reproduced

`content/mime.py:189` emits, for the unused half of a `multipart/alternative` message:

```python
Reduction(kind=ReductionKind.ALTERNATIVE_PART_UNUSED, removed_chars=0, mime=..., bytes=..., detail=...)
```

`Reduction._kind_specific_obligations` accepts it: `ALTERNATIVE_PART_UNUSED` is one of ten
kinds in `_ZERO_REMOVAL_KINDS`, because it declares that a part was **not used**, not that
characters were removed. `MessageRow._reductions_have_an_unabridged_path`, one layer up, asked
the same question with no exemption list at all:

```python
if reduction.removed_chars == 0 and reduction.count in (None, 0):
    raise ValueError(...)
```

Run against the real pipeline before the fix:

```
$ python -c "... process_message(mime_kit.nested_multipart_message()) ..."
reductions that MessageRow will refuse: [('alternative_part_unused', 0, None)]
```

and through the served path:

```
mcp.shared.exceptions.MCPError: mailweave_search could not be answered: MailWeave's own
response model refused the response MailWeave built. The arguments were accepted; this is a
defect in this server, not in the call
```

That is `-32603` on a message with a text part and an HTML part — which is most real mail. The
same crash arrives from `UNKNOWN_CHARSET`, `CHARSET_REPLACEMENTS`, `UNDECODABLE_BODY`,
`DUPLICATE_HEADERS`, `UNDECODABLE_ENCODED_WORD`, `PART_DEPTH_CAP`, `PART_COUNT_CAP`,
`BODY_HEAD_TRUNCATED` and `HTML_TO_TEXT` — every kind the list exempts.

### Why twenty-six rounds did not see it

`tests/fixtures/mailbox.py` could emit `text/plain`, or `multipart/mixed` when a message had an
attachment. It had no way to emit `multipart/alternative` and no way to declare a charset, so no
test in the suite had ever served one. `tests/fixtures/mime_kit.py` *does* build the shape, and
`tests/test_content_pipeline.py` asserts on the reduction it produces — one layer below the row
that refuses it. Both halves were tested. The seam was not.

### The fix

The rule now lives once, on the record that is about it:

```python
    @property
    def is_a_silent_reduction(self) -> bool:
        return (
            self.removed_chars == 0
            and self.kind not in self._ZERO_REMOVAL_KINDS
            and self.count in (None, 0)
        )
```

`Reduction`'s own validator and `MessageRow`'s both ask it. The second copy is gone rather than
corrected, which is the point: a rule written twice is a rule that will disagree with itself.

The fixture gained the shapes: `Msg.html_alternative` builds a real `multipart/alternative`
payload, and `Msg.declared_charset` / `Msg.body_encoding` put a `Content-Type` charset on the
text part so AD D.4a's charset ladder is reachable from a **served response** rather than only
from `content`'s own unit tests.

### After

Twelve calls — six shapes × `mailweave_search` and `mailweave_get_messages` — all served, with
the reduction **declared on the wire** rather than dropped:

| shape | reductions carried |
|---|---|
| `multipart/alternative` | `alternative_part_unused` |
| declared `ISO-8859-8-I` | `charset_replacements`, `unknown_charset` |
| declared `unicode` | `charset_replacements`, `unknown_charset` |
| declared `UNKNOWN-8BIT` | `charset_replacements`, `unknown_charset` |
| alternative + `ISO-8859-8-I` | all three |
| alternative + latin-1 bytes | `alternative_part_unused` |

**Replant verified.** With the old predicate put back and everything else unchanged, the first
call raises `-32603` again; with it removed, twelve of twelve pass.

---

## R-MCP-024 — the estimate, and the dimension it was never varied over

### The defect, measured

`layout_chars` is what the A.9a ladder shrinks against; `rendered_chars` is the response itself.
The first has to be at or above the second, or the ladder passes a response the surface backstop
then refuses — an answerable query turned into an error.

Round 26 certified the property over ten shapes that were **single-source on every one of them**,
and held the *consequence* ("nothing served crosses the cap") rather than the inequality, with
`if result.is_error: continue`. Both halves of that hid this. Measured on the served path over a
matrix that varies source count (round 27's own fixture, so the two columns are comparable):

| shape | before: est / wire / slack | after: est / wire / slack |
|---|---|---|
| 1 thread | 5754 / 5352 / **+402** | 6150 / 5352 / +798 |
| 2 threads | 8908 / 8824 / **+84** | 9700 / 8824 / +876 |
| 3 threads | 12062 / 12295 / **−233** | 13250 / 12295 / +955 |
| 4 threads | 15216 / 15768 / **−552** | 16800 / 15768 / +1032 |
| 5 threads | 18370 / 19239 / **−869** | 20350 / 19239 / +1111 |
| 6 threads | 21524 / 22710 / **−1186** | 23900 / 22710 / +1190 |
| 8 threads | *declined* | 23264 / 22159 / +1105 — **4 messages** |
| 10 threads | *declined* | 24562 / 23442 / +1120 — **3 messages** |
| 12 threads | *declined* | 23926 / 22836 / +1090 — **1 message** |
| short ids | *declined* | 24067 / 23200 / +867 — **5 messages** |
| long ids | *declined* | 24776 / 23311 / +1465 — **4 messages** |
| long thread ids only | *declined* | 24320 / 22601 / +1719 — **2 messages** |
| short bodies | *declined* | 24672 / 23505 / +1167 — **4 messages** |
| long bodies | 24336 / 24888 / **−552** | 21706 / 20776 / +930 |

The estimate crossed below the rendered size at **three threads** and stayed there, and seven
shapes that declined outright now come back with mail.

### Where the error was, and what replaced it

Three constants were flat numbers standing in for quantities that scale with the ids they
render. Each was measured against the rendered form on the dimension it multiplies, and the
part that varies is now charged off the actual id — the treatment `ROW_ID_COPIES` already gave
a message id, for the reason it gives: *a Gmail id is longer than a fixture's and the estimate
must not depend on which it meets.*

| constant | was | measured | now |
|---|---|---|---|
| `SOURCE_STRUCTURAL_CHARS` | 1100 flat | 1354–1359 + **5.7** per thread-id char (at 5, 16, 22 chars) | 1400 + `SOURCE_ID_COPIES` (6) × thread id |
| `WITHHELD_RECORD_CHARS` | 700 flat | 369 + **4.0** per thread-id char + **2.0** per message-id char | 420 + 4 × thread id + 2 × message id |
| `NOT_INCLUDED_SOURCE_CHARS` | 700 flat | 846 / 901 / 971 at thread ids of 5 / 16 / 30 — flat 821 + **5.0** per char | 1020 + `NOT_INCLUDED_ID_COPIES` (5) × thread id |

The withheld constant was *over*-charging by 293 characters per record, which is the safe
direction and was not harmless: a wide search degrades until every message is a withheld record,
and at 700 each the estimate of that end state was ~32,000 characters against a 25,000 cap, so
the ladder could not converge and the search declined **with no mail** while the response it
refused would have rendered well inside the cap. Both directions of error came from the same
cause — a constant never measured on the shape it is reached by.

`ladder.py`'s step 8 charges a withheld record through the same `withheld_chars` the estimate
uses, so the step's "is a record cheaper than the row it replaces?" check and the estimate cannot
disagree about the answer.

### The thread id a withheld record names

The record renders its message's thread, and the layout cannot always see that thread: A.9a step
7 removes sources (recorded in `split_off`), and **a thread `max_hit_threads` capped away never
became a source at all**. The first version of this fix charged the widest id the layout could
see and claimed that was a bound. It is not, and
`test_the_charged_thread_id_width_covers_every_withheld_record_actually_emitted` failed on the
16-thread shape with `th012fffffffffff`, cap `max_hit_threads` — a thread the layout had never
held. That claim would have been the "a claim wider than the code" defect, shipped.

`Layout.accounted_thread_id_chars` is now set by the producers off `DispositionLedger.origins` —
the same field `envelope.withheld` reads each record's thread from — so the charge and the record
cannot disagree about the id.

### R-MCP-030 — the test that let it through

`test_the_character_estimate_bounds_the_rendered_result` is replaced by two tests that fix both
of its weaknesses:

* `test_the_character_estimate_is_at_or_above_the_rendered_result` asserts **the inequality**,
  not its consequence, over nineteen shapes that vary source count (1–20), messages per thread,
  thread-id length (5–40), message-id length (7–30), body length and sender count. It captures
  the ladder's finished layout by spying on `run_ladder` in **both** producers — `plan` and
  `expansion` — because a spy on one would have made half the matrix assert nothing while
  reporting a pass, which is R-MCP-030's own shape.
* `test_a_search_that_is_served_carries_mail` asserts the payload, so a response inside every cap
  and carrying nothing is a failure and not a pass. The three shapes that cannot meet it today
  are `xfail(strict=True)` naming R-MCP-033, so the list fails the day the defect is fixed and
  cannot outlive it.

---

## R-MCP-025 — the way out that the server refused

`surface/server._narrower_call` minted, for a declined search:

```json
{"tool": "mailweave_search", "args": {"query": "...", "budget": {"max_hit_threads": 1}}}
```

`BUDGET_KEYS` did not contain `max_hit_threads`, so calling it returned `-32602 unknown budget
key`. Contract I-2's proof-of-violation (c): an affordance that cannot execute. The parser
already stated the rule that was broken, in the comment beside `max_ms`/`max_server_ms` —
naming one spelling and not the other *"would have made an affordance this server minted invalid
at the tool that minted it."*

`max_hit_threads` is now a real caller-settable budget: a `BudgetRequest` field, parsed by
`parse_search`, clamped **downward only** by `apply_floor` (the published figure is the most this
server will map), and passed to `assemble` by `service.search`. The threads it stops from being
mapped are not dropped — they become `withheld` records naming the cap, each with the call that
reaches them.

After, on a 30-thread mailbox:

```
max_hit_threads=1: is_error=False sources=1 rows=1
max_hit_threads=2: is_error=False sources=2 rows=2
```

**A test executes the minted call.** `test_the_retry_a_declined_search_hands_back_executes_and_
returns_mail` drives a real decline, takes the `retry_with` off the payload, calls it, and asserts
the answer has a message in it — because an affordance offered as the way out of a decline that
returns another decline is not a way out. No test in the suite executed a minted affordance
before this round, which is why a published affordance and a published argument list disagreed
for a whole round while everything passed. Two more hold the general property: the set of budget
caps this server can mint is read from its two builders (`WITHHELD_CAP_OF` and `_narrower_call`)
and checked against `BUDGET_KEYS`, and every affordance a served response carries is run back
through the parser of the tool it names.

---

## R-MCP-032 — the source A.9a step 8 emptied and left standing (found here, fixed here)

Step 8 withholds rows one at a time and never asked what a source had left, so it could take a
thread's last row and emit the source anyway: `included: 0 of 1`, with no affordance naming the
thread, which contract R-07 refuses at the envelope and which reaches the caller as `-32603` —
R-MCP-023's shape, one layer on.

```
ValidationError: source th00f includes 0 of 1 messages with no affordance that names it (contract R-07)
```

It was latent before this round and became reachable on ordinary wide searches the moment the
estimate was corrected, **because a truthful estimate degrades further than an optimistic one**.
That is the general hazard in fixing an under-estimate, and it is why the regression test runs
across the whole width of the matrix rather than at the one shape that first showed it.

`_retire_emptied_sources` moves such a source out through step 7's own `_split_off`: nothing
leaves the response that had not already left it, and the thread gains the
`not_included_sources[]` entry and map affordance R-07 asks for. It shrinks in both units, so the
driver's third gate passes it rather than needing an exception.

---

## R-MCP-033 — the bookkeeping crowds out the mail (found here, NOT fixed)

**This is reported rather than fixed, under OD-7.** It needs a decision about what a response
carries, which is a schema question of the kind OD-5 was.

A search that hits fifteen one-message threads renders **22,451 characters and carries zero
messages**. The composition:

| block | characters | entries |
|---|---|---|
| `withheld` | 6,816 | 15 records — `why` is 282 chars, and there are **2 distinct `why` strings** |
| `not_included_sources` | 4,908 | 12 entries — `why` is 253 chars, **1 distinct string** |
| `affordances` | 2,415 | 27 |
| `retrieval_report` | 1,147 | |
| text mirror | 6,672 | the same content again, because a host may charge for either half |
| **`sources`** | **2** | **0** |

About 7,300 characters — a third of the host's whole budget — are two sentences repeated
twenty-seven times, and the mirror renders them a second time. The mail is what does not fit.
Body length is irrelevant: at 110, 40 and 8 words per message the fifteen-thread response is
byte-identical, because it contains no bodies.

Measured across width, with the round 27 constants:

| hit threads | messages returned |
|---|---|
| 5 | 5 |
| 10 | 3 |
| 12 | 1 |
| 15–16 | **0** |
| 20 and up | **declined** |

Round 27 moved this line outward — before it, 8 threads already declined — and did not remove it.
Any common word in a real inbox hits far more than fifteen threads, so **this is a blocker for the
live demonstration** and the reason it is filed rather than worked around.

Three directions, none of them taken here:

1. **Deduplicate the identical `why`.** A sentence that is the same on twenty-seven records is
   not information per record. One declared reason with the records referring to it would return
   roughly 7,000 characters — the largest single win, and a wire-shape change.
2. **Summarise the tail.** One declared "18 further threads matched" entry with a paging
   affordance, instead of eighteen entries and thirty records. Cheapest on the wire, and it
   changes what contract R-06 and invariant I-1 require per id — the biggest architectural claim.
3. **Measure instead of estimate.** The surface already renders and measures the real result. If
   a rendered-size overshoot re-ran the ladder against a tightened cap rather than refusing, the
   estimate would need to be approximately right rather than a strict bound, and this whole class
   of defect would stop mattering. The largest change, and the one that removes the class.

---

## Gates

```
ruff check .                                   All checks passed!
ruff format --check .                          200 files already formatted
mypy --strict server/src tests tools harness   Success: no issues found in 173 source files
python -m tools.guards                         guards clean: 7 guards over server/src
python -m tools.field_census                   TOTAL FIELDS: 249  (unchanged; no audited module gained a field)
pytest -q -m "not network"                     2,830 passed, 3 xfailed (R-MCP-033), 0 failed — was 2,737
```

## Have I trusted a peer?

Three places, and each is named rather than assumed:

* **`widest_thread_id`'s first version trusted a claim I wrote myself** — that every accounted id
  belongs to a thread the layout is holding or has split off. The test disproved it on the
  sixteen-thread shape. The charge now reads the width from the ledger the records are built
  from.
* **The row and participant charges were not re-measured**, only checked: over the matrix they
  over-charge by 8 to 77 characters per row and the aggregate slack is positive on every served
  shape, so they are bounds. They were not independently re-derived, and if a future change moves
  them the matrix is what will say so.
* **`NOT_INCLUDED_SOURCE_CHARS`'s flat part is 1,020 against a direct measurement of 821.** The
  direct measurement counted only the block, the affordances and the mirror lines that name the
  thread; the aggregate said the true figure is about 200 higher, and the constant follows the
  aggregate. The residual I could not attribute by name is the gap between the two, and it is a
  margin rather than an understanding.
