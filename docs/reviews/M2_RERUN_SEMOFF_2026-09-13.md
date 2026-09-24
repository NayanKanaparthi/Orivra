# The sem-off rerun after repairs 1-3, per case, and one R-M2-076 recommendation

Regression diagnostics, not acceptance evidence. The original real-backend run is preserved
unchanged as `benchmarks/diagnostic-run-4311.ORIGINAL-2026-09-13.{txt,json}` (md5 `2f596f3c…`
/ `4ed0978f…`). This rerun is `benchmarks/diagnostic-rerun-semoff-4311.{txt,json}`, produced by
`benchmarks/rerun-semoff-4311.py` on the `sem-off` arm - no backend registered, no stand-in -
so everything below is lexical retrieval, disclosure and expansion. Widening, the host cap,
the E2 floor and the corpus are unchanged.

## What was repaired first

| ID | repair | commit |
|---|---|---|
| R-M2-077 | `expansion._rows_of` names a reply's parent whenever the source *accounts for* it (row, collapsed-run member, or withheld record); only a row discloses content. `Source`'s C-02a check reads the same way. Tested by id and by map position at every content view; 8 of 10 tests fail on the previous tree | `6e38f58` |
| R-M2-078 | `follow()` is breadth-first over every response it obtains, under `MAX_RECOVERY_ROUNDS = 4` hops and `MAX_RECOVERY_CALLS = 32` total calls (the bound the suite already enforced, now named, not raised). No call twice; a raise is recorded by tool and class and scored FAILED, not as empty evidence; `Reach.stopped` says why the driver stopped | `8485654` |
| R-M2-079 | `pf-q-1`, frozen before this rerun: the proper nouns of the question when it has any, else its content words; one query, one page, no reformulation; a pure function of the question string that imports neither corpus nor cases. Labelled a deterministic baseline, not Baseline E, not Claude's Gmail connector | `18295e2` |

## Per case

`retrieved` is measured at the mailbox: whether any `q` the ladder issued returned the evidence
message (msg) or any message of its thread (thread). `first resp` is EP §6.1 disclosure in the
first response. `expansion` is the driver following only what responses offered, under the
stated budgets. `raised` counts follow-up calls that raised (on any thread).

| case | retrieved (msg / thread) | first resp | expansion | calls | stopped | raised | remaining failure |
|---|---|---|---|---|---|---|---|
| DIAG-SEM-01 | no / yes | no | no | 32 | call_budget | - | surfaced, never offered as a body under the budget |
| DIAG-SEM-02 | no / yes | no | no | 20 | hop_budget | 1 | surfaced, never offered as a body under the budget |
| DIAG-SEM-03 | no / yes | no | no | 32 | call_budget | 3 | surfaced, never offered as a body |
| DIAG-RANK-01 | yes / yes | no | no | 0 | - | - | first response declined: DisclosureLadderExhausted |
| **DIAG-RANK-02** | no / yes | no | **yes** | 26 | evidence_in_hand | 2 | **delivered** |
| DIAG-RANK-03 | yes / yes | no | no | 0 | - | - | first response declined: DisclosureLadderExhausted |
| DIAG-RANK-04 | yes / yes | no | no | 0 | - | - | first response declined: DisclosureLadderExhausted |
| DIAG-EXP-01 | yes / yes | no | no | 18 | hop_budget | 3 | surfaced, never offered as a body |
| DIAG-EXP-02 | yes / yes | no | no | 0 | - | - | first response declined: DisclosureLadderExhausted |
| DIAG-EXP-03 | yes / yes | no | no | 32 | call_budget | - | surfaced, never offered as a body under the budget |
| DIAG-REV-01 | no / yes | no | no | 32 | call_budget | - | thread retrieved, message never named |
| DIAG-REV-02 | yes / yes | no | no | 0 | - | - | first response declined: DisclosureLadderExhausted |
| DIAG-REV-03 | yes / yes | no | no | 0 | - | - | first response declined: DisclosureLadderExhausted |
| DIAG-UNANS-01 | control | | | 0 | | | first response declined: DisclosureLadderExhausted |
| DIAG-UNANS-02 | control | | | 0 | | | answered |

Totals over 13 answerable cases: thread retrieved 13, message retrieved 8, first response 0,
expansion **1**, floor-tight 0, floor-generous **5**, qf-1 6 (handed the right conversation;
residual bias, not retrieval).

**What moved, and what did not.** Before the repairs, expansion reached 0 of 13 and every
`get_messages` on a reply raised. After them, one case is delivered end to end
(DIAG-RANK-02: search → `not_included` → map of a 14-message thread as 14 stub rows, each
with its `unabridged` call → body, 26 calls), and the other twelve now carry a named remaining
failure instead of a zero. The primitive floor at the generous budget - "search the entity
name, read the top 25" - puts the evidence in hand on **5 of 13** (RANK-01/02/03/04, REV-03),
which is more than MailWeave's no-backend arm delivers on the same cases. That is the floor
doing its job: on those five, the machinery has not yet earned its place.

