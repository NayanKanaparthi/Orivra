# ROUND 18 — R-RETR review (a region is what an operator *does*, and one prefix is not that)

**Reviewer:** R-RETR, independent instance, 2026-09-04. Sole gating reviewer for round 18.
Verified by execution per `AGENT_LOOP.md` §4/§5/§5a. **Source, tests and docs untouched** — every
probe ran from `/tmp/rretr18/*.py` against the real tree; every planted defect ran in a scratch copy
at `/tmp/rretr18/tree` (a full copy **including `docs/`**) with `PYTHONPATH` set and
`mailweave.__file__` **and** `tests.__file__` asserted to resolve there and asserted *not* to resolve
into `/root/mailweave`. Probe files are named against every result below. Nothing in `/tmp/rretr15`,
`/tmp/rretr16`, `/tmp/rretr17` or `/tmp/r18impl` was used to build any of my sets; where I re-ran a
prior instance's file I say so and label it a regression check. My vocabulary is invented
(`vorpal frobnitz snicker blorp quondam glimlock thrumble wibble`), my senders are `.example` /
`.invalid`, my mailboxes, oracles and seeds are mine.

## Environment

| Gate | Result (run twice, before and after all probing, identical both times) |
|---|---|
| `ruff check .` | All checks passed |
| `ruff format --check .` | 156 files already formatted |
| `mypy --strict` | Success, 130 source files |
| `python -m tools.guards` | 7 guards clean (forbidden-import, generative-client, gmail-endpoint, ground-truth-isolation, scope-literal, unaudited-disk-write, unwrapped-http-client) |
| `pytest -q -m "not network"` | **2,271 passed** in 59s; re-counted independently via `--collect-only -q` summed per file = **2,271** |
| `pytest -m replant` | 2 passed, 27s — the two marked tests **are** in the default gate (report §13 is right; the module docstring of `tests/test_replants_round18.py`, which says they are "deselected from the default run", is wrong) |
| `tools/rubric_status.py --check` | criteria 113; **6 PASS / 0 FAIL / 0 BLOCKER / 107 NOT TESTED**, 11 transitions — as the work order requires |

`mailweave.__file__` → `/root/mailweave/server/src/mailweave/__init__.py`. After all probing,
`diff -r` of `server/`, `tests/` and `tools/` against the copy I took before starting: **identical**.
The only files in the tree with a modification time inside my review window are the implementer's own
(10:02–10:33 UTC, before this review began).

**Scratch-tree discipline.** `/tmp/rretr18/tree` was asserted green (2,271 passed) before the first
plant; `__pycache__` cleared and `server/`, `tests/`, `tools/` restored from a pristine copy between
plants; every plant asserts its anchor count `1/1` before writing and asserts the file changed after,
printing the before/after content hash.

## Reachability rule I applied (§5a)

Unchanged in substance from rounds 15–17. `LadderRunner`, `assemble` and `Envelope` have no MCP tool
surface today; §5a exists to stop findings against code that does not exist and to stop re-review of
sealed modules, **not** to make this round's own code inert. **A defect triggered by an ordinary
query string reaching `LadderRunner.run` + `assemble` is REACHABLE.** Every finding I raise below is
reachable today except where I say otherwise, and where I say otherwise I say what would make it
reachable. Where the *fix* belongs to another workstream I name it, and the finding stays open and
blocking here (§5a: "a deferred finding is blocking in the round it returns to").

---

# Part A — the owner's five requirements, each attacked

## 1. Machine-readable, user-visible mailbox provenance on every `MessageRow`, from actual labels

**Derived from observed labels, not from the query — established.** `assemble.py:755` is the only
place a provenance is built and it reads `Message.label_ids` of the `threads.get` response and
nothing else. There are exactly two `MessageRow(` constructions in the product (`assemble.py:758`
and `:777`) and both pass the same value.

**I could not make a provenance disagree with its labels.** `/tmp/rretr18/` session probe:

```
MailboxProvenance.model_validate({"observed": true,  "labels": [],        "regions": ["spam"]})    REFUSED
MailboxProvenance.model_validate({"observed": true,  "labels": ["INBOX"], "outside_the_default_mailbox": true})  REFUSED
MailboxProvenance.model_validate({"observed": false, "labels": ["SPAM"]}) REFUSED
object.__setattr__(p, "regions", ("spam",))                              AttributeError: property has no setter
```

`regions` and `outside_the_default_mailbox` are `computed_field` properties and `extra="forbid"`
refuses them as input. This is a property of the type, not a convention. I confirm it.

**Every row, at every depth, stubs included — established, and undefended.** `wibble` over a thread
whose members sit in four different places:

```
row x-1 role=matched  mailbox=(observed=True, labels=('INBOX',), regions=(),        outside=False)
row x-2 role=stub     mailbox=(observed=True, labels=('TRASH',), regions=('trash',), outside=True)
row x-3 role=stub     mailbox=(observed=True, labels=('SPAM',),  regions=('spam',),  outside=True)
row x-4 role=matched  mailbox=(observed=True, labels=(),         regions=(),         outside=False)
```

But **removing provenance from every non-hit row leaves all 2,271 tests green** (plant X2,
`/tmp/rretr18/extraplants.py`): with `mailbox=provenance if is_hit else
MailboxProvenance.unobserved()` planted, x-2 and x-3 report `observed: false` and the suite does not
notice. Making `MessageRow.mailbox` optional (plant X1) is likewise green. The stub case is the one
the implementer's own report names as the reason the field had to be on the row — "a thread map can
carry a spam reply into an otherwise ordinary thread" — and my randomised trials produced **808**
such stub rows. **R-RETR-038.**

**Survives serialisation.** `env.model_dump(mode="json")` carries `mailbox` on every row with all
four keys. (The dumped form is not re-validatable, because `extra="forbid"` refuses the two computed
fields on the way back in. Nothing in the product round-trips an envelope, so this is a scope note,
not a finding.)

**A row whose labels were never observed — the third state has no producer.**
`MailboxProvenance.unobserved()` is called nowhere in `server/`; `Message.label_ids` is
`Field(default=(), alias="labelIds")`, so an absent `labelIds` and a stated empty list are the same
value by the time `assemble` sees them. Executed (`/tmp/rretr18/p3_unobserved.py`), with a transport
that omits `labelIds` from `threads.get`:

```
x-1 observed=True labels=() regions=() outside_the_default_mailbox=False
x-2 observed=True labels=() regions=() outside_the_default_mailbox=False   <- the fixture holds x-2 in TRASH
x-3 observed=True labels=() regions=() outside_the_default_mailbox=False   <- and x-3 in SPAM
```

`observed` is a constant `true` in every response the product can produce, and the response makes the
positive claim "this message is in neither region" from an observation that stated nothing. The
docstring's "a third state, not a flag" and the report's "a row the ledger placed but no
label-bearing observation touched reports `observed: false`" are both false on execution.
**R-RETR-039.**

**Collapsed runs.** `CollapsedRun` carries `member_ids` and no provenance — and it has **no product
producer** (`CollapsedRun(` appears only in `tests/`). So "on every row including collapsed runs" is
vacuously true today and would stop being true the first time `assemble` mints one. Recorded as a
scope note against WS-03/WS-11 rather than as a finding, per §5a.

**Verdict: PARTIALLY MET.** The derivation is right, structural, and on the wire. Two defects: the
one shape that motivates it is undefended by any test (R-RETR-038), and the "not known" state the
model documents cannot be produced, so an unobserved label set is reported as an observed absence
(R-RETR-039).

## 2. `-in:spam` never searches spam; explicit scope preserved across every probe

**The plain spellings are fixed, and I confirm it.** Over 330 queries that write a negated spam or
trash region (12 spellings × 10 bodies × 3 tails) and the 1,516 probes they plan, **60** probes enter
a region the query excluded — and **zero** of them come from `-in:spam`, `-in:trash`, `-IN:SPAM`,
`-in:spam,` or `-in:spam -in:trash`. Scope survives decomposition, relaxation and multiple scopes at
once:

```
-in:spam snicker quondam glimlock
   wire [('-in:spam snicker quondam glimlock', False), ('-in:spam snicker', False),
         ('-in:spam quondam', False), ('-in:spam glimlock', False)]
-in:spam from:zz@parts.invalid snicker quondam
   wire [... six probes, every one carrying '-in:spam' ...]
-in:spam -in:trash -in:sent -in:drafts snicker
   wire [('-in:spam -in:trash -in:sent -in:drafts snicker', False)]        one probe, nothing dropped
in:spam -in:spam snicker            wire [('in:spam -in:spam snicker', True)]   contradictory: sent verbatim
in:inbox -in:spam in:anywhere snicker  wire [(verbatim, True)]                  many scopes: sent verbatim
"in:spam" snicker / -"in:spam" snicker  scope inside a phrase is a phrase, not a region  — correct
```

**But three spellings still cross the boundary,** and the 60 partition cleanly across them:

| cause | probes | example |
|---|---|---|
| Gmail grouping punctuation | 30 | `(-in:spam) snicker` → `L3 'in:anywhere snicker' includeSpamTrash=True` |
| `label:` naming a system mailbox | 20 | `-label:spam snicker` → `L3 'in:anywhere snicker' includeSpamTrash=True` |
| fullwidth spelling | 10 | `-ＩＮ：ＳＰＡＭ snicker` → `L3 'in:anywhere -in spam snicker' includeSpamTrash=True` |

