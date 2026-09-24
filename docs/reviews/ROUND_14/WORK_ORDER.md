# ROUND 14 — a claim wider than the code

**Issued by:** orchestrator, 2026-09-02
**Protocol:** `docs/AGENT_LOOP.md` §5.

Round 13 did real work: R-SEC-045, 046, 047 and 048 are closed, and so are all five round-12
LOWs — each verified twice, by the gating reviewers and again by the orchestrator attacking the
code directly. The `IdentityRegistry` survived every lifecycle attack two reviewers could build:
the table drains, it outlives its ledger, it is clean under eight threads, it fails closed across
a real subprocess. That part is sound and is **not** what this round is about.

Both reviewers, working independently and in different domains, named the same theme. R-SEC put
it as *"five of my six findings are the same shape — a claim wider than the code."* R-ARCH found
the same thing from the other side: **the round's exit condition was met and the property was
not.** Every finding below is a place where a docstring, a test, or an exit condition asserts
something broader than what the code actually enforces.

That is this round's subject. Not a mechanism — a habit.

## Part 1 — R-ARCH-032 (HIGH). The single authoritative record is mutable.

Round 13's insight was right: move the facts out of the certificate so a copy states *nothing*
rather than something false. The execution left the record itself writable.

```python
facts = envelope.disposition._certified
vars(facts)["withheld"]  = ()          # two plain writes
vars(facts)["hit_count"] = 1
envelope.model_copy(update={"withheld": (), "partial": False}).model_dump()
```

Orchestrator-reproduced: this publishes `"withheld": []`, `"partial": false` for a response that
dropped a message. `_CertifiedFacts` is `@dataclass(frozen=True)` **without slots**, so it keeps a
`__dict__`, and `frozen=True` guards only attribute assignment.

This is worse than R-SEC-046, and the reason is the design's own strength: there is now exactly
**one** record of what `certify` computed, so once it is rewritten every cross-check agrees, the
certificate's `__repr__` reports the lie as genuine, and no validator can tell. Concentrating the
truth in one place raises the cost of that place being writable.

R-ARCH verified the fix direction by execution, and so did the orchestrator: `object.__setattr__`
is **allowed** on a `frozen=True, slots=True` dataclass and **refused** on a `NamedTuple`. Do not
take that on our word — re-establish it yourself before relying on it.

And note what this says about exit conditions. Round 13's was *"no certificate `certify` never
minted is accepted"* — which is **true** of this attack, because this certificate **was** minted.
A provenance-shaped exit condition cannot see a mutability defect. Write yours so it could.

## Part 2 — R-ARCH-034 (HIGH). The chokepoint re-runs 17 of 41 validators.

The serializer re-runs every `mode="after"` validator **on the envelope**, and none of the 24 on
its nested models. `envelope.model_copy(update={"sources": ...})` — R-SEC-047's own reproduction
line, one field over — puts a message at position 900 of a two-message thread onto the wire,
violating amendment A3.

This is the **tenth** appearance of "one shape validated, peers trusted", and the third round
running in which it appears *inside the fix for the previous instance*. Read that sentence before
you write your fix, and design so that the eleventh is not yours.

## Part 3 — R-SEC-054 (HIGH) and R-ARCH-033 (HIGH). Sealing the object, trusting the reader.

R-SEC-054: `disposition.py` claims a duck-typed impostor "is refused by `Envelope`'s field type,
which is an `isinstance` check". A `__class__` property defeats `isinstance`; the envelope accepts
it and serialises `withheld: []` / `partial: false` **with no ledger in the process at all**. The
covering test plants a duck *without* `__class__`, so it passes without ever exercising the
property it exists to defend — the failure mode this project has hit more than any other.

R-ARCH-033: the certificate is sealed against subclassing; its only reader, `Envelope`, is not.
Three public routes each yield `partial: false, withheld: []`. Worse, discovery off `type(self)`
means a subclass method of the same name **replaces** the validator — so "discovered rather than
listed" is robust against forgetting and defenceless against overriding, which the docstring does
not say.

Treat these as one problem: **a sealed object read by an unsealed reader is not sealed.**

## Part 4 — R-SEC-055 (MEDIUM). The OD-4 walk has two writers and checks for one.

`isinstance(record, dict)` admits a subclass that hides `items()`. The walk reads it as empty and
passes; `json.dumps` writes `{}` — and then `render_summary` writes the body into `SUMMARY.md` by
`__getitem__`. The stated defence, "the checker and the writer agree", is true of *one* of the two
writers. Demonstrated on a non-prose key.

## Part 5 — the LOWs, and the claims behind them

R-SEC-056: `validation.py` says `hide_input_in_errors` "closes it for *every* renderer". It closes
`str()` only — `.errors()` and `.json()`, with no arguments, carry the input in full. Fix the
claim, and the code if it can be fixed.
R-SEC-057 (non-ASCII `proof` raises `TypeError`, not the documented single answer), R-SEC-058 (the
widening check tokenises on whitespace, so grouping punctuation and Unicode equivalence around the
same operator evade it), R-SEC-059 (`seed_address` is a caller parameter with no config binding
and no caller — and the whole of control 2 rests on it).
R-ARCH's MEDIUM: the capability sweep's population **excludes the reading site**, which is where
its own rule was discovered.

## The standing instruction for this round

Every module in your diff that claims something about what an attacker must do, or what a check
covers, gets that claim **executed**. If you cannot execute it, narrow the claim until you can.
Round 12's `pinning.py` enumerated "the only remaining routes" and was wrong; round 13's
`disposition.py` claimed an `isinstance` check that `__class__` defeats. Both times the code was
better than the sentence next to it, and both times the sentence is what a future reader would
have trusted.

R-SEC left one LOW deliberately open with a stated reason, and judged that the right call. It is.
**A claim you cannot establish, stated as unestablished, is a better artifact than a claim you
can only establish for the one shape you had in mind.**

## Explicitly NOT in this round

The retry/backoff curve — still the owner's decision.
Amendment A1's external content witness — still not in-process buildable, still not yours.

## Constraints

OD-1..OD-4 binding. I-1..I-4. A1..A7 binding. No personal mail text anywhere. Do not mark any
rubric criterion PASS; do not edit `FINDINGS_LEDGER.md` or `RUBRIC_TRANSITIONS.md`. 7 PASS / 106
NOT TESTED unchanged. All gates clean (ruff, format, mypy --strict, `python -m tools.guards`,
`pytest -q -m "not network"` — 1,847 tests currently).

Reintroduction checks: **assert every anchor matched before applying it**, and assert the file
actually changed. Round 12 produced three false greens this way and round 13's reviewer hit the
same failure independently.

## Gating reviewers

`R-ARCH` (Parts 1, 2, 3 — the envelope contract and I-1/I-2) and `R-SEC` (Parts 3, 4, 5).

## Exit condition

Stated as a property, not as provenance, because round 13's provenance-shaped condition was
satisfied by a broken build:

> No response reaches any serialisation route stating a disposition that differs from what the
> ledger it was retrieved with computed — **whatever** was done to the objects in between, and
> whether the certificate was minted or not.

Plus: every after-validator in the envelope tree is re-established at the chokepoint, not only the
envelope's own; and every claim in the diff about what a check covers has been executed.
