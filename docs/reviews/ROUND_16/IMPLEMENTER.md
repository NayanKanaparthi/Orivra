# ROUND 16 — IMPLEMENTER — WS-04 fix round: the ladder finds what is there, or says it did not

**Work order:** `docs/reviews/ROUND_16/WORK_ORDER.md`
**Protocol:** `docs/AGENT_LOOP.md` §5, under §5a.
**Gating reviewer:** R-RETR, on what this round changes.

---

## 0. The state I inherited, stated first

The working tree was **not** clean when I started. An interrupted earlier run of this same work
order had already written most of Parts 1–5: the `ConstraintUnit` model, the D.3 rule-2 conjunct
fix, `_why_this_thread_cannot_be_mapped` / `_withhold_the_whole_thread`, the R-RETR-011..014/016
fixes, and the correction to amendment **A8**. Two files were left unformatted, which is how I
first knew the run had been cut short.

I did not take any of it on trust. I re-ran every R-RETR reproduction for Parts 1–4 myself and drove
my own probes at every claim. That found **six defects in the inherited fixes**, three of which
together made **757 of 2,300** ordinary operator combinations raise an uncaught `ValueError` instead
of answering:

1. L1b planned a probe made of nothing but a mailbox-scope operator (712 of the 757);
2. a caller-typed scope-only query reached `Probe.__post_init__`'s refusal as a `ValueError` rather
   than as MailWeave's declared inability (64);
3. L3's whole-mailbox probe repeated a scope operator instead of replacing it (106) — and where it
   did not raise, it declared a broadening that searched the *narrower* scope;
4. L3's widening step turned `-from:x` into `{-from:x to:x}` — "not from x, or to x", a different and
   near-total query, which paired with a scope operator read spam and trash;
5. L3 re-sent L1's own query as its broadening when the user wrote the widening operator themselves;
6. `analyse` raised a bare `ValueError` on `newer_than:7d older_than:30d`, an ordinary typable query.

Plus one in the corrected text of amendment **A8** itself: its correction paragraph pointed at "the
paragraph below headed …" which the correction had replaced, so the reference dangled.

All seven are described below and all of them are mine to own: the round's deliverable is the tree as
it now stands, not the part of it I typed.

| | round 15 exit | tree as I found it | tree now |
|---|---|---|---|
| `pytest -q -m "not network"` | 2,180 | 2,223 (2 files unformatted) | **2,235** |
| `ruff format --check` | clean | **2 files would be reformatted** | clean |
| rubric | 7 PASS / 0 FAIL / 0 BLOCKER / 106 NOT TESTED, 11 transitions | unchanged | **unchanged** |

`docs/reviews/FINDINGS_LEDGER.md` and `docs/reviews/RUBRIC_TRANSITIONS.md` are untouched. I marked
no criterion.

---

## 1. Part 1 — R-RETR-006 (BLOCKER). A parse failure is a declared inability, not a mailbox read.

### What changed

**A query no rung can turn into a probe is refused before any Gmail call.** `LadderRunner.run_parsed`
raises `QueryNotSearchable` (a `MailweaveError`) carrying the same declaration `dropped_declarations`
would have put in `asked_for.dropped`. `BroadeningRung._anywhere` plans nothing when the parse leaves
no fragment that *selects*, and `Probe.__post_init__` makes the shape unrepresentable so it cannot
return through another rung.

**My correction to the inherited fix, and it is the round's own named defect.** The inherited version
keyed the refusal on `not parsed.constraints` and refused the bad shapes inside `Probe.__post_init__`
with a `ValueError`. That covered the shape MailWeave *composes* and left the shape a caller can
*type*:

```
mailweave_search("in:anywhere")        -> ValueError out of plan_ladder  (an ordinary Gmail query)
mailweave_search("in:anywhere rollout")-> ValueError out of plan_ladder  (the query L3 composes)
mailweave_search("in:spam rollout")    -> ValueError out of plan_ladder
```

Measured over a 2,300-query cross-product of ordinary operator spellings
(`/tmp/r16impl/v3_fuzz.py`, `v4_causes.py`): **757 raised rather than answered**
— 712 at L1b, 64 at L1, 106 at L3, counted by which rungs raise, so the classes overlap. Every one
was a query naming a member of `WIDENING_MAILBOX_OPERATORS`. After the fix: **0 of 2,300**.

