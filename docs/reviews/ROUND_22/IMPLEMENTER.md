# ROUND 22 — implementer's report

**WS-10: escalation policy, budgets, stopping and outcome, over a handle that reports what it saw.**
Third of OD-6's five workstreams to the usable milestone. Written after the gates below were run.

Everything in this file that says "executed" names the file and the assertion. Where I could not
establish something I say so under its own heading rather than leaving the silence to be read as
agreement.

---

## Part 0 — the three carried findings, and what each cost

I ran the reviewer's reproductions **before** touching anything, as instructed. All three reproduced.

| Finding | Repro, before | Repro, after |
|---|---|---|
| R-RETR-058 | `/tmp/rretr21/p8_matrix_range.py`: 7 shapes, `outcome None: False`, `from_cache: False`, `cache_tautology: False` | matrix rebuilt; see §0.1 |
| R-RETR-059 | `/tmp/rretr21/p2_seen_change_served.py`: `handle_stale_unverifiable`, `changed={}`, content served | `handle_stale`, `changed={'t-alpha': '1 label additions'}`, content refused |
| R-RETR-060 | `/tmp/rretr21/p3_watermark_reach.py`: quiet thread, 2 calls per redemption, LRU never serves | see §0.3 — the mechanism is closed and **the reviewer's own script still prints the old output**, for a reason I give there |

### 0.1 · R-RETR-058 — the matrix, and three clauses that were worse than vacuous

`seven_shapes` is now `redemption_shapes` and returns **eleven**. The two the finding named — a clean
redemption cold and warm — plus **two more that widening the matrix immediately falsified clauses
over**:

* `handle_stale/caught_by_the_digest` — the watermark expired, so step 2 could not look and step 4
  caught the change. `outcome = handle_stale` with `liveness = unverifiable`.
* `handle_stale/pages_outstanding` — amendment A10's own shape: a walk that saw a change and ran out
  of pages.

Adding them made **three** clauses fail, and each was asserting something untrue of the reachable
space rather than merely vacuous. R-RETR had already reached two of them by execution (`p1`), and
the matrix had not:

* **clause (e)** asserted `liveness is UNVERIFIABLE ⇒ outcome is handle_stale_unverifiable`. False on
  the digest-caught shape. Now: `outcome ∈ {handle_stale_unverifiable, handle_stale}`, and a
  `handle_stale` there must carry `digest_check = mismatch`, which is the pair naming *which step
  found it*;
* **clause (g)** asserted `handle_stale ⇒ trace.changed`. False on the same shape: step 4 has no
  per-thread record to list, because step 2 is the only step that reads history. Now the account is
  required from the step that produced the finding, and a step-4 finding must carry an *empty*
  `changed` — so the branch cannot quietly acquire an invented one;
* **clause (b)** asserted `served == (FETCH in steps ∧ DIGEST in steps)`, a biconditional. False
  wherever all four steps ran and the recompute refused — which is step 4 doing its job. The
  biconditional would have forbidden the defence-in-depth branch from refusing anything. Now: `served`
  iff the outcome is one of the two that carry content; `served ⇒ both steps ran`; and *not* served
  with `DIGEST` reached ⇒ `digest_check is MISMATCH`.

The non-vacuity assertions are now over the **answers**, never over the dict keys, and each names the
clause it keeps honest.

**Proof that each of the eight clauses can now fail.** `/tmp/ws10/p_clauses.py` — my own plant
harness (`/tmp/ws10/plantkit.py`), not the reviewer's; full scratch tree including `docs/`, all three
packages asserted to resolve inside it and not into `/root/mailweave`, anchor asserted to match once,
file asserted to change, and **only** the property test run:

```
CONTROL (unplanted): PASS
a  surface written by hand rather than read from ERROR_SURFACE        caught=True
b1 a clean redemption that serves nothing                             caught=True
b2 a digest mismatch that serves the map it just disagreed with       caught=True
c  a step-1 refusal that claims a liveness result                     caught=True
c2 a step-1 refusal that spends a Gmail call first                    caught=True
d  the warm path wearing the cold path's label (ADV-002)              caught=True
e  an unverifiable probe served from the LRU (BOTH defences removed)  caught=True
e2 an unverifiable probe that hides which class it is                 caught=True
f  fetched_at restamped on a cache hit                                caught=True
f2 verified_at set on a live fetch too                                caught=True
g  a handle_stale from step 2 that does not name what moved           caught=True
g2 a handle_stale from step 4 that invents what moved                 caught=True
h  an affordance minted from an unverified payload                    caught=True   (/tmp/ws10/p_h.py)
A10 the A10 rule reverted                                             caught=False  (see below)
```

The reviewer's own `/tmp/rretr21/p7_clause_plants.py` on the same tree: 7 of its 8 caught, with row
(e) `False` — and that row is **correct** and R-RETR said so: the eviction and the lookup-skip defend
it independently, so removing one leaves the behaviour intact. My row (e) removes **both**, and it is
caught. That is the honest form of the check.

**The one plant the property does not catch, named rather than hidden.** Reverting amendment A10's
second rule (`if probe.saw_a_change and probe.conclusive:`) leaves the property green, because a
collapsed `handle_stale_unverifiable` violates none of the eight clauses — it is a different
property. `/tmp/ws10/p_a10.py`, each test run alone:

```
CATCHES         test_a_walk_that_saw_a_change_and_ran_out_of_pages_reports_what_it_saw
CATCHES         test_an_unverifiable_probe_is_reserved_for_a_walk_that_observed_nothing
does NOT catch  test_every_handle_outcome_only_claims_what_the_step_that_ran_produced
does NOT catch  test_a_history_walk_that_stopped_early_is_unverifiable_rather_than_clean
```

