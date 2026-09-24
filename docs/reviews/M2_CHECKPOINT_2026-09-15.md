# M2 checkpoint, 2026-09-15 (`ba99c7a`): what is closed, what blocks acceptance, what is next

Written after the real-model diagnostic and trace closed the backend-on delivery regression
(`docs/reviews/INTEGRATION_REPAIR_2026-09-15.md` §8, R-M2-100). It uses evidence already in the
repository and runs nothing new. It does not reopen the repaired mechanism, rerun the campaign,
rebuild the corpus or begin M3.

**Where M2 stands in one paragraph.** Everything M2's **Build** line names is built, reviewed
and committed. Nothing M2's **Accept** line names has run. The work of the last three days was
diagnosis and repair of defects found *while preparing to measure*, not measurement: the
navigation redesign (A14), then the integration repair (A15), then the real-model confirmation
that the semantic arm no longer loses cases the lexical arm delivers. That is a floor, not a
result. The registered hypotheses H1, H2 and H3 remain unmeasured, and the two findings the
real trace produced (R-M2-101, R-M2-102) say the semantic rung currently pays a cost no
measurement supports and has no path by which a correct retrieval becomes a better response.

---

## 1. What still blocks M2 acceptance

M2's **Accept** line, from `docs/ORIVRA_V1_PLAN.md` §M2, is: *H1, H2, H3 measured on F1-F17
against the v0.1 lexical arm; `generative_llm_calls` stays zero on F1/F2 traces; the injection
fixtures pass; any hypothesis that fails removes its machinery from the default path rather
than being argued with.* Five things stand between here and that, in the order they bind.

**(a) There is no case file for F1-F17.** Everything around the questions is built: the
generator, the answer key, the schema, the joins, the four arms, the scoring, and an export kit
(`mailweave_harness.evaluation --export-kit DIR`) that hands an independent author the brief,
the field list, the families, the hypotheses and a standalone checker. The questions themselves
are not written, and by the project's own rule they cannot be written here: an implementer
writing them writes the exam it is sitting. The fifteen-case diagnostic set is not a substitute
and says so in its own metadata (`sufficient_for_m2_acceptance: false`); it was authored for
diagnosis, covers four mechanisms rather than seventeen families, and every run of it prints
that it is not an acceptance run.

**(b) The corpus content gate is open.** R-M2-067 through R-M2-073 are unclosed and the fifth
independent content read stands at NO. They are not cosmetic: R-M2-069 measures an odds ratio
of about 29 for hedging cues between evidence and distractors, R-M2-070 shows content-free
thread shape identifying the family, and R-M2-072 shows evidence positions fixed within a
family. A corpus that gives the family away from register or shape cannot support a claim about
retrieval. The real-model run measures the residual directly: the query-free baseline qf-1,
handed the right conversation and no query, answers 6 of 13. Until that gate closes, an H1/H2/H3
number would be a number about the corpus.

**(c) No live mailbox, and no approved first write.** The seeding driver, its four refusals,
the settle gate and the cleanup are built and tested against a double and have never touched a
mailbox; the approval (`--approve-writes-to <account>`) has not been given. PF-4b, PF-10 and
PF-5 are registered and unrun, and GMAIL-01's live smoke suite has the same prerequisite.
**Corrected 2026-09-16: the prerequisite is PF-10's and GMAIL-01's, not PF-4b's or PF-5's** -
see the amendment below, item 4. (c)'s first clause is also overtaken: writes *were* approved
and executed once, and the corpus was cleaned up afterwards.

**(d) H2 and H3 have no measurement of any kind yet**, and H1 has none on the registered
families. What exists is delivery on a diagnostic set under known-target reachability. The
acceptance runner that would produce the registered numbers is not built.

