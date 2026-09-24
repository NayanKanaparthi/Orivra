# Orivra / MailWeave: engineering learning journal

Started: 2026-09-15. Owner: Nayan.

## Purpose and recording rules

Capture failures, investigations, decisions and verified outcomes for later interviews,
résumé discussions and technical writing. This is a retrospective, not a product contract
or permission to change the implementation. Do not let it drive acceptance criteria.

This initial history is reconstructed from the owner’s development conversation. Historical
outcomes below are reported outcomes unless explicitly identified as source-reviewed.
Recheck original records before publishing exact numbers or claiming causality.

For future significant findings, append: symptom → competing explanations → discriminating
evidence → root cause → decision → verification → remaining uncertainty. Record exposed
diagnostics as development evidence, not fresh held-out acceptance. Keep unsuccessful
experiments. Never turn a proposed repair into a completed achievement.

The project was built with AI-assisted implementation and review. Describe personal ownership
accurately: product direction, questions, experiments run, decisions and verification. Explain
which coding or review work was assisted rather than implying every line was written unaided.

## 1. A passing test can fail to exercise its claim

**Examples:** The first deadline comparison answered small queries under both limits but did
not distinguish those limits. The first metadata-header probe used messages without reply
headers, so it could not establish preservation of those headers. Some corpus coverage checks
counted allocated positions or sentinel-bearing messages instead of evidence satisfying a
family’s actual requirements.

**Investigation and response:** Add eligibility floors and per-property coverage, distinguish
uninformative from passing, preserve the raw records and withdraw unsupported conclusions.
The later PF-2 run reportedly compared 12 messages, including 11 with reply-linking headers.

**Lesson:** A useful test needs a reason it would fail if the claimed property were absent.
Test data and the test can share the same blind spot.

## 2. Deadline tuning requires an informative experiment

**Symptom:** Small live queries almost exhausted the original 2,000 ms deadline; broader
queries initially failed on response size, obscuring the timing question.

**Response:** Separate search and expansion timings; counterbalance/repeat arms; distinguish
declines, evidence depth and completeness; require the actual acceptance query to contribute.
The later three-arm run showed useful evidence at 7,700 ms but instability at the upper arm.
Adoption of 7,700 ms was recorded as an owner decision, not a clean automatic validation pass.

**Lesson:** An operational decision under uncertainty is legitimate when its warrant and
limitations are explicit. Do not rewrite the experiment’s verdict to justify the decision.

## 3. Audit bookkeeping can crowd out the evidence

**Symptom:** A response could contain zero rows and still exceed a 25,000-character limit
because it accounted for 45 withheld messages with verbose records. Later retrieval breadth
exposed related failures even after grouping and deduplication.

**Response:** Group omissions at recoverable granularity, deduplicate repeated explanations,
measure structured content plus its text mirror, and preserve exact internal accounting.

**Lesson:** Removing content does not necessarily reduce serialized size. Observability and
provenance have resource costs that belong in the design, not just in final validation.
Earlier improvements did not eliminate every instance of this architectural class.

## 4. Performance measurements must represent the real lifecycle

**Symptom:** A backend factory loaded model weights per acquisition. A smoke run reported
36,543 ms of loading against a 6,000 ms semantic-work budget. Early timing curves also mixed
warm-up effects and an unspecified accelerator with claims about CPU performance.

**Response:** Reuse the backend for the server process; distinguish startup from warm query
work; name the device; warm up each stage; retain repeated samples and runtime versions.
The qualified CPU run reported approximately 250 ms for the measured warm embedding and
reranking workload. It did not measure Gmail latency or retrieval quality.

**Lesson:** Measure the deployment lifecycle, not merely a function call. Loading, inference,
I/O, memory and relevance are different questions.

## 5. A test double must not manufacture the property under test

**Symptom:** The seeder inserted 2,248 messages, but its thread grouping disagreed with the
manifest. The double had assigned thread IDs from that manifest, hiding the missing real API
behavior.

