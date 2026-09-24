# A16 — exhaustive accounting, separated from evidence protection, for D.5 step (c)

**2026-09-15, against `9a03eb4`.** One consolidated implementation and verification report,
as asked. Contract text: `docs/ARCHITECTURE_AMENDMENTS.md` §A16. Findings:
`docs/reviews/FINDINGS_LEDGER.md` R-M2-101 (update) and R-M2-104 to R-M2-111. Regressions:
`tests/test_a16_recency_pool_evidence.py`. Replants: R254 to R258. Measurement records:
`benchmarks/README-a16-paired-2026-09-15.md`.

**The headline, first, because it is the one that could be misread.** The amendment is
implemented, reviewed twice, regressed and gated. **The cost reduction it was authorised to
achieve is not established.** On the corrected instrument it measures, at the campaign level,
**five calls out of 341** in listed mode and **one out of 321** in named, with delivery,
declines and recoveries unchanged; and the half of the amendment that does the narrowing
measures **exactly zero** there. §5 says why and what it would take to establish.

---

## 1. What was built

The owner's decision, in one sentence: membership in `H` **solely** through an internal D.5
step-(c) recency probe is accounting, not evidence. The id keeps its place in `H`, its
`certify` disposition, its provenance and its omission accounting; it loses the A.9(1)
evidence tier, A.9a step 3's protected top-k, and the power to anchor an A.9(2) floor.

Three pieces of product code.

**(a) Provenance that can answer the question.** `HitOrigin` records where an id *entered*
`H` and a repeat sighting deliberately does not move it, so the origin cannot say "was this
ever matched by a lexical rung". `DispositionLedger` now records an `AdmissionRoute`
(`endpoint`, `rung`, `query`) on **every** observation, beside the origin and not instead of
it. `_admit` remains the sole writer, so all three intakes (`record_list_page`,
`record_history_additions`, `record_thread`) carry it; `H` is unchanged.

**(b) The predicate.** `assemble.pool_listed_only` demotes an id only when every one of its
`messages.list` routes is L5 **and** carries one of the step-(c) probe queries the pool's own
plan holds (`recency_probe_queries`, read off `plan.probes` by `PoolStep.RECENCY`), and it has
no `history.list` route. Shortlisted ids are exempt by construction.

**(c) One decision point.** `hit_threads` computes each planned thread's tier as
`(listings − demoted) | shortlist`, and every surface reads that one set.

## 2. The boundaries, and where each is held

| the owner's boundary | held by |
|---|---|
| a shortlisted message is eligible semantic evidence however it was listed | `pool_listed_only`'s exemption **and** `hit_threads`' union (§3, finding 1) |
| a lexical match keeps its protection even if the probe also returned it — **and even if the probe returned it first** | routes, not origins; `test_a_lexical_match_the_recency_probe_listed_first_keeps_its_evidence_route`; replant R255 |
| a direct user date query is not an internal recency probe | the probe set is the plan's, never the clause's shape; `test_a_callers_own_date_query_…`; replant R257 |
| D.5 step (b)'s participant probes are untouched | the `queries` restriction; `test_a_participant_probe_is_not_a_recency_probe_…` and a byte-identical end-to-end run compared on rows **and** on the finished layout; replant R257 |
| explicit reads are untouched | `surface/expansion.py` records under `EXPANSION_RUNG = RungId.L4` and imports nothing narrowed |
| existing evidence keeps its parent/child obligations even when those members are pool members | A16 removes a pool row's power to *anchor*; `test_the_floor_member_of_an_evidence_message_survives_being_a_pool_member` |
| a response of only unselected recency candidates must not claim query evidence survived | the ladder's own gate, `_carries_nothing`, over the narrowed set |
| ADV-110 intact; no reordering of partially scored lexical candidates; no scoring expansion | `_semantic_key`'s rung guard untouched; `rung_of` and the ranking computed from listings alone |
| models, budgets, corpus, caps, diagnostic limits unchanged | no edit to `constants.py`, the models list, the corpus or the runner |

### 2a. The boundaries claim, reconciled (added 2026-09-16)

