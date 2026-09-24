# ROUND 30 — focused review: the adoption of `MAX_SERVER_MS = 7,700`

**Reviewer:** R-V01 (independent, adversarial) · **Date:** 2026-09-09 · **Scope:** the adoption
of 7,700 and nothing else. Gmail rate limiting is out of scope by owner instruction and was not
investigated. Anything else outside scope is a one-line note with a severity.

**Nothing in the tree was modified.** Every number below is read out of
`validation-records/deadline-validation-run3.json` with a script, or off the source with grep.

---

## A. Blast radius — one real inconsistency, one stale rationale, no inversion

Checked by grep, not from memory. `MAX_SERVER_MS` is consumed in exactly one place that
matters (`policy/budget.py:229`, the per-query default) and read by two others
(`gmail/retry.py` via `remaining_ms`, `preflight/probes/latency.py`).

* **`MAX_CONCURRENT_QUERIES = 2` / the A.5c governor — no wait exists.** `Governor.admit`
  refuses immediately with `process_quota_refused` and never blocks (`policy/budget.py:400-418`);
  the class docstring says so and the code matches. **There is no governor wait bounded by
  `max_server_ms`**, so nothing there got 3.85× longer. The only consequence is that an
  in-flight query now occupies a slot for up to 7.7 s instead of 2 s.
* **`MAX_SEMANTIC_MS = 6,000` — no ordering is assumed anywhere.** The only comparison of the
  two clocks in the whole tree is `latency.py:161`, and it does not compare them to each other.
  `BudgetAccountant.enter_semantic` **resets** `_started_ms` and swaps the cap
  (`policy/budget.py:308-323`), so the two are sequential and independent; 7,700 > 6,000 inverts
  no invariant. Worst-case wall time for a semantic query rises from 8.0 s to 13.7 s, and L5/L6
  are unbuilt.
* **`FLOOR_QUOTA_UNITS = 845`** is a quota figure with no time term; unaffected.
* **`MAX_HTTP_REQUESTS = 24` — see R-V31-001. The relationship is still violated.**

### R-V31-001 — 7,700 does not satisfy the pair that motivated it, and the docstring does not say so · MEDIUM
PF-21's registered trigger is `MAX_HTTP_REQUESTS × slowest_p90 > MAX_SERVER_MS`, and it is
live code: `latency.py:161` returns `Verdict.FAIL` on exactly that inequality. The registered
candidate `24 × slowest_p90` rounded up to the hundred is **12,300**, so the measured slowest
p90 is ≈512 ms. At 7,700 the published pair now assumes `7700 // 24 = 320` ms per request,
still well under 512, so **PF-21 continues to return FAIL** — the probe that raised R-RETR-065
is not satisfied by the value adopted to answer it. The constant's docstring recites the old
83 ms figure and stops there; it never states that 7,700 leaves the same arithmetic unsatisfied,
only less so. Run 3 corroborates: 13-19 requests in 5.1-7.6 s is ~400 ms per request, and 24 of
those is ~9.6 s.

Not a blocker: PF-21 is not among the gate-blocking probes (AD line 1643 names PF-13 and PF-15),
and 12,300 was explicitly registered as "an upper-bound formula and **not the default by
itself**". But the docstring is the artifact a reader consults, and it currently reads as though
the arithmetic objection was retired.

### R-V31-002 — the `MAX_SEMANTIC_MS` rationale is now inverted · LOW
`constants.py:207-208`: "one deadline over both would either strangle the semantic rung or hand
the lexical ones **six seconds of slack**." With the lexical cap at 7,700 and the semantic one at
6,000 the sentence points the wrong way — a unified deadline would now hand the *semantic* rung
1.7 s of slack. One line, and it sits three lines above the constant that moved.

### R-V31-003 — the effective retry budget grew with the deadline · LOW
`BackoffState._budget_ms()` is `min(MAX_BACKOFF_TOTAL_MS, remaining_ms)` where `remaining_ms` is
the rung's unspent `max_server_ms` (`gmail/retry.py:75-79`). At 2,000 ms a late call was often
clamped below the retrier's own 1,500 ms total; at 7,700 the full 1,500 ms is available for far
more of the query. No relationship inverts — it is a `min` — but per-call worst-case latency
rises, and the two 403s in run 3 each burned "3 attempt(s) within the 1500 ms backoff bound".
Recorded as a consequence, not a defect.

---

## B. Pinned expectations — one that should have moved and did not

