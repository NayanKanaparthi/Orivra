# ROUND 23 — R-DISC review (the admission was fixed; the ordering, the ladder and the ceiling were not)

**Reviewer:** R-DISC, independent instance, 2026-09-05. Sole gating reviewer for round 23; the
disclosure domain, which owns DISC-01..06, PART-05 and EV-03 and has not reviewed since round 9.
Verified by execution per `AGENT_LOOP.md` §4/§5/§5a, classified for severity **and** urgency
separately per **OD-6**.

**Source, tests, `FINDINGS_LEDGER.md`, `RUBRIC_TRANSITIONS.md` and `RELEASE_RUBRIC.md` untouched.**
Every probe ran from `/tmp/rdisc23/p*.py` against the real tree; the two plants ran in a **full**
scratch copy at `/tmp/rdisc23/tree` including `docs/` (asserted: `docs/RELEASE_RUBRIC.md` present),
with `PYTHONPATH` set explicitly and `mailweave.__file__`, `tests.__file__` **and**
`mailweave_harness.__file__` all asserted to resolve inside `/tmp/rdisc23/tree` — an assertion that
mattered, because my first plant run silently imported `/root/mailweave/server/src/mailweave` and
"passed". `/tmp/rdisc23/_env.py` and the scratch `conftest.py` carry those assertions.

My vocabulary is invented (`borogrove`, `slithy`, `toves`, `outgrabe`); my senders are `.example` /
`.invalid` (RFC 2606/6761); my mailboxes and oracles are written in my probe files. No fixture below
contains real or realistic personal mail text. I read no reviewer probe set under `/tmp/rretr15..22`.
**This file is the only thing I wrote inside `/root/mailweave`.**

---

## Environment

| Gate | Result (re-run by me, after all probing) |
|---|---|
| `ruff check server/src tests tools harness` | All checks passed |
| `ruff format --check .` | 197 files already formatted |
| `mypy --strict` | Success: no issues found in **170** source files |
| `python -m tools.guards` | 7 guards clean (forbidden-import, generative-client, gmail-endpoint, ground-truth-isolation, scope-literal, unaudited-disk-write, unwrapped-http-client) |
| `pytest -q -m "not network"` | **rc 0** (`/tmp/rd4.log`, `EXIT=0`). Independently counted: `--co -q` summed per file = **2,615**; the progress stream carries **2,615** marks and **no** `F`/`E`/`s`. The `-q` summary line does not flush in this environment — three runs, none printed it — so the exit code and the mark count are the evidence |
| `pytest -q tests/test_replants.py -rA` | 4 passed, `EXIT=0` — anchors match once, cited tests exist, scratch tree resolves, every behaviour fails a test when removed |
| `python -m tools.rubric_status` | criteria 113; **6 PASS / 0 FAIL / 0 BLOCKER / 107 NOT TESTED**, 11 transitions — unchanged |

### The tree I actually reviewed is not the tree round 23 shipped

`docs/reviews/ROUND_23/IMPLEMENTER.md` closed at **10:59 UTC**. Round 24 (WS-15) has since edited
four of the six disclosure modules:

```
disclosure/floor.py      10:06     disclosure/ladder.py     11:28   <- after round 23 closed
disclosure/weights.py    10:16     disclosure/layout.py     11:28   <- after
disclosure/segments.py   10:03     disclosure/plan.py       12:03   <- after
                                   disclosure/__init__.py   12:06   <- after
```

The round-23 report's own gate block says **2,557 passed**; the tree now collects **2,615**. So the
implementer's numbers are not reproducible as printed, and I did not treat that as a discrepancy —
I re-ran every gate myself and report what I measured. I checked that **none** of my findings
depends on round 24's additions (`body_full` in `_PLANNABLE_DEPTHS`, `evidence_view`, the widened
`depth_for`): every reproduction below goes through mechanisms round 23 wrote.

---

## Reachability and urgency, as I applied them

* **Reachability (§5a).** REACHABLE = reproducible today by driving `drive` → `assemble`
  (`tests/test_lexical_ladder.answer`) against a synthetic mailbox behind `httpx.MockTransport`,
  using the shipped defaults, or by calling `mailweave.disclosure.disclose` with the shipped
  `Ceilings()`. REACHABLE-IN-POLICY = the defect is in the published policy the response *declares*
  (a score, a reason, a `why` string) rather than in a payload the ladder mangles. I use no other
  class; nothing below is unreachable.
* **Urgency (OD-6), separate from severity.** *Blocks the milestone* = would stop OD-6's six
  criteria (server starts, connects, Claude drives it, handles/scope/provenance, smoke test,
  review), **or** would put a false statement in front of a model on the shipped path, **or** would
  make a tool call fail outright. Everything else *rides along*. §5a's counter-rule is equally
  binding on me: **anything reachable today is fixed today, whatever its severity**, and everything
  below is reachable today.

**Three of these are, in my judgement, critical correctness defects in the sense OD-6's counter-rule
names** — R-DISC-019, R-DISC-020 and R-DISC-021 — because one makes the server crash a tool call,
one silently breaks the guarantee the project calls its biggest, and one makes the degradation
ladder enlarge the thing it is degrading. I do not soften them and I do not defer them.

---

## Priority 1 — is the policy query-aware, or fixture-aware?

**It is neither, quite. It is *thread*-aware.** The admitting components (`PARTICIPANT_MATCH`,
`TERM_OVERLAP`, `TEMPORAL_PROXIMITY`-on-the-query's-window) are almost always constant across a
thread, because the facts they read are thread-level facts:

* `TERM_OVERLAP` reads `_tokens(candidate.subject) | _tokens(candidate.observed_text)`. Gmail sends
  the *same* subject on every message of a thread (`_subject_of(by_id[message_id])` in
  `assemble._thread_input` is the per-message header, which is `Re: <subject>` for every reply). So
  a query term that appears in the subject fires `TERM_OVERLAP` on **every** message.
* `PARTICIPANT_MATCH` reads `From`/`To`/`Cc`/`Reply-To` — and a named participant is usually on the
  recipient list of every message in the thread.
* `TEMPORAL_PROXIMITY`'s anchored disjunct is `inside_query_date_window`, and a thread that ran
  inside a one-day-granular window is inside it entirely.

So admission is all-or-nothing at thread granularity, and it carries **no** information that
distinguishes one message from another. `/tmp/rdisc23/p01_query_vs_fixture.py`, part C:

```
subject carries the term     fill size=16
subject does not             fill size=0
```

The consequence is DISC-01's acceptance failing outright — see R-DISC-017 — and the ranking
collapsing onto `POSITION_ADJACENCY` — see R-DISC-018.

**A case whose choice cannot be explained from the query alone.** Take the thread of
`/tmp/rdisc23/p02_disc01_pairs.py`: one subject line, `Re: Q3 borogrove slithy toves outgrabe plan`,
carried by all 24 messages. Six materially different queries — `borogrove`, `slithy`, `toves`,
`outgrabe`, `plan`, `borogrove slithy` — produce **the same included set, the same depths, and the
same reason on every row**:

```
queries: 6   pairs: 15   pairs whose included set DIFFERS: 0
reason components each query produced for one representative fill row:
  borogrove          (TERM_OVERLAP,) score=4
  slithy             (TERM_OVERLAP,) score=4
  ... all six identical
```

A reader given the response cannot recover *which* of the six was asked. The reason names a
mechanism, which is what DISC-01's guard demands — and the mechanism is the same mechanism with the
same value for every query, so the guard's requirement is satisfied while its purpose is not.

---

## Priority 2 — attacking `ADMITTING_COMPONENTS`, the implementer's own confession

The implementer's account of the defect is exactly right and I reproduce its diagnosis: two
components "fire without reading anything the caller wrote", so admitting on `score > 0` selected
the ±2 window. `ADMITTING_COMPONENTS` removes those two from admission. **It does not touch the
ordering, and the same two components are the whole of the ordering in the modal query class.**

`/tmp/rdisc23/p16_ordering_collapse.py`, 40 messages, 5 hits, one shared subject carrying the term,
query = one term:

```
admitted candidates: 35 of 35 non-hits
distinct scores    : [6, 4]
every candidate at the TOP score 6 -> [1, 2, 6, 7, 9, 10, 14, 15, 17, 18, 22, 23, 25, 26, 30, 31, 33, 34]
+/-2 window positions                 -> [1, 2, 6, 7, 9, 10, 14, 15, 17, 18, 22, 23, 25, 26, 30, 31, 33, 34]
|+/-2 window| = 18;  the top 18 of the query-aware ranking is exactly the +/-2 window? True
```

Every candidate scores 4 from `TERM_OVERLAP`. The **only** discriminating component is
`POSITION_ADJACENCY` — the one deliberately pinned to Baseline F(±2)'s radius. So the shipped
policy's preference order *is* Baseline F's selection, top-ranked, wearing a `QueryScoredFill`
reason that names `term_overlap, position_adjacency` and a score of 6.

**Is `ADMITTING_COMPONENTS` principled or a patch?** It is principled as far as it reaches: "a row
no component of the query reached carries no query-specific reason" is a real rule and it is the
right rule. But it is a rule about *admission* answering a problem that lives in *selection*, and
the round's evidence for it — `test_a_row_no_anchored_component_reached_is_not_filled` — builds a
row with **no** anchored component, which is the one case the patch was written for. Nothing tests
the case where every row has the same anchored component, which is the common one. The threshold is
declared as an addition to A.9(3); my finding is that the addition is necessary and not sufficient,
and that A.9(3) needs a second one about ordering.

**Is there a query class for which the fixed policy still reduces to ±2?** Yes, and it is the modal
one: any query whose anchored component fires uniformly over the thread. That is every subject-term
query, every `from:`/`to:` query naming a thread participant, and every date-window query over a
thread that ran inside the window. What the fix achieved is that the *admitted set* is now the whole
thread instead of the ±2 window; the *disclosed prefix under a binding budget* is still ±2-first.

---

## Priority 3 — the promotion rule, and whether it says no for the right reasons

**On OD-3's own 40/6 case the split is not 5-of-11-by-dependence. It is every parent and no child.**
`/tmp/rdisc23/p24_od3_case.py` reproduces the report's figures exactly (7,760 tokens, ceiling 9,000,
no step fired, 11 members, 5 promoted, efficiency 0.216 / 0.881) and then prints *which*:

```
Counter({('child', None): 6, ('parent', 'quotation'): 5})
```