The table above says "held". Three open findings qualify what that word covers, and the
qualification belongs beside the claim rather than three documents away.

  * **R-M2-106 — the roles.** "Matched/context roles" is in the owner's list of surfaces. It is
    half held: `is_hit` reads the narrowed tier, `pooled_only` still reads origins. So an id in
    the tier can be reported `role: context`. The boundary A16 *does* hold is the one its own
    regressions assert - a recency-only row is not `matched` - and the row above should be read
    as that, not as "the role rule was narrowed".
  * **R-M2-108 — membership.** `hit_threads` decides which ids are candidates for the tier from
    the **first-admission origin**, not from routes. The owner's instruction "do not assume a
    first-admission origin describes every later qualification" is satisfied for the demotion
    predicate and **not** for the grouping above it: an id a thread read admitted and a lexical
    rung later listed is not a hit at all. That is pre-existing and out of this amendment's
    scope, and it means "a lexical match keeps its protection even if the probe returned it
    first" holds for probe-*listed*-first and not for probe-*read*-first.
  * **R-M2-109 / R-M2-113 — the stand-down.** A16 is gated on a shortlist existing. When the
    pool ran its probes and produced none, the step-(c) admissions keep the tier in full. That
    path also cannot emit a response at all (R-M2-113, below), so the boundary is not merely
    unheld there - the response is refused. Neither is caused by A16.

None of the three is a regression introduced here, and none is hidden by the table: each has a
ledger row, and R-M2-113 has a reproduction. What the table means, exactly, is: **every
boundary the owner drew is held on the path A16 changes, and three pre-existing limits bound
that path.**

**Applied to the surfaces named, and *not* to two of them — stated rather than claimed.**
Planning, A.9a step 3's `_top_k_hit_ids`, A.9(2)'s `floor_pairs` anchors, `_carries_nothing`
and the recovery width all read the narrowed tier. **Source eligibility does not**: A.9(5) is
decided by `_split_off_unselected_pool_threads` on the admitting rung and the shortlist, and
it already refused to make a pool thread a source before this amendment. **The
matched/context roles half do**: `is_hit` reads the tier, `pooled_only` reads origins, so a
row's role and its tier can disagree. Rewriting `pooled_only` on routes was tried in the first
pass and is a widening — a step-(b) participant row whose Gmail `q` is `from:…` becomes
`matched` — so it was reverted and the asymmetry is recorded (R-M2-106).

## 3. Two independent reviews, and what they changed

Neither reviewer wrote the code. Each was given the contract, the diff and a rubric, and told
to treat the amendment's own documentation as a claim to falsify.

**First review — nine findings.** Three HIGH/MEDIUM ones changed the implementation before it
was regressed: the routes were inert at the call site; the `pooled_only` rewrite was a
widening (reverted); LR arrivals were being demoted (`history.list` now qualifies). It also
found the regressions vacuous — **16 of 19 passed with the amendment removed** — because a
bag-of-words fixture had shortlisted the very ids the assertions called recency-only. That was
repaired by pinning selection to a marker word with `k` tied to the marked count.

**Second review — eleven findings, two HIGH.** Both HIGH ones are repaired:

  * **Finding 1 (R-M2-111).** A16 could empty the tier of a source holding the shortlist's own
    choice. `hit_threads` builds hits from `messages.list`; the pool embeds **every row of a
    thread it reads**, so the shortlist routinely selects a message the probe never listed.
    Subtraction alone left `hit_ids` empty while `_split_off_unselected_pool_threads` kept the
    thread — because the shortlist *had* selected in it. `_may_leave_without_emptying_the_answer`
    then returns `True` and `_carries_nothing` takes its "there was never any evidence" branch:
    a decline became an empty served response, and a nine-row response became six sources with
    no rows. Repaired by the union; the reviewer's 28-cell sweep re-run after the repair shows
    **0 divergent cells**.
  * **Finding 2 (R-M2-110).** The synthetic mailbox double could not evaluate `after:<epoch>`,
    the form the server itself writes, and "cannot judge" is implemented as *matches every
    message*. **No test in this repository had ever observed the recency window excluding
    anything.** The double now evaluates epoch seconds, as Gmail does. This is why the first
    A16 regression suite could not have found finding 1, and it materially changes what §5
    measures.

Repaired without changing behaviour: the documentation's claim that source eligibility reads
the narrowed set (it does not, §2); the roles claim; the `_routes` "including repeats" wording;
the control's list of surfaces; two tests that could not fail (the caller's-date-query boundary
and the participant-probe end-to-end comparison), and a missing replant for the step-(c)
restriction. Recorded and **not** repaired, with the reason in each row: R-M2-108
(`hit_threads` still decides *membership* on the first-admission origin — fixing it changes
what a lexical hit is for every request), R-M2-109 (A16 stands down when the probes ran and no
shortlist exists, on a path that cannot emit a response at HEAD for an unrelated reason),
R-M2-104, R-M2-105, R-M2-106.

