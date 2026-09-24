# Design note: navigation and disclosure, one correction for R-M2-076 and R-M2-080

Written before implementation. The objective is not that every message is accounted for -
it already is - but that an agent can navigate to and read evidence through executable calls,
within declared limits.

## 1. The four findings, verified against the code

**1. Explicit reads observe and plan the surrounding thread, and its inventory displaces the
read.** Verified, with a correction to the wording. `service._threads_of` does one
`messages.get` per named id and one `threads.get` per distinct thread; `expansion._planned_rows`
then plans *every message of the thread* as a row ("Every message of the thread as a planned
row"), named ones as `Band.EVIDENCE`, the rest as `Band.MAP` at stub depth; `accounted_ids =
ledger.origins` makes the whole thread the response's obligation. Measured on single-thread
fixtures: a read of **one** 340-character message renders 8,311 characters in a 90-message
thread and 17,632 in a 400-message thread, the growth entirely inventory (`collapsed_runs`
8,352 + their `affordances[]` twin 4,154 at 400). Across threads: a read of 8 messages in 8
threads of 90 delivers **2**, the other six threads split off into `not_included` with their
requested messages undelivered and no continuation. The correction: a read does not observe
*unrelated* threads; it observes the requested messages' *own* threads whole, and it is that
inventory - rows, runs, participants, affordance twins, request echo - that consumes the
response. The effect is as stated.

**2. Explicit reads use search-oriented selection and collapse.** Verified verbatim.
`_planned_rows`: "A.9a's step 3 protects the top *k* of them and degrades the rest";
`DISCLOSURE_TOP_K_HITS = MAX_BODY_FETCHES_L0 = 5` applies to named rows; `ladder._collapsible`
takes **every** stub row, requested or not, so `get_messages(ids, view=stub)` returns zero rows
for any request; the run's affordance is the request that produced it. Measured: five snippet
rows whatever N is; zero stub rows whatever N is.

**3. Runs and recovery affordances repeat member ids.** Verified on the expansion path, not on
the search path - a disagreement worth stating. Measured id copies on the wire: search-path
run **1** (its affordance is `thread_map(thread_id)`), thread-map run **3** (`member_ids`, the
run's `get_messages` affordance, its twin in `affordances[]`), `get_messages(92, snippet)` **5**
(the two `asked_for` echoes as well). And the estimate charges **three copies to every run on
every path** (`COLLAPSED_RUN_MEMBER_ID_COPIES = 3`): 2.57× the rendered run block on the search
path. So on the search path the bookkeeping growth is partly an over-estimate, and it is the
per-thread group and record overhead (518 and 671 characters each) that is real; on the
expansion path the repetition is real. Both are addressed below.

**4. Narrowing retries reduce width or keep a prefix, with no continuation.** Verified.
`recovery.narrower_call`: search halves `max_hit_threads` then hops to the top thread's map;
`get_messages` keeps `ids[: len//2]` "so a client that wants the rest asks for the rest";
`thread_map` offers `segment: 0`. Every retry is a *narrower alternative*; nothing served
afterwards names the remainder. Segments are E.2's temporal experiment (`segment_boundaries`
splits on pauses, not on size), which is why a segment of a 94-message thread estimated at
59,000 characters and declined.

## 2. Responsibilities, and the contract amendments that separate them

| operation | selects | carries | continues via |
|---|---|---|---|
| `mailweave_search` | ranks evidence (unchanged ladder, unchanged E2 floor) | evidence rows; each hit thread's *compact inventory*; other threads as pointers | each source's `map_id`; `not_included`/`withheld_groups` affordances (unchanged) |
| `mailweave_thread_map` | nothing - structure only | **a page**: rows for one window of positions, compact runs for the rest | `page` continuations |
| `mailweave_get_messages` | nothing - the caller named it | **the requested content first**, at the requested depth, as many whole rows as fit; a compact scope declaration of the thread; never the thread's map as rows | a `requested` continuation for the rest of the batch; the thread's `map_id` for its structure |
| any decline | - | `retry_with` = a narrower alternative (scope change), unchanged | - |

**Amendment M1 - compact runs (all paths).** A `CollapsedRun` lists each member id **once**
(`member_ids`, unchanged: the inspectable inventory) and carries an affordance that names the
run by *position range against the source's `map_id`* - `get_messages(map_id, positions=[…],
view=stub)` - never by re-listing its ids; the run's affordance is **not** twinned in
`affordances[]`. Without a handle (no signing key), the affordance lists ids, and that is the
declared cost of the no-handle path. `COLLAPSED_RUN_MEMBER_ID_COPIES` becomes what the wire
carries, verified by the existing charged-at-or-above certification, not chosen.

**Amendment M2 - requested rows are the request.** On the expansion path a named message is
`Band.REQUESTED`: never collapsed by any step, never degraded below the depth asked for by
top-k; the surrounding thread is planned as compact runs from the start (positions, ids once),
not as stub rows for the ladder to collapse. When the requested rows do not all fit, the
response keeps as many **whole rows as fit, in request order**, and declares the rest in a
continuation (M4). A single requested body that alone exceeds the cap is head-truncated with
its `BODY_HEAD_TRUNCATED` reduction declared and its `unabridged` call named - the truthful
limit; no promise that `body_full` fits.

**Amendment M3 - map pages.** `mailweave_thread_map` gains `page` (zero-based). Page *k*
carries rows for positions `[k·W, (k+1)·W)` at stub depth with their `unabridged` calls, and
compact runs for every other page, each run's affordance being `thread_map(thread_id|map_id,
page=j)`. `W` is not a constant: it is the largest window whose rendered response fits the cap
beside the compact inventory of the rest, found by the shared sizing (§4). `page` absent means
page 0, so a long thread's map now carries rows where it carried none. `segment` stays as
E.2's experiment, untouched.

**Amendment M4 - continuations, distinct from narrowing.** A served response gains
`continuations[]`: `{scope: "requested" | "thread", thread_id, positions: [start, end] |
null, message_ids: [...] (no-handle path only), remaining: n, affordance}`. A continuation
*preserves access to the remainder* of something this response started - the rest of a
requested batch, the other pages of a map - and following it makes progress: the remainder
is strictly smaller and never contains what this response carried. A `narrowing` on a decline
*changes scope*: it is the failed call with one dimension reduced. The two are different
fields with different meanings and a client can branch on which it holds. A declined batch
read, retried at half, is then served with a `requested` continuation for the other half, so
the chain completes the batch; the decline alone never promises delivery.

**Amendment M5 - compact per-thread pointers on the search path.** `withheld_groups[]` is
emitted grouped by reason like `not_included_sources[]` already is: one block per reason, one
entry per thread `{thread_id, message_count, affordance}`. Every thread stays individually
named with its own executable call; only the repeated sentence and scaffolding go. Withheld
*records* (step 8, per message) are unchanged: they are individually accountable omissions
and stay that way.

**Amendment M6 - shared sizing verifies the render.** Every served response is planned on the
estimate and then **rendered and measured** (`partition.rendered_chars` on both forms, the
same measurement `declared_result` refuses on). For maps and reads the measurement drives a
fit loop: over the cap → move the last row into the continuation and re-render, until it fits
or one row remains; a lone row over the cap is truncated with its reduction declared. The
search path keeps its estimate-driven ladder and its refusal, with M1 and M5 shrinking what it
has to fit. No constant is tuned to a fixture: `W` and the batch cut are outcomes of
measurement.

## 3. Handles, expiry, mailbox changes, the no-handle path

Continuations use the **existing** `map_id`: a signed, self-describing handle over the
thread's `historyId` at fetch, the mailbox watermark, `fetched_at`, a mapping digest and a
TTL (`HANDLE_TTL_SECONDS = 900`). Redemption re-probes; a thread that moved is
`HANDLE_STALE_*` (refused, or in band with a re-map affordance where AD A.10 says so), a
rotated key is `HANDLE_INVALID` with a `thread_map(thread_id)` remedy. A continuation by
position is therefore honest by construction: it is only honoured against the thread state it
was minted for. Without a signing key nothing can be verified, so continuations name ids
(`message_ids`) and pages by `thread_id` + `page`; a page by index against a thread that has
since changed is declared by the source's own `fetched_at` and `history_id`, which every
source already carries. No session, no database, no persistent graph.

## 4. What is preserved

Exhaustive internal disposition accounting (`DispositionLedger`, `H ⊆ R`, `accounted_for ==
stated_total` on every mapped source). Thread identity and reply-parent references (R-M2-077's
rule: referenced when accounted, disclosed only as a row). Content fencing (every row's
`content` through `builder.fence_content`). Permissions (the read scope is unchanged;
continuations execute the same tools). Freshness (`fetched_at`, `verified_at`, `history_id`
on every source). Truthful partiality (`partial`, `truncated_by`, reductions declared per row).
The E2 floor on the search path: membership unchanged, no obligation deleted; the expansion
path has no floor and says so, as before.

## 5. Compatibility

Tool names unchanged. New optional argument `page` on `mailweave_thread_map`. New optional
field `continuations[]` on the envelope (absent = none). `CollapsedRun.affordance` changes
tool for expansion-path runs (from `get_messages(ids, snippet)` to a positions read) - a
client that followed the old affordance follows the new one the same way. `withheld_groups[]`
changes from a flat per-thread list to reason blocks - the one incompatible wire change, and
it mirrors the shape `not_included_sources[]` already has. `schema_version` stays 2 with these
additive changes documented in D.2; the reason-block change is the one a strict reader would
notice, and it is called out in the wire model's docstring.

Not changed: `MAX_SERVER_MS`, `HOST_RESULT_CHAR_CAP`, the token ceilings, `MAX_RECOVERY_*`,
the evaluation corpus, the mailbox, marketing, M3.

## 6. Acceptance

Corpus-independent fixtures, generated variations (thread sizes drawn from a seeded range),
every test measuring the actual rendered size with `rendered_chars` against
`HOST_RESULT_CHAR_CAP`, checking accounting (`accounted_for == stated_total`, ids unique across
rows/runs/withheld), and fencing on every content row:

1. **Explicit reads at early, middle and late positions** in threads of 3, 12, 40, 90, 200,
   400 messages, by id and by map position: the requested row is present with content at the
   requested depth; the response is not declined; its size is bounded independently of thread
   length up to a declared inventory cost.
2. **Batches that exceed one response**: 8 ids across 8 long threads and 40 ids in one thread:
   the union over the `requested` continuations equals the request exactly (identity, not
   count); no id twice; each continuation strictly smaller; the chain terminates.
3. **Complete map traversal**: pages of threads of 40, 90, 200, 400: the union of row ids over
   all pages equals the thread order exactly; no page repeats a position; every page fits.
4. **Oversized individual content**: a single body over the cap is truncated with its
   reduction declared and its `unabridged` named; `body_full` on it is declined with a
   narrowing, never served over the cap.
5. **Stale or unavailable handles**: a positions continuation against a thread that gained a
   message is refused/declared per A.10 with a re-map affordance; the no-key path continues
   by ids and pages.
6. **Broad searches whose bookkeeping displaced evidence**: the 33-thread / 667-id shape
   (probe-touched threads as compact pointers) fits or declines with a retry whose served
   response carries continuations; the estimate never under-charges the render.
7. **Known-target reachability** (labelled as such): from a map, a message at any position of
   a 90-message thread is read by following offers only, within the standing 33-call/4-hop
   budget. This is *reachability of a known target*, not discovery; the R-M2-080 tests are
   re-labelled and their guard corrected (rendered size via `rendered_chars`, the configured
   cap, unexpected declines fail, follow-ups measured, membership identity checked).

The sem-off diagnostic reruns unchanged afterwards, through the boundary, with earlier records
preserved; its delivered / recoverable / measurable columns are reported with the four
sections the owner asked for.

## 7. Implementation record (2026-09-14) — departures from §2-§6, each with its reason

Implemented in `server/src/mailweave/surface/expansion.py`, `disclosure/pages.py`,
`disclosure/ladder.py` (`_collapsible`), `disclosure/layout.py` (`Band.REQUESTED`),
`envelope/{wire,response,builder,measure,disposition}.py`, `retrieval/assemble.py`
(`_collapsed_runs`), `structure/threadmap.py` (`auth_record_chars`), `surface/{arguments,
tools,rendering,service}.py`, and the two harness drivers. Report:
`docs/reviews/M2_NAVIGATION_REDESIGN_2026-09-14.md`. Amendment A14.

1. **M1's run affordance is the page form on every path**, `thread_map(thread_id, page)`,
   not the `get_messages(map_id, positions=[…], view=stub)` M1 wrote. A positions read of a
   long run would not fit and would decline into the same narrowing chain; a page is bounded by
   construction and needs no handle, so the no-key path is the same path. Search-path runs
   changed from the E.2 segment form to pages for the same reason: `thread_map(t, segment=k)`
   on a long thread declined terminally (the segment is every position of a span as rows), which
   is where `DIAG-EXP-01` stopped on 2026-09-13.
2. **The page width is a property of the thread map, not of the call.** `ThreadMap` gained
   `auth_record_chars` (the thread's widest INJ-05 record) so a map served from the LRU without
   rows computes the same width as one built from a `threads.get`; `disclosure.pages` is the
   one arithmetic, read by the map, the read and the search. The width is bisected on the
   ladder's estimate against `MAP_CEILINGS` (the published ceilings plus the host cap — a map
   takes no budget argument), with one extra run and the next-page continuation charged so
   every page fits what page 0 fits.
3. **M2's "head-truncate a lone oversized body" is not implemented.** A `body_full` that does
   not fit even alone and scoped declines with the `view` narrowing R-MCP-039 certified
   (`body_full` → `body_clean`), as before; a head-truncated `body_full` would be a `body_full`
   that is not full. Acceptance item 4 of §6 is therefore held in its second clause only. The
   tail of a message longer than the cap is a declared limit of the inline surface.
4. **The order of sacrifice on a read is inventories before rows** — the design's "requested
   content first", made concrete: (i) every row with every inventory; (ii) every row, inventories
   kept thread by thread in rank order while the estimate fits (a thread without its inventory
   is *scoped*: rows, direct reply parents as records, the rest one group under the map call, no
   `map_id`); (iii) no inventories, the longest prefix of rows in request order, the rest in the
   `requested` continuation, threads with no kept row *deferred* (one not-included entry and
   one group whose call is their share of the batch). Each level is found on the estimate and
   then rendered and measured; where the render disagrees the search continues on the render.
5. **M4's `partial`.** A `requested` continuation makes the response `partial` and counts as an
   artifact of `truncated_by: mailweave`; a `thread` continuation does neither — the map beside
   it is whole. `Sufficiency` is `ambiguous` while a `requested` continuation remains.
6. **M5 (`withheld_groups[]` reason blocks) is deferred.** After M1 and M2 no measured case
   needed it; the incompatible wire change is avoided for now.
7. **The drivers gained one stated rule** beside "nothing is invented": a wanted id listed in a
   run's inventory is read by name (`get_messages(message_ids=[id])`, D.1's contract for a named
   message). It is a known-target rule, switchable (`--no-named-reads`), and both modes are
   recorded so the wire's contribution and the rule's are reported apart.
8. **The lone-row decline** is raised by `expansion.expand` itself (no arrangement fits) rather
   than by the ladder's emptiness gate; replant R123's expansion-side citation moved accordingly.
9. **Constants moved by measurement, not choice:** `COLLAPSED_RUN_MEMBER_ID_COPIES` 3 → 1,
   `COLLAPSED_RUN_MEMBER_CHARS` 16 → 6, plus `COLLAPSED_RUN_THREAD_ID_COPIES = 2`, each certified
   at-or-above the render on both run forms at every id width.
10. **Runs span pages and name the page of their first position** - not one run per page as
    M3's wording implies. One run per page would cost ~470 characters each and a 400-message
    thread has 31 pages; the source's `page/page_size/pages` make any page one computed call
    away, and a client that knows a position computes `position // page_size`. The
    listed-affordances-only driver does not compute, which is why `DIAG-EXP-01` (position 89)
    walks pages 0→3 by continuation and runs out of depth in that mode (independent review,
    finding 4).