**(e) The two open real-model findings bear on what the answer could be.** R-M2-102: on this
corpus no semantic score can promote a thread into the mapped set, because `max_hit_threads`
cuts the pre-ranking order and the D.7 ranking reorders only what survived the cut. R-M2-101:
the rung's first-response cost comes from its probes admitting their whole result set to `H`,
which no model changes. If H2 or H3 were measured today and failed, the plan's own rule ("any
hypothesis that fails removes its machinery from the default path") would fire against
machinery that has not yet been given a path to succeed. Deciding (e) before measuring is
cheaper than measuring twice.

*Nothing in the A14 or A15 repairs changes any of (a) to (d).* They removed defects that would
have contaminated the measurement; they did not advance it.

### Amended 2026-09-15, later the same day: (c) and (d) were stale, and the correction is specific

The owner's A16 authorisation said: *"Before building acceptance infrastructure, correct the
checkpoint's stale inventory. The evaluation runner and historical live-seeding records already
exist. Identify exact missing or unverified capabilities, not a blanket 'not built.' Do not
duplicate the runner or reseed."* Both (c) and (d) said "not built" about capabilities that
exist and have run. **Nothing below is to be built again**: the runner is not to be duplicated
and the corpus is not to be reseeded.

**(c) is wrong as written: the live path has been exercised end to end.** *(Further corrected
2026-09-16: the cleanup covered the **malformed** insertion only. Its 2,248 deleted ids are all
in `verification-gate-1042.MALFORMED-R-M2-033.json` and none are in `verification-gate-1042.json`,
whose reseed is timestamped after the cleanup - so a corpus may still be in that mailbox. See
`docs/reviews/M2_ACCEPTANCE_HANDOFF_2026-09-16.md` §2.)* Writes
*were* approved and executed against `mailweave.test@gmail.com`. `benchmarks/seeding-gate-1042.log`
records 2,248 messages in 40 threads inserted with `writes approved: yes`; the settle gate
reported 40 discrepancies on the first attempt and **0 on the rerun**
(`benchmarks/seeding-gate-1042.rerun.log`); `benchmarks/cleanup-campaign.log` records all 2,248
recorded ids deleted, 0 already gone and 0 failed, with the verification and cleanup reports
preserved (`benchmarks/verification-gate-1042.json`, and the two `…MALFORMED-R-M2-033.json`
records kept as evidence of that finding). What is true is narrower and is what (c) should have
said - *and which is now itself corrected: whether a corpus is seeded in that mailbox right now
is **unestablished**, because the cleanup that was read as removing it deleted a different set of
ids* - and `benchmarks/manifest-gate2-2087.json` (2,452 messages) has no seeding log, so that manifest
has never been live. A campaign needs a fresh seed from an existing manifest, not a new driver.

**(d) is wrong as written: the acceptance runner is built.** `mailweave_harness.evaluation`
carries `--run` (the four-arm factorial, the primitive floor, the query-free baseline, the
report and the hypothesis verdicts), `--dry-run` (the whole pipeline offline on the dummy
corpus), `--live-check` (the whole campaign command against the real seeded mailbox on a
sentinel-token case file), `--validate`, `--schema` and `--export-kit`; it is covered by
`tests/test_acceptance_runner.py` and `tests/test_evaluation_harness.py`.

