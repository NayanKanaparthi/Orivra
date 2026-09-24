# RUBRIC_TRANSITIONS.md — every rubric status change, with its reviewer

**Purpose.** `AGENT_LOOP.md` §6 requires that every status transition in
`RELEASE_RUBRIC.md` record the round number and the reviewer ID, and §1 requires that only
a reviewer that did not write the code may set `PASS`. A markdown status column cannot
carry that, so it is carried here and checked mechanically by
`tools/rubric_status.py --check`, which CI runs.

**Who writes this file.** The orchestrator, from reviewer reports only. An implementer may
not add a row. A criterion marked `PASS` in the rubric with no `PASS` row here fails CI.

**Evidence** must name the reproduction — a test node id, a command, or the reviewer report
path — not a verdict. "Looks good" is not evidence (`AGENT_LOOP.md` §4).

| Criterion | Round | Reviewer | From | To | Evidence |
|---|---|---|---|---|---|
| PART-02 | 1 | R-DISC | NOT TESTED | PASS | 25 adversarial envelope-construction probes; included/accounted counts derived from payload, mismatches rejected (docs/reviews/ROUND_01/R-DISC.md) |
| PART-03 | 1 | R-DISC | NOT TESTED | PASS | `partial` is derived from payload state, not settable; probes attempting to assert a false value rejected (docs/reviews/ROUND_01/R-DISC.md) |
| ~~PART-07~~ | ~~1~~ | ~~R-DISC~~ | ~~NOT TESTED~~ | ~~PASS~~ | Structural scope: closed Role vocabulary, all 7 values, message cannot be included without role+reason; tests/test_envelope_contract.py. Behavioural half re-tests when retrieval rungs land (docs/reviews/ROUND_01/R-DISC.md) |
| ROUTE-01 | 1 | R-DISC | NOT TESTED | PASS | Zero-evidence response cannot be constructed without executed-rung record and diagnosis; `_no_bare_empty_response` probes (docs/reviews/ROUND_01/R-DISC.md) |
| NFR-01 | 1 | R-SEC | NOT TESTED | PASS | Full suite executed with no API key present; `make test` green offline (docs/reviews/ROUND_01/R-SEC.md) |
| NFR-04 | 1 | R-ARCH | NOT TESTED | PASS | Independent clean copy in /tmp, `uv sync --frozen`, ruff + mypy + 199/199 pytest reproduced without reference to HANDOFF (docs/reviews/ROUND_01/R-ARCH.md) |
| REG-04 | 1 | R-SEC | NOT TESTED | PASS | Fixture audit found no real personal mail; suite runs with network disabled (docs/reviews/ROUND_01/R-SEC.md) |
| SEC-04 | 3 | R-SEC | NOT TESTED | PASS | Atomic temp-file+rename verified by forking and hard-exiting a real save() between fsync and replace; orphan sweep verified against dead-pid only (docs/reviews/ROUND_03/R-SEC.md) |
| ~~INJ-04~~ | ~~3~~ | ~~R-SEC~~ | ~~NOT TESTED~~ | ~~PASS~~ | Bidi/zero-width scope: RLO in Subject, From display name and attachment filename stripped and declared; Hebrew and Arabic undamaged; parsers confirmed to make no network calls (docs/reviews/ROUND_03/R-SEC.md) |

| INJ-04 | 4 | R-ARCH | PASS | NOT TESTED | **REVERTED.** R-ARCH-009: the Round 3 recommendation was explicitly "ready for PASS on the bidi/zero-width scope specifically". The orchestrator recorded it unqualified, citing only that narrow evidence, while the criterion is about the whole HTML pipeline. Overreach by the orchestrator, not by R-SEC |
| PART-07 | 4 | R-ARCH | PASS | NOT TESTED | **REVERTED.** R-ARCH-010: the Round 1 recommendation said "structural half only, coverage half not-yet-PASS", with companion finding R-DISC-004 (8 of 10 reason-render variants untested) still open three rounds later. The orchestrator recorded a flat PASS. A criterion is passing or it is not; there is no half |

| INJ-04 | 5 | R-SEC | NOT TESTED | PASS | **Re-promoted at full scope with the citation the Round 4 revert was right to demand.** R-SEC verified across three rounds: Round 1 covered visible-text extraction, hidden-content flagging, no network and no entity resolution; R-SEC-002 (nesting DoS, 122.36s to 0.47s) closed Round 2 and reverified Round 3; R-SEC-005 (bidi/zero-width across Subject, From display name and attachment filename) closed Round 3 and reverified Round 5. R-ARCH-009 was a citation defect in the orchestrator's ledger row, not a false claim by R-SEC (docs/reviews/ROUND_05/R-SEC.md) |

| INJ-04 | 9 | R-SEC | PASS | NOT TESTED | **REVERTED, second time.** R-SEC found that `strip_invisible_characters` lists 16 code points where Unicode defines ~170, so U+061C, soft hyphen and the entire tag block survive. The reviewer flagged this as bearing on INJ-04's "flagged hiding" clause. They did not explicitly ask for a revert; the orchestrator is reverting because a criterion whose evidence a reviewer has called into question should not be counted as passing while that is unresolved. Re-verification is in the Round 10 scope (docs/reviews/ROUND_09/R-SEC-DISC.md) |
| ROUTE-01 | 16 | R-RETR (regression recorded by orchestrator) | PASS | NOT TESTED | **Regression, not an over-promotion.** Round 1's PASS was sound against round-1 code: a zero-evidence response could not be built without its executed-rung record and diagnosis. Round 16's fix for R-RETR-006 made MailWeave *raise* on a query it cannot search, so **17 of 50 plausible queries now produce no envelope at all** (R-RETR-022) — which fails the statement more completely than the bare empty response the criterion was written against. Only a reviewer may restore it, on round-17 code. |

**7 transitions stand. 2 were reverted by R-ARCH audit. 106 criteria remain `NOT TESTED`.**

The two reversals are recorded rather than deleted. Both were orchestrator errors: a reviewer
recommended a *scoped* pass and the orchestrator recorded an *unqualified* one. The rubric has
no half-pass, so the honest status is `NOT TESTED` until a reviewer verifies the whole
criterion. Struck-through rows above are the original erroneous entries, kept for the trail.

Deliberately NOT recorded despite orchestrator verification: the OD-2 outcome-enforcement
probes in `docs/reviews/ROUND_01/R-ORCH.md`. `R-ORCH` is not an `AGENT_LOOP` §2.3 reviewer
domain, and the orchestrator recording its own probes as PASS is exactly the
self-certification §1 forbids. Those criteria wait for a domain reviewer.