End to end, on a mailbox where the search term exists **only** in SPAM and TRASH
(`/tmp/rretr18/p1_grouped_scope.py`, `p2_label_scope.py`):

```
'-in:spam snicker'                wire [('-in:spam snicker', False)]                     rows []          inconclusive
'(-in:spam) snicker'              wire [('snicker', False), ('in:anywhere snicker', True)]
                                  rows [('s-1','matched',('spam',)), ('s-2','matched',('trash',))]  answered
'-(in:spam) snicker'              — identical
'{-in:spam} snicker'              — identical
'-(in:spam OR in:trash) snicker'  — identical
'-label:spam snicker'             wire [('-label:spam snicker', False), ('snicker', False),
                                        ('in:anywhere snicker', True)]
                                  rows [('s-1','matched',('spam',)), ('s-2','matched',('trash',))]  answered
```

The grouped case is the sharper of the two, because the predicate family already agrees with me
about it and the parser does not: `declares_the_search_region('(-in:spam)')`,
`('-(in:spam)')` and `('{-in:spam}')` all return **True** — `_operator_token` strips
`QUERY_GROUPING_PUNCTUATION` precisely so `(in:anywhere)` cannot evade the coupling — while
`parse('(-in:spam) snicker').constraints` is `[('terms', ('snicker',))]`, so `search_region_of` never
sees the fragment and `BroadeningRung._anywhere`'s new gate never fires. The drop is declared
(`unparsed_syntax`), so the response does not lie about it; it still reads the mail the caller
excluded and reports `outcome: answered`. **R-RETR-035** and **R-RETR-036**; the fullwidth half is
**R-RETR-037** (round 17's R-RETR-034 escalated: it is no longer only a narrowing reinterpretation,
it now defeats the region gate).

**Verdict: PARTIALLY MET.** The invariant holds for every `in:` spelling written the way Gmail's own
documentation writes it, in both polarities, across every rung — which is the substance of the
owner's instruction and is a genuine repair of a HIGH. It does not hold when the same operator is
grouped, when the region is named with `label:`, or when it is typed on a fullwidth IME.

## 3. L3 `in:anywhere` broadening kept, only when the user specified no scope

**Kept, and the rows say where they came from.** `snicker` (no scope) still reaches
`in:anywhere snicker` with the flag, and the rows it admits carry `regions ('spam',) / ('trash',)`.
`in:spam vorpal` and `in:anywhere vorpal` are unwidened and correctly flagged.

**A query with a scope that still reaches `in:anywhere` — found, five of them.** The table above:
`(-in:spam)`, `-(in:spam)`, `{-in:spam}`, `-(in:spam OR in:trash)`, `-label:spam`/`-label:trash`, and
the fullwidth `ＩＮ：ＳＰＡＭ` / `-ＩＮ：ＳＰＡＭ`. Each is R-RETR-035/036/037.

**A scope-free query that wrongly does *not* reach it — found.** `names_a_mailbox_location` is
`token.startswith("in:")`, so any value under that prefix is a region declaration, including values
that are not mailbox locations at all. Executed on a mailbox where the term exists only in spam:

```
'snicker'                      wire [('snicker', False), ('in:anywhere snicker', True)]   L3 fires
'is:unread snicker'            wire [5 probes: L1, L1b×2, L2×2]                            decomposes, relaxes
'in:unread snicker'            wire [('in:unread snicker', False)]                         ONE probe
'in:starred snicker'           wire [('in:starred snicker', False)]                        ONE probe
'in:read snicker'              wire [('in:read snicker', False)]                           ONE probe
'in:important snicker'         wire [('in:important snicker', False)]                      ONE probe
'in:nonexistentplace snicker'  wire [('in:nonexistentplace snicker', False)]                ONE probe
```

`in:unread` and `is:unread` are the same request to Gmail. Written with `in:` it names no region, yet
it suppresses L1b, L2 **and** L3 — the whole recovery ladder — and the response is `inconclusive`
with `not_tried` reporting `L0/L1b/L2/L3: not_applicable`. A typo (`in:inbx`) does the same.
**R-RETR-041.**

**Verdict: PARTIALLY MET.** The step survives and is correctly narrowed for the queries the
predicate can see. The predicate's residue cuts both ways: it lets three spellings of a declared
scope through into `in:anywhere`, and it withholds the whole ladder from queries that declared no
region.

## 4. Negated phrases remain exclusions

**Met.** 16 adversarial shapes, all correct — colon-carrying, unicode, uppercase-unicode, multiple
negations, negated beside positive, negated phrase carrying an operator spelling, empty and
whitespace-only phrases:

```
-"thrumble notice vorpal"                     render -"thrumble notice vorpal"   phrases () excluded ('thrumble notice vorpal',)
-"Re: thrumble quarterly" glimlock            render -"Re: thrumble quarterly" glimlock       carrier not matched
-"naïve résumé cliché" glimlock               render carries the negation, qualifying_phrases ()
-"NAÏVE RÉSUMÉ CLICHÉ" glimlock               idem
"thrumble notice vorpal" -"Re: thrumble quarterly"   phrases ('thrumble notice vorpal',) excluded ('Re: thrumble quarterly',)
-"thrumble" -"notice" -"vorpal" glimlock      three exclusions, only the message carrying none is matched
-"in:spam vorpal" glimlock                    the operator spelling inside quotes stays a phrase
-"" glimlock / -" " glimlock                  declared `selects_nothing`, not searched
subject:glimlock -"thrumble notice vorpal"    both carried
```

`qualifying_phrases` is `()` for every negated phrase, so A.8a branch E-b never treats an exclusion
as an exact-signal lookup. I planted the inverse (`qualifying_phrases` reading
`(*phrases, *excluded_phrases)`) and it is **CAUGHT** by two tests. I found no shape where a negated
phrase is searched for.

One behaviour worth the orchestrator's eye rather than mine: an exclusion is **relaxable** at L2.
`in:inbox -"quadrant…" quadrant` drops the exclusion, declares the drop, lowers coverage and does not
claim the constraint on the row. That is the declared-relaxation contract working; whether an
*exclusion* should be relaxable at all is a policy question, and the implementer flagged it. I agree
it is a policy question and not a defect.

**Verdict: MET.**

## 5. Regression and mutation tests failing on replant, including an operator-family sweep

### The vacuity sweep over the whole suite

I swept every test module with an AST scanner (`/tmp/rretr18/vacuity.py`) for the shape "the expected
side is the implementation restated": an assertion with the same product call on both sides, and an
assertion comparing a product-derived attribute against a product derivation with no literal
anywhere. **Zero same-call-both-sides assertions. Forty derivation-vs-attribute candidates**, of
which all but one are a derivation compared with a written-out literal or a parametrised `expected`.

The one that is still literally `f(x) == f(x)` is
`test_a_probe_enforces_only_the_constraints_its_own_q_carries_whole:1183`
(`probe.enforced == constraints_carried_whole(probe.query, parsed_query.constraints)`) — and it is
**not** vacuous, because the same test carries four written-out oracles below it (L0's E-c branch at
both arities, L0's E-b branch at both arities, and L3's `{from:x to:x}` disjunction). Likewise
`test_every_disclosed_row_states_the_region_its_own_labels_place_it_in` now writes its expected
regions out per planted id. **Both of the two the implementer reported catching are genuinely
repaired.** So: **one** surviving instance of the literal shape, zero surviving instances of the
*defect*.

Static scanning is not enough for this class, so I also emptied seven derivations the round's tests
read and asked whether the test that reads each one fails (`/tmp/rretr18/vplant.py`):

```
V1 declares_the_search_region always False        named=FAILS   whole-suite=FAILS
V2 carriage_token collapses to ""                 named=FAILS   whole-suite=FAILS
V3 constraints_carried_whole always empty         named=FAILS   whole-suite=FAILS
V4 mailbox_regions_of always empty                named=FAILS   whole-suite=FAILS
V5 search_region_of always empty                  named=FAILS   whole-suite=FAILS
V6 query_tokens reverts to a whitespace split     named=FAILS   whole-suite=FAILS
V7 region_constraint_names always empty           named=GREEN   whole-suite=FAILS
```

Every oracle the round's tests stand on is independently anchored. V7 is the one whose two obvious
test modules do not hold it (something else in the suite does) — a coverage note, not a defect.

### The operator-family sweep: is it a family sweep?

**For a filtering operator, yes.** I added `PRIORITY = "priority"` to `OperatorName` with
`OperatorKind.TEXT` and registered it everywhere the guards force
(`KIND_BY_OPERATOR`, `FIDELITY_TABLE`, `OPERATOR_FAMILY_VALUES`, the double's
`IMPLEMENTED_OPERATORS`) — `/tmp/rretr18/newop2.py filter`. Suite: **2,274 passed**. Behaviour:
`priority:high` is relaxable, droppable from decomposition, carried whole where it should be, and
`-in:spam priority:high snicker` correctly plans **no** L3 step. A filtering operator nobody added
is covered, without editing any predicate.

**For a scope-declaring operator, no — and the suite does not notice.** I added
`MAILBOX = "mailbox"` with `OperatorKind.LOCATION`, registered identically
(`/tmp/rretr18/newop2.py scope`). Suite: **2,274 passed, green**. Behaviour, run from the scratch
tree with `mailweave.__file__` asserted at `/tmp/rretr18/tree/...`:

```
declares_the_search_region('mailbox:spam')   = False
declares_the_search_region('-mailbox:spam')  = False

'-mailbox:spam snicker'          probes  L1 '-mailbox:spam snicker' False
                                         L2 'snicker'               False     <- the region relaxed away
                                         L3 'in:anywhere snicker'   True      <- widened out of the region
'-mailbox:spam snicker quondam'  probes  L1b 'snicker' / 'quondam'   False     <- the region dropped from every unit
                                         L3 'in:anywhere snicker quondam' True
```

Registering an operator without a family value **does** fail five tests, including the family sweep —
so the sweep cannot be *narrowed* by adding an operator, which is a real and worthwhile guard, and I
confirm it. But registering it properly leaves the sweep green while the new scope operator is
dropped, relaxed away and widened out of. What generalises is *"a new location value written under
the `in:` prefix"* (`in:snoozed`, `in:sent` — I confirm those behave identically without an edit),
not *"a scope operator nobody has added yet"*, which is what A9-A2 and the docstring claim. The
predicate asks a **spelling** question; `KIND_BY_OPERATOR` — the field that says what an operator
does — is not consulted, and could not be as it stands, because `OperatorKind.LOCATION` also holds
`is`, `has`, `list` and `filename`. **R-RETR-036.**

### The 16 replants

Reproduced independently, in my own scratch tree at `/tmp/rretr18/replanttree`
(`/tmp/rretr18/replant_run.py`, `whole_suite=True`):

```
mailweave.__file__ -> /tmp/rretr18/replanttree/server/src/mailweave/__init__.py
tests.__file__     -> /tmp/rretr18/replanttree/tests/__init__.py
resolves into /root/mailweave? False False

all 16 entries: anchor 1/1, file changed True, CAUGHT by its named test, CAUGHT by the
whole suite with that test deselected.
```

**I confirm the implementer's table in full**, including the greenness precondition on the pristine
copy. This is the claim round 17 could not make and it is now true.

**What the manifest does not cover.** I planted eleven behaviours the round changed that are *not*
in it (`/tmp/rretr18/extraplants.py`, `extra2.py`). Nine are CAUGHT — including a swapped region
label vocabulary, a provenance that filters SPAM/TRASH out of the labels, an L3 gate that reads only
positive regions, a narrowing location no longer carried onto a unit, `extra="ignore"` on
`MailboxProvenance`, a region present in one vocabulary and absent from the other, and the
`qualifying_phrases` inversion. **Two are MISSED**, both about provenance being on *every* row: X1
(`MessageRow.mailbox` defaulted rather than required) and X2 (stub rows lose it). **R-RETR-038.**

**Two holes in the harness itself.** (a) `_environment` puts `scratch/server/src` and `scratch` on
`PYTHONPATH` but not `scratch/harness/src`, and the assertion covers `mailweave` and `tests` only —
so in the planted subprocess `mailweave_harness` resolves to
`/root/mailweave/harness/src/mailweave_harness/__init__.py`, and the five test modules that import it
run against the **working** tree. No manifest entry plants into `harness/`, so no row above is wrong;
the claim "both packages resolve inside the scratch copy" simply covers two of the three importable
packages the suite uses. (b) The in-suite runner calls `run_replants(scratch)` with
`whole_suite=False`, which is the branch that skips `assert_the_scratch_tree_is_green` — so the CI
copy of the round's central evidence has no positive guard that the copy it planted into was sound,
which is the failure mode that function's own docstring exists for. I tried two realistic copy
breakages (omitting `docs/`, omitting `conftest.py`) and neither made it vacuous, so this is a
missing guard rather than a live vacuity. **R-RETR-042.**

**Verdict: PARTIALLY MET.** The replant manifest is real, exhaustive over the diff it claims, and
independently reproduced 16/16 both ways — this is the strongest testing work any round of this
project has produced. Two behaviours the round changed are outside it and undefended, and the
operator-family sweep is a family sweep for filters and a prefix sweep for scopes.

---

# Part B — recall, evidence preservation, and the remaining findings

## Recall, adversarially, on my own sets

1,200 randomised trials over three seeds (`/tmp/rretr18/recall.py`), oracle written in the harness
implementing RO F2 message-scoping plus the thread-level recovery L1b promises, over region-free,
`in:anywhere`, `in:spam`, `-in:spam` and `in:inbox` shapes:

```
trials 1200   answered 821   threads the oracle says must be reached 1450
threads present that the ladder does not return while reporting `answered`    0
threads present that it does not return while reporting `inconclusive`        0
```

The one deliberate recall loss this round introduces — the region is no longer relaxable, so
`in:inbox snicker` for a message outside the inbox now returns nothing — is **not** a recall defect:
the query named the inbox and the message is not in it. It is correctly reported `inconclusive` with
`empty_diagnosis.status: incomplete` and `untried_drops ('in','terms')`, which is OD-2's shape. The
`in:unread` class (R-RETR-041) *is* a recall loss, because those queries named no region.

## Evidence preservation: `H = disclosed ∪ withheld`

2,200 randomised end-to-end trials on my own mailboxes, five seeds, across the new provenance path,
the tightened scope rules and the L3 replacement (`/tmp/rretr18/trials.py`):

| | 1,800 ordinary (seeds 180418 / 7 / 991) | 400 forced-overflow (seeds 2026 / 55) |
|---|---|---|
| envelopes / raises / crashes | 1,800 / 0 / 0 | 400 / 0 / 0 |
| `H ⊆ disclosed ∪ withheld` violations | **0** | **0** |
| disclosed ∩ withheld | **0** | **0** |
| phantom ids | **0** | **0** |
| provenance disagreeing with the planted labels | **0** | **0** |
| rows seen / rows outside the default mailbox | 8,263 / 3,645 | 5,318 / 2,013 |
| withheld records exercised | 0 | **267** |
| spam/trash requests over an excluding query | 15 | 0 |
| **matched** rows from an excluded region | 13 | 0 |
| stub rows from an excluded region | 511 | 297 |

The provenance oracle is written in the trial harness against the planted label sets, not by calling
`mailbox_regions_of`. All 15 requests and all 13 matched rows are R-RETR-035/036: 12 of 15 and 12 of
13 are the `label:` residue, the rest the grouped spelling. The 808 stub rows are thread-map members
in spam or trash whose thread was matched elsewhere — I agree with the implementer that disclosing
them as stubs *and saying where they are* is the right answer, and it is exactly what makes the field
worth having.

## ROUTE-01 and R-RETR-032

**The report class is improved.** `thread:1837abf`, `tel:+15550100`, `(vorpal OR frobnitz)` and
`{vorpal frobnitz}` now mint an offer, and I executed each: all four reach Gmail.

**The third kind of offer does not reach Gmail.** For a query naming only where to look, the offer is
`{"query": "in:anywhere", "terms": []}`. Executed:

```
'in:anywhere'  first pass wire=[]  offer {'query': 'in:anywhere', 'terms': []}
   -> executing the offer 'in:anywhere': wire=[] rows=0 outcome=inconclusive   REACHES GMAIL = False
'in:spam', 'in:trash'  — identical
```

`test_a_zero_evidence_report_offers_the_call_that_would_reach_a_rung` executes three queries and this
is not among them; `test_a_report_with_nothing_to_offer_offers_nothing` asserts this offer's *shape*
only. No tool in the tree takes a `terms` argument. So §9's "**Every** affordance the report class
mints is executed and asserted to reach Gmail" is false: this one is a suggestion, which is the
distinction AD-03 draws.

**And the ordinary zero-evidence response still carries none.** 900 randomised zero-evidence probes
over 22 shapes:

```
zero-evidence responses                      822
carrying an affordance                        93
carrying none                                729   (88.7%)
```

with examples that have a concrete untried call:

```
'in:sent frobnitz'      untried_drops ('in','terms')  not_tried L0/L1b/L2/L3  outcome inconclusive  affordance none
'in:drafts glimlock'    untried_drops ('in','terms')  not_tried L0/L1b/L2/L3  outcome inconclusive  affordance none
'zzalpha OR zzbeta'     untried_drops ('terms',)      not_tried L0/L2         outcome inconclusive  affordance none
```

R-RETR-032's own repro list included `borogrove` and `from:nobody@… borogrove` — the ordinary class —
and those are untouched. **R-RETR-040.** ROUTE-01's acceptance is "100% of zero-evidence responses
carry … and affordances"; the measured rate is 11.3%.

## R-RETR-030 — is the refusal right, or an evasion?

**Right, and I checked rather than read.** `ExecutedProbe` records `ids_returned` (a count),
`ids_admitted` (a delta), and `threads`/`thread_of` — and `threads` is built from `admitted`
(`ladder.py:1043–1052`), so it is a delta too. Nothing in the seam records which ids or threads a
probe's *page* contained. "Which routes admitted a disclosed row" is therefore not computable in
`assemble`, exactly as the docstring says. I implemented the required fix (intersection over routes
with a non-empty admission, restored to the full route set when none has one) in the scratch tree:

```
FAILED tests/test_lexical_ladder.py::test_a_decomposition_probe_is_not_reported_as_a_dropped_constraint
FAILED tests/test_lexical_ladder.py::test_a_probe_whose_rows_an_earlier_probe_admitted_still_counts_as_a_route
```

