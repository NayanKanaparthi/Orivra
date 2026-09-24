# ROUND 28 — a surface-efficiency checkpoint, not the thesis

**Issued by:** orchestrator, 2026-09-07
**Protocol:** `docs/AGENT_LOOP.md` §5, scope per **OD-7** and the owner's instructions of
2026-09-07 (this file restates them; where they conflict with anything older, they win).

## What this round is

Five bounded corrections to the surface the model sees and to one wasteful read, measured on
fixtures and then on a live rerun. It is **not** a test of MailWeave's progressive-disclosure
thesis, not WS-08, not WS-09, and its hours are not inside the remaining estimate until that
estimate is recalculated against `IMPLEMENTATION_PLAN.md`. Nothing here may be described as
query-aware, relevance-ranked, or as handling broad searches.

## The five

**1. Schema-consistent retries.** `surface/tools.py`'s `budget` schema gains
`max_hit_threads`. `surface/arguments.BUDGET_KEYS` is read from that schema - the derivation
its docstring already claims and does not perform - so the parser and the schema are one
list. Round 27's affordance test is widened: every budget key any affordance can mint is
validated against the published `inputSchema` with a JSON Schema validator, not only parsed.

**2. One recommended expansion call, both halves.** One entry in the existing
`affordances[]` list: `mailweave_get_messages` naming the **matched/evidence rows that lack
the requested body depth**, bounded by an existing published constant with the bound's
justification written beside it. Context and map stubs are never recommended. When no
matched body is missing, no recommendation is emitted. The text mirror renders this one
entry with its arguments. No new wire field; the cost is charged in the character estimate
and re-measured on the round 27 matrix. The other mirror lines stay as they are and stay
filed.

**3. The search description.** One new claim on `mailweave_search`, backed by a test like
every other claim: `mailweave_get_messages` is the direct, identity-preserving way to read a
message the response has already identified, and avoids another exploratory search. **Do not
claim a narrower search cannot recover such a message** - the owner's experiment shows it can.

**4. One `messages.get(format=full)` per named id.** `surface/service.py:416` fetches every
named id in full to learn its thread and discards the payload; `:442` fetches it in full
again. `_threads_of` hands what it fetched to `_bodies_for`. The test asserts, per call, at
most one full read per named id, and reports **every endpoint's count individually** -
profile, history, list, threads.get, messages.get - because watermark, liveness and map calls
are their own overhead and are not to be folded into one number.

**5. A measured deadline, in that order.** A read-only latency probe in the harness
preflights (PF-21): ten sequential calls each of `getProfile`, `messages.list`,
`threads.get(metadata)` and `messages.get(full)` against the test account, p50/p90/max per
endpoint, numbers only. **The probe runs first and its figures are shown to the owner before
`MAX_SERVER_MS` changes.** `MAX_HTTP_REQUESTS × slowest p90` is a *candidate upper-bound
formula*, not the default by itself; the proposed default is validated on neutral end-to-end
searches before it is adopted, and the constant then carries the derivation, the figures and
the date.

## Not in this round

Cross-call body cache. Thread ranking. Disclosure wire format. Body-selection order (N-1).
R-MCP-033. `sufficiency: ambiguous` on non-questions (filed). Argument rendering on the
other mirror lines (filed).

## Acceptance - measured, none targeted

* every affordance a served response carries, both halves, validates against the published
  schema and parses at the tool it names;
* a fixture search returning degraded evidence rows, followed by the recommended call copied
  from the **text mirror alone**, returns `body_clean` for those rows; the same once live;
* Gmail requests per response from `counters`, per endpoint, on the matrix and on the live set;
* per call, `messages.get(full)` per named id ≤ 1, on every tool, on the mock transport;
* `budget_caps_hit` per response on the live rerun with **default** budgets, reported as found;
* rendered characters per response on the nineteen shapes before and after, the recommended
  line's measured cost, estimate ≥ rendered everywhere;
* tool calls per question and tool names from the log and the owner's transcript on the live
  rerun, reported as counts.

## Review

**R-MCP** (surface, mirror, descriptions, schema) and **R-RETR** (reads per call, the probe,
the deadline derivation, anything that touched retrieval). Both independent, both against the
rubric with the §5a reachability gate. Findings recorded in the ledger **before** completion
is declared. Then the measurement report. Then stop for approval.

## Gates

ruff, ruff format, mypy --strict, `python -m tools.guards`, field census, full suite. Rubric
stays 6 / 0 / 0 / 107 unless a reviewer moves a criterion.
