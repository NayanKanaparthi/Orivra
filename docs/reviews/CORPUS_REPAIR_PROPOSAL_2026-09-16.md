# Bounded corpus repair: what to fix, what "passed" means, and when to stop

**2026-09-16. A proposal, not a change.** Nothing in it has been implemented. It exists so the
scope, the bar and the exit are fixed *before* any generator work starts, because the failure
mode this repair has to avoid is not a missed defect - it is an unbounded loop in which each
round removes a regularity and the next read measures whatever regularity replaced it.

Mailbox status, for the record: the account holds **2,293 messages and 10 sentinel collisions**
as of the owner's read-only survey. No cleanup, deletion or reseed is authorised and none has
been done. **This repair is entirely offline.** Deployment is a separate plan, presented for
approval only once the gate below passes (§5).

---

## 1. The two kinds of defect, kept apart

The seven open findings are not one list. Five are things a generator put there and can take
away. Two are properties of generating the text at all, and the ledger already says so: *"a
generator that writes a decisive sentence differently from an ordinary one leaves a register
signal, and a generator that lays out a family the same way twice leaves a shape signal… each
of those [attacks] weakens the case the family is registered to make, and the next read will
measure whatever regularity replaces them."*

Treating the second kind as a bug to be driven to zero is what makes the loop unbounded. This
proposal repairs the first kind to a pass, holds the second kind to a **pre-registered ceiling**,
and publishes the residual as a baseline.

## 2. Determinate defects: repair to a rule

Each gets a `coverage.RULES` entry and a negative fixture, because `RULES_WITHOUT_NEGATIVES` is
empty and a rule nobody has shown can fail is what R-M2-045 was.

| finding | the concrete defect | the rule that closes it |
|---|---|---|
| **R-M2-067** | F11's trap does not fire in `t0031`: the BM25 construction query ranks the trap 5th behind four generic fillers. The family exists to show escalation does *not* trigger, so an instance with a weak lexical signal tests the opposite | `f11` already asserts "a trap that outranks its own evidence on a lexical query". Extend it to assert the trap outranks **every** message in its thread, not only its evidence, and hold it per instance |
| **R-M2-068** | Three families are determinate by a route other than the registered mechanism. F17's reversal is identifiable three ways without following a reply chain, and F17 is *"the only test of the non-negotiable E2 reply-chain floor"*. F16's near-duplicates differ in two details, one an explicit integer ordinal the key names verbatim - which is F1's mechanism, and it leaves `cut_loss` unable to separate a ranking failure from a retrieval failure. F13's reply-relationship requirement is not realised in the text | One rule per family asserting the **registered mechanism is necessary**: remove it and the answer is no longer uniquely determined. F17: the reversal is not identifiable without the chain. F16: exactly one value differs between near-duplicates. F13: the evidence's `replies_to` target is what disambiguates |
| **R-M2-071** | Twelve entity-free, digit-free scaffolding sentences occur inside exactly one family each. The role-level repair holds (zero complete-and-exclusive n-grams per `(family, role)`); it does not reach one level up | Lift the existing n-gram exclusivity check from `(family, role)` to `family`: no scaffolding sentence is exclusive to one family |
| **R-M2-072** | Positions are fixed within a family - F13's evidence at index 5 in both instances, F14's at 7, F7's figure half at 6, F8's cover at 8; F2 and F13 have a single role-position fingerprint across both instances. And `trap_decoy` is 11 of 11 after 13:00 against a base rate of 0.60 | A rule that every family draws its role positions from §4.4's grid across its instances, and that time-of-day is independent of role at the corpus level |
| **R-M2-073** | Ground truth disagrees with the text: F15's note cites a "90-message ceiling" where EP §3.8's is 100 and 90 is §4.4's thread length, with eight unsplit threads of 90-94; F2 and F8 attach `older_value` to chronologically newest messages; F7's sibling threads carry no distractor against §4.3's "every case has ≥1 distractor"; F12's `construction_query` is the evidence sentence verbatim | Four assertions in the existing per-family rules. These are corrections, not redesigns |

