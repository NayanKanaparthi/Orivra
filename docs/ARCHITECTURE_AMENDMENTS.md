# Architecture amendments

Append-only. Each amendment is a change to `ARCHITECTURE_DECISION.md` forced by a measured
finding, recorded here rather than by silently editing the architecture, so the reason
survives. Per `SCOPE_CORRECTION.md`, amendments are for cases that are *genuinely necessary*,
not for tidying.

---

## A1 · The counting proxy must be a content witness, not a count cross-check

**Round 3. Forced by:** R-RETR's verification of H1b (`docs/reviews/ROUND_03/R-RETR.md`).

**Finding.** Completeness of the hit set `H` cannot be guaranteed in-process. `FetchedIds` is
an ordinary constructor, and even a capability token is defeated by subclassing and overriding
`_release`. A verifier running in the same interpreter as the code it checks is not a boundary.
This is a property of the situation, not a bug.

**What changes.** WS-13's counting proxy was specified as a cross-check on `http_requests`.
That is necessary but not sufficient. It must become a **content witness**: for every observed
Gmail call it records the exact set of message ids in the response, and the harness asserts

```
H ⊆ observed_ids
```

Counting calls proves the server did not make secret requests. Only recording their contents
proves the server did not invent ids it never received, which is the failure this project
exists to prevent.

**Consequence for EV-01.** The criterion splits, and both halves must be stated separately
rather than blurred:

- **Bounded below** (every id the ledger knows is accounted for): provable in-process, and
  the Round 1 to 3 machinery does it.
- **Bounded above** (the ledger knows every id Gmail returned): **cannot pass in-process**.
  It passes only under the content witness, and any claim of evidence preservation that does
  not say which half it means is overclaiming.

**Also affects.** WS-16, which hosts the proxy. `RELEASE_RUBRIC.md` EV-01 needs its acceptance
split accordingly, at the same time the proxy is built, not before.

---

## A2 · An id enters `H` through any observed Gmail response, not only `messages.list`

**Round 3. Forced by:** R-RETR-004.

**Finding.** Round 3 sealed `H` so that ids may only enter through a sealed page from
`messages.list` or `history.list`. But `ARCHITECTURE_DECISION.md` §D.5 builds the semantic
candidate pool thread-wise, and its **first-choice** source arrives via `threads.get`. When
WS-08 lands, a legitimate top-k selection from that pool would be rejected by the seal.

**Root cause.** The narrowing encoded an implementation detail as if it were the principle.
The principle is *an id may only enter `H` by being observed in a real Gmail response.*
`threads.get` is a real Gmail response. Restricting to two endpoints was an accident of which
rungs existed when the seal was written.

**What changes.** The sealed-page concept generalises to a sealed *observation*, carrying which
endpoint produced it. `threads.get` responses become a first-class `H` clause (`H-thr`)
alongside `H-lex` and `H-hist`. The single-writer property is preserved: still exactly one
writer of `_origins`, still admitting only sealed observations, still no path that accepts a
bare id list.

**Explicitly not changed.** The seal is not loosened to accept unsourced ids. Adding a
legitimate observed source is the opposite of weakening it, and A1 still applies: none of this
is a guarantee until the content witness exists.

**Deadline.** Must land before WS-08 starts, or the semantic rung will be built against a
contract that rejects its own inputs.

---

## A3 · Positions are 0-based and bounded by `stated_total`

**Round 4. Forced by:** R-RETR-005 and R-ARCH-013, the same defect found independently by two
reviewers and escalated to the orchestrator under `AGENT_LOOP.md` §8 because it needed a
convention decision rather than a mechanical fix.

**Finding.** `CollapsedRun.positions` has no lower bound, and neither it nor
`MessageRow.position` is bounded against `stated_total`. Executed proof: a `map_id`-bearing
source with `stated_total=5` and a run at `positions=(900, 904)` builds cleanly and presents
itself as a complete map. Round 4 made occupancy exclusive, so no two things claim one slot,
but nothing requires the slots to be inside the thread.

**Decision.** A position is a **0-based index into the thread's chronological message order**.
Every position `p` in a row or a collapsed run must satisfy:

```
0 <= p < stated_total
```

**Why this convention.** 0-based matches the language the code is written in and the API's own
list ordering, so no translation layer is needed at the boundary where mistakes happen.
Chronological order is the only ordering Gmail actually guarantees across a thread. And
binding the range to `stated_total` rather than to a separately declared length means the
completeness claim and the position claim are checked against the *same* number, which is the
`derive the claim from the enumeration` rule applied once more.

**What changes.** The bound is enforced where occupancy is already computed, so a source
claiming a complete map cannot place any part of it outside the thread it claims to describe.
Out-of-range positions raise rather than being clamped, because clamping would silently move
evidence, which is the failure class this project exists to prevent.

**Consequence.** `PART-05` cannot pass until this lands. R-RETR was right to leave it
`NOT YET PASS`.

---

## A4 · `included` counts every message present at any depth, stubs included

**Round 5. Forced by:** R-ARCH-008 and R-DISC-007, filed in Round 1 as needing an orchestrator
ruling. None was made for four rounds. This closes it.

**The divergence.** For a thread of 42 messages disclosed as 7 bodies plus 35 stubs:

- `PRODUCT_CONTRACT.md` R-05 treats `included_as_stub` as a **subset** of `included`, giving
  `included = 42`.
- `ARCHITECTURE_DECISION.md` §D.2's worked example treats them as **disjoint**, giving
  `included = 7` and `included_as_stub = 35`.

The code follows R-05.

**Ruling: R-05 is correct. §D.2's worked example is wrong and changes.**

**Why.** The project has already settled this question elsewhere and the disjoint reading
contradicts it. The disposition ledger raises an error when a withheld record is filed for a
message that is present as a stub, with the reason stated in its own source: *depth reduction
is not omission; a stub row is disclosed, so a withheld record for it is false.* A stub is
disclosure at low depth, not absence.

If `included` excluded stubs, then a complete map of a 42-message thread would report
`included = 7` against `stated_total = 42`, and an agent reading that would reasonably conclude
35 messages were missing when every one of them is present and addressable. That is a partial
view misrepresenting itself, which is the failure this project exists to prevent, produced by
the project's own arithmetic.

Under the subset reading, `included == stated_total` is exactly the statement "every message in
this thread is present in this response at some depth", which is the map-carrier guarantee
stated as a number. `included_as_stub` then answers the different and also useful question of
how much of it is shallow.

**What changes.** `ARCHITECTURE_DECISION.md` §D.2's worked example only. No code changes; the
implementation was already right. The Round 5 test that pinned the shipped reading stays, and
its docstring is updated to record that the ruling now exists rather than that it is owed.

**Note for the record.** This sat unresolved for four rounds because nothing tracked
escalations. It surfaced now because the findings ledger was finally populated, which is the
second thing that ledger caught in two rounds.

---

## A5 · The quote stripper biases toward under-stripping

**Round 6. Forced by:** R-ARCH-015, twice. Round 5's fix was verified and Round 6 found it still
deletes sender-authored prose: 6 of 15 realistic corporate sentences wrongly stripped, a 40%
false-positive rate on the class it was supposed to have fixed.