**Response:** Correct the insertion behavior, run a four-message real threading rehearsal,
then perform explicitly authorised cleanup and reseeding with recorded IDs. The subsequent
run reported 2,248 messages in 40 conversations with zero discrepancies.

**Lesson:** Offline tests cannot validate an external service by assuming its answer. Use a
small, controlled integration rehearsal before scaling an irreversible operation.

## 6. Evaluation data is an engineering artifact

**Symptom:** The initial corpus had enough messages but insufficient semantic content for
several registered families. Later generators leaked answers through tokens, wording,
positions, distinctive values or family-specific shapes.

**Response:** Independent case authoring, content review, negative fixtures and query-free
baselines exposed weaknesses that schema validation did not catch. Some dataset limitations
remain open; diagnostic cases are not formal acceptance evidence.

**Lesson:** Corpus size and schema validity do not establish task validity. A baseline can
reveal shortcuts without its score being arithmetically subtractable from another system’s.

## 7. Accounted for, reachable and delivered are different states

**Symptom:** Reply expansion could raise on parent-linkage validation; the harness initially
hid exceptions and followed only one expansion hop. Later it bypassed the shipped MCP
boundary, missing structured recovery. Long-thread runs repeatedly pointed to snippets without
ever delivering the desired body.

**Response:** Exercise the shipped boundary, record exceptions/refusals, use bounded traversal,
separate explicit reads from search selection, add pages and requested-batch continuations.
The reported sem-off diagnostic improved from 2/13 to 9/13 using listed calls; known-target
direct reads reached 11/13. These are reachability results, not agent answer accuracy.

**Lesson:** Local validity of each response does not guarantee that the sequence of responses
lets a caller accomplish the task. Verify end-to-end progress and actual content delivery.

## 8. A continuation is a promise about state

**Symptom:** Thread-ID/page-number continuations recomputed page width after mailbox changes,
potentially skipping or repeating rows. The first test restarted traversal, avoiding the flaw.

**Response:** The reported repair signs page width and thread state through the handle system,
checks outstanding continuations and returns an explicit restart on invalidation. No-handle
navigation and total-thread inventory size remain declared limitations.

**Lesson:** Pagination correctness includes changes between calls, not just complete traversal
of a static fixture. Test the old cursor against the changed state.

## 9. Current case: adding semantic retrieval reduced delivery

**Status: diagnosis recorded at d4ab767; R1–R4 repair proposed, not verified as implemented.**

**Observed on the real-model diagnostic:** Backend-on delivered 4/13 versus backend-off 9/13
through listed calls, and 5/13 versus 11/13 with known-target direct reads. Backend-on recorded
32 declines versus 9. Models loaded successfully; these were not installation failures.

**Competing explanations:** Poor embedding relevance, reranking errors, resource exhaustion,
disclosure overhead, offer ordering or a measurement defect.

**Investigation:** Existing paired traces located losses; a model-free structural reproduction
inspected pool membership, layouts, protected rows, group emission and recovery. It reproduced
the refusal pattern. Selected sizing/grouping/recovery code was independently inspected in
this Codex conversation; the entire causal chain was not independently rerun here.

**Diagnosed mechanism:** Semantic shortlist hits increased protected evidence in already-hit
threads. Pool omissions added fixed bookkeeping. The estimator treated groups as foldable
when the wire kept them named. A measured stand-in example estimated 24,531 characters but
rendered 32,259. Recovery repeatedly reduced hit-thread width without removing the binding
pool or protected-row cost. Alphabetical offer ordering compounded one navigation failure.

**Proposed repair:** Share grouping logic between sizing and emission; preserve navigable
search evidence before emptying a response without weakening requested reads; recover against
the actual binding constraint; preserve available retrieval rank through offers.

**Uncertainty:** Real shortlist distributions were not captured in the original traces.
Stand-in agreement supports the structural diagnosis but does not prove all real-model
mechanisms identical. Reranking quality and semantic usefulness remain unestablished.
Query-aware fill was planned but eliminated before emission in the structural reproduction,
so equal arm outcomes did not measure its benefit.

**Interview explanation, accurate today:**

