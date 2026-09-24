# ROUND 19 — implementer's report

**Round:** 19. **Authority:** OD-5. **Mechanics:** A9. **Gating reviewer:** R-RETR.
**Work order:** `docs/reviews/ROUND_19/WORK_ORDER.md`.

Round 18 was right about almost everything and wrong about one predicate. This round corrects
that predicate and the four consequences that hang off it. OD-5's schema change, the
negated-phrase exclusions, the `enforced`-derived-once repair and the vacuity work are all kept
as they were.

---

## 0. The correction, in one paragraph

`declares_the_search_region`'s docstring stated the asymmetry rule correctly and its body asked
`token.startswith(MAILBOX_LOCATION_PREFIX)` — the spelling of one operator, not the behaviour of
any. R-RETR proved the consequence the only way that counts: it registered a new `mailbox:`
operator with `OperatorKind.LOCATION`, exactly as an implementer would, and 2,274 tests stayed
green while every probe dropped it, L2 relaxed it away and L3 widened out of it.

The predicate now asks `KIND_BY_OPERATOR`. To make that answerable, `OperatorKind.LOCATION` —
which held the operator that names a mailbox region *and* the four that name a message's state,
attachments, list header and filenames — is **split** into `REGION` and `ATTRIBUTE`. The old
member is removed rather than aliased: an operator registered against a name that no longer
exists fails at import; one registered against a name that quietly changed meaning would be
classified as a filter in silence, which is the failure being repaired.

That is the whole change. Everything below is its consequences, its cost, and the evidence.

---

## 1. Part 1 — R-RETR-035/036/037: the region asymmetry reads the registry

### What changed

| File | Change |
|---|---|
| `query/operators.py` | `OperatorKind.LOCATION` → `REGION` + `ATTRIBUTE`; `label`, `category`, `in` are `REGION`, `is`, `has`, `list`, `filename` are `ATTRIBUTE`. New `operator_of(fragment)` and `declares_the_search_region(fragment)`, which reads `KIND_BY_OPERATOR`. `tokenise` re-emits a group holding exactly one operator (`_sole_operator_of_a_group`). |
| `constants.py` | `_operator_token` → public `operator_token`; `names_a_mailbox_location`, `declares_the_search_region` and `carries_nothing_to_select_by` removed from here — the first is gone, the other two moved to the modules that can read the registry. `MAILBOX_LOCATION_PREFIX` keeps only the one job a prefix can do — `region_name` takes it back off `REGION_LABEL_BY_OPERATOR`'s keys. |
| `query/analysis.py` | `carries_nothing_to_select_by` moved in beside `selects_something`; new `region_declarations_of(parsed)`; `RELAXATION_ORDER` gains `region` and `attribute` in the position `location` held. |
| `retrieval/ladder.py` | L3's gate reads `region_declarations_of(parsed)` — the query's parsed fragments **and** its own raw tokens; `_anywhere`'s replacement filter reads `declares_the_search_region`; `_widened` reads the participant operator through `operator_of` rather than by splitting on a colon. |
| `retrieval/assemble.py` | the de-grouping affordance is not minted for a query that declared a region (it inverts polarity). |
| `tests/fixtures/mailbox.py` | the double evaluates `category:`, which the ladder can send and it used to raise on. |

### Why the layering moved

`constants.py` is the module `query/operators.py` imports, so a predicate in `constants` cannot
read the operator registry — which is exactly why round 18's predicate could not. The predicate
now lives beside the data it reads. `carries_nothing_to_select_by` follows it into
`query/analysis.py`, next to `selects_something`, which is the same sentence asked of one
fragment. Nothing about either rule changed in the move.

### The `label:` residue — decided, not re-named

`label:` can name a user's own label or one of Gmail's system mailboxes, and nothing in this
repository can tell them apart; that needs Gmail's system-label vocabulary (**R-GMAIL**, A.6).
R-RETR offered a two-value vocabulary (`label:spam`, `label:trash`) as the cheap conservative
rule and noted it is the enumeration A9 forbids writing.

**Decision: `label` is registered `OperatorKind.REGION`. Every `label:` value declares the
region.** No value vocabulary, no `label:`-shaped special case, and it holds for `label:inbox`,
`label:sent` and a system label Gmail names next year without an edit.

The two errors are not symmetrical and that is the whole of the reasoning. Reading a region as a
filter lets a probe search mail the caller excluded and disclose it as a match — not
recoverable. Reading a filter as a region withholds a relaxation — recoverable, and this round
hands the recovery back as an executable affordance (§3).

