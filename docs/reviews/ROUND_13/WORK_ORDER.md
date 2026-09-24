# ROUND 13 — the certificate class, closed at the operation rather than at the paths

**Issued by:** orchestrator, 2026-09-02
**Protocol:** `docs/AGENT_LOOP.md` §5. Round 12 closed five findings and opened four. Three of
the four are the same defect, and it is now in the server tree at the seal every invariant in
this project rests on.

## What round 12 established, so you do not redo it

Five round-11 findings are **closed**, each verified twice — by round 12's R-SEC and again by
the orchestrator attacking the code directly rather than reading the report:

* the preflight runner completes; all six probes run end to end and reach four *different*
  verdicts, so a double that answered everything alike would not have passed;
* no secret fragment reaches any error, `repr`, `args`, `__notes__`, or `__cause__` chain across
  152 forced failures — and the canary now discovers secret-bearing models by **reflection**, so a
  model that does not exist yet is already covered. That property is real; a planted model failed
  the canary immediately. **Do not weaken it.**
* the OD-4 record walk, the `errors[]` correction, and `MailboxScope` all hold.

Round 12's `validation.py` and `MailboxScope` are good work. This round is not a rewrite of it.

## The finding that reopens round 12 — Part 1, highest priority

**R-SEC-045 (HIGH).** `SeedSession`'s proof binds `id(credential)`. The module argues that id
cannot be recycled "because the session holds a reference to the object". **That argument is
false for the attacker's session**, and 3b itself is what broke it: `assert_bound_to` deliberately
stopped reading `self.credential` (so a legitimate `deepcopy` would still work), so nothing keeps
the *minting* credential alive once the honest session is dropped.

Forgery by ordinary public API — no private name, no `object.__setattr__`, no `copy`, no pickle:

1. read `address`, `scopes` and `proof` off a real session; they are public fields;
2. let the honest session go out of scope, so the minting credential is collected;
3. allocate attacker-controlled credentials until one lands on the freed address;
4. build with the **public constructor**. `assert_bound_to` authorises it.

Reproduced by R-SEC at 59/60 and 60/60, and independently by the orchestrator at **39/40**. The
authorised credential reports a *different* mailbox from the one the session names — which is
precisely the property SEC-03 exists to make impossible. It also reopens **R-SEC-040**, and
falsifies the module's third enumeration of "what remains possible".

Do not fix this by re-adding the identity comparison — that is what 3b removed, for a real reason
(a legitimately copied session must still work with its own client). And do not fix it by making
`proof` private; a leading underscore is not a security boundary and this project has said so
before. Bind to something that is **stable, non-recyclable and not a memory address** — what the
credential *is*, established from what was observed, rather than where it happens to live. Then
state what the new binding does and does not prove, and make sure the module's "what remains
possible" section is true of the code you leave behind, because it was not this time.

## Part 2 — the same shape at the disposition seal (R-SEC-046, R-SEC-047, both HIGH)

Pre-existing, not round 12's doing, and **inert today** — but this is the seal that
`withheld := H − disclosed` rests on, and both invariants I-1 and I-2 run through it.

```
forged = copy.copy(certificate)      # public
forged.hit_count = 1                 # a plain attribute assignment
forged.withheld  = ()                # another one
Envelope(..., certificate=forged)    # accepted
```

The envelope then states `withheld: []` and `partial: false` for a ledger that recorded a hit no
record accounts for. `DispositionCertificate` verifies its mint token in `__init__` **only**, and
`copy.copy` and `__reduce_ex__` never run it. One layer up, `envelope.model_copy(update=...)`
skips every validator including `_withheld_matches_the_certificate` and serialises straight to the
wire. Orchestrator reproduced both directly.

Close it the way round 12 closed 3b at its best: **verify at the point of use**, so that no
construction path matters and the property holds for reconstruction protocols Python has not
shipped yet. A certificate that has to be re-established against the ledger it claims to summarise
cannot be forged by writing attributes onto a copy.

## Part 3 — R-SEC-048 (MEDIUM): Part 5's exit condition is not actually met

`_is_our_prose` exempts a path whose first segment is a prose field and whose remaining segments
are **all integers** — so a *nested list* under `notes` (`notes[0][0]`, and deeper) is still exempt
at any depth. Round 12's exit condition said "any nesting depth under any key"; it is true for
dicts and false for nested lists. Fix the property, and re-state the exit condition to match what
the code actually guarantees.

## Part 4 — the LOW findings, where they are cheap and honest

R-SEC-049 (`__context__` retains the raw `ValidationError`), R-SEC-050 (the canary misses
`SecretBytes`, `SecretStr` subclasses, and non-module-level models), R-SEC-051 (two sweep holes in
the scope coupling, one of them the likeliest real mistake), R-SEC-052 (ambiguous HMAC material),
R-SEC-053 (the `PROSE_FIELDS` de-duplication test cannot detect a divergent copy in the checker).

Take these only where the fix is genuine. **A LOW you cannot close honestly, leave open and say
why** — that is a better outcome than a narrowed test.

## Part 5 — the sweep's scope, argued rather than assumed

Round 12 scoped its standing sweep to `pinning.py`, reasoning that a general sweep would flag
honestly constructor-only validators elsewhere and get switched off. R-SEC judged that an argument
against a rule nobody proposed: a sweep scoped to **capability tokens** — objects whose existence
authorises something — flags exactly two sites, and the second is `disposition.py`, i.e. Part 2.
Re-scope it that way, or make the case that capability tokens are not a decidable category here.

## Explicitly NOT in this round

The retry/backoff curve. Still an architecture decision, still going to the owner, still not a
constant to widen quietly.

## Constraints

OD-1..OD-4 binding. Invariants I-1..I-4. Amendments A1..A7 binding; A1 is not yours to build. No
personal mail text anywhere. Do not mark any rubric criterion PASS and do not add rows to
`RUBRIC_TRANSITIONS.md` or `FINDINGS_LEDGER.md` — the orchestrator does that. 7 PASS / 106 NOT
TESTED must be unchanged. All gates clean: ruff, ruff format, mypy --strict, `python -m
tools.guards`, `pytest -q -m "not network"`.

## On reintroduction checks, because round 12 got this wrong first

Round 12's first reintroduction run produced **three false greens**: `ruff format` had reflowed the
code after the patch anchors were written, so `str.replace` matched nothing and the defect was
never introduced at all. Round 12's R-SEC hit the identical failure independently. **Assert that
every anchor matched before applying it.** A reintroduction harness that silently reintroduces
nothing is the most dangerous artifact in this repository: it manufactures confidence.

## Gating reviewers

`R-SEC` (Parts 1, 3, 4) and `R-ARCH` (Part 2 — it is the disposition seal and the envelope
contract, not a security control, and it should be read by the domain that owns I-1).

## Exit condition

No session that `assert_bound_to` accepts can name an address whose profile was never observed,
by any route that does not require a private name. No `DispositionCertificate` that `certify`
never minted is accepted by an `Envelope`. The OD-4 walk holds for nested lists. Every claim each
module makes about what remains possible is true of the code as shipped.
