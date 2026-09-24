# M2 navigation and disclosure redesign — consolidated report (2026-09-14; §9 follow-ups 2026-09-15)

Scope: the owner's brief of 2026-09-13 — one coherent correction for R-M2-076 and R-M2-080,
implemented, gated, independently reviewed, and re-measured on the unchanged sem-off
diagnostic through the MCP boundary. Design note:
`docs/reviews/DESIGN_NAVIGATION_AND_DISCLOSURE_2026-09-14.md` (§7 records where the
implementation departed from it, and why). Amendment: `docs/ARCHITECTURE_AMENDMENTS.md` A14.

Not done, by instruction: no change to `MAX_SERVER_MS`, the host cap, the token ceilings or the
recovery budgets; no corpus change, no mailbox change, no marketing edit, no M3. `MAX_RERANK_PAIRS`
and the E2 floor are untouched. The real-model run has not been executed here; its command is at
the end.

## 1. Which architectural failure classes are fixed

Each is stated as the property now held, with the test that holds it. All are corpus-independent
(`tests/test_navigation_and_disclosure.py`, generated threads of 3/12/40/90/200/400 messages,
every served response measured with the production `rendered_chars` against
`HOST_RESULT_CHAR_CAP`, accounting and fencing checked on every response).

| class | before (measured 2026-09-13) | now | held by |
|---|---|---|---|
| **An explicit read plans and degrades the whole surrounding thread.** One id in a 90-message thread rendered 8,311 chars with the row degraded; in a 400-message thread 17,632. | rows for every position, then A.9a | the requested row at the requested depth, `Band.REQUESTED` — no ladder step collapses or degrades it — and the thread as a compact inventory of runs (member ids once, each pointing at a map page). 90 messages: 5.8k chars, 400: 9.0k, the row at `body_clean` in both | `test_an_explicit_read_delivers_the_requested_row_at_any_position` (18 cases), `…by_map_position…` (9), `test_a_reads_size_is_bounded_by_its_inventory…` |
| **A requested view is not the request.** `view: stub` returned 0 rows for every request; a snippet read returned a top-k of 5. | `_collapsible` took requested stubs; `_planned_rows` degraded beyond top-k | N ids at `stub`/`snippet` return N rows, `role: requested` | `test_a_requested_view_returns_every_requested_row_at_that_view` (6) |
| **A long thread's map is opaque and its run loops.** Zero rows, one run listing every id, affordance = `get_messages(all N, snippet)` → the same shape again. | | a **page**: `page_size` stub rows with `unabridged` calls, other pages as runs pointing at `thread_map(thread_id, page)`, a `thread` continuation to the next page (since 2026-09-15 `thread_map(map_id, page + 1)`, §9.2), `page/page_size/pages` stated. Every page still carries the remaining member inventory, so the map keeps a total-thread-size limit (§9.3). Following `thread` continuations from page 0 visits every position exactly once; every page reachable directly and tiling with its runs | `test_following_thread_continuations_from_page_zero_visits_every_position_once` (5), `test_every_page_is_reachable_directly_and_tiles_with_its_runs` (2), round-24 run tests rewritten |
| **A batch that does not fit is split off with no way back.** 8 ids across 8 long threads delivered 2, the rest `not_included` with no continuation. | | the longest prefix in request order, the rest in a `requested` continuation whose union over the chain is the request by identity, no id twice, each remainder strictly smaller; deferred threads carry their share of the batch as their call. 8×8 `body_clean`: 3 calls (3+4+1); 40 ids in one 400-thread: 5 calls (9+10+10+10+1) | `test_a_batch_across_many_long_threads…` (2), `test_a_batch_inside_one_long_thread…` (3), `test_a_cut_batch_defers_whole_threads…` |
| **Run affordances repeat member ids and, on the search path, point at a segment that declines terminally.** `DIAG-EXP-01` stopped on `thread_map(t, segment=1) → budget_exhausted terminal`. | 3 id copies per member charged; segment form | ids once (`COLLAPSED_RUN_MEMBER_ID_COPIES = 1`, `COLLAPSED_RUN_MEMBER_CHARS = 6`, thread id charged twice at its width); every path's runs point at pages sized by one arithmetic (`disclosure/pages.py`) | `test_a_collapsed_run_is_charged_at_or_above_what_it_renders` (24 cases, both forms), round-26 shape matrix |
| **Sizing verified on the wire.** | estimate only; refusal at `declared_result` | every read arrangement is chosen on the estimate and then rendered and measured before it is served; maps are sized by an upper-bound probe over every page of the snippet-scanned map (one width per thread state, on every path) and refused by `declared_result` if the render disagrees (an estimate defect, certified against) | `_well_formed` in every acceptance test; `test_the_repair_keeps_every_response_under_the_cap_and_fully_accounted` |
| **Reply-parent references survive scoping.** | | a scoped source withholds its rows' direct parents as records with their own read; the row names the parent; the rest is one group under the map call; `included + withheld_here + group == stated_total` | `test_a_scoped_read_names_reply_parents_it_withholds_as_records_with_their_own_call`; replant R226 re-pointed at it |
| **A continuation followed after the thread changed.** (Superseded 2026-09-15, §9.2: the 2026-09-14 row here claimed a page "names a thread and an index" and tested a restart from page 0, which the owner rejected.) | `thread_map(thread_id, page + 1)`, width recomputed per call: a change before the cursor repeated or skipped a row silently | the continuation names its page's own `map_id`; following it redeems the handle (probe, digest, signed page width) and a thread or paging that moved is `handle_stale` with page 0 as the explicit restart; a server that mints no handle offers no `thread` continuation | §5 of `test_navigation_and_disclosure.py`: nine tests that hold an outstanding continuation across an arrival, a departure, a width change, a relabel, an unverifiable window, a paging change and expiry, plus the pointer and no-key tests; replants R252, R253 |