## The remaining failures, decomposed

The twelve undelivered cases fall into exactly three classes, and the boundary between two of
them was measured rather than guessed (`benchmarks/diagnosis-4311/p3a_…`).

**(a) Six declines - R-M2-076 proper.** RANK-01/03/04, EXP-02, REV-02/03 and the UNANS-01
control. The first response raises `DisclosureLadderExhausted`; the driver has nothing to
follow. In every one of these the lexical rungs *had retrieved the evidence message*.

**(b) Three long threads where no response ever offers a body.** SEM-03 (t0004, 94
messages), EXP-01 (t0010, 92), REV-01 (t0049, 31). With the call budget removed entirely
(diagnostic only) the driver still never receives a body-level call for the evidence after
57, 30 and 151 calls: a thread map that cannot fit its messages as ~744-character stub rows
under the 25,000-character cap collapses them into one run whose only affordance is
"fetch all N as snippets"; the snippet response collapses again and offers snippet subsets;
the chain never narrows to a message. The threshold is about thirty messages - RANK-02's
14-message thread mapped as rows and was delivered; REV-01's 31-message thread did not.

**(c) Three cases where a body call is offered and the budget runs out first.** SEM-01
(t0011, 23), SEM-02 (t0031, 27), EXP-03 (t0046, 16). With the budget removed they are
delivered after 44, 23 and 35 calls. The first response offers eleven thread maps in
`not_included_sources`, unranked; the evidence's thread is ninth or tenth in the list, or
(EXP-03) reachable only through a sibling's map; the driver follows the offers in order and
spends its 32 calls before it gets there. This is a fixed scripted driver meeting an unranked
offer list, and it is reported as such, not repaired by raising the budget.

## One bounded R-M2-076 repair, recommended

**Drive the product's own declared recovery contract in the harness.** At the MCP surface a
decline is not an exception: `surface/server.py` turns `DisclosureLadderExhausted` into a
`BUDGET_EXHAUSTED` refusal carrying `retry_with`, built by `recovery.narrower_call` - the
failed call with one dimension reduced (`max_hit_threads` halved, then the top hit thread's
map), never the same call twice, terminal when the chain ends (R-MCP-033). The harness calls
`service.search()` directly and sees the raw exception, so the six declines were scored as
"product failed" when a client would have received a next call. The recovery contract that
exists specifically for this decline has never been measured.

The repair: in `arms._execute`, treat `DisclosureLadderExhausted` and `HostCapExceeded` as the
declined response they become at the surface - compute `narrower_call` exactly as `server.call`
does, record the decline as a hop with its stated narrowing, and offer the retry to `follow()`
under the same 4-hop / 32-call budgets. Harness only; no change to widening, the cap, E2, the
corpus, or any limit.

It is recommended on evidence, not on the argument. Driving the chain by hand on the six
declined cases under the same 32-call budget (`benchmarks/diagnosis-4311/p3b_…`):

| case | declines before an answer | the chain | then |
|---|---|---|---|
| DIAG-RANK-04 | 1 | `max_hit_threads` 9 → 4 | **delivered** after 29 more calls |
| DIAG-RANK-03 | 1 | 12 → 6 | surfaced; budget exhausted (class c) |
| DIAG-REV-03 | 1 | 12 → 6 | surfaced; budget exhausted (class c) |
| DIAG-RANK-01 | 4 | 12 → 6 → 3 → 1 → map of top thread | answered; top thread is not the evidence's |
| DIAG-REV-02 | 4 | 12 → 6 → 3 → 1 → map of top thread | answered; top thread is not the evidence's |
| DIAG-EXP-02 | 5 | … → map of top thread, segment 0 | terminal: the 92-message map declines too (class b) |
| DIAG-UNANS-01 | 1 | 12 → 6 | answered `inconclusive` - the control becomes measurable |

Six "F" cells become one delivery, two budget-bound, two top-thread misses and one terminal -
each a named state a product repair can be aimed at, where before there was only the raise.
And it exposes the next two product questions without pre-judging them: whether the top thread
the chain narrows to is the right one (RANK-01, REV-02), and what a map of a 90-message thread
should offer when its stubs do not fit (EXP-02, and class b above). Those are the R-M2-076
repairs that would need retrieval or wire-format authorisation; this one needs neither.

## Not established, unchanged

Nothing here speaks to the semantic rung: the five cases the lexical rungs never reach
(SEM-01/02/03 by design, RANK-02 by chance of a sibling hit, REV-01) still need the real
backend, and the Mac run's JSON cannot say whether it pooled them. The acceptance criteria and
the content gate are unchanged; R-M2-067..073 stay open.