**What it costs, measured rather than asserted** (§6, and
`test_what_the_conservative_reading_costs_is_declared_and_one_call_from_recovered`): a query of
`label:X` plus one term has one decomposition unit instead of two, so a thread whose label is on
one message and whose term is on another is no longer recovered by L1b. That is the founding
bug's own shape, and losing it for user labels is a real loss. It is the same loss round 18
accepted for `in:inbox` and OD-5 point 3 requires of any named scope ("preserved across every
probe"). The response does not pretend otherwise: it is `inconclusive`, names `label` among the
untried drops, and carries the concrete call that finds the thread. Executed, that call finds it.

`category:` is registered `REGION` on the same reading — a Gmail tab is where a message is filed.
I record the counter-reading for the orchestrator rather than hiding it: no `category:` value
names a region outside the default mailbox, so the unrecoverable error is impossible for it, and
`ATTRIBUTE` would keep thread-split recovery for tab-scoped queries at the cost of letting L3
widen out of a tab into spam. I took the uniform reading; the alternative is one line in
`KIND_BY_OPERATOR` if the orchestrator prefers it.

### The grouped and fullwidth residues — decided

Two different problems that round 18's docstring named together.

**Grouped, single operator** (`(-in:spam)`, `-(in:spam)`, `{-in:spam}`): the predicate family
already read these as operators — `operator_token` strips Gmail's grouping punctuation — and the
parser classified them `passthrough`, so the fragment never became a constraint and the gate
never saw a region. **`tokenise` now re-emits a group holding exactly one documented operator as
that operator.** A group of one operator is that operator, and `operator_token` has assumed it
since round 13.

Three things it refuses rather than guesses, each a place a guess would invert the caller's
meaning: a group holding **more than one** token (`-(a OR b)` is `-a AND -b`; distributing a
negation is regrouping a boolean, which this parser deliberately is not), a **double negation**,
and an opener closed by the other grouping's closer.

**Grouped, several tokens, and fullwidth**: for these the parse cannot carry the region at all.
`region_declarations_of` therefore asks `declares_the_search_region` of the query's **raw
tokens** as well as of its parsed fragments, and L3's gate reads that. `operator_token`
NFKC-normalises, so the fullwidth spelling is read as the operator it is. This is the interim
R-RETR-037 itself proposes; whether `tokenise` should normalise is a policy question for A.6 and
stays open (**WS-10**, §8).

The union of two sources is deliberate and is not two derivations of one fact that could
disagree: it is one question asked of two representations of the same query, answered "yes" if
either says so, in the direction whose error is recoverable.

### Verification

`(-in:spam) snicker`, `-(in:spam) snicker`, `{-in:spam} snicker` now send
`[('-in:spam snicker', False)]` and disclose nothing; `-(in:spam OR in:trash) snicker` and
`(-in:spam -in:trash) snicker` send `[('snicker', False)]` with the flag clear and no `L3`;
`-label:spam snicker` and `-label:trash snicker` send only the exclusion;
`-ＩＮ：ＳＰＡＭ snicker` no longer reaches `in:anywhere`. `snicker` — a query naming no region —
still reaches `in:anywhere snicker` with `includeSpamTrash=true` and returns the spam and trash
rows as matches, which is A9-A3's published step surviving.

---

## 2. Part 2 — R-RETR-038/039: provenance on every row, and a field that could lie

### `observed` now has a producer, and the derived fields are absent when it is false

`Message.label_ids` is `tuple[str, ...] | None`, defaulting to `None`: an absent `labelIds` and a
stated empty list are different facts and used to be one value. `assemble` calls
`MailboxProvenance.unobserved()` for the first and `.of(...)` for the second.

`MailboxProvenance.regions` and `.outside_the_default_mailbox` return `None` when
`observed is False`. Round 18's docstring said `observed` was "a third state and not a flag", and
the code contradicted it twice: the state had no producer, and where it was constructed the
boolean computed `bool(())` and reported **false** — a field a caller branches on, saying "not
spam" about a message whose labels were never seen. `None` is not `False`.

Executed through the real client and the real `assemble`, behind a transport that removes
`labelIds` from each `threads.get` message:

```
x-1 role=matched observed=False labels=() regions=None outside_the_default_mailbox=None
x-2 role=stub    observed=False labels=() regions=None outside_the_default_mailbox=None
x-3 role=stub    observed=False labels=() regions=None outside_the_default_mailbox=None
```

Whether Gmail ever omits `labelIds` for a labelled message is **R-GMAIL** (PF-2 for
`format=metadata`). This makes the distinction representable either way, which is what stops the
response from guessing.

### The two off-manifest holes R-RETR planted are now defended

* **stub rows** (plant X2): `test_a_stub_row_states_the_region_its_own_labels_place_it_in` drives
  a thread whose matched member is in the inbox and whose *stub* members are in TRASH and SPAM,
  with the expected regions **written out per planted id** rather than recomputed from the row's
  own labels. Manifest entry **R21**;
* **requiredness** (plant X1): `test_a_row_without_a_mailbox_provenance_is_not_representable`
  validates a `MessageRow` payload with no `mailbox` key and requires the refusal. Manifest entry
  **R22**.

Plus **R23** (the absent-label-set default) and **R24** (the derived field reading as a negative).

---

## 3. Part 3 — R-RETR-040: an affordance that does not execute

**Half one, the offer that reached nothing.** `{"query": "in:anywhere", "terms": []}` is
**deleted**. Executed, it sent no request: no tool in this tree takes a `terms` argument, and the
region alone is the listing `why_this_q_is_not_a_probe` refuses under its own name. R-RETR-023's
rule applies to it exactly: the only call that would help is a different question, and MailWeave
does not invent one.

**Half two, the 88.7% carrying nothing.** The response class R-RETR measured is the *ordinary*
one — the ladder ran, found nothing, and named drops it did not try — and affordances were minted
only for the class where no rung ran at all. `recovery_affordances` now mints for it, from the
one shape that is executable today: **the caller's own query without the region it named**, for a
query that named one positively. That is the drop this round's own conservative reading made
unreachable, so it is the recall this round owes back.

Executed against `/tmp/rretr18/pristine` — R-RETR's untouched copy of the round-18 tree — and
against this one, over a mailbox holding nothing that matches:

```
                        round 18                     round 19
'in:sent frobnitz'      affordances []               [{'query': 'frobnitz'}]
'in:unread snicker'     affordances []               [{'query': 'snicker'}]
'label:quillon vorpal'  affordances []               [{'query': 'vorpal'}]
'-in:spam snicker'      affordances []               []          — deliberate, see below
'in:anywhere'           [{'query': 'in:anywhere',    []          — the offer that reached
                          'terms': []}]                            nothing, deleted
```

The first three carry the offer in `empty_diagnosis.affordance` as well, which is the same
object: an affordance in the envelope and not in the diagnosis would be two statements about one
fact.

**Never an offer that undoes an exclusion.** A negated region declaration is the caller saying
*not there*; the call that drops it is scope-free, and A.7 L3's published step widens a scope-free
query to the whole mailbox. So MailWeave does not propose it. Nor does it mint the de-grouping
offer for a grouped region declaration: stripping the grouping off `-(A OR B)` yields `-A B`,
which asserts the second — an offer into the region the caller excluded, minted by MailWeave
rather than written by the caller. Both are asserted in
`test_nothing_offered_would_undo_an_exclusion_the_caller_wrote`. If the orchestrator judges this
too conservative, ROUTE-01's acceptance needs the exception written into it, because as written
it is unmeetable for this class.

**The test is generated from the branch set**, not from a list of queries, and it *executes* what
each branch mints: `test_every_offer_any_branch_mints_is_executed_and_reaches_gmail`. An offer
carrying a `query` must reach Gmail; an offer carrying a `relax` budget is asserted against the
thing that makes it concrete — a drop the rung really would plan at that budget.

**And the percentage is replaced by a property, because a percentage cannot be asserted.**
`test_a_zero_evidence_response_offers_nothing_only_when_nothing_would_help` requires, of every
zero-evidence response in a twenty-shape set, either an executable offer or a proof that no call
existed: no drop the response reports untried is one a probe could reach at any budget, and there
is no region that could be dropped without undoing an exclusion. My own measured rate is in §6.

**ROUTE-01 is not marked and must not be**: only a reviewer may, and the exclusion class above is
a policy question the criterion's wording does not yet cover.

---

## 4. Part 4 — the remaining findings

**R-RETR-042 (harness).** `_environment` now puts `scratch/harness/src` on `PYTHONPATH` and
`assert_imports_resolve_into_the_scratch_tree` asserts **all three** importable packages resolve
inside the copy and none into the working tree. `run_replants` proves the copy sound on **every**
pass — not only under `whole_suite` — with `assert_the_named_tests_pass_before_planting`, which
runs every test the manifest cites on the pristine copy and requires them to pass: that is the
control each CAUGHT row depends on, and it costs one subprocess rather than a whole suite. The
module docstring's claim that the marked tests are "deselected from the default run" was false
and is corrected; `tests/test_replants_round18.py` is renamed `tests/test_replants.py`, since the
manifest now covers two rounds.

**R-RETR-041 (`in:unread` and a mistyped location).** Narrowed and mitigated, not closed, and the
reason is the one that decides every value question in this round. Holding the location half to a
published value vocabulary would make `in:unread` a filter correctly and would make
`in:snoozed` — or whatever Gmail names next — a filter *wrongly*, which is the unrecoverable
direction. So every value of a region-selecting operator still declares the region, `in:unread`
still costs its query the recovery ladder, and what changed is that the response now carries the
concrete call that recovers it (`{"query": "snicker"}`) instead of naming four untried rungs and
stopping. Closing it properly needs Gmail's location vocabulary: **R-GMAIL**, fix at **WS-10**.

**R-RETR-030 (`enforced` as the union over routes).** Stays open, as the work order requires, and
one of its two live reproductions is closed as a side effect rather than by me addressing it:

```
round 18:  'label:projecta vorpal'  wire [.., 'label:projecta', 'vorpal']  rows l-1 (label), l-2 (terms)
round 19:  'label:projecta vorpal'  wire ['label:projecta vorpal']         rows []   affordance {'query': 'vorpal'}
round 18:  'from:a@parts.example vorpal'  rows l-1 (from), l-2 (terms)   ← still live
round 19:  'from:a@parts.example vorpal'  rows l-1 (from), l-2 (terms)   ← still live, unchanged
```

The `label:` reproduction is gone because the label is now carried onto every unit, so the L1b
probe that produced the union no longer exists — which is the recall cost of §1 wearing a
different hat, not a repair of the seam. **`from:` remains the live reproduction**; the finding's
account is unchanged and belongs to **WS-16 / amendment A1**.

**R-RETR-029** (the `Default_Ignorable_Code_Point` residue) is untouched and open; severity at
**R-GMAIL**, fix at **WS-10**.

---

## 5. The new-operator acceptance test

R-RETR's method, in the suite: `tests/test_new_operator_round19.py`, with the machinery in
`tests/fixtures/new_operator.py`. Each half copies the whole tree, asserts all three packages
import from the copy and none from the working tree, registers one operator **everywhere an
operator is registered**, and then asks about behaviour:

| Registered | Kind | What the probe requires |
|---|---|---|
| `mailbox:spam` | `REGION` | read as a region declaration in both polarities; carried by **every** probe of every rung; no probe sets `includeSpamTrash`; no rung widens to the whole mailbox |
| `priority:high` | `TEXT` | **not** a region; dropped by L2; a decomposition unit of its own; the query still reaches the published broadening |

Registration means: `OperatorName` member, `KIND_BY_OPERATOR` entry, `FIDELITY_TABLE` entry (and
its count), `OPERATOR_FAMILY_VALUES` entry, the double's `IMPLEMENTED_OPERATORS`. Three of those
live under `tests/`, and they are registration sites rather than oracles: they say *what the
operator is*, not *what the code should do with it*. **No assertion, no expected value and no
population was edited.** Both halves pass, and the four sweep modules pass in the planted tree.

**The test caught me writing the enumeration again.** My first version of the classification
oracle in `tests/test_region_kind_round19.py` asserted
`set(WHAT_EACH_OPERATOR_DOES) == {name.value for name in OperatorName}` — total over the lexicon —
so registering `mailbox:` failed a test until someone edited it. That is the enumeration this
round removed, wearing a test's clothes, and the acceptance test failed on exactly that line. The
oracle is now a subset assertion with the reasoning written beside it; what makes a new operator
*state* what it does is `test_the_kind_map_is_total_over_the_lexicon`, and what makes it *covered*
is that the sweeps read the registry.

**The acceptance test is not vacuous, checked by running it against round 18's semantics.** I
rebuilt round 18's behaviour in a scratch copy by planting manifest entries R17–R20 (the four
that describe this round's semantic changes) and registered the same two operators there:

```
round 19 (this tree)   mailbox   PASS   SCOPE OPERATOR COVERED
round 19 (this tree)   priority  PASS   FILTER OPERATOR COVERED
round 18 semantics     mailbox   FAIL   AssertionError: the new operator is not read as a region
round 18 semantics     priority  PASS   FILTER OPERATOR COVERED
```

The control passing in both trees is the point: round 18's machinery worked and its input was
wrong, and a fix that made everything a region would pass the first half and fail the second.

**The family sweep is generated from the registry, not from a prefix.**
`test_every_probe_the_ladder_composes_searches_the_region_the_query_named` and
`test_a_query_that_named_a_region_is_never_widened_out_of_it` now draw their region population
from `REGION_DECLARING_FRAGMENTS`, which is every operator `KIND_BY_OPERATOR` declares `REGION`
written with the value `OPERATOR_FAMILY_VALUES` already requires of every member of the lexicon,
in both polarities. That is what makes "no edit here" true rather than hoped for.

---

## 6. My own adversarial sets, how I built them, and my numbers

Nothing in `/tmp/rretr15` … `/tmp/rretr18` was used to build any set below. My vocabulary is
`vellichor tarnhelm quillon sable-8821`, my senders are `.example` / `.invalid`, my mailboxes and
oracles are mine, and **every oracle is written in the probe file without calling a product
predicate**: my own tokeniser, my own NFKC-and-strip fold, my own list of the three widening
spellings. I did run the reviewer's `p1_grouped_scope.py`, `p2_label_scope.py` and
`p3_unobserved.py` against the tree **before changing anything**, as the work order requires, and
all three reproduced; they are not part of my measurement.

### The plan-layer sweep — 1,680 scoped queries, 6,100 probes

Population: every region-selecting operator × seven values (`spam`, `trash`, `inbox`, `sent`,
`promotions`, `unread`, `quillon-8821`) × both polarities × **eight spellings** (bare, `(x)`,
`{x}`, `-(x)`, uppercase, fullwidth, trailing comma, `[x]`) × five bodies (a term, two terms, a
participant plus a term, an operator plus a phrase, a term plus an exclusion).

| | this tree | round 18 (`/tmp/rretr18/pristine`) | round 18 rebuilt by planting R17–R20 |
|---|---|---|---|
| probes planned | 6,100 | 8,410 | 8,410 |
| probes entering a region the query excluded | **0** | 180 | 180 |
| probes widening out of a region the query named | **0** | 1,365 | 1,365 |
| `includeSpamTrash` set for a query that did not widen | **0** | 1,420 | 1,420 |
| region fragments a probe dropped | **0** | 1,512 | 1,512 |
| scope-free queries still broadened | 20/20 | 20/20 | 20/20 |

The two round-18 columns being identical is a check on my own plants: the four manifest entries
reproduce round 18's semantics exactly over this population, so the "before" column is round 18's
behaviour and not my reconstruction of it.

### End to end — 720 scoped queries against my own mailboxes

Three operators × five values × both polarities × six spellings × four bodies, over a mailbox
holding the marker in the inbox, in spam, in trash, under a user label and under a category tab,
and a second word planted **only** outside the default mailbox so the ladder runs to the end
rather than stopping on early evidence.

| | this tree | round 18 semantics |
|---|---|---|
| requests into spam or trash from a query that did not ask | **0** | 276 |
| rows disclosed from a region the query excluded | **0** | 48 |

### Zero-evidence affordances — my own twenty-five shapes

```
zero-evidence responses                25
carrying an affordance                 13   (52.0%)
offers executed that reached Gmail     26
offers executed that reached nothing    0
```

The twelve that carry none, each checked: four are queries whose only untried drop is the
query's own content (`zzalpha`, `zzalpha zzbeta`, `zzalpha OR zzbeta`, `zzalpha -zzbeta` —
dropping it leaves a listing, and the ladder including L3 already ran); five have **no** untried
drop at all (`from:…`, `subject:…`, `newer_than:…`, `after:…`, a phrase — the diagnosis is
`complete`, which is a finding rather than a gap); three are the deliberate exclusion class
(`-in:spam`, `-in:trash`, `-label:spam`). The suite asserts that partition rather than the
percentage.

