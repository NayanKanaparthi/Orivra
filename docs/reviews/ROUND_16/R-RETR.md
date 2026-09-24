# ROUND 16 — R-RETR review (WS-04 fix round: the ladder finds what is there, or says it did not)

**Reviewer:** R-RETR, independent instance, 2026-09-03. Sole gating reviewer for round 16.
Verified by execution per `AGENT_LOOP.md` §4/§5/§5a and §7. **Source and tests untouched** —
every probe ran from `/tmp/rretr16/*.py` against the real tree, every planted defect ran in a
scratch copy at `/tmp/rretr16/tree` with `PYTHONPATH` set and `mailweave.__file__` asserted to
resolve there. Probe files are named against every result below.

## Environment

| Gate | Result |
|---|---|
| `ruff check .` | All checks passed |
| `ruff format --check .` | 153 files already formatted |
| `mypy --strict` | Success, 127 source files |
| `python -m tools.guards` | 7 guards clean (forbidden-import, generative-client, gmail-endpoint, ground-truth-isolation, scope-literal, unaudited-disk-write, unwrapped-http-client) |
| `pytest -q -m "not network"` | **2,235 passed**; re-counted independently via `--collect-only -q` summed per file = **2,235** |
| `tools/rubric_status.py --check` | 7 PASS / 0 FAIL / 0 BLOCKER / 106 NOT TESTED, 11 transitions — unchanged |

All gates run twice, before and after all probing, identical both times. `mailweave.__file__` →
`/root/mailweave/server/src/mailweave/__init__.py`. Nothing under `/root/mailweave` was written by
this review except a pytest `.pyc` (`find -newermt` over `server tests tools harness docs` returns
`tests/__pycache__/test_lexical_ladder.cpython-312.pyc` and nothing else).

**Scratch-tree discipline.** `/tmp/rretr16/tree` is a full copy including `docs/` (without it,
four rubric/preflight tests fail for the wrong reason and a plant sweep would run against a
tree that was never green). Verified green at **2,235 passed** before the first plant, with
`mailweave.__file__` and `tests.__file__` both asserted to start with `/tmp/rretr16/tree/`.

## Reachability rule I applied (§5a)

Unchanged from round 15 and restated because it decides the classification of every finding
below. `LadderRunner` and `assemble` have no MCP tool surface today; §5a exists to stop findings
against code that does not exist and to stop re-review of sealed modules, not to make this
round's own code inert. **A defect triggered by an ordinary query string reaching
`LadderRunner.run` / `assemble` is REACHABLE.** Every finding I raise is reachable; I mark none
inert. Where a *fix* belongs to another workstream I name it, but the finding stays open and
blocking here (§5a: "a deferred finding is blocking in the round it returns to").

---

## Priority 1 — recall, adversarially

### What holds, established by execution

**R-RETR-008 is genuinely fixed, and further than the implementer's table shows.**
(`/tmp/rretr16/r1_decomp.py`, `r2_shapes.py`.) Every row: L1 returns **0**, the terms live in
different messages of one thread, and the thread comes back as a `Source`.

| query | units | L1b probes | result |
|---|---|---|---|
| `rollout cutover` | 2 | 2 | 2 rows, both `matched` |
| `rollout cutover handover` | 3 | 3 | 3 rows, all `matched` |
| `… switchover` (4 terms) | 4 | 3 (A.7 cap) | 4 rows, 3 `matched` + 1 `stub` |
| `… turnover` (5 terms) | 5 | 3 | 5 rows, 3 `matched` + 2 `stub` |
| `"a b" "c d"` | 2 phrase units | 2 | recovered |
| `"a b" "c d" "e f"` | 3 phrase units | 3 | recovered |
| `from:a from:b` / `label:a label:b` / `subject:a subject:b` | 2 each | 2 | recovered |
| `subject:vendor rollout cutover` | 3 | 3 | recovered |
| `after:X before:Y` written out | **1** joint unit | — | halves not intersected |
| `newer_than:7d older_than:30d` | 1 joint unit | — | no window, no crash |

Unicode and punctuation shapes all decompose: NBSP, em-dash, zero-width space, fullwidth,
`ﬁ` ligature (NFKC → `final`), case folding, hyphenated compounds, trailing punctuation.

**R-RETR-007 is fixed at the point that matters, which the implementer did not demonstrate.**
The implementer's evidence is a case where the stop **no longer fires at all**. I built one where
it *does* fire (`/tmp/rretr16/r11_stop.py`): `when is the cutover from:dev@team.example`, two
noise threads carrying date-like tokens, plus a split thread.

```
answer_type : present=True examined=2
stop        : D.3-2 fired_after L1
rungs run   : ['L1', 'L1b']       skipped: ['L0','L2','L3']
t-split     : found, both messages, role matched
```

The stop fires, `halts_after` is L1b, and the split thread is recovered. That is the fix working
under load rather than the trigger being disabled.

**Triples do not break the plan layer.** The implementer's sweep states its bound as "singles and
ordered pairs, not triples". I swept **7,980 ordered triples** of 21 operator spellings
(`/tmp/rretr16/r20_triples.py`): **0 raised, 0 planned probes that are listings** by the module's
own two predicates. A separate 676-query singles+pairs cross-product: **0 raised**
(`/tmp/rretr16/r19_fuzz.py`).

### Where it still silently returns the whole mailbox and calls it an answer

**An empty or whitespace-only quoted phrase reproduces R-RETR-006's three failures exactly.**
`why_this_q_is_not_a_probe` and `selects_something` judge a fragment *syntactically*. `""` is a
non-empty string, is not a mailbox-scope operator and is not a negation, so it passes every check
and becomes a probeable constraint (`/tmp/rretr16/r3_vacuous.py`, `r4_empty_phrase_blast.py`,
`r5_empty_phrase_l3.py`).

```
mailweave_search('""')  against a mailbox whose default view is empty
  wire      : [('""', False), ('in:anywhere ""', True)]     <-- includeSpamTrash=true
  |H|       : 10   (6 spam + 4 trash)
  sources   : 10 threads, every row role: matched
  outcome   : answered      term_coverage : 1.0
```

That is the BLOCKER's three failures in one response: rows that match nothing returned as matches;
spam and trash read for a query that asked for neither; and `answered` with full term coverage
saying it succeeded. The same shape reaches Gmail for `" "`, `"\t"`, `"\xa0"`, `"​"`,
`""""`, `subject:""`, `subject:" "`, and for an operator written with an empty value —
`subject:`, `label:`, `is:`, `in:`, `has:` all reach the wire as bare tokens and L3 composes
`in:anywhere subject:` with `includeSpamTrash=true`.

The trigger is not only the degenerate `mailweave_search('""')`. `report "" 2026` and
`he said "" ok` — paste artefacts — parse to `phrase=('""',)` plus terms, and then **L1b probes
`""` on its own**, pulling the entire default mailbox into `H` for a query about "report 2026"
(`/tmp/rretr16/r4_empty_phrase_blast.py`: 5/5 unrelated threads disclosed as `matched`,
`outcome: answered`).

**Filed as R-RETR-017, BLOCKER.**

**A query naming a widening mailbox scope loses that scope at every decomposition probe, so the
founding bug's shape in spam or trash is unrecoverable.** `decomposition_units_of` correctly
refuses to make a *unit* out of a scope fragment — and then no other unit carries it either, and
`Probe.include_spam_trash` is derived from the probe's own `q`, so the flag flips to false as well
(`/tmp/rretr16/r25_scopedrop.py`, `r26_scopedrop2.py`):

```
mailweave_search("in:anywhere rollout cutover"), split thread in SPAM
  wire   : [('in:anywhere rollout cutover', True), ('rollout', False),
            ('cutover', False), ('rollout cutover', False)]
  |H| = 0   sources = []   outcome = inconclusive
```

Same for `in:spam rollout cutover` and `in:trash rollout cutover`. `label:archive rollout cutover`
**does** recover, because a non-widening label is itself a unit — so the loss is specific to the
three widening operators, i.e. to exactly the query a user types after the default search failed.
This sits at the join of R-RETR-006's fix (a scope fragment is not a unit) and R-RETR-008's fix
(units are what L1b probes): **the twelfth instance of "one shape validated, its peer trusted",
at the same join the implementer found the eleventh.**

**Filed as R-RETR-019, HIGH.**

### Where the response claims more than any probe carried

`_asked_for` computes `enforced` as *the parse minus the constraints an L2 relaxation gave up*.
No other rung contributes, so a constraint that L3 abandoned, or that an L0 stop never executed,
is reported **enforced** (`/tmp/rretr16/r13_enforced.py`, `r14_l3only.py`, `r12_l0stop.py`).

```
mailweave_search("from:bob@team.example cutover")
  the only disclosed row is a SPAM message from marketing@vendor.invalid,
  admitted by L3's 'in:anywhere cutover', which dropped from:
  enforced            : ('from', 'terms')
  dropped             : []
  term_coverage       : 1.0      constraint_drop_depth : 0
  outcome             : answered
```