5 of 5 parents promoted, 0 of 6 children promoted. The rule discriminated on **relation**, not on
dependence. The report offers "it promotes five of eleven" as evidence the rule sometimes says no;
on this input it says yes to every parent unconditionally and no to every child unconditionally.

### Where it should say no and does

`QUOTATION` fires on `incorporates_text_it_did_not_write(evidence.body)` — *any* `quoted` or
`forwarded` span anywhere in the evidence message. It never asks whether the parent is what was
incorporated. `/tmp/rdisc23/p09_promotion.py`:

```
evidence forwards an unrelated message; parent is 'ok' and was never quoted
dependence -> quotation
a one-word 'thanks' parent                 -> quotation
a parent with no observed text at all      -> quotation
```

My reasoning about "the evidence depends on it" is: the evidence cannot be read without the member
when the evidence's own text *incorporates the member's text*, or when the member *changes the
answer the evidence gives*. Clause 1 tests neither; it tests "did this message quote something".
Since Gmail replies quote by default, clause 1 is close to `relation is PARENT`. The wire then
carries `dependence: quotation` about a message the evidence never quoted — a mechanical-looking
claim that is false.

### Where it should say yes and does not

`CONTRADICTION` requires a token of A.8a's lexicon in `member.observed_text`. Two independent
failures, both reproduced:

1. **The lexicon does not contain the reversal A.9a itself quotes.** `/tmp/rdisc23/p20_contradiction_lexicon.py`:

```
  refused    "Actually, let's not - we're pushing to Q4."     <- A.9a's own example sentence
  refused    'Hold off on this for now please.'
  refused    'We are not going ahead with it.'
  refused    'Scratch that, the date has moved.'
  refused    'That is no longer happening.'
  PROMOTED   'We decided against it.'
  refused    'Cancelled.'                                     <- see R-DISC-027
```

2. **`observed_text` for a floor member is a snippet, so a reversal past the snippet boundary is
   invisible to the clause and invisible in the payload.** `/tmp/rdisc23/p11_promotion_depth.py`,
   end to end through the real client and transport:

```
   r-3 role=child depth=snippet promoted=None
       disclosed text = 'Thanks for putting the whole plan together, it reads well an'
       does the disclosed text contain the reversal? False
```

That is T-CD2's failure mode, produced by the mechanism written to mitigate it. (Honest caveat: the
synthetic mailbox truncates snippets at 60 chars where Gmail gives ~200, so this fixture overstates
the *rate*. The mechanism is not a fixture artifact — the clause reads only the snippet — but I did
not measure the rate on real mail and cannot.)

### The clause that can never fire

`CONSTRAINT_CARRIER` is `member.constraint_coverage - evidence.constraint_coverage`.
`constraint_coverage_of` returns `()` for any message with no admitting probe, i.e. for every
non-hit; and `floor_of` skips any candidate that is a hit. So on the shipped path a floor member's
coverage set is **always empty** and the difference is always empty.
`/tmp/rdisc23/p10_constraint_carrier.py` ran the whole `CORPUS` table plus a purpose-built
split-evidence thread and found **0** occurrences. `grep` confirms the only place
`FloorDependence.CONSTRAINT_CARRIER` is produced outside `floor.py` is
`tests/test_disclosure_round23.py:500` — the hand-built `PROMOTION_MATRIX`, which supplies the member
a coverage set the shipped path never gives it. That is round 21's R-RETR-058 lesson repeating in
the test the report cites *as* the answer to R-RETR-058.

---

## Priority 4 — floor membership at every degradation step

### The claim holds against the code's definition of the floor, and the definition has a hole

`assert_floor_intact` is genuinely driver-level, genuinely applied to the output of every step
whatever is passed, and the sixteen plants are real: I re-ran them and they pass, and I planted my
own (drop `CHILD` from `floor_of`) in the scratch tree and **five** tests went red. That machinery
works.

**But `floor_ids` is not A.9(2)'s floor.** `floor_of` skips a candidate member that is itself an
evidence message (`if member_id in hits or member_id in seen: continue`). A.9(2) says "*Each hit's*
reply parent and direct children are **always present in the response**" — it does not exempt a
parent that happens to also match. `/tmp/rdisc23/p04_floor_hole.py`:

```
floor members computed by the planner: [('t-m009','parent'), ('t-m012','child')]
is m11's reply parent (m10) in the floor?   False        # m10 and m11 are both hits
```