Accounting, fencing, freshness and the E2 floor are preserved by the existing validators, which
were not loosened: `certify` still refuses a withheld id without a record and a note for a
disclosed id (the fit loop *withdraws* the notes of an abandoned trial through a new producer
method, `DispositionLedger.withdraw_notes`, which cannot hide an omission); `partial` and
`truncated_by` are derived, and a `requested` continuation now enters both derivations.

**Preserved explicitly as declared limits, not fixed.** A `body_full` read of a message that
does not fit even alone declines with the `view` narrowing R-MCP-039 certified; the tail of a
message longer than the cap is unreachable inline. A thread whose inventory alone exceeds the
cap (~800-1,000 messages at 16-character ids) declines its map. The design note's M2 sentence
about head-truncating a lone oversized body was **not** implemented — it would make `body_full`
a `body_full` that is not full — and §7 of the note records that.

## 2. Which cases now deliver content

The unchanged sem-off diagnostic (15 cases, 13 answerable, corpus generator 3 seed 4311),
through the MCP boundary, same budgets (33 calls, depth 4), same scoring. Three records, all
preserved under `benchmarks/`:

| run | driver | delivered | recoverable | measurable | undelivered, why |
|---|---|---|---|---|---|
| `diagnostic-rerun-boundary-semoff-4311` (2026-09-13, old wire) | listed affordances | **2/13** | 5 | 13 | call_budget 6, hop_budget 5 |
| `diagnostic-rerun-boundary-semoff-nav-listed-4311` (new wire) | listed affordances only (`--no-named-reads`) | **9/13** | 4 | 13 | hop_budget 3 (EXP-01, EXP-02, REV-02), no_new_affordances 1 (REV-01) |
| `diagnostic-rerun-boundary-semoff-nav-4311` (new wire) | + a listed id is read by name | **11/13** | 4 | 13 | hop_budget 1 (REV-02), no_new_affordances 1 (REV-01) |
| `diagnostic-rerun-boundary-semoff-cont-listed-4311` (2026-09-15, continuations by handle, §9) | listed affordances only | **9/13** | 4 | 13 | as the `nav-listed` record; RANK-03 and REV-03 each one call more (a page one row narrower) |
| `diagnostic-rerun-boundary-semoff-cont-4311` (2026-09-15) | + a listed id is read by name | **11/13** | 4 | 13 | identical to the `nav` record, call for call |

The two 2026-09-15 records are kept apart from the two 2026-09-14 ones and from each other:
*listed-only* and *named-read* are two driver modes, both known-target, and neither is agent
discovery. Nothing earlier was overwritten.

**Read the two new columns apart.** The 2 → 9 step is the wire: pages instead of opaque runs,
requested rows instead of degraded maps, continuations instead of dead ends. The 9 → 11 step is
a driver rule — *a named id is readable by name* (`mailweave_get_messages(message_ids=[id])`, D.1's
own contract for a message the caller can name; `boundary.Served.offers`, `arms._recovery_calls`).
It is legitimate and it is **known-target**: the driver knows which id it wants. Both drivers are
known-target — `follow_boundary` has always followed only offers that could carry a `required`
id — and the diagnostic has never measured query-driven discovery. It measures whether a client
that knows what it wants can reach it through what the responses offer.