The second review's scope finding about the checkpoint edits was a **false positive caused by
an incomplete brief** — the authorisation's inventory-and-framing paragraphs were not quoted to
it. The sentence it objected to has been replaced with the authorisation's own words.

## 4. Gates

| gate | result |
|---|---|
| full offline suite | **4,149 passed, 0 failed**, 103 files (`tests/test_new_operator_round19.py` collects only replant-marked tests and exits 5; pre-existing) |
| A16 regressions | 24, all passing |
| **non-vacuity** | with the amendment neutralised at the product in every way it is expressed — `not_evidence`, `selected`, and the step-(c) `queries` restriction — **11 of 24 fail**. The 13 that pass are the deliberate controls and the guards on the half the amendment must not touch, each labelled as such in its own docstring |
| replants | R254–R258 **CAUGHT**, every citation; no duplicate replant names or numbers |
| `ruff check` | clean on every file this change touches; repo-wide count unchanged from HEAD |
| `mypy` (strict) | **73 errors in 21 files — identical to HEAD**; zero from this change; production source clean |

The repo's own `make lint` / `make types` / `make format-check` are **red at HEAD** and were
before this change (163 ruff errors, 110 of them in `harness/` including 38 `B023`
loop-variable-late-binding; 73 mypy errors, all in tests; 25 files unformatted). Recorded as
R-M2-107, not repaired here, with a note that the harness's `B023` set should be triaged before
the next measurement campaign.

## 5. Paired measurement — and what it does not establish

All **[word]**: the deterministic stand-in, no models, no mailbox, one corpus at one seed,
budgets and caps unchanged. Records and provenance:
`benchmarks/README-a16-paired-2026-09-15.md`. Four trees, differing in exactly two things: the
product (A16 or not) and the test double (corrected or not).

### 5.1 Campaign — the fifteen diagnostic case/arm rows, both driver modes

| | `full` listed | `full` named | `sem-off` (both) |
|---|---|---|---|
| no A16 | 9/15 delivered, **341** calls, 10 declines | 11/15, **321** calls, 10 declines | 9/15 · 301 · 4 — and 11/15 · 281 · 4 |
| **A16** | 9/15 delivered, **336** calls, 10 declines | 11/15, **320** calls, 10 declines | identical |

**No case gained, no case lost, on any arm, in either mode.** Declines and recoveries
unchanged. The semantic arm's call surcharge over `sem-off` falls from 40 to 35 in listed mode
and from 40 to 39 in named: **1.5% and 0.3% of the arm's own cost.**

### 5.2 First response — the seven traced cases, `full` arm

| tree | layout `hit_ids` | evidence rows delivered | final rendered chars | declines |
|---|---|---|---|---|
| old double, no A16 | 660 | 155 | 156,537 | 1 |
| old double, **A16** | **530** | 79 | 156,471 | 1 |
| corrected double, no A16 | 406 | 27 | 164,851 | 2 |
| corrected double, **A16, subtraction only** | **406** | **27** | **164,851** | 2 |
| corrected double, **A16** | **530** | 58 | 156,841 | 2 |

Three things follow, and the third is the one that matters.

**(i) A16 is invariant to the instrument.** 530 tier members either way. What moved is the
baseline it is read against.

**(ii) On the instrument R-M2-101 was diagnosed on, A16 does exactly what it was authorised to
do**: the tier falls 660 → 530 (−20%) and the delivered evidence rows 155 → 79, with no change
in declines. Those are R-M2-101's own numbers moving — RANK-03 72 → 44, REV-03 125 → 68,
SEM-01 114 → 71, SEM-03 74 → 45.

**(iii) On the corrected instrument the narrowing measures exactly zero.** "Subtraction only"
is identical to "no A16" on every case, every quantity. The predicate is not inert — on
DIAG-SEM-03 it demotes **100 ids of an `H` of 479** — but those ids are almost entirely in
threads A.9(5) already withholds, so removing them from a tier changes no response. Once the
double stops matching the whole mailbox with the probe's own clause, the recency-only ids
inside *mapped* threads are three, not hundreds.

So the entire measured difference on the corrected instrument is the **union** half — the
shortlist's selections becoming evidence (R-M2-111's repair). Its effect is more evidence
delivered (27 → 58 rows) in a smaller response (164,851 → 156,841 chars, −4.9%), at an
unchanged decline count. That is a correctness gain, and it is the opposite sign to a cost
reduction on the tier.

