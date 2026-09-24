# v0.1 live demonstrations 5.1 - 5.4: results

All four run by the repository owner through a real MCP client against the live test mailbox on
commit `ab72930` (`MAX_SERVER_MS = 7,700`). **All four met their `docs/V0_1_DEMO.md` §5
criteria.** The observations at the foot are recorded as backlog, not as passes reinterpreted.

## Provenance, stated plainly

5.1's evidence is a structured record written by the §7 script and committed:
`rmcp033-acceptance-hit-threads-1-ab72930.json`. **5.2 through 5.4 are operator transcripts of
what the MCP client reported**, not structured records. Where a field is quoted below it is
quoted from what the client rendered, and the client itself flagged more than once that it was
reading the text mirror rather than the structured payload. That distinction matters for
observation 4.

## 5.1 - the broad query that returned bookkeeping and no mail (R-MCP-033) - PASS

Criterion: a served response with at least one source and at least one matched row, inside the
25,000-character host cap.

`mailweave_search {"query": "after:2026/09/01", "budget": {"max_hit_threads": 1}}` returned 1
source, 1 matched row at `body_clean` (`1a0750dcff6babce`), 14,029 characters, 5,137 ms, 13
requests. `budget_caps_hit: ["max_hit_threads"]`; `max_server_ms` did not fire.
`omission.bound` null, 44 messages withheld across 13 groups, tail empty. No `-32603`, no retry
loop, no unrecoverable decline. Failed twice before this on the 2,000 ms deadline.

## 5.2 - a long thread - PASS

Criterion: the thread arrives as one source, its total stated, its members present as rows or
inside declared collapsed runs each carrying an expansion call, and the answering message at
`body_clean` or offered by the recommended expansion.

One source, `stated_total: 12`, 12 of 12 rows present, no collapsed runs. The answering message
`1a075a351cc9d190` (position 7, thread `1a075a12d3dec8eb`) arrived at `body_clean` on the first
call, satisfying the criterion's first branch. Search: `partial` yes, `outcome` inconclusive,
`truncated_by` mailweave, caps `disclosed_token_ceiling`, depths body_clean at 0/2/7, snippet at
1/3/4/8, stub at 5/6/9/10/11. A follow-up `get_messages` at those positions returned them at
`body_clean`, `partial` no, `outcome` answered. Positions 1, 3, 4 and 8 were never read past
snippet; the operator recorded that as an unread remainder rather than smoothing it over.

The correct answer was reached: UTC dates read as local during the reconciliation join, fixed by
normalising both date columns to UTC before joining, with a midnight-boundary regression check
added afterwards.

## 5.3 - a decision that was later reversed - PASS

Criterion: both messages identified, the answer states the later one, and if the earlier is not
in the response it is named in `withheld[]` or reachable through a listed call. The reversal
must not be silently flattened.

All four messages of thread `1a075a437a305e2c` came back as rows. The approval
`1a075a43918e05eb` (position 0) and the final decision `1a075a4a501838ee` (position 3) were both
identified, the later one treated as authoritative and the earlier one explicitly called
superseded. Nothing was withheld on any of the three calls; `partial` no, `truncated_by`
nothing, `budget_caps_hit` none, no declines.

The correct answer was reached: Larch approved conditionally, then withdrawn when it could not
meet recycled-content certification; Willow chosen. The operator noted that the first message
reads as a clean approval in isolation, which is the failure mode this case exists to catch, and
it was not flattened.

## 5.4 - an answer spread across separate threads - PASS

Criterion: each contributing thread is a source (or a `withheld_groups[]` entry with a map
call), the answer cites ids from more than one thread, and `partial` is truthful.

Two threads, both returned as sources, each `included 1 of stated_total 1, as_stub 0`:
`1a075a87ecc5f404` in `1a075a87988f254f` (the count) and `1a075a8d63cc0d0c` in
`1a075a8d0a1cc337` (destination and deadline). No `withheld_groups[]` entries, so no map call
was needed. `partial` no on all three calls, which is truthful: both threads were fully
included and nothing was withheld. `budget_caps_hit` none, no declines.

The correct answer was reached, from two threads that never reference each other: 24 kits, Dock
3 at the North Pavilion, by 16:00 IST on 22 September 2026.

## Observations, recorded as backlog

None of these changed a verdict. All four criteria are met on their own terms. These are what
the runs surfaced beyond them, and they are written here because the alternative is losing them.

1. **No recommended expansion affordance appeared in 5.2** even though matched rows came back
   below the requested depth, which is the condition round 28 built that affordance for. The
   criterion was satisfied by its first branch (the answering message was already at
   `body_clean`), so this did not decide the case. The operator constructed the expansion by
   hand from the `map_id` and positions. Whether the affordance was never built or was built and
   not rendered is **undetermined from the client side** and was not investigated.
2. **No date or timestamp reached the client for any message in 5.3.** Chronological order was
   inferred from thread position and reply linkage. For a decision-reversal case, "which one is
   later" resting on position rather than a disclosed timestamp is thinner evidence than it
   looks, even though the answer was right.
3. **5.4 reported `outcome: inconclusive` and `sufficiency: insufficient` with `caps hit: none`
   and every not-tried rung `not_applicable`.** Both facts the question needed were in the
   response. This may be `outcome_of`'s I-4 clause working as designed - `answered` requires
   evidence the query itself produced, not merely disclosed rows - or it may be the
   cross-thread shape scoring insufficient by construction. **Undetermined; not investigated.**
4. **Both 5.4 searches disclosed matched rows at `snippet` when `body_clean` was requested,
   with `caps hit: none` and `truncated_by: nothing`.** A.9a's depth demotion is step 1 and the
   architecture says each step is declared in `reductions[]` and named in `budget_caps_hit`. In
   5.2 the equivalent demotion did name `disclosed_token_ceiling`. Either the declaration was
   made and not rendered - R-MCP-042, the text mirror - or a demotion happened undeclared. If
   one of these four is a real defect, this is the one I would open first.

Observations 1 and 4 have the same possible cause and the same resolution: read the structured
payload rather than the text mirror. That is one call, and it is the first thing to do after the
freeze.