Step 8's guard is `row.id not in working.floor_ids`, so nothing protects it. Driven:
`/tmp/rdisc23/p04b_floor_hole.py`, 60-message chain, every message a hit (an ordinary outcome for a
term carried in every reply's quoted history), ceiling 1,000 / overflow 1,100:

```
floor members the planner computed: []   (empty!)
steps    : [(8, 'withheld_record')]
withheld : 44 ids
disclosed evidence messages whose A.9(2) floor member is ABSENT: 1
   t-m015 is disclosed; its direct child t-m016 is withheld and not in the payload
```

The withheld record carries an affordance, so nothing vanished *silently* — EV-03 survives. What
does not survive is OD-3's sentence: "membership is absolute — every message in that chain is always
in the response, **never a bare count**". A `withheld` record is a bare pointer.

**Why the round's own evidence cannot catch this.** Every floor assertion in the round —
`plan.layout.floor_ids <= plan.layout.present_ids` in the Hypothesis sweep, the sixteen plants,
`test_the_ladder_terminates_on_the_forty_message_six_hit_case` — checks the payload against
`floor_of`'s **own output**. `grep -n "parent_of\|children_of" tests/test_disclosure_round23.py`
returns five hits, all fixture *inputs*; **no test derives "reply parents and direct children of
every evidence message" from the reply tree and checks the payload against that.** It is
`digest(x) == digest(x)` — the cache tautology BLOCKER ADV-002 was written about, in the round's
biggest claim.

I confirmed the behaviour is pinned in **neither** direction: in the scratch tree I made `floor_of`
record hit-members too, and `tests/test_disclosure_round23.py` + `tests/test_region_kind_round19.py`
(84 tests) still pass; `/tmp/rdisc23/p04c.py` then shows the same input declares
`DisclosureLadderExhausted` instead of breaking the chain, which is A.9a's own prescribed outcome.

### Does the matrix reach what it asserts about?

Mostly. `test_the_shape_matrix_reaches_every_step_and_both_ceilings` is a genuine advance on round
21 and it does assert reach over the same tuple the property sweep consumes. Three gaps:

* `test_every_disclosure_shape_keeps_the_five_properties_that_make_the_ladder_honest` documents
  **five** properties and asserts **three**. Properties 2 (every floor member present) and 3 (every
  accounted message present or withheld) appear only in the docstring; `ShapeResult` discards the
  ids, so the matrix sweep *cannot* check them. The Hypothesis sweep does check both — against
  `floor_ids`, so see above.
* `_shape`'s exhausted branch returns `floor=True` as a **literal**, unmeasured. The report's printed
  matrix shows `floor True` for `floor_alone_exceeds_the_overflow` on that literal's authority, and
  `assert {shape.floor for shape in matrix} == {True, False}` consumes it.
* The matrix has no shape in which two hits stand in a parent/child relation, which is the shape the
  hole lives in, and no shape in which a degradation step *enlarges* the layout (R-DISC-019).

---

## Priority 5 — ceilings

### The response does exceed the ceiling it declares, once "the response" means what the host gets

`measure_tokens` counts disclosed row text plus `STUB_ROW_TOKEN_ESTIMATE` per stub row and per
collapsed run. It counts no key, no id, no `position`, no `role`, no `reason`, no `linkage`, no
`provenance`, no `unabridged` affordance, no `withheld[]`, no `not_included_sources[]`, no
`retrieval_report`, and not the text mirror WS-15 sends alongside `structuredContent`.
`/tmp/rdisc23/p15_wire_ratio.py`, every row through the real client, transport and `render`:

```
  msgs  measure_tok  ceiling  structured_chars  text_chars  total_chars  chars/measured_tok
     5         1200     9000             15035        9163        24198                20.2
    20         2500     9000             36132       20535        56667                22.7
    60         2900     9000             69812       31215       101027                34.8
   200         4300     9000            188006       68909       256915                59.7
   400         6300     9000            357006      122909       479915                76.2
   600         8300     9000            526006      176909       702915                84.7
```

The target client's cap is `_meta["anthropic/maxResultSizeChars"]`, **[VERIFIED] 25,000 chars with a
10,000-char warning** (AD PF-6). A **five-message** response is already at the cap while the ladder
reports 13 % of its budget spent. A 600-row response is **28×** the cap and declares itself inside
its ceiling. The host truncates; DISC-06's acceptance is "Responses truncated by the host: **0**
`[DEFINITIONAL]`".

I want to be scrupulous about what is round 23's and what is inherited. PF-6 is unresolved and both
ceiling *numbers* are `[DESIGN, set by PF-6]`, so the numbers are provisional by design. That is not
the defect. The defect is that the enforced quantity is not monotone in the wire size — the ratio
runs 20 → 85 across ordinary shapes — so **no** choice of token ceiling makes it an upper bound. AD
§D.4's own sentence "Both ceilings sit below the [VERIFIED] 25 k Claude Code cap so MailWeave authors
its own truncation" compares 9,000 tokens with 25,000 chars, which is a unit error; WS-11 built the
enforcement on top of it and did not surface it.

**What does hold, and I checked it independently:** the ladder's estimate and the envelope's estimate
are one number. `/tmp/rdisc23/p19_measure_equality.py`, five shipped-path shapes, `layout.cost() ==
measure_tokens(envelope)` with delta 0 every time. That is a real property and the round earned it.

### The overflow is used for depth, not for membership

A.9a: "**If and only if** the E2 floor's *membership* cannot be carried within it" … "Floor
membership is the **only** thing that may raise the ceiling." The code's condition is different:
ceiling still normal **and** some floor member present **and** steps 1–5 changed nothing. Those are
not the same predicate, and the implementer's own fixture shows the gap.
`/tmp/rdisc23/p03b_overflow.py` runs the exact fixture from
`test_a_ladder_step_that_removes_nothing_does_not_claim_a_truncation`:

```
steps : [(6, 'declared_overflow_ceiling')]     ceiling applied : 12000   tokens: 10740
bands x depths: {('floor','snippet'): 117, ('evidence','snippet'): 60, ('map','stub'): 3}
MEMBERSHIP COUNTERFACTUAL: all 180 present ids as bare 40-token stubs = 7200 tokens
normal ceiling = 9000
```

Floor *membership* fits the normal ceiling with 1,800 tokens to spare. The overflow bought snippet
*depth* for 117 floor rows and 60 evidence rows. `assemble._ceiling_of` then emits
`ceiling{normal:9000, applied:12000, why:"E2 floor membership"}` — the `why` is a hard-coded string
selected by `applied != normal`, not derived from anything. It is a false statement about why the
response is bigger, in the field the architecture created to make that statement true.

### A response the host would have to truncate, or no response at all

See R-DISC-019 and R-DISC-020: past ~650 disclosed rows the shipped path does not truncate itself —
it raises `DisclosureLadderExhausted` out of `assemble`, and nothing catches it.

---

## Priority 6 — are the weights fixed, and is the pinning real?

**Fixed: yes.** `E4_WEIGHTS` is a `MappingProxyType` over a literal dict with no other reference;
`grep` over `server/src`, `harness/src` and `tools` finds no code path that rebinds or mutates
`E4_WEIGHTS`, `E4_ADJACENCY_POSITIONS`, `E4_MINIMUM_FILL_SCORE` or `ADMITTING_COMPONENTS` — the only
importers are `__init__.py`'s re-export and `plan.py`'s three reads. `score_of` is a plain sum with
no normalisation, decay or per-query rescaling. R75's plant is caught. This one is solid and I say so.

**Pinning: real in effect, tautological in test.** `FixedWindow.radius: int = E4_ADJACENCY_POSITIONS`
— they are the same symbol, so `E4_ADJACENCY_POSITIONS == FixedWindow().radius` is true by
definition and the assertion's only load-bearing half is the literal `== 2`. That literal does work
(R74's plant to 6 is caught), and the shared symbol means the policy can never quietly out-reach the
default baseline. So the property is delivered; the *test* that claims to establish it establishes
one third of itself. I do not file this separately — it is folded into R-DISC-029.

---

## Priority 7 — is the comparison fair?

**Structurally, yes, and this is the round's best work.** `Selector` is the single point of
difference; both arms take the same `ceilings` through the same `disclose`, get the same `floor_of`,
the same promotion rule, the same `run_ladder`, the same `layout_tokens`. I tried three ways to make
the baseline lose unfairly and could not:

* *Different ceiling.* Impossible — `ceilings` is a parameter of `disclose`, not of the selector.
* *Different floor or promotion.* Impossible — `floor_members` never sees the selector.
* *Different degradation order.* `_score_of` maps `FixedWindow`'s offsets to 3/2/1 while the shipped
  arm's rows carry 4–15, so within the FLOOR band the two arms could order degradation differently.
  `/tmp/rdisc23/p21_arm_symmetry.py` shows the scores do differ (6 vs 2) but on every input I built
  the score was uniform within the band and the ordering degenerated to `-position` in both arms. I
  could not turn the asymmetry into an outcome. The implementer flagged this as a trusted peer; my
  finding is that it is a latent asymmetry and not a demonstrated unfairness.

**But the round's evidence that the baseline is not handicapped is a fixture artifact.**
`test_the_baseline_is_not_handicapped_by_the_planner` uses `chain_thread(hit_subject_term=True)`,
which puts the query term in the subject of the *hits only*. Gmail puts one subject on every message.
`/tmp/rdisc23/p21_arm_symmetry.py`:

```
round-23 fixture (term on hit subjects only) shipped fills   0   baseline fills   9   baseline >= shipped? True
shared subject line carrying the term        shipped fills  16   baseline fills   9   baseline >= shipped? False
```

So the assertion `len(baseline_fill) >= len(shipped_fill)` is true of the fixture and false of the
modal real case. The claim it is offered for — that nothing is shaped to disadvantage the baseline —
I still believe, on the structural argument above. The test is not evidence for it.

**And the "equal budget" is equal in a quantity that is not the budget.** DISC-02 requires equality
"asserted by the harness from measured tokens". Both arms are equal in `layout_tokens`, which
R-DISC-022 shows is 20–85× away from the bytes either arm actually costs the caller — and the ratio
depends on *row count*, which is exactly what the two arms differ in. The shipped arm fills 16 rows
where the baseline fills 9, so at equal `layout_tokens` the shipped arm sends materially more wire.
That is not a fairness defect in the planner; it is DISC-02's acceptance not yet being satisfiable.

---

## Priority 8 — does `reductions[]` record every step?

Two gaps, both reproduced.

**A depth demotion removes text and leaves no record.** `/tmp/rdisc23/p13_reductions_record.py`:

```
depth=body_clean  kept=None  disclosed_tokens=  600  reductions=[('body_head_truncated', 3800, 600)]
depth=body_clean  kept=250   disclosed_tokens=  250  reductions=[('body_head_truncated', 5900, 250)]
depth=snippet     kept=None  disclosed_tokens=   25  reductions=[]
depth=stub        kept=None  disclosed_tokens=    0  reductions=[]
```

`PlannedRow.rendered()` emits a `body_head_truncated` record only on the head-truncation branch. The
`body_clean → snippet` rung of steps 3 and 4 drops ~1,150 tokens of text this response *holds*, and
the `snippet → stub` rung of step 1 drops the snippet, and neither leaves a count. The `depth` field
and the `unabridged` affordance are both present and correct — which is why I grade this MEDIUM and
not HIGH — but DISC-03's acceptance is "every … truncated body carries a **size count** of what was
removed"; "silent reductions: **0**".

**The step list never reaches the wire.** `disclosure.steps` is consumed in exactly two places
(`assemble.py:1413`, `assemble.py:2051`): a boolean for `truncated_by`, and adding one
`disclosed_token_ceiling` name to `budget_caps_hit`. `/tmp/rdisc23/p14_wire.py` greps the rendered
`structuredContent`:

```
   'A.9a'                       present: False
   'step' / 'precedence'        present: False
   'e4_query_scored_fill'       present: False
   'declared_overflow_ceiling'  present: False
```

The `LadderStep.detail` lines — "N row(s) reduced in depth; X -> Y tokens (estimate)" — are computed
and discarded. A.9a: "each step is declared in `reductions[]` and named in `budget_caps_hit`. **Order
is the contract: the reader must be able to reconstruct what was sacrificed first.**" The reader
cannot. The work order names this bullet as normative.

**What does hold.** I attacked EV-03's "nothing is dropped without a record" and could not break it.
`accounted_ids` is `frozenset(ledger.origins)` and covers every mapped member on the shipped path
(`/tmp/rdisc23/p18_accounted.py`, `p18b.py`: `present - origins` is empty in both), so
`assert_nothing_vanished`'s guard is not narrowed by its `& accounted_ids`; `DispositionLedger.certify`
computes `withheld := H − disclosed`; `Source._a_claimed_map_accounts_for_every_message` forces every
position to be a row, a run member or a withheld record. Steps 7 and 8 both file records with
executable affordances. That half of EV-03 is real.

---

## Priority 9 — the largest honest gap, judged

The implementer names "a promoted floor member whose body was never fetched stays at `snippet`" as
the round's largest gap and says it "does not block integration". **The first half understates it and
the second half is right.**

It understates it because promotion currently buys **nothing at all** on the shipped path.
`/tmp/rdisc23/p11_promotion_depth.py`, on the round's own end-to-end fixture:

```
   e-1 role=parent   depth=snippet     promoted=quotation
   e-3 role=child    depth=snippet     promoted=contradiction
   e-4 role=stub     depth=stub        promoted=None
```

`FLOOR_BASE_DEPTH` is `snippet` and a promoted member reaches `snippet`. Thread maps are fetched
`format=metadata`, so a floor member never has a body, so `depth_for` always falls back. Both promoted
rows are byte-identical in *content* to an unpromoted one; the only difference is the reason string.
So OD-3's split — "membership is guaranteed, **depth is earned**" — has an implemented first half and
an unimplemented second half. It is not "narrower than it should be"; it is the whole effect. Add
R-DISC-024 (clause 3 dead, clause 1 undiscriminating, clause 2 lexicon-blind) and what ships is a
label attached by a rule that is right about roughly half the cases it is asked.

It does not block integration: OD-6's six milestone criteria are about the server starting,
connecting, being driven, carrying handles/scope/provenance, a smoke test and a review. None of them
turns on promotion depth. I agree with the implementer's urgency call and disagree with its
characterisation.

---

## Findings

```
ID:            R-DISC-017
Severity:      HIGH
Reachability:  REACHABLE today. Modal case: any query whose terms appear in the thread subject
               Gmail sends on every message, or which names a participant on every message, or
               which carries a date window the thread sits inside.
Blocks milestone? NO for OD-6's six criteria. YES for any claim that WS-11 delivered its exit
               condition ("what is disclosed depends on the query"), and this is a reachable
               correctness defect, so §5a says fix it now.
Rubric:        DISC-01 (its acceptance, directly), DISC-02 (the arm being compared).
Location:      server/src/mailweave/disclosure/weights.py, `components_of` - TERM_OVERLAP reads
                 `_tokens(candidate.subject)`, a thread-level fact.
               server/src/mailweave/disclosure/weights.py, `ADMITTING_COMPONENTS` - all three
                 admitting components are thread-constant in the common case.
               server/src/mailweave/retrieval/assemble.py:1330 `_subject_of(by_id[message_id])`
                 supplies the per-message subject, which Gmail makes identical across a thread.
Repro:         /tmp/rdisc23/p02_disc01_pairs.py - one 24-message thread, subject
                 "Re: Q3 borogrove slithy toves outgrabe plan" on every message, six queries:
                 queries: 6   pairs: 15   pairs whose included set DIFFERS: 0
                 every fill row's reason, for all six: (TERM_OVERLAP,) score=4
               /tmp/rdisc23/p01_query_vs_fixture.py part A - depth map identical: True
Expected:      DISC-01: "For a fixed thread and a set of >=5 differing queries, the included message
               sets differ in >= [UNSET] of pairs, and each inclusion carries a query-specific
               reason. Identical output for materially different queries: flagged and investigated."
Actual:        0 of 15 pairs differ; the reason is identical in kind and in value for all six.
Required fix:  Make the admitting predicates message-discriminating. Two candidates, both cheap and
               neither a new number: (a) score TERM_OVERLAP over `observed_text` alone and let the
               subject contribute only where it *differs* from the thread's modal subject (Gmail
               already gives "subject-if-changed" its own slot in A.9(4)); (b) require the anchored
               component to be one that separates candidates within the thread - if a component
               fires on every candidate of a thread it ranks but does not admit, which is the same
               rule ADMITTING_COMPONENTS already applies to POSITION_ADJACENCY, applied to the
               thread rather than to the component. Then add a test that runs >=5 queries over one
               thread whose subject carries all of their terms and asserts the included sets differ.
```
```
ID:            R-DISC-018
Severity:      HIGH
Reachability:  REACHABLE-IN-POLICY today, and REACHABLE in disclosure whenever the budget binds.
Blocks milestone? NO for OD-6's six. YES for DISC-01/DISC-02 being answerable at all: the shipped
               arm's preference order is the baseline's selection, so the comparison WS-16 runs
               would measure two orderings that agree at the top.
Rubric:        DISC-01 (its degenerate-strategy guard, "a fixed +/-2 policy fails DISC-01 by
               construction"), DISC-02.
Location:      server/src/mailweave/disclosure/weights.py, `rank` - sorts by (-value, position);
                 `ADMITTING_COMPONENTS` narrows admission and touches nothing about ordering.
               server/src/mailweave/disclosure/weights.py, `E4_ADJACENCY_POSITIONS` - the only
                 component that separates candidates once TERM_OVERLAP is thread-constant.
               docs/reviews/ROUND_23/IMPLEMENTER.md Part 0 - "The other components keep their
                 published weight and rank the admitted rows; they no longer admit any." That is
                 the defect stated as the repair.
Repro:         /tmp/rdisc23/p16_ordering_collapse.py - 40 messages, 5 hits, shared subject, one term:
                 admitted candidates: 35 of 35 non-hits;  distinct scores: [6, 4]
                 score-6 positions   -> [1,2,6,7,9,10,14,15,17,18,22,23,25,26,30,31,33,34]
                 Baseline F +/-2     -> [1,2,6,7,9,10,14,15,17,18,22,23,25,26,30,31,33,34]
                 the top 18 of the query-aware ranking is exactly the +/-2 window? True
               /tmp/rdisc23/p17_binding_budget.py - at a binding ceiling the survivors are a
                 prefix-plus-remainder of that order rather than the window exactly, because
                 `_degrade_band` stops as soon as the layout fits; the ordering is the finding.
Expected:      The published policy's preference order must not coincide with Baseline F's selection
               for the modal query class. DISC-01's guard names this policy by construction.
Actual:        For a one-term query on a shared subject line the E4 score has two values, and the
               top value is exactly Baseline F's +/-2 window, position for position.
Required fix:  Fix R-DISC-017 (a discriminating anchored component removes the tie), and add the
               ordering half of the admission rule to A.9(3) as a published amendment: a candidate's
               *rank* may not be decided by query-independent components alone. Execute it:
               assert that on a thread where every candidate fires the same anchored component the
               E4 ranking is NOT the +/-2 window - the test is three lines and it is the one this
               round is missing.
```
```
ID:            R-DISC-019
Severity:      HIGH
Reachability:  REACHABLE today, on the shipped path, with the shipped ceilings. Structural on real
               mail, not a fixture artifact: Gmail's snippet is <=~200 chars, i.e. <=~36 whitespace
               tokens, and STUB_ROW_TOKEN_ESTIMATE is 40, so `snippet -> stub` raises the estimate
               for every real row.
Blocks milestone? YES - this is a critical correctness defect under OD-6's counter-rule. A response
               300 tokens over the ceiling is tripled by the ladder and then refused.
Rubric:        DISC-06, DISC-03, DISC-04, and A.9a's own precedence.
Location:      server/src/mailweave/disclosure/layout.py, `PlannedRow.cost` - a stub row costs
                 STUB_ROW_TOKEN_ESTIMATE (40); a snippet row costs count_tokens(text) and nothing
                 for its own structure. A snippet row is therefore *cheaper* than a stub row.
               server/src/mailweave/envelope/measure.py:19,34 - the same asymmetry, inherited.
               server/src/mailweave/disclosure/ladder.py, `_to_snippet_or_stub`,
                 `_degrade_without_head_truncation` (step 1), `_degrade_through_head_truncation`
                 (steps 3, 4) - every one of them contains the snippet -> stub transition.
               server/src/mailweave/disclosure/ladder.py, `_degrade_band` - `while working.cost() >
                 target` keeps degrading while the cost rises, so the inflation runs away.
               tests/test_disclosure_round23.py, `test_a_step_only_ever_lowers_a_rows_depth` -
                 monotone in *depth*, silent about *cost*. This is the peer that was trusted.
Repro:         /tmp/rdisc23/p08_step1_inflates.py - 310 rows at a 30-token snippet, 300 tokens over:
                 row at snippet depth costs    : 30
                 SAME row degraded to stub cost: 40
                   step 1 e4_query_scored_fill    9300 ->   12370
                   step 8 withheld_record        12370 ->   12280
                 *** DisclosureLadderExhausted: still ~12280 against a ceiling of 12000
               /tmp/rdisc23/p07_exhausted_why.py - the same on the SHIPPED path, 700 messages:
                   step 1 e4_query_scored_fill    9300 ->   27270
                 pre-ladder cost 9,300; post-ladder 23,970.
Expected:      A degradation step reduces the measured size, or it is not a degradation step. A.9a's
               ladder is a ladder.
Actual:        Steps 1, 3 and 4 enlarge the layout whenever the row's snippet is shorter than 40
               whitespace tokens, which is every Gmail snippet.
Required fix:  Charge a row its structural cost regardless of depth: `cost()` becomes
               STUB_ROW_TOKEN_ESTIMATE + count_tokens(text or ""), in `layout.py` AND in
               `envelope/measure.py` together (they must stay one measure - that property is real
               and must not be broken to fix this). Then add the missing monotonicity assertion:
               `after.cost() <= before.cost()` for every step but 6, asserted in `run_ladder`
               beside the two existing gates, so it covers a step nobody has written yet. Note that
               the fix raises every measured response, so PF-6's ceilings must be re-derived after
               it, and R-DISC-022 must be fixed in the same pass or the new numbers are as
               disconnected from the wire as the old ones.
```
```
ID:            R-DISC-020
Severity:      HIGH
Reachability:  REACHABLE today, end to end, through `assemble` behind httpx.MockTransport. Currently
               entangled with R-DISC-019, which is what drives ordinary inputs into it; it is
               independently reachable whenever the floor alone exceeds the overflow.
Blocks milestone? YES. OD-6 criterion 3 is "Claude can invoke it and successfully search for and
               retrieve a real email or thread". On a large thread the tool call raises instead of
               answering, and D.11's partition makes a budget refusal an in-band declared result,
               never a protocol error.
Rubric:        DISC-06, EV-03, MCP-side D.11 partition; AD A.9a step 8.
Location:      server/src/mailweave/disclosure/ladder.py, `run_ladder` - raises
                 DisclosureLadderExhausted.
               server/src/mailweave/retrieval/assemble.py:1934 `disclose(...)` - not guarded.
               server/src/mailweave/surface/server.py:132-149 `_dispatch` - catches ToolRefused,
                 HandleRefused, ArgumentInvalid. DisclosureLadderExhausted is a MailweaveError and
                 is in none of them, and `mailweave.errors.ERROR_SURFACE` has no code for it, so it
                 escapes to the JSON-RPC layer as an internal error with no remediation and no
                 affordance.
               The exception text also asserts a cause it did not check: "the remaining payload is
                 floor membership". In /tmp/rdisc23/p08 the remaining payload is 310 fill and
                 evidence rows and one floor member.
Repro:         /tmp/rdisc23/p06_shipped_band.py - one thread, every message matching:
                 per=  600  tokens=8300 ceiling=9000  (fits)
                 per=  700  *** DisclosureLadderExhausted escapes assemble()
                 per= 1000  *** DisclosureLadderExhausted escapes assemble()
Expected:      "an inability declared where it occurs, never a response handed to the host to cut"
               (ladder.py's own docstring). A declared inability is an in-band result or a D.11
               refusal with a code and an executable retry - not a stack trace.
Actual:        An unhandled exception out of the tool handler.
Required fix:  Give it a D.11 code on the Surface.TOOL_ERROR side (or, better, make it in-band: the
               honest response is every hit as a withheld record plus `not_included_sources[]`,
               which is what step 8 was for). Catch it in `surface/server.py::_dispatch` and add it
               to ERROR_SURFACE so `declined` can assert against the table. Derive the exception's
               "what is left" sentence from the layout instead of asserting it. Add an end-to-end
               test at a thread size that reaches it - `tests/test_lexical_ladder.answer` with ~700
               matching messages does it today.
```
```
ID:            R-DISC-021
Severity:      HIGH
Reachability:  REACHABLE today: any thread in which one hit is the reply parent or direct child of
               another hit, plus a ceiling that reaches step 8. Adjacent hits are the norm for a
               term carried in a thread's quoted history.
Blocks milestone? NO for OD-6's six criteria; YES as a critical correctness defect - it is the
               silent failure of the guarantee the work order calls "the biggest claim in the
               project", and it is reachable, so §5a says today.
Rubric:        OD-3 (membership absolute), AD A.9(2), A.9a, T-CD2; DISC-01's Verify clause ("the
               only test of the non-negotiable E2 reply-chain floor").
Location:      server/src/mailweave/disclosure/floor.py, `floor_of`:
                 `if member_id in hits or member_id in seen: continue`
                 The `in hits` clause is right about not emitting a second *record* and wrong about
                 dropping the id from the *protection set*.
               server/src/mailweave/disclosure/ladder.py, `step_8_withheld_record` - its guard
                 `row.id not in working.floor_ids` is therefore a no-op, which the implementer
                 noticed (report, "Have I trusted a peer?" item on R72) and read as "the clause is
                 harmless" rather than "the floor is under-computed".
               server/src/mailweave/disclosure/ladder.py, `assert_floor_intact` - checks
                 `before.present_ids & before.floor_ids`, so it can only ever defend what
                 `floor_of` put in.
               tests/test_disclosure_round23.py - every floor assertion is against
                 `layout.floor_ids` / `plan.threads[i].floor`. `grep -n "parent_of|children_of"`
                 returns fixture inputs only. Nothing derives A.9(2)'s floor independently.
Repro:         /tmp/rdisc23/p04_floor_hole.py - two adjacent hits m10 (parent) and m11 (child):
                 floor members computed by the planner: [('t-m009','parent'), ('t-m012','child')]
                 is m11's reply parent (m10) in the floor?   False
               /tmp/rdisc23/p04b_floor_hole.py - 60-message chain, every message a hit,
                 Ceilings(normal=1000, overflow=1100):
                 floor members the planner computed: []      steps: [(8,'withheld_record')]
                 disclosed evidence messages whose A.9(2) floor member is ABSENT: 1
                   t-m015 is disclosed; its direct child t-m016 is withheld and not in the payload
               /tmp/rdisc23/p04c.py (scratch tree, PYTHONPATH asserted) - with `floor_of` recording
                 hit-members, the same input declares DisclosureLadderExhausted instead, which is
                 A.9a's own prescribed outcome; and the scratch run of
                 tests/test_disclosure_round23.py + tests/test_region_kind_round19.py (84 tests)
                 passes unchanged, so the current behaviour is pinned in neither direction.
Expected:      AD A.9(2): "Each hit's reply parent and direct children are ALWAYS PRESENT in the
               response; they are never absent, never reduced to a bare count." OD-3: "membership is
               absolute". No exemption for a member that is itself a hit.
Actual:        A hit that is another hit's parent or child is outside `floor_ids` and step 8 removes
               it. The surviving hit's reply chain has a hole, filled by a withheld record.
Required fix:  Two separable changes, both needed.
               (1) Record hit-members in `floor_of` (relation and anchor as now, `dependence=None`
                   since they are already at evidence depth) so `floor_ids` is A.9(2)'s set, and let
                   `plan_thread`'s existing hit-first branch keep them banded EVIDENCE so no second
                   disposition is created. A.7a is satisfied by the banding, not by the omission.
               (2) Stop checking the floor against its own derivation. Add a test that computes
                   `{parent_of[h]} | children_of[h]` for every h in `hit_ids` straight from the
                   ThreadInput and asserts that set is inside `layout.present_ids` at every step and
                   at both ceilings - over the shape matrix and the Hypothesis sweep. Without (2)
                   the next omission in `floor_of` is invisible in exactly the same way.
```
```
ID:            R-DISC-022
Severity:      HIGH
Reachability:  REACHABLE today. A five-message response already reaches the target client's default
               cap while declaring 13% of its ceiling spent.
Blocks milestone? YES for DISC-06 as written ("Responses truncated by the host: 0 [DEFINITIONAL]")
               and for OD-6 criterion 3 in practice, since a host-truncated payload is a payload
               Claude cannot read to the end. NOT a blocker on the ceiling *numbers*, which are
               PF-6's and provisional by design.
Rubric:        DISC-06 (primary), DISC-04 (the efficiency figures are in the same units), DISC-05
               (FLAT_MAP_MESSAGE_BOUNDARY is derived from this estimate), PART-05's guard.
Location:      server/src/mailweave/envelope/measure.py, `measure_tokens` - counts row text plus 40
                 per stub row and per collapsed run. Not counted: every JSON key, id, position,
                 role, reason, depth, linkage, provenance and unabridged affordance on every row;
                 `withheld[]`; `not_included_sources[]`; `retrieval_report`; `asked_for`; and the
                 text mirror `surface/partition.declared_result` sends beside structuredContent.
               server/src/mailweave/envelope/response.py:604 - the ceiling is enforced against it.
               server/src/mailweave/disclosure/layout.py, `layout_tokens` - the same measure.
               docs/ARCHITECTURE_DECISION.md:1212 - "Both ceilings sit below the [VERIFIED] 25 k
                 Claude Code cap": 9,000 *tokens* against 25,000 *chars*. Inherited unit error;
                 WS-11 built the enforcement on it without surfacing it.
Repro:         /tmp/rdisc23/p15_wire_ratio.py (real client, real transport, real `render`):
                 msgs  measure_tok  ceiling  structured_chars  text_chars  total_chars  ratio
                    5         1200     9000             15035        9163        24198   20.2
                   20         2500     9000             36132       20535        56667   22.7
                  200         4300     9000            188006       68909       256915   59.7
                  600         8300     9000            526006      176909       702915   84.7
               Cap: `anthropic/maxResultSizeChars` = [VERIFIED] 25,000 chars, 10,000 warning (PF-6).
Expected:      "MailWeave is the author of its own truncation." A ceiling that binds the response.
Actual:        The enforced quantity is 1/20th to 1/85th of the response, and the ratio moves with
               row count, so no constant conversion makes it an upper bound.
Required fix:  Measure the thing that is sent. Serialise the rendered `structuredContent` plus the
               text mirror and count *characters* against a character ceiling - the host's own unit,
               and the only one `maxResultSizeChars` can be compared with. Keep the "one measure"
               property: `layout` must estimate the same characters the envelope measures, which
               means the layout has to carry a per-row structural constant that reflects the wire
               row (this is the same edit R-DISC-019 needs, done once). PF-6 then registers a char
               ceiling instead of a token ceiling, and AD D.4/A.9a's 9,000/12,000 are restated in
               chars. Until that lands, no DISC-04 or DISC-05 number computed in these units should
               be quoted anywhere - including the 0.216 / 0.881 in the round-23 report.
```
```
ID:            R-DISC-023
Severity:      MEDIUM
Reachability:  REACHABLE today - it fires on the implementer's own fixture, in the round's own test
               `test_a_ladder_step_that_removes_nothing_does_not_claim_a_truncation`.
Blocks milestone? NO - rides along. But it puts a false mechanical statement on the wire, which is
               the honesty class this project exists to prevent, so I do not soften it.
Rubric:        DISC-06, OD-3, AD A.9a step 6 and D.2's `ceiling{}` field note.
Location:      server/src/mailweave/disclosure/ladder.py, `step_6_declared_overflow` - three
                 conditions, none of which is "floor membership cannot be carried at the normal
                 ceiling". "Steps 1-5 have nothing left to give" is not that predicate: steps 3 and
                 4 stop at `snippet` by design, so a response made of snippets exhausts 1-5 with
                 every id still affordable as a 40-token stub.
               server/src/mailweave/retrieval/assemble.py:1424-1428, `_ceiling_of` -
                 `why="E2 floor membership" if applied != NORMAL_CEILING_TOKENS else None`. The
                 reason is selected by the number, not derived from the cause.
               server/src/mailweave/envelope/wire.py, `Ceiling._overflow_is_declared` - requires a
                 non-empty `why`; does not and cannot check that it is true.
Repro:         /tmp/rdisc23/p03b_overflow.py - the fixture from
                 tests/test_disclosure_round23.py::test_a_ladder_step_that_removes_nothing_...:
                 steps: [(6,'declared_overflow_ceiling')]   ceiling: 12000   tokens: 10740
                 floor members: 117 at snippet; every present id as a bare stub = 7200 tokens
                 normal ceiling = 9000  -> membership was affordable with 1,800 to spare
               Wire: ceiling{normal:9000, applied:12000, why:"E2 floor membership"}.
Expected:      A.9a: "IF AND ONLY IF the E2 floor's membership cannot be carried within it ... Floor
               membership is the ONLY thing that may raise the ceiling."
Actual:        The overflow is raised whenever steps 1-5 are exhausted and any floor member exists,
               and is spent on snippet depth for floor and evidence rows alike.
Required fix:  Make step 6 compute the counterfactual it claims: raise only if the layout with every
               floor member reduced to its cheapest present form (a stub row, or a collapsed-run
               member) still exceeds the normal ceiling. Derive `ceiling.why` from that computation
               and carry the number it produced, so the field states a fact the payload can be
               checked against. Then add the missing rung the exhaustion exposes: A.9a's steps 3
               and 4 stop at snippet, so there is nothing between "floor at snippet" and "raise the
               ceiling" - if that is intended, step 6's precondition must say so; if it is not, the
               document needs a step, and that is an owner-visible amendment, not an implementer's.
```
```
ID:            R-DISC-024
Severity:      MEDIUM
Reachability:  REACHABLE today, all three clauses.
Blocks milestone? NO - rides along. But clause 3 is dead code with a wire vocabulary member and a
               test that reaches it only through hand-built inputs, which is R-RETR-061's rule
               ("a citation that does not catch is worse than no citation") one level up.
Rubric:        OD-3 (promotion "when the evidence depends on it"), AD A.9(2), T-CD2, DISC-01.
Location:      server/src/mailweave/disclosure/floor.py, `incorporates_text_it_did_not_write` -
                 reads `any(span.classification in INCORPORATED_SPANS for span in body.spans)`, i.e.
                 "did the evidence quote *anything*", never "did it quote this parent".
               server/src/mailweave/disclosure/floor.py, `dependence_of` clause 3 -
                 `member.constraint_coverage - evidence.constraint_coverage`; on the shipped path a
                 floor member is never a hit (`floor_of` skips hits) and
                 `retrieval/signals.constraint_coverage_of` returns () for a message with no
                 admitting probe, so the left operand is always empty.
               server/src/mailweave/disclosure/floor.py, `carries_a_decision_cue` - reads the
                 member's snippet, since thread maps are format=metadata.
               tests/test_disclosure_round23.py:500 - the only producer of CONSTRAINT_CARRIER
                 anywhere outside floor.py, in a hand-built matrix.
Repro:         /tmp/rdisc23/p09_promotion.py:
                 evidence forwards an unrelated message; parent is 'ok', never quoted -> quotation
                 a parent with no observed text at all                                -> quotation
               /tmp/rdisc23/p10_constraint_carrier.py - the whole CORPUS table plus a purpose-built
                 split-evidence thread: constraint_carrier occurrences: 0 (the split-evidence
                 messages all became hits, so there was no floor member to carry the constraint).
               /tmp/rdisc23/p20_contradiction_lexicon.py - 8 of 10 ordinary reversals refused,
                 including A.9a's own quoted example "Actually, let's not - we're pushing to Q4."
               /tmp/rdisc23/p24_od3_case.py - on OD-3's 40/6 case:
                 Counter({('child', None): 6, ('parent','quotation'): 5})
Expected:      "A floor member is promoted only when the evidence message it hangs off cannot be
               read without it", and a matrix that reaches every answer it asserts about.
Actual:        Clause 1 is `relation is PARENT` in disguise; clause 2 misses most reversals and can
               only see the first ~200 characters; clause 3 cannot fire on any input this system
               produces.
Required fix:  Clause 1: check that the evidence's incorporated span actually derives from the
               parent - A7's spans carry the signal that classified them, and a quoted span whose
               text is a prefix of the parent's observed text is a mechanical test that does not
               need a new number. Where that cannot be decided, refuse (an absent input is an
               absence). Clause 3: either give it a producer - `admitted_by` per decomposition probe
               already distinguishes which constraint admitted which message, so a *hit* that is
               another hit's parent/child is the natural carrier once R-DISC-021 records those -
               or remove the vocabulary member and say why. Clause 2: state in floor.py that the
               clause sees only what the observation carried, and file the lexicon's coverage as a
               PF-13 dependency rather than as a property of this rule. Then re-point
               `test_the_promotion_rule_matrix_reaches_every_answer_it_asserts_about` at inputs the
               *planner* produces, not at hand-built MemberFacts.
```
```
ID:            R-DISC-025
Severity:      MEDIUM
Reachability:  REACHABLE today - it is the shipped behaviour on every response.
Blocks milestone? NO - rides along, and I agree with the implementer that it does not block OD-6.
               I disagree with calling it a narrowing: it is the entire effect of the rule.
Rubric:        OD-3 ("membership is guaranteed, depth is earned"), AD A.9(2), DISC-05's depth
               vocabulary instrumentation, T-CD2.
Location:      server/src/mailweave/disclosure/floor.py, FLOOR_BASE_DEPTH = SNIPPET,
                 FLOOR_PROMOTED_DEPTH = BODY_CLEAN.
               server/src/mailweave/disclosure/plan.py, `depth_for` - a body depth needs a fetched
                 body; thread maps are format=metadata (assemble `_thread_input`, bodies only from
                 `run.bodies`), so a floor member never has one.
Repro:         /tmp/rdisc23/p11_promotion_depth.py, on the round's own end-to-end fixture:
                 e-1 role=parent depth=snippet promoted=quotation
                 e-3 role=child  depth=snippet promoted=contradiction
                 e-4 role=stub   depth=stub    promoted=None
               Both promoted rows carry the same depth an unpromoted member gets. The `FloorPromoted`
               reason is the only difference in the payload.
Expected:      OD-3: "Structurally necessary parents and children are promoted to deeper content
               when the evidence depends on them."
Actual:        Promotion decides a label. No response this system produces discloses more text
               because of it.
Required fix:  Either build the budgeted fetch the implementer scoped (A.7's `max_body_fetches`
               remainder, spent by WS-10's accountant, not by disclosure - T-CD3 forbids disclosure
               initiating it), or state in OD-3's own terms that depth is not currently earned by
               anything and let the owner see that the split they accepted has one implemented half.
               Whichever, `FloorPromoted` must not read as a depth claim while it is only a reason:
               add the achieved depth to the record, or name the affordance that would reach it.
```
```
ID:            R-DISC-026
Severity:      MEDIUM
Reachability:  REACHABLE today, in both arms, on every response where step 3 fires.
Blocks milestone? NO - rides along.
Rubric:        EV-02 (its second guard names this policy by name), DISC-01, RANK-03, A.9a step 3.
Location:      server/src/mailweave/disclosure/ladder.py, `_top_k_hit_ids` - sorts by
                 `(-row.fill_score, row.position)`. Every EVIDENCE row's `fill_score` is 0, because
                 `QueryAwareFill.select` ranks `_candidates(thread)` which excludes hits, and
                 `FixedWindow.select` skips hits explicitly. So the tie-break IS the selection.
               server/src/mailweave/disclosure/ladder.py, DISCLOSURE_TOP_K_HITS docstring - "Which
                 hits are the top k is decided by the published E4 score (weights.py), ties by
                 thread position. Deliberately not by recency and not by arrival order."
               server/src/mailweave/disclosure/ladder.py, `_degrade_band` for Band.EVIDENCE - the
                 same uniform 0 means the degradation order is `-position`, i.e. newest hit first.
Repro:         /tmp/rdisc23/p12_scoring_claims.py part 2, 30 messages, 10 hits:
                 arm=query_aware_e4          distinct evidence fill_scores=[0]
                    protected top-5 = the 5 EARLIEST hits by position? True
                 arm=baseline_f_fixed_window distinct evidence fill_scores=[0]
                    protected top-5 = the 5 EARLIEST hits by position? True
Expected:      A.9a step 3 protects the top-k hits by the published score. EV-02's guard: "a fixed
               newest-K or oldest-K policy passes the mean but fails the per-position bar by
               construction."
Actual:        Oldest-K by thread position keeps its body; newest-first loses depth. Which hits keep
               body depth is a pure function of position, in both arms.
Required fix:  Score the hits. `_candidates` already excludes them so that the floor and the fill do
               not compete for budget; that is a reason not to let a hit be *admitted* by the fill,
               not a reason to leave its score at 0. Compute `score(candidate, query)` for every hit
               and store it on the row (the components are all available for a hit - it has a body,
               addresses, a date and a position), use it in `_top_k_hit_ids` and in `_degrade_band`,
               and assert that the protected set is NOT the first k by position on a thread where
               the scores disagree with the order. Fix the docstring either way.
```
```
ID:            R-DISC-027
Severity:      MEDIUM
Reachability:  REACHABLE today. A decision verb at the end of a sentence is its commonest position.
Blocks milestone? NO - rides along.
Rubric:        DISC-01 (the E4 DECISION_CUE component), OD-3/T-CD2 (the CONTRADICTION clause),
               and PF-13's lexicon base rate, which inherits it.
Location:      server/src/mailweave/query/analysis.py, `content_tokens` - the token regex is
                 `[\w'/@.-]+`, which treats `.` as a word character (so addresses and dates survive
                 intact). A trailing full stop therefore stays attached to the word.
               server/src/mailweave/disclosure/weights.py, `_tokens` docstring - "`content_tokens`
                 rather than `str.split` so that `"decided,"` and `"decided"` are one token: a
                 lexicon match that depended on the punctuation next to a word would fire on the
                 corpus somebody wrote and not on the mailbox." The comma case works; the period
                 case, which the sentence is about, does not.
               server/src/mailweave/disclosure/floor.py, `carries_a_decision_cue` - same tokenizer.
Repro:         /tmp/rdisc23/p20_contradiction_lexicon.py and the follow-up one-liner:
                 'decided,'  -> ['decided']   cue=True
                 'Decided!'  -> ['decided']   cue=True
                 'approved;' -> ['approved']  cue=True
                 'decided.'  -> ['decided.']  cue=False
                 'Cancelled.'-> ['cancelled.'] cue=False
Expected:      The docstring's own sentence, executed. A lexicon match must not depend on the
               punctuation next to the word.
Actual:        Every decision verb that ends a sentence is invisible to DECISION_CUE, to the
               promotion rule's CONTRADICTION clause, and to TERM_OVERLAP for a query term in the
               same position.
Required fix:  Strip a trailing `.` (and `-`) from a token that is not itself an address, a date or
               a decimal - `analysis.py` already distinguishes those shapes for `_DATE_LIKE_RE`.
               This is a `query/` change with consumers in three modules, so it needs its own test
               naming all three. Then execute the weights.py docstring: assert `content_tokens` maps
               `decided.`, `decided,`, `decided!` and `decided` to one token.
```
```
ID:            R-DISC-028
Severity:      MEDIUM
Reachability:  REACHABLE today for the snippet -> stub half (A.9a step 1, which fires on the shipped
               path); REACHABLE in the layout for the body_clean -> snippet half, and on the shipped
               path only where more than DISCLOSURE_TOP_K_HITS bodies were fetched.
Blocks milestone? NO - rides along.
Rubric:        DISC-03 ("silent reductions: 0"), EV-03, A7 ("annotate; never silently delete"),
               A.9a ("each step is declared in reductions[] and named in budget_caps_hit"), and the
               work order's normative bullet "Order is the contract".
Location:      server/src/mailweave/disclosure/layout.py, `PlannedRow.rendered` - emits a
                 BODY_HEAD_TRUNCATED record only on the head-truncation branch; the STUB branch
                 returns `(None, ())` and the SNIPPET branch returns only `base_reductions`.
               server/src/mailweave/retrieval/assemble.py:1413 and :2051 - the only two consumers of
                 `disclosure.steps`: a boolean and one cap name. `LadderStep.detail` is computed by
                 `_detail` and discarded.
Repro:         /tmp/rdisc23/p13_reductions_record.py:
                 depth=body_clean kept=None disclosed=600 reductions=[('body_head_truncated',3800,600)]
                 depth=snippet    kept=None disclosed= 25 reductions=[]
                 depth=stub       kept=None disclosed=  0 reductions=[]
               /tmp/rdisc23/p14_wire.py - grep of the rendered structuredContent:
                 'A.9a' False | 'step' False | 'precedence' False |
                 'e4_query_scored_fill' False | 'declared_overflow_ceiling' False
Expected:      Every content reduction declared in place with a size count; every A.9a step declared
               so a reader can reconstruct what was sacrificed first.
Actual:        A depth demotion removes text with no count. The step sequence exists only in
               process memory.
Required fix:  Emit a reduction on every rung the ladder takes, not only head truncation: a
               `depth_reduced` record naming the depth it came from and the tokens it dropped
               (both are on the PlannedRow). And put the ladder's own account on the wire - the
               eight `LadderStep` records are already built with mechanical detail lines; a
               `reductions`-shaped response-level block, or `budget_caps_hit` entries named per
               step, is the smaller of the two edits. Assert the wire carries the step numbers in
               ascending order on a response where the ladder fired.
```
```
ID:            R-DISC-029
Severity:      LOW
Reachability:  REACHABLE today - these are defects in the round's own evidence, not in served
               behaviour. Each of the three behaviours is separately true today for a fixture
               reason and false on the modal real input.
Blocks milestone? NO - rides along. But a later round will trust these as pinned properties.
Rubric:        DISC-01, DISC-02, OD-3; and R-RETR-058's rule, which this round cites as answered.
Location:      tests/test_disclosure_round23.py,
                 `test_every_disclosure_shape_keeps_the_five_properties_that_make_the_ladder_honest`
                 - docstring lists five properties; the body asserts three. Properties 2 (floor
                 present) and 3 (nothing vanished) are unassertable from ShapeResult, which keeps
                 only counts.
               tests/test_disclosure_round23.py, `_shape` - the DisclosureLadderExhausted branch
                 returns `floor=True` as a literal. The report's printed matrix carries that value
                 as measured, and `assert {shape.floor ...} == {True, False}` consumes it.
               tests/test_disclosure_round23.py, `test_a_floor_member_is_never_scored_by_the_fill` -
                 asserts `not (floor & set(plan.threads[0].fill))`. plan.py's `_candidates` docstring
                 says "Every message of this thread that is neither a hit nor a floor member" and
                 the code skips hits only; the assertion holds because `chain_thread` puts the term
                 on hit subjects alone.
               tests/test_disclosure_round23.py,
                 `test_the_baseline_is_not_handicapped_by_the_planner` - same fixture dependence.
               tests/test_disclosure_round23.py,
                 `test_the_adjacency_radius_is_the_baselines_own_radius` - `FixedWindow.radius`
                 defaults to `E4_ADJACENCY_POSITIONS`, so two thirds of the assertion is
                 `X == X`; only the literal `== 2` can fail.
Repro:         /tmp/rdisc23/p12_scoring_claims.py part 1, shared subject line:
                 floor members that the fill ALSO scored: all 7 of them, fill_score 6 each
               /tmp/rdisc23/p21_arm_symmetry.py part A:
                 round-23 fixture   shipped fills 0   baseline fills 9   baseline >= shipped? True
                 shared subject     shipped fills 16  baseline fills 9   baseline >= shipped? False
Expected:      A property asserted over a matrix is evidence only where the matrix witnesses it; a
               docstring claim about what disclosure guarantees is executed (the round's own rule).
Actual:        Two of five properties documented and not executed; one matrix value asserted rather
               than measured; two behavioural claims that invert on a realistic subject line; one
               tautological identity.
Required fix:  Carry `floor_ids`, `present_ids` and `withheld_ids` on ShapeResult and assert
               properties 2 and 3 in the matrix sweep as well as in the Hypothesis one. Measure
               `floor` in the exhausted branch. Add a `shared_subject_thread` builder beside
               `chain_thread` and re-run the floor-scoring and not-handicapped tests against it -
               they will fail, which is the point, and R-DISC-017's fix is what makes them pass
               again. Replace the radius identity with an assertion that the shipped policy's
               structural reach is not greater than the radius Baseline F is run at.
```
```
ID:            R-DISC-030
Severity:      LOW
Reachability:  REACHABLE today - it is why the ladder in /tmp/rdisc23/p08 cannot recover after
               step 1 inflates it.
Blocks milestone? NO - rides along, but it should be fixed with R-DISC-019 because it is the same
               band-versus-depth confusion.
Rubric:        A.9a steps 2 and 5, PART-05, DISC-04.
Location:      server/src/mailweave/disclosure/ladder.py, `_collapsible` -
                 `row.band is Band.MAP and row.depth is Depth.STUB`.
               A.9a step 5 is written in terms of *stub rows*: "Hit-bearing-thread stubs -> declared
               collapsed runs". A FILL row that step 1 degraded to stub, or a FLOOR row that has no
               observed text, is a stub row in a hit-bearing thread and is never collapsible.
Repro:         /tmp/rdisc23/p08_step1_inflates.py - after step 1 turned 307 fill rows into stubs:
                   step 5 hit_thread_stub_runs   12370 ->   12370   (no change)
               and /tmp/rdisc23/p07_exhausted_why.py, same, on the shipped path.
Expected:      Step 5 collapses the hit-bearing thread's stub rows.
Actual:        It collapses only rows the *planner* banded MAP, so the ladder cannot recover the
               tokens its own earlier step spent.
Required fix:  Make `_collapsible` read the depth and the floor set, not the band: any row at
               Depth.STUB may be collapsed, since a collapsed-run member is present (A.7a, R-06) -
               which is already the argument the function's own docstring makes about floor members
               at stub depth. Keep the existing exclusion of anything above stub depth, which is
               what stops a floor member being collapsed out of a depth it earned.
```

---

## Verdict per degenerate-strategy guard

| Guard | Verdict |
|---|---|
| **DISC-01** — *"vary output randomly"; ruled out by requiring each inclusion's reason to name a mechanism traceable to the query* | **DEFEATED, in the direction the guard does not look.** The guard rules out too much variation and says nothing about none. Six materially different queries produce one representation, and every row carries a mechanism-naming reason traceable to the query (`term_overlap`, score 4) — the guard's requirement satisfied and its purpose defeated (R-DISC-017). The DISC-02 cross-reference ("a fixed ±2 policy fails DISC-01 by construction") is also defeated at the ranking (R-DISC-018). |
| **DISC-02** — *"give the query-aware arm a larger budget"; ruled out by the equal-budget requirement asserted from measured tokens* | **HELD structurally, on an unmeasurable quantity.** One `Selector`, one planner, one ladder, one estimate, one ceiling — I attacked it three ways and could not make the baseline lose unfairly. But the "measured tokens" the guard rests on are 1/20th–1/85th of the response (R-DISC-022), and the ratio moves with row count, which is what the arms differ in. The guard holds; the acceptance it guards is not yet satisfiable. |
| **DISC-03** — *"never strip anything, so nothing needs declaring"* | **HELD.** The ladder strips, and `truncated_by` is refused without an artifact (`degradation_artifacts`). The failure here is the opposite one: some stripping is not declared (R-DISC-028). |
| **DISC-04** — *"return stubs only and disclose nothing"; ruled out by EV-02/EV-06 recall bars on the same run* | **NOT TESTABLE HERE.** The bars are `[INHERITED — EP §13.4]` and the pinned tokenizer is at G0. I note in passing that the degenerate strategy is currently *more expensive* than the honest one in this system's own estimate — a stub row costs 40 and a snippet row costs its text (R-DISC-019) — so the guard is accidentally over-satisfied by a defect. |
| **DISC-05** — *"add levels because they look sophisticated"; ruled out by requiring the comparison to exist before the level ships* | **NOT SATISFIED.** The segment map is built, labelled `SEGMENT_MAP_IS_EXPERIMENTAL`, removable in one edit, and its boundary is derived rather than invented — all real. The comparison does not exist, and the criterion says the comparison must exist *before the level ships*. WS-15 has now shipped it behind `mailweave_thread_map(segment=…)`. Its boundary, `NORMAL_CEILING_TOKENS // STUB_ROW_TOKEN_ESTIMATE = 225`, is also computed in the units R-DISC-022 invalidates. |
| **DISC-06** — *"set the ceiling so low that nothing useful is ever returned"* | **HELD, and the inverse failure is present.** 9,000 tokens is not a starving ceiling. The ceiling is enforced against a quantity that is not the response (R-DISC-022), a step of the ladder can enlarge the response (R-DISC-019), and the ladder's failure mode is an unhandled exception rather than a truncation (R-DISC-020). |
| **PART-05** — *"emit a map so large it dominates the budget"; ruled out by DISC-04's token ceiling, which counts map tokens* | **DEFEATED.** A 600-row map measures 8,300 tokens against a 9,000 ceiling and renders 702,915 characters — 28× the target client's default cap. The map does dominate; the ceiling that was to rule it out counts 40 tokens per stub row and nothing for the structure around it (R-DISC-022). |
| **EV-03** — *"never drop anything (dump)"; inverse: "label everything withheld"* | **HELD, both directions.** Steps 7 and 8 drop and record; `withheld := H − disclosed` is computed by the ledger and refused by `Envelope` if the emitted list disagrees; `Source._a_claimed_map_accounts_for_every_message` forces three dispositions; `assert_nothing_vanished` covers every accounted id and I confirmed `accounted_ids` is not narrowed on the shipped path. Nothing is labelled withheld that is disclosed. |

---

## Recommendations, per criterion I own

Scoped, every one of them. **I recommend no transition to PASS anywhere.** Two of these have been
recorded as unqualified passes in this project before; the scope sentence is part of the
recommendation and must travel with it.

**DISC-01 · Output is conditioned on the query · M**
**Recommendation: leave NOT TESTED, and record the reproduction against it.** I can establish the
opposite of its acceptance: 0 of 15 pairs differ on a thread whose subject carries every query's
term (R-DISC-017), and the ranking's top class is Baseline F's window (R-DISC-018). *My evidence
covers* constructed multi-query threads at the policy level and one end-to-end run; it does **not**
cover F17, which the Verify clause also requires and which needs WS-16. I did not run the
`[UNSET]` pair-difference threshold, because it is unregistered — but 0/15 fails any threshold above
zero, so the criterion is decidable today in the negative and I say so.

**DISC-02 · Query-aware policy vs fixed window at equal budget · M**
**Recommendation: leave NOT TESTED.** *What I can establish:* the two arms run through one planner,
one floor, one promotion rule, one ladder, one ceiling and one estimate, differing in exactly one
object, and I could not construct an unfairness (Priority 7). That is a genuine achievement and it
should be recorded as such **without** being recorded as the criterion. *What I cannot establish:*
the comparison itself (WS-16), the budget–recall curve over ≥3 levels (EP §7.2), and the
equal-*budget* premise, which is currently equality in a quantity 20–85× away from the response
(R-DISC-022). Note also that the round's "baseline is not handicapped" evidence inverts on a
realistic subject line (R-DISC-029) — the claim survives on the structural argument, not on that test.

**DISC-03 · Depth vocabulary and declared reductions · M**
**Recommendation: leave NOT TESTED, with two halves separated.** *Established by execution:* 100 % of
disclosed rows carry a depth from the closed set, and 100 % of non-stub rows carry an executable
`unabridged` affordance (`/tmp/rdisc23/p22_disc03.py`, over a 60-message shipped-path response).
*Not established, and false on execution:* "silent reductions: 0" — a `body_clean → snippet` or
`snippet → stub` rung removes text with no size count (R-DISC-028). *My evidence does not cover* the
`format=raw` diff check the Verify clause names; that needs a live account.

**DISC-04 · Context efficiency against full dump · M**
**Recommendation: leave NOT TESTED, and do not quote the round's numbers.** I reproduced them exactly
(7,760 / 36,000 = 0.216, relevant fraction 0.881) and they are honest arithmetic in the units the
module uses. Those units are invalidated for any comparison with a host budget by R-DISC-022, and
`full_dump_tokens` is Baseline B *for this run*, not Baseline B — the implementer says so and is
right. Also: `full_dump_tokens`'s docstring says a message with neither body nor snippet "counts a
stub row"; the code counts 0. That is conservative against MailWeave, so it is a docstring defect
and not a number defect; I fold it into R-DISC-029's class rather than filing it.

**DISC-05 · Disclosure depth is justified by measurement · C**
**Recommendation: leave NOT TESTED, and raise the trigger question with the orchestrator.** The
trigger is declared met by design. The level now *ships* (WS-15 serves `segment`), and the criterion
requires the comparison to exist before it does. That is a scheduling conflict between OD-6's build
order and DISC-05's own remedy, and it is not mine to resolve. *My evidence covers* that the level is
built, labelled, derives both its numbers, and returns `None` below the boundary so depth *n−1* is
the same code path. It covers nothing about a measured win.

**DISC-06 · Self-truncation before host truncation · M**
**Recommendation: leave NOT TESTED. This is the criterion I would most strongly resist any future
pass on.** *Established:* the ladder's estimate and the envelope's estimate are one number on the
shipped path, and `Envelope` refuses a payload over its declared ceiling and a truncation claim with
no artifact behind it. Both are real and both were earned. *False on execution:* the response does
exceed what the host will accept while declaring itself inside its ceiling (R-DISC-022); a
degradation step can enlarge the response (R-DISC-019); and past ~650 rows the shipped path raises
instead of truncating (R-DISC-020). The criterion also carries a documented request-rate-limit
obligation (CONS-038) which is WS-15's and which I did not review.

**PART-05 · Unexpanded content is visible as stubs · M**
**Recommendation: leave NOT TESTED, but record that the schema half is strong.** *Established by
execution:* a `map_id`-bearing source must account for every position as a row, a collapsed-run
member or a withheld record (`Source._a_claimed_map_accounts_for_every_message`); runs carry
`positions`, `count`, `member_ids` and an expansion affordance that is a valid
`mailweave_thread_map` call including its `segment` argument; A3's bounds and A4's `included` reading
are enforced at construction. I could not construct a bare "N omitted". *Not established:* the
guard is defeated (see the guard table) — the map does dominate the budget, and DISC-04's ceiling
does not see it. *My evidence does not cover* the Verify clause's second half, "R-RETR confirms the
split-evidence case is solvable by the agent aiming at a stub", which is not mine and needs an agent.

**EV-03 · Withheld-record discipline · M**
**Recommendation: leave NOT TESTED, closest of the eight to establishable.** *Established by
execution:* every id steps 7 and 8 remove becomes a withheld record with `disclosed_token_ceiling`,
a `why` naming A.9a and an executable affordance; `withheld := H − disclosed` is the ledger's and
`Envelope` refuses a disagreeing list; `assert_nothing_vanished` runs on every step and its
`accounted_ids` is not narrowed on the shipped path (`p18`, `p18b`). I attacked it four ways and
broke none of them. *Not established:* the acceptance's "any hit not disclosed at body depth appears
as a stub or a withheld record carrying … why it was not expanded" is satisfied for the *withheld*
branch and thin for the *reduced-depth* branch, where the demotion carries no count (R-DISC-028).
*My evidence does not cover* the Verify clause's "R-ARCH by code read of every code path that can
remove a candidate" — I read `disclosure/` and `retrieval/assemble.py` and no further.

---

## Overall verdict

**Round 23 does not pass its gate.** Six findings are reachable today and three of them are, in my
judgement, critical correctness defects under OD-6's counter-rule: the degradation ladder enlarges
the response it is degrading (R-DISC-019); the shipped path raises an unhandled exception instead of
answering (R-DISC-020); and the guarantee this project calls its biggest is under-computed in a way
none of the round's sixteen plants, nine shapes or Hypothesis sweep can see, because they all check
the floor against its own derivation (R-DISC-021). Under §5a, reachable is fixed today.

The thesis itself is not established. What is disclosed does not depend on the query for the modal
query class (R-DISC-017), and where the score does discriminate, it discriminates by exactly the
radius Baseline F uses (R-DISC-018). The implementer found the ±2 degeneracy in the admission and
repaired it honestly and visibly; the same degeneracy is still in the ordering, and the repair's own
argument — "the other components keep their published weight and rank the admitted rows" — is where
it now lives. **This is not a failure of candour.** The report told me where to look, named the
right module, and the confession in Part 0 is the reason I found the ordering half in an hour rather
than a day. That is what a report should do and I want it on the record.

Three things this round built are genuinely good and should not be lost in a fix pass: the
driver-level gates with sixteen real plants (I planted my own and it went red five ways); the single
`Selector` that makes DISC-02's equal-budget property structural rather than careful; and the
`layout.cost() == measure_tokens(envelope)` identity, which I verified independently on five shipped
shapes. Each survives every attack I made on it. The fixes below must not break the third one — the
right repair changes both measures in the same edit.

**On integration under OD-6.** R-DISC-020 blocks OD-6 criterion 3 for large threads and must be
fixed before the milestone is claimed; it is a small fix. R-DISC-019 and R-DISC-021 do not block the
six criteria and are named critical anyway, because the counter-rule's exception is exactly for
defects of this kind. R-DISC-022 blocks DISC-06 and, in practice, criterion 3 as well, but its
repair is entangled with PF-6, so my recommendation is: fix the *quantity measured* now (it is the
same edit as R-DISC-019), and let PF-6 register the number. Everything else rides along.

---

## Established by execution

1. All five gates clean on the current tree: ruff, ruff format (197 files), `mypy --strict` (170
   files), seven guards, `pytest -q -m "not network"` **rc 0** over **2,615** collected tests with no
   F/E, `tests/test_replants.py` 4 passed, rubric unchanged at 6/0/0/107.
2. The two estimates are one estimate: `layout.cost() == measure_tokens(envelope)`, delta 0 on five
   shipped-path shapes from 5 to 600 messages (`p19`).
3. OD-3's 40-message / 6-hit case reproduces exactly as reported: 7,760 tokens against the 9,000
   normal ceiling, no ladder step fired, 11 floor members, 5 promoted, 6 refused, efficiency
   0.216 / relevant fraction 0.881 (`p24`).
4. The published E4 weights are fixed: no code path in `server/src`, `harness/src` or `tools`
   rebinds or mutates `E4_WEIGHTS`, `E4_ADJACENCY_POSITIONS`, `E4_MINIMUM_FILL_SCORE` or
   `ADMITTING_COMPONENTS`; `score_of` is an unnormalised sum; R74 and R75 are caught.
5. The driver-level floor gate is real and general: my own plant (drop `CHILD` from `floor_of`) in an
   isolation-asserted scratch tree turned five tests red.
6. The two arms differ in exactly one object and I could not make the baseline lose unfairly by
   ceiling, floor, promotion or evidence tier (`p21`).
7. EV-03's record discipline survives four attacks: `accounted_ids` covers every mapped member on the
   shipped path, steps 7 and 8 both file records with executable affordances, the ledger derives the
   withheld set, and `Source` forces three dispositions per position (`p18`, `p18b`, `p22`).
8. PART-05's schema obligations are enforced at construction: positions bounded by `stated_total`,
   runs contiguous and counted, `included` counting run members, and the run's `segment` affordance a
   call `mailweave_thread_map` actually accepts.
9. DISC-03's depth vocabulary: 100 % closed-set depths, 100 % `unabridged` affordances on non-stub
   rows (`p22`).

## False on execution

1. **"Two materially different queries produce different representations."** 0 of 15 pairs differ,
   with an identical reason and score on every row (`p02`). — R-DISC-017
2. **"A score above zero is necessary and not sufficient" is enough to separate the policy from
   Baseline F.** The top score class of the E4 ranking is exactly Baseline F's ±2 window (`p16`). —
   R-DISC-018
3. **"A step only ever lowers a row's depth"** implies the ladder shrinks the response. Step 1 took a
   9,300-token layout to 27,270 on the shipped path (`p07`, `p08`). — R-DISC-019
4. **"An inability declared where it occurs, never a response handed to the host to cut."** It is an
   unhandled exception out of `assemble` and out of the MCP dispatcher (`p06`). — R-DISC-020
5. **"Every floor member is present at every degradation step."** True of `floor_ids`; false of
   A.9(2)'s floor. A disclosed hit's direct child was withheld (`p04b`). — R-DISC-021
6. **"A response never exceeds the ceiling it declares."** True of the estimate; a five-message
   response renders 24,198 characters — 97 % of the host's 25,000-char default cap and 2.4× its
   10,000-char warning — and a 600-row response is 28× the cap (`p15`). — R-DISC-022
7. **"The overflow is not a budget; it is the promise that membership is never the thing cut."** On
   the implementer's own fixture it bought snippet depth while membership was affordable with 1,800
   tokens to spare, and the wire says `why: "E2 floor membership"` (`p03b`). — R-DISC-023
8. **"Which hits are the top k is decided by the published E4 score … deliberately not by arrival
   order."** It is the k earliest by thread position, in both arms (`p12`). — R-DISC-026
9. **"`content_tokens` … so that `decided,` and `decided` are one token."** True of the comma, false
   of the full stop, which is where a decision verb usually sits (`p20`). — R-DISC-027
10. **"`_candidates`: every message that is neither a hit nor a floor member."** The code skips hits
    only; on a shared subject line all seven floor members were scored, at 6 each (`p12`). —
    R-DISC-029
11. **"At ±2 the baseline fills strictly more rows than the shipped policy."** True of the round's
    fixture, false on a realistic subject line, where the shipped arm fills 16 to the baseline's 9
    (`p21`). — R-DISC-029
12. **"The promotion rule promotes five of eleven"** as evidence of discrimination. It promoted 5 of
    5 parents and 0 of 6 children, on relation alone (`p24`). — R-DISC-024

## Not establishable here at all

1. **DISC-02's comparison, DISC-04's bars, DISC-05's depth arm, and F17 at each tier.** Each needs
   the WS-16 harness and G0-registered numbers. This round makes all four runnable and I confirmed
   the hooks exist; I did not run them and no in-process test can.
2. **Whether the E4 score's ordering is better than the baseline's.** It is a mechanical sum of five
   predicates with no measured relation to relevance. The implementer says so and is right.
3. **The pinned tokenizer, and therefore every token figure in this review and in the round-23
   report.** PF-6. What I *could* establish is that the estimate's relationship to the wire is not a
   constant, which is a statement about the estimate rather than about the number.
4. **Whether A.8a's decision lexicon has a usable base rate on real mail.** PF-13. If it is inert,
   the `CONTRADICTION` clause is inert with it, independently of R-DISC-027.
5. **Whether one day is the right `E4_TEMPORAL_PROXIMITY_SECONDS`.** Derived from Gmail's
   day-granular date operators, which is an argument and not a measurement. WS-16/WS-17.
6. **The real-mail rate at which a reversal falls past Gmail's ~200-character snippet.** The
   mechanism is reproduced (`p11`); the fixture's 60-character snippet overstates the rate and I have
   no corpus that would settle it. OD-4 forbids me one.
7. **DISC-06's request-rate-limit half (CONS-038)** and the MCP-07 interop test. WS-15's surface and
   a real client; R-MCP's round, not mine.
8. **Anything requiring a live account** — OD-6 criteria 2, 3 and 4-on-real-mail. OAuth consent
   status is unchanged and untouched by round 23.