```
mailweave_search('"vendor selection review" cutover')   # D.3-1b stop at L0
  executed q          : '"vendor selection review"'   -- 'cutover' never sent
  enforced            : ('phrase', 'terms')
  term_coverage       : 1.0      dropped: []
  a thread carrying only the phrase is disclosed as matched
  outcome: answered   sufficiency: sufficient
```

LEX-02's acceptance clause is "every dropped signal is named with the rung that dropped it. Cases
where a signal was silently dropped: **0**." Two rungs drop signals and neither is named. The
per-row `constraint_coverage` is honest in both cases (`('terms',)`, not `('from','terms')`) — the
defect is at the response level, in the block LEX-02 makes mandatory.

**Filed as R-RETR-020, HIGH.**

### The precision cost R-RETR-008's fix newly makes routine

Not a silent drop — `constraint_coverage` and `scan_scope` are mechanically honest — but nothing
at response level separates an intersection member from a fragment hit
(`/tmp/rretr16/r22_scale.py`, `r21_window.py`, `r13_enforced.py`):

* `rollout cutover`, 41 messages, 20 threads with only "rollout", 20 with only "cutover", 1 split:
  **12 sources, 11 of them single-word threads, every row `matched`**, 29 withheld,
  `outcome: answered`, `term_coverage: 1.0`. The split thread *is* preferred to position 1 — the
  `prefer=intersection` tie-break works — but 11 of 12 disclosed threads do not satisfy the query;
* `newer_than:7d rollout`: a message from **2025-01-05** is disclosed `role: matched` while
  `asked_for.parsed.window_utc.start` is `2026-08-27T12:00:00Z`, `enforced=('newer_than','terms')`,
  `term_coverage: 1.0`. L1b's `rollout` probe carries no date at all;
* `from:ana@… rollout cutover handover` (4 units, cap 3): a thread **no message of which contains
  "handover"** is disclosed with all three rows `matched`, `enforced=('from','terms')`,
  `term_coverage: 1.0`, `outcome: answered`.

Round 15's `rollout cutover` returned `inconclusive` with zero sources. Round 16's returns twelve
threads under `answered`. That is a better answer and a louder claim, and the claim is not scoped.

**Filed as R-RETR-024, MEDIUM.**

---

## Priority 2 — the refusal's new blast radius

I audited **50 queries a user would plausibly type** (`/tmp/rretr16/r27_refusal_audit.py`):
**17 refused, 33 planned.** The refusals fall into four classes and one of them should not exist.

| class | count | verdict |
|---|---|---|
| zero-constraint parse failure (`the`, `?`, `''`, `'   '`) | 4 | correct |
| widening-scope-only (`in:anywhere`, `in:spam`, `in:trash`, `in:anywhere -invoice`) | 4 | correct as a rule, see note |
| unprovable `name:value` alone (`thread:1837abf`) | 1 | correct not to execute; wrong to have no response |
| **quoted phrase containing a colon** | **8** | **wrong** |

**A quoted phrase containing a colon is classified as an unknown operator.** `tokenise` does
`body.partition(":")` **before** the quoted-phrase branch, so `"9:30 standup"` becomes
`OperatorName('"9:30')` → `ValueError` → `UNKNOWN_OPERATOR`. R-RETR-012's fix then keeps unknown
tokens out of the executed `q`, and R-RETR-006's fix then refuses the empty ladder plan
(`/tmp/rretr16/r9_phrase_ops.py`, `r10_phrase_refusal.py`):

```
mailweave_search('"9:30 standup"')
  QueryNotSearchable: '"9:30 standup"' is a name:value token outside Gmail's
  documented operator set (RO F3, LEX-02) ...
  gmail calls: Counter()      wire: []
```

Eight of my fifty: `"9:30 standup"`, `"note: see below"`, **`"Re: quarterly plan"`**,
`"http://docs.example.test/plan"`, `"ratio 3:1"`, `"budget: approved"`, `"Q3: results"`,
`"12:00 handover"`. With a companion term the phrase is silently unsearched rather than refused:
`'"9:30 standup" thursday'` executes only `thursday`, declares the phrase dropped under
`unproven_operator`, `term_coverage: 0.5` — and the phrase itself is never searched for at any
rung. `subject:"note: see below"` works, because the operator branch unquotes the tail; only a
**bare** quoted phrase breaks.

This also silently disables **A.8a branch E-b** for every phrase containing a colon, so LEX-04's
exact-lookup family is narrower than it appears.

The tokenisation predates this round; the *consequence* is this round's. `ParsedQuery.render`'s
own docstring records that the token "rode inside the residual terms, so it reached Gmail
conjoined with the rest of the query" before R-RETR-012's fix — i.e. the phrase used to be
searched for and now is not. **This is a regression introduced by the fix for R-RETR-012, at its
join with the fix for R-RETR-006.**

**Filed as R-RETR-018, HIGH.**

**Note on the scope-only refusals.** `why_this_q_is_not_a_probe`'s own docstring says the rule
"judges the *user's own* `q`, so `-cutover` passes it: … it is the listing the user asked for,
which MailWeave has no business refusing." `in:spam` is also a listing the user asked for, and it
is refused. The distinction the code actually draws — refuse only a listing that *leaves the
default mailbox* — is coherent and I do not file against it, but the docstring's stated principle
is wider than the code it explains, which is this project's recurring shape one more time. I
record it and do not file it.

**And every refusal produces no response at all.** `run_parsed` raises `QueryNotSearchable`; no
`Envelope` is built. `ARCHITECTURE_DECISION.md` A.2: "**There is never a bare empty result.** If no
rung produced evidence, the same envelope is returned carrying a `RetrievalReport`." D.3 rule 6:
"**Never** a bare empty result (C-08). An empty result always carries `outcome`." Rubric
**ROUTE-01 is currently PASS** on the statement "A no-evidence outcome is a structured report,
never an empty set or a nonexistence claim."

I checked the implementer's stated reason and it is true of the code as it stands:
`Envelope._no_bare_empty_response` refuses `report.rungs == ()`, so a zero-rung structured report
is not constructible without naming a rung that did not run. The *schema* question is WS-10's and
the escalation is correct. The *finding* is not thereby closed: it is reachable today, its blast
radius is 17 of 50 plausible queries rather than the four parse failures it was designed for, and
ROUTE-01's Round-1 evidence (`_no_bare_empty_response` probes at the envelope layer) no longer
covers what a caller sees. Under this project's own round-4 and round-9 precedent, a passing
criterion whose evidence a reviewer calls into question should not be counted as passing while
that is unresolved. **I recommend the orchestrator treat ROUTE-01 as called into question. I mark
nothing.**

**Filed as R-RETR-022, MEDIUM** (severity bounded because the reason travels in the exception
message and a caller can catch it; reachability and the ROUTE-01 interaction are what make it
blocking rather than the severity).

---

## Priority 3 — R-RETR-008's fix at its edges, and the twelfth instance

Verified as claimed (table above), plus the shapes the implementer did not report: five terms,
three phrases, contradictory operators (`is:read is:unread`, `in:inbox in:trash`,
`is:unread -is:unread`, `from:a -from:a`), crossing date pairs (absolute and relative), operators
inside phrases, unicode, punctuation. **The shapes it misses** are R-RETR-019 (the widening scope
dropped at every unit) and one smaller one:

**`ConstraintUnit.label` is not unique within a parse, and the collision empties the
intersection.** `label` is `f"{name}[{fragment}]"`, so a repeated identical fragment produces two
identical labels; `by_unit = {entry.probe.unit: entry.threads …}` keeps the **later** probe, whose
admission delta is empty because the earlier identical probe already admitted everything
(`/tmp/rretr16/r28_dupunit.py`):

```
'from:ana@team.example from:ana@team.example cutover'
  units       : ['from[from:…]', 'from[from:…]', 'terms']   unique = False
  wire        : L1b sends 'from:ana@team.example' TWICE, then 'cutover'
  by_unit     : {'from[from:…]': [], 'terms': []}
  intersection: []
```

Two costs: one of the three A.7 decomposition slots is spent re-sending an identical `q` (I-3,
adaptive cost), and the intersection is empty, so `evidence_ids` from L1b is empty and its finds
are disclosed at `stub` depth rather than `body_clean`. `ConstraintUnit`'s docstring says "`label`
is unique within a parse"; it is not.

**Filed as R-RETR-025, LOW.**

---

## Priority 4 — D.3 rule 2 and the stop rules in their published order

**Rule 2's fourth conjunct is now `run.answer_type.present is True`** — verified by reading
`_after_rung` and by planting `not run.answer_type.blocks_stop` back (caught, twice, by two
independent tests). **`halts_after` is `RungId.L1B`** — verified by reading, by planting
`RungId.L1` back (caught), and by driving a query on which the stop actually fires (above).

**Did any other rule import a neighbour's escape?** I checked each rule the module implements:

* **rule 0** — `answer_type_presence` is computed before the E-a/E-b test at L0. ✔ It is
  *re-computed* at L1 on L1's texts, overwriting L0's value; D.3 rule 0's letter says "evaluated on
  L0's hits". For a query with no L0 rung there are no L0 hits and the L1 evaluation is the only
  one available, so the deviation is in the conservative direction. Recorded, not filed;
