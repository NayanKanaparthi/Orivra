# Evaluation scope: what can still be measured, what cannot, and what would be needed

**A proposal for the owner, not a decision I am taking, and not a waiver of anything.** Both
independent reviews are in: C4 on the corpus is **NO**, and the runner was **not fit to grade
M2** before the bounded repair. The corpus is frozen and no third repair round is proposed. The
question this file answers is narrower and unavoidable: given the material that exists and has
been reviewed, what can be claimed, and at what cost would the rest be claimable.

Nothing below lowers a bar. Where a criterion cannot be met it is named as unmet.

## 1. The three constraints that set the scope

**C4-01 is the largest.** Evidence positions and role layouts are identical at every seed:
41/41 on the sample profile, 208/208 at gate. `EVALUATION_PLAN.md:564` says a new master seed
re-randomises "evidence positions, distractor placement", and `:1092` (G3) says memorising "the
answer is at position 37" is "worthless across runs by construction". It is not. A shape lookup
trained on one seed places the answer exactly in 97 of 200 gate threads at another. **Every
multi-seed number anyone has produced - including the 0.354 → 0.232 in the repair report - is
one geometry measured six times.** Whether G3 is mandatory is a plan question with two readings
on record, and it is the first thing the owner has to settle.

**The runner's scope is narrower than the plan's.** Reconciled against the plan and stamped
into every record as `SCOPE`: of EP's baselines the command implements Baseline F at N=2 and
nothing else - no B, C, D, A/A', no Baseline E (`primitive.py` says in its own docstring that
it is not that arm), no SEM-LOCAL-ALT or SEM-HOSTED. Of EP's metrics it computes recall,
`cut_loss`, `levels_traversed` and recoverability; it does not compute `rank_of_evidence`,
aggregated tokens, latency percentiles, API-call counts, the escalation confusion table,
budget-matched curves, P6/P7, any freshness measure, or McNemar. H1-H3 themselves are
registered in `ORIVRA_V1_PLAN.md:877-879`, not in `EVALUATION_PLAN.md`; the mapping onto EP's
eleven falsifiers is asserted in code comments and nowhere else.

**Per-family compromise, from C4 §2.** F1, F2, F5, F6 hold. F3 holds as a position sweep only.
F4, F7, F8, F11, F13, F14, F16, F17 fail on at least one of answerability, ground truth, or
mechanism. F12 holds for recall and not for answer accuracy. F15 is answerable but not scored
as the key declares.

## 2. What can be tested credibly with the reviewed material

Each of these survives both reviews. Each carries the caveat beside it, in the same sentence,
wherever it is reported.

| claim | on what | the caveat that travels with it |
|---|---|---|
| **H3's F3 position-flatness clause** | 84 gate F3 threads | the register leak is identical at all seven sweep positions (C4 §6, 84/84), so the *contrast* measures position even though the absolute score does not. One seed's geometry |
| **Retrieval recall on F1, F2, F5, F6** | 36 registered cases | single-geometry; F2 is not scored by C2/C3 at all |
| **Recoverability, first response against after expansion** | every family | it is a description, not a hypothesis clause, and it is now reported with controls excluded |
| **The primitive-tools floor comparison** | all cases | it is a fixed policy, **not Baseline E**; it does not answer EP's "agents already do this" falsifier |
| **Controls: was the unanswerable answered** | 10 F10 cases | newly reported; reported, never graded |
| **That the command executes end to end offline** | dry run | establishes the path, not a number |

## 3. What cannot be tested with this material, and why

| claim | blocked by | status |
|---|---|---|
| **H2, entire** | C4-05: the F16 confirmation states the adopted figure outright in 8/8, so no near-duplicate ranking is required. A hypothesis with an uninterpretable clause cannot HOLD | **unmeasured** |
| **H1's F4 clause** | C4-08: the evidence is a direct reply to the lexical trap in 6/12 and within two positions in 7/12 | **confounded** |
| **H1's F11 clause** | C4-04: one of the two sample threads carries ground truth a competent reader rejects | **not on this population** |
| **H3's F17 clause** | C4-06: reversal wording plus the entity name finds the answer 8/8 with no reply chain. C4-11: the case is answerable only through headers a human reader cannot see | **does not test the E2 floor** |
| **Every cross-seed claim** | C4-01 | **withdrawn** |
| **Answer-accuracy scoring on F3, F4, F11, F12** | C4-07: "trust the sentence that names the entity formally" is right 116/116 | **unmeasured** |
| **F7 cross-thread dependence** | C4-02: the dependence is not in the text; the case is two independent lookups labelled `all_of` | **unmeasured** |
| **F8 attachment currency** | C4-09: the two same-named copies are separable only by a hedge that also appears in unrelated filler | **undecidable** |
| **F14's changed-address identity** | C4-10: eleven messages in nine conversations assert the opposite | **contradicted by the corpus** |
| **Anything requiring Baselines A-E, the budget curve, freshness, latency percentiles or API counts** | not implemented in the canonical entry point | **unmeasured** |

## 4. What would need independently authored replacement material

Ordered by what each unblocks, not by effort. **None of it is proposed as a generator rewrite**,
and none of it should be authored by whoever grades it.

1. **A seed-varying layout.** The one change that unblocks every multi-seed claim, and the only
   one that is a generator change rather than new material. It is a plan question first: either
   G3 is mandatory and the generator must meet `:564`, or the plan is re-registered by its
   owner to say positions are fixed and memorisation is not tested. **An implementer's closing
   note does not settle it** - that is how R-M2-044 was closed against the plan's own text.
2. **Held-out acceptance questions, authored by someone who has not read the answer key.**
   Already commissioned in principle and deliberately not written by the corpus reviewer or by
   me. Without them, every recall number is measured against questions written from the same
   notes that built the threads, and C4-12 found those notes wrong about their own threads in
   five families.
3. **An F16 replacement whose confirmation does not state the figure**, or H2 stays unmeasured.
   This is the single largest unmeasured claim.
4. **F7, F8, F14 replacements**, each fixing the specific defect C4 names. F7 needs text that
   links the halves; F8 needs a decidable currency signal; F14 needs a corpus that does not
   contradict its own key.
5. **Baseline E as the plan defines it**, if EP's "agents already manage thread expansion"
   falsifier is to be answered at all. The current floor is honest about not being it.

## 5. The three options, and what each one costs

**Option A - report the narrow set.** Publish §2 and mark everything in §3 unmeasured, with
C4-01 stated wherever a number appears. Cheapest, honest, and it does not reach M2 acceptance:
H2 is unmeasured and H1 and H3 each keep one clause. *This is a narrower release, not a pass.*

**Option B - settle G3, then commission the replacement material in §4 items 2-4.** Unblocks
cross-seed claims and H2. Largest cost, and it is the only path to the M2 claims as registered.

**Option C - re-register the criteria to what this material can support.** Legitimate only if
done before any number is read and by the plan's owner, with the same pre-registration
discipline the content gate had. It is not a waiver if it is written down first and it is a
waiver if it is not.

I recommend **A now and B started in parallel**, and I am flagging that this is a
recommendation and not a finding. Option C should not be taken on the implementer's argument.

## 6. What is not proposed

* No third corpus-repair round, no generator rewrite, no change to the frozen corpus.
* No mailbox operation, no M3 work.
* No silent waiver: every criterion this material cannot meet is listed in §3 as unmet, and
  §5's option C is named as a re-registration that needs its own discipline rather than as a
  way of passing.