### The recall cost, measured

| query, over a thread whose scope one message satisfies and whose term another carries | round 18 | this tree |
|---|---|---|
| `label:quillon vellichor` | recovered | **not recovered** — `inconclusive`, offer `{'query': 'vellichor'}` |
| `category:updates vellichor` | recovered | **not recovered** — `inconclusive`, offer `{'query': 'vellichor'}` |
| `from:ana@team.example vellichor` (control) | recovered | recovered |
| `is:starred vellichor` (control) | recovered | recovered |

Executing the offered call recovers the thread in both lost cases. That is the trade stated as a
number: two operator families lose L1b's thread-split recovery, the response says so, and the
recovery is one declared call away.

The `category:` row's "round 18" column is measured against the rebuilt tree rather than
`/tmp/rretr18/pristine`, because the round-18 mailbox double raises `UnimplementedOperator` on
`category:` — an operator the ladder could already send. Teaching the double to evaluate it is
part of this round's diff and is why the row can be measured at all.

### Two checks on my own tests rather than on the code

* **a vacuity scan over the two modules this round adds**, written here rather than borrowed: no
  assertion has the same product call on both sides, and every derivation-versus-attribute
  comparison has a written-out literal on the expected side. The candidates it surfaced are the
  classification oracle (compared against a written-out dict), the stub-provenance oracle
  (written out per planted id) and the flag assertion (compared against my own three literal
  spellings);
