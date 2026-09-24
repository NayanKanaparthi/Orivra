# ROUND 01 — Work Order

**Issued by:** orchestrator, 2026-08-30
**Protocol:** `docs/AGENT_LOOP.md` §5
**Scope rule:** credential-free workstreams only. Gmail OAuth setup is with the owner and is not yet done, so nothing in this round may require live Gmail.

## Workstreams in scope

| WS | Name | What must exist at the end of this round |
|----|------|------------------------------------------|
| WS-00 | Repo scaffold and CI gates | Python 3.12+ project via `uv`, package layout, lint/type/test commands, CI config that runs them, and the CI guards the rubric requires (ground-truth isolation, trace-content audit, no-network-in-unit-tests) |
| WS-19 | Loop machinery | `FINDINGS_LEDGER.md` seeded, rubric status tooling that reads `RELEASE_RUBRIC.md` and reports criterion states, and a check that fails if any criterion is claimed PASS without a reviewer reference |
| WS-01 | Config and credentials | Two-client credential model (read-only server / full-scope seeder), secure token storage with correct file permissions, config loading and validation, two-host egress allowlist enforced in code. Everything except the interactive consent step |
| WS-03 | Response envelope and partiality | The envelope types, `retrieval_report` including the three-way `outcome` field, `not_tried[].why` closed vocabulary, per-message `role`/`reason`, `pool` block, and **`withheld := H − disclosed` computed as a set difference at envelope construction with an in-code assertion that fails loudly** |
| WS-07 | Content processing | MIME walk, HTML-to-text, quote stripping, signature handling, encoding and charset handling, producing `body_clean`. Parsers configured with network disabled |

## Binding constraints

- `docs/PRODUCT_CONTRACT.md` invariants I-1..I-4 and `docs/OWNER_DECISIONS.md` OD-1..OD-4 are binding. OD-2's `NOT_FOUND` / `INCONCLUSIVE` distinction must be structurally representable in WS-03's types, not merely documented.
- No personal email bodies in any log, trace or test fixture.
- No fabricated thresholds. Anything marked `[UNSET — register at G0]` stays unset and must not be given a default that silently becomes the bar.

## Target rubric criteria

Those mapped to WS-00, WS-19, WS-01, WS-03 and WS-07 in `docs/IMPLEMENTATION_PLAN.md`. The implementer proposes which reached acceptance; **only a reviewer may mark any criterion PASS** (`AGENT_LOOP.md` §6).

## Gating reviewers

`R-ARCH`, `R-DISC`, `R-SEC`, `R-RETR` (for the `H ⊆ R` assertion specifically).

## Exit condition

`AGENT_LOOP.md` §5 step 6: zero open BLOCKER, zero open HIGH, and every criterion this round targeted either reviewer-confirmed PASS or explicitly carried forward with a reason.