11. **A `thread` continuation carries its page's own `map_id`** (2026-09-15, the owner's
    follow-up on continuation correctness; ledger R-M2-087). M3 wrote the continuation as
    `thread_map(thread_id, page + 1)` with the width recomputed on every call, so a message
    that arrived or left before the cursor, or a width that moved, shifted page *k+1*'s
    starting position and the walk repeated or skipped a message with nothing saying so - and
    the §5 test of 2026-09-14 restarted from page 0 after the change, which is not that
    property. The continuation is now `thread_map(map_id, page + 1)`: following it is a
    redemption under AD A.10 (probe, digest), so a thread that moved is `handle_stale` with
    the re-derivation - page 0 by `thread_id` - as the explicit restart. The handle also signs
    the width the thread was paged at (`HandlePayload.page_sizes`, `HANDLE_VERSION` 2), and a
    page after the first is refused when the recomputed width is not that one - the one way a
    width moves with the thread unchanged is a server whose paging constants changed under an
    outstanding handle (independent review of 2026-09-15, finding 2). A response that mints no
    handle offers no `thread` continuation; its runs still point at every page. Cost: the
    page probe charges the continuation's handle at the payload schema's bounds
    (`widest_handle_chars`, ~660-680 characters) rather than at any minted handle, so the
    width cannot move with a `historyId`'s digits or a key epoch, plus the in-band
    `handle_stale_unverifiable` note a page served through a handle can carry; a 90-message
    thread pages at 15 rather than 17, a 400-message thread at 12 rather than 13.