* **rule 1** — `branch is E_A` ⇒ `halts_after=L0`. ✔ matches "STOP after L0";
* **rule 1b** — `exact_signal.fired and not answer_type.blocks_stop` (`present is not False`). ✔
  That *is* rule 1b's own text ("only if `answer_type_presence` is true, **or** the query carries
  no answer-type cue"). No import in either direction;
* **rule 2's third conjunct** is coded as `not run.parsed.passthrough` where D.3 writes
  `constraint_drop_depth == 0`. I checked whether that is weaker: `constraint_drop_depth` at L1 is
  `len(dropped_declarations(parsed))`, which counts passthrough **and** unknown operators; but
  `term_coverage` — the second conjunct — has `unproven = passthrough + unknown_operators` in its
  denominator, so `term_coverage == 1.0` already implies both are empty. The coded conjunct is
  therefore redundant rather than weaker, and the stop can only fire less often than D.3 permits.
  **Not a finding**, recorded because it looks like one;
* **rule 3** ("any rung returning `sufficiency == sufficient` ⇒ STOP") is **not implemented in the
  ladder** and the module docstring scopes itself to rules 0/1/1b/2. `sufficiency` is computed at
  assembly. Recorded as a documented omission, not filed;
* **rule 4** is `_should_run`'s `evidence_count == 0`, i.e. only the `hit_count == 0` disjunct; the
  other three escalate to L4/L5, which do not exist. Correct.

**One consequence of rule 1b worth naming, and it is a reporting defect rather than a stop
defect.** D.3 rule 1b halts after L0 for an E-b phrase even when the query carries other
constraints, so `'"vendor selection review" cutover'` executes only the phrase and reports
`enforced=('phrase','terms')`, `term_coverage: 1.0`, `sufficiency: sufficient`. That is folded
into R-RETR-020 rather than filed separately, because the fix is one fix.

---

## Priority 5 — evidence preservation under all of it

**500 randomised trials, 0 violations** (`/tmp/rretr16/r15_sweep.py`). Mailboxes of 1–26 messages
over random threads, senders, label sets (INBOX / IMPORTANT / SPAM / TRASH / UNREAD), attachments
and rfc822 ids, against 30 query shapes chosen to include this round's new paths: 2/3/4-term
decomposition, repeated operators, multi-phrase, scope operators, crossing date pairs, negations,
unknown operators, the empty phrase, booleans, `rfc822msgid:`. Asserted from **outside** the
process against the double's own `returned_ids` log:

```
trials=500  answered=500  refused=0  crashed=0  violations=0
  every id messages.list returned entered H
  H subset of (disclosed union withheld)
  disclosed and withheld are disjoint
  no phantom id
```

**The new paths individually** (`/tmp/rretr16/r16_parts34.py`):

| path | result |
|---|---|
| refusal | zero Gmail calls (`box.calls` empty), so there is nothing to account for |
| decomposition (2–5 units, cap at 3) | `H = disclosed ∪ withheld` in every shape |
| whole-thread withholding, order underivable (all messages) | 0 sources, 3 ids withheld `partial_source_failure`, 1 `not_included_sources`, `outcome: inconclusive`, `partial: true`, H accounted |
| the same for **one** message only (custom transport, the peer the fixture flag cannot reach) | identical treatment, H accounted |
| `NotIncludedSource` with `stated_total: null` (self-disagreeing thread) | 5 healthy sources, 2 ids withheld, H accounted, envelope serialises |
| overflow at `max_hit_threads` with L1b's broad probes (41-message mailbox) | 12 sources, 29 withheld records, `partial: true` |

I could not construct a run in which an observed id is neither disclosed nor withheld.

---

## Priority 6 — A8 and Part 4

**The corrected A8 text is true of the code, clause by clause, by execution.**

| A8 clause | executed |
|---|---|
| the disposition "builds, validates and serialises today, provided the disagreeing thread is not made a `Source`" | `/tmp/rretr15/c3_a8_alt.py` — BUILT, serialises |
| "five threads retrieved correctly were lost because a sixth disagreed with itself" — now not | `/tmp/rretr15/c4_blast.py` and `/tmp/rretr16/r16_parts34.py`: **5 sources**, `t-bad` a `NotIncludedSource`, both its ids withheld with `mailweave_get_messages` affordances |
| "A `NotIncludedSource` states no total (`stated_total: null`)" on disagreement | `stated_total=None` observed; and on the *order*-underivable thread, where there is no disagreement, it states `3` normally |
| the arithmetic still refuses a `Source` at 9 and at 10 | `/tmp/rretr15/c1_a8.py`, `c2_a8_floor.py` — both validators fire, unchanged |
| the correction paragraph names the old heading and the new one | both present in the text; the old heading no longer appears as a heading |

**Does the arithmetic retained under the new heading bound what the heading says?** The heading is
"The arithmetic, which bounds `Source.stated_total` and nothing wider." I tested the "nothing
wider" half by planting `stated_total=len(recorded.thread.messages)` into the `NotIncludedSource`
path (`/tmp/rretr16/plants_run3.py`, plant P13): the envelope refuses it —
*"not-included source t-ancient states the thread holds 8 messages, but 9 distinct messages were
observed"*. So the ≥-observed floor binds a `NotIncludedSource` too; what the *A6 exactness* rule
binds is `Source` alone, and `stated_total: null` is the value that satisfies the floor without
making the A6 claim. **The heading is accurate: the pair with no solution is `Source`-only, and
`None` is a real answer rather than a hole.** `_total_this_thread_can_state`'s docstring says
exactly this and is now executed rather than read.

**PF-1 and PF-2 remain unmeasurable here** and the code is correct either way.

---

## Priority 7 — was R-RETR-015 rightly left open?

**Mostly yes, and one buildable piece was declined.**

R-RETR-015 named three fixes: term-level relaxation inside `terms`; phrase-to-terms degradation at
L3; or an explicit A.7 statement that k = 1 is out of L2/L3's scope. The decomposition half of the
finding is genuinely closed — `rollout cutover`, `rollout OR escalation` and `rollout note` all
have an L1b now (`/tmp/rretr16/r24_k1.py` confirms `units=2` for each). What remains is a query
whose single constraint is a **single unit**: one bare word, one quoted phrase.

I agree the two remaining alternatives are not an implementer's call. Term-level *relaxation*
would change what `constraints_dropped`, `RELAXATION_ORDER` and `max_relax_probes = min(k,6)`
range over — A.7's L2 cost row and ROUTE-03's published order. Phrase-to-terms degradation is
A.7's L3 step verbatim. **Correct deferral to A.7 / WS-10.**

**But the response's account of the gap was buildable and was not built**
(`/tmp/rretr16/r24_k1.py`):

```
mailweave_search('"the migration window slips"')     # and 'teleportation', etc.
  empty_diagnosis : incomplete, tried=(), untried_drops=('phrase',), restores=None
  affordance      : {'tool': 'mailweave_search', 'args': {'relax': {'max_probes': 1}}}
  max_relax_probes(1) = 1        RelaxationRung().plan(parsed) = []   at any budget
```

`untried_drops` names a drop that **no budget can reach** — dropping the only constraint renders
an empty `q` and `RelaxationRung.plan` declines it by design — and the affordance offers exactly
the budget the run already had, so following it changes nothing. ADV-105's whole point was that
"the probe budget ran out" and "no single drop restores results" must not be the same shape in the
schema; there is now a third case, "this drop is structurally unprobeable", collapsed into
`incomplete`, wearing an affordance that cannot do what it offers. AD-03 requires affordances to
be concrete `{tool, args}` pairs that would reach the untried rung.

**Filed as R-RETR-023, MEDIUM.** Its fix is `assemble`'s, not A.7's.

---

## Scepticism checks the work order asked for

### The six defects in inherited fixes — planted back, my own way

`/tmp/rretr16/plant.py` (mine, written independently of `/tmp/r16impl/plant.py`): anchor-count
asserted, before/after content hash printed, file-changed asserted, `__pycache__` cleared before
each run, imports re-asserted inside the scratch tree before every plant, source restored from the
real tree afterwards. Scratch tree verified green at 2,235 first.

```
imports resolve into the scratch tree:
   /tmp/rretr16/tree/server/src/mailweave/__init__.py
   /tmp/rretr16/tree/tests/__init__.py

CAUGHT  I1  selects_something tests the negation prefix only (the pre-fix rule)
CAUGHT  I2  the refusal is keyed on the empty constraint list again
CAUGHT  I3  L3 repeats a mailbox-scope fragment beside the widening operator
CAUGHT  I4  L3 widens a negated participant into its own opposite
CAUGHT  I5  L3 re-sends L1's own query as its broadening
CAUGHT  I6  a crossing date pair builds a TimeWindow again
CAUGHT  P8  D.3 rule 2's fourth conjunct imports rule 1b's no-cue escape
CAUGHT  P9  the L1 stop switches L1b off again
CAUGHT  P10 assemble invents a position when the observation stated none
CAUGHT  P11 a self-disagreeing thread denies the whole response  (re-run with a clean
            ValueError after my first attempt caught only a NameError)
CAUGHT  P12 decomposition keys its intersection on the constraint, not the unit
CAUGHT  P13 the not-included source states an enumeration below what was observed
```

