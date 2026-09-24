# ROUND 18 — implementer's report

**Implementer:** round-18 instance, 2026-09-04. Working tree `/root/mailweave`, not a git repo.
**Binding:** `docs/OWNER_DECISIONS.md` OD-5 and `docs/ARCHITECTURE_AMENDMENTS.md` A9, read before
anything was written. `docs/reviews/ROUND_18/WORK_ORDER.md` Parts 0–6 and the owner's four restated
instructions.

Before changing anything I ran the three reviewer reproductions the work order names for Parts 1–3
(`/tmp/rretr17/p9_negscope.py`, `p22_negphrase.py`, `p3_l0ident.py`) and reproduced all three exactly
as filed. Those runs are regression checks against a prior instance's files and are labelled as such;
**every number I report as mine comes from sets I built** (`/tmp/claude-0/.../scratchpad/my_sweep.py`,
`my_trials.py`, `my_trials_overflow.py`), and nothing in `/tmp/rretr15`, `/tmp/rretr16` or
`/tmp/rretr17` was used to construct any of them.

---

## 0. The re-derived asymmetry rule

This is the round's most important output, so it is first. It is stated **once**, in
`server/src/mailweave/constants.py::declares_the_search_region`, and every other statement of it in
the tree points at that one.

> **A fragment of a query either *declares the region* the search runs over — which messages Gmail
> will consider at all, and with them whether `includeSpamTrash` is set — or it *filters within*
> whatever region is being searched. A probe composed from a subset of a query's fragments may leave
> out a filter: omitting one can only widen the match **inside** the region, which costs precision
> and never recall, and is the direction such a probe is allowed to be wrong in. It may not leave out
> a region declaration: omitting one widens nothing, it moves the probe to a *different* region,
> where it can match messages the query excluded and miss messages the query asked for. **Polarity
> decides which region a declaration names. It never decides whether a fragment is one.**

**Why this is the derivation and not two operator names.** The question the rule asks is *what does
this operator do* — select a region, or constrain within one — so the predicate asks
`names_a_mailbox_location` (Gmail's location prefix, written as a **prefix** precisely so a location
nobody has enumerated is covered) after stripping polarity, because polarity is not part of the
question. **No predicate added this round tests for a particular operator value** — not `in:spam`,
not `in:trash`, not `label:`. The only vocabulary it consults is `MAILBOX_LOCATION_PREFIX`, which
already existed and is written as a *prefix* for exactly this reason. A scope operator added tomorrow
is covered in both polarities the moment it is a location, with no second edit; a *filter* added
tomorrow is covered because it is not one.