* **one V-plant of my own**, because the flag assertion reads `operator_token` on both sides and
  emptying it would satisfy both at once. Planted `return token` — no NFKC, no strip, no fold —
  into a scratch copy: `tests/test_region_kind_round19.py` **FAILS**, on three tests
  (`test_a_fragment_that_names_no_operator_and_no_value_declares_no_region`,
  `test_a_region_the_parse_could_not_carry_still_stops_the_broadening`,
  `test_no_probe_of_the_whole_region_family_enters_a_region_the_query_excluded`). The
  normalisation this round leans on is independently anchored.

---

## 7. The spelling-versus-data sweep

Every predicate in `server/src` whose docstring describes a category, checked against what it
reads. Forty-two predicates were enumerated by AST; the ones where the question could arise:

| Predicate | Reads | Verdict |
|---|---|---|
| `operators.declares_the_search_region` | `KIND_BY_OPERATOR` | **repaired this round.** Was a prefix; is now the registry |
| `operators.operator_of` | `OperatorName` | data. New this round |
| `analysis.carries_nothing_to_select_by` | `declares_the_search_region`, `matchable_content_of`, the negation prefix | data |
| `analysis.selects_something` | the above | data |
| `analysis.region_declarations_of` | the above, over fragments **and** raw tokens | data. New this round |
| `ladder.why_this_q_is_not_a_probe` | the three predicates above | data |
| `ladder._widened`'s participant branch | **was** `fragment.partition(":")` compared with a name; **now** `operator_of(fragment)` | **repaired this round.** The fragments are canonical so the two agree today; the difference is that the new one keeps agreeing, and a fragment no documented operator can be read out of is carried unchanged rather than widened into a disjunction of a name nobody wrote |
| `assemble.without_the_region_it_named`'s polarity test | **was** `fragment.startswith`; **now** `operator_token(fragment).startswith` | **repaired this round**, same reasoning |
| `constants.carries_nothing_but_mailbox_scope` | `WIDENING_MAILBOX_OPERATORS` | **spelling, and right — but the docstring was wider than the code.** It refuses a `q` of nothing but the three operators that *leave the default mailbox*; `in:inbox` alone is not refused, because the caller asked for that listing and MailWeave has no business refusing it. The first line said "a mailbox-scope operator", which `in:inbox` is. Corrected in place, with the division of labour written down: a `q` a *rung* composed is held to the wider rule |
| `constants.widens_beyond_the_default_mailbox` | `WIDENING_MAILBOX_OPERATORS` | **spelling, and right.** It is one half of the `includeSpamTrash` coupling and must name the exact `q` spellings the flag is paired with. Widening it to the registry would set the flag for `label:spam`, which is a claim about Gmail's API nothing here can establish; the residue is named in its own docstring and is R-GMAIL's. Conservative direction: it can only refuse a *disagreeing* pair |
| `constants.is_the_widening_mailbox_operator` | `ANYWHERE_OPERATOR` | **spelling, and right.** Its category *is* that one operator — "the operator `BroadeningRung` substitutes" — not a class of them |
| `constants.matchable_content_of` / `carries_no_content` | `unicodedata.category` | data, asked of the runtime. The model instance of this rule |
| `identifiers._looks_like_a_word` | `PUBLISHED_NON_IDENTIFIER_WORDS` | **membership, and right.** A.8a E-c says "no dictionary hit", there is no dictionary, and the docstring says "a published word" rather than "a word" |
| `timepolicy.resolve_relative`'s branch table | the literal expressions of `RELATIVE_EXPRESSIONS` | **spelling, and right.** The category *is* the published phrase, and a member with no branch fails a parametrised test over the whole table |
| `envelope/wire.NotTriedEntry.blocks_not_found` | `BLOCKING_NOT_TRIED` | data, over a closed enum |
| `signals.AnswerTypePresence.blocks_stop` | a tri-state field | data |
| `content/mime.is_attachment` | the part's own filename / attachment id | data |
| `content/payload.is_multipart` | `mime_type.startswith("multipart/")` | **spelling, and right**: MIME's own type/subtype grammar defines the category |
| `content/quotes.looks_quoted`, `_is_attribution_shaped` | text shape | **right by construction**: the category *is* a shape, and both names say "looks like" / "shaped" |
| `auth/tokenstore`, `envelope/fence`, `content/html_text` | markers and syntax this repository itself writes, or HTML's grammar | right |