### 5.3 What is therefore claimed, and what is not

**Claimed.** A16 is implemented as authorised and holds every boundary in §2. It changes no
delivery outcome on the diagnostic set. It removes a live overclaim (R-M2-111) and repairs a
measuring instrument that had never been correct (R-M2-110).

**Not claimed, explicitly.** That A16 reduces the semantic arm's cost. Five calls in 341 is
not a cost reduction and is not offered as one. Nor is the −4.9% rendered size, which the
union — not the narrowing — accounts for. R-M2-103 stands unchanged: the semantic rung still
costs more per case than backend-off for the same delivery, and nothing measured here narrows
that.

**Not measured.** Real models. The stand-in decides everything except which 25 pool rows the
shortlist selects and their order — and §5.2(iii) shows the result now turns on precisely
which rows those are, so the stand-in is a weaker proxy for this amendment than it was for A15.
A real-model re-measure is the next measurement, and it needs the Mac:

```
cd ~/Desktop/Nayan/MailWeave
PYTHONPATH=server/src:harness/src:orivra/src:tests/fixtures:. \
  .venv/bin/python benchmarks/trace-first-response-4311.py \
    --models-root ~/.local/share/mailweave/models --device cpu --tag a16-real
PYTHONPATH=server/src:harness/src:orivra/src:. \
  .venv/bin/python benchmarks/run-diagnostic-4311.py \
    --models-root ~/.local/share/mailweave/models --device cpu \
    --out benchmarks/diagnostic-run-boundary-a16-named-<rev>.txt \
    --json benchmarks/diagnostic-run-boundary-a16-named-<rev>.json
# and again with --no-named-reads for the listed mode
```

The pre-A16 real-model records to read it against already exist and are unchanged:
`benchmarks/diagnostic-run-boundary-repair-{listed,named}-ba99c7a.{txt,json}` and
`benchmarks/trace-first-response-ba99c7a.json`. **Those records were produced with the
uncorrected double's behaviour nowhere in them** — they are real Gmail-shaped runs against the
synthetic corpus through `SyntheticMailbox`, so R-M2-110 applies to them too, and the honest
comparison is A16 against a re-run of the same commit with the corrected double, not against
the stored records alone.

## 6. Not done, by instruction

M3 is not begun. No mailbox write, no reseed, no duplication of the evaluation runner, no
history rewrite, no remote, no credential or permission change, no edit to `marketing/`. The
Mac `.venv` was not touched: every command in this work ran on `$HOME/ovenv` in the isolated
environment, and no `uv` or `make` target was invoked.

---

# 11. The real-model paired measurement (2026-09-16) — result

Run by the owner on the laptop, `benchmarks/paired-a16-runner.py`, base ref `9a03eb4` against
the A16 working tree. Records preserved at **`benchmarks/a16-models.VyHeie/`** (manifest, six
records, six logs, the report). Backend on both sides, from the records rather than the flags:
`minishlab/potion-retrieval-32M+BAAI/bge-reranker-base`, revisions `6fc8051fab2a+2cfc18c9415c`,
CPU, torch 2.14.0 / sentence-transformers 5.7.0 / transformers 5.17.0 — **identical**, which
the runner refuses to proceed without. Corpus generator 3, seed 4311, profile `sample`, case
file sha256 `869ed634…`, 13 answerable + 2 controls. Both sides carry the identical shared
instrumentation: the manifest records the corrected simulator replacing `222e2fad…` on `pre`
and already `same` on `post`.

## 11.1 The result, plainly

**Required-evidence delivery is unchanged: 9/13 listed and 11/13 named.** Per case, not only in
total — there are **no identity swaps**: every case that delivered before delivers after, and
every case that did not, still does not.

**Calls increase by one in each mode**, on the `full` arm: 338 → 339 listed, 318 → 319 named.
The whole of it is one case, **DIAG-RANK-02, 24 → 25 in both modes**. Every other case is
identical in calls and in declines.

**Declines are unchanged**: 9 on `full` in both modes, and unchanged per case. Recoverable
unchanged at 5. Controls unchanged: 0 answered on either side in every retrieval arm.

`sem-off` is identical across the pair on every quantity — 9/13 and 11/13, 299 and 279 calls,
4 declines. That is the pairing's own control, and it holds.