Both new-wire records were produced from the final code state (the review's finding 5: an
earlier pair had not been, and disagreed on calls both drivers make identically). Case by case,
new wire, listed-only driver: SEM-01/02/03, RANK-01/02/03/04, EXP-03, REV-03 delivered.
EXP-01: evidence at position 89 of a ~90-message thread; the map's run spans pages 1-5 and
names page 1 (design note §7.10), so the listed-only driver walks pages 0→1→2→3 by
continuation and the depth budget of 4 ends it. The wire states `page_size` on every page, so
a client that knows a position computes `position // page_size` in one call — a computed
call, not a listed one, which this driver mode deliberately does not make; the named-reads
mode reads the id in one. EXP-02: the evidence's thread is offered first, but 21 sibling
threads are mapped in the same hop and the walk into pages 1-2 of the evidence's thread runs
out of depth — the same span-of-pages shape. REV-01, REV-02: retrieval — see §3.

## 3. Which failures remain retrieval or ranking problems

* **DIAG-REV-01** — the evidence's thread is never offered: 35 offers in the first served
  response, none of them its thread. No disclosure change reaches this; the lexical rungs do not
  retrieve the thread for this query. Unchanged from every earlier run.
* **DIAG-REV-02** — the search declines through four narrowings (`max_hit_threads` 12→6→3→1)
  and the chain's last step maps the *top* thread, which is not the evidence's thread. The
  narrowing chain spends the whole depth budget by itself. Top-thread selection, measured and
  named as a separate issue on 2026-09-13; not changed here.
* **Offer order** — in EXP-02, RANK-01 (offered 24th of 29), RANK-03 (25th of 29), EXP-03 (29th
  of 31), REV-03 (23rd of 35) the evidence's thread sits deep in an unranked offer list. They
  now deliver because the walk no longer wastes calls on affordances that loop, but the order
  is still retrieval's, not disclosure's, and a tighter call budget would expose it again.
* **Broad-search bookkeeping (R-M2-076's mechanism)** — the 33-thread / 667-id shape still
  declines on the first search in 4 of 13 cases (`recoverable 4`); the redesign made every
  decline's *retry* land on a response that can be navigated, which is why those cases now
  deliver. M5 of the design note (`withheld_groups[]` as reason blocks) was deferred: after M1
  and M2 no measured case needed it. The first-response decline rate is unchanged and is a
  retrieval-width and pointer-cost question, as diagnosed on 2026-09-13.

## 4. Which claims still require independent acceptance

1. **Query-driven discovery.** Nothing here shows that a model, handed these responses, finds
   the right page or the right id. The pages now carry identity facts (subject, sender, date,
   position) an agent can choose by, and the continuations and `page_size` make any position
   one computed call away; whether the model does so is the real-model run and, beyond it, M3.
2. **The real-model diagnostic** (command below) on the same 15 cases, both driver modes, with
   earlier records preserved. Its `delivered` column is known-target reachability under the
   semantic arms' first responses and offer order; it is not model discovery either.
3. **Live mail.** Every measurement here is on synthetic and sample corpora with 40-word
   bodies. Real bodies at `body_clean`'s 600-token cap are roughly 2-4× larger, and real
   `Authentication-Results` records widen page rows; page widths and batch prefixes will be
   smaller on live mail. The invariants (fit, accounting, continuation identity) do not depend
   on the sizes; the delivery density does.
4. **The estimate's headroom.** Served responses render at 65-85% of the cap (a 90-message page
   at 20.1k of 25k; a scoped batch prefix at 17.7k). The stub-row charge (1,038 vs ~744
   rendered) and the per-source structural charge are the remaining over-estimates. Growing the
   served prefix on the measured render rather than the estimate would deliver more per call;
   it is a design choice (the ceiling would then bind on measurement, not on the estimate) and
   is not made here.
5. **`withheld_groups[]` reason blocks (M5)** — designed, not implemented; the incompatible wire
   change it implies is avoided for now.
6. **AD E.2's segment map** (R-M2-085) declines on any genuinely segmented thread and never
   did otherwise; no affordance names it now. Whether to remove the experiment or re-base it
   on pages is an owner decision.
