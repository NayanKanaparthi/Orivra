# ROUND 27 — three things, then real mail

**Issued by:** orchestrator, 2026-09-06
**Protocol:** `docs/AGENT_LOOP.md` §5, scope per **OD-7**. The smallest round in the project.

## Why this round exists

Round 26 fixed six of its eight targets fully and two for the shape Gmail sends. R-MCP then found
three things that block a live demonstration, **none of them among the eight**, and every one the
kind only a live-shaped review finds. The most important is the first: the message format every real
inbox is full of crashes the server, and it never fired in twenty-six rounds because the fixture never
produced one. That is the argument for OD-6's live milestone, made by the code.

## The three

**R-MCP-023 (HIGH). An ordinary `multipart/alternative` message makes `search` and `get_messages`
return `-32603 "this is a defect in this server"`.** `MessageRow._reductions_have_an_unabridged_path`
refuses any zero-size reduction with no exemption list; `Reduction._kind_specific_obligations` one
layer down exempts exactly those kinds. Unknown declared charsets (`ISO-8859-8-I`, `unicode`,
`UNKNOWN-8BIT`) and undecodable bodies do the same. Fix: one exemption, **read from
`Reduction._ZERO_REMOVAL_KINDS` rather than restated**, and a fixture that emits
`multipart/alternative` — plus one of each of the three charset shapes — so the unit tests exercise
what the inbox will.

**R-MCP-024 (HIGH). `layout_chars` is not an upper bound on `rendered_chars`.** Under by 12 to 1,513
characters on every multi-source response. The surface backstop catches it, so nothing over-cap is
served — but ordinary multi-thread searches (3 threads × 3 messages; 30 one-message threads)
**decline with no mail**. The certifying test's ten shapes were all one thread; source count was the
one dimension held constant and the one the estimate fails on. Fix: raise `SOURCE_STRUCTURAL_CHARS`
against a matrix that **varies source count**, and fix R-MCP-030 in the same edit so the next
constant is checked on the dimension this one was not.

**R-MCP-025 (HIGH). The way out of the decline is a call the server refuses.** The `retry_with`
handed back mints `budget: {max_hit_threads: 1}`, which `mailweave_search` rejects with `-32602
unknown budget key`. Contract I-2 proof-of-violation (c): an affordance that cannot execute. Fix:
accept `max_hit_threads` in `BUDGET_KEYS` (it is already a published `BudgetCapName` and a `Budget`
field), or mint a retry from arguments the tool accepts. And **a test that executes the minted
call** — no test in the suite does, which is why a published affordance and a published argument
list disagreed for a round.

## What this round does not do

Everything else. R-MCP-026..031 and the twelve from round 25: tracked. N-1: tracked, ruled silent
rather than false. No new workstream.

## Constraints

OD-1..OD-7; I-1..I-4; A1..A12. No Sampling, no LLM call, no embedding. No network in tests. No real
or realistic personal mail text. Do not touch retry/backoff. Do not mark any rubric criterion PASS;
do not restore ROUTE-01; do not edit `FINDINGS_LEDGER.md` or `RUBRIC_TRANSITIONS.md`. Do not tune
against any reviewer's probe set.

Gates clean: ruff, ruff format, mypy --strict, `python -m tools.guards`,
`pytest -q -m "not network"` (**2,737** currently pass). Rubric stays **6 PASS / 0 FAIL / 0 BLOCKER
/ 107 NOT TESTED**.

Reintroduction: every anchor matched, every file changed, all three packages resolving into your
scratch tree (whole tree incl. `docs/`), every `caught_by` citation catching individually.

## Deliverable

`docs/reviews/ROUND_27/IMPLEMENTER.md`: the three, each with the reproduction run before and after,
and the test that executes the minted call. "Have I trusted a peer?" Anything new, filed and left.

## Gating review

Orchestrator verification by execution, then the live demonstration. A formal review pass runs on
the demonstration itself, not on this round alone.

## Exit condition

A `multipart/alternative` message and three unusual charsets are served. A 30-thread search returns
mail. The affordance a decline hands back executes.