12. **Runs stay pointers, by choice.** `collapsed_runs[].affordance` is
    `thread_map(thread_id, page)` on every path: a map page carries at most two runs and a
    handle on each would cost about two rows of width; a read's inventory or a search's runs
    may carry many; and one run form is what lets a page named by a search be the page the
    map serves. A pointer followed after the thread moved lands on a page that states its
    own state and lists every id once, and claims nothing about the run that named it. The
    review's finding 1 corrected the docstring that had justified this by "tens of runs".
13. **The re-derivation affordance every `handle_*` refusal offered was not executable**
    (ledger R-M2-088): it named `thread_ids`, an argument `mailweave_thread_map` never took,
    so the one call offered as the way out of a stale handle was refused as unknown. Found
    when the refusal became a traversal's restart; it now names `thread_id`, and every §5
    restart is parsed by the surface's own reader before it is followed.
14. **Map pagination retains a total-thread-size limit.** Every page carries the remaining
    member inventory - every other page's ids, once - so a page's cost has a floor that grows
    with the thread, and a thread whose inventory alone exceeds the host cap has no page that
    fits (`page_size` 1, the map declines): on the order of 800-1,000 messages at Gmail's
    16-character ids. This is not size-independent pagination and §3 must not be read as
    promising one; it bounds the rows a response carries, not the inventory.

