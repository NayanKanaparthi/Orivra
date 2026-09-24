# ROUND 17 — refuse the unanswerable, answer the rest

**Issued by:** orchestrator, 2026-09-03
**Protocol:** `docs/AGENT_LOOP.md` §5, gate per §5a.

## Read this first: the shape of the last two rounds

Round 15 **answered too much** — a query the parser drew no constraints from was broadened to the
whole mailbox, spam and trash included, and reported `outcome: answered, term_coverage: 1.0`.

Round 16 fixed that, and **now refuses too much**. R-RETR: **17 of 50 plausible queries produce no
envelope at all.** One of them, R-RETR-018, is a straight regression — `"Re: quarterly plan"`
reached Gmail and worked before round 16.

Neither extreme is the product. The target is narrow and stated in the exit condition below:
*refuse only what genuinely cannot be searched, answer everything else, and never claim success for
rows that match nothing.* Round 16's own instinct was right — a parse failure must not become a
whole-mailbox read — and its implementation drew the line by the wrong test.

Round 16 did close seven findings, verified twice, and its decomposition fix holds at 2/3/4/5 bare
words. Keep all of that.

## Part 1 — R-RETR-017 (BLOCKER). The blocker's fix judged syntax, not selectivity.

`mailweave_search('""')` reproduces R-RETR-006 **exactly**: wire `('in:anywhere ""', True)`, six
spam and four trash messages disclosed as `role: matched`, `outcome: answered`,
`term_coverage: 1.0`. Same for `" "`, `subject:""`, and bare `subject:` / `label:` / `is:`.

`selects_something` asks whether the query *parsed*, not whether what it parsed can *select*
anything. An empty phrase is syntactically a phrase and semantically nothing. **The predicate must
be about what a fragment can select**, and it must hold for fragments nobody has enumerated —
including ones a future operator introduces. Round 16 already learned this lesson once inside its
own round; do not learn it a third time.

## Part 2 — R-RETR-018 (HIGH). A regression that costs 8 of 50 plausible queries.

`tokenise` partitions on `:` *before* the quoted-phrase branch, so `"Re: quarterly plan"`,
`"9:30 standup"`, `"note: see below"` and a quoted URL are all classified as unknown operators.
R-RETR-012's fix then drops them from the `q`, and R-RETR-006's fix refuses the whole query with
zero Gmail calls.

A colon inside quotes is not an operator separator. This is the most ordinary thing a user will
type — a reply subject — and it worked before this round.

## Part 3 — R-RETR-019 (HIGH). The twelfth instance, at the join of round 16's own two fixes.

`in:anywhere rollout cutover`, with the split thread in spam: every L1b probe drops the scope
operator and flips `includeSpamTrash` to false. `|H| = 0`. **The founding bug's shape, made
unrecoverable by the interaction of R-RETR-006's fix and R-RETR-008's.**

Round 16 found the eleventh instance of this pattern at this same join and fixed it. This is the
twelfth, at the same join. That is not bad luck — it says the join itself is under-specified.
Rather than fixing the third instance, **state what the invariant is** where decomposition meets
scope, and enforce it once.

## Part 4 — R-RETR-020 (HIGH). `enforced` is computed from one rung's drops.

`asked_for.enforced` subtracts only **L2's** drops, so `from:bob@… cutover` can return a spam
message from a different sender via L3 while reporting `enforced=('from','terms')`, `dropped=[]`,
`term_coverage 1.0`. A response stating it enforced a constraint it did not is the same class as
round 15's blocker: not the wrong rows, but the response lying about them.

`enforced` must be derived from what **every** executed rung actually enforced. If that is not
computable from what rungs currently record, make them record it — do not approximate.

## Part 5 — ROUTE-01 has been reverted to NOT TESTED, and you are why

Round 1 legitimately passed ROUTE-01 (*"a no-evidence outcome is a structured report, never an
empty set or a nonexistence claim"*). Round 16's raising broke it: 17 of 50 plausible queries now
produce no report at all, which fails the statement more completely than the bare empty response it
was written against. The orchestrator recorded the regression; only a reviewer can restore it.

**A query MailWeave cannot search should still get a structured report** — queries executed,
constraints dropped with reasons, what was not tried, affordances — rather than an exception,
wherever a report can honestly be made. Reserve raising for what genuinely cannot produce one, and
say in your report which is which and why.

## Part 6 — the MEDIUMs and the LOW

R-RETR-021 (a test asserting `in:spam` while every *narrowing* scope — `in:inbox`, `in:drafts`,
`label:inbox` — really does emit `in:anywhere in:inbox is:unread`; the 2,550-query sweep passed
because its assertions are about listings, not scope), R-RETR-023 (at k=1, `empty_diagnosis` reports
`incomplete` and ships a `max_probes: 1` affordance that is a no-op — buildable, and declined),
R-RETR-024 (the decomposition cap's precision cost, undeclared at response level: a Jan-2025 message
returned `matched` under `newer_than:7d`), R-RETR-025 (`ConstraintUnit.label` is not unique, so a
repeated fragment collapses the intersection).

Take these where the fix is genuine. **A finding you cannot close honestly, leave open with the
reason** — under §5a that is a correct outcome.

## Constraints

OD-1..OD-4; I-1..I-4; A1..A8 (A1 not yours to build). No LLM call, no embedding —
`generative_llm_calls = 0` is CI-enforced. No network in tests. No real or realistic personal mail
text. Do not touch retry/backoff — owner decision. Do not mark any rubric criterion PASS; do not
edit `FINDINGS_LEDGER.md` or `RUBRIC_TRANSITIONS.md`.

**Do not tune against either R-RETR instance's private probe sets.** Both built their own query
sets; fitting to them is benchmark special-casing, WS-17 sweeps for it, and it would be a serious
finding against you. Build your own adversarial sets and report the numbers you get on them.

Gates clean: ruff, ruff format, mypy --strict, `python -m tools.guards`,
`pytest -q -m "not network"` (2,235 currently pass). Rubric must read **6 PASS / 0 FAIL /
0 BLOCKER / 107 NOT TESTED** — ROUTE-01 was reverted this round; do not restore it.

Reintroduction: assert every anchor matched and every file changed, and assert `mailweave.__file__`
resolves into your scratch tree — the venv's editable `.pth` otherwise silently tests the real one.

## Gating reviewer

`R-RETR`, on what this round changes.

## Exit condition

A query that can be searched is searched. A query that cannot is refused **with a structured report**
wherever one can honestly be made, naming what was executed and what was dropped. No response claims
to have enforced a constraint it did not. No query reads outside what it asked for. And the founding
shape — terms split across messages of one thread — survives being combined with a scope operator.