Swept every `2_000` / `2,000 ms` / `2000` in `.py`, `.md`, `.json` and `.toml` outside
`.venv`/caches. Every surviving reference is either a historical record (run 1-3 records, the two
acceptance records, `RMCP033-ACCEPTANCE-VERDICT-FAILED.md`, the preserved half of
`DEADLINE_DECISION.md`), the deliberate harness pin, synthetic test data
(`test_deadline_validation.py:299`), or an unrelated constant. **Records did not move, and
should not have.**

### R-V31-004 — AD A.7's cap table still publishes `max_server_ms = 2,000`, and nothing pins it · HIGH
`docs/ARCHITECTURE_DECISION.md:356` reads `| max_server_ms | **2,000** (L0–L4) | RTT-bound |`.
The governing document and the shipped constant now disagree, and no amendment records the
change: `grep -rn "7,700\|7_700" docs/` matches only `V0_1_DEMO.md`, the findings ledger and my
own round-30 review — nothing in `ARCHITECTURE_DECISION.md` or `ARCHITECTURE_AMENDMENTS.md`.

The one test that swept that row against the code,
`tests/test_ws10_escalation.py::test_every_published_cap_is_a_constant_this_module_enforces`, was
edited to `(7_700, 6_000)`. Its docstring still says *"The values are quoted from the
architecture rather than imported into the expectation … a change to the implementation's
constants cannot silently redefine what this test is checking"* — which is now false of that one
row. The added comment is honest about the move, and that is the right instinct, but the net
effect is that the code moved, the test moved with it, and **the document it was quoting did
not**. PF-21's own registration anticipated this exactly: "the constant then carries the figures
and the date of the run (A.11), **and the cap-table sweep test moves with it**" — the sweep test
moved; the cap table it sweeps did not.

Fix: amend AD A.7's row (or add an `ARCHITECTURE_AMENDMENTS.md` entry the row points to) and
restore the test's docstring to describe what it now does.

### R-V31-005 — a stale docstring inside the test that was rewritten · LOW
`tests/test_deadline_validation.py:332` still says the third pre-registered query is a "control
at the **published width**", while lines 342-345 of the same test assert
`control.max_hit_threads == acceptance.max_hit_threads` (both 1). The control's width changed
when R-V30-007 was addressed; the sentence above the assertion did not. *Adjacent to this
round rather than in it — recorded, not chased.*

---

## C. Is the caveat load-bearing? — **yes, in all three artifacts**

* **`constants.py:174-205`.** The second sentence of the docstring is *"Owner-selected
  operational default, not a passed automatic validation. That distinction is load-bearing and is
  repeated wherever this number is documented."* A dedicated **"The caveat, which is not
  optional"** section states `adoptable: false`, names the cause, and ends *"this constant may
  not be cited as a passed registered validation."* A reader cannot come away believing the
  validation passed.
* **`DEADLINE_DECISION.md`.** The new section's own heading sentence is *"**Not** a passed
  automatic adoption verdict, and it must never be cited as one"*, the verdict block is
  reproduced field by field, and a **"What this may be described as"** section gives permitted
  and not-permitted phrasings verbatim. The closing section says what would settle it properly
  and that it was not run.
* **`FINDINGS_LEDGER.md:694`.** R-RETR-065 is closed as *"**CLOSED by owner decision, 2026-09-09
  — not by a passed validation**"*, carries the failing verdict and the cause, and repeats the
  description constraint.
* **`V0_1_DEMO.md:62` and `:196`** both carry it, the second in the limitations list with the
  instruction "never as validated".

**The preserved 2026-09-08 decision is not distorted.** The banner is a superseding note, not an
edit: it says what changed, points to the new section, and states *"Everything above that section
is the 2026-09-08 decision preserved as written, because it was correct on the evidence available
that day and its reasoning is what the reopening turned on."* The old text still reads as a
refusal to adopt, and the new section explicitly names which of its premises R-MCP-033 overturned
("more deadline makes the failure worse, not better"). That is the honest way to supersede a
document: the reasoning is shown to have been correct and then shown to have expired.

One thing I could not check: `632cfbc`, `b0420ce` and `2a1253b` are cited as commits and this
tree is not a git repository, so the provenance of the committed-unedited claim is attested, not
verified here.

---

## D. The transcribed run-3 table — **three defects, one material**

Every cell diffed against the raw JSON by script. The `search ms` column is the median of the
three repeats in **all nine rows** — correct throughout.

### R-V31-006 — the table hides the two declined repeats it was written to disclose · MEDIUM
Rows 3 and 6 (the 12,300 arm on both `after:2026/09/01` queries) are rendered as a clean
`1 / body_clean / max_hit_threads / 13 / 5,877` and `2 / body_clean / disclosed_token_ceiling /
15 / 6,207`. The raw record for those two cells is:

```
09/01 [hit_threads=1] @12300  evidence=[1, 0, 1]  declined=[False, True, False]  http=[13, -1, 14]
09/01 [hit_threads=3] @12300  evidence=[2, 2, 0]  declined=[False, False, True]  http=[15, 19, -1]
```

One repeat of each **declined** — those are the two `upstream_rate_limited` 403s, and they are
the entire reason the registered verdict is `adoptable: false`. The table shows a single
evidence figure with nothing marking that a third of each cell is a refusal. It is repaired two
paragraphs below in prose, and the verdict block is reproduced faithfully, so the document as a
whole is truthful — but the table is where a reader looks, and the owner's ground *"12,300 ms
demonstrated no necessary benefit"* is read straight off rows that look equivalent only because
a declined repeat is invisible in them. Mark the cells (e.g. `1 (1 of 3 declined)`).

Related: the `http` medians in those two rows are taken across a `-1` sentinel that stands for a
declined repeat. Both happen to land on a real observation, but a median over a sentinel is not
a measurement.

### R-V31-007 — two `http` cells are the first repeat, not the median · LOW
Every other cell in that column is the median.

| row | table | raw | median |
|---|---|---|---|
| 4 — `[hit_threads=3]` @ 2,000 | **6** | `[6, 5, 5]` | 5 |
| 8 — control @ 7,700 | **14** | `[14, 15, 16]` | 15 |

Both are repeat 0. Neither figure carries any argument in the document, so this is precision,
not substance — but the column has no stated rule and two of its nine cells follow a different
one from the other seven.

### R-V31-008 — the `caps hit` column drops `max_hit_threads` from five of nine rows · LOW
Raw `budget_caps_hit` for the three 2,000 ms rows is `("max_server_ms", "max_hit_threads")` and
for the two `[hit_threads=3]` rows at 7,700/12,300 is
`("disclosed_token_ceiling", "max_hit_threads")`. The table shows only the first element of each.
Only rows 2, 8 and 9 are complete. If the column means "the cap that bound" it should say so;
as headed it is a named wire field, and this is a smaller instance of the very defect round 30
closed — a width cap that withheld and is not named in the list a reader consults.

### Everything else in the table is exact
Labels (all three, including `after:2026/09/08 [hit_threads=1]`), evidence counts on the six
clean rows, depths, and all nine `search ms` medians. The owner's grounds are exact too:
2,000 returned `[0,0,0]` on the acceptance query; 7,700 returned `[1,1,1]` at `body_clean` with
no `max_server_ms` in any repeat's caps; the acceptance-query wall times are `[6041, 5105, 6352]`
= "~5,105, 6,041 and 6,352"; the candidate served non-empty evidence in all nine repetitions
(`[1,1,1] [2,2,2] [1,1,1]`). The caveat's cause is exact: **two** declines, both
`upstream_rate_limited` (403 on `users.getProfile`), both on the 12,300 arm, and they are what
`differences` attributes `stable: false` and `no_asymmetric_decline: false` to.

---

## The harness pin — **forced, and it damages no recorded comparison. I agree.**

`ARMS = (BASELINE_MS, CANDIDATE_MS, UPPER_BOUND_MS)`, and `judge` builds
`runs = {ms: observations(label, ms) for ms in ARMS}`. Had `BASELINE_MS` followed
`MAX_SERVER_MS`, `ARMS` would be `(7_700, 7_700, 12_300)` and the dict comprehension would
collapse to **two** keys: `by_repeat[BASELINE_MS]` and `by_repeat[CANDIDATE_MS]` would be the
same object, every `baseline` would *be* its own `candidate`, and `baseline_showed_it` could
never be true — the harness would become permanently unable to adopt anything, silently, with no
error. Pinning is not a preference; the alternative is a broken instrument.

It damages nothing recorded: `deadline-validation-run3.json` carries
`arms_ms.baseline_shipped = 2000`, and runs 1-3 were all taken with 2,000 as the baseline arm, so
the pin is the figure those records were actually measured against. `test_deadline_validation.py`
now asserts both `BASELINE_MS == 2_000` and `MAX_SERVER_MS == 7_700`, which is the right pair to
pin: it makes the divergence deliberate and visible rather than incidental.

---

## Out of scope, recorded not chased

* LOW — the `Governor` is not wired into the serving path: `MailweaveService.search` constructs
  a `BudgetAccountant` directly rather than through `Governor.admit`, so
  `max_concurrent_queries` is unenforced on the MCP surface (the surface holds one lock per call,
  which is why nothing has noticed). Pre-existing, unrelated to this change.
* Noted with approval — R-V30-008 from the round-30 review landed: `acceptance_query_informative`
  is now a verdict field and run 3's record carries it as `false`, which is what makes the
  failing verdict legible.
