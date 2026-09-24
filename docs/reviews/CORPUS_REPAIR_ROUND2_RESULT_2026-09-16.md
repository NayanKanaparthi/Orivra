# Bounded corpus repair: result against the frozen criteria

**Round 2 of 2. The gate FAILS. This is not M2 acceptance and is not permission to deploy the
corpus.** What follows is the repaired manifest, the gate's own numbers, the limitations that
remain, and the options.

**Status, 2026-09-17: the corpus is frozen and generator repairs have stopped.** Option 3 was
taken - commission the independent read. No third round, no change to C1, no deployment, no
acceptance claim. The corpus's identity is recorded in
`benchmarks/gate/corpus-freeze-round2.json` and `python tools/gate/freeze_corpus.py --check`
against that file exits non-zero if any of it moves. Three corrections were made to this report
on the same date and each is marked in place: the exact-shape claim in §4, the standing of the
C1 argument in §4 and §5, and the framing of the two coverage-rule revisions in §6.

**What was frozen, precisely.** `tools/gate/content_gate.py` (`gate-1`, sha256
`3e08991c78eb5182…`), the solver `qf-1` (`queryfree.py` sha256 `afc77fcb5a0f3eb7…`), the
population, the scoring rule and the per-family denominators - all fixed before any generator
edit, recorded in `CONTENT_GATE_FREEZE_2026-09-16.md`, and neither gate nor solver touched
since; both hashes are re-emitted in all four result files.

**What was not frozen.** `coverage.RULES`. Eleven rules were added during the repair and two of
them were revised more than once while the work was in flight. §6 states that plainly and
preserves every superseded definition as runnable code. "The frozen criteria" in this report
means C1-C4 and the solver, and means nothing wider.

**The query-free solver is handed the correct conversation.** `select_within_thread` receives
the thread the declared evidence sits in and answers inside it. Its score is an upper bound on
register leakage *given perfect retrieval*, not a lower bound on anyone's difficulty.

**24/39 and 6/13 are not the same baseline and are never differenced.** The first is this
population - scored threads of the generated corpus, as the fifth independent read measured it.
The second is `qf-1` over the thirteen authored diagnostic cases. Different populations,
different denominators, different selection.

---

## 1. The verdict

| Criterion | Bar | Round 0 | Round 1 | Round 2 | Verdict |
|---|---|---|---|---|---|
| **C1** shape | every `(length, participants, senders, distinct hours)` maps to ≥2 families | 41 of 45 map to one | 41 of 44 | **36 of 41** | **FAIL** |
| **C2** no family solved outright | every scored family below 100% | 3 families at 100% | none | **none** | **PASS** |
| **C3** residual | ≤ 40% over the population | 18/41 = 0.439 | 10/41 = 0.244 | **10/41 = 0.2439** | **PASS** |
| **C4** independent read | a human YES | not run | not run | **not run** | **open** |

**Overall: FAIL, on C1, with C4 not yet attempted.**

Round 1 is the statistical pass; round 2 is the determinate repairs plus the shape work. There
is a third result file, `content-gate-round1b.json` at 12/41 = 0.2927, taken between them - the
determinate repairs alone moved the rate *up* at this seed while moving the six-seed mean down,
which is what an n=41 single-seed reading is worth. Both frozen hashes are identical in all
four result files, so every comparison here is made with the same instrument.

C3's 40% is the provisional engineering threshold this repair was approved against. It is not a
statistically established validity threshold: no power analysis stands behind it, and passing it
is not evidence the corpus is free of shortcuts.

## 2. What moved, measured over six seeds rather than one

One seed cannot separate a repair from an RNG reshuffle. Seeds 4311, 101, 202, 303, 777, 919 at
the `sample` profile, the frozen gate run unchanged on each:

| | before the repair | after |
|---|---|---|
| mean `qf-1` rate | 0.354 | **0.232** |
| mean families at 100% | 0.75 | **0.17** |
| worst seed | — | 0.293 |
| best seed | — | 0.171 |

