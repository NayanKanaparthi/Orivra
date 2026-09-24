# ROUND 12 — Fix round, ahead of the owner's first live run

**Issued by:** orchestrator, 2026-09-01
**Protocol:** `docs/AGENT_LOOP.md` §5. Round 11 was not blocked by either reviewer, but three
items must land before the owner runs anything against real Gmail, and one is already blocking
them at the terminal.

**Context you need:** the owner is running OAuth consent right now. The preflight probes are the
next thing they will run, and one of these findings means those probes cannot work at all.

## Part 1 — the preflight runner is broken. Highest priority.

`mailweave-preflight --run` crashes on its **very first Gmail call, every time, regardless of
which probe is selected**, because a plain empty-string default violates a field constraint.
R-SEC found this while chasing something else.

Nothing about the live phase can begin until this works. Fix it, and then **run every probe
against the fake transport end to end** so that the next failure the owner sees is a real finding
about Gmail rather than a defect in our own runner.

## Part 2 — a real secret fragment reaches an error message

A credential file corrupted such that `refresh_token` fails Pydantic type validation puts a
**truncated but substantial fragment of the real secret** into `TokenStoreError`'s message,
reachable through the preflight runner.

The existing canary greps five failure modes for four secrets and did not catch this, so the
canary is incomplete as well as the code. Fix both: never let a validation failure quote the
value, and extend the canary to cover validation-error paths, not only the flows it currently
walks.

## Part 3 — `SeedSession` is weaker than its own docstring claims

The module says bypassing the account check requires "reaching for the private name". R-SEC built
a `SeedSession` **directly, for the owner's real mailbox address, with zero calls to
`getProfile` and no private name at all.** It also carries no binding to the client or token that
produced it, so a legitimately minted session can be paired with a different credential.

This is inert today because nothing destructive exists to reach — R-SEC was careful about that —
but it guards the credential that can permanently delete mail, and it must be correct **before**
WS-16 wires it to anything.

Make the session mintable only by the code that actually observed the profile, and bind it to the
credential that produced it. Then correct the docstring: a claim about what an attacker must do
is a claim, and this one was false.

## Part 4 — a documentation correction, no behaviour change

R-GMAIL settled the nine guessed shapes against the live discovery document (`gmail:v1`, rev
`20260727`). Two were resolved **in the code's favour**, and the handoff's claim that `errors[]`
is "the older spelling" is **backwards for Gmail specifically**. Correct that where it appears.

Four remain genuinely open and belong in the preflight list rather than being guessed again:
metadata `snippet`/`internalDate`, page-token length, duplicate history ids, and the `scope`
field. Make sure all four are recorded as preflight questions.

## Part 5 — an OD-4 backstop that only works for the shape it was written against

`assert_record_is_content_free` freezes the field-name it is tracking at the first dict
level, so any string nested under one of the seven "our prose" exempt top-level keys inherits
that exemption **at any depth**. R-SEC proved it both directions: mail body text under
`{"notes": {"raw_snippet": ...}}` passes; the same text under a non-exempt top-level key
correctly raises.

This is unreachable through the six probes shipped today - all of them emit flat strings under
those keys - but Part 1 requires every probe to run end to end, and probes are about to grow
structured notes. The module's own docstring says the property is "checkable by shape"; that is
false for any nested shape.

It is also the **same defect class as R-SEC-032** (round 9): a guard validated against the one
shape its author had in mind. Track the field-name chain at every level, or restrict the
exemption to string-typed values only - whichever makes the property hold for shapes nobody has
written yet. This was left out of the original issue of this work order by mistake; it is not
new scope.

## Explicitly NOT in this round

The retry and backoff curve. R-GMAIL found it sits far below Google's documented guidance — 250ms
base with a 1.5s total budget against Google's 1-2-4s progression — so a genuine rate limit will
essentially never clear and becomes a hard failure. **That is an architecture decision and it is
going to the owner**, not into a fix round. Do not widen the constants.

## Standing check

The "one shape validated, peers trusted" pattern now has an AST sweep guarding three shapes.
Confirm your changes do not introduce a fourth shape that the sweep does not cover, and say so.

## Constraints

OD-1..OD-4 binding. Invariants I-1..I-4. Amendments A1..A7 binding; A1 is not yours to build. No
personal mail in fixtures or logs. Do not mark any rubric criterion PASS and do not add rows to
`RUBRIC_TRANSITIONS.md` or `FINDINGS_LEDGER.md`. Seven criteria pass; do not regress them.

## Gating reviewers

`R-SEC` (Parts 2, 3 and 5 - you found all four, Part 3 guards a delete credential, and
Part 5 is an OD-4 backstop).

## Exit condition

Every probe runs end to end against the fake transport. No secret reaches any message on any
validation path. `SeedSession` cannot be minted without an observed profile and is bound to its
credential. `assert_record_is_content_free` rejects mail text at any nesting depth under any
key.