Four changes, all in one statement rather than four:

* `why_this_q_is_not_a_probe(query) -> str | None` in `retrieval/ladder.py` is the single spelling of
  "this `q` is a listing, not a probe". `Probe.__post_init__` raises on it; `FilteredRung.plan`
  **declines** on it. That pairing is the module's own existing rule — one place decides not to plan,
  the other makes the object unrepresentable — written once instead of twice;
* the refusal in `run_parsed` is keyed on **`not plan_ladder(parsed)`**, the empty ladder plan, not on
  the empty constraint list. It therefore covers both classes and cannot come apart from what the
  rungs actually planned;
* `decomposition_units_of` no longer makes a probeable unit out of a fragment that selects nothing —
  see §2, because that is where the 712 lived;
* `BroadeningRung` stopped composing two shapes that are not broadenings: a widening probe that
  **conjoins a narrower scope operator** (`in:anywhere in:spam …`, which searches the narrower scope
  and declares that it widened), and a widening probe **identical to L1's own query**, which costs a
  Gmail call to re-observe what L1 observed.

Two further shapes of the same class, both found by my own probing rather than filed:

* **L3 widened a negated participant into its own opposite.** `-from:x` became `{-from:x to:x}` —
  "not from x, or to x", which is nearly every message there is. Paired with a scope operator the
  user wrote it composed a probe that *passed* the select-something check on the strength of its
  `to:` half and read spam and trash. A negation selects nothing, so there is nothing there to
  widen; it is now carried unchanged;
* **a crossing date pair raised out of `analyse`.** `newer_than:7d older_than:30d` is typable and its
  two bounds cross, so `TimeWindow.__post_init__` — correctly a guard against a programming error —
  let a bare `ValueError` escape on a user's query. `window_from_operators` now claims **no window**
  and carries both operators onto the wire verbatim, which is the rule that function already applies
  to a date value it cannot resolve. The ladder then answers it as it answers any zero-hit query and
  L2's relaxation is what recovers it, which is a better answer than a refusal.

### Executed evidence

| Claim | Evidence |
|---|---|
| a zero-constraint query reaches Gmail **zero times** and states a reason | `test_a_query_the_parser_produces_nothing_from_is_refused_not_scanned` (6 shapes), `test_no_rung_plans_a_probe_for_a_query_the_parser_produced_nothing_from` |
| a query naming only *where* to look does the same, with non-empty constraints | `test_a_query_that_names_only_where_to_look_is_refused_not_scanned` (6 shapes; asserts `parse(q).constraints != ()` so the two classes cannot collapse into one) |
| a scope operator **with** something to find is executed as written, once | `test_a_query_naming_where_to_look_and_what_to_find_is_searched_in_that_scope` |
| no rung raises over the operator lexicon | `test_no_query_the_operator_lexicon_can_spell_makes_a_rung_raise` — 2,550 queries derived from `FIDELITY_TABLE` (itself bound to `OperatorName`), each negated form, the widening operators and free-text shapes; asserts every planned probe is not a listing, and that every composed probe (L1b/L2/L3) selects something |
| L3 does not conjoin a narrower scope | `test_a_broadening_probe_does_not_carry_a_narrower_scope_than_the_one_it_widens_to` |
| L3 does not widen a negation into a disjunction | `test_a_negated_participant_is_not_widened_into_its_own_opposite` |
| a crossing date pair resolves to no window rather than raising | `test_a_pair_of_date_operators_that_cross_resolves_to_no_window_not_a_crash` |
| the historical claim in `carries_nothing_to_select_by`'s docstring | rebuilt the described code state in the scratch tree and ran it: `-cutover` → wire `('-cutover', False), ('in:anywhere -cutover', True)`, **8 spam messages as `role: matched`**, `outcome: answered`, `term_coverage: 1.0`. Reproduces exactly (`/tmp/r16impl/v12_historic.py`) |

### What I could not establish

* Whether refusing with an exception is the right *surface*. `QueryNotSearchable` is not in D.11's
  closed vocabulary and `run_parsed` produces no envelope, while A.2 and D.3 rule 6 say there is
  never a bare empty result. The reason is recorded in the class's own docstring: a structured report
  must state which rungs executed, and for this query none did — naming one to satisfy the validator
  would be a false statement about what was executed. **Whether the envelope schema should be able to
  carry a zero-rung structured report is a contract question and is recorded for WS-10**, not
  decided here (AL §8).
