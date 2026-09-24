# Diagnosis: why the backend-on arms deliver 4/13 and 5/13 where backend-off delivers 9/13 and 11/13 (2026-09-15)

Records: `benchmarks/diagnostic-run-boundary-cont-listed-07b9f9c.{txt,json}` and
`…-cont-named-07b9f9c.{txt,json}` (real backend `minishlab/potion-retrieval-32M` +
`BAAI/bge-reranker-base`, CPU, commit 07b9f9c). Both preserved, untouched; nothing in this
diagnosis rewrote or re-ran them. No mailbox was contacted and no campaign was re-run.

Scope, as asked: the earliest consequential divergence per lost case; embedding retrieval kept
apart from reranking; why the fixed-window and query-aware arms are identical; one causal
diagnosis with code references and a repair proposal. Nothing was implemented. No model is
replaced, no threshold tuned, no budget enlarged, no corpus changed, semantic retrieval is not
switched off as a remedy, and M3 is not begun.

## 0. Method

**Existing records first.** The JSON records carry, per case and arm, the call shapes and
outcomes (`trace[]`), `calls`, `declines`, `stopped`, and first/after evidence counts. They do
not carry decline texts, retrieval reports, layouts or offer lists (the runs were made without
`--traces`), so the records establish *where* the arms diverge and the shape of the chain, and
not what the first response was made of.

**One model-free local diagnostic, then.** `benchmarks/run-diagnostic-4311.py`'s own
`substrate()` was driven with the harness's deterministic bag-of-words stand-in
(`tests/fixtures/eval_dummy._WordBackend`) in place of the model, on the same corpus (generator
3, seed 4311, 1,725 messages / 76 threads), the same 13 answerable cases and the same four arms,
through `server.call`, first search only, with spies on `disclosure.plan.run_ladder` and each
A.9a step. Scripts: `benchmarks/_patches/first-response-anatomy.py` (per arm: pool, H, hit
spread, decline text, offer list), `chain-anatomy.py` (the narrowing chain, each decline's
text), `step-anatomy.py` and `decisive-table.py` (the layout after every ladder step),
`rev03-render.py` (estimate against render), `selector-diff.py` (fill planned vs fill on the
wire; wire diff between selectors). Output kept at
`benchmarks/first-response-anatomy-wordbackend.json`. Everything below that carries a number
from these runs is labelled **[word]**; everything from the real-model records is labelled
**[real]**.

**Why the stand-in is admissible evidence here.** The semantic rung's *structure* - the pool it
reads, the ids it admits into `H`, the number of shortlist hits, how they are dispositioned and
what the ladder then does - is decided before any score is read: `semantic.pool.plan_pool`
(`server/src/mailweave/semantic/pool.py:135`) is pure in the parse, the ladder's touched
threads and the profile; the shortlist is *top-k by cosine with k = MAX_RERANK_PAIRS = 25*
(`semantic/shortlist.py`, module docstring), a fixed size whatever the scores are. The stand-in
therefore reproduces everything except *which* 25 messages are chosen and their order. The
test of admissibility is agreement with the real records on what the records do state - and it
agrees: the same 10 of 13 first searches decline (EXP-01, SEM-01, SEM-02 served; the rest
declined) in both, and the chain's terminal `thread_map` target is the same thread on all seven
cases where the real chain reached one (EXP-02 → t-t0004, EXP-03 → t-t0002, RANK-03 → t-t0004,
REV-01 → t-t0001, REV-02 → t-t0000, REV-03 → t-t0000, SEM-03 → t-t0004), and RANK-02 serves at
`max_hit_threads: 1` after three declines in both. Where the two could differ - which threads
the 25 hits fall in - is named as the one model-dependent residual in §4 and §8.

## 1. The paired outcome, restated from the records [real]

Both modes, `full` against `sem-off` (the `fixed-window` arms are call-for-call identical to
their semantic-state twins; §5):

| | full (listed / named) | sem-off (listed / named) |
|---|---|---|
| delivered | 4/13 / 5/13 | 9/13 / 11/13 |
| first search served | **3/13** (EXP-01, SEM-01, SEM-02) | **9/13** |
| declines per run | 32 | 9 |
| calls (mean) | 13.9 / 13.8 | 21.3 / 19.8 |
| evidence in the first response | 0/13 | 0/13 |

