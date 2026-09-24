# ROUND 17 — IMPLEMENTER — refuse the unanswerable, answer the rest

**Work order:** `docs/reviews/ROUND_17/WORK_ORDER.md`
**Protocol:** `docs/AGENT_LOOP.md` §5, under §5a.
**Gating reviewer:** R-RETR, on what this round changes.

---

## 0. The one thing this round is about, stated before the parts

Round 15 answered too much: a query the parser drew no constraint from was broadened to the
whole mailbox, spam and trash included, and reported `answered` with `term_coverage: 1.0`.
Round 16 stopped that and then refused too much: 17 of 50 plausible queries produced **no
envelope at all**, and a quoted reply subject — the most ordinary thing a user types — was a
straight regression.

Neither extreme is the product. Two sentences separate them and both are load-bearing:

* **not sending a query to Gmail** and **not answering the caller** are different decisions,
  and round 16 made them one. A query MailWeave cannot search still gets a structured
  report wherever one can honestly be made;
* a predicate about what a fragment *can select* is not the same as a predicate about how a
  fragment is *spelled*, and round 16 wrote the second while meaning the first.

Everything below follows from those two, plus the invariant in §3, which is the round's most
important output and which subsumes two of its findings rather than one.

| | round 16 exit | tree now |
|---|---|---|
| `pytest -q -m "not network"` | 2,235 | **2,248** |
| `ruff check` / `ruff format --check` / `mypy --strict` / `python -m tools.guards` | clean | clean |
| rubric | 6 PASS / 0 FAIL / 0 BLOCKER / 107 NOT TESTED, 11 transitions | **unchanged** |

`docs/reviews/FINDINGS_LEDGER.md` and `docs/reviews/RUBRIC_TRANSITIONS.md` are untouched. I
marked no criterion and did not restore ROUTE-01. Nothing in the retry/backoff constants was
touched.

**Files changed** (ten, and nothing else in the tree):
`server/src/mailweave/constants.py`, `query/operators.py`, `query/analysis.py`,
`retrieval/ladder.py`, `retrieval/assemble.py`, `envelope/response.py`, `errors.py`;
`tests/fixtures/mailbox.py`, `tests/test_query_analysis.py`, `tests/test_lexical_ladder.py`.

**Before I changed anything** I reproduced R-RETR's Parts 1–4 from `/tmp/rretr16` against the
tree as I found it: `r3_vacuous.py` (12 threads disclosed as `matched` for `mailweave_search('""')`,
`outcome: answered`, `term_coverage: 1.0`), `r9_phrase_ops.py` and `r10_phrase_refusal.py`
(every quoted phrase containing a colon refused with zero Gmail calls), `r25_scopedrop.py`
(`|H| = 0`, `sources = []` for the founding shape in spam), `r13_enforced.py` /
`r14_l3only.py` / `r12_l0stop.py` (`enforced` naming constraints no executed probe carried).
All four reproduce exactly as filed.

---

## 1. Part 1 — R-RETR-017 (BLOCKER). A predicate about selection, not about spelling.

### What changed

**`constants.matchable_content_of(token)` is the new predicate, and it asks a structural
question rather than matching a named shape.** Round 16's two predicates test *how a token is
spelled* — is it one of three named scope operators, does it begin with a minus — so `""`
walked between them: a non-empty string, not a scope operator, not a negation. It became a
`phrase` constraint, L1b probed it alone, and L3 composed the widening operator beside it with
`includeSpamTrash=true`.