— precisely the two named. The account is accurate and the judgement is correct. **The finding stays
open**, narrowed to two live reproductions rather than three, one of which the implementer did not
name:

```
label:projecta vorpal     enforced ('label','terms') tc 1.0 dropped []  over l-2, which carries no PROJECTA label
from:a@parts.example vorpal  enforced ('from','terms') tc 1.0 dropped []  over l-2, whose sender is b@parts.example
in:inbox vorpal           fixed by Part 1 — one route, both rows in the inbox
newer_than:7d vorpal glimlock  fixed — enforced ('terms',) tc 0.5, newer_than dropped
```

Per-row `constraint_coverage` is honest in both live cases, which is what keeps it at MEDIUM.
**WS-16 / amendment A1** for the seam; the alternative (keep the union, stop deriving
`term_coverage` from it) is a contract change and belongs with the orchestrator. I agree with both
halves of that.

## R-RETR-029, 033, 034, 031 on this round's code

* **R-RETR-029 — narrowed, not closed; I confirm both halves.** My own sweep of the whole Unicode
  space (not the BMP): **967,113** code points in the ten categories, **0** of them content-bearing
  bare, negated or quoted. The residue is live and correctly named: `matchable_content_of('ㅤ')` is
  `'ᅠ'`, and `mailweave_search('ㅤ')` still plans `[('ᅠ', False), ('in:anywhere ᅠ', True)]` —
  R-RETR-017's wire shape. Severity is still decided at **R-GMAIL**. Open, **WS-10**.
* **R-RETR-033 — closed.** `after:2026/13/45 vorpal`, `before:2026/02/31 vorpal`,
  `after:0000/01/01 vorpal` and a two-invalid-date query all run end to end without raising.
* **R-RETR-034 — closed as filed, reopened wider.** The two modules still disagree about NFKC, and
  the consequence is no longer only a narrowing reinterpretation: it now defeats the round-18 region
  gate. Refiled as **R-RETR-037** at MEDIUM.
* **R-RETR-031 — closed.** The L3 branch is a positive assertion identified by what the probe did
  (`regions_a_probe_added`), the narrowing half is asserted, and R15/R16 are standing manifest
  entries that I re-ran and confirmed CAUGHT by the invariant test alone.

---

## Findings