The last row matters: **no arm's first response ever carries the evidence content**. Every
delivery on every arm came from the driver's walk over what the first served response offered.
So the regression is not "the semantic arm retrieved the wrong candidates and the lexical arm the
right ones"; it is that the semantic arm's first response is *refused* where the lexical arm's is
*served*, and a refused response offers one call (its `retry_with`) where a served one offers
twenty to forty.

Cases backend-off delivers and backend-on loses: **EXP-03, RANK-02, RANK-03, REV-03, SEM-01**
(both modes) and **EXP-02** (named-read mode only). The declined-chain signature on `full` is
`calls=5, declines=4, stopped=hop_budget`: the search declines, three `max_hit_threads`
narrowings (12→6→3→1) decline, the fourth retry is `thread_map(top thread)`, and the driver's
depth (`MAX_RECOVERY_ROUNDS = 4`, `harness/src/mailweave_harness/evaluation/arms.py:72`) is
spent. RANK-02 differs (24 calls: the chain serves at width 1, then one round of walking);
REV-03 differs (3 calls: two declines and `no_new_affordances`); SEM-01 differs (33 calls: served,
walked to the call budget without reaching the evidence).

## 2. Earliest consequential divergence, per lost case

Read each row as: what `sem-off` did, what `full` did, and the first point at which the
difference decided the outcome. Numbers are [word] unless marked [real]; the *structure* of each
row is corroborated by the [real] trace shape.

