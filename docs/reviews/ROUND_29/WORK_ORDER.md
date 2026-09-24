# Round 29 — R-MCP-033, the v0.1 blocker

**Scope: this finding only.** Not N-1, not R-MCP-039, not R-MCP-034/035, not WS-08/WS-09, not
the deadline. `MAX_SERVER_MS` stays 2,000. No general audit round runs before this closes.

## The defect, stated as the code shows it

`Layout.accounted_ids` is `frozenset(ledger.origins)`: every message id the ledger ever
observed. The character charge for bookkeeping is `accounted_ids - present_ids`, one full
`withheld` record each (`disclosure/layout.py:388-422`). Three consequences follow, and all
three are the finding:

1. **Capping does not shrink.** A thread dropped by `max_hit_threads`
   (`retrieval/assemble.py:1990`) keeps its observed ids in `accounted_ids`; the cap moves them
   from disclosed to withheld and charges each one 516 characters. Tightening the cap makes the
   response the same size or larger. Confirmed live: 26,060 characters at `max_hit_threads: 3`
   and 26,060 at `max_hit_threads: 1`.
2. **The ladder cannot converge.** Step 8 removes a row worth `840 + 8*M` and adds back a
   withheld record worth `420 + 4*T + 2*M`: 968 out, 516 back, a net 452. Step 7 adds
   `1,020 + 5*T` for the source on top of a record per row. So the cheapest path to "smaller"
   is to strip every row, and once every row is gone the bookkeeping alone exceeds the cap.
   That is why the refusal reports 0 rows, 0 sources, 45 withheld records.
3. **The recovery loops.** `_narrower_call` (`surface/server.py:267-284`) mints
   `{"query": <same>, "budget": {"max_hit_threads": 1}}` unconditionally, without looking at
   what the caller already asked for. A caller who asked for `max_hit_threads: 1` is handed
   back its own request.

## The rule the fix is built on

**A withheld record is written at the granularity of the call that recovers it.**

That is the whole design, and it is a contract reading rather than a size trick. AD's own table
says a `max_hit_threads` withholding arises "so no map exists to carry a stub row" and hands the
caller `mailweave_thread_map{thread_id}`. The recovery is per **thread**. Emitting forty-five
per-message records whose only affordance is the same three thread-map calls is not more
truthful than three records that each say how many messages they stand for: it is the same
information, repeated, at a granularity the caller cannot act on.

R-06 governs the other side of the line and is not weakened: *"withheld content is represented
as visible stubs, not as a number alone, **wherever the map is present**"*. Where a map is
present the rows stay rows. Grouping applies only where no map exists to carry a stub.

So:

| the cap | granularity | wire shape |
|---|---|---|
| `disclosed_token_ceiling`, `partial_source_failure` | per message — the caller can pass the id to `mailweave_get_messages` | individual `withheld[]` record, unchanged |
| `max_hit_threads`, `max_source_threads`, `max_pool_threads`, `max_pool_messages` | per thread — the recovery is a thread map | one `withheld_groups[]` record per (thread, cap) with an exact `message_count` |

## What must be built

1. **`WithheldGroup` on the wire** — `{thread_id, cap, why, message_count, affordance}`.
   `message_count` is exact, never a floor or an estimate.
2. **An omission summary, machine-readable** — counts of withheld messages in total and by cap,
   not-included sources, and threads never mapped, as structured fields. The remediation prose
   keeps saying it in words; the prose stops being the only place it is said.
3. **`DispositionLedger.certify()` keeps its assertion unchanged.** `H == disclosed ∪ withheld`
   is still enforced over **ids**, in process, before anything is emitted. The change is what
   the wire carries, not what the invariant covers. A new assertion is added beside it: the
   individual records plus the group counts must sum to exactly `|withheld_ids|`, so a grouped
   id cannot be dropped and cannot be double-counted.
4. **`layout_chars` charges the shape that will actually be emitted** — grouped ids at one group
   record each, ungrouped ids at one message record each. An estimate that charges a shape the
   response does not emit is the defect R-MCP-024 already closed once; this must not reopen it.
   `layout_chars >= rendered_chars` must still hold across the existing matrix.
5. **A retry that differs and progresses.** `_narrower_call` reads what was applied and mints
   something strictly narrower on some dimension. When no narrower search exists it changes
   dimension rather than repeating itself. A guard refuses to emit any affordance whose
   `(tool, args)` equals the failed `(name, arguments)`.

## Acceptance — every one demonstrated by execution

The nine requirements in `docs/reviews/R-MCP-033.md`. Mapping to the checks:

| # | requirement | check |
|---|---|---|
| 1 | compact bookkeeping, truthful aggregates | grouped records with exact counts; the sum assertion in `certify()` |
| 2 | counts machine-readable | structured summary fields asserted on the served envelope, not on prose |
| 3 | `max_hit_threads` reduces the response | one mailbox, two caps, `rendered_chars` strictly smaller at the tighter cap |
| 4 | retry never identical | property test over declines: `(tool, args) != (name, arguments)` |
| 5 | following the retry progresses | execute the minted retry; the chain terminates in a served response, bounded |
| 6 | non-empty evidence inside 25,000 | the regression fixture returns >= 1 source and >= 1 matched row |
| 7 | no silent drop | `certify()` assertion unchanged plus the new sum assertion |
| 8 | regression + independent review | the 45-record fixture, shown to fail at `5e86229`; one focused review |
| 9 | live diagnostic repeated | the owner re-runs the exact diagnostic; recorded beside the failing one |

## What must not be done

- Do not raise `HOST_RESULT_CHAR_CAP` or any ceiling.
- Do not drop bookkeeping without accounting for it. Requirement 7 exists to make that a
  failure rather than a fix.
- Do not special-case `after:2026/09/01`, this mailbox, this thread count, or this
  `max_hit_threads` value anywhere in the server.
- Do not tune a constant until the regression passes. If the arithmetic needs a constant to
  change, the constant changes because it was measured wrong, and the measurement is shown.
