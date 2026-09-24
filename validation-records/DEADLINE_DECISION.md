# The deadline decision

> **Superseded 2026-09-09. `MAX_SERVER_MS` is now 7,700 ms** by owner decision, not by a
> passed registered validation. See "The reopening, and the decision that closed it" at the
> foot of this file. Everything above that section is the 2026-09-08 decision preserved as
> written, because it was correct on the evidence available that day and its reasoning is
> what the reopening turned on.

**Decided 2026-09-08 by the owner, on the evidence below. Status: blocked on R-MCP-033.**

The candidate 7,700 ms is **not adopted**. `MAX_SERVER_MS` is unchanged at 2,000 ms and no
constant was edited at any point in this measurement: every arm passed its deadline as a
`budget` argument, which `apply_floor` clamps from below only.

## What was asked

R-RETR-065 filed that `MAX_SERVER_MS = 2,000` had never been measured against a network.
PF-21 measured it: the slowest endpoint's p90 is roughly 5x the 83 ms the published pair had
assumed. From those figures came a candidate (7,700 ms) and a registered upper bound
(`MAX_HTTP_REQUESTS` x slowest p90 = 12,300 ms). The question was whether ordinary searches
under the candidate return the same answer-supporting evidence as under the bound.

**PF-21 is referenced here, not restated.** The probe that produced it is committed at
`4dfeb9a` (`harness/src/mailweave_harness/preflight/probes/latency.py` and its tests). Its
*measured output* was not in that commit and was still untracked; `preflight-records/` is
therefore committed here, alongside the records that depend on it, rather than restated in
this document.

## What the measurement found

Three arms, three counterbalanced repeats each, on the pre-registered neutral query
`after:2026/09/01` with `max_hit_threads: 3`. `stable: true`: every repeat of every arm agreed
with itself about declining, evidence, `partial`, `withheld`, `not_included` and
`budget_caps_hit`.

| arm | median search | estimated chars | rows | sources | withheld |
|---|---|---|---|---|---|
| 2,000 ms (shipped) | 2,278 ms | ~26,060 | 0 | 0 | 45 |
| 7,700 ms (candidate) | 5,795 ms | ~29,360 | 0 | 0 | 45 |
| 12,300 ms (bound) | 6,302 ms | ~29,360 | 0 | 0 | 45 |

Every one of the nine calls declined with `budget_exhausted`, and **not on the clock**. The
refusal names its own cause: the assembled response exceeds `HOST_RESULT_CHAR_CAP` (25,000),
DISC-06 forbids handing truncation to the host, so nothing is emitted. The A.9a ladder ran
every published step in all three arms.

## Why the deadline cannot be settled here

1. **The deadline is not the binding constraint on this query.** The character cap is. The
   candidate and the bound both finished well inside their own deadlines (5.7-6.6 s) and
   produced byte-identical estimates, so between 7,700 and 12,300 there is nothing to choose:
   the extra 4,600 ms bought zero.
2. **More deadline makes the failure worse, not better.** 26,060 characters at 2,000 ms,
   29,360 at both larger arms. Longer to work means more gathered means a larger overflow.
3. **The one query that generates enough sequential work to spend a 7.7 second clock is the
   query whose response cannot be emitted at all.** The queries that do answer (`delimiter`,
   `has:attachment`, run 1) make three or four Gmail requests and never approach 2,000 ms, so
   they would be informative with the baseline showing no difference: not adoptable either,
   for the opposite reason.

Adopting 7,700 ms on this evidence would mean adopting on evidence the registered rule was
written to reject. The rule reported `adoptable: false`, `informative_queries: 0`, and that is
the correct answer to the question as asked.

## Records, and what each one is

| file | what it is | verdict |
|---|---|---|
| `deadline-validation-run1-raw.json` | the first run, two arms, on queries that made four Gmail requests | **automatic verdict INVALID** - see the companion `.md`; kept as raw evidence, bytes unchanged |
| `deadline-validation-run1-VERDICT-INVALID.md` | why run 1's `adoptable: true` decided nothing | - |
| `deadline-validation-run2.json` | the corrected three-arm rule, counterbalanced, three repeats | `adoptable: false`, `informative_queries: 0`, `stable: true` |
| `rmcp033-diagnostic-hit-threads-1.json` | **not deadline evidence.** One call, arguments copied verbatim from run 2's own `retry_with` | see `docs/reviews/R-MCP-033.md` |

## One thing a reader should not misread

In run 2 every arm records `caps_named_in_remediation: []`. That does **not** mean the refusal
named no cap. The harness scans the remediation for published `BudgetCapName` values, and the
cap actually binding here is `HOST_RESULT_CHAR_CAP`, which is not a budget key. The refusal
names it in prose ("the host's cap of 25000"). The empty list is a limit of what the harness
classifies, not a property of the response.

## What reopens this

R-MCP-033. Once a capped broad query returns mail inside the host cap, the same three-arm
validation can run against a query that both answers and spends a real clock, which is what the
registered rule needs and has never had. Until then the deadline question has no measurable
answer and 2,000 ms stands.

---

# The reopening, and the decision that closed it

**2026-09-09. `MAX_SERVER_MS` changed from 2,000 ms to 7,700 ms.** Owner decision on repeat
observations. **Not** a passed automatic adoption verdict, and it must never be cited as one.

