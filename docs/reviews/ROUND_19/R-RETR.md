# ROUND 19 — R-RETR review (the registry answers; three punctuation spellings still do not reach it)

**Reviewer:** R-RETR, independent instance, 2026-09-04. Sole gating reviewer for round 19.
Verified by execution per `AGENT_LOOP.md` §4/§5/§5a, and classified for urgency per **OD-6**.
**Source, tests and docs untouched** — every probe ran from `/tmp/rretr19/*.py` against the real
tree; every registration and every plant ran in a scratch copy under `/tmp/rretr19/t_*`, each a
**full** copy including `docs/`, with `PYTHONPATH` set and `mailweave.__file__`,
`mailweave_harness.__file__` **and** `tests.__file__` asserted to resolve inside it and asserted
*not* to resolve into `/root/mailweave`. Probe files are named against every number below.

Nothing in `/tmp/rretr15`, `/tmp/rretr16`, `/tmp/rretr17` or `/tmp/rretr18` was used to build any
of my sets. My vocabulary is invented (`zorbal quintle mirephant tarnix dovetail-7714 sable
zzalpha zzbeta`), my senders are `.example` / `.invalid`, my mailboxes, spellings, oracles and
seeds are mine, and every oracle in this review is written out in the probe file rather than
borrowed from a product predicate — my own NFKC fold, my own strip of the product's own declared
grouping punctuation, my own list of the three region-selecting operator names and the three
widening spellings. Where I re-ran a prior instance's tree I say so and label it a reference
measurement. I registered a **new** operator pair (`vault:` REGION, and the filtering control) so
that nothing here is measured on the implementer's own `mailbox:` / `priority:`.

---

## Environment

| Gate | Result (run twice, before and after all probing, identical both times) |
|---|---|
| `ruff check .` | All checks passed |
| `ruff format --check .` | 159 files already formatted |
| `mypy` (strict) | Success, 133 source files |
| `python -m tools.guards` | 7 guards clean (forbidden-import, generative-client, gmail-endpoint, ground-truth-isolation, scope-literal, unaudited-disk-write, unwrapped-http-client) |
| `pytest -q -m "not network"` | **2,290 passed** in 76.5 s; re-counted independently via `--collect-only -q` summed per file = **2,290** |
| `pytest -m replant` | **4 passed**, 2,286 deselected, 51.8 s — the four marked tests **are** in the default gate, and the corrected module docstring now says so |
| `tools/rubric_status.py --check` | criteria 113; **6 PASS / 0 FAIL / 0 BLOCKER / 107 NOT TESTED**, 11 transitions — unchanged, as the work order requires |

`mailweave.__file__` → `/root/mailweave/server/src/mailweave/__init__.py`. No file under `server/`,
`tests/`, `tools/` or `harness/` has a modification time inside my review window: the newest is
`server/src/mailweave/constants.py` at 13:40 UTC, inside the implementer's own window, and my review
began at 15:43. Exactly two files in the tree are newer than the implementer's window and neither is
code: `docs/OWNER_DECISIONS.md` at 15:44, which is the owner's OD-6 entry landing as this review
started, and this file. **I wrote nothing else.**

**Scratch-tree discipline.** Every scratch tree is a full `copytree` of `/root/mailweave` minus
`.venv`, `.git`, `__pycache__`, `.*_cache` and `.hypothesis` — so `docs/` and `tests/conftest.py`
are present and asserted present, since `tools/rubric_status.py` reads `docs/RELEASE_RUBRIC.md` and
a copy without it fails the whole suite for a reason no plant caused. Every registration asserts its
anchor matched exactly once before writing. Every plant asserts the file's content hash changed.

## Reachability rule I applied (§5a), and urgency under OD-6

Unchanged in substance from rounds 15–18. **A defect triggered by an ordinary query string reaching
`LadderRunner.run` + `assemble` is REACHABLE.** Every finding below is reachable today.

OD-6 adds a second axis and I keep it strictly separate from severity. **Blocks round 20** means:
this defect is a *critical correctness or safety defect* in OD-6's sense — a plausible query, typed
by a person or composed by a calling agent, produces a wrong or unsafe result that the response does
not itself declare. **Rides along** means the finding is real and stays open, and fixing it is not
worth another audit-only round. I have separated the two deliberately and I have not softened a
severity to make a schedule work: two of my five findings are MEDIUM and none of them blocks.

---

# Part 0 — the central question, adjudicated

## 0.1 What actually happens when a new REGION operator is registered

I registered `vault:` — a scope-declaring operator nobody has added — in stages, each stage in its
own full scratch copy, and ran the suite at each stage. `/tmp/rretr19/a1_registration_ladder.py`,
`/tmp/rretr19/a3_minimal.py`.

| registered | suite |
|---|---|
| `OperatorName.VAULT` + `KIND_BY_OPERATOR[VAULT] = REGION` (product only) | **rc=2, 3 collection errors** — `KeyError: 'vault'` in `tests/test_lexical_ladder.py`, `tests/test_region_and_provenance_round18.py`, `tests/test_region_kind_round19.py` |
| + `FIDELITY_TABLE` entry and its count | **rc=2**, the same three collection errors |
| + `OPERATOR_FAMILY_VALUES["vault"] = "archive"` | **2,289 passed**, 4 deselected |
| + the double's `IMPLEMENTED_OPERATORS` | **2,289 passed**, 4 deselected |
| enum + kind + family values, **without** the fidelity entry | **1 failure**: `test_every_parsed_operator_reaches_the_executed_query[vault]` |

So the minimal edit set to register a new operator is: two product edits (`OperatorName`,
`KIND_BY_OPERATOR`) and three test-side edits (`FIDELITY_TABLE` + its count,
`OPERATOR_FAMILY_VALUES`). **The literal exit criterion — "a newly registered scope-declaring
operator is covered without editing a test" — is not met.** The orchestrator's reading is exact:
without a sample value, collection dies with `KeyError: 'vault'` at
`POSITIVE_REGION_FRAGMENTS`'s `OPERATOR_FAMILY_VALUES[name.value]`.

## 0.2 Is that an enumeration in disguise? **No — and here is the discriminating test**

The question is not "does a human have to type something" but "can a new REGION operator end up
*silently uncovered*". That is what round 18's defect was: `OperatorKind.LOCATION` existed, the
operator was registered against it, and **2,274 tests stayed green** while every probe dropped it.
Silence is the whole character of the defect.

Five things, each executed:

1. **The classification decision is in product code.** `KIND_BY_OPERATOR` is what decides whether an
   operator declares the region, it is total over `OperatorName`, and the sweep population
   `REGION_DECLARING_OPERATORS` is *derived from it* rather than written out. Nothing in
   `tests/` says what `vault:` does.
2. **What the test-side dict supplies is a datum no code here can know.** `vault:` takes `archive`
   and not `high`; the fidelity table supplies the same class of datum (what does `vault:archive`
   parse to?) and so does the double's operator semantics. These are registration sites, not
   oracles about behaviour — the distinction the implementer draws, and it survives inspection.
3. **The failure mode is loud and immediate.** Three collection errors and a named totality test
   (`test_the_operator_family_vocabulary_covers_every_operator_this_parser_knows`), not a green run
   over an uncovered operator. That is the *opposite* of round 18.
4. **A degenerate value cannot empty the sweep.** I tried to weaken it from the test side:
   `OPERATOR_FAMILY_VALUES["vault"] = " "` → **3 named failures**
   (`test_every_probe_the_ladder_composes_searches_the_region_the_query_named`,
   `test_a_query_that_named_a_region_is_never_widened_out_of_it`,
   `test_a_broadening_probe_does_not_carry_a_narrower_scope_than_the_one_it_widens_to`);
   `= '""'` → **3 collection errors**. The datum fails closed in both directions.
5. **And the coverage is real, not merely green.** §0.3.

**Verdict on `OPERATOR_FAMILY_VALUES`: it is a registration site, not an enumeration.** The exit
criterion as written was the wrong criterion — a new operator's *value* is data only a human has,
exactly as its *name* is. The criterion I would put in its place, and which **is** met:
*registering a new REGION operator in the product must either cover it or fail loudly; it must never
leave the suite green and the operator uncovered.*

One residue worth naming rather than filing: the dict is transitively a *population*
(`POSITIVE_REGION_FRAGMENTS` is built from it). What is unedited is the population's **rule**; what
is supplied is the **datum the rule needs**. That is a real distinction and it is the one the
verdict rests on, so I state it rather than let it be read as a technicality.

## 0.3 Does the safety property actually hold? I registered `vault:` and tried to make it leak

`/tmp/rretr19/a2_vault_safety.py`. Full copy, all three packages asserted resolving inside it and
none into the working tree, `vault:` registered `REGION` everywhere an operator is registered
(including the double's *semantics*, so `vault:spam` matches a SPAM-labelled message — otherwise an
end-to-end statement about it would be vacuous).