* L3's `in:anywhere` step still reads spam and trash for a query that did not name them — for example
  `is:unread` with no hits at L1. That is A.7's L3 row as written, it runs only when nothing was
  found, and it is declared per probe in `scan_scope`. Narrowing it is A.7's decision, not this
  finding's.

---

## 2. Parts 2 and 3 — R-RETR-007 and R-RETR-008. The founding bug's commonest shape.

### What changed

**The constraint model now answers two different questions separately.** A `Constraint` is one
*droppable* unit — dropping the query's subject is one relaxation step, not one per word — and it is
as many *probeable* units as it has independently satisfiable fragments. `ConstraintUnit` and
`decomposition_units_of` are the new half; `DecompositionRung.plan` reads `parsed.decomposition_units`
rather than `parsed.constraints`, and L1b's intersection is keyed on the probe's **unit** rather than
on the constraint it enforces.

The change is **at the constraint model, not at the rung**, so it holds for every kind at once. Three
exclusions, each of them a peer that would otherwise have been trusted:

* a **negated** fragment is never a unit — `-cutover` is satisfied by nearly every message, so a
  probe carrying one alone is a whole-mailbox listing wearing a fragment of the query as a disguise;
* a **mailbox-scope** fragment is never a unit — **this one is mine.** The inherited rule tested the
  negation prefix only, so `in:anywhere rollout` planned an L1b probe of `in:anywhere` alone. That is
  where 712 of the 757 raises lived: the round's fix for R-RETR-008 and the round's fix for
  R-RETR-006, each right about the shape it was written for, wrong at their join. `selects_something`
  is now one predicate over both classes, defined in terms of `carries_nothing_to_select_by`, which
  is the same sentence written for a whole `q`;
* a **jointly binding** kind (dates) contributes one unit between *all* of its constraints. The
  inherited code grouped per constraint, which is the derived `date_window` and nothing else, so a
  user who wrote `after:X before:Y` out — the ordinary way to write a window — had the halves
  intersected on `threadId` and got back threads holding one message in 2025 and one in 2027 as
  `role: matched` for a window neither is in. That correction was already in the tree when I arrived
  and I verified it by execution; I record it because it is the same defect one round earlier.

**R-RETR-007** is fixed at both ends: D.3 rule 2's fourth conjunct is now `answer_type_presence`
(`present is True`), not `not blocks_stop` (`present is not False`) which imported rule **1b**'s
no-cue escape into rule 2; and `LadderStop.halts_after` for the rule-2 stop is **L1b**, because A.7's
table calls L1b "feeds L1" — it is part of L1's answer rather than an escalation from it.

### Executed evidence — the shape table, driven end to end (`/tmp/r16impl/v7_decomp.py`)

Every row: L1 returns **0**, the thread's messages live in different messages of one thread, and the
thread comes back as a `Source`.