7. **The review's recorded-not-changed items** — runs spanning pages (§7.10), the fit loop's
   linear fallback when the render disagrees with the estimate, the fixed order of sacrifice
   on reads (inventories before rows, not cost-aware).

## 5. The independent review, and what it changed

One focused review of the whole diff (`docs/reviews/DESIGN_NAVIGATION_AND_DISCLOSURE_2026-09-14.md`
§7 records the dispositions; ledger R-M2-081 to R-M2-086). Fourteen findings; none accepted on
the implementer's word:

| # | severity | finding | disposition |
|---|---|---|---|
| 1 | HIGH | the page width depended on who asked: the search path sized it on a body-scanned map, the served map is snippet-scanned; a run could name a page the map refused | **fixed** — one rule for the snippet-observed text; the search path rebuilds the snippet map to size a page; held by `test_a_search_runs_page_is_the_page_the_map_serves` |
| 2 | HIGH | the width probe priced page 0 only; a later page with a wider participant index could be over budget and step 8 would withhold requested rows under a page claim | **fixed** — an upper-bound probe over every page (`_probe`, `_index_bound`, map-carried `auth_record_chars`/`display_name_chars`); step 8 never takes a requested row; held on a varied fixture |
| 3 | MEDIUM | `omission.bound` named the token ceiling when the host cap bound | **fixed** — decided on the whole request |
| 4 | MEDIUM | runs span pages and name the first; an unrecorded departure from M3 that is the cause of EXP-01/02 in listed-only mode | **recorded** (§7.10) and attributed in §2; per-page runs rejected on cost |
| 5 | MEDIUM | the two new-wire diagnostic records came from different code states | **fixed** — both re-run from the final state; they now agree on every shared call |
| 6 | MEDIUM | the recovery chain still named `segment: 0`, which declines terminally on a long thread | **fixed** — the chain names the thread's map; a map has nowhere narrower to go; R-M2-085 records that E.2's segment map never worked on a segmented thread |
| 7 | MEDIUM | tests did not reach the claimed invariants (no search-run follow, no varied fixture, `_well_formed` blind on the no-key path, a vacuous snippet arm, a size claim held by no test) | **fixed** — each addressed; the growth bound is now a stated inequality |
| 8 | LOW | a deferred thread's read call was not charged in the estimate | **fixed** |
| 9 | LOW | a reply parent outside the thread would be filed as a note outside `H` | **fixed** — guarded |
| 10 | LOW | three misleading texts | **fixed** |
| 11 | LOW | the service-seam driver had no `named_reads` switch | **fixed** |
| 12 | LOW | the fit loop degrades to a linear scan when the render disagrees with the estimate | **recorded**, not changed |
| 13 | LOW | stale comments | **fixed** |
| 14 | INFO | edge cases and unrelated churn | **recorded** |

What the reviewer could not verify from the files — the suite, mypy, ruff, the replants, the
measured sizes, the runner's plumbing — was re-run after the fixes and is reported in §6.

## 6. Gates run

* Full offline suite: **4,051 tests in 100 files, 0 failures** (`-m "not network and not
  replant"`); 62 acceptance tests for this change (`test_navigation_and_disclosure.py` 58,
  `test_r_m2_080_long_thread_body_reach.py` 4, relabelled known-target). After the 2026-09-15
  follow-ups (§9): **4,061 tests, 0 failures**; `test_navigation_and_disclosure.py` 68.