All six inherited defects are real (each plant reproduces a distinct failure) and all six are
fixed (each plant is caught by a test that names it). My first P12 attempt was a **bad plant**, not
a missed catch — `(probe.enforced or (probe.unit,))[0]` resolves to the label for a piece-probe, so
it did not reintroduce the defect; re-planted as `unit.split("[")[0]` it is caught.

### Is the implementer's plant harness testing the real tree? No.

`/tmp/r16impl/tree` had been deleted, so the harness **crashed** rather than silently testing the
real tree — the correct failure mode. I rebuilt the tree from my own clean copy and ran their
harness unmodified:

```
imports resolve into the scratch tree:
/tmp/r16impl/tree/server/src/mailweave/__init__.py
/tmp/r16impl/tree/tests/__init__.py
scratch tree green on all 13 target tests before planting
... all 12 plants caught by the tests that name them
```

`PYTHONPATH` is set on both the resolution check and every test run, `PYTHONDONTWRITEBYTECODE=1`
is set on the test runs, and the assertion `str(SCRATCH) in where` cannot pass for
`/root/mailweave/...`. **The 12/12 claim reproduces independently.**

### The plant that was "not caught on first run" — the test it produced does not exercise what it names

`test_a_broadening_probe_does_not_carry_a_narrower_scope_than_the_one_it_widens_to`. Its docstring:
*"a scope operator the user wrote is replaced wholesale … Conjoining the two instead sends the
widening operator beside a narrowing one, which searches the narrower scope."* Its body parses
`f"{SPAM_OPERATOR} is:unread"` — a **widening** operator, which `_anywhere` strips by
`carries_nothing_but_mailbox_scope`. For an ordinary *narrowing* scope operator the behaviour the
docstring forbids is exactly what happens (`/tmp/rretr16/r17_narrow_scope.py`,
`/tmp/rretr16/r18_l3wire.py`):

```
'in:inbox'                  L3 -> [('in:anywhere in:inbox', True)]
'in:inbox is:unread'        L3 -> [('in:anywhere in:inbox is:unread', True)]
'in:drafts is:unread'       L3 -> [('in:anywhere in:drafts is:unread', True)]
'in:chats has:attachment'   L3 -> [('in:anywhere in:chats has:attachment', True)]
'label:inbox is:unread'     L3 -> [('in:anywhere label:inbox is:unread', True)]

on the wire, mailweave_search("in:inbox is:unread"):
  ('in:anywhere in:inbox is:unread', True)
  scan_scope L3 q='in:anywhere in:inbox is:unread'
```

The probe searches the inbox, sets `includeSpamTrash=true`, declares in `scan_scope` that it
widened to everywhere, and re-observes what L1 already observed (I-3). And
`test_no_query_the_operator_lexicon_can_spell_makes_a_rung_raise` **did** generate `in:inbox` —
it is `FIDELITY_TABLE[OperatorName.IN]` — and passed, because its two assertions are about
listings, not about scope contradiction. So the sweep saw the shape and could not catch it, and
the behavioural test written to close the gap tests the one spelling the fix covers.

**Filed as R-RETR-021, MEDIUM. This is the twelfth "one shape validated, its peers trusted" — at
the test written to close the eleventh.**

### R-RETR-011..016, spot-checked

| finding | verdict on execution |
|---|---|
| **011** relative window declared but not applied | **closed.** `newer_than:7d` → `window_utc.start = 2026-08-27T12:00Z`, the instant the wire `q` actually cuts at; the rendered `date_window` family (`last week` → `after:2026/08/23 before:2026/09/01`) really is sent widened. `/tmp/rretr15/d3_margin.py`, `d1_battery.py` |
| **012** unknown operator on the wire, absent from `asked_for` | **closed for the shape filed** (`thread:abc rollout` → `q='rollout'`, `dropped=[unproven_operator]`, `term_coverage 0.5`) and **regressed for a shape it created** — see R-RETR-018 |
| **013** the L1b bound's missing precondition | **closed as a claim.** The docstring names the page budget; `test_a_truncated_decomposition_page_drops_a_thread_the_bound_does_not_cover` exists; `/tmp/rretr15/a4_paging.py` reproduces the truncation with the thread now a source and 89 withheld records |
| **014** two docstrings contradicting each other | **closed.** `operators.py` now states what `render()` states and quotes its own false sentence. One residue: it claims "a reader of the response can see that MailWeave declined to prove it" — false for the class where the unknown token is the whole query, because there is no response (R-RETR-022) |
| **016** `answered` beside a declared-incomplete scan | **closed.** `/tmp/rretr15/a5_paging_fatal.py` now reports `outcome: inconclusive`, `partial: true`, 188 withheld records |
| **015** | see priority 7 |

### Test-citation sweep

Every `test_…` name cited in `IMPLEMENTER.md` resolves to a real test (28 checked, 28 present).
`test_every_test_a_source_docstring_names_exists` is live (the prior instance planted a stale
citation and it fired).

### A bound on every end-to-end claim in this round, mine and the implementer's

`tests/fixtures/mailbox.py`'s `IMPLEMENTED_OPERATORS` covers **13 of the 21** `OperatorName`
members. `bcc`, `deliveredto`, `category`, `list`, `filename`, `size`, `larger`, `smaller` raise
`UnimplementedOperator` rather than being evaluated, so no query using them can be driven end to
end against the double. That is the fixture being correctly strict, and it is a real ceiling on
every recall statement in this document and in the implementer's.

---

## Findings

