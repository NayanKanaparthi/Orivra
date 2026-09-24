# Through the MCP boundary: the sem-off comparison, and the long-thread blocker

Regression diagnostics, not acceptance evidence. All earlier runs are preserved:
`diagnostic-run-4311.ORIGINAL-2026-09-13.*` (the real-backend run on the service seam),
`diagnostic-rerun-semoff-4311.*` (sem-off after repairs 1-3, service seam). This run is
`diagnostic-rerun-boundary-semoff-4311.*`, from `benchmarks/rerun-boundary-4311.py`.

## What changed in the driver, and what did not

`evaluation/boundary.py` drives every call through `surface/server.py::call` - the case's own
search, every refusal retry a decline offers (`retry_with`, R-MCP-033), every expansion
affordance - classifies each result the way a client does (served / declined / raised), and
counts all of them against one budget: `TOTAL_CALLS = 1 + MAX_RECOVERY_CALLS = 33` calls per
case, depth `MAX_RECOVERY_ROUNDS = 4`. A refusal retry is one level deeper like any other call.
Nothing was raised: the follow-up budget is the one the service-seam driver always had, with
the search now counted too. Corpus, cases, scoring rule (EP §6.1 `disclosed`) unchanged.

Three columns are kept apart and must not be read as one:

| column | means | is evidence? |
|---|---|---|
| **delivered** | the required evidence's content is in hand after the walk | yes - the only one |
| **recoverable** | a decline was turned into a served response somewhere in the chain | no - the contract working |
| **measurable** | the case ended in a named state (`Reach.stopped`), not a raise | no - a property of the driver |

**R-M2-076 is not resolved.** Six raw exceptions became six structured refusals with retries;
that makes them measurable and, in five cases, recoverable. Only one of the six was delivered.

## Per case, `sem-off`, 33-call budget

| case | delivered | recoverable | measurable | calls | declines | stopped | top thread | priority (kept separate) |
|---|---|---|---|---|---|---|---|---|
| DIAG-SEM-01 | no | no | yes | 33 | 0 | call_budget | - | offered 10th of 35; map followed; body call never offered |
| DIAG-SEM-02 | no | no | yes | 21 | 1 | hop_budget | - | offered 11th of 22; map followed; body call never offered |
| DIAG-SEM-03 | no | no | yes | 33 | 3 | call_budget | - | evidence thread is a source (94 msgs); body never offered |
| DIAG-RANK-01 | no | yes | yes | 5 | 4 | hop_budget | **top thread ≠ evidence thread** | chain 12→6→3→1→map used all four levels |
| **DIAG-RANK-02** | **YES** | no | yes | 27 | 2 | evidence_in_hand | - | offered 2nd of 26; 14-msg map as rows → body |
| DIAG-RANK-03 | no | yes | yes | 33 | 3 | call_budget | - | offered 19th of 23; map followed; a body call was offered, budget spent first |
| **DIAG-RANK-04** | **YES** | yes | yes | 31 | 2 | evidence_in_hand | - | 1 decline (9→4), then offered 2nd of 27 → 11-msg map → body |
| DIAG-EXP-01 | no | no | yes | 19 | 3 | hop_budget | - | offered 3rd of 6; 92-msg map followed; body never offered |
| DIAG-EXP-02 | no | no | yes | 5 | 5 | hop_budget | **top thread ≠ evidence thread** | chain used all four levels; 5th decline terminal |
| DIAG-EXP-03 | no | no | yes | 33 | 0 | call_budget | - | offered 29th of 31; map followed at the budget's edge |
| DIAG-REV-01 | no | no | yes | 33 | 0 | call_budget | - | evidence thread not offered at all (35 offered) |
| DIAG-REV-02 | no | yes | yes | 5 | 4 | hop_budget | **top thread ≠ evidence thread** | chain used all four levels |
| DIAG-REV-03 | no | yes | yes | 33 | 2 | call_budget | - | offered 17th of 29; map followed; body never offered |
| DIAG-UNANS-01 | control | yes | yes | 2 | 1 | no_new_affordances | - | served `inconclusive` after one retry |
| DIAG-UNANS-02 | control | no | yes | 1 | 0 | no_new_affordances | - | served `inconclusive` |

Totals over 13 answerable: **delivered 2**, recoverable 5, measurable 13; floor-tight 0,
floor-generous 5, qf-1 6 (handed the right conversation; residual bias). Undelivered by why the
driver stopped: call_budget 6, hop_budget 5.

## The undelivered eleven, in the classes that were measured

**Top-thread selection** (3, kept separate, not repaired): RANK-01, EXP-02, REV-02. The chain
narrowed 12 → 6 → 3 → 1 → `thread_map(top thread)` and the top thread was not the evidence's.
The chain is four calls deep, so on the standing depth budget it also leaves nothing for
expansion even when the top thread is right. Two separate facts: which thread the chain picks,
and how long the chain is. Neither is a driver problem and neither is repaired here.