The one place two operator values are written this round is Part 0's `REGION_LABEL_BY_OPERATOR`, and
it is a different question: which *label id* Gmail states for a message in each region. That cannot
be derived (Gmail's `in:drafts` is the label `DRAFT`), it is written through the existing
`SPAM_OPERATOR`/`TRASH_OPERATOR` constants rather than as new literals, and its keys are held to
`WIDENING_MAILBOX_OPERATORS - {ANYWHERE_OPERATOR}` by execution — so a region added to one vocabulary
and forgotten in the other fails a test.

**The single test that enforces it over the operator family** is
`tests/test_lexical_ladder.py::test_every_probe_the_ladder_composes_searches_the_region_the_query_named`.
Its population is generated, not listed:

* the region half from `NARROWING_MAILBOX_LOCATIONS` and `WIDENING_MAILBOX_OPERATORS`, each in both
  polarities — 21 region prefixes including the empty one;
* the filter half from **every member of `OperatorName`**, in both polarities, with a representative
  value (`OPERATOR_FAMILY_VALUES`), plus eight text shapes. A member added to the enum without a
  value fails `test_the_operator_family_vocabulary_covers_every_operator_this_parser_knows`, so the
  sweep cannot be narrowed by adding an operator.

It asserts four things of every probe of every rung, and the last two are new:

1. every region fragment the query wrote is in the probe's `q`;
2. `include_spam_trash` agrees with the query's own render;
3. **the narrowing half** — no probe names a region the query did not write (R-RETR-031: the
   round-17 test asserted only that *widening* fragments were carried, so a probe that *added*
   `in:inbox` was invariant-clean);
4. **the L3 exemption is a positive assertion, not a `continue`** (R-RETR-031). A probe that changed
   the region is identified by *what it did* — its region set is not the query's — rather than by
   its `q` beginning with the widening operator, which was true of L1's own query and of a probe
   that widens and then restricts. Such a probe must be L3, must genuinely widen, may only run over
   a query that declared no region, and every region fragment it carries must be the widening
   operator itself.

Anti-vacuity, four ways: `len(LADDER) == 5`; `checked > 400` (actual **3,765** probes checked over
1,050 queries);
`swept_operators == {member.value for member in OperatorName}`; and a scoped decomposition really
does produce two spam-widened probes. **R-RETR-031's own two plants, run against this test alone:**

```
I5  a decomposition unit prefixed with a location the query never wrote   CAUGHT
I3  an L3 probe that declares a widening and conjoins a narrowing location CAUGHT
```

Both are now standing entries R15 and R16 of the replant manifest, so the claim "the invariant is
enforced once, by one membership test" is executed on every replant run rather than asserted.

---

## 1. Part 0 — mailbox provenance is a field (OD-5 point 1, A9-A1)

**What changed.** `MessageRow` gains `mailbox: MailboxProvenance`, a required field. The model has
two stated fields and two computed ones:

| field | kind | meaning |
|---|---|---|
| `observed` | stated | did any observation state this message's labels? |
| `labels` | stated | the label ids the observation stated, verbatim |
| `regions` | **computed** | `constants.mailbox_regions_of(labels)` — the regions outside the default mailbox |
| `outside_the_default_mailbox` | **computed** | `bool(regions)` — the one boolean a caller branches on |

**Why `regions` is computed rather than accepted.** OD-5 names the defect: *a value accepted from
the caller when the same value is already derivable from what was observed*. Making `regions` a
`computed_field` means there is **no place to put** a provenance that disagrees with the labels the
same row reports — `MailboxProvenance.model_validate({"observed": true, "labels": [], "regions":
["spam"]})` is refused by `extra="forbid"`, which is executed in
`test_a_provenance_cannot_state_a_region_its_labels_do_not_carry`.

**Why `labels` is on the wire.** For the reason `CollapsedRun.member_ids` is: without the input, a
reader cannot check the derived claim against anything, and a derived claim whose input the response
withholds is a claim taken on trust. Gmail states label **ids**; a user's own label is an opaque
`Label_N` id whose display name lives behind `users.labels.list`, which this server does not call,
so no mail-derived text reaches the wire through this field.

**Where it is derived.** `retrieval/assemble.py`, from `Message.label_ids` of the `threads.get`
response the row comes out of, and from nothing else. Every row gets it — matched, stub and
thread-map alike — because a thread map can carry a spam reply into an otherwise ordinary thread.

**`observed` is a third state, not a flag.** `messages.list` returns no labels, so a row the ledger
placed but no label-bearing observation touched reports `observed: false` and no regions — "this
response does not know", which is not the same fact as "this message is in neither region". It is the
distinction `observed_internal_dates` draws by *absence* (amendment A6), made explicit because a
boolean has no absent value.

**The vocabulary is one vocabulary with two spellings.** `REGION_LABEL_BY_OPERATOR` maps the `in:`
operator that names each region to the label id Gmail states, and
`test_the_region_label_vocabulary_is_the_widening_operator_vocabulary` holds its keys to
`WIDENING_MAILBOX_OPERATORS - {ANYWHERE_OPERATOR}` by execution. The label ids are **written**, not
derived by upper-casing the operator: that derivation is right for these two by luck and wrong in
general (`in:drafts` is the label `DRAFT`), and a rule that is right twice by accident is a claim
about Gmail's label vocabulary nothing here can establish (**R-GMAIL**).

**Executed.** Over 1,800 randomised end-to-end trials on my own mailboxes (§6), **0** rows whose
`mailbox.regions` disagreed with the SPAM/TRASH membership of the labels the fixture planted, read by
an oracle written in the trial harness rather than by calling the derivation. 8,697 rows seen, 3,406
of them outside the default mailbox.
`test_a_rows_provenance_does_not_change_with_the_query_that_found_it` is the property that fails for
*every* wrong derivation at once: the same message found three ways reports one provenance, and a
provenance read off the probe's `includeSpamTrash`, off the rung or off the `q` changes when the
query does.

**The census moves 208 → 213**, documented in `tests/test_field_census.py` with the split between
the two stated and the two computed fields, because the point of the schema change is exactly that
the branchable values are derived.

---

## 2. Part 1 — `-in:spam` never searches spam (OD-5 points 2 and 3, A9-A2/A3, R-RETR-026)

**Reproduced first.** `/tmp/rretr17/p9_negscope.py` before the change:

```
-in:spam borogrove   wire [('-in:spam borogrove', False), ('borogrove', False),
                           ('in:anywhere borogrove', True)]
                     sources t-sp q-2 matched (SPAM), t-tr q-3 matched (TRASH)
                     outcome answered
```

**After** (same script, unchanged): `wire [('-in:spam borogrove', False)]`, no sources, `enforced
('in','terms')`, `term_coverage 1.0`, `outcome inconclusive`. The same holds for
`-in:spam -in:trash borogrove`, `-in:trash borogrove` and `in:inbox borogrove`.

**Four edits, one rule.**

1. `constants.declares_the_search_region` — the rule of §0, and the only place polarity is stripped.
2. `query/analysis.mailbox_scope_of` → **`search_region_of`**, renamed rather than edited so every
   caller was revisited: it now yields every fragment the predicate accepts, in either polarity and
   including narrowing locations. `region_constraint_names` sits beside it so "which constraint is
   the region one?" has one derivation.
3. `retrieval/ladder.BroadeningRung._anywhere` — the published `in:anywhere` step returns nothing
   when `search_region_of(parsed.constraints)` is non-empty. A.7 L3 widens the scope of a query that
   did not name one; a query that named one, positively or negatively, has already answered the
   question the step exists to ask.
4. `retrieval/ladder.RelaxationRung._relaxed_query` — **the region is not relaxable.** Relaxation
   widens *within* the region, which is why dropping a filter is a recoverable false negative;
   dropping the region searches somewhere else. The drop stays in `drop_order`, is reported in
   `untried_drops`, and is offered no budget — the same treatment a drop no budget can reach already
   gets (R-RETR-023).

**Two consequences that fall out of the same change rather than being separate rules.** A narrowing
location is a region declaration too, so `in:inbox` is carried onto every unit instead of being
probed *alone*: round 17 planned an L1b probe whose whole `q` was `in:inbox` and an L2 "relaxation"
whose whole `q` was `in:inbox`, both of which ask Gmail to list a mailbox on behalf of a query that
named something to find. And `in:inbox zephyr` is now answered strictly inside the inbox, which
removes one of R-RETR-030's three reproductions as a side effect (§7).

**L3's broadening survives, narrowed** (A9-A3, R-RETR's reasoned verdict). With no region named it
still fires after nothing was found, still sets the flag, and the rows it admits now say where they
came from: `test_the_published_broadening_still_reaches_spam_when_no_region_was_named` asserts
`{"r-sp": ("spam",), "r-tr": ("trash",)}` under `outcome: answered`.

**Numbers, on my own sets.** 18,596 queries / 33,383 planned probes: `lost_region 0`,
`entered_excluded_region 0`, `reached_an_unnamed_region 0`, `flag_disagrees_with_the_query 0`,
`widening_step_over_a_scoped_query 0`. 1,800 randomised end-to-end trials: **0** requests with
`includeSpamTrash` over a query that declared a region, **0** matched rows from a region the query
excluded.

---

## 3. Part 2 — a negated phrase is an exclusion (OD-5 point 4, R-RETR-027)

`ParsedQuery.phrases` now means *the phrases the query asks Gmail to match*; the negated ones are in
`excluded_phrases`, and `_build_constraints` renders them `-"…"` so the polarity reaches the wire.
Everything that reads `phrases` — A.8a branch E-b through `qualifying_phrases`, the confidence tier,
the risk factors — inherits the correction, because the field it reads no longer contains them.