Replant **R59** cites the two that catch, and only those.

**The matrix's reach, printed** (`/tmp/ws10/p_matrix_handles.py`, my re-derivation of the reviewer's
`p8`):

```
shape                               outcome                     liveness              from_cache    digest                  served
clean/cold                          None                        verified_unchanged    ()            recomputed_from_fetch   True
clean/warm                          None                        verified_unchanged    ('t-alpha',)  cache_tautology         True
handle_invalid                      handle_invalid              not_reached           ()            not_reached             False
handle_key_rotated                  handle_key_rotated          not_reached           ()            not_reached             False
handle_expired                      handle_expired              not_reached           ()            not_reached             False
handle_stale/cold                   handle_stale                changed               ()            not_reached             False
handle_stale/warm                   handle_stale                changed               ()            not_reached             False
handle_stale_unverifiable/cold      handle_stale_unverifiable   unverifiable          ()            recomputed_from_fetch   True
handle_stale_unverifiable/warm      handle_stale_unverifiable   unverifiable          ()            recomputed_from_fetch   True
handle_stale/caught_by_the_digest   handle_stale                unverifiable          ()            mismatch                False
handle_stale/pages_outstanding      handle_stale                changed               ()            not_reached             False

shapes in the matrix                        : 11
any shape with outcome None (clean)         : True
any shape with threads_from_cache non-empty : True
any shape with digest_check==cache_tautology: True
any served thread with from_cache True      : True
any served thread with verified_at set      : True
any handle_stale with liveness CHANGED      : True
any handle_stale caught by the digest       : True
any refusal after all four steps ran        : True
```

**What §1.3 of the round-21 report claimed and what is true now.** It said the matrix "adds the clean
redemption as the eighth answer". It did not; `seven_shapes` returned seven and the test asserted
`len(shapes) == 7`. It now returns eleven, and the count assertion is not the evidence — the
answer-level assertions are, and the count is there only so the builder failing silently is visible.

### 0.2 · R-RETR-059 — a walk that saw a change says so

`redeem.py`'s condition was `not probe.expired and not probe.pages_exhausted and probe.touched`. It
is now `probe.saw_a_change`, a new property on `LivenessProbe` beside the narrowed `conclusive`. The
two are two questions and the round that ran them together served a map under a sentence saying the
change could not be seen.

* `LivenessProbe.conclusive` — narrowed in its docstring to the **negative** answer only, with the
  reason: `touched` is built from records the walk read; an unread page can add to it and cannot
  subtract from it.
* `LivenessProbe.saw_a_change` — new, and the 404 path returns `touched={}` so an expired watermark
  can never reach it saying yes.
* `Liveness.UNVERIFIABLE`'s docstring is narrowed to "observed nothing **and** could not finish".
* The `handle_stale` detail now declares the *list's* incompleteness when the walk was short — "this
  is at least what moved rather than all of it; the refusal does not depend on the remainder" —
  which is a different claim from the finding's completeness and is asserted in the test.

Executed: `test_a_walk_that_saw_a_change_and_ran_out_of_pages_reports_what_it_saw` asserts
`handle_stale`, the named change, `served == ()`, the affordance, `steps == (verify, liveness_probe)`,
the absence of "could not be verified" and the presence of "at least what moved".
`test_an_unverifiable_probe_is_reserved_for_a_walk_that_observed_nothing` asserts the **partition** as
four `(outcome, liveness)` cells over {404, pages outstanding} × {saw a change, did not}, rather than
two examples. The 404 row is where I learned something: with the watermark expired, step 2 cannot see
the change and step 4 catches it — `handle_stale` with `liveness = unverifiable`, a third mechanism,
and the pair is what makes it visible rather than collapsed into the row above.

### 0.3 · R-RETR-060 / amendment A10 — the watermark, and an honest residual

`HandlePayload.history_id` is now the **mailbox** `historyId` observed before this response's first
`threads.get`, passed into `mint` as `mailbox_history_id`. `thread_history_ids[]` is unchanged and
still floors the probe per thread. `assemble` reads the watermark at the top, and `redeem`'s page
bound is `MAX_LIVENESS_PAGES` — its own registered constant, with its own comment saying it bounds a
*sync* walk and not `MAX_PAGES_PER_QUERY`'s disclosure page.

**Where I deviated from the reviewer's suggested fix, and why.** R-RETR asked for the payload
validator to become `history_id >= max(thread_history_ids)`, calling it "the same class of check in
the safe direction". I did not adopt it, and the reason is executable rather than an opinion.
`max(thread_history_ids)` is a watermark taken *after* the last thread's read. A change to a
*different* named thread between its own read and that moment then sits **below** the walk's start:
invisible to the probe, and absent from the map. R-RETR itself established the mechanism when it ruled
`max` unsafe among the per-thread ids; the same argument applies to a watermark constrained to be at
least `max`. `test_a_watermark_taken_after_the_fetch_can_hide_a_change_the_handle_should_see` runs
that: the probe from the post-fetch watermark reports `touched == {}` and `conclusive`, and the probe
from a watermark taken before the first read reports `{'t-alpha'}`.

So the payload's arithmetic re-derivation is **gone rather than replaced**, and I say plainly what
that costs: nothing arithmetic cross-checks `history_id` any more, because no relation to
`thread_history_ids` holds in general (a quiet thread's own id is below it; a thread changed between
the observation and its read has one above it). The field joins `fetched_at`, `mapping_digest` and
`account_hash`, none of which is re-derived either: it is observed and signed, and a forged watermark
needs a forged signature. The property that *does* make it safe is an **ordering**, which no validator
over two integers can see, so it is checked where it is observable —
`test_the_mailbox_watermark_is_observed_before_the_first_thread_is_fetched` reads the transport's own
call log and asserts `profile` precedes `threads.get`.