**Three repairs** (`declares_the_search_region`, `_widened`'s participant branch,
`without_the_region_it_named`'s polarity test), **one docstring narrowed** to what its code does
(`carries_nothing_but_mailbox_scope`), and **seven predicates where a spelling or a membership
test is genuinely the right thing** — each named above with the reason it is right, which is
always the same reason: the category *is* the spelling. An operator this repository pairs a
request flag with, one specific operator, a published word list standing in for a dictionary the
project may not have, a published table of English phrases whose totality a test enforces, MIME's
own grammar, a text shape whose predicate says "looks like", and markers this repository writes
itself.

---

## 8. What I could not establish

* **whether Gmail reads a grouped operator, a fullwidth operator, or `label:spam` the way this
  code now assumes.** Every choice above is conservative in the direction that costs recall
  rather than discloses excluded mail, and PF-20 / R-GMAIL are where a live run answers it;
* **which `label:` values are system mailboxes.** The whole `label:` decision rests on not
  knowing. R-GMAIL, A.6; when it lands, `label:` splits and the recall cost in §6 goes away for a
  user's own labels;
* **whether `in:unread` should be a filter.** Same shape, from the other side: it needs Gmail's
  *location* vocabulary. R-RETR-041 stays open (WS-10);
* **whether `format=metadata` `threads.get` ever omits `labelIds` for a labelled message.** This
  round makes the distinction representable; whether it is ever exercised in production is PF-2;
* **whether `tokenise` should NFKC-normalise.** That decides what the executed `q` contains and
  is A.6's to answer (WS-10). The boundary is closed meanwhile by reading the raw tokens;
* **whether a `category:` tab is a scope.** Argued both ways in §1; I took the uniform reading and
  the alternative is one registry line;
* **whether offering to drop an exclusion should ever be allowed.** I refuse it; ROUTE-01's
  acceptance as written does not admit the exception, which is the orchestrator's to settle;
* **a *positive* region declaration lost to a multi-token group.** `{in:spam in:trash} snicker`
  executes `snicker` in the default mailbox and declares the group dropped as
  `unparsed_syntax`, so it returns rows from a region the caller did not name. This round stops
  the *widening* half of that shape — no rung now sets `includeSpamTrash` for it — and leaves the
  rest, because the negated form of the same shape (`-(in:spam OR in:trash) snicker`) executes
  the default mailbox, which is exactly what the caller asked for, and one rule cannot refuse the
  first without refusing the second. Distributing a boolean over a group is the parser this
  module does not have. Unchanged from round 18 in what it executes; recorded here rather than
  left to be found;
* **anything about a real mailbox.** Every number here is against `httpx.MockTransport` and a
  synthetic double written from Gmail's documentation.

---

## 9. Have I trusted a peer?

The work order told me round 18 was sound except for one predicate, and named the parts to keep.
I did not take that on the work order's word:

* **I ran the reviewer's own reproductions against the unmodified tree first** (`p1`, `p2`, `p3`),
  before changing a line, and all three reproduced exactly as filed;
* **I did not tune against them.** My populations, bodies, vocabulary, oracles and mailboxes are
  mine, and my oracles do not call the predicates under test. Where my numbers and R-RETR's cover
  the same ground they are different numbers over different sets, deliberately;
* **I re-measured round 18 rather than believing the report about it.** The "before" columns in §6
  come from executing `/tmp/rretr18/pristine` — the reviewer's untouched copy of the round-18
  tree — and separately from rebuilding round 18's semantics by planting my own manifest entries.
  The two agree exactly, which is what makes either believable;
* **I checked the claim I was told was correct.** R-RETR reported the filtering control covered;
  I re-registered `priority:` myself, in both trees, and it is;
* **I checked a finding's disposition rather than accepting it.** R-RETR-030's `label:`
  reproduction is *gone*, and I did not report that as a fix: it disappeared because the query no
  longer decomposes, which is my own change's cost, and the `from:` reproduction is unchanged and
  still live. I executed both;
* **I did not trust my own report either.** The acceptance test in §5 was written to fail if my
  fix were an enumeration, and it caught my own test doing exactly that.

Where I did rely on someone else's work without re-deriving it: the sixteen round-18 manifest
entries, which I re-anchored where I moved the code and re-ran in full (§10) rather than
re-justifying each behaviour from scratch.

---

## 10. The reintroduction check

Twenty-eight entries: round 18's sixteen, re-anchored where this round moved the code they
describe, plus twelve for this round's behaviours. Run in a **full** copy of the tree —
`docs/` included, which is what round 18's own first harness broke by omitting — with all three
importable packages asserted to resolve inside the copy and none into the working tree, every
anchor asserted to match exactly once before the write, every file asserted to change by content
hash, and every test the manifest cites asserted to pass on the copy **before** anything was
planted.

```
mailweave         -> <scratch>/server/src/mailweave/__init__.py
mailweave_harness -> <scratch>/harness/src/mailweave_harness/__init__.py
tests             -> <scratch>/tests/__init__.py
resolves into /root/mailweave?  False  False  False
docs/ copied: True     tests/conftest.py copied: True
```

| entry | file | anchor | content hash | its named test | whole suite, that test deselected |
|---|---|---|---|---|---|
| `R1-negated-region-is-not-a-region` | `operators.py` | 1/1 | bd822190 → 7738ada0 | CAUGHT | CAUGHT |
| `R2-l3-widens-out-of-a-declared-region` | `ladder.py` | 1/1 | 15f4ef68 → 9f516168 | CAUGHT | CAUGHT |
| `R3-region-derivation-drops-negations` | `analysis.py` | 1/1 | aba31fee → 34e4c576 | CAUGHT | CAUGHT |
| `R4-relaxation-drops-the-region` | `ladder.py` | 1/1 | 15f4ef68 → c6b2f3ac | CAUGHT | CAUGHT |
| `R5-l0-claims-the-whole-constraint` | `ladder.py` | 1/1 | 15f4ef68 → 41645786 | CAUGHT | CAUGHT |
| `R6-enforcement-credits-a-fragment` | `analysis.py` | 1/1 | aba31fee → 07ba5fb8 | CAUGHT | CAUGHT |
| `R7-negated-phrase-is-searched-for` | `analysis.py` | 1/1 | aba31fee → d0b099e8 | CAUGHT | CAUGHT |
| `R8-predicates-split-a-quoted-value` | `constants.py` | 1/1 | 4e8b0b48 → 484e5cd0 | CAUGHT | CAUGHT |
| `R9-provenance-is-not-the-observed-labels` | `assemble.py` | 1/1 | 6f6e52b3 → d7824508 | CAUGHT | CAUGHT |
| `R10-region-derivation-from-labels-is-empty` | `constants.py` | 1/1 | 4e8b0b48 → 14d24b2c | CAUGHT | CAUGHT |
| `R11-zero-evidence-report-offers-nothing` | `assemble.py` | 1/1 | 6f6e52b3 → 6873c62e | CAUGHT | CAUGHT |
| `R12-content-filter-is-one-category-again` | `constants.py` | 1/1 | 4e8b0b48 → 7172d12a | CAUGHT | CAUGHT |
| `R13-double-crashes-on-a-calendar-invalid-date` | `mailbox.py` | 1/1 | 0e4e80ad → d7e9bf85 | CAUGHT | CAUGHT |
| `R15-a-unit-narrows-into-a-region-nobody-named` | `analysis.py` | 1/1 | aba31fee → 2bda9c42 | CAUGHT | CAUGHT |
| `R16-a-widening-probe-restricts-after-declaring` | `ladder.py` | 1/1 | 15f4ef68 → 3163cafd | CAUGHT | CAUGHT |
| `R14-carriage-strips-grouping-punctuation` | `constants.py` | 1/1 | 4e8b0b48 → bbd6ea60 | CAUGHT | CAUGHT |
| `R17-region-predicate-is-a-prefix-again` | `operators.py` | 1/1 | bd822190 → a3d47a5a | CAUGHT | CAUGHT |
| `R18-the-broadening-gate-cannot-see-an-unparsed-region` | `analysis.py` | 1/1 | aba31fee → 52b19297 | CAUGHT | CAUGHT |
| `R19-a-group-holding-one-operator-is-not-read` | `operators.py` | 1/1 | bd822190 → 4a3958a2 | CAUGHT | CAUGHT |
| `R20-a-label-is-registered-as-a-filter` | `operators.py` | 1/1 | bd822190 → bb4b0e3e | CAUGHT | CAUGHT |
| `R21-stub-rows-lose-their-provenance` | `assemble.py` | 1/1 | 6f6e52b3 → 72f50432 | CAUGHT | CAUGHT |
| `R22-provenance-is-optional-on-a-row` | `wire.py` | 1/1 | 820193a6 → 5fae5b97 | CAUGHT | CAUGHT |
| `R23-an-absent-label-set-is-a-stated-empty-one` | `models.py` | 1/1 | 99fd72bd → 4f43151f | CAUGHT | CAUGHT |
| `R24-an-unobserved-provenance-reads-as-a-negative` | `wire.py` | 1/1 | 820193a6 → 9e9bd328 | CAUGHT | CAUGHT |
| `R25-a-scoped-zero-evidence-response-offers-nothing` | `assemble.py` | 1/1 | 6f6e52b3 → 6551fa45 | CAUGHT | CAUGHT |
| `R26-an-offer-undoes-an-exclusion-the-caller-wrote` | `assemble.py` | 1/1 | 6f6e52b3 → 330b1b0f | CAUGHT | CAUGHT |
| `R27-a-degrouping-offer-inverts-a-negated-region` | `assemble.py` | 1/1 | 6f6e52b3 → d7d81256 | CAUGHT | CAUGHT |
| `R28-the-offer-that-reaches-no-rung-comes-back` | `assemble.py` | 1/1 | 6f6e52b3 → 0dddb25e | CAUGHT | CAUGHT |

**28/28 anchors matched exactly once, 28/28 files changed, 28/28 CAUGHT by the named test and 28/28 CAUGHT by the whole suite with that test deselected.** Elapsed 1,601s.

R1's replacement is worth naming: the predicate it plants into no longer exists where round 18
wrote it, so the entry now plants round 17's polarity defect into `declares_the_search_region`'s
new home - a fragment declares a region only when it is positive. The behaviour it removes is
the same one, and it is still caught by the same test.

---

## 11. Files changed

```
server/src/mailweave/query/operators.py     OperatorKind split; operator_of;
                                            declares_the_search_region; grouped-operator tokenising
server/src/mailweave/query/analysis.py      carries_nothing_to_select_by moved in;
                                            region_declarations_of; RELAXATION_ORDER
server/src/mailweave/query/__init__.py       exports
server/src/mailweave/constants.py            operator_token made public; three predicates removed;
                                            two docstrings narrowed to what they do
server/src/mailweave/retrieval/ladder.py     L3 gate; _anywhere filter; _widened reads the registry
server/src/mailweave/retrieval/assemble.py   unobserved provenance; the deleted offer;
                                            without_the_region_it_named; recovery_affordances
server/src/mailweave/envelope/wire.py        MailboxProvenance's absent derived fields
server/src/mailweave/gmail/models.py         label_ids is absent-able

tests/test_region_kind_round19.py            new: 17 tests, this round's behaviours end to end
tests/test_new_operator_round19.py           new: the acceptance test
tests/fixtures/new_operator.py               new: registration in a scratch tree
tests/fixtures/replants.py                   3 entries re-anchored where the code moved,
                                            12 added, harness repaired (R-RETR-042)
tests/test_replants.py                       renamed from test_replants_round18.py; docstring corrected
tests/fixtures/mailbox.py                    the double evaluates category:
tests/test_lexical_ladder.py                 region population read from the registry; two fixtures
tests/test_query_analysis.py                 relaxation-order population read from the fidelity table
tests/test_region_and_provenance_round18.py  three assertions updated to this round's semantics
docs/reviews/ROUND_19/IMPLEMENTER.md         this report
```

Nothing else was touched. `FINDINGS_LEDGER.md`, `RUBRIC_TRANSITIONS.md` and every rubric
criterion are unchanged; ROUTE-01 is not restored; no retry or backoff constant was edited.

---

## 12. Gates

```
$ ruff check .
All checks passed!

$ ruff format --check .
159 files already formatted

$ mypy
Success: no issues found in 133 source files

$ python -m tools.guards
guards clean: forbidden-import, generative-client, gmail-endpoint, ground-truth-isolation,
              scope-literal, unaudited-disk-write, unwrapped-http-client over server/src

$ pytest -q -m "not network"
2290 passed in 97.09s

$ pytest -m replant
4 passed, 2286 deselected in 67.26s

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

2,271 tests before, **2,290** after: seventeen in `tests/test_region_kind_round19.py`, two in
`tests/test_new_operator_round19.py`. The rubric is unchanged at **6 PASS / 0 FAIL / 0 BLOCKER /
107 NOT TESTED** with eleven transitions; I marked nothing, and ROUTE-01 is not restored.

The four `replant`-marked tests are collected and run by `-m "not network"` — they are part of
the gate above, not additional to it. `pytest -m replant` reproduces §10's table on its own.
