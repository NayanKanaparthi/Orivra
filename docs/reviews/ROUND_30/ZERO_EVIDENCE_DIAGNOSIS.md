# The zero-evidence path, diagnosed from the failed acceptance record

Source: `validation-records/rmcp033-acceptance-hit-threads-1.json`, taken on commit `632cfbc`
against a live mailbox through the shipped `call` path. Nothing here is inferred from a
synthetic run; where a synthetic reproduction is used it is named as one.

## What the record fixes in place

```
declined: false          sources: 0            matched_rows: 0
partial: true            rendered_chars: 8748  search_wall_ms: 2252
budget_caps_hit: ["max_server_ms"]
omission.withheld_by_cap: {"max_hit_threads": 44, "max_server_ms": 1}
counters: http_requests 6, api_calls 6, quota_units 105
```

## The call mix, recovered exactly from the counters

The quota table (`gmail/rates.py`, VERIFIED RO F7) prices `messages.list` at 5 units,
`messages.get` at 20, `threads.get` at 40, `history.list` at 2 and `getProfile` at 1. Over six
requests totalling 105 units there are exactly two integer solutions:

| solution | messages.list | messages.get | threads.get | history.list | getProfile |
|---|---|---|---|---|---|
| A | 0 | 1 | 2 | 2 | 1 |
| B | **1** | **5** | **0** | 0 | 0 |

Solution A is impossible twice over: a search cannot reach a hit set with zero `messages.list`,
and two `threads.get` calls would have produced two maps and therefore sources, while the record
says `sources: 0`. **Solution B is what happened: one list page, five body fetches, and not a
single thread map.**

**Corroborated independently of the arithmetic** (round-30 review): a synthetic 14x3 mailbox
driven with an operator-only query, `max_hit_threads: 1` and `max_api_calls: 6` reproduces the
counters exactly - 6 requests, 6 api calls, 105 units, mix `1 list + 5 get`, zero sources, zero
matched rows.

**Five is not a cap.** An earlier draft of this document said five was `MAX_BODY_FETCHES_L0 = 5`
and that was wrong (R-V30-001): `after:2026/09/01` is operator-only, so the run is **L1**
(`rungs: ["L1"]` in the record), and L1's body-fetch cap is `MAX_BODY_FETCHES_L1 = 10`. Five is
the clock stopping partway through ten, not a budget being reached. The conclusion is unchanged
and the mechanism is worse than the draft claimed: nothing bounded the fetching except time.

**The counters are over attempts, not over successes** (R-V30-002). `record_attempt` sits inside
the retry loop, so a retried call increments `http_requests`, `api_calls` and `quota_units`
alike. Two consequences, and neither is resolvable from this record: it is *not* established
that five distinct message bodies were retrieved, and `RETRY_BASE_MS = 250` means a single
retry would put at least 250 ms of deliberate sleep inside the 2,252 ms. So the per-request
latency figure below is an average over attempts that may include a backoff, and is a third
candidate explanation alongside network variance and first-call handshake cost.

## The path

1. L1 issues one `messages.list`. It finds fourteen hit-bearing threads holding forty-five
   messages. `H` is established and every id in it is accounted for from here on.
2. The ladder fetches five message bodies, spending five sequential `messages.get` round trips.
3. The 2,000 ms deadline expires. Total wall time 2,252 ms across six attempts, so roughly
   330 ms per attempt against PF-21's measured 83 ms - the discrepancy R-RETR-065 exists for,
   and the reason no arithmetic based on PF-21 predicts this run. Three candidate causes fit
   and this record separates none of them: real network variance, first-call TLS and token
   refresh inside the timed window, and one or more retries each carrying `RETRY_BASE_MS`
   of backoff.
4. `assemble` runs with the clock already exhausted. It buys no mailbox watermark, which is why
   `getProfile` does not appear: "a budget already exhausted before the maps buys no watermark".
5. `max_hit_threads: 1` permits exactly one thread map. The accountant refuses it. **Zero
   `threads.get` calls are made.**
6. A `source` is a mapped thread. With no map there is no source, so nothing can be disclosed
   as a row, and every one of the forty-five ids leaves through the only lawful exit: a
   `withheld` record or group. Thirteen capped-away threads become thirteen groups (44
   messages); the one permitted thread's single message becomes one record naming
   `max_server_ms`.

## What this is, and what it is not

**It is not a bookkeeping-overflow failure.** R-MCP-033's repair is visibly working: the
response served at 8,748 characters against a 25,000-character cap, with thirteen groups and
one record where the 2026-09-08 diagnostic produced forty-five records and a decline at ~26,060
characters. No `-32603`, no host-cap refusal, no retry loop.

**It is not a case of retrieval finding nothing.** Fourteen hit-bearing threads were found and
forty-five messages were accounted for, and five `messages.get` attempts were spent on bodies.
How many of those five *succeeded* is not established by this record, for the reason above.

**It is a budget apportionment failure.** The deadline was spent entirely on the ladder's body
fetches, and the one `threads.get` that would have turned retrieved evidence into a disclosable
source was never affordable. The response is truthful about all of it, and it carries fourteen
executable recovery calls, so the invariants hold - but the acceptance gate asks for at least one
source and one matched row, and this returns neither.

Two things follow, and only the first is settled:

* **Settled: the deadline is not calibrated against observed latency.** Six requests exhausted
  it. PF-21's 83 ms per request predicts about 500 ms for those six. Whether the gap is real
  network variance, first-call TLS and token refresh inside the timed window, or both, is not
  separated by this record, and this document does not guess. That is what run 3 measures.
* **Not settled, and deliberately not acted on: whether the ordering is also wrong.** A design
  that reserved the single `threads.get` needed to produce one source would have returned mail
  here at any deadline value. That is a change to budget apportionment, not a constant, and
  proposing it before the measurement exists would be fitting a mechanism to one 2,252 ms
  observation. It is recorded here as a question for after run 3, not as a plan.

## What would make this a reading instead of an inference

`MeterReading` already carries `api_calls_by_endpoint` and `http_requests_by_endpoint`;
`Counters` drops both, which is why the call mix above had to be recovered by solving an
equation (R-V30-003). Surfacing them would make the next diagnosis of this kind direct. Not done
in round 30: they are new wire fields, and the field census, the sizing constants and the
serialisation inventories were all certified against the current shape days ago. Recorded as the
first item for whatever round follows the deadline measurement.