```
declares_the_search_region('vault:spam')      True     ('-vault:spam')        True
                          ('(vault:spam)')    True     ('-(vault:spam)')      False *
                          ('(-vault:spam)')   True     ('-{vault:spam}')      False *
                          ('{vault:spam}')    True     ('-[vault:spam]')      False
                          ('VAULT:SPAM')      True     ('-VAULT:SPAM')        True
                          ('vault:spam,')     True     ('-vault:spam,')       True
                          ('vault:archive')   True     ('-vault:archive')     True
                          ('[vault:spam]')    True     ('-ｖａｕｌｔ：ｓｐａｍ')  True
* rescued by `tokenise`'s single-operator group re-emission; see the end-to-end row below
```

Plan layer, 60 scoped queries × 6 bodies: **30 violations, every one of them from
`-[vault:spam]`.** End to end, against a mailbox holding the marker in the inbox, in spam and in
trash and a second word planted only outside the default mailbox:

```
-vault:spam quintle      flag=False anywhere=False  rows outside default: []      q=['-vault:spam quintle']
-(vault:spam) quintle    flag=False anywhere=False  []                             q=['-vault:spam quintle']
(-vault:spam) quintle    flag=False anywhere=False  []                             q=['-vault:spam quintle']
-{vault:spam} quintle    flag=False anywhere=False  []                             q=['-vault:spam quintle']
-VAULT:SPAM quintle      flag=False anywhere=False  []                             q=['-vault:SPAM quintle']
-vault:spam, quintle     flag=False anywhere=False  []                             q=['-vault:spam, quintle']
vault:spam quintle       flag=False anywhere=False  []                             q=['vault:spam quintle']
vault:inbox quintle      flag=False anywhere=False  []                             q=['vault:inbox quintle']
-[vault:spam] quintle    flag=True  anywhere=True   LEAK m-sp(spam), m-tr(trash)   q=['quintle','in:anywhere quintle']
```

**The safety property holds, and it holds for a reason rather than by luck.** A brand-new
region-selecting operator is read as a region in both polarities, carried by every probe of every
rung, never relaxed away, never widened out of, with `includeSpamTrash` never set — with **no
predicate edited and no test oracle edited**. That is A9-A2 satisfied, and it is what round 18 did
not have. The one residue is `-[vault:spam]`, and it is not a property of `vault:` at all: it is
shared, identically, with `in:`, `label:` and `category:`. It is **R-RETR-043** below.

It also stops crashing *and* does the work: the control half is intact. A newly registered
**filtering** operator is still dropped by L2, still gets a decomposition unit of its own, and its
query still reaches the published broadening — so "make everything a region" would not pass here.

---

# Part A — the owner's five requirements, each attacked

## 1. Machine-readable provenance on every `MessageRow`, from actual labels — **MET**

Round 18: partially met, with R-RETR-038 (stub provenance undefended) and R-RETR-039 (`observed`
had no producer and read as a negative). Both are closed and both are now defended.

**`unobserved` is producible and never reads as a negative.** `/tmp/rretr19/c1_provenance.py`, with
a transport that removes `labelIds` from every `threads.get` message:

```
m-ct role=matched observed=False labels=() regions=None outside=None
m-in role=matched observed=False labels=() regions=None outside=None
m-lb role=matched observed=False labels=() regions=None outside=None
```

and on the wire, `{"observed": false, "labels": [], "regions": null,
"outside_the_default_mailbox": null}`. **`None` is not `False`, and it survives serialisation.**

**A stated empty list is a different fact and reads as one.** With `labelIds: []` instead of
absent: `observed=True regions=() outside=False`. **And the distinction is per message, not per
response** — with `labelIds` removed for `m-in` only, `m-in` reports `observed=False regions=None`
while `m-ct` and `m-lb` report `observed=True regions=()`. That is the property that makes the
field trustworthy at all.

**Stubs carry their own labels.** A thread whose matched member is in the inbox and whose two stub
members are in TRASH and SPAM:

```
k-1 role=matched labels=('INBOX',) regions=()        outside=False
k-2 role=stub    labels=('TRASH',) regions=('trash',) outside=True
k-3 role=stub    labels=('SPAM',)  regions=('spam',)  outside=True
```

and all three carry `mailbox` on the wire.

**I could not make a provenance disagree with its labels.** Six forgeries, all refused:

```
{"observed": true,  "labels": [],        "regions": ["spam"]}                     REFUSED
{"observed": true,  "labels": ["INBOX"], "outside_the_default_mailbox": true}     REFUSED
{"observed": false, "labels": ["SPAM"]}                                           REFUSED (validator)
{"observed": false, "regions": []}                                                REFUSED
{"observed": false, "outside_the_default_mailbox": false}                         REFUSED
{"observed": true,  "labels": ["SPAM"],  "regions": []}                           REFUSED
object.__setattr__(p, "regions", ("trash",))   AttributeError: property has no setter
object.__setattr__(p, "labels", ("INBOX",))    mutates `labels` — and `regions` recomputes to (),
                                               so the two still cannot disagree
```

`MessageRow.mailbox` is a **required** field (`is_required() is True`), and a row payload without it
is refused. Over **900 randomised trials** (`/tmp/rretr19/h1_recall.py`) with 25 % of messages
having their `labelIds` stripped: **0 rows without provenance, 0 rows whose derived fields
contradicted `observed`, 1,229 rows legitimately reporting `observed: false`.**

*Scope notes, not findings.* `WithheldRecord` carries `id`, `thread_id`, `cap`, `why`, `affordance`
and **no** provenance — OD-5 point 1 binds `MessageRow`, and a withheld id was never label-observed,
so this is correct today; it becomes a question the first time a cap withholds an id whose labels
*were* observed. `CollapsedRun` still has no product producer. The dumped row is still not
re-validatable (`extra="forbid"` refuses the two computed fields on the way back in); nothing in
the product round-trips an envelope.

## 2. `-in:spam` never searches spam; an explicit scope is preserved across every probe — **PARTIALLY MET**

This is where the round's one real defect lives, and it is much smaller than round 18's.

**The sweep.** 20 spellings × 7 region operator/value pairs × 7 bodies = **980 scoped queries,
3,404 planned probes** (`/tmp/rretr19/b3_table.py`). My oracle is the product's *own declared*
normalisation applied consistently: NFKC, then its own `QUERY_GROUPING_PUNCTUATION` stripped from
both ends, in either order around the negation prefix.

```
spelling     queries  probes  region fragments dropped  widened out  includeSpamTrash
bare, -bare, (x), -(x), (-x), {x}, -{x}, {-x}, x,, -x,, -x;, UPPER, -UPPER
                  49     154        0            0            0        (each, 13 spellings)
[x]               49     154      154            0            0
[-x]              49     154      154            0            0
fullwidth         49     247      247            0            0
-fullwidth        49     238      238            0            0
-[x]              49     203      203           49           49    <-- LEAK
-,x               49     203      203           49           49    <-- LEAK
-(x               49     203      203           49           49    <-- LEAK
TOTAL            980    3404     1402          147          147
scope-free queries still broadened: 7/7   (A9-A3's published step survives)
```

**Seventeen of twenty spellings are clean**, including every documented `in:` spelling in both
polarities, both nestings of parentheses and braces, the trailing comma and semicolon, uppercase,
`label:`-named, `category:`-named and **both fullwidth forms**. Round 18's `-(in:spam)`,
`(-in:spam)`, `{-in:spam}`, `-label:spam` and `-ＩＮ：ＳＰＡＭ` are all closed, verified end to end.

**Three spellings leak**, and they share one root cause: a grouping or separating character sitting
*between* the negation prefix and the operator. End to end, over a mailbox with a word planted only
outside the default mailbox (`/tmp/rretr19/b2_e2e_leak.py`):

```
-[in:spam] quintle        flag=True anywhere=True  rows m-sp(spam), m-tr(trash) role=matched
-(in:spam quintle         flag=True anywhere=True  rows m-sp(spam), m-tr(trash) role=matched
-,in:spam quintle         flag=True anywhere=True  rows m-sp(spam), m-tr(trash) role=matched
-[label:spam] quintle     flag=True anywhere=True  rows m-sp(spam), m-tr(trash) role=matched
-[category:updates] quintle flag=True anywhere=True rows m-sp(spam), m-tr(trash) role=matched
-[in:trash] quintle       flag=True anywhere=True  rows m-sp(spam), m-tr(trash) role=matched
```

The response is **not** silent about it: `asked_for.dropped` names `unproven_operator` for the
token, and every returned row states its own region. That is what keeps this MEDIUM rather than
HIGH, and it is the difference between this and R-RETR-026/035, where a *parsed and honoured*
exclusion was abandoned. **R-RETR-043.**

**One more thing this sweep establishes, and it is a positive.** For the `[x]` and fullwidth
spellings, 154 and 247 region fragments are dropped from the composed `q` — and **0** probes widen
and **0** set the flag. The raw-token half of `region_declarations_of` is doing exactly the job it
was added for: the region the parse could not carry still stops the broadening. The cost is
precision (`[in:spam] zorbal` executes `zorbal` in the default mailbox and returns inbox rows), and
it is declared as `unproven_operator`.