**The independent review (2026-09-14) and what it changed.** Findings 1 and 2 (HIGH): the
page width depended on the caller - the search path sized it on a map scanned over bodies
while the served map is scanned over snippets, so the same thread had two widths and a run
could name a page the server refused; and the probe priced page 0 only, so a later page with
a wider participant index could be over budget and step 8 would then have withheld requested
rows under a page claim. Both fixed: `disclosure.pages` is sized on the snippet map on every
path (`structure.threadmap.snippet_observed_text`, one rule), and the probe is an upper bound
over every page (`_probe` at the thread's longest id and widest INJ-05 record; `_index_bound`
at the most-cited rows and the dearest addresses a page can bring in, display names at the
thread's longest, `ThreadMap.display_name_chars`); step 8 never takes a `Band.REQUESTED` row.
Finding 3 (MEDIUM): `omission.bound` on a cut read named the token ceiling when the host cap
bound - fixed, decided on the whole request. Finding 5 (MEDIUM): the two new-wire diagnostic
records came from different code states - both re-run from the final state. Finding 6
(MEDIUM): the recovery chain still named `segment: 0` - a segment map of a long thread declines
terminally (R-M2-085), so the chain names the thread's map (a page that fits) and a map has
nowhere narrower to go. Finding 8 (LOW): a deferred thread's read call is now charged in the
estimate. Finding 9 (LOW): a reply parent outside the thread is never filed. Findings 7, 10,
11, 13: tests strengthened (a search run's page is the served page; a varied fixture with
distinct senders, Gmail-width ids and authentication records; scoped arithmetic in
`_well_formed`; a stated growth bound), texts corrected, the service-seam driver gained the
same `named_reads` switch. Finding 12 (LOW, the fit loop's behaviour when the render disagrees
with the estimate) and the INFO items are recorded, not changed.

