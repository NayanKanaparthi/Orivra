# ARCHITECTURE_DECISION.md — The Smallest Coherent Architecture for MailWeave

**Date:** 2026-08-30
**Author:** Architecture synthesis agent
**Inputs:** MAILWEAVE_CONTEXT.md (cited as CTX) and the six research docs, cited as A (VERIFIED_RESEARCH), B (RETRIEVAL_OPTIONS), C (ROUTING_OPTIONS), D (CONTEXT_DISCLOSURE_OPTIONS), E (EVALUATION_PLAN), F (SECURITY_NOTES).
**Question answered (CTX §51):** *What is the smallest coherent architecture that can test the central MailWeave hypothesis without boxing us into a bad design?*
**Hypothesis under test (CTX §66):** adaptive query-conditioned evidence selection + progressive context disclosure can preserve or improve evidence recall while reducing irrelevant context, versus fixed-K previews and full-thread dumps.

Every decision below states **what was chosen, why, and what evidence would reverse it.** Numbers are cited from the research docs; pre-registered thresholds are decisions (frozen in experiment log 001 per E §8.1), not measurements.

---

## 0. The architecture in one paragraph

A **stateless, read-only, TypeScript MCP server** ("A+map", B §5) exposing **four tools** over stdio: message-level Gmail search with a deterministic in-server relaxation ladder (`search_mail`), a complete thread skeleton (`thread_map`), explicit-depth message fetch (`get_messages`), and attachment stubs (`get_attachment`). Every response is a **map-carrier** (D §5 P2): hits can never silently vanish because every message in a touched thread appears at least as a stub row, and partiality/trust metadata is structural, not optional. Disclosure is **one level deep plus a direct-fetch escape hatch** — no multi-level ladder (A §8.1). Routing is **zero-LLM deterministic** (C §7): cheap rungs in the server, expensive escalation owned by the client agent via typed affordances. The server persists nothing but OAuth tokens (F §4.1). It is measured, from day one, against a **seeded real-Gmail test account** (E §1) with five baselines — including the one that could kill the thesis: a strong agent with honest primitive tools (E §4.5, A §12.1).

```text
agent (client LLM) ⇄ MCP stdio ⇄ MailWeave server (TS, stateless, gmail.readonly)
                                     │ Tier-1 parse → L0–L3 ladder → map-carrier response
                                     ▼
                              Gmail REST (messages.list / messages.get / threads.get)
harness (Python, separate OAuth client, mail.google.com, seed account only)
   seeder → settle gate → Tier-1 scripted driver / Tier-2 pinned agent → JSONL traces → analysis
```

### Decision register (details and reversal criteria in the cited sections)

| # | Decision | Where |
|---|---|---|
| D1 | Retrieval core = stateless Option A + thread-map slice of D; no index, no vector store | §1.1 |
| D2 | Four committed tools: `search_mail`, `thread_map`, `get_messages`, `get_attachment` | §1.2 |
| D3 | Response shape = P2 map-carrier + partiality metadata + RetrievalReport + trust envelope | §1.3 |
| D4 | Routing v1 = zero-LLM deterministic L0–L3 ladder with code-enforced budget caps; client owns expensive escalation | §1.4 |
| D5 | Stack: TypeScript server / Python harness; MCP stdio + JSONL traces as the seam | §1.5 |
| D6 | OAuth: `gmail.readonly` server; separate full-scope seeder client, pinned to the seed account; production-unverified posture | §1.6 |
| D7 | Eval: seeded real-Gmail account, baselines A–E, two tiers, E §8.2 bars adopted with amendments | §1.7, §9 |
| D8 | Seeding via `insert` + explicit `internalDateSource=dateHeader`, with a pre-registered flip rule to `import` | §2a |
| D9 | Disclosure = one level + direct-fetch escape hatch; Baseline E gate-binding; no multi-level ladder | §2b |
| D10 | Ground truth = seed manifest IDs; REST `threads.get` validated, hosted `get_thread` never an oracle | §2c |
| D11 | Quotas: plan on today's conservative table; Loop 0 empirical probe discriminates | §2d |
| D12 | Deployment: local-first stdio process, MCP spec 2026-07-28-native, BYO Google Cloud project | §1.5, §1.6 |

---

## 1. Chosen now (required to prove the thesis)

### 1.1 Retrieval core: Option A + the thread-map slice of Option D

**Chosen:** stateless direct Gmail; `messages.list(q)` message-level search as the only retrieval engine; batched `messages.get` (metadata for candidates, full for disclosed evidence, ≤50/batch per B F5); `threads.get(format=metadata, metadataHeaders=[From,To,Cc,Subject,Date,Message-ID,In-Reply-To,References])` as the thread-map primitive. No index, no vector store, no sync machinery. Gmail is the sole source of truth.
**Why:** message-level search preserves hit identity by construction — the #296 bug class is structurally impossible when message IDs flow from search into representation (B F1, B §2-A). Statelessness eliminates the stale-index paradox (CTX §45) and gives the strongest privacy posture (F §4.1). Every heavier option (B/C/E/F variants) fronts complexity before any benchmark shows Gmail primitives failing, violating CTX §55.
**Reverse if:** Loop 4/5/6 gates measure the specific failures that activate the deferred options (§3, §4 below). Nothing short of a measured failure reverses this.

**Known cost accepted:** API `q` is message-scoped, not thread-wide (B F2) — multi-constraint queries can under-recall vs the Gmail UI. Mitigation is designed in (query decomposition + threadId intersection at 5 quota units per extra list, B F2) and benchmarked (F7 family); it lives in the server ladder (C open Q4 resolved: deterministic tier, not an escalation).