**Stub rows from an excluded region.** 900 randomised trials produced **181** disclosed rows from a
region the query excluded — **all of them `role: stub`, `depth: stub`, reason `ThreadMember`; zero
matched**; with **0** probes carrying `includeSpamTrash` and **0** probe `q`s dropping the exclusion
the caller wrote. This is OD-3's reply-chain floor meeting OD-5 point 3: `threads.get` on a thread
L1 matched inside the allowed region returns the whole thread, and the trash member is carried as a
labelled stub rather than silently dropped. The *code* is right. What is wrong is a **claim**:
round 18's `test_a_query_that_excluded_a_region_never_reads_it_and_never_discloses_a_row_from_it`
asserts "no disclosed row — matched **or** stub — comes from a region the caller excluded", which
the code does not guarantee and which passes only because its fixture puts every message in its own
thread. **R-RETR-048.**

## 3. An explicit scope is preserved across every probe, derived from what an operator does — **PARTIALLY MET**

Same evidence, same single defect. Over the 2,594 probes of the seventeen clean spellings, **0**
region fragments were dropped, **0** probes widened, **0** set the flag; over the three leaking
spellings, all three counts are 49. The derivation itself is sound and is genuinely registry-driven:
§0.3's `vault:` registration is the proof, and `RelaxationRung` refuses a region drop at any rank
(ROUTE-03 trace below shows `in:inbox` correctly absent from the drop sequence).

## 4. A negated phrase remains an exclusion — **MET**

`/tmp/rretr19/i1_req45.py`, seven adversarial shapes including a colon-carrying phrase, a fullwidth
phrase, an empty phrase, mixed polarity and a phrase beside a quoted operator value:

```
-"quintle decision notes" zorbal        -> ['-"quintle decision notes" zorbal', 'zorbal',
                                             'in:anywhere -"quintle decision notes" zorbal']
-"Re: quintle notes" zorbal             -> exclusion carried on every probe
-"ｑｕｉｎｔｌｅ ｎｏｔｅｓ" zorbal              -> exclusion carried on every probe
zorbal -"quintle decision notes" -mirephant -> exclusion carried on every probe
subject:"a b" -"quintle decision notes" zorbal -> 7 probes, exclusion never inverted
-"" zorbal                              -> the empty phrase is refused, not searched
```

**No probe of any rung searches *for* a phrase the caller negated, in any shape I could write.**

## 5. L0 uses the corrected `enforced` semantics, derived where `enforced` is computed — **MET**

`constraints_carried_whole` is the single derivation and every rung reads it. I attacked it two
ways. Planting a sixth rung is blocked by an anti-vacuity guard that pins `LADDER` to the five rungs
the architecture names — a legitimate guard, but it means the plant tests the guard rather than the
derivation. So I planted the over-claim into an existing rung instead: replacing `FilteredRung`'s
`enforced=constraints_carried_whole(...)` with `enforced=tuple(c.name for c in parsed.constraints)`
leaves the suite **green** — and that is correct rather than a gap, because L1's `q` is
`parsed.render()`, which carries every constraint whole by construction. I confirmed the two are
extensionally equal over 16 query shapes including an unresolvable date, an invalid calendar date, a
fullwidth operator, a grouped boolean and an unknown operator: **0 queries where L1's `enforced`
differs from the full constraint set.** The defence of this requirement therefore rests on manifest
entries R5 and R6 and on the ladder-wide sweep, both of which I re-ran and both of which are CAUGHT
(§E).

---

# Part B — the `label:` / `category:` → REGION decision and its declared cost

**The cost is real and the implementer measured it honestly. I reproduced it on my own thread-split
mailbox** (`/tmp/rretr19/f1_cost.py`), where the scope is satisfied by one message of a thread and
the term by another, so a message-scoped `q` carrying both matches nothing:

```
query                              recovered?     outcome        units  offer
label:Label_91 zorbal              NOT recovered  inconclusive     1    {'query': 'zorbal'}
category:updates zorbal            NOT recovered  inconclusive     1    {'query': 'zorbal'}
from:ana@team.example zorbal       recovered      answered         2    []      (control)
is:unread zorbal                   recovered      answered         2    []      (control)
has:attachment zorbal              recovered      answered         2    []      (control)
subject:Kickoff zorbal             recovered      answered         2    []      (control)
```

Executing the offered call recovers the thread in both lost cases. Against `/tmp/rretr18/pristine`
— the round-18 tree, used here as a reference measurement of the prior round's product behaviour
and asserted to be the tree the import resolves into — `label:Label_91 project` sent three `q`s
(`label:Label_91 project`, `label:Label_91`, `project`) where this tree sends one. **That is the
whole of the regression, and the response says so: `inconclusive`, `label` among the untried drops,
and the concrete call beside it.**

**Is the conservative direction conservative in every case?** I looked for a case where it is not,
and found none in the query shapes I could construct. Specifically I tested four hypotheses and
falsified all four:

* *the reclassification makes an ordinary listing unanswerable* — **false**. `label:Label_91`,
  `category:updates`, `in:inbox` and `in:sent` alone are still executed and still return rows under
  `answered`; `why_this_q_is_not_a_probe` deliberately judges the **user's own** `q` more
  permissively than a composed one, and that division is documented and correct;
* *`label:X -term` becomes a refused listing* — **false**, it executes;
* *`label:X in:inbox` (two regions, nothing to select) becomes refused* — **false**, it executes;
* *a probe searches a region the caller did not name* — **false**: 0 across 3,404 probes, and 0
  matched rows from an excluded region across 900 randomised trials.

The one place the direction is *not* conservative is R-RETR-043, and there it is inverted in a way
worth naming precisely: **`[in:spam]` is read generously as a region and `-[in:spam]` is not.** The
product takes the generous reading exactly where generosity costs recall and the strict reading
exactly where strictness costs a disclosure. That is the inverse of the principle
`KIND_BY_OPERATOR`'s own comment states.

`category:` deserves one sentence of its own. I agree with the uniform reading and I record the
counter-reading as the implementer did: no `category:` value names a region outside the default
mailbox, so the unrecoverable error is impossible for it, and `ATTRIBUTE` would keep thread-split
recovery for tab-scoped queries. It is one registry line either way and it belongs with the
orchestrator, not with me.

---

# Part C — provenance, in full

Covered under requirement 1. Three additional attacks, all negative:

* **can provenance be made to disagree with labels through the wire?** No — the dumped form carries
  both `labels` and the two derived fields, and the derived fields have no setter and are refused as
  input;
* **can a row reach the wire without provenance?** No — required field, and there are exactly two
  `MessageRow(` constructions in the product, both passing the same value read from that message's
  own `label_ids`;
* **can `observed` be true where nothing was observed?** No — `assemble` calls `unobserved()`
  exactly when `Message.label_ids is None`, and `label_ids` is `None` only for a response that
  carried no `labelIds` at all.

---

# Part D — affordances, I-4 and ROUTE-01

## D.1 What I measured

38 shapes of my own, over a mailbox holding nothing any of them asks for
(`/tmp/rretr19/d1_affordances.py`):

```
zero-evidence responses                 37 / 38 shapes
carrying an affordance                  13   (35.1%)
offers carrying a query, executed       26
offers that reached Gmail               26
offers that reached nothing              0
```

**R-RETR-040's second half is closed and I confirm it by execution: every offer any branch mints
now executes and reaches Gmail.** The `{"query": "in:anywhere", "terms": []}` offer is gone and
nothing replaced it with another shape that reaches no rung. My rate (35.1 %) differs from the
implementer's (52 %) because the shape sets differ; neither number is the criterion.

## D.2 The partition is not a partition — two counter-examples, both with a working call

The implementer replaced the percentage with a property: *a response carries an offer unless there
is no call to make.* That is the right property. **It is currently false**, in two classes.

**Class one — mixed polarity.** A query that names a region positively *and* excludes another gets
nothing, although the call that drops only the positive scope exists, executes, and does not undo
the exclusion:

```
in:inbox -in:spam zzalpha     untried_drops ['in','terms']   affordances []   plannable_drops ()
-in:spam in:sent zzalpha      untried_drops ['in','terms']   affordances []
in:sent -label:spam zzalpha   untried_drops ['in','label','terms']  affordances []
candidate call:  '-in:spam zzalpha'    -> reaches Gmail: [('-in:spam zzalpha', False)]
```

`without_the_region_it_named` bails as soon as **any** region fragment among the region constraints
is negated, so it refuses an offer that would not have undone anything. **R-RETR-045.**

**Class two — an unproven operator in the recovery class.** `report_affordances` mints a working
offer for `unproven_operator` and `unparsed_syntax` drops, and that offer is delivered **only** when
no rung ran at all:

```
thread:1837abf zzalpha   dropped ['unproven_operator']  untried ['terms']  affordances []
                         report_affordances(parsed) = [{'query': '"thread:1837abf" zzalpha'}]
                         executing it reaches Gmail: 6 requests, including the operator as a phrase
vault:archive zzalpha    dropped ['unproven_operator']  affordances []   same shape
```