> Adding semantic retrieval made our diagnostic worse, so I did not assume we needed a better
> model. We compared the same cases with the backend on and off and traced where evidence
> stopped being deliverable. The investigation identified a conflict between the extra
> retrieval structure, response accounting and recovery policy. The important lesson was to
> evaluate the whole evidence-delivery pipeline, not just model scores. The repair still needs
> verification before I can claim the regression is fixed.

## 10. Integration repair implemented; real-model verification pending

2026-09-15, commit `7224b86`. Source: `docs/reviews/INTEGRATION_REPAIR_2026-09-15.md`.
The checkout and diagnostic budgets were checked in this conversation; tests and reported
stand-in results were not independently rerun here.

**Implementation reported:** One grouping arrangement now drives sizing and emission.
Search preserves its final evidence-bearing source as recoverable runs before emptying it;
explicit reads remain protected. Refusals expose cost terms and predicted fitting widths,
and offers retain available retrieval rank. Pool narrowing was rejected because in this
implementation it creates more groups, not fewer. That is a useful example of correcting a
proposed remedy after inspecting the actual mechanism.

**Review lesson:** Predicted narrower layouts initially used ranking order, while the real
producer cuts by pre-ranking order. The independent review caught that mismatch; the fix
carries the producer's cut order explicitly and tests predictions against actual calls.

**Reported stand-in outcomes:** Full delivery improved 4→9 of 13 in listed mode and 5→11
in named mode, without delivery losses; backend-off delivery stayed at 9 and 11. Full-arm
declines fell 32→7. Named-mode calls increased 180→308 because responses now offered paths
to walk instead of terminating early. Better delivery is not automatically better efficiency.

**Bound qualification:** The server's worst-case recovery-chain promise changed 7→12 hops.
The diagnostic still permits only 4 levels and 33 total calls per case, so the reported gains
were not obtained by enlarging its traversal budget. The server contract change remains a
distinct decision and must not be described as all bounds staying unchanged.

**Pending:** Verify with the real installed models. Broad-query first-response overflow,
never-offered evidence, and large-map inventory limits remain. Matching the simpler arm on
exposed diagnostic cases would repair this regression, not prove semantic retrieval adds value.

**Provenance warning:** A `--tag` names an output; it does not select the code revision. A trace
run on `7224b86` is post-repair evidence even if someone labels it `d4ab767`. If the old trace
was not run before updating, do not reconstruct that historical claim from a new-code run.

## 11. Real-model diagnostic reproduces the repair

The owner completed the trace and both diagnostics tagged `ba99c7a`, using the actual locked
Potion and BGE models on CPU. This entry is based on the complete pasted terminal results,
not an independently rerun experiment. Records: `trace-first-response-ba99c7a.json` and
`diagnostic-run-boundary-repair-{listed,named}-ba99c7a.{txt,json}` under `benchmarks/`.

**Paired delivery:** Backend-on improved 4→9 of 13 in listed mode and 5→11 in named mode.
Backend-off stayed at 9 and 11. The case tables show five regained listed-mode cases
(EXP-03, RANK-02, RANK-03, REV-03, SEM-01), plus EXP-02 in named mode, and no delivery losses.
Backend-on declines fell 32→7; backend-off declines fell 9→4. The diagnostic still uses
33 calls and four levels per case.

**Cost qualification:** Post-repair mean calls remain higher with the backend enabled:
24.8 vs 23.0 listed and 23.7 vs 21.5 named. Equal delivery is not an efficiency advantage.
Both named-mode arms still miss REV-01 and REV-02; listed mode also misses EXP-01 and EXP-02.

**Trace qualification:** The post-repair trace measures real shortlist distributions and
group arrangements, with 13 served and one declined first search among its selected 14
case/arm pairs. It is not a recovered pre-repair trace. RANK-03 selects 24 of 25 messages
from t-t0048 while the final listed source is t-t0004, illustrating why shortlist membership
and downstream source selection must be inspected separately rather than assuming they agree.