**In-process cache (B open Q3 resolved):** a per-process TTL cache keyed by message ID with `fetchedAt` stamps is permitted; nothing at rest, nothing served without its freshness stamp. The cache/index line: anything persisted to disk, or served without a stamp, is an index and is not in v1.

**Gmail client (B open Q1 resolved):** wrap `googleapis` (typed payloads out of the box — the MIME-parsing risk lives exactly there, B §4.3); hand-roll the `/batch` endpoint if the lib's modern auth path lacks it (B §4.3 caveat). **Reverse if:** Loop 0 shows the lib obstructs batching/auth — then a thin fetch-based client over the ~5 REST endpoints, keeping discovery-derived types.

### 1.2 Tool surface: four tools, committed names

Namespaced `mailweave_*`; descriptions are compile-time constants (F §6.3.4); annotations truthful (`readOnlyHint: true`).

| Tool | One-line contract |
|---|---|
| `search_mail(query, opts?)` | Tier-1 deterministic parse → L0–L3 ladder in one call; returns evidence (hits at `body_clean`, each with role + mechanical reason), a full map of the focal thread + mini-maps (total, hit positions, map affordance) for other touched threads, and a `RetrievalReport`; **cannot return a bare empty result**. `opts` includes `allow_relaxation` (default true; every relaxation disclosed — C open Q1 resolved). |
| `thread_map(thread_id)` | Complete skeleton: every message as a row (pos, id, from, date, reply-parent, flags, snippet, role), segment grouping, exact total, freshness stamp. Run-collapsing per D §4.4 above 150 rows, always with an expand affordance. |
| `get_messages(ids[] \| {thread_id, rows\|all}, view)` | Bodies at explicit depth `stub\|snippet\|body_clean\|body_full\|raw`; the escape hatch — any content is one call away from any map. Recursive partiality markers per D §5.4.3 (`quoted_removed_chars`, in-text truncation markers + `body_full` path). |
| `get_attachment(message_id, part_id, mode)` | v1 implements `mode=metadata` only (filename/mimeType/size as fenced untrusted text); `extract_text` is deferred (§3) and `save`/bytes never inline. |

**Why:** D §7's T2 verdict (primitives with a `view` depth preset beat both the mega-tool T1 and the level-knob T3), C §7's consolidation of the ladder inside one search tool, and Anthropic's tool guidance (D §1.3). `search_mail` embeds enough that easy queries finish in one call, preserving T1 ergonomics inside a T2 surface (D §7).
**Reverse if:** Loop 2's calls-to-answer metric shows agents failing to follow result-embedded affordances (D's judgment claim, explicitly untested — D §11), in which case fold `thread_map` into `search_mail` responses harder and/or add a single `get_thread_full` convenience.

### 1.3 Response shape: map-carrier + partiality metadata + RetrievalReport + trust envelope

**Chosen:** D's Shape **P2** as the response spine, with F §6.3's trust envelope and C §5.3's `RetrievalReport`, serialized as `structuredContent` with a mirrored text block (D open Q9 resolved: both, per spec back-compat).

Committed principles:
1. **Map-carrier:** every touched thread's messages appear at least as stub rows; `complete: true` only from an actual full skeleton fetch.
2. **Partiality metadata** satisfies E §3.2's P1–P5 mechanical assertions by construction: stated total, included set, machine-actionable more-affordance, role tag on every message (`matched | context | parent | child | requested | stub | derived`), no silent derivation. No bare counts — every count sits next to a concrete call (D §5.4.1).
3. **RetrievalReport** on weak/empty outcomes: queries executed, constraints dropped and why, hit counts per rung, what was *not* tried, affordances that would try it (C §5.3). The response schema has no representation for a bare "not found."
4. **Trust envelope:** email-derived text only in dedicated leaf fields, wrapped in per-response nonce fences; per-item `{source: "gmail", trust: "untrusted", role, role_reason}`; from/to as `{display_name, address}` pairs; `Authentication-Results` surfaced as receiver-recorded; no mail-derived string ever in tool metadata or error strings (F §6.3, §7.2).
5. **Self-truncation:** L1 response target ≤ ~4,000 tokens, hard ceiling ~9,000 with explicit in-band markers (D §6.3) — MailWeave truncates itself explicitly before Claude Code's 25k host cap does it silently (D §1.3).
6. **Freshness stamp** (`fetchedAt`) on every map and body (D §5.4.4).
7. **Honest provenance only:** mechanical reasons ("gmail q matched", "parent of hit"), never fabricated scores (CTX §20).

**Why:** P2 makes the Evidence Preservation and Partiality invariants structural (D §5 P2 pros); the envelope is the injection defense MCP itself does not provide (F §5).
**Reverse if:** Loop 2 shows map overhead dominating token budgets on multi-thread results beyond the D §4.4 compression ladder's ability to contain — then P1 coverage-headers for non-focal threads (mini-maps are already this concession; the invariant-minimum mini-map = total + hit positions + affordance, D open Q2 resolved).

### 1.4 Routing: zero-LLM deterministic ladder, client-driven escalation