First response, `full` arm: the evidence tier rises on five of the seven traced cases
(EXP-03 109 → 129, RANK-02 15 → 40, REV-03 49 → 72, SEM-01 59 → 65, SEM-03 23 → 44), is
unchanged on RANK-03, and rises by one on EXP-02. Tier members *present* move on two
(SEM-03 8 → 24, EXP-03 3 → 4). Rendered size is unchanged on five and rises slightly on two
(EXP-03 +22 chars, RANK-02 +68). **Content rows are 0 on thirteen of the fourteen traced
case/arms on both sides** — every present message is a collapsed-run member — so "tier present"
and "rows delivered" are not the same quantity anywhere on this set.

## 11.2 What is not claimed

**No cost reduction.** Cost did not fall; it rose by one call in each mode. The reduction A16
was authorised to achieve is not established, and this run does not establish it.

**No semantic advantage.** `full` and `sem-off` deliver the same 9/13 and 11/13 as each other,
before and after, and `full` costs 40 more calls in each mode than `sem-off` does. Nothing here
supports a claim that the semantic rung earns its cost. R-M2-103 stands.

**No separate causal effects.** This is a **combined** comparison: `post` carries the
protection-narrowing and the shortlist-union together, and the pair cannot attribute any part
of the difference to either. The tier rising on five cases is consistent with more than one
mechanism and is not evidence for one of them. Nothing in §11 is decomposed, and the stand-in's
decomposition is a stand-in result that is not carried over here.

**No M2 acceptance.** This is a 13-case diagnostic set whose own metadata says
`sufficient_for_m2_acceptance: false`, run under known-target reachability. It measures whether
this change moved anything. It does not measure the product.

## 11.3 Retain or revert, component by component

Contract correctness and measured benefit are separate questions and are answered separately.
**The measured column is the same for both components** and says nothing about either
individually: the run compared `pre` against `post`, `post` carries both, and no part of the
difference is attributable. That is not a gap to be filled by reasoning; it is what a combined
comparison can support.

### Protection-narrowing (the authorised change)

**Contract correctness: sound, and independent of the measurement.** A.9(1) spends the evidence
tier on "every hit"; A.7a admits a step-(c) probe's whole result set to `H`; D.5 never analysed
step (c) at all, and A.9(5) already carves pool membership out of a neighbouring obligation on
the same reasoning. Without the narrowing, a message qualifies as evidence - anchoring an E2
floor and competing for the protected top-k - because it fell inside a ninety-day window. That
is an overclaim on its face, and the amendment removes it.

**Measured benefit: none established.** Delivery unchanged, declines unchanged, one call more
per mode across `pre`/`post` combined. The cost reduction this was authorised to achieve is
withdrawn as a justification.

**Recommendation: retain, on the contract argument alone, with the cost claim struck.** Reverting
restores a contract defect and buys nothing measured, because the measurement shows no cost to
recover. **The owner's call to make, and here is the case against:** the V1 plan's rule is that
machinery which fails its hypothesis leaves the default path. If A16 is read as a cost
hypothesis, it failed and that rule fires. It is not being read that way here - it was
authorised as a contract amendment and the cost was an expectation attached to it, not its
premise - but that reading is available and this recommendation does not foreclose it.

### Shortlist-union (the defect repair)

**Contract correctness: it fixes a demonstrated wrong-answer path.** A source holding the
message the shortlist selected, with an empty `hit_ids`, turns `_carries_nothing` to its "there
was never any evidence" branch and lets A.9a step 7 drop the source carrying the answer. That
was reproduced end to end by the second independent review, and a 28-cell sweep moved in 9 cells
including a decline becoming an empty served response. The repair is that the evidence tier is
what the query selected, shortlist included.

**Measured benefit: not attributable, and not expected to be large here.** The shape it repairs
needs a thread the pool *read* but the probe did not *list*; how often the diagnostic set
presents that shape is not known and this run cannot say.

**Recommendation: retain.** Reverting reinstates a reproduced path that drops the answer. But it
should be **re-filed as its own amendment**: it was not part of the owner's authorisation, it
travelled inside A16 only because A16 exposed it, and leaving it inside an amendment about the
recency pool makes it invisible to anyone reading either one later.

### Not decided here

Whether the semantic rung earns its cost. `full` and `sem-off` deliver the same 9/13 and 11/13
at 40 more calls per mode, before and after. That is R-M2-103's question, it is unchanged by
this run, and it is not A16's to answer.
