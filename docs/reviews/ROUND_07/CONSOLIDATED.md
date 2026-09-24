# ROUND 07 — Consolidated findings and gate decision

**Orchestrator, 2026-08-31.** Reviewers: R-ARCH, R-DISC.

## Gate decision: **ROUND 07 DOES NOT CLOSE.** One BLOCKER, the project's first.

## R-ARCH-022 — BLOCKER

Amendment A5 gated this round on **zero** false positives against sender-authored prose. The
implementer measured 0 of 36. R-ARCH wrote its own corpus and also measured 0 of 36, in two
positions, 72 of 72 sentences surviving.

Then R-ARCH asked why the harness only tested one position, and found the gate does not hold.

The underlying `email_reply_parser` library applies its own crude `QUOTE_HDR_REGEX`,
`HEADER_REGEX` and `SIG_REGEX` **before A5's protection ever runs**. A sentence matching one of
them — *"Once the negotiations concluded, the legal team wrote:"* — is marked `hidden` by the
library and deleted wholesale by MailWeave, with **zero A5 protection and zero ambiguity flag**.
It destroys that sentence and the unrelated sentence following it, silently.

A5 was applied at the wrong layer. It guards a decision the library has already made.

This is a BLOCKER rather than a HIGH because it is silent content destruction of the user's own
words, in the component the project's central claim depends on, with the protection that was
supposed to prevent it measurably not in the path.

## R-ARCH also corrected two reported numbers

**False negatives are 36.8%, not 12.5%.** R-ARCH's own 19-header corpus across Gmail, Outlook,
Apple Mail, Android, Yahoo, ProtonMail, mailing lists and bare `>` chains found 7 of 19 headers
surviving. The cause is a pronoun and weekday-abbreviation collision (`Mon` against French
`mon`, and peers) that the implementer's Tuesday-only corpus could never have exposed.

**The audit's "187 fields, programmatically enumerated" does not reproduce.** Running its own
published script gives 173; the remaining 14 were hand-added. They are accurate, but the claim
of full programmatic enumeration is not, and the value of that audit rests on its completeness.

## Closed, and closed well

**R-DISC-011** is closed on every route R-DISC attacked: collapsed runs, unthreaded ids, the
serialisation-time write, mixed-thread maps, and all four endpoint pairings. The check turned
out **broader than its docstring implies**, applying unconditionally rather than only to maps.
`MessageRow.thread_id` was removed outright rather than validated, which is the right shape.

Both instances the audit found that no reviewer had reported are real and closed.
`stated_total`'s lower bound composes correctly with A3 at the boundaries.

**Reintroduction counts matched exactly this round** — 10 of 10 verified by R-ARCH, all six
verified independently by R-DISC. After two rounds of small discrepancies, that is worth noting.

## The eighth instance, and what it means

R-DISC did build an eighth exploit: a `map_id` source reporting `partial=False` with a fabricated
message substituted for a real one. But it required **fabricating an observation**, and both
routes are the residue the implementer had already declared and already tests by name.

R-DISC could not make it work with only real, unfabricated ids. Every honest attack is closed.

That distinction is the round's real result. The recurring defect has two halves that look
identical and are not:

- a caller **misstating** a value the system already observed — closed by derivation, and now
  by A6;
- a caller **fabricating** an observation that never happened — **not closeable in-process at
  all**, only by A1's external witness.

## A6 decided: accepted as amended

Both reviewers converged. R-ARCH: amend, because only 2 of the 20 class-O fields are mail text
and the other 18 need small typed scalars, so a narrow named-fields widening closes the class
with no retention surface under OD-4. R-DISC: adopt, but it is not load-bearing, because the
surviving exploits bypass class O entirely.

Final form is in `ARCHITECTURE_AMENDMENTS.md`: sealed observations widen to **named scalar
fields**, explicitly not whole response bodies.

## The convergence

Three independent lines now point at one mechanism. A1 came from a reviewer proving in-process
guarantees impossible. A6 came from an implementer proving field-level derivation insufficient.
R-DISC's attack shows the only surviving exploits are exactly the ones A1 addresses.

**`PART-05` and `EV-01`'s upper half are blocked on the same single thing, and it is not more
validation code.** It is the external witness in WS-13 and WS-16.

That is a useful place to have arrived. The foundation has stopped producing new classes of
defect, and what remains needs the Gmail client and the harness to exist.

## Criteria

8 pass, unchanged. `PART-05` not promotable and now for a *structural* reason rather than a
defect, which is a different and better answer than the last three times it was blocked.
