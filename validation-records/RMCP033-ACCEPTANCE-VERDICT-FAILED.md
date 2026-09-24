# v0.1 acceptance test 5.1 — FAILED, twice

**Verdict: failed.** Recorded here so the failure is part of the project's evidence rather than
a thing that happened between commits.

| | |
|---|---|
| test | `docs/V0_1_DEMO.md` §5.1, the broad query that R-MCP-033 was written against |
| call | `mailweave_search {"query": "after:2026/09/01", "budget": {"max_hit_threads": 1}}` |
| commit under test | `632cfbc` (Round 29: R-MCP-033 and R-MCP-039 closed, reviewed, rechecked) |
| mailbox | live, through the shipped MCP path, `gmail.readonly` only |
| date | 2026-09-09 |
| raw record | `rmcp033-acceptance-hit-threads-1.json`, written by `docs/V0_1_DEMO.md` §7's script |
| operator | repository owner |

## Why it failed

§5.1's gate is "a served response carrying at least one source with at least one matched row,
inside the 25,000-character host cap". The response was served and inside the cap. It carried
**zero sources and zero matched rows**.

```
declined: false     sources: 0    matched_rows: 0    partial: true
rendered_chars: 8748 (cap 25,000)  search_wall_ms: 2252
budget_caps_hit: ["max_server_ms"]
omission: {withheld_messages: 45, withheld_threads: 13,
           withheld_by_cap: {max_hit_threads: 44, max_server_ms: 1}}
withheld_groups: 13   withheld_records: 1   withheld_tail: []
code / narrowing / terminal / retry_with: null
counters: 6 http_requests, 6 api_calls, 105 quota_units
```

## What the record does establish

**R-MCP-033's repair works live.** The same call on 2026-09-08 produced forty-five per-message
withheld records and a decline at roughly 26,060 characters against the host cap. Here it
serves at 8,748 characters with thirteen counted groups and one record, the omission counts sum
exactly (44 + 1 = 45), `withheld_tail` is empty because thirteen groups sit under the naming
bound of twenty-four, and there is no `-32603`, no host-cap refusal and no retry loop. The
response-size class of failure is closed.

**R-RETR-065 is now the exposed blocker.** The shipped 2,000 ms deadline stopped the query after
six requests. `docs/reviews/ROUND_30/ZERO_EVIDENCE_DIAGNOSIS.md` recovers the exact call mix
from the counters - one `messages.list`, five `messages.get`, **zero `threads.get`** - so no
thread map was ever fetched, and without a map there is no source to disclose a row on.

## Two declaration defects this record exposed, both fixed in round 30

1. `omission.bound` read "the response reached its declared token ceiling" while
   `budget_caps_hit` contained no `disclosed_token_ceiling` and the response sat at 8,748 of
   25,000 characters. `OmissionSummary.bound` documents itself as "`None` when the ladder
   reduced nothing"; both producers stated it unconditionally.
2. `max_hit_threads` withheld 44 of the 45 messages and was absent from `budget_caps_hit`. AD
   A.7 lists it under **Global caps per top-level query**; AD D.11 routes "a per-query cap
   reached" to in-band `budget_caps_hit`. Its absence also let `outcome` read `answered` on
   capped responses, against D.3 rule 5 as implemented in `account.outcome_of`.

Regressions: `tests/test_v0_1_acceptance_round30.py`; replants R128 and R129.

## What this record is not

It is not evidence for any particular deadline value. One observation at 2,252 ms says the
shipped value did not suffice on this mailbox at this moment; it does not say what would. That
question goes to the counterbalanced three-arm run (2,000 / 7,700 / 12,300) over the exact
acceptance call plus a narrow control, pre-registered in
`harness/src/mailweave_harness/validation/deadline.py`. `MAX_SERVER_MS` remains **2,000** and is
not modified until that measurement exists.

---

# Rerun on `b0420ce` — FAILED again

`rmcp033-acceptance-hit-threads-1-rerun-b0420ce.json`, 2026-09-09, same call, same mailbox,
after round 30's declaration fixes.

```
declined: false     sources: 0    matched_rows: 0    partial: true
rendered_chars: 8738 (cap 25,000)  search_wall_ms: 2300
budget_caps_hit: ["max_server_ms", "max_hit_threads"]
omission: {bound: null, withheld_messages: 45, withheld_threads: 13,
           withheld_by_cap: {max_hit_threads: 44, max_server_ms: 1}}
withheld_groups: 13   withheld_records: 1   withheld_tail: []
counters: 5 http_requests, 5 api_calls, 85 quota_units
```

**Both round-30 declaration fixes are confirmed on live data.** `omission.bound` is `null`,
where the first run asserted a token ceiling it never reached. `budget_caps_hit` now carries
both `max_server_ms` and `max_hit_threads`, where the first run named only the clock while
`max_hit_threads` withheld 44 of the 45 messages. `outcome` reads `inconclusive`, which is D.3
rule 5 applied to the repaired list.

**The acceptance gate is still failed, and not as a judgement call.** `docs/V0_1_DEMO.md` §5.1
requires at least one source and at least one matched row. This returned zero of each.

**The zero-evidence path reproduced.** Five requests and 85 quota units solve to
`1 messages.list + 4 messages.get + 0 threads.get` - one fewer body fetch than the first run and
the same shape: no thread map, therefore no source, therefore nothing to disclose. That is
confirmation of `docs/reviews/ROUND_30/ZERO_EVIDENCE_DIAGNOSIS.md`, not a new finding.

Two observations at 2,252 ms and 2,300 ms are consistent with each other and rule out the
first having been a one-off fluctuation. Neither is evidence for any particular replacement
value. That question goes to deadline run 3, whose specs and adoption rule are pre-registered
and unchanged from the moment this record was written.
