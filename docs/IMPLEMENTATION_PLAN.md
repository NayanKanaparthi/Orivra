# IMPLEMENTATION_PLAN.md — the executable work plan

**Status:** the last planning artifact. From here discoveries become code, tests, reviewer findings,
regression fixtures, or short amendments to `ARCHITECTURE_DECISION.md`. Nothing in this file restates
rationale: design lives in `ARCHITECTURE_DECISION.md` (AD), criteria in `RELEASE_RUBRIC.md` (RR),
process in `AGENT_LOOP.md` (AL), measurement in `EVALUATION_PLAN.md` (EP), binding owner resolutions
in `OWNER_DECISIONS.md` (OD), posture in `SECURITY_NOTES.md` (SN). Citations are pointers, not
summaries.

**Scope rule.** Every capability in AD §E.1 is built. Benchmarks tune and validate; they never decide
whether a contracted capability exists (SC §1–§5, AD §E preamble). No workstream below is optional:
each advances at least one mandatory criterion, and 110 of the 113 criteria are mandatory.

**Sequencing rule.** No calendar estimates. Order is expressed in rounds (AL §5) and dependencies.

---

## 1. Workstreams

`Deps` are workstream IDs. `Reviewers` are the AL §2.3 domains whose sign-off the workstream cannot
close without; the adversarial reviewer (AL §2.4) sits over all of them before the gate.