Register separation, measured as the odds that an evidence message carries a hedge, proposal,
hearsay or reminder cue against the odds for every other message in a scored thread: **0.54 →
0.78** (1.00 is no separation). The cue itself is now on 3 of 39 evidence messages and 148 of
1,349 others.

## 3. The five determinate repairs

Each is a property of the text, each has a rule in `coverage.RULES`, and each rule has a
negative fixture in `tests/test_coverage_rules.py` that fails without it.
`RULES_WITHOUT_NEGATIVES` is empty and `test_every_rule_has_a_negative_fixture` is the gate on
that.

| Finding | What was wrong | Repair | Rule |
|---|---|---|---|
| **R-M2-067** | F11's trap ranked 5th in one of two instances, behind four ordinary fillers; the family exists to show a weak-hit escalation policy does not escalate, and what such a policy reads is the *best* hit | the trap is redrawn until it is rank 1 in the conversation **it ships as** - the trailing traffic is appended before the rank is established, not after; a fourth trap form quotes the question it answers | `f11_top` |
| **R-M2-068** | F17's reversal replied to whatever message preceded it (filler, in both instances), so the reply-chain floor had nothing to follow; F16's candidates differed in the figure *and* an ordinal the key named verbatim, which is F1's mechanism; F13's chain was said not to be realised | F17's reversal replies to the best-scoring reinforcement; F16's candidates carry no ordinal and the confirmation names the figure; F13's chain measured as already correct and now held by a rule | `f17_chain`, `f16_mechanism`, `f13_chain` |
| **R-M2-071** | twelve entity-free, digit-free scaffolding sentences occurred inside exactly one family each | F14's roster and address-change lines, F15's forward marker and F13's acceptance became shared banks; `chatter.FOIL_KINDS` draws them, and the `stale`, `dated_event` and `identity` banks, into ordinary traffic everywhere | `scaffolding_not_family_exclusive` |
| **R-M2-072** | F14 put every planted role at the same index in all eight instances and F2 in all ten; `trap_decoy` was 78% after 13:00 against 58% | layouts drawn (`spread`, and drawn filler inside F2's and F13's fixed skeletons); a timestamp collision rolls to the next day at the drawn hour instead of adding an hour; the opener's hour is drawn too | `role_positions_vary`, `hour_independent_of_role` |
| **R-M2-073** | F15's note claimed a "90-message ceiling" the corpus refutes; F2 put the superseded value on the newest message; F7's figure half carried no distractor; F12's construction query was its evidence sentence verbatim, answer included | note rewritten to what is true; F2's renderings swapped; F7's figure half gained a tabled estimate; F12's query is a quotable fragment with no declared value in it | `f15_split_cause`, `older_value_is_older`, `f7_halves_each_contested`, `f12_query` |

**Mechanism checks are scoped to each family's registered requirement.** None of them says a
question must have exactly one solution method. `f16_mechanism` says the *second* method F16
shipped with was a unique exact-match key; `f17_chain` says the route that family exists to test
must exist, not that no other route may.

### One repair found a defect that was not on the list

`t0041` in the gate profile declared `evidence_at: 2` and held a `trap_decoy` there. `_before`,
drawing a position earlier than an anchor, fell back to the whole thread when nothing fit
earlier - and had no reason to skip the evidence, because it was never told about it. Only F3
has a rule that looks. The repair is in two places: `_before` takes the positions its caller has
reserved, and **`place` refuses to write a non-answer-bearing line over an answer-bearing one**,
which makes the same defect a generation-time error in every family rather than in the one that
happens to check. `tests/test_evidence_position_is_not_overwritten.py`, 15 assertions including
a fixture that reproduces the unrepaired draw.

## 4. An argument that C1 cannot be met as written - which is a claim for the reviewer, not a finding

**This section is an argument, not an established impossibility, and it is the implementer's
argument about a criterion the implementer failed.** Treat it accordingly. No proof is offered
that no generator satisfying the registered family requirements can satisfy C1; what is offered
is a reason to doubt it and the measurements behind that reason. Whether the argument holds is
one of the four questions put to the independent corpus reviewer, and the reviewer is free to
reject it.

