# Round 29 — implementer's notes (R-MCP-033 and R-MCP-039, the v0.1 closure tranche)

Every claim here is a claim about what executed. Where a number appears it was measured, and
the test that measures it is named.

## What changed, and the rule it changed under

**A withheld record is written at the granularity of the call that recovers it.** That single
rule produced the whole of the size change and it is a contract reading, not a size trick:
AD A.7a hands a `max_hit_threads` withholding a `mailweave_thread_map{thread_id}`, so one
counted group per thread says what forty-five per-message records said, to a caller who can
only act on it a thread at a time. R-06 ("visible stubs, not a number, *wherever the map is
present*") is untouched: where a map exists, rows stay rows.

Three forms of the same overflow, one design:

| form | before | after |
|---|---|---|
| 45 messages from 15 unmapped threads | 45 × (420+4T+2M) = 23,220 chars | 15 groups × (490+4T) = 8,310 |
| 16 split-off single-message threads | 16 × (1,020+5T) = 17,600 | 1 block (510) + 16 × (320+4T) = 6,654 |
| every ceiling record embedding the 206-char host-cap sentence | once per record | once, in `omission.bound` |

~~A group standing for one message is written as that message's record (`GROUP_WORTH_WRITING =
2`) - a group of one costs more than naming it.~~ **Wrong, and removed in the repair pass
(R-V01-007).** On the real serializer a group of one is 451 characters against a record's
461, and the rule kept the single-message-thread form of R-MCP-033 - a broad `after:` query
on a real inbox - as per-message records charged 656 each. A group of one is a group; the
granularity is read off the affordance alone (`WithheldGranularity.of(tool)`: `THREAD` when
the remedy is `mailweave_thread_map`, `MESSAGE` otherwise).

**The tail.** Groups beyond `MAX_WITHHELD_GROUPS_NAMED = 24` under a cap that has a widening
call fold into one `withheld_tail[]` entry: the cap, the shared reason, exact thread and
message counts, and the same search at the published width (`max_hit_threads: 12`). Only
`max_hit_threads` folds - it is the one published width key; `max_source_threads` groups are
always named. The certificate's sum includes the tail, so `H == disclosed ∪ withheld` is
asserted over named records, named groups and the tail together. Forty-five and sixty
single-message threads at `max_hit_threads: 1` now serve: 24 named groups, one tail, mail.

## Two regressions I introduced and caught by execution

1. **The ladder served an empty response.** Before grouping, an emptied response was still
   thousands of withheld records and failed the size check; the cost of the bookkeeping was
   the guard against emptiness, by accident. A 4,000-message thread came back `src=0
   present=0`. `_carries_nothing` now refuses a response that lost every matched message.
   Its first version also refused ordinary no-match searches; it now checks evidence *loss*.
2. **Step 7 split away every evidence-bearing source** of a twelve-thread search, for the
   same reason. `_may_leave_without_emptying_the_answer` writes the rule down instead of
   paying for it.

## A pre-existing defect the change exposed

`WITHHELD_RECORD_CHARS` was under by a flat 225 at every id width since round 27: measured
against the token-ceiling reason (46 chars) and charged for the host-cap reason (282). Invisible
because `NOT_INCLUDED_SOURCE_CHARS` over-charged ~500 the other way in every shape that had
both. Correcting the one exposed the other:
`test_the_character_estimate_is_at_or_above_the_rendered_result[20 threads]` failed at -788.

The round then bounded every reason a record can carry (the `partial_source_failure` one
embedded a list of ids and had no maximum) and **certified the constants** against every
reason variant at id widths 1 / 16 / 20 / 30 through the real renderer, with the real
serializer's separators and the real affordance each variant carries
(`tests/test_omission_sizing_round29.py`; the first census used compact separators and a
thread-map affordance on the budget-cap variant - R-V01-013). Final figures:
`WITHHELD_RECORD_CHARS = 560` (+4/thread-id char, +2/message-id char, **+1/query char for a
record whose affordance is a search** - R-V01-013(a), below), `WITHHELD_GROUP_CHARS = 490`
(+4T), `NOT_INCLUDED_SOURCE_CHARS = 320` (+4T), `NOT_INCLUDED_BLOCK_CHARS = 510`,
`WITHHELD_TAIL_CHARS = 540` (+2 per query char), `COLLAPSED_RUN_CHARS = 440` with members at
`16 + 3 × id` (R-V01-005: members render three times). Rows now charge their `reductions[]`
and `attachments[]` at their exact serialised size (R-V01-003), and the response's account
of its request - `asked_for`, `scan_scope`, `not_tried`, a breached cap's `affordances[]`
entry - is measured off the blocks themselves before the ladder runs (R-V01-004, 013(a)).

**What the recheck found and this pass fixed.** A budget or clock cap (`max_api_calls`,
`max_server_ms`) files one record per message in every thread it stopped the server
mapping, and each record's affordance is the caller's own search, query included. The
constant was measured at a six-character query: twenty-four such records were 2,458 under
at a 407-character query and 12,858 under at 807. The layout now carries
`query_bearing_ids` (seeded from the same ledger sweep the records are filed from) and charges
each one `json_string_chars(query)` - the JSON-escaped length, since a quoted query renders
longer than it reads. Held end to end at the demo query, a 200-character one and an
800-character one with escaped quotes, on both the record-bearing and the zero-record shape
(`test_budget_cap_shapes_are_estimated_at_or_above_what_they_render_at_any_query_length`);
replant R126. The reviewer's width matrix re-run after the fix: no under-estimate at widths
5/16/20/30/40 across every reason variant, tail boundary 23-100 threads.

## The recovery chain

`surface/recovery.py`. `MAX_RECOVERY_STEPS = 7`, the largest of three per-tool schedules,
each derived and held by a test that requires the bound to be **tight** (the first draft said
5, then 4; the review's `message_ids` dimension made it 7):

* search: `halvings_to_one(12) + 1 = 4` - the width in effect, `min(cap, threads mapped)`,
  halves to 1, then the tool changes to a `mailweave_thread_map` of the top-ranked hit thread
  (`segment: 0` only if the thread has segments - R-V01-010);
* get_messages: `1 + 1 + halvings_to_one(50) = 7` - `view` first (`body_full → body_clean`),
  then the ids (or `positions`, for the `map_id` form - added at the recheck) halved from at
  most `MAX_MESSAGE_IDS_PER_RETRY = 50`, a *retry* bound and not a request cap (a schema
  `maxItems` was tried and removed: it broke collapsed-run affordances naming more);
* thread_map: 1.

Every other argument the caller sent travels unchanged (R-V01-009). Every decline carries
`narrowing{dimension, applied, proposed}` and `terminal`; `terminal: true` only when the
schedule has no smaller legal call. The guard `is_the_same_call` is the direct form of the
cycle-free property.

## REG-01 / REG-02, demonstrated

Against the server tree at `5e86229` (the fifteen changed files staged from the device and
substituted into a scratch copy; `mailweave.__file__` confirmed to resolve there):

```
live shape, 18 threads x 3 messages, max_hit_threads: 3
  5e86229: is_error=True  budget_exhausted  ~34,235 chars  retry_with: max_hit_threads: 1
  round 29: served, sources >= 1, matched rows >= 1, 45 messages grouped, <= 25,000 chars

20 single-message threads
  5e86229: is_error=True  budget_exhausted  ~26,500 chars
  round 29: served, one not_included block, matched rows >= 1

body_full, 3,500-word message  (R-MCP-039)
  5e86229: MCPError -32603 "MailWeave's own response model refused the response ..."
  round 29: declined budget_exhausted, narrowing view body_full -> body_clean, one hop, served
```

Replants R123 (emptiness gate removed), R124 (retry repeats the width), R125 (grouped
messages not counted against H): all three **CAUGHT**, every citation alone. R124's first
version substituted a *narrower* width and was caught by nothing - a narrower retry is not the
defect; a repeated one is - and was re-anchored.

Round 27's `WITHOUT_MAIL_TODAY` xfail list, three shapes under `xfail(strict=True,
reason="R-MCP-033 ...")`, emptied by **passing**.

## Test expectations changed, each with its reason

* `test_disclosure_round23`: the shape that declared inability now answers (kept, asserted
  from the other side); a new single-huge-thread shape reaches the refusal.
* Three pinned inventories: field census 249 → 276, wire-tree validators 48 → 50, envelope
  validators 18 → 19, serialisation field set + `PARTIALITY_SIGNALS` gain `withheld_groups`,
  `withheld_tail` and `omission`.
* `test_thread_map_round20::test_sibling_threads_beyond_the_cap_are_withheld_rather_than_dropped`:
  a thread `max_source_threads` withholds is recovered by one thread map, so it is now one
  group naming the thread (asserted: the id is still in `withheld_ids`, the group carries the
  cap, the map call and `message_count == 1`), not one record per message.
* `test_round25`'s injected-exception decline is driven with `segmented=True` so the retry it
  asserts is a real narrowing; `test_round24`'s reach and accounting assertions include groups;
  `test_round26`'s ceiling-scope test reads the bound off `omission.bound`.
* `test_lexical_ladder`, `test_round26`, `test_mcp_surface_round24`, `test_round27`: read the
  reason off the block it moved to, or the flat `not_included_entries` view.
* `test_round27` / `test_round28` retry tests: twenty one-message threads no longer decline,
  so the declining fixture is one thread too large for any arrangement, and the claim is the
  chain's.

## The consolidated review and the repair pass

`V0_1_REVIEW.md`: fourteen findings, eight HIGH, all reachable by execution. The repair pass
took every HIGH and the three cheap MEDIUMs; the recheck (appended to the same file) returned
REPAIRED on 001-009 and 011, PARTIALLY REPAIRED on 010 (the `map_id` + `positions` form, fixed
above - replant R127) and one remaining under-estimate, 013(a), fixed above. No regression of a
repaired shape.

Recorded, not fixed, for v0.1 (MEDIUM/LOW, none on a documented workflow):

* R-V01-004 residual: a row's `reason` re-renders every *matched* term twice, uncharged; a
  query whose term matches ~60 rows reaches the rendered-size backstop (declared, never
  truncated).
* R-V01-005 capability shift: one `body_clean` read inside a ~300-message thread now declines
  `terminal` where the under-estimate used to serve it at 23,250; twenty named ids in a
  twenty-message thread collapse to a run at 5,203 characters because the corrected estimate
  (25,611) sits above the render (21,878). Both are the estimate erring high, which is the
  direction it may err in.
* R-V01-007 residual: 26+ single-message hit threads at the *published* width decline once
  and serve at hop 1.
* The budget-cap record charge is the flat longest-variant figure (+292 over what a budget
  record renders), so a long query under a budget cap declines one hop earlier than the wire
  strictly needs; the chain still ends in the truthful capped response
  (`test_a_long_query_budget_decline_still_terminates_in_a_served_response`).
* `_exhausted` is reachable (§5a, reviewer-confirmed) and its floor-membership sentence is
  stale on an emptied response; non-budget declines carry `terminal: false, retry_with: null`.
