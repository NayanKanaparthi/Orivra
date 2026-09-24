# ROUND 02 — Work Order (fix round)

**Issued by:** orchestrator, 2026-08-31
**Protocol:** `docs/AGENT_LOOP.md` §5. Round 1 did not gate: 6 HIGH open.
**Input:** `docs/reviews/ROUND_01/CONSOLIDATED.md` and the four reviewer reports beside it.

## The governing instruction

Three reviewers found the same defect at three layers: **a claim about what is represented,
computed separately from the enumeration of what actually exists, so the two can silently
diverge.** That is Gmail issue #296 reproduced inside MailWeave.

Round 1 solved this correctly in exactly one place — `withheld := H − disclosed`, derived by
set difference, which resisted every attack. Apply that same inversion at the remaining
sites. **Derive the claim from the enumeration; never assert it alongside.** Do not patch the
symptoms individually.

## Required fixes

| ID | Fix | Acceptance |
|----|-----|------------|
| **H1** | The transport owns ledger recording. Provide `list_messages(ledger, ...) -> ScanScopeEntry` (or equivalent) such that a caller *cannot* obtain a bare ID list. A future rung must be structurally unable to under-record `H` | A probe that fetches 100 IDs and records 10 must be impossible to write, not merely discouraged |
| **H2** | A `Source` claiming `map_id` must account for every message in the thread as a row, a collapsed run, or a withheld record. Derive completeness from enumeration | Constructing a map that omits a message with no accounting must raise |
| **H3** | The six AST guards: either harden materially against string concatenation, `importlib.import_module`, and `Path.open("w")`/`os.write`, or narrow each guard's documented claim to exactly what it catches. An overstated guard is worse than none | The R-SEC-001 demonstration file must either fail the guards, or the guards' docs must no longer claim to catch what it does |
| **H4** | Depth and size caps on HTML before parse. Any truncation is a declared `Reduction`. No silent content loss at extreme depth in either parser | The quadratic blowup case terminates in bounded time with a declared reduction |
| **H5** | Quote stripper: classify Outlook-style and forwarded blocks as `quoted`, not `signature`; handle signatures with no `--` delimiter | Test against the reply-chain corpus R-ARCH used; report measured before/after |
| **H6** | `mark_self_truncated()` must verify actual shrinkage against the ceiling rather than accept a claim | Shipping 27,000 tokens against a 9,000-token ceiling must raise |
| **M1** | Declared reduction *magnitude* must match actual shrinkage, not merely be non-zero | A stripper removing 220 chars while declaring 1 must fail a test |
| **M2** | `TokenStore.save()` atomic: write to a temp file with correct mode, then rename | Reproduce R-SEC-003's crash window and show it is closed |
| **M3** | Flag or strip unicode bidi-override characters in the content pipeline | Declared as a `Reduction` if stripped |

## Constraints

- Binding as always: `docs/OWNER_DECISIONS.md` OD-1..OD-4, contract invariants I-1..I-4, no
  personal email content in fixtures or logs, no fabricated thresholds, `[UNSET]` stays unset.
- Do not mark any rubric criterion PASS. Only reviewers do that.
- Stay in scope: this is a fix round. Do not start Gmail client retrieval logic, rungs,
  ranking or the MCP surface. H1 asks for the *seam* that WS-02 will use, not WS-02 itself.
- Every fix needs a test that fails before it and passes after. For H1, H2 and H6 the test
  must demonstrate the *impossibility*, not merely the happy path.

## Gating reviewers

`R-RETR` (H1, H2), `R-SEC` (H3, H4, M2, M3), `R-ARCH` (H5, M1, test quality of all fixes),
`R-DISC` (H2, H6).

## Exit condition

Zero open BLOCKER and zero open HIGH, with each fix verified by a reviewer who did not write
it, and no regression in the four criteria that passed in Round 1.