**Acceptance for §2: every rule above passes on a freshly generated corpus, each has a negative
fixture that fails without the repair, and `RULES_WITHOUT_NEGATIVES` stays empty.** Binary, and
re-runnable offline with no mailbox.

## 3. Statistical defects: hold to a ceiling, publish the residual

**R-M2-069 (register separation).** Two of 45 evidence messages carry a hedge, proposal, hearsay
or reminder cue; 43 of 75 distractors do. Odds ratio about 29. A query-free solver scores
**24 of 39** overall and **100% on F4, F5, F6, F11, F13, F15 and F17**, against a within-thread
random baseline of 7.5%.

**R-M2-070 (thread shape).** `(length, participants, senders, distinct hours)` maps to a single
family for **36 of 76** threads and covers all sixteen families - EP §2.4.5's Tier-1 redacted
observable.

The repair varies both: evidence sometimes written in hedged registers, unhedged assertions that
are wrong, layout drawn per instance rather than per family. **What it does not do is aim at
zero**, because each step in that direction weakens the case a family is registered to make.

**Pre-registered acceptance, and these numbers are the owner's to set before the work starts,
not after a result is in hand:**

| criterion | proposed bar | why this bar |
|---|---|---|
| **C1 - no family is given away by shape** | every `(length, participants, senders, distinct hours)` value maps to **≥ 2 families** | The tuple is the Tier-1 observable. Requiring it to be ambiguous everywhere is checkable and does not require any particular overall entropy |
| **C2 - no family is solved outright without the query** | qf-1 scores **< 100% on every family** | The seven wipeouts are the finding. A family a query-free solver always gets is a family measuring something other than retrieval |
| **C3 - the overall residual is bounded** | qf-1 scores **≤ 40%** overall (currently 61.5%) | A bound, deliberately well above the 7.5% random floor: the aim is a corpus a solver cannot walk, not one with no regularity |
| **C4 - the read passes** | the sixth independent content read returns **YES** | The gate has never been an internal judgement and is not becoming one |

**C3's number is a proposal.** If you want a different one, set it now and it becomes the
pre-registration; setting it after seeing a score is how a bar becomes a description.

## 4. The stopping condition

**At most two repair rounds.** Round one implements §2 and §3. The read runs. If C1 to C4 pass,
the gate closes and §5 begins. If any fails, round two addresses only the named failures.

**After round two the loop stops, whatever the result.** If C1 to C4 still do not all pass:

  * the corpus is **not** repaired further;
  * `qf-1` is published as a **baseline beside H1, H2 and H3** in every campaign report, with the
    residual stated per family;
  * M2's claims narrow accordingly: a hypothesis whose families the query-free baseline also
    solves is reported with that fact attached, and no retrieval claim is made over it;
  * and the comparison that is licensed is the **paired, case-level** one the ledger already
    specifies - which cases each arm answered, where they disagree, in which direction, per
    family, with the budget stated. **An aggregate margin establishes nothing about mechanism
    and is not to be reported as if it did.**

That is the exit. It does not depend on the corpus reaching a state nobody has shown is
reachable, and it produces a usable campaign either way.

## 5. What happens when the gate passes

A **separate mailbox deployment plan, presented for approval**. It is not written here and no
part of it is authorised by this document. It will have to cover, at least: what the 2,293
messages now in the account are to become; whether the new corpus goes to that account or
another; the write approval; the settle gate; `--live-check`; and a cleanup record whose ids are
checked against the insertion it claims to cover, which is the one thing the last cleanup did not
have (R-M2-117).

## 6. Out of scope, explicitly

A16 is closed and is not reopened. No product change is proposed here. No held-out acceptance
questions are authored - that is the independent author's, and a corpus repaired by the same
hands that write the exam is the failure this project's loop rule exists to prevent. No mailbox
contact of any kind.
