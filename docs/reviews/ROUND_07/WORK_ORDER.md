# ROUND 07 — Work Order

**Issued by:** orchestrator, 2026-08-31
**Protocol:** `docs/AGENT_LOOP.md` §5. Round 6 did not gate: 2 HIGH.
**Input:** `docs/reviews/ROUND_06/CONSOLIDATED.md`, the three Round 6 reports, amendment A5.

## Part 1 — the class audit. Read this before writing any code.

R-DISC-011 is the **seventh** appearance of one defect shape:

> A value is accepted from the caller when the same value is already derivable from what was
> observed.

Seven instances so far: the hit set (`H` from recorded rather than fetched), thread maps
(`map_id` completeness), collapsed runs (id-level, then position-level), positions (unbounded
against `stated_total`), shape bounds (one concrete input spelling), withheld records
(`thread_id`), and now disclosed rows (`MessageRow.thread_id`).

Six were fixed one at a time. **Do not fix the seventh that way.**

Instead: **audit every model field in the envelope and ledger layers** and classify each as

- **derivable** — the same fact is already available from a sealed observation or from another
  field computed off one. These must be derived and the caller-supplied parameter removed, the
  way `note_withheld` lost its `thread_id` in Round 6.
- **genuinely caller-owned** — the caller is the only source of truth for it (a query string, a
  budget cap, a tool argument). These stay, and the audit records *why* the caller is the
  authority.

Produce the classification as a table in your handoff, covering every field, including the ones
you conclude are fine. A field you did not consider is the eighth instance waiting to happen.

Then fix every field in the first category, `MessageRow.thread_id` included. Property tests must
generate the caller-supplied and observed values independently so a lazy implementation cannot
pass by coincidence.

If the audit shows the class cannot be closed by field-level derivation alone, say so plainly
and describe what would close it. That is a more valuable result than a seventh patch.

## Part 2 — amendment A5, the quote stripper

Read A5 in `docs/ARCHITECTURE_AMENDMENTS.md`. It is binding and it changes the component's
default rather than tuning it.

Strip only on a **strong structural signal**: a recognised client's quote header format, a `>`
chain, a MIME boundary, an explicit forwarded-message separator. Prose that merely looks like an
attribution because of word order is left alone. Where unsure, keep the text and record a
`Reduction` of zero with a reason, so the ambiguity is visible rather than silently resolved.

| Acceptance | |
|---|---|
| False positives on sender-authored prose | **zero** against R-ARCH's fifteen realistic corporate sentences and any others you write. This is gated |
| False negatives | measured and reported, not gated, until real mail exists |
| R-ARCH-019 | Apple Mail "Begin forwarded message" separators no longer leak, and header fields are filed as `quoted` not `signature` |
| R-ARCH-020 | the duplicate `_ATTRIBUTION_VERBS` entry removed; the locale count in docs and tests matches reality |

Note the accepted cost: token efficiency gets worse and some headers survive. A5 explains why
that is the correct trade.

## Part 3 — Round 6 mediums

| ID | Defect |
|----|--------|
| **R-SEC-026** | Comprehensions and lambda parameters are not modeled as scopes; a comprehension variable named `os` shadowing the real import misresolves and false-positives on both guards |
| **R-SEC-027** | The generic `.open()` fallback flags any mode-word containing w, a, x or +; "readonly" is flagged as a write |
| **R-SEC-028** | LOW: the ground-truth isolation guard substring-matches, flagging "manifestly" and "harnessed" |

R-SEC-026 and R-SEC-027 are both **false positives**, which is the failure mode that gets guards
switched off. Treat them at the same weight as bypasses.

## Accuracy note

Two reviewers independently measured the Round 6 handoff's "7 tests break" claim as 8 and 9.
Minor, and disclosed in your favour rather than against it, but count by running rather than by
recalling.

## Standing rules

A guard may close a finding by catching the bypass or by honestly documenting that it does not,
never by implying coverage it lacks. Every fix needs a test that fails before and passes after,
verified by reintroducing the defect and counting the failures by running them.

## Constraints

OD-1..OD-4 binding. Invariants I-1..I-4. Amendments A1..A5 binding; **A1 is still not yours to
build**. No personal mail in fixtures or logs. No fabricated thresholds. Do not mark any rubric
criterion PASS and do not add rows to `RUBRIC_TRANSITIONS.md` or `FINDINGS_LEDGER.md`. No Gmail
retrieval logic, rungs, ranking or MCP surface. Eight criteria pass; do not regress them.

## Gating reviewers

`R-DISC` (Part 1, and whether the class is genuinely closed), `R-ARCH` (Part 2, attacking the
stripper in both directions, and test quality), `R-SEC` (Part 3 and a fresh false-positive sweep).

## Exit condition

Zero open BLOCKER and zero open HIGH. Part 1's audit table complete and every derivable field
either derived or justified. Zero false positives on sender-authored prose.