```
ID:            R-RETR-035
Severity:      HIGH
Reachability:  REACHABLE today. An ordinary Gmail query string — parentheses are Gmail's
               own documented grouping syntax and a calling agent composing
               `-(in:spam OR in:trash)` is the likeliest producer — through
               LadderRunner.run + assemble, both of which exist and execute.
Rubric:        OD-5 point 3 and A9-A2/A3 (an explicit scope is preserved across every
               probe; `in:anywhere` only when the query named no scope); the work order's
               exit condition ("No probe reaches a region the query excluded"); LEX-02;
               EV-04's paired hallucinated-found guard; contract I-4.
Location:      server/src/mailweave/query/operators.py, tokenise — a token carrying a
                 group opener or closer is classified `passthrough` and never becomes a
                 constraint fragment, whatever it says;
               server/src/mailweave/retrieval/ladder.py, BroadeningRung._anywhere — its
                 new gate reads `search_region_of(parsed.constraints)`, so a region the
                 parse discarded is a region the gate cannot see;
               server/src/mailweave/constants.py, declares_the_search_region — which
                 *accepts* the grouped spelling, because `_operator_token` strips
                 QUERY_GROUPING_PUNCTUATION for exactly this reason. The predicate family
                 and the parser disagree about the same token.
Repro:         /tmp/rretr18/p1_grouped_scope.py  (mailbox: 'snicker' only in SPAM and TRASH)
                 declares_the_search_region('(-in:spam)')  = True
                 declares_the_search_region('-(in:spam)')  = True
                 parse('(-in:spam) snicker').constraints  = [('terms', ('snicker',))]
                 mailweave_search('(-in:spam) snicker')
                   wire    [('snicker', False), ('in:anywhere snicker', True)]
                   rows    s-1 matched regions ('spam',); s-2 matched regions ('trash',)
                   outcome answered      dropped ['unparsed_syntax']
                 identical for '-(in:spam) snicker', '{-in:spam} snicker',
                 '-(in:spam OR in:trash) snicker', '(-in:spam -in:trash) snicker'
               Plan-layer: 330 queries writing a negated spam/trash region, 1,516 probes,
                 30 probes entering the excluded region from this cause alone.
Expected:      A fragment that declares the region declares it however it is written.
               `declares_the_search_region` already says so; the parse must hand the
               predicate the token, or `BroadeningRung` must read the region off something
               that survives the parse. `-(in:spam) snicker` must not send `in:anywhere`
               with includeSpamTrash=true and must not disclose the excluded rows.
Actual:        A grouped scope is `passthrough`, so `search_region_of` is empty, so the
               round-18 gate does not fire, so the published broadening runs and returns
               the SPAM and TRASH messages as `role: matched` under `outcome: answered`.
               The drop is declared as `unparsed_syntax`, so the response is not lying —
               it has read mail the caller told it not to read, which is the different
               kind of wrong OD-5 was written about.
Required fix:  Two candidates, and the choice is the implementer's. (1) `tokenise` strips
               the grouping punctuation from a token that would otherwise parse as an
               operator, and re-emits it without the group — sound because a group of one
               operator is that operator, and `_operator_token` already assumes it. (2) If
               a `passthrough` token cannot be re-emitted, then `BroadeningRung.plan` must
               decline whenever any *raw* token of the query satisfies
               `declares_the_search_region`, not only when a constraint fragment does — the
               conservative reading, and the one that matches the predicate's own docstring.
               Either way the test is a family sweep over `NARROWING_MAILBOX_LOCATIONS` and
               `WIDENING_MAILBOX_OPERATORS` × both polarities × the four grouping spellings,
               and it must be in the replant manifest.
```
```
ID:            R-RETR-036
Severity:      HIGH
Reachability:  REACHABLE today through `-label:spam` / `-label:trash`, which are ordinary
               Gmail syntax reaching `analyse` from any query string. The structural half —
               a scope operator that is not spelled `in:` — is established by execution but
               is not reachable until such an operator exists; I record both, because the
               binding claim in A9-A2 is about the second and the wrong rows come from the
               first.
Rubric:        OD-5 point 3 and A9-A2 verbatim ("the invariant's asymmetry clause must be
               derived from what an operator does, so it holds for scope operators nobody
               has added yet"); the work order's Part 4 ("the sweep is over the *family*,
               not per operator"); LEX-02; EV-04; contract I-4.
Location:      server/src/mailweave/constants.py, names_a_mailbox_location —
                 `token.startswith(MAILBOX_LOCATION_PREFIX)`, i.e. one lexical prefix;
               server/src/mailweave/constants.py, declares_the_search_region — which asks
                 that question after stripping polarity and nothing else;
               server/src/mailweave/query/operators.py, KIND_BY_OPERATOR — the mapping that
                 does record what an operator constrains, is not consulted, and could not be
                 as it stands, because OperatorKind.LOCATION also holds `is`, `has`, `list`
                 and `filename`;
               tests/test_lexical_ladder.py, the region half of
                 test_every_probe_the_ladder_composes_searches_the_region_the_query_named,
                 whose population is generated from the prefix and therefore cannot see this
Repro:         /tmp/rretr18/p2_label_scope.py  (mailbox: 'snicker' only in SPAM and TRASH)
                 mailweave_search('-label:spam snicker')
                   wire    [('-label:spam snicker', False), ('snicker', False),
                            ('in:anywhere snicker', True)]
                   rows    s-1 matched regions ('spam',); s-2 matched regions ('trash',)
                   enforced ('terms',)  outcome answered
                   dropped ('label', "no route this response rests on carried
                            '-label:spam': the evidence came from L3 …")
                 identical for '-label:trash snicker'
               /tmp/rretr18/newop2.py scope — `MAILBOX = "mailbox"` added to OperatorName
                 with OperatorKind.LOCATION and registered in KIND_BY_OPERATOR,
                 FIDELITY_TABLE, OPERATOR_FAMILY_VALUES and the double's
                 IMPLEMENTED_OPERATORS, exactly as an implementer adding one would:
                   pytest -m "not network"  ->  2,274 passed, GREEN
                   declares_the_search_region('-mailbox:spam') = False
                   '-mailbox:spam snicker'         L2 'snicker' / L3 'in:anywhere snicker' True
                   '-mailbox:spam snicker quondam' L1b 'snicker' / 'quondam' — region dropped
                 The control: `PRIORITY = "priority"` with OperatorKind.TEXT, registered the
                 same way, is correctly treated as a filter throughout (2,274 passed).
               1,800 randomised trials: 12 of 15 spam/trash requests over an excluding query
                 and 12 of 13 matched rows from an excluded region come from this cause.
Expected:      A9-A2's own sentence: the clause is derived from *what an operator does* —
               whether it selects a region or filters within one — so it holds for scope
               operators nobody has added yet. Adding a LOCATION-kind operator and finding
               it dropped from every unit, relaxed away, and widened out of, with the suite
               green, is that sentence being false.
Actual:        The derivation is a one-prefix vocabulary. It generalises over *location
               values* under `in:` — which is real and is why `in:snoozed` and `in:sent`
               need no edit — and not over scope *operators*. `label:spam` selects the spam
               region and is read as a filter, so `-label:spam` is relaxed away at L2 and
               the query is widened into the region it excluded. A new scope operator is
               uncovered and nothing in 2,274 tests says so.
Required fix:  The honest half first: `declares_the_search_region`'s docstring and A9-A2's
               claim must be narrowed in writing to what the code does — "a location value
               under Gmail's `in:` prefix, in either polarity" — because a claim to
               generalise that does not is worse than a named vocabulary. Then close the
               reachable half: `label:` naming a system mailbox needs Gmail's system-label
               vocabulary, which nothing here can establish (**R-GMAIL / A.6**), so until
               that lands the conservative rule is available and cheap — a `label:` value
               that case-folds to a member of `REGION_LABEL_BY_OPERATOR`'s region names is
               treated as a region declaration. That is a two-value vocabulary and it is
               the one A9 forbids writing; the alternative is to keep it open and stop
               claiming the generalisation. My recommendation is: narrow the claim now,
               take the conservative rule now (a false *refusal to widen* costs recall and
               is recoverable; a false widening reads excluded mail and is not), and put
               the structural derivation — a per-operator "selects a region / filters within
               one" fact beside `KIND_BY_OPERATOR`, which is where it belongs — on
               **WS-10** with R-GMAIL's label question attached. Whatever is chosen, the
               family sweep must be given a new LOCATION-kind operator and must fail.
```
```
ID:            R-RETR-037
Severity:      MEDIUM
Reachability:  REACHABLE today. A fullwidth-typed query from an IME reaches `analyse`
               unchanged. Supersedes R-RETR-034 (LOW), which is the same root cause with a
               smaller consequence; the consequence is now a scope-preservation violation.
Rubric:        OD-5 point 3; A9-A2; LEX-02; the residue `widens_beyond_the_default_mailbox`
               names in its own docstring.
Location:      server/src/mailweave/query/operators.py, tokenise (no NFKC) against
               server/src/mailweave/constants.py, _operator_token and matchable_content_of
                 (both NFKC-normalise). Round 18 made `query_tokens` the one splitter and
                 left the two *normalisations* disagreeing, which is the half that matters
                 now that a region declaration is what the predicate is looking for.
Repro:         /tmp/rretr18/sweep.py and directly:
                 mailweave_search('-ＩＮ：ＳＰＡＭ snicker')
                   probes  L1 '-in spam snicker' False; L1b 'spam' / 'snicker';
                           L3 'in:anywhere -in spam snicker'  includeSpamTrash=True
                 mailweave_search('ＩＮ：ＳＰＡＭ snicker')
                   probes  L3 'in:anywhere spam snicker'      includeSpamTrash=True
                 declares_the_search_region('-ＩＮ：ＳＰＡＭ') is True — the predicate reads
                 it as a region; the parser does not, so the gate never sees it
               Plan-layer: 10 of the 60 boundary-crossing probes in my 330-query set.
Expected:      One token, one reading. Whichever way A.6's normalisation policy is decided,
               a fullwidth `-in:spam` must not become the terms `-in` and `spam` and then
               reach `in:anywhere` with includeSpamTrash=true.
Actual:        The parser reads it as terms; `in:` is stripped as a stopword; the query is
               treated as having declared no region; L3 widens into spam and trash. Round
               17 filed this as a narrowing reinterpretation (LOW). Round 18's region gate
               made the same disagreement a boundary crossing.
Required fix:  Unchanged in substance from R-RETR-034 and now urgent: `tokenise` and
               `constants._operator_token` must apply the same normalisation, and the
               decision must be written where both read it (**A.6 / WS-10**). Until it is
               decided, `BroadeningRung.plan` can decline on the NFKC-normalised raw
               tokens, which is the same conservative rule R-RETR-035's fix (2) needs and
               closes both with one clause.
```
```
ID:            R-RETR-038
Severity:      MEDIUM
Reachability:  REACHABLE as a coverage defect today — the behaviour is correct in the tree
               and nothing holds it, so the next diff that touches `assemble` can remove it
               silently. It is the round's own central behaviour, in the shape the round's
               own report names as its motivation.
Rubric:        OD-5 point 1 ("**Every** `MessageRow` carries machine-readable mailbox
               provenance"); A9-A1; work order Part 4 ("every behaviour this round changes
               gets a test that fails when the behaviour is removed"); AL §7.2.
Location:      server/src/mailweave/retrieval/assemble.py, the second MessageRow
                 construction (the stub/thread-map branch, `mailbox=provenance`);
               server/src/mailweave/envelope/wire.py, MessageRow.mailbox — required by
                 declaration, with a comment saying requiredness is the point;
               tests/fixtures/replants.py — neither behaviour is a manifest entry
Repro:         /tmp/rretr18/extraplants.py, over a scratch tree asserted green first, with
               `mailweave.__file__` and `tests.__file__` asserted inside it:
                 X1  `mailbox: MailboxProvenance = MailboxProvenance(observed=False)`
                       anchor 1/1, file changed          -> 2,271 passed  **MISSED**
                 X2  `mailbox=provenance if is_hit else MailboxProvenance.unobserved()`
                       anchor 1/1, file changed          -> 2,271 passed  **MISSED**
               and X2 is behaviour-changing, executed on the planted tree:
                 mailweave_search('wibble')
                   x-2 role=stub observed=False labels=() regions=()   (the fixture: TRASH)
                   x-3 role=stub observed=False labels=() regions=()   (the fixture: SPAM)
               My 2,200 randomised trials produced 808 stub rows in spam or trash. Nine
               other off-manifest plants over the same paths are CAUGHT, so this is two
               specific holes rather than a thin area.
Expected:      "Every row gets it — matched, stub and thread-map alike — because a thread
               map can carry a spam reply into an otherwise ordinary thread" (IMPLEMENTER
               §1). If that sentence is load-bearing, removing it must fail a test.
Actual:        `test_every_disclosed_row_states_the_region_its_own_labels_place_it_in`
               reads `rows(envelope)`, and its written-out oracle covers ids that are all
               hits in its fixture, so it never observes a stub. Nothing else asserts a
               stub row's provenance, and nothing asserts that the field is required.
Required fix:  Two manifest entries and the assertions that catch them. (a) Extend
               `test_every_disclosed_row_states_the_region_its_own_labels_place_it_in`'s
               fixture with a thread whose matched member is in the default mailbox and
               whose *stub* members are in SPAM and TRASH, and assert those stub rows'
               written-out regions — the shape that produced 808 rows in my trials. (b)
               Assert the requiredness directly: `MessageRow.model_validate` of a payload
               with no `mailbox` key is refused. Both belong in `tests/fixtures/replants.py`
               (four lines each, as the manifest's own docstring says).
```
```
ID:            R-RETR-039
Severity:      LOW
Reachability:  REACHABLE today for the false statement (`observed: true` over labels no
               observation stated) whenever a `threads.get` response omits `labelIds` for a
               message; whether Gmail ever omits it for a message that *has* labels is
               R-GMAIL. The dead third state is reachable as a claim in the response schema
               and in the round's report today.
Rubric:        OD-5 point 1; A9-A1; amendment A6's absence-versus-zero discipline, which
               `MailboxProvenance`'s docstring cites as its model; LEX-02.
Location:      server/src/mailweave/gmail/models.py:137 —
                 `label_ids: tuple[str, ...] = Field(default=(), alias="labelIds")`, so
                 "absent" and "stated empty" are one value by the time assemble sees it;
               server/src/mailweave/retrieval/assemble.py:755 — `MailboxProvenance.of(...)`
                 unconditionally, so `observed` is a constant `true`;
               server/src/mailweave/envelope/wire.py:379 — `unobserved()`, whose only
                 callers are `tests/fixtures/envelope_kit.py` and one assertion
Repro:         /tmp/rretr18/p3_unobserved.py — the real client and the real assemble, behind
               a transport that removes `labelIds` from each threads.get message:
                 x-1 observed=True labels=() regions=() outside_the_default_mailbox=False
                 x-2 observed=True labels=() regions=() outside_the_default_mailbox=False
                 x-3 observed=True labels=() regions=() outside_the_default_mailbox=False
                 x-4 observed=True labels=() regions=() outside_the_default_mailbox=False
               ground truth: x-2 is TRASH, x-3 is SPAM.
               grep -rn "unobserved" server/ -> one definition, no product caller.
Expected:      The docstring's own words: "`observed` is a third state and not a flag. A row
               whose labels no observation stated … reports `observed: false` and no
               regions, which says 'this response does not know' rather than 'this message
               is in neither region'." A field that can only take one value in production
               is a flag that has been documented as a state.
Actual:        Every row the product can produce reports `observed: true`. Where Gmail
               stated nothing, the response states `outside_the_default_mailbox: false` —
               a positive claim about the message's location derived from nothing observed,
               which is the class OD-5 exists to end, arriving one layer below the field
               written to end it.
Required fix:  Give `Message.label_ids` the absence A6 gives `observed_internal_dates`:
               `tuple[str, ...] | None = None`, so an absent `labelIds` is distinguishable
               from a stated empty list, and have `assemble` call `MailboxProvenance.of`
               only for the first and `unobserved()` for the second. Assert it with a test
               that drives a `threads.get` response with no `labelIds`, and put it in the
               manifest. Separately record for **R-GMAIL** whether `format=metadata`
               `threads.get` ever omits `labelIds` for a labelled message, which decides
               whether this is a schema tidy or a live wrong disclosure.
```
```
ID:            R-RETR-040
Severity:      MEDIUM
Reachability:  REACHABLE today. Every zero-evidence response, which is the commonest
               response an unanswerable query produces.
Rubric:        ROUTE-01 acceptance ("100% of zero-evidence responses carry: queries
               executed, constraints dropped with reasons, per-rung hit counts, what was not
               tried, and **affordances**"); AD-03 (an affordance is a concrete call that
               would reach the untried rung); this is R-RETR-032 partly closed rather than
               closed.
Location:      server/src/mailweave/retrieval/assemble.py, report_affordances — mints only
                 for the no-rung-ran report class, and its third kind
                 (`carries_nothing_but_mailbox_scope`) mints a call that reaches nothing;
               server/src/mailweave/retrieval/assemble.py, _empty_diagnosis — mints only for
                 a restoring drop or a budget-bound untried drop, and the round's own
                 "the region is not relaxable, and is offered no budget" rule removes the
                 second for every scoped query;
               tests/test_region_and_provenance_round18.py,
                 test_a_zero_evidence_report_offers_the_call_that_would_reach_a_rung — three
                 queries, none of them the scope-only kind;
                 test_a_report_with_nothing_to_offer_offers_nothing — asserts the scope-only
                 offer's shape rather than executing it
Repro:         /tmp/rretr18/ session probes:
                 900 randomised zero-evidence probes over 22 shapes:
                   zero-evidence responses 822; carrying an affordance 93; carrying none 729
                 with untried drops and no offer:
                   'in:sent frobnitz'    untried_drops ('in','terms')  not_tried L0/L1b/L2/L3
                   'in:drafts glimlock'  untried_drops ('in','terms')  not_tried L0/L1b/L2/L3
                   '-in:spam snicker'    untried_drops ('in','terms')  not_tried L0/L1b/L2/L3
                   'zzalpha OR zzbeta'   untried_drops ('terms',)      not_tried L0/L2
                 and the offer that does not reach Gmail, executed:
                   mailweave_search('in:anywhere') -> offer {'query': 'in:anywhere',
                                                             'terms': []}
                   executing that offer -> wire []  rows 0  outcome inconclusive
                   (same for 'in:spam', 'in:trash'; no tool in the tree takes `terms`)
Expected:      ROUTE-01's fifth element on 100% of zero-evidence responses, and AD-03's
               "concrete call that would reach the untried rung" for each one minted.
               R-RETR-023's rule — offer nothing where nothing would help — narrows which
               responses need one; it does not reach `in:sent frobnitz`, which names two
               untried drops and four untried rungs.
Actual:        11.3% of my zero-evidence responses carry an affordance. The report class
               R-RETR-032 named is improved for two of its three kinds — I executed those
               two and they reach Gmail — and the third mints a re-run of the same refused
               query with a decorative empty `terms` slot. The round's own report claims
               "**every** affordance the report class mints is executed and asserted to
               reach Gmail"; the test executes three of the four offers it produces and the
               fourth would fail.
Required fix:  (a) Delete or repair the scope-only offer. `{"query": "in:anywhere",
               "terms": []}` reaches no rung; if the intent is "tell the caller to add
               something to look for", that is an affordance with no executable form today
               and R-RETR-023's own rule says mint nothing. Extend
               test_a_zero_evidence_report_offers_the_call_that_would_reach_a_rung to
               execute **every** offer any of the report class's branches mints, generated
               from the branch set rather than listed. (b) Mint an offer in
               `_empty_diagnosis` for an untried drop that has no budget, which is the class
               the region rule created: the honest offer for `-in:spam snicker` is the same
               query without the exclusion, and offering it is not crossing the boundary —
               the caller crosses it or does not. If the orchestrator judges that MailWeave
               must never offer to cross a stated boundary, then ROUTE-01's acceptance needs
               that exception written into it, because as written it is unmeetable.
```
```
ID:            R-RETR-041
Severity:      MEDIUM
Reachability:  REACHABLE today. `in:unread`, `in:read` and `in:starred` are ordinary Gmail
               idioms; a mistyped location (`in:inbx`) is ordinary user error.
Rubric:        LEX-03 (multi-constraint decomposition — suppressed entirely); ROUTE-02
               (mis-parse recovery — a mistyped location disables every recovery rung);
               ROUTE-03; A.7 L1b/L2/L3.
Location:      server/src/mailweave/constants.py, names_a_mailbox_location — any value
                 under the `in:` prefix is a mailbox location, including values that name a
                 message state rather than a region;
               and, through it, `carries_nothing_to_select_by`, `decomposition_units_of`,
               `RelaxationRung._relaxed_query` and `BroadeningRung._anywhere`, all of which
               now treat such a token as an unrelaxable, uncarriable region declaration
Repro:         /tmp/rretr18/ session probe, mailbox where 'snicker' is only in SPAM:
                 'snicker'                      wire L1 + L3 'in:anywhere snicker' True
                 'is:unread snicker'            wire 5 probes (L1, L1b x2, L2 x2)
                 'in:unread snicker'            wire [('in:unread snicker', False)]   ONE
                 'in:starred snicker'           wire [('in:starred snicker', False)]  ONE
                 'in:read snicker'              wire [('in:read snicker', False)]     ONE
                 'in:important snicker'         wire [('in:important snicker', False)] ONE
                 'in:nonexistentplace snicker'  wire [('in:nonexistentplace snicker', False)]
                 every one of them: outcome inconclusive, not_tried L0/L1b/L2/L3
                 all `not_applicable`, empty_diagnosis untried_drops ('in','terms'),
                 no affordance
Expected:      `in:unread` and `is:unread` are the same request to Gmail and should reach
               the same rungs. A token that filters within a region is a filter, whatever
               prefix it is written with; only a token that selects the region is a region
               declaration.
Actual:        The whole recovery ladder — decomposition, relaxation and the published
               broadening — is withheld from any query carrying an `in:` token, including
               tokens that name no region and tokens that name nothing at all. This is the
               second edge of R-RETR-036's prefix: the same over-broad reading that misses
               `label:spam` over-fires on `in:unread`.
Required fix:  The same derivation R-RETR-036 needs, from the other side: a per-operator
               fact about what the operator does, not a prefix. As an interim that costs
               nothing and is checkable, hold the location half to a published vocabulary —
               `NARROWING_MAILBOX_LOCATIONS` and `WIDENING_MAILBOX_OPERATORS` already exist
               as one, and unlike a per-operator list they are a *value* vocabulary of
               Gmail's regions, so `in:unread` falls out of it correctly and `in:snoozed`
               is added by one line when Gmail names it. Note that this trades R-RETR-036's
               open-endedness for correctness on today's values and the trade must be made
               deliberately: whichever way, the docstring must stop claiming both.
               Independently: `not_tried` reporting `not_applicable` for L2 and L3 when the
               real reason is "the region is not relaxable" and "the query declared a
               region" understates OD-2's "routes not tried" report. The third
               `EmptyDiagnosisStatus` member the implementer names (WS-10) is where that
               vocabulary belongs.
```
```
ID:            R-RETR-042
Severity:      LOW
Reachability:  REACHABLE as a coverage defect today. No row of the current manifest is
               wrong — I re-ran all sixteen and confirmed them — but two guards the harness
               claims are narrower than the claim.
Rubric:        Work order Part 4; AL §7.2 (a test that passes for the wrong reason); the
               harness's own docstring, which names both traps.
Location:      tests/fixtures/replants.py, _environment — PYTHONPATH is
                 `scratch/server/src:scratch`, with no `scratch/harness/src`;
               tests/fixtures/replants.py, assert_imports_resolve_into_the_scratch_tree —
                 asserts `mailweave` and `tests`, not `mailweave_harness`;
               tests/test_replants_round18.py,
                 test_every_behaviour_round_18_changed_fails_a_test_when_it_is_removed —
                 calls `run_replants(scratch)` with `whole_suite=False`, which is the branch
                 that skips `assert_the_scratch_tree_is_green`;
               and the module docstring, which says the marked tests are "deselected from
                 the default run" while `-m "not network"` collects and runs them (§13 of
                 the report is right and the docstring is wrong)
Repro:         In the exact environment `_environment` builds:
                 mailweave         -> /tmp/rretr18/tree/server/src/mailweave/__init__.py
                 tests             -> /tmp/rretr18/tree/tests/__init__.py
                 mailweave_harness -> /root/mailweave/harness/src/mailweave_harness/__init__.py
               Five test modules import `mailweave_harness` (test_claims_round14,
               test_auth_and_config, test_harness_pinning, test_preflight_probes,
               test_preflight_runner_end_to_end), so the whole-suite deselected pass runs
               them against the working tree.
               And: `pytest -m "not network" --collect-only -q | grep replant` -> 4 tests.
Expected:      "Both packages resolve inside the scratch copy and not into the working
               tree" should cover every importable package the suite uses; and the runner
               that ships in CI should have the greenness precondition its own docstring
               says exists for it ("a broken *copy* makes every plant report CAUGHT for
               free … and it caught me").
Actual:        The third package resolves into the working tree, so a manifest entry
               planted into `harness/src` would report MISSED for free. And the CI runner
               has no positive evidence the copy it planted into was sound. I tried two
               realistic copy breakages (omitting `docs/`, omitting `conftest.py`) and
               neither made it vacuous, so this is a missing guard rather than a live
               vacuity — which is exactly the state round 17's own unasserted fixes were in.
Required fix:  Add `scratch/harness/src` to `_environment`'s PYTHONPATH and
               `mailweave_harness` to both halves of the import assertion. Call
               `assert_the_scratch_tree_is_green` unconditionally in `run_replants`, or run
               one known-green control plant per pass. Correct the module docstring.
```

