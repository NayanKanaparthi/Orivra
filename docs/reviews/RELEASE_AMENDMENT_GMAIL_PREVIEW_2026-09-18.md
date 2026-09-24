# Release amendment — Orivra for Gmail, preview (2026-09-18)

**Status.** Owner decision, recorded. Amends the *sequencing* of §9a's release checkpoint. It
does not amend the product scope, does not waive a criterion, and does not close a finding.

---

## 1. What this changes, and what it does not

**Changes.** When the M2 comparative acceptance is answered, and what the release may be called
before it is answered. The release path from here is: finish M2's product prerequisites, build
M3's query-time Gmail graph, verify the whole Gmail experience, prepare a release candidate.

**Does not change.** The intended product. Orivra for Gmail ships M2's retrieval and disclosure
**and** M3's query-time context graph. This amendment is not a decision to ship the older
MailWeave feature set under a new name, and nothing here authorises dropping the graph, the
expansion handles, the omission accounting or the certificate extension.

Drive (M4) and Slack (M5) remain later work, as §9a already says.

---

## 2. The comparative acceptance: a release-gate exception, not a satisfied criterion

**What this is, named in the rubric's own terms.** `PROC-01` says `NOT TESTED` blocks release
exactly like `FAIL`. H1, H2 and H3 are `NOT TESTED`. This amendment does not change that
status, does not re-score it, and does not argue it away. It records an **explicit
release-gate exception for a preview release**: the preview ships with a mandatory criterion
unmet, the exception is written down here with the owner's name on it, and the exception's
whole content is a restriction on what may be claimed.

An exception is not a pass. Three consequences follow and none of them is optional:

1. The criterion stays open in `FINDINGS_LEDGER.md` and in `RUBRIC_TRANSITIONS.md` as unmet.
2. The preview may not be described anywhere as having met M2's acceptance, and no artefact
   may imply a comparison it has not made (§5).
3. A **general-availability release is still blocked** by this criterion. The exception is
   scoped to the preview and expires with it; it is not a precedent for the next release and
   does not transfer to one.

**Scope of the exception, exactly.** It covers H1, H2 and H3 - the comparative hypotheses in
§9a.2's "M2's Accept, in full" - and nothing else. Every other mandatory criterion in
`RELEASE_RUBRIC.md` still binds, unwaived: retrieval correctness, disclosure, MCP conformance,
freshness, security, injection posture, observability and regression. This amendment waives
one thing and it says which.

### 2a. The measurements themselves

§9a.2 binds "M2's Accept, in full: H1, H2, H3 measured on F1–F17 against the v0.1 lexical arm."
**That measurement has not been made, and this amendment does not make it.**

| Registered hypothesis | State |
|---|---|
| H1 — semantic escalation recovers evidence lexical retrieval misses, at zero cost on exact lookups | **NOT MEASURED.** Deferred. |
| H2 — bounded reranking improves top-of-list precision without changing exact-match families | **NOT MEASURED.** Deferred. |
| H3 — query-aware disclosure selects the answering message more often than position-based selection | **NOT MEASURED.** Deferred. |

Three things are true at once and all three are recorded rather than reconciled:

1. **The corpus was rejected.** The independent corpus read (`C4_CORPUS_READ_2026-09-17.md`)
   returned NO on C4 after two repair rounds. The round-two corpus is frozen at
   `benchmarks/gate/corpus-freeze-round2.json` and stays frozen.