**DIAG-EXP-03** (evidence thread t-t0046).
*Candidates:* identical lexical retrieval (the `LadderRunner` runs before and independently of
the registry, `surface/service.py:317-329`); `full` adds an L5 pool of 300 messages, H 533 →
561 ids, 21 → 23 threads. *Evidence before/after ranking:* in H on both arms as an unmapped
thread; never a hit; never a row. *Mapped thread order:* rank-0 source t-t0002 on both.
*Disclosure size:* after A.9a step 5 the rank-0 source is 2,032 chars on `sem-off` (0 rows,
one run of 8; its 3 hits are all beyond top-k and collapse) and **8,197 on `full`** (8 hits,
3 of them inside the protected top-k at snippet depth, all 8 floor members - the shortlist made
every message of the thread a hit); fixed bookkeeping with every source split off 19,673 vs
**22,730** (pre-ladder thread-granular groups 9 vs 18: the pool's unselected threads).
*Cap/refusal:* `sem-off` keeps t-t0002 at 21,705 ≤ 25,000 and serves, hits present as run
members; `full` cannot keep it (22,730 + 8,197 = 30,927), step 7's last resort splits the only
evidence-bearing source, `_carries_nothing` fires: "121 retrieved, 0 present, 12 split off".
At `max_hit_threads: 1` the same: one source of 5 protected snippet rows (9,803) beside 22
named groups (11,396) = 26,330 > cap → split → empty → decline. *Recovery:* three narrowings
that never touch the cause, then `thread_map(t-t0002)` ≠ t-t0046, depth spent. `sem-off`'s walk
reached the evidence's group at offer 29 of 31, call 23. **Divergence: the first-response
decline.**

**DIAG-RANK-03** (t-t0048). Same mechanism, larger: rank-0 t-t0004 has 4 hits / 3,494 chars
on `sem-off` and **57 hits / 5 protected / 14,491 chars** on `full`; fixed bookkeeping 18,684
vs 22,585 (groups 7 → 18). Chain 5→2→1, then `thread_map(t-t0004)` ≠ t-t0048 [real and word].
`sem-off` served at hop 0, evidence at offer 25 of 29, delivered at call 25/23.

**DIAG-RANK-02** (t-t0036). Rank-0 source changes (t-t0009 → t-t0003; `hit_threads` orders
lexical threads by rung, `prefer`, then **thread id**, `retrieval/assemble.py:499-506`, and the
added hits changed which threads carry any); rank-0 grows 6,444 → 8,444 (protected 1 → 4);
fixed bookkeeping **16,249 → 22,744** (groups 4 → 15). Here the pool groups are the larger
term. `full` declines through 12→6→3, serves at width 1 (22,821 chars, 0 not-included, the
evidence's group 13th of 24) with one driver round left; `sem-off` served at hop 0 with the
evidence's thread 2nd in `not_included_sources` and delivered at call 18. **Divergence: the
first-response decline, then the chain consuming three of four rounds.**

**DIAG-REV-03** (t-t0013). A different refusal class. The ladder's estimate says 24,531 and
fits; the rendered response is **32,259** and `partition.declared_result` refuses it
(`surface/partition.py:82-111`, `HostCapExceeded`). Cause: the estimate assumed 24 named
withheld groups and a folded tail (`disclosure/layout.py:522 named_groups`), the wire named
**50** - 45 under `max_pool_messages` and 5 under the token ceiling - and no tail, because
only `max_hit_threads` has a tail recovery filed (`retrieval/assemble.py:3166`) and the ledger
folds nothing else (`envelope/disposition.py:1822-1823`), while the estimate counts the pool's
groups as foldable (`assemble.py:3004`, `foldable_grouped_threads = len(overflow) +
len(pool_granular)`). Retry `max_hit_threads: 6` declines, `no_new_affordances` at call 3
[real]. `sem-off`: 46 → 38 groups, served at 19,315, evidence at offer 23 of 35, delivered at
31/30. **Divergence: an estimate that under-charges the semantic arm's bookkeeping by ~7.7k.**

**DIAG-SEM-01** (t-t0011). Both first searches serve (22,4xx chars; rank-0 t-t0000 identical).
`full` offers 41 calls, `sem-off` 35; the six extra are the pool's unselected threads as
groups. Withheld groups are written **sorted by thread id** (`disposition.py:1797`) and the
driver walks groups before `not_included_sources` and both before anything ranked
(`boundary.py:171-178`), so the evidence's offer index is its thread id's alphabetical position
(10th on `sem-off`, 9th [word] on `full`), each `thread_map` of a long thread costing one to
three page calls. `sem-off` reached it at call 28 of 33; `full` reached the call budget [real].
Under the real model the six inserted groups sit wherever the real shortlist's unselected
threads sort. **Divergence: offer count and a walk order that is not a rank.**

**DIAG-EXP-02** (t-t0009; lost in named-read mode). Both arms decline the first search - this
is R-M2-076's own shape, 132 retrieved, 12 split off, 750/794 withheld. At `max_hit_threads:
6` `sem-off` fits (19,474 rendered, the evidence's thread first in `not_included_sources`) and
delivers at call 25; `full` does not (groups 9 → 21, +2.2k of fixed bookkeeping) and declines
through 3 and 1 to `thread_map(t-t0004)` ≠ t-t0009. **Divergence: the pool's groups alone.**

REV-01 and REV-02 are lost on both arms (R-M2-084, retrieval) and are not re-diagnosed here;
`full` additionally turns REV-01's served first response into a decline by the EXP-03
mechanism (groups 30 → 39, rank-0 hits 3 → 15).

## 3. The causal diagnosis

**The semantic rung adds structure to the first response that the A.9a ladder cannot shed
inside the host cap, and the recovery chain then narrows a dimension that does not contain
that structure.** One cause, three limbs, each with the code that produces it.

**(i) Hit concentration in the top-ranked source.** D.5 step (a) seeds the pool with the threads
L0-L3 already touched (`semantic/pool.py:163-165`, `seed_threads`), so most of the 25
shortlisted messages land in threads that are already hit-bearing. A shortlisted message is a
hit (`ReasonKind.SEMANTIC_SCORE`), every hit is an E2 floor member, and the ladder protects the
top `DISCLOSURE_TOP_K_HITS = 5` hits at depth (`disclosure/ladder.py:403-417`,
`_top_k_hit_ids`, step 3) - chosen by `hit_ranks` (`disclosure/plan.py:219`), which ranks hits
by the E4 predicates and position and **not** by any semantic score. A protected row is not
stub depth, so `_collapsible` (`ladder.py:312-335`) never folds it into a run; a floor member
is never taken by step 8. The rank-0 source's floor therefore stops shrinking at ~8-15k
characters, where on the lexical arm the same thread collapses to a 2k run (its few hits being
beyond top-k). Step 7's main loop cannot take a source holding floor members
(`ladder.py:503-533`); its last resort `_split_a_source_whose_floor_does_not_fit`
(`ladder.py:589-623`) can and does take the last one; `_carries_nothing` (`ladder.py:1025`)
then refuses the emptied response. EXP-03, RANK-03, SEM-03, and REV-01's decline are this limb;
RANK-02 partly.

**(ii) The pool's bookkeeping is always named and is charged as if it folded.** Every pool
thread the shortlist passed over, and every pool candidate the pool cap never read, becomes one
thread-granular `withheld_groups[]` entry (`assemble.py:2382-2410`, `_split_off_unselected_pool
_threads`; `assemble.py:2932-2936`, `pool_granular`), ~490 characters each
(`envelope/measure.py:405`). Two consequences. (a) A fixed cost before any ladder step runs:
+9 to +12 groups on the lost cases, 2-6k of the 25k cap, which is exactly the margin the
lexical arm served inside (EXP-02 at width 6, RANK-02). (b) An estimate that is not a bound:
the layout counts these groups as foldable (`assemble.py:3004`) but the ledger folds only caps
with a tail recovery, and only `max_hit_threads` has one (`assemble.py:3166`;
`disposition.py:1815-1836`), so past 24 groups the wire names all of them and the estimate
names 24. On REV-03 that is 45 pool groups named against 24 assumed: 32,259 rendered against
24,531 estimated, refused by the host-cap backstop rather than by the ladder. This is the shape
R-MCP-033 recorded (round 29) - "a sixty-thread recency window produced forty-two thousand
characters of disposition records" - returning through the groups the fix introduced. The
round-27 estimate certification (`tests/test_round27.py`, `ESTIMATE_SHAPES`) runs every shape
without a backend, so the semantic arm's bookkeeping has never been inside the matrix.

**(iii) The recovery chain narrows the wrong dimension and spends the depth budget doing it.**
`recovery.narrower_call` (`surface/recovery.py:117-168`) halves `max_hit_threads` on every
search decline whose effective width exceeds 1, whether the ladder refused for *size* or for
*emptiness*; `DisclosureLadderExhausted` (`ladder.py:104-124`) carries no field that says which,
although `_exhausted_by_emptiness`'s own docstring (`ladder.py:1063-1071`) says the retry beside
it "must change dimension rather than narrow further" (R-MCP-033 requirement 5). Narrowing
`max_hit_threads` removes hit-bearing sources - it does not shrink the rank-0 source's protected
floor (limb i) and does not remove a single pool group (limb ii) - so the chain declines at
6, 3 and 1 for the same reason it declined at 12 (EXP-03's four decline texts differ only in
the counts the narrowing removed: 12 / 6 / 3 / 1 sources split off, 561 / 466 / 466 / 466
withheld, 0 present each time), and the fourth and last round of the driver is spent on
`thread_map(top thread)`. The top thread is the first lexical hit thread under the ranking key
(rung, `prefer`, then thread id - `assemble.py:499-506`), not the evidence's, in every lost
case. On the lexical arm the first
response is served at hop 0 and all four rounds go to the walk.

A fourth, weaker limb reaches the one served-and-lost case: **the walk's offer order is not a
rank** - groups sorted by thread id, then split-off sources in reverse rank
(`disposition.py:1797`; `boundary.py:171-178`; `ladder._split_off` appends victims max-rank
first). Adding six pool groups moves the evidence's offer and adds page calls before it (SEM-01).
This is retrieval-order for *reachability*; it is not R-M2-084's "never offered".

The quantified picture, after step 5 of the ladder, first search, `sem-off` → `full` [word]:

| case | pre-ladder groups | rank-0 source: hits / protected / chars | fixed cost, no sources | verdict |
|---|---|---|---|---|
| EXP-03 | 9 → 18 | 3/0/2,032 → 8/3/8,197 | 19,673 → 22,730 | served → declined |
| RANK-03 | 7 → 18 | 4/0/3,494 → 57/5/14,491 | 18,684 → 22,585 | served → declined |
| RANK-02 | 4 → 15 | 2/1/6,444 → 8/4/8,444 (different thread) | 16,249 → 22,744 | served → declined |
| EXP-02 | 9 → 21 | 94/1/6,511 (same) | 20,405 → 22,654 | declined → declined; at width 6: served → declined |
| REV-03 | 38 → 46 | 2/1/4,247 → 13/0/2,117 | 22,291 → 22,414 | served → refused on render (32,259) |
| SEM-01 | 18 → 26 | 13/0/2,117 (same) | 22,430 → 22,467 | served → served; 35 → 41 offers |
| SEM-03 | 0 → 7 | 5/2/8,338 → 56/5/14,703 | 9,035 → 15,175 | served → declined (recovered at width 1: top = evidence) |

## 4. Embedding retrieval and reranking, separated

The two stages and what each can change:

* **Pool construction** (before any embedding): `plan_pool` names the threads; `SemanticRunner`
  reads them with `threads.get(format=metadata)`; every id enters `H`. Model-independent. It is
  the whole of limb (ii) and the precondition for limb (i).
* **Stage A, embedding shortlist**: top-25 by cosine over the pool (`semantic/shortlist.py`).
  The *size* of the hit set it adds is fixed at 25 by rule; the *membership* is the model's.
  Limb (i) needs the 25 to land in already-hit-bearing top threads, which the pool's seeding
  makes likely under any scorer - the pool is mostly those threads - and which the [real]
  records corroborate on every declined-chain case: a decline at `max_hit_threads: 1` is only
  possible when the single top source's protected floor plus the fixed bookkeeping exceeds the
  cap, i.e. when the shortlist has put several of the top-5 hits into that thread.
* **Stage B, the cross-encoder (L6)**: reorders the 25. It admits no ids
  (`hit_count_per_rung` shows L6: 0 on every served response, both backends); it does not feed
  `hit_ranks` or the top-k protection (`plan.py:219-259`, E4 predicates only); it orders threads
  *within L5 only* and "no lexical thread moves" (`assemble.py:482-497`). It therefore cannot
  produce a decline, cannot change which lexical thread is rank 0, and cannot change the chain's
  target. The evidence: the terminal `thread_map` targets agree between the real reranker and
  the bag-of-words stand-in on all seven declined-chain cases, and L6 did not even fire on
  RANK-02's served response (`rungs` without L6, the D.7 gate).

**Verdict:** the regression is caused by the semantic rung's pool and shortlist *structure* -
the pool's bookkeeping and the shortlist's fixed 25 hits concentrated by the pool's own
seeding - meeting a ladder that protects hits and a chain that narrows hit threads. Embedding
*quality* is not implicated by any measurement here: a bag-of-words embedding produces the same
declines, the same chain, the same targets. Reranking is exonerated for the first-response
regression. The one model-dependent residual is the per-thread distribution of the 25 hits and
the alphabetical position of the unselected pool threads (SEM-01's walk), both confirmable with
a single traced run (`--traces`) of the lost cases - not another campaign.

## 5. Why `fixed-window` and `full` (and their sem-off twins) have identical outcomes

**The selector was exercised.** With spies on `plan.run_ladder`, the two selectors plan
different fill sets on every case (e.g. RANK-01: 0 rows query-aware vs 42 fixed-window; EXP-03:
3 vs 23; REV-03: 0 vs 70) [word]; `plan_thread` calls `selector.select` unconditionally
(`plan.py:356`), and `substrate()` installs `FixedWindow()` on the two fixed arms
(`run-diagnostic-4311.py:252-259`). It was not skipped.

**Its output never reaches the wire.** Every first response on this corpus starts far over the
host cap (the twelve-source cases plan 500-660k characters against 25k), and on every case
the ladder ran through step 5 and into step 7. Step 1 (`e4_query_scored_fill`) takes the fill's depth first, step 5 collapses the
resulting stubs into runs, and the count of `Band.FILL` rows on every served first response is
**zero on every case, both semantic states, both selectors** [word]. The scrubbed wire of the
two selectors differs in nothing but the fence nonce and a one-second recency boundary. Wire-
identical responses give the driver identical offers, so identical walks and identical calls:
that is what the records show (`full` 13.9 vs `fixed-window` 13.9 calls, 32 vs 32 declines;
`sem-off` 21.3 vs `sem-off+fixed-window` 21.3, 9 vs 9) [real].

**Recovery did not mask a first-response difference.** There was no first-response difference
to mask: the arms are identical *before* any retry. DISC-02's comparison (query-aware fill
against Baseline F at equal budget) is unmeasurable on this corpus and these budgets, not
because the selector is broken but because the fill is the first thing every response
sacrifices. A comparison that could show the selector needs responses that carry fill rows -
short threads, or a cap the fill fits under - which no diagnostic case here produces.

## 6. Kept apart

*Reachability, not discovery.* Every number above is known-target: the driver follows offers
that could carry a `required` id and walks groups and not-included entries unconditionally
(`boundary.py:279-290`). Nothing here says whether a model would choose the right offer; the
lexical arm's deliveries came from exhaustive walking, not from ranking.

*Wrong content retrieved, not a wrong answer generated.* The chain's terminal
`thread_map(top thread)` serves a real thread that is not the evidence's - wrong content
reached, stated as such (`evidence_after 0/1`). No answer is generated anywhere in this harness;
the `w` flags in FATAL PROBLEMS belong to the primitive-floor and qf-1 baselines and do not
appear on any `full` cell.

*Not this diagnosis.* R-M2-076's first-response overflow on the lexical arm (EXP-02, RANK-01,
RANK-04, REV-02 decline on both arms) and R-M2-084's never-offered evidence (REV-01, REV-02).
The semantic arm makes both worse by the limbs above; it does not cause them.

## 7. Repair proposal (not implemented; one coherent change in four parts)

The order is by certainty and by how much each part is a correctness defect rather than a
design choice. Each names the code, the cases it would move, and the evidence that would have
to hold before it is accepted. Predicted effects are [word] arithmetic and are predictions.

**R1 - The estimate charges what the wire names** (defect; `retrieval/assemble.py:2932-3004`,
`envelope/disposition.py:1815-1836`, `disclosure/layout.py:522`). Either file a tail recovery
for the two pool caps so their groups fold like `max_hit_threads`' - the honest tail affordance
is a question, since AD-03 forbids a pool-widening call and the group's own remedy is a thread
map per thread - or, simpler and always true, count `pool_granular` as **fixed** in
`foldable_grouped_threads` and stop counting overflow twice (`len(overflow) +
len(pool_granular)` sums sets that overlap; `foldable` exceeded `grouped` by 27 on REV-03).
With the estimate honest, REV-03's response would decline through the ladder with a
`retry_with` instead of being refused on render with none; every served semantic response's
estimate becomes a bound again. Certify by adding the `_WordBackend` to
`test_the_character_estimate_is_at_or_above_the_rendered_result`'s matrix (a semantic-arm
shape per row): the estimate has never been certified with a pool in it.

**R2 - Before the ladder empties the response, it collapses the last source** (contract-level,
`disclosure/ladder.py:589-623` and `_collapsible`). A.7a says a collapsed-run member is
*present*; `_carries_nothing` accepts it; the lexical arm's served responses on this corpus are
exactly that shape (zero rows, the hits as run members) and the driver delivers from them. Yet
the last resort prefers splitting the only evidence-bearing source to degrading its protected
rows. Proposal: one step between 7's last resort and the emptiness gate - when a single
evidence-bearing source remains and it is over, its rows including the top-k-protected and
floor rows degrade to stub and collapse into runs, and only if that still does not fit is it
split. OD-3's ordering is preserved (a response carrying its hits as run members is the louder
claim than an empty one). On EXP-03 at width 12 this gives 22,730 + 2,032 = 24,762 [word] on
the *current* estimate - and the current estimate names 24 of that response's 30 groups while
the wire names every split-off and pool group (only `max_hit_threads` groups fold), so once R1
makes the estimate honest EXP-03 is over again: **R2 alone is not sufficient there**; with R3's
`pool` narrowing or a pool-shape decision it is. On SEM-03 (15,175 + 2k) it is sufficient alone. It is right independently of the
semantic arm: it is the ladder emptying a response it could have collapsed.

**R3 - The chain changes dimension on an emptiness decline** (contract gap, R-MCP-033
requirement 5; `disclosure/ladder.py:104-124`, `surface/recovery.py:117-168`,
`surface/server.py:296-312`). Carry the refusal class on `DisclosureLadderExhausted`
(`empty: bool`, or the `Reason`), and for an emptiness refusal offer the top thread's map - or,
when the pool's groups dominate the fixed cost, the same search with `pool: {max_threads: n}`
narrowed, which *is* an existing argument and does reduce limb (ii) - **first**, instead of
halving `max_hit_threads` three times. This does not deliver a case by itself (the top thread
is not the evidence's in any lost case) but it returns three of the four driver rounds to the
walk: RANK-02 would walk its served response's 24 offers with four rounds instead of one. It
is the change R-MCP-033 already promised.

**R4 - Offers in retrieval order** (reachability; `envelope/disposition.py:1797`,
`disclosure/ladder.py:562-587`, `harness/…/boundary.py:171-178`). Emit `withheld_groups[]` and
`not_included_sources[]` in the rank the ladder held them at, not by thread id and not
max-rank-first, and have the driver walk them in that order. This is what "offer order is
retrieval's" would actually mean; today it is alphabetical. Moves SEM-01 on the semantic arm
and shortens every lexical walk (EXP-03 at offer 29 of 31, RANK-03 at 25 of 29). It changes no
budget and no case.

**What the proposal deliberately does not do.** It does not touch the pool's bounds (25
threads / 300 messages / k=25), the recency window, `MAX_HIT_THREADS`, the cap or the driver's
budgets; it does not swap or tune either model; it does not gate L5 off. Whether the pool
*should* seed from the ladder's own touched threads (D.5 step (a)) - the design decision that
puts the shortlist's hits where the lexical hits already are, and so drives limb (i) - is an
owner decision on the architecture, recorded here and not proposed.

**Acceptance evidence to require, in order.** (1) The estimate matrix with a backend: estimate
≥ render on every shape. (2) The word-backend first-response table above re-run: first searches
served on `full` at least where `sem-off` serves them, or declined with a retry that changes
dimension. (3) The two real-model modes re-run into new record names, both earlier pairs kept;
the claim to test is "backend-on delivers no fewer cases than backend-off", not any absolute
number. (4) Reachability and discovery still reported apart.

## 8. Uncertainties, stated

* The per-thread distribution of the real shortlist's 25 hits is not in the records. The
  inference that it concentrated in the top lexical threads under the real model rests on the
  chain reaching width 1 and still declining on the same five cases, which the mechanism
  requires and no other measured mechanism produces. One traced run of EXP-03 and RANK-03 would
  make it a measurement.
* SEM-01's real-model walk order (which pool threads sorted before t-t0011) is likewise not
  recorded; the [word] index is 9 of 41. The mechanism (alphabetical groups, page calls per
  map) is code, not inference.
* RANK-02's rank-0 change (t-t0009 → t-t0003) is [word]; under the real model the served
  width-1 response's rank-0 thread is not recorded. It does not affect the diagnosis: the
  case is lost to the chain consuming rounds, whichever thread was first.
* The [word] character figures are the estimate's (`layout.chars()`), not renders, except
  where a render is stated (REV-03: 32,259; the served responses' 16,984-22,821). Estimates
  were at or above renders on every served case here, REV-03 being the one exception and the
  subject of R1.

## Findings ledger rows added

R-M2-093 (limb i, HIGH, OPEN), R-M2-094 (limb ii-b: estimate counts pool groups as foldable,
HIGH, OPEN - a defect), R-M2-095 (limb iii: the chain narrows `max_hit_threads` on an
emptiness refusal, MEDIUM, OPEN), R-M2-096 (offer order is alphabetical, MEDIUM, OPEN),
R-M2-097 (the estimate matrix has never included a backend, MEDIUM, OPEN), R-M2-098 (the
selector's output never reaches the wire on this corpus, so DISC-02 is unmeasured here, INFO).

---

**Addendum, 2026-09-15, after the real-model trace (`ba99c7a`). Nothing above is edited; this
says which of its claims are now measured and which one is wrong.**

Confirmed as observations by `benchmarks/trace-first-response-ba99c7a.json`: the pool is
model-independent (identical seeds, candidates, threads read and rows embedded under the real
models and the stand-in, on all seven traced cases); the hit set's size is fixed at 25 by rule
(`|hit_ids|` identical between backends on every case); L6 admits no ids on any served
response; and the regression is structural rather than about embedding quality, since the
shortlist's membership differs substantially between the real models and the bag of words while
every disclosure outcome - served or declined, group keys, named groups, folded tails, final
sources, characters - is identical. §4's "one model-dependent residual" is settled: it did not
matter.

**§3 limb (i) is wrong about its mechanism, and §7's R2 does not depend on it.** The
concentration is real and larger than stated (the rank-0 source's present hits go 4 to 57 on
RANK-03 with the backend on), but it is not D.5 step (a) putting the shortlist's 25 into
already-hit-bearing threads. `SemanticRunner._build_pool` sends each probe as
`list_messages(rung=RungId.L5)`, so every id a probe returns is an L5 hit and an E2 floor
member: 334 to 462 of them on these cases, against a shortlist of 25. Recorded as R-M2-101.

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

One thing the stand-in could not have shown, recorded as R-M2-102: on RANK-03 the real
embedding ranked the evidence thread first and the response still did not map it, because
`max_hit_threads` cuts the pre-ranking order.

Full reconciliation, with the paired real-model outcome and its call cost:
`docs/reviews/INTEGRATION_REPAIR_2026-09-15.md` §8.