**Chosen:** C §7's hybrid, verbatim: Tier-1 deterministic parser (operators table, C §1.1) with graded `ParsedQuery` confidence; heuristic first-rung pick (C §2-A, ~50 lines); in-server micro-ladder **L0–L3** (exact → filtered → relax one constraint at a time → broaden) with budget caps enforced in code and **reported when hit**: ≤3 list-rounds beyond L0/L1, ≈25 Gmail calls, ≈2 s server-side p95, **zero LLM calls, zero embeddings, zero sampling** (C §5.2). Sufficiency signals are counts/coverage only (C §5.1). L4+ (expansion, segments, related threads, semantic) is client-invoked via affordances. Seam (C open Q2, D open Q1 resolved): **server adapts retrieval; agent drives disclosure.**
**Why:** the client LLM is the best query-understander and is already paid for (C §3); MCP sampling is deprecated so there is no free server-side intelligence (C §4.1b, A §7.2); RAGRouter-Bench shows cheap lexical routing captures most of the win (A §8.2); the ladder guarantees the floor — one tool call never yields a bare false "not found" (C §3 hybrid). Security independently favors zero internal LLM in v1 (F open Q4).
**Reverse if:** Loop 3 gate fails its recovery bar (≥80% of initially-missed cases recovered by fallback, E §8.2) with traces showing misparse-class failures a Tier-2 classifier would fix — then C §2-B's small-model classifier, trained on the traces Decision 9 (CTX §31) requires first.

### 1.5 Stack: TypeScript server, Python harness, JSONL seam

