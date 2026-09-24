# ROUND 30 — focused review: the four round-30 changes

**Reviewer:** R-V01 (independent, adversarial) · **Date:** 2026-09-09 · **Scope:** only the
round-30 changes the work request names. Anything outside it is a one-line note with a
severity, not a finding.

**Nothing in the tree was modified.** Replants and the uncovered-gate probe were planted in a
scratch copy at `/tmp/.../scratchpad/r30`; `docs/` was copied in so the document-reading tests
could run. Probes: `/tmp/.../scratchpad/r29/p30_callmix.py … p37_bicond.py`.

---

## 1. The call-mix reconstruction — **sound, with two false supporting claims**

**The arithmetic is right.** Exhaustive enumeration over all five endpoints at the
`gmail/rates.py` rates gives exactly two non-negative integer solutions to
`Σcalls = 6, Σunits = 105`:

```
A: list 0, get 1, threads 2, history 2, profile 1
B: list 1, get 5, threads 0, history 0, profile 0
```

**The table is the one that computed the field.** `CallMeter.reading()` multiplies
`PUBLISHED_QUOTA_UNITS` over `_api_calls` into `quota_units_diagnostic`
(`gmail/meter.py:93-104`), and `assemble` writes that into `Counters.quota_units`
(`assemble.py:2448`), which is the record's field. No second table exists.

**Solution A's elimination holds**, and on a firmer ground than the diagnosis gives: every
metered search I drove begins with `users.messages.list`, and L4's structural probes are
`messages.list` too, so no path reaches `H` with zero of them.

**Independent corroboration, stronger than the arithmetic.** A synthetic 14×3 mailbox, an
operator-only query, `max_hit_threads: 1` and `max_api_calls: 6` reproduces the record's
counters *exactly* — `http_requests 6, api_calls 6, quota_units 105`, mix
`1 messages.list + 5 messages.get`, `sources 0`, `matched_rows 0`,
`withheld_by_cap {<budget cap>: n, max_hit_threads: 39}` (`p31_dateonly.py`). The path the
diagnosis describes is realisable and produces the record.

### R-V30-001 — "Five is not a coincidence" names the wrong constant · MEDIUM
`MAX_BODY_FETCHES_L0 = 5` was not in play. `after:2026/09/01` is operator-only, so the run is
**L1** (`rungs: ['L1']`, observed on the same shape), and L1's fetch cap is
`MAX_BODY_FETCHES_L1 = 10` (`retrieval/ladder.py:1553`). Five is therefore the clock stopping
the loop half way through a budget of ten, not a cap being reached. The conclusion survives and
is in fact strengthened; the stated reason is false and is presented as confirmation.

### R-V30-002 — retries are invisible in these counters and are not considered · MEDIUM
`_request` calls `meter.record_attempt` **inside** the retry loop (`gmail/client.py:470-471`),
so a retried call increments `http_requests`, `api_calls` **and** `quota_units`. The equation is
over *attempts*, not logical calls: `get: 5` may be five bodies, or four with one retried, or
three with two. Two claims do not survive that:

* "Five message bodies were successfully fetched and are in memory" — not established;
* step 3's latency arithmetic ("roughly 330 ms per request against PF-21's measured 83 ms").
  `RETRY_BASE_MS = 250`, so one retry puts ≥250 ms of *sleep* inside the 2,252 ms and one extra
  20-unit charge in the total. The diagnosis names two candidate explanations for the gap and
  does not name this third one, which its own counters cannot exclude.

### R-V30-003 — the record cannot settle it, and one field would · LOW
`MeterReading` already carries `api_calls_by_endpoint` and `http_requests_by_endpoint`;
`Counters` (`envelope/wire.py:335-340`) carries only the three totals, so the per-endpoint
breakdown and the attempt count are dropped before the record is written. Emitting them makes
this reconstruction a reading rather than an inference and separates retries from calls.

**Nothing else inflates the counters.** The `Governor` reads a meter and issues no calls. A
`ThreadMapCache` hit would skip `threads.get` *and* the meter, but that can only add sources,
and the record has none — so it cannot rescue solution A.

---

## 2. `budget_caps_hit` sweeps every cap that withheld — **correct, document and consequence**