| query | units | L1b probes | found |
|---|---|---|---|
| `rollout cutover` | `terms[rollout]`, `terms[cutover]` | `rollout`, `cutover` | 2 rows, both `matched` |
| `rollout cutover handover` | 3 term units | 3 | 3 rows, all `matched` |
| `rollout cutover handover switchover` | 4 term units | 3 (the A.7 cap) | 4 rows — 3 `matched`, 1 `stub`; the cap costs precision, not recall |
| `"vendor selection" cutover` | `phrase`, `terms` | 2 | 2 rows |
| `from:ana@… from:bo@…` | `from[…ana]`, `from[…bo]` | 2 | 2 rows |
| `from:ana@… cutover` | `from`, `terms` | 2 | 2 rows (round 15's fixture, unregressed) |
| `subject:vendor rollout cutover` | `subject`, 2 term units | 3 | 2 rows |

Multi-fragment kinds, at the parse (`/tmp/r16impl/v13_multiphrase.py`): two quoted phrases →
two units; `label:a label:b` → two units; `to:` and `cc:` → one unit each. A written-out
`after:X before:Y` → **one** unit carrying both constraints, same as the derived window.

Tests: `test_two_bare_words_in_two_messages_of_one_thread_are_recovered`,
`test_decomposition_splits_every_constraint_kind_whose_fragments_bind_separately`,
`test_a_constraint_of_several_fragments_decomposes_into_one_unit_per_fragment`,
`test_a_negated_fragment_is_not_a_decomposition_probe_of_its_own`,
`test_a_mailbox_scope_fragment_is_not_a_decomposition_probe_of_its_own` (asserted over the whole
`WIDENING_MAILBOX_OPERATORS` vocabulary, not one spelling),
`test_a_date_window_is_one_unit_whether_it_is_written_out_or_derived`,
`test_the_l1_stop_does_not_switch_off_the_rung_that_feeds_l1`,
`test_d3_rule_2_uses_the_fourth_conjunct_the_architecture_writes`,
`test_an_exact_signal_stop_at_l0_halts_every_later_rung_including_l1b`.

R-RETR's own `a1_terms.py`, `a2_stop.py` and `a3_conjunct.py` run green against the tree: the split
thread is a source in all three grammars, and `not_tried` no longer names L1b.

### What I could not establish

* **LEX-03's recall rate and ROUTE-02's recovery rate.** Both bars are `[UNSET — register at G0]`
  against corpora that do not exist. My table is constructed cases, not a measurement. **WS-16.**
* The L1b cap at more than three units yields a *superset* intersection; the fourth unit's message is
  disclosed as a stub because its thread is hit-bearing anyway. That is the documented behaviour and
  I executed it, but the precision cost has no measured distribution. **WS-16.**
* `not_tried[].why` is still `not_applicable` for L2/L3 when the escalation policy declined to run
  them. R-RETR-007's second alternative needed a fourth vocabulary value; I took the first
  alternative instead (L1b runs before the stop can halt it), so the vocabulary gap is now confined
  to the case A8 note 1 already escalated. **WS-10/WS-11.**

---

## 3. Part 3 — R-RETR-009. No order is presented as chronological unless it is.

### What changed

`assemble` has **no fallback index**. `_why_this_thread_cannot_be_mapped` asks two questions of every
`threads.get` before a `Source` is built — does it omit a hit its own `messages.list` returned, and
does it state a chronological position for every message — and a thread that fails either is not
mapped at all. `_withhold_the_whole_thread` gives it A.7a's disposition: every id the ledger observed
in that thread becomes a `partial_source_failure` withheld record with a `mailweave_get_messages`
affordance, plus a `not_included_sources` entry carrying the reason and a `mailweave_thread_map`
affordance. `RecordedThread.scalars_absent_because` — which had no consumer — is quoted into the
`why`.

### Executed evidence (`/tmp/r16impl/v8_positions.py`), three shapes, one of them a peer

| `threads.get` | result |
|---|---|
| every `internalDate` present | one source, rows `(m-zulu, 0, matched) (m-alpha, 1, stub) (m-mike, 2, stub)` — chronological, matched message first |
| **no** `internalDate` (PF-2's shape) | no source; `not_included_sources: [t-p]`; all three ids withheld under `partial_source_failure`; `partial: true`; `outcome: inconclusive` |
| `internalDate` missing for **one** message only | identical treatment — the peer the all-or-nothing fixture flag cannot reach, driven through a custom transport |

`H ⊆ disclosed ∪ withheld` held in all three. Test:
`test_a_thread_whose_order_cannot_be_derived_is_not_placed_in_an_invented_one`.

### What I could not establish

**PF-2** — whether `threads.get(format=metadata)` really omits `internalDate` on a live account. The
code path is live and was wrong either way; its frequency is a measurement I cannot take.

---

## 4. Part 4 — R-RETR-010. A8's contradiction is real; its stated reason was not.

### What changed in the text

Amendment **A8** now says plainly that the sentence *"not expressible in the shipped schema —
arithmetic rather than effort"* **is false**, that R-RETR disproved it by execution, and that the
answer is built. It does not soften it and it does not rewrite around it: the arithmetic that
paragraph carried is retained verbatim under a heading that says what it actually bounds —
**`Source.stated_total` for the disagreeing thread, and nothing wider**. I corrected one further
defect in that text while I was in it: the correction paragraph referred to a paragraph "below headed
…" that the correction had itself replaced, so the reference dangled. It now names both the old
heading and the new one.

What stays deferred is unchanged and is the part that was always a contract question: a schema that
can say *complete as the thread enumeration reported, incomplete against what was retrieved* is a
change to PART-03 and R-08, is **WS-11's**, and has **PF-1** as its input.

### What changed in the code

One self-disagreeing thread is now **one thread's disposition**, not the response's. A
`NotIncludedSource` states `stated_total: null` when the enumeration and the observation disagree —
which is the honest answer a schema that cannot hold two completeness claims can still give — and
states the enumeration normally when there is no disagreement.

### Executed evidence (`/tmp/r16impl/v9_a8.py`)

Five healthy threads plus one thread whose `threads.get` omits its own `messages.list` hit:

```
sources        : 5   (t-ok-1 .. t-ok-5, each included == stated_total == 1)
not_included   : [('t-bad', stated_total=None)] with a mailweave_thread_map affordance
withheld       : bad-1, bad-2 -- both partial_source_failure, both with mailweave_get_messages
H              : 7 ids;  H subset of disclosed union withheld: True
bad-1          : withheld (the omitted hit has a disposition, not a silence)
partial: True   outcome: answered   envelope serialises: True
```

R-RETR's `c1_a8.py` still shows **both** validators refusing a `Source` at 9 and at 10, which is the
half of A8 that was right. `c4_blast.py` now prints five healthy threads instead of a refusal.
Tests: `test_a_thread_map_that_omits_one_of_its_own_hits_is_withheld_rather_than_shipped`,
`test_one_self_disagreeing_thread_does_not_deny_the_other_five`.

### What I could not establish

**PF-1** — whether real Gmail produces the shape at all. The claim half needed no measurement and is
closed; the blast-radius half is now safe either way.

---

## 5. Part 5 — the MEDIUMs and LOWs

| Finding | Disposition | Executed evidence |
|---|---|---|
| **R-RETR-011** relative windows declared widened, not widened | **closed.** The margin applies where MailWeave *renders* the boundary (`yesterday` → `after:2026/09/01 before:2026/09/04`, `widened_days=1`, declared). An operator the user wrote is carried verbatim and `window_utc` now states the instant it actually cuts at, so nothing declares a widening no probe performed | `d3_margin.py`: declared `start` `2026-08-27T12:00Z`, wire `newer_than:7d`, the edge message is outside the declared window **and** disclosed. `test_a_gmail_relative_age_operator_declares_the_instant_it_actually_cuts_at`, `test_a_widened_relative_expression_sends_the_widened_bound_it_declares`, `test_the_old_relative_age_widening_is_not_reintroduced` |
| **R-RETR-012** unknown operator on the wire, absent from `asked_for` | **closed.** Kept out of the executed `q` and declared dropped under `unproven_operator`; `term_coverage` falls to 0.5 | `a9_unknown_op.py`, `test_an_operator_mailweave_cannot_prove_is_declared_and_not_executed` |
| **R-RETR-013** the L1b bound's missing precondition | **closed as a claim.** The docstring names the page budget as the second precondition and the truncation case is executed | `test_a_truncated_decomposition_page_drops_a_thread_the_bound_does_not_cover` |
| **R-RETR-014** two docstrings contradicting each other | **closed.** `operators.py` now states what `render()` states, and records that it used to say the opposite | `d5_claims.py`; the false sentence survives only as a quotation of itself |
| **R-RETR-016** `answered` beside a declared-incomplete scan | **closed.** `outcome` needs rows, evidence, **and** a scan not declared incomplete | `a5_paging_fatal.py` now reports `inconclusive`; `test_a_run_that_declares_pages_remaining_does_not_also_report_answered` |
| **R-RETR-015** no recovery route for a single-constraint query | **partly closed, and I say plainly what is left** — see below |

### R-RETR-015, not fully closed

The constraint-model fix closes the part of it that was a *decomposition* gap. Measured on shapes I
constructed (`/tmp/r16impl/v11_k1.py`), not on R-RETR's set:

```
'rollout cutover'                k=1  units=2   L1, L1b(rollout|cutover), L3
'rollout OR escalation'          k=1  units=2   L1, L1b(rollout|escalation), L3
'rollout note'                   k=1  units=2   L1, L1b(rollout|note), L3
'rollout'                        k=1  units=1   L1, L3(in:anywhere rollout)
'"the rollout schedule slipped"' k=1  units=1   L0, L1, L3(in:anywhere "…")
'subject:vendor'                 k=1  units=1   L1, L3
```

Two of the three shapes R-RETR filed now have a decomposition rung. What remains open is a query
whose single constraint is a **single unit** — one bare word, or one quoted phrase. It has L1 and
L3's scope widening and no term-level relaxation inside the phrase. R-RETR's own required fix names
the alternatives as "phrase-to-terms degradation at L3, **or** an explicit statement in A.7 that
k = 1 is out of L2/L3's scope and which rung owns it". Both are changes to A.7's published L3 step
and cost row, which is not an implementer's call (AL §8). **Left open, with the reason: it belongs to
A.7 / WS-10.** Under §5a that is a correct outcome, not a gap.

---

## 6. Have I trusted a peer rather than checking it?

**I asked the question three times and it found something every time.** The question I asked was not "is
my fix right?" but "**what is the next object over that my fix's rule should also be true of, and did
anyone execute it?**"

1. *The refusal in `Probe.__post_init__` is a rule about a `q`. Which other code composes a `q` out
   of a subset of the query's fragments?* — L2 (checked, already guarded), L3 (guarded for the
   fragments it chooses, **not** for the composed query, and not for a scope fragment it repeated),
   and **L1b's units, which were not guarded at all**. That is the 712-query hole, and it sat exactly
   at the join of this round's two headline fixes. I did not find it by reasoning: I found it by
   running every single, ordered pair and three-combination of 23 operator spellings — 2,300 queries
   — through `plan_ladder` and counting what raised. The reasoning came second, and on its own it
   would not have come at all.
2. *The refusal is a rule about a query MailWeave composed. What about a query a caller typed?* —
   `mailweave_search("in:anywhere")` and `mailweave_search("in:spam rollout")` are ordinary Gmail
   queries and both were uncaught `ValueError`s. A declared inability that arrives as an internal
   invariant is not a declared inability.
3. *`selects_something` says a negation selects nothing. Where else does this module assume a
   fragment selects?* — `BroadeningRung._widened`, which turned `-from:x` into `{-from:x to:x}`.

The standing form of the question is now a test rather than a habit:
`test_no_query_the_operator_lexicon_can_spell_makes_a_rung_raise` sweeps 2,550 queries built from
`FIDELITY_TABLE` — which is itself bound to `OperatorName`, so an operator added to the lexicon is
swept without anyone remembering — and asserts of **every planned probe of every rung** that it is
not a listing, and of every *composed* probe that it selects something. Its bound is stated in its
own docstring: singles and ordered pairs, **not triples**. A defect needing three fragments at once
would not be seen by it.

Where I have **not** closed the question: the sweep is over the plan layer only. It says no rung
plans a listing; it does not say every planned probe is a *useful* one, and it cannot, because
"useful" is a recall measurement and that is WS-16's.

---

## 7. Every docstring claim my diff makes about coverage, with its executed evidence

The mechanical half is `test_every_test_a_source_docstring_names_exists`, which reads every string
constant in both source trees and requires each `test_…` identifier to resolve. It fired on me while
I worked, naming all three tests I had cited in a docstring before writing them, which is the sweep
doing its job.

| Claim | Where | Executed by |
|---|---|---|
| a fragment fails `selects_something` iff it is a negation or a mailbox-scope operator | `query/analysis.py`, `selects_something` | `test_a_negated_fragment_is_not_a_decomposition_probe_of_its_own`; `test_a_mailbox_scope_fragment_is_not_a_decomposition_probe_of_its_own`, which loops over the whole `WIDENING_MAILBOX_OPERATORS` vocabulary |
| "757 raised rather than answered, 712 of them at this rung, every one naming a member of `WIDENING_MAILBOX_OPERATORS`" | `query/analysis.py`, `_units_of_one` | measured before the fix and re-measured after (0/2,300): `/tmp/r16impl/v3_fuzz.py`, `v4_causes.py`. **I corrected this number twice while writing** — my first draft said 693, which is the count for two of the eight raising classes, and my second put L1 at 54 and L3 at 100 rather than 64 and 106 |
| the refusal covers a query that names only where to look, and `FilteredRung` declines rather than raising | `retrieval/ladder.py`, `why_this_q_is_not_a_probe`, `FilteredRung` | `test_a_query_that_names_only_where_to_look_is_refused_not_scanned` (6 shapes) |
| the condition is the empty ladder plan, not the empty constraint list | `retrieval/ladder.py`, `run_parsed` | same test — it asserts `parse(q).constraints != ()` **and** `plan_ladder(...) == ()` |
| a mailbox-scope fragment is *replaced wholesale*, as a date window is | `retrieval/ladder.py`, `_anywhere` | `test_a_broadening_probe_does_not_carry_a_narrower_scope_than_the_one_it_widens_to` |
| a probe identical to L1's query is not a broadening | `retrieval/ladder.py`, `BroadeningRung.plan` | `test_a_query_naming_where_to_look_and_what_to_find_is_searched_in_that_scope` |
| a negated participant is carried unchanged | `retrieval/ladder.py`, `_widened` | `test_a_negated_participant_is_not_widened_into_its_own_opposite` |
| a crossing date pair claims no window and both operators still reach the wire | `query/timepolicy.py`, `window_from_operators` | `test_a_pair_of_date_operators_that_cross_resolves_to_no_window_not_a_crash` |
| **inherited:** `mailweave_search("-cutover")` returned 8 spam rows as `matched` under `answered` / `term_coverage: 1.0` | `constants.py`, `carries_nothing_to_select_by` | not a test — a claim about code that no longer exists. I rebuilt that code state in the scratch tree and reproduced it exactly (`/tmp/r16impl/v12_historic.py`) rather than inheriting the number |
| **inherited:** the unit rule "holds for a repeated operator and a multi-phrase query by the same code" | `retrieval/ladder.py`, `DecompositionRung` | `/tmp/r16impl/v13_multiphrase.py` — two phrases → two units, `label:a label:b` → two units; plus `test_decomposition_splits_every_constraint_kind_whose_fragments_bind_separately` |

---

## 8. Reintroduction checks

Every source edit **I** made this round was applied by `/tmp/r16impl/edit.py`, which **asserts its
anchor matched exactly the expected number of times before applying it** and **asserts the file
changed** before writing, printing the before/after content hash. No edit was forced past a failed
anchor; the ones that missed were re-derived from the real file, and one of them is why this
paragraph is being rewritten rather than patched. The interrupted run used the same discipline
through its own `/tmp/r16impl/apply.py` and left its own plant harness at `/tmp/r16impl/plants.py`.
I did **not** rely on that harness: its anchors were written against an intermediate constraint
model (`Constraint.units`) that no longer exists, so it would abort on its own anchor assertions —
which is the harness behaving correctly rather than evidence about the tree.

The check I rely on is my own plant sweep (`/tmp/r16impl/plant.py`): each fix's inverse is planted in
a **scratch copy** and the tests that name it are run against that copy. It covers the inherited
fixes as well as mine, because a fix I did not write is still a fix I am handing over.

> **The `.pth` trap, handled explicitly.** The venv installs `mailweave` as an editable path
> configuration, so a scratch copy silently tests the real tree unless `PYTHONPATH` is set. The
> harness asserts, before any plant, that `mailweave.__file__` and `tests.__file__` both resolve
> **inside the scratch tree**, and prints them. It also asserts the scratch tree is green on all 13
> target tests before the first plant, so a plant cannot be "caught" by a test that was already red.

```
imports resolve into the scratch tree:
  <scratch>/tree/server/src/mailweave/__init__.py
  <scratch>/tree/tests/__init__.py
scratch tree green on all 13 target tests before planting

CAUGHT  anchor 1/1, file changed  P1  L1b units filter on the negation prefix only (the pre-fix rule)
CAUGHT  anchor 1/1, file changed  P2  L1 plans on any non-empty q (round 15's condition)
CAUGHT  anchor 1/1, file changed  P3  L3 repeats a mailbox-scope fragment beside the widening operator
CAUGHT  anchor 1/1, file changed  P4  the refusal is keyed on the empty constraint list again
CAUGHT  anchor 1/1, file changed  P5  a crossing date pair builds a TimeWindow again
CAUGHT  anchor 1/1, file changed  P6  L3 widens a negated participant into a from|to group
CAUGHT  anchor 1/1, file changed  P7  L3 re-sends L1's own query as its broadening
CAUGHT  anchor 1/1, file changed  P8  D.3 rule 2's fourth conjunct imports rule 1b's no-cue escape
CAUGHT  anchor 1/1, file changed  P9  the L1 stop switches L1b off again
CAUGHT  anchor 1/1, file changed  P10 assemble invents a position when the observation stated none
CAUGHT  anchor 1/1, file changed  P11 a self-disagreeing thread denies the whole response again
CAUGHT  anchor 1/1, file changed  P12 decomposition keys its intersection on the constraint, not the unit
all 12 plants caught by the tests that name them
```

**One plant was not caught on its first run and that is recorded rather than tidied away.** P3's
first target was the operator sweep, which passed with the defect planted — because repeating a
scope fragment produces a probe that is *wrong* (it searches the narrower scope while declaring it
widened) but not one that *raises*, and the sweep only asserts that no rung raises. The right test
did not exist, so I wrote it
(`test_a_broadening_probe_does_not_carry_a_narrower_scope_than_the_one_it_widens_to`) and re-ran the
sweep from a fresh scratch tree. A plant that is not caught is evidence about the tests, not about
the plant.

---

## 9. Findings not closed, with the workstream that owns them

| Not closed | Reason | Owner |
|---|---|---|
| **R-RETR-015**, the single-unit residue | both of R-RETR's named fixes change A.7's published L3 step and cost row; not an implementer's call | **A.7 / WS-10** |
| whether a zero-rung run should produce a structured report rather than an exception | the schema must be able to say "no rung executed" without a false `not_tried` entry; a vocabulary/contract question | **WS-10** (recorded in `QueryNotSearchable`'s docstring with the reproduction) |
| `not_tried[].why` for a rung a stop or the escalation policy declined | the closed D.2 vocabulary has no true value; already escalated as A8 note 1 | **WS-10/WS-11** |
| the two-completeness-claims schema for a self-disagreeing source | contract change to PART-03 and R-08 | **WS-11**, with **PF-1** as input |
| **EV-02, EV-04, EV-06, ROUTE-02** rates | need a seeded corpus, Baseline B/D, holdout seeds and a counting proxy. **I did not tune against R-RETR's probe set**: I ran its scripts only as a regression check that nothing crashes, and every recovery number in this document is measured on cases I constructed | **WS-16** |
| **LEX-04**'s network-level cost bar | must come from network-level counts, not the meter's self-report | **WS-16 / R-PERF** |
| **PF-1**, **PF-2**, **PF-9**, **PF-13**, **PF-14** | live-account measurements | credentials, then R-GMAIL |
| whether A.6a rule 3 should be read as covering the `newer_than:`/`older_than:` operator family | R-RETR-011 is closed by the option R-RETR named (declare what was searched). If a reviewer reads rule 3 as promising a widening for the *operator* family too, that is an architecture question and I have not answered it | **orchestrator / A.6a** |

Nothing in the retry/backoff constants was touched; they remain the open owner decision.

---

## 10. Gates, as run

```
ruff check .                     All checks passed!
ruff format --check .            153 files already formatted
mypy --strict                    Success: no issues found in 127 source files
python -m tools.guards           guards clean: forbidden-import, generative-client, gmail-endpoint,
                                 ground-truth-isolation, scope-literal, unaudited-disk-write,
                                 unwrapped-http-client over server/src
pytest -q -m "not network"       2,235 passed          (re-counted independently via
                                                        --collect-only -q summed per file = 2,235)
python tools/rubric_status.py    criteria 113; PASS 7 / FAIL 0 / BLOCKER 0 / NOT TESTED 106
  --check                        reviewer transitions recorded: 11        (unchanged)
```

`generative_llm_calls = 0` is enforced by the `generative-client` guard, in that clean list. Nothing
this round imports a model, embeds anything or consults corpus frequency; no test in it touches the
network (`conftest.py` denies `socket.connect`), and no fixture carries real or realistic personal
mail — `test_no_fixture_in_this_file_carries_anything_that_could_be_real_mail` executes that rather
than asserting it.