**Chosen (user-delegated, decided now):**
- **Server: TypeScript** on Node LTS, `@modelcontextprotocol/server` v2 targeting spec 2026-07-28 (stateless, server-minted handles as ordinary tool args — A §7.1), stdio transport primary (F §10 P1). `googleapis` for typed Gmail payloads; `crisp-oss/email-reply-parser` (Node, ~10 locales, verified in production use — D §6.2) for quote-stripping; a permissively-licensed Node HTML→text lib (license check is a Loop 0 item; GPLv3 `html2text` avoided per D §6.2).
- **Eval harness, seeder, and analysis: Python** 3.12+, `mcp` SDK v2 as the scripted driver client; `email.message.EmailMessage` for RFC 2822 corpus generation (the reference implementation Google's own sending guide names — E §1.2.4); pandas/scipy for stats (Wilson CIs, McNemar, bootstrap — E §8.1).
- **The seam:** MCP stdio between harness and server; **per-query JSONL traces on disk** (schema = C §6 ∪ E §3.3) so analysis is language-independent — exactly B §4.4's decoupling argument.

**Why (B §4.6):** typed payload access where the MIME-parsing risk lives; TS MCP SDK v2 shipped stable first with clean stdio middleware; `npx` distribution ergonomics; and the harness-language argument for Python is fully satisfied *without* constraining the server, because the driver speaks MCP and the traces are JSONL. Python keeps its real strengths (corpus generation, stats, and the sentence-transformers/Chroma path if Loop 4 ever activates) on the harness side where they belong.
**Reverse if:** (a) Loop 4's entry condition fires and a spike shows Node's local-embedding path (transformers.js/ONNX) inadequate — then the semantic worker becomes a Python sidecar process first; full server rewrite only if (b) the TS SDK v2 shows blocking defects in Loop 0–1 (it currently throttles new-contributor PRs "while v2 settles" — B §4.2, a churn signal to watch, not a blocker).

**Deployment model (decided with the stack):** local-first stdio subprocess, spec-2026-07-28-native (stateless; cross-call referents like `map_id` are server-minted handles passed as ordinary tool args — A §7.1 — with stateless re-derivation via a repeat `threads.get` when the in-process cache lacks them, D open Q3 resolved). No listening TCP socket in default config (F §10 P1); no hosted deployment in v1.
**Reverse if:** a demo host that matters cannot spawn stdio servers — then Streamable HTTP bound to loopback with an auth token (F §5), nothing else changes.

### 1.6 OAuth and security posture

**Chosen:** F's two-zone architecture verbatim (F §0, §1.5, §2):
- **Server (Zone A):** exactly one scope, `gmail.readonly` — the minimal viable read scope, since `gmail.metadata` can neither use `q` nor read bodies (F §1.2, B F8). No write tools exist in the tool list; the lethal-trifecta action leg is removed inside the connector (F §6.1, §8).
- **Seeder/harness (Zone B):** separate OAuth client in a separate GCP project, `https://mail.google.com/` (required for deterministic `batchDelete` teardown — F §1.4; E open Q1 for Agent F resolved in favor of full scope on the disposable account), mechanically pinned: hard-abort unless `getProfile().emailAddress` equals the seed account (F §2.5).
- **Both projects: In production, unverified** (personal-use path) to escape the verified 7-day Testing-status refresh-token expiry (F §2.2). Loopback + PKCE(S256), OS keyring or 0600/0700 token files, `.gitignore` + secret scanning before first commit (F §3.3 — the gitignore is currently absent).
- **Trace redaction is account-keyed, not config-keyed:** seed-account runs log full content; any unrecognized account gets the IDs-and-metrics-only profile with the sentinel canary test (F §4.3, §10 T3). No telemetry. Distribution is BYO-Google-Cloud-project, no shared client ID (F §2.4).
- **Injection fixtures ship in the eval corpus** (body/subject/display-name/filename/hidden-HTML payloads) with F §10 I1–I3 assertions as gate items.

**Why:** every element is verified against primary sources in F; the read-only single scope is also what makes the anti-gaming story clean (E §1.2.9 scope matrix).
**Reverse if:** the production-unverified console flow proves unavailable for restricted scopes (F could-not-verify #2 — Loop 0 item P7): fall back to Testing status + scripted weekly re-auth with automated `invalid_grant` detection (E §1.2.9), and accept the cadence cost.

### 1.7 Evaluation: seeded real-Gmail substrate, five baselines, two tiers

**Chosen:** E's design adopted wholesale — real Gmail test account seeded with deterministic synthetic corpora (E §1); families F1–F10 with the position-sweep adversary at {2,7,20,37,51,83,99}/100 (E §2.4); Tier-1 scripted ground-truth-blind driver + Tier-2 pinned agent (E §6); anti-gaming G1–G8 (E §5); baselines A (hosted-MCP reproduction, with the A′ honesty-labeled fallback), B (full dump — the recall ceiling MailWeave must match at a fraction of the tokens; now also the vendor's own institutionalized workaround, A §3.4/§11.2), C (fixed-K variants), D (plain message-level search — the latency yardstick), and **E (strong agent + honest primitive tools — the thesis-killing competitor, §2b below)**.
**Exit criteria:** E §8.2's bars are **adopted** with the amendments in §9 of this document, frozen in experiment log 001 before Loop 0 closes.
**Why:** seeding real Gmail keeps ground truth fully known while every measurement traverses the real API path (E §1.1) — the only design that satisfies both the no-mock constraint and manifest-scored recall; the anti-gaming structure (G1–G8) is what makes a self-built benchmark credible.
**Reverse if:** S1–S10 smoke tests invalidate the substrate (E §1.3 declares this a loud, work-stopping blocker — escalate to synthesis, do not quietly work around); specifically S6's thread-ceiling fallback (N=90, fractions normative) and S2's subject policy are pre-authorized substrate adjustments, not reversals.

### 1.8 Instrumentation from day one

**Chosen:** content-free-by-default JSONL trace per top-level query (C §6 schema: query features, routing rungs, constraints dropped, per-rung hit counts, budget caps hit, cost) joined to E §3.3's harness-measured fields; headline metrics only from harness-measured + manifest-scored fields (E G8); network-level API counting via a CONNECT/SNI counting proxy by default, full TLS interception only if per-endpoint attribution becomes necessary (E open Q6 resolved); self-reported counters cross-checked, never headline.
**Why:** the traces are what make every §3/§4 deferral decidable later (B §5.6) and are the raw material for any future learned router (CTX §15, Decision 9).

---

## 2. Cross-doc tensions, resolved

### 2a. Seeding: `insert` vs `import`

**Tension:** E §1.2.1 decides `insert` (+ explicit `internalDateSource=dateHeader`, since insert defaults to `receivedTime`); F §1.3 calls `import` "the better seeding primitive" for fixture realism and notes import defaults to `dateHeader`.

**Decision: `insert`, always with explicit `internalDateSource=dateHeader`.**
**Why:** the two primitives are equal on dating once the parameter is explicit — import's friendlier *default* is a footgun avoided, not a capability gained. The difference that matters is import's "standard email delivery scanning and classification" (E §1.2.1): for a ground-truth corpus that is precisely the nondeterminism to avoid — a fixture spam-classified or reclassified breaks manifest scoring silently, the exact class of silent failure this project exists to eliminate. F's realism argument targets the delivery path; but the realism that matters for the *read* path is search-indexing behavior, which is tested directly rather than assumed. Freshness realism is handled separately: Loop 6 uses real delivery, never inserts (E §7).
**Validating smoke test (pre-registered flip rule):** S4 asserts `internalDate` equals the intended epoch ms and `after:`/`before:` bound correctly; **S8 is extended to a twin-corpus probe** — seed ~50 messages via `insert` and ~50 via `import(neverMarkSpam=true)`, compare settle-time distributions and any label/classification divergence. If inserted mail's settle p90 exceeds imported mail's by >5 minutes, or shows search anomalies imported mail lacks, the seeder flips to `import` — a one-flag change; the corpus is byte-identical either way.
**Reverse if:** the S8 flip rule fires.

### 2b. Disclosure depth: arXiv 2607.17598 vs the multi-level design

**Tension:** A §8.1's verified prior art: progressive disclosure gains are "near zero when a strong agent harness already divides and retrieves on its own"; at corpus scale one-level disclosure wins; "a second, deeper routing level never helps and sometimes breaks accuracy outright, so one level is enough." D designs a rich option space (E1–E6 expansions, depth enum, level presets); CTX §10.2 sketches a Level-0→5 ladder.

**Decision: disclosure is exactly one server-shaped level plus a direct-fetch escape hatch.**
- **Level 0 — the `search_mail` response:** evidence bodies (`body_clean`) + complete focal-thread map with stubs. Justification: this level must exist — it is the carrier of the invariants (hits preserved, partiality explicit) and of the thesis's token savings.
- **Escape hatch — `get_messages` at any depth, including whole-thread:** justification: A §8.1's "one level + full-fetch" is precisely what the paper found sufficient; a strong agent aiming at map rows *is* the retrieval the paper says strong harnesses do well. Any message is one call from any map — there is no rung between the map and the bytes.
- **No mandatory intermediate rungs.** The CTX §10.2 L0→L5 ladder is retained as conceptual vocabulary only; T3's `level` parameter is rejected as API (D §7); `view` depth is a per-fetch parameter, not a hierarchy the agent climbs.
- **Expansion policies (E1 window / E2 reply-chain / E4 scored fill) are Loop 2 experiment arms, not architecture.** Arm D-base (hits + ±2 window + map) vs Arm D-var (hits + reply-chain floor + mechanically-scored fill + map) at equal token budget, per D §9. Both arms are single-level. D-base is the presumptive default; D-var ships only if H2 holds (wins split-evidence/interleaved cases at equal budget). If H2 fails, ship the simpler policy (D §9 H3, CTX §55).
- **The falsification arm is committed:** Baseline E — the same pinned agent given honest primitives (`search_messages(q)`, `get_message`, `get_thread`, paginated) at the same round budget — is **gate-binding at Loop 2+ Tier-2 gates**, not merely present. Pre-registered interpretation (margins frozen in log 001): MailWeave must beat Baseline E on at least one of {answer accuracy, median disclosed tokens (≥30% reduction), e2e latency} without losing on the others beyond margins (3 points accuracy, +20% latency). If it cannot, the added-value component of the thesis is falsified and §8's shrink plan executes.

**Reverse if:** Loop 2 traces show agents systematically failing to reach mapped evidence in ≤4 rounds (`recall@≤4rounds` materially below `recall@1round` + map visibility) — evidence that one level is too *shallow* for weak clients — then a single optional server-side bundle-more parameter, never a second mandatory level.

### 2c. `get_thread` as ground truth (issue #239)

**Tension:** every reproduction (including A's live probe) leans on `get_thread` completeness, but claude-ai-mcp #239 reports the *hosted* `get_thread` truncating/malforming on 10+-message threads (A §6.1); A's probe covered only a 7-message thread (A §10.6).

**Decision: the ground-truth anchor is the seed manifest, never any thread fetch.** The manifest's Gmail IDs are captured from `insert` responses at creation time — Gmail's own IDs, issued per message, independent of any read path. All recall scoring joins on manifest IDs (E §2.1 already does this); REST `threads.get` is *validated against* the manifest rather than trusted:
- **Loop 0 assertion (extends S1/S6):** REST `users.threads.get` in both `metadata` and `full` formats returns **exactly the manifest ID set** (set equality, not count equality) at N ∈ {10, 100, 105}.
- **Standing canary:** re-asserted on one long thread at every gate.
- **Hosted `get_thread` (Baseline A) is a measured subject, never an oracle** — E §4.1's protocol already scores its payloads verbatim; the #296 contrast pair (search preview vs get_thread) is recorded, and Loop 0 additionally records hosted-get_thread completeness on the N=100 seeded thread, which directly arbitrates #239 at the depth A's probe could not.
- **Fallback oracle if REST `threads.get` itself proves incomplete at N=100** (would be significant news): paginated `messages.list(labelIds=[mw-run-*])` + per-message `messages.get` as the completeness check, and the REST defect gets reported publicly with the reproduction.

**Reverse if:** nothing reverses manifest-as-truth; it is the only path that does not assume the thing under test.

### 2d. The quota-number discrepancy

**Tension:** B F7 (flagged, two consistent same-day fetches): today's quota page reads `messages.get` 20 u / `threads.get` 40 u / 6,000 u/min/user / 80 M-day billing threshold; widely cited historical values are ~10× looser (5 u / 10 u / 250 u/sec/user / 1 B-day free tier). E §1.2.7 independently fetched the same 6,000 figure. Neither agent could reach a second authoritative source (Cloud Console inaccessible from the research environment).

**Decision: plan against today's (conservative) table; Loop 0 probes empirically before anything depends on the difference.** The discrepancy changes nothing for Loops 1–3 on a seeded mailbox (B F7: interactive paths fit comfortably under either reading) but changes bulk-ingest feasibility for the deferred C/E/F options by ~10× (33 min vs ~3.5 min per 10k messages — B §2-C).
**Loop 0 probe (pre-registered discriminator):** (i) the write side is already covered by S10 (1,000 inserts at 80% of the computed ceiling, log 429 frequency); (ii) **read-side burst probe:** sustain batched `messages.get` at ~400–600 calls/min for 2–3 minutes against the seeded account — today's table predicts throttling at ≈300 gets/min (6,000÷20), the historical table at ≈3,000/min (15,000÷5); the 429 onset rate discriminates cleanly; (iii) read the project's actual quota panel in Cloud Console once the GCP projects exist (the check neither agent could perform). Record all three in experiment log 001; all future bulk-ingest arithmetic uses the measured numbers.
**Reverse if:** n/a — this is an empirical probe by design; the plan is conservative either way.

---

## 3. Deferred intentionally (useful, not required for the thesis)

Each waits for its measured trigger; none blocks the hypothesis test.

| Deferral | Trigger to build | Source |
|---|---|---|
| **Attachment text extraction** (`extract_text` mode, sandboxed per F §7.3 tier 2) | F8 family failures that metadata + carrying-message disclosure cannot pass | F open Q8, E §2.3 |
| **Derived summaries** (segment/thread level, `derived: true`, faithfulness-evaluated) | Very large threads where even segment maps overflow budgets; Loop 5+ with its own eval | D §4.5 |
| **Multi-thread auto-expansion** (E5 beyond stubs+affordances) | F7 family failures under affordance-only cross-thread disclosure | D §3-E5 |
| **P3 resource-link overlay** for bulky artifacts (raw MIME, attachment bytes) | A host matrix showing reliable resource support; always with in-band tool fallbacks | D §5-P3 |
| **Elicitation-based disambiguation** ("three Sarahs — which?") | Client-support check passes; ambiguity-map failures observed | C §4.1d |
| **Caller-supplied budget caps as API surface** | Demand from real hosts | C open Q7 |
| **Contacts/frequent-correspondents resolver cache** (v1 uses probe queries) | Name-resolution failures in traces | C open Q4 |
| **Workspace-internal OAuth option** (escapes consumer-account constraints entirely) | Production-unverified posture fails (Loop 0 P7) or an org owner materializes | F §2.2, E §9 Q2 |
| **Second standby seed account, non-English T3 cases** | Operational need; T3 stays non-gate-binding | E §1.8, §2.5 |

---

## 4. Experimental branch (build only if baseline results show need)

Entry conditions are pre-registered; a negative result is logged as a first-class outcome (E G7).

| Branch | Entry condition (gate-measured) | Shape when built | Source |
|---|---|---|---|
| **On-demand semantic retrieval** | Loop 4 entry: lexical-only recall < 0.70 on F4-T2 at a HOLDOUT gate | Option **B** (ephemeral query-time pool embedding, provenance-labeled, local model default) — never a persistent index first | B §2-B, E §8.2, F §4.2 |
| **Query-aware / reply-chain expansion as default policy** | Loop 2 H2 (D-var wins split-evidence at equal budget) or Loop 5 entry (F5/F6/F7 accuracy < 0.75 with window expansion) | E2 structural floor + E4 mechanical scoring, reasons always mechanical | D §3, §9 |
| **Metadata-only local cache** (Option F) | Loop 5/6 evidence: repeated 40 u thread-map fetches or cross-thread walks measurably dominate quota/RTT | Headers-only store, `historyId`-stamped, content always live | B §2-F |
| **History-synchronized index** (Option E) | Loop 6 shows direct-API freshness lag (Problem B confirmed on REST) or scale pain stateless can't absorb | Full sync + `history.list` polling; staleness stamped on every response; 404→full-resync loud | B §2-E, F §4.2 |
| **Tier-2 small-model router classifier** | Loop 3 recovery bar missed with misparse-class trace evidence; requires traces per Decision 9 | Adaptive-RAG-style, trained on harvested outcome labels; synthetic-account traces only (Limited Use policy) | C §2-B, F §2.4 |
| **Server-side LLM rerank/sufficiency** (opt-in key) | Ambiguity-map failures Tier-2 traces attribute to ranking; explicit user opt-in + privacy disclosure | Quarantined: closed-type outputs only (enums/IDs/booleans), validated before use | C §4.1c, F §6.3.6 |
| **Push notifications** (`users.watch` + Pub/Sub) | Loop 6 shows polling insufficient (polling at 2 u/30 s is ≈0.07% of budget — unlikely) | Per B F6, with re-watch cron and fallback polling | B F6 |

---

## 5. Rejected (cost not justified)

| Rejected | Why |
|---|---|
| **Standalone persistent vector index (Option C)** | Dominated: without E-style sync it recreates the stale-index bug MailWeave exists to fix (CTX §45); with sync it *is* E + embeddings. If ever needed, it is an extension of the history-synced index, never a first build (B §2-C verdict). |
| **MCP sampling for any routing/rerank** | Deprecated in spec 2026-07-28 ("new implementations SHOULD NOT adopt"); never supported on Claude-family hosts anyway (C §4.1b, A §7.2). |
| **Mandatory LLM router on every query** | Violates the Adaptive Cost Invariant; redundant — the calling model already classified the query when it chose tool + args (C §2-C, §3). |
| **Training a router now** | No traces exist; training would encode assumptions as ground truth (CTX Decision 9; C §2-B). |
| **Multi-level disclosure ladder as API** (T3 level knob; CTX §10.2 L0→L5 as tool design) | Directly contradicted by the only controlled study: "a second, deeper routing level never helps and sometimes breaks accuracy" (A §8.1); also collapses D §2's two axes (D §7-T3). |
| **`gmail.metadata`-scope architecture** | Cannot use `q` search and cannot read bodies — structurally incapable of the thesis; buys no verification relief either (still restricted) (F §1.2, B F8). |
| **Full-thread dump as default representation** | The context-inefficient baseline the project exists to beat; now also the vendor's institutionalized workaround, i.e., Baseline B (A §3.4, §11.2). It remains a *baseline fixture* forever (E §4.2). |
| **Hosted `get_thread` as designed-in fallback/oracle** | #239 evidence it truncates on 10+-message threads; MailWeave's own REST path + manifest replaces it (§2c; A §6.1, §11 weakens-2). |
| **Shared OAuth client ID distribution** | Converts MailWeave into a restricted-scope-verified app, likely with CASA assessment; BYO-project keeps each user personal-use exempt (F §2.4). |
| **Seeding via `messages.send`** | Costs 100 u, actually delivers mail, and adds the classification lottery; reserved exclusively for Loop 6 freshness probes as a labeled secondary condition (E §1.2.1, §7). |
| **Fabricated relevance scores / synthetic "snippet" text** | Honesty rule: mechanical reasons only; Gmail-derived snippet labeled `gmail_snippet`, never our own text under that name (CTX §20; D open Q6). |
| **Writing any Gmail write/send tools into the v1 server** | Read-only posture is load-bearing for the security story (trifecta leg removal) and for consent honesty; futures gated by F §8's ceremony list. |

---

## 6. Loop 0 preflight list

Every load-bearing assumption gets an empirical smoke test **before anything depends on it**. Failures are loud blockers (E §1.3). This list extends E's S1–S10 (all adopted); every probe's outcome — including boring passes — is recorded in experiment log 001, because these results are the evidence base for the §3/§4 gates.
The probes run in dependency order: auth (P7) → seeding mechanics (P2/P3/P6/P9/P10/P14) → read-path validation (P1/P5/P13) → cost/limits (P4/P12) → external baselines (P8/P11) → stack checks (P15).

| # | Probe | Assumption at risk | Source of doubt |
|---|---|---|---|
| P1 | `threads.get(format=metadata, metadataHeaders=Message-ID,In-Reply-To,References)` returns those headers; and whether `snippet`/`internalDate`/`sizeEstimate`/attachment part metadata accompany the metadata format | The thread map's reply-tree and row content | Docs name To/From/Subject only as examples (D §1.1, §11) |
| P2 | N=100 and N=105 single-thread inserts stay one `threadId` (S6) | The ~100-messages-per-conversation ceiling (third-party documented) vs API threading | E §1.2.5; fallback = N=90 fraction-preserving grid (E §2.4) |
| P3 | Byte-identical Subject threads; `Re:`-prefixed variant recorded (S2) | "Subject headers must match" strictness | E §1.2.3 |
| P4 | Quota probe: S10 write-side + read-side burst (~400–600 gets/min; 429 onset discriminates 300 vs 3,000/min ceilings) + Cloud Console quota panel | The ~10× quota-table discrepancy | §2d; B F7 |
| P5 | REST `threads.get` completeness: manifest ID-set equality at N ∈ {10,100,105}, `metadata` and `full`; hosted `get_thread` measured on the same threads | "get_thread is reliable ground truth" | §2c; A §6.1 (#239) |
| P6 | Caller-supplied `Message-ID` preserved verbatim; `rfc822msgid:` finds it (S3) | Ground-truth joins + exact-match probes | E §10.1 |
| P7 | Both GCP projects reach In-production-unverified with restricted scopes; token longevity confirmed past 7 days; whether Testing-issued tokens survive publishing | 7-day token churn killing eval cadence | F §2.2, F could-not-verify #2–3 |
| P8 | Hosted-MCP Baseline A: connector sign-in to the seeded test account; #296 `rfc822msgid:` replication attempt executed and dated; else A′ invoked with the RECONSTRUCTED label | Baseline A attachability and honesty | E §4.1, §9 Q4 |
| P9 | `internalDateSource=dateHeader` yields intended epoch ms; `after:`/`before:` bound correctly (S4) | All temporal families | E §1.2.2 |
| P10 | Twin-corpus insert-vs-import settle/classification probe (extended S8) + settle gate operational | Seeding-primitive choice; indexing of inserted mail | §2a; E §10.6 |
| P11 | Freshness smoke (promoted from Loop 6 per B §5 risk 1): small H0/H1/H2 arm run, no claims recorded | Problem B unhedged in the stateless design | B §5, E §7 |
| P12 | Latency baseline: p50/p95 per Gmail method and per batch size, from the harness host | All wall-clock planning figures are estimates | B F9 |
| P13 | `resultSizeEstimate` error magnitude measured; `threads.get` ordering observed (harness sorts by `internalDate` regardless) | Sufficiency signals; position derivation | C §5.1, E §10.8 |
| P14 | Labels applied on insert (S5); label-scoped `batchDelete` reset restores baseline (S9); `getProfile` callable under `gmail.readonly` (account-pinning path) | Cleanup determinism; redaction-profile keying | E §1.2.8, F could-not-verify #5 |
| P15 | Node dependency check: HTML→text lib license (permissive), `googleapis` batch path, reply-parser behavior on fixture corpus | Stack commitments of §1.5 | B §4.3, D §6.2 |

---

## 7. The four invariants: structural enforcement

| Invariant (CTX §39) | How the chosen design enforces it structurally |
|---|---|
| **Evidence Preservation** | Retrieval is message-level: hits are Gmail message IDs before any representation exists (B F1) — the #296 class requires *our* layer to drop IDs, and the P2 serializer makes that unrepresentable: it takes the evidence set as input and asserts `evidence ⊆ rendered rows` (CI-tested); every message in a touched thread is at least a stub row, so omission is a visible stub, never an absence. Gate: Loop 1 recall ≥ 0.98, position spread ≤ 0.05, FNF = 0 (E §8.2). |
| **Explicit Partiality** | The map-carrier shape *is* the partiality artifact: exact totals from real skeleton fetches, included-set identification, role tags, and a concrete affordance beside every count (D §5.4.1) — mechanically audited by E §3.2's P1–P5 adapters (gate ≥ 0.98). Partiality is recursive: `quoted_removed_chars`, in-text truncation markers with `body_full` paths, announced run-collapsing, search-scope statements, `fetchedAt` stamps (D §5.4). Self-truncation at ~9k tokens keeps truncation authority with MailWeave, explicit, below host caps (D §1.3, §6.3). |
| **Adaptive Cost** | The cheap path is enforced in code: L0–L3 ladder budgets (≤3 relax rounds, ≈25 Gmail calls, ~2 s p95, 0 LLM calls) are constants, and caps hit are reported in-band (C §5.2). Expensive capabilities (semantic, LLM, multi-thread expansion) exist only as client-invoked affordances or opt-in config — the server *cannot* spend them unprompted. Gate: Loop 3 simple-family p50 ≤ 1.25× Baseline D (E §8.2). |
| **Recoverability** | The response schema has no bare-empty shape: weak/empty outcomes are `RetrievalReport`s naming what was tried, what was dropped, what was not tried, and the calls that would try it (C §5.3). Relaxation is systematic one-constraint-at-a-time — enumerable, loggable, cap-bounded. Because hits are IDs, a found target cannot be un-found downstream; routing errors can only delay, never destroy (C §5.3.3). Gate: Loop 3 fallback recovery ≥ 80%; FNF = 0 on answerable families, paired with the hallucinated-found guard on F10 (E §3.1). |

---

## 8. Falsifiability: what kills or shrinks the thesis, and what we do then

Restating CTX §57 as benchmark outcomes with pre-committed responses. The architecture is deliberately modular so each response is a deletion, not a rewrite: the ladder is a policy object inside `search_mail`; the map-carrier is a serializer; semantic retrieval is an unbuilt interface stub.

| Kill/shrink outcome (measured at gates) | What the architecture does in that world |
|---|---|
| **Baseline E (strong agent + honest primitives) matches MailWeave** on accuracy with no ≥30% token or latency win (§2b margins) | The added-value claim is retired. MailWeave repositions as *the honest-primitives contract*: message-level tools + partiality/trust envelope + the map as a cheap convenience — published with the negative result front and center. That is still a real contribution: no existing Gmail MCP ships evidence preservation or partiality semantics (A §5.5), and the vendor's own surface still lacks both (A §3.4). |
| **Progressive disclosure costs more tool calls / worse e2e latency than larger context** (Loop 2 e2e vs Baseline B) | Default response bundles more (bigger first disclosures inside the one level); the map stays as the partiality carrier, its budget share reduced; the finding is logged and the token-savings claim dropped or scoped. |
| **Adaptive routing adds latency without recall** (Loop 3 bars missed with no recovery wins) | Strip the ladder to L0/L1 + `RetrievalReport`; keep client escalation; the router becomes a parser only. |
| **Semantic adds negligible recall** (Loop 4 entry never fires, or adopt-bar missed) | Never built; the permanent negative-result log entry becomes part of the public story (E §8.2 explicitly calls this a process pass). |
| **Evidence is rarely buried in real workloads** (R1 census distributions) | Reposition from efficiency win to correctness/robustness fix for the documented failure class; the buried-evidence families remain as regression armor, headline claims re-scoped to measured distributions. |
| **Gmail primitives + full-thread fetch are simply good enough** (Baselines B/D beat or tie on recall AND tokens AND latency) | The strongest shrink: MailWeave's public artifact becomes the benchmark + the reproduction + the response-shape convention, and the code is a thin honest wrapper. The goal is to discover what works, not to protect the idea (CTX §57). |

Claim discipline stands regardless: no public claims before the CTX §58 minimum-proof list is met; no freshness sentences of any kind before Loop 6 completes (E §7); public-issue evidence cited as provenance, never blended with our measurements (E §4.1).

---

## 9. Adopted exit criteria (E §8.2), with amendments

**Adopted as proposed:** Loop 0 (substrate green + baseline floor), Loop 1 (recall ≥ 0.98 overall / ≥ 0.95 per position / spread ≤ 0.05 / FNF = 0 / within 2 points of Baseline B), Loop 2 (tokens ≤ 30% of Baseline B median; relevant-token fraction ≥ 3×; P1a/P2/P3 ≥ 0.98, P4/P5 ≥ 0.95; rounds p95 ≤ 4; recall@1round ≥ 0.85 on F1/F2; e2e ≥ Baseline B − 3 points; partiality probe ≥ 0.9), Loop 3 (p50 ≤ 1.25× Baseline D on simple; recovery ≥ 80%; no p95 regression > 20%), Loop 4 entry/adopt (< 0.70 F4-T2 entry; +15 points / ≤ +50% p95 / simple-latency unchanged), Loop 5 entry/adopt, Loop 6 completion criteria. Statistical hygiene (Wilson CIs, McNemar, two HOLDOUT seeds, pre-registration) adopted in full.

**Amendments (frozen in experiment log 001 before Loop 0 closes):**
1. **Loop 2/3 gates add the Baseline-E comparison as binding** (§2b): MailWeave must beat Baseline E on ≥1 of {accuracy, ≥30% median token reduction, e2e latency} without losing >3 points accuracy or >20% latency on the others.
2. **Loop 0 adds** the quota probe (P4), REST-`threads.get` completeness validation (P5), the insert/import twin probe with its flip rule (P10), the freshness smoke (P11), and the production-unverified auth validation (P7).
3. **Loop 2 runs both disclosure arms** (D-base, D-var per D §9) under equal token budgets; the shipped default is decided by H2/H3, simpler-wins on a tie.
4. **Tier-2 cadence:** gate-only until Loop 2, then weekly on the stratified subsample (E §9 Q5 resolved as proposed); agent and judge models pinned in log 001.
5. **Open questions resolved as recorded in §1–§5** (scope = `gmail.readonly` for systems under test; fractions-normative N=90 fallback; personas as From-headers only outside Loop 6; census script gets F's privacy review before first personal-mailbox run; non-English excluded from gates).

---

**Non-architectural loose end, tracked here so it is owned:** the "MailWeave" name has near-collisions (MailWeaver.ch; parked mailweaver.com — A §10.3) and CTX §7's specific claimed collisions were not reconfirmed; re-run the name/namespace check before any public release. Not a build blocker (CTX §7).

*Next deliverable: IMPLEMENTATION_PLAN.md translating this into milestones/interfaces/tests without overwriting this rationale (CTX §52). Nothing in that plan may weaken an invariant, un-gate an experimental branch, or blend claim classes.*