**Recovery prioritisation** (3, kept separate, not repaired): RANK-03, REV-03, EXP-03. A decline
was recovered (or none occurred), the evidence's thread was offered - 19th, 17th, 29th in an
unranked list - the driver followed it, and the budget ran out before the body. RANK-03 had a
body call offered and unexecuted at the budget's edge.

**The long-thread blocker** (5, product, R-M2-080): SEM-01 (t0011, 23 msgs), SEM-02 (t0031,
27), SEM-03 (t0004, 94), EXP-01 (t0010, 92), REV-01 (t0049, 31). The map of the evidence's
thread was followed - or the thread was a source - and **no response ever offered a call that
carries the body.** Measured on a corpus-free 90-message fixture
(`tests/test_r_m2_080_long_thread_body_reach.py`):

  * `thread_map`: zero rows, one run of 90, one affordance - `get_messages(all 90, snippet)`.
  * `get_messages(N, snippet)` for N = 90, 45, 23, 12: **exactly five** snippet rows (the
    protected top-k, `DISCLOSURE_TOP_K_HITS = MAX_BODY_FETCHES_L0 = 5`), each with its
    `unabridged` body call, and a run of the remaining N-5 whose affordance is again
    `get_messages(<same members>, snippet)`. Following it yields the same five rows.
  * `get_messages(N, stub)` for N = 90, 45, 23, 1: **zero rows** in every case. A named stub
    is collapsed like any other (`ladder._collapsible` takes every stub row), so the stub view
    of `mailweave_get_messages` never returns the message it was asked for.

So the chain from a long thread's map is: run → the same five rows → the same run. Message
75 of 90 is named by every response and read by none. The driver's budget is not the cause:
with the budget removed it is still never offered. This is a product blocker on the
expansion path and it is recorded as R-M2-080.

## R-M2-080: the regression, and a bounded repair proposal

**The regression is in place and strictly expected to fail.** Two tests in
`tests/test_r_m2_080_long_thread_body_reach.py`, `xfail(strict=True)` against R-M2-080, state
the requirement on a 90-message single-thread fixture with the fact at position 75: following
only what the responses offer, within the standing budget, the message's body is in hand -
from the search, and from the map alone. A third test is the guard the repair must not break:
every served response stays under the host cap, and every mapped source accounts for every
position as a row, a run member or a withheld record. The two flip to passing when the repair
lands; the guard must not move.

**The proposal, two changes on the expansion path, both inside the cap and the accounting:**

1. **A requested stub is the request, not the map's filler.** `ladder._collapsible` exempts
   rows whose id is in the layout's `hit_ids` (which on the expansion path is exactly
   `wanted.named`) while they fit; only the unrequested remainder collapses. Then
   `get_messages(ids, view=stub)` returns those ids as stub rows, each with its `unabridged`
   body call, up to the number the cap admits - about twenty, derived from the accounting
   constants (`ROW_STRUCTURAL_CHARS`, the identity block, the overhead), never hard-coded.
2. **A collapsed run's affordance advances and narrows.** A run of N members is emitted as
   ⌈N / W⌉ runs of at most W members, W the row capacity from (1), each carrying
   `get_messages(member_ids=<that window>, view=stub)`. `CollapsedRun` is unchanged in shape:
   one affordance per run, more runs. Following a window returns its members as stub rows (1),
   each one call from its body. A run never again offers the call that produced the response
   it sits in.

Hop count for a 90-message thread: search (0) → map (1) → window of ≤20 as stub rows (2) →
body (3). Inside the four-hop budget with one to spare. Omission accounting is untouched: a run
member is still a run member and `accounted_for` counts the same three dispositions. The cap
is honoured by construction: W is derived from it, and the ladder still runs on the estimate.
Cost: `ladder._collapsible` (an exemption keyed on the layout's own `hit_ids`),
`expansion._collapsed` and `assemble`'s run emitter (windowing), a capacity function in
`envelope/measure.py` beside the constants it reads, and the accounting for runs and their
affordances - which is already per-run. Estimated 80-150 lines plus the tests already written.
This is a change to A.9a's published behaviour ("every stub row is collapsible") and to the
expansion path, and it needs that authorisation; nothing here executes it.

What it would not fix, and is not claimed to: the three top-thread misses and the three
budget-bound cases above, which are measured separately; and the five cases the lexical rungs
never reach at all, which need the real backend.

## Not established, unchanged

Nothing here speaks to the semantic rung. The acceptance criteria and the content gate are
unchanged; R-M2-067..073 stay open. R-M2-076 is not resolved.