* `mypy --strict`: `mailweave`, `mailweave_harness` clean (175 files). `ruff`: server tree clean.
* Replants: 32 entries whose anchors touch the changed files re-run (`run_sel_replants.py`),
  all CAUGHT; R72, R91, R111, R226 re-pointed; R123's expansion-side citation dropped with the
  reason recorded (the expansion producer now declines before the ladder's emptiness gate runs).
* Certifications: run charge at-or-above render on both run forms × 4 member counts × 3 id
  widths; round-26 shape matrix; wire census (+10 fields: `Continuation` ×6,
  `Envelope.continuations`, `Source.page/page_size/pages`), validator census (+2).
* Offline plumbing verification of the real-model runner: `verify-diagnostic-runner.py` ALL
  PASSED with the new driver flag.

## 7. The real-model command (Mac, existing models and environment)

From the repository root on the Mac, with the provisioned models and the project `.venv`
(PF-4 passed on CPU). Preflight first; it fails clearly if either model does not load and never
substitutes a stand-in:

```
cd /Users/nayankanaparthi/Desktop/Nayan/MailWeave && \
PYTHONPATH=server/src:harness/src:orivra/src:tests/fixtures:. \
  .venv/bin/python benchmarks/run-diagnostic-4311.py \
  --models-root ~/.local/share/mailweave/models --device cpu --preflight-only
```

Then the run, both driver modes, each under its own record name so nothing earlier is touched:

```
cd /Users/nayankanaparthi/Desktop/Nayan/MailWeave && \
PYTHONPATH=server/src:harness/src:orivra/src:tests/fixtures:. \
  .venv/bin/python benchmarks/run-diagnostic-4311.py \
  --models-root ~/.local/share/mailweave/models --device cpu \
  --out benchmarks/diagnostic-run-boundary-nav-listed-4311.txt \
  --json benchmarks/diagnostic-run-boundary-nav-listed-4311.json \
  --no-named-reads && \
PYTHONPATH=server/src:harness/src:orivra/src:tests/fixtures:. \
  .venv/bin/python benchmarks/run-diagnostic-4311.py \
  --models-root ~/.local/share/mailweave/models --device cpu \
  --out benchmarks/diagnostic-run-boundary-nav-4311.txt \
  --json benchmarks/diagnostic-run-boundary-nav-4311.json
```

The corpus is the local sample (read-only); no mailbox is touched. Compare against
`benchmarks/diagnostic-run-4311.ORIGINAL-2026-09-13.txt` (service seam, old wire: 0/13) and the
three boundary records above.

## 8. M2 status

Not declared complete. The suite is green. Of the two architectural blockers named on
2026-09-13, **R-M2-080 is repaired within the demonstrated scope** - known-target
reachability on corpus-independent fixtures of 3-400 messages and on the thirteen sem-off
diagnostic cases through the boundary - and **R-M2-076 remains open** for the first-response
bookkeeping overflow on broad searches (4 of 13 first searches still decline; what changed is
that the retry lands on a navigable response). They are not both closed. The items in §4 are
open, the real-model run has not been made, and two diagnostic cases remain retrieval failures
that no disclosure change reaches. The qualifications in §9 were resolved before any
acceptance claim is made, as the owner required.

## 9. Follow-ups of 2026-09-15 (the owner's three bounded items)

### 9.1 Closure wording, reconciled

Every place that said or implied "both blockers closed" now says what §8 says: R-M2-080 closed
within the demonstrated scope; R-M2-076 open, narrowed to first-response overflow. Changed:
§1 (the superseded row), §8, the ledger's redesign section intro and R-M2-080 row, A14's
closing paragraph. The 2026-09-14 commit message's phrasing is left as history.

### 9.2 Continuation correctness across thread changes

**The defect, stated.** A `thread` continuation was `thread_map(thread_id, page + 1)` and the
width was recomputed on every call. A message arriving or leaving before the cursor shifts
every later position; a width that moves changes where page *k+1* starts. Either way the next
page opened with a row the previous page had carried, or without the row that had been first
on it, and nothing on the wire said so. The 2026-09-14 test restarted from page 0 after the
change and therefore did not test this (ledger R-M2-087).

**Safe behaviour, defined within the freshness architecture (AD A.10), and implemented.** The
continuation is the handle form, `thread_map(map_id, page + 1)`, minted over the state the
page was served in. Following it is a redemption before anything is paged: the liveness probe
walks history for the named thread; the served map's digest is recomputed against the
handle's; and - new to the handle - the map's page width is recomputed and compared with the
width the handle signed (`HandlePayload.page_sizes`, `HANDLE_VERSION` 2). A touch the probe
sees, a relabel included, is `handle_stale`; a message added or removed anywhere fails the
digest whatever the probe saw, including when the history window could not be walked; a width
that moved with the thread unchanged - only a server whose paging constants changed under the
handle can do that - is `handle_stale` too; an aged handle is `handle_expired`. Every refusal
is a tool error carrying the re-derivation, page 0 by `thread_id`, as the explicit restart -
an affordance that, it turned out, had never been executable (it named `thread_ids`;
R-M2-088, fixed). When the probe could not look and nothing changed, the page is served live
with `handle_stale_unverifiable` in band and the traversal stays exact. A response that mints
no handle offers no `thread` continuation. Runs keep the pointer form by choice (design note
§7.12): a pointer lands on a self-describing page and claims nothing about the run.

**Tests, corpus-independent, continuing an existing traversal.** `_traverse` walks pages by
continuation and returns the outstanding one; each §5 test changes the thread and follows
*that* continuation, then walks the restart and checks it covers the new thread exactly at one
width: an arrival before the cursor (asserted among visited positions) and after; a departure
before and after; a width change (a 512-character authentication record; the width is
asserted to have moved and the restart to walk at the new one); a relabel; an expired history
window without a change (served in band, exact to the end) and with one (digest refusal); a
paging change with the thread unchanged (a measure constant moved, no history record); an
expired handle under one clock driving both the client's stamp and the redemption. Beside
them: the pointer form after a departure (served, page 2 of the new state, the run's first
member no longer on it and named by page 1's run - the reason the pointer form cannot be the
continuation); the no-key path (no `thread` continuation on any page, every page reachable by
pointer, batches continuing by id); and a page served by handle (from the LRU, without rows)
carrying the rows and runs the same page served by thread id carries. Replants R252 (the
continuation as a pointer again) and R253 (a continuation offered where nothing can verify
it) are CAUGHT.

**Cost.** The page probe charges the continuation's handle at the payload schema's bounds
(`widest_handle_chars`: ~660-680 characters; a minted handle is ~420) rather than at any
minted handle, so the width cannot move with a `historyId`'s digits or a key epoch, and the
in-band note a handle-served page can carry (R-M2-090). Widths: 40 messages 16 (was 18), 90:
15 (17), 200: 14 (16), 400: 12 (13); pages 3/6/15/34; a 90-message page renders 17.9-19.3k of
25k, a 400-message page 11.3-19.8k. The round-27 estimate matrix still holds with a margin of
368-4,745 characters (per added source ~+60) after the handle grew by `page_sizes`.

**Independent review** (one focused review of this diff, eleven findings, dispositions in the
design note §7.11-§7.13 and the ledger): finding 1 (MEDIUM, the "tens of runs" justification
for pointer runs was false for map pages - at most two) → the choice recorded honestly;
finding 2 (MEDIUM, the width was not fixed by the handle) → `page_sizes` in the signed
payload, checked on `page >= 1`, held by a test that moves a constant with no history record;
finding 3 (LOW, the unverifiable note uncharged) → charged; finding 4 (LOW) was against a
stale staged copy - a map has had no narrower call since 2026-09-14; finding 5 (LOW, the
relabel over-claim: on the unverifiable branch a label-only change is served in band, not
refused) → wording corrected everywhere; finding 6 (LOW, the expiry test used two clocks) → one
clock; finding 7 (LOW) → the restart's width asserted; finding 8 (LOW, a false sentence in
`re_derivation_of`) → removed, and R-M2-088 recorded; finding 9 (LOW, this report's stale
row) → superseded in place; findings 10-11 (INFO: the `marketing/README.md` hunk is the
owner's uncommitted work and stays out; a reflow had dropped 11 characters from the varied
fixture's authentication record - restored; `_restarted` now walks the restart's args
verbatim). The reviewer had no shell; what it could not run - the suite, mypy, ruff, the
replants, the sizes - was re-run after the fixes: **4,061 tests in 100 files, 0 failures;
mypy strict clean; ruff clean on the server tree; 51 replants whose files this change touched
re-run, 50 CAUGHT and one pre-existing non-catching citation recorded (R-M2-092, R232's second
citation, which does not catch at 6be6172 either).**

### 9.3 Map pagination retains a total-thread-size limit

Every page carries the remaining member inventory - every other page's ids, once, in its
runs - so a page's cost has a floor that grows with the thread, and a thread whose inventory
alone exceeds the host cap has no page that fits: `page_size` returns 1 and the map declines
through the ladder's refusal (`test_r_mcp_033_round29`'s 1,000-message decline). At Gmail's
16-character ids that is on the order of 800-1,000 messages. Paging bounds the *rows* a
response carries, not the inventory. **It is not size-independent pagination**, and no text
here, in A14, in the tool description or in `disclosure/pages.py` describes it as one any
longer (R-M2-091). A map of a thread past that limit is a declared limit of the inline
surface, not a page further on.

### 9.4 What did not change

No budget, case, corpus or mailbox; `MAX_SERVER_MS`, the ceilings, the host cap and the
recovery budgets; M3 not begun; the four earlier diagnostic records untouched; `marketing/`
untouched. The real-model command in §7 is unchanged and proceeds in parallel; its handles now
carry `page_sizes` and its continuations are the handle form, which the drivers follow
verbatim.