| ID | Workstream | What gets built | Deps | Rubric criteria advanced | Required tests | Gating reviewers |
|---|---|---|---|---|---|---|
| **WS-00** | Repo scaffold and tooling | `server/` + `harness/` as separate `pyproject.toml` packages, Python 3.12+, `uv` lockfile, `models.lock` with SHA-256 pins; pytest layout with an offline default runner; CI jobs: import-linter forbidden-module contract (`server` ⊁ `harness`), grep sweep for `manifest`/`seed_map`/`ground_truth`/`harness` in `server/**`, scope-literal sweep, `gmail/v1` path-literal sweep, generative-client import sweep; `docs/reviews/` + `experiments/` trees | — | NFR-01, NFR-04, PROC-03, REG-03, SEC-01, SEC-02, SEC-08 | CI gates fail on a deliberately planted violation of each sweep; clean-machine bootstrap from the lockfile alone | R-ARCH, R-SEC |
| **WS-01** | Config and credential handling | Two OAuth clients (read `gmail.readonly`; harness `https://mail.google.com/`), loopback + PKCE S256, `0600` token store in a `0700` dir; salt generation and storage; HMAC handle key with `key_epoch`; `~/.local/state/mailweave/watermark.json`; profile derivation (`users.getProfile` digest **and** `client_id == seed_client_id`, fail-closed to `personal`, fatal `auth_profile_underivable`); `mailweave auth`, `mailweave purge`, `harness auth --refresh` (AD §A.4, §B.9) | WS-00 | SEC-01, SEC-02, SEC-03, SEC-04, GMAIL-06, NFR-04 | Config-forgery test (edited `seed_account_hash` still derives `personal`); `getProfile` failure → server refuses to start; token-store permission assertions; expired/revoked refresh → `auth_reauth_required` with the re-auth wording | R-SEC, R-GMAIL |
| **WS-02** | Gmail client layer | Typed `httpx` client over exactly the six endpoints of AD §A.5 with Pydantic payload models; **pager** (`pageToken`, explicit `maxResults`, `resultSizeEstimate` never a truth source, `scan_scope` emission); **batcher** (≤50 sub-requests); **retrier** (250 ms base, ×2, ±25 % jitter, 3 retries, 1500 ms total clamped to the rung's remaining clock, every attempt charged); **decoder** boundary handing off to WS-07; the `http_requests` / `api_calls` / `quota_units` counter split; process-wide **quota governor** (token bucket, `floor_reserve = 900 u`, `max_concurrent_queries = 2`, declared wait/refusal) | WS-00, WS-01 | GMAIL-01, GMAIL-04, GMAIL-05, PERF-02, PERF-03, NFR-03 | Fake-transport unit suite for pager/batcher/retrier/counters; 429 and 5xx injection → `upstream_rate_limited` in-band vs `upstream_unavailable` tool error; governor contention test asserting `process_quota_wait` + `waited_ms`; live smoke once credentials exist | R-GMAIL, R-PERF, R-ARCH |
| **WS-03** | Response envelope and partiality metadata | Schema v2 models (AD §D.2); the **disposition ledger** — `H` accumulated from every executed `messages.list` (incl. L5 participant probes), `history.list` additions and the declared shortlist; `withheld := H − disclosed` computed as a set difference at envelope time with `assert H == disclosed ∪ withheld` before the response leaves the process; withheld record shape `{id, thread_id, why, cap, affordance}`; `stated_total`/`included`/`included_as_stub`, `scan_scope[]`, `ceiling{}`, `errors[]`, `budget{}`, `truncated_by`, role + mechanical reason + `constraint_coverage` on every message; size measurement and self-truncation | WS-00 | EV-01, EV-03, PART-01, PART-02, PART-03, PART-04, PART-05, PART-06, PART-07, DISC-06, ROUTE-01 | Property test: for randomised ladder traces the assertion holds, and a deliberately "forgetful" cap raises rather than silently drops; every withheld record's affordance is executable; `stated_total` vs manifest; response never exceeds the PF-6 ceiling | R-DISC, R-RETR, R-ARCH |
| **WS-04** | Query analysis, lexical rungs, evidence preservation | `ParsedQuery` (provable operators, residual terms, address-normalised participants, interrogative class, answer-type lexicon, confidence tier, `paraphrase_risk`), model-free; A.6a time/timezone policy incl. `window_utc` and the declared `date_margin_days` widening; L0 exact-operator, L1 filtered, **L1b decomposition/intersection**, L2 one-at-a-time relaxation (`max_relax_probes = min(k,6)`), L3 broadening; `exact_signal_match` per the three enumerated branches of A.8a; `empty_diagnosis` three states incl. `{"status":"incomplete"}` | WS-02, WS-03 | LEX-01, LEX-02, LEX-03, LEX-04, EV-02, EV-04, EV-05, EV-06, ROUTE-02, ROUTE-03, ROUTE-04 | Operator-parse fidelity table; L1b recovers the cross-message-constraint case; relaxation enumerability; `exact_signal_match` unit table per branch; issue-#296 signature non-reproduction; position-sweep recall against the full-dump ceiling | R-RETR, R-ARCH |
| **WS-05** | Thread map and structural retrieval | One `threads.get` per hit-bearing thread (deduped per query, `max_hit_threads = 12`); JWZ/IMAP-REFERENCES reply-tree reconstruction with `linkage:"date-adjacent (no RFC reply headers)"` for orphans and no silent re-parenting; address-keyed participant index with authorship vs mentions; strict `internalDate` ordering; position on every row; L4 sibling/structural expansion as separate sources (`max_source_threads = 4`) | WS-02, WS-03, WS-07 | STR-01, STR-02, STR-03, STR-04, STR-05, GMAIL-03 | Reply-tree fixtures incl. broken threading, subject change mid-thread, forwards; ordering test where API array order ≠ `internalDate` order; hearsay-vs-authorship discrimination; declared-gap assertions | R-RETR, R-GMAIL |
| **WS-06** | Handles and staleness | `map_id` = base64url payload + HMAC over `{v, key_epoch, account_hash, thread_ids[], fetched_at, history_id, mapping_digest, ttl}`; redemption order — verify → **independent `history.list` liveness probe** → fetch → digest recompute; error classes `handle_invalid` / `handle_key_rotated` / `handle_expired` / `handle_stale` / `handle_stale_unverifiable`; the LRU with key `(thread_id, history_id_at_fetch)`, 60 s TTL, 64 entries, eviction on staleness; `fetched_at` never restamped, `verified_at` added on LRU service | WS-01, WS-05 | MCP-02, MCP-06, NFR-03 | **PF-15**: mutate-then-redeem executed cache-cold **and** cache-warm as two cases; restart-with-outstanding-handle keeps handles valid; deliberate key rotation yields `handle_key_rotated`, not `handle_expired`; trace labels the warm digest check `cache_tautology` | R-MCP, R-GMAIL, R-SEC |
| **WS-07** | Content processing | AD §D.4a end to end: part selection (`text/plain` preferred, unused alternative declared, depth cap 12 / part cap 64), base64url decode with padding restoration and `undecodable_body` declaration, charset ladder (declared → UTF-8 → cp1252 → latin-1) with replacement counts, RFC 2047 header decoding with verbatim retention of undecodable words and duplicate-header counts, HTML → visible text via `selectolax` (`lxml.html` pinned fallback) with explicit hidden-construct removal, `talon` quote/signature stripping (`email-reply-parser` fallback), NFKC + whitespace normalisation before embedding with recorded truncation; every removal emitted as a `reductions[]` record with a count | WS-00 | GMAIL-02, INJ-04, DISC-03 | Whole pipeline run **with sockets disabled**; GMAIL-02 fixture set (encoded-word subjects, non-UTF-8 charsets, HTML-only bodies, nested multiparts, missing/duplicate headers); hidden-construct corpus asserting `hidden_content` counts; licence assertions on the pinned versions | R-SEC, R-GMAIL, R-DISC |
| **WS-08** | Local semantic rung (L5) | `embed()`/`rerank()` interface with the local backend registered by default; `mailweave setup-models` as the **only** network path to the model host, checksum-pinned; server load forced offline (`HF_HUB_OFFLINE=1`, `local_files_only=True`, local path never a repo id) with single-flight `asyncio.Event` load guard and `max_model_rss_mb` refusal; thread-wise pool construction (a/b/c priority, `max_pool_threads`, `max_pool_messages`), pool disclosed by `scope_rule` + sizes and enumerated as `pool_ids[]` **in the trace only**; stage A `potion-retrieval-32M`, stage B `bge-reranker-base`, shortlist `rule:"top-k by stage-A cosine", k = 25` reported in `retrieval_report.shortlist`; deterministic `semantic_unavailable` degradation | WS-02, WS-03, WS-07 | SEM-01, SEM-02, SEM-03, SEM-04, SEM-05, SEM-06, NFR-01, SEC-07 | Full suite with the model host blocked, server cold-started (PF-5 part b); SEM-LOCAL-ALT registers a second backend without touching ladder code; missing-weights run emits `not_tried` and continues; step-(b) probe IDs appear in `H` and are disposed of; paraphrase-family recall vs SEM-OFF | R-RETR, R-SEC, R-PERF |
| **WS-09** | Ranking (L6) | `mailweave/mechanical-v1` deterministic composite with the firing components named; ambiguity-gated cross-encoder rerank with hard code-level prohibitions (never on `exact_signal_match`, never on `hit_count == 1`, never on an `rfc822msgid:` route); `score.basis` mandatory wherever a number appears; `ordering_effect` false unless the score exists for every candidate in the comparison; Gmail-`q`-selected rows carry no numeric score; bounded body-depth disclosure with ranked stubs | WS-05, WS-08 | RANK-01, RANK-02, RANK-03, RANK-04 | Reranker beats recency and seeded-random controls; trace-verified exclusion from the cheap path; mixed-scale ordering test asserting the mechanical fallback; no-fabricated-score sweep over all response paths | R-RETR, R-PERF |
| **WS-10** | Escalation policy, budgets, stopping, outcome | The ladder state machine L0→L6 + LR under the per-query `budget_accountant` nested in the governor; the AD §A.7 caps enforced in code; the D.3 stopping rules **in their published order**; `floor_quota_units = 845` clamp-up with `budget_clamped{requested, applied, why}`; mid-rung timeout contract (emit what was retrieved, unfinished work → `not_tried`, undisclosed `H` members → `withheld`); the three-way `outcome` of OD-2 — `not_found` **only** when no applicable rung is untried for budget/cap/timeout/error and `budget_caps_hit` is empty, else `inconclusive`; `not_tried[].why` closed vocabulary (`not_applicable` vs `budget\|cap\|timeout\|error`) | WS-04, WS-05, WS-08, WS-09 | AD-01, AD-02, AD-03, AD-04, AD-05, PERF-01, PERF-04, EV-04 | Machine-checkable outcome rule: no response carries `not_found` with a non-empty `budget_caps_hit` or a non-`not_applicable` `not_tried` entry; budget-clamp test; cap-exhaustion produces named cap + rungs not reached + affordances; cheap-family cost and latency bars; escalation fires on the hard families | R-RETR, R-PERF, R-DISC |
| **WS-11** | Representation and disclosure | E2 reply-chain floor — **membership absolute, depth declared** (OD-3): parents and direct children always present, promoted to deeper content when the evidence depends on them; E4 query-scored fill with fixed published weights and reason strings; the A.9a degradation precedence 1–8 executed in order, each step recorded in `reductions[]` and named in `budget_caps_hit`; `body_clean` 600 tok soft cap, 250 tok head-truncation step; 9,000 tok normal ceiling with the 12,000 tok overflow **only** for floor membership, declared in `ceiling{}`; collapsed runs; `not_included_sources[]`; affordance minting as concrete `{tool, args}`; the segment map as the AD §E.2 experimental level | WS-03, WS-05, WS-09 | DISC-01, DISC-02, DISC-03, DISC-04, DISC-05, DISC-06, PART-05, EV-03 | Ladder-termination test on the 40-message/6-hit case; floor membership survives every degradation step; F17 decision-reversal family scored at **each** depth tier against Baseline F(±2); query-aware vs fixed window at equal budget; context efficiency vs full dump; self-truncation before host truncation | R-DISC, R-RETR |
| **WS-12** | Freshness and the recency rung (LR) | `fetched_at` on every map/body/artifact and `history_id` on every source from day one; the non-content watermark store and its declared re-baseline on the `history.list` 404; the LR rung priced at `2 + 20n` with `max_recency_fetch = 8` and overflow IDs as withheld records; the **closed** client-side re-check subset (`from`/`to`/`cc`, `after`/`before` on integer epochs, `has:attachment`, `label:` via the once-per-process `labels.list`) and the verbatim never-a-`q`-match reason string with `role:"context"`; the temporal partiality field (P7) on every response; the FRESH-02 mitigation, built if any of MF1–MF6 fires | WS-02, WS-06, WS-10 | FRESH-01, FRESH-02, FRESH-03, FRESH-04, FRESH-05, FRESH-06 | Watermark contains only `{schema, account_hash, history_id, observed_at}`; expired-`historyId` re-baseline is reported, never silent; free-text-term LR result never attributed as a `q` match; stamps present on 100 % of responses; H5 and **H5-LRoff** arms run per stratum with pooling prohibited | R-GMAIL, R-RETR, R-SEC |
| **WS-13** | Observability and redacted traces | Trace schema v2 (AD §A.11, §D.10) with per-rung latency, both counters plus diagnostic `quota_units`, `pool_ids[]`, `shortlist{}`, `disposition{}`, `exact_signal_match{}`, `answer_type_presence{}`, `freshness{}`, `eval_join`; `Redacted[str]` newtype whose `__str__`/`__repr__` redact under the personal profile, so exception formatting redacts too; two trace record types with the `PersonalTrace` type structurally unable to hold mail text, emitter statically bound at startup; JSONL sink; `mailweave inspect <trace_id>` (IDs → live re-fetch → terminal only, never disk); the `--diagnose=<finding-id>` gated escape hatch | WS-01, WS-02 | OBS-01, OBS-02, OBS-03, OBS-04, SEC-05, SEC-06, SEC-08 | **PF-8** sentinel canary across traces, logs and **forced exception paths**, zero hits; profile fail-closed test; counter cross-check against the harness counting proxy on `http_requests`; no-mail-content-at-rest sweep of every writable path | R-SEC, R-ARCH, R-PERF |
| **WS-14** | Untrusted content and injection defenses | Per-response `fence_nonce` wrapping all mail-derived text; `content.trust` + `content.source` on every body; connector-voiced fields assembled from typed values only; identity fields split (address vs display name) with authentication results labelled; internal model outputs closed-typed by construction (vectors and floats only) and `generative_llm_calls = 0` enforced as a constant plus the CI import gate; the untrusted-data warning carried in the **static tool description**, never in per-result text | WS-03, WS-07 | INJ-01, INJ-02, INJ-03, INJ-04, INJ-05, INJ-06, SEC-07 | Injection fixture corpus: instructions in bodies, subjects, display names and hidden HTML neither steer behaviour nor vanish from the payload; nonce is unguessable per response and mail text cannot close its own fence; spoofed-display-name case labelled; egress allowlist asserted at exactly two runtime hosts with no listening socket | R-SEC, R-DISC |
| **WS-15** | MCP server surface | The four compile-time-constant tools of AD §D.1 over stdio with `readOnlyHint: true`, `structuredContent` mirrored to an agreeing text rendering, no Sampling; argument validation incl. `view:"raw"` → `unsupported_view` and `mode:"metadata"`-only attachments served from `payload.parts`; the D.11 closed error vocabulary with its in-band/tool-error partition; `force_rungs` that can only add rungs; `scan.max_pages` and budget arguments honouring the floor clamp | WS-03, WS-06, WS-10, WS-11 | MCP-01, MCP-02, MCP-03, MCP-04, MCP-05, MCP-06, MCP-07 | Spec-revision conformance suite; structured/text parity property test; annotation truthfulness (no tool can write); metadata constancy across restarts; **PF-7** real-client search → map → get_messages loop with zero host-side truncation | R-MCP, R-ARCH |
| **WS-16** | Evaluation harness, seeder and permanent baselines | Separate `mailweave-harness` package importing only `response_schema.json` and the frozen extraction adapter; the counting proxy (the sole authority on call counts); the seeder (`messages.insert` with `internalDateSource=dateHeader`, caller-chosen `Message-ID`s, `threadId` + RFC 2822 `References`/`In-Reply-To` + byte-identical subject, fictional `.example`/`.invalid` personas); corpus shapes incl. depth 0/5/25 freshness threads, near-duplicate clusters, MIME-signature coverage and structural scaffolding; families F1–F17; Tier-1 oracles O1–O9 and protocols D1–D8; **permanent baselines A/A′, B, C(-old5/-new5/-new20), D, E-matched, E-generous, F(±1/±2/±5)**; M1 and M2 execution modes; experiment log 001 | WS-00 | E2E-01, E2E-02, E2E-03, E2E-04, GMAIL-07, PROC-03, PROC-04, PROC-05, OBS-02 | S1–S14 smoke assertions green on two seeds; ground-truth files unreadable from `server/**` (structurally, per the CI gates of WS-00); corpus regenerated from a fresh seed at each gate; reviewer-selected held-out seed reproduces the numbers; both mailbox profiles exercised | R-ARCH, R-GMAIL, R-PERF, adversarial |
| **WS-17** | Regression suite and fixtures | The EP §5.2 sanitization procedure; F-offline fixtures (deterministic bytes, no network) and F-seeded fixtures (re-seeded cases); the pre-fix-commit assertion harness; the "no benchmark special-casing" sweep over both tests and `server/**`; the fixture lifecycle that never removes a fixture | WS-07, WS-16 | REG-01, REG-02, REG-03, REG-04 | Every finding of severity ≥ MEDIUM has a green fixture or a recorded owner-approved exception; each new fixture demonstrably **fails** against the pre-fix commit; the whole F-offline suite runs with networking disabled | R-ARCH, R-RETR, adversarial |
| **WS-18** | Documentation and claims | README, SETUP (clean-machine, BYO Google Cloud project), SECURITY and the operating-footprint note; the claim → measurement map with every headline sentence bound to a named experiment-log entry; the unbundled statement of the three problems; the limitations / not-measured section; prior-art citations; the read-only and untrusted-content disclosures; the §58 minimum-proof bundle assembled **before** the headline claim | all | DOC-01, DOC-02, DOC-03, DOC-04, DOC-05, DOC-06, NFR-02 | Claim-vs-measurement diff at every gate; no freshness sentence exists anywhere until FRESH-01's log entry exists; overstated claim is a BLOCKER at the release gate | R-DOC, adversarial |
| **WS-19** | Loop machinery and gate integrity | `docs/reviews/FINDINGS_LEDGER.md` and the per-round directories of AL §9; the rubric status table wired so only reviewers move a criterion to `PASS` with round + reviewer recorded; the degenerate-strategy probe recorded per metric; the adversarial reviewer brief; the release-gate checklist of AL §10 | WS-00 | PROC-01, PROC-02, PROC-03, PROC-04, PROC-05, PROC-06 | A criterion cannot reach `PASS` without a reviewer report naming the reproduction; `NOT TESTED` blocks the gate exactly like `FAIL`; baselines demonstrated runnable at every gate | R-ARCH, R-DOC, adversarial |

### Conditions carried into WS-11 from amendment A7 (round 9 review, recorded round 10)

A7 landed the annotation half of the content pipeline in round 9: `body_clean` is the whole
body with classified spans, and `AnnotatedBody.view(classes)` chooses what to show. **The
disclosure half is not built.** As of round 10 nothing in `server/src/mailweave/envelope/`
references `AnnotatedBody`, `SpanClass` or `default_view`, verified by grep and by execution
in `docs/reviews/ROUND_09/R-SEC-DISC.md` §2.1. That is expected — the disclosure layer *is*
WS-11 — but it means three requirements were filed against a round that has not happened yet,
and they belong here rather than only in a review directory.

**1. The `uncertain` signal must be structured, not prose-only (R-DISC-015, MEDIUM).** A7
writes what it judged into a free-text `Reduction.detail`, and `AnnotatedBody.latched` /
`.hidden_chars` are Python properties with no serialised counterpart. A consuming agent reading
the response therefore cannot tell, *by program*, that a message carries a judged extent it
could widen into. Until `latched` is a structured field on the wire, A7's "the text is one view
away" promise is unverifiable by the caller it is made to.

**2. Widening must be floor-message-specific, not a global default (R-DISC-014/R-DISC ruling,
§2.5).** R-DISC ruled to keep `original` as the default view: the wide alternative
(`original + uncertain`) recovers all 1,264 latch-corpus characters but shows the *entire*
unclosed quote chain in 17.4% of real header shapes, which is unbounded cost. The narrow
default's residual risk is bounded and cheap to close — **provided the closing mechanism gets
built**, which means the floor selector widens the OD-3 floor messages specifically rather than
flipping one global default.

**3. `SpanClass` must stay inside one `Depth` step, never become a second navigation axis
(R-DISC-014, MEDIUM).** `SpanClass` has five members and `view()` takes an arbitrary class set,
so exposing "widen by span class" as an affordance independent of `Depth` would be exactly the
second navigational level `CONTEXT_DISCLOSURE_OPTIONS.md` T-CD1 rejected on cited evidence. The
composition that avoids it: `Depth.BODY_CLEAN` maps to `view()` (original only) and
`Depth.BODY_FULL` maps to every class — one axis, not two.

**And the framing that must travel with them (R-ARCH-029).** The recovery guarantee is
`view(list(SpanClass))`, which returns the text exactly. It is **not** "one class wider": all
fourteen of round 8's misclassified entries are still incomplete one class wider, measured in
`tests/test_a7_default_view_quality.py::test_one_class_wider_does_not_recover_the_misclassified_entries`.
What downgrades content loss from a blocker is containment — the text is present and
addressable — not that one widening retrieves it.

**Coverage assertion.** The `Rubric criteria` column, unioned, is exactly the 113 IDs of RR's status
summary. A criterion appearing in two rows is advanced by both and passed by neither alone.

---

## 2. Dependency order and critical path

Rounds are AL §5 rounds, not weeks. Within a round the listed workstreams proceed in parallel.

| Round | Workstreams | Notes |
|---|---|---|
| **R0** | WS-00, WS-19 | Scaffold and loop machinery. Nothing else can be reviewed until the CI gates and the ledger exist. |
| **R0-PF** | Credential-free preflights **PF-4, PF-4b, PF-5, PF-6**; harness skeleton of WS-16 | PF-4/PF-4b set the semantic caps and arm stack reversals R1/R2; PF-6 sets **both** disclosure ceilings and is blocking for WS-11. |
| **R1** | WS-01, WS-03, WS-07 | Envelope and content processing are the two widest dependencies; both are fully buildable offline. |
| **R2** | WS-02, WS-13, WS-14 | Transport, traces and the untrusted envelope. WS-13 must land before real-mailbox work starts (PF-8 is a precondition, not a follow-up). |
| **R3** | WS-04, WS-05, WS-06, WS-08 | The four retrieval substrates. WS-08 needs WS-07 for pool text; WS-06 needs WS-05 for maps. |
| **R4** | WS-09, WS-10, WS-11 | Ranking, the ladder and disclosure close on the substrates. WS-10 is the critical-path node: it depends on all four of R3. |
| **R5** | WS-15, WS-12 | MCP surface over the finished ladder; freshness rung over the finished watermark and handles. |
| **G0** | WS-16 full corpus + baselines; remaining preflights; pre-registration (§4) | The substrate gate. No capability gate may run before it closes. |
| **R6+** | Capability gates CG-EP, CG-PD, CG-AD, CG-SEM, CG-STR, CG-RANK, CG-FRESH, CG-REG, CG-REAL; WS-17, WS-18 | All mandatory, workable in any order the loop finds convenient (EP §13.4). |

**Critical path:** WS-00 → WS-03 → WS-05 → WS-10 → WS-15 → G0 → CG-EP/CG-PD → release gate.
PF-6 is on it (it sets the ceilings WS-11 allocates against) and PF-2 is on it for WS-05/WS-08.

### 2.1 Buildable immediately — no Gmail credentials required

WS-00, WS-03, WS-07, WS-14, WS-19 in full; WS-01 except the interactive consent step; WS-02, WS-04,
WS-05, WS-06, WS-08, WS-09, WS-10, WS-11, WS-13, WS-15 against a fake Gmail transport plus recorded
and hand-built payload fixtures; WS-16's harness skeleton, extraction adapter, counting proxy and
Baseline B/C/D/F implementations; WS-17's fixture machinery. Preflights **PF-4, PF-4b, PF-5, PF-6**
need only the dev laptop, a network path to the model host at setup time, and an MCP client.
**Work starts here, now.**

### 2.2 BLOCKED ON CREDENTIALS (real Gmail)

| Blocked | Needs |
|---|---|
| WS-01 first-run consent; profile derivation against a live account; PF-8 on the personal profile | Read OAuth client + personal-mailbox consent |
| Live smoke and E2E for WS-02, WS-05, WS-06, WS-12; PF-1, PF-2, PF-3, PF-9, PF-13, PF-14, PF-15, PF-16 | Read client, plus the seed account for the seeded probes |
| WS-16 seeding, corpus regeneration, all Tier-2 numbers; PF-11's Baseline E runs; S1–S14 | Harness OAuth client + dedicated seed Gmail account |
| PF-10 and every freshness arm (H0–H5, H5-LRoff, later H6) | Seed account **and** a second unrelated sending account |
| All of GMAIL-01..07, E2E-01..04, FRESH-01..06 reaching `PASS` | The above, end to end |

Until credentials exist these are `NOT TESTED`, which blocks release exactly like `FAIL` (AL §6).
They are not deferred and not descoped; they are queued behind §5.

---

## 3. Loop-0 preflight

PF-1, PF-2 and PF-6 are blocking. PF-13 and PF-15 are gate-blocking at G0. AD §F holds the full
statement of each check; this table is the work order.

| PF | Measures | Design commitment validated | If it fails |
|---|---|---|---|
| **PF-1** | `threads.get(format=full)` message count vs the seeded manifest at depths 5/12/40/100 | Baseline B is a lossless ceiling; PART-01's manifest equality | Baseline B is labelled **lossy** in every table, comparisons re-interpreted, PART-01 unachievable as written ⇒ escalate (AD §H-2) |
| **PF-2** | Whether `threads.get(format=metadata)` returns the reply headers, `snippet` and `internalDate` | Pool text and the reply-chain floor's data source | (a) missing ⇒ floor needs `format=full` (bytes/latency, not quota). (b) missing ⇒ `threads.get(format=full)` at the same 40 u, pool text = subject+participants+body-head-400, `max_pool_threads` 25→15 declared per T-RO1; if `full` also truncates, `messages.get(format=metadata)` bounded to 60 rows; if neither, escalate |
| **PF-3** | Real quota unit costs and the per-minute ceiling, by driving to 429 | The 5/20/40/2 rate table, every cap derived from it, the governor's bucket | A ~4× tighter reality ⇒ `max_hit_threads` 12→6, `max_source_threads` 4→2, `max_pool_threads` 25→12, `max_quota_units` halved, reduced bounds declared, governor re-set; the calibration date rides every published quota number |
| **PF-4** | Cold load, per-text embed latency, 100/200/400-text wall clock, 25-pair rerank, RSS on the dev laptop | `max_semantic_ms`, `max_pool_messages`, `max_rerank_pairs`, `max_model_rss_mb`, the default model | A stage-A quality miss fires **R1** as a *design* change: widen shortlist → shrink pool → bi-encoder stage A, each measured before the next |
| **PF-4b** | The Node arm on the same pool, texts and hardware | That stack reversal **R2 can fire at all** | Node materially faster at equal quality ⇒ R2 fires and the stack decision reopens as a finding |
| **PF-5** | (a) token-free model download + licence + SHA-256; (b) full suite cold-started with the model host blocked; (c) content pipeline with sockets disabled | The two-host runtime egress allowlist; `HF_HUB_OFFLINE`/`local_files_only`; INJ-04's zero-network condition | A gated default ⇒ swap the default model. Any runtime egress to the model host ⇒ D.8 is not implemented. A parser fetching a remote entity ⇒ INJ-04 fails |
| **PF-6** | The host output cap on the target clients and the `_meta` raise | **Both** self-truncation ceilings (9,000 normal, 12,000 floor-membership overflow) | A lower real cap ⇒ lower both and re-tune the budget ladder **before** any disclosure measurement. If the cap cannot hold the overflow, A.9a step 7 is the only path and AD §H-9 is live |
| **PF-7** | A real MCP client driving search → map → get_messages | `structuredContent`/text parity; zero host-side truncation | A Python-specific host incompatibility fires stack reversal **R3** |
| **PF-8** | Sentinels in query text and bodies vs traces, logs and forced exception paths; profile fail-closed | `Redacted[str]` as a type-level property; SEC-06 | Any leak ⇒ the mechanism is wrong and is fixed **before** real-mailbox development starts |
| **PF-9** | A two-constraint query whose constraints live in different messages of one thread | L1b decomposition as a first-class rung | `q` thread-wide ⇒ L1b is unnecessary and its budget returns to other rungs |
| **PF-10** | Arrival → first-surfacing per arm, stratified at thread depth 0/5/25 | The freshness protocol and OD-1's service level | Any of MF1–MF6 firing makes FRESH-02 mandatory inside the loop |
| **PF-11** | Baseline E built with honest primitives, run as E-matched and E-generous **before** MailWeave is measured | The project's central falsifier | If E cannot be built honestly, no comparative claim may be made at all |
| **PF-12** | The harness client's 7-day Testing expiry; that the seed-only allowlist blocks personal consent at Google's side; re-consent duration | The Google-side control behind profile condition (ii) | Blocking friction ⇒ harness moves to Production-unverified with the `getProfile` assertion as sole control (T-SN4 reversal) |
| **PF-13** | `answer_type_presence` base rate per interrogative class against **quote-stripped** bodies; `exact_signal_match` per-family firing rate | That both predicates are signals rather than constants | A base rate near 1 makes the predicate inert as a downgrade; only its under-trigger rate matters and AD §E.2's removal gate is live |
| **PF-14** | Gmail's `after:`/`before:` boundary zone and inclusivity, seeded at 23:30 and 00:30 local | A.6a's `date_margin_days` widening | Deterministic ⇒ margin drops 1→0, recorded. Non-deterministic ⇒ ±1d stays and is documented as an instrument limitation |
| **PF-15** | Mutate-then-redeem executed cache-cold **and** cache-warm | That handle staleness is a verification, not a tautology | A warm-path pass a mutation cannot break means the check is a tautology and A.10 step 2 is wrong |
| **PF-16** | The suite's own per-run quota budget, an exclusive window for PF-3, and a pre-run in-flight check | That PF-3's calibration is not contaminated | Contention makes limits look tighter than they are, propagating into every published cost number |

---

## 4. G0 pre-registration

**When.** At the substrate gate, after the reference distributions of EP §13.3 are measured on a
HOLDOUT seed and before **any** capability gate runs and before any implementation is reviewed
against a bar. A criterion reviewed against an unregistered UNSET number is itself a BLOCKER (RR
"How to use this document").

**What is registered.** For each bar: the value expressed as a delta or bound **against a named
reference distribution**, its rationale, the arm it binds on, and the timestamp — written into
`experiments/experiment_log_001.md`.

**Who freezes it.** The owner (values that are product promises) or synthesis (values that are
deltas against a measured distribution), recorded in log 001 and frozen at that point. Amendment
requires a logged amendment retaining the original and re-running the affected gate; amendment
*after seeing the result it would change* escalates to the human (AL §8, EP §13.2 step 4).

**Already registered, not open (OD-1, binding).** Freshness service level: **p90 ≤ 60 s from
H0/history-confirmed arrival, evaluated independently at thread depths 0, 5 and 25; pooling across
depths prohibited.** Second, independent trigger: **any confirmed real-mail false negative** — the
message is present and should match and MailWeave does not surface it — **is a defect regardless of
percentile** and forces the mitigation build. FRESH-05 checks the entry's timestamp, not its value.

**Also already binding, not to be re-derived at G0:** the inherited CG-EP / CG-PD / CG-AD bars, and
every `[DEFINITIONAL]` bar (zero non-Google egress, P2/P3 = 1.00, P6 provenance labelling, P7 = 1.00,
no unexplained `not_found`, cheap-path exclusion of the reranker, no fixture closed without a green
regression test).

**Currently UNSET — each needs a number at G0 or its gate is blocked:**

| Bar | Reference distribution it is expressed against | Gate it blocks |
|---|---|---|
| `semantic_gain` on F4-T2, F4-T3, F11 | SEM-OFF ablation | CG-SEM |
| `backend_parity` tolerance | local vs hosted arm on the same families | CG-SEM |
| F12 over-escalation ceiling | query-shape-only vs composite trigger ablation | CG-AD, CG-SEM |
| Escalated-path p95 latency | G0 escalated-arm latency distribution | CG-SEM |
| F13 / F14 / F15 accuracy | G0 structural-family baseline | CG-STR |
| `cut_loss` reduction on F16 | no-reranker arm | CG-RANK |
| Budget levels for the budget–recall curve | Baseline F(±1/±2/±5) and Baseline C curves | CG-PD, CG-STR |
| AD-04's cost bar on `api_calls` | G0-measured Baseline D `api_calls` on F1/F2 | CG-AD |
| Incomplete-diagnosis rate ceiling (ROUTE-04, OD-2) | G0 relaxation-probe distribution on multi-constraint families | CG-AD |
| RANK-04 body-depth disclosure cap | G0 disclosure-depth distribution | CG-RANK, CG-PD |
| Stage-A `recall@shortlist` (fires R1) | PF-4 shortlist recall on the seeded pool | CG-SEM, stack decision |
| D2 MIME-signature frequency floor | D2 census on the real mailbox | CG-REAL |

---

## 5. Owner checklist

Ordered. Each step is a thing only Nayan can do, with what it unblocks. Steps 1–8 are the whole of
§2.2's blockage.

1. **Create two Google Cloud projects** — one for the read server, one for the harness/seeder. Keep
   them separate; the separation is the control, not a tidiness preference (AD §B.9).
   *Blocks:* every credentialed step below, i.e. all of §2.2.
2. **Enable the Gmail API** in both projects.
   *Blocks:* any OAuth client creation.
3. **Create the read-only server OAuth client** in the read project: type **Desktop app**
   (installed-app loopback, PKCE), scope **exactly** `https://www.googleapis.com/auth/gmail.readonly`
   and nothing else.
   *Blocks:* WS-01 first-run consent, PF-2, PF-3, PF-8 on the personal profile, all GMAIL-* criteria.
4. **Create the separate seeder OAuth client** in the harness project: type Desktop app, scope
   `https://mail.google.com/` (full — `insert`/`import` need it).
   *Blocks:* the seeder, the corpus, every Tier-2 number, PF-11, PF-13, S1–S14.
5. **Set publishing status. Concrete recommendation, and it differs per project.**
   - **Read project → "In production", not submitted for verification.** SN §2.2 verifies that
     Testing status expires refresh tokens **7 days from consent**; SC §13 puts this client on the
     hot path daily, so a Friday token death is unacceptable. Cost: the unverified-app warning
     (click through via Advanced) and a 100-new-user lifetime cap — irrelevant at this scale.
   - **Harness project → keep in "Testing", with the test-user allowlist containing only the seed
     account.** This makes personal-mailbox consent to the write-scoped client impossible **at
     Google's side**, which is the hard control AD §A.4 condition (ii) depends on. Accept the 7-day
     re-consent; corpus regeneration is a gate-time activity, and `harness auth --refresh` is one
     command. PF-12 confirms both halves; if re-consent proves blocking, T-SN4's reversal moves the
     harness to Production-unverified with the `getProfile` assertion as the sole control — record
     that as your decision, not an agent's.
   *Blocks:* PF-12; and, if left in Testing, the read client will die weekly mid-round.
6. **Create the dedicated seed Gmail account** — new, permanent, used for nothing else, never your
   personal mailbox. Then **create or nominate a second, unrelated sending account** for freshness
   delivery probes (the primary arm sends from a different account; `insert` bypasses delivery and
   cannot measure freshness).
   *Blocks:* seeding, S12's delivered-reply-into-a-deep-thread assertion, PF-10, and every freshness
   arm.
7. **Add the seed account as the sole test user** on the harness client's consent screen.
   *Blocks:* step 5's Google-side control and PF-12.
8. **Run first-run consent, twice.** `mailweave auth` against the read client on your personal
   mailbox, and `harness auth` against the harness client on the seed account. Record the seed
   account's digest into `seed_account_hash`; the salt is generated on first run and lives in the
   token store.
   *Blocks:* profile derivation, PF-8's live canary, and the first real-mailbox round.
9. **Confirm OD-1's freshness values are in `experiments/experiment_log_001.md` before PF-10 starts.**
   The values are decided; the pre-registration is a timestamp check (FRESH-05).
   *Blocks:* the freshness probe run.
10. **Reserve an exclusive window for PF-3.** It drives the project to 429 by design; nothing else
    may run against that project during it (PF-16).
    *Blocks:* trustworthy quota calibration, and therefore every published cost number.
11. **Standing, per incident: OD-4 approvals.** Metadata/ID/timing/structure diagnostics need no
    approval. Persisting or surfacing actual personal-mail text for forensic debugging needs your
    explicit approval, per incident. `mailweave inspect` is memory-and-terminal only and exists
    before the first real-mailbox round precisely so this rule is cheap to obey.

---

## 6. Round cadence

**Work orders map one-to-one onto workstream slices.** The orchestrator issues a work order naming
the workstream, the rubric criteria that slice is meant to move, the reviewers required, and the open
findings assigned to the round (AL §5 step 1). An implementer agent takes it in an isolated worktree,
writes code and tests, runs the full local suite, and hands back a `HANDOFF.md` whose explicit
"not done / not verified" section is part of the deliverable. The implementer never touches the
rubric, the contract, the ledger's severity fields or a reviewer's report; nothing it claims is a
`PASS` until a reviewer that did not write the code reproduces the evidence (AL §1, §6). A workstream
larger than one round is sliced by dependency, not by criterion — shipping half a ladder is
reviewable; shipping half a criterion is not.

**Findings drive the next round.** Reviewers run in parallel as fresh instances against the branch
(AL §5 step 4); the orchestrator consolidates into `docs/reviews/ROUND_N/CONSOLIDATED.md` and the
ledger. The round closes only on zero open BLOCKER, zero open HIGH, every targeted criterion
reviewer-confirmed `PASS`, and no regression from `PASS` (AL §5 step 6). Otherwise the findings
*become* the next work order, re-reviewed by the domains that raised them plus a regression pass over
the criteria the diff could plausibly touch. Every real failure also produces a Tier-3 fixture before
its finding can close (EP §1.2 step 5b), so the regression suite grows monotonically with the loop.
Deadlocks, unachievable criteria, and any real-Gmail behaviour that contradicts a load-bearing
architecture assumption escalate rather than resolve quietly (AL §8).

---

## 7. Risk register

| Risk | Early-warning signal | Response |
|---|---|---|
| Credentials arrive late and the credential-blocked half of the plan compresses | R3 completes with §2.2's list untouched | Keep building §2.1 and deepen the fake-transport fixtures from the REST schema; do **not** re-scope a criterion to fit; the queue in §2.2 is the escalation artifact |
| PF-2 finds no `snippet` under `format=metadata` and PF-1 finds `format=full` truncates | Either probe returning the bad branch | Take the D.5 ranked fallbacks in order; if neither is available the semantic rung's design escalates to the owner rather than shipping on an uncosted fallback |
| PF-3 shows quota materially tighter than published | 429s far below 6,000 u/min | Halve the derived caps per AD §F, re-set the governor, declare every reduced bound in-band, and stamp the calibration date on every published quota number |
| Stage A cannot place true evidence in the top 25 of ~300 rows | `recall@shortlist` below the G0-registered bar | Fire R1 as a **design** change — widen shortlist, then shrink pool, then bi-encoder stage A — each measured before the next; do not silently raise `k` to pass |
| The token ceiling and the E2 floor collide on real threads | `ceiling.applied = 12000` firing routinely, or `disclosed_token_ceiling` withheld records appearing on ordinary queries | OD-3 pre-authorises branch (i): show fewer matched messages at full text so the chain keeps its depth; branch (ii) only if PF-6 says the client's real cap allows it; (iii) is last resort |
| Baseline E-generous matches MailWeave on answer accuracy | CG-PD's e2e arm showing no accuracy separation | EP §8.7's pre-committed response: the claim narrows to cost, rounds, latency, predictability and explicit partiality, in those words, enforced at the documentation gate. The product still ships |
| A real-mail false negative appears on the owner's mailbox | Any D6 / O7 instance the owner confirms | OD-1's second trigger fires regardless of percentile: build and verify the FRESH-02 mitigation against arm H6 by removing the specific trigger, without regressing cheap-path bars |
| Criteria accumulate as `NOT TESTED` and the gate is approached by attrition | The RR status table static across two consecutive rounds in any area | `NOT TESTED` blocks release exactly like `FAIL`; the orchestrator schedules the untested area as the next work order and the adversarial reviewer is briefed on it specifically |