The argument. C1 asks that **no** `(length, participants, senders, distinct hours)` value map
to a single family. `length` is an exact message count, so satisfying C1 requires threads of
different families to collide on an exact count as well as on three other integers. With 41
conversations spread over 16 registered shapes - one of which is a 90-message family and
another a 4-to-20-message one - most threads will hold a tuple of their own however the
generator draws, and the statistic then reports granularity rather than leakage. The freeze
record flagged the concern before the work started; the shuffle baselines below are the
measurement of it.

What would falsify the argument: a generator that keeps every registered family requirement -
F3's sweep across a long conversation, F15's four structural shapes, F2's window with its
margins - and still lands every thread's exact tuple on a tuple another family also holds. That
has not been attempted and is not claimed to be impossible.

`tools/gate/shape_diagnostics.py` (**non-gating; C1 is unchanged and nothing here feeds it**)
reports the quantity C1 reaches for - bits the shape carries about the family - against a
shuffle baseline, because mutual information is biased upwards on a sparse table:

| view | before: MI / shuffled 95th | after: MI / shuffled 95th | excess over its own baseline |
|---|---|---|---|
| exact C1 tuple | 3.508 / 3.508 | 3.522 / 3.405 | 0.000 → 0.118 |
| coarsened shape | 2.556 / 1.989 | 2.316 / 2.196 | **0.567 → 0.120** |
| participants only | 1.597 / 0.992 | 1.202 / 1.116 | 0.605 → 0.086 |
| senders only | 1.580 / 0.997 | 1.259 / 1.095 | 0.583 → 0.164 |
| hours band only | 0.500 / 0.427 | 0.347 / 0.363 | 0.072 → **−0.016** |
| length band only | 1.161 / 0.787 | 1.073 / 0.734 | 0.374 → 0.339 |

Read the excess, not the raw number.

**Correction, 2026-09-17.** An earlier version of this paragraph said the exact tuple "carries
no more than a random relabelling of the same threads carries, before or after". The table
above refutes it: after the repair the exact tuple is **3.522 against a shuffled 95th of
3.405**, an excess of 0.118 at p=0.001. Exact-shape information exceeds its shuffle baseline.
What is true is narrower and is what the row actually shows: the exact tuple sits at 3.52 of a
3.72-bit ceiling and its *shuffle baseline* also sits at 3.41, so the margin available to any
repair is about a tenth of a bit - the statistic is close to saturated by how finely it
partitions the threads. At HEAD the excess was 0.000 and after the repair it is 0.118, so on
this measure the exact tuple became *slightly more* informative, not less, while the coarsened
shape became substantially less so. Both movements are inside a tenth of a bit and neither is
offered as a result.

On the coarsened shape, which is what a reader could actually observe, leakage fell by about
four fifths. Time-of-day is now at or below its own shuffle floor. Thread length is the
residual, and it is largely irreducible: F3 *is* the long-conversation family by registration.

## 5. Limitations that remain

1. **C1 is argued to be unsatisfiable while the families keep their registered shapes**, for
   the reason in §4. That is an argument put for review, not a demonstrated impossibility, and
   it comes from the party that failed the criterion. The criterion is frozen and unchanged.
2. **C2 is fragile at these denominators.** Eleven of fourteen scored families have n=2. At a
   0.23 base rate, the chance that at least one family of fourteen scores 2/2 by luck alone is
   about 40%. Across the six seeds a family hit 100% on two of them - a different family each
   time. Reading C2 on one seed is reading noise; the multi-seed mean (0.17 families) is the
   number worth quoting.
3. **The 40% ceiling has no power analysis behind it** and never did. It was approved as a
   provisional engineering threshold for this repair.
4. **The residual shortcut is not zero and will not go to zero.** A generator that writes a
   decisive sentence at all leaves *some* register signal. `qf-1` still scores 0.232 with the
   conversation handed to it.
