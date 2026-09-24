# Why the diagnostic scored zero: verified causes and a bounded repair proposal

The real-backend diagnostic run of 2026-09-13 (`benchmarks/diagnostic-run-4311.{txt,json}`,
md5 `2f596f3c…` / `4ed0978f…`, preserved unchanged) scored `full` 0/13 on answerable cases,
failed on 10/15, and scored both primitive floors 0/13. This document is the diagnosis the
owner asked for, in the two paths asked for. Every number below was reproduced on the
no-backend arms (`sem-off`, `sem-off+fixed-window`) in the isolated environment, so no model
and no stand-in is involved in any of it; the scripts are in `benchmarks/diagnosis-4311/`.

The fifteen exposed cases were used as development cases. None of their answers, quotes or
scoring rules was changed, and no limit was raised.

## Path 1 - the measurement is sound; the expansion surface is not

### 1a. Positive control: the scorer recognises fetched content

`g-t0011-004` (DIAG-SEM-01's primary evidence) fetched by its recorded id through the same
`GmailClient` and content pipeline the primitive floor uses returns 179 characters, and
`disclosed(Disclosure({id: text}), id, quote)` is **True**. The ids on both sides of the join
are the raw mailbox ids (`MessageRow.id` is the raw id; a root message fetched through
`service.get_messages` comes back keyed `g-t0011-000` in `content_by_id`). The scorer, the
content pipeline and the evidence-id join are not where the zeros come from.

### 1b. `mailweave_get_messages` raises for every reply fetched without its whole ancestor chain (R-M2-077, product, BLOCKER)

| request | result |
|---|---|
| `message_ids=[root]` | OK, content returned |
| `message_ids=[pos 4]`, any content view | **raises** `ValidationError`: *"declares linkage=in-reply-to … and names none (C-02a)"* |
| `message_ids=[pos 3, pos 4]` | **raises** on pos 3 (its parent, pos 2, is not in the request) |
| `map_id` + `positions=[89]` | **raises**, both views |
| `view=stub` | OK, zero rows |

Cause, in `surface/expansion.py::_rows_of`:

```python
linkage=link.linkage,
reply_parent_id=(link.parent_id if link.parent_id in present else None),
```

The parent id is masked whenever the parent is not among this response's rows, while the
linkage still says a parent was found. `MessageRow`'s C-02a validator refuses that pair, so
the call raises. `retrieval/assemble.py` (the search path) names the parent unconditionally
at both of its row sites, which is the correct reading of C-02a: the parent is a fact of the
thread, whether or not this response happens to carry it. Every affordance that names a
single message - a row's `unabridged`, a withheld record, a thread map position - executes
this path, so the expansion surface cannot return the body of any reply unless the caller
also requests its entire chain back to the root. `arms._execute` swallows the raise as
`None`, so in the diagnostic it is invisible and reads as "expansion reached nothing".

### 1c. A non-declining miss, traced: DIAG-EXP-01 on `sem-off`

Query *"What notice period does the Lantern agreement carry?"*; evidence `t0010` position 89.

1. **Search.** The ladder issued five `q` strings: the full conjunction (0 ids), `notice`
   (100), `period` (0), `lantern` (100, **includes the evidence**), `in:anywhere …` (0).
2. **Selection.** The response's two sources are `t0004` and `t0005`; `t0010` is in
   `not_included_sources` with a thread-map affordance. Zero content rows in the response.
3. **Expansion, hop 1.** The harness driver executes `thread_map(t0010)`. The map comes back
   with `stated_total=92`, **zero rows**, one collapsed run of all 92 members and one
   affordance: `get_messages(message_ids=[all 92], view=snippet)`. The evidence is now
   *surfaced* (its id is in the run) and still not in hand.
4. **Hop 2.** That affordance executes and returns 0 content: snippets are not disclosure
   under EP §6.1, correctly.
5. **Hop 3.** `get_messages(map_id, positions=[89])` - the call a reader would make next -
   **raises** (1b).
6. **The driver never gets to hops 2-3 anyway** (R-M2-078, harness): `arms.follow()` reads
   recovery affordances from the *first* envelope only, so an affordance offered by a thread
   map it obtained during recovery is never executed. Expansion is one hop by construction,
   and `after_expansion` understates reach for every multi-hop case.

Result: `surfaced_only={g-t0010-089}`, `after_expansion=∅`, twelve calls executed, three of
them raising `DisclosureLadderExhausted` on `thread_map(t0004, segment=…)`.

### 1d. The primitive floor's zero is a property of the floor, not of the scorer (R-M2-079)

`PrimitiveTools.search` passes the case's question **verbatim** as Gmail `q`. Under the
synthetic mailbox's conjunctive `q` - every whitespace token must match the message, which is
what Gmail's own filtering guide documents - a fifteen-word question with punctuation
attached matches nothing. Measured: **0 ids on 15 of 15 queries** at the generous budget. The
floor as built cannot retrieve anything for a natural-language question, so its 0/13 says
nothing about MailWeave's margin over primitives. This is disclosed, not repaired.

### 1e. Where the lexical rungs actually stand, per case (no backend)

`*` marks a probe whose hits include the required evidence.

| case | outcome | probes (ids returned) | threads touched |
|---|---|---|---|
| DIAG-SEM-01 | answered, 0 content | 0 0 83 28 0 | 30 |
| DIAG-SEM-02 | answered, 0 content | 0 17 61 0 0 | 12 |
| DIAG-SEM-03 | answered, 0 content | 0 0 23 0 0 | 7 |
| DIAG-RANK-01 | declined | 0 28\* 56\* 21 | 26 |
| DIAG-RANK-02 | answered, 0 content | 0 21 0 0 0 | 16 |
| DIAG-RANK-03 | declined | 0 27\* 47\* 28\* 0 | 19 |
| DIAG-RANK-04 | declined | 3\* 50\* 51\* 54\* | 33 |
| DIAG-EXP-01 | answered, 0 content | 0 100 0 100\* 0 | 5 |
| DIAG-EXP-02 | declined | 0 51\* 100 0 0 | 21 |
| DIAG-EXP-03 | answered, 0 content | 0 21\* 33\* 100 0 | 21 |
| DIAG-REV-01 | answered, 0 content | 0 33 51 53 0 | 42 |
| DIAG-REV-02 | declined | 0 44\* 54\* 100 0 | 62 |
| DIAG-REV-03 | declined | 0 21 100\* 29\* 0 | 50 |
| DIAG-UNANS-01 | declined | 0 49 100 67 0 | 50 |
| DIAG-UNANS-02 | answered | 1 21 33 58 | 30 |

The lexical rungs retrieve the evidence in **8 of 13** answerable cases. Every one of those
eight then either declines (6) or answers with zero content rows (2). On the no-backend arm,
retrieval is not the first-order failure for those eight; disclosure is. The other five
(SEM-01/02/03 by design, RANK-02, REV-01) are never retrieved lexically and can only be
reached by the semantic rung; whether the real backend pooled them on the Mac run is
**unestablished** - the run's JSON does not carry pool contents, and nothing here speaks to it.

Two things the probe strategy does that this document records and does not audit: it
widens to single terms even after the conjunction has already hit (RANK-04's conjunction
returned exactly the three messages of the right thread, evidence included, before three
generic probes touched 32 more threads), and its single-term probes are the first three
content terms in order, so `off`, `far`, `carries`, `contractual` are probed and the entity
name often is not.

## Path 2 - R-M2-076 reproduced on DIAG-RANK-04, step by step

Query *"Who carries contractual liability under the Jarrow agreement?"*, evidence `t0035`
position 5. Ceilings: 9,000 tokens normal, 12,000 overflow, **25,000 characters** host cap.

### 2a. The ladder

| step | tokens | chars | sources | rows | evidence |
|---|---|---|---|---|---|
| as planned | 86,013 | 758,047 | 9 | 592 (461 stub, 121 snippet, 10 body) | present |
| 1 query-scored fill | 85,493 | 752,297 | 9 | 592 | present |
| 3 hit bodies beyond top-k | 84,301 | 732,879 | 9 | 592 | present |
| 4 floor bodies | 83,201 | 720,625 | 9 | 592 (587 stub) | present |
| **5 hit-thread stub runs** | **6,840** | **82,119** | 9 | 8 + 11 runs | present |
| 6 overflow ceiling | no change | | | | |
| **7 split by source** | 2,365 | 24,294 | **0** | 0 | withheld |

Step 5 brings the layout inside the **token** ceiling with the evidence still present as a
`body_clean` row. What is over is the **character** cap, by 3.3×. Step 7 then removes every
source at once, and the ladder "fits" by carrying nothing, which `_carries_nothing` correctly
refuses to emit.

### 2b. What consumes the characters at step 5

| source | rows | run members | chars | note |
|---|---|---|---|---|
| t0035 | 6 (3 body, 3 stub) | 5 | 13,567 | **evidence** |
| t0005, t0006, t0007, t0008, t0009, t0004 | **0** | 90-94 each | 6,292-6,488 each | six empty sources, 38k chars |
| t0002, t0033 | 1 each | 7, 19 | 5,029, 6,588 | |

Six sources that carry **no rows at all** cost 38,000 characters between them, purely to
list ~550 member ids of collapsed runs. The one source that carries the answer costs 13,567
for three ~200-character bodies and three stubs.

### 2c. Why step 7 removes everything rather than something

Every one of the nine sources holds E2 floor members (5, 8, 10, 6, 11, 11, 20, 11, 2 of the
84 floor ids). Step 7 only splits a source that holds none, so its loop finds **zero
candidates**; the fallback `_split_a_source_whose_floor_does_not_fit` then removes all nine.
The step is all-or-nothing under this floor, not selective.

### 2d. The evidence source alone does not fit either, and here is the accounting

With every other source split off and `t0035` kept:

| item | chars |
|---|---|
| response structure | 2,600 |
| request echo | 2,034 |
| recommended-expansion block | 860 |
| evidence source (6 rows, 1 run, participants) | 13,567 |
| withheld records ×4 | 2,684 (671 each) |
| **withheld groups ×24** | **12,432** (518 each) |
| withheld tail ×1 | 662 |
| not-included sources ×8 | 2,784 (348 each) |
| **total** | **37,623** vs 25,000 |

**24,056 characters - 96% of the cap - is bookkeeping for the 656 accounted ids that are not
in the response.** The four probes touched 33 threads; 9 were fetched, 21 were capped by A.7
before the ladder ran and each becomes a ~518-character `withheld_groups[]` entry named one
by one (all foldable, all named, because 21 is under `MAX_WITHHELD_GROUPS_NAMED = 24`). The
response cannot fit its own pointers, before a single body is considered.

### 2e. Real limit, overestimate, or accounting defect?

- **The 25,000-character cap is a real, declared host limit** - `HOST_RESULT_CHAR_CAP`,
  [VERIFIED] in the architecture, enforced because the host cuts above the SDK. Whether the
  actual host would accept more is PF-6's question (`_meta["anthropic/maxResultSizeChars"]`
  is not read by this build) and is not answered here.