```
ID:            R-RETR-017
Severity:      BLOCKER
Reachability:  REACHABLE today. An ordinary query string through LadderRunner.run +
               assemble, both of which exist and execute. No Gmail dependency for the
               wire shape; the disclosure shape follows from the code whatever Gmail
               returns for the composed q.
Rubric:        LEX-02 (mandatory); the work order's own exit condition ("No query causes
               a read outside what it asked for. No response reports `answered` for rows
               that match nothing"); contract I-4's paired hallucinated-found guard;
               AD A.7 L3.
Location:      server/src/mailweave/query/analysis.py, selects_something (judges a
                 fragment by syntax, so '""' passes);
               server/src/mailweave/retrieval/ladder.py, why_this_q_is_not_a_probe (same
                 rule for a whole q) and BroadeningRung._anywhere (composes
                 `in:anywhere ""`);
               server/src/mailweave/query/analysis.py, _build_constraints (an empty
                 quoted phrase becomes a `phrase` constraint; an operator with an empty
                 value becomes that operator's constraint)
Repro:         /tmp/rretr16/r3_vacuous.py, r4_empty_phrase_blast.py, r5_empty_phrase_l3.py
                 mailweave_search('""')      -> wire ('""', False), ('in:anywhere ""', True)
                 mailweave_search('" "')     -> same class
                 mailweave_search('subject:""'), ('subject:" "'), ('""""'),
                   ('"\t"'), ('"\xa0"'), ('"​"')  -> same class
                 mailweave_search('subject:'), ('label:'), ('is:'), ('in:'), ('has:')
                   -> bare operator token on the wire; L3 composes
                      ('in:anywhere subject:', True)
                 mailweave_search('report "" 2026')  -> L1b probes '""' alone
Expected:      A rung that cannot narrow must not widen to everything. `Probe.__post_init__`
               refuses a q that is a listing; LEX-02 requires term_coverage to reflect what
               was executed. A quoted phrase with no content, and an operator with no value,
               name nothing to find.
Actual:        On a mailbox whose default view is empty (all SPAM/TRASH):
                 wire       [('""', False), ('in:anywhere ""', True)]
                 |H| = 10   (6 spam + 4 trash), 10 sources, every row role: matched
                 outcome: answered      term_coverage: 1.0
               On an ordinary mailbox, `""` alone or beside any other constraint pulls the
               entire default mailbox into H at L1 and again at L1b: 12/12 threads
               disclosed as matched under outcome: answered, term_coverage 1.0.
               This is R-RETR-006's three failures — wrong rows, mail nobody asked for,
               and a response saying it succeeded — through a door its fix left open.
Required fix:  `selects_something` and `why_this_q_is_not_a_probe` must judge what a
               fragment can select, not how it is spelled: a quoted phrase whose content
               is empty under whitespace collapse, and an operator with an empty value,
               select nothing and are not probeable units, not probes, and not fragments
               a broadening may carry. Decide deliberately whether such a token should be
               dropped-and-declared (as an unproven operator is) or refused with the rest
               of the query; whichever is chosen, term_coverage must reflect it.
```
```
ID:            R-RETR-018
Severity:      HIGH
Reachability:  REACHABLE today. Any bare quoted phrase containing a colon.
Rubric:        LEX-02 (mandatory: "operators used are limited to Gmail's documented set"
               is satisfied, but "cases where a signal was silently dropped: 0" is not);
               LEX-04 (branch E-b cannot fire for this class); ROUTE-02.
Location:      server/src/mailweave/query/operators.py, tokenise() — `body.partition(":")`
                 runs before the quoted-phrase branch at the end of the loop, so a quoted
                 token containing a colon is classified UNKNOWN_OPERATOR and never reaches
                 `TokenRole.PHRASE`;
               interacting with server/src/mailweave/query/analysis.py, render()
                 (R-RETR-012's fix: unknown tokens are not re-emitted) and
               server/src/mailweave/retrieval/ladder.py, run_parsed
                 (R-RETR-006's fix: an empty ladder plan is refused)
Repro:         /tmp/rretr16/r9_phrase_ops.py, r10_phrase_refusal.py, r27_refusal_audit.py
                 mailweave_search('"9:30 standup"')          -> QueryNotSearchable,
                                                                0 Gmail calls
                 mailweave_search('"Re: quarterly plan"')     -> same
                 mailweave_search('"note: see below"')        -> same
                 mailweave_search('"http://docs.example.test/plan"') -> same
                 mailweave_search('"ratio 3:1"'), ('"Q3: results"'),
                   ('"budget: approved"'), ('"12:00 handover"')     -> same
                 mailweave_search('"9:30 standup" thursday')  -> executes only 'thursday';
                   the phrase is declared dropped as `unproven_operator`, term_coverage 0.5,
                   and is never searched for at any rung
               8 of 50 plausible queries in my audit.
Expected:      A quoted phrase is a phrase search. `_operator_token`'s own docstring says
               so: "The leading quote of a phrase search is deliberately not stripped:
               `"in:anywhere"` is a phrase search rather than an operator, and reading it
               as one would be a false refusal." The tokeniser reads it as one.
Actual:        The whole phrase is reported as "a name:value token outside Gmail's
               documented operator set", removed from the executed q, and — when it is the
               query's only content — the query is refused with zero Gmail calls. Before
               R-RETR-012's fix the token rode into the q inside the residual terms and the
               phrase was searched for (ParsedQuery.render's own docstring records this).
               So the fix for R-RETR-012, joined to the fix for R-RETR-006, turned a
               working phrase search into a refusal. A.8a branch E-b is also unreachable
               for every phrase containing a colon.
Required fix:  Classify a quoted token as a PHRASE before attempting the operator split:
               `name:value` is an operator only when `name` is unquoted. Then a colon
               inside a phrase is content, as it is inside `subject:"note: see below"`,
               which already works.
```
```
ID:            R-RETR-019
Severity:      HIGH
Reachability:  REACHABLE today. Any query naming in:anywhere / in:spam / in:trash
               together with two or more probeable fragments.
Rubric:        LEX-03 (mandatory)
Location:      server/src/mailweave/query/analysis.py, _units_of_one /
                 decomposition_units_of — a mailbox-scope fragment is correctly excluded
                 from being a unit, and no other unit carries it;
               server/src/mailweave/retrieval/ladder.py, DecompositionRung._probe
                 (query=unit.fragment only) and Probe.include_spam_trash (derived from the
                 probe's own q, so the flag flips to false with the operator)
Repro:         /tmp/rretr16/r25_scopedrop.py, r26_scopedrop2.py
                 mailbox: thread t-q, q-1 "rollout" and q-2 "cutover", both labels ("SPAM",)
                 mailweave_search("in:anywhere rollout cutover")
                   wire   [('in:anywhere rollout cutover', True), ('rollout', False),
                           ('cutover', False), ('rollout cutover', False)]
                   |H| = 0   sources = []   outcome = inconclusive
                 same for "in:spam rollout cutover" and "in:trash rollout cutover"
                 contrast "label:archive rollout cutover" -> found (a non-widening scope
                   is itself a unit, so the intersection carries it)
Expected:      LEX-03: a thread whose constraints are satisfied jointly by different
               messages is not missed. The user named the scope explicitly; the rung built
               to recover split evidence must search where it was told to.
Actual:        Every L1b probe drops the scope the user wrote and searches the default
               mailbox with includeSpamTrash=false, so the founding bug's own shape is
               unrecoverable in exactly the place a user goes when the default search
               failed. L2's relaxation drops the scope constraint as well, and L3's
               anywhere probe equals L1's baseline and is not planned. The response is
               honest (inconclusive), so this is a recall failure and not a lie.
Required fix:  A decomposition probe must carry the query's mailbox scope alongside its
               unit's fragment — the scope says *where*, which is orthogonal to what the
               unit selects, and it is the one fragment every probe should keep. The same
               question applies to L2: dropping the scope is a relaxation, but dropping it
               silently at L1b is not.
```
```
ID:            R-RETR-020
Severity:      HIGH
Reachability:  REACHABLE today. Any run whose disclosed evidence came from a probe
               carrying fewer constraints than the query, other than an L2 relaxation
               that matched — i.e. any L3-only recovery, and any L0 stop on a
               multi-constraint query.
Rubric:        LEX-02 (mandatory; "every dropped signal is named with the rung that
               dropped it. Cases where a signal was silently dropped: 0")
Location:      server/src/mailweave/retrieval/assemble.py, _asked_for
                 `enforced = tuple(c for c in parsed.constraints
                                   if c.name not in set(dropped_names))`
                 where `dropped_names` is populated only from probes with
                 `Probe.relaxes` (True at L2 and nowhere else — assemble.py, the
                 `disclosed_dropped` loop)
Repro:         /tmp/rretr16/r14_l3only.py, r12_l0stop.py, r13_enforced.py
               (a) mailbox: one SPAM message from marketing@vendor.invalid whose body
                   says "cutover"; one inbox message from ana@team.example, unrelated
                   mailweave_search("from:bob@team.example cutover")
                     only disclosed row: the spam message, admitted by L3's
                       'in:anywhere cutover' (reason names that q)
                     asked_for.enforced  ('from', 'terms')
                     asked_for.dropped   []
                     term_coverage 1.0   constraint_drop_depth 0   outcome answered
               (b) mailweave_search('"vendor selection review" cutover'), D.3-1b stop at L0
                     executed q '"vendor selection review"' only
                     asked_for.enforced ('phrase', 'terms')   dropped []
                     term_coverage 1.0   outcome answered   sufficiency sufficient
                     a thread carrying only the phrase disclosed as role: matched
Expected:      LEX-02: a parsed signal is either enforced in the executed q or reported as
               dropped, with the rung that dropped it. `from:` was not enforced on the
               route that produced the only evidence; `cutover` was never sent at all.
Actual:        `enforced` is a statement about the parse minus L2's drops, not about what
               any probe carried, so L3's abandonment of `from:` and an L0 stop's
               non-execution of `terms` are both invisible. term_coverage and
               constraint_drop_depth inherit the error. The per-row `constraint_coverage`
               is honest in both cases, which makes the response-level claim contradict its
               own rows.
Required fix:  Derive `enforced` from what the probes that produced the disclosed evidence
               actually carried (`Probe.enforced` is already recorded per probe and is
               already correct), and name the rung for each drop. `Probe.relaxes` should
               continue to distinguish an *abandonment* from a decomposition sibling, but
               "not a relaxation" must not mean "was enforced".
```
```
ID:            R-RETR-021
Severity:      MEDIUM
Reachability:  REACHABLE today. Any query whose only constraints are a narrowing mailbox
               scope plus non-text operators — `in:inbox`, `in:sent`, `in:drafts`,
               `in:chats`, `label:inbox`, alone or with is:/has:/from:.
Rubric:        LEX-02 (asked_for/scan_scope correctness); contract I-3 (adaptive cost);
               AD A.7 L3
Location:      server/src/mailweave/retrieval/ladder.py, BroadeningRung._anywhere — the
               fragment filter is `carries_nothing_but_mailbox_scope(fragment)`, which is
               defined over WIDENING_MAILBOX_OPERATORS only, so a *narrowing* scope
               fragment is conjoined rather than replaced;
               tests/test_lexical_ladder.py::test_a_broadening_probe_does_not_carry_a_
               narrower_scope_than_the_one_it_widens_to, which asserts only the
               SPAM_OPERATOR spelling
Repro:         /tmp/rretr16/r17_narrow_scope.py, r18_l3wire.py
                 'in:inbox'                -> L3 ('in:anywhere in:inbox', True)
                 'in:inbox is:unread'      -> L3 ('in:anywhere in:inbox is:unread', True)
                 'in:drafts is:unread'     -> L3 ('in:anywhere in:drafts is:unread', True)
                 'in:chats has:attachment' -> L3 ('in:anywhere in:chats has:attachment', True)
                 'label:inbox is:unread'   -> L3 ('in:anywhere label:inbox is:unread', True)
               on the wire, mailweave_search("in:inbox is:unread"):
                 ('in:anywhere in:inbox is:unread', True)
                 scan_scope L3 q='in:anywhere in:inbox is:unread'
Expected:      The test's own docstring: "a scope operator the user wrote is replaced
               wholesale by ANYWHERE_OPERATOR … Conjoining the two instead sends the
               widening operator beside a narrowing one, which searches the narrower
               scope: a broadening probe that does not broaden, and a second scan_scope
               entry saying it did."
Actual:        Exactly that, for every narrowing scope operator. The probe searches the
               inbox, sets includeSpamTrash=true, declares `in:anywhere …` in scan_scope,
               and costs a Gmail call to re-observe what L1 observed.
               The operator sweep did generate `in:inbox` (it is FIDELITY_TABLE's `in`
               spelling) and passed, because its assertions are about listings rather than
               about scope; the behavioural test written to close this gap uses the one
               spelling the fix already covers.
Required fix:  Replace *any* mailbox-scope fragment when widening, not only a widening
               one; and widen the test to the narrowing spellings, driven from a named
               vocabulary rather than one literal, so the assertion's scope equals the
               claim's scope.
```
```
ID:            R-RETR-022
Severity:      MEDIUM
Reachability:  REACHABLE today. 17 of 50 plausible queries in my audit produce no
               response at all.
Rubric:        ROUTE-01 (currently PASS — statement, not the Round-1 evidence);
               AD A.2 ("There is never a bare empty result"), D.3 rule 6, contract C-08
Location:      server/src/mailweave/retrieval/ladder.py, run_parsed — raises
                 QueryNotSearchable and builds no Envelope;
               server/src/mailweave/envelope/response.py,
                 Envelope._no_bare_empty_response — refuses `report.rungs == ()`
Repro:         /tmp/rretr16/r27_refusal_audit.py, r10_phrase_refusal.py
                 17/50: 8 quoted phrases with a colon (R-RETR-018), 4 scope-only,
                 4 zero-constraint parse failures, 1 unprovable operator alone.
                 Every one: QueryNotSearchable out of run_parsed, box.calls empty,
                 no Envelope.
Expected:      A.2: "If no rung produced evidence, the same envelope is returned carrying
               a RetrievalReport instead of hits: queries executed, constraints dropped
               and why, hit counts per rung, empty_diagnosis, rungs not tried and why, and
               the affordances that would try them (C-08, ROUTE-01/04)."
Actual:        No envelope. I verified the implementer's stated reason is true of the code:
               a zero-rung structured report is not constructible without naming a rung
               that did not run, because `_no_bare_empty_response` requires
               `report.rungs`. The schema change is WS-10's and the escalation is right.
               The finding is not thereby closed: the refusal's reach is now the phrase
               class and the unprovable-operator class as well as the parse failures it was
               designed for, and `operators.py`'s claim that "a reader of the response can
               see that MailWeave declined to prove it" is false for a query that is
               nothing but such a token.
Required fix:  Either the envelope schema carries a zero-rung structured report (WS-10's
               contract question, with this reproduction), or `run_parsed` produces an
               envelope naming the five rungs as not_applicable with the refusal in
               empty_diagnosis. Narrowing the refusal class (R-RETR-017, R-RETR-018) is a
               precondition either way. I recommend the orchestrator treat ROUTE-01 as
               called into question until this is resolved; I mark nothing.
```
```
ID:            R-RETR-023
Severity:      MEDIUM
Reachability:  REACHABLE today. Every zero-hit single-unit query — one bare word or one
               quoted phrase, the commonest query shape there is.
Rubric:        ROUTE-04 (mandatory); AD-03 (affordances are concrete calls); ADV-105
Location:      server/src/mailweave/retrieval/assemble.py, _empty_diagnosis — the
                 `incomplete` branch, whose affordance is
                 {"relax": {"max_probes": len(parsed.constraints)}};
               server/src/mailweave/retrieval/ladder.py, RelaxationRung.plan — a probe
                 whose remaining constraints render an empty q is never planned, at any
                 budget
Repro:         /tmp/rretr16/r24_k1.py
                 mailweave_search('"the migration window slips"')   [0 hits]
                   empty_diagnosis: incomplete, tried=(), untried_drops=('phrase',),
                                    restores=None
                   affordance     : {'relax': {'max_probes': 1}}
                   max_relax_probes(1) == 1 already; RelaxationRung().plan(parsed) == []
                 same for 'teleportation' (untried_drops=('terms',))
Expected:      ADV-105/OD-2: "the probe budget ran out" and "no single drop restores
               results" are different findings and must not share a shape. AD-03: an
               affordance is a concrete {tool, args} pair that would reach the untried
               rung.
Actual:        A third case — "this drop can never be probed, at any budget" — is reported
               as `incomplete` (the budget shape) with an affordance that re-runs the query
               with the budget it already had. Following it changes nothing.
Required fix:  Distinguish a drop the budget did not reach from a drop that is structurally
               unavailable, and do not mint a relaxation affordance for the second. This is
               the part of R-RETR-015 that is `assemble`'s rather than A.7's; the recovery
               route itself remains correctly deferred to A.7 / WS-10.
```
```
ID:            R-RETR-024
Severity:      MEDIUM
Reachability:  REACHABLE today. Any query of two or more units whose conjunction matches
               nothing at L1 — which is now the ordinary two-word query.
Rubric:        LEX-02 (asked_for correctness), LEX-03 (the cap's documented cost),
               EV-05's recency clause; AD A.7 L1b cap row
Location:      server/src/mailweave/retrieval/ladder.py, DecompositionRung (the cap and
                 the deliberately broad per-unit probes);
               server/src/mailweave/retrieval/assemble.py, assemble/_asked_for (nothing
                 at response level separates an intersection member from a fragment hit)
Repro:         /tmp/rretr16/r22_scale.py, r21_window.py, r13_enforced.py
               (a) 41 messages: 20 threads with only "rollout", 20 with only "cutover",
                   one split thread with both. mailweave_search("rollout cutover"):
                     12 sources (the split thread first, correctly preferred),
                     11 single-word threads, all rows role: matched, 29 withheld,
                     outcome answered, term_coverage 1.0
               (b) mailweave_search("newer_than:7d rollout"): a message dated 2025-01-05
                     disclosed role: matched while window_utc.start is 2026-08-27T12:00Z;
                     enforced ('newer_than','terms'), term_coverage 1.0, outcome answered
               (c) mailweave_search("from:ana@team.example rollout cutover handover"),
                   4 units against the cap of 3: a thread no message of which contains
                   "handover" is disclosed with all three rows matched, enforced
                   ('from','terms'), term_coverage 1.0, outcome answered
Expected:      The response should be able to say that the disclosed evidence answers part
               of the query. LEX-03's cap claim ("costs precision and never recall") is
               true of recall and says nothing about how the precision cost is disclosed.
Actual:        `constraint_coverage` per row is honest (empty for a piece-probe) and
               `scan_scope` lists the probes actually sent, so a careful reader can
               reconstruct it — but `outcome: answered`, `term_coverage: 1.0` and
               `enforced` naming every constraint are all response-level claims that the
               query was answered. Round 15's `rollout cutover` said `inconclusive` with
               zero sources; round 16's says `answered` with twelve, eleven of which do
               not satisfy the query.
Required fix:  Scope the response-level claim to what was actually satisfied: derive
               `sufficiency`/`outcome` (or a declared field) from the intersection rather
               than from disclosure alone when L1b is the only rung that produced rows,
               and declare the L1b cap when it binds (which unit was not probed). No
               change to the rung's recall behaviour is implied.
```
```
ID:            R-RETR-025
Severity:      LOW
Reachability:  REACHABLE today. Any query repeating an identical operator fragment.
Rubric:        none — contract I-3 (adaptive cost); LEX-03 adjacent
Location:      server/src/mailweave/query/analysis.py, ConstraintUnit (docstring: "`label`
                 is unique within a parse"; it is `f"{name}[{fragment}]"`, so identical
                 fragments collide);
               server/src/mailweave/retrieval/ladder.py, _after_rung's L1B branch —
                 `by_unit = {entry.probe.unit: entry.threads …}` keeps the later probe
Repro:         /tmp/rretr16/r28_dupunit.py
                 parse('has:attachment has:attachment') -> two units, same label
                 parse('label:alpha label:alpha')       -> two units, same label
                 mailweave_search("from:ana@team.example from:ana@team.example cutover")
                   wire: L1b sends 'from:ana@team.example' twice, then 'cutover'
                   by_unit: {'from[from:…]': [], 'terms': []}   intersection: []
Expected:      One label per probe, and no probe that repeats another probe's q.
Actual:        A duplicate fragment spends one of the three A.7 decomposition slots on an
               identical query, and the dict collapse keeps the second probe's admission
               delta, which is empty because the first already admitted everything — so
               the intersection is empty and L1b's finds are disclosed at `stub` depth
               rather than `body_clean`.
Required fix:  De-duplicate fragments when building units (a repeated fragment is one
               unit), or make `label` unique by position. The docstring's uniqueness claim
               should be executed by a test rather than asserted.
```