**Defensible story now:** We identified and repaired an integration regression, then verified
the recovered evidence delivery with the real models on the same diagnostic cases. We did not
change models or increase the diagnostic traversal budget. This does not yet prove semantic
retrieval improves quality, reranking adds value, or an unaided agent can find the answers.
The cases are exposed diagnostic cases, not held-out M2 acceptance.

## Next entry

### A16 reveals a simulator defect; qualify the earlier measurements

Report: `docs/reviews/A16_RECENCY_POOL_2026-09-15.md`, working tree based on `9a03eb4`.
At inspection A16 was uncommitted. The fixture's date parser previously accepted slash dates
but not the epoch-second form emitted by internal recency probes. The unsupported predicate
matched everything. Earlier runs used real embedding/reranking models but this same synthetic
mailbox, so real models did not make those runs faithful to Gmail's recency filtering.

The reported product-by-fixture comparison is useful experimental control. With the corrected
fixture, A16's subtraction alone changed no measured response on the diagnostic. Its shortlist
union accounted for the measured difference. Do not claim the intended protection narrowing
delivered the predicted cost benefit. Earlier R1–R4 results remain observations under the old
simulator, not proof that the measured scale or cause generalises to real Gmail.

Further checks needed before a costly real-model comparison: triage reachable late-bound
closures in the evaluation path; use the same corrected fixture for baseline and A16; distinguish
13 answerable cases from two controls; distinguish content rows from required answer evidence.
Unfixed findings include an embedding-failure reporting crash (R-M2-109), first-origin versus
later-route selection (R-M2-108), and role/tier asymmetry (R-M2-106). Their existence must not
be hidden by a blanket claim that every authorised boundary is held.

Interview lesson: validate the simulator's semantics as well as the model and product. A paired
improvement can be real within a flawed simulation while the explanation of its real-world
importance still needs revision. Preserve the data and narrow the claim rather than erasing it.

### Contract investigation at `9a03eb4`

The investigation distinguishes retaining every observed ID in the contract's hit set `H`
from assigning every pool admission evidence-tier depth and reply-chain obligations. The
proposed decision is to keep accounting intact while changing protection for unselected,
recency-pool-only candidates. This is a contract amendment, not a verified implementation.
R-M2-102 is reported working-as-designed under ADV-110's prohibition on ordering partially
scored lexical candidates by incomparable scores. That explains the behavior; it does not
establish that this product tradeoff is optimal.

Evaluation caveat checked against plan §8.2: H1 concerns semantic retrieval, H2 reranking,
H3 query-aware disclosure. L5-only evidence tests a route for semantic recall benefit; it
must not become a blanket prerequisite for measuring H2/H3. Those need their own exercised
comparisons. The checkpoint still contains the previously identified false blanket claims
about no live seeding and no acceptance runner, despite the new investigation.

### Checkpoint correction after `8bf8855`

The implementer's reconciliation revises the earlier shortlist-concentration explanation:
R-M2-101 attributes the excess hit/floor membership to pool probe results being treated as
hits, not just the 25 selected messages. R-M2-102 records a separate selection problem:
correct semantic candidates can be excluded by a mapping cut made before ranking. Preserve
these as newly reported findings to verify, not conclusions already fixed by R1–R4.

The shared Mac `.venv` was again replaced from Linux through an indirect `make acceptance`
invocation. Codex verified its Python symlink points into a Linux session. Lesson: isolation
must cover transitive build commands, not just a promise not to invoke a package manager.
Restoration was recommended, not performed by Codex; affected acceptance outputs are invalid.

Two checkpoint inventory claims were also checked against the repository: the evaluation
CLI's `_run` exists and wires arms/traces, and earlier live seeding/cleanup records still
exist. This does not prove current acceptance readiness or current mailbox state. It does
disprove the blanket claims that no runner was built and seeding never touched a mailbox.
Distinguish missing capability, unverified capability, and unsuitable evaluation data before
creating new work.

Record scoped closure of this regression, disposition of remaining failures, and independently
validated retrieval-quality and agent-discovery results when available. Do not turn another
passing diagnostic into a broader product claim.