- **The estimates are faithful or conservative, never under.** Measured against rendered
  wire: a stub row estimates 1,038 and renders 744 (+40%); a 92-member collapsed run estimates
  4,948 and renders 2,943 (+68%); body rows are measured, not estimated. The margin is a
  multiplier, not the cause: rendered rather than estimated, the step-5 layout is still
  ~55,000 characters against 25,000.
- **The cost is the wire format's per-record overhead, and it is real.** One body row
  carrying 196 characters of text renders 1,762 characters, 753 of them a `reductions[]` block
  declaring a whitespace normalisation that removed one character and a signature
  classification that removed none, with every null field serialised. A stub is 744. A
  withheld pointer is ~671, a withheld group ~518. Under a 25,000 cap that admits ~24 stubs,
  or ~10 short bodies, or ~37 group pointers - and nothing else.

So: not a broken invariant, not an arithmetic defect, not a host that is smaller than
declared. A **design-level accounting cost** - every observed id must appear on the wire at
500-700 characters each - meeting a probe strategy that observes 30-60 threads per question,
under a floor that makes the only reductive step all-or-nothing.

## The findings, and what is unestablished

| ID | class | finding |
|---|---|---|
| R-M2-077 | product, BLOCKER | `get_messages` raises for any reply fetched without its whole ancestor chain (1b) |
| R-M2-078 | harness | `follow()` executes affordances from the first envelope only; expansion is one hop by construction |
| R-M2-079 | harness | the primitive floor's verbatim `q` returns 0 ids on 15/15; its 0/13 is uninformative |
| R-M2-076 | product, design | mechanism now verified: withheld accounting for probe-touched threads consumes 96% of the character cap; step 7 is all-or-nothing under the E2 floor (2a-2e) |