2. **The runner was rejected, twice.** `RUNNER_REVIEW_RESULT_2026-09-17.md` and then
   `RUNNER_RECHECK_RESULT_2026-09-17.md` both returned NO. The second round of repairs
   (`contracts.py`'s clause decision tables) is in the tree and is **not** claimed as acceptance;
   it has not been through a recheck.
3. **Therefore no comparative claim is available.** Not "H1 holds", not "H1 fails", not "the
   semantic path is better", not "the semantic path is no worse". The honest state is that the
   instrument that would answer the question has not been shown to work on a corpus that has not
   been shown to answer it.

**Explicitly not claimed by this release, in any artefact, including README, docs, package
metadata and marketing:** that Orivra for Gmail retrieves better than a lexical baseline; that
semantic escalation is measured to help; that reranking is measured to help; that query-aware
disclosure is measured to beat a fixed window. A preview may describe what the product *does*.
It may not describe what it is *better than*.

---

## 3. What is preserved

Nothing is deleted, downgraded or re-scored to make this amendment true.

- The rejected corpus and its freeze manifest.
- Both corpus-repair rounds and their results.
- Both runner reviews, the recheck, the reviewers' probes with their original hashes, and
  `PROBE_INTEGRITY_2026-09-18.md`'s standing rule that review directories are read and run,
  never edited.
- `FINDINGS_LEDGER.md` in full, with every OPEN row still open. In particular R-M2-101, R-M2-103,
  R-M2-107, R-M2-108, R-M2-109, R-M2-112 and R-M2-118 remain open and are not closed by this
  amendment.
- `EVALUATION_SCOPE_DECISION_2026-09-17.md`'s three-way split of what can be tested credibly,
  what needs independently authored material, and which M2 claims stay unmeasured.

---

## 4. What stops

For this release path only:

- **No third corpus-repair round.** No re-seeding, no regeneration, no edits to the frozen corpus.
- **No broad evaluator work.** The clause decision tables are the last bounded evaluator change on
  this path. The evaluator stays in the tree, runnable, and is not used to declare readiness.
- **No general audit expansion**, and no benchmark redesign.

What does not stop: correctness, security, permission, omission-accounting, freshness and recovery
testing on the product itself, with small independently checked fixtures and realistic workflow
demonstrations. Those are release evidence. The rejected benchmark is not, and is not cited as
quality evidence anywhere in the release candidate.

---

## 5. The claims boundary this leaves

**Every claim below is conditional on the tests that demonstrate it, and is scoped to what
those tests cover.** None is a universal guarantee, and the difference is not a formality: a
test demonstrates behaviour on the inputs it exercises, and this product has no evidence about
inputs no test has reached. Where a claim is written as "demonstrated on X", X is the whole of
the claim.

| Claim | Demonstrated by | Scope it does **not** cover |
|---|---|---|
| Omission accounting is complete against the response's own certificate | the certificate seal and disposition suites; `certify` refuses a response whose ids lack a disposition | completeness against the *mailbox* - only against what this response observed |
| The graph's capped branches are recoverable | `test_orivra_graph_slice.py`, on the synthetic mailbox at a 7-node budget | real Gmail threads at scale; no live-mailbox graph run has been made |
| Observed and inferred relations are distinguishable | `test_observed_and_inferred_are_distinguishable_on_the_wire` - and today **every** edge is observed, so the inferred half is untested because it does not exist yet | anything about inferred edges; `supersedes_stated` is unbuilt |
| A reply edge is never drawn from date adjacency | `test_a_date_adjacent_row_produces_no_edge_and_is_reported_as_a_gap`, plus C-02a in the wire model | nothing - this one is structural: the builder reads `linkage`, not position |
| The semantic backend's absence produces a declared fallback | `tests/test_r_m2_113_semantic_unavailable_fallback.py` | backend failures in modes that test does not construct |
| Expansion handles expire and cannot be forged | `test_an_expired_query_id_is_refused_rather_than_rebuilt`, `test_a_handle_the_graph_never_minted_is_refused` | adversarial handle forgery beyond argument substitution |
| Permission requirements travel with every edge | the edge model re-derives the conjunction and refuses a mismatch; asserted in `test_every_edge_carries_both_endpoints_in_support_and_derives_its_own_conjunction` | live permission *release*, which is `permission.release` against a probe and is not exercised end to end |

**Not supportable, and therefore not said:** the product retrieves *correctly* in general; the
graph is *complete*; permissions are *safe* in the abstract. Each of those is a universal where
the evidence is a set of cases.

Also not supportable: any comparison, any superiority, any efficiency claim (R-M2-103 and
R-M2-112 are open and no cost claim is established), and any statement that M2's acceptance was
met or waived-as-met. The accurate sentence is "shipped under a recorded release-gate exception
with the comparative criteria unmet".

**Graph relationships are not causation.** A `supersedes_stated` edge is a statement about what two
messages say, carrying the spans it was derived from. It is not a claim that one decision caused
another, and the release documentation says so where the graph is described.

---

## 6. Where the deferred work goes

The comparative acceptance is deferred, not abandoned. It needs, in this order: independently
authored replacement corpus material that the corpus review's four questions can be answered
"yes" on; a runner that passes an independent recheck; and then H1/H2/H3 measured on it. That
sequence sits after this release checkpoint and before any comparative claim is made anywhere.

---

*Amends: `docs/ORIVRA_V1_PLAN.md` §9a. Does not supersede it — §9a.2's obligations stand, with
M2's Accept recorded here as unmet and deferred rather than dropped.*