Before: `-"quadrant notice zephyr"` rendered `"quadrant notice zephyr"` and returned the one message
that *has* the phrase as `role: matched`, `constraint_coverage ('phrase',)`, `term_coverage 1.0`.
After: it renders `-"quadrant notice zephyr"`, the carrier is not matched, and the message that does
not carry the phrase is.

The negated phrase is also never a probe of its own (`selects_something` is false for it), which is
load-bearing: a `q` of nothing but "everything except this phrase" is R-RETR-006's mailbox listing.
That required Part 8 below.

Round 17's test asserted only the half that worked; it now asserts render, `phrases`,
`excluded_phrases`, `qualifying_phrases`, the constraint fragments and the decomposition units, for
both the colon-free and the colon-carrying spelling — because asserting one and trusting its peer is
the shape that produced the finding.

---

## 4. Part 3 — `enforced` is derived once, where it is computed (OD-5 point 5, R-RETR-028)

`query/analysis.constraints_carried_whole(query, constraints)` answers one question — *does this `q`
carry every fragment of that constraint?* — and **every rung of `LADDER` now calls it** instead of
declaring its own value. Comparison is `constants.carriage_token`: NFKC, casefold, and surrounding
phrase quotes removed (quoting narrows what a token matches and never widens it, which is why A.8a
branch E-c's quoted identifier carries the term it quotes); polarity is **not** reduced, because
`-from:x` and `from:x` ask opposite questions.

**It reproduces every hand-written value it replaces**, which I checked by execution rather than by
reading: replacing all five rungs' hand-declared lists left the pre-existing suite green, and those
tests are what asserted the old values. It also fixes L0, where the rule had never been applied:

```
PO-2026-0041 zephyr   before  enforced ('terms',)  term_coverage 1.0  sufficiency sufficient
                              row i-1 constraint_coverage ('terms',)   — i-1 has no "zephyr"
                      after   enforced ()          term_coverage 0.0  dropped ['terms']
                              row i-1 constraint_coverage ()
"phrase A" "phrase B" before  enforced ('phrase',) from a q carrying phrase A only
                      after   enforced ()
PO-2026-0041          after   enforced ('terms',)  term_coverage 1.0   — the control still holds
```

`carriage_token` deliberately does **not** strip Gmail's grouping punctuation, unlike its neighbours:
that is exactly what must not be reduced, because A.7 L3 composes `{from:x to:x}`, a disjunction
strictly wider than the `from:x` the caller wrote. Stripping the brace read the group's first member
as the constraint and reported a widened participant enforced — R-RETR-020's over-claim arriving
through the derivation written to prevent it. I found that by planting it (R14).

The family enforcement sweep is
`test_a_probe_enforces_only_the_constraints_its_own_q_carries_whole`, over the same generated
population as §0 restricted to four region prefixes (**756** probes checked), **plus written-out
oracles** for the L0 branches and for
L3's disjunction, because `probe.enforced == constraints_carried_whole(...)` compares one derivation
with itself and is satisfied by any consistent derivation, including a broken one. My own replant
harness caught me making exactly that mistake twice (§5).

---

## 5. Part 4 — the replant manifest, and what it caught in my own tests

`tests/fixtures/replants.py` holds a manifest of **16 entries**: every behaviour this round changed,
plus R15/R16, the two guard-strength shapes R-RETR-031 asks for by name. `tests/test_replants_round18.py`
runs it.

**Reintroduction check, with the proof.** `assert_imports_resolve_into_the_scratch_tree` runs a
subprocess and asserts both packages resolve inside the scratch copy **and** not into the working
tree — the second assertion is not redundant, because a scratch path underneath the working tree
satisfies the first. Executed:

```
mailweave.__file__ -> /tmp/r18proof/tree/server/src/mailweave/__init__.py
tests.__file__     -> /tmp/r18proof/tree/tests/__init__.py
resolves into /root/mailweave?  False False
```

Every anchor asserted `1/1` before writing and every file asserted changed by sha256 after:

```
plant                                          anchor  sha256 before   sha256 after    changed
R1-negated-region-is-not-a-region              1       be26444c75298b  e1b066da9acadc  True
R2-l3-widens-out-of-a-declared-region          1       4eedca02f1c899  900bda1fdb0f4a  True
R3-region-derivation-drops-negations           1       ac7d66c0ba387a  7fabcc68f57a42  True
R4-relaxation-drops-the-region                 1       4eedca02f1c899  55b5d515382365  True
R5-l0-claims-the-whole-constraint              1       4eedca02f1c899  73dd4233ed4c74  True
R6-enforcement-credits-a-fragment              1       ac7d66c0ba387a  1e260a4309f470  True
R7-negated-phrase-is-searched-for              1       ac7d66c0ba387a  5d6d06df4d67dc  True
R8-predicates-split-a-quoted-value             1       be26444c75298b  d0572a381cf9d7  True
R9-provenance-is-not-the-observed-labels       1       b079b1650da31d  8efe8e96b3824b  True
R10-region-derivation-from-labels-is-empty     1       be26444c75298b  99cade05e76338  True
R11-zero-evidence-report-offers-nothing        1       b079b1650da31d  0bbed42cf322d3  True
R12-content-filter-is-one-category-again       1       be26444c75298b  ee827c0053ffb6  True
R13-double-crashes-on-a-calendar-invalid-date  1       07849ffe47deac  b29b3b220d037b  True
R14-carriage-strips-grouping-punctuation       1       be26444c75298b  56ad959984f624  True
R15-a-unit-narrows-into-a-region-nobody-named  1       ac7d66c0ba387a  dbe450b2e8ad78  True
R16-a-widening-probe-restricts-after-declaring 1       4eedca02f1c899  97000fb0a7e0fc  True
```

**Every one of the sixteen is CAUGHT, twice over.** The first column is the test named against it;
the second is the **whole suite with that test deselected**, which is the question R-RETR asked of
round 17 and got "2,248 green" for. The scratch tree was asserted green before the first plant.

```
plant                                          anchor changed named   whole suite, own test deselected
R1-negated-region-is-not-a-region              1      True    CAUGHT  CAUGHT
R2-l3-widens-out-of-a-declared-region          1      True    CAUGHT  CAUGHT
R3-region-derivation-drops-negations           1      True    CAUGHT  CAUGHT
R4-relaxation-drops-the-region                 1      True    CAUGHT  CAUGHT
R5-l0-claims-the-whole-constraint              1      True    CAUGHT  CAUGHT
R6-enforcement-credits-a-fragment              1      True    CAUGHT  CAUGHT
R7-negated-phrase-is-searched-for              1      True    CAUGHT  CAUGHT
R8-predicates-split-a-quoted-value             1      True    CAUGHT  CAUGHT
R9-provenance-is-not-the-observed-labels       1      True    CAUGHT  CAUGHT
R10-region-derivation-from-labels-is-empty     1      True    CAUGHT  CAUGHT
R11-zero-evidence-report-offers-nothing        1      True    CAUGHT  CAUGHT
R12-content-filter-is-one-category-again       1      True    CAUGHT  CAUGHT
R13-double-crashes-on-a-calendar-invalid-date  1      True    CAUGHT  CAUGHT
R14-carriage-strips-grouping-punctuation       1      True    CAUGHT  CAUGHT
R15-a-unit-narrows-into-a-region-nobody-named  1      True    CAUGHT  CAUGHT
R16-a-widening-probe-restricts-after-declaring 1      True    CAUGHT  CAUGHT
```

The in-suite run (`pytest -m replant`, 26s) plants each entry and runs only the test named for it;
the whole-suite column above is the out-of-tree pass, which takes about eleven minutes and is not in
the default gate.

**What the harness found in my own work, which is the reason it is worth having.** Two of the tests I
wrote were vacuous, and the manifest is what said so:

* **R10** — emptying `mailbox_regions_of` left
  `test_every_disclosed_row_states_the_region_its_own_labels_place_it_in` green, because it asserted
  `row.mailbox.regions == mailbox_regions_of(row.mailbox.labels)`: one derivation compared with
  itself. The expected regions are now written out per planted id.
* **R14** — a `carriage_token` that strips grouping punctuation left
  `test_a_probe_enforces_only_the_constraints_its_own_q_carries_whole` green for the same reason.
  Written-out oracles for L3's disjunction were added.

A third such error was in the harness itself and is worth recording because it is the same class: my
first scratch copy excluded `docs/`, `tools/rubric_status.py` reads `docs/RELEASE_RUBRIC.md`, and the
whole-suite pass therefore failed on a tree nothing had been planted into — making every whole-suite
verdict CAUGHT for free. `assert_the_scratch_tree_is_green` now runs the suite on the pristine copy
before the first plant, and the run below is the one after that fix.

**Two standing in-suite tests keep the manifest honest** and run on every suite run, in under a
second: `test_every_replant_anchor_matches_exactly_once_in_the_tree` (a manifest whose anchors have
rotted reports MISSED for free — it caught a rot within this round, when `ruff format` reflowed the
phrase-render expression) and `test_every_replant_names_a_test_that_exists`.

---

## 6. The unasserted-fix sweep

R-RETR found two round-17 fixes undefended and said the class was worth more than the instances. I
agree, so I planted back a behaviour from **every round-17 (and several earlier) repair I could
locate in the tree** — seventeen of them, none of which round 18 changed — and asked the whole suite
whether anything goes red. Manifest and runner: `scratchpad/unasserted_sweep.py`, over a scratch copy
asserted green before the first plant, every anchor `1/1`, every file asserted changed, imports
asserted inside the copy.

```
plant                                                 anchor changed whole suite
S1  a vacuous token becomes a constraint again          1     True    CAUGHT
S2  a quoted colon is an unknown operator again         1     True    CAUGHT
S3  a repeated identical fragment is two units again    1     True    CAUGHT
S4  `_routes` keys on the admission delta again         1     True    CAUGHT
S5  decomposition credited with no disclosed thread     1     True    CAUGHT
S6  a budget affordance minted unconditionally          1     True    CAUGHT
S7  a cap-bound constraint reported enforced            1     True    **MISSED**
S8  a negated participant widened into its opposite     1     True    CAUGHT
S9  a relaxation that selects nothing is sent           1     True    CAUGHT
S10 a listing `q` is planned rather than declined       1     True    CAUGHT
S11 the probe refusal drops its content clause          1     True    CAUGHT
S12 `constraint_coverage` not filtered to the parse     1     True    **MISSED**
S13 a broadening counts as a relaxation                 1     True    CAUGHT
S14 L2 and L3 run before the evidence gate              1     True    CAUGHT
S15 `include_spam_trash` is not derived from the `q`    1     True    CAUGHT
S16 an unproven operator rides into the `q`             1     True    CAUGHT
S17 L1b is gated on the L1 stop                         1     True    CAUGHT
```

**Fifteen of seventeen were already defended.** The two that were not, and what I did about each:

* **S7 — R-RETR-024(c)'s own fix.** `_decomposition_enforced` credits a constraint to the L1b rung
  only when *every* unit of it was probed; with more units than `MAX_DECOMPOSITION_PROBES` the A.7
  cap cuts the plan short and the constraint must not be reported enforced. That is precisely the
  claim R-RETR verified by hand last round ("at 4, 5 and 6 units … `enforced ()`,
  `term_coverage 0.0`"), and **nothing in the suite held it**: removing the clause left everything
  green. Closed by `test_a_constraint_whose_pieces_the_cap_never_probed_is_not_reported_enforced`,
  which asserts both halves — the claim falls *and* the thread is still recovered, because a fix that
  closed the claim by losing the recall would satisfy an assertion about the claim alone. Re-planted:
  **CAUGHT**.
* **S12 — R-DISC-006's `constraint_coverage` filter.** Removing it left the suite green, and the
  reason is honest rather than alarming: now that every rung derives `enforced` from
  `constraints_carried_whole` over `parsed.constraints`, a foreign constraint name has **no reachable
  producer**, so the filter is defence in depth rather than a live guard. That is the same shape
  round 17 disclosed for its own P2, and the right treatment is the one it did not get: execute it at
  the function rather than leave a clause with no test, because a later change to any rung could
  quietly make it reachable again. Closed by
  `test_a_row_never_names_a_constraint_the_parse_did_not_produce`. Re-planted: **CAUGHT**.

**What the sweep does not cover, stated so the number is not read as wider than it is.** Seventeen
plants is what I could locate by reading the round-16 and round-17 repairs in the tree; it is not
every behaviour in the tree, and a behaviour whose repair left no distinctive anchor is not in it.
The round-18 manifest is exhaustive over this round's diff; this one is a *sample* over prior rounds,
and I report it as one. The standing mechanism that makes the next round cheaper is
`tests/fixtures/replants.py`: adding an entry is four lines, and the two in-suite tests keep the
manifest from rotting.

---

## 7. Parts 5 and 6 — the remaining findings, taken or left open with the reason

### R-RETR-032 (LOW) — affordances on zero-evidence responses. **Closed.**

`retrieval/assemble.report_affordances` mints an offer from the declaration that produced it:
`unproven_operator` → the same query with the token quoted; `unparsed_syntax` → the same query with
the boolean and grouping tokens removed, which is what `render` would have executed; a query naming
only *where* to look → the region kept, with an explicit empty `terms` slot. The offers reach both
`envelope.affordances` and `empty_diagnosis.affordance`.

R-RETR-023's rule is kept — nothing is offered where nothing would help
(`test_a_report_with_nothing_to_offer_offers_nothing` executes `""`, `the and of`, `?`, `subject:`).
And AD-03's requirement that an affordance be *a concrete call that would reach the untried rung* is
executed rather than asserted: `test_a_zero_evidence_report_offers_the_call_that_would_reach_a_rung`
**runs each offered call** and asserts it reaches Gmail.

```
thread:1837abf        -> {"query": "\"thread:1837abf\""}     follow-up reaches Gmail
(zephyr OR borogrove) -> {"query": "zephyr borogrove"}        follow-up reaches Gmail
{zephyr borogrove}    -> {"query": "zephyr borogrove"}        follow-up reaches Gmail
in:anywhere           -> {"query": "in:anywhere", "terms": []}
""  the and of  ?  subject:  -> no offer
```

**I do not mark ROUTE-01 and I do not restore it.** That is a reviewer's decision and R-RETR named
this finding as the one thing standing in its way; closing the finding is in scope, marking the
criterion is not.

### R-RETR-029 (MEDIUM) — the content predicate. **Half closed, half named as residue.**

`NON_MATCHING_CHARACTER_CATEGORIES` replaces the single `Cf`: `Cc, Cf, Cs, Co, Cn, Zs, Zl, Zp, Mn,
Me`, each named with the reason it is there, and each **asked of the runtime** by
`unicodedata.category` rather than transcribed as code points.
`test_a_token_of_marks_controls_or_separators_names_nothing_to_match` sweeps the whole BMP — **11,107
code points** in those categories, every one content-free bare, negated and quoted, against **43**
under round 17's `Cf`-only rule. Lone combining marks (U+0301), variation selectors (U+FE0F),
controls and the space-separator family are closed.

**The residue, named rather than glossed.** Unicode's `Default_Ignorable_Code_Point` property covers
characters that render as nothing while carrying an ordinary category — U+3164 HANGUL FILLER, which
NFKC-folds to U+1160 (`Lo`), and U+115F. `unicodedata` exposes **no property API** for it in this
runtime, so it cannot be *derived* the way every category above is, and transcribing the set would be
the hand-list this predicate exists to avoid. Those spellings remain content, are executed rather
than silently dropped, and the test asserts that as a **known** value so the day it changes the suite
says so. U+2800 BRAILLE PATTERN BLANK is deliberately not in the residue: it is category `So` and is
a meaningful character in braille text. **Open: WS-10, and R-GMAIL for whether Gmail matches any of
them at all — which is where this finding's severity is actually decided.**

### R-RETR-030 (MEDIUM) — `enforced` as the union over routes. **Narrowed by Part 1; the reviewer's required fix attempted and not taken, with the reason.**

Two of the three reproductions are gone as a side effect of Part 1. The **after** column is measured
on my own fixtures; the **before** column is measured by *reconstruction* — planting R1–R7 back into a
scratch tree together and re-running the same three shapes — except where marked, where it is
R-RETR's filed reproduction on its own fixture and I say so rather than presenting it as mine.

```
in:inbox zephyr                 before  enforced ('in','terms') tc 1.0 over a row not in the inbox
                                        [R-RETR's filed reproduction; my reconstruction does not
                                         reach it, because it also needs the `carries_nothing_to_
                                         select_by` region clause reverted, which is not one plant]
                                after   one route only. The non-inbox row is not disclosed at all,
                                        so the claim has nothing false left to be about
newer_than:7d zephyr borogrove  before  enforced ('terms',) tc 0.5 over two Jan-2025 rows   [measured]
                                after   enforced () tc 0.0 inconclusive, both constraints dropped
label:projecta zephyr           before  enforced ('label','terms') tc 1.0, l-2 carries no label
                                after   unchanged — this one is live                        [measured]
```

The same reconstruction re-establishes R-RETR-026 itself, which is the check that the plants really
reconstruct round 17 rather than something else: with R1–R7 planted, `-in:spam borogrove` on my
fixture returns to
`wire [('-in:spam borogrove', False), ('borogrove', False), ('in:anywhere borogrove', True)]`,
two SPAM/TRASH rows `matched`, `outcome: answered`; without them it is one probe, no rows,
`term_coverage 1.0`, `inconclusive`.

I implemented the reviewer's required fix — intersect over the routes that admitted a **disclosed**
row — and it fails two existing tests, for a reason that is a property of the instrument rather than
of the fix. `ExecutedProbe.ids_admitted` is the *delta* of ids a probe was the first to record,
because the transport hands back counts rather than ids precisely so that a probe cannot report ids
an earlier one recorded. A probe that returned exactly the disclosed rows an earlier probe had
already admitted therefore has an empty delta and drops out of "routes with a disclosed admission" —
which is what `test_a_probe_whose_rows_an_earlier_probe_admitted_still_counts_as_a_route` exists to
forbid, and `test_a_decomposition_probe_is_not_reported_as_a_dropped_constraint` fails with it too.
Trading a documented over-claim for an undetected under-count is not a fix. **Open**, with the
reason recorded in `_asked_for`'s own docstring: it needs the seam to hand back a page's ids, which
is amendment A1's content witness and **WS-16**, not a change in `assemble`. The reviewer's
alternative — keep the union and stop deriving `term_coverage` from it — is a contract change and
belongs with the orchestrator.

### R-RETR-031 (MEDIUM) — the invariant test's two holes. **Closed**; see §0. Both plants CAUGHT against the invariant test alone, and both are standing manifest entries.

### R-RETR-033 (LOW) — the double crashes on a calendar-invalid date. **Closed.**

`tests/fixtures/mailbox.py::_date_value` returns `None` for a syntactically-matching but
calendar-invalid date, which is the answer it already gives for a value whose shape it does not
recognise, and `None` already means "Gmail judges it, we do not".
`test_a_calendar_invalid_date_is_carried_to_gmail_and_the_double_does_not_crash` drives
`after:2026/13/45`, `before:2026/02/31` and `after:0000/01/01` end to end. This is a *ceiling* fix:
no end-to-end statement about that documented A.6a class was establishable by anyone before it.

### R-RETR-034 (LOW) — `tokenise` and `constants` disagree about NFKC. **Left open, with the reason.**

Closing it means deciding whether a user's query is normalised the way mail text is, which is the
query-normalisation policy question already escalated (**A.6 / WS-10**). Either answer changes what
`ＩＮ：ＡＮＹＷＨＥＲＥ` means, and an implementer choosing it would be deciding a product question
in a docstring. Round 18 does not make it worse: the fullwidth spelling still parses as terms, so
`search_region_of` never sees it and the query is treated as having declared no region — the same
state as before, now stated in one place instead of two.

### My own finding, in the same class as the ones I was sent to fix

`constants.query_tokens` is now the **one** splitter, and `query.operators.tokenise` reads it instead
of carrying its own copy. Before, the predicate family split on whitespace while the parser split
outside quotes, so `carries_nothing_to_select_by('-from:x')` was `True` and
`carries_nothing_to_select_by('-from:"Amy Smith"')` was `False` — the same constraint, written with a
value that happens to contain a space, became an L1b unit whose `q` asks Gmail for the whole mailbox
minus one sender. That is R-RETR-006's shape reached through the one spelling nobody checked, and it
is what Part 2 would have re-opened, since a negated phrase is a multi-word quoted token.
`test_a_negated_operator_with_a_quoted_value_is_not_a_probe_of_its_own` sweeps the operator family in
both polarities with a two-word quoted value.

---

## 8. My own adversarial sets, how I built them, and my numbers

**Nothing here comes from `/tmp/rretr15`, `/tmp/rretr16` or `/tmp/rretr17`.** Vocabulary, mailboxes,
oracles and seeds are mine.

### The plan-layer sweep — 18,596 queries, 33,383 probes

`scratchpad/my_sweep.py`. Vocabulary of 120 tokens: every `OperatorName` with a value I chose, in
both polarities; eleven mailbox locations in both polarities plus a grouped and a capitalised
spelling of each; phrases with and without colons, negated and not; quoted multi-word operator
values; identifiers; grouping and boolean tokens; four blank-rendering code points; and five
malformed shapes. Population: every single token, **every ordered pair**, and a strided walk over
ordered triples.

```
swept                              18596
probes                             33383
parse_raised                           0
plan_raised                             0
lost_region                             0
entered_excluded_region                 0
reached_an_unnamed_region               0
flag_disagrees_with_the_query           0
enforced_overclaim                      0
negation_executed_positively            0
composed_probe_is_a_listing             0
widening_step_over_a_scoped_query       0
```

**Every check is computed by an oracle written in the sweep**, not by calling the derivation it
checks — including its own tokeniser, its own region reading and its own "carried whole" rule.

**Is the sweep vacuous? No, and I established that by planting.** Each of the sixteen manifest
defects was planted into a scratch tree and the sweep re-run against it:

```
R1  negated region is not a region      SEEN  lost_region 1275, entered_excluded_region 1,
                                              widening_step_over_a_scoped_query 859
R2  L3 widens out of a declared region  SEEN  widening_step_over_a_scoped_query 2476
R3  region derivation drops negations   SEEN  lost_region 1275
R4  relaxation drops the region         SEEN  lost_region 3025, flag_disagrees 542
R5  L0 claims the whole constraint      SEEN  enforced_overclaim 964
R6  enforcement credits a fragment      SEEN  enforced_overclaim 252
R7  negated phrase is searched for      SEEN  negation_executed_positively 1748
R8  predicates split a quoted value     SEEN  enforced_overclaim 4614, composed_probe_is_a_listing 310,
                                              reached_an_unnamed_region 461
R14 carriage strips grouping            SEEN  enforced_overclaim 1868
R9..R13                                 blind — disclosure-layer and fixture defects, outside a
                                              plan-layer sweep by construction
```

R7 was **blind on my first attempt**, because the oracle read negated fragments off the *constraints*
— and a defect that discards polarity at the parse makes those fragments positive. The oracle now
reads the raw query. I record that because it is the same "one derivation compared with itself"
error the replant harness caught in my tests.

### Randomised end-to-end trials — 1,800 trials over three seeds

`scratchpad/my_trials.py`. Mailboxes of 1–22 messages over 1–9 threads, random label sets drawn from
seven (including SPAM-only, TRASH-only and SPAM+UNREAD), random bodies over an eight-word invented
vocabulary with a planted phrase in a quarter of them; queries drawn from twelve region fragments
(both polarities, widening and narrowing) crossed with six shapes.

| | seed 20260904 | seed 7 | seed 991 |
|---|---|---|---|
| trials / envelopes | 600 / 600 | 600 / 600 | 600 / 600 |
| raised / crashes | 0 / 0 | 0 / 0 | 0 / 0 |
| `H ⊆ disclosed ∪ withheld` violations | 0 | 0 | 0 |
| disclosed ∩ withheld | 0 | 0 | 0 |
| phantom ids | 0 | 0 | 0 |
| provenance disagrees with the labels | 0 | 0 | 0 |
| requests into spam/trash the query did not ask for | 0 | 0 | 0 |
| **matched** rows from a region the query excluded | 0 | 0 | 0 |
| rows seen | 2,782 | 3,079 | 2,836 |
| rows outside the default mailbox | 1,056 | 1,215 | 1,135 |

**Forced-overflow pass**, because a preservation invariant that never sees a withheld record is a
weaker statement than it reads as: 28–60 messages over 20–46 threads, 400 trials over two seeds —
**162 withheld records**, 0 preservation violations, 0 overlaps, 0 phantom ids.

### Two numbers that are not zero, and are not violations

**283 / 236 / 224 rows from a region the query excluded — all of them `role: stub`.** These are
thread-map members: MailWeave matched a message in the region the caller asked about, mapped its
thread, and the thread contains a message that lives in trash. Omitting it would be a silent
omission of a thread member, which is the issue-#296 defect this project exists to prevent; the
honest answer is to disclose it as a stub *and say where it is*, which is exactly what Part 0's field
now does. **0 of them are `matched`.** I flag it because a reader of "no row from an excluded region"
would otherwise be surprised, and because it is the clearest single case for why the field had to be
on the row rather than in `scan_scope`.

**14 / 7 / 4 messages containing an excluded phrase disclosed as matched.** These are L2 relaxations:
dropping a *filter* widens within the region, which the asymmetry rule permits and ROUTE-03
enumerates. Checked in full:

```
in:inbox -"quadrant notice handover" quadrant
  wire  [('in:inbox -"quadrant notice handover" quadrant', False), ('in:inbox quadrant', False)]
  row   m1 matched  constraint_coverage ('in','terms')   — 'phrase' absent, correctly
  enf   ('in','terms')  term_coverage 0.67  sufficiency ambiguous
  drop  phrase — "relaxation at L2 executed without '-\"quadrant notice handover\"' (A.7 L2)"
```

The drop is declared with the negated fragment rendered, the coverage falls, and the row does not
claim the constraint. This shape is **new this round** — before Part 2 a negated phrase was not an
exclusion at all — so I record it explicitly for the reviewer rather than letting it be discovered:
it is the declared-relaxation contract working, and if the orchestrator judges that an *exclusion*
should never be relaxed, that is a policy the same one-line rule can carry.

---

## 9. Have I trusted a peer?

The honest answer is **yes, twice, and the harness caught both** — which is the only reason I can
answer the question with evidence instead of an intention.

* I wrote `test_every_disclosed_row_states_the_region_its_own_labels_place_it_in` comparing
  `row.mailbox.regions` with `mailbox_regions_of(row.mailbox.labels)` — the derivation under test on
  both sides. Emptying the derivation left it green (R10). Fixed with a written-out oracle.
* I wrote `test_a_probe_enforces_only_the_constraints_its_own_q_carries_whole` comparing
  `probe.enforced` with `constraints_carried_whole(...)` — same shape. A `carriage_token` that
  strips grouping punctuation left it green (R14). Fixed with written-out oracles for L0's two
  branches and L3's disjunction.

Three more places where I checked rather than trusted:

* **The asymmetry rule is not asserted to generalise; the sweep generates its population from
  `OperatorName` and from the location prefix**, and a test holds the operator vocabulary to the enum
  so a new operator cannot narrow the sweep by existing.
* **`constraints_carried_whole` "reproduces every hand-written value it replaces"** is not a claim I
  made from reading. The pre-existing tests are what asserted those values, and they stayed green
  when the five rungs stopped declaring them.
* **Every affordance the report class mints is executed** and asserted to reach Gmail, rather than
  asserted to exist.

**And the reviewer is a peer too.** I did not take R-RETR's three findings on the report: I ran the
reproductions first and got the filed results. I did not take its *required fix* for R-RETR-030 on
the report either — I implemented it, and it fails two existing tests for a reason the finding did
not anticipate (§7), which is a better answer than either accepting or ignoring it. And I did not
build any set from `/tmp/rretr15`, `/tmp/rretr16` or `/tmp/rretr17`; my sweep's vocabulary, its
oracles, my mailboxes and my seeds are mine, and I established that they are not vacuous by planting
into them rather than by saying so.

And one where I could not check, and say so: **whether Gmail evaluates any of this the way the double
does.** Every end-to-end number in this report is bounded by a `MockTransport` double that evaluates
13 of 21 `OperatorName` members. **R-GMAIL / WS-16.**

---

## 10. Every docstring claim my diff makes about coverage, with the evidence

| claim | where | executed evidence |
|---|---|---|
| the asymmetry rule "holds for a scope operator nobody has added yet" | `declares_the_search_region` | region sweep over 7 narrowing + 3 widening locations × 2 polarities, generated from the location **prefix**; `in:snoozed` and `in:sent` (not enumerated anywhere in the source) behave identically in my own sweep |
| "enumerating the location operators by name here would have been the fourteenth instance" | `decomposition_units_of`, `declares_the_search_region` | no operator name appears in any predicate added this round; the family test's population is `OperatorName` and the prefix |
| `constraints_carried_whole` "reproduces every hand-written value it replaces" | `constraints_carried_whole` | the 2,248 pre-existing tests, which asserted those values, stayed green when all five rungs stopped declaring them; plus written-out oracles for L0 E-b/E-c and L3's disjunction |
| "a rung added later inherits it" | `ExactOperatorRung._branch`, `_broadening` | `test_a_probe_enforces_only_the_constraints_its_own_q_carries_whole` ranges over `LADDER` by membership, 756 probes, `len(LADDER) == 5` asserted |
| "one splitter, read by both" | `query_tokens`, `tokenise` | `tokenise` imports it; R8 planted back is CAUGHT; the quoted-negation family test covers all 21 operators × 2 polarities |
| the content filter is "asked of the runtime, category by category" | `NON_MATCHING_CHARACTER_CATEGORIES` | BMP sweep, 11,107 code points, all content-free bare/negated/quoted; the residue asserted as a known non-empty value |
| provenance is "derived from the observed labels, never from the query" | `MailboxProvenance` | `regions` is a computed field and `extra="forbid"` refuses it as input; R9 and R10 planted back are CAUGHT; 1,800 trials, 0 disagreements against a written-out oracle |
| affordances are "a concrete call that would reach the untried rung" | `report_affordances` | the test executes each offered call and asserts Gmail is reached |
| "the region is not relaxable … reported in `untried_drops` and offered no budget" | `RelaxationRung` | `_relaxed_query` returns `None`, which `plannable_drops` reads, so `_empty_diagnosis` mints no budget affordance for it |
| the invariant is "enforced once, by one membership test" | `decomposition_units_of` | R15 and R16 planted back are CAUGHT **by that test alone** — the claim round 17 made and did not have |

---

## 11. What I could not establish

* **Whether Gmail treats U+3164 / U+1160 as content**, and therefore whether R-RETR-029's residue is
  a MEDIUM or nothing. `unicodedata` exposes no `Default_Ignorable_Code_Point` API, so the predicate
  cannot cover them structurally, and only a live run can say whether it matters. **R-GMAIL / PF-20.**
* **Whether `label:` names a system mailbox.** `declares_the_search_region` inherits
  `names_a_mailbox_location`'s residue exactly, at the same width: a `label:` query is treated as
  declaring no region, so L3 still widens it. Executed: `label:projecta borogrove` reaches
  `in:anywhere borogrove` and returns spam and trash rows — now each carrying
  `mailbox.regions ('spam',)` / `('trash',)`, which is the disclosure OD-5 required and is what makes
  the residue survivable. **R-GMAIL / A.6.**
* **Every rate the rubric asks for.** LEX-03's and ROUTE-02's recall bars, EV-02's position sweep,
  EV-04's paired hallucinated-found rate, EV-06's Baseline B, ROUTE-04's ceiling — all
  `[UNSET — register at G0]` or needing a seeded corpus. Every number here is on sets I constructed
  and is offered as nothing else. **WS-16.**
* **R-RETR-030's honest `enforced`**, for the reason in §7: it needs the seam to hand back page ids.
  **WS-16 / amendment A1.**
* **R-RETR-034's normalisation policy.** **A.6 / WS-10.**
* **The third `EmptyDiagnosisStatus` member** ("structurally unprobeable at any budget"), unchanged
  from round 17 and still **WS-10**. The region drop now joins that class: it is reported in
  `untried_drops` with no offer, which is the honest shape the vocabulary cannot name.
* **The live account**, and the eight `OperatorName` members the double does not evaluate. Every
  end-to-end statement in this report is bounded by that. **R-GMAIL / WS-16.**

I marked no rubric criterion, did not restore ROUTE-01, did not edit `FINDINGS_LEDGER.md` or
`RUBRIC_TRANSITIONS.md`, did not touch retry or backoff, and added no LLM or embedding call.

---

## 12. Files changed

| file | what |
|---|---|
| `server/src/mailweave/constants.py` | `query_tokens`, `declares_the_search_region`, `carriage_token`, `REGION_LABEL_BY_OPERATOR`, `region_name`, `mailbox_regions_of`, `NON_MATCHING_CHARACTER_CATEGORIES` |
| `server/src/mailweave/query/operators.py` | reads `query_tokens` instead of its own splitter |
| `server/src/mailweave/query/analysis.py` | `search_region_of` (was `mailbox_scope_of`), `region_constraint_names`, `constraints_carried_whole`, phrase polarity, the restated invariant |
| `server/src/mailweave/retrieval/ladder.py` | L0's `_branch`, L1/L1b/L2/L3 derive `enforced`, the region gate at L3, the region is unrelaxable, `_broadening` |
| `server/src/mailweave/retrieval/assemble.py` | `MailboxProvenance` on every row; `report_affordances`; the R-RETR-030 finding recorded in `_asked_for` |
| `server/src/mailweave/envelope/wire.py`, `envelope/__init__.py` | the `MailboxProvenance` model and its export |
| `tests/fixtures/mailbox.py` | the calendar-invalid date fix (R-RETR-033) |
| `tests/fixtures/replants.py`, `tests/test_replants_round18.py` | the manifest and its runner |
| `tests/test_region_and_provenance_round18.py` | Parts 0–3 and 5, end to end |
| `tests/test_lexical_ladder.py` | the family sweeps, the invariant, the enforcement rule |
| `tests/test_query_analysis.py`, `tests/fixtures/envelope_kit.py`, `tests/test_field_census.py`, `tests/test_wire_tree_round14.py`, four other test files | the schema change and the negated-phrase assertion |
| `pyproject.toml` | the `replant` marker |

---

## 13. Gates

Run last, on the tree as it stands, twice with identical results.

```
$ ruff check .
All checks passed!

$ ruff format --check .
156 files already formatted

$ mypy --strict
Success: no issues found in 130 source files

$ python -m tools.guards
guards clean: forbidden-import, generative-client, gmail-endpoint, ground-truth-isolation,
              scope-literal, unaudited-disk-write, unwrapped-http-client over server/src

$ pytest -q -m "not network"
2271 passed in 59.15s

$ pytest -m "not network" --collect-only -q     (summed per file)
2271

$ python tools/rubric_status.py --check
criteria: 113  (mandatory 110, conditional 2, optional 1)
status:
  PASS         6
  FAIL         0
  BLOCKER      0
  NOT TESTED   107
reviewer transitions recorded: 11
gate-blocking criteria (NOT TESTED / FAIL / BLOCKER): 106
```

**2,248 → 2,271, and the 23 are accounted for**: 16 in
`tests/test_region_and_provenance_round18.py`, 4 in `tests/test_replants_round18.py`, and 3 in
`tests/test_lexical_ladder.py` (the operator-family vocabulary check, the never-widened-out-of-a-
region test and the enforcement sweep). No
test was deleted; the three that changed shape —
`test_every_probe_the_ladder_composes_searches_the_region_the_query_named`,
`test_a_broadening_probe_does_not_carry_a_narrower_scope_than_the_one_it_widens_to` and
`test_a_quoted_phrase_containing_a_colon_is_a_phrase_not_an_unknown_operator` — each assert strictly
more than they did. The `replant` marker is registered in `pyproject.toml` and its two heavy tests
**are** in the default `-m "not network"` gate, which is why the suite now takes about a minute
rather than thirty-five seconds; that is the cost of the round's central claim being defended by CI
rather than by a scratch script.

The rubric is unchanged at **6 PASS / 0 FAIL / 0 BLOCKER / 107 NOT TESTED**, 11 transitions.