**Unestablished, and stated as such:** whether the real semantic rung pooled the five
lexically unreachable cases on the Mac run; what the host's true result cap is; whether a
correct answer, once one is produced, is reached by the mechanism each case names. Nothing in
this document changes the acceptance criteria or the content gate; R-M2-067..073 stay open.

## Bounded repair proposal - for approval, nothing executed

Ordered by leverage per line changed. Each is separable; none raises a limit or touches a
case.

1. **R-M2-077 (product, narrow).** In `expansion._rows_of`, name `reply_parent_id =
   link.parent_id` unconditionally, as `assemble.py` already does at both of its row sites.
   Regression tests: `get_messages` by id and by `map_id`+`positions` on a reply whose parent
   is not requested returns the row at every content view; a replant that re-masks the parent
   must fail them. About ten lines plus tests. This alone makes hop 3 executable everywhere.
2. **R-M2-078 (harness, measurement only).** `follow()` gathers affordances from every
   envelope obtained so far, breadth-first, under the existing round bound and no-repeat rule;
   `_execute` records the exception class on the `CaseRun` instead of returning `None`, so a
   raise during recovery is reported as a product failure rather than as silence. Re-running
   the diagnostic after 1 and 2 will move `after_expansion` for the eight lexically retrieved
   cases; it is the cheapest way to find out how much.
