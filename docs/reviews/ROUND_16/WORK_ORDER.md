# ROUND 16 — the ladder finds what is there, or says it did not

**Issued by:** orchestrator, 2026-09-03
**Protocol:** `docs/AGENT_LOOP.md` §5, gate per §5a.

Round 15 built the ladder and it works: L1b's recovery is real, positions are flat across a
40-message thread, and the disposition ledger survived its first real consumer — 400 randomised
mailbox×query trials with zero violations of `H = disclosed ∪ withheld`, and issue #296 refused
in **three** planted shapes, including two the round did not anticipate.

R-RETR then found eleven things. **Every one is reachable** — a defect in code that runs, not an
attack on code that does not exist. That is §5a working as intended, and it is why this round
looks different from 12, 13 and 14.

## Part 1 — R-RETR-006 (BLOCKER). A parse failure becomes a whole-mailbox read.

`mailweave_search("(rollout OR escalation)")` — ordinary Gmail syntax — puts
**`q=in:anywhere`, `includeSpamTrash=true`** on the wire. Same for `("the and of")`, `("  ")`,
and a zero-hit `("newer_than:30d")`. Orchestrator-reproduced: the hit set fills with 60 ids
including **6 from spam**, twelve arbitrary threads come back as `role: matched`, and the response
states `outcome: answered`, `term_coverage: 1.0`.

Three separate failures in one line:

1. **Wrong.** Threads that match nothing are returned as matches.
2. **Reads mail nobody asked for.** Spam and trash are outside what a mailbox owner means by
   "my mail", and nothing in the query asked for them.
3. **It says it succeeded.** `answered` with full term coverage is the response actively
   misreporting itself — worse than the wrong rows, because a caller cannot tell.

`Probe.__post_init__` already refuses an empty `q` for exactly this reason. `BroadeningRung._anywhere`
walks around the refusal. **A rung that cannot narrow must not widen to everything** — a parse that
yielded no constraints is a parse failure, and the honest answer is a declared inability, not the
whole mailbox. Note `MailboxScope.WHOLE_MAILBOX` exists for probes that legitimately mean
"everything"; a retrieval rung is not one of them.

## Part 2 — R-RETR-007 and R-RETR-008 (both HIGH). The founding bug's commonest shape is unrecoverable.

These two are why the project exists, so treat them as the round's centre, not its tail.

**R-RETR-007.** D.3 rule 2's stop fires at L1 and switches L1b off, reporting it `not_applicable`
while its plan was non-empty. The split-evidence thread is never searched and the response says
`answered` / `sufficient`. The cause is precise: the fourth conjunct is coded as `not blocks_stop`,
which imports rule **1b**'s no-cue escape into rule **2** — and that is what makes it fire on
ordinary queries rather than the narrow case it was written for.

**R-RETR-008.** All residual terms are collapsed into a single `terms` constraint. So
`"rollout cutover"` — two words, spread across two messages of one thread — has k=1, L1b is
"not applicable", and the thread is never found. **That is the founding bug's commonest shape**,
and Round 15's L1b fixture only recovers it because its constraints happen to be an operator plus
a term. Two bare words is the case a user will actually type.

Fixing 008 means residual terms must be decomposable individually. Do not special-case two-word
queries; make the constraint model carry what L1b needs.

## Part 3 — R-RETR-009 (HIGH). Invented order presented as chronological.

When `threads.get` omits `internalDate` — PF-2's shape, which Gmail may well produce — the seal
correctly refuses to invent positions, and `assemble` invents them anyway, degenerating to
alphabetical-by-id and presenting it as chronological order. `scalars_absent_because` records the
absence and has no consumer.

A3 says positions are 0-based indices into **chronological** order. An order that is not
chronological, presented as though it were, is a false statement about evidence — the same class as
the omission this project exists to fix, one level down.

## Part 4 — R-RETR-010 (HIGH). A8's contradiction is real; its stated reason is not.

The contradiction reproduces — R-RETR drove both validators, at 9 and at 10. But amendment A8 says
the A.7a answer is "not expressible in the shipped schema", and **that is false on execution**:
`partial_source_failure` plus its affordance builds, validates and serialises today, provided the
disagreeing thread is not made a `Source`. Meanwhile the current behaviour denies the **entire
response** — five healthy threads lost because a sixth disagreed with itself.

So: fix the blast radius (one bad thread must not deny the other five), and **correct A8's text** —
the schema question stays deferred to WS-11 where it belongs, but a false reason for deferring is
exactly the "claim wider than the code" this project keeps producing. I wrote that sentence; correct
it plainly rather than softening it.

## Part 5 — the MEDIUMs and LOWs

R-RETR-011..016 as filed. Take them where the fix is genuine. **A finding you cannot close honestly,
leave open with the reason stated** — under §5a that is a correct outcome, not a gap.

## What R-RETR could not establish, and what that means for you

EV-02, EV-04, EV-06 and ROUTE-02 could not be established without a seeded corpus and live Gmail.
ROUTE-02 measured **8/12** on the reviewer's own mis-parse set with 0 false-not-founds. Do not try
to make those numbers by tuning against a reviewer's private probe set — that is benchmark
special-casing and WS-17 sweeps for it. They are WS-16's to measure.

## Constraints

OD-1..OD-4 binding; I-1..I-4; A1..A8 (A1 not yours to build; **A8's text is yours to correct**).
No LLM call, no embedding — `generative_llm_calls = 0` is CI-enforced. No network in tests. No real
or realistic personal mail text. Do not touch retry/backoff — owner decision. Do not mark any rubric
criterion PASS; do not edit `FINDINGS_LEDGER.md` or `RUBRIC_TRANSITIONS.md`.

Gates clean: ruff, ruff format, mypy --strict, `python -m tools.guards`, `pytest -q -m "not network"`
(2,180 currently pass).

Reintroduction checks: **assert every anchor matched before applying it**, and assert the file
actually changed. Note R-RETR's own warning — the venv's editable `.pth` resolves `mailweave` to the
real tree regardless of `cwd`, so a scratch copy silently tests the original unless `PYTHONPATH` is
set explicitly. Round 12 lost three checks to a quieter version of this.

## Gating reviewer

`R-RETR`, on what this round changes.

## Exit condition

No query causes a read outside what it asked for. No response reports `answered` for rows that
match nothing. Two bare words split across two messages of one thread are found. No order is
presented as chronological unless it is. One self-disagreeing thread does not deny a response.