**What is actually missing or unverified, named exactly:**

  1. **The F1-F17 case file.** Genuinely absent, and by the project's own rule it cannot be
     written here. Unchanged from (a).
  2. **`--live-check` has never produced a record.** The live path of the *runner* (as opposed
     to the seeder, which has run live) is tested against a double only. This is one command
     against a freshly seeded mailbox and it is the smallest thing that would move (c) and (d).
  3. ~~**No arm isolates the cross-encoder.**~~ **Closed 2026-09-16** (ledger R-M2-116). A
     third factor and one arm, `no-rerank`: stage-A embedding on, D.7's second tier genuinely
     absent - no backend acquired for it, no pair scored, no score fabricated, and the
     registered `mailweave/mechanical-v1` ordering standing. `full` against `no-rerank` is H2's
     matched pair and `mailweave-evaluation --dry-run` runs it. H2 is now **measurable**; it is
     not measured, and it still needs the case file (item 1).
  4. **PF-4b, PF-10 and PF-5 have no records.** `preflight-records/` holds PF-2, PF-4 and PF-21
     only. **Corrected 2026-09-16: only PF-10 needs a mailbox**, and this item said otherwise.
     Read from their own protocols (AD's PF table): **PF-4b** is the Node arm of PF-4's latency
     measurement - same pool, same laptop, same texts - and touches no mailbox; **PF-5** is (a)
     an anonymous model download recording licence and SHA-256, (b) the full suite cold-started
     with all egress except Gmail and OAuth blocked *and the model host blocked*, (c) the
     content pipeline with sockets disabled: a provisioning and network-isolation probe, no
     mailbox. **PF-10** is the freshness baseline and does need live mail - a seed account
     **and** a second unrelated sending account (`docs/IMPLEMENTATION_PLAN.md`), observing real
     delivered mail arrive.
  5. **The runner has not been independently reviewed.** Unchanged from §4(5).

*Nothing in the A14, A15 or A16 amendments changes (a), (b) or the five items above.*

---

## 2. Which remaining failures are already diagnosed

Every failure still visible in the real-model records has a cause on file. None needs a new
investigation to be understood; each needs a decision or an implementation.

| what fails | where it shows | cause on file |
|---|---|---|
| DIAG-REV-01, DIAG-REV-02 never deliver, on every arm and both modes | after the repair they walk 27 and 28 offers and stop at `no_new_affordances` | **R-M2-084**: the evidence thread is never among the offers. A retrieval failure no disclosure change reaches. The repair sharpened the symptom (it was `hop_budget` at 5 calls before, which masked it) without touching the cause |
| DIAG-EXP-01 and DIAG-EXP-02 deliver in named mode and not in listed mode | `--no-named-reads` | the evidence is reachable only by reading an id a collapsed run lists. That is the driver rule the two modes exist to report apart; it is a measurement boundary, not a product defect, and it is already reported apart |
| DIAG-RANK-01 and DIAG-RANK-04 decline their first search at the published width on every arm | 2 declines each, then a retry serves and the case delivers | **R-M2-076**: the first response's bookkeeping overflows on broad queries. Open. A15 changed the chain (one directed hop to the widest width that fits) and not the first response |
| the semantic arm costs more per case than the lexical arm for the same delivery | 24.8 against 23.0 calls listed, 23.7 against 21.5 named | **R-M2-103**, with **R-M2-101** as the mechanism behind the size of the layout |
| a correct semantic retrieval changes nothing | DIAG-RANK-03: 24 of 25 shortlisted messages in the evidence thread, top five cosines, still not mapped | **R-M2-102**, **closed as working-as-designed**: ADV-110 forbids ordering a comparison by a cosine the other candidates do not have, and the evidence thread was admitted by L1b. The consequence is a case-design requirement, §4(1) |
| the query-aware selector cannot be compared with Baseline F | the `fixed-window` arms are call-for-call identical to their twins | **R-M2-098**: the fill is the first thing every response on this corpus sacrifices, so DISC-02 is unmeasurable here. Needs a corpus with responses that carry fill rows, not a code change |
| a thread whose member ids alone exceed the host cap has no map that fits | declines terminally | **R-M2-091**, recorded as a declared limit of the inline surface (A14) |

---

## 3. The smallest next step

**Amended 2026-09-15, later the same day.** This section named one read-only investigation as
the next step: *does a pool probe's result set belong in `H` as hits?* That investigation is
done (`docs/reviews/R_M2_101_102_INVESTIGATION_2026-09-15.md`). It returned an answer to a
question that was the wrong shape, and it withdrew the fallback this section offered. What
follows replaces it.

**The question was malformed and is settled.** In this architecture `H` *is* the hit set, so
there is no "accounted member of `H` that is not a hit". And the ids must be in `H`: A.7a
(H-lex), `PRODUCT_CONTRACT` I-1, `RELEASE_RUBRIC` EV-01 and D.5 all say so, with an
anti-deflation rationale. No repair may remove them. What those four documents actually decide,
though, is the disposition of **step (b)**'s participant probes, and they decide it as
*accounting*: "disclosed if their thread is mapped, otherwise a `withheld` record". **The probe
doing the work on every traced case is step (c)**, the recency probe, which no clause anywhere
analyses - on all seven, the query names no participant, so step (b) sends nothing and one
`after:<epoch>` probe over the default 90-day window admits 334 to 462 ids against a shortlist
of 25.

> **Qualified 2026-09-16 — R-M2-110. The record above is preserved unchanged; this is what it
> now means.** Every figure in this project that counts what D.5 step (c)'s probe admitted was
> produced through `SyntheticMailbox`, whose `_date_value` matched `YYYY/MM/DD` only. The
> server writes that probe as `after:<epoch>` (A.6a rule 4), the double returned "cannot judge"
> for it, and "cannot judge" is implemented as **matching every message**. So the probe had no
> window in any run recorded here — **including the real-model runs**: the models decide which
> pool rows the shortlist selects and in what order, not whether the double filters by date.
> Real models did not make the synthetic date filtering correct.
>
> What survives: the **mechanism**. A pool probe's `messages.list` admits its whole result set
> to `H` at L5, and A.9 then spends the evidence tier and the E2 floor on it. That is a reading
> of the code and the contract and is unaffected.
>
> What does not survive: the **magnitude**. "334 to 462 ids" is a windowless probe's result set,
> not the probe the server sends to Gmail. Re-measured under the corrected double, the same
> mechanism leaves three demoted ids inside mapped threads on DIAG-SEM-03, not hundreds
> (`docs/reviews/A16_RECENCY_POOL_2026-09-15.md` §5.2, ledger R-M2-112). The size of this
> finding is unestablished until it is re-measured, and no work should be justified by the
> old number.

**What is genuinely open is a composition nobody argued, and it is an owner decision rather
than an investigation.** A.7a admits the probe ids for accounting; A.9(1) then spends the
evidence tier on "every hit" and A.9(2) owes each hit a non-negotiable reply-chain floor, and
the code implements that literally (`plan.py:375` and `:278`). So a message that fell inside a
90-day window is an evidence-tier row with a floor the ladder may never drop. D.5's own text has
already carved pool membership out of a neighbouring representation obligation - "the pool
creates no `source`, no mini-map and no stub rows" - on the same reasoning, and stopped there.

> **The decision: is A.9's evidence tier and E2 floor owed to every member of `H`, or to the
> members the query selected - the lexical matches and the shortlist's 25 - with pool-probe
> admissions carried as accounted context, disposed of exactly as D.5 already specifies and
> never disclosed as evidence?**

The narrowest version is confined to step (c), the clause nobody wrote and the probe doing the
work. It is an amendment, not a fix, because the literal text says "every hit". If taken it
changes no budget, model, corpus or cap, leaves the size of `H` and `certify` untouched, needs
no new bookkeeping (`HitOrigin` already records the clause, endpoint, rung and query per id),
and is the only identified change that reduces the semantic arm's first-response cost at its
source.
Two things would have to be settled with it: `_carries_nothing` reads "evidence survived"
against `hit_ids` and would need the narrowed set, and `hit_threads` ranks by admitting rung, so
a thread reached only by a pool probe needs a stated place in that order.

**The fallback this section offered is withdrawn.** It suggested that if the answer came back
"hits by contract", the next lever would be to let the score reach the mapping decision by
making `max_hit_threads` a prefix of the ranking. Under ADV-110 that is not available: a reused
cosine may order a comparison only where it exists for every candidate, and the lexical threads
`k` cut off have none. Making it available means scoring every hit-bearing thread rather than a
bounded pool, which is a scope change to D.5. R-M2-102 is closed as working-as-designed and its
consequence moved to §4(1).

**So the next step is a decision, and while it is pending the next implementation is the
acceptance runner** (§1(d)): it is on the critical path to every number M2 owes, it can be built
and reviewed while the case file is authored elsewhere, and it depends on neither open finding.

**Amended 2026-09-15, later the same day.** Both halves of that sentence are now overtaken.
The decision was taken - amendment **A16**, the owner's scoped separation of exhaustive
accounting from evidence protection for D.5 step (c) - and implemented, reviewed and regressed
(`docs/ARCHITECTURE_AMENDMENTS.md` A16; `tests/test_a16_recency_pool_evidence.py`; ledger
R-M2-101 update and R-M2-104 to R-M2-107). And the acceptance runner is not the next thing to
*build*, because it is built (§1 amendment). The smallest next step is now item 2 of that
amendment: **one `--live-check` run against a freshly seeded mailbox**, which is the only
capability on the critical path that is untested outside a double, and which needs the owner's
approval for the seed rather than any new code.

---

## 4. Which independent evaluations are still required to establish product value

Nothing measured so far speaks to product value. Every number in the repository is either a
mechanism check or known-target reachability. Five independent things are still owed, in
dependency order.

**(1) An independently authored F1-F17 case file, with one requirement now known.** By the
project's own loop rule the implementer may not write the exam; the export kit exists so this
can be handed out as a command rather than a document. The requirement, from R-M2-102: the
semantic rung may add threads no lexical rung reached and may not reorder the lexical ones
(ADV-110), so **a semantic benefit can appear only on a case whose evidence thread is reachable
by no lexical rung**. The current diagnostic set contains no such case - DIAG-RANK-03's evidence
thread was found by L1b, the embedding ranked it first, and the architecture correctly refused
to let that matter - so as things stand H2 and H3 would measure nothing about the rung even if
everything else were ready. This belongs in the authoring brief as a family, not as a hint.

### Amended 2026-09-15, later the same day: (1)'s framing was wrong for two of the three hypotheses

The owner's A16 authorisation said: *"H1 needs cases that exercise incremental semantic
retrieval. H2 needs an exercised reranking comparison. H3 needs an exercised query-aware versus
position-based disclosure comparison. L5-only evidence is not a blanket requirement for all
three. Independent authors should use natural questions, with mechanism eligibility verified
separately rather than questions tailored to this implementation."*

The requirement above was stated as though it applied to H1, H2 and H3 alike. It does not.
**L5-only evidence is not a blanket requirement.** It is the eligibility condition for *one*
mechanism - incremental semantic retrieval - and stating it as a general rule would have sent
an independent author looking for a single exotic case shape and produced a case file that
exercises none of the three comparisons properly. Each hypothesis has its own eligibility
condition, and each is about a comparison being *exercised*, not about the answer coming out a
particular way:

  * **H1 - semantic escalation recovers evidence lexical retrieval misses.** Needs cases that
    exercise **incremental semantic retrieval**: the semantic rung must be able to add a thread
    no lexical rung reached. This is where R-M2-102's condition belongs and only here. The
    diagnostic set contains no such case (DIAG-RANK-03's evidence thread was found by L1b, the
    embedding ranked it first, and ADV-110 correctly refused to let that matter).
  * **H2 - bounded reranking improves top-of-list precision.** Needs an **exercised reranking
    comparison**. Today there is none, for two independent reasons, and the first is
    infrastructure rather than case design: no arm isolates the cross-encoder (§1 amendment,
    item 3), and R-M2-093 measured that the cross-encoder "admits no ids, feeds neither
    `hit_ranks` nor the top-k, and moves no lexical thread". The evidence thread does **not**
    have to be L5-only for H2 - reranking is about order within what was retrieved - but the
    reranker's output has to reach a measured quantity, and a case has to present enough
    plausible candidates for an ordering to be wrong.
  * **H3 - query-aware disclosure beats position-based selection.** Needs an **exercised
    query-aware versus position-based comparison**. The arms exist (`fixed-window`,
    `sem-off+fixed-window`) and R-M2-098 measured them as wire-identical to their twins on this
    corpus: every layout is far over the cap, A.9a takes the fill's depth first, and zero
    `Band.FILL` rows survive on any served first response. So H3 needs cases whose responses
    *fit* well enough for the selector's choice to survive the ladder - shorter threads,
    narrower results - and the evidence thread need not be L5-only here either.

**How the brief should put this to an independent author.** Ask for **natural questions** a
person would actually send about the corpus, and verify mechanism eligibility **separately**,
against the case file that comes back, rather than asking the author to satisfy a mechanism
condition while writing. A question written to make a mechanism eligible is a question written
by the implementation, which is the failure the independent authorship rule exists to prevent.
The eligibility check is ours to run and to report - "of the seventeen families, *n* exercise
incremental semantic retrieval, *m* exercise a reranking comparison, *p* exercise the
disclosure comparison" - and a hypothesis whose comparison no case exercises is reported
**unmeasured**, which is a result, rather than measured on cases that cannot move it.

**(2) An independent content read of the corpus that passes.** The fifth stands at NO and
R-M2-067 through R-M2-073 are open. Until it passes, no retrieval claim is separable from the
corpus's own leakage, which qf-1 measures at 6/13.

**(3) H1, H2 and H3 measured against the v0.1 lexical arm**, with the pre-registered
claim-narrowing rule (EP §8.7) and Baseline E at both budget variants, and with the plan's own
consequence attached: a hypothesis that fails removes its machinery from the default path.

**(4) A discovery measurement, kept apart from reachability.** Every delivery number in this
repository comes from a driver that walks offers which *could* carry a required id, knowing the
id. Whether a model *chooses* the right offer is untested, and it is the thing a customer
experiences. R-M2-102 says that today the semantic score cannot influence that choice at all,
so this measurement is also the test of whether the rung has a reason to exist.

**(5) An independent review of the acceptance runner before its numbers are read**, on the same
footing as the reviews of the disclosure and navigation work. A measurement instrument that the
implementer both wrote and interpreted is the failure mode this project has already avoided
twice.

Live-mail validation sits across (3) and (4) and needs the owner's approval for the first
write. **Corrected 2026-09-16:** of the probes this sentence named, only **PF-10** and
**GMAIL-01** are live-mail work. **PF-4b** (the Node latency arm) and **PF-5** (model
provisioning, licence and SHA-256, and cold-start network isolation) touch no mailbox and need
no seeding or write approval; they are runnable now.

---

## Records this checkpoint rests on

`benchmarks/diagnostic-run-boundary-repair-{listed,named}-ba99c7a.{txt,json}` and
`benchmarks/trace-first-response-ba99c7a.json` (real models, `ba99c7a`);
`benchmarks/diagnostic-run-boundary-cont-{listed,named}-07b9f9c.{txt,json}` (before, unchanged);
`docs/reviews/INTEGRATION_REPAIR_2026-09-15.md` §8;
`docs/reviews/DIAG_SEMANTIC_REGRESSION_2026-09-15.md` and its addendum;
`docs/reviews/R_M2_101_102_INVESTIGATION_2026-09-15.md` (§3's investigation, and §4(1)'s
requirement); `docs/reviews/M2_DIAGNOSTIC_HANDOVER.md` "What this run cannot establish";
`docs/ORIVRA_V1_PLAN.md` §M2; `docs/reviews/FINDINGS_LEDGER.md` R-M2-065 to R-M2-103.