3. **R-M2-079 (harness).** Give the floor a stated query-to-`q` policy that a fixed agent
   would plausibly use - the question's content words OR-joined, or its capitalised terms -
   and record it in `primitive.py` as the pre-registered policy. Without this there is no
   floor, and EP §7.5's degenerate-strategy guard is not being run.
4. **R-M2-076 (product, design - needs a decision, not a patch).** Three levers, each with
   what it costs, in the order I would take them:
   - *Widening policy.* Do not widen to single-term probes once an earlier probe has hit;
     RANK-04's conjunction found exactly the right thread and the widening buried it under
     32 more. This is a change to L1b's rule and needs retrieval authorisation. It is the
     smallest change with the largest effect on accounted-thread count.
   - *Pointer cost.* A `withheld_groups[]` entry at ~518 characters and a `withheld` record
     at ~671 are pointers; a compact form (thread id, count, one affordance) would be a
     fraction of that. Wire-format change, R-MCP territory, contract-visible.
   - *Measure the host cap* (PF-6) before anyone argues about 25,000. If the host reads
     `_meta["anthropic/maxResultSizeChars"]`, prefer it; if it does not, the constant stands.
     This is a measurement, not a limit raise, and I am not proposing to change the constant
     on the strength of this document.

   I am **not** proposing to weaken the E2 floor or to make step 7 split floor-bearing
   sources: the floor is the non-negotiable reply-chain contract and R-M2-068 says F17 is its
   only test.

What I would run first, once 1-3 are approved: the same fifteen cases on `sem-off` only, in
the isolated environment, no models needed, to measure how far 1-2 move `after_expansion`
before any retrieval change is discussed.
