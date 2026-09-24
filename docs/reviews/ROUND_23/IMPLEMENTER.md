# ROUND 23 — implementer's report

**WS-11: representation and query-aware disclosure.** Fourth of OD-6's five workstreams to the
usable milestone. Written after the gates at the end of this file were run.

Every sentence here that says "executed" names the file and the assertion. Where I could not
establish something I say so under its own heading rather than leaving the silence to be read as
agreement.

---

## Part 0 — what this round is, and the one thing that changed my design mid-round

The work order says this round builds the claim rather than machinery. The claim is that what a
response discloses about a thread depends on what was asked, and the thing to beat is a fixed ±2
window around every hit.

**I built the policy, found that it was the baseline, and fixed it.** The first working version of
the E4 fill admitted any candidate whose score was above zero. Two of the five published components
— `position_adjacency` and the "near a hit" half of `temporal_proximity` — fire without reading
anything the caller wrote, so for a query that names one term and nothing else, "score above zero"
selected exactly the positions within ±2 of every hit. That is Baseline F, emitted under the
query-aware policy's name, and it is DISC-01's degenerate strategy verbatim ("a fixed ±2 policy
fails DISC-01 by construction").

It would have shipped unnoticed. It passed every test I had written at that point, its reason
strings named mechanisms, and the two arms agree on the easy cases. What surfaced it was an
*existing* round-19 test — `test_a_stub_row_states_the_region_its_own_labels_place_it_in` — going
red because rows it expected as stubs had become `Role.CONTEXT` fill rows for no reason the query
gave. A test written for provenance caught a disclosure degeneracy, which is the argument for
keeping non-vacuity guards in old tests.

The repair is `ADMITTING_COMPONENTS` (`disclosure/weights.py`): **a score above zero is necessary
and not sufficient.** A row is filled only when at least one component *anchored in what the query
wrote* fired — an address the query named, a term it wrote, or its own parsed date window. The other
components keep their published weight and rank the admitted rows; they no longer admit any.
`WindowOffset` remains the reason kind for a positional inclusion, and it belongs to Baseline F.

**This is an addition to AD A.9(3)'s published policy**, argued in `weights.py` and recorded here as
such, in the shape round 22 used for `NotTriedWhy.STOPPED_ON_EVIDENCE`. A.9(3) lists five components
and no admission threshold; the threshold is mine. It narrows what the policy discloses and it is
the difference between the thesis and its baseline, so it should be attacked first.

---

## Part 1 — the new package

`server/src/mailweave/disclosure/` — 1,930 lines: six modules (1,776 lines) plus the package's own
`__init__.py`. Split by what each module is allowed to decide.

| Module | What it decides | Lines |
|---|---|---|
| `weights.py` | the published E4 table, the five components, the admission rule | 302 |
| `floor.py` | the E2 floor and, in one function, **the promotion rule** | 218 |
| `layout.py` | the immutable shape the ladder shrinks, and the one cost estimate | 229 |
| `ladder.py` | A.9a's eight-step precedence as data, and the driver's two gates | 533 |
| `plan.py` | A.9's four tiers into a layout, for either arm; DISC-04's efficiency | 399 |
| `segments.py` | AD §E.2's experimental second navigational level | 95 |

Two new closed vocabularies live in `envelope/vocab.py` rather than in the package —
`FillComponent`, `FloorRelation`, `FloorDependence` — because a reason string a caller branches on
is part of the wire schema, and a schema that imported a policy module would make the wire's
vocabulary depend on how the policy is currently tuned.

Two new `ReasonKind` members, `query_score_fill` and `floor_promoted`, and both exist because WS-11
makes a claim no field carried. Without `components`/`score` a filled row's reason is a sentence
rather than a mechanism a reader can recompute (DISC-01). Without `dependence` a promoted floor
member is byte-identical on the wire to one the promotion rule refused, which is the whole of the
distinction OD-3 draws. The field census moves 236 → 243 and the number is pinned in
`tests/test_field_census.py` with the derivation written out.

### What each test establishes

`tests/test_disclosure_round23.py`, 67 tests. Grouped by what they are evidence *for*:

* **the weights are fixed and published** — `test_the_published_weights_are_the_ones_the_round_report_publishes`
  pins all five values, so a benchmark-driven retune is a visible edit to a test;
  `test_every_published_component_carries_a_published_weight` keeps the table total over the
  vocabulary; `test_every_component_fires_on_its_own_trigger_and_is_silent_without_it` reaches all
  five and their negations from one neutral candidate, so neither a component nobody can trigger nor
  a `components_of` that returns everything survives;
* **the policy is not the baseline** — `test_a_row_no_anchored_component_reached_is_not_filled`
  builds the exact degeneracy above (two positions from a hit, an hour away, score 5) and asserts
  it is refused; `test_the_temporal_component_anchors_only_on_the_querys_own_window` separates the
  component's two disjuncts;
  `test_two_materially_different_queries_produce_different_representations` is DISC-01 at the policy;
* **the promotion rule** — see Part 3;
* **floor membership survives every step** — see Part 4;
* **self-truncation before host truncation** —
  `test_the_ladders_measure_and_the_envelopes_measure_are_the_same_number` builds a real `Envelope`
  through `DispositionLedger.certify` and asserts `measure_tokens(envelope) == layout.cost()` on
  three shapes; `test_an_assembled_response_never_exceeds_the_ceiling_it_declares` asserts the
  artefact;
* **the two arms at equal budget** — Part 5;
* **the segment map** — four tests, Part 6;
* **the shipped path** — four end-to-end tests through the real client, the real transport and the
  real `assemble`, asserting the wire reasons, the depths, the `ceiling{}` block and the cap list.

### What I could not establish in Part 1

* **`E4_TEMPORAL_PROXIMITY_SECONDS` is derived, not measured.** It is one day because Gmail's date
  operators are day-granular (AD A.6), so a day is the finest interval a query can express. That is
  an argument, not a measurement; nothing in this build measures whether a day is the right window.
  WS-16/WS-17.
* **The score has no measured relationship to relevance.** It is a mechanical sum of five
  predicates. Whether the ordering it produces is better than the baseline's is DISC-02's question
  and this round does not answer it — it makes it runnable.

---

## Part 2 — the A.9a ladder, and how the precedence is kept honest

`LADDER_STEPS` is **data**: a tuple of `Step(precedence, name, apply)` where every `apply` is a total
function `(Layout, Ceilings) -> Layout`. `run_ladder` iterates it, stops as soon as the layout fits
the ceiling it has declared, records each step that changed something as a `LadderStep` with a
mechanical detail line, and applies **two gates to the output of every step**.

`test_the_published_precedence_is_the_one_the_architecture_prints` reads
`docs/ARCHITECTURE_DECISION.md`, extracts A.9a's own numbered code block, and asserts the eight
entries against `LADDER_STEPS` by number and by phrase. Two rounds of this project have got a
published order wrong by transcribing it, so this one is checked against its authority.
`test_the_published_ceilings_and_body_budgets_are_the_documents_own` does the same for 600 / 250 /
9,000 / 12,000.

`DISCLOSURE_TOP_K_HITS` — step 3's protected hit count — is **not a new number**: it is A.7's
published `max_body_fetches` at L0 (5), so no figure enters the system that could have been chosen
after seeing a benchmark. Which hits are the top *k* is decided by the published E4 score, ties by
thread position: deliberately not by recency, which EV-02's guard names, and not by Gmail id, which
would be a coin flip presented as a ranking (RANK-03).

**What the ladder produces on OD-3's own case.** Forty messages, six hits, bodies fetched for the
whole thread:

```
disclosed 7,760 whitespace tokens against the 9,000 normal ceiling; ladder steps fired: none
floor 11 members — 5 promoted (quotation), 6 refused
context efficiency vs the full dump: 7,760 / 36,000 = 0.216; relevant-token fraction 0.881
```

The ladder terminates on it without firing, which is stronger than A.9a's own re-derivation, and the
reason is OD-3's split: the document's arithmetic put ~18 floor messages at body depth, and the
promotion rule puts six of eleven at snippet.

### What I could not establish in Part 2

* **The token count is an estimate, and it is named as one everywhere.** DISC-04's pinned tokenizer
  is registered at G0; `measure_tokens` and `layout_tokens` are whitespace counts. What I *did*
  establish is that the two are the **same** estimate, which is the property DISC-06 actually needs.
* **`measure_tokens` does not count `withheld[]`, `not_included_sources[]` or `retrieval_report`.**
  That is inherited from WS-03 and it has a consequence I should name: A.9a step 7 always reduces the
  measured size, because splitting a source removes its rows and adds withheld records the estimate
  does not see. On a real wire the records cost tokens. This makes step 7 look cheaper than it is,
  and it is the first thing to re-check when PF-6's tokenizer lands.

---

## Part 3 — the promotion rule, stated once, and the case where it says no

> **A floor member is promoted above its base depth only when the evidence message it hangs off
> cannot be read without it.** Dependence is one of exactly three mechanical relations, tested in
> this published order, and the first that holds is the one recorded:
>
> 1. **`quotation`** — the member is the evidence message's *reply parent*, and the evidence's own
>    annotated body carries a `quoted` or `forwarded` span (A7). The evidence's text incorporates
>    text it did not write, so reading it at body depth while its parent is a snippet is reading half
>    a quotation.
> 2. **`contradiction`** — the member is a *direct child* of the evidence and the text this response
>    observed for it carries a token of A.8a's published decision lexicon. This is T-CD2's shape: the
>    quiet later reply that reverses.
> 3. **`constraint_carrier`** — the member satisfies a constraint of the *query* that the evidence
>    message does not. Gmail evaluates `q` message-scoped (RO F2), so a thread can answer a
>    two-condition question with two messages and no single message matches.
>
> A floor member for which none holds stays at its base depth and says so.

Base depth is `snippet` where this response observed text and `stub` where it did not — never below,
which is where A.9a's honesty note puts the floor's bottom.

### Where it says no

`test_the_promotion_rule_refuses_an_ordinary_adjacent_reply`. A **direct child of the evidence**,
already present by the floor's absolute membership guarantee, one position away, whose text this
response holds, and cheap to promote — *refused*. It carries no decision cue, it covers no constraint
its parent misses, and the quotation clause is about parents. Saying yes there would have been the
easier code and the easier sentence, and it would have made the E2 floor a window of unbounded
radius with a query-aware name.

The refusal is not an edge case. On a twelve-message chain with three hits
(`test_the_rule_says_no_at_least_as_often_as_yes_on_an_ordinary_thread`) the rule promotes three of
six; on OD-3's forty-message case it promotes five of eleven; in the end-to-end fixture it promotes
two of two floor members and refuses the fourth message, which is not a floor member at all.

`test_the_promotion_rule_matrix_reaches_every_answer_it_asserts_about` checks the matrix's keys
against `{*FloorDependence, None}` and **executes every row**, so a clause that could never fire, or
an answer no input reaches, fails rather than being asserted about here.

Three further tests pin the ways the rule must not overreach:
`..._refuses_a_parent_whose_child_quotes_nothing`, `..._refuses_a_parent_whose_body_was_never_fetched`
(an absent input is an absence, never a negative claim), and
`test_a_promoted_member_is_still_only_promoted_to_text_that_exists`.

### What I could not establish in Part 3

* **Whether promotion improves an answer.** Three dependences are three hypotheses about what an
  agent needs. F17 at each tier decides that; this round builds the hook.
* **`contradiction` depends on the decision lexicon reaching quote-stripped text.** PF-13 measures
  that lexicon's base rate for `answer_type_presence`; nothing measures it here. If the lexicon is
  inert on real mail, clause 2 is inert with it, and that is a stated risk of the design rather than
  a hidden one.
* **A promoted floor member whose body was never fetched stays at `snippet`.** Thread maps are
  fetched with `format=metadata`, so only evidence messages have bodies. Promotion therefore decides
  *whether* and the observation decides *how deep*, and in the shipped path a promoted parent is
  commonly a snippet with an affordance rather than a body. Closing that needs a budgeted body fetch
  drawn from A.7's `max_body_fetches` remainder; I did not build it, because disclosure initiating a
  fetch is exactly the escalation T-CD3 forbids and doing it properly is a budget decision that
  belongs with WS-10's accountant. **This is the largest gap in the round** and it is named again in
  Part 9.

---

## Part 4 — floor membership survives every degradation step

**The gate lives in the driver, not in the steps.** `assert_floor_intact` and
`assert_nothing_vanished` are called by `run_ladder` on the output of every step it is given,
whatever it is given. A check written inside a step is a check the ninth step can be added without;
a check in the driver covers step nine the day it exists. That is this round's answer to "one shape
validated, peers trusted": the eight steps do not each get their own defence, they share one.

**Each step's removal of a floor member, planted and refused.**
`test_every_ladder_step_is_refused_when_it_drops_a_floor_member` is parametrised over
`LADDER_STEPS`: for each of the eight, the step is wrapped in a variant that does its own work and
then removes one floor member, and the driver refuses it with `FloorMembershipLost` naming the
step's precedence. `test_every_ladder_step_is_refused_when_it_drops_a_message_without_a_record` does
the same eight times for contract I-1's half. `test_the_unplanted_ladder_is_not_refused_on_the_same_input`
is the control, and the fixture is asserted oversized where it is used, so a fixture that quietly
starts fitting cannot make sixteen plants pass vacuously.

Two of the steps also refuse *inside themselves* — step 7 never picks a source holding a floor
member, step 8 never picks a floor member — and both refusals are separately planted (replants R71,
R72). A step that knows it must not take something should not try; the gate is what catches the day
somebody edits it.

---

## The commonality across the disclosure shapes, and proof the matrix reaches them

**The shape space** the work order names is eight steps × two ceilings × floor-or-not.

**The commonality** is the driver. Whatever a shape's size, its ceiling, its step sequence or its
floor, five things hold, and each is a way the ladder could be dishonest:

1. the response fits the ceiling it declares (DISC-06);
2. every floor member is present, as a row or a declared collapsed-run member (OD-3);
3. every accounted message is present or carries a withheld record (contract I-1);
4. the steps that fired are in the published order and none fired twice (A.9a);
5. the overflow ceiling is applied only where there is a floor to protect.

**The test** is `test_every_disclosure_shape_keeps_the_five_properties_that_make_the_ladder_honest`,
run over the shape matrix, plus `test_the_ladders_invariants_hold_over_generated_shapes`, a
Hypothesis sweep over threads whose size, hit density, text and body availability the generator
chooses rather than a fixture author. `test_a_step_only_ever_lowers_a_rows_depth` adds monotonicity:
no step may deepen a row, at any ceiling, in any shape.

**Proof the matrix reaches them.** `test_the_shape_matrix_reaches_every_step_and_both_ceilings`
asserts, over the same set the property sweep runs on, that every one of the eight steps fires
somewhere, that both ceilings are applied, that a floor-bearing and a floor-free response are both
present, that a split and a withheld record both occur, and that the declared inability is
reachable. The matrix, printed from the code:

```
shape                             steps        ceiling  floor  split  withheld  tokens  exhausted
fits_without_the_ladder           []              9000   True      0         0     245      False
no_floor_at_all                   []              9000  False      0         0     305      False
fill_and_sibling_runs             [1, 2]          9000   True      0         0    7390      False
hit_and_floor_bodies              [3, 4]          9000   True      0         0    8880      False
hit_thread_stub_runs              [5]             9000   True      0         0     120      False
overflow_for_floor_membership     [6]            12000   True      0         0   10740      False
split_by_source                   [5, 6, 7]      12000   True      1        60   10740      False
withheld_by_ceiling               [6, 8]         12000   True      0        39   11980      False
floor_alone_exceeds_the_overflow  —                  —   True      0         0       —       True
```

Round 21's R-RETR-058 was a matrix that asserted about shapes it never built. This one is asserted to
reach what it asserts about, and the reach assertion runs on the *same* tuple the property sweep
consumes, so they cannot drift.

**Two facts the matrix taught me, which I would not have written down otherwise.**

* **Step 7 is reachable only when a floor-free source exists.** A response every one of whose sources
  carries floor members cannot be split at all, and goes straight to step 8. That is a consequence of
  the guarantee rather than a defect, and it is why the matrix needs a hit-bearing thread whose
  members name no reply parents (`flat_thread`) to reach step 7 at all.
* **The overflow ceiling can defeat a low ceiling in a test.** Setting `normal` low while leaving
  `overflow` at 12,000 makes step 6 raise past the tier under test, so the "tier" is silently the one
  above. `DEPTH_TIERS` sets both together and says why.

---

## The published E4 weights, and why each is what it is

| Component | Weight | Why that, and why there |
|---|---|---|
| `participant_match` | **5** | The only component computed from a header **Gmail states** about this message — its own `From`/`To`/`Cc` — matched against an address the *query named*. Most query-driven, least text-dependent, and available on a row held only as a stub, so it does not get stronger because a message happened to have its body fetched. |
| `term_overlap` | **4** | The query's own words, as query-driven as the above, and below it for one mechanical reason: a term can land in text this message **quoted** from another, so a term match is evidence about the thread as often as about the message. An address cannot be borrowed that way. |
| `temporal_proximity` | **3** | Partly query-driven — it fires on the query's own parsed date window as well as on nearness to a hit — and partly structural. Below the two that are wholly query-driven, above the one that is wholly structural. |
| `position_adjacency` | **2** | Structural, query-conditioned only through the hit it measures from. Its radius is **pinned to Baseline F(±2)'s own radius**, so the query-aware arm gets no more structural reach than the baseline does and a measured win cannot come from a wider window. |
| `decision_cue` | **1** | The **only** component that fires identically for every query against a given mailbox. A query-independent component that could outrank a query-derived one is a policy that looks adaptive and is not, which is DISC-01's guard. It therefore carries strictly the least weight of any component: it can break a tie and can never by itself order one candidate ahead of another the query reached. |

Small integers, because the score is compared and rendered and never interpolated: integer arithmetic
makes ties exact rather than float-adjacent, so the ordering of two candidates cannot depend on the
platform's rounding.

Three of these are executed rather than argued.
`test_no_query_independent_component_can_outrank_a_query_derived_one` is
`max(weight of query-independent) < min(weight of query-derived)`.
`test_the_adjacency_radius_is_the_baselines_own_radius` is `E4_ADJACENCY_POSITIONS == FixedWindow().radius == 2`.
`test_the_published_weights_are_the_ones_the_round_report_publishes` pins the table, so this document
and the code cannot disagree.

Reason strings come from the closed vocabulary: `QueryScoredFill` carries `tuple[FillComponent, ...]`
and an integer and **no string parameter at all**, so there is no field on it a caller's text can
reach. `tests/test_wire_retention_round10.py` used to assert that every reason kind has a string
parameter to sweep; it now asserts that a kind with none is built only from closed types — a stronger
statement than the sweep it replaces, rather than an exemption from it.

---

## Every docstring claim about what disclosure guarantees, executed

`tests/test_lexical_ladder.py::test_every_test_a_source_docstring_names_exists` reads every string
constant in both source trees and requires every `test_...` identifier in them to resolve. It went
red four times while I wrote this round, which is the mechanism working. The claims:

| Claim, and where it is written | Executed by |
|---|---|
| `weights.py`: "a query-independent component can never by itself order one candidate ahead of another that the query reached" | `test_no_query_independent_component_can_outrank_a_query_derived_one` |
| `weights.py`: the table is total over the vocabulary | `test_every_published_component_carries_a_published_weight` |
| `weights.py`: admitting on structural components alone *is* Baseline F | `test_a_row_no_anchored_component_reached_is_not_filled` |
| `floor.py`: "the rule is written so that the ordinary neighbour is refused" | `test_the_promotion_rule_refuses_an_ordinary_adjacent_reply` |
| `floor.py`: a clause whose input is absent does not fire negatively | `test_the_promotion_rule_refuses_a_parent_whose_body_was_never_fetched` |
| `layout.py`: the ladder's measure and the envelope's are one measure | `test_the_ladders_measure_and_the_envelopes_measure_are_the_same_number` |
| `ladder.py`: "the gate is the driver's, so it covers a step nobody has written yet" | `test_every_ladder_step_is_refused_when_it_drops_a_floor_member` (×8) |
| `ladder.py`: the precedence is the document's | `test_the_published_precedence_is_the_one_the_architecture_prints` |
| `ladder.py`: the top-k is a published cap, not a new number | `test_the_protected_hit_count_is_a_published_cap_and_not_a_new_number` |
| `ladder.py`: "the overflow is not a budget" | `test_the_overflow_ceiling_is_reachable_only_for_floor_membership` (three branches, with a positive control) |
| `ladder.py`: an inability is declared, never shipped oversized | `test_the_ladder_declares_an_inability_rather_than_shipping_an_oversized_response` |
| `plan.py`: "Baseline F is a `Selector` in this module, runnable at any radius, under the same ceiling" | `test_the_fixed_window_baseline_runs_through_the_same_ladder_at_the_same_ceiling`, `test_the_baseline_runs_at_every_radius_it_is_a_baseline_at` |
| `plan.py`: "nothing in the query-aware arm gets a token the baseline could not have" | `test_the_baseline_is_not_handicapped_by_the_planner` |
| `plan.py`: the floor is not scored and does not compete with the fill | `test_a_floor_member_is_never_scored_by_the_fill` |
| `segments.py`: built, labelled, and neither number invented | `test_the_segment_map_is_labelled_experimental_and_derives_its_boundary` |
| `segments.py`: temporal, so an unbroken conversation is one segment | `test_segments_are_temporal_and_a_thread_that_never_paused_is_one_segment` |
| `assemble.py`: "nothing about depth is decided in this module" | `test_the_shipped_path_promotes_the_floor_members_the_evidence_depends_on` + replant R76 |
| `builder.py`: `truncated_by` is a claim that something was removed | `test_a_ladder_step_that_removes_nothing_does_not_claim_a_truncation` |

One claim I **removed** rather than executed: `assemble.py`'s module docstring said "It is still
deliberately **not** WS-11's disclosure ladder" and "It applies no A.9a degradation ladder and no
token-budget arithmetic." Both became false in this round, so both are rewritten rather than left as
a claim narrower than the code.

---

## Part 5 — the two arms, at equal budget

DISC-02 requires the shipped policy and Baseline F(±2) to be compared at *equal token budget*,
"asserted by the harness from measured tokens, not from configuration". The only way to make that
structurally true rather than carefully arranged is to give both arms one code path and let them
differ in exactly one object.

`Selector` is that object. `QueryAwareFill` and `FixedWindow(radius)` are the two implementations;
everything else — the evidence tier, the E2 floor, the promotion rule, the A.9a ladder, the ceilings,
the cost estimate — is shared. `test_the_fixed_window_baseline_runs_through_the_same_ladder_at_the_same_ceiling`
asserts the two arms agree on ceiling, floor and present set and differ on the fill.
`test_both_arms_fit_the_same_ceiling_on_the_same_input` is the Hypothesis version.

**Nothing is shaped to disadvantage the baseline.** `test_the_baseline_is_not_handicapped_by_the_planner`
asserts that on a one-term query at ±2 the baseline fills **at least as many rows** as the shipped
policy does — which is currently strictly more, because the shipped policy refuses the rows the
baseline takes on position alone. `E4_ADJACENCY_POSITIONS` is pinned to the baseline's radius, and
`test_the_baseline_runs_at_every_radius_it_is_a_baseline_at` runs ±1/±2/±5 as PROC-04 requires them
to remain runnable. arXiv 2607.17598 remains runnable against this build for the same reason: nothing
in the planner knows which arm it is serving.

**The F17 hook.** `test_the_reversing_reply_is_present_at_every_degradation_tier` is parametrised
over the three tiers A.9a names — floor at `body_clean`, head-truncated, and `snippet` — and asserts
in **both arms** at each tier that the reversing child is present, that the floor is intact, and that
the response fits. `test_the_three_depth_tiers_are_actually_distinct_on_the_same_thread` proves the
three tiers are three, so the parametrised test is not one tier run three times.

**Context efficiency** (DISC-04) is `efficiency()`, computed from the same estimate the ceiling is
enforced with. On the 40-message case: 7,760 disclosed against a 36,000-token dump (0.216), relevant
fraction 0.881. Reported as numbers, not as a verdict — the bars are `[INHERITED — EP §13.4 CG-PD]`
and this module does not carry them, because a module that carried a bar is a module that can be
tuned to it.

### What I could not establish in Part 5

* **The comparison itself.** I built both arms and the equal-budget property; I did not run F17, and
  I did not produce a budget–recall curve over ≥3 matched budget levels. That is WS-16 and EP §7.2.
* **`full_dump_tokens` is the dump *for this run*.** It counts each message at whatever depth this
  response holds — a fetched body, else a snippet, else nothing — because it cannot count text
  nothing fetched. Against Baseline B proper (every message at body depth) the ratio would be
  smaller, i.e. this figure is conservative in the direction that does not flatter MailWeave. Still,
  it is not the DISC-04 number and must not be quoted as one.

---

## Part 6 — the segment map (AD §E.2, experimental)

Built, labelled `SEGMENT_MAP_IS_EXPERIMENTAL`, and removable in one edit: `segment_of` returns `None`
for every thread below the boundary and a `None` segment simply does not appear in a collapsed run's
affordance arguments, which is DISC-05's depth-*n−1* arm reached from the same code path rather than
hypothetically.

Neither number is invented. The boundary is `NORMAL_CEILING_TOKENS // STUB_ROW_TOKEN_ESTIMATE` = 225,
derived from two published figures that PF-6 sets. The discontinuity that ends a segment is
`E4_TEMPORAL_PROXIMITY_SECONDS`, reused rather than duplicated. Segmentation is **temporal** (A.9(6)
puts it under E3), so a thread that never paused is one segment however long it is — the honest
answer, since there is no second navigational level to offer over a conversation that never stopped.

### What I could not establish in Part 6

DISC-05's comparison. EP §7.5.1's depth arm needs threads at and above the PF-6 boundary and a
measured win; this round makes the level exist and makes it removable.

---

## Part 7 — the shipped path

WS-11 is wired into `assemble`, not built beside it. The sequence is now: map the hit-bearing
threads → L4 → project each mapped thread to a `ThreadInput` → `disclose()` once over the whole
response → materialise `Source`s from the resulting layout. `_rows_of` reads the planned depth, the
planned text and the planned reductions; it decides none of them.

Four end-to-end tests run through the real `GmailClient`, the real retry ladder, the real egress
allowlist and an `httpx.MockTransport`, on a thread where the hit quotes its parent and a later reply
reverses the decision. They assert on the **disclosed payload**: `FloorPromoted` with
`dependence=quotation` on the parent, `FloorPromoted` with `dependence=contradiction` on the child,
an ordinary later reply left as a stub, `QueryScoredFill` whose `score` equals the sum of the weights
of the components it names, and the `ceiling{}` block.

Two smaller behaviours the integration needed and that are recorded rather than absorbed:

* **`truncated_by` is not set by step 6 alone.** Raising the declared ceiling removes nothing, and
  `Envelope` refuses a truncation claim with no A.9a artifact behind it — correctly. Without the
  distinction a response whose only step was the overflow would be unbuildable.
  `_the_ladder_removed_something` carries it; `DECLARED_OVERFLOW_STEP` names the 6.
* **`budget_caps_hit` gains `disclosed_token_ceiling`** when the ladder fired, because a reader
  looking for "what cost me content" reads the cap list and the ladder is a cap like any other.

### PART-05 and EV-03, which the work order names alongside the DISC criteria

Both are shapes rather than numbers, and both are produced by the ladder rather than asserted
beside it.

* **PART-05 — withheld content is a shape, not a number.** A collapsed run is a `CollapsedRun`
  carrying `positions`, `count`, **`member_ids`** and an expansion affordance, so a reader can
  compute the disclosed set from the response alone and a bare "N omitted" is unconstructible.
  Positions are 0-based, contiguous, and bounded by `stated_total` (amendment A3): `PlannedRun`
  refuses a reversed or mis-counted run at construction, `Source` refuses one that leaves the
  thread or collides with a row, and `included` counts rows **plus** run members (amendment A4), so
  `included == stated_total` remains the map-carrier guarantee stated as a number. The collapse
  steps take only rows already at `stub` depth, which is why a floor member is never collapsed out
  of a depth it had earned.
* **EV-03 — nothing is dropped between retrieval and representation without a record.** The two
  steps that remove anything, 7 and 8, file a `withheld` record per accounted id with cap
  `disclosed_token_ceiling`, a `why` naming A.9a, and an executable
  `mailweave_thread_map` / `mailweave_get_messages` affordance. I did not write the accounting:
  `DispositionLedger.certify` computes `withheld := H − disclosed` and `Envelope` refuses a
  response whose emitted withheld list is not that set difference. `assert_nothing_vanished` is the
  same rule applied one layer down, at each step, so a loss fails where it happens rather than at
  assembly.

### One behaviour change to an existing test, named rather than absorbed

`test_a_hit_beyond_max_body_fetches_is_a_stub_row_and_not_a_withheld_record` asserted that a capped
hit is a **stub**. It is now disclosed at whatever depth the text this response holds supports —
`snippet` where the observation carried one — because a depth is a statement about text that exists
and disclosing a snippet as a stub understates the payload. The property the test is named for is
unchanged and is what it now asserts: reduced in depth, never withheld, with the affordance that
fetches the rest.

---

## Have I trusted a peer?

Yes, in three places, and here they are.

1. **The eight steps share one defence, and I did not write a per-step gate.** That is the design and
   I argue for it, but it means the *quality* of each step's own internal logic is defended by the
   property sweep and the reach matrix rather than by eight bespoke tests. If step 3's ordering were
   wrong — say it protected the *worst*-scoring hits — every gate and every property would still
   pass. What catches that is `test_a_step_only_ever_lowers_a_rows_depth` (partially) and the
   shape matrix's per-step reach (partially). **A reviewer should attack step ordering inside a
   step, not membership across steps.**
2. **`_degrade_band`'s "worst first" is one ordering, tested at one level.** It is
   `(fill_score ascending, position descending)` and it is the same function for steps 1, 3 and 4.
   I tested that the ordering exists and that it is deterministic; I did not test that it degrades
   the right row first on a case where two candidates tie on score and differ in what a reader needs.
   Ties are broken by position, which is a fact of the thread rather than a judgement, and that is as
   far as I can defend it without a relevance measurement.
3. **`FixedWindow`'s offsets are mapped into the same score space so both arms share the ladder.**
   `_score_of` inverts `abs(offset)` so "nearer the hit" sorts like "scored higher". That mapping is
   mine, it is documented where it happens, and it is the one place the baseline's data touches the
   shipped policy's machinery. If it is wrong, the two arms degrade in different orders and DISC-02's
   comparison measures the mapping. It is tested only indirectly, by
   `test_both_arms_fit_the_same_ceiling_on_the_same_input`.

And one place I *stopped* trusting a peer mid-round: the first version of replant **R72** removed
step 8's `and row.id not in working.floor_ids` clause and reported CAUGHT would have been impossible
— a hit is never a floor member, so the clause is a no-op on its own and the plant introduced
nothing. The manifest now widens the candidate set instead, and the comment says why. R69's second
citation was likewise removed: the shipped-path test does not catch a rule that promotes everything,
because that fixture's only floor members are the two the rule already promotes. **A citation that
does not catch is worse than no citation**, which is R-RETR-061.

---

## Anything unreachable, with its workstream, and whether it blocks integration under OD-6

| Unreachable | Why | Workstream | Blocks OD-6? |
|---|---|---|---|
| Promotion to `body_clean` for a floor member whose body was not fetched | Thread maps use `format=metadata`; only evidence messages have bodies. Promotion decides *whether*, the observation decides *how deep* | needs a budgeted fetch drawn from A.7's `max_body_fetches` remainder — WS-10's accountant + WS-11 | **No.** The row is present, at snippet, with an executable `mailweave_get_messages` affordance. It narrows what the floor delivers today and it is declared in place |
| Semantic reuse in the E4 fill (T-CD3) | L5 does not exist, so there are no vectors to reuse. `score.basis` and `ordering_effect: false` have no producer | WS-08/WS-09 | No |
| DISC-02's actual comparison, DISC-04's bars, DISC-05's depth arm, F17 | Each needs the harness and the registered G0 numbers | WS-16, WS-17, G0 | No — this round makes all four *runnable* |
| The pinned tokenizer | Registered at G0; PF-6 sets both ceilings | R0-PF | No, but every token figure in this report is an estimate until it lands |
| `not_included_sources[]` from step 7 on the shipped path | Reachable in the layout and asserted there; the shipped path has never produced a response large enough to split, because `max_hit_threads` caps at 12 threads and `format=metadata` keeps bodies scarce | WS-16's corpus | No. The mechanism, the withheld records and the affordances are exercised in the layout tests |
| `raw` depth | Not independently requestable (AD D.1, ADV-208) — by design | — | No |

Nothing here is a critical correctness or safety defect, so under OD-6's counter-rule integration
proceeds. The one thing that genuinely blocks criteria 2, 3 and 4-on-real-mail is still OAuth consent
status, unchanged and untouched by this round.

---

## Gates

```
$ .venv/bin/ruff check server/src tests tools harness
All checks passed!

$ .venv/bin/ruff format --check .
186 files already formatted

$ .venv/bin/mypy --strict
Success: no issues found in 160 source files

$ .venv/bin/python -m tools.guards
guards clean: forbidden-import, generative-client, gmail-endpoint, ground-truth-isolation,
scope-literal, unaudited-disk-write, unwrapped-http-client over server/src

$ .venv/bin/python -m pytest -q -m "not network"
2557 passed

$ .venv/bin/python -m tools.rubric_status
criteria: 113  (mandatory 110, conditional 2, optional 1)
status:
  PASS         6
  FAIL         0
  BLOCKER      0
  NOT TESTED   107
reviewer transitions recorded: 11
gate-blocking criteria (NOT TESTED / FAIL / BLOCKER): 106
```

No rubric criterion was moved. `ROUTE-01` was not restored. `FINDINGS_LEDGER.md` and
`RUBRIC_TRANSITIONS.md` are untouched. No reviewer probe set under `/tmp/rretr15..22/` was read or
tuned against; every fixture in `tests/test_disclosure_round23.py` is generated by that file's own
builders.

### Reintroduction

`tests/fixtures/replants.py` gains **R67–R77**, eleven entries for the eleven behaviours this round
changed, and re-anchors **R46** and **R57**, whose anchored lines moved when the disclosed reductions
became the ladder's. `tests/test_replants.py` passes: every anchor matches exactly once, every cited
test exists, the scratch tree resolves all three packages inside itself (whole tree including
`docs/`), every planted file is asserted changed by content hash, and **every `caught_by` citation
fails on its own**.

```
R46-a-message-no-reply-can-name-looks-like-an-ordinary-reply-again  matches=1  CAUGHT (1/1)
R57-the-body-bearing-row-loses-the-same-fact                        matches=1  CAUGHT (1/1)
R67-the-fill-admits-on-position-alone                               matches=1  CAUGHT (2/2)
R68-the-driver-stops-defending-floor-membership                     matches=1  CAUGHT (1/1)
R69-every-floor-member-is-promoted                                  matches=1  CAUGHT (1/1)
R70-the-overflow-ceiling-is-a-budget                                matches=1  CAUGHT (1/1)
R71-a-source-holding-a-floor-member-is-split-off                    matches=1  CAUGHT (1/1)
R72-a-floor-member-is-withheld-at-the-ceiling                       matches=1  CAUGHT (1/1)
R73-the-ladder-and-the-envelope-measure-differently                 matches=1  CAUGHT (1/1)
R74-the-adjacency-radius-outgrows-the-baseline                      matches=1  CAUGHT (1/1)
R75-a-published-e4-weight-moves                                     matches=1  CAUGHT (2/2)
R76-the-disclosed-depth-goes-back-to-being-decided-in-assemble      matches=1  CAUGHT (1/1)
R77-the-top-k-becomes-its-own-number                                matches=1  CAUGHT (1/1)
```

R67's second citation is `tests/test_region_kind_round19.py::test_a_stub_row_states_the_region_its_own_labels_place_it_in`
— the round-19 test that found the degeneracy in Part 0. It is cited because it catches, and because
a round-19 provenance test defending a round-23 disclosure property is the best evidence I have that
the non-vacuity guards in old tests earn their keep.