## What reopened it

R-MCP-033 was closed in round 29, exactly the condition this file named as the reopener. The
broad capped query then served inside the host cap, so the clock became measurable for the
first time.

Live v0.1 acceptance test 5.1 then failed twice on the shipped 2,000 ms, on `632cfbc` and again
on `b0420ce`. Both records are committed beside this file. The exact acceptance call served
truthfully at ~8,700 characters with zero sources and zero matched rows, spending its whole
deadline before it could afford the one `threads.get` a source requires.

Note what this overturned. The 2026-09-08 decision reasoned that "more deadline makes the
failure worse, not better", because at that time more time meant more bookkeeping against a
character cap that was already breached. With R-MCP-033 fixed that reasoning no longer holds:
more time now buys thread maps, and thread maps are what the response had none of.

## The measurement

`deadline-validation-run3.json`, three pre-registered queries x three arms x three
counterbalanced repeats, arms unchanged from their round-28 registration.

Read per repeat, not as a summary. The two declined repeats are the whole reason the verdict
is false, so the table shows them rather than a median that conceals them.

| query | arm | evidence per repeat | declined | depth | caps hit | http per repeat | search ms per repeat |
|---|---|---|---|---|---|---|---|
| `after:2026/09/01 [hit_threads=1]` | 2,000 | **0, 0, 0** | - | - | `max_server_ms`, `max_hit_threads` | 5, 5, 5 | 2,199 / 2,409 / 2,063 |
| the same, **the acceptance call** | 7,700 | **1, 1, 1** | - | `body_clean` | `max_hit_threads` | 13, 13, 14 | 6,041 / 5,105 / 6,352 |
| the same | 12,300 | 1, **0**, 1 | **repeat 1** | `body_clean` | `max_hit_threads` | 13, -, 14 | 5,423 / 6,112 / 5,877 |
| `after:2026/09/01 [hit_threads=3]` | 2,000 | 0, 0, 0 | - | - | `max_server_ms`, `max_hit_threads` | 6, 5, 5 | 2,323 / 2,509 / 2,408 |
| the same | 7,700 | 2, 2, 2 | - | `body_clean` | `disclosed_token_ceiling`, `max_hit_threads` | 15, 15, 15 | 6,143 / 6,287 / 6,203 |
| the same | 12,300 | 2, 2, **0** | **repeat 2** | `body_clean` | `disclosed_token_ceiling`, `max_hit_threads` | 15, 19, - | 6,085 / 9,046 / 6,207 |
| `after:2026/09/08 [hit_threads=1]`, the control | 2,000 | 0, 0, 0 | - | - | `max_server_ms`, `max_hit_threads` | 6, 5, 6 | 2,360 / 2,423 / 2,393 |
| the same | 7,700 | 1, 1, 1 | - | `body_clean` | `max_hit_threads` | 14, 15, 16 | 5,800 / 6,236 / 7,605 |
| the same | 12,300 | 1, 1, 1 | - | `body_clean` | `max_hit_threads` | 14, 14, 14 | 5,773 / 6,189 / 5,795 |

A dash in `http` marks a repeat that declined and therefore recorded no request count. The two
declines are the two `upstream_rate_limited` 403s, both on the 12,300 ms arm, both on
`users.getProfile`.

**Read the 12,300 rows carefully before treating them as equivalent to 7,700.** Two of their
three repeats declined, so "12,300 demonstrated no necessary benefit" rests on rows that look
comparable only once you account for the missing repeat. The claim survives - where 12,300 did
answer it returned exactly what 7,700 returned, at no better latency - but it is a weaker
statement than the row shapes suggest.

The owner's stated grounds: 2,000 ms returned zero evidence on all three repeats of the exact
acceptance query; 7,700 ms returned the same non-empty `body_clean` evidence on all three;
7,700 never hit `max_server_ms`; its acceptance-query wall times were ~5,105, 6,041 and
6,352 ms; across all three registered queries it served evidence in all nine repetitions; and
12,300 ms demonstrated no necessary benefit.

## The formal verdict, preserved exactly

**`adoptable: false`.** The registered rule did not pass, and the record says so:

```
adoptable: False   stable: False   equivalent_evidence: True
candidate_never_hit_the_clock: True   no_asymmetric_decline: False
baseline_shows_a_difference: True     informative_queries: 1
acceptance_query_informative: False
```

Every failing condition traces to one upstream cause: the 12,300 ms reference arm took two
`upstream_rate_limited` (403) declines from Gmail during the run. That made its repeats
disagree with each other, made the bound decline where the candidate answered, and so left the
acceptance query classified uninformative. It is a property of the upstream service during that
window, not of any deadline value. Deliberately not investigated: out of scope for this
closure round, recorded as backlog.

## What this means for how the number may be described

Permitted: "operational default selected by the owner on repeat live observations, after the
shipped value failed live acceptance twice."

Not permitted: "validated", "adopted by the registered rule", "passed the three-arm
validation". The registered rule returned false and the record is committed unedited at
`2a1253b`.

## What would settle it properly

A clean re-run of the same three arms in a window without upstream rate limiting. The harness
is unchanged and needs no edits to do it. Not required for v0.1, and not run: this closure
round is bounded to the change itself.