---

## Recommendations, per criterion

**I mark nothing. Every recommendation is scoped, and I name what my evidence does not cover.**
WS-04 targets LEX-01..04, EV-02, EV-04..06 and ROUTE-02..04; I revisit each of the prior
instance's six recommendations on this round's code.

* **LEX-01 · Message-level search is the first rung — RECOMMEND PASS, scoped** (prior instance:
  PASS scoped; I confirm on new code).
  Evidence: `call_log[0]` is `messages.list` with a non-empty `q` in every run I drove — the 500-trial
  randomised sweep, the 17-case mis-parse battery, the three exact-signal branches, and every targeted
  probe. `hit_threads` derives `H`'s hit half only from `ObservedEndpoint.MESSAGES_LIST` origins, so no
  thread listing can feed it; message ids are carried into rows, positions and withheld records.
  **Two scope notes a reader of a PASS must have.** R-RETR-017 makes that first call `q='""'` or
  `q='in:anywhere ""'` for the vacuous-fragment class — the letter holds, the spirit does not, exactly
  as the prior instance said of R-RETR-006. R-RETR-018/022 mean that for 17 of 50 plausible queries
  there is **no** first Gmail call at all; "the first call is `messages.list`" is vacuously true there.
  Not covered: the live account.

* **LEX-02 · Operator-parse fidelity and coverage reporting — RECOMMEND NOT PASS** (prior instance:
  NOT PASS; unchanged, on new grounds).
  The fidelity half is re-established independently: 21/21 `OperatorName` members parse and reach L1's
  executed `q`; negation, quoting and angle-address normalisation correct; and the two prior defects in
  the coverage half are genuinely closed (R-RETR-011 declares the instant the `q` cuts at; R-RETR-012
  keeps an unprovable token off the wire and names it). The coverage half still fails on three
  executed counts, all new this round: **R-RETR-017** (`term_coverage: 1.0` over a whole-mailbox read),
  **R-RETR-018** (a quoted phrase reported as an unproven operator, and the query refused),
  **R-RETR-020** (a constraint L3 or an L0 stop abandoned, reported as `enforced`, `drop_depth 0`).
  The acceptance clause "cases where a signal was silently dropped: **0**" is not met.
  One scope question I did **not** score against the criterion: an L1b piece-probe's rows carry
  `constraint_coverage: ()`. The field is present and the emptiness is the conservative direction the
  code argues for; whether "every disclosed message carries `constraint_coverage`" is satisfied by an
  empty tuple is a contract reading, not an execution result.