5. **Two coverage rules cannot see small effects and say so.** `hour_independent_of_role` does
   not test a role carried by fewer than ten conversations;
   `scaffolding_not_family_exclusive` does not test a sentence appearing in fewer than three.
   Both limits are the corpus's size, not a choice about what counts.
6. **F17's `construction_query` is a message body verbatim**, which is the same circularity
   R-M2-073 named in F12 and which the approved scope did not cover. `_ranked_f17` therefore
   asks whether a reinforcement outranks the reversal on *its own text*. Open, unrepaired,
   recorded here rather than fixed outside the approved scope.
7. **The full 265-replant sweep was not re-run.** The 53 replants whose anchor file this work
   changed were run and all 53 were caught, 0 missed. The rest are unchanged files whose
   citations are green in the full suite.
8. **`coverage` reports the properties someone thought to check.** The previous version of that
   file passed a corpus an independent reader failed. C4 is still the gate.

## 6. Two coverage rules were revised mid-work. This is a methodology revision.

**The evaluation methodology as a whole was not frozen.** What was frozen, and verifiably so,
is the content gate and the query-free solver: `content_gate.py` (`gate-1`) and `queryfree.py`
(`qf-1`), whose sha256 digests are identical in all four result files. `coverage.RULES` was
*not* frozen. It was edited throughout the repair - eleven rules were added - and two of them
changed shape more than once while the work was in flight. Earlier statements in this report
about "the frozen criteria" refer to C1-C4 and the solver, and to nothing else.

Both revisions replaced a worse estimator with a standard one rather than a threshold with a
looser one. That is the implementer's account of them and it is a claim the reviewer should
test, which is why **every superseded definition is preserved as runnable code** in
`tools/gate/superseded_rules.py` and run against the frozen corpus beside the shipped one.

**What the superseded versions say about the frozen corpus** (`benchmarks/gate/superseded-rules-sample-4311.json`,
`…-gate-5309.json`):

