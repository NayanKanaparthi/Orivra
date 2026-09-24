# ROUND 28 — implementer's report (items 1–4; item 5 pending the owner's probe run)

**Implementer:** orchestrator, 2026-09-07
**Work order:** `docs/reviews/ROUND_28/WORK_ORDER.md`
**Scope held:** no cross-call cache, no thread ranking, no wire redesign, no N-1 pipeline change,
no R-MCP-033 fix. Nothing here is evidence about progressive disclosure or query-aware depth.

## 1. Schema-consistent retries (R-MCP-037, closing R-MCP-025's second half)

`surface/tools.py`: the `budget` schema gains `max_hit_threads` with a description that says
what it does and that it is the key a decline's `retry_with` carries. `arguments.BUDGET_KEYS`
is now `published_budget_keys()`, read off `SEARCH.input_schema` — the derivation the old
comment claimed. Round 27's test asked the parser; a strict client asks the schema first, so
`test_every_budget_cap_this_server_can_mint_validates_against_the_schema` runs every
affordance both builders can produce (`_raise_to` over `WITHHELD_CAP_OF`, and `_narrower_call`)
through `jsonschema.Draft202012Validator` **and** the parser. `jsonschema` and
`types-jsonschema` become explicit dev dependencies rather than a transitive one.

## 2. One recommended expansion, both halves

`assemble.recommended_expansion`: one `affordances[]` entry, `mailweave_get_messages` naming the
**matched/evidence rows below the requested depth**, in wire order, at most
`RECOMMENDED_EXPANSION_LIMIT = MAX_BODY_FETCHES_L0 = 5` — A.7's own "how many messages is it
worth reading in full at the cheapest tier", the same figure A.9a step 3 protects. Context rows
and map stubs are never named. Nothing is emitted when every matched row is at depth.

The mirror renders that one entry with its arguments (`next call mailweave_get_messages
{"message_ids":[…],"view":"body_clean"}`). It is identified **by what it names, not by position**:
a `get_messages` affordance all of whose ids are present matched rows. A withheld record's
affordance names an id that is not a row; a run's names a thread; so the rule picks out the
recommendation from the payload alone and a forged first entry would not be rendered as one.
Every other affordance line is still a tool name — the mirror does not grow with the withheld
count, so R-MCP-033 is not made worse. `_read_affordances` still round-trips the tool name.

Measured on the twelve-hit shape: entry 133 + line 115 = **248 characters** naming five
six-character ids. Charged as `RECOMMENDED_EXPANSION_CHARS = 240` plus two copies of the five
longest present hit ids, **only on layouts that can carry one** (`Layout.recommends_expansion`,
set by `plan.disclose`, never by `expansion`). The first version charged it everywhere and
tipped a `body_full` fixture sitting at the cap's edge into a zero-row expansion — which is how
R-MCP-039 was found (below). Estimate ≥ rendered on all nineteen shapes, slack +1,070 to +1,947.

Behaviour on the fixtures:

| shape | matched rows by depth | recommendation |
|---|---|---|
| 1 thread × 12 hits | 5 body_clean, 1 snippet, 6 stub | 5 of the 7 missing, all matched |
| 1 hit at position 7 of 12 | 1 body_clean + 11 context (9 stub, 2 snippet) | **none** |
| 3 threads × 3 hits | 9 body_clean | **none** |

And the acceptance the order names: the line copied from the text alone, validated against the
schema, executed, returns `body_clean` text for every id it named.

## 3. The description (R-MCP-036)

One claim on `mailweave_search`, three evidence tests: a search returns each matched thread
whole; `mailweave_get_messages` by id or `map_id`+position is the direct, identity-preserving way
to read a row the response already identified, at one read, and avoids another exploratory
search; when matched rows could not be carried at depth, `affordances[]` holds one recommended
call and the text carries it with its arguments. **It does not say a narrower search cannot
recover a row** — the owner's experiment showed it can — and
`test_no_description_claims_a_narrower_search_cannot_recover_an_identified_message` sweeps every
claim on every tool for that sentence.

## 4. One `messages.get(full)` per named id (R-MCP-038)

Confirmed before changing: `service.py:416` fetched full to learn the thread and kept only
`thread_id`; `:442` fetched full again. `_threads_of` now returns the messages it fetched and
`_bodies_for` processes what is in hand, fetching only what is not (the `map_id` route arrives
with nothing in hand and pays its one read there). Per endpoint, `mailweave_get_messages` at
`body_clean`, two-thread fixture:

| named ids | | getProfile | history | list | threads.get | messages.get | full reads per id |
|---|---|---|---|---|---|---|---|
| 1 | before | 1 | 0 | 0 | 1 | **2** | 2 |
| 1 | after | 1 | 0 | 0 | 1 | **1** | 1 |
| 3 | before | 1 | 0 | 0 | 1 | **6** | 2 |
| 3 | after | 1 | 0 | 0 | 1 | **3** | 1 |
| 5 | before | 1 | 0 | 0 | 1 | **10** | 2 |
| 5 | after | 1 | 0 | 0 | 1 | **5** | 1 |

The profile call and the thread map are their own overhead and are reported as such, not folded
in. Replant verified: with the reuse line put back to `None`, the per-id assertion fails at 2.
A `stub` request reads no body at all (asserted).

## 5. The deadline — probe built, constant untouched

PF-21 is registered in AD §F, wired into the runner ahead of PF-3, exercised end to end on the
fake transport, and committed first (`4dfeb9a`) so the owner can run it while this report is
written. **`MAX_SERVER_MS` has not changed.** The candidate formula is registered as a bound;
adoption waits for the figures and a validation on neutral end-to-end searches.

## Found, not fixed, reported

**R-MCP-039 (HIGH, reachable).** A `body_full` request for a body at the cap's edge: the ladder
withholds the only named row, `expand` builds a zero-evidence envelope, ROUTE-01 refuses it,
the caller gets `-32603` instead of a declared decline with a narrower call. Pre-existing;
surfaced by a 250-character estimate change. Out of this round's scope; filed for the owner.

## Gates

ruff, ruff format (202 files), mypy --strict (175 files), 7 guards, field census 249 unchanged
(no audited module gained a field — `Layout` is not audited; `recommends_expansion` is a
planning flag, not a wire field), **2,855 passed / 3 xfailed / 0 failed**, was 2,830.

## Have I trusted a peer?

The `is_the_recommended_expansion` rule assumes no other affordance on the surface names present
matched rows by id. I checked the builders in `assemble.py` (withheld → absent ids; runs →
thread or positions; breach → search) and `expansion.py`. A future affordance that names present
matched rows would render with arguments too — which is probably right, and is a thing the
reviewer should look at rather than take from me.