Because `assemble` chooses `report_affordances` **or** `recovery_affordances` on `run.rungs_run`,
and `recovery_affordances` mints only the region kind, any query with one executable fragment beside
an unprovable operator is told a token was dropped and given no way to have it honoured — which is
I-4 exactly. **R-RETR-046.** The implementer's own §3 says the report class is 11.3 % of
zero-evidence responses; the two other offer kinds live only there.

## D.3 The assertion that should have caught class one is vacuous

`test_a_zero_evidence_response_offers_nothing_only_when_nothing_would_help` proves its silent class
with, among others, line 797:

```python
assert without_the_region_it_named(parsed) is None, query
```

`recovery_affordances` returns `()` **exactly when** that function returns `None`, and the silent
branch is reached only when `recovery_affordances` returned `()`. The assertion therefore restates
the code's own branch condition and can never fail for any shape. It is `f(x) == f(x)` at one
remove — the same product call on one side and the branch it drives on the other. **R-RETR-047.**
The test's *third* assertion (`for offer in report_affordances(parsed): assert offer.args ==
{"query": parsed.render()}`) is correctly written and **would** catch class two — the population
just contains `thread:1837abf` alone (report class, passes) and not `thread:1837abf zzalpha`
(recovery class, fails). So the "partition" is, as the work order suspected, partly a description of
the shapes chosen. My vacuity scan of both new modules found this one assertion and no other:
zero self-comparisons, and the other four `is None` assertions on product calls are legitimate
written-out expectations.

## D.4 ROUTE-01 — my decision

**ROUTE-01 stays NOT TESTED, and I am not restoring it.** Two independent reasons, and I want both
on the record because only the first is a wording problem:

1. **The acceptance is unmeetable as written.** "100 % of zero-evidence responses carry … and
   affordances" cannot hold for a response where no call would help — `zzalpha` over an empty
   mailbox, `?`, `the and of`. Minting something anyway is precisely what R-RETR-023 removed. This
   needs the same treatment OD-2 gave ROUTE-04: re-scope the fifth element to *"an executable
   affordance wherever a different call would reach a rung, and a stated reason where none would"*,
   with the exclusion class written into it explicitly. **That is an owner/orchestrator amendment,
   not a reviewer's to make.**
2. **Even under the amended reading the property is false today**, by D.2. Two classes have a
   concrete, executable, non-exclusion-undoing call and offer nothing.

So this is not "ROUTE-01 is blocked on wording". It is blocked on wording **and** on behaviour, and
I am naming which is which. What would restore it: the amendment, plus R-RETR-045 and R-RETR-046
fixed, plus a re-run of D.1's measurement showing every silent response proven silent by something
other than the branch that silenced it.

---

# Part E — the 28-entry replant harness

**The manifest is sound against the working tree.** All 28 anchors match exactly once; no
replacement equals its anchor; all 23 distinct cited tests exist by name in the files cited
(`/tmp/rretr19/e1_replant_spotcheck.py`). Paths: `assemble.py` 7, `analysis.py` 5, `operators.py` 4,
`ladder.py` 4, `constants.py` 4, `wire.py` 2, `mailbox.py` 1, `models.py` 1.

**Seven entries planted my own way**, each into a fresh full copy with imports asserted:

```
entry                                              named test   content hash          whole suite, that test deselected
R2-l3-widens-out-of-a-declared-region              CAUGHT       15f4ef68->9f516168    CAUGHT
R17-region-predicate-is-a-prefix-again             CAUGHT       bd822190->a3d47a5a    CAUGHT
R19-a-group-holding-one-operator-is-not-read       CAUGHT       bd822190->4a3958a2    CAUGHT
R21-stub-rows-lose-their-provenance                CAUGHT       6f6e52b3->72f50432    CAUGHT
R24-an-unobserved-provenance-reads-as-a-negative   CAUGHT       820193a6->9e9bd328    CAUGHT
R26-an-offer-undoes-an-exclusion-the-caller-wrote  CAUGHT       6f6e52b3->330b1b0f    CAUGHT
R28-the-offer-that-reaches-no-rung-comes-back      CAUGHT       6f6e52b3->0dddb25e    CAUGHT
```

**R-RETR-042 is closed and I checked the fix rather than reading it.** `_environment` now carries
`harness/src` and the assertion covers all three packages; in my own copies `mailweave`,
`mailweave_harness` and `tests` all resolve inside the scratch tree and none into
`/root/mailweave`; `docs/` and `tests/conftest.py` are copied.

**Is the pre-plant control real?** I attacked it. On a copy with `docs/` removed:

```
the tests the manifest names            pass    <- the narrow control does NOT fire
the whole suite                         FAIL
```

That looks like a weakened guard and it is not, and the distinction matters enough to spell out.
`run_replants` calls the narrow control on **every** pass and `assert_the_scratch_tree_is_green`
additionally under `whole_suite=True` — and `whole_suite=True` is exactly the branch that produces
the whole-suite column, which is the column a broken copy would fill for free. The narrow control
protects the named column, which is the only column CI produces, and it protects it soundly: a
docs-less copy leaves every named test passing, so a plant that fails to bite still reports MISSED
honestly. The strong control still guards the column that needs it. **This is a correct fix and I
confirm both halves.**

---

# Part F — the spelling-versus-data sweep, verified by finding one the implementer missed

I enumerated the product's predicates by AST rather than by reading the report's table: 41
bool-returning or predicate-named functions in `server/src`, of which the implementer's table lists
21. I went through the 20 unlisted ones. Most are correctly outside the question — `charset_is_known`
reads the codec table, `carries_nothing_searchable` is structural, `_should_run` is a policy over
rung ids, `mentions` walks a JSON tree, `complete_as_reported`, `more_pages`, `latched`, `is_fenced`
and the tokenstore helpers are all structural or read markers this repository writes.

**One is the shape the standing instruction is about, and it is the root cause of R-RETR-043.**

```python
# server/src/mailweave/query/operators.py
GROUP_OPENERS: Final[str] = "({"          # "Characters that open or close one of Gmail's groupings."
GROUP_CLOSERS: Final[str] = ")}"

def _is_group_token(raw: str) -> bool:
    stripped = raw.strip("-")
    return bool(stripped) and (stripped[0] in GROUP_OPENERS or stripped[-1] in GROUP_CLOSERS)