**The failing approach.** Detect attribution lines by locale word-order heuristics ("evidence
must precede the verb, subject not first-person"). Round 6 defeated it with an adverb between
the pronoun and the verb, and found first-person-plural pronouns absent from the pattern
entirely. Each iteration produces a narrower heuristic and a new escape.

**The asymmetry that settles it.** The two failure modes do not cost the same thing:

- **Under-stripping** leaves an attribution line in `body_clean`. Cost: a few tokens, and a
  slightly noisier body.
- **Over-stripping** deletes a sentence the sender actually wrote. Cost: evidence destroyed
  silently, which is the exact failure this entire project exists to prevent, committed by our
  own code on the user's own words.

A 40% false-positive rate on realistic prose is not a tuning problem. It is the wrong default.

**Decision.** Strip only on a **strong structural signal**: a recognised client's quote header
format, a `>` chain, a MIME boundary, or an explicit forwarded-message separator. Prose that
merely *looks* like an attribution because of word order is left alone.

Where the stripper is unsure, it keeps the text and records a `Reduction` of zero with a reason,
so the ambiguity is visible rather than resolved silently in either direction.

**Consequence, stated honestly.** Token efficiency gets worse. Some quote headers will survive
into `body_clean`. That is the correct trade: the project's central claim is that it does not
silently lose content, and a stripper that deletes 40% of a realistic sentence class makes that
claim false in the most embarrassing possible way.

**Measurement.** The false-positive rate on sender-authored prose is the primary metric for this
component and must be **zero** on the reviewer corpora. The false-negative rate (headers that
survive) is secondary and reported, not gated, until real mail exists to measure it against.

---

## A6 · ACCEPTED AS AMENDED — sealed observations widen to named fields, not whole responses

**Round 7. Status: ACCEPTED AS AMENDED after review, binding.** Originally proposed as whole-response sealing. Raised by the Round 7 implementer's field audit.
Reviewers assess it this round; the orchestrator decides after. It is recorded as a proposal
rather than a decision because accepting an architectural claim on the implementer's word is
the exact failure this project keeps catching.

**The finding.** Round 7 audited all 187 model fields in the envelope and ledger layers, asking
of each whether it is derivable from an observation or genuinely caller-owned. The binary the
work order asked for was insufficient: the real split was 52 derivable, 103 caller-owned, and
**20 "observed but unsealed"** — plus 7 seal parameters and 5 ledger-internal.

That third class is the answer to why this defect keeps recurring.

**Why field-level derivation cannot close the class.** Three reasons, all specific:

1. `FetchedIds` records a **subset** of what a Gmail response actually said. `stated_total`,
   `position`, `internal_date`, `history_id` and `fetched_at` have no observed value to derive
   *from*, so "derive it" degenerates into checking one caller assertion against another.
2. The seal is itself a caller assertion (A1's residue), so derivation moves the lie rather
   than removing it.
3. Where a value *is* derivable, both available mechanisms cost something already paid for: a
   `computed_field` serialises last and would push `partial` back behind `sources`, undoing
   R-DISC-003; and a `mode="before"` validator must read unnormalised input in every spelling,
   reopening R-SEC-021.

**The proposal.** A sealed observation records the **complete Gmail response**, not a selected
projection of it. Every field in the "observed but unsealed" class then has an observed value to
derive from, and the eighth instance of this defect has nowhere to live.

**Why this is worth doing rather than patching.** It converges with A1. The content witness A1
requires must record exactly what each Gmail call returned; sealing the whole response is the
same data, captured at the same boundary, for the same reason. Two amendments that arrived from
opposite directions — one from a reviewer proving in-process guarantees impossible, one from an
implementer proving field-level derivation insufficient — want the identical mechanism.

**Costs to weigh, honestly.** Memory footprint per observation grows. The redaction rules in
OD-4 and Appendix A.3 apply to anything retained, so a whole-response seal must not become a
place where message bodies quietly persist. And a larger sealed object is a larger surface for
the same class of defect if any part of it is caller-supplied.

**For reviewers.** Is the three-reason argument sound? Is whole-response sealing the right
mechanism, or is there a cheaper one that closes the class? Does it create a retention problem
under OD-4? Say so plainly; a proposal rejected with reasons is a good outcome.

### A6 — review outcome and final form

Both reviewers assessed the proposal independently and reached compatible conclusions, which
is the strongest signal this project has produced.

**R-ARCH: amend, do not accept as written.** The diagnosis is sound — class O ("observed but
unsealed") is real, and the classification spot-checks correct across all five classes. But
whole-response sealing is overbroad: **only 2 of the 20 class-O fields are actual mail text.**
The other 18 need small typed scalars. A narrow, named-fields widening closes the class without
creating any retention surface under OD-4 and Appendix A.3.

**R-DISC: adopt, but it is not the load-bearing piece.** A6 closes honestly-scoped fields that
have nothing to derive from. But R-DISC's two successful exploits **bypass class O entirely**:
they *fabricate* rather than *misstate*. A6 cannot close fabrication. Only A1's external witness
can.

**Final form, binding.** Sealed observations widen to carry the **named scalar fields** the
class-O audit identified — `stated_total`, `position`, `internal_date`, `history_id`,
`fetched_at` and their peers — and **not** whole response bodies. Mail text is explicitly
excluded from what a seal retains, so nothing here becomes a place bodies quietly persist.

**What A6 does and does not buy, stated plainly so no one overclaims later.** It removes the
class of defect where a caller *misstates* a value the system already observed. It does nothing
about a caller *fabricating* an observation that never happened. Those are different failures
and only the second one is architecturally interesting, because it is the one that cannot be
closed in-process at all.

**The convergence worth recording.** Three independent lines of work now point at the same
mechanism. A1 came from a reviewer proving in-process guarantees impossible. A6 came from an
implementer proving field-level derivation insufficient. And R-DISC's Round 7 attack shows the
only surviving exploits are exactly the ones A1 addresses. `PART-05` and `EV-01`'s upper half
are blocked on the same single thing, and it is not more validation code. It is the external
witness in WS-13 and WS-16.

---

## A7 · The content pipeline annotates; it does not delete

**Round 8. Forced by:** four consecutive rounds of the same failure, and R-ARCH-025 / R-ARCH-026.

**The record.** Round 5 fixed the quote stripper. Round 6 defeated the fix with an adverb.
Round 7 fixed it again under amendment A5, and found the protection sat above a library that had
already decided. Round 8 removed the library, owned the detection, measured **0 false positives
across 200 sentences in three corpora** — and a reviewer's **fourth** corpus immediately found
**14 of 54 destroyed, 25.9%**, worse than the rate A5 was written to fix. The same reviewer
measured the latch at **1,251 of 1,251 tagged sender characters destroyed** across sixteen cases.

Four rounds, four fixes, four new destruction shapes. Every fix was real and every measurement
was honest. The approach is what keeps failing.

**Why it cannot converge.** Deciding whether a line is quoted material or the sender's own prose
is genuinely ambiguous. `"To: recap, we need three approvals"` is a sentence. It is also a header
field followed by text. No rule separates those without a corpus containing that shape, and no
corpus contains every shape. Each round buys the shapes we thought of.

The deeper problem is the operation, not the rule. **Deletion is irreversible**, so every
ambiguous case is a coin flip where one face destroys the user's words permanently.

**Decision. `body_clean` stops being a smaller copy of the body, and becomes the full text with
classified spans.**

- The pipeline **annotates** spans as `quoted`, `signature`, `forwarded` or `original`, with the
  signal that classified each.
- **No text is removed.** A span the pipeline is unsure about is annotated `uncertain` and is
  still present.
- The disclosure layer decides what to *show*, per its existing budgets and depth vocabulary.
  Showing only `original` spans is the default view and reproduces today's token economics.
- Because nothing was deleted, any view is reversible: `view(list(SpanClass))` returns the full
  text exactly. That is the guarantee, and it is **not** "one class wider" — all fourteen of
  round 8's misclassified entries are still incomplete one class wider (R-ARCH-029). What makes
  this amendment downgrade content loss from a blocker is containment, not any particular
  widening step.

**Status, round 10: the annotation half is built and the disclosure half is not** (R-DISC-016).
`content/` annotates; nothing in `envelope/` references `AnnotatedBody`, `SpanClass` or
`default_view` yet, because the disclosure layer is WS-11 and WS-11 has not started. The three
conditions the round-9 review attached to that wiring — a **structured** `latched` signal rather
than prose, **floor-message-specific** widening rather than a global default, and `SpanClass`
staying inside one `Depth` step rather than becoming a second navigation axis — are recorded in
`docs/IMPLEMENTATION_PLAN.md` §1 under "Conditions carried into WS-11".

**What this buys.** Content destruction becomes **structurally impossible** rather than
defended against. It is the same move that has worked every other time in this project: make the
bad state unrepresentable instead of guarding the path to it. `withheld := H − disclosed` did it
for evidence. Deriving thread ids did it for provenance. This does it for text.

It also makes the classifier's remaining errors **cheap**. A misclassified span shows the wrong
default view and the text is still there. Today the same error is permanent.

**Costs, stated honestly.** The envelope carries more text before disclosure trims it, so the
pipeline's internal footprint grows. Some plumbing changes: `body_clean`'s consumers now ask for
a view rather than a string. And the classifier's accuracy still matters for default-view
quality — this removes the catastrophic failure mode, not the need to classify well.

**Measurement changes with it.** "False positives on sender prose" stops being a gate, because
the failure it gated cannot occur. It becomes a **default-view quality metric**, reported and
tracked. The new gate is simpler and total: **no input text is absent from the annotated
output.** That is one property, mechanically checkable, and it cannot be defeated by a corpus
nobody thought of.

---

## A8 — NAMED OPEN CONTRADICTION, not yet a decision (round 15; **corrected round 16**)

**Status: OPEN**, and narrower than this amendment first stated. Unlike A1–A7 it decides nothing. It
records a contradiction found by execution, fixes the reproduction in place, and schedules the
decision. It is written down because an unrecorded contradiction is the thing this project has lost
most often.

**Correction, round 16, forced by R-RETR-010.** As first written, this amendment carried a paragraph
headed *"Why the asked-for answer cannot be built in the shipped schema"*, whose sentence *"not
expressible in the shipped schema — arithmetic rather than effort"* said the A.7a disposition — a
`partial_source_failure` withheld record with a `mailweave_get_messages` affordance — could not be
built. That is false, and R-RETR disproved it by execution with no Gmail dependency: the envelope
builds, validates and serialises today, provided the disagreeing thread is not made a `Source`. It is
now built, and `test_a_thread_map_that_omits_one_of_its_own_hits_is_withheld_rather_than_shipped`
executes it.

That paragraph is replaced below by *"The arithmetic, which bounds `Source.stated_total` and nothing
wider"*: the arithmetic in it was correct and is retained verbatim, under a heading that says what it
actually bounds. It bounds something smaller than the sentence it was used to justify: what has no
solution is **`Source.stated_total`** for the disagreeing thread, not the disposition. A `NotIncludedSource` states no total (`stated_total: null`)
and MailWeave says why in `why`, which is a claim it can make honestly.

**Two things were wrong as a consequence, and both are fixed rather than reasoned around.**

1. *"The bug cannot be shipped. That is safe."* — safe about that thread and unsafe about every other
   query the mailbox can answer. The refusal denied the **entire response**: five threads retrieved
   correctly were lost because a sixth disagreed with itself
   (`test_one_self_disagreeing_thread_does_not_deny_the_other_five`). A source that cannot describe
   itself is now one thread's disposition.
2. The claim itself was **wider than the code**, which is the defect class this project keeps
   producing and which this document exists to record rather than repeat. It was written in the
   orchestrator's own text, in the round that named the defect class.

**What stays deferred, and it is the part that was always a contract question.** A schema that can
say *complete as the thread enumeration reported, incomplete against what was retrieved* — two
completeness claims about one source — remains a change to PART-03 and R-08, and remains **WS-11's**,
with **PF-1** as its input. Nothing below about that is withdrawn. What is withdrawn is the reason
given for not building anything in the meantime.

**The shape.** Gmail's `threads.get` returns a thread that omits a message its *own* `messages.list`
returned for the same query — Gmail disagreeing with itself, one endpoint against the other. This is
the originating bug's cause rather than its symptom.

**What MailWeave did in round 15, and what it does now.** It refused to answer at all: `assemble`
raised `DispositionInvariantError` naming the id, the thread and the shape. Since round 16 it does
what §A.7a asks — the thread is **not** made a `Source`, every id observed in it becomes a
`partial_source_failure` withheld record carrying a `mailweave_get_messages` affordance, and the
disagreement is named in a `not_included_sources` entry. The rest of the response is unaffected.

**The arithmetic, which bounds `Source.stated_total` and nothing wider.** For a thread whose
`threads.get` states nine messages while `messages.list` placed a tenth id in it, `Envelope` requires
`Source.stated_total` to be simultaneously:

* **exactly** what the `threads.get` observation stated (amendment **A6**,
  `_stated_total_is_the_one_the_observation_stated`) — 9; and
* **at least** the distinct ids the ledger observed in that thread
  (`_stated_total_is_not_below_what_was_observed_in_the_thread`) — 10.

No value satisfies both, so no `Source` for that thread is constructible — **and that is the whole of
what is inexpressible.** Independently, **PART-03**'s phantom-remainder rule refuses a withheld record
charged to a *source* that reports itself complete, which this one would do on its own enumeration's
terms — so the thread must not be a source, which is exactly what the disposition above does rather
than a further obstacle to it. Both verified by execution, not by reading.

**What a resolution requires.** A schema that can say *complete as the thread enumeration reported,
incomplete against what was retrieved* — two different completeness claims about one source, which
the current model collapses into one number. That is a contract change to PART-03 and R-08.

**Why it is not decided now.** It rests on a measurement nobody has taken: **PF-1** says whether real
Gmail produces this shape at all, and PF-1 needs live credentials. Deciding a schema change against a
shape that may not exist would be specification expansion of exactly the kind the owner prohibited.
Under `AGENT_LOOP.md` §5a this is deferred to **WS-11**, blocking in that round, and PF-1's result
is its input.

**Reproduction, kept green:** `test_a_thread_map_that_omits_one_of_its_own_hits_is_withheld_rather_than_shipped`,
and `test_one_self_disagreeing_thread_does_not_deny_the_other_five` for the blast radius.

**A second shape reaches the same disposition** (round 16, R-RETR-009): a `threads.get` that states no
`internalDate` for a message states no chronological order for the thread, and amendment **A3** makes
a position an index into that order. The seal already refuses to invent one; the assembly used to
invent one anyway. Such a thread is withheld under the same rule and for the same reason — a source
that cannot describe itself is not shown as though it had. **PF-2** says whether `format=metadata`
produces the shape.

**Two smaller schema questions found alongside it, same disposition — WS-10/WS-11, not decided here:**

1. `not_tried[].why` has no value for *"the escalation policy declined to run this rung because
   evidence already existed"*. The closed vocabulary offers `not_applicable` and
   `budget | cap | timeout | error`; all four are false. Round 15 uses `not_applicable` and never
   emits `not_found`, so OD-2's machine-checkable rule is never violated — but the vocabulary may
   need a fourth value, and a vocabulary is not an implementer's call.
2. L4, L5, L6 and LR are **absent** from `not_tried` rather than listed as `not_applicable`, because
   claiming they could not have helped would be the false half of OD-2's distinction. The consequence
   is carried by never emitting `not_found`.

---

## A9 — mailbox provenance on every row; scope is preserved, never widened (round 18)

**Authority: OD-5.** Binding. This amendment carries the mechanics; OD-5 carries the decision.

**The defect this closes.** The round-17 invariant — *a probe composed from a subset of a query's
fragments searches the region the query named* — was right, and its **asymmetry clause was wrong**:
it permitted omitting a negation on the reasoning that a negation "widens within the same region."
True for `-from:x`. False for `-in:spam`, because a negated scope operator is not a filter inside a
region; **it is the region declaration.** Reproduced by the orchestrator across four shapes:
`-in:spam borogrove` sent `in:anywhere` with `includeSpamTrash=true`. R-RETR measured 201 such
probes in a 5,979-query sweep and 47 of 600 randomised trials disclosing a SPAM or TRASH row as
`role: matched`, `outcome: answered`.

**A1 — provenance is a field.** Every `MessageRow` carries mailbox provenance derived from the
message's **observed labels**. Not from the query that found it — that is the derivable-from-the-
caller defect this project has now found more than a dozen times, and the label set is what was
actually observed. Not a prose mention: a caller must be able to branch on it.

**A2 — scope is preserved across every probe.** Any probe derived from a query that named a scope,
positively or negatively, carries that scope. The asymmetry clause is re-derived from **what an
operator does** — whether it selects a region or filters within one — so it holds for scope
operators nobody has added yet. Enumerating `in:` and `label:` by name would be the fourteenth
instance of the pattern that produced this amendment.

**A3 — L3's broadening survives, narrowed.** `in:anywhere` is reached only when the query named no
scope at all, and only after nothing was found. That step is A.7's published behaviour and R-RETR's
reasoned verdict was to keep it.

**A4 — every behaviour here is mutation-tested.** R-RETR established that round 17's fixes for
R-RETR-026 and R-RETR-028 were **unasserted**: planting the defects back left all 2,248 tests green.
A fix no test defends is a fix the next round silently undoes. The sweep is over the **operator
family**, not per operator.

---

## A10 — the handle's watermark is the mailbox's, not the thread's (round 22)

**Authority:** R-RETR's ruling on round 21's declared deviation, accepted by the orchestrator.

**The deviation, accepted.** WS-06's `map_id` payload carries `thread_history_ids[]` beyond AD
§A.10's published field list. R-RETR ruled the field **genuinely required**: a stateless redemption
can form neither A.10's own LRU key nor a per-thread probe floor without it, and `min` is the only
safe choice among thread ids — `max` is not, because a thread that changed after the lowest
watermark would be walked past.

**The derivation, amended.** `history_id` must be **the mailbox watermark observed at fetch**, not
`min(thread_history_ids)`. This is not bookkeeping. The thread's own `historyId` can be arbitrarily
old, so a walk floored on it starts arbitrarily far back; with Gmail's 100-record page default and
`max_liveness_pages = 1`, R-RETR measured 150 unrelated mailbox changes making **every** redemption
return `handle_stale_unverifiable` with the LRU permanently bypassed at two calls, forever. The
mailbox watermark bounds the walk by the handle's own ttl, which is what makes the liveness probe
terminate for a reason rather than by luck.

**A second rule, from the same finding (R-RETR-059).** A liveness walk that **saw** a change and ran
out of pages reports `handle_stale`. `handle_stale_unverifiable` is reserved for a walk that
observed *nothing* and could not finish. Collapsing the first into the second serves content while
saying the change could not be verified — false twice over, because the change was both real and
seen. The five error classes exist to be distinguishable; a class that absorbs its neighbour's cases
is a class that says less than its name.

---

## A11 — a component that cannot separate candidates within a thread ranks but does not admit (round 25)

**Authority:** R-DISC-017/018, accepted by the orchestrator. Amends AD §A.9(3).

**The defect.** E4's `TERM_OVERLAP` reads the candidate's subject, and Gmail sends **one subject per
thread** on every message. So on the modal query class — terms that appear in the subject, a
participant on every message, a date window the thread sits inside — the anchored component fires
on **every** candidate. It admits everything and separates nothing, and the only component left to
order the admitted rows is `POSITION_ADJACENCY`. The E4 top class then **is** Baseline F's ±2
window, position for position. R-DISC measured six materially different queries against one thread
producing zero differing pairs. The thesis as shipped was ±2 under a query-aware name, which is the
exact degenerate strategy DISC-01's guard was written against, and the guard caught it.

Round 23's `ADMITTING_COMPONENTS` repaired *admission* and left *ordering* untouched, and its own
report described that as the fix. The three fairness tests passed because they compare across
different threads, not different queries against one thread.

**The rule, stated once.** A.9(3)'s admission rule already says `POSITION_ADJACENCY` ranks but does
not admit. A11 generalises it from *the component* to *the component's behaviour on this thread*:

> A component that fires identically on every candidate of a thread **ranks but does not admit**
> on that thread, whatever its published weight. Admission requires a component that separates at
> least one candidate from another. And a candidate's **rank** may not be decided by
> query-independent components alone.

This is not a new number and not a new weight. It is the existing rule applied where it was always
meant to apply.

**The test the round was missing** is three lines: a thread where every candidate fires the same
anchored component, and an assertion that the E4 ranking is **not** the ±2 window. It is required,
and so is a test that runs ≥ 5 queries over one thread whose subject carries all their terms and
asserts the included sets differ.

**A second rule from the same review (R-DISC-019).** A degradation step may not make the response
larger. `snippet → stub` currently does, because a stub is charged 40 tokens and a snippet only its
text (Gmail's snippets are ≤ ~36 tokens). A row is charged its **structural** cost at every depth,
so the ladder is monotone in cost as well as in depth — the test that was monotone only in depth
trusted its peer.

---

## A12 — what round 24 added to D.1 and what round 25 had to change under A.9a, recorded (round 25)

**Status: a RECORD, not a decision.** Filed by the round-25 implementer because R-MCP-015 is
right that two rounds changed published surfaces without an amendment entry, and A10 set the
precedent that a deviation from a published section is recorded here rather than only in a
round report. Every item below is **owner-visible and awaiting ratification**; none of it is
an argument that the change was correct, only a statement that it happened and why.

### A12.1 · Round 24's additions to AD D.1's published signatures (R-MCP-015)

`surface/tools.py` publishes more than D.1 writes, and the additions are additions rather
than narrowings:

* `mailweave_search` gained `relax{max_probes}` and `structural{max_probes}` argument blocks;
* `budget` accepts four cap spellings beyond D.1's three (`max_ms` **and** `max_server_ms`
  name one cap, because an affordance this server mints uses the second and D.1 writes the
  first — a call this server minted would otherwise be invalid at the tool that minted it);
* `force_rungs` accepts both the `RungId` vocabulary this server mints (`"L3"`) and the D.1
  family names it publishes (`"structural"`);
* `envelope/wire.py` gained `AttachmentMetadata` (field census 243 → 249);
* `disclosure/layout.py` made `body_full` a plannable depth, so
  `mailweave_get_messages(view="body_full")` travels through the same measure-and-degrade
  path as everything else rather than being a second route to the wire.

Round 25 adds one more: `query` carries a published `maxLength`
(`constants.MAX_QUERY_CHARS`), because without a bound a query reached an unwrapped
`httpx.InvalidURL` and was echoed back about four times over in a 4 MB response
(R-MCP-013).

### A12.2 · A.9a's rungs 3 and 4 now reach `stub`, and the document does not say so

**Forced by:** R-DISC-020 and R-DISC-023 together, which are the same gap seen from two sides.

A.9a's rungs 3 and 4 stop at `snippet`, and A.9a's honesty note says why: *membership plus a
snippet is the claim that is true*. What the document does not say is what happens when
snippet does **not** fit. Round 23's answer was, in order: raise the ceiling (step 6),
withhold (step 8), and finally raise `DisclosureLadderExhausted` — so a 200-message thread
every message of which matched came back as 200 pointers or as an exception out of the tool
handler. R-DISC-023 named the missing rung explicitly and said it was an owner-visible
amendment rather than an implementer's.

Round 25 wrote the rung and is recording it here rather than leaving it in a round report.
`_degrade_through_head_truncation` now ends `... -> snippet -> stub`. Three things bound it:

1. **it is reached last.** The driver stops degrading the moment the layout fits, so a
   response that fits at snippet never sees this rung and A.9a's honesty note still decides
   the ordinary case;
2. **a stub row is still a member** (A.7a, contract R-06), and — with R-DISC-030's fix to
   `_collapsible` — is collapsible into a *declared run with an expansion affordance*. So the
   rung converts "200 pointers, or an exception" into "a complete map, every message present
   and addressable", which is the direction OD-3 points;
3. **it made A.9a's own "if and only if" checkable.** Step 6 now raises the ceiling only when
   the response would still exceed the normal ceiling with every message reduced to a bare
   stub row — the counterfactual A.9a's text names and round 23 approximated with "steps 1-5
   are exhausted". That counterfactual was unreachable before this rung existed, which is why
   round 23 could not have implemented it.

**What the owner is being asked to ratify:** that A.9a's rung list gains `snippet -> stub` at
steps 3 and 4, and that its honesty note becomes a statement about the *preferred* bottom
rather than the last one.

### A12.3 · Round 26 gave A.9a a second ceiling, in a second unit (R-DISC-033, R-MCP-021)

**Status: a RECORD, not a decision**, filed for A12's own reason — a change to a published
surface belongs here rather than only in a round report.

**Forced by:** an ordinary twelve-message thread rendering **25,358 characters** against the
host's [VERIFIED] 25,000-character result cap while declaring `truncated_by: null`,
`partial: false`, `withheld: []` and `included: 12 of 12` — issue #296's shape, produced by
MailWeave. The host cuts an over-cap result **above the SDK**: the identical call driven in
process and through the real `Client` returns byte-identical sizes, so no layer below the cut
can observe it, declare it, or leave a record of what went.

What changed, in four sentences:

1. **`constants.HOST_RESULT_CHAR_CAP = 25_000` is published** beside the two token ceilings.
   AD F PF-6 names the figure; nothing in `server/src` had ever measured in its unit
   (`grep -rl maxResultSizeChars server/src` returned nothing).
2. **`Ceilings` carries it, optionally.** `host_chars` is `None` for a layout nobody is
   serving — the harness' arm comparison, DISC-04's efficiency ratio, every measurement — and
   is set by `surface.service.SERVED_CEILINGS` on all four tools, which is every path by which
   a response reaches a client. A.9a's published steps are unchanged; what changed is that
   `over_budget` asks about both ceilings, so the same rungs run for one more reason.
3. **`surface.partition.declared_result` measures the rendered `CallToolResult`** against the
   constant whatever was planned, and refuses one that is over it. The refusal becomes a
   declared `budget_exhausted` result with a narrower call to make — the shape
   `DisclosureLadderExhausted` already had.
4. **`measure_tokens` charges what it had not been charging** (R-DISC-032): `Source`'s own
   structure, its participant index, and the `not_included_sources[]` block. The participant
   index alone was 82 % of the rendered response on a mailing-list thread and was charged
   nothing, which made round 25's headline property — the estimate is an upper bound on the
   rendered wire — false from about twenty-five distinct senders up.

**The consequence, stated plainly, because it is a capability reduction.** A response is now
held to roughly seven ordinary messages at full body depth, and past that MailWeave degrades
depth, collapses stub runs and files withheld records to fit. That is not new behaviour
arriving; it is the same arithmetic, moved from the host — where it was silent and lost
evidence — to this server, where it is declared with a call that fetches what went. The three
tool-description claims and `SETUP.md` §6 were saying the opposite and now say this.

**What the owner is being asked to ratify:** that a served response is bound by two ceilings
in two units, and that the second one is enforced by refusing rather than by guessing a
conversion between them. Re-deriving the 9,000 and 12,000 token figures from the measured cap
remains PF-6's, and this round did not touch them.

### A12.3 · A.9(2)'s floor is relative to the evidence still disclosed

**Forced by:** R-DISC-021's fix meeting R-DISC-020's requirement.

Recording hit-members in `floor_of` (R-DISC-021) makes every hit of an adjacent-hit chain a
floor member, so on a thread where every message matched the floor is the whole thread. Read
absolutely — *these ids may never leave, whatever happens to the messages they are owed to* —
that makes an exception the only possible answer for a thread larger than the overflow
ceiling, which is the trade R-DISC-020 refused.

The gate therefore reads A.9(2) as the sentence it is: *while a hit is in the response, its
reply parent and direct children are in the response with it.* A step that takes a whole
source away — A.9a 7, which declares every id it removes in `not_included_sources[]` and as a
`withheld` record — takes the evidence and its floor together and leaves no chain with a hole
in it. Every other removal of a member is refused exactly as before, and `Layout.floor_pairs`
names *whose* floor each member is so the two cases are distinguishable at all.

**What the owner is being asked to ratify:** that "membership is absolute" (OD-3) means
absolute *relative to the disclosed evidence*, and that a whole declared source split is not a
breach of it.

### A12.4 · `ceiling{}` may declare a ceiling **below** the published one

**Forced by:** R-MCP-004.

`Ceiling` refused `applied < normal` and pinned `normal` to the published constant, so AD
D.1's published `budget.max_disclosed_tokens` was unrepresentable: every value in [1, 8999]
raised a `ValidationError` that reached the caller as `-32602 INVALID_PARAMS`. `normal` is
still the published figure; `applied` is now what this response was actually held to, in
either direction, and **any** departure carries a `why`. A caller-lowered ceiling is a
ceiling; what it must not be is silent.


## A13 · `max_server_ms` is 7,700 ms, by owner decision rather than by validation

**Forced by:** R-RETR-065, and by live v0.1 acceptance test 5.1 failing twice on the published
figure.

A.7's cap table published `max_server_ms = 2,000` as a [DESIGN] starting value. R-RETR-065
observed in round 28 that it had never been measured against a network and that the published
pair `max_http_requests = 24` with a 2,000 ms deadline assumes 83 ms per request. Deadline runs
1 and 2 could not settle it: every arm declined on the host character cap rather than the clock,
which is R-MCP-033, so the clock was never what was being measured.

With R-MCP-033 closed, acceptance test 5.1 failed on 2,000 ms twice against a live mailbox
(`632cfbc`, `b0420ce`): the broad capped query served truthfully at ~8,700 characters carrying
**zero sources and zero matched rows**, having spent its whole deadline on one `messages.list`
and four or five `messages.get` calls without ever affording the single `threads.get` that a
`source` requires.

Deadline run 3 measured 2,000 / 7,700 / 12,300 ms across three pre-registered queries and three
counterbalanced repeats. On the acceptance query 2,000 returned zero evidence in every repeat
and 7,700 returned the same non-empty `body_clean` evidence in every repeat without hitting the
clock; 12,300 showed no benefit over 7,700.

**The published figure is now 7,700, and it is an owner-selected operational default.** Run 3's
registered verdict is `adoptable: false`: the 12,300 ms reference arm took two
`upstream_rate_limited` 403s from Gmail during the run, which broke `stable` and
`no_asymmetric_decline`. The number may be described as selected on repeat live observations and
**never** as validated. Record and reasoning: `validation-records/DEADLINE_DECISION.md`; raw
record committed unedited.

**What this amendment does not settle.** PF-21's arithmetic objection is unretired: at 24
requests and the ~400 ms per request run 3 observed, no deadline below about 9.6 s lets
`max_http_requests` be spent, so `preflight/probes/latency.py` still returns FAIL on
`24 x p90 > max_server_ms`. 7,700 is the figure that makes the documented v0.1 workflows return
mail, not the figure that reconciles the pair. Reconciling them is future work.

## A14 · Navigation and disclosure: pages, requested rows, continuations (2026-09-14)

**Forced by:** R-M2-076 and R-M2-080, the 2026-09-13 sem-off diagnostics through the MCP
boundary (`docs/reviews/M2_BOUNDARY_RERUN_2026-09-13.md`), and the owner's redesign brief.
Design note: `docs/reviews/DESIGN_NAVIGATION_AND_DISCLOSURE_2026-09-14.md`.

The expansion path planned the whole surrounding thread as rows and let A.9a degrade and
collapse them: a read of one message in a 90-message thread rendered 8,311 characters with
the row degraded, `get_messages(ids, view: stub)` returned zero rows for every request
(`ladder._collapsible` took a requested stub like any other), a snippet read returned a top-k
of five, and a long thread's map was zero rows and one run whose affordance re-listed every
member id and returned the same shape. Nothing an agent could follow narrowed to a body.

**What D.1 and D.2 now say, additively (`schema_version` stays 2):**

* `mailweave_thread_map(thread_id?, map_id?, segment?, page?)`. `page` is zero-based and
  exclusive with `segment`. A map is served as a **page**: `page_size` positions as stub rows,
  each with its `unabridged` call; every other page as a `collapsed_runs[]` entry that lists
  its members' ids **once** and whose affordance is `mailweave_thread_map(thread_id, page)`
  for the page its first position falls in; and a `thread` continuation to the next page.
  `Source` states `page`, `page_size`, `pages` together. `page_size` is not a constant: it is
  the widest page whose upper-bound estimate - over every page, not page 0 - fits the
  published ceilings and the host's cap, computed by one arithmetic (`disclosure.pages`) from
  the *snippet-scanned* thread map alone: `ThreadMap.auth_record_chars` and
  `display_name_chars` carry the thread's widest INJ-05 record and longest display name so a
  map served from the LRU computes the same width as one built from the read, and the search
  path sizes on the snippet map rather than on its body-scanned one. Pages therefore tile the
  thread whichever page is asked for first, and every page fits what the probe fits. A `page`
  outside the thread is an invalid argument, never another page. `segment` stays as AD §E.2's
  experiment.
* `mailweave_search`'s `collapsed_runs[].affordance` names a page the same way. It used to
  name the temporal segment, and following that call on a long thread declined terminally -
  as did the recovery chain's `segment: 0` hops (R-MCP-033's search→map hop and the map's own
  narrowing), which now name the thread's map and nothing narrower: a map is already the page
  that fits, and one that does not fit is at the declared inventory limit. `segment` remains
  accepted as E.2's experiment; no affordance names it (R-M2-085).
* On `mailweave_get_messages` a named message is `Band.REQUESTED`: no step of A.9a collapses
  it or degrades it below the depth asked for, so a stub or snippet read of N ids returns N
  rows. The thread each requested row is in rides along as a compact inventory (runs pointing
  at pages, `map_id` minted) when that fits beside the rows. When it does not, the fit loop
  sacrifices in a published order: inventories first, thread by thread in rank order (a
  thread without its inventory is *scoped* - its rows, their direct reply parents as
  `withheld[]` records, everything else one thread-granular `withheld_groups[]` entry under
  the thread's map call; a scoped source mints no `map_id`); then requested rows, keeping the
  longest prefix in request order that fits and naming the rest in a **`requested`
  continuation**. A thread none of whose named messages fit is *deferred*: one
  `not_included_sources[]` entry and one group, whose call is that thread's share of the
  continuation. Every arrangement is checked on the estimate and then measured as rendered
  (`envelope.measure.rendered_chars` against `HOST_RESULT_CHAR_CAP`) before it is served.
* `Envelope.continuations[]`: `{scope: "requested"|"thread", thread_id?, positions?,
  message_ids[], remaining, affordance}`. A continuation preserves access to the **remainder**
  of something this response started and following it makes progress: the remainder is
  strictly smaller and never contains what this response carried. It is not a `narrowing`,
  which travels on a decline and changes scope. A `requested` continuation makes the response
  `partial` and is an artifact of `truncated_by: mailweave`; a `thread` continuation is not
  an omission - the map beside it is whole.
* A single requested body that does not fit even alone and scoped is **declined** with the
  `view` narrowing R-MCP-039 certified (`body_full` → `body_clean`), never head-truncated
  below the depth asked for. The tail of a message longer than the cap is a declared limit
  of the inline surface. So is a thread whose inventory alone - every member id once -
  exceeds the cap: around 800-1,000 messages at Gmail's 16-character ids; its map declines.
* `COLLAPSED_RUN_MEMBER_ID_COPIES` is 1 and `COLLAPSED_RUN_MEMBER_CHARS` is 6, measured:
  a member's id renders once, in `member_ids`, on both paths. The run's thread id is charged
  at its width, twice (`COLLAPSED_RUN_THREAD_ID_COPIES`), for the affordance and its twin.

**What is preserved.** Exhaustive disposition accounting (`certify` still refuses a withheld
id without a record, a note for a disclosed id, and a group count that does not sum);
`accounted_for == stated_total` on every source that claims a map; reply-parent references
followable through rows, run members or withheld records (R-M2-077); content fencing;
freshness stamps; the E2 floor on the search path; `MAX_SERVER_MS`, the token ceilings, the
host cap and the recovery budgets, unchanged.

**Addendum, 2026-09-15 (continuation correctness; the owner's follow-up).**

* A `thread` continuation names its page's own handle: `mailweave_thread_map(map_id, page +
  1)`, not the thread and an index. Following it redeems the handle under A.10 first, and the
  page is served only when the probe saw nothing touch the thread (or could not look -
  `handle_stale_unverifiable` in band, fetched live), the thread still digests to the
  handle's `mapping_digest`, and the map's page width is the one the handle signed. A thread
  that moved, or a paging that moved, is `handle_stale` with the re-derivation - page 0 by
  `thread_id` - as the explicit restart; an aged handle is `handle_expired` the same way. A
  traversal therefore never skips or repeats a position silently: it is told to start again.
  A response that mints no handle offers no `thread` continuation.
* `HandlePayload` gains `page_sizes` (positionally aligned with `thread_ids`; `HANDLE_VERSION`
  2, so handles minted before it are `handle_invalid`): the width each named thread's map was
  paged at. The digest fixes the messages and their order; this fixes the paging, which can
  move with the thread unchanged only when the server's own measure constants change under an
  outstanding handle. Checked by the surface on `thread_map(map_id, page >= 1)`; page 0 is
  page 0 at any width.
* `collapsed_runs[].affordance` stays the pointer form `thread_map(thread_id, page)` on every
  path, recorded as a choice (design note §7.12): a run's page is the page of the thread as
  it stood at `fetched_at`; the page it lands on states its own `page`, `page_size`, `pages`,
  `stated_total` and `fetched_at` and lists every id once; nothing about a run is a claim
  that the page is unchanged.
* The re-derivation affordance a `handle_*` refusal carries names `thread_id` - the argument
  the map tool takes - rather than `thread_ids`, which it never took.
* The page width charges the continuation's handle at the payload schema's bounds
  (`handles.mint.widest_handle_chars`) and the in-band note a handle-served page can carry,
  so the width is a function of the thread state and published bounds alone.
* **Stated as a limit, not a property:** map pagination carries the remaining member
  inventory on every page and therefore retains a total-thread-size limit - on the order of
  800-1,000 messages at 16-character ids - beyond which the map declines. It is not
  size-independent pagination.

**What this amendment does not settle.** M5 of the design note (`withheld_groups[]` as
reason blocks) is deferred: after M1 and M2 no measured case needed it. Whether a client
*discovers* the right page or the right id is retrieval and ranking, not disclosure, and is
measured separately (`docs/reviews/M2_NAVIGATION_REDESIGN_2026-09-14.md`). R-M2-076 remains
open for the first-response bookkeeping overflow on broad searches; this amendment closes
R-M2-080 within the demonstrated scope (known-target reachability on corpus-independent
fixtures and the thirteen sem-off diagnostic cases), not both blockers.

## A15 · The first response's sizing, its last resort, its refusal's cause, and the order of its offers (2026-09-15)

**Forced by:** R-M2-093 to R-M2-097, the causal diagnosis of the backend-on regression
(`docs/reviews/DIAG_SEMANTIC_REGRESSION_2026-09-15.md`), and the owner's authorisation of the
R1-R4 repair as one scoped integration change. Report and evidence:
`docs/reviews/INTEGRATION_REPAIR_2026-09-15.md`. Regressions:
`tests/test_integration_repair_2026_09_15.py`, corpus-independent.

The semantic rung's structure - a pool whose unselected and unread candidates are all named
as groups, and a shortlist whose hits land in the top lexical source and are protected there -
met a ladder whose estimate charged the pool's groups as if they folded, whose last resort
emptied a response it could have collapsed, whose refusal said nothing about what did not
fit, and whose offers were walked in an order that was not a rank. Four parts, each a
correctness change to an existing contract rather than a new budget or a new model.

**R1 - one arrangement for sizing and wire (R-M2-094, R-M2-097).** `Layout` carries the
`withheld_groups[]` keys it will file, `(thread, cap)`, and the set of caps whose groups may
fold (`foldable_caps`: the caps a tail recovery is filed for, today `max_hit_threads`
alone); `envelope.grouping.arrange_groups` is the one arithmetic that decides, on both the
estimate and the ledger, which groups are named (the fixed caps always; the foldable ones up
to `MAX_WITHHELD_GROUPS_NAMED`), which fold into `withheld_tail[]`, and in what order. A thread
is under one cap: a mapped thread is never grouped; a thread the width cap left unmapped is
under `max_hit_threads` even when the pool also listed and never read it; the pool's caps
name only the threads nothing else accounts for. The round-27 estimate matrix runs with a
backend registered, and the estimate is at or above the rendered size on every shape.

**R2 - A.9a step 7's last resort collapses the last evidence-bearing source before it lets it
leave (R-M2-093; search only).** A.7a has always counted a collapsed-run member as *present*.
When the only source still carrying evidence does not fit, its rows - the top-k-protected
hits and the floor included - go to stub depth and collapse into declared runs
(`ladder._last_source_to_runs`, re-cutting rows and existing runs into maximal contiguous
runs), and only if that still does not fit is the source split and the response refused as
empty. The reduction is declared (step 7's `collapsed run(s) declared`, `row(s) reduced in
depth`; `truncated_by: mailweave`; `partial: true`); the ways back are executable and named
on the response - the run's own map call, and the recommended `mailweave_get_messages` read,
which now names collapsed hits as well as rows below depth (bounded by
`RECOMMENDED_EXPANSION_LIMIT`); and run membership is **not** delivered content (the harness
counts only rows at a body depth, EP §6.1). An explicit read is untouched: the move never
runs where `evidence_is_the_map`, and a `Band.REQUESTED` row keeps its depth (A14). A
thread too large even as a run - its inventory alone over the cap - still refuses through
the emptiness gate; round 29's "single thread too large for any arrangement" fixture is now
that shape (nine hundred messages), and the three-hundred-message one is served as
membership. Correct sizing (R1) and this move together can *increase* refusals on a shape
where the estimate used to under-charge; nothing hides that.

**R3 - a refusal carries what it was made of, and the retry reduces that (R-M2-095).**
`DisclosureLadderExhausted` carries a `RefusalCause` and the decline carries it as `cause`:
`kind` (`size` | `empty`), the binding `unit` and `cap`, the refused layout's cost by the
term the wire renders it as (`CostTerms` - the very terms `layout_chars`/`layout_tokens`
sum, not a second breakdown), the named groups by cap, the width in effect, the top thread,
the last evidence-bearing source's smallest inventory (`residual`), and `fits_at` /
`refused_at`: **the ladder itself, run over the same retrieval at every narrower
`max_hit_threads`**, as `_step_8_would_fit` asks step 8 a hypothetical. The retry
(`recovery.narrower_call`) is the widest width that fits - the fewest threads moved from mapped
to grouped, each with its map call on the served response; which threads those are is the
producer's cut order, carried as `PlannedSource.mapped_at`, not the ranking's (R-M2-099) -
declared `narrowing.kind: narrower`; when no width fits, the hop to `mailweave_thread_map(top thread)`
is declared `scope_change`, and the remediation says which hit-bearing threads that map does
not account for. Without a cause (the render backstop; a read's `view` and id chain) the
schedule is what it was. A retry is never a continuation: a continuation rides on a served
response and asks for the remainder; a retry rides on a decline and asks for less or for
something else. `MAX_RECOVERY_STEPS` is 12, derived: a cause-directed chain may reduce the
width by one per hop from the published 12 to 1 and then change tool; in practice it is one
hop, and the bound is what holds if the ladder's answer at a narrower width were ever wrong.
Narrowing the pool is **not** a cost-reducing recovery and is not offered: the candidates a
smaller pool does not read are still accounted for, one group each, so a narrower pool has
more of them, not fewer.

**R4 - retrieval's rank on the offers, and a walk that follows it (R-M2-096).**
`withheld_groups[].rank` and `not_included_sources[].sources[].rank` (both optional, `>= 0`)
carry the retrieval's own order for the threads that had one - the mapped order, overflow
continuing it - via `DispositionLedger.note_rank`; the ledger writes named groups and the
producer writes split-off entries in that order, the unranked after, by thread id and cap.
The harness driver walks the two blocks as one sequence in ascending rank, the unranked
after in the order listed (`arms.in_retrieval_order`, `boundary.Served.offers`), and the
known-target offers (a wanted id's row, run, record or continuation) come first and
separately, as before. Nothing reads an expected evidence id, a corpus position or a case
label to order anything.

**What is preserved.** Every evidence and floor membership obligation; `certify`'s exhaustive
accounting; the explicit-read contract of A14 in full; the ladder's eight steps and their
order (`LADDER_STEPS`); `MAX_SERVER_MS`, both token ceilings, the host cap, the pool's bounds,
`MAX_HIT_THREADS`, the driver's rounds and calls; the models, the corpus and the acceptance
criteria of M2. `schema_version` stays 2: the new fields are optional and additive
(`rank` on two entry kinds; `cause` and `narrowing.kind` on a decline).

**Declared limits.** A decline now runs the ladder up to eleven more times on a hypothetical
layout to fill `fits_at`; measured at about 80 ms over the plain refusal on the shapes in
the regression file and on the diagnostic corpus with the stand-in backend, inside the
unchanged deadline. The `fits_at` table is exact to the ladder's arithmetic and to a producer
emulation - the first `width` sources of the cut order kept, the rest demoted to groups under
`max_hit_threads` with their hits and floor obligations removed as the producer would, the
ledger's observed ids a harmless superset; a map-stage budget breach at the narrower width is
not emulated. The retry's own ladder is still the arbiter, and a wrong entry costs one more
hop, never a repeated call. Step 8 keeps the last matched message present (the emptiness
gate's rule, applied where step 8 used to reach it first), so the last resort's collapse is
reached on every path that would otherwise empty a search. A thread whose inventory alone exceeds the cap still
declines on its map (A14's limit). R-M2-076's broad-query first response still declines on
the lexical arm's widest shapes; what this amendment changes there is the chain - one hop
to a served response, at the widest width that fits - not the first response.

## A16 · Exhaustive accounting and evidence protection are separated for D.5 step (c) (2026-09-15)

**Forced by:** R-M2-101, which corrected the diagnosis's limb (i): the backend-on call and
size cost is not the shortlist's twenty-five selections but the L5 **probes**, which admit
their whole result set to `H`. (The figure R-M2-101 attached to that - 334-462 ids on the
diagnostic queries - was measured through a double that could not evaluate the probe's own
`after:<epoch>` clause and so matched every message with it, in the real-model runs as much as
the stand-in ones. The mechanism is what forces this amendment; the magnitude is qualified and
unestablished - R-M2-110, R-M2-112.) **Authorised by** the owner's scoped decision of
2026-09-15. Regressions: `tests/test_a16_recency_pool_evidence.py`, corpus-independent.
Replants: R254, R255, R256.

**Three claims, kept apart on purpose (2026-09-16).** This amendment is read wrongly if its
parts are read as one, so they are separated here and everywhere they are cited:

  1. **The contract rationale — A.9's evidence tier is owed to what the query selected.**
     An argument from A.7a, A.9(1), A.9(2), A.9(5) and D.5. It stands or falls on the reading
     of those clauses and **nothing measured bears on it**, in either direction.
  2. **The protection-narrowing change** — an id reached solely by an internal step-(c) probe
     loses the tier, the protected top-k and the power to anchor a floor. This is what the
     owner authorised. On a correct instrument its measured effect on a served response is
     **zero** (§A16's closing note, ledger R-M2-112).
  3. **The shortlist-union correction** — a message the shortlist selected is in the tier even
     when only a thread read reached it. This is a **defect repair**, found by the second
     independent review (R-M2-111), not part of the authorisation; it is in this amendment
     because (2) is what exposed it. Every measured difference on a correct instrument is
     this, not (2).

Claim 1 is not evidence for claim 2's value, and claim 3's measured effect is not claim 2's.

**What the contract said and did not say.** AD A.7a requires every id a retriever returns to
enter `H`, and ADV-109 named one of the pool's steps by hand: `messages.list` at any rung
"including the L5 pool-construction **participant probes of D.5 step (b)**". D.5 step (c) -
the most-recent-threads probe over a date window, `DEFAULT_RECENCY_DAYS` when the query names
none - was never analysed. Its ids entered `H` under the general clause, and from there A.9(1)
("every hit at `body_clean`"), A.9a step 3's protected top-k and A.9(2)'s reply-chain floor
applied to them as they apply to any hit. A ninety-day window therefore became evidence, took
protection from shortlisted messages, and anchored floors of its own.

**The amendment, in one sentence.** Membership in `H` **solely** through an internal
recency-pool probe is accounting, not evidence: the id keeps its place in `H`, its `certify`
disposition, its provenance and its omission accounting, and loses only the evidence tier,
the protected top-k, and the power to anchor a floor.

**Which makes the tier what the *query* selected, and that has two halves.** The first review
of this amendment implemented the subtraction alone and stated, as a virtue, that it "widens
nothing". That was true of the function and false of the response. `hit_threads` builds a
thread's hits from `messages.list` observations, and D.5's pool embeds **every row of a thread
it reads** - so the shortlist routinely selects a message the step-(c) probe never listed,
because it is outside the window or past the probe's single page. Such a message was never in
`hit_ids`; before the amendment its thread was hit-bearing anyway through the recency-only rows
beside it, and after the subtraction alone it was hit-bearing through nothing, while
`_split_off_unselected_pool_threads` still kept it as a source because the shortlist *had*
selected in it. A source holding the decisive message with an empty `hit_ids` turns
`_carries_nothing` to its "there was never any evidence" branch and lets A.9a step 7 drop the
source carrying the answer - the overclaim this amendment exists to prevent, one layer down.
So `hit_threads` also **unions the shortlist's own ids** into the threads it plans: the tier is
`(listings - demoted) | shortlist`. `rung_of`, the ranking and `listed_ids` are computed from
the listings alone, so nothing about ordering, rung attribution or the issue-#296 integrity
check moves. Demonstrated on a two-message thread by the independent review (finding 1) and
held by `R258` and two regressions.

**Solely is load-bearing, and it is decided on routes, not on origins.** `HitOrigin` records
where an id *entered* `H`; a second sighting deliberately does not move it. Reading the origin
would therefore call a lexical match "recency-only" whenever the pool's probe happened to list
it first - and L4's structural recovery and LR run after the pool, so that ordering is
reachable. `DispositionLedger` now records an `AdmissionRoute` (`endpoint`, `rung`, `query`)
for **every** observation, alongside and not instead of the origin, and
`assemble.pool_listed_only` demotes an id only when every one of its `messages.list` routes is
L5 *and* carries one of the step-(c) probe queries the pool's own plan holds
(`recency_probe_queries`), and it has no `history.list` route at all.

**The boundaries, as the owner drew them.**

  * a **shortlisted** message is eligible semantic evidence however it was listed;
  * a **lexical** match keeps its protection even when the recency probe also returned it,
    and even when the probe returned it first;
  * a **direct user date query** is not an internal recency-pool probe: the probe set is read
    off `plan.probes` by `PoolStep.RECENCY`, so what makes a query internal is which probe
    sent it, never what the clause looks like;
  * **D.5 step (b)'s participant probes are untouched** - out of the amendment's set, and
    still in the set the row roles have always used;
  * **explicit reads are untouched**;
  * a `threads.get` of a pool thread does **not** rescue a recency-only id: thread membership
    has never been a listing, and `hit_threads` reads `messages.list` alone;
  * **existing evidence keeps its parent/child obligations** even when those members are also
    pool members. A16 takes away a pool row's power to *anchor* a floor; it does not take it
    out of the floor it belongs to.

**Applied once, so it is applied consistently.** The tier is decided in one place -
`hit_threads` - and these surfaces read that one set: planning (`ThreadPlan.hit_ids` and
`Layout.hit_ids`), A.9a step 3's `_top_k_hit_ids`, A.9(2)'s `floor_pairs` anchors, the emptiness
gate `_carries_nothing` - so a response whose surviving rows are all unselected recency
candidates no longer claims that query evidence survived - and the width the recovery narrows
to.

**Two of the surfaces the owner named are *not* decided by the tier, and saying otherwise
would be the easiest thing in this amendment to get wrong.** Source eligibility is A.9(5),
decided by `_split_off_unselected_pool_threads` on the admitting **rung** and the shortlist;
it already refused to make a pool thread a source before this amendment and is unchanged by
it. The matched/context **roles** are decided by `is_hit` *and* `pooled_only`, and
`pooled_only` reads origins (below), so a row's role and its tier can disagree. Both are
recorded as they are rather than claimed as narrowed (independent review, findings 2 and 7).

**Accounting is untouched, and that is the half with the invariant.** The demoted thread stays
in `plans` with an empty `hit_ids` so `_split_off_unselected_pool_threads` and `_undisclosed_caps`
still dispose of it; dropping it instead raised `DispositionInvariantError: hits left the
payload with no withheld record`, which is the seal doing its job. `ThreadPlan.listed_ids`
carries what the ledger listed for the thread, so the issue-#296 integrity check still sees
every listed id whether or not it is evidence.

**What is recorded rather than changed.** `pooled_only` - the *role* rule - still reads
origins. Rewriting it on routes was tried and is a
**widening**, not a fix: a participant-probe row whose Gmail `q` is `from:...` becomes
`matched`. It is left alone deliberately, and that asymmetry (routes decide the tier, origins
decide the role and source eligibility) is the amendment's, not an oversight.
`_reason`/`_semantic_reason` also still read origins, and L6's `hit_messages` counter is
unreviewed for this distinction; both are recorded in the findings ledger, unfixed
(R-M2-104, R-M2-105). Two further limits the second independent review established are
recorded and not repaired here: `hit_threads` still decides **membership** on the
first-admission origin, so an id a thread read admitted and a lexical rung later listed never
becomes a hit at all (R-M2-108); and the amendment stands down when the pool ran its probes
and produced no shortlist (`semantic.result is None`), which is a path that cannot complete a
response at HEAD for an unrelated reason (R-M2-109).

**An instrument was repaired to make this reachable.** The server writes step (c)'s probe as
`after:<epoch>` (A.6a rule 4), and the synthetic mailbox double returned "cannot judge" for
that form - which it treats as *matching every message*. So no test in this repository could
observe the recency window excluding anything, and every integration statement ever made about
the pool was made against a probe that selected the whole mailbox. `tests/fixtures/mailbox.py`
now evaluates epoch seconds, as Gmail does. This is a test double, not product code, and it is
why finding 1 needed an independent reviewer to monkeypatch the product to reproduce it
(R-M2-110).

**What this amendment does not claim.** Nothing about cost - and the measurement, now done,
says so directly. On the corrected instrument the narrowing's effect on a served response is
**zero**: the ids it demotes are almost entirely in threads A.9(5) already withholds. At the
campaign level A16 moves five calls of 341 and changes no delivery outcome. See
`docs/reviews/A16_RECENCY_POOL_2026-09-15.md` §5 and ledger R-M2-112, which also records that
R-M2-101's own 334-462 figure was measured through the instrument R-M2-110 corrected, so the
size of the problem this amendment was authorised to solve is itself unestablished.

### A16 · Owner decision, 2026-09-16: both components retained, on separate grounds

The paired real-model measurement is complete (`benchmarks/a16-models.VyHeie/`,
`docs/reviews/A16_RECENCY_POOL_2026-09-15.md` §11, ledger R-M2-115). **Both components are
retained. Neither is retained for a measured benefit, and neither carries one.**

**Protection-narrowing — retained because it implements the approved distinction between
candidate accounting and protected evidence.** An id that an internal D.5 step-(c) probe
returned, and that nothing else reached, is a *candidate the pool accounted for*, not evidence
the query produced. Before this amendment it took A.9(1)'s evidence tier, A.9a step 3's
protected top-k and the power to anchor an A.9(2) floor, because it fell inside a date window.
The amendment makes the accounting exhaustive and the protection selective, which is the
distinction the owner approved. **No performance-benefit claim attaches to it.**

**Shortlist-union — retained because it repairs the reproduced selected-message omission.** A
source holding the message the shortlist selected could reach the ladder with an empty
`hit_ids`; `_carries_nothing` then took its "there was never any evidence" branch and A.9a step
7 was free to drop the source carrying the answer (R-M2-111, reproduced end to end by the
second independent review). The repair is that the tier is what the query selected, the
shortlist included. **No performance-benefit claim attaches to it**, and its measured effect is
not separable from the narrowing's in the run that was made.

**The separation, stated once so it is not lost.** These are two changes with two
justifications. The first is a contract distinction the owner approved. The second is a defect
repair the amendment exposed and was never part of the authorisation. The measurement compared
`pre` against `post` with both present and **cannot attribute any part of its result to either**
- so nothing in it supports or undermines either justification, and no part of it is offered as
evidence for one. The A16 measurement task is **closed**; its records and the R-M2-113 repair
evidence are preserved.