`matchable_content_of` removes, in order, everything that is not content — NFKC, Gmail's
grouping punctuation, the negation prefix, the operator **name** (when the name is unquoted,
which is Part 2's rule read here), the phrase quotes, and every Unicode format character
(category `Cf`, asked of the runtime rather than transcribed, the same derivation
`content/html_text.py` gives its reason for) — and returns what is left for Gmail to look for.
Empty means the token filters nothing.

That is the property an enumeration of the eight reported spellings could not have: **an
operator added to `OperatorName` tomorrow either carries a value or carries nothing**, and this
sees that without an edit. `carries_no_content(q)` is its whole-`q` form.

Three consumers, each stating the same sentence at its own layer:

* `analyse` **filters such a token out before it becomes a constraint**, so no rung can
  compose one into a `q`. It is recorded in `ParsedQuery.vacuous_tokens`, counted by
  `unproven` (so `term_coverage` falls for it) and declared by `dropped_declarations` under
  `selects_nothing`;
* `query.analysis.selects_something` gains the third clause, so a *fragment* that names
  nothing is never a decomposition unit;
* `retrieval.ladder.why_this_q_is_not_a_probe` gains the matching check, so the shape is
  unrepresentable as a `Probe` and cannot return through a rung nobody has written yet.

**The choice R-RETR-017 asked me to make deliberately.** A vacuous token is **dropped and
declared**, not refused with the rest of the query. `report "" 2026` is a paste artefact
around a real question: MailWeave searches `report 2026`, reports `term_coverage: 0.5`, and
names `""` in `asked_for.dropped` with the reason. Refusing the whole query would let one
meaningless token cost the caller their question. When the vacuous token is *all* there is, no
constraint survives, `carries_nothing_searchable` becomes true, and the query is reported
unsearchable by that rule — with a structured report, per Part 5.

### Executed evidence

| Claim | Evidence |
|---|---|
| the rule holds for spellings nobody enumerated | `test_a_token_that_names_nothing_to_match_is_not_a_probe_however_it_is_spelled`: 16 reported shapes **plus** a generated family built from six runtime-derived format characters, asserted at four layers (`matchable_content_of`, `carries_no_content`, `why_this_q_is_not_a_probe`, `Probe.__post_init__`) |
| the fragment-level clause is executed, not just written | the same test asserts `selects_something` directly on `""`, `" "`, `subject:`, `label:""`, U+200B — the parse layer removes these before a constraint exists, so without this assertion the clause would be an unexecuted claim (plant **P2** was MISSED on my first sweep for exactly that reason, and this assertion is what caught it) |
| beside real content it is a drop, not a refusal | same test: `report "" 2026` → `render() == "report 2026"`, `term_coverage 0.5`, `selects_nothing` declared |
| at the wire, the BLOCKER is gone | same test drives `mailweave_search('""')`: `box.queries == []`, no sources, `inconclusive`, `term_coverage 0.0`. R-RETR's own `r3_vacuous.py` now prints `wire: []` and `|H|: 0` for all eleven of its shapes |
| a token that *does* select is untouched | same test, anti-vacuity half, including the distinction that `-cutover` **names** something and still **selects** nothing |

### Reintroduction

Plants **P2** (the content clause removed from `carries_nothing_to_select_by`), **P3** (the
parse keeps vacuous tokens as constraints) and **P4** (`why_this_q_is_not_a_probe` stops
refusing a content-free `q`) — each anchor asserted `1/1`, each file asserted changed, all
three CAUGHT. Table in §8.

### What I could not establish

* Whether Gmail itself treats `subject:` with an empty value as a no-op or as an error. The
  code no longer sends one either way, so the question is about the API's behaviour rather
  than about MailWeave's, and it is a live-account measurement. **R-GMAIL.**
* Whether an *unquoted* term made entirely of format characters should also be normalised out
  of the executed `q` when it sits beside real terms. Today `roll­out cutover` sends the
  soft hyphen to Gmail verbatim and matches nothing. That is a **query normalisation policy**
  question — the content pipeline strips these from mail text, and whether the same rule
  should apply to a user's query is an A.6 decision, not an implementer's. Recorded, with the
  reproduction, in §9.

---

## 2. Part 2 — R-RETR-018 (HIGH). A colon inside quotes is content.

### What changed

One clause. `tokenise` did `body.partition(":")` before its own quoted-phrase branch could see
the token, so `"Re: quarterly plan"` was read as an operator called `"Re`. It is now

```python
if separator and head and not head.startswith(PHRASE_QUOTE):
```

— **`name:value` is an operator only when `name` is unquoted**, which is the sentence
`constants._operator_token` has carried since round 13 ("a quoted widening scope operator is a
phrase search rather than an operator, and reading it as one would be a false refusal"),
applied where the reading is actually done. `PHRASE_QUOTE` is written once, in `constants`,
beside the negation prefix and the scope vocabulary.

**The fixture had the same defect, independently, and only execution found it.**
`tests/fixtures/mailbox.py::_token_matches` partitions on `:` before its own phrase branch, so
after the parser fix `"Re: quarterly plan"` reached `_operator_matches('"re', …)` and raised
`UnimplementedOperator`. The double is written from Gmail's documentation rather than from the
parser, and Gmail documents quotes as making their contents content — so the same clause is
correct there, and it is now written there.

### Executed evidence

`test_a_quoted_phrase_containing_a_colon_is_a_phrase_not_an_unknown_operator`: nine shapes a
user types (a reply subject, a time, a note prefix, a quarter label, a ratio, a budget line, a
URL, a phone-ish token, a bare `a: b`), each asserted to parse as a `phrase`, to carry no
`unknown_operators`, to reach the wire as `render() == the written token`, and to report
`term_coverage 1.0`. Plus a negated phrase, the `subject:"note: see below"` control that always
worked, and — the class this rule must **not** swallow — `thread:1837abf rollout`, which is
still an unproven operator, declared and kept off the wire (R-RETR-012 unregressed).

End to end: R-RETR's own `r10_phrase_refusal.py` now shows every one of its refusals answered
(`wire: [('"9:30 standup"', False)]`, `outcome: answered`, `term_coverage: 1.0`), and
`'"9:30 standup" thursday'` searches the phrase instead of silently dropping it.

### Reintroduction

Plant **P1**, anchor `1/1`, file changed, CAUGHT.

### What I could not establish

Whether Gmail's own parser reads `"9:30 standup"` as a single phrase or as two tokens. RO F3
documents quoting as grouping, and the double implements that reading; the live check is
**PF-9 / R-GMAIL**. The change can only widen what MailWeave sends (the token was previously
sent as nothing at all), so the risk direction is precision rather than recall.

---

## 3. Part 3 — R-RETR-019 and R-RETR-021. The invariant at the decomposition/scope join.

### The invariant, stated

> **A probe composed from a subset of a query's fragments searches the region the query
> named.** The fragments a probe may leave out are exactly those whose omission can only
> *widen* what it matches **inside that region**: a negation may be left out, because "and not
> this" removed is a superset; a mailbox-scope fragment may not, because removing it moves the
> probe into a different and **narrower** region and takes `includeSpamTrash` with it. The only
> rung allowed to change the region is the one whose published step is to replace it
> (AD A.7 L3), which replaces it **wholesale** and declares the replacement.

It is written once, in `query/analysis.decomposition_units_of`, beside the derivation
`mailbox_scope_of` that every rung reads.

**Why the invariant rather than a third fix.** Round 16 excluded a scope fragment from the
decomposition units — correctly, since a probe of the bare widening operator is a listing — and
read that exclusion as also excluding it *from the probes*, which is a second and different
decision. That produced R-RETR-019 at L1b (`|H| = 0` for the founding shape in spam) and, at
the same join, R-RETR-021 at L3 (a broadening probe conjoining the widening operator with the
narrowing location it was supposed to replace, searching the narrower one and declaring that
it had widened). Round 16 had already found and fixed an earlier instance at this join. Three
instances at one join is the join being under-specified, not three rungs being unlucky — so the
statement is made once and **the enforcement is one test over the whole ladder**.

The asymmetry that makes the statement precise, and that round 16 did not separate:

| fragment left out of a composed probe | effect | permitted |
|---|---|---|
| a negation (`-cutover`, `-from:x`) | the probe matches a **superset** within the same region: precision only | yes |
| a **narrowing** location (`in:inbox`) | superset within the default mailbox | yes |
| a **widening** mailbox scope (`in:anywhere`/`in:spam`/`in:trash`) | the probe moves to a **narrower** region and `include_spam_trash` flips with it: **recall, and unrecoverable** | no |

### What changed

* `analysis.mailbox_scope_of(constraints)` is the one derivation of "the region this query
  named": exactly the fragments `selects_something` rejects for naming a region, in every
  spelling `carries_nothing_but_mailbox_scope` normalises. A *negated* scope fragment is not
  one of them and is not carried — it excludes, and omitting an exclusion widens;
* `decomposition_units_of` prefixes that scope onto **every** unit's fragment, so
  `Probe.include_spam_trash` — which is derived from the probe's own `q` and cannot be
  supplied beside it — comes out right by construction rather than by memory. The scope
  constraint joins each unit's `constraints` (a row admitted by a scoped unit probe really is
  in the region asked for) but **not** its `derived_from`, which answers the different
  question §4 needs;
* `ExactOperatorRung` carries the same scope, for the same reason: without it a query naming
  spam probed the *default* mailbox at L0, could match an inbox message the query's own scope
  excluded, and D.3 rule 1b could halt the ladder on it before L1 ever applied the scope;
* `BroadeningRung._anywhere` replaces **every fragment that names a mailbox location**, not
  only the three widening ones. `constants.names_a_mailbox_location` is the vocabulary and it
  is written as the `in:` **prefix**, so a location Gmail names later is covered without an
  edit — `MAILBOX_LOCATION_PREFIX`, with `WIDENING_MAILBOX_OPERATORS` as its widening subset;
* and a location that was *replaced* is not one that was *enforced*
  (`is_the_widening_mailbox_operator` decides when the substitution is the identity) — which
  is Part 4's rule arriving inside Part 3's code.

### The single test that enforces it

`tests/test_lexical_ladder.py::test_every_probe_the_ladder_composes_searches_the_region_the_query_named`

It ranges over `LADDER` **by membership** and over a 4 × 13 cross-product of scopes and query
bodies (bare words at two/three/four units, phrases, participants, repeated operators, written
and relative windows, negations, an identity lookup, a `is:` state), and asserts of every
planned probe of every rung that every scope fragment the query wrote is in the probe's `q`
and that `include_spam_trash` agrees with the query. **The two exemptions are enumerated in
the test rather than assumed**, so a rung cannot acquire one by being written later:

* L2 may change the region when its **declared** drop is the scope constraint — a relaxation
  ROUTE-03 enumerates and `asked_for.dropped` names;
* L3's whole-mailbox step may replace it, and is required to *actually widen*
  (`include_spam_trash` true) rather than merely to say so.

Anti-vacuity is asserted twice: `len(LADDER) == 5`, more than 100 probes checked, and the
scoped decomposition shape is asserted to produce two probes both carrying the flag — without
the scope half of the invariant those are exactly the rows that regress.

### Executed evidence

`r25_scopedrop.py`, R-RETR's own reproduction, before and after:

```
before   wire [('in:anywhere rollout cutover', True), ('rollout', False),
                ('cutover', False), ('rollout cutover', False)]
         H = []   sources = []   outcome = inconclusive
after    wire [('in:anywhere rollout cutover', True), ('in:anywhere rollout', True),
                ('in:anywhere cutover', True)]
         H = ['sp-1', 'sp-2']   sources = [('t-sp', ['sp-1','sp-2'])]   outcome = answered
```

`r17_narrow_scope.py`, R-RETR's R-RETR-021 reproduction: `in:inbox is:unread`,
`in:drafts is:unread` and `in:chats has:attachment` now plan `in:anywhere is:unread` /
`in:anywhere has:attachment` — the location replaced, not conjoined — and
`in:anywhere is:unread` plans **nothing**, because the caller already asked for everywhere and
a probe identical to L1's own query is not a broadening (I-3).

On my own constructed recovery set (§6), all three scoped-spam/trash shapes recover with
`outcome: answered` and `term_coverage: 1.0`.

### Reintroduction

Plants **P5** (scope dropped from every unit), **P6** (only the widening locations replaced),
**P7** (a replaced location reported enforced) and **P16** (L0 drops the scope) — every anchor
`1/1`, every file changed, all four CAUGHT.

### What I could not establish

**`label:` naming a system mailbox.** `label:inbox is:unread` still composes
`in:anywhere label:inbox is:unread`: a probe that costs a Gmail call and does not widen.
Telling `label:inbox` from a user's own label needs a vocabulary of Gmail's system label names
that nothing in this repository can establish, and inventing one would be a claim about Gmail
dressed as a constant. It is a cost and a `scan_scope` entry, not a wrong row. **Named as a
residue in `names_a_mailbox_location`'s own docstring and left open** — §9, and it is the same
residue `widens_beyond_the_default_mailbox` already names at the same width for `label:spam`.

I also considered and **rejected** a "decline any broadening whose `q` is a token-superset of
the baseline" rule, which would have covered the `label:` case: it also declines
`in:anywhere is:unread` over the baseline `is:unread`, which *is* a genuine broadening because
the region widens. A rule that closes a residue by suppressing a correct probe is worse than
the residue.

---

## 4. Part 4 — R-RETR-020 (HIGH). `enforced` is what the executed rungs enforced.

### What changed

`asked_for.enforced` was *the parse minus the constraints an L2 relaxation gave up*, so every
rung except L2 was assumed to have carried everything. Two ordinary shapes made that false, and
neither is a relaxation, which is why the derivation could not see them:

* a run whose only evidence came from L3's whole-mailbox probe reported
  `enforced=('from','terms')`, `dropped=[]`, `term_coverage: 1.0` for a spam message from a
  different sender that L3 admitted **after dropping `from:`**;
* a D.3 rule 1b stop at L0 reported `enforced=('phrase','terms')` for a run whose only executed
  `q` was the phrase — a rung that never ran cannot have dropped anything.

"Not a relaxation" was being read as "was enforced". It is now derived:

* **`Probe.dropped` is populated at L3.** `BroadeningRung` returns a `Broadening(query,
  enforced, given_up)` rather than a pair, because a broadening **replaces** constraints with
  wider forms — a window `BROADENING_DATE_FACTOR` times as long, a participant turned into
  `{from|to}`, a named location turned into the whole mailbox — and a hit admitted by any of
  those need not satisfy what the caller wrote. `Probe.relaxes` stays false: a broadening is
  not the query giving a constraint up in the sense ROUTE-03 enumerates;
* **`assemble._routes(run)`** names the probes the response rests on: those whose **page
  returned rows**, and every executed probe when none did (a zero-hit response rests on all of
  them, and "the whole query was executed and matched nothing" is a different statement from
  "part of it was"). The count read is `ids_returned` and **not** `ids_admitted`, which is a
  delta — see the regression note below;
* **`assemble._decomposition_enforced(run)`** is L1b's contribution, at the rung level, because
  a decomposition probe carries one piece and its siblings carry the rest: whatever every
  executed probe carried whole (today, the query's scope), plus every constraint **all** of
  whose units were probed. It is credited only when a thread in the intersection is among the
  ones being disclosed;
* `enforced` is then the **union** over routes, minus the constraints a relaxation that
  matched something gave up. Union rather than intersection because the routes are
  alternatives: L1 finding rows while a broad L1b piece-probe also admits some does not make
  L1's enforcement untrue. What the union cannot do is invent an enforcement nobody performed;
* every constraint not in that union is a `DroppedConstraint` **naming the rung**, which is
  LEX-02's "every dropped signal is named with the rung that dropped it".

**The one rule left exactly as round 16 wrote it** is the relaxation's: a probe that relaxed a
constraint and matched something gave it up, read off the page's own count. Extending the
account to the other rungs must not weaken the one rung that already had one.

### The regression I introduced and caught, recorded rather than tidied away

My first version of `_routes` keyed on `ids_admitted`. That is a **delta** — what a probe was
the first to record — so a probe whose page returned rows an earlier probe had already admitted
reports an empty set while having matched exactly what is disclosed. It dropped such probes out
of the account. I found it by running my own end-to-end audit (§6), not by reasoning:
`from:ana@… from:bo@… cutover` reported `enforced=()` and `term_coverage 0.0` for a query whose
answer was disclosed. The old code's own docstring had already given the reason for reading the
page count, one rung over. It is now planted back as **P14** and caught by
`test_a_probe_whose_rows_an_earlier_probe_admitted_still_counts_as_a_route`.

### Executed evidence

R-RETR's own reproductions, after:

```
r14_l3only.py    enforced ('terms',)   dropped [('from', "no route this response rests on
                 carried 'from:bob@team.example': the evidence came from L3 …")]
                 term_coverage 0.5   constraint_drop_depth 1
r12_l0stop.py    '"vendor selection review" cutover' -> enforced ('phrase',)
                 dropped ['terms']   term_coverage 0.5
r13_enforced.py  CASE B (4 units, cap 3) -> enforced ('from',) dropped ['terms']
                 term_coverage 0.5   — the A.7 cap declared, which is R-RETR-024(c)
```

Tests: `test_a_route_that_widened_a_constraint_does_not_report_it_enforced` (the L3-only
recovery end to end, the L0 stop end to end, and the widening step at the plan layer),
`test_a_decomposition_that_never_intersected_does_not_report_the_query_enforced`,
`test_a_probe_whose_rows_an_earlier_probe_admitted_still_counts_as_a_route`.

### Reintroduction

Plants **P8** (L3 reports what it widened as enforced), **P9** (`enforced` is the parse minus
L2's drops again), **P14** (routes keyed on the delta), **P15** (L1b credited without the
intersection). Every anchor `1/1`, every file changed, all four CAUGHT.

### What I could not establish

* **A per-*row* statement of joint satisfaction.** `constraint_coverage` is per row and honest,
  and `enforced` is per response and now honest about the routes — but there is no field that
  says "this row satisfied the query as a whole", and the wire vocabulary has no spelling for
  one. For a query answered by L1b's intersection the *thread* satisfies the query and no
  single row does, which is the founding shape and not a defect; for a thread the intersection
  does not contain, the rows carry empty coverage and the response-level claim now excludes
  the constraint. Whether the schema should carry a third statement is **WS-10/WS-11**.
* Whether `constraint_drop_depth` should be the depth of one route or the count of distinct
  constraints some route dropped. I kept the second, which is what the wire model enforces
  (`len(dropped)`), and stated the alternative reading in the docstring so it is a choice
  rather than an accident.

---

## 5. Part 5 — ROUTE-01. Where the report/raise line falls, and why there.

### The line

> **A query gets a structured report whenever there is something true to report about it.
> A query is refused only when every field of the report would describe a search that had no
> subject.**

Concretely: **only an empty or whitespace-only `q` raises.** Everything else — a parse failure
(`the and of`, `?`, `(rollout OR escalation)`, `{…}`), a query naming only where to look
(`in:anywhere`, `in:spam`, `in:anywhere -invoice`), a `name:value` token MailWeave cannot prove
standing alone (`thread:1837abf`, `tel:…`), and a token that names nothing to match (`""`,
`" "`, `subject:`) — gets an envelope.

### The reasoning, since the work order asked for it

**Why those get a report.** Each of them has content a report can be *about*: a parse, one or
more tokens the response can name and say why it did not execute, in several cases a constraint
list, and five rungs whose non-application is a true statement. A caller receiving
`asked_for.dropped: [{"constraint": "unproven_operator", "why": "'thread:1837abf' is a
name:value token outside Gmail's documented operator set … The search ran without it"}]` plus
`not_tried` naming every rung can act on it — reword the query, quote the token, drop it. An
exception carrying one string in its message cannot be inspected field by field, cannot carry
`empty_diagnosis`, and — the point ROUTE-01 actually makes — *is not a response at all*, so a
calling agent receives an error rather than evidence about its own query. A.2 says there is
never a bare empty result; 17 of 50 queries producing no result whatsoever is further from that
than the bare empty payload the criterion was written against.

**Why the empty query does not.** Every field would be a fabrication in the shape of a fact.
`term_coverage` computes 1.0 — nothing was dropped, because nothing was asked.
`empty_diagnosis` computes `complete` — no drop went untried, because there is no drop.
`asked_for.parsed` is empty operators, empty terms. Together they read *"MailWeave searched and
found nothing, and nothing you asked for was given up"* about a question nobody put. That is
the **nonexistence claim** ROUTE-01 forbids in its other half, and OD-2's whole point is that
MailWeave never claims absolute mailbox nonexistence. A refusal naming the empty input is the
honest answer here; a report would be the dishonest one. I did not convert every raise into a
report, and this is the case where I did not.

**The boundary is a property of the input, not of the parse**, which is what makes it
checkable: `not parsed.raw.strip()`. A query that wrote *something* the parser could not use has
that something to report; a query that wrote nothing has nothing.

### What changed

* `LadderRunner.run_parsed` returns a `LadderRun` in which every rung is `not_applicable` —
  the rare case where that is literally true of all five — instead of raising, for every
  unplannable query except the empty one. Zero Gmail calls either way: `plan_ladder` is
  consulted before any probe executes;
* `assemble` builds the report from it. `outcome: inconclusive` (never `not_found`, per OD-2,
  since no applicable route ran), `sufficiency: insufficient`, `rungs: ()`, `not_tried`
  naming all five `not_applicable`, `empty_diagnosis` present, and `asked_for` carrying the
  parse-time declarations **plus** a per-constraint drop whose `why` is
  `why_this_q_is_not_a_probe`'s own sentence — so `in:anywhere` reports `enforced: ()`,
  `term_coverage: 0.0` and the reason nothing could be planned, rather than claiming to have
  enforced a constraint it never sent;
* `Envelope._no_bare_empty_response` now requires `report.rungs or report.not_tried` rather
  than `report.rungs`. **This is a validation rule, not a schema change**: no field, no
  vocabulary value and no contract sentence changes, and what the rule forbids is unchanged —
  silence about the ladder, silence about the scan, silence about the drops. Its previous form
  demanded that a rung have *executed*, which forced a false `not_tried` entry for the one
  query where none did; that was the reason round 16 gave for escalating to WS-10, and it is
  removed rather than deferred. The other two checks are untouched;
* `QueryNotSearchable`'s docstring now carries the line and the reasoning above.

### Executed evidence

`test_a_query_the_parser_produces_nothing_from_is_reported_not_scanned` over eight shapes:
`box.queries == []`, `ledger.hit_ids` empty, `api_calls == 0`, `rungs_run == ()`, every rung in
`rungs_skipped`, and then on the envelope — `rungs == ()`, all five rungs in `not_tried` under
`not_applicable`, an `empty_diagnosis`, and **every declaration `dropped_declarations` produces
present in `asked_for.dropped` with a non-empty `why`**.

`test_a_query_that_asked_for_nothing_at_all_is_refused_rather_than_reported` asserts both
directions, so the line cannot be satisfied by refusing everything or by reporting on
everything.

`test_a_query_that_names_only_where_to_look_is_reported_not_scanned` (six shapes) additionally
asserts `enforced == ()` and `term_coverage == 0.0` — the report does not claim the constraint
it parsed was enforced.

**On R-RETR's own 50-query audit, re-run as a regression only** (`r27_refusal_audit.py`):
17 refused → **10 with no probe, of which 8 now receive a structured report and 2 (`''`,
`'   '`) raise**. The eight quoted-phrase-with-colon refusals are gone entirely. I report that
as a regression check, not as evidence; my own numbers are in §6.

### Reintroduction

Plants **P10** (raise instead of report) and **P11** (the envelope refuses a zero-rung report
however well accounted for) — anchors `1/1`, files changed, both CAUGHT.

### What I could not establish

* Whether `not_applicable` is the *right* value for all five rungs here, as against a
  vocabulary value meaning "the parse gave this rung nothing to plan". `not_applicable` means
  "the rung could not have helped this query", which is true — and this is the one case in the
  codebase where it is true of every rung at once. A finer value is a **D.2 vocabulary change,
  WS-10/WS-11**, and would be the same escalation A8 note 1 already carries.
* Whether a calling agent prefers an exception or an envelope for the empty query. That is a
  product question with a real answer only from use; I chose the one that cannot state a
  falsehood.

---

## 6. My own adversarial set, and the numbers I got

**I did not tune against either R-RETR instance's probe sets.** I ran their Parts 1–4
reproductions before changing anything (the work order asked for that) and again afterwards as
regression checks, and every number below is from sets and mailboxes I built:
`/tmp/r17impl/{harness,box,a1_plausible,a3_sweep,a5_preservation,a6_recovery}.py`. Nothing in
them is copied from `/tmp/rretr15` or `/tmp/rretr16`; my mailbox, my categories, my seeds.

### (a) The plausible-query audit — 72 queries, 16 categories

Categories chosen from what someone types about work mail, not from a finding list: one bare
word; two/three/five bare words; a plain quoted phrase; a quoted phrase with a colon; operator
plus terms; a repeated operator; negations; mailbox scope; dates (absolute, relative, crossing);
booleans and grouping; an unprovable `name:value`; tokens that name nothing; a question in
words; identifier lookups; case, punctuation and unicode shape; and one eight-constraint
conjunction.

The "before" column is measured, not remembered: the round-16 tree no longer exists, so it is
reconstructed in the scratch tree by planting the inverse of every round-17 change that can
alter whether a query is answered at all (**P1, P3, P4, P5, P10, P11**), with each anchor
asserted and each file asserted changed (`/tmp/r17impl/a4_before_after.py`).

| | round 16 (planted back) | round 17 |
|---|---|---|
| **raised — no envelope at all** | **16 / 72 (22%)** | **0 / 72** |
| envelope with no Gmail call (searched nothing, reported why) | 0 | 13 / 72 |
| reached Gmail | 56 | 59 |
| `outcome: answered` | 45 | **47** |
| `outcome: inconclusive` | 11 | 25 |
| queries reporting `answered` for a `q` that filters nothing | **5** (`""`, `" "`, `subject:`, `subject:""`, `""""`) | **0** |

The 16 round-16 refusals were the 8 quoted phrases with a colon, 4 scope-only queries, 2 of the
grouping shapes, and the 2 unprovable `name:value` tokens standing alone. The 13 no-Gmail-call
queries under round 17 are the same classes **minus** the eight phrases (now searched) **plus**
the five vacuous-token queries (which round 16 answered by reading the mailbox).

**No query round 16 answered legitimately became `inconclusive`.** The per-query diff
(`a7_diff.py`, same plant reconstruction) shows exactly 21 outcome changes: the 16 that raised
now report (7 `answered`, 9 `inconclusive`), and the 5 vacuous-token queries that round 16
called `answered` over a whole-mailbox read now report `inconclusive`. Nothing else moved.

**Part 4's effect is on the claim, not on the disclosure**, and it shows as coverage rather
than as outcome. Reconstructing the whole of round 16 (every plant except P2, which changes
nothing observable) and comparing the 56 queries that produce an envelope under both:
**17 report a lower `term_coverage`** — every one a case where the disclosed evidence came from
routes that did not carry the whole query (`rollout cutover handover` 1.0 → 0.0, the four
natural-language questions 1.0 → 0.0, the eight-constraint conjunction 1.0 → 0.43) — and **one
reports a higher one**: `from:ana@… from:ana@… cutover` 0.0 → 1.0, because R-RETR-025's
de-duplication stopped a duplicate probe from emptying the intersection. None of the seventeen
lost a source; the disclosure is the same rows with a smaller claim over them.

### (b) A plan-layer sweep of my own — 18,103 queries

`a3_sweep.py`, over a 46-token vocabulary of my own including every shape this round changed
(vacuous tokens, quoted phrases with colons, all three widening and four narrowing locations,
negated scope, unimplemented operators, grouping tokens): every single, **every ordered pair**,
and a strided walk over triples — which is the bound round 16's own sweep named as its limit.

```
swept              : 18103
raised             : 0
planned a listing  : 0
lost its region    : 0
```

### (c) Evidence preservation, end to end — 400 randomised trials

`a5_preservation.py`, mailboxes of 1–22 messages over random threads, senders, label sets
(INBOX/UNREAD/SPAM/TRASH/IMPORTANT), attachments and rfc822 ids, against 26 query shapes,
asserted from outside the process against the ledger and the envelope:

```
trials 400   envelopes 400   refusals 0   crashes 0
H subset of (disclosed union withheld)  : 0 violations
disclosed and withheld disjoint         : 0 violations
no phantom id                           : 0 violations
reads outside what the query asked for  : 0
```

That last line is the exit condition's other half, and it is asserted as a rule rather than as
a spot check: for every executed probe with `include_spam_trash` true, either the caller's own
query widened, or the probe is L3's published widening step.

### (d) Recovery on cases where I planted the answer — 20/20

`a6_recovery.py`, twenty constructed cases, each with the answer in a known thread and twelve
noise threads: two/three bare words; the same in spam and in trash with the scope named; the
same anywhere; operator plus term, in the default mailbox and in spam; two senders; phrase plus
term; a reply subject as a phrase; subject operator plus two words; a written-out window; a
relative window; a negation; a repeated identical operator; a boolean the parser drops; an
unprovable operator; an empty phrase beside two words; case and punctuation; and four units
against the cap of three. **20/20 recovered.**

**This is a constructed-case measurement and not a recall rate.** LEX-03's and ROUTE-02's bars
are `[UNSET — register at G0]` against corpora that do not exist, and no number here is offered
against them. **WS-16.**

Two rows in it are worth stating because they read as failures and are not:
`rollout cutover handover` and `rollout cutover handover switchover` recover the thread and
report `inconclusive` with `term_coverage 0.0`, because the intersection is empty — the third
probe's entire contribution consists of ids an earlier probe already admitted, which is the case
`Decomposition`'s docstring bounds. The thread is found and disclosed; the claim over it is
smaller than the disclosure, which is the direction this round is moving in.

---

## 7. Have I trusted a peer rather than checking it?

I asked it four times. **Three of the four were answered by execution, and reasoning would not
have found any of those three.**

1. *The tokeniser reads `name:value`. What else in this repository reads `name:value` out of a
   query string?* — `constants._operator_token` (already correct, and its docstring had been
   saying so since round 13), `matchable_content_of` (written with the rule from the start),
   and **`tests/fixtures/mailbox.py::_token_matches`**, which had the identical defect from its
   own independent code. I did not deduce that: the parser fix made the double raise
   `UnimplementedOperator` on the first end-to-end run.
2. *The scope invariant is a rule about L1b. Which other rungs compose a `q` out of a subset of
   the query's fragments?* — L0 (fixed; it could stop the ladder on a message the query's own
   scope excluded), L3 (fixed, and it turned out to be R-RETR-021, a finding I had filed under
   a different part), L2 (declares its drop, so exempt and enumerated as such in the test), L1
   (carries everything). This one *was* answered by reasoning, and the reason it was is that the
   invariant had already been written down: the question "which rungs does this sentence apply
   to?" is answerable when there is a sentence.
3. *`enforced` is derived from routes. What number does the existing code read to identify one,
   and why?* — I keyed on `ids_admitted` and my own audit showed `term_coverage 0.0` for a query
   whose answer was disclosed. The delta/page-count distinction was already written in
   `_asked_for`'s own docstring for L2; I extended the function without extending the sentence.
   Planted back as P14.
4. *L1b's rung-level enforcement is a claim about the rung. When is it not true?* — when the
   intersection is empty, which my audit showed as `enforced=('from','phrase')` on a query whose
   relaxation had restored results. Planted back as P15.

**Where I have not closed the question.** The invariant test covers the *plan* layer over a
constructed population; it says every planned probe searches the region the query named, and it
does not say the region is the *useful* one. It also does not reach a rung that does not exist
yet — but because it iterates `LADDER` and asserts `len(LADDER) == 5`, a sixth rung arrives in
it the day it is added, with its exemption (if it needs one) having to be written into the test
explicitly.

---

## 8. Reintroduction checks

Harness: `/tmp/r17impl/plant.py` and `/tmp/r17impl/plants.py`. Discipline, stated because each
of these has cost this project checks before:

* every plant **asserts its anchor matched exactly the expected number of times** before
  anything is written, and **asserts the file changed** afterwards, printing the before/after
  content hash. Two plants aborted on their own anchor assertion during development (P7 and P8,
  after `ruff format` rewrapped the code they were written against) and were re-derived from
  the real file rather than forced;
* `mailweave.__file__` **and** `tests.__file__` are asserted to resolve inside the scratch tree
  before any plant runs, with `PYTHONPATH` set on the resolution check and on every test run —
  the venv installs `mailweave` as an editable path configuration, so a scratch copy silently
  tests the real tree otherwise. The assertion `str(SCRATCH) in where` cannot pass for
  `/root/mailweave/...`, and the negative is asserted too;
* the scratch tree is asserted **green on every target test before the first plant**, so a
  plant cannot be "caught" by a test that was already red;
* `__pycache__` is cleared before every run and the source is restored from the real tree
  between plants, so one plant cannot leak into the next.

```
imports resolve into the scratch tree:
   /tmp/r17impl/tree/server/src/mailweave/__init__.py
   /tmp/r17impl/tree/tests/__init__.py
scratch tree green on all 11 target tests before planting

CAUGHT  anchor 1/1, file changed  P1   the tokeniser reads a quoted phrase's colon as an operator separator again
CAUGHT  anchor 1/1, file changed  P2   `carries_nothing_to_select_by` judges spelling only, without the content clause
CAUGHT  anchor 1/1, file changed  P3   a token that names nothing to match becomes an ordinary constraint again
CAUGHT  anchor 1/1, file changed  P4   `why_this_q_is_not_a_probe` stops refusing a q that filters nothing
CAUGHT  anchor 1/1, file changed  P5   decomposition drops the query's mailbox scope from every unit (R-RETR-019)
CAUGHT  anchor 1/1, file changed  P6   L3 replaces only the widening locations and conjoins the narrowing ones
CAUGHT  anchor 1/1, file changed  P7   L3 reports a location it replaced with a wider one as enforced
CAUGHT  anchor 1/1, file changed  P8   L3 reports a constraint it widened (dates, participants) as enforced
CAUGHT  anchor 1/1, file changed  P9   `enforced` is the parse minus L2's drops again (R-RETR-020)
CAUGHT  anchor 1/1, file changed  P10  an unplannable query raises instead of producing a structured report
CAUGHT  anchor 1/1, file changed  P11  the envelope refuses a report whose rungs are empty however well accounted for
CAUGHT  anchor 1/1, file changed  P12  `empty_diagnosis` mints a budget affordance no budget can act on (R-RETR-023)
CAUGHT  anchor 1/1, file changed  P13  a repeated identical fragment is two units with one label again (R-RETR-025)
CAUGHT  anchor 1/1, file changed  P14  the route derivation keys on the admission delta, losing a relaxation's drop
CAUGHT  anchor 1/1, file changed  P15  L1b's rung-level enforcement is credited without the intersection (R-RETR-024)
CAUGHT  anchor 1/1, file changed  P16  L0 drops the query's mailbox scope from its branch probe
all 16 plants caught by the tests that name them
```

**One plant was MISSED on its first run and that is recorded rather than tidied away.** P2
removes the content clause from `carries_nothing_to_select_by`, and nothing failed — because
the parse layer (P3's fix) removes such tokens before a constraint exists, so the fragment-level
clause has no reachable trigger *today*. It is defence in depth at the layer where a rung
composes a `q` from a subset of the query's fragments, and a rule that is never executed is a
claim rather than a rule. I added the direct fragment-level assertion to the test that names it
and re-ran the whole sweep from a fresh scratch tree. **The clause's unreachability today is
recorded in §9 rather than hidden by the test that now covers it.**

---

## 9. Part 6 — the MEDIUMs and the LOW, and everything left open

| Finding | Disposition | Evidence |
|---|---|---|
| **R-RETR-021** narrowing scope conjoined at L3 | **closed for `in:`**, open for `label:` naming a system mailbox | `test_a_broadening_probe_does_not_carry_a_narrower_scope_than_the_one_it_widens_to`, driven from `WIDENING_MAILBOX_OPERATORS` **plus** a named `NARROWING_MAILBOX_LOCATIONS` vocabulary — the round-16 test asserted the single spelling its own fix covered. `r17_narrow_scope.py` confirms end to end |
| **R-RETR-022** every refusal produced no response | **closed** — §5 | `test_a_query_the_parser_produces_nothing_from_is_reported_not_scanned`, 8 shapes; R-RETR's own audit 17 → 2 actual raises |
| **R-RETR-023** an affordance no budget can act on | **closed** | `RelaxationRung.plannable_drops` shares one expression with `plan` (`_relaxed_query`), so the offer cannot promise a probe the planner has already refused. `test_a_drop_no_budget_can_reach_is_not_offered_a_budget`, with a crowded-query control so this is not a rule that removes affordances. R-RETR's `r24_k1.py` now shows `affordance: None` |
| **R-RETR-024** the decomposition cap's precision cost, undeclared | **partly closed, and I say which part** — see below | `test_a_decomposition_that_never_intersected_does_not_report_the_query_enforced`; `r13_enforced.py` CASE B now reports `enforced ('from',) dropped ['terms'] term_coverage 0.5` |
| **R-RETR-025** `ConstraintUnit.label` not unique | **closed** | a repeated identical fragment is one unit (`dict.fromkeys`), which fixes the label collision and the wasted A.7 probe slot by the same change. `test_a_repeated_identical_fragment_is_one_unit_and_every_label_is_unique` over six collision shapes, plus the control that two *different* fragments are still two units |

### R-RETR-024, precisely: what is closed and what is not

**Closed.** The response no longer claims a constraint the cap prevented it from probing
(`enforced` drops it, named with L1b), and `outcome` for an L1b-only run is already derived from
the intersection rather than from disclosure, so `rollout cutover handover` reports
`inconclusive` where round 16 reported `answered`.

**Not closed.** When L1 *does* find something and L1b's broad piece-probes also pull unrelated
threads into `H`, the response reports `answered` with `term_coverage: 1.0` over a disclosure
that includes those threads — `label:inbox cutover` discloses twelve threads, eleven of which
match only `label:inbox`. Every one of those rows carries an honest `constraint_coverage` and
`scan_scope` lists the probes, and the response-level claim is true **of the route that
answered** (L1 carried both constraints and matched). What is missing is a way to say "these
rows answer the query and those were obliged by the ledger", and there is no field for it: it is
the same schema gap as §4's residue. **WS-10/WS-11**, with this reproduction.

### Open, with the reason and the workstream

| Not closed | Reason | Owner |
|---|---|---|
| `label:` naming a system mailbox is not recognised as a location, so L3 can still compose a broadening that does not broaden for that one spelling | needs a vocabulary of Gmail's system label names that nothing here can establish; guessing at it would be a claim about Gmail dressed as a constant. Named in `names_a_mailbox_location`'s own docstring | **A.6 / R-GMAIL** (live check), or an architecture decision |
| a query term made of format characters (`roll­out`) is sent verbatim and matches nothing | whether a user's *query* should be normalised the way mail *text* is, is an A.6 policy question, not an implementer's call (AL §8) | **A.6 / WS-10** |
| a trailing-punctuation term (`cutover.`) is sent verbatim | same class, same reason; both are pre-existing and neither is this round's | **A.6 / WS-10** |
| the fragment-level clause of `carries_nothing_to_select_by` has no reachable trigger today, because the parse layer removes vacuous tokens first | it is the same sentence written where a rung composes a `q` from a subset, and removing it would leave the next such rung unguarded. Executed directly rather than left as a claim | recorded here; nothing to build |
| A.8a branch E-c says the identifier is "executed as a quoted single-token query", and L0 now sends the query's mailbox scope beside it | the deviation is in the conservative direction (the branch fires over the region the caller asked about instead of a different one) and `evaluate_exact_signal` still finds the token, but whether A.8a's wording forbids the conjunct is an architecture reading | **orchestrator / A.8a** |
| a third `EmptyDiagnosisStatus` for "this drop is structurally unprobeable at any budget" | `EmptyDiagnosisStatus` is a closed wire vocabulary; adding a member is a contract change. What a reader sees today is `untried_drops` naming the drop, no affordance offering to reach it, and `not_tried` naming L2 `not_applicable` | **WS-10** |
| a response-level field separating "rows that answer the query" from "rows the ledger obliged" | no spelling in the schema; §4 and R-RETR-024's residue are the same gap | **WS-10/WS-11** |
| **R-RETR-015**'s single-unit residue (one bare word, one quoted phrase, no term-level relaxation) | unchanged from round 16: both named fixes change A.7's published L3 step and L2 cost row | **A.7 / WS-10** |
| `not_tried[].why` for a rung a stop or the escalation policy declined | closed D.2 vocabulary has no true value; already escalated as A8 note 1 | **WS-10/WS-11** |
| **EV-02, EV-04, EV-06, LEX-03, ROUTE-02** rates | need a seeded corpus, Baseline B/D, holdout seeds and a counting proxy. Every number in §6 is on sets I constructed and is offered as nothing else | **WS-16** |
| **LEX-04**'s network-level cost bar | must come from network-level counts, not the meter's self-report | **WS-16 / R-PERF** |
| **PF-1, PF-2, PF-9, PF-13, PF-14, PF-20** | live-account measurements | credentials, then R-GMAIL |
| the fixture evaluates 13 of 21 `OperatorName` members | correctly strict — an ignored operator would make a rung look successful — and a real ceiling on every end-to-end statement above, mine included | **WS-16** |

---

## 10. Every docstring claim my diff makes about coverage, with its executed evidence

The mechanical half is `test_every_test_a_source_docstring_names_exists`, which reads every
string constant in both source trees and requires each `test_…` identifier to resolve. **It
fired on me across two runs, naming five citations** — four tests I had cited in a
docstring before writing them, and one left stale by a rename — which is the sweep doing its
job.

| Claim | Where | Executed by |
|---|---|---|
| a token's matchable content is empty **iff** it names nothing to match, for spellings nobody enumerated including future operators | `constants.matchable_content_of` | `test_a_token_that_names_nothing_to_match_is_not_a_probe_however_it_is_spelled` — 16 reported shapes plus a family generated from six runtime-derived `Cf` characters, at four layers |
| `carries_nothing_to_select_by` has three clauses, and the third is round 17's | `constants.carries_nothing_to_select_by` | same test's direct `selects_something` assertions; plant **P2** |
| `name:value` is an operator only when `name` is unquoted | `query.operators.tokenise` | `test_a_quoted_phrase_containing_a_colon_is_a_phrase_not_an_unknown_operator` — 9 shapes, a negated phrase, the `subject:"…"` control, and the unproven-operator class it must not swallow |
| the invariant: every composed probe searches the region the query named | `query.analysis.decomposition_units_of` | `test_every_probe_the_ladder_composes_searches_the_region_the_query_named` — 4 × 13 queries over all five rungs, >100 probes, exemptions enumerated, anti-vacuity asserted |
| a widening scope fragment is carried by every unit and enforced by every unit probe | `retrieval.ladder.DecompositionRung._probe` | `test_a_mailbox_scope_fragment_is_not_a_decomposition_probe_of_its_own`, rewritten to the invariant and asserted over the whole `WIDENING_MAILBOX_OPERATORS` vocabulary |
| `ConstraintUnit.label` is unique within a parse | `query.analysis.ConstraintUnit` | `test_a_repeated_identical_fragment_is_one_unit_and_every_label_is_unique` — six collision shapes and the control |
| L3 replaces **every** mailbox location, not only the widening ones | `retrieval.ladder.BroadeningRung._anywhere` | `test_a_broadening_probe_does_not_carry_a_narrower_scope_than_the_one_it_widens_to`, driven from two named vocabularies |
| a constraint L3 widened or replaced is not one it enforced | `retrieval.ladder.Broadening`, `_widened`, `_anywhere` | `test_a_route_that_widened_a_constraint_does_not_report_it_enforced` |
| `enforced` is derived from what the executed rungs enforced | `retrieval.assemble._asked_for` | same test (L3-only recovery, L0 stop) and `test_a_decomposition_that_never_intersected_does_not_report_the_query_enforced` |
| `_routes` reads the page's own count, not the admission delta | `retrieval.assemble._routes` | `test_a_probe_whose_rows_an_earlier_probe_admitted_still_counts_as_a_route`, which asserts the fixture really produces the overlap before asserting the consequence |
| L1b enforces through its intersection and the A.7 cap is declared when it binds | `retrieval.assemble._decomposition_enforced` | `test_a_decomposition_that_never_intersected_does_not_report_the_query_enforced` (both directions, plus the over-cap case) |
| a budget affordance is minted only when a budget is what stands in the way | `retrieval.assemble._empty_diagnosis`, `RelaxationRung.plannable_drops` | `test_a_drop_no_budget_can_reach_is_not_offered_a_budget`, with the crowded-query control |
| an unplannable query is reported, and only an empty one is refused | `retrieval.ladder.run_parsed`, `errors.QueryNotSearchable` | `test_a_query_the_parser_produces_nothing_from_is_reported_not_scanned` (8 shapes), `test_a_query_that_asked_for_nothing_at_all_is_refused_rather_than_reported` (both directions), `test_a_query_that_names_only_where_to_look_is_reported_not_scanned` (6 shapes) |
| a report naming every rung as not tried is not a bare empty result | `envelope.response.Envelope._no_bare_empty_response` | the same tests; plant **P11** |
| the `label:` residue L3 cannot see | `constants.names_a_mailbox_location` | **not a coverage claim — it is named as a residue and left open** (§9). No test asserts it is closed, because it is not |

**Claims I did not re-measure.** `_units_of_one`'s inherited "757 raised, 712 of them at this
rung" is round 16's number about code that no longer exists; I did not re-derive it, and my own
18,103-query plan-layer sweep returns 0 raised, which is consistent with it having been fixed
rather than a re-measurement of it.

---

## 11. Gates, as run

```
ruff check .                     All checks passed!
ruff format --check .            153 files already formatted
mypy --strict                    Success: no issues found in 127 source files
python -m tools.guards           guards clean: forbidden-import, generative-client,
                                 gmail-endpoint, ground-truth-isolation, scope-literal,
                                 unaudited-disk-write, unwrapped-http-client over server/src
pytest -q -m "not network"       2,248 passed          (re-counted independently via
                                                        --collect-only -q summed per file = 2,248)
python tools/rubric_status.py    criteria 113; PASS 6 / FAIL 0 / BLOCKER 0 / NOT TESTED 107
  --check                        reviewer transitions recorded: 11        (unchanged)
```

`generative_llm_calls = 0` is enforced by the `generative-client` guard, in that clean list.
Nothing this round imports a model, embeds anything or consults corpus frequency; no test in it
touches the network (`conftest.py` denies `socket.connect`), and no fixture carries real or
realistic personal mail — `test_no_fixture_in_this_file_carries_anything_that_could_be_real_mail`
executes that rather than asserting it. Every address in the material I added uses the reserved
`.example` / `.invalid` TLDs and every subject and body is invented for a structural property.