**Carried forward, open, and blocking in the round they return to (§5a):**

* **R-RETR-029** (MEDIUM) — the content predicate. Materially narrowed and I confirm the
  measurement independently (967,113 code points, 0 content-bearing). The
  `Default_Ignorable_Code_Point` residue is live: `mailweave_search('ㅤ')` plans
  `[('ᅠ', False), ('in:anywhere ᅠ', True)]`. Severity decided at **R-GMAIL**; fix at **WS-10**.
* **R-RETR-030** (MEDIUM) — `enforced` as the union over routes. Narrowed from three
  reproductions to two, both live (`label:projecta vorpal`, `from:a@parts.example vorpal`). The
  refusal is correct and I verified it by implementing the fix. **WS-16 / amendment A1** for the
  seam; the contract alternative is the orchestrator's.
* **R-RETR-034** — superseded by R-RETR-037 at higher severity. Do not close it separately.

**Closed, verified by execution:** R-RETR-026 (for every `in:` spelling; the residues are refiled as
035/036/037), R-RETR-027, R-RETR-028, R-RETR-031, R-RETR-033. R-RETR-032 is **partially** closed —
see R-RETR-040.

---

## Recommendations, per criterion

**I mark nothing.** Every recommendation is scoped and I name what my evidence does not cover.