| rule | version | sample-4311 | gate-5309 |
|---|---|---|---|
| hour | v1 message-level two-proportion | no finding | no finding |
| hour | v2 mean of per-conversation deltas | no finding | no finding |
| hour | v3 within-conversation permutation | no finding | no finding |
| hour | **shipped** Mantel-Haenszel | no finding | no finding |
| scaffolding | v1 messages vs message share | no finding | no finding |
| scaffolding | v2 conversations vs conversation share | **1 finding** (F3's "Flagging in case that moved.", p=0.008) | no finding |
| scaffolding | **shipped** conversations vs message share | no finding | no finding |

So on the corpus that is now frozen, **the revisions change nothing except one finding from the
version that was replaced for producing exactly that class of finding** - a long-thread family's
ordinary closing line, reported because a conversation-share null ignores that a ninety-message
conversation is ten times likelier to contain any given sentence than a nine-message one. The
revisions are not load-bearing for the round-two result. They were load-bearing *during* the
work, on intermediate corpora that no longer exist, and that is the part a reviewer cannot
reproduce and should not take on trust.

* `hour_independent_of_role` began as a message-level two-proportion test. Hours are drawn per
  `(conversation, position)`, so five revisions of one F16 schedule landing in the afternoon is
  one coincidence and not five, and the test reported a different set of roles at every seed. It
  is now **Mantel-Haenszel across conversations**: each conversation is a stratum, the null
  within it is the hypergeometric one exchangeability implies, and the statistic sums
  observed-minus-expected over strata. That is the textbook test for this shape and it weights a
  conversation by its information rather than by its existence.
* `scaffolding_not_family_exclusive` began by counting messages against a message-share null,
  then conversations against a conversation-share null. The first overstated evidence from one
  long thread; the second reported F3's ordinary closing lines, because a ninety-message
  conversation is ten times likelier to contain any given sentence than a nine-message one. It
  now counts **conversations** against a **message-share** null, which is the pair of units the
  two effects actually live in.

Both were re-specified against seeds 101-919 and the gate profile rather than against the frozen
seed's verdict, and C3 at seed 4311 is 0.2439 under either. But the honest statement of the risk
is this: **a rule revised by the person whose corpus it judges, while that corpus is being
repaired, is not an independent check of that corpus**, whatever the statistical merits. The
preserved definitions above are what makes the revision auditable instead of asserted.

## 7. Gates run

* full suite: 108 files, 107 green, 1 file collecting nothing (`test_new_operator_round19.py`,
  all tests deselected by marker - unchanged from before).
* `mypy server/src harness/src orivra/src`: clean, 200 files.
* `ruff`: `E501` + `F841` in `seed/` is 33, the same count as at HEAD. The `B023` diagnostics
  rose from 38 to 51 - the same shape as the existing ones, from the new drawn-layout closures,
  and `tests/test_corpus_redraw_closure_binding.py` was extended to cover `redraw_until_top`
  alongside `redraw_until_ranked` so the new ones are held by the same three tests.
* replants: 53 of 53 targeted, all caught.

## 8. The decision, and the options

**Decided 2026-09-17: option 3.** The corpus is frozen as it stands and goes to an independent
reader. C1 is unchanged, no third round is run, nothing is deployed and nothing is accepted.
Two review packages are commissioned and run in parallel:
`CORPUS_REVIEW_PACKAGE_2026-09-17.md` and `RUNNER_REVIEW_PACKAGE_2026-09-16.md`.

The three options as they stood:

**The repaired corpus does not pass the frozen gate.** Under the approved stopping condition,
work stops here rather than continuing to a third round.

Three options, none of which is implied by the numbers above:

1. **A narrower release.** Ship the corpus for the families whose registered mechanism is now
   held by a rule with a negative fixture, and exclude the shape claim from what the corpus is
   said to support. C2 and C3 pass; C1 is a claim about Tier-1 redacted observables that this
   corpus cannot make.
2. **A revised evaluation.** Re-register C1 on the coarsened shape with a shuffle baseline -
   the quantity `shape_diagnostics.py` already reports - and re-run. This is a change to the
   criterion, it should not be made on the implementer's argument alone, and it needs the same
   pre-registration discipline the first one had: written and hashed before the next generator
   edit.
3. **Stop and commission the independent read (C4) anyway.** *(Taken.)* C4 is the criterion the
   whole gate was built to support, it has never been attempted, and a reader's verdict on the
   repaired corpus is information neither C1 nor C3 can give. It does not turn a FAIL into a
   PASS.

The corpus is **not** approved for mailbox deployment. No mailbox writes, deletions or
reseeding were performed, no product code was changed, and A16 stays closed.

## 9. Files

| | |
|---|---|
| frozen gate | `tools/gate/content_gate.py`, freeze record `docs/reviews/CONTENT_GATE_FREEZE_2026-09-16.md` |
| results | `benchmarks/gate/content-gate-round1.json`, `content-gate-round1b.json`, `content-gate-round2.json` |
| non-gating diagnostic | `tools/gate/shape_diagnostics.py`, `benchmarks/gate/shape-diagnostics-round2.json` |
| rules and fixtures | `harness/src/mailweave_harness/seed/coverage.py`, `tests/test_coverage_rules.py` |
| the out-of-scope repair | `tests/test_evidence_position_is_not_overwritten.py` |
| approved proposal | `docs/reviews/CORPUS_REPAIR_PROPOSAL_2026-09-16.md` |
| corpus freeze record | `tools/gate/freeze_corpus.py`, `benchmarks/gate/corpus-freeze-round2.json` |
| superseded rule definitions | `tools/gate/superseded_rules.py`, `benchmarks/gate/superseded-rules-sample-4311.json`, `…-gate-5309.json` |
| corpus review package | `docs/reviews/CORPUS_REVIEW_PACKAGE_2026-09-17.md` |
| runner review package | `docs/reviews/RUNNER_REVIEW_PACKAGE_2026-09-16.md` |