**The residual, measured rather than argued** (`/tmp/ws10/p_residual.py`):

```
A. quiet thread, mailbox already 150 records ahead BEFORE the mint (A10's own case)
   cold: outcome=None calls=2   warm: outcome=None calls=1 from_cache=('t-alpha',)
B. how many changes AFTER the mint one page still covers
     99 post-mint records: outcome=None                      liveness=verified_unchanged
    100 post-mint records: outcome=None                      liveness=verified_unchanged
    101 post-mint records: outcome=handle_stale_unverifiable liveness=unverifiable
    150 post-mint records: outcome=handle_stale_unverifiable liveness=unverifiable
```

A10 closes the **unbounded** window: history that accumulated before the handle existed no longer
costs anything, the LRU serves, and a warm redemption is 1 call. What remains is bounded by the
handle's own ttl and is exactly Gmail's page default: **more than 100 mailbox history records inside
900 seconds** — a sustained rate above about 6.7 records per minute — still exhausts one page and
answers `handle_stale_unverifiable`. That is why the reviewer's `p3_watermark_reach.py` still prints
the old output: its 150 changes happen *after* the mint, where both derivations give the same walk
start, so it measures the page bound rather than the watermark. I am not treating that script's output
as a failure of A10, and I am not treating A10 as having closed it either.

**The one-line remedy I did not take, named.** `_fetch_liveness_page` sets no `maxResults`, so Gmail's
default of 100 applies; the documented maximum is 500 ([VERIFIED] RO F6) and `history.list` is charged
per call rather than per record, so 500 would cover five times the window at the same 2 quota units.
I did not take it: it is a latency and response-size trade nobody has measured, PF-3 has not run, and
this round's instruction was to *register* the sync page bound with its residue declared rather than
to tune it. It is R-GMAIL's and WS-12's, and it is written here so the silence is not read as
agreement.

### 0.4 · R-RETR-061 — `caught_by` citations, one at a time

`run_replants` ran every citation in one pytest invocation and read one return code, so `caught=True`
meant "at least one of them failed". `PlantResult.caught_per_citation` now records each citation run
**alone**, `caught` is `all(...)`, and `citations_that_do_not_catch` names the failures.

It bit immediately and correctly. My first R55 replant cited
`test_a_quiet_thread_redeems_clean_at_the_shipped_page_budget`, and that test did **not**
individually catch the plant: on a mailbox that has never moved, a single-thread handle's
`min(thread_history_ids)` and the mailbox watermark are *the same number*, so churn added after the
mint costs both derivations the same walk. The test now puts the 150 records **before** the mint and
asserts the gap — `int(history_id) - int(thread_history_ids[0]) == 150` — with a message saying that
without it the two derivations agree and the test discriminates nothing. R55's two citations now each
catch alone.

R50 and R51 — the two the finding named — now catch under both citations, because the widened matrix
made the property test genuinely defend the cache tautology and the `fetched_at` stamp.

### 0.5 · R-RETR-062 — the honest `elsewhere` column

`whole_suite=True` now runs with `--ignore=tests/test_replants.py`, so
`test_every_replant_anchor_matches_exactly_once_in_the_tree` — which is not marked `replant`, runs in
the default gate, and fails for any plant that rewrites its own anchored line — no longer makes the
column `True` before any behavioural test is consulted.

Round 22's own entries, per citation and with the corrected column
(`/tmp/ws10/p_replant_table.py`; every row: anchor matched once, file changed):

| replant | caught | elsewhere | per-citation |
|---|---|---|---|
| R55 the handle watermark is the thread's own instead of the mailbox's | True | **False** | both citations catch |
| R58 the watermark is observed after the threads are fetched | True | True | catches |
| R59 a walk that saw a change reports that it could not look | True | **False** | both citations catch |
| R60 a budget below the recoverability floor is accepted | True | True | catches |
| R61 a rung declined on evidence is reported as inapplicable | True | True | catches |
| R62 `not_found` is claimed over a ladder that is missing rungs | True | True | both citations catch |
| R63 rule 2 carries rule 1b's answer-type escape | True | True | catches |
| R64 a rung stopped part-way throws away the probes that ran | True | True | catches |
| R65 the budget is checked after the spend instead of before it | True | **False** | catches |
| R66 a blocked rung is reported without the call that reaches it | True | **False** | catches |

Four of ten are defended by exactly one test each. That is a perfectly acceptable state for a
replant and it is printed as `False`.

### 0.6 · R-RETR-063 and R-RETR-064 — recorded, not taken

* **R-RETR-063.** `MessageRow.reason` and `MessageRow.reason_detail.message_id_header` render a
  sender-chosen `Message-ID` verbatim. It is the same string as R-RETR-056's and it is R-SEC's and
  WS-14's call; I did not act on it and I am recording, as the finding asks, that this round did not
  narrow it either. The two locations stand as named.
* **R-RETR-064.** A cache-served redemption puts nothing into the `DispositionLedger` while handing
  back a map that names messages. Still true; still not a defect, because nothing assembles an
  `Envelope` from a redemption. It is WS-15's first problem and it is unchanged by this round.

---

## Part 1 — WS-10

New package `mailweave.policy`, three modules split by **what each one reads**:

| module | reads | holds |
|---|---|---|
| `budget.py` | a `CallMeter` and an injected clock | `BudgetRequest`, `AppliedBudget`, `apply_floor`, `BudgetAccountant`, `CapBreach`, `Governor` |
| `stopping.py` | signals already computed | AD D.3's rules, in `PUBLISHED_ORDER`, one named predicate each |
| `account.py` | neither | `RungState`, `RungAccount`, `LadderAccount`, `outcome_of` |

Nothing here computes a disposition. `withheld := H − disclosed` stays `DispositionLedger.certify`'s;
this layer reads the ledger's answer and refuses to say `not_found` over it.

### 1.1 · The caps, and the floor clamp

AD A.7's whole cap table is now constants (`MAX_QUOTA_UNITS` 1,200 / `MAX_QUOTA_UNITS_SEMANTIC` 2,400,
`MAX_API_CALLS` 80, `MAX_HTTP_REQUESTS` 24, `MAX_SERVER_MS` 2,000, `MAX_SEMANTIC_MS` 6,000,
`MAX_CONCURRENT_QUERIES` 2), swept against the document's own numbers by
`test_every_published_cap_is_a_constant_this_module_enforces` with the values quoted rather than
imported.

`apply_floor` has three cases and a test each: no request (default, no clamp); at or above the floor
(verbatim, no clamp); below the floor (raised to exactly 845, `budget_clamped{requested, applied,
why}` on the wire). A request *above* the published default is honoured — A.7 clamps from below only
and there is no ceiling on a caller's own quota. `BudgetClamp`'s own validators already refuse a clamp
that lowers and one landing under the floor, so the only representable clamp is the one A.7 describes.

`BudgetAccountant.check` refuses **before** the spend.
`test_the_accountant_refuses_before_the_spend_and_not_after_it` drives it to refusal and asserts the
*meter* — two calls under a two-call budget, not three. The time cap is checked first, and
`test_a_time_cap_is_reported_before_a_call_cap_when_both_would_fire` executes why: a query that ran
out of time ran out however cheap the next call is, and naming `max_api_calls` would send the caller
to raise the wrong number. Both caps are recorded, and `caps_hit` keeps them in the order they fired.

`Governor` is the process-wide half: two admissions, then `BudgetRefused` with
`cap = process_quota_refused`, and release on the way out even when the query raises. The accountant
is constructed *by* `admit`, so a query that was never admitted has no accountant to spend through —
A.7's nesting as a construction rule rather than a convention.

### 1.2 · D.3's rules, in their published order

`PUBLISHED_ORDER` is data, and `test_the_published_order_is_the_order_the_document_prints` parses
`docs/ARCHITECTURE_DECISION.md` §D.3's own numbered list and compares:
`("0","1","1b","2","3","4","5","6")`. An order a reader has to check by eye is an order this project
has twice failed to check by eye.

Each rule is a separate named predicate. `mailweave.retrieval.ladder` now **calls** them for the
subset a lexical rung can reach (0, 1, 1b, 2) instead of restating them, so rule 2 and rule 1b cannot
come apart between two readers again. `first_rule_that_fires` iterates `PUBLISHED_ORDER` and looks
each predicate up, rather than being an if-chain that can be reordered by one line;
`test_the_first_rule_that_fires_is_the_first_one_in_the_documents_order` constructs an input on which
rules 1, 1b, 2, 3 and 5 all hold and asserts rule 1 comes back.

