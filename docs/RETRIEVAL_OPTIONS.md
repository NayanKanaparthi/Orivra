# RETRIEVAL_OPTIONS.md — Retrieval Architecture Comparison for MailWeave

**Author:** Agent B (retrieval architecture researcher)
**Date:** 2026-08-30
**Status:** Input to `ARCHITECTURE_DECISION.md` synthesis. Per Decision 12, this document compares options and states a leaning; it does not lock a design.

**Method note.** Every Gmail API and SDK fact below was re-verified against live documentation on 2026-08-30 via web fetch (direct curl to `developers.google.com` is blocked in this environment; fetches went through the research proxy's page-summarization path, with decision-critical tables re-fetched with verbatim-quote prompts and cross-checked). Facts I could not verify are collected in the final section and marked inline as **[unverified]** or **[estimate]**.

---

## 1. Verified Gmail API ground truth

All retrieval options are judged against these primitives. This section is the factual foundation; the option analysis cites it by fact number.

### F1. Message-level lexical search exists and preserves hit identity

`users.messages.list(q=...)` returns **the individual matching messages** — each result contains *only* `id` and `threadId`; bodies/snippets are not included and must be fetched via `messages.get`. `maxResults` defaults to 100, max 500; pagination via `pageToken`/`nextPageToken`. `resultSizeEstimate` is explicitly an *estimate* (do not use it as ground truth for partiality counts). The `q` parameter "supports the same query format as the Gmail search box" and **cannot be used when the only scope granted is `gmail.metadata`**.
Source: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list

This is the single most important fact for MailWeave: the Gmail API's native search unit is the message, so the evidence that caused a match is identified by ID *before* any representation layer touches it. The hosted-MCP bug (#296) is structurally impossible to reproduce if the pipeline carries these IDs through to the representation.

### F2. API search is message-scoped, not thread-scoped (differs from Gmail UI)

The filtering guide states two semantic differences from the web UI: (a) alias expansion is not supported, and (b) **"the Gmail UI allows users to perform thread-wide searches, but the API doesn't."** In the API, all terms of a `q` must match within a single message; in the UI, a thread can match because different messages jointly satisfy the query. Dates accept `YYYY/MM/DD` (interpreted midnight PST) or epoch seconds for timezone-accurate windows.
Source: https://developers.google.com/workspace/gmail/api/guides/filtering

Two consequences:

- **Pro (evidence preservation):** a hit is a specific message, never a vague "this thread matched somehow".
- **Con (recall):** a multi-constraint query ("from:sarah launch october") can miss threads where Sarah's message says "yes, agreed" and a *different* message contains "launch october". The benchmark (Agent E) must include this case. Mitigation inside any option: decompose the query into per-constraint searches, intersect/union `threadId` sets client-side (each extra `messages.list` costs only 5 quota units, F7).

### F3. There is no thread operator in the query language

The documented operator list (`from:`, `to:`, `cc:`, `bcc:`, `subject:`, `after:`, `before:`, `older_than:`, `newer_than:`, `label:`, `category:`, `has:`, `list:`, `filename:`, `in:`, `is:`, `deliveredto:`, `size:`, `larger:`, `smaller:`, `rfc822msgid:`, plus `OR`, `AND`, `-`, quoted phrases, `( )`, `{ }`) contains **no operator that restricts a search to a given thread ID**. Combined with F2, "search within this thread" must be implemented as: `threads.get` → filter messages client-side.
Sources: https://support.google.com/mail/answer/7190 ; https://developers.google.com/workspace/gmail/api/guides/filtering

`rfc822msgid:` does allow exact-message lookup by RFC 822 Message-ID (this is the operator used in the issue #296 reproduction).

### F4. `messages.get` has four formats; `threads.get` returns whole threads only

- `messages.get` formats: `minimal` (IDs/labels), `metadata` (headers + structure; `metadataHeaders[]` selects specific headers, e.g. only From/To/Date/Subject), `full` (parsed body in `payload`), `raw` (RFC 2822).
- `threads.get` accepts `full` / `metadata` / `minimal` and returns **all messages in the thread**; there is **no pagination or partial fetch within a thread**.
Sources: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/get ; https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.threads/get

Design consequence: `threads.get(format=metadata, metadataHeaders=[From,Date,Subject])` is a natural **"thread map" primitive** — one round-trip yields the complete, current message inventory of a thread (IDs, senders, dates) without bodies. This directly supports the Partiality Invariant ("thread has 100 messages; you have seen 3; here is the map") at bounded token cost. The token cost of a metadata thread map is bounded but not tiny for 100-message threads; the representation layer can compress it (counts + time ranges + the map on request).

### F5. Batching reduces round-trips but not quota

HTTP batching (`/batch/gmail/v1`): hard limit **100 calls per batch**, and **"sending batches larger than 50 requests is not recommended"** because larger batches are likely to trigger rate limiting. A batch of *n* requests **counts as n requests against quota**.
Source: https://developers.google.com/workspace/gmail/api/guides/batch

So batching converts *n* HTTP round-trips into ~1 wall-clock round-trip, but buys zero quota relief.

### F6. Incremental sync and push primitives exist and are cheap

- `users.history.list(startHistoryId=...)` returns chronological mailbox changes (`messagesAdded`, `messagesDeleted`, `labelsAdded`, `labelsRemoved`; filterable by `historyTypes`, `labelId`; `maxResults` default 100 / max 500). A `historyId` is **"typically valid for at least a week, but in some rare circumstances may be valid for only a few hours."** An expired/invalid `startHistoryId` returns **HTTP 404** → client must full-sync.
- Full sync per Google's guide = `messages.list` for IDs + batched `messages.get`; store the latest `historyId`.
- Push: `users.watch` + Cloud Pub/Sub; **must re-watch at least every 7 days (daily recommended)**; notification payload is `{emailAddress, historyId}`; **max notification rate 1 event/sec per user, excess dropped**; delivery "typically within a few seconds" but "notifications might be delayed or dropped" — Google itself recommends fallback polling.
Sources: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.history/list ; https://developers.google.com/workspace/gmail/api/guides/sync ; https://developers.google.com/workspace/gmail/api/guides/push

### F7. Quota units and rate limits (as published today — see discrepancy flag)

Fetched verbatim from the quota page on 2026-08-30:

| Method | Quota units |
|---|---|
| `getProfile` | 1 |
| `history.list` | **2** |
| `messages.list` | **5** |
| `messages.get` | **20** |
| `messages.attachments.get` | 20 |
| `threads.list` | 10 |
| `threads.get` | **40** |
| `labels.list` | 1 |
| `watch` | 100 |
| `messages.send` | 100 |

Rate limits: **1,200,000 quota units/min per project**; **6,000 quota units/min per user per project**; **80,000,000 units/day per project** before billing applies.
Source: https://developers.google.com/workspace/gmail/api/reference/quota

**Discrepancy flag (important).** Widely cited historical values for this page were `messages.get` = 5, `threads.get` = 10, per-user limit "250 quota units per user per second", and a 1,000,000,000 units/day free tier. Two independent fetches today consistently returned the table above instead, so I treat today's page as authoritative — but I could not cross-check against a second Google source (console quotas are not fetchable from this environment). The difference changes bulk-indexing feasibility by ~10× (see Options C/E), so **Loop 0 must include an empirical quota probe** (hammer a seeded mailbox, observe 429s and the console's reported limits). Either reading changes nothing for Loops 1–3 on a seeded test mailbox (hundreds of messages).

Derived arithmetic used below (current-page numbers, per user per minute):
- ≈ **300 `messages.get`/min** (6,000 ÷ 20) or **150 `threads.get`/min** or **1,200 `messages.list`/min**.
- `threads.get` (40) costs the same as **two** `messages.get` (20 each). Quota-wise, selective message fetching only beats a thread fetch when ≤2 messages are needed from that thread. **Token/context-wise the ordering inverts** — a 100-message `threads.get(full)` is a context catastrophe. MailWeave's economics: progressive disclosure optimizes *tokens*; quota mildly *favors* coarse fetches; the eval must track both budgets separately.
- `history.list` at 2 units → polling every 30 s costs 4 units/min ≈ 0.07% of the per-user budget. Freshness polling is effectively free.

### F8. Scopes and OAuth operational facts

Verbatim classification from the scopes page: **Restricted** scopes include `mail.google.com`, `gmail.readonly`, `gmail.modify`, `gmail.metadata`, `gmail.compose`, `gmail.insert`, `gmail.settings.*`. **Sensitive:** `gmail.send` (and add-on scopes). **Non-sensitive/recommended:** `gmail.labels`, some add-on scopes. "Restricted scopes … require restricted scope OAuth App Verification" (and a CASA security assessment if restricted-scope data is stored/transmitted on servers — applies to *published* apps, not private testing).
Source: https://developers.google.com/workspace/gmail/api/auth/scopes

- `gmail.metadata` cannot read bodies **and cannot use `q`** (F1) — so even a metadata-only architecture needs `gmail.readonly` if it wants Gmail-side search. `gmail.readonly` is the correct minimal scope for every option below; all are read-only.
- **Testing-status token churn (verified):** "A Google Cloud Platform project with an OAuth consent screen configured for an external user type and a publishing status of 'Testing' is issued a refresh token expiring in 7 days" (except bare profile scopes). Source: https://developers.google.com/identity/protocols/oauth2
  Consequence for the user-fixed "real Gmail from day one" constraint: with a plain consumer test Gmail account, expect **forced re-auth every 7 days**. Mitigations: (a) scripted re-auth as part of the dev loop; (b) a Google Workspace account with an *Internal* OAuth app (no 7-day expiry, no verification) **[standard practice, not re-verified today]**; (c) accept the churn for Loops 0–3.

### F9. Latency ground truth

Google does not publish REST latency figures. Public numbers do not exist to verify, so this document counts **API round-trips (RTTs)** as the latency unit, per the task definition. For wall-clock intuition only: individual Gmail REST calls are commonly observed in the **~100–400 ms** range from well-connected hosts, and a 50-call batch completes in far less time than 50 sequential calls but more than one small call **[estimate — must be measured in Loop 0 against the seeded mailbox; record p50/p95 per method and per batch size]**.

---

## 2. The candidate architectures

Six options. A–E as chartered; F is an added variant I can justify (metadata-only local cache) that fills the gap between D and E. Each option is scored on: evidence-preservation correctness, latency (RTTs), privacy footprint, implementation complexity, freshness, MCP usability, quota cost.

A shared property first: **every option below builds on F1** (message-level search), because that is the atomic fix for the documented failure. The options differ in what they add around it.

---

### Option A — Stateless direct Gmail (lexical, message-level, Gmail as sole source of truth)

**Shape.** Translate/forward the query to `messages.list(q=...)`; fetch the hits via batched `messages.get` (metadata first, `full` for the top few); expand on demand via `threads.get` (thread map, then targeted gets). No state beyond the process (at most a per-session in-memory cache keyed by message ID, annotated with `fetchedAt`).

**Evidence preservation: excellent by construction.** Hit IDs from F1 flow straight into the representation. The #296 class of bug (search matched message X, representation shows oldest five) cannot occur unless MailWeave's own representation layer drops IDs — which is exactly the invariant the eval guards. Caveat: F2's message-scoped `q` is a *recall* semantics difference vs. the UI; correctness of what is returned is unaffected, but the benchmark must measure the multi-constraint recall gap and the query-decomposition mitigation.

**Latency.** Typical walk-throughs (RTT = one HTTPS exchange; batch = 1 RTT):
- *Simple lookup* ("email from Sarah yesterday"): `messages.list` (1 RTT, 5 u) + batch `messages.get(metadata)` on ≤10 hits (1 RTT, ≤200 u) → **2 RTTs**, agent sees headers+snippet-equivalents; +1 RTT if bodies of top hits are then requested (or fold into the same batch with `full` for the top 3).
- *Buried evidence* (target at 37/100): identical 2 RTTs — position in thread is irrelevant because retrieval is message-level. Expansion: `threads.get(metadata)` thread map (1 RTT, 40 u) + batch get of chosen neighbors (1 RTT). **Worst realistic interactive path: 4 RTTs.**
- *Full-thread baseline for comparison*: `messages.list` + `threads.get(full)` = 2 RTTs, 45 u, but unbounded token cost.

**Privacy: minimal possible.** Read-only scope, no persistence, bodies transit process memory only. Nothing to delete, no index to leak. This is the reference point every other option must justify moving away from.

**Complexity: lowest.** No sync, no store, no schema. The hard work is representation/disclosure design (Agent D's domain), not infrastructure.

**Freshness: equals Gmail's own search index.** `messages.get`/`threads.get` by ID are authoritative. The open question is whether *direct API* `messages.list(q)` exhibits the #82548 lag reported against the hosted MCP — the doc's Problem B hypothesis. Loop 6's experiment (send message → poll `messages.get` vs `messages.list(q)` vs hosted MCP) decides this; Option A deliberately does not pre-solve it.

**MCP usability: good, with one nuance.** Tools map cleanly (`search`, `fetch_evidence`, `thread_map`, `expand`). Multiple small tools + progressive disclosure means more tool-call round-trips for the *agent* — the doc's own falsifiability list (§57) includes "progressive disclosure causes more tool calls and worse end-to-end latency"; the eval measures it. Stateless server fits the MCP 2026-07-28 stateless direction (see §4).

**Quota.** 105–265 u per query at the walk-through depths → a per-user budget of 6,000 u/min sustains **~25–55 such queries/min**, far above interactive need. Even the historical lower limits comfortably cover interactive use.

**Verdict.** The floor every other option must beat *on a measured failure* (§55 of the context doc).

---

### Option D — Structural/thread-aware retrieval layered on A

(Taken out of letter order because it is A's natural first extension, and my recommendation folds a thin slice of it into the minimal build.)

**Shape.** Same statelessness as A, plus structure-aware operations computed *at query time from data already fetched or one thread map away*:
- thread map (F4) as a first-class representation: counts, time range, participants, position of hits;
- reply-chain expansion (walk `In-Reply-To`/`References` headers — request them via `metadataHeaders`) instead of only ±N neighbors;
- participant filtering/ranking (From/To/Cc of candidates);
- time-segment expansion (messages in the thread within a window around the hit).

**Evidence preservation:** inherits A's. Structural expansion adds *labeled* context ("included because: direct parent of hit"), which strengthens the matched-vs-contextual distinction required by §26.

**Latency:** A + 1 RTT (thread map, 40 u) per thread examined; reply-chain walks are client-side over the map + targeted batch gets (1 RTT per depth level if not prefetched). Cross-thread participant queries ("what has Sarah told me about Apollo") decompose into 1–3 extra `messages.list` calls (5 u each) — still single-digit RTTs.

**Privacy:** identical to A.

**Complexity: moderate.** Header parsing (`References` chains are messy in the wild), thread-map representation, expansion policies. No storage. The main risk is over-designing expansion policy before Loop 5 shows fixed windows failing — sequencing answer: ship the thread map + fixed-window expansion in the minimal build; add reply-chain/participant expansion when Loop 5 measures a gap.

**Freshness:** identical to A.

**MCP usability: the best of all options.** The thread map is precisely the "explicit partiality" artifact MCP tool output needs: `{thread_total: 100, disclosed: [37, 38, 41], matched: [37], more: true, expansion_ops: [...]}`.

**Quota:** A + 40 u per examined thread; negligible.

---

### Option B — Hybrid lexical + on-demand semantic (no persistent index)

**Shape.** Run A/D first. When lexical evidence is weak (0 hits, or low-confidence hits for a paraphrase-shaped query), fetch a *candidate pool* (e.g., recent/filtered messages via `messages.list` with relaxed `q` + batched gets), embed the candidates and the query **at query time**, rank by similarity, disclose top evidence. Embeddings are ephemeral (session cache at most).

**Evidence preservation: good, with an honesty obligation.** Semantic hits are *inferred* relevance, not Gmail-search hits; per §20 the representation must label the provenance ("selected by embedding similarity 0.xx", not fake confidence). Because the pool is fetched from Gmail live, no staleness is introduced.

**Latency: the escalation path is expensive.** Beyond A's RTTs: 1–2 `messages.list` (relaxed scope) + batched gets for a pool of ~50–200 candidates (1–4 batch RTTs at ≤50/batch, F5) + 1 embedding-provider RTT (hosted) or local model inference. Realistic escalated query: **4–8 RTTs + embedding time**. This is acceptable *only because* it runs on the adaptive path (Adaptive Cost Invariant): simple queries never pay it.
- Pool-size quota math: 100 candidates × 20 u = 2,000 u = one-third of the per-user minute budget — fine occasionally, not as the default path.

**Privacy: worse than A only at query time.** With a hosted embedding API, bodies of pool candidates leave the machine transiently. A local embedding model (see §4 stack notes) removes that egress at CPU/latency cost. Nothing persists either way — this is the decisive privacy advantage over C/E.

**Complexity: moderate.** Embedding client + rank + provenance labeling; no store, no sync. The subtle part is the *escalation trigger* (Agent C's domain: what counts as "lexical failed").

**Freshness: same as A** (pool is fetched live).

**MCP usability:** same surface as A/D; escalation is internal. Disclosure metadata must state which retrieval produced each item.

**Verdict.** The correct *shape* for semantic retrieval **if** Loop 4 measures a paraphrase-recall gap. It defers the entire index/privacy/staleness problem while still answering the semantic-gap hypothesis. Per §55, do not build until lexical demonstrably misses paraphrases.

---

### Option C — Persistent semantic index (pre-embedded mailbox, vector store)

**Shape.** Bulk-ingest the mailbox (full sync per F6), embed all message bodies, store vectors + text locally (Chroma/sqlite-vec/LanceDB/etc. — or hosted, which multiplies the privacy cost). Query = embed query → ANN search → verify/fetch current state from Gmail.

**Evidence preservation: two distinct hazards.**
1. *Staleness omission* — the stale-index paradox (§45): a query answered from an index that lags the mailbox can silently miss the newest evidence, recreating the class of bug MailWeave exists to fix, in a worse form (our own fault, not Google's).
2. *Provenance blur* — semantic hits need honest labeling (as in B).
Mitigation for (1) requires exactly the sync machinery of Option E — which is why C is not really a standalone option (see verdict).

**Latency: best-in-class at query time** (local ANN in milliseconds; 1 embedding call for the query; +1–2 RTTs only to verify/refresh disclosed items — a verification step the Evidence Preservation Invariant effectively mandates, since disclosing index-cached content as current mailbox state without a check would misrepresent deleted/changed messages).

**Ingest cost is the real bill (quota + time + money):**
- 10,000-message mailbox: 10,000 × 20 u = 200,000 u → at 6,000 u/min/user ≈ **33 min minimum** just for Gmail fetches (F7 numbers; ~3.5 min under the historical numbers — the discrepancy flag matters exactly here), in ≥200 batch RTTs (≤50/batch), plus embedding ~10k texts.
- 100,000-message mailbox: ≈ 5.5 h fetch minimum, plus embedding cost/time.

**Privacy: the worst option.** Full corpus of bodies + embeddings persisted; embeddings of private email sent to a hosted provider unless a local model is used; store must support deletion, encryption-at-rest decisions, and log hygiene. This is a materially different product posture than A/B/D (§41 makes this tradeoff explicit).

**Complexity: high.** Ingest pipeline, vector store, embedding lifecycle (model version migrations re-embed the corpus), degraded-mode behavior mid-sync, deletion semantics — plus, to be correct, all of E's sync.

**Freshness: poor unless E is bolted on.** Without history sync, the index silently decays; with it, you have built E + embeddings.

**MCP usability:** same query surface; must additionally expose index status ("last synced historyId/time") as a resource per §45.

**Verdict.** Dominated: C without E's sync violates the stale-index principle; C with sync ⊇ E. If a benchmark ever justifies a persistent semantic layer, it should be an *extension of E*, never a standalone first build. Rejected for Loops 1–3 with confidence.

---

### Option E — History-synchronized local index (`users.history.list` incremental sync)

**Shape.** Full sync once (F6): page `messages.list` (500/page, 5 u/page) + batch `messages.get` for all messages; store locally (SQLite + FTS5 is the natural fit); then poll `history.list(startHistoryId)` (2 u) and/or `users.watch` push to stay current. Queries run against the local store; Gmail remains the recovery source of truth (404 → full resync).

**Evidence preservation: good if and only if the freshness contract is explicit.** The design *can* honor the invariants: staleness is quantifiable ("synced through historyId H at T"; with 30 s polling the worst-case lag is ~30 s + processing). But every local-search answer must carry that stamp, and the 404/expiry path (F6: validity "typically at least a week… sometimes only a few hours") must degrade loudly to full resync, not silently serve the stale store.
**A second, underappreciated correctness cost:** local search must *reimplement or translate Gmail's query semantics* (F3's operator list — `from:` alias handling, `OR`/`-`, date boundaries in PST, `label:` vs `category:`…). Any divergence between MailWeave-local search and Gmail search is a new class of silent semantic drift — precisely what the project criticizes. This is the option's biggest hidden risk, bigger than the sync plumbing.

**Latency: best steady-state.** Query-time Gmail RTTs = 0 (local FTS in ms), + optional verification gets for disclosed items. Initial sync as computed in C (33 min per 10k messages at current quota figures — the discrepancy flag is decision-relevant here too). Push adds Cloud Pub/Sub infrastructure (topic + subscription + re-watch cron, F6) for seconds-level freshness; polling at 2 u is nearly free and simpler.

**Privacy: near-C.** Full local copy of bodies (no embedding egress, so better than hosted-embedding C; equal to local-embedding C minus vectors). Same deletion/encryption/log obligations.

**Complexity: highest of the non-vector options.** Sync state machine (full, partial, 404 recovery, label churn), local schema, query translation layer, storage growth. Realistically the majority of the codebase would be sync + local search rather than the retrieval/disclosure ideas MailWeave actually wants to test.

**Freshness: the whole point.** Bounded, measurable lag; solves Problem B *if Problem B exists on the direct API* — which is untested (Loop 6). Also enables cheap structural/cross-thread queries and gives C a sound foundation later.

**MCP usability:** same surface + mandatory staleness resource. Also uniquely enables "what changed since X" tools (`history.list` semantics surfaced to the agent) — genuinely useful, but not needed for the thesis.

**Verdict.** The correct *eventual* home for freshness guarantees and cheap structure — but building it first would front-load the largest complexity/privacy budget before any benchmark shows Gmail's own primitives failing. Per §55 and Loop 6: build only after a measured freshness or cost failure of A/D.

---

### Option F (added variant) — Metadata-only local cache layered on A/D

**Justification for adding:** there is a large gap between "no state" (A/D) and "full mailbox copy" (E). Header-level state — message ID, threadId, From/To/Cc, Date, Subject, labels, `References`/`In-Reply-To` — enables participant graphs, thread maps without repeated 40 u fetches, cross-thread navigation, and freshness probes, at a fraction of E's privacy and sync surface. Prior-art Gmail MCPs don't occupy this slot, and it is the natural fallback if Loop 5 shows structural queries getting quota- or RTT-heavy.

**Shape.** Same as E's sync loop but storing **no bodies**: full metadata sync via batched `messages.get(format=metadata, metadataHeaders=[From,To,Cc,Date,Subject,Message-ID,In-Reply-To,References])`, kept current via `history.list` (2 u polls). All *content* retrieval remains live Gmail (A/D path). Note: the `gmail.metadata` *scope* cannot serve this design because it forbids `q` search (F8); the scope remains `gmail.readonly`, and "metadata-only" is a *storage policy*, not a scope choice — worth stating in SECURITY_NOTES.

**Evidence preservation:** content always fetched live → no content staleness; structural answers (thread maps, participant lists) carry a sync stamp like E. Quota cost of metadata gets is the same 20 u as full gets (quota is per-method, not per-format — F7 table lists methods only), so **initial sync quota/time equals E's**; only storage, privacy, and egress shrink.

**Latency:** steady-state thread maps and participant queries become local (0 RTTs); content fetch RTTs as in A.

**Privacy:** headers are still sensitive (who talks to whom, when, about what subject), but no bodies at rest — a much easier deletion/encryption story than E.

**Complexity:** ~60–70% of E (same sync state machine; no body storage, no local body search, no query-language reimplementation — Gmail still does all content search).

**Freshness:** structural layer bounded-lag like E; content layer live like A.

**MCP usability:** as D, with instant maps.

**Verdict.** The best-value *second* architecture — but still a §55 deferral: adopt only when benchmarks show D's per-query 40 u thread maps or cross-thread walks are a measured bottleneck, or Loop 6 demands a freshness probe cheaper than search polling.

---

## 3. Comparison matrix

Scale: ++ strong / + adequate / 0 neutral / − weak / −− disqualifying-without-mitigation. "RTTs" = Gmail API round-trips on the *typical* interactive path (escalations noted).

| Criterion | A stateless | D structural (+A) | B on-demand semantic (+A/D) | C persistent vector | E history-synced index | F metadata cache (+D) |
|---|---|---|---|---|---|---|
| Evidence-preservation correctness | ++ (by construction) | ++ (labeled context) | + (provenance labeling required) | −− unless E-style sync added | + (needs staleness stamp + query-semantics parity) | ++ (content always live) |
| Latency (typical) | 2–4 RTTs | 3–5 RTTs | A/D, escalated: 4–8 RTTs + embed | ~0–2 RTTs (after 33 min/10k ingest) | ~0–2 RTTs (after ingest) | 1–3 RTTs |
| Privacy footprint | ++ none at rest | ++ none at rest | + transient egress (hosted embed) / ++ local | −− bodies+vectors at rest | − bodies at rest | 0/− headers at rest |
| Implementation complexity | ++ lowest | + moderate | + moderate | −− highest | − high | 0 medium |
| Freshness | = Gmail search (Problem B untested) | = A | = A | −− decays / needs E | ++ bounded lag | content: =A; structure: bounded |
| MCP usability | + | ++ thread map = partiality artifact | + (internal escalation) | + (+ status resource) | + (+ status resource, "what changed" tools) | ++ |
| Quota per query | ~100–300 u | ~150–350 u | escalation ~2,000 u | ~0–40 u + ingest 20 u/msg | ~0–40 u + ingest 20 u/msg | ~50–150 u + ingest 20 u/msg |
| Invariant risk | F2 recall semantics | over-designed expansion | fake-confidence risk | stale-index paradox (§45) | query-semantics drift; 404 resync | scope-vs-storage confusion |

---

## 4. STACK EVIDENCE (TypeScript vs Python) — verified 2026-08-30

The stack decision belongs to synthesis; this section supplies the evidence and a leaning.

### 4.1 Protocol state (affects both languages equally — but matters)

- Current MCP spec revision is **2026-07-28** (previous: 2025-11-25, 2025-06-18, 2025-03-26, 2024-11-05). Verified: https://modelcontextprotocol.io/specification/versioning
- The 2026-07-28 release makes the core **stateless request/response**; introduces **MRTR (Multi Round-Trip Requests)** which *replaces server-initiated elicitation, sampling, and roots*; **deprecates Roots, Sampling, and Logging** (≥12-month offramp); moves **Tasks** into a formal extension; deprecates the legacy HTTP+SSE transport (year-long offramp); adds cacheable list results and auth hardening (CIMD). Verified: https://blog.modelcontextprotocol.io/posts/2026-07-28/
- **Design consequence for MailWeave:** do not architect any retrieval step around MCP *sampling* (e.g., "ask the client's LLM to rerank") — it is deprecated; a rerank needing an LLM must use MRTR or the server's own model access. Progressive disclosure as *multiple cheap tool calls* fits the stateless direction cleanly; stdio remains fully supported for local servers.

### 4.2 Official SDKs

| | TypeScript | Python |
|---|---|---|
| Package(s) | v2 split: `@modelcontextprotocol/server`, `@modelcontextprotocol/client` (+ `node`/`express`/`fastify`/`hono` middleware); v1: `@modelcontextprotocol/sdk` | `mcp` (v2 keeps the FastMCP decorator API) |
| Current stable | **2.0.0, published 2026-07-27** (verified via npm registry; beta cycle through July) | **2.1.1, released 2026-08-25** (verified via PyPI); v1 line at 1.29.1 (2026-08-24) |
| Spec 2026-07-28 support | Yes (v2 stable) | Yes (v2 stable) |
| Transports | stdio, Streamable HTTP | stdio, Streamable HTTP, legacy SSE (superseded) |
| Tier | Tier 1 | Tier 1 |
| Features | tools/resources/prompts, auth helpers, OAuth client helpers; structured tool output | tools/resources/prompts, structured output validation, sampling & elicitation (v1 features; deprecated per spec), OAuth 2.1 resource server, progress/logging |
| Community scale | 13.1k stars | 23.4k stars |
| v1 support window | ≥6 months of fixes post-v2 | critical fixes + security patches |

Sources: https://github.com/modelcontextprotocol/typescript-sdk ; https://github.com/modelcontextprotocol/python-sdk ; https://blog.modelcontextprotocol.io/posts/sdk-betas-2026-07-28/ ; https://pypi.org/project/mcp/ ; npm registry.

**Read:** effective parity. Both are Tier 1 with stable v2 for the current spec (TS shipped v2 stable ~4 weeks earlier and its middleware split is tidier for HTTP deployment; Python's FastMCP decorators are the fastest authoring path; TS repo currently throttles new-contributor PRs "while v2 settles" — mild churn signal on both sides of a major version). SDK maturity is **not** a deciding factor either way. One nuance: a v2-native build starts MailWeave on the stateless spec from day one, avoiding a later migration off deprecated patterns.

### 4.3 Gmail client libraries

| | Node: `googleapis` | Python: `google-api-python-client` |
|---|---|---|
| Latest | 174.0.1 (npm registry; regeneration cadence active) | 2.199.0, **released 2026-08-20** |
| Status | official; **maintenance mode** ("complete… critical bugs and security issues… no new features") | official; **maintenance mode** (same wording) |
| Typing | **written in TypeScript, types out of the box** (per README) | dynamic discovery-based client, no first-party type hints (third-party stubs exist **[not re-verified today]**); package ~50+ MB since discovery docs are bundled |
| Recommended alternative | none for Gmail | Google recommends Cloud Client Libraries "where possible" — **none exists for Gmail**, so this client remains the real option |
| Auth | `google-auth-library` | `google-auth` + `google-auth-oauthlib` |

Sources: https://www.npmjs.com/package/googleapis ; https://pypi.org/project/google-api-python-client/

**Read:** both are maintenance-mode auto-generated wrappers over the same REST surface (MailWeave could even call REST directly and skip both — worth a synthesis thought given how few endpoints we use: list/get/threads.get/history.list/batch). The concrete difference is developer experience: compile-time typed Gmail payload access in TS vs. untyped dict navigation in Python. Gmail's deeply nested `payload.parts` MIME trees are exactly where static types pay off. Note the raw HTTP batch endpoint (F5) has uneven convenience-support in both libraries' modern auth paths **[not verified in detail today]** — budget a small amount of hand-rolled batch code in either language.

### 4.4 Eval-harness ergonomics

- The benchmark driver talks to MailWeave **over MCP stdio**, so the *harness language is decoupled from the server language* — this weakens "pick Python for evals" as an argument for the server itself.
- Python advantages: pandas/notebooks for trace analysis; `pytest`; mature eval frameworks (e.g., Inspect) **[ecosystem familiarity, statuses not re-verified today]**; `sentence-transformers`/Chroma if Loops 4+ ever activate semantic retrieval locally.
- TypeScript advantages: same-language in-process testing of the server (vitest); the official MCP client SDK for driving the server in tests; `promptfoo`-style tooling.
- Pragmatic split that preserves both: **server in one language; traces as JSONL on disk; analysis in anything** (a notebook reading JSONL does not constrain the server stack).

### 4.5 Embedding/vector ecosystem (only relevant to deferred Loops 4+)

Python is clearly stronger for *local* embeddings (sentence-transformers, Chroma-native); Node is serviceable (transformers.js/ONNX Runtime) and equal for *hosted* embedding APIs **[general knowledge, not re-verified today]**. Because §55 defers semantic retrieval until a measured lexical failure, this should carry little weight for the initial stack — but if synthesis weights Loop 4 heavily, it is Python's best argument.

### 4.6 Leaning

**TypeScript, moderately held.** Rationale: (1) typed Gmail payloads where the parsing risk lives; (2) v2-stable MCP server SDK shipped first, with clean stdio + Streamable HTTP middleware; (3) MCP host ecosystem/`npx` distribution ergonomics for end users; (4) the eval harness is language-decoupled over stdio, and JSONL traces keep Python's analysis strengths available anyway. Python remains fully defensible (FastMCP authoring speed, larger SDK community, embedding ecosystem if Loop 4 activates) — if synthesis expects semantic retrieval to arrive early and locally, that tips it back. Final call belongs to synthesis alongside Agents C–F evidence.

---

## 5. Recommendation for Loops 1–3

**Smallest architecture that can test the thesis: Option A + the thread-map slice of Option D** ("A+map"):

1. `messages.list(q)` message-level search — hit IDs are first-class (Loop 1: evidence preservation; the buried-at-37/100 test passes by construction, then the eval proves it).
2. Batched `messages.get` — metadata for candidates, `full` for disclosed evidence (F5: ≤50/batch).
3. `threads.get(format=metadata)` thread map as the partiality artifact — exact totals, positions of hits, explicit expansion handles (Loop 2: progressive disclosure vs full-thread and fixed-K baselines, measuring evidence recall vs context tokens).
4. Fixed-window neighbor expansion as the *baseline* expansion policy, expressed through the map (reply-chain/participant expansion waits for Loop 5 evidence).
5. Lexical-only routing with recoverable broadening (drop constraints, decompose multi-constraint queries per F2, widen date windows) — Loop 3's adaptive layer, no embeddings involved.
6. Instrumentation from day one: per-query JSONL trace (route, RTTs, quota units, tokens disclosed, recall vs seeded ground truth) — this is what makes §55 deferrals decidable later.

**Deferred until a benchmark demonstrates need (per §55):**
- **On-demand semantic (B):** activate only if Loop 4's paraphrase suite shows lexical+broadening recall materially below target. B, not C, is the designated shape when it happens.
- **Metadata cache (F):** only if Loop 5 shows structural queries dominated by repeated thread-map fetches or cross-thread walks (quota/RTT evidence), or Loop 6 wants a cheap freshness probe.
- **History-synced index (E):** only if Loop 6 shows direct-API search freshness lag (Problem B) or scale pain a stateless server cannot absorb. `history.list` at 2 u makes the *measurement* of freshness trivial without building the index.
- **Persistent vector index (C):** rejected as a standalone; if ever needed it is an extension of E.
- Push notifications (`watch`/PubSub), reranking models, decision/event extraction, participant graphs: all wait for their measured failure.

**Key risks of this recommendation:**
1. **Freshness (Problem B) is unhedged.** If direct-API `messages.list(q)` itself lags like #82548, A+map inherits the lag until E/F is built. Mitigation: Loop 6's experiment is cheap (2 u polls + timed sends to the seeded mailbox); run an early smoke version during Loop 0, not after Loop 3.
2. **F2 recall semantics.** Message-scoped `q` can under-recall multi-constraint queries vs. the UI's thread-wide matching. Mitigation is designed in (query decomposition + threadId intersection) but adds router complexity; benchmark must include these cases or we ship a silent recall regression while claiming to fix one.
3. **Paraphrase gap may bite early.** If real queries are paraphrase-heavy, lexical-only Loops 1–3 may look weak before Loop 4 authorizes B. Mitigation: keep B's escalation interface designed (not built) so activation is additive.
4. **Quota-table uncertainty (F7 flag).** If the historical lower per-user throughput were still in force the interactive path is still fine, but Loop 0 must empirically confirm before any bulk operation is planned.
5. **Agent-side tool-call overhead.** Progressive disclosure trades server round-trips for agent round-trips; §57 explicitly lists this as a falsifier. The eval's end-to-end latency comparison against full-thread dumping is the honest check.
6. **7-day refresh-token churn** (F8) on a consumer test mailbox adds dev friction; decide mailbox type (consumer vs Workspace-internal) before Loop 0.

---

## Open questions for synthesis

1. **Stack:** accept the TypeScript leaning, or does weight on early semantic loops (Python's sentence-transformers/Chroma edge) or team/agent familiarity override it? Also: wrap `googleapis`/`google-api-python-client`, or call the ~5 REST endpoints directly with a thin typed client (both official libs are maintenance-mode)?
2. **MCP surface shape** (with Agents C/D): one high-level `search_email` tool with disclosure metadata vs. several primitives (`search`, `thread_map`, `expand`, `fetch`)? How does the thread-map artifact serialize into structured tool output, and does any flow want MRTR?
3. **Session cache policy:** is a per-session in-memory cache (avoid re-paying 20 u for a message the agent just saw) compatible with the stale-index paradox stance, provided entries carry `fetchedAt` and TTL? Where is the line between "cache" and "index"?
4. **Query decomposition ownership** (with Agent C): does the F2 mitigation (multi-list + threadId intersection) live in the deterministic router tier or behind an escalation?
5. **Freshness experiment timing:** promote Loop 6's direct-API freshness smoke test into Loop 0 (my recommendation, risk 1) — agreed?
6. **Loop 4 activation threshold:** what paraphrase-recall delta justifies building B? (Suggest: pre-register the threshold in EVALUATION_PLAN.md to keep §55 honest.)
7. **Test mailbox type** (with Agent F): consumer Gmail in Testing status (7-day token churn) vs. Workspace internal app — who owns provisioning, and does seeding tooling need `gmail.insert`/`messages.import` (a write scope on the *seeding* tool only, keeping MailWeave itself read-only)?
8. **v2-native or v1-compat MCP:** build directly on spec 2026-07-28 stateless semantics (my leaning), or target 2025-11-25-compat for older hosts? Which hosts must MailWeave demo against?

## What I could not verify

1. **Gmail REST latency numbers** — Google publishes none; all wall-clock figures above are estimates pending Loop 0 measurement (F9).
2. **The quota discrepancy** (F7): today's page (messages.get 20 u, threads.get 40 u, 6,000 u/min/user, 80 M/day billing threshold) vs. widely cited historical values (5 u / 10 u / 250 u/sec/user / 1 B-day free tier). Two consistent fetches of the live page are my evidence; I could not reach a second authoritative source (direct fetch blocked; Cloud Console inaccessible from this environment). Treat today's numbers as planning-conservative and probe empirically in Loop 0.
3. **Message ordering of `messages.list` results** (commonly observed newest-first by internalDate) — not explicitly documented on the reference page; do not build correctness on it.
4. **Whether quota units vary by `format`** on `messages.get`/`threads.get` — the quota table is per-method only, so I assumed format-independent cost; unconfirmed edge.
5. **Batch-endpoint convenience support** in current `googleapis` / `google-api-python-client` auth paths (§4.3) — flagged from ecosystem familiarity, not re-verified today.
6. **Third-party Python type stubs** (`google-api-python-client-stubs`) current quality/coverage.
7. **Eval-framework statuses** (Inspect, promptfoo, etc.) as of today — cited as ecosystem familiarity only (§4.4).
8. **Local embedding ecosystem claims** (§4.5) — general knowledge, relevant only to deferred loops.
9. **Workspace-internal OAuth app exemption** from the 7-day Testing-status token expiry — the 7-day rule itself is verified verbatim (F8); the internal-app mitigation is standard practice I did not re-verify against today's docs.
10. **Hosted Gmail MCP internals** (whether `search_threads` truncation is a cap, a cache, or a projection) — unknowable from public docs; MailWeave's baseline comparisons must treat it as a black box (consistent with §36's claim discipline).
11. The earlier summarizer pass that classified `gmail.readonly` as merely "sensitive" was contradicted by the verbatim re-fetch (it is **restricted**); I report the verbatim version and note the summarization hazard as a caution for future doc verification.

---

## SCOPE CORRECTION ADDENDUM (2026-08-30)

**Added by:** research-revision agent, after `docs/SCOPE_CORRECTION.md` (authoritative).
**Nature of this addendum:** §§1–4 above are verified API/SDK ground truth and option analysis. None of it is edited, retracted or renumbered. What changes is §5 ("Recommendation for Loops 1–3"), whose *deferral logic* — "build only after a measured failure" — was the scope misunderstanding the correction repudiates. The option analysis itself was right; the sequencing verdicts attached to it were scoped to a product we are no longer building.

### 1. Status of this document's conclusions

**Stand unchanged.** All of §1 (F1–F9), the six option analyses in §2, the comparison matrix in §3, and the SDK/library/protocol evidence in §4.1–4.4. Also unchanged: every "What I could not verify" item, including the F7 quota discrepancy flag, which is now *more* decision-relevant, not less (§3.4 below).

**Superseded as product scope, still valid as baselines to measure against:**

| Original conclusion | Status now |
|---|---|
| §5: "Smallest architecture that can test the thesis: **A + thread-map slice of D**" | **A+map is the cheap first rung and the cost/latency baseline.** It is no longer the build target. Correction §3 requires an escalation ladder above it. |
| §5 deferral: "**On-demand semantic (B):** activate only if Loop 4's paraphrase suite shows lexical recall below target" | **Superseded.** Correction §4: semantic retrieval is part of the complete product, not "maybe someday." B remains the *designated shape* — that judgement was correct and is now endorsed by correction §4's own description of the architecture. |
| §5 deferral: "**Metadata cache (F):** only if Loop 5 shows structural queries dominated by repeated thread-map fetches" | **Softened.** Correction §5 requires participant/structural/temporal retrieval *capability*; it explicitly does **not** require a persistent participant graph. F is now a live architecture candidate for the structural layer, gated on measured cost rather than on permission to build the capability at all. |
| §5 deferral: "**History-synced index (E):** only if Loop 6 shows freshness lag" | **Partly superseded.** Correction §12 requires freshness to be *tested on real delivered mail* and mitigated **before** freshness claims are made — so E (or another defensible reconciliation mechanism) is conditionally mandatory on a measurement that must now happen early, not "later." The measurement gate survives; the "maybe never" framing does not. |
| §2 Option C verdict: "Dominated… Rejected for Loops 1–3 with confidence" | **Stands as a default, with its permanence removed.** Correction §11: persistent semantic indexing is *optional*, Gmail remains source of truth "unless a properly synchronized architecture is justified." C-without-E is still wrong for the stale-index reason. C-as-an-extension-of-E remains the only defensible form. |
| §4.6: "**TypeScript, moderately held**" | **Materially weakened — see §4/T-RO4.** Its rationale rested partly on §4.5's premise that "semantic retrieval is deferred, so the embedding ecosystem should carry little weight for the initial stack." That premise is now false. The leaning is genuinely reopened. |
| §5 risk 1: "Freshness is unhedged… run an early smoke version during Loop 0" | **Upgraded from a risk note to a requirement** (correction §12). |

**Genuinely invalidated:** the *gating logic* of §5's "Deferred until a benchmark demonstrates need" list — i.e. the rule that a capability may not be built until a benchmark demonstrates its absence hurts. Under correction §1–§5 the escalation ladder is product scope; benchmarks now decide *how* each rung is built and when it fires, not *whether* it exists. The list's individual technical judgements (B not C; F between D and E; C only as an extension of E) all survive.

### 2. Baseline vs product requirement

| Capability | Our recommended baseline / first rung | Complete-product requirement |
|---|---|---|
| Lexical retrieval | `messages.list(q)` message-level search + batched `messages.get` (Option A) | Same — unchanged, and correction §3 keeps it as the cheapest path precisely because Gmail returns message-level hit identity |
| Structural retrieval | `threads.get(format=metadata)` thread map + **fixed-window** neighbour expansion | Reply relationships, participant relationships, temporal relationships, thread position, subject/snippet relevance, and multi-thread relationships (correction §5) — computed live from the thread map where possible |
| Semantic retrieval | *(was: deferred)* | **Required escalation path** (correction §4). On-demand bounded candidate pool + query/candidate embedding at retrieval time is the endorsed shape; persistent index optional |
| Semantic backend | *(was: unscoped)* | **Provider-agnostic interface with a fully LOCAL, zero-API-cost default** (Appendix A.1). Hosted embedding/reranking is opt-in, for benchmarking or explicit user choice, and **may never be required for core functionality** |
| Candidate ranking / reranking | *(was: "waits for its measured failure")* | **Required where candidate ambiguity requires it** (correction §8) — and forbidden on easy queries. An exact `rfc822msgid:` or invoice-number query must never pay for a reranker |
| Internal LLM calls | Zero | **Permitted architecture choice** (correction §8), constrained by A.1: local, or opt-in with a deterministic/local fallback. Core quality may not depend on a paid API |
| Persistent index (vector or full-body) | Rejected by default | **Optional architecture choice** (correction §11). Gmail remains source of truth unless a properly synchronised architecture is justified |
| Freshness | "= Gmail search, untested" | **Tested on real delivered mail; mitigated (e.g. History-based reconciliation) before any freshness claim** (correction §12) |
| Router | Recoverable, untrained | Unchanged (correction §9) |
| Development environment | Seeded test mailbox | **Real Gmail primary from day one** (correction §13); deterministic seeded corpora in a **separate dedicated Gmail account** (A.2) |

### 3. Facts that survive untouched

Architecture can rely on these without re-reading §1:

- **F1** `messages.list(q)` → `{id, threadId}` only; `maxResults` default 100 / max 500; `resultSizeEstimate` is an estimate; **`q` unusable under `gmail.metadata`**.
- **F2** API search is **message-scoped, not thread-wide**; multi-constraint queries can under-recall vs the Gmail UI. Mitigation (decompose → per-constraint `messages.list` → intersect `threadId` sets, 5 u each) is unchanged and is now more important, because a lexical under-recall is exactly what triggers the required semantic escalation.
- **F3** No thread operator in the query language; "search within this thread" = `threads.get` + client-side filter. `rfc822msgid:` is the exact-lookup primitive.
- **F4** `messages.get` formats minimal/metadata/full/raw; `threads.get` returns **whole threads only**, no intra-thread pagination. `threads.get(format=metadata, metadataHeaders=[...])` is the thread-map primitive.
- **F5** HTTP batch: hard limit 100/batch, **>50 not recommended**; a batch of *n* counts as *n* against quota. Round-trips shrink; quota does not.
- **F6** `history.list` semantics; historyId "typically valid for at least a week… in rare circumstances only a few hours"; expired → **HTTP 404 → full resync**. `users.watch` requires re-watch ≤7 days, max 1 notification/sec/user, delivery not guaranteed (Google recommends fallback polling).
- **F7** Quota units as published today: `history.list` 2, `messages.list` 5, `messages.get` 20, `threads.get` 40; **6,000 u/min per user per project**. Derived: ≈300 `messages.get`/min per user. **The discrepancy flag stands and now binds harder** — see §4/T-RO2, where per-user quota directly caps semantic candidate-pool size.
- **F8** `gmail.readonly` is **restricted** (verbatim re-fetch corrected an earlier "sensitive" summarisation); it is the minimal viable scope because of F1. Testing-status OAuth projects get **7-day refresh tokens**.
- **F9** No published Gmail latency figures; RTT is the unit; wall-clock numbers are estimates pending measurement.
- **§4.1–4.2** MCP 2026-07-28 is stateless; **Sampling is deprecated** — no "borrow the client's model" path exists. TS `@modelcontextprotocol/server` 2.0.0 (2026-07-27) and Python `mcp` 2.1.1 (2026-08-25) are both v2-stable for the current spec.
- **§4.3** Both official Gmail client libraries are in **maintenance mode**; calling the ~5 REST endpoints directly remains viable.

### 4. Unresolved tensions — stated, not smoothed

**T-RO1 — On-demand semantic retrieval needs a candidate pool that lexical retrieval must define, and it exists because lexical retrieval failed.**

This is the deepest unresolved problem the correction creates for this document, and it is structural, not a tuning issue.

Correction §4's worked example is a query ("When did we postpone the launch?") whose evidence ("We'll push go-live into Q4") shares **no** content terms with it. Option B's design fetches "a *candidate pool* … via `messages.list` with relaxed `q`". But if the lexical layer cannot find the message, it also cannot reliably *scope* a pool that contains it — the pool must instead be defined by something query-independent: recency window, participant set, label, or thread adjacency. Those are honest scoping choices, but they are **scope limits, not recall guarantees**, and a paraphrased query about an 18-month-old message from an unremembered sender falls outside any bounded pool we can afford.

Constraints architecture must satisfy (not a conclusion to delete):
- The pool's scoping rule must be **declared in the response's partiality metadata** — "semantically ranked over the 400 most recent messages matching `after:2026/02/01`", never "no semantic match found." A silent bounded pool would recreate the exact false-negative failure MailWeave exists to fix, in our own code.
- If the honest recall target requires an unbounded pool, that is the measured justification correction §11 asks for before adopting a synchronised persistent index — the decision is available, it just has to be earned with a measurement rather than assumed away in either direction.
- A cheap middle path worth costing: embed **headers + Gmail `snippet` only** for a wide pool (no body fetch, no 20 u/message), reserving body embedding for a shortlist. Snippets are already returned by search-adjacent calls and are far cheaper on every budget; the quality cost is unmeasured. **[unverified — no measurement exists; propose as a candidate, not a finding.]**

**T-RO2 — The zero-API-cost local default is affordable on latency only for small pools, and quota caps the pool independently.**

Two independent ceilings collide on the escalation path:

- **Quota (verified, F7):** body fetches cost 20 u/message. A 300-message pool = 6,000 u = the entire per-user per-minute budget. A 100-message pool = 2,000 u, one third of it. So candidate pools are quota-bounded at roughly **low hundreds of messages per escalated query**, before any embedding happens. (Under the historical quota reading this ceiling is ~4× higher — which is why the F7 discrepancy must be settled empirically.)
- **Local inference (assessed below):** a 308M-class local model on a developer laptop CPU is fast enough for a query and a few hundred short candidate texts *if* pool size stays in the low hundreds, and is not fast enough to be invisible.

The honest consequence: **the semantic rung will cost seconds, not milliseconds, and it must therefore be reported as an escalation with a stated cost, never run silently on the default path.** That is consistent with correction §8 ("must not run unnecessarily on easy queries") — but it means the product's answer to a hard paraphrase query is measurably slower than its answer to an easy one, and the README must say so rather than quoting only the easy-path latency.

**T-RO3 — Correction §11's stale-index warning and correction §4's semantic requirement pull in opposite directions, and the resolution is not free.**

§11 is right that a persistent semantic index recreates the stale-information failure MailWeave exists to prevent. §4 is right that semantic retrieval is required. The on-demand shape (Option B) resolves the conflict *only* at the pool sizes T-RO1/T-RO2 permit. Beyond that, the options are: (a) accept bounded semantic recall and declare the bound; (b) build E-style history synchronisation and put embeddings on top of it (Option C-as-extension-of-E), paying the sync + privacy + query-semantics-drift costs §2 documents; (c) index only **metadata/headers/snippets** persistently (Option F) and keep bodies live, which bounds both the privacy and the staleness surface but also bounds semantic quality. This document does not have evidence to choose; it has evidence that (a) and (c) are much cheaper than (b) and that (b)'s biggest hidden cost is **reimplementing Gmail's query semantics**, not the sync plumbing.

**T-RO4 — The TypeScript leaning's stated rationale is partly void.**

§4.6's leaning explicitly discounted the embedding ecosystem because semantic retrieval was deferred, while §4.5 stated that "if synthesis weights Loop 4 heavily, it is Python's best argument." The correction weights it heavily by fiat. Local embedding + local reranking is now core product, and the Python ecosystem for it (sentence-transformers, ONNX Runtime, FlagEmbedding, model2vec) is deeper and better-trodden than Node's. Against that, the TS-favouring arguments survive intact (typed Gmail MIME payloads where the parsing risk lives; MCP v2 server SDK; `npx` distribution), and EmbeddingGemma's own launch material names `transformers.js` among supported runtimes, so a Node-local path is real rather than theoretical. **Verdict: reopened, not reversed.** Architecture must decide with local-inference ergonomics as a first-class criterion.

### 5. Local semantic backend — assessment for Appendix A.1

Owner decision A.1 requires a provider-agnostic semantic interface with a **fully local, zero-API-cost default**. This section is the requested assessment: what is actually viable on a developer laptop for on-demand candidate-pool embedding. **All figures were fetched 2026-08-30; verification status is marked per row. Nothing here is a measurement we made — the Loop-0 probe must produce our own numbers on our own corpus and hardware.**

#### 5.1 Candidate local models

| Model | Params | Dims | Context | Notes | Verification |
|---|---|---|---|---|---|
| **EmbeddingGemma** (google) | 308M | 768, MRL-truncatable to 512/256/**128** | 2K tokens | "<15ms embedding inference time (256 input tokens) on EdgeTPU"; "run on less than 200MB of RAM with quantization"; "highest ranking open multilingual text embedding model under 500M on MTEB"; stated to work with "sentence-transformers, llama.cpp, MLX, Ollama, LiteRT, transformers.js, LMStudio…"; Google's own use case list names "your personal files, texts, emails" offline | **VERIFIED** against ai.google.dev/gemma/docs/embeddinggemma and developers.googleblog.com. Note the 15/22ms figure is **EdgeTPU, not laptop CPU** — do not quote it as a CPU number |
| **Qwen3-Embedding-0.6B** | 0.6B | up to 1024, user-defined 32–1024 | **32K tokens** | MTEB multilingual mean 64.33 / English v2 mean 70.70; Apache-2.0; matching **Qwen3-Reranker-0.6B** (32K, instruction-aware) | **VERIFIED** against the HF model card |
| **potion-retrieval-32M** (Model2Vec static) | 32.3M | MRL 32–512 | n/a (static) | MTEB Retrieval **35.06** vs all-MiniLM-L6-v2's **42.92** — i.e. "81.69% of the performance of all-MiniLM-L6-v2"; Model2Vec claims "up to 500 times faster on CPU than the original model"; MIT | **VERIFIED** against the HF model card and the Model2Vec repo. The 500× figure is the project's own claim, not independently measured |
| **all-MiniLM-L6-v2** | ~22M | 384 | 512 tokens | The long-standing cheap default; a third-party 2026 round-up puts it at MTEB ~56.3 and says it "runs in under 10ms on CPU" | Model facts VERIFIED; **the MTEB and 10ms figures are third-party blog claims, [unverified] against a primary source** |
| **bge-m3** | 568M | 1024 | 8192 | Hybrid dense+sparse+multi-vector; third-party round-up MTEB ~63.0 | [unverified] against primary source |

#### 5.2 Local reranking

Correction §8 permits reranking where ambiguity requires it. Local cross-encoder options exist at usable sizes — `qwen3-reranker-0.6b` (0.6B), `bge-reranker-base` (278M), `bge-reranker-v2-m3` (568M), `mxbai-rerank-xsmall` (70M), `gte-reranker-modernbert-base` (149M) — **[model inventory VERIFIED via a 2026 third-party comparison; the comparison's latency table is measured on an NVIDIA H100, e.g. 188ms/query for jina-reranker-v3 scoring 100 candidates, and is therefore useless as a laptop-CPU estimate]**. The important structural fact needs no benchmark: a cross-encoder scores **query×candidate pairs**, so its cost is linear in pool size with no reusable per-document work, unlike a bi-encoder. On CPU this makes reranking affordable only over a **shortlist** (order 10–50), never over the raw candidate pool. That is a design constraint, not a preference.

#### 5.3 What this means for the architecture

1. **A local default is viable and is the right default.** A 308M-class model at <200MB quantised, or a 0.6B Apache-2.0 model with a matching reranker, runs on an ordinary developer laptop. Google's own positioning for EmbeddingGemma is offline personal-email search. Nothing about A.1 is aspirational.
2. **Two-stage is the shape that fits the budgets.** Static/tiny embeddings (potion-retrieval-32M class, ~82% of MiniLM retrieval quality at claimed orders-of-magnitude lower cost) or a small bi-encoder over the whole candidate pool → a cross-encoder reranker over a shortlist of tens. This satisfies "adaptive behaviour and good retrieval" (correction §8) without a paid API and without a persistent index.
3. **Quality gap vs hosted is real but not disqualifying.** A 2026 third-party ranking puts hosted leaders (Gemini `embedding-001` 68.32, Qwen3-Embedding-8B 70.58, `voyage-3-large`, Cohere `embed-v4`) above the sub-1B local tier, with prices ~$0.06–0.15/1M tokens **[third-party, unverified against vendor pricing pages]**. Qwen3-Embedding-0.6B's verified 70.70 English-v2 mean sits close enough that the local default is defensible on quality, not merely on principle. Hosted stays opt-in for benchmarking — which is also the honest way to *measure* the local default's cost, per A.1.
4. **Latency must be measured, not asserted.** Every per-embedding latency figure available today is either EdgeTPU, GPU, or third-party blog. **The Loop-0 probe must measure: model load time (cold start matters for a stdio MCP server), per-text embed latency at our real body lengths, and total wall-clock for a 100/200/400-message pool, on the actual dev laptop.** Until then, treat "seconds, not milliseconds" (T-RO2) as the planning assumption.
5. **The interface, not the model, is the deliverable.** A.1 asks for provider-agnostic. Define one narrow interface (`embed(texts[]) -> vectors[]`, `rerank(query, candidates[]) -> scores[]`) with a local implementation as default and hosted implementations as opt-in adapters. Model choice then becomes a swappable measurement, and the "hosted never required" rule is enforceable in code (and testable: the full test suite must pass with all network egress except `gmail.googleapis.com` blocked).
6. **New non-retrieval costs to budget:** model weights are a download and a supply-chain dependency; cold-start load time is charged to the first escalated query unless the model is pre-warmed; RAM footprint competes with the host application; and model-version changes silently change ranking behaviour, so the model identity and version belong in every trace and in any score provenance string (which §2 Option B already requires be honest rather than fabricated).

### 6. What architecture must now decide that this document treated as deferred

1. **The escalation ladder's shape and triggers** — correction §3's `lexical → structural → semantic → rerank → progressive expansion` as an actual state machine, including which rungs run server-side inside one tool call. (Interacts directly with the seam problem in `ROUTING_OPTIONS.md`'s addendum.)
2. **Candidate-pool scoping policy** (T-RO1): recency? participants? labels? thread adjacency? — and the exact partiality text that declares the bound in every semantically-ranked response.
3. **Whether the pool is embedded from bodies or from headers+snippets** (cost vs quality; currently unmeasured).
4. **Local model + reranker selection**, and whether the two-stage static→cross-encoder shape is adopted. Decide against measured numbers from the Loop-0 probe, not the table in §5.1.
5. **Stack**, now that local inference is core (T-RO4).
6. **Structural layer implementation:** live computation from the thread map (correction §5's preference) vs Option F metadata cache — gated on measured thread-map cost, with the capability required either way.
7. **Freshness mitigation design** (correction §12): is `history.list` reconciliation the mechanism, and what measurement triggers building it? Pre-register the threshold.
8. **Persistent-index decision** (correction §11): if bounded on-demand recall proves insufficient, which of C-as-extension-of-E / Option F / bounded-and-declared is adopted — and what synchronisation evidence would justify it.
9. **Settle the F7 quota discrepancy empirically** before any pool-size or bulk-operation decision is finalised; it moves the semantic pool ceiling by ~4×.
10. **Session cache vs index line** (original open question 3) — now sharper, because embeddings are a cache-like artifact with a much longer useful life than a fetched body.
