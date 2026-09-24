# R-MCP-033 — the v0.1 product blocker

**Escalated HIGH -> BLOCKER on 2026-09-08 by the owner**, as a portfolio-release sequencing
decision. Nothing was removed from the project scope: the remaining workstreams continue after
the v0.1 demonstration is stable. What changed is order. No further general audit round runs
before this is fixed.

Raised round 27. Ledger row in `docs/reviews/FINDINGS_LEDGER.md`.

## The defect, in one line

The disclosure bookkeeping crowds out the mail: on a broad query the response is entirely
accounting for what was left out, exceeds `HOST_RESULT_CHAR_CAP`, and is refused whole, so the
caller gets nothing rather than something partial.

## Evidence

Round 27 filed it from a synthetic 15-thread shape: 22,451 characters carrying zero messages,
6,816 in `withheld`, 4,908 in `not_included_sources`, 2,415 in affordances, and the text mirror
rendering all of it a second time. That was a fixture.

It is now confirmed against **real mail on a live mailbox**, twelve calls, 2026-09-08:

- `validation-records/deadline-validation-run2.json` - `after:2026/09/01`,
  `max_hit_threads: 3`, three deadlines x three counterbalanced repeats. All nine declined
  `budget_exhausted`. Estimated response 26,060 characters at the shipped 2,000 ms deadline and
  29,360 at both 7,700 and 12,300 ms, against a 25,000 cap. **Zero rows, zero sources, 45
  withheld records** in every single call. `stable: true`.
- `validation-records/rmcp033-diagnostic-hit-threads-1.json` - one call, arguments copied
  verbatim from run 2's own `retry_with`: `max_hit_threads: 1`. Declined identically. Estimated
  26,060 characters, zero rows, zero sources, 45 withheld records.

## What the diagnostic established, and what it did not

**Established: the recommended retry is invalid.** The decline at `max_hit_threads: 1`
re-proposes `{"query": "after:2026/09/01", "budget": {"max_hit_threads": 1}}` - the identical
arguments that just produced it. A client that follows the remediation loops without
terminating. This is a defect in the recovery contract, not only in the sizing.

**Established: that retry did not make the response smaller.** 26,060 characters at
`max_hit_threads: 3`, 26,060 at `max_hit_threads: 1`. Zero characters of difference.

**Not established: that `max_hit_threads` never bounds the response.** Both of those calls ran
under the shipped 2,000 ms deadline and stopped there (2,278 ms and 2,301 ms), so the deadline
is a confound: it is possible that the cap would bind at a larger deadline and the two runs
merely stopped at the same point for the same unrelated reason. The cap was not tested at a
larger deadline with a smaller thread count. A fix must demonstrate the cap binding, not assume
it from these two numbers.

**Observation, not yet a separate finding.** The structured decline carries no `withheld` count
as data: the diagnostic record reads `withheld: 0` while the remediation prose says 45 withheld
records. A client can only recover that number by parsing English. This is adjacent to
R-MCP-034's class (recovery information present in prose, absent from the structure). A
reviewer should decide whether it is separable or part of this fix; it is recorded here rather
than given an ID by the orchestrator alone.

## Acceptance criteria

**Superseded 2026-09-08.** The owner replaced the earlier seven with the nine below after the
diagnostic. Requirements 1, 2, 4 and 5 are new; the rest restate the seven. R-MCP-033 is fixed
only when **all nine** hold:

1. cap or compact the per-message bookkeeping while preserving truthful aggregate omission
   information;
2. expose omitted counts machine-readably, not only inside remediation prose;
3. make `max_hit_threads` genuinely reduce the response;
4. never return a `retry_with` identical to the failed request;
5. prove that following the retry produces progress;
6. return non-empty evidence for this broad capped query within 25,000 characters;
7. preserve the no-silent-drop invariant;
8. add the 45-withheld-record regression and obtain one focused independent review;
9. repeat this exact live diagnostic after the fix.

Requirements 1-7 are demonstrated by execution, not by claim. Requirement 8 satisfies
REG-01/REG-02: the fixture must be shown to **fail** against the pre-fix commit. Requirement 9
is the same live call, `after:2026/09/01` with `max_hit_threads: 1`, recorded next to
`validation-records/rmcp033-diagnostic-hit-threads-1.json` so the before and after sit together.

## The arithmetic, exactly

The refusal's numbers are fully reconstructed from the code, and they close to the character:

```
layout_chars =  RESPONSE_STRUCTURAL_CHARS                       2,600
             +  recommended_expansion_chars (naming nothing)      240
             +  45 x withheld_chars(420 + 4*T + 2*M)  @T=M=16  23,220
             +  0 x not_included_chars                                0
             =                                                  26,060   (observed: ~26,060)
```

and at the two larger deadlines three more threads were mapped and then split off by A.9a step
7, adding `3 x not_included_chars(1,020 + 5*16) = 3 x 1,100 = 3,300`, giving 29,360 (observed:
~29,360). Nothing here is estimated after the fact; both figures fall out of
`disclosure/layout.py:388-422` and the constants in `envelope/measure.py`.

**This resolves the confound recorded above.** The reason `max_hit_threads: 1` did not shrink
the response is structural, not an artifact of the 2,000 ms deadline:
`Layout.accounted_ids = frozenset(ledger.origins)` holds every id the ledger *observed*, and the
withheld charge is `accounted_ids - present_ids`. Capping threads away moves ids from
*disclosed* to *withheld*; it never removes them from the charge. A tighter cap therefore leaves
the bookkeeping the same size or makes it larger, which is exactly what both runs showed. The
earlier caution about the deadline can be withdrawn: requirement 3 is a confirmed defect, and
`retrieval/assemble.py:1990` with `disclosure/layout.py:418` is where it lives.

**And it explains why the ladder empties the response.** Dropping a row under step 8 removes
roughly `840 + 8*M` characters and adds back a withheld record of `420 + 4*T + 2*M` - at
`T = M = 16` that is 968 out and 516 back in, a net saving of 452 per row. Splitting a whole
source under step 7 adds `1,020 + 5*T` on top of one withheld record per row it held. The
ladder therefore has to strip everything before it can fit, and once every row is gone the
bookkeeping that remains is larger than the cap on its own. The response is pure bookkeeping
because the bookkeeping is what overflowed.

## Sequencing

Blocked behind this, explicitly:

- R-RETR-065 / the `MAX_SERVER_MS` decision. Closed as blocked, `MAX_SERVER_MS` stays 2,000.
  See `validation-records/DEADLINE_DECISION.md`. The three-arm validation harness is built,
  corrected and tested; it has never had a query that both answers and spends a real clock,
  and this is why.
- Further general audit rounds. Round 28's R-MCP and R-RETR reviews included.

Not blocked, and not started: N-1, R-MCP-039, WS-08, WS-09, the measurement campaign, history
rewrite, credential rotation. These remain in scope and resume after the v0.1 demonstration is
stable.

## What must not be done to satisfy this

Any route out is a decision about what a response carries. Round 27 named three: dedupe the
shared `why`, summarise the tail, or measure-and-retry instead of estimate. None of them is
"raise the cap", none is "drop the accounting quietly", and none is a special case for this
query. Criterion 2 exists to make silent dropping a failure rather than a fix, and criterion 5
exists so the fix is shown against the shape that actually broke.