Round 16's defect is executed as its own test over all three values of the tri-state:
`test_rule_two_does_not_carry_rule_one_bs_escape` asserts rule 2 requires `present is True` while rule
1b takes `present is not False`, at `True`/`None`/`False`. `rule_4_escalates` carries two disjuncts
that are **not computable today** — `paraphrase_risk ≥ θ` (θ is [PRE-REG at G0]) and a tier-1
`non_lexical` confidence (WS-09's). They arrive as `None` and are treated as *not firing* rather than
as false, and the docstring says so; writing them in as `False` would be the claim wider than the
code, one disjunct at a time.

### 1.3 · The mid-rung timeout contract

The accountant is consulted at **four** points, all the same way — before the call, keeping what
already ran:

1. before each lexical probe (`LadderRunner.run_parsed`);
2. before each body fetch (`_fetch_bodies`);
3. before each `threads.get` at the map stage (`assemble`);
4. before each L4 structural probe, and before the `getProfile` watermark.

A rung stopped part-way keeps its executed probes, and — this is the part I got wrong first and
execution corrected — it appears in **both** `rungs` and `not_tried`. `Envelope` refuses a `rungs`
that omits a rung which admitted ids ("a route that produced evidence and is not listed is a route the
reader cannot see", EV-01/PART-01), so reporting a mid-rung stop only as `not_tried` makes the
response unbuildable. Both facts are true and both are needed: the probes that ran produced evidence
the reader must see, and the probes that did not are work the caller is owed a call for. `rungs_run`
now includes a rung that sent at least one probe, and `rungs_cut_short` names the shape.

Threads the budget stopped us from mapping become `withheld` records naming the cap
(`WITHHELD_CAP_OF`) with the call that raises it. Nothing observed is dropped: the certificate's
`hit_count == disclosed_hits + len(withheld_ids)` is asserted for every shape.

Executed: `test_a_budget_that_stops_the_maps_emits_what_it_retrieved_and_withholds_the_rest` (the
three clauses in one run) and `test_a_rung_stopped_part_way_keeps_the_probes_that_ran`, which asserts
`partial` is non-empty *before* iterating it — the loop would otherwise assert nothing, which is the
vacuity this round is about.

### 1.4 · OD-2's three-way outcome

`outcome_of` is the one producer. `not_found` requires **all** of:

* no rung untried for a blocking reason;
* `budget_caps_hit` empty;
* nothing withheld — passed as `hits`, the size of `H`, and not as a withheld count, because
  computing one would mean computing `H − disclosed` a second time and that set difference is
  `certify`'s. The identity that makes `hits` the right input is A.7a's own, and the clause is reached
  only when nothing was disclosed;
* no unfetched pages;
* and **every rung of `LADDER` has an account**. L5, L6 and LR are unbuilt, so this clause is what
  keeps `not_found` off the wire today — as a rule, not as a caller's discipline. There is no honest
  `not_tried[].why` for "this rung does not exist yet": one value would claim it could not have
  helped and the other five would claim some call reaches it. The absence is read as an absence.

`answered` needs disclosure, evidence the query itself produced, no truncation, **and no cap having
fired** — D.3 rule 5 read as it is written ("The outcome is `inconclusive`, never `not_found`"), not
merely as "never `not_found`". That is the clause that keeps a partial answer from contradicting its
own `budget` block, and `blocked/structural` in the matrix is exactly that case: four sources
disclosed, L4 blocked by `max_api_calls`, outcome `inconclusive`.

Executed: `test_not_found_needs_every_condition_and_each_one_alone_withholds_it` (one assertion per
conjunct, each alone), `test_a_ladder_missing_a_rung_entirely_cannot_say_not_found` (and the same
evidence over a *complete* ladder giving `not_found`, so the clause is doing the work),
`test_answered_needs_disclosure_and_evidence_the_query_itself_produced`, and end to end
`test_no_response_this_build_can_produce_says_not_found`. The wire validator
`RetrievalReport._od2_outcome_rule` is untouched and is a second, independent refusal: one produces
an honest outcome, the other refuses a dishonest one.

---

## The commonality across the ladder's shapes

**Stated once:**

> Every rung of the ladder is, at every moment, in exactly one of three accounted states — **ran**,
> **not applicable**, or **blocked** — the state is decided before the rung is reached and recorded
> when it is; and the response's `rungs`, `not_tried`, `budget_caps_hit` and `outcome` are all read
> off that one record rather than derived a second time.

The one exception is not an exception to the *account*, only to the arithmetic: a rung whose plan a
cap **split** is in two states at once, because the account is over its plan and the plan was in two
parts. That is the mid-rung case and it is a clause rather than a footnote.

**The test:** `tests/test_ws10_escalation.py::test_every_rung_is_accounted_for_in_exactly_one_state`,
over `SHAPES` — **eleven** whole queries run end to end through the real ladder and the real
assembly, under eleven budget and clock settings. Nine clauses: (a) totality, and the both-lists
case requiring a declared probe to show for it; (b) `not_applicable` is exactly the reason with no affordance; (c) a named cap is in
`budget_caps_hit` **and the affordance reaches what the reason blocked** — a budget-blocked rung
offers the call that raises *that cap*, a policy-declined rung offers `force_rungs`; (d) OD-2, both
directions; (e) `answered` implies rows; (f) `hit_count_per_rung` covers exactly the rungs listed as
run; (g) a cap makes the outcome inconclusive; (h) the spend never exceeded the applied budget and the
applied budget was never under the floor; (i) `H = disclosed ∪ withheld`, read off the certificate.

### Proof its matrix reaches every shape it claims — R-RETR-058's lesson, applied here

`test_the_shape_matrix_reaches_every_state_and_every_outcome_it_asserts_about` asserts over the
**answers**, never over the keys in `SHAPES`, and each assertion names the clause it keeps honest.
Printed (`/tmp/ws10/p_matrix.py`):

| shape | outcome | rungs run | `not_tried` (non-`not_applicable`) | caps | src | withheld | clamp |
|---|---|---|---|---|---|---|---|
| `answered/plain` | answered | L1,L4 | L3:stopped_on_evidence | - | 5 | 0 | False |
| `answered/decomposed` | answered | L1,L1b,L4 | L2,L3:stopped_on_evidence | - | 5 | 0 | False |
| `empty/relaxed` | answered | L1,L1b,L2 | L3:stopped_on_evidence | - | 1 | 0 | False |
| `empty/unrelaxable` | inconclusive | L1,L3 | - | - | 0 | 0 | False |
| `answered/exact` | answered | L0 | L1,L3:stopped_on_evidence | - | 1 | 0 | False |
| `blocked/before_the_first_probe` | inconclusive | - | L1:cap, L3:cap | max_api_calls | 0 | 0 | False |
| `blocked/before_the_maps` | inconclusive | L1 | L3:cap | max_api_calls | 0 | 4 | False |
| `blocked/timeout` | inconclusive | L1 | L1b,L2,L3:timeout | max_server_ms | 0 | 0 | False |
| `blocked/mid_rung` | inconclusive | **L1,L1b** | **L1b**,L2,L3:timeout | max_server_ms | 0 | 1 | False |
| `answered/clamped` | answered | L1,L4 | L3:stopped_on_evidence | - | 5 | 0 | **True** |
| `blocked/structural` | inconclusive | L1 | L3:stopped_on_evidence, **L4:cap** | max_api_calls | 4 | 0 | False |

```
outcomes reached          : ['answered', 'inconclusive']
not_tried whys reached    : ['cap', 'not_applicable', 'stopped_on_evidence', 'timeout']
caps reached              : ['max_api_calls', 'max_server_ms']
states reached            : ran=True not_applicable=True blocked=True
affordance both sides     : True True
withheld both sides       : True True
clamp both sides          : True True
not_found present         : False
```

Every clause has a witness on both sides: a rung that ran and one that did not; an entry with an
affordance and one without; a run that hit a cap and one that did not; a *time* cap as well as a call
cap; a clamped budget and an unclamped one; a response with withheld records and one without; and
`blocked/mid_rung`, which is the only shape reaching clause (a)'s both-lists branch — without it that
branch is a loop over an empty set and the mid-rung contract is asserted by nothing.

**`not_found` is absent, and its absence is asserted rather than assumed.** The matrix test asserts
`Outcome.NOT_FOUND not in outcomes` with the message saying why and saying what to do when it fails:
the day L5, L6 and LR exist, that assertion is what will fail and tell the next implementer the matrix
should now reach `not_found`. The rule that produces the absence is executed separately at the unit,
over a complete account, so `outcome_of` is exercised over **all three** outcomes even though the
integration reaches two.

**The matrix found three defects in my own clauses while I was building it**, and I record them
because that is the evidence the check works: clause (a) was written as disjointness and is false at
the mid-rung boundary; clause (g)'s "a cap implies inconclusive" was false until I read D.3 rule 5
properly; and gating only the lexical probes left body fetches, L4's probes and the watermark call
uncharged — `blocked/before_the_maps` reported four API calls under a two-call budget, which is
exactly the "accepted-and-then-overrun" A.7 forbids.

---

## The ruling on `not_tried[].why`

**Question, as round 15 left it:** the vocabulary has no value for *"the policy declined to run this
rung because evidence already existed."*

**Ruling: `not_applicable` is the wrong word. A fourth value, `stopped_on_evidence`, is added.**
Three reasons, in the order that decides it.

1. **`not_applicable` states something false.** Its meaning — the one a caller reads and the one that
   makes it the single value compatible with `not_found` — is *this rung could not have helped this
   query*. L5 after D.3 rule 1 stopped the ladder is not a rung that could not have helped; it is a
   rung nobody needed. Those are different facts about the mailbox, and writing the second under the
   first's name is a claim wider than the code in the field OD-2's whole distinction rests on. Round
   15 got away with it only because it never emitted `not_found`, which is the vocabulary being wrong
   with nothing going red.
2. **The two have different remedies, and that is this project's own test for whether a distinction is
   real** — the test that made `MailboxProvenance` a field rather than a mention and `Linkage`'s gaps
   separate members. `not_applicable` has no affordance and can have none: no budget reaches a rung
   that does not apply. `stopped_on_evidence` has one, and it already exists in the plan — WS-15's
   `force_rungs`, which "can only add rungs". A vocabulary that cannot tell *there is nothing more*
   from *there is more and you may have it* loses the affordance, which is the thing AD-03 exists for.
3. **It is safe against OD-2 twice over, and the code rests on the second rather than on the first.**
   A D.3 stop rule fires only on non-zero evidence — rules 1 and 1b need `exact_signal_match` with at
   least one hit, rule 2 needs `hit_count ∈ [1,5]`, rule 3 needs `sufficiency == sufficient` — so
   `not_found`'s own second conjunct ("and no evidence was found") is already false wherever this
   value can appear. I did not want the guarantee to rest on that argument, so
   `stopped_on_evidence` is in `BLOCKING_NOT_TRIED` and a response carrying one is refused
   `not_found` **mechanically**. The cost of the belt-and-braces is nil: no response that could
   honestly say `not_found` can carry this value.

**How the addition is kept visible rather than absorbed.** `BLOCKING_NOT_TRIED` is now derived as
`frozenset(NotTriedWhy) - {NOT_APPLICABLE}` rather than listed, so a member added later forbids
`not_found` until somebody argues that it should not — the safe default, and the same derivation
`DECLARED_GAP_LINKAGES` uses. `PUBLISHED_NOT_TRIED` holds AD D.2's five verbatim, and
`test_the_vocabulary_is_the_published_one_plus_exactly_one_argued_addition` asserts the difference is
exactly `{"stopped_on_evidence"}` — so a *second* addition cannot arrive without somebody making the
same case. `tests/test_outcome_od2.py` quotes the published list and the addition as two separate
sets.

**What it changes on the wire.** Every rung the policy declined — the D.3 halt, and L2/L3 declined
because `evidence_count != 0` — moves from `not_applicable` to `stopped_on_evidence` with a
`force_rungs` affordance. `answered/plain` above shows it: L3 is `stopped_on_evidence`, not
`not_applicable`, because L3 was applicable and L1 had already found three threads.

**This is an implementer's addition to a published closed vocabulary and I am flagging it as one.**
AD D.2 is the owner's document; I have made the case here and in `NotTriedWhy`'s own docstring, and if
the reviewer or the owner rules the other way the change is one enum member and one branch in
`run_parsed`.

---

## Every docstring claim about a budget or an outcome, with its evidence

| Claim, and where it is written | Executed by |
|---|---|
| `apply_floor`: a request below the floor is raised to exactly 845 and declared | `test_a_budget_below_the_floor_is_clamped_up_and_the_clamp_is_declared` |
| `apply_floor`: at or above the floor is honoured verbatim, no clamp; A.7 clamps from below only | `test_a_budget_at_or_above_the_floor_is_honoured_verbatim_with_no_clamp` (incl. 10× the default) |
| `apply_floor`: no request declares no clamp | `test_no_request_declares_no_clamp` |
| `AppliedBudget`: `semantic` widens the quota cap to A.7's escalated figure | `test_every_published_cap_is_a_constant_this_module_enforces` |
| `BudgetAccountant`: "refuses **before** the spend, never after it" | `test_the_accountant_refuses_before_the_spend_and_not_after_it` — asserts the *meter*, 2 calls under a 2-call budget |
| `BudgetAccountant.check`: "the time cap comes first" | `test_a_time_cap_is_reported_before_a_call_cap_when_both_would_fire` |
| `BudgetAccountant.check`: "every cap that fires is recorded, so a response that hit two names two" | same test — `caps_hit == (max_api_calls, max_server_ms)` |
| `enter_semantic`: the semantic deadline is a separate cap | `test_the_semantic_deadline_is_a_separate_cap_from_the_lexical_one` |
| `CapBreach`: every breach carries the call that raises **that** cap; `why` is `timeout` for time caps | `test_every_cap_breach_carries_the_call_that_would_raise_it`; clause (c) of the commonality |
| `Governor`: admits to the limit, then refuses by name; the accountant is created by `admit` | `test_the_governor_admits_up_to_its_limit_and_refuses_by_name` |
| `Governor.query`: releases even when the query raises | `test_the_governor_releases_even_when_the_query_raises` |
| `RungAccount`: the two impossible records cannot be built (four shapes) | `test_the_two_impossible_rung_records_cannot_be_built` |
| `outcome_of`: OD-2's conjunction, each conjunct alone withholding `not_found` | `test_not_found_needs_every_condition_and_each_one_alone_withholds_it` |
| `outcome_of`: a ladder missing a rung cannot say `not_found` | `test_a_ladder_missing_a_rung_entirely_cannot_say_not_found` (+ the complete-ladder control) |
| `outcome_of`: `answered` needs disclosure **and** query evidence **and** no cap | `test_answered_needs_disclosure_and_evidence_the_query_itself_produced`; clause (g) + `blocked/structural` |
| `LadderRunner.__init__`: "the default is no budget rather than an unlimited one" | the 2,474-test suite, every existing caller of which constructs a runner without one |
| `_fetch_bodies`: "a body the budget stopped is not lost — the id is in `H`" | clause (i) over `blocked/before_the_maps` (4 withheld, 0 disclosed) |
| `_execute_structural_expansion`: L4's probes are charged like every other probe | `blocked/structural`; the matrix's "structural rung, blocked by a budget" assertion |
| `_mailbox_watermark`: one `getProfile`, **only** when a minter exists | `test_a_response_that_cannot_mint_handles_does_not_pay_for_the_watermark` |
| `_mailbox_watermark`: charged like every other call; no watermark ⇒ no `map_id` | `test_a_budget_that_cannot_afford_the_watermark_mints_no_handle` |
| `redeem`: a clean redemption's walk ran "to the end of Gmail's history" | `test_a_clean_redemption_is_never_issued_by_an_incomplete_walk` |
| `MAX_LIVENESS_PAGES`: one page covers the handle's ttl after A10 | `test_a_quiet_thread_redeems_clean_at_the_shipped_page_budget`; the residual is measured in §0.3 |
| `HandlePayload.history_id`: a post-fetch watermark can hide a change | `test_a_watermark_taken_after_the_fetch_can_hide_a_change_the_handle_should_see` |
| `mint`: the ordering "cannot be checked here" and is checked where it is observable | `test_the_mailbox_watermark_is_observed_before_the_first_thread_is_fetched` |
| `LivenessProbe.conclusive` / `.saw_a_change`: neither flag devalues a positive finding | `test_a_walk_that_saw_a_change_and_ran_out_of_pages_reports_what_it_saw`, and the four-cell partition test |

Two claims in this table rest on the suite rather than on a named assertion, and I mark them as such:
"the default is no budget rather than an unlimited one" is established by every pre-WS-10 caller still
passing, not by a test written for it.

---

## Have I trusted a peer?

Yes, three times, in this round, in the budget work itself — and I found all three by building the
shape matrix rather than by re-reading the code.

1. **Body fetches.** I gated the lexical probes and stopped. `blocked/before_the_maps` then reported
   four API calls under a two-call budget: `_fetch_bodies` was spending `messages.get` outside every
   cap. A.7's caps are per *query*, not per rung, so a run that spent its whole `max_api_calls` on
   bodies has spent it. Fixed, and replanted as R65.
2. **L4's structural probes.** Same shape one rung further out, and the matrix could not see it until
   I added a thread whose reply parent is filed elsewhere — without one, L4 never plans a probe and
   every clause about the structural rung's budget is asserted over a rung that never runs. Fixed; the
   matrix now carries `blocked/structural` and asserts that a *structural* rung blocked by a budget is
   reached.
3. **The `getProfile` watermark.** A response with a minter and an exhausted budget still spent a unit
   on a watermark it would then use to mint a handle. Now the accountant is asked, and a query that
   cannot afford the watermark mints no `map_id` — the same rule `_map_id_for` already applied to a
   thread with no `historyId`, for the same reason.

And once more, in the tests rather than the code: `test_a_rung_stopped_part_way_keeps_the_probes_that_ran`
iterated a list I had not asserted was non-empty. It was non-empty, but only at one particular clock
tick — at `MAX_SERVER_MS / 2` the stop lands *between* rungs and the loop asserts nothing. The
assertion is now there with the reason.

Where I have **not** re-verified a peer and am relying on the round-21 work: the five error classes,
the LRU's bypass-and-evict, the `fetched_at` non-restamping and the 300-sequence liveness property.
R-RETR attacked all of them and could not get around them; I changed the watermark's *derivation* and
one branch condition, and re-ran the whole handles file plus the eleven-shape property after each. I
did not rebuild R-RETR's 300-sequence oracle.

---

## What I could not establish

* **`not_found` end to end.** No response this build can produce may claim it, because L5, L6 and LR
  do not exist. The *rule* is executed over a complete account; the *integration* reaches two of the
  three outcomes. This is not a gap I can close from here — it closes when WS-12 (LR) and WS-13 (L5/L6)
  land, and the matrix test is written to fail loudly on that day.
* **Whether the shipped `MAX_LIVENESS_PAGES = 1` is the right sync budget.** I registered it as its
  own number with its residue declared and measured (§0.3). Whether 1 page or `maxResults=500` or both
  is right depends on a real mailbox's history rate, which is R-GMAIL's and PF-3's.
* **Whether a relaxed answer should be `answered`.** A query whose only evidence came from an L2
  relaxation reports `answered` with `asked_for.dropped` naming what was given up. That is the
  behaviour before this round and I did not change it; I record it because `unrelaxed_evidence_count`
  exists and a reviewer may reasonably think `inconclusive` is the honest value. It is a contract
  question, not an implementation one.
* **Rule 4's two uncomputable disjuncts.** `paraphrase_risk ≥ θ` and tier-1 `non_lexical` are `None`,
  treated as not-firing, and named as such in the predicate's docstring. θ is [PRE-REG at G0] and the
  confidence signal is WS-09's.
* **The semantic quota widening.** `apply_floor(semantic=True)` exists and is tested at the unit; no
  code path sets it, because nothing escalates to L5. WS-13's.
* **`Governor` under real concurrency.** It is a counter, not a semaphore, because this server is
  stdio-serial. `process_quota_wait` has no producer. A second concurrent client is MCP-02's other half
  and is WS-15's, exactly as R-RETR said.

---

## Unreachable from code that exists today

| Thing | Workstream | Blocks integration under OD-6? |
|---|---|---|
| `outcome: not_found` on a real response | WS-12 (LR), WS-13 (L5/L6) | **No.** `inconclusive` is the honest answer while the ladder is incomplete, and it is produced by a rule rather than avoided |
| `BudgetCapName.PROCESS_QUOTA_WAIT` | WS-15 (a second concurrent client) | No |
| `policy.account.blocked_by` — a constructor with no production caller; `assemble` builds its accounts from the `not_tried` entries it is shipping | WS-15, when the MCP surface builds an account for a rung it declined | No. Named here so its absence from the production path is on the record; its behaviour is exercised at the unit |
| `AppliedBudget.max_pool_threads` / `max_pool_messages` / `max_rerank_pairs` / `max_recency_fetch` — carried, not enforced | WS-12, WS-13 | No. They are A.7's numbers held in one place so the rung that arrives finds them; nothing claims they are enforced |
| `Redemption`'s own budget — `redeem` spends two Gmail calls under no accountant | WS-15 | No, and it is worth a line: a redemption is a tool call, not a query, and A.7's caps are per top-level query. WS-15 has to decide whether a `map_id` redemption is charged to the query that follows it |
| R-RETR-064's warm-redemption ledger gap | WS-15 | No — unchanged by this round, and WS-15 hits it on its first attempt to build a response from a redemption |
| `Source.verified_at` produced by `redeem` and set by nothing | WS-15 | No |

None of these blocks integration. OD-6's counter-rule is satisfied: this round produced a workstream
and closed five filed findings.

---

## Gates

```
$ ruff check .
All checks passed!

$ ruff format --check .
178 files already formatted

$ mypy
Success: no issues found in 152 source files

$ python -m tools.guards
guards clean: forbidden-import, generative-client, gmail-endpoint, ground-truth-isolation,
scope-literal, unaudited-disk-write, unwrapped-http-client over server/src

$ pytest -q -m "not network"
rc 0 - collected 2,474 (independently summed from --collect-only -q per file; 2,439 before this round)

$ pytest -m replant -q
4 passed - still inside the default gate, not deselected from it

$ tools/rubric_status.py --check
criteria: 113  (mandatory 110, conditional 2, optional 1)
  PASS 6   FAIL 0   BLOCKER 0   NOT TESTED 107
reviewer transitions recorded: 11
```

I marked no rubric criterion. I did not restore ROUTE-01. I did not edit `FINDINGS_LEDGER.md` or
`RUBRIC_TRANSITIONS.md`. I did not touch `RETRY_BASE_MS`, `RETRY_FACTOR`, `RETRY_JITTER_FRACTION`,
`MAX_RETRIES` or `MAX_BACKOFF_TOTAL_MS` — the new `MAX_LIVENESS_PAGES` sits two blocks above them in
`constants.py` and is a page budget, not a retry constant. No LLM call, no embedding, no network in
tests, and no fixture in this round carries real or realistic personal mail: every address is
`.example` or `.invalid`, and the vocabulary (`quillevant`, `sprindle`) is invented.

## Files changed

**New:** `server/src/mailweave/policy/{__init__,budget,stopping,account}.py`,
`tests/test_ws10_escalation.py`.
**Changed:** `server/src/mailweave/constants.py`, `envelope/vocab.py`, `gmail/client.py`,
`handles/mint.py`, `handles/redeem.py`, `retrieval/assemble.py`, `retrieval/ladder.py`;
`tests/test_handles_round21.py`, `tests/test_lexical_ladder.py`, `tests/test_outcome_od2.py`,
`tests/test_replants.py`, `tests/fixtures/replants.py`.
**Probe scripts** (mine, outside the tree): `/tmp/ws10/plantkit.py`, `p_clauses.py`, `p_a10.py`,
`p_h.py`, `p_r55.py`, `p_r65.py`, `p_matrix.py`, `p_matrix_handles.py`, `p_midrung.py`,
`p_residual.py`, `p_l4budget.py`, `p_replant_table.py`.