**The document reading is verified, not over-read.** AD A.7's *Global caps per top-level query*
lists `max_hit_threads` at 12 with the note "**Never** silently exceeded: hits in threads beyond
it become `withheld` records". AD D.3 rule 5 reads, verbatim: *"Any cap exhausted ⇒ stop, emit,
name the cap plus untried rungs with affordances (AD-03), **and emit a `withheld` record for
every hit the cap prevented from being disclosed** (A.7a). The outcome is **`inconclusive`**,
never `not_found` (D.2)."* The outcome clause is a positive assertion, not a negative one, so
`answered → inconclusive` on capped shapes is the document's rule.

**No idle cap found, and the property is structural.** An entry reaches `caps` only from
`unmapped_by_budget`, `overflow` or `beyond_cap`. `already = {plan.thread_id for plan in plans}`
(`assemble.py:2125`) excludes **every** hit-bearing thread — mapped and overflow alike — from
`siblings`, so an overflow thread cannot be re-mapped into a source and then name a cap that
withheld nothing. L4's recovery probes are `messages.list`, which is id-yielding, so every
`beyond_cap` thread has ids in the ledger for the sweep to file. Executed over 14 shapes with a
spy on `_withhold_undisclosed_threads` comparing the swept table against the notes actually
filed: `IDLE_SWEPT = []` on every one, including `max_source_threads` at 0, 1 and 4
(`p32_caps.py`, `p33_struct.py`).

**`max_pages_per_query` cannot enter through this loop**: it is a `BudgetCapName` with no
`WithheldCap` twin, and `more_pages` feeds `unfetched_pages`, not `caps_hit`. A `scan.max_pages`
shape returns `caps_hit: ['disclosed_token_ceiling']` only.

**`partial_source_failure` is the only `WithheldCap` with no `BudgetCapName`**, so the
`except ValueError: continue` covers exactly it. It also cannot appear in `caps` today — it is
filed by `_withhold_the_whole_thread`, not through that table — so the guard is defensive rather
than load-bearing, which is the right way round.

### R-V30-004 — the no-idle-cap property is structural, not asserted · LOW
Nothing tests that a cap entering `budget_caps_hit` through the new loop withheld something. One
assertion in the round-30 file (`declared ⊇ withheld_by` is there; `swept ⊆ filed` is not) would
close the direction a future producer could break.

---

## 3. `omission.bound` stated only when a ceiling bound — **no blocker; the predicate is wrong**

**The blocker the request defines does not exist.** Every sentence containing `omission.bound`
is emitted inside a loop over `split_off` or `withheld_ids`, and both are terms of
`a_ceiling_bound`, in **both** producers (`assemble.py:1593`, `expansion.py:523`). Executed over
**142 served shapes** across all three tools — thread counts 1-45, per-thread 1-300, width caps,
token ceilings, `get_messages` id counts — no record, group, tail or block ever refers to a
`bound` that is `None` (`p34_bound.py`).

### R-V30-005 — the ladder can reduce with all three terms false, and the round's own biconditional is false · MEDIUM
`test_the_declarations_agree_on_every_shape_and_the_response_still_fits` asserts
`disclosed_token_ceiling ∈ budget_caps_hit ⟺ omission.bound is not None`. **Ten served shapes
violate it** (`p37_bicond.py`): one thread of 6-12 messages at
`budget.max_disclosed_tokens` 1,800-3,000 returns `truncated_by: "mailweave"`,
`budget_caps_hit: ["disclosed_token_ceiling"]` and `omission.bound: null`. The ladder
demonstrably reduced — depth demotions, and a declared collapsed run on two of them — and no
ceiling is named. This is the request's own question answered yes; it is not a blocker only
because nothing in those responses refers to the missing sentence.

The defect it exposes is an asymmetry: a depth-only reduction forced by the **host cap** states
`bound` (24 such shapes observed), the identical reduction forced by the **token ceiling** does
not. The predicate tests "a ceiling *omitted* something", and its name claims "a ceiling bound".
Adding `disclosure.steps` as a fourth term — the same condition that puts
`disclosed_token_ceiling` in the cap list — makes the name true and the test's biconditional
true with it.

### R-V30-006 — the `expansion.py` half of the change is uncovered · MEDIUM
R129's anchor is `assemble.py` only, and no test in the suite asserts `omission.bound` on a
`thread_map` or `get_messages` response — the only `bound` assertions are round 26's and round
30's, both driving `mailweave_search`. Reverting `expansion.py`'s gate to unconditional
(`if True:`) on the scratch copy leaves **100 tests across ten of the most relevant files
green**, the whole round-30 file included. The gate is correct today; nothing holds it there.