* **LEX-03 · Multi-constraint decomposition — RECOMMEND NOT PASS** (prior instance: NOT PASS; much
  closer now, still not).
  Established and reproducible: two, three, four and five bare words; phrase + word; two and three
  phrases; repeated `from:`, `label:`, `subject:`; `subject:` + two terms; a written-out date window as
  **one** unit; the founding shape recovered under a D.3-2 stop that actually fires; and R-RETR-007's
  stop no longer switching the rung off. That is the project's founding bug, fixed at the constraint
  model rather than at the rung, and it is the strongest thing in this round.
  Blocking: **R-RETR-019** — a query naming `in:anywhere`/`in:spam`/`in:trash` loses that scope at
  every decomposition probe, so the same shape in spam or trash is unrecoverable. Independently, the
  criterion's recall bar is `[UNSET — register at G0]` against a Baseline D that does not exist, so no
  rate can be reported by anyone this round.

* **LEX-04 · Exact-signal stop — RECOMMEND PASS, scoped** (prior instance: PASS scoped; I confirm,
  with one new scope note).
  Re-established on all three A.8a branches against a 40-message thread: **rungs executed = 1**,
  `stop_rule` D.3-1 / D.3-1b / D.3-1b, **3 Gmail calls measured at the transport boundary**
  (`messages.list`, `messages.get`, `threads.get`), zero embedding, model and reranker calls (none
  exist; the `generative-client` guard is clean). The predicate takes no corpus or frequency parameter.
  **New scope note:** R-RETR-018 means branch **E-b cannot fire for any phrase containing a colon**,
  so the exact-lookup family this PASS is measured over is narrower than it appears. And R-RETR-020
  shows that when the E-b stop fires on a *multi-constraint* query the response over-reports
  `enforced` — a LEX-02 defect reached through LEX-04's stop, not a LEX-04 defect.
  Not covered, unchanged: the criterion's cost bar is a network-level median over a family
  distribution. A `MockTransport` boundary is one case per branch. **WS-16 / R-PERF.**

* **EV-02 · Position-independent evidence recall — CANNOT ESTABLISH.** No EP §4.4 corpus, no ~100-
  message thread, no holdout seed, no two-seed CI, no DISC-04/PERF-01 on the same run. I re-ran the
  prior instance's 40-message position sweep as a regression only. **WS-16.**

* **EV-04 · Zero false "not found" — RECOMMEND NOT PASS, with the letter noted.** Over roughly 600
  executed runs this round, `not_found` was never emitted and cannot be — `NOT_FOUND` appears nowhere
  in `retrieval/` — so the rate is trivially 0 and stays 0 while `outcome` has two reachable values.
  That is not evidence for the criterion. Its **paired hallucinated-found rate**, which the criterion
  says may never be reported alone, is what R-RETR-017 and R-RETR-020 are shaped like: a mailbox read
  reported as matches, and a route's abandonment reported as enforcement. **WS-16** for the
  measurement; the two findings block regardless.

* **EV-06 · Recall against the full-dump ceiling — CANNOT ESTABLISH.** No Baseline B, no corpus
  instance, no paired scoring, no interleaved session. **WS-16.**

* **ROUTE-02 · Mis-parse recovery — CANNOT MARK PASS; measured on a set I built, and the shortfall is
  named.** On **my own 17-case set** built this round (`/tmp/rretr16/r23_misparse.py`, a four-message
  answering thread plus noise): **14/17 recovered, 0 false-not-found, 2 refused, 1 genuinely not
  recovered.** The one true failure is the phrase near-miss — R-RETR-015's remaining half. Both
  refusals are R-RETR-018 (`"week two: migration window"`) and the unprovable-operator class. On the
  prior instance's 12-case set, re-run as a regression, recovery is **11/12** (was 8/12); I report that
  as a regression check only, not as evidence, and I note explicitly that I found no sign of tuning
  against it — the two cases that moved are explained by the L1b constraint-model change and by
  R-RETR-012's drop, both of which I verified on my own cases first.
  The bar is `[UNSET — register at G0]`, so no one can mark this criterion this round.

* **ROUTE-03 · Relaxation is systematic and enumerable — RECOMMEND PASS, scoped** (prior instance:
  PASS scoped; I confirm on the new constraint model, which is what could have broken it).
  Re-established by independent replay on a 5-constraint query: exactly one constraint dropped per
  probe; order is `RELAXATION_ORDER` with ties by write order; the **published plan and the executed
  sequence are equal as ordered lists** — `['after','from','to','subject','terms']`; each step logs its
  dropped constraint, `q` and hit count; `max_relax_probes = min(k,6)` binds at k=8 with the two
  unreached drops named. The round-16 `ConstraintUnit` change did **not** disturb it: `Constraint`
  remains the droppable unit and `_ordered_for_relaxation` still ranges over `parsed.constraints`.
  Scope: the guarantee still has no subject when the query is one unit (R-RETR-023), which is a
  ROUTE-04/ROUTE-02 gap rather than a ROUTE-03 one, but a reader of a PASS should know it.

