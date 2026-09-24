# M1 complete — source-independent contracts, adapter boundary, and the seeder

**Closed:** 2026-09-10 by owner decision, on the live acceptance recorded at
`validation-records/M1_LIVE_ACCEPTANCE.md` (commit `91a2607`).

M1's definition of done was: a working Gmail-only Orivra MCP path, preserved MailWeave
compatibility, the bounded seeder, a green existing suite, and the four demonstrations checked for
semantic equivalence through both surfaces. Every clause is met.

## The commit ledger

| Commit | What it added |
|---|---|
| `8c9e904` | Orivra source-independent contracts, and the gates computed rather than declared |
| `e14f144` | The adapter boundary, the Gmail adapter, the registry, and a budget that binds nothing |
| `35daaf2` | The Orivra MCP surface, and the replant guard that had stopped guarding |
| `73fa1f6` | The bounded seeder, and a guard runner that swept one tree of two |
| `b628b24` | Handle compatibility proved by execution, and one level-2 comparison for both runs |
| `74540bc` | Fifteen replants for M1's own behaviours, and the one that was MISSED |
| `803b597` | The correction pass: what an independent review found, and what now defends it |
| `23c106d` | The closure pass: the owner's R-M1-016 decision, and two corrections it exposed |
| `91a2607` | The acceptance correction: the lockfile committed, and the affordance bound made to fail closed |

Nine commits. The completion count is nine, not six and not seven; earlier drafts of this ledger
undercounted and are superseded by this table.

## What the independent review found

The reviewer's verdict was **"M1 is green and M1 is not correct."** Four criticals, every one of
them reachable through the published contract rather than through internal state:

- **R-M1-001** — a `pydantic.ValidationError` escaped the `orivra_ask` handler carrying
  `input_value` including node content. R-SEC-043 recurring. Fixed by one shared `in_band`
  partition used by both surfaces.
- **R-M1-002** — `except LookupError` over-caught `KeyError`/`IndexError` and echoed `str(exc)`
  as an `auth_reauth_required` remediation. Fixed by `ConnectorUnavailable(RuntimeError)`.
- **R-M1-003** — a bidirectional subset test in `Candidate.matches` let a one-word key match any
  phrase containing it. The reviewer used it to build a contract-accepted, correctly-typed
  **observed** `supersedes_stated` edge at a document the text never named. Fixed by a
  one-directional rule plus a generic-token stoplist.
- **R-M1-004** — `Source.collapsed_runs` was dropped, so a 300-message thread reported
  `included=300` with zero omission records. Fixed by emitting an omission at BRANCH granularity.

Eighteen further findings were fixed in the same correction pass. R-M1-016 was escalated to the
owner and settled by the permission-conjunction decision built in the closure pass.

## Backlog carried into M2

Seven items, recorded rather than fixed, listed in full in
`docs/reviews/ORIVRA_V1/M1_FINDINGS.md`. The two most likely to matter:

- **R-M1-025, the scope-blind clause gate.** It scans the sentence and the line rather than the
  governing clause, so "the May 2 pricing draft" refuses on the modal `may`. Every failure is in
  the safe direction, but the true-positive rate is lower than the design believes. A
  clause-structured recogniser is M3's work.
- **R-M1-031, budget stages vs the plan's schedule.** Plan §2.3 says `cold_start_ms`,
  `retrieval_ms` and `disclosure_ms` are first measured at M1; `m1_budget()` ships all eight
  unmeasured. Declared, and a deviation.

## Limits of the acceptance evidence

Stated rather than buried. Paired affordance execution was exercised on one of four demonstration
queries, because the other three offered zero pairs. The fail-closed over-limit path did not fire
live, because this run surfaced 11 pairs and the bound is 12. Both are recorded in the acceptance
record. M1 is closed with these limits known, not with them resolved.

## What M1 does not claim

No semantic search, no RAG, no embeddings, no reranking, no query-aware depth. Those are M2's
scope. M1 built the boundary they will be implemented behind.