---

## 4. The deadline re-registration — **the judge does not bind the acceptance call**

**The narrow control is narrower by construction.** `after:2026/09/08` selects a subset of
`after:2026/09/01` in any mailbox, so no mailbox knowledge is needed. (Strictly: no wider —
equal if that week is empty.)

### R-V30-007 — the control is narrower in date range and *wider* in width · MEDIUM
It runs at the published `max_hit_threads` of 12 while the two broad specs run at 1 and 3, so it
may issue up to twelve `threads.get` calls where the acceptance call issues at most one. It is
therefore not reliably a query "where the deadline was never the constraint" — on a busy week it
can spend the clock harder than the calls it controls for. The arm comparison is not corrupted
(each label is compared only against itself across arms), so the risk is an inconclusive run 3,
not a wrong adoption.

### R-V30-008 — `judge` can return `adoptable: true` while the acceptance call returns zero rows · HIGH
`Verdict.adoptable` requires `informative_queries > 0`, and `informative` is incremented **per
label**. The "identical, non-empty matched evidence in every repetition" condition therefore has
to hold for *some* label, not for the query the re-registration exists for. Demonstrated
(`p36_judge.py`): a `Comparison` in which `after:2026/09/01 [hit_threads=1]` returns zero matched
rows under all three arms in all three repeats, while the other two labels are informative and
the baseline hits the clock on one, yields

```
adoptable: True    informative_queries: 2
uninformative: ["'after:2026/09/01 [hit_threads=1]': both answered with no matched evidence; ..."]
```

The failure is recorded honestly under `uninformative`, but `adoptable: true` is the record's
machine-readable headline and `adoption_rule` is the docstring, so a reader is told the candidate
is adoptable on a run where live acceptance 5.1 still fails. Required fix: make adoptability
depend on the **registered acceptance label** being among the informative ones, or report
informativeness per label in the `Verdict`.

### R-V30-009 — `judge` answers a narrower question than the round's framing · LOW
Only the candidate is tested for adoptability; the baseline is tested only for *showing a
difference*, and no value between 2,000 and 7,700 is measured. So the rule decides "is 7,700
adoptable in preference to the shipped 2,000", not "the lowest measured value that enables useful
evidence". Defensible with three registered arms — the docstring does not overclaim — but the
framing around it is wider than what the code decides.

---

## The regressions

Planted one at a time on the scratch copy, each citation run alone; the working tree is
byte-identical afterwards. Pristine scratch baseline: `tests/test_v0_1_acceptance_round30.py`
11 passed.

| replant | citation | result |
|---|---|---|
| R128 | `test_every_cap_that_withheld_content_names_itself_in_budget_caps_hit` | **FAILED** (3 of 4 parametrisations) |
| R128 | `test_a_response_that_hit_a_cap_never_calls_itself_answered` | **FAILED** (2 of 4) |
| R129 | `test_the_acceptance_shape_states_no_ceiling_it_did_not_reach` | **FAILED** |
| R129 | `test_the_declarations_agree_on_every_shape_and_the_response_still_fits` | **FAILED** |

Both genuinely bind. **R128 does not pass for the wrong reason**: it is anchored on the sweep
itself and both sides of `withheld_by ⊆ declared` are derived from the payload rather than
restated.

### R-V30-010 — two of R128's four shapes do not exercise the sweep · LOW
With the sweep disabled, `width cap at the published width` and `a budget cap mid-map` still
pass, because `max_api_calls` and `disclosed_token_ceiling` reach `caps_hit` through
`accountant.caps_hit` and the `disclosure.steps` clause independently. The shape list is doing
less work than its four entries suggest; the two width-cap shapes carry the test.

**R129's second citation certifies a narrower property than it states** (R-V30-005), and neither
citation reaches the `expansion.py` producer the same round changed (R-V30-006).

---

## Out of scope, recorded not chased

* LOW — `_exhausted`'s refusal text still says "0 row(s), of which 0 are E2 floor membership"
  about an emptied response (carried from the round-29 review).
* LOW — `budget_caps_hit` now makes `outcome: inconclusive` the common case for any broad query
  on a mailbox with more than twelve hit-bearing threads. Correct per D.3 rule 5; no rubric,
  contract or demo criterion keys on `answered`, so nothing downstream breaks.