# server/src/mailweave/constants.py
QUERY_GROUPING_PUNCTUATION: Final[str] = "(){}[],;"   # "Gmail's grouping and separating punctuation"
```

**Two vocabularies for one category, and they disagree on `[`, `]`, `,` and `;`.** That is the
R-ARCH-031 shape this repository has now found more than a dozen times, stated in
`WIDENING_MAILBOX_OPERATORS`' own comment — *"a vocabulary spelled twice is how the two come to
disagree"* — and it is spelled twice here. The comparison side strips `[`; the parse side does not
know it exists. Combined with `operator_token` stripping punctuation **before** the negation prefix
is removed (so a leading `-` blocks the left-hand strip), the consequence is exactly the asymmetry
`declares_the_search_region`'s docstring forbids:

```
declares_the_search_region('[in:spam]')   True
declares_the_search_region('-[in:spam]')  False     <- "Polarity ... never decides whether a
declares_the_search_region('-,in:spam')   False         fragment is one" -- here it does
declares_the_search_region('-(in:spam')   False
```

**R-RETR-044.** I record it as a finding separate from the leak because the leak is one consequence
and the duplicated vocabulary will produce others: `assemble.report_affordances`' de-grouping uses
the constants spelling while `tokenise` uses the operators spelling, so the two modules already
disagree about what a group is.

I also checked, and am **not** filing, `constants.region_name`. Its docstring says "the bare region
a **location operator** names" and its body does `removeprefix(MAILBOX_LOCATION_PREFIX)`, so
`region_name('label:spam')` returns `'label:spam'` — a category name that is wider than the code
since the `REGION` split. It has exactly one product caller, `mailbox_regions_of`, which passes it
only `REGION_LABEL_BY_OPERATOR`'s two `in:` keys. **Unreachable today; §5a says do not chase it.**
It should be in the sweep's table with that reachability written beside it.

Everywhere the implementer says a spelling check is genuinely right, I agree, and I re-derived two
of them rather than accepting them: `widens_beyond_the_default_mailbox` must name the exact `q`
spellings the request flag is paired with (widening it to the registry would set the flag for
`label:spam`, which is a claim about Gmail nothing here can establish — and I confirmed the
consequence: a newly registered REGION operator naming spam does **not** set the flag, which fails
closed); and `is_the_widening_mailbox_operator`'s category really is one operator.

---

# Part G — recall, evidence preservation, and R-RETR-030

## G.1 `H = disclosed ∪ withheld`

`/tmp/rretr19/h1_recall.py` (900 randomised trials, randomised mailboxes, randomised region
spellings, 25 % of messages with `labelIds` stripped) and `/tmp/rretr19/h2_withheld.py` (10 runs
against a 160-message / 40-thread mailbox that forces the hit-thread cap):

```
trials                                                900 + 10
ids in H neither disclosed nor withheld                      0
withheld records produced                                  454
withheld records with no affordance                          0
rows with absent or self-contradictory provenance            0
rows disclosed from a region the query excluded            181  (all role=stub, 0 matched)
probes carrying includeSpamTrash for an excluding query       0
probe q's that dropped the exclusion the caller wrote          0
```

Nothing vanishes, every withheld id carries a working retrieval affordance, and the region invariant
holds at the wire in every trial.

## G.2 Criterion traces on my own sets

```
LEX-01   600 envelopes; first scan_scope entry is a messages.list q in 600/600
LEX-02   600 envelopes; parsed constraints neither enforced nor declared dropped: 0 (my own oracle)
ROUTE-03 drops are one at a time, in the published order, logged, and reproducible across two runs;
         a region constraint is correctly absent from the sequence
           'in:inbox from:ana@team.example newer_than:7d zzalpha'
             -> [('newer_than',), ('from',), ('terms',)]
ROUTE-04 6/6 constructed single-restoring cases name the right constraint, status complete
```

## G.3 R-RETR-030 — the `from:` reproduction is live, and there is a third

`/tmp/rretr19/g1_rretr030.py`, run against this tree and against `/tmp/rretr18/pristine`:

```
                                 this tree                                round 18
from:a@parts.example zorbal      enforced ['from','terms'] tc 1.0         identical
                                 rows l-1 matched cov ('from',)
                                      l-2 matched cov ('terms',)
label:Label_77 zorbal            wire ['label:Label_77 zorbal']           wire 3 q's, rows l-1, l-2
                                 rows []  offer {'query':'zorbal'}        the union reproduction
subject:First zorbal             enforced ['subject','terms'] tc 1.0      identical   <-- NEW
                                 rows l-1 matched cov ('subject',)
                                      l-2 matched cov ('subject','terms')
```

**The implementer's account is exactly right and I verified both halves.** `from:` is unchanged and
live. The `label:` reproduction is gone **because the query no longer decomposes** — the recall cost
of Part B wearing a different hat — and the implementer reported it as that rather than as a fix,
which is the right call and the one I checked rather than accepted. I add a third live
reproduction, `subject:First zorbal`, which shows the seam is not `from:`-specific: it is any
decomposable non-region operator. R-RETR-030 stays **OPEN**; the refusal remains correct;
**WS-16 / amendment A1**.

## G.4 R-RETR-041 and R-RETR-037, narrowed

**R-RETR-041 is materially narrower than round 18 filed it**, and I checked rather than read.
"The whole recovery ladder is withheld from any query carrying an `in:` token" is no longer true:

```
in:unread zorbal mirephant   units=2  probes ['in:unread zorbal mirephant','in:unread zorbal','in:unread mirephant']
in:snoozed zorbal mirephant  units=2  same shape
in: zorbal                   declares_the_search_region('in:') = False  -> the value-less half is CLOSED
```

Decomposition and relaxation both survive with the region carried onto each unit. What is withheld
is L3's broadening and the region drop, and the region drop is now handed back as an executable
call. Open, narrowed, **WS-10 / R-GMAIL**.

**R-RETR-037 (fullwidth) — the boundary is closed, the executed `q` residue is not.** The gate holds
(0 widened, 0 flagged across 485 fullwidth probes). What the caller gets instead:

```
-ｉｎ：ｓｐａｍ quintle
  wire      [('-in spam quintle', False), ('spam', False), ('quintle', False)]
  asked_for terms ['-in','spam','quintle']; enforced ['terms','stopwords_removed:-in:spam']
  outcome   inconclusive
```

The residual-term pipeline folds and re-tokenises on the colon, so a query that said "not in spam"
executes a probe searching the default mailbox for the *word* `spam`. No region is entered, the
response discloses the rewritten terms and names the rewrite, and the outcome is `inconclusive`.
A wrong question honestly reported. Open, **A.6 / WS-10**.

---

## Findings

```
ID:            R-RETR-043
Severity:      MEDIUM
Reachability:  REACHABLE today. An ordinary query string through LadderRunner.run + assemble.
               The trigger spellings are unusual for a human (`-[in:spam]`, `-,in:spam`,
               `-(in:spam` with an unbalanced opener) but are exactly what a calling agent
               composing a bracketed or partially-grouped exclusion produces, and the
               positive form of the same spelling IS already read as a region by this code.
Blocks round 20?  NO — rides along. The response declares the token dropped under
               `unproven_operator` in the same envelope and every returned row states its own
               region, so this is a declared drop with an unwanted consequence rather than the
               undeclared boundary crossing OD-6 means by a critical safety defect. Fix it in
               the round that next touches `query/operators.py`.
Rubric:        OD-5 point 3 and A9-A2 (an explicit scope is preserved across every probe, in
               either polarity); the work order's exit condition ("No probe enters a region the
               query excluded, under any spelling"); LEX-02; EV-04's paired hallucinated-found
               guard; contract I-4.
Location:      server/src/mailweave/constants.py, operator_token — strips
                 QUERY_GROUPING_PUNCTUATION from both ends *before* the negation prefix is
                 considered, so a leading `-` blocks the left-hand strip;
               server/src/mailweave/query/operators.py, operator_of — removes the `-` and then
                 partitions on `:` without re-stripping, so the body still carries `[`, `(` or
                 `,` and no OperatorName matches;
               server/src/mailweave/query/operators.py, _is_group_token / GROUP_OPENERS — `[`
                 is not a group opener here, so `tokenise` cannot rescue the token either.
Repro:         /tmp/rretr19/b2_e2e_leak.py, /tmp/rretr19/b3_table.py, /tmp/rretr19/a2_vault_safety.py
                 declares_the_search_region('[in:spam]')   = True
                 declares_the_search_region('-[in:spam]')  = False
                 mailweave_search('-[in:spam] quintle')   (quintle planted only in SPAM/TRASH)
                   wire    [('quintle', False), ('in:anywhere quintle', True)]
                   rows    m-sp matched regions ('spam',); m-tr matched regions ('trash',)
                   outcome answered      dropped ['unproven_operator']
                 identical for '-,in:spam quintle', '-(in:spam quintle', '-[label:spam] quintle',
                 '-[category:updates] quintle', '-[in:trash] quintle', and for a newly
                 registered REGION operator: '-[vault:spam] quintle'.
               Plan layer: 980 scoped queries over 20 spellings, 3,404 probes; 147 probes
                 widen out of the excluded region and 147 set includeSpamTrash, all of them
                 from these three spellings; 0 from the other seventeen.
Expected:      "Polarity decides which region a declaration names. It never decides whether a
               fragment is one" — `declares_the_search_region`'s own docstring. If
               `[in:spam]` is read as a region, `-[in:spam]` must be too, and no probe may
               widen out of it.
Actual:        The generous reading is applied in the polarity where it costs recall and the
               strict reading in the polarity where it costs a disclosure — the inverse of the
               asymmetry KIND_BY_OPERATOR's own comment states. The excluded SPAM and TRASH
               rows come back as `role: matched` under `outcome: answered`.
Required fix:  In `operator_of`, strip the grouping punctuation again after removing the
               negation prefix (equivalently: normalise polarity and punctuation to a fixed
               point rather than in one pass). Two lines. Then fix R-RETR-044 so the two
               modules cannot disagree about what punctuation is. The test is the existing
               family sweep extended with the negated-punctuation spellings `-[x]`, `-,x`,
               `-(x`, `-;x` over both polarities and every registered REGION operator, and it
               belongs in the replant manifest.
```
```
ID:            R-RETR-044
Severity:      MEDIUM
Reachability:  REACHABLE today — it is the root cause of R-RETR-043 and it already makes
               `tokenise` and `report_affordances` disagree about what a group is.
Blocks round 20?  NO — rides along, with R-RETR-043, which is its live consequence.
Rubric:        The work order's standing instruction ("every predicate whose docstring
               describes a category must read the data that defines that category"); A9-A2;
               R-ARCH-031's rule, stated in this repository's own constants module, that a
               vocabulary spelled twice is how two layers come to disagree.
Location:      server/src/mailweave/query/operators.py — GROUP_OPENERS = "({",
                 GROUP_CLOSERS = ")}", documented as "Characters that open or close one of
                 Gmail's groupings", read by `_is_group_token` and `_sole_operator_of_a_group`;
               server/src/mailweave/constants.py — QUERY_GROUPING_PUNCTUATION = "(){}[],;",
                 documented as "Gmail's grouping and separating punctuation", read by
                 `operator_token`, `carriage_token` and `assemble.report_affordances`.
               `_is_group_token` is a predicate whose name states a category and whose body
               reads one of the two vocabularies; it is not in the round's sweep table.
Repro:         /tmp/rretr19/b3_table.py; direct:
                 operator_token('[in:spam]')  = 'in:spam'      _is_group_token('[in:spam]')  = False
                 operator_token('-[in:spam]') = '-[in:spam'    _is_group_token('-[in:spam]') = False
                 -> declares_the_search_region disagrees with itself across polarity (R-RETR-043)
               And across modules: `report_affordances` de-groups with the constants spelling
               while `tokenise` groups with the operators spelling, so a token one strips the
               other does not.
Expected:      One vocabulary for "the punctuation Gmail groups and separates with", written
               once, read by both the parse and the comparison — the rule this repository
               already applies to the scope operators and the negation prefix.
Actual:        Two, disagreeing on four characters, in the two modules whose disagreement
               about one token was round 18's central finding.
Required fix:  Write the vocabulary once in `constants` and have `operators` read it, or split
               it explicitly into "grouping" and "separating" with both named and both read by
               both sides. Add `_is_group_token` to the sweep table with its verdict. A test
               that asserts the two modules read the same character set, and a manifest entry
               that plants a divergence back.
```
```
ID:            R-RETR-045
Severity:      MEDIUM
Reachability:  REACHABLE today. `in:inbox -in:spam <term>` is an ordinary query and a natural
               one for a calling agent to compose.
Blocks round 20?  NO — rides along. It costs recoverability, not correctness: the response
               names the untried drop, so the caller is not misled, only unhelped.
Rubric:        ROUTE-01's fifth element; contract I-4 (recoverability); AD-03 ("an affordance
               is a concrete call that would reach the untried rung"); OD-2's disclosure rule.
Location:      server/src/mailweave/retrieval/assemble.py, without_the_region_it_named — the
               `if any(... startswith(NEGATION_PREFIX) ...)` early return is taken over the
               whole region constraint set rather than over the fragments the offer would drop.
Repro:         /tmp/rretr19/d1_affordances.py
                 'in:inbox -in:spam zzalpha'    untried_drops ['in','terms']  affordances []
                 'in:sent -label:spam zzalpha'  untried_drops ['in','label','terms']  affordances []
                 without_the_region_it_named(parsed) = None ; plannable_drops = ()
                 the call that helps: '-in:spam zzalpha'  -> reaches Gmail [('-in:spam zzalpha', False)]
Expected:      Either an offer that drops the positive region and keeps every exclusion the
               caller wrote, or a stated reason why none exists. The rule the function
               documents — "never an offer that undoes an exclusion" — is satisfied by such an
               offer, so refusing it is wider than the rule.
Actual:        A single negated region anywhere in the query suppresses the offer for the
               positive one, and the response says nothing about why.
Required fix:  Drop only the *positive* region constraints and keep the negated ones, refusing
               only when what is left is not a probe or when nothing positive was named. Assert
               it over a mixed-polarity population, and add the shape to ZERO_EVIDENCE_SHAPES.
```
```
ID:            R-RETR-046
Severity:      MEDIUM
Reachability:  REACHABLE today. `thread:1837abf <term>` is `report_affordances`' own documented
               example; any query pairing an undocumented operator with one executable term
               reaches this.
Blocks round 20?  NO — rides along, with R-RETR-045; same class, same consequence.
Rubric:        ROUTE-01's fifth element; ROUTE-02 (mis-parse recovery); contract I-4; LEX-02
               (a dropped signal is named — it is, but with no way to act on it).
Location:      server/src/mailweave/retrieval/assemble.py — the envelope chooses
               `report_affordances(run.parsed) if not run.rungs_run else recovery_affordances(run)`,
               and `recovery_affordances` mints only the region-drop kind. The
               `unproven_operator` and `unparsed_syntax` offers exist and execute, and are
               unreachable for every response where any rung ran.
Repro:         /tmp/rretr19/d1_affordances.py
                 'thread:1837abf zzalpha'   dropped ['unproven_operator']  affordances []
                   report_affordances(parsed) = [{'query': '"thread:1837abf" zzalpha'}]
                   executing that call reaches Gmail: 6 requests
                 'thread:1837abf' alone (no rung runs) DOES carry the same offer
                 same shape for any unregistered operator, e.g. 'vault:archive zzalpha'
Expected:      The offer kinds are properties of the *query*, not of which response class it
               landed in. A declared `unproven_operator` drop should carry its recovery
               wherever it is declared.
Actual:        The two are mutually exclusive on `run.rungs_run`, so 88.7% of zero-evidence
               responses (the implementer's own figure for the non-report class) can never
               receive two of the three executable offer kinds.
Required fix:  Union the two producers rather than choosing between them, de-duplicating by
               `args`. `report_affordances`' internal guards already refuse an offer that names
               the query the ladder executed, so the union cannot mint a no-op.
```
```
ID:            R-RETR-047
Severity:      MEDIUM (a defect in the suite, not in the product)
Reachability:  REACHABLE — it is the assertion that would have to catch R-RETR-045, and does not.
Blocks round 20?  NO — rides along with the two findings it fails to catch.
Rubric:        AGENT_LOOP §7.2 (a test that passes for the wrong reason); the round's own
               standing rule that no assertion may have the same product call on both sides.
Location:      tests/test_region_kind_round19.py:797, inside
               test_a_zero_evidence_response_offers_nothing_only_when_nothing_would_help.
Repro:         `assert without_the_region_it_named(parsed) is None` is reached only when
               `envelope.affordances` is empty, and for the recovery class
               `envelope.affordances == recovery_affordances(run)`, which is `()` **exactly
               when** `without_the_region_it_named(run.parsed) is None`. The assertion restates
               the branch condition that produced the silence and cannot fail for any shape.
               Executed: 'in:inbox -in:spam zzalpha' is silent, has a working call, and would
               satisfy both surviving assertions of the silent branch.
Expected:      The silent class is proved by something independent of the code that silenced
               it — an oracle written in the test that enumerates the calls a caller could make
               and shows each reaches no rung.
Actual:        Two of the three assertions have content (the plannable-drops intersection, and
               the report-class check, which is correctly written and would catch R-RETR-046 if
               the population contained the shape); the third has none.
Required fix:  Replace line 797 with a written-out oracle over candidate calls: for each region
               constraint the query wrote positively, construct the query without it, assert it
               either is not a probe or reaches no rung. Extend ZERO_EVIDENCE_SHAPES with a
               mixed-polarity shape and an unproven operator beside an executable term.
```
```
ID:            R-RETR-048
Severity:      LOW (a claim wider than the code; the code is right)
Reachability:  REACHABLE — 181 such rows in 900 randomised trials.
Blocks round 20?  NO — rides along. The behaviour is OD-3's floor and is correct; what is wrong
               is a sentence in a test.
Rubric:        OD-3 (membership is absolute, depth degrades) against OD-5 point 3; the work
               order's exit condition wording; AGENT_LOOP §7.2.
Location:      tests/test_region_and_provenance_round18.py,
               test_a_query_that_excluded_a_region_never_reads_it_and_never_discloses_a_row_from_it
               — the third assertion loops over `rows(envelope)`, matched and stub alike, and
               its fixture (`spread_mailbox`) puts every message in its own thread, so no thread
               ever has members in two regions.
Repro:         /tmp/rretr19/h1_recall.py, 900 randomised trials:
                 rows from an excluded region, by role/depth: {('stub','stub'): 181}
                 example: '-in:trash sable tarnix' -> row m-7 role=stub regions=('trash',)
                          reason=ThreadMember; 0 probes with includeSpamTrash; 0 q's dropping
                          the exclusion
Expected:      Either the assertion says "no *matched* row comes from a region the caller
               excluded" — which is what the code guarantees and what OD-5 point 3 requires —
               or the product drops excluded-region members from the thread map, which OD-3
               forbids.
Actual:        The test asserts the stronger claim and passes only because its fixture cannot
               produce a thread that would falsify it. A future reviewer reading the test learns
               a guarantee the product does not make.
Required fix:  Narrow the assertion to `role is Role.MATCHED`, and add a fixture with one
               thread whose matched member is in the inbox and whose stub member is in TRASH,
               asserting positively that the stub IS carried, IS `depth: stub`, and DOES report
               `regions=('trash',)` — the OD-3/OD-5 interaction stated honestly rather than
               asserted away.
```

**Carried forward, open, and blocking in the round they return to (§5a):**

* **R-RETR-029** (MEDIUM) — the `Default_Ignorable_Code_Point` residue. Untouched this round, as
  the implementer says. Severity at **R-GMAIL**, fix at **WS-10**.
* **R-RETR-030** (MEDIUM) — `enforced` as the union over routes. **Live**, unchanged, and I add a
  third reproduction (`subject:First zorbal`) beside `from:`, which shows it is any decomposable
  non-region operator rather than `from:` specifically. The `label:` reproduction is gone as a side
  effect of Part B's recall cost and was reported as that, correctly. **WS-16 / amendment A1.**
* **R-RETR-037** (MEDIUM) — narrowed. The broadening boundary is closed for every fullwidth
  spelling (0 of 485 probes widen); the executed-`q` residue is live and honestly declared.
  **A.6 / WS-10.**
* **R-RETR-041** (MEDIUM) — materially narrowed and mitigated. `in:` with no value no longer
  declares a region; decomposition and relaxation survive for `in:unread`; only L3 and the region
  drop are withheld, and the drop is offered back as an executable call. **WS-10 / R-GMAIL.**

**Closed, verified by execution:** **R-RETR-035** (every documented spelling, both polarities,
grouped both nestings, `label:`-named, `category:`-named, uppercase, comma, semicolon and fullwidth
— the residue is refiled as R-RETR-043/044 at lower severity and narrower scope), **R-RETR-036**
(the predicate reads `KIND_BY_OPERATOR`; a newly registered REGION operator is covered, established
by registering one and attacking it), **R-RETR-038** (stub provenance, defended by R21 and by my own
plant), **R-RETR-039** (`unobserved` has a producer and reads as `null`, defended by R23/R24),
**R-RETR-042** (all three packages resolve into the scratch copy; the pre-plant control is real and
correctly scoped). **R-RETR-040 is partially closed**: the non-executing offer is gone and all 26
offers I executed reached Gmail; the coverage half is refiled as R-RETR-045/046/047.

---

## Recommendations, per criterion

**I mark nothing.** Every recommendation is scoped and I name what my evidence does not cover.

* **LEX-01 · Message-level search is the first rung — RECOMMEND PASS, scoped** (unchanged from
  rounds 17 and 18; I re-confirm on this round's code). Evidence: 600 randomised envelopes, the
  first `scan_scope` entry is a `messages.list` with a non-empty `q` in **600 of 600**; plus 910
  preservation trials with no exception. *Scope:* all traces are through `MockTransport`; "no code
  path derives the primary hit set from a thread-level listing" is a code-read claim. **R-ARCH /
  R-GMAIL.**
* **LEX-02 · Operator-parse fidelity and coverage reporting — RECOMMEND NOT YET**, and the reason
  is narrower than last round. Positive evidence: 600 envelopes, **0** parsed constraints neither
  enforced nor declared dropped, measured against my own oracle; `constraint_coverage` present and
  honest on every disclosed row across 910 trials; the region is now carried onto every probe for
  seventeen of twenty spellings. The blocker is still the acceptance's "signals silently dropped:
  **0**": R-RETR-043 drops a region declaration into `unproven_operator` and then acts on its
  absence by widening, and R-RETR-030 still reports `enforced ('from','terms')` at
  `term_coverage 1.0` over rows no single route carried.
* **LEX-03 · Multi-constraint decomposition — RECOMMEND NOT YET.** The mechanism is right, the
  region is carried onto every unit in both polarities, and R-RETR-041's suppression is now limited
  to L3. Two reasons not to mark: the recall bar is `[UNSET — register at G0]` against Baseline D,
  and this round *deliberately removes* decomposition for `label:` and `category:` queries — a
  measured, declared recall regression (Part B) that the criterion's family will feel.
* **LEX-04 · Exact-signal stop — RECOMMEND NOT YET, unchanged.** The stop fires correctly; the cost
  bar needs network-level counts. **WS-16 / R-PERF.**
* **EV-02 · Position-independent evidence recall — RECOMMEND NOT YET.** No position sweep exists;
  needs a seeded corpus. **WS-16.**
* **EV-04 · Zero false "not found" on answerable cases — RECOMMEND NOT YET.** 910 trials produced
  **0** cases where a present, matching thread was not returned under `answered` or `inconclusive`,
  and **0** matched rows from a region the query excluded — a real improvement on round 18's 13. The
  paired hallucinated-found half is now down to R-RETR-043's three punctuation spellings, which is
  the smallest this has been; it is not zero.
* **EV-05 · Issue #296 signature is non-reproducible — RECOMMEND NOT YET.** The thread-map floor
  holds in every trial and every member states where it lives, including the unobserved case.
  Clause 2 needs the live signature. **R-GMAIL.**
* **EV-06 · Recall against the full-dump ceiling — RECOMMEND NOT YET.** Needs Baseline B and a
  seeded corpus. **WS-16.**
* **ROUTE-01 · No bare empty response — RECOMMEND NOT YET, and I am the reviewer who could have
  restored it.** See Part D.4. Two independent blockers, and I separate them because only one is
  wording: (1) the acceptance's "100 % … affordances" is unmeetable as written and needs the same
  OD-2-style re-scoping ROUTE-04 got, which is the orchestrator's to make; (2) **even under the
  amended reading the property is false today** — R-RETR-045 and R-RETR-046 are two classes with a
  concrete, executable, exclusion-preserving call and no offer. The *structural* half of ROUTE-01 is
  in good shape and I record it: over 37 zero-evidence responses, every one carried queries executed,
  constraints dropped with reasons, per-rung hit counts and what was not tried; bare empty
  responses **0**; and all 26 offers executed reached Gmail with **0** reaching nothing.
* **ROUTE-02 · Mis-parse recovery — RECOMMEND NOT YET.** The recovery-rate bar is `[UNSET]`, and
  R-RETR-046 removes the recovery for the mis-parse class the criterion is most about (an operator
  MailWeave cannot prove).
* **ROUTE-03 · Relaxation is systematic and enumerable — RECOMMEND PASS, scoped.** Executed: drops
  are one constraint at a time, in `RELAXATION_ORDER`'s published sequence, each logged with the
  constraint and the resulting hit count, and identical across two runs of the same input. The
  round-19 change (splitting `LOCATION` into `REGION` + `ATTRIBUTE` in the same position) leaves the
  published sequence unchanged for every query that writes one of them, which I verified, and a
  region is correctly *absent* from the sequence because it is refused as a drop. *Scope:* the
  ordering is verified over my own multi-constraint set, not over a registered distribution of real
  query shapes; and "documented order" is documented in `RELAXATION_ORDER`, which is now keyed on
  enum values whose names changed this round — the architecture's A.7 L2 prose should be re-read
  against it. **R-ARCH.**
* **ROUTE-04 · Empty-result diagnosis — RECOMMEND NOT YET, close.** Executed: 6/6 constructed
  single-restoring cases name the correct constraint with `status: complete`; `untried_drops` is
  populated and the outcome is `inconclusive` in every incomplete case I produced. What stops it is
  the `[UNSET]` incomplete-diagnosis ceiling — which cannot be registered before G0 — and the fact
  that the *diagnosis* now routinely reports an untried drop with no offer beside it
  (R-RETR-045/046), which is inside ROUTE-01 rather than ROUTE-04 but is what a caller reading the
  diagnosis experiences.

---

## Verdict on each of OD-5's five requirements

| # | Requirement | Round 18 | **Round 19** | Why |
|---|---|---|---|---|
| 1 | Machine-readable mailbox provenance on every `MessageRow`, from actual labels | partially met | **MET** | Derived and unforgeable (6 forgeries refused); required on the row; present on stubs from their own labels; `unobserved` has a producer, is per-message, and reads as `null` not `false`, on the wire; 0 violations in 910 trials. R-RETR-038 and R-RETR-039 closed and defended by R21–R24. |
| 2 | L3's `in:anywhere` kept, and only when the user specified no scope | partially met | **PARTIALLY MET** | 0 widenings across the 2,594 probes of seventeen spellings including every documented one, both fullwidth forms, `label:`- and `category:`-named; the published step still fires for a scope-free query (7/7). 147 probes widen for `-[x]`, `-,x`, `-(x` (**R-RETR-043**). |
| 3 | An explicit scope is preserved across every probe, derived from what an operator does | partially met | **PARTIALLY MET** | The derivation is genuinely registry-driven — a newly registered `vault:` REGION operator is carried, unrelaxed and unwidened across every spelling and both polarities with no predicate and no oracle edited. Same three-spelling residue as requirement 2. |
| 4 | A negated phrase remains an exclusion | met | **MET** | 7 adversarial shapes including colon-carrying, fullwidth, empty and mixed-polarity; no probe of any rung searches for a negated phrase. |
| 5 | L0 uses the corrected `enforced` semantics, derived once | met | **MET** | One derivation, read by every rung; the over-claim plant at L1 is extensionally a no-op (verified over 16 shapes), and the requirement's defence rests on R5/R6, both CAUGHT in my own scratch tree. |

## Verdict on the `OPERATOR_FAMILY_VALUES` question

**Not an enumeration in disguise; the exit criterion as written was the wrong criterion.** The
decision about what an operator *does* lives in product data and the sweep population is derived
from it; what the test-side dict supplies is a plausible *value*, which no code in this repository
can know and which the fidelity table and the mailbox double already require for the same reason.
Omitting it fails **loudly** — three collection errors and a named totality test — which is the
opposite of round 18's silent 2,274-green under-coverage; a degenerate value fails closed in both
directions I tried; and the coverage it buys is real, established by registering `vault:` and
attacking it behaviourally rather than by reading a green suite. Replace the criterion with:
*registering a new REGION operator in the product must either cover it or fail loudly; it must never
leave the suite green and the operator uncovered.* That criterion is **met**.

## Overall verdict

**Integration should proceed. Round 20 is not blocked by anything in this review.**

OD-6 asks whether an audit-only round is justified by a *critical correctness or safety defect*. I
looked for one, with the method that found round 18's, and I did not find one. What I found is:

* the central defect of round 18 is **fixed at the root** — the predicate reads the registry, and I
  proved the fix generalises by registering an operator nobody has added and failing to make it
  leak in fourteen of seventeen spellings, both polarities, every rung;
* every documented spelling a person or a calling agent would plausibly write — `-in:spam`,
  `-(in:spam)`, `(-in:spam)`, `-{in:spam}`, `-label:spam`, `-category:updates`, `-IN:SPAM`,
  `-in:spam,`, `-ＩＮ：ＳＰＡＭ`, multi-scope and contradictory-scope forms — is clean at the wire
  and in the response;
* the one leaking class needs a grouping character wedged between the minus and the operator, and
  the same response declares the token dropped under `unproven_operator` and labels every row's
  region. It is real, it is MEDIUM, and it is not the undeclared boundary crossing OD-6 means;
* provenance is complete, unforgeable and honest about what it does not know;
* nothing vanishes: 0 lost ids and 454 withheld records with affordances across 910 trials;
* five gates clean, twice, at 2,290 tests, with the rubric untouched.

The five findings I file are all **ride-along**. Three of them (043/044 and 045/046) cluster into two
small, well-localised repairs — a two-line normalisation fix plus one vocabulary written once, and
a union of two affordance producers plus a polarity-aware region drop — and both clusters are
natural work for the round that next opens `query/operators.py` and `retrieval/assemble.py`. Two
(047/048) are test-strength repairs that should travel with them.

I would not hold WS-05, WS-06, WS-10, WS-11 or WS-15 for any of it. The specific reason: none of
these five defects can produce a *wrong answer the response does not itself declare*, and the
milestone OD-6 describes — a live account, a real thread, stable handles, truthful scope, Spam/Trash
provenance — is now better served by finding out what Gmail actually does with a grouped operator,
a fullwidth operator and `label:spam` than by another round of reasoning about it here. Four of my
own open items and four of the carried-forward ones are marked **R-GMAIL** and cannot be closed by
any amount of further static review. **Go.**

---

## Established by execution

* **All five gates clean and stable**, twice, before and after all probing: **2,290** tests,
  independently re-counted by summing `--collect-only` per file; `pytest -m replant` 4 passed; the
  rubric unchanged at 6/0/0/107 with 11 transitions; no source or test file modified inside my
  review window.
* **The region predicate reads the registry, and the fix generalises.** A brand-new `vault:` REGION
  operator, registered as an implementer would in a full isolated copy, is read as a region in both
  polarities, carried by every probe of every rung, never relaxed away, never widened out of, with
  `includeSpamTrash` never set — **no predicate edited, no test oracle edited**. The filtering
  control still behaves as a filter.
* **17 of 20 spellings clean** across 980 scoped queries and 3,404 probes: 0 region fragments
  dropped, 0 widenings, 0 flags. Every round-18 leak spelling is closed end to end.
* **The published broadening survives**: a scope-free query still reaches `in:anywhere` with the
  flag set and returns the spam and trash rows, 7/7.
* **Provenance**: 6 forgeries refused by the type; `regions` has no setter; `mailbox` required on
  the row; the unobserved state producible, per-message, and `null` on the wire; 910 trials, 0 rows
  without or contradicting provenance, 1,229 legitimately-unobserved rows.
* **A negated phrase is never searched for**, in 7 adversarial shapes.
* **Evidence preservation**: 910 trials, 0 ids in `H` neither disclosed nor withheld, 454 withheld
  records, 0 without an affordance.
* **Region invariant at the wire**: 0 probes with `includeSpamTrash` and 0 probe `q`s dropping the
  caller's exclusion, across 900 randomised trials; 0 *matched* rows from an excluded region.
* **Affordances**: 26 of 26 offers executed reached Gmail; 0 reached nothing. R-RETR-040's
  non-executing offer is gone.
* **7 of 28 replants planted my own way, all CAUGHT** by their named test *and* by the whole suite
  with that test deselected; all 28 anchors match 1/1; all 23 cited tests exist; all three packages
  resolve into the scratch copy and none into the working tree.
* **LEX-01** 600/600. **LEX-02** 0 silent drops by my own oracle. **ROUTE-03** ordered, one at a
  time, logged, reproducible, with the region correctly refused as a drop. **ROUTE-04** 6/6
  restoring constraints named correctly.
* **R-RETR-030's `from:` reproduction is live and unchanged**, in this tree and in round 18's;
  `subject:` is a third; the `label:` one closed as a side effect of the recall cost, exactly as the
  implementer reported.
* **The recall cost is what the implementer said it is**: `label:` and `category:` queries lose L1b
  thread-split recovery (1 decomposition unit instead of 2), the response says `inconclusive` and
  names the drop, and executing the offered call recovers the thread.
* **The five new defects**, each with a reproduction: the negated-punctuation region leak (147
  probes, 6 end-to-end spellings), the duplicated grouping vocabulary, the mixed-polarity affordance
  gap, the unproven-operator affordance gap, and the vacuous partition assertion.

## False on execution

* **The work order's exit condition, "A newly registered scope-declaring operator is covered
  without editing a test"** — false as literally written: registration requires
  `OPERATOR_FAMILY_VALUES` and the fidelity table, and without the first, collection dies with
  `KeyError` in three modules. Adjudicated above: the criterion was wrong, not the design.
* **"No probe enters a region the query excluded, under any spelling — grouped, negated,
  fullwidth, `label:`-named"** — true for seventeen of the twenty spellings I wrote, including every
  one that clause names, and false for `-[in:spam]`, `-,in:spam` and `-(in:spam`, each of which
  sends `in:anywhere` with `includeSpamTrash=true` and returns the excluded SPAM and TRASH rows as
  `role: matched` under `outcome: answered`.
* **`declares_the_search_region`'s "Polarity … never decides whether a fragment is one"** —
  `[in:spam]` is a region declaration and `-[in:spam]` is not.
* **"`operator_token` strips Gmail's grouping punctuation" (the implementer's account of why the
  grouped residue is closed)** — it strips it from the right end of a negated token and not from the
  left, because the negation prefix stops the strip.
* **"The suite asserts that partition rather than the percentage"** — the partition test's
  silent-class proof rests on `assert without_the_region_it_named(parsed) is None`, which is the
  branch condition that produced the silence, so it cannot fail; and two response classes with a
  working, exclusion-preserving call carry no offer.
* **"No tool in this tree takes a `terms` argument … the only call that would help is a different
  question"** — true of the deleted offer, and it does not follow that no call helps for the classes
  that inherited its silence: `-in:spam zzalpha` and `"thread:1837abf" zzalpha` both reach Gmail.
* **Round 18's `test_a_query_that_excluded_a_region_never_reads_it_and_never_discloses_a_row_from_it`,
  "no disclosed row — matched **or** stub"** — 181 stub rows from an excluded region in 900 trials.
  The code is right (OD-3); the assertion is wider than the code and its fixture cannot falsify it.
* **Round 18's own R-RETR-041, "the whole recovery ladder is withheld from any query carrying an
  `in:` token"** — no longer true: `in:unread zorbal mirephant` decomposes into two units with the
  region carried onto each, and `in:` with no value no longer declares a region at all.

## Not establishable here at all

* **Whether Gmail reads `-[in:spam]`, `-,in:spam` or an unbalanced `-(in:spam` as a scope
  exclusion.** If it does, R-RETR-043 is a boundary crossing; if it does not, it is a declared drop
  with a cosmetic inconsistency. Either way the *internal* asymmetry — generous positively, strict
  negatively — is a defect on its own terms. **R-GMAIL / PF-20.**
* **Which `label:` values are Gmail system mailboxes.** The whole `label:` → REGION decision, and
  the recall cost I measured in Part B, rest on not knowing. **R-GMAIL / A.6.**
* **Whether `in:unread` should be a filter** (R-RETR-041), and whether a `category:` tab is a scope.
  Both need Gmail's location vocabulary; the second is one registry line and belongs to the
  orchestrator. **R-GMAIL / WS-10.**
* **Whether `threads.get` with `format=metadata` ever omits `labelIds` for a labelled message**,
  which decides whether the now-producible unobserved state is a schema tidy or a live case.
  **R-GMAIL / PF-2.**
* **Whether `tokenise` should NFKC-normalise**, which decides what the executed `q` contains for the
  fullwidth shapes and closes R-RETR-037's residue. **A.6 / WS-10.**
* **R-RETR-030's honest `enforced`**, which needs the seam to hand back a page's ids.
  **WS-16 / amendment A1.**
* **Every rate the rubric asks for**: LEX-03's and ROUTE-02's recall bars, EV-02's position sweep,
  EV-04's paired hallucinated-found rate, EV-06's Baseline B, ROUTE-04's incomplete-diagnosis
  ceiling, LEX-04's cost bar. All `[UNSET — register at G0]` or needing a seeded corpus, Baselines
  B/D, holdout seeds and a network-level counting proxy. **Every number in this review is on sets I
  constructed and is offered as nothing else. WS-16 / R-PERF.**
* **A ceiling on all of the above, mine and the implementer's**: the mailbox double evaluates 14 of
  21 `OperatorName` members. Every end-to-end statement in this round is bounded by that, and by the
  absence of a live account — which is exactly what OD-6's milestone exists to remove, and the
  strongest reason in this document to proceed to it. **R-GMAIL / WS-16.**