* **ROUTE-04 · Empty-result diagnosis — RECOMMEND NOT PASS** (prior instance: PASS scoped; **I
  disagree with that on this round's code and say so plainly**).
  What holds is unchanged and I re-executed it: `complete` with the correct `restores` on constructed
  cases whose restoring constraint I chose — **7/7** on my mis-parse battery where a single drop does
  restore (`terms` twice, `label`, `subject`, `to`, `cc`, `from`), and **3/3** correct
  `restores: None` where no probed drop restores (the two wrong-window cases and the wrong `is:`
  state), `complete`/`restores: None` when nothing restores,
  `incomplete` with a complete `untried_drops` at the `min(k,6)` budget, `None` on an answered
  response, and `outcome: inconclusive` in every incomplete case.
  What blocks: **R-RETR-023.** For every single-unit query the diagnosis reports `incomplete` — the
  budget shape — for a drop no budget can reach, and mints an affordance that re-runs the query with
  the budget it already had. ADV-105's defect was precisely two different findings sharing one shape;
  there are now three sharing it, and the third ships a call that does nothing. That is inside
  ROUTE-04's acceptance ("Where the probe budget ran out before all single-constraint drops were tried,
  `empty_diagnosis.status` is `incomplete`, `untried_drops` is complete") — the budget did not run out.
  The incomplete-diagnosis-rate ceiling is `[UNSET — G0]` independently.

* **ROUTE-01 · No bare empty response — currently PASS; RECOMMEND the orchestrator treat it as
  called into question.** Not a WS-04 target and not mine to mark, recorded because this round's diff
  reaches it. Round 1 passed it on `_no_bare_empty_response` probes at the envelope layer, which remain
  true. Round 16 added a path in which no envelope is built at all, for 17 of 50 plausible queries
  (R-RETR-022). Under this project's own round-4 and round-9 precedent, that is a criterion whose
  evidence a reviewer has called into question.

* **EV-05 — adjacent, not a WS-04 target, one note.** Clause 2 (recency) is now *better* than round 15
  on the declaration side — `window_utc` states the instant the `q` cuts at (R-RETR-011 closed) — and
  *worse* on the disclosure side: R-RETR-024(b) puts a January-2025 message into a
  `newer_than:7d` response as `role: matched` with `term_coverage: 1.0`, because L1b's term probe
  carries no date. Both halves still need the live account.

---

## Overall verdict

**Round 16 does not close.** One BLOCKER, three HIGH and five MEDIUM/LOW findings, all reachable
from ordinary query strings through code that exists and executes today.

**What the round got right, and it is a lot.** The BLOCKER is closed for the shape it was filed
against. R-RETR-007 is fixed at both ends and I proved it on a case where the stop actually fires
rather than one where it no longer can. R-RETR-008 is fixed **at the constraint model**, which is
what the work order asked for, and it holds for every kind at once — bare words at two through
five, phrases, repeated operators, and a written-out date window that correctly refuses to split.
R-RETR-009's assembly no longer invents an order, and its peer — one missing `internalDate` rather
than all of them — behaves identically. R-RETR-010's blast radius is gone: five healthy threads
survive a sixth that disagrees with itself, `H = disclosed ∪ withheld` across every new path in 500
randomised trials, and A8's corrected text is true of the code clause by clause, including the
"nothing wider" claim, which I tested by planting a wider one and watching the envelope refuse it.
The six inherited defects the implementer reports are real and are fixed — I planted all six back
my own way and all six were caught. The 12/12 plant claim reproduces independently, and the
harness is not testing the real tree.

**What it got wrong is the same thing, three more times.** Every one of my HIGH findings and the
BLOCKER lives at a *join*: R-RETR-017 where the round's own "must select something" rule meets a
token that selects everything while looking like a selector; R-RETR-018 where R-RETR-012's fix
meets R-RETR-006's; R-RETR-019 where R-RETR-006's fix meets R-RETR-008's; R-RETR-021 at the test
written to close the previous instance of exactly this. The implementer asked "what is the next
object over that my fix's rule should also be true of?" three times and found something every
time — and the question was asked of the *objects* the fix touched, not of the *rules* the fix
composed with. The three fixes are each right about the shape they were written for.

The work order's exit condition has four clauses. **Two bare words split across two messages of one
thread are found** — yes, and at three, four and five words too. **No order is presented as
chronological unless it is** — yes. **One self-disagreeing thread does not deny a response** —
yes. **No query causes a read outside what it asked for, and no response reports `answered` for
rows that match nothing** — no: `mailweave_search('""')` reads spam and trash and reports ten
threads as matched under `answered` / `term_coverage: 1.0`.

---

## Established by execution

* All gates reproduce, twice: ruff, format (153), mypy --strict (127), 7 guards, **2,235 tests**,
  rubric unchanged at 7 PASS / 0 FAIL / 0 BLOCKER / 106 NOT TESTED, 11 transitions.
* **R-RETR-008 is fixed at the constraint model.** Two, three, four and five bare words; phrase +
  word; two and three phrases; `from:a from:b`; `label:a label:b`; `subject:a subject:b`;
  `subject:` + two terms; a written-out `after:X before:Y` as one joint unit; a crossing date pair
  claiming no window instead of raising. Unicode, punctuation and case all decompose.
* **R-RETR-007 is fixed under load**: with `answer_type_presence` genuinely true and D.3 rule 2
  firing, `halts_after` is L1b, L1b runs, and the split thread is recovered.
* **R-RETR-009**: a `threads.get` that states no chronological position — for all messages or for
  one — yields no source, a `not_included_sources` entry, `partial_source_failure` withheld records
  with affordances, and `outcome: inconclusive`.
* **R-RETR-010**: five healthy threads survive a sixth that disagrees with itself;
  `NotIncludedSource.stated_total` is `null` on disagreement and the enumeration otherwise; the
  envelope serialises; both A8 validators still refuse a `Source` at 9 and at 10; and the
  ≥-observed floor binds a `NotIncludedSource` too, which is what makes A8's "and nothing wider"
  heading accurate.
* **`H = disclosed ∪ withheld` in 500 randomised mailbox × query trials**, witnessed from outside
  the process by the double's own returned-ids log, with refusal, decomposition, whole-thread
  withholding and `stated_total: null` among the paths exercised. Zero violations, zero crashes.
* **0 raises over 676 singles-and-pairs and 7,980 ordered triples** of the operator lexicon; no
  planned probe is a listing by the module's own two predicates, at either arity.
* **The six inherited defects are real and fixed** — all six planted back independently, all six
  caught. **The 12-plant harness is sound**: imports verified inside the scratch tree two
  independent ways, 12/12 reproduced.
* **ROUTE-03 in full** on the new constraint model: planned drops == executed drops as ordered
  lists, `['after','from','to','subject','terms']`.
* **LEX-04**: one rung and three transport-level Gmail calls on all three A.8a branches, zero
  model/embedding/rerank calls.
* Mis-parse recovery on **my own** 17-case set: 14/17, 0 false-not-found.

## False on execution

* **"A rung that cannot narrow must not widen to everything"** — `mailweave_search('""')` puts
  `('in:anywhere ""', True)` on the wire and returns spam and trash as `role: matched` under
  `answered` / `term_coverage: 1.0` (R-RETR-017).
* **`_operator_token`'s "`"in:anywhere"` is a phrase search rather than an operator, and reading it
  as one would be a false refusal"** — `tokenise` reads every quoted phrase containing a colon as an
  operator, and the query is falsely refused (R-RETR-018).
* **`operators.py`'s "a reader of the response can see that MailWeave declined to prove it"** —
  false for a query that is nothing but such a token: there is no response (R-RETR-018/022).
* **`test_a_broadening_probe_does_not_carry_a_narrower_scope_than_the_one_it_widens_to`** — the
  behaviour its docstring forbids happens for every narrowing scope operator; the test asserts the
  one widening spelling the fix covers (R-RETR-021).
* **`asked_for.enforced` as a statement about what was searched** — a constraint L3 abandoned or an
  L0 stop never executed is reported enforced, with `term_coverage: 1.0` and
  `constraint_drop_depth: 0` (R-RETR-020).
* **`ConstraintUnit`'s "`label` is unique within a parse"** — a repeated identical fragment produces
  two identical labels and an empty intersection (R-RETR-025).
* **A.2's "There is never a bare empty result"** — 17 of 50 plausible queries produce no envelope at
  all (R-RETR-022).
* **`empty_diagnosis`'s `incomplete` meaning "the budget ran out"** — for a single-unit query it
  means "this drop is unreachable at any budget", and the affordance it ships is a no-op
  (R-RETR-023).
* **L1b's scope handling** — a query naming `in:anywhere` has that scope dropped from every
  decomposition probe, and the founding bug's shape in spam is unrecoverable (R-RETR-019).

## Not establishable here at all

I have no live Gmail, no seeded corpus, no Baseline B or D, and no counting proxy. Nothing in this
review is evidence for any of the following.

* **EV-02** (EP §4.4 position sweep on a ~100-message thread, reviewer-chosen holdout seed, two
  seeds within CI, DISC-04 + PERF-01 on the same run) — **WS-16**.
* **EV-06** (recall within 2 points of Baseline B, paired McNemar, same corpus instance) — **WS-16**.
* **EV-04**'s rate and its paired hallucinated-found rate on unanswerable controls — **WS-16**.
* **LEX-03**'s recall bar, **ROUTE-02**'s recovery bar and **ROUTE-04**'s incomplete-diagnosis
  ceiling — all `[UNSET — register at G0]`. **G0.**
* **LEX-04**'s network-level median-≤3 bar over a family distribution — **WS-16 / R-PERF**.
* **EV-05**'s live-account half, and **PF-9** (whether real Gmail's `q` is thread-wide — I executed
  message-scoping against the double, which is a fact about the double) — **credentials, R-GMAIL**.
* **PF-1** (whether real Gmail returns a `threads.get` omitting its own `messages.list` hit) and
  **PF-2** (whether `format=metadata` omits `internalDate`). Both code paths are live and now
  correct either way; their frequency is not mine to measure.
* **PF-14** (the real `after:`/`before:` boundary), which decides whether `date_margin_days` is 1
  or 0. R-RETR-011 is closed by the option R-RETR named; the value is PF-14's.
* **PF-13** (the `answer_type_presence` base rate). R-RETR-007's fix makes D.3 rule 2 fire only on
  `present is True`, which raises rather than lowers the stakes on that measurement: the predicate
  now decides whether the stop fires at all, and I could not measure how often it is true.
* **Whether the eight `OperatorName` members the double does not evaluate behave as claimed.**
  `IMPLEMENTED_OPERATORS` covers 13 of 21; `bcc`, `deliveredto`, `category`, `list`, `filename`,
  `size`, `larger`, `smaller` cannot be driven end to end. Every recall statement in this document —
  and in the implementer's — is bounded by that.
* **Whether A8's retained arithmetic is retained *verbatim*.** This is not a git repository and I
  have no round-15 text to diff against. I established that the arithmetic is *correct* and that the
  heading over it is *accurate*; "verbatim" I took on the implementer's word and could not check.
* **Whether the historical "757 of 2,300" counts are exact.** I established that the six inherited
  defects are real (each plant reproduces a distinct failure) and that the current tree raises on
  **0 of 676** singles-and-pairs and **0 of 7,980** triples. The pre-fix per-rung breakdown is a
  claim about code that no longer exists, and I did not rebuild the intermediate state to count it.
* **Whether a future MCP surface would pass the query shapes R-RETR-017 and R-RETR-018 fire on.**
  There is no MCP surface. I judged both reachable on the code that exists; a caller that sanitised
  input would narrow but not remove them — `"Re: quarterly plan"` and `report "" 2026` are valid
  queries by any input rule.