* **LEX-01 · Message-level search is the first rung — RECOMMEND PASS, scoped** (round 17: PASS
  scoped; I confirm on this round's code). Evidence: 1,500 randomised envelopes, `call_log[0]` is
  `messages.list` with a non-empty `q` in **1,500 of 1,500**; plus 2,200 preservation trials and
  1,200 recall trials with no exception. `hit_threads` still derives `H`'s hit half only from
  `MESSAGES_LIST` origins. *Scope:* all traces are through `MockTransport`; "no code path derives the
  primary hit set from a thread-level listing" is a code-read claim I confirm by inspection but
  cannot execute against Gmail. **R-ARCH / R-GMAIL.**
* **LEX-02 · Operator-parse fidelity and coverage reporting — RECOMMEND NOT YET, one criterion-level
  reason.** The positive evidence is strong and better than last round: over 1,500 randomised
  envelopes, **0** parsed constraints neither enforced nor declared dropped, and **0** constraints
  reported enforced that no executed `q` carried whole — measured against my own tokeniser and my own
  "carried whole" rule, not `carriage_token`. `constraint_coverage` is present and honest on every
  disclosed row in 13,581 rows. The blocker is the acceptance's "cases where a signal was silently
  dropped: **0**": R-RETR-035 drops a *region* declaration into `unparsed_syntax` and then acts on
  its absence, and R-RETR-030's union still reports `enforced ('from','terms')` at
  `term_coverage 1.0` over a disclosure containing a row from a route that carried neither.
* **LEX-03 · Multi-constraint decomposition — RECOMMEND NOT YET.** The mechanism is right and the
  scope is now carried onto every unit in both polarities (verified across 33k+ planned probes). Two
  reasons not to mark: the recall bar is `[UNSET — register at G0]` against Baseline D, and
  R-RETR-041 suppresses decomposition entirely for any query carrying an `in:` token.
* **LEX-04 · Exact-signal stop — RECOMMEND NOT YET, unchanged.** The stop fires correctly and L0's
  `enforced` is now honest (Part 3, verified: `PO-2026-0041 zephyr` reports `enforced ()`,
  `term_coverage 0.0`). The cost bar needs network-level counts. **WS-16 / R-PERF.**
* **EV-02 · Position-independent evidence recall — RECOMMEND NOT YET.** No position sweep exists;
  needs a seeded corpus. **WS-16.**
* **EV-04 · Zero false "not found" on answerable cases — RECOMMEND NOT YET.** 1,200 recall trials
  produced **0** cases where a present, matching thread was not returned under `answered` or
  `inconclusive`. But the paired hallucinated-found rate is the other half of the criterion, and
  R-RETR-035/036/037 are that half: 13 matched rows in 1,800 trials that the query excluded.
* **EV-05 · Issue #296 signature non-reproducible — RECOMMEND NOT YET.** The thread-map floor holds
  in every trial and now says where each member lives, which is a real strengthening. Clause 2 needs
  the live signature. **R-GMAIL.**
* **EV-06 · Recall against the full-dump ceiling — RECOMMEND NOT YET.** Baseline B does not exist.
  **WS-16.**
* **ROUTE-01 · No bare empty response — RECOMMEND DO NOT RESTORE.** This is my decision and I make
  it against the round's work, not around it. The regression that caused the revert is closed; the
  report class is genuinely improved; and I executed the offers rather than reading them. But the
  acceptance says *100% of zero-evidence responses carry … affordances*, and on my sets **729 of 822
  (88.7%) carry none**, including responses that name two untried drops and four untried rungs. One
  of the four offer kinds the round added does not reach Gmail when executed. R-RETR-032 named the
  ordinary class (`borogrove`, `from:nobody@… borogrove`) as well as the report class, and only the
  report class moved. **If R-RETR-040 is closed — every zero-evidence response with a concrete
  untried call carries an executable offer, and every minted offer is executed by its test — I would
  expect to recommend PASS at full scope next round, and this is the only criterion that is one
  finding away.** If instead the orchestrator decides MailWeave must never offer to cross a stated
  boundary, the acceptance itself needs amending, and that is an owner-adjacent question, not mine.
* **ROUTE-02 · Mis-parse recovery — RECOMMEND NOT YET.** The recovery-rate bar is `[UNSET]`, and
  R-RETR-041 makes a mistyped location (`in:inbx zephyr`) a case with **no** recovery route at all,
  which is the criterion's own family.
* **ROUTE-03 · Relaxation is systematic and enumerable — RECOMMEND PASS, scoped.** Verified: drops
  are one at a time in `plannable_drops` order, reproducible across two independent parses of the
  same input, each logged with the constraint dropped and the resulting count, and the log line
  names A.7 L2 and ROUTE-03. The round's change — the region is not relaxable — is *within* the
  criterion, because it is documented, ordered and reported in `untried_drops`. *Scope:* the two
  things my evidence does not cover are that the drop order is the one AD A.7 L2 documents (an
  R-ARCH code read, which I did not repeat) and that a relaxed `q` behaves this way at Gmail.
  *Second scope note:* an **exclusion** is now relaxable (`-"phrase"` dropped at L2, declared). That
  is inside ROUTE-03 as written; whether it should be is a policy question for the orchestrator.
* **ROUTE-04 · Empty-result diagnosis — RECOMMEND NOT YET, but the correctness half is met.** On my
  six constructed single-cause cases the report names the restoring constraint correctly **6/6**,
  with `status: complete`, `tried` complete and an affordance. Where the region is the cause,
  `status: incomplete`, `untried_drops` complete and `outcome: inconclusive` — OD-2's shape, correct.
  Not yet, for two reasons: the incomplete-diagnosis ceiling is `[UNSET — register at G0]`, and
  `not_tried` reports `not_applicable` for rungs that were *declined by policy* rather than
  inapplicable (R-RETR-041's second half), which understates what OD-2 requires a negative result to
  report.

---

## Verdict on each of the owner's five requirements

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 1 | Machine-readable, user-visible mailbox provenance on every `MessageRow`, derived from actual labels | **PARTIALLY MET** | Derivation is structural and unfalsifiable (computed fields + `extra="forbid"`, four refused forgeries); on every row at every depth including stubs; on the wire. But the stub case is undefended (X2: 2,271 green) and the "not observed" state has no producer, so an unstated label set is reported as `outside_the_default_mailbox: false`. R-RETR-038, R-RETR-039. |
| 2 | `-in:spam` never searches spam; explicit scope preserved across every probe | **PARTIALLY MET** | 0 boundary crossings for every documented `in:` spelling across 330 scoped queries / 1,516 probes, and scope carried through decomposition, relaxation, many-scope and contradictory-scope shapes; a scope inside a phrase correctly stays a phrase. 60 crossings remain, in exactly three spellings: grouped (30), `label:` (20), fullwidth (10). R-RETR-035, R-RETR-036, R-RETR-037. |
| 3 | L3 `in:anywhere` broadening kept, only when the user specified no scope | **PARTIALLY MET** | Kept and correctly gated for every spelling the predicate sees, with the admitted rows now stating their region. Five spellings of a declared scope still reach it (035/036/037); and seven `in:` values that name no region wrongly suppress it *and* the rest of the ladder (R-RETR-041). |
| 4 | Negated phrases remain exclusions | **MET** | 16 adversarial shapes — colons, unicode, uppercase unicode, multiple negations, negated beside positive, an operator spelling inside a negated phrase, empty and whitespace phrases — all exclusions, `qualifying_phrases` empty for every one, the inverse plant CAUGHT by two tests. |
| 5 | Regression and mutation tests failing on replant, including an operator-family sweep | **PARTIALLY MET** | 16/16 replants independently reproduced CAUGHT by their named test **and** by the whole suite with that test deselected, with import discipline verified; seven emptied-oracle plants all caught; one surviving `f(x)==f(x)` assertion, non-vacuous because of its written-out oracles; zero others in the suite. But: two round-18 behaviours are outside the manifest and undefended (R-RETR-038); the sweep is a genuine family sweep for a **filtering** operator and a prefix sweep for a **scope-declaring** one — a new `OperatorKind.LOCATION` operator is dropped, relaxed away and widened out of with the suite green (R-RETR-036); and two harness guards are narrower than claimed (R-RETR-042). |

---

## Overall verdict

**DO NOT CLOSE ROUND 18 YET — one HIGH class remains reachable, and it is the round's own class.**

This is the best-executed round this project has had. The re-derived asymmetry rule is stated once
and read everywhere; `enforced` is derived once and every rung inherits it; the negated phrase is
fixed in every spelling I could invent; the replant manifest is real and I reproduced all sixteen
entries both ways; the implementer found two vacuous tests in its own work and said so with the
evidence; it implemented a reviewer's required fix, found it wrong, and reported *why* instead of
either accepting or ignoring it; and evidence preservation is clean across 2,200 randomised trials
with 267 withheld records exercised.

And the round's own central claim is false in the way this project keeps being false. A9-A2 says the
clause is derived from **what an operator does** so that it holds for scope operators nobody has
added yet. It is derived from **how an operator is spelled** — one prefix. I added a
`OperatorKind.LOCATION` operator the way an implementer would, and the suite stayed green while the
new scope operator was dropped from every decomposition unit, relaxed away at L2, and widened out of
at L3. The reachable form of that is `-label:spam`, which reads spam today, and the parser's own
grouping and normalisation seams give two more spellings that do the same. `-in:spam` no longer
searches spam. `-(in:spam)`, `-label:spam` and `-ＩＮ：ＳＰＡＭ` still do.

Two of the three have cheap conservative fixes that cost recall rather than boundary-crossing, and I
have named them. The third — a structural "selects a region / filters within one" fact — is a real
piece of design and belongs with WS-10 and R-GMAIL, not in a docstring. What must not survive this
round is the *claim* to have derived it, because the next round will build on that sentence.

**Rubric:** unchanged at 6 PASS / 0 FAIL / 0 BLOCKER / 107 NOT TESTED, 11 transitions. I marked
nothing, restored nothing, and edited neither `FINDINGS_LEDGER.md` nor `RUBRIC_TRANSITIONS.md`.

---

## Established by execution

* **All five gates clean and stable**, twice, before and after all probing: 2,271 tests, independently
  re-counted by summing `--collect-only`; the rubric unchanged; the tree byte-identical to the copy I
  took before starting.
* **Provenance is derived, not accepted.** Four attempted forgeries refused by the type; `regions`
  has no setter; the same message found three ways reports one provenance; 13,581 rows across 2,200
  trials, **0** disagreements with a written-out oracle over the planted labels.
* **`-in:spam` no longer searches spam** for every spelling Gmail documents, in both polarities, at
  every rung, through decomposition, relaxation, multiple scopes and contradictory scopes: 0 of 1,516
  probes over 330 scoped queries for the plain spellings.
* **A negated phrase is an exclusion** in 16 adversarial shapes, and the inverse plant is caught.
* **All 16 replants CAUGHT twice over**, in my own scratch tree, with `mailweave.__file__` and
  `tests.__file__` asserted inside it and asserted not to be `/root/mailweave`.
* **Seven emptied-oracle plants all caught**, including the derivations the round's own tests read.
* **The vacuity sweep**: zero `assert f(x) == f(x)` assertions with the same call on both sides in
  the whole suite; forty derivation-vs-attribute candidates, of which one is the literal shape and it
  carries four written-out oracles beside it. Both tests the implementer reported catching are
  genuinely repaired.
* **Evidence preservation**: 2,200 trials, 0 violations of `H ⊆ disclosed ∪ withheld`, 0 overlaps,
  0 phantom ids, 267 withheld records.
* **Recall**: 1,200 trials, 1,450 threads my oracle says must be reached, 0 missed under `answered`
  or `inconclusive`.
* **LEX-01**: 1,500/1,500 first calls are `messages.list`. **LEX-02**: 0 silent drops, 0 enforced
  constraints no executed `q` carried, by my own oracle. **ROUTE-03**: ordered, one at a time,
  logged, reproducible. **ROUTE-04**: 6/6 restoring constraints named correctly.
* **R-RETR-030's refusal is correct**: `threads` is built from the admission delta, so the required
  fix is not computable here, and implementing it fails exactly the two tests named.
* **A filtering operator added to `OperatorName` is fully covered by the family sweep** without
  editing a predicate.
* **The five new defects**, each with a reproduction: the grouped scope (30 probes), the `label:`
  region (20 probes, 12 of 13 wrong matched rows in my trials), the fullwidth region (10 probes), the
  undefended stub provenance (2,271 green), and the 88.7% of zero-evidence responses with no
  affordance.

## False on execution

* **"The asymmetry clause is re-derived from what an operator does … so it holds for scope operators
  nobody has added yet"** (A9-A2, and `declares_the_search_region`'s docstring). A
  `OperatorKind.LOCATION` operator added and registered exactly as an implementer would is treated as
  a filter — dropped from every unit, relaxed away, widened out of — with all 2,274 tests green. The
  predicate is `startswith("in:")`.
* **"No predicate added this round tests for an operator value … the only vocabulary it consults is
  `MAILBOX_LOCATION_PREFIX`"** — literally true, and it is the sentence that hides the defect above.
  One prefix is a vocabulary of one.
* **"`-in:spam` never searches spam"** — true for every documented `in:` spelling and false for
  `-(in:spam)`, `(-in:spam)`, `{-in:spam}`, `-(in:spam OR in:trash)`, `-label:spam`, `-label:trash`
  and `-ＩＮ：ＳＰＡＭ`, each of which sends `in:anywhere` with `includeSpamTrash=true` and discloses
  the excluded SPAM and TRASH rows as `role: matched` under `outcome: answered`.
* **"`observed` is a third state, not a flag"** and **"a row the ledger placed but no label-bearing
  observation touched reports `observed: false`"** — `MailboxProvenance.unobserved()` has no product
  caller; `observed` is a constant `true`; a `threads.get` that states no `labelIds` produces
  `outside_the_default_mailbox: false` over a TRASH message.
* **"Every row gets it — matched, stub and thread-map alike"** — true of the code and defended by
  nothing: removing provenance from every non-hit row leaves 2,271 tests green, and stubs are the
  808-row case the field was argued for.
* **"Every affordance the report class mints is executed and asserted to reach Gmail"** — three of
  four kinds are executed; the fourth (`{"query": "in:anywhere", "terms": []}`) is asserted by shape,
  and executing it reaches no rung at all.
* **"Both packages resolve inside the scratch copy and not into the working tree"** — true of the two
  named; `mailweave_harness` resolves into `/root/mailweave/harness/src` in the planted subprocess.
* **`tests/test_replants_round18.py`'s docstring, "marked `replant` and deselected from the default
  run"** — `-m "not network"` collects and runs all four. (Report §13 states this correctly; the
  docstring contradicts it.)

## Not establishable here at all

* **Gmail's system label vocabulary**, without which `label:spam` cannot be told from a user's own
  label. This decides whether R-RETR-036's reachable half is a conservative-rule fix or a design
  question. **R-GMAIL / A.6.**
* **Whether Gmail accepts `-(in:spam)` and `-(in:spam OR in:trash)` as scope exclusions** — I show
  MailWeave discards them; whether Gmail would have honoured them decides whether R-RETR-035 is also
  a recall defect on top of a boundary crossing. **R-GMAIL.**
* **Whether Gmail treats U+3164 / U+1160 as content**, which decides R-RETR-029's severity.
  **R-GMAIL / PF-20.**
* **Whether `threads.get` with `format=metadata` ever omits `labelIds` for a labelled message**,
  which decides whether R-RETR-039 is a schema tidy or a live wrong disclosure. **R-GMAIL.**
* **Whether the query normalisation policy makes `ＩＮ：ＳＰＡＭ` an operator or a term** — either
  answer closes R-RETR-037, and choosing it is a product decision. **A.6 / WS-10.**
* **R-RETR-030's honest `enforced`**, which needs the seam to hand back a page's ids. **WS-16 /
  amendment A1.**
* **Every rate the rubric asks for**: LEX-03's and ROUTE-02's recall bars, EV-02's position sweep,
  EV-04's paired hallucinated-found rate, EV-06's Baseline B, ROUTE-04's incomplete-diagnosis
  ceiling, LEX-04's cost bar. All `[UNSET — register at G0]` or needing a seeded corpus, Baselines
  B/D, holdout seeds and a network-level counting proxy. **Every number in this review is on sets I
  constructed and is offered as nothing else. WS-16 / R-PERF.**
* **A ceiling on all of the above, mine and the implementer's**: the double evaluates 13 of 21
  `OperatorName` members. Every end-to-end statement in this round is bounded by that, and by the
  absence of a live account. **R-GMAIL / WS-16.**
