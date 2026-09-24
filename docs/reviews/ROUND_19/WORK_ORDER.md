# ROUND 19 — read the kind, not the spelling

**Issued by:** orchestrator, 2026-09-04
**Protocol:** `docs/AGENT_LOOP.md` §5, gate per §5a. Authority: **OD-5**, mechanics: **A9**.

## What round 18 got right, and it is most of it

OD-5's schema change is in: `MessageRow` carries `MailboxProvenance` computed over observed
`labelIds`, with no place to state a disagreeing value. Requirement 4 is **met outright** —
negated phrases are exclusions, including with colons, unicode and mixed polarity. Evidence
preservation held over 2,200 randomised trials with 267 withheld records; recall over 1,200
trials missed no thread. The suite contains **zero** `f(x) == f(x)` self-comparing assertions,
and the implementer caught two vacuous tests it had written itself and repaired them with
written-out oracles. Sixteen replants, all caught by their named test *and* by the whole suite
with that test deselected.

Keep all of that. This round is one predicate and its consequences.

## Part 1 — R-RETR-035 (the central finding). The rule is right; the code asks how it is spelled.

A9-A2 requires the asymmetry be derived from **what an operator does**, so it holds for scope
operators nobody has added yet, and says in as many words that enumerating `in:` and `label:` by
name would be the next instance of the pattern.

`declares_the_search_region`'s docstring states the rule correctly and beautifully. Its
implementation is:

```python
return token.startswith(MAILBOX_LOCATION_PREFIX) and bool(matchable_content_of(fragment))
```

That is the spelling, not the behaviour. **`OperatorKind.LOCATION` already exists as declared
data in `query/operators.py` and this predicate does not read it.**

R-RETR proved the consequence the only way that counts: it registered a new `mailbox:` operator
*exactly as an implementer would*, with `OperatorKind.LOCATION`, and **2,274 tests stayed green**
while `-mailbox:spam snicker` was dropped from every decomposition unit, relaxed away at L2, and
widened out of at L3 with `includeSpamTrash=true`. The control — `PRIORITY`, a filtering operator
— *is* correctly covered, which shows the machinery works and the input to it is wrong.

Reachable today, not merely hypothetically: over 330 scoped queries and 1,516 probes, **60 still
enter an excluded region** — 0 for every documented `in:` spelling, 30 for grouped spellings, 20
for `label:`, 10 for fullwidth. End to end, `-(in:spam OR in:trash) snicker`, `(-in:spam) snicker`
and `-label:spam snicker` each send `in:anywhere snicker` with the flag set and return the SPAM
and TRASH rows as `role: matched`, `outcome: answered`.

**The fix is to read the declared kind.** An operator's registry entry already says what it does;
that is the "what an operator does" A9 asked for, and it makes a newly registered operator covered
the day it exists rather than the day someone remembers to add it to a prefix check.

Two residues the current docstring names honestly and which the fix must actually resolve rather
than re-name: `label:` can name a system mailbox or a user's own label, and grouped/fullwidth
spellings reach the predicate in a form the prefix check does not recognise. Decide each, state
the decision, and test it.

**The acceptance test is R-RETR's own method:** register a new scope-declaring operator and a new
filtering one, and confirm both are covered **without editing any test**. If your fix requires
editing a test to cover a newly registered operator, it is the enumeration again.

## Part 2 — R-RETR-036 and R-RETR-041. Provenance has holes the manifest did not name.

R-RETR planted eleven off-manifest behaviours and two were **missed by all 2,271 tests**:

* **stub rows lose provenance** — OD-5 says *every* `MessageRow`, and a stub is one;
* **`mailbox` becoming optional** leaves the suite green, so nothing defends the field's presence.

And `observed` has **no product producer**: a `threads.get` that omits `labelIds` yields
`outside_the_default_mailbox: false` over a TRASH message. A field that reports "not spam" for a
message whose labels were never seen is worse than no field, because a caller can branch on it.
Under OD-5 provenance is *derived from observed labels* — so an unobserved label set must be
representable as exactly that, and must not read as a negative.

## Part 3 — ROUTE-01, and why it is still not restorable

R-RETR: **729 of 822 zero-evidence responses (88.7%) carry no affordance**, and one of the four
offer kinds — `{"query":"in:anywhere","terms":[]}` — does not reach Gmail when executed. Round 18
made zero-evidence reports mint affordances and its test executes them; the test covers the 11.3%.

An affordance that does not execute is worse than an absent one: it is a promise of recoverability
the response cannot keep, and contract invariant I-4 is recoverability. Fix both halves. Do not
mark the criterion — only a reviewer may.

## Part 4 — the remaining findings

R-RETR-037..040, R-RETR-042 as filed. **R-RETR-030 stays open** — R-RETR verified the refusal is
right rather than an evasion (`threads` is built from the admission delta, and the required fix
fails exactly the two named tests), and it belongs to WS-16's content witness. It now has two live
reproductions, `label:` and `from:`; keep them attached to the finding.

## The standing instruction, sharpened

Round 18's predicate is this project's **other** recurring defect — *a claim wider than the code* —
and it appeared at the precise spot an amendment had warned about. So for this round: **every
predicate whose docstring describes a category must read the data that defines that category, not
a spelling that usually correlates with it.** Sweep your diff for that shape and report what you
found, including anywhere you decided a spelling check was genuinely right.

## Constraints

OD-1..OD-5; I-1..I-4; A1..A9 (A1 not yours to build). No LLM call, no embedding. No network in
tests. No real or realistic personal mail text. Do not touch retry/backoff — open owner decision.
Do not mark any rubric criterion PASS; do not restore ROUTE-01; do not edit `FINDINGS_LEDGER.md`
or `RUBRIC_TRANSITIONS.md`.

**Do not tune against any reviewer's probe set** (`/tmp/rretr15..18/`). Build your own; report your
own numbers.

Gates clean: ruff, ruff format, mypy --strict, `python -m tools.guards`,
`pytest -q -m "not network"` (2,271 currently pass). Rubric stays **6 PASS / 0 FAIL / 0 BLOCKER /
107 NOT TESTED**.

Reintroduction: assert every anchor matched, every file changed, and `mailweave.__file__` **and**
`tests.__file__` resolving into your scratch tree — copy the **whole** tree including `docs/`,
since round 18's own harness broke by excluding it and reported free passes.

## Gating reviewer

`R-RETR`, on what this round changes.

## Exit condition

A newly registered scope-declaring operator is covered without editing a test. No probe enters a
region the query excluded, under any spelling — grouped, negated, fullwidth, `label:`-named.
Every `MessageRow` including stubs carries provenance, an unobserved label set is representable as
unobserved and never reads as a negative, and no zero-evidence response offers an affordance that
does not execute.
