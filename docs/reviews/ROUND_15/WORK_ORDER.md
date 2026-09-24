# ROUND 15 — WS-04: query analysis and the lexical rungs

**Issued by:** orchestrator, 2026-09-03
**Protocol:** `docs/AGENT_LOOP.md` §5, under the **new §5a reachability gate**.

## Read this part first

Rounds 3–14 built and hardened the foundation: the Gmail client, the response envelope, the
disposition ledger, the content pipeline. That work is done and it is sound. It is also
**eleven review rounds on one module while retrieval had none**, and nineteen of the findings
those rounds produced were described by the reviewers who filed them as unreachable — inert
against code that does not exist yet.

`AGENT_LOOP.md` §5a is new and it changes what closes a round: **a finding blocks only if code
that exists today can trigger it.** Read §5a before you start, including the four things the
rule is *not*.

This round builds the thing all of that was for. **MailWeave cannot search a mailbox yet.**
After this round it can.

## What you are building

WS-04 from `docs/IMPLEMENTATION_PLAN.md`, whose row is normative. Two halves.

**Query analysis — `ParsedQuery`, model-free.** Provable Gmail operators separated from residual
free-text terms; participants address-normalised; interrogative class; answer-type lexicon;
confidence tier; `paraphrase_risk`. No LLM call, no embedding — this rung is deterministic, and
`generative_llm_calls = 0` is enforced by a CI guard that will fail you.

**The lexical ladder** — `AD §A.2`, `§A.6a`, `§A.8a`:
- **L0** exact-operator: the query's provable operators, sent as Gmail `q`.
- **L1** filtered: operators plus residual terms.
- **L1b** decomposition / intersection — the rung that recovers a constraint spread across
  *different messages of one thread*. This is the shape of the originating bug; it is the reason
  the project exists; it is not optional.
- **L2** one-at-a-time relaxation, `max_relax_probes = min(k, 6)`, every probe enumerable.
- **L3** broadening.

Plus `§A.6a` time and timezone policy including `window_utc` and the declared
`date_margin_days` widening; `exact_signal_match` per the **three enumerated branches** of
`§A.8a` (a closed definition — do not add a fourth); and `empty_diagnosis`' three states,
including `{"status":"incomplete"}`.

## What you must not break, and what you get for free

Every id you observe from **any** Gmail response enters the ledger's `H` (amendment A2), and
`withheld := H − disclosed` is computed as a set difference at envelope construction. You do not
maintain that. You **use** `DispositionLedger` and let it do the accounting — the whole point of
the last eleven rounds is that a rung cannot silently drop a message even by mistake.

The recurring defect of this project, found ten times, is *"one shape validated, peers trusted"* —
a guard or a parse written against the one case its author had in mind. Five rungs is five shapes.
Before you finish, name what is common to all five and test **that**, not each one separately.

The second recurring defect is *a claim wider than the code*. Every docstring you write asserting
what a rung covers, or what a parse guarantees, gets executed.

## Tests

No network. Use `httpx.MockTransport` behind the real client, as
`tests/test_preflight_runner_end_to_end.py` does — real URLs, real retry ladder, real egress
check. What that file does for the preflight runner, this round needs for the ladder.

Required by the plan's own acceptance column:
- an **operator-parse fidelity table** — every operator MailWeave claims to parse, parsed;
- **L1b recovers the cross-message-constraint case** (the originating bug's shape);
- **relaxation is enumerable** — every probe L2 would send is listable before it is sent;
- an `exact_signal_match` unit table, per branch;
- **issue #296 signature non-reproduction**: a thread whose match lies in an old message must
  not come back with that message missing and no marker. This is the bug MailWeave exists to
  fix; assert it directly.

Fixtures carry no real or realistic personal mail text.

## Rubric

WS-04 targets LEX-01..04, EV-02, EV-04..06, ROUTE-02..04. Do **not** mark any criterion PASS —
only a reviewer may, and the orchestrator records it. Leave the status table alone. Do not edit
`FINDINGS_LEDGER.md` or `RUBRIC_TRANSITIONS.md`.

## Constraints

OD-1..OD-4 binding; invariants I-1..I-4; amendments A1..A7 binding (A1 is not yours to build).
Do not touch the retry/backoff constants — owner decision. Gates clean when you finish: `ruff
check`, `ruff format --check`, `mypy --strict`, `python -m tools.guards`, `pytest -q -m "not
network"` (1,950 tests currently pass).

Reintroduction checks: **assert every anchor matched before applying it**, and assert the file
actually changed. Round 12 produced three false greens this way and round 13's reviewer hit the
same failure independently.

## Deliverable

`docs/reviews/ROUND_15/IMPLEMENTER.md`: what you built, what each test establishes, and what you
could **not** establish. Name explicitly:
- what is common to all five rungs, and the test that covers the commonality rather than the five
  instances;
- every claim your docstrings make about coverage, with the executed evidence for each;
- anything you found that is **not reachable today** — say so plainly and name the workstream that
  would make it reachable. Under §5a that is a correct and useful answer, not a gap.

## Gating reviewer

`R-RETR` — one reviewer, on new code. Under §5a a fix round reviews what it changed.

## Exit condition

MailWeave answers a query against a mailbox: the ladder runs, every id observed is accounted for
by the ledger, and the issue-#296 shape does not reproduce.
