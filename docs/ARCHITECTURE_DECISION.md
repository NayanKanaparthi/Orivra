# ARCHITECTURE_DECISION.md — The complete MailWeave architecture

**Status:** authoritative architecture. Frozen for implementation; revisable only through the
findings ledger (`AGENT_LOOP.md`) or a Loop-0 measurement that fires a stated reversal criterion.
**Revision:** **Round-1 repair, 2026-08-30**, against `reviews/ARCH_REVIEW_1.md` (32 findings) and the
architecture-relevant findings of `reviews/CONSISTENCY_AUDIT_1.md`. Every BLOCKER and HIGH is closed or
escalated by name in the **REPAIR LOG (Round 1)** at the end of this file; **§I** records what is escalated to the owner.
**Governed by:** `SCOPE_CORRECTION.md` (owner direction) > `PRODUCT_CONTRACT.md` (what must be true) >
this document (how it is built). **Measured by:** `RELEASE_RUBRIC.md`. **Measured with:** `EVALUATION_PLAN.md`.
**Scope of this document:** components, seams, technology selection, tool names, algorithms, budgets,
and the resolution of every tension `PRODUCT_CONTRACT.md` §9 and the five research addenda handed to
architecture.
**Supersedes:** the archived synthesis in `docs/archive/`, which scoped the project to a minimal
thesis test. That scoping is void (`SC` §1–§2). This document builds the complete product.

Source shorthand as in the contract: `CTX`, `SC`, `RO`, `CD`, `SN`, `RT`, `VR`, `EP`, `RR`.

**Number discipline.** Every figure below is one of: a **[VERIFIED]** fact with a citation; a
**[DESIGN]** budget or cap I am setting, which is a starting value to be tuned by measurement and is
never presented as an observation; or **[PRE-REG]** / **[TBM]** — to be measured, with the Loop-0
check that measures it named. No number in this document is a measurement MailWeave has made.

---

## 0. Decision summary

| # | Decision | Clause served |
|---|---|---|
| D1 | **Stack: Python 3.12+**, `mcp` v2 SDK, direct Gmail REST over `httpx`, `sentence-transformers` 6.x for local inference | §B, N-01/N-02 |
| D2 | **Seam (c): server-enforced floor.** The server runs the whole ladder L0–L6 inside one `mailweave_search` call under a hard budget; only full-thread fetch, deeper views and wider re-runs are client-invoked affordances | T-RC1, C-05, I-4 |
| D3 | **Four MCP tools**, compile-time constant, `structuredContent` mirrored to text, self-truncating | C-07, N-MCP-4/5 |
| D4 | **Disclosure depth shipped: one navigational level (the thread map) + one content escape hatch.** Depth vocabulary is per-message content depth, not navigation. Segment map is the single flagged exception above a measured token boundary, and it trips DISC-05 | T-1, T-CD1, C-06 |
| D5 | **Semantic rung: on-demand, two-stage, fully local.** Stage A static embeddings over a thread-wise-constructed bounded pool; stage B cross-encoder over a shortlist. No persistent index, no vector DB, no disk | C-03, T-RO1/2/3, SC §11 |
| D6 | **Internal models: embeddings and a cross-encoder only. Zero generative LLM calls, enforced in code.** Deterministic declared degradation when the runtime is absent | SC §8, A.1, INJ-06 |
| D7 | **Freshness: `history.list` reconciliation, no Pub/Sub.** Stamps everywhere from day one. The LR recency rung runs off a **persisted non-content `historyId` watermark**, costs `2 + 20n` (not 2), re-checks only a **closed constraint subset** locally and never claims a Gmail `q` match. LR ships **Experimental with a removal gate** (E.2) | T-4, C-09, FRESH-03 |
| D8 | **Quota-native budgeting.** Caps are denominated in Gmail quota units, not call counts, because methods differ 5/20/40 | T-2, RO F7 |
| D9 | **Handles are signed, self-describing, and re-verified on redemption by an *independent* `history.list` liveness probe that does not consume the cached artifact.** A changed thread fails loudly, cache-warm as well as cache-cold | SC §14, N-MCP-3, MCP-06 |
| D11 | **One process-wide quota governor and a stated concurrency model.** Per-query accountants nest inside a process-level token bucket sized to the measured per-minute ceiling; contention is an in-band declared wait or refusal, never an upstream 429 | GMAIL-05, PERF-01, MCP-02 |
| D12 | **Every ID the ladder retrieves has exactly one disposition: `disclosed` or `withheld`.** The `withheld` list is *computed as a set difference at envelope time*, not populated by hand, so no cap anywhere in the ladder can silently drop a hit | I-1, EV-01, C-01 |
| D10 | **Traces are type-level redacted.** The personal profile has no trace type capable of holding mail text; the profile is derived from the authenticated account, fail-closed | N-05, SEC-06, T-SN1/2 |

---

## A. System architecture

### A.1 Component map

```
                       MCP client (Claude Code / other host)
                                   │  stdio, MCP 2026-07-28, stateless
        ┌──────────────────────────▼──────────────────────────────────────┐
        │ mcp_surface        4 constant tools; structuredContent ⇄ text;  │
        │                    per-response size ceiling + self-truncation  │
        └───────┬───────────────────────────────────────────┬────────────┘
                │ ParsedQuery                                │ handle redemption
        ┌───────▼────────┐                          ┌────────▼─────────┐
        │ query_analysis │                          │ handles          │
        │ Tier-1 parser  │                          │ mint/verify/     │
        │ features only  │                          │ redeem (HMAC)    │
        └───────┬────────┘                          └────────┬─────────┘
                │                                            │
        ┌───────▼────────────────────────────────────────────▼─────────┐
        │ ladder  — the escalation state machine (L0…L6)               │
        │   budget_accountant (per query: quota units, api_calls,      │
        │     http_requests, wall-clock, texts) nested inside the      │
        │     process-wide quota_governor (A.5c) and disposition_ledger│
        │     (A.7a: every retrieved ID → disclosed | withheld)        │
        │   ┌──────────┬───────────┬───────────┬──────────┬─────────┐  │
        │   │ lexical  │ structural│ semantic  │ ranking  │ recency │  │
        │   │ L0-L3    │ L4        │ L5        │ L6       │ LR      │  │
        │   └────┬─────┴─────┬─────┴─────┬─────┴────┬─────┴────┬────┘  │
        │        │           │           │          │          │       │
        │   ┌────▼───────────▼───────────▼──────────▼──────────▼────┐  │
        │   │ sufficiency — signals + verdict + stop/escalate rules │  │
        │   └────────────────────────┬──────────────────────────────┘  │
        └────────────────────────────┼─────────────────────────────────┘
                                     │ EvidenceSet (+ RetrievalReport, always)
        ┌────────────────────────────▼─────────────────────────────────┐
        │ representation — E2 reply-chain floor → E4 query-scored fill  │
        │   depth assignment, declared stripping, fence+nonce,          │
        │   map-carrier assembly, affordance minting, self-truncation   │
        └────────────────────────────┬─────────────────────────────────┘
                                     │
        ┌─────────────┬──────────────▼──────────────┬──────────────────┐
        │ gmail_client│ semantic_backend            │ trace            │
        │ 6 REST eps  │ embed()/rerank() interface  │ profile-bound    │
        │ pager,batch │ single-flight model load    │ emitters;        │
        │ retrier,    │ local default; in-memory    │ Redacted[str]    │
        │ decoder,    │ vector LRU; no disk         │ JSONL sink       │
        │ quota meter │ hosted adapters opt-in      │                  │
        ├─────────────┴─────────────────────────────┴──────────────────┤
        │ quota_governor (process-wide token bucket) · watermark store │
        │ (historyId only — no mail content, no subjects, no addresses)│
        └──────┬───────────────────────────────────────────────────────┘
               │ auth (OAuth loopback + PKCE S256, one scope, 0600 store)
               ▼
        gmail.googleapis.com  +  oauth2.googleapis.com (refresh only)
        ── runtime egress allowlist: exactly these two hosts, nothing else ──
        (the model host is reachable only from the separate `mailweave setup-models`
         command; the server process loads weights offline from a pinned local path — D.8)
```

### A.2 Data flow for one `mailweave_search` call

1. **Parse.** `query_analysis` produces a `ParsedQuery`: Gmail operators it can prove, residual
   terms, participant entities (address-normalised), date references, interrogative type, an
   answer-type lexicon (`when`→date-like tokens, `how much`→numeric/currency, `did we decide`→decision
   verbs), a confidence tier (`exact | filtered | weak | non_lexical`) and a `paraphrase_risk`
   heuristic (RT §1.2, §6). No model runs here.
2. **Ladder.** The `ladder` executes rungs against `budget_accountant`. Each rung returns candidates
   with a **mechanical provenance record** — the exact `q` executed, the method, the rung — never a
   bare score.
3. **Sufficiency.** After every rung, `sufficiency` recomputes signals (A.7) and emits
   `sufficient | insufficient | ambiguous`, which drives stop-or-escalate.
4. **Structural enrichment.** For every **hit-bearing** thread, one `threads.get(format=metadata)`
   builds the thread map: reply tree, participant index, temporal order, positions. All structural
   signals are computed live from these maps. No persistent graph (SC §5). Hit-bearing threads are
   mapped up to `max_hit_threads`; hits in threads beyond that cap are **withheld records**, never
   silent drops (A.7a).
5. **Representation.** `representation` allocates the token budget along the published degradation
   ladder of A.9a: hits at `body_clean`, reply-chain floor **present at a declared depth**,
   query-scored fill to the budget, everything else a stub row (or a declared collapsed run) in the map.
6. **Envelope.** The **disposition ledger** is closed: `withheld := H − disclosed`, computed here as a
   set difference over the IDs the ladder actually retrieved, not assembled by the rungs that dropped
   them; a non-empty residue with no `withheld` record is an internal error, not a shipped response
   (A.7a). Mail-derived text is fenced with a per-response nonce; connector-voiced fields are
   assembled from typed values only; affordances are minted as concrete `{tool, args}` pairs; the
   response is measured against the size ceiling and self-truncated if needed.
7. **Trace.** One trace row per top-level call, emitted through the profile-bound type.

**There is never a bare empty result.** If no rung produced evidence, the same envelope is returned
carrying a `RetrievalReport` instead of hits: queries executed, constraints dropped and why, hit
counts per rung, `empty_diagnosis` (which single dropped constraint restores results), rungs *not*
tried and why, and the affordances that would try them (C-08, ROUTE-01/04).

### A.3 The seam — server vs calling agent

`ROUTING_OPTIONS` offered (a) all-server, (b) all-client-for-expensive-rungs, (c) hybrid with a
server-enforced floor. **Committed: (c).** Option (b) is inadmissible because I-4 is a release
criterion and (b) makes it hostage to client quality (RT §3, failure mode 2) — which is the exact
mechanism of the original bug: an agent concluding "not found" from one impoverished response.

| Runs inside one server call, always, under budget | Offered as a typed affordance |
|---|---|
| L0–L3 lexical, incl. decomposition/intersection and one-at-a-time relaxation | Full-thread fetch (`view=body_full`, all positions) |
| LR recency reconciliation on recency-cued queries | Deeper content view of named messages |
| L4 structural expansion within `max_source_threads` | Re-run with a **wider** semantic pool or a different pool scope |
| L5 semantic escalation within `max_pool_threads` | Sibling-thread pivots beyond `max_source_threads` |
| L6 ranking / cross-encoder rerank on the shortlist | Attachment inspection |
| Disclosure assembly | Segment expansion in a very large thread |

The cost of this seam is stated plainly: **a local model is a default-build dependency** (RT
addendum T-RC1). Accepted. Its absence degrades declaredly (D6), never silently.

### A.4 Auth and token handling

- One scope, literally: `https://www.googleapis.com/auth/gmail.readonly` (N-04, SEC-01). A CI
  string-search gate fails the build on any other `googleapis.com/auth/` literal in server code.
- Installed-app loopback redirect on `127.0.0.1`, PKCE S256 unconditionally, no OOB, no custom
  schemes (SN §3). Token store `0600` inside a `0700` directory; never in the repo tree.
- **Read client posture: Production-unverified.** The 7-day Testing-status refresh expiry
  ([VERIFIED] SN §2) is unacceptable on a path SC §13 puts in daily use (T-SN4).
- **Profile derivation (N-05, SEC-06) — two independent conditions, both required.** At startup,
  `users.getProfile(me)` → `emailAddress` → `SHA-256(salt ‖ address)`. Profile = `seed` **only if
  both** hold: **(i)** the digest equals the configured `seed_account_hash`, **and (ii)** the
  credential in use carries `client_id == seed_client_id`, i.e. the process is running on the
  **harness OAuth client** — which by A.2/B.9 is in Testing status with a test-user allowlist
  containing only the seed account, so Google itself refuses consent for any other mailbox on it.
  Either condition failing ⇒ `personal`. Unset config ⇒ `personal`.
  This closes the config-forgery path: editing `seed_account_hash` to the personal address's digest
  satisfies (i) but cannot satisfy (ii), because the personal mailbox **cannot hold a token for the
  harness client at all** (ADV-205). The control is Google-side, not code-side.
  **Salt provenance.** Generated once, on first run, as `secrets.token_bytes(32)`; stored inside the
  `0600` token store beside the refresh token; never in config, never in the repo, never logged.
  Rotating or losing the salt changes every digest and therefore **fails closed to `personal`**.
  **`getProfile` failure is fatal.** If the startup `users.getProfile` call fails for any reason
  (network, expired refresh token, revoked grant), the profile is *underivable*, and an underivable
  profile cannot be made safe by defaulting: the server exits with `auth_profile_underivable` (D.11)
  and serves nothing. PF-8 covers both the forgery attempt and the fatal-startup path.
- Distribution keeps every user personal-use-exempt by requiring a BYO Google Cloud project
  ([VERIFIED] SN §2, restricted-scope verification/CASA analysis).

### A.5 Gmail client layer

A thin typed layer over exactly six REST endpoints, called directly over `httpx`, not through
`google-api-python-client`. Rationale: both official clients are maintenance-mode generated wrappers
([VERIFIED] RO §4.3); six endpoints do not justify a ~50 MB discovery-bundled dependency; and hand-rolled
HTTP batch is needed in either language anyway (RO F5). `google-auth`/`google-auth-oauthlib` are still
used for the OAuth dance. Responses are parsed into Pydantic models hand-written from the REST schema,
which gives the payload typing that was TypeScript's strongest argument (§B.5). Because this decision
moves pagination, batch, backoff and decoding in-house, it carries its own reversal criterion **R5**
(§B.8) — a hand-rolled client with no reversal path was a review finding (ADV-214).

**The surface, complete, with the rate the accountant charges** (ADV-201). No endpoint may be called
that is not on this table; a CI grep gate fails the build on any other `gmail/v1` path literal.

| Endpoint | Rate | Used by |
|---|---|---|
| `users.messages.list` | **5 u** [VERIFIED RO F7] | L0–L3 lexical, L1b decomposition, L5 pool participant probes |
| `users.messages.get` | **20 u** [VERIFIED RO F7] | hit bodies, LR candidate re-check, attachment-metadata reads (`format=full`) |
| `users.threads.get` | **40 u** [VERIFIED RO F7] | thread maps (hit, structural, pool) |
| `users.history.list` | **2 u** [VERIFIED RO F7] | LR rung; handle-liveness probe (A.10) |
| `users.labels.list` | **1 u** [TBM — PF-3; planning value from the published usage-limits table] | once per process: resolves `label:<name>` → `labelIds` so LR's client-side re-check can evaluate a `label:` constraint without guessing (A.7a, D.9). Nothing else consumes labels |
| `users.getProfile` | **1 u** [TBM — PF-3; same source] | startup profile derivation (A.4) and the harness account-pinning assertion (B.9) |

`users.messages.attachments.get` is **removed from the surface for this release** (ADV-207): it returns
attachment *bytes*, which B-04 and E.3 exclude, and `mailweave_get_attachment(mode:"metadata")` is
served entirely from the carrying message's `payload.parts` tree (filename, mimeType, size, partId)
via `messages.get(format=full)`. Removing it also narrows the audited call surface for SEC-02/SEC-07.

**A.5a Transport components — first-class, not one-line responsibilities.**

- **Pager.** `pageToken` walking with **`resultSizeEstimate` never used as a truth source**
  (GMAIL-04; RO F1). Page size is set explicitly (`maxResults`, [DESIGN] 100, Gmail's own default —
  RO F1) rather than defaulted, and the ladder's page budget is `max_pages_per_query = 1` [DESIGN].
  Every executed query records `scan_scope{q, page_size, pages_fetched, ids_returned, more_pages}`
  and that record is emitted in the response (A.7a, D.2) — GMAIL-04's guard requires scan scope to be
  declared once paging stops, and `more_pages: true` always carries a widening affordance.
- **Batcher.** HTTP batch capped at 50 sub-requests ([VERIFIED] RO F5: hard limit 100, >50 not
  recommended; a batch of *n* costs *n* quota units). Batching changes `http_requests`, never
  `api_calls` or quota — see the counter split below.
- **Retrier.** Exponential backoff with jitter on 429/5xx: base 250 ms, factor 2, jitter ±25 %,
  `max_retries = 3`, and a hard `max_backoff_total_ms = 1500` that is additionally clamped to the
  *remaining* `max_server_ms`/`max_semantic_ms` for the rung in flight. **Every HTTP attempt is
  charged to the accountant, including the attempt that 429'd**, because the upstream quota was spent.
  When the bound is reached the rung stops and the response carries `upstream_rate_limited` in-band
  with the rungs not reached (D.11, AD-03) — it is never a bare failure and never a silent retry loop.
- **Decoder.** The MIME/charset/part-selection boundary — specified in **D.4a**, not left implicit.

**A.5b Two counters, never conflated** (ADV-106). A network counting proxy sees one HTTP request per
`batch` call whatever *n* is; quota is charged per sub-request. Those are different quantities and the
document previously used one word for both.

| Counter | Definition | Observable by | Bounds it carries |
|---|---|---|---|
| `http_requests` | HTTP requests leaving the process | the harness counting proxy, exactly | `max_http_requests = 24` [DESIGN]; **OBS-04's agreement tolerance binds on this counter only** |
| `api_calls` | logical Gmail sub-requests (a batch of *n* = *n*) | server-side count; proxy can bound it by parsing batch bodies | `max_api_calls = 80` [DESIGN] (this is what the former `max_gmail_calls` meant) |
| `quota_units` | `api_calls` × the rate table above | **not observable in any Gmail response** — a multiplication, therefore a **diagnostic**, never a headline (ADV-211, A.11) | `max_quota_units` (A.7) |

AD-04's "median network API calls ≤ 3" is not a cost bound under batching — 1 list + 1 batch of 10
gets + 1 batch of 12 maps is 3 HTTP requests and 665 u. That is escalated to the owner in §I.

**A.5c The quota governor and the concurrency model** (ADV-107). The per-query `budget_accountant`
refuses a call that would exceed *that query's* `max_quota_units`; it says nothing about the
per-minute per-user ceiling, which is where 429s actually come from.

- **Process-wide token bucket.** Capacity and refill are set to the per-minute per-user-per-project
  budget — [VERIFIED] published 6,000 u/min (RO F7), **re-set from PF-3's measurement** at G0. Every
  charge passes the governor before the query accountant.
- **Reserved floor.** `floor_reserve = 900 u` is never lent to an escalating query, so a concurrent
  query can always run the recoverability floor (A.7). A query that cannot get floor capacity within
  `max_server_ms` returns the RetrievalReport with `process_quota_refused` — a truthful empty, not a
  429 (C-08).
- **Concurrency: bounded parallel, `max_concurrent_queries = 2` [DESIGN].** The server is a single
  asyncio event loop; there are no threads, so the in-process LRU (A.10), the watermark file and the
  HMAC key are guarded by ordinary `asyncio.Lock`s and need no thread-safety story. A third
  concurrent `mailweave_search` is admitted but blocks at the governor; if it waits at all, its
  response carries `budget_caps_hit: ["process_quota_wait"]` with `waited_ms` (AD-03). MCP-02's
  "second concurrent client" case is therefore defined behaviour, not an accident.
- **Single-flight model loading.** Cold loads are guarded by a per-model `asyncio.Event`: the second
  concurrent escalation awaits the same load future rather than starting its own. `max_model_rss_mb`
  is set from PF-4; a request that would require loading a *second distinct* model while the first is
  resident is refused in-band with `semantic_unavailable{why:"model_rss_bound"}` rather than swapping.
- **Mid-rung timeout contract.** When `max_server_ms` or `max_semantic_ms` expires inside a rung:
  results already retrieved are emitted; the rung's unfinished work becomes `not_tried` with an
  affordance; `budget_caps_hit` names the clock that fired; and **any ID already in `H` but not
  disclosed becomes a `withheld` record** (A.7a). Partial escalation is a declared state, not an
  undefined one.
- **Suite-level budget.** PF-3 drives to 429 *by design* and will contend with anything else on the
  project. §F states its exclusive window and the suite's own quota budget.

**Honest arithmetic.** At the published rate a fully semantic-escalated query costs ≈2,177 u (A.7),
so the 6,000 u/min ceiling admits **≈2.7 fully-escalated queries per minute**; an L0/L1-only query
costs 305–790 u, i.e. ≈7–19 per minute. The governor turns that ceiling into a declared wait instead
of an upstream 429. This number is published in the README's latency/cost section, not hidden.

### A.6 Query analysis

Deterministic, model-free (RT §1.2). Produces `ParsedQuery`. Two facts constrain it hard:

- **Gmail `q` is message-scoped**: all terms must match within a *single* message, and there is no
  thread operator ([VERIFIED] RO F2, F3). A query whose constraints are satisfied jointly by
  *different* messages of one thread therefore goes through **L1b decomposition**: one `messages.list`
  per constraint (5 u each), intersect on `threadId`, then resolve. This is a first-class rung, not a
  fallback.
- `rfc822msgid:` is the exact-lookup primitive and the strongest stop signal.

**A.6a Time and timezone policy** (ADV-204). Date handling was previously unspecified in four places
that all depend on it — relative-date resolution, `after:`/`before:` boundaries, `internalDate`
ordering, and the freshness stamps. One rule, stated once:

1. **Reference zone.** The Gmail API exposes no account timezone, so relative expressions ("last
   Tuesday", "yesterday", "this quarter") resolve in the **host's IANA zone** (`TZ`, falling back to
   `UTC` when unset). The zone actually used is declared in `asked_for.parsed.timezone`. MailWeave
   never silently assumes the account's zone equals the host's.
2. **Declared absolute window.** Every resolved date reference is emitted twice: as the Gmail
   operator form (`after:2026/05/01`, date-valued) **and** as `asked_for.parsed.window_utc:
   {start, end}` in RFC 3339 UTC. The reader can always see what was actually searched.
3. **Boundary safety.** Gmail's `after:`/`before:` are date-valued and their boundary zone is not
   documented for our account. Relative-date windows are therefore widened by
   `date_margin_days = 1` [DESIGN] on each side, declared in `asked_for.enforced` as
   `{"date_window_widened": "±1d, timezone-boundary safety"}`. Explicit user-supplied absolute dates
   are **not** widened. **PF-14** measures the real boundary behaviour on the seed account; if it is
   deterministic the margin drops to 0 and the change is recorded. EP's F2 family already uses
   ≥48 h margins for this reason, so the policy is compatible with the suite.
4. **Comparisons are UTC-epoch.** `internalDate` ordering (D.6), LR's client-side date re-check (D.9)
   and `window_containment` compare integer epoch milliseconds. No local-time arithmetic anywhere.
5. **Stamps.** `fetched_at`, `verified_at` and every trace timestamp are RFC 3339 UTC with `Z`.

### A.7 The retrieval ladder

Costs below are **corrected** to include the thread maps that R-01 (position within thread) and R-05
(`stated_total`) require and that the previous table omitted (ADV-108), and to price LR at its real
cost (ADV-101). A thread map is fetched **at most once per query**; the accountant dedupes across
rungs, so the map column is a per-query total, not a per-rung one.

```
Rung  Action                                              Cost model              Stop / escalate
L0    exact-operator query (rfc822msgid | quoted phrase   5 u + ≤5×20 u           STOP per D.3 rule 1
      | structured identifier — A.8 defines these)        + maps                  (branch-dependent)
L1    filtered lexical: every provable operator           5 u + ≤10×20 u          STOP if hit_count∈[1,5]
      (maps fetched in parallel with bodies, not after)   + maps                  ∧ term_coverage=1
                                                                                  ∧ drop_depth=0
                                                                                  ∧ answer_type_presence
L1b   decomposition/intersection for multi-constraint     ≤3 × 5 u                feeds L1
L2    relax: drop ONE constraint per step, enumerable     ≤min(k,6) × 5 u         records constraints_dropped
L3    broaden: in:anywhere, dates ×4, from:→from|to       ≤2 × 5 u
LR    recency reconciliation (history.list + re-check)    2 u + ≤8×20 u           recency-cued queries only
L4    structural expansion from thread maps               ≤4 × 40 u
L5    semantic escalation (two-stage, local)              ≤25×40 u + 2×5 u + CPU  gated, see D.5
L6    ranking / cross-encoder rerank on shortlist         0 Gmail, CPU            gated, see D.7
L7    disclosure assembly                                 0

maps  hit-bearing thread maps, shared by L0/L1/L1b/L2/L3  ≤12 × 40 u = 480 u      never capped below
                                                                                  the hit-thread count
                                                                                  without a withheld
                                                                                  record (A.7a)
```

**Global caps per top-level query [DESIGN — starting values, tuned at G0/CG-*, enforced in code]:**

| Cap | Value | Note |
|---|---|---|
| `max_quota_units` | **1,200** normal / **2,400** semantic-escalated | derived below, not asserted |
| `max_api_calls` | **80** | the quantity the old `max_gmail_calls = 40` was trying to bound; 40 was arithmetically impossible against the rung caps (ADV-106) |
| `max_http_requests` | **24** | proxy-observable; OBS-04 binds here |
| `max_pages_per_query` | **1** (`page_size` 100) | `H` is defined over the pages actually fetched; `more_pages` is declared with a widening affordance (A.7a) |
| `max_hit_threads` | **12** | maps for hit-bearing threads. **Never** silently exceeded: hits in threads beyond it become `withheld` records |
| `max_source_threads` | **4** | sibling/structural expansion threads that become additional `source` objects (A.9(5)). This is the cap A.9(5) previously called `max_map_threads` |
| `max_pool_threads` | **25** | **renamed** from the pool sense of `max_map_threads` (ADV-003). Pool membership creates **no** `source` and **no** map row — it is disclosed by count and scoping rule in `retrieval_report.pool` |
| `max_pool_messages` (`max_embed_texts`) | **300** | stage-A texts |
| `max_rerank_pairs` | **25** | **also the declared shortlist size `k`** that defines `H` from the scored retriever (A.7a, §H-5) |
| `max_relax_probes` | **min(k_constraints, 6)** | scales with parsed constraint count (ADV-105); untried drops are reported, see D.2 `empty_diagnosis.status` |
| `max_recency_fetch` | **8** | LR's `n`; IDs beyond it are `withheld` |
| `max_body_fetches` | **10** (L1) / **5** (L0) | hits beyond the cap are **disclosed as stub rows in their thread map**, at declared reduced depth — not withheld, not dropped |
| `max_server_ms` | **7,700** (L0–L4) | RTT-bound. **2,000 until 2026-09-09**, a [DESIGN] planning value; raised by owner decision on deadline run 3 after live v0.1 acceptance failed twice on it. Amendment A13, and not a passed registered validation — see there |
| `max_semantic_ms` | **6,000** (L5–L6) | CPU-bound, separate by design (RT addendum §5.3) |
| `max_concurrent_queries` | **2** | A.5c |
| `generative_llm_calls` | **0** | hard, not configurable |

**The budget arithmetic, shown** (the previous 1,500/3,000 were unexplained — ADV-201):

```
L0            5 +  5×20                       =   105 u
L1            5 + 10×20                       =   205 u
hit maps     12×40 (shared across L0–L3)      =   480 u
L1b           3×5                             =    15 u
L2            6×5                             =    30 u
L3            2×5                             =    10 u
LR            2 +  8×20                       =   162 u
L4            4×40                            =   160 u
                                                -------
normal-path worst case                            1,167 u   ⇒ max_quota_units = 1,200
L5            25×40 + 2×5 (participant probes) = 1,010 u
                                                -------
semantic worst case                               2,177 u   ⇒ max_quota_units = 2,400
```

**The recoverability floor, costed** (ADV-212). L0 + L1 + hit maps + L1b + L2 + L3 + the
RetrievalReport = **845 u** (**365 u** if the client also declines maps, which it may not, because
R-01/R-05 need them). `floor_quota_units = 845` is a published constant. A client may lower budgets
but **may not lower them below the floor**: a `budget.max_quota_units` under 845 is **clamped up to
845** and the clamp is reported in the `budget` block as `budget_clamped{requested, applied, why}`
(AD-03, D.11). It is never accepted-and-then-overrun, and never silently refused.

Exhausting any cap produces a `budget` block naming the cap, the rungs not reached, and the
affordances that would reach them (AD-03) — **and, per A.7a, a `withheld` record for every hit the cap
prevented from being disclosed.**

### A.7a Hit disposition — how `H ⊆ R` is made structurally true

*(BLOCKER ADV-001. The previous draft used the word `withheld` exactly once, as an empty array in a
schema sketch, and no rule anywhere populated it. That is the reintroduction of the original bug: a
retrieval stage identifying a message and a later stage removing it with no marker.)*

**Definition of `H` (the hit set).** `H` is the set of message IDs the retriever returns **as evidence
candidates**, namely:

- **(H-lex)** every ID returned by every executed Gmail `messages.list` — on the pages actually
  fetched — at **any** rung: L0, L1, L1b, L2, L3, and **the L5 pool-construction participant probes
  of D.5 step (b)**, which are `messages.list` calls like any other and are covered by this clause
  (ADV-109). In the rubric's words (EV-01), this clause explicitly includes "**the
  relaxation/broadening `messages.list` calls and the participant `from:`/`to:` probes that build a
  semantic candidate pool**";
- **(H-hist)** every `messagesAdded[].message.id` LR retrieves from `history.list`;
- **(H-thr)** every message row an executed `threads.get` returned — **added by amendment A2**
  (`ARCHITECTURE_AMENDMENTS.md`, forced by R-RETR-004). D.5 builds the semantic candidate pool
  thread-wise and its first-priority source arrives through this endpoint and no other, so without
  this clause a legitimate top-k selection out of that pool names IDs that entered no clause at all
  and the disposition ledger refuses it. The principle the three observed clauses share is that **an
  ID may only enter `H` by having been observed in a real Gmail response**; which endpoints those are
  is a fact about which rungs exist, not a property of `H`;
- **(H-sem)** from any **scored retriever** — quoting the canonical clause now carried identically by
  `PRODUCT_CONTRACT.md` I-1 and `RELEASE_RUBRIC.md` EV-01, not paraphrasing it: *"the candidates that
  pass the retriever's selection threshold — the **shortlist that enters the disclosure candidate
  set** — **not** every row that received a score. The shortlist size and the selection rule are a
  **declared, pre-registered parameter** reported in the retrieval report, never a free per-run
  implementer choice, so `|H|` cannot be shrunk to make this invariant pass."* MailWeave's declared
  parameter is **`rule: "top-k by stage-A cosine"`, `k = max_rerank_pairs = 25`**, reported in every
  response as `retrieval_report.shortlist{rule, k, size}`. The canonical clause's "selection
  threshold" is therefore instantiated here by a **published constant**, never by an implementer-set
  score cut-off — which is what makes EV-01's *deflationary* guard bite (§H-5, ADV-109, CONS-003).

**`H` is not the scored pool.** The pool is disclosed separately and by construction, in its own
`retrieval_report.pool{scope_rule, thread_count, message_count, window, why}` block, and its full
membership is enumerated **by ID in the trace** (`semantic.pool_ids[]`) so EV-01 can be joined against
a real set rather than the implementer's account of one. This is the canonical resolution of the
I-1 / DISC-04 / RANK-04 collision, and it is applied identically in the contract and the rubric.

**Definition of `R`.** IDs present in the response at **any** depth — a stub row inside a thread map
counts, a member of a declared collapsed run counts — **plus** IDs carried by a `withheld` record.

**The disposition rule.** Every ID in `H` has exactly one disposition. There is no third state.

```
withheld := H − disclosed          # computed at envelope time (A.2 step 6), as a set difference,
                                   # NOT populated by the rung or the cap that dropped the ID
assert H == disclosed ∪ withheld   # enforced in code before the response leaves the process;
                                   # a non-empty residue is an internal error, never a shipped response
```

That inversion is the structural fix. Previously `withheld` could only be right if every future cap
remembered to write to it; now a cap that forgets produces a **failing assertion**, not a silent loss.

**Withheld record shape** — `{id, thread_id, why, cap, affordance}`, never a bare number (R-06):

| `cap` | Arises when | `affordance` |
|---|---|---|
| `max_hit_threads` | the hit's thread was beyond the 12-map cap, so no map exists to carry a stub row | `mailweave_thread_map{thread_id}` |
| `max_pool_threads` / `max_pool_messages` | a D.5 step-(b) probe returned IDs in threads the pool cap excluded | `mailweave_search{pool:{max_threads: 50}}` |
| `max_recency_fetch` | LR returned more `messageAdded` IDs than `n` | `mailweave_get_messages{message_ids:[…]}` |
| `max_quota_units` / `max_api_calls` / `max_server_ms` / `max_semantic_ms` | a cap or clock fired mid-rung before the ID could be mapped or fetched | `mailweave_search{budget:{max_quota_units: …}}` or `force_rungs` |
| `disclosed_token_ceiling` | the response hit the hard token ceiling **after** the A.9a degradation ladder was exhausted — i.e. the ID could not be carried even as a collapsed-run member | `mailweave_thread_map{map_id, segment: n}` |
| `partial_source_failure` | a sub-request inside a `threads.get`/`messages.get` fan-out failed | retry affordance naming the failed IDs |

**What is *not* a withheld case.** A hit that was fetched-as-stub rather than fetched-as-body is
**disclosed** (depth is declared per R-04 with an unabridged path), not withheld. Confusing depth
reduction with omission is the error that makes `withheld` lists meaningless.

**Scan scope is a first-class field** (ADV-001(b/c), ADV-304, GMAIL-04). `H` is defined over the pages
actually fetched, and the response says so:

```jsonc
"scan_scope": [
  {"q":"from:amy launch after:2026/05/01","rung":"L1","page_size":100,"pages_fetched":1,
   "ids_returned":46,"more_pages":true,
   "affordance":{"tool":"mailweave_search","args":{"scan":{"max_pages":3}}}}
]
```

`more_pages: true` with no affordance is non-conforming. Unfetched pages are **outside `H`** by this
declared definition — that is the honest position, because MailWeave never saw those IDs — and the
declaration is what keeps it honest rather than convenient.

**Worked trace of the review's own reproduction.** `from:amy launch after:2026/05/01`; L1's
`messages.list` returns 46 IDs across 31 threads on one page, `more_pages: true`.

- 12 hit-bearing threads are mapped (480 u). Every message of those 12 threads — including all their
  hits — appears as at least a stub row. Say that is 19 of the 46 hits: **disclosed**.
- Of those 19, the top 10 by mechanical rank are at `body_clean` (200 u); the other 9 are stub rows
  with `depth:"stub"`, a declared reduction and an `unabridged` affordance: **disclosed**.
- The remaining 27 hits live in the other 19 threads. Each gets a `withheld` record naming
  `cap:"max_hit_threads"`, `why:"31 hit-bearing threads; 12 mapped"`, and a `mailweave_thread_map`
  affordance: **withheld**.
- `scan_scope` declares one page of 100 fetched with more available, plus its widening affordance.
- `H = 46 = disclosed(19) + withheld(27)`. The assertion holds; EV-01's exact set assertion passes;
  nothing was silently dropped. The same accounting runs at L2, L3, LR and the L5 probes.

### A.8 Sufficiency evaluation

Signals, all computable without a model (RT §5.1): `hit_count` (actual page, never
`resultSizeEstimate`), `exact_signal_match`, `term_coverage`, `constraint_drop_depth`,
`participant_authorship`, `window_containment`, `duplicate_thread_concentration`, `empty_diagnosis`,
and — **only once a scored retriever has run** — score margin. Scores are never fabricated for
lexical hits (CTX §20, RANK-03).

#### A.8a `exact_signal_match` — normative definition

*(BLOCKER ADV-004. This predicate is the pivot of the design — D.3 rules 1 and 4, D.5's firing
condition, D.7's prohibition, A.7's L0 stop — and the previous draft never defined it. An undefined
kill-switch is the document's largest gameability lever: a broad reading makes six criteria easy while
shrinking the denominators of the two criteria meant to catch that.)*

`exact_signal_match` is **true iff exactly one of three enumerated branches holds**, each of which is
an *identity* claim about a token, not a *rarity* claim about a word:

| Branch | Condition | Rationale |
|---|---|---|
| **E-a** `rfc822msgid` | the parsed query contains an `rfc822msgid:<…>` term, it was executed verbatim, and `hit_count == 1` | RFC 822 message ids are globally unique identifiers. This is identity, not retrieval |
| **E-b** verbatim phrase | a quoted phrase of **≥3 tokens after stopword removal** was executed as a Gmail quoted phrase; `hit_count ∈ [1,3]`; **and MailWeave itself verifies** the phrase appears as a contiguous substring of the hit's cleaned body or subject under NFKC + case-folding + whitespace collapse | Gmail's phrase matching is not documented as literal; we do not take its word for a stop decision |
| **E-c** structured identifier | the query contains a token matching the **published structured-identifier lexicon** — an RFC-822 message id, an invoice/order/ticket/PO/SKU-shaped token (≥6 chars, ≥2 digits, no dictionary hit), a tracking number, or an IBAN-shaped token — executed as a quoted single-token query, with `hit_count ∈ [1,3]` | These are the "invoice-number query" SC §8 names. The lexicon is a closed, published, testable list |

**False in every other case.** In particular, the phrase "unique token" from the previous draft's L0
row is **withdrawn as a qualifying signal**: corpus frequency is never consulted, and no
frequency threshold may create an exact-signal match. That closes the dial an implementer could
otherwise have widened to make the whole ladder stop early (ARCH_REVIEW §3, degenerate build item 1).

`exact_signal_match` is a **required trace field**, recorded with its firing inputs:
`{fired: bool, branch: "E-a"|"E-b"|"E-c"|null, phrase_tokens: n, hit_count: n,
verified_locally: bool}`. It is emitted whether it fires or not.

**Pre-registered firing-rate bound.** Its firing rate **per EP family** is reported at G0 and bounded:
`exact_signal_match` fires on ≤ `[PRE-REG at G0]` of F11 (lexical-trap) cases and ≤ `[PRE-REG at G0]`
of F4 (paraphrase) cases. A rate above the registered bound is a finding, not a tuning note — because
a broad predicate does not fail the rubric, it *removes cases from it*. G0 additionally publishes the
`exact_signal_match` firing rate **inside CG-SEM's SEM-OFF reference distribution**, so the
contamination ARCH_REVIEW §3 identifies (cases where SEM-ON and SEM-OFF behave identically contribute
zero to `semantic_gain` in both arms) is visible as a number rather than hidden.

#### A.8b `answer_type_presence`, and the ordering bug

One addition this architecture makes, to attack T-RC2: **`answer_type_presence`**. For interrogative
queries with a decision or temporal cue, check mechanically whether any hit's cleaned body contains a
token of the query's answer type (a date-like token for *when*, a numeric/currency token for *how
much*, a decision verb for *did we decide*). Absence downgrades the verdict to `insufficient`
regardless of `hit_count`. This is a model-free proxy for CRAG's retrieval evaluator ([VERIFIED] RT §0,
arXiv:2401.15884), and it is the only pre-escalation signal that can see the confident-but-wrong
lexical result.

**It is computed before any stop rule is evaluated, not after** (ADV-004). The previous ordering had
D.3 rule 1 kill the whole ladder on `exact_signal_match` *before* rule 4 ever consulted
`answer_type_presence` — i.e. it disabled the architecture's only answer to T-RC2 on exactly the
confident-but-wrong cases T-RC2 exists for. D.3 now evaluates `answer_type_presence` as **rule 0**,
and only branch **E-a** (identity) may stop unconditionally. See D.3.

**Its base rate must exist before the design leans on it** (ADV-104). A predicate that is true 97 % of
the time is not a signal; it is a constant. **PF-13** measures the base rate of
`answer_type_presence == true` on a random sample of the seed corpus, **per interrogative class**
(*when* / *how much* / *did we decide* / other), at G0. The measurement runs against quote-stripped
bodies specifically, because signature blocks, scheduling text and un-stripped
`On Tue, 3 Sep 2026 … wrote:` attribution lines all carry date-like tokens; if quote-stripping does
not reach them the predicate is inert as a downgrade and only its **under**-trigger rate matters.
That is a stated risk of the hypothesis, not a hidden one.

**Settled by** — corrected (ADV-104, CONS-016). The instruments are **CG-AD** (the escalation
confusion table, published with both off-diagonal cells: over- and under-escalation rates, and
`escalation_cost`) and **CG-SEM** (the F11 `semantic_gain` bar and the F12 over-escalation ceiling),
plus the **F11/F12 trigger ablation**, which has now landed at `EVALUATION_PLAN.md` §7.4 and is a
published cell of gate **CG-AD** (§13.4). The
previous citation — "PF-9/CG-EP" — was wrong twice over: PF-9 checks Gmail `q` message-scoping and
CG-EP measures evidence preservation; neither measures escalation triggering. **The PF-9 reference is
deleted.**

### A.9 Representation and disclosure

Shipped policy (the D-var of `CD` §9, promoted to product by SC §6):

1. **Evidence tier.** Every hit at `body_clean`, subject to the A.9a ladder.
2. **Reply-chain floor (E2) — non-negotiable in *membership*, declared in *depth*.** Each hit's reply
   parent and direct children are **always present in the response**; they are never absent, never
   reduced to a bare count, and never dropped to make room. What *is* budget-bounded is their
   **depth**, along the published ladder of A.9a, with the depth used declared per message. See the
   honesty note below — this wording is a correction, not a softening (ADV-003).
3. **Query-scored fill (E4)** over the remaining budget. Mechanical score over: participant match
   (address-keyed), subject/snippet term overlap, temporal proximity to a hit or to a query date-ref,
   thread-position adjacency, decision-cue lexicon match. Fixed published weights; the reason string
   names the firing components and their values.
4. **Everything else** in every mapped thread: a stub row in the map — position, from-address, date,
   subject-if-changed, reply parent, hit flag, and a snippet on rows above a visibility threshold —
   or, above the ceiling, a **declared collapsed run** carrying its member count and an expansion
   affordance (R-06, PART-05).
5. **Multi-thread (E5).** Sibling threads (normalised subject, participant overlap, forward detection,
   or additional lexical hits) appear as **separate sources**, each with its own mini-map and its own
   hits at `body_clean`, capped by **`max_source_threads` = 4**. *Pool membership is not a source*:
   the L5 pool creates no `source`, no mini-map and no stub rows (A.7a), which is what removes the
   287-stub-row arithmetic contradiction the review found.
6. **Temporal segmentation (E3)** applies only inside the segment map, above the size boundary (D.4).

**Semantic scoring inside disclosure (T-CD3): reuse only, never trigger.** If L5 already ran, the
query vector and candidate vectors exist in-process, so the E4 fill re-scores at zero marginal cost.
Disclosure **never** initiates embedding on its own. Three constraints the previous wording missed
(ADV-110):

- **`score.basis` is mandatory** wherever a numeric score appears: it names *what text was embedded*
  (`"subject+participants+snippet"`, `"subject+participants+body_head_400"`, or `"body_clean"`). A
  cosine computed over subject+participants+snippet, attached to a message disclosed at `body_clean`,
  reads as body-level similarity unless the basis is stated. RANK-03 requires the mechanism to be
  named, and *what was embedded* is the load-bearing half of the mechanism.
- **No mixed-scale ranking inside one comparison.** Vectors exist only for pool rows; E4 fill
  candidates include messages from touched-but-not-pooled threads, which have none. Within a single
  fill, **all** candidates are ordered by `mailweave/mechanical-v1`. A reused cosine may enter the
  ordering as a declared additive component **only if it exists for every candidate in that
  comparison**; otherwise it is carried as an informational field with `score.ordering_effect: false`.
  Ranking two candidates against each other on different scales is exactly the fabricated
  comparability RANK-03 exists to prevent.
- **"Zero marginal cost" holds only on the intersection** (pool rows ∩ fill candidates). Outside it
  the rule is mechanical scoring — never "embed a bit more", which is the trigger T-CD3 forbids.

### A.9a The degradation ladder under the token ceiling

*(BLOCKER ADV-003. Re-derived: a 40-message thread with 6 hits puts ~24 messages at body depth —
at CD's 300–800-token planning range, ~11,200 tokens — against a 9,000-token hard ceiling; at the
former 1,000-token `body_clean` soft cap, ~24,000. The floor, the map and the ceiling were
arithmetically incompatible on a routine input, and "the response self-truncates explicitly rather
than dropping the floor" did not say what actually degrades.)*

**Three changes make the commitments compatible without weakening any of them.**

1. **The pool is not a source.** Removed the 287-stub case entirely (A.9(5), A.7a).
2. **Body budget tightened, ceiling given a declared overflow.** `body_clean` soft cap **600 tok**
   (was 1,000); head-truncation step at **250 tok**. The **normal hard ceiling stays 9,000 tok**
   [DESIGN, set by PF-6]. If and only if the E2 floor's *membership* cannot be carried within it, the
   response raises to a **declared overflow ceiling of 12,000 tok** — still far below the [VERIFIED]
   25 k Claude Code cap — and says so in-band:
   `"ceiling": {"normal": 9000, "applied": 12000, "why": "E2 floor membership"}`.
   Floor membership is the **only** thing that may raise the ceiling.
3. **Precedence is published.** Under the ceiling, degradation happens in this order, first to last,
   and each step is declared in `reductions[]` and named in `budget_caps_hit`:

```
 1. E4 query-scored fill        body_clean → snippet → stub
 2. Sibling-source stub rows    stub rows → declared collapsed runs (with affordance)
 3. Hit bodies beyond the top-k body_clean(600) → head-truncated body_clean(250) → snippet
 4. E2 floor bodies             body_clean(600) → head-truncated body_clean(250) → snippet
 5. Hit-bearing-thread stubs    stub rows → declared collapsed runs (never removed)
 6. Overflow ceiling 9,000 → 12,000, declared, only for floor membership
 7. Split by source: lowest-ranked sources become declared `not_included_sources[]` entries,
    each with a `mailweave_search`/`mailweave_thread_map` affordance
 8. If a hit still cannot be carried even as a collapsed-run member: a `withheld` record with
    cap `disclosed_token_ceiling` (A.7a). This is the only path by which a hit leaves the payload.
```

**Never degraded, at any step:** membership of any ID in `H` in either `disclosed` or `withheld`;
`stated_total`; `scan_scope`; the `withheld` list itself; `retrieval_report`.

**Re-derivation on the review's own case.** 40-message thread, 6 hits, ~18 floor messages, 24 bodies:
at 400 tok each that is 9,600 + 40 stubs × 40 = 1,600 = **11,200 tok** — fits the 12,000 overflow with
the floor at full `body_clean`. At the 600-tok cap the same shape is 14,400 + 1,600 = 16,000, so steps
3–4 fire: hit and floor bodies head-truncate to 250 tok → 6,000 + 1,600 = **7,600 tok**, inside the
normal 9,000 ceiling with room. **The ladder terminates on this input**, which is what the previous
policy could not demonstrate.

**Honesty note on T-CD2 — what survives and what does not.** The reviewer is right that a message
truncated away is as absent as a message dropped, and a label is not a mitigation. So the floor's
guarantee is restated at the level where it is *true*: **membership plus a snippet**. A reversing
reply ("Actually, let's not — we're pushing to Q4") is typically short, and `snippet` carries Gmail's
first ~200 characters, so in the common case the reversal is *visible at the degraded depth*, not
merely counted; where it is not, it is one named affordance away and the truncation is declared in
place. That is a real mechanism and a bounded claim. It is **not** the claim "the agent will notice",
which T-CD2 already refused to make.
**Reversal criterion for T-CD2 — now non-empty** (ADV-003(d), ADV-302, CONS-007): the F17
decision-reversal family (requested as a change to `EVALUATION_PLAN.md` §4.7) is run at **each
degradation tier** — floor at `body_clean`, floor head-truncated, floor at `snippet`. If accuracy at
the tier the budget actually produces is not better than Baseline F(±2) at equal token budget, **the
floor is not doing its job at that depth**, and the response is a design change (fewer hits at body,
a higher ceiling, or a narrower fill), escalated per §I — not a quieter claim.

### A.10 Handle minting and redemption (MCP is stateless — SC §14)

`map_id` is a server-minted opaque handle passed as an ordinary tool argument. Format: base64url of
`{v, key_epoch, account_hash, thread_ids[], fetched_at, history_id, mapping_digest, ttl}` with an
HMAC over the whole payload. It is **self-describing** (no server-side session) and **verified, not
trusted** on redemption.

**Key persistence** (ADV-212). The HMAC key lives in the `0600` token store, not in process memory
alone, and carries a `key_epoch`. A restart therefore does **not** invalidate outstanding handles, so
the previous design's misattributed `handle_expired`-on-a-fresh-handle disappears. A deliberate
rotation bumps `key_epoch` and produces a distinct, truthful error class **`handle_key_rotated`**
naming the re-derivation call (D.11).

#### Redemption, in order

1. **Verify HMAC, `key_epoch` and TTL** [DESIGN: 30 min]. Failures produce `handle_invalid`,
   `handle_key_rotated` and `handle_expired` respectively — three distinct classes, each with the
   re-derivation call.
2. **Independent liveness probe — this is the check that can actually fail.**
   `history.list(startHistoryId = handle.history_id, historyTypes = [messageAdded, messageDeleted,
   labelAdded, labelRemoved])`, **2 u**. If any returned history record touches a `thread_id` the
   handle names ⇒ loud **`handle_stale`**, naming what changed (messages added or removed, with
   counts) and the re-derivation call. If the call 404s (expired `historyId`, [VERIFIED] RO F6) ⇒
   `handle_stale_unverifiable`: the LRU is **bypassed**, step 3 is a forced live `threads.get`, and
   the in-band record says the staleness could not be verified from history.
   *This probe reads a different resource from the one the cache holds, so a cache hit cannot make it
   pass.* The previous design recomputed `mapping_digest` from the very cached map that produced it —
   `digest(x) == digest(x)`, true by construction — so `handle_stale` could never fire on a cache
   hit and MCP-06's mutate-then-redeem test could not fail (BLOCKER ADV-002).
3. **Fetch the named threads.** Gmail stays source of truth (N-03). The in-process LRU may serve this
   step **only** when step 2 returned clean.
4. **Recompute `mapping_digest`.** Mismatch ⇒ `handle_stale`. On a cache hit this comparison is
   **tautological and is labelled as such in the trace** (`digest_check: "cache_tautology"`); it is
   defence-in-depth against a cold-fetch bug, never the verification. Step 2 is the verification.

#### The LRU, specified

Previously it had no TTL, no size and no invalidation rule anywhere in the document.

- **Key** `(thread_id, history_id_at_fetch)`; **TTL 60 s** [DESIGN], always ≤ the handle TTL;
  **max 64 thread maps**; entries are evicted on any `handle_stale` naming their thread, and on any
  `handle_stale_unverifiable`.
- **`fetched_at` is the cache entry's own fetch time and is never restamped.** A response served
  through the LRU additionally carries **`verified_at`** — the timestamp of step 2's liveness probe.
  Two fields, both true: *this content was read at T₀; it was verified unchanged at T₁*. Restamping
  `fetched_at` to now would assert a freshness the response does not have (FRESH-03, violations
  required = 0).
- **Test obligation.** MCP-06's mutate-then-redeem case is executed **cache-warm as well as
  cache-cold**, as two distinct cases; a warm-only pass is not a pass. Registered as **PF-15**.

`mailweave_get_messages` also accepts bare Gmail message IDs, so no affordance ever *requires* a
handle (R-07).

### A.11 Instrumentation and the trace/redaction pipeline

Schema v2 extends RT §6 with the fields the complete product needs: per-rung latency, `http_requests`
and `api_calls` (A.5b) and derived `quota_units`, `embed_texts`, `rerank_pairs`, `model_id`+
`model_revision`, `pool_scope`, pool sizes and **`pool_ids[]`** (A.7a), `shortlist{rule, k, size}`,
`levels_traversed`, `disclosed_tokens_est`, `budget_caps_hit[]`, `sufficiency_verdict`,
`exact_signal_match{fired, branch, phrase_tokens, hit_count, verified_locally}` (A.8a),
`answer_type_presence{value, class}`, `disposition{hit_count, disclosed, withheld[]}` (A.7a),
`freshness{history_id, watermark_source, reconciled, lag_observed_ms?}`, and `eval_join`.

**Quota units are a diagnostic, never a headline** (ADV-211, OBS-02). No Gmail response carries a
quota figure; every unit number MailWeave states is a multiplication of a *published* table by a call
count — a self-report by construction. Therefore: the **harness-derived headline cost metric is
`api_calls` by method**, proxy-observed and multiplied by the **PF-3-calibrated** table at analysis
time; `quota_units` appears in traces and responses labelled `diagnostic`; and any published quota
figure carries the PF-3 calibration date. `http_requests` is the only counter the proxy can assert
exactly, and OBS-04's agreement tolerance binds on it alone (A.5b).

**Redaction is a type-level property, not a filter.** There are two trace record types. The
`PersonalTrace` type has *no field* whose type can hold mail-derived text; the emitter is statically
bound at startup by the derived profile (A.4). Every mail-derived string in the process is carried in
a `Redacted[str]` newtype whose `__str__`/`__repr__` render `<redacted:len=N:sha8=…>` under the
personal profile — which is what makes SEC-06's **error-path** requirement achievable rather than
aspirational, since exception formatting goes through the same `__repr__`.

Defaults follow `SN` §4.3, which is stricter than A.3 and stays the default (T-SN2): no snippets, no
subjects, no header values, no display names, no addresses, and **no raw query strings** — query text
is stored as `query_features` plus a salted hash. A.3's snippet exception is a narrow gated escape
hatch: `--diagnose=<finding-id>` names the failure being diagnosed, redaction is applied by code (hard
length cap, address/URL/number masking), output goes to `traces/personal/diagnose/<finding-id>/`
which is gitignored, and the flag value is recorded in the trace so its use is self-documenting. It
never widens to subjects, addresses or display names.

**ID-based forensics (T-SN1).** `mailweave inspect <trace_id>` re-fetches the trace's message IDs
live from Gmail into memory and prints to the terminal only, never to disk. This must be built in
Loop 0, *before* the pressure arrives — a rule that is expensive to obey at high frequency is a rule
that gets bypassed.

---

## B. The stack decision

### B.1 Why this was genuinely open

`RO` §4.6 leaned TypeScript "moderately", and `RO` addendum T-RO4 correctly voids part of that
rationale: §4.5 discounted the embedding ecosystem *because semantic retrieval was deferred*. A.1 and
SC §4 make local inference core. The leaning is reopened, and the deciding criterion changes from
"typed MIME payloads" to "which ecosystem actually runs local embedding **and** reranking on a
developer laptop, today, with pinnable ungated models".

Everything below was fetched **2026-08-30** from primary registries and model cards.

### B.2 Python local-inference runtime — [VERIFIED]

| Package | Version | Released | Note |
|---|---|---|---|
| `sentence-transformers` | 6.0.0 | 2026-08-18 | one library covering static, bi-encoder **and** CrossEncoder; ONNX + OpenVINO backends documented (sbert.net efficiency guide) |
| `model2vec` | 0.9.0 | 2026-08-12 | the static-embedding tier |
| `onnxruntime` | 1.29.0 | 2026-08-17 | |
| `transformers` | 5.16.1 | 2026-08-26 | |
| `llama-cpp-python` | 0.3.35 | 2026-08-17 | GGUF path |
| `optimum` | 2.3.0 | 2026-08-04 | ONNX export/quantisation |
| `FlagEmbedding` | 1.4.2 | 2026-08-24 | BGE family |

Models, all usable through the single `sentence-transformers` API:
`minishlab/potion-retrieval-32M` — **MIT, ungated**, 32.3M params, MTEB Retrieval **35.06** vs
all-MiniLM-L6-v2's **42.92** (81.69%), "orders of magnitude faster on both GPU and CPU" (model card,
[VERIFIED]); `Qwen/Qwen3-Embedding-0.6B` — Apache-2.0, ungated, 32K context ([VERIFIED] RO §5.1);
`BAAI/bge-reranker-base` and `mxbai-rerank-xsmall-v1` cross-encoders; `google/embeddinggemma-300m`.

### B.3 Node / TypeScript local-inference runtime — [VERIFIED]

| Package | Version | Published | Note |
|---|---|---|---|
| `@huggingface/transformers` | 4.2.0 | **2026-04-22** | last release **>4 months** before today; `next` dist-tag still on `4.0.0-next.11` (2026-03-30) |
| `onnxruntime-node` | 1.29.0 | 2026-08-24 | actively maintained |
| `node-llama-cpp` | 3.20.0 | 2026-08-11 | has **both** `createEmbeddingContext()` and `createRankingContext()`/`rankAndSort()` |
| `@modelcontextprotocol/server` | 2.0.0 | 2026-07-27 | |
| `googleapis` | 176.0.0 | 2026-08-18 | |

Model coverage in Node is **real, not theoretical**: `onnx-community/embeddinggemma-300m-ONNX` ships a
`@huggingface/transformers` snippet with `dtype: fp32|q8|q4` and MRL truncation to 512/256/128;
`onnx-community/Qwen3-Embedding-0.6B-ONNX` ships a `pipeline("feature-extraction", …)` snippet and
shows ~18k downloads/month; `Xenova/bge-reranker-base` ships a `pipeline("text-classification", …)`
snippet, i.e. cross-encoder reranking works. transformers.js 4.x adds a native WebGPU runtime and
q1/q2/q4/q8 dtypes.

**Static tier in JavaScript — the corrected fact** (ADV-103). The Model2Vec repository documents
Python and integrations with `sentence-transformers` and LangChain and names no first-party
JavaScript/TypeScript path ([VERIFIED], github.com/MinishLab/model2vec); `@huggingface/transformers`
carries an **open, unimplemented** feature request for model2vec support
([VERIFIED, re-checked 2026-08-30], github.com/huggingface/transformers.js issue #970). But
model2vec-distilled models **are** published in ONNX form on the Hub (e.g.
`futur/Qwen3-Embedding-0.6B-model2vec-onnx`, [VERIFIED, re-checked 2026-08-30]), and
`onnxruntime-node` 1.29.0 is actively maintained — so a static tier in Node is *awkward and
unsupported*, **not impossible**. The previous draft's sentence, "that tier exists only in Python",
overstated the evidence, and the whole stack decision rested on the overstatement. It is withdrawn.
The corrected deciding argument is in **B.8**.

*Deleted from this section:* the "second signal" about `@huggingface/transformers`'s four-month
release gap (ADV-303). B.8 declares that a transformers.js release is **not** a reversal criterion; a
factor that new evidence cannot move was never load-bearing, and keeping both sentences was
incoherent. The release cadence is recorded in the table above as a fact and carries no weight in the
decision.

### B.4 MCP SDK maturity — parity, slight Python edge

`@modelcontextprotocol/server` **2.0.0** (2026-07-27) vs Python `mcp` **2.1.1** (2026-08-25) — both
v2-stable against spec 2026-07-28, both Tier 1. TS shipped v2 stable four weeks earlier; Python has
shipped more recently. Sampling is deprecated in both and we build on neither ([VERIFIED] RO §4.1,
VR §7). **Not a deciding factor.**

### B.5 Gmail client typing — the TS advantage has largely evaporated

`googleapis` 176.0.0 is written in TypeScript with first-party types. But
`google-api-python-client-stubs` **1.40.0 (2026-08-22)** is actively maintained and generates
**TypedDicts for the response schemas** from the same Google Discovery Documents that produce the TS
types ([VERIFIED], PyPI project page). Caveats that survive and are recorded honestly: the stubs are
stub-only (unusable at runtime, so `from __future__ import annotations` / `TYPE_CHECKING` discipline
is required), third-party, and slow to infer. **This architecture sidesteps the caveats entirely** by
calling the six REST endpoints directly and hand-writing Pydantic models for the payloads we parse
(A.5) — which gives runtime-validated types, better than either generated client, and puts a
validation boundary exactly where the MIME parsing risk lives.

### B.6 Distribution

`uv` 0.12.7 (2026-08-27, [VERIFIED] PyPI) makes `uvx mailweave` the Python equivalent of `npx`, with
lockfile-pinned dependencies for contract **N-08** / rubric **NFR-04** (the previous "NFR-08" cites a
criterion that does not exist — CONS-029). Node's `npx` ergonomics advantage is now marginal;
neither ecosystem avoids native binaries once local inference is in the default build
(`onnxruntime-node` and `onnxruntime` are both native).

### B.7 What I could not verify

- **CPU latency for any candidate model on a developer laptop.** Every figure in existence is
  EdgeTPU (EmbeddingGemma's "<15 ms at 256 tokens"), GPU (the H100 reranker table), or a third-party
  blog. sbert.net documents ONNX and OpenVINO backends but the excerpt exposed no CPU speedup number.
  **[TBM — PF-4.]** T-RO2's "seconds, not milliseconds" remains the planning assumption.
- Whether `onnx-community/embeddinggemma-300m-ONNX` is downloadable without an HF token. The
  upstream `google/embeddinggemma-300m` **is gated** ("review and agree to Google's usage license",
  license `gemma`, [VERIFIED]); the ONNX mirror showed no gate but did not confirm anonymous
  download. **[TBM — PF-5.]** This is why EmbeddingGemma is *not* the default (D5).
- `bge-reranker-base`'s exact licence text was not re-fetched today. **[TBM — PF-5.]**
- Relative throughput of `sentence-transformers`+ONNX vs `transformers.js` on identical hardware.
  Nobody has measured it for us. **This is now measured: PF-4b runs a Node arm on the same pool and
  the same laptop** (ADV-103). Without it R1 and R2 could never fire, because both require evidence
  about the path we did not choose, and PF-4 only ever exercised the path we did.

### B.8 DECISION

**Python 3.12+.** `mcp` v2 (stdio), direct Gmail REST over `httpx` with hand-written Pydantic
payload models, `sentence-transformers` 6.x as the single local-inference API, `onnxruntime` as the
CPU backend, `uv` for pinned reproducible installs.

The decision turns on one asymmetry that **the corpus can actually check** — restated after review
(ADV-103), because the previous formulation ("the static-embedding tier exists only in Python") both
overstated its source and evaporated under the design's own fallback plan:

> **D5 needs three inference jobs — a cheap wide-pool stage A, a shortlist cross-encoder, and the
> ability to swap either one — and Python covers all three behind a single API. No JavaScript stack
> covers all three behind any single API.**

Why that is the deciding fact and not a taste:

1. **The source says "or", so "static" was never the requirement.** `RETRIEVAL_OPTIONS` addendum
   §5.3(2) reads "**static/tiny embeddings (potion-retrieval-32M class) *or* a small bi-encoder**
   over the whole candidate pool → a cross-encoder reranker over a shortlist". Stage A's requirement
   is *cheap enough for the pool*, not *static*. Converting that disjunction into a necessity was the
   error.
2. **The cost previously attributed to a Node bi-encoder was the wrong cost.** T-RO2's arithmetic
   (300 × 20 u) is a **quota** cost, and thread-wise pool construction already eliminated it (T-RO2's
   own resolution row). The residual cost is CPU, and B.7 states plainly that no CPU figure exists for
   any candidate model on a laptop. That claim is withdrawn; PF-4b will produce the number.
3. **What actually survives is the API-surface asymmetry, and it is [VERIFIED] on both sides.**
   `sentence-transformers` 6.0.0 covers static, bi-encoder **and** `CrossEncoder` through one library
   with one release cadence (B.2). Node needs `@huggingface/transformers` for the bi-encoder and the
   text-classification reranker, `onnxruntime-node` for a hand-exported static tier, and
   `node-llama-cpp` for the GGUF path — three runtimes, three model universes, three failure modes.
4. **The asymmetry is stable under our own fallbacks; the old one was not.** D.5's stated remedy if
   `potion-retrieval-32M` misses its bar is to swap stage A to `Qwen3-Embedding-0.6B` or
   `EmbeddingGemma-300m`. In Python each swap is a **model-id change under the same API**, so SEM-03's
   contract ("a second implementation registers without touching retrieval logic") holds across the
   whole swap set. In Node the same swap crosses a **runtime** boundary. The previous argument
   evaporated the instant the swap happened; this one does not — which is precisely the property a
   load-bearing criterion must have.

**The quality headroom is a real risk and is recorded as one, not waved past:** potion's MTEB
Retrieval **35.06** against all-MiniLM-L6-v2's **42.92** is an ~18 % relative deficit *on retrieval*,
in a product whose release invariant is zero false not-found, with stage A required to place true
evidence in the top 25 of ~300 rows. R1 below is the criterion that acts on it.

Node's one live advantage — first-party TS types on `googleapis` — is one we decline anyway for a
six-endpoint surface (§B.5).

**Reversal criteria — any one of these reopens the decision, and I will treat it as a finding, not an
embarrassment:**

- **R1 (rewritten — single conjunct, design consequence).** PF-4 shows stage A does not clear its
  quality bar on our corpus (`recall@shortlist` below `[PRE-REG at G0]`). **Consequence: a design
  change, not a stack change** — in order, (i) widen the shortlist (`max_rerank_pairs`), (ii) shrink
  the pool and declare the reduced bound per T-RO1, (iii) replace stage A with a bi-encoder
  (`Qwen3-Embedding-0.6B`) under the same API. Each step is measured before the next.
  *The previous R1 required a second conjunct — "a Node-viable bi-encoder meets the latency budget" —
  that PF-4 was never going to establish, so R1 could not fire regardless of what stage A did
  (ADV-103.3). A reversal criterion that cannot fire is worse than none.*
- **R2 (now firable).** **PF-4b** shows the Python path cannot embed a 300-text pool within
  `max_semantic_ms` on the dev laptop **while the Node arm on the same pool and hardware can**. PF-4b
  exists specifically so this conjunct can be established or refuted (ADV-103.3).
- **R3.** Real interop testing (PF-7) finds a host that works with TS MCP servers and not Python ones.
- **R4.** Content **decoding or part selection** in Python produces a defect class that typed TS
  payloads would have prevented, observed twice in the findings ledger. *(Narrowed from "MIME
  parsing": Gmail parses MIME server-side and returns a structured payload tree, so the residual risk
  is decoding and part selection — D.4a — not MIME parsing. B.5's claim is corrected accordingly.)*
- **R5 (new — the hand-rolled Gmail client, ADV-214).** Two or more GMAIL-02 / GMAIL-04 / GMAIL-05
  findings traceable to **transport** code (batch construction or parsing, pagination, backoff,
  base64url/charset decoding) ⇒ adopt `google-api-python-client` for transport, keeping the Pydantic
  models as the payload validation boundary, which is where B.5's argument actually holds. Declining
  the official client moved pagination, batch, retry and decoding in-house against three mandatory
  criteria; that decision now has a reversal path of its own, and A.5a names those components as
  first-class rather than as one-line responsibilities.

Not reversal criteria: transformers.js shipping a release; ecosystem sentiment; a faster hosted model.

### B.9 Eval harness language and coupling

**Python, separate package (`mailweave-harness`), separate repo directory, separate GCP project and
OAuth client, scope `https://mail.google.com/`, pinned to the seed account** (A.2, SN §2.5). Harness
language is decoupled from server language in principle (it talks MCP stdio), and Python is chosen
here for pandas/pytest/notebook analysis, not because the server is Python.

**Coupling rules, enforced structurally by CI — not by review** (ADV-213). PROC-03 explicitly
excludes inspection as the enforcement mode ("verified **structurally** … not by inspection alone; a
reviewer finding otherwise raises a BLOCKER regardless of behavior"), and the previous wording was
exactly the excluded mode. The mechanisms:

- **Directory and process isolation.** `server/` and `harness/` are separate top-level packages with
  separate `pyproject.toml` files. The server process is launched with its working directory inside
  `server/`, and in the E2E container `harness/` is not mounted into the server's filesystem
  namespace at all.
- **CI gate 1 — dependency graph.** An `import-linter` contract, `server` **must not** import
  `harness` (forbidden-module contract, transitively), run as a required job. Violation fails the build.
- **CI gate 2 — grep sweep as a job.** `manifest`, `seed_map`, `ground_truth`, `harness` and the
  manifest path literals are searched across `server/**`; any hit fails the build.
- **CI gate 3 — scope literal sweep.** Any `googleapis.com/auth/` literal in `server/**` other than
  `gmail.readonly` fails the build (A.4).
- The counting-proxy configuration lives only in `harness/`; the server receives a URL from an env var
  and knows nothing about what is on the other end.

**The coupling rules themselves:**
- The harness imports **nothing** from the server package except a versioned `response_schema.json`
  and the frozen extraction adapter (EP §3.2).
- Ground-truth manifests live only in the harness and are unreadable by the server (PROC-03).
- Gmail call counting is done by a **counting proxy** the harness runs, with the server pointed at it
  by env var — never from server self-reports (PERF-02, OBS-02/04).
- Baselines A/A′, B, C, D, E-matched, E-generous and F(±1/±2/±5) are permanent harness fixtures
  (EP §8, PROC-04).
- **Harness OAuth posture (T-SN4): Testing status with the test-user allowlist containing only the
  seed account.** This makes personal-mailbox consent to the write-scoped client impossible *at
  Google's side*, a hard control no code bug can bypass. The cost is the [VERIFIED] 7-day
  authorization expiry, i.e. weekly interactive re-consent. Accepted because corpus regeneration is a
  gate-time activity (E2E-02), not a per-commit one; mitigated by a one-command `harness auth --refresh`
  and a pre-gate checklist item. The read client stays Production-unverified (A.4).

---

## C. Tension resolutions

Every tension named in `PRODUCT_CONTRACT` §9 and in the five research addenda. "Settled by" names the
Loop-0 preflight (§F) or the capability gate that arbitrates where evidence cannot yet decide.

| ID | Decision | Rationale | Reversed by | Settled by |
|---|---|---|---|---|
| **T-1** disclosure depth | Ship **one navigational level** (the thread map) + one content escape hatch (`get_messages`). Per-message *content* depth vocabulary `stub/snippet/body_clean/body_full/raw` is orthogonal and is not a routing hierarchy. Segment map is the single exception (T-CD1) | 2607.17598: a second routing level "never helps and sometimes breaks accuracy" ([VERIFIED] VR §8.1). PD's defensible claim here is honest partiality, not accuracy | A DISC-05 measurement showing depth *n* beats *n−1* on the same cases | **CG-PD's depth line + `EVALUATION_PLAN.md` §7.5.1** (the PD-DEPTH-N vs PD-DEPTH-N1 large-thread arm, which now exists); DISC-05 fires by design (see §H-3) |
| **T-2** structural cost at 40 u | Quota-native budgeting (D8). Thread maps are the unit: one `threads.get(format=metadata)` = 40 u buys an entire thread's header rows. Three distinct caps, renamed so one name no longer means two things (ADV-003): `max_hit_threads` **12** (hit-bearing maps — never silently exceeded, overflow becomes `withheld`), `max_source_threads` **4** (sibling/structural sources), `max_pool_threads` **25** (L5 pool; creates no source and no map rows). **No metadata cache in v1** — N-03 requires a measured failure first | Message-wise enrichment costs 20 u/message; thread-wise amortises across a whole thread. 25 threads = 1000 u of a 6000 u/min budget ([VERIFIED] RO F7) | PF-3 showing the real quota is ~4× tighter ⇒ caps drop to 2/12 and the reduced bound is declared; or measured thread-map re-fetch dominance ⇒ Option F metadata cache with SN §4.2's full rule set | PF-3 |
| **T-3** what "complete" means | Ship `completeness: "as_reported_by_source"` with `source`, `stated_total`, `fetched_at`. **A total is what the source reported at `fetched_at` — never an unverifiable claim of absolute completeness.** Divergence from the seeded manifest is a **ground-truth-validation** concern (PF-1/GMAIL-03), not a runtime claim, and is bounded by a pre-registered rate rather than merely published (§H-2, ADV-209) | No thread operator, no count field, and `get_thread` truncation is reported (VR §6.1, §11.2). Only the source-at-time-T claim is honest | Nothing — this is the ceiling of what the API can support | PF-1 validates the *instrument* against the seed manifest (GMAIL-03) |
| **T-4** freshness vs zero-dependency | **`history.list` polling only. No Pub/Sub, ever, in the core path.** Stamps ship day one. The `historyId` watermark **persists in a named non-content file** (`state/watermark.json`, `0600`, `{account_hash, history_id, observed_at}` and nothing else) — without it LR could only see mail delivered during the current process's life, i.e. almost never (ADV-101). LR costs **`2 + 20n`**, not 2, and re-checks only a **closed constraint subset** locally, never claiming a Gmail `q` match it did not get. LR ships **Experimental with a removal gate** (E.2, CONS-031) | `users.watch` needs Cloud Pub/Sub, a hosted dependency colliding with N-01/N-02; polling is cheap and key-free ([VERIFIED] RO F6, F7) | Only an MF1/MF5 result that polling provably cannot close — and then as an opt-in that keeps the core key-free | PF-10 → MF1–MF6 |
| **T-5** debuggability vs A.3 | Real-mailbox forensics run through **ID-based re-fetch into memory** (`mailweave inspect`), never disk. The A.3 snippet exception is per-incident, code-redacted, gitignored, self-documenting | SN §4.3's stricter default stands; making compliance *cheap* is the only durable enforcement (T-SN1) | Nothing; if forensics prove impossible, the failure is reproduced on the seed account instead | PF-8 (canary incl. error paths) |
| **T-VR1** PD required, measured near-null | Implement PD as required; **state the claim on the honest-partiality/cost axis**, not accuracy. Keep Baseline E-generous live permanently. Publish a null accuracy result as a null result | Both sides are true. The paper measures accuracy on books; MailWeave's property is "no silent false not-found", which is vendor-documented as absent today (VR §0.1) | Nothing reverses the *implementation*; a loss to E-generous narrows the **claim** to cost/rounds/latency/predictability, per EP §8.7's pre-committed interpretation rule | CG-PD + every gate's E-generous arm |
| **T-VR2** one mailbox cannot settle freshness | Two mailboxes minimum; new-mail and long-thread strata separated; direct REST distinguished from any hosted layer. **A negative result on one mailbox licenses no freshness sentence** | Lag is account- and thread-variable in the reported evidence (VR §11) | — | PF-10, FRESH-01 |
| **T-VR3** `get_thread` may itself truncate | PF-1 measures REST `threads.get` message counts against the seed manifest **before** any baseline number is published. If truncation is real, Baseline B is labelled lossy everywhere and PART-01 needs owner rewording (§H-2) | The ground-truth baseline is an unverified assumption (VR §6.1, #239) | — | **PF-1 (blocking)** |
| **T-RO1** semantic needs a pool lexical can't scope | Pool is **query-independent by construction** and its scoping rule is **declared in every response**: `pool{scope_rule, thread_count, message_count, window, why}`. The honest sentence is "no semantic match within *this declared pool*", never "no semantic match" | A silent bounded pool recreates the exact false-negative failure MailWeave exists to fix, in our own code | An honest recall target that provably needs an unbounded pool — which is the measured justification SC §11 demands before a synchronised persistent index | CG-SEM |
| **T-RO2** quota + CPU cap the pool | **Thread-wise pool construction** (`max_pool_threads` 25 × 40 u ≈ 1000 u for ~300 message rows) instead of message-wise (300 × 20 u = 6000 u — the entire per-minute budget). The rung is **announced with its cost**, never run silently; README quotes easy-path *and* escalated-path latency | 6× cheaper for the same pool. T-RO2's own arithmetic, redirected through the cheaper primitive | PF-3 (quota reality) or PF-4 (CPU reality) moving either ceiling | PF-3, PF-4 |
| **T-RO3** stale-index vs required semantic | **(a) bounded-and-declared.** No persistent index, no vector DB, no disk. Vectors live in an in-process LRU keyed `(message_id, internalDate, model_id, model_revision)`, memory-only, dying with the process | Resolves the paradox by never creating a second source of truth. An `internalDate` change invalidates the key, so the cache cannot serve a stale body's vector | A measured recall/latency win over on-demand, **with C-09's freshness obligations budgeted into the same loop** (contract §7) | CG-SEM, SEM-05 |
| **T-RO4** TS premise void | Reopened and decided: **Python** (§B) | See §B.8 | §B.8 R1–R4 | PF-4, PF-7 |
| **T-RC1** escalation cannot be hostage to the client | **Seam (c): server-enforced floor** (A.3). Server runs L0–L6 in one call; a local model is a default-build dependency | I-4 is a release criterion; (b) delegates it to a client we do not control, which is the original bug's mechanism | Nothing — (b) is inadmissible while I-4 is release-blocking | — |
| **T-RC2** the trigger can't be computed pre-escalation | Escalate on **query shape ∨ result shape ∨ `answer_type_presence` failure** (A.8); **accept over-triggering** and bound it with the cost budget rather than the trigger. `exact_signal_match` is now **normatively defined** (A.8a) and only its identity branch **E-a** (`rfc822msgid`, `hit_count == 1`) stops the ladder unconditionally; on the phrase and structured-identifier branches `answer_type_presence` is evaluated **before** the stop, so the signal built for T-RC2 is no longer disabled on exactly T-RC2's cases (ADV-004) | Confident-but-wrong is invisible to pre-escalation signals. `answer_type_presence` is a model-free CRAG-evaluator proxy — a hypothesis, not a finding | Measured over-trigger blowing PERF-01/SEM-04, or under-trigger blowing SEM-01 ⇒ fall back to the pure query-shape trigger | **CG-AD** (escalation confusion table, both off-diagonal cells) + **CG-SEM** (F11 `semantic_gain`, F12 over-escalation ceiling) + the **F11/F12 trigger ablation**, now landed at **`EVALUATION_PLAN.md` §7.4** and published as a CG-AD gate cell (EP §13.4). *The previous cell cited CG-EP (evidence preservation) and A.8 cited PF-9 (Gmail `q` scoping); neither measures escalation triggering — ADV-104, CONS-016. **CG-EP is deliberately not reinstated here** (reconciliation, Round 1): its bars are recall, FNF, Baseline-B proximity and hallucinated-found, so a pointer at CG-EP would return T-RC2 to being settled by an instrument that cannot test it. F11 is the plausible-but-wrong-lexical family with F12 as its paired negative control; the "currently under-represented" clause is stale — EP Rev-2 §4.7 added both at n=10 — ADV-301, CONS-037.* |
| **T-RC3** rungs + relaxation erode "I asked for X" | Every message carries a mechanical reason **and** a `constraint_coverage` field naming which of the user's own constraints it satisfies. The response carries an `asked_for` block: parsed constraints, enforced vs dropped, per rung | Keeps the response readable as "here is what I actually searched for" — a response-format constraint, not a reason to drop rungs | — | ROUTE-03, RANK-03 |
| **T-CD1** the compression ladder is itself multi-level | Flat map by default. The **segment map is the only second navigational level**, entered only above a measured token boundary, and it **trips DISC-05** — which we accept and will satisfy with a measurement, not waive | A 500-message map at ~20 k tokens is unusable against a [VERIFIED] 25 k host cap with a 10 k warning. The ladder answers a hard constraint | The DISC-05 comparison failing ⇒ the segment level is removed and very large threads are handled by declared truncation + affordance only | PF-6, CG-PD, **DISC-05 measured by `EVALUATION_PLAN.md` §7.5.1** |
| **T-CD2** query-aware selection hides the reversing message | The **E2 reply-chain floor is non-negotiable in *membership* and budget-bounded in *depth*** (A.9a). Floor messages are always present — never absent, never a bare count — and degrade `body_clean(600)` → head-truncated `body_clean(250)` → `snippet`, each step declared in place with an unabridged affordance. Only after the whole degradation ladder, the declared 9,000→12,000 overflow ceiling, and source-splitting are exhausted may a hit leave the payload, and then only as a `withheld` record (A.7a) | Honest correction after review (ADV-003): the previous "not budget-negotiable" was arithmetically impossible — a 40-message thread with 6 hits needs ~11,200 tok against a 9,000-tok ceiling — and "self-truncates explicitly rather than dropping the floor" was a label, not a mechanism, since a truncated-away message is as absent as a dropped one. What is *true* is membership plus a snippet: a reversing reply is usually short, so at `snippet` depth the reversal is commonly **visible**, not merely counted. That is the claim; "the agent will notice" is not | **F17 run at each degradation tier.** If accuracy with the floor at the depth the budget actually produces is not better than Baseline F(±2) at equal token budget, the floor is not doing its job at that depth ⇒ design change (fewer hits at body, higher ceiling, or narrower fill), escalated per §I | **F17 decision-reversal** (n = 8; highest query-scoring messages support A, a low-scoring later reply reverses to B, distractors reinforce A) — **landed at `EVALUATION_PLAN.md` §4.7** (n = 8, CONS-007, ADV-302) and bound at gate **CG-PD** (EP §13.4), which requires F17 "scored strictly in both the query-aware and Baseline F(±2) arms". Run in the query-aware **and** Baseline F(±2) arms, at all three floor depths |
| **T-CD3** beating ±2 may force embeddings into disclosure | **Reuse, never trigger** (A.9). Mechanical scoring by default; if L5 already ran, its vectors re-score the fill at zero marginal cost | Disclosure never *causes* latency; it only *reuses* it. Bounds the coupling to queries that already escalated | — | Pre-registered Loop-2 arm: mechanical-D-var vs reuse-D-var vs D-base at equal token budget |
| **T-SN1** strictest profile governs debugging | ID-based forensics tooling built **in Loop 0**; redaction canary is a continuous test covering error paths; the A.3 exception is time-boxed and self-documenting | A rule that is inconvenient at high frequency gets bypassed. Make compliance cheap | — | PF-8 |
| **T-SN2** A.3 slightly more permissive than SN §4.3 | **SN §4.3's stricter list is the default** — including its raw-query-string rule, which A.3 does not address. A.3's snippet allowance is a mechanically gated exception that never widens to subjects, addresses or display names | Resolved deliberately rather than by drift, as the addendum demands | An owner decision, recorded | SEC-06 |
| **T-SN3** local-first puts injection + bait on the default path | Internal models are **embeddings and a cross-encoder only** (D6): outputs are float vectors and float scores, so INJ-06's closed-type requirement is satisfied structurally. Expansion parameters originate **only** in tool arguments. Every semantically-selected result carries rank provenance with `model_id@revision`. Embedding-bait and keyword-stuffing fixtures are added to the I1 suite | The cheapest way to satisfy a quarantine contract is to have nothing to quarantine. A generative model would add the full free-text attack surface for no measured benefit | A measured failure that only a generative model fixes — then INJ-06's full apparatus is built first | INJ-03, INJ-06, PF-5 (weight pinning) |
| **T-SN4** dedicated seed account costs 7-day re-consent | Harness in **Testing status with a seed-only allowlist** (Google-side hard control); read client **Production-unverified**. Weekly re-consent accepted, mitigated by one-command refresh + pre-gate checklist | Corpus regeneration is gate-time, not per-commit. The allowlist is a control no code bug can bypass | Re-consent friction actually blocking a gate ⇒ switch harness to Production-unverified and rely on the `getProfile` pinning assertion alone | PF-12 |

---

## D. Concrete design commitments

### D.1 MCP tool surface

Four tools, namespaced, compile-time constant (MCP-05), `readOnlyHint: true` (MCP-04), each returning
`structuredContent` **and** a text mirror that agrees with it (MCP-03).

```
mailweave_search(query: str,
                 constraints?: {from?, to?, after?, before?, label?, has_attachment?},
                 pool?:   {scope: "auto"|"thread"|"recency"|"participant", window?, max_threads?},
                 scan?:   {max_pages?},                       // A.7a scan-scope widening
                 budget?: {max_quota_units?, max_ms?, max_disclosed_tokens?},
                 force_rungs?: ["structural"|"semantic"|"rerank"|"recency"],
                 view?: "body_clean" | "snippet")            -> SearchResult
mailweave_thread_map(thread_id?: str, map_id?: str, segment?: int) -> ThreadMap
mailweave_get_messages(message_ids?: [str], map_id?: str, positions?: [int],
                       view: "stub"|"snippet"|"body_clean"|"body_full") -> Messages
mailweave_get_attachment(message_id: str, part_id: str, mode: "metadata") -> Attachment
```

`mailweave_search` completes an easy query in **one call** — evidence at readable depth, not a handle
to redeem (CD §7 T2). `force_rungs` is how an affordance re-runs an expensive rung; it can only *add*
rungs, never remove the recoverability floor. `scan.max_pages` is the executable affordance behind a
`scan_scope.more_pages: true` declaration (A.7a). `mode` on `get_attachment` accepts only `"metadata"`
in this release (B-04) and is served from the carrying message's `payload.parts`, not from
`messages.attachments.get`, which is off the surface (A.5, ADV-207).

**`view: "raw"` is not independently requestable in this release** (ADV-208). `raw` stays in the
closed depth vocabulary (contract R-04) and is reachable only as the declared unabridged form of a
decoding failure; a `view:"raw"` argument is rejected with `unsupported_view` (D.11). This removes one
separately-requestable disclosure level from the DISC-05 count without narrowing any contracted
capability — `body_full` is the escape hatch, and `raw` served none. `snippet` **stays** requestable,
and H-3's DISC-05 commitment is extended to measure the content-depth vocabulary, not only the
segment map.

### D.2 Response schema sketch

```jsonc
{
  "schema_version": 2,
  "fence_nonce": "mw-7f3a…",              // per-response; mail text cannot close its own fence
  "asked_for": {                           // T-RC3
    "parsed": {"from":"amy@…","after":"2026/05/01","terms":["launch"],
               "timezone":"Pacific/Auckland",                       // A.6a rule 1
               "window_utc":{"start":"2026-04-30T11:00:00Z","end":"2026-06-01T11:00:00Z"}},
    "enforced": ["from","terms",{"date_window_widened":"±1d, timezone-boundary safety"}],
    "dropped": [{"date_window":"zero hits at L1"}],
    "term_coverage": 0.67, "constraint_drop_depth": 1
  },
  "sources": [{
    "thread_id": "…", "stated_total": 42, "included": 42, "included_as_stub": 35,
    // AMENDED by A4 (Round 5): `included` counts every message present at ANY depth,
    // stubs included, per contract R-05. This example previously read `included: 7`,
    // treating the two as disjoint. Under that reading a complete 42-message map
    // reports included=7 against stated_total=42 and an agent reasonably concludes 35
    // are missing when all 42 are present. `included == stated_total` is the
    // map-carrier guarantee stated as a number.
    "completeness": "as_reported_by_source", "source": "gmail.threads.get",
    "fetched_at": "2026-08-30T14:02:11Z",   // cache-entry time; NEVER restamped (A.10)
    "verified_at": "2026-08-30T14:06:40Z",  // history.list liveness probe, when served via LRU
    "history_id": "998877",
    "map_id": "mw1.eyJ…",                   // signed, self-describing (A.10)
    "messages": [{
      "id": "18f…", "position": 37, "internal_date": "…",
      "role": "matched",                    // matched|context|parent|child|requested|stub|derived
      "reason": "gmail q matched: from:amy launch",   // mechanical, never decorative
      "constraint_coverage": ["from","terms"],
      "depth": "body_clean",                // stub|snippet|body_clean|body_full  (raw not requestable)
      "reductions": [{"kind":"quoted","removed_chars":4210,"stripper":"talon@<ver>"},
                     {"kind":"html_to_text","parser":"selectolax@<ver>"},
                     {"kind":"hidden_content","removed_chars":812,
                      "constructs":["display_none","comment","zero_width"]},
                     {"kind":"body_head_truncated","kept_tokens":250,"why":"A.9a step 4"}],
      "unabridged": {"tool":"mailweave_get_messages","args":{"message_ids":["18f…"],"view":"body_full"}},
      "score": {"value":0.81,"method":"cosine","model":"potion-retrieval-32M@<rev>",
                "basis":"subject+participants+snippet",      // ADV-110: what was embedded
                "ordering_effect": false},                   // true only if present for ALL candidates
      "content": {"trust":"untrusted_third_party","source":"gmail_body",
                  "text":"<<<mw-7f3a … mw-7f3a>>>"}
    }],
    "collapsed_runs": [{"positions":[4,29],"count":26,"why":"disclosed_token_ceiling",
                        "affordance":{"tool":"mailweave_thread_map","args":{"map_id":"mw1.eyJ…","segment":2}}}]
  }],
  "not_included_sources": [],               // A.9a step 7: whole sources split off, each with an affordance
  "partial": true,
  "affordances": [{"what":"35 messages of this thread remain stubs","tool":"mailweave_get_messages",
                   "args":{"map_id":"mw1.eyJ…","positions":[1,2,3],"view":"body_clean"}}],
  "retrieval_report": {                      // ALWAYS present, hits or not (C-08)
    "outcome": "inconclusive",               // answered | not_found | inconclusive (OD-2; see field note)
    "rungs": ["L0","L1","L2","L5"], "hit_count_per_rung": [0,0,3,9],
    "scan_scope": [{"q":"from:amy launch after:2026/05/01","rung":"L1","page_size":100,
                    "pages_fetched":1,"ids_returned":46,"more_pages":true,
                    "affordance":{"tool":"mailweave_search","args":{"scan":{"max_pages":3}}}}],
    "pool": {"scope_rule":"25 most recent threads matching after:2026/02/01",
             "thread_count":25,"message_count":287,"why":"lexical weak; pool is query-independent",
             "note":"pool membership creates no source and no stub rows (A.7a)"},
    "shortlist": {"rule":"top-k by stage-A cosine","k":25,"size":25},   // this — not the pool — is H_sem
    "not_tried": [{"rung":"wider_pool","why":"cap",       // closed vocabulary; see field note
                   "affordance":{"tool":"mailweave_search","args":{"pool":{"max_threads":50}}}}],
    "empty_diagnosis": {"status":"incomplete","tried":["from","to","subject"],
                        "untried_drops":["after","before"],"restores":null,
                        "affordance":{"tool":"mailweave_search","args":{"constraints":{"before":null}}}},
    "budget_caps_hit": ["max_quota_units"], "sufficiency": "ambiguous",
    "counters": {"http_requests": 6, "api_calls": 31, "quota_units": 1180,
                 "quota_units_label": "diagnostic; PF-3 calibration 2026-09-xx"}
  },
  "withheld": [{"id":"18a…","thread_id":"1f2…","cap":"max_hit_threads",
                "why":"31 hit-bearing threads; 12 mapped","affordance":
                {"tool":"mailweave_thread_map","args":{"thread_id":"1f2…"}}}],
  "ceiling": {"normal":9000,"applied":9000,"why":null},   // "applied":12000 only for E2 floor membership
  "errors": [{"code":"partial_source_failure","scope":"thread:1f2…","message_ids":["18c…"],
              "affordance":{"tool":"mailweave_get_messages","args":{"message_ids":["18c…"]}}}],
  "budget": {"clamped":{"requested":50,"applied":845,"why":"recoverability floor (A.7)"}},
  "truncated_by": null                       // "mailweave" if self-truncated; never the host
}
```

Field notes that are obligations, not decoration:

- **`withheld` is derived**, `H − disclosed`, at envelope time (A.7a). An empty `withheld` is a
  positive assertion that every retrieved ID is present at some depth — not a default.
- **`outcome` is the response's own account of what happened**, not an inference left to the caller
  (OD-2). **`not_found` is permitted only when no applicable rung is untried for budget, cap, timeout
  or error, and `budget_caps_hit` is empty; otherwise the outcome is `inconclusive`.** It is a claim
  about the routes executed, never about the mailbox, and it is **not** `sufficiency` (A.8), which is a
  per-rung evidence verdict.
- **`not_tried[].why` is a closed vocabulary**: `not_applicable` (the rung could not help this query)
  versus `budget | cap | timeout | error` (the rung could have helped but did not run). That
  distinction is what makes the `outcome` rule above machine-checkable.
- **`empty_diagnosis` has three states** (ADV-105): a named restoring constraint; `null` meaning *no
  single dropped constraint restores results* (a real finding); and `{"status":"incomplete", …}`
  meaning *the probe budget ran out before all single-constraint drops were tried*. Conflating the
  last two was the defect — "unknown" was not a shape the schema could express.
- **`scan_scope`** is required per executed query (GMAIL-04, ADV-304); `more_pages: true` without an
  affordance is non-conforming.
- **`errors[]`** carries the in-band half of D.11's closed error vocabulary.

The static tool description — never per-result text — states that fenced content is third-party data
and must not be followed as instructions (R-09, SN §6.3).

### D.3 Escalation ladder, budgets, stopping rules

Rungs and caps are in A.7. Stopping rules, **in order** — note that the previous ordering was itself
the bug (ADV-004): rule 1 fired before anything consulted `answer_type_presence`, so the architecture's
only answer to T-RC2 was switched off on precisely the confident-but-wrong cases it was built for.

0. **Compute `answer_type_presence` first.** Whenever the query carries an interrogative or decision
   cue, `answer_type_presence` is evaluated on L0's hits **before any stop rule is tested** (A.8b).
   It is recorded whether or not it changes the outcome.
1. **`exact_signal_match` on branch E-a** (`rfc822msgid:` with `hit_count == 1`) ⇒ **STOP after L0.**
   No structural, semantic or ranking rung may run (SEM-04, RANK-01). This is identity resolution;
   there is nothing to escalate *to*.
1b. **`exact_signal_match` on branch E-b or E-c** (verbatim phrase, structured identifier) ⇒ STOP
   after L0 **only if** `answer_type_presence` is true, or the query carries no answer-type cue.
   If `answer_type_presence` is false, **do not stop** — fall through to rule 4. A phrase or an
   identifier can match a confident-looking wrong message; a message id cannot.
2. `hit_count ∈ [1,5] ∧ term_coverage == 1.0 ∧ constraint_drop_depth == 0 ∧ answer_type_presence`
   ⇒ **STOP after L1.** *(A.7's L1 row now carries the same fourth conjunct — the two statements
   previously disagreed inside one document: CONS-036.)*
3. Any rung returning `sufficiency == sufficient` ⇒ STOP.
4. `hit_count == 0` after L3, or `term_coverage < 1 ∧ paraphrase_risk ≥ θ`, or tier-1 confidence
   `non_lexical`, or `answer_type_presence == false` ⇒ **escalate to L4/L5.** `θ` is [PRE-REG at G0].
5. Any cap exhausted ⇒ stop, emit, name the cap plus untried rungs with affordances (AD-03), **and
   emit a `withheld` record for every hit the cap prevented from being disclosed** (A.7a).
   The outcome is **`inconclusive`**, never `not_found` (D.2).
6. **Never** a bare empty result (C-08). An empty result always carries `outcome`, and the outcome is
   **`not_found`** only on the exhaustion case of D.2's rule — otherwise **`inconclusive`**.

**Gameability note, recorded deliberately.** ARCH_REVIEW §3 shows that a broad `exact_signal_match`
does not merely make six criteria easy — it *removes cases from the denominators* of AD-05 and CG-SEM
and contaminates SEM-OFF, the reference distribution meant to catch it. The three countermeasures are
all in A.8a and none of them is discretionary: the predicate is a closed three-branch definition with
no frequency dial; it is a required trace field with its firing inputs; and its **per-family firing
rate is pre-registered and published at G0**, so breadth appears as a number instead of as an absence.

### D.4 Disclosure policy shipped, and its depth

The policy is A.9; the degradation ladder under the ceiling is A.9a. **Shipped depth: one navigational
level + one content escape hatch.** Content-depth vocabulary is closed:
`stub | snippet | body_clean | body_full | raw`, of which **four are independently requestable**
(`raw` is not — D.1, ADV-208). Budget ladder [DESIGN, from CD §6.3, tuned at CG-PD]:

| Level | Budget | Changed? |
|---|---|---|
| stub row | ≤40 tok | — |
| snippet | ≤25 tok | — |
| `body_clean` | **soft cap 600 tok** | was 1,000; tightened so the E2 floor fits (A.9a) |
| `body_clean` head-truncated | 250 tok | new degradation step |
| `body_full` | soft cap 4,000 tok | — |
| `raw` | never inline | — |
| L1 evidence response target | ≤4,000 tok | — |
| **hard per-response ceiling** | **9,000 tok**, with a **declared overflow to 12,000 tok** reachable only for E2 floor membership | ADV-003 |

Both ceilings sit below the [VERIFIED] 25 k Claude Code cap so MailWeave authors its own truncation
(DISC-06); the 12,000 overflow exceeds the 10 k host *warning*, which is a warning and not a
truncation, and it is entered only when the alternative is losing floor membership. **PF-6 sets both
numbers from the measured host cap.**

Every reduction — quote stripping, HTML→text, hidden-construct removal, head truncation, stub-run
collapsing, scan-scope limits — is declared **in place** with a size count and an unabridged path
(CD §5.4 rule 3, R-04), using the `reductions[]` vocabulary of D.2 and, for scan scope, the
`scan_scope` block of A.7a.

### D.4a Content processing — the components, named

*(ADV-202, ADV-203, CONS-025. The previous draft excluded one library on licence grounds and named no
replacement, and specified no decoding policy at all. INJ-04, GMAIL-02 and DISC-03 are three mandatory
criteria resting on components that did not exist in the document.)*

**What Gmail does and does not do for us.** Gmail parses MIME server-side and returns a structured
`payload` tree. So the residual risk is **decoding and part selection**, not MIME parsing — which is
also why B.5's Pydantic-boundary argument is restated at the payload level and R4 is narrowed (§B.8).

**1 · Part selection** (load-bearing for `body_clean`).
- `multipart/alternative`: prefer `text/plain`. If it is absent or empty after stripping, use
  `text/html` → visible text. If **both** exist and `text/plain` is used, the unused HTML part is
  declared — `{"kind":"alternative_part_unused","mime":"text/html","bytes":N}` — so nothing is
  silently discarded.
- `multipart/mixed` / `related`: walk every leaf; non-text leaves become attachment-metadata rows
  (filename, mimeType, size, partId) from the same tree (B-04).
- Depth cap 12, part cap 64; exceeding either is declared, never truncated silently.

**2 · Body decode.** `payload.body.data` and `payload.parts[].body.data` are **base64url**
(RFC 4648 §5, `-_`, unpadded): padding is restored before decoding. A decode failure emits
`{"kind":"undecodable_body","bytes":N}` and the message is still disclosed with an empty
`body_clean` and a `raw` unabridged path — **declared, never dropped** (GMAIL-02).

**3 · Charset.** Taken from the part's `Content-Type; charset=`. Resolution ladder: declared charset →
UTF-8 → cp1252 → latin-1, with the charset actually used named in the reduction record. Decoding uses
`errors="replace"` and the replacement count is declared:
`{"kind":"charset_replacements","count":N,"charset_used":"cp1252","charset_declared":"iso-8859-1"}`.

**4 · Headers.** RFC 2047 encoded-words decoded via stdlib `email.header.decode_header` +
`make_header`. An undecodable encoded-word is **kept verbatim** and flagged, never dropped. Duplicate
headers: all values retained, the first used for display, the count declared. A missing `Message-ID`
yields `linkage: "no Message-ID"` (D.6), never a guessed parent.

**5 · HTML → visible text.** **`selectolax`** (MIT, maintained, Lexbor/Modest C parser, no network) is
the parser; **`lxml.html`** (BSD) is the pinned fallback. **`html2text` remains excluded — GPLv3**
([VERIFIED] CD §3). Hidden-construct removal, as INJ-04 requires, is an explicit filter, not a hope:
drop `<script>`, `<style>`, `<head>`; drop nodes with `display:none`, `visibility:hidden`,
`font-size:0`, or width/height ≤ 1 px; drop HTML comments; strip zero-width characters
(U+200B–U+200D, U+2060, U+FEFF); normalise NBSP; flag colour-equals-background text. Every removal is
counted into `{"kind":"hidden_content","removed_chars":N,"constructs":[…]}` — the
`hidden_content_removed` signal INJ-04 requires, which previously had no home in the schema.

**6 · Quote and signature stripping.** **`talon`** (Apache-2.0, per CD §3) for reply quotes and
signature blocks, emitting `{"kind":"quoted","removed_chars":N,"stripper":"talon@<ver>"}`. Stripping
is **heuristic and bypassable, and is declared as such**; the unabridged path is always present. If
`talon` cannot be pinned at build time, the fallback is `crisp-oss/email-reply-parser` (MIT) with the
same declaration contract. Licences are recorded because `html2text` was excluded on exactly that basis.

> **Superseded in part, Round 8 (2026-08-31), by R-ARCH-022 — the round 7 BLOCKER.** The
> `email-reply-parser` fallback shipped, and it decided deletions on its own `On.*wrote:$`, one-line
> `From|Sent|To|Subject:` and dash-prefix patterns **before** amendment A5's strong-structural-signal
> rule could run, destroying sender-authored paragraphs with no A5 check and no ambiguity flag. A
> dependency that silently deletes user text cannot be audited after the fact, so it has been removed
> from the deletion path and from the dependency list entirely; `content/quotes.py` now owns the
> segmentation, and reductions report `stripper: "mailweave.content.quotes@<rev>"`. The declaration
> contract, the reduction record and the always-present unabridged path are unchanged. `talon` remains
> this section's first choice if it can ever be pinned, and it would be subject to the same rule: it
> may propose, it may not decide. **This note records the change; the amendment entry in
> `ARCHITECTURE_AMENDMENTS.md` is the orchestrator's to write** — see
> `docs/reviews/ROUND_08/HANDOFF.md` part 1.

**7 · Normalisation before embedding.** NFKC → whitespace collapse → quote-stripped body; no
lowercasing (model-dependent); truncation to the model's context window with the truncated length
recorded in the trace, so a silently clipped input can never be mistaken for a weak match.

**8 · Status (reconciliation, Round 1).** This subsection is what **CONS-025** asked for, and it
closes it: INJ-04's "maintained parser" + hidden-construct removal + zero-network condition,
GMAIL-02's RFC 2047 encoded-words / non-UTF-8 charsets / HTML-only bodies, and DISC-03's
declared-reduction-with-a-count now each rest on a **named component with a named licence**
(selectolax MIT, lxml BSD fallback, talon Apache-2.0 with an MIT fallback, stdlib `email`), not on an
unselected one. `RELEASE_RUBRIC.md` and `EVALUATION_PLAN.md` recorded CONS-025 as "NOT CLOSED — not
ours" because the fix was owned by this file; their repair logs are updated to point here.

**9 · Test obligations.** The whole pipeline is exercised **with sockets disabled** — no parser may
fetch a remote entity, stylesheet or image (INJ-04's zero-network condition) — as part of **PF-5**,
and against GMAIL-02's fixture set (encoded-word headers, non-UTF-8 charsets, HTML-only bodies,
nested multiparts, missing and duplicate headers).

### D.5 The semantic rung

**Fires when** rule 4 of D.3 holds and `exact_signal_match` is false. **Never** on exact-lookup or
sender/date families (SEM-04).

**Pool construction (thread-wise, T-RO2).** Union, in priority order, capped at
**`max_pool_threads` = 25** threads / `max_pool_messages` (`max_embed_texts`) = 300 message rows:
(a) threads already touched by L0–L3; (b) threads of participants parsed from the query
(`from:`/`to:` probes, 5 u each); (c) most-recent threads in the query's date window, or a default
recency window if none. Each thread costs one `threads.get(format=metadata)` = 40 u and yields **all**
its message rows. The scoping rule is declared verbatim in `retrieval_report.pool` (T-RO1).

**Pool membership is not disclosure membership, and step (b) is not exempt from `H`** (A.7a,
ADV-003, ADV-109). Two rules that were previously missing:

- The pool creates **no `source`, no mini-map and no stub rows**. It is disclosed by its scoping rule
  and its size in `retrieval_report.pool`, and enumerated **by ID in the trace** (`semantic.pool_ids[]`)
  so EV-01 joins against a real set. This is what makes the semantic rung implementable under I-1
  without 287 stub rows blowing the token ceiling, and it is the canonical I-1 / DISC-04 / RANK-04
  resolution applied identically across the document set.
- Step (b)'s participant probes are **`messages.list` calls**, so every ID they return is in `H`
  under clause (H-lex) — the *first* clause of I-1, which §H-5's narrowing never touched. Those IDs
  are disposed of by A.7a like any other: disclosed if their thread is mapped, otherwise a `withheld`
  record with `cap: "max_pool_threads"` and a pool-widening affordance.
- `H` from the scored retriever is the **shortlist**: top-`k` by stage-A cosine with
  `k = max_rerank_pairs = 25`, a declared pre-registered constant reported in
  `retrieval_report.shortlist{rule, k, size}` — **not** a score threshold an implementer picks, which
  would hand them the dial that sets `|H|` (§H-5, ADV-109).

**Pool text.** `subject + from/to addresses + Gmail snippet` per message row. **PF-2 is blocking:**
the REST docs say `format=METADATA` returns "only email message ID, labels, and email headers"
([VERIFIED], Format enum) and do **not** document `snippet`.

**If PF-2 finds snippets absent, that is a design change, not a cost change** (ADV-102). The previous
sentence was wrong on both halves and is withdrawn. Stage A is the *only* thing deciding which 25 of
~300 rows reach the cross-encoder; with its input reduced to subject + participants, SC §4's own
worked example — query "postpone the launch", evidence "We'll push go-live into Q4" — is invisible,
and stage A degrades from a weak retriever to a near-random shortlist selector on exactly the family
that justifies the rung. And the stated fallback was unaffordable: 300 rows × 20 u = **6,000 u = the
entire per-minute budget**, the same figure T-RO2 uses to reject message-wise pool construction and
E.4 lists as a "pure cost rejection".

**Ranked fallbacks, in order, each with its real cost:**

1. **`threads.get(format=full)` — the primary fallback.** Same method, therefore the **same 40 u**
   (quota is per method, not per format — [VERIFIED] CD §3). Pool text becomes
   `subject + participants + first 400 chars of cleaned body` (D.4a), which is *stronger* than the
   snippet path, at a **bytes-and-latency** cost rather than a quota cost. Because the parse+embed
   cost rises, `max_pool_threads` drops **25 → 15** [DESIGN] until PF-4/PF-4b measure it, and the
   reduced bound is **declared in every semantic response** per T-RO1. This is the branch PF-2 should
   be expected to take.
2. **Bounded `messages.get(format=metadata)` per row — only if PF-1 shows `threads.get(format=full)`
   itself truncates.** `messages.get` is 20 u regardless of format, so the pool is hard-bounded to
   `max_pool_messages = 60` (60 × 20 = **1,200 u**), and the recall consequence of the smaller pool is
   declared in every semantic response, again per T-RO1.
3. **If neither is available, PF-2 has failed blocking and the rung's design is escalated to the
   owner (§I)** rather than shipped on a fallback nobody costed.

**Stage A — static bi-encoder over the whole pool.** Default `minishlab/potion-retrieval-32M`
(MIT, ungated, 32.3M params). Chosen over EmbeddingGemma as the default because EmbeddingGemma is
HF-gated, which is friction against NFR-04's clean-machine setup.
**Stage B — cross-encoder over the shortlist.** Default `BAAI/bge-reranker-base`, `max_rerank_pairs=25`.
Cross-encoders score query×candidate pairs with no reusable per-document work, so their cost is linear
in pool size — affordable only over a shortlist ([VERIFIED] RO §5.2). This is a design constraint, not
a preference.
**Opt-in swaps behind the same interface:** `Qwen/Qwen3-Embedding-0.6B` + `Qwen3-Reranker-0.6B`,
`google/embeddinggemma-300m` (MRL-truncatable to 128 dims), and hosted providers for benchmarking only.

**Interface (SEM-03).** `embed(texts: list[str]) -> list[Vector]` and
`rerank(query: str, candidates: list[str]) -> list[float]`. Local implementation registered by
default; a second implementation registers without touching retrieval logic. The mechanical
enforcement of "hosted never required" is the egress-blocked test (NFR-01, SEM-02).

**Cost disclosure.** The response carries `cost.semantic_ms`, `cost.embed_texts`,
`cost.rerank_pairs`, `model_id@revision`, and `escalated: true`. Public latency claims must quote the
escalated path as well as the easy path (T-RO2).

**Deterministic fallback (D6).** If the model runtime or weights are unavailable, L5 emits
`not_tried: [{rung:"semantic", why:"local model unavailable", affordance:…}]` and the ladder continues.
Silent no-op is a BLOCKER by construction (SEM-02's guard).

### D.6 Structural signal computation under quota

All live from thread maps; no persistent graph (SC §5, contract §7).

- **Reply tree:** JWZ/IMAP-REFERENCES reconstruction from `Message-ID` / `In-Reply-To` / `References`.
  Gmail thread membership is looser than RFC threading, so orphans are expected and are labelled
  `linkage: "date-adjacent (no RFC reply headers)"` — **never silently re-parented** (C-02a).
  **PF-2 also settles** whether `metadataHeaders[]` returns these headers under `format=metadata`; if
  not, the reply-chain floor needs `format=full`, which changes bytes and latency but not quota
  (quota is per method, not per format — [VERIFIED] CD §3).
- **Participants:** keyed on the **address**, never the display name; `authored-by-X` and
  `mentions-X` are distinct roles (C-02b, SN §7.2).
- **Temporal:** ordering strictly by `internalDate`, never API array order (C-02c).
- **Position:** exposed on every row (STR-04).
- **Multi-thread:** sibling discovery by normalised subject, participant overlap, forward detection,
  or additional lexical hits; each sibling is a separate `source` with its own map, capped at
  **`max_source_threads` = 4** and stubs-first (C-02e, STR-05). *Pool membership is not sibling
  discovery: the L5 pool creates no `source` and no map rows (A.9(5), A.7a).*

### D.7 Ranking policy

Two tiers, both mechanical about provenance (RANK-03):

- **Mechanical ranking** runs whenever more than one candidate is disclosed. Deterministic composite
  over structural signals; `score.method = "mailweave/mechanical-v1"` with the firing components
  listed. Reproducible given the same inputs (C-04b).
- **Cross-encoder rerank** runs **only** when an ambiguity signal fires: hit-count band, `term_coverage < 1`,
  thread concentration, or a scored-retriever margin. Hard prohibitions in code: never when
  `exact_signal_match`, never when `hit_count == 1`, never on an `rfc822msgid:` route (RANK-01).
- Disclosure at body depth is capped (`RANK-04 [PRE-REG]`); the remainder appears as ranked stubs with
  reasons. Results selected by Gmail `q` say exactly that and carry **no** numeric score.
- **Every numeric score carries `basis`** — the text that was actually embedded — and a reused stage-A
  cosine may affect ordering **only where it exists for every candidate in that comparison**;
  otherwise `ordering_effect: false` and the ordering is `mailweave/mechanical-v1` alone (A.9,
  ADV-110). Mixing scales inside one comparison is the fabricated comparability RANK-03 exists to
  prevent, and the pool covers only some of the candidates a fill considers.

### D.8 Internal-model policy

**Local-only, and no generative model at all in this release.** The only models are the stage-A
bi-encoder and the stage-B cross-encoder. Enforced by a code-level constant `generative_llm_calls = 0`
and a CI gate that fails on any chat/completions client import in server code.

Rationale: SC §8 permits internal model calls; it does not require them. Embeddings and cross-encoder
scores are **closed types by construction** — float vectors and floats — so INJ-06's requirement is
satisfied structurally rather than by a validator that could be wrong. A generative model would add
the full free-text injection surface (SN §6.2 case 2) on the default path for no measured benefit.
If a measured failure later demands one, INJ-06's full quarantine apparatus is built first: enum
route labels, numeric scores, message-ID lists and booleans only; free text treated as untrusted;
**expansion parameters only ever from the agent's explicit tool arguments, never from mail content.**

**Weight provisioning and the egress property** (ADV-210, H-4). Setup-time provisioning is
*necessary but not sufficient*: the `sentence-transformers` / `transformers` / `huggingface_hub`
default load path performs a **hub revalidation request** for the model repo unless offline mode is
forced. The previous draft asserted the egress property as a consequence of setup-time provisioning
and never stated the enforcement that actually produces it. Both halves are now explicit:

- **Runtime — offline, always.** The server process sets `HF_HUB_OFFLINE=1` and passes
  `local_files_only=True`, and loads weights from a **checksum-pinned local path, never a repo id**.
  A load that would touch the network fails closed to the deterministic degradation below, rather
  than reaching out.
- **Setup — a separate command, on the allowlist for that step only.** `mailweave setup-models`
  is the only code path permitted to contact the model host (the host named in `models.lock`, by
  default `huggingface.co` and its CDN). It is never invoked from the server process and never from a
  query path.
- **Egress allowlist, canonical:** **two runtime hosts — `gmail.googleapis.com` and
  `oauth2.googleapis.com`** — and nothing else; the model host is **setup-time only**. PF-5 verifies
  the property the only way that counts: it runs the full suite with the model host blocked and the
  server started cold, so a hidden revalidation call is a test failure rather than a surprise.

**Mirrored in the governing documents (reconciliation, Round 1).** The identical property is now
carried by `PRODUCT_CONTRACT.md` **N-06**, `RELEASE_RUBRIC.md` **SEC-07** and **SEM-02**, and
`EVALUATION_PLAN.md` **§7.1 bar 2** and **§3.9 S14**: exactly two runtime hosts
(`gmail.googleapis.com`, `oauth2.googleapis.com` for token refresh only) and no other; model weights
provisioned at **setup time only** from a declared model host; **runtime loading forced offline**
(`HF_HUB_OFFLINE=1` / `local_files_only=True`) from a checksum-pinned local path; and verification on a
**cold** start with the model host blocked (PF-5, S14). SEC-07 additionally asserts no listening socket
and stdio transport (contract N-07, CONS-018). Nothing about the property was relaxed to make it
satisfiable — the unsatisfiable *wording* was replaced by the true one. §I O-4 is closed.

`model_id` and `model_revision` appear in every trace and in every score provenance string, because a
model change silently changes ranking.

### D.9 Freshness approach

- **Stamps everywhere, day one** (FRESH-03): every map, body and cached artifact carries `fetched_at`;
  every source carries `history_id`.
- **The `historyId` watermark — where it lives** (ADV-101). MCP is stateless and there is no
  persistent mail-content store (B-06), but LR needs a watermark from *before* the delivery it is
  meant to catch; with in-process-only state the first query of a process has none and later ones
  have one only minutes old, so LR would see almost nothing. The watermark therefore persists in
  **`~/.local/state/mailweave/watermark.json`**, mode `0600` inside a `0700` directory, containing
  exactly `{schema, account_hash, history_id, observed_at}` — **no message IDs, no subjects, no
  addresses, no mail content of any kind**. It is a non-content synchronisation stamp, not a cache: it
  is never served as an answer, and Gmail remains the source of truth (N-03, B-06). It is updated
  after every call that observed a `historyId`, carries a FRESH-03 stamp, and on the [VERIFIED] 404
  for an expired `historyId` (RO F6) triggers a **declared re-baseline** reported in the response,
  never silent. `mailweave purge` deletes it.
- **LR rung, correctly priced.** `history.list(startHistoryId)` costs 2 u and returns history records
  whose `messagesAdded[].message` carries id / threadId / labelIds — **not headers, not bodies**. Each
  candidate must then be fetched at 20 u. **The real cost is `2 + 20n`**, with
  `n ≤ max_recency_fetch = 8` (≤162 u); IDs beyond the cap become `withheld` records (A.7a). A.7's
  former flat "2 u" was wrong by up to two orders of magnitude.
- **The client-side re-check is a closed, published subset — and it never claims a Gmail `q` match.**
  "Re-checked against the query's constraints client-side" is exactly the cost T-RO3 names as
  option (b)'s "biggest hidden cost — reimplementing Gmail's query semantics", which E.4 cites to
  reject persistent indexes. So the re-check is bounded to constraints whose semantics we can
  reproduce exactly:
  **re-checked locally** — `from` / `to` / `cc` (normalised address equality), `after` / `before`
  (integer `internalDate` epoch comparison, A.6a rule 4), `has:attachment` (payload part scan),
  `label:` (`labelIds`, resolved once per process via `labels.list` — A.5);
  **never re-checked locally** — free-text terms, `subject:` term semantics, stemming, phrase
  semantics, `OR`/negation grouping.
  A message surfaced by LR while any residual free-text term exists is disclosed with
  `role: "context"` and the verbatim reason
  `"history.list messageAdded since <history_id>; constraints re-checked locally: [from, after]; free-text terms NOT re-checked — Gmail q did not match this message"`.
  It is never attributed to the user's query as a `q` match (R-03, T-RC3), which was both a
  correctness and a provenance defect.
- **No Pub/Sub** (T-4). **No persistent index**, so there is no index to resync.
- The full mitigation (FRESH-02) is built if any of **MF1–MF6** fires. MF6 — MailWeave's own median
  lag exceeding direct-API lag by >60 s — is a MailWeave bug and is fixed regardless of the
  mitigation decision.
- **No freshness sentence exists anywhere public before FRESH-01's entry exists** (H-04).

### D.10 Observability and trace schema

Schema v2 as in A.11. Required fields per top-level call: `trace_id`, `schema_version`,
`query_features` (never raw text), `routing{initial_route, rungs_executed, constraints_dropped,
fallback_triggered, fallback_reason, escalation_offers_returned}`, `retrieval_outcome{rounds,
http_requests, api_calls_by_method, quota_units (diagnostic), hit_count_per_rung, scan_scope[],
term_coverage_final, exact_signal_match{fired, branch, phrase_tokens, hit_count, verified_locally},
answer_type_presence{value, class}, budget_caps_hit, sufficiency_verdict, false_notfound_guard}`,
`disposition{hit_ids_count, disclosed_count, withheld[{id, cap}]}`, `semantic{model_id,
model_revision, embed_texts, rerank_pairs, pool_scope, pool_threads, pool_messages, pool_ids[],
shortlist{rule, k, size}}`, `disclosure{levels_traversed, levels_traversed_to_answer,
disclosed_tokens_est, ceiling_applied, per_message[{id, role, reason, depth, tokens}]}`,
`freshness{history_id, watermark_source, reconciled}`, `errors[]`,
`cost{latency_ms_total, latency_ms_per_rung, waited_ms}`, and `eval_join`.

`pool_ids[]` lives **only** in the trace, never in the response (A.7a, §H-5(b)) — it is what lets
EV-01 be joined against a real set instead of the server's account of one. Under the personal profile
it is a list of opaque Gmail IDs, which the A.11 type policy already permits (IDs and metadata are
persisted by default; bodies and subjects are not).

`(query_features, successful_route, cost)` is exactly a training example for a future learned router
(SC §9, B-05) — and note the [VERIFIED] Limited Use constraint (SN §3): a learned router may only ever
be trained on **synthetic seed-account traces or strictly per-user personalised data**, never pooled
real-mailbox content. Traces are JSONL on disk under the profile-bound type; personal-profile traces
carry no mail-derived text at any depth, including error paths.

### D.11 Error taxonomy — a closed vocabulary

*(ADV-206. The previous draft introduced `handle_expired`, `handle_stale` and the `budget` block ad
hoc and defined no error shape at all; GMAIL-06 requires token failure to be "a clear re-auth
instruction, never a confusing retrieval error".)*

**The partition rule.** Anything that still permits a **truthful partial answer** is an **in-band
field on a successful response**. Only a condition that makes the *whole call* unanswerable is an
**MCP tool error**. This keeps C-08's "never a bare empty result" and MCP-06's "fail loudly" from
pulling in opposite directions.

| Code | Surfaces as | Fires when | Remediation / affordance carried |
|---|---|---|---|
| `auth_reauth_required` | tool error | refresh token expired (the [VERIFIED] 7-day Testing clock), revoked, or password-changed | `mailweave auth` — a re-auth instruction, in those words |
| `auth_profile_underivable` | **startup failure**, server does not serve | `users.getProfile` failed at startup, so the redaction profile cannot be derived (A.4) | check network/credentials; the server refuses to start rather than guess a profile |
| `handle_invalid` | tool error | HMAC verification failed | the re-derivation call |
| `handle_key_rotated` | tool error | `key_epoch` mismatch after a deliberate key rotation (A.10) | the re-derivation call — **distinct from `handle_expired`**, which previously misattributed the cause |
| `handle_expired` | tool error | HMAC valid, TTL passed | the re-derivation call |
| `handle_stale` | tool error | liveness probe or digest mismatch; names what changed with counts | the re-derivation call |
| `handle_stale_unverifiable` | **in-band** | `history.list` 404'd on the handle's `historyId`; LRU bypassed and a live fetch performed | none needed; the response says staleness could not be verified from history |
| `budget_clamped` | in-band `budget` | a client budget below `floor_quota_units = 845` (A.7) | states requested vs applied |
| `budget_exhausted` | in-band `budget_caps_hit` | a per-query cap reached | `not_tried[]` + affordances |
| `process_quota_wait` | in-band `budget_caps_hit` | the query waited at the process governor (A.5c) | `waited_ms` |
| `process_quota_refused` | in-band, with the RetrievalReport | floor capacity unobtainable within `max_server_ms` | retry affordance |
| `upstream_rate_limited` | in-band | 429 persisting past the retry bound (A.5a) | rungs not reached + affordances |
| `upstream_unavailable` | tool error | 5xx persisting past the retry bound | retry guidance |
| `partial_source_failure` | **in-band, per source** | a sub-request inside a `threads.get`/`messages.get` fan-out failed | the source is still returned with `included` reduced, and **the failed IDs become `withheld` records** with a retry affordance (A.7a) |
| `semantic_unavailable` | in-band `not_tried` | model runtime, weights, or RSS bound (A.5c) | `force_rungs` affordance once available |
| `scan_scope_incomplete` | in-band `scan_scope` | `more_pages: true` | `scan.max_pages` affordance |
| `undecodable_content` | in-band `reductions[]` | base64url/charset failure (D.4a) | `raw` unabridged path |
| `unsupported_view` | tool error | `view:"raw"` requested (D.1) | names the supported views |

Every code is a compile-time constant in one module; adding one is a schema change with a version bump.


---

## E. Chosen / Experimental / Deferred / Rejected

**Read the correction first.** "Deferred" here means **outside this release's product boundary**
(contract §7). It does **not** mean "a required capability postponed until a benchmark justifies it" —
that gating logic is the scope misunderstanding SC §1–§5 repudiates. Semantic retrieval, structural
retrieval, ranking, query-aware disclosure and freshness handling are all **Chosen**.

### E.1 Chosen — built in this release

Lexical rung with decomposition/intersection and enumerable one-at-a-time relaxation (C-01, C-08) ·
structural retrieval computed live from thread maps: reply tree, address-keyed participants, temporal
ordering, thread position, subject/snippet relevance, multi-thread assembly (C-02) · on-demand
two-stage **local** semantic escalation with a declared bounded pool (C-03) · mechanical ranking plus
ambiguity-gated cross-encoder rerank (C-04) · the adaptive ladder with quota-native budget caps and
in-band cap reporting (C-05) · query-aware progressive disclosure with a reply-chain floor that is
**non-negotiable in membership and declared in depth** (C-06, A.9a) · **the hit-disposition ledger:
every retrieved ID disclosed or `withheld`, checked by assertion at envelope time** (I-1, A.7a) ·
map-carrier responses with per-message role, mechanical reason, constraint coverage, depth, declared
reductions and `scan_scope` (C-07) · the always-present RetrievalReport (C-08) · freshness stamps and
non-content `historyId` watermark snapshotting (C-09; the LR *rung* itself is Experimental — E.2) ·
the content-processing pipeline of D.4a · the process-wide quota governor and stated concurrency
model (A.5c) · the closed error vocabulary of D.11 · trace schema v2 with type-level
redaction and ID-based forensics (C-10, N-05) · nonce-fenced untrusted-content envelope (C-11) ·
signed self-describing handles (SC §14) · single `gmail.readonly` scope, stdio, no telemetry (N-04,
N-06, N-07) · `uv`-pinned reproducible setup (N-08).

### E.2 Experimental — built, measured, flagged, removable

| Item | Gate that decides it | Removed if |
|---|---|---|
| Segment map (second navigational level) for very large threads | **DISC-05**, measured by **`EVALUATION_PLAN.md` §7.5.1** (arms PD-DEPTH-N1 vs PD-DEPTH-N at the PF-6 token boundary) and published at **CG-PD** | the depth-*n* vs depth-*n−1* comparison shows no win ⇒ large threads get declared truncation + affordance only |
| Semantic **reuse** in disclosure scoring (T-CD3) | Loop-2 arm: mechanical vs reuse vs D-base at equal budget | no measured win ⇒ mechanical only |
| Cross-encoder rerank vs mechanical ranking alone | **RANK-02** (vs recency and seeded-random controls) | it does not beat both controls ⇒ mechanical ranking only, published as a negative result (H-07) |
| Snippet-only vs body-based pool text (RO T-RO1's "cheap middle path", explicitly unmeasured) | **PF-2 + CG-SEM** | quality cost too high ⇒ body fetch for a shorter pool |
| `answer_type_presence` escalation trigger | **CG-AD + CG-SEM + the F11/F12 trigger ablation** (EP §7.4), with its G0 base rate from **PF-13** | over/under-triggering, or a base rate so high the predicate is inert ⇒ pure query-shape trigger |
| **LR recency rung** (moved here from Chosen — CONS-031) | **FRESH-01 / MF1–MF6**, run on the named arm **`H5-LRoff`** (`EVALUATION_PLAN.md` §11.1) — MailWeave with the recency rung disabled — on which **MF6 and MF3 are evaluated** (EP §13.4 CG-FRESH), with shipped-configuration arm `H5` reported alongside, so the measured lag is the server's and not its own mitigation's | no measured recency-query benefit ⇒ LR removed and recency queries rely on `messages.list` alone, with stamps retained |
| Hosted embedding/rerank adapters | benchmarking only | never required; N-01 forbids dependence |

### E.3 Deferred — outside this release's product boundary

Exactly contract §7's table, unchanged and re-affirmed: write/draft/send tools · persistent semantic
index · persistent participant graph · learned routing policy · derived summaries and decision
timelines · attachment content extraction · `users.watch` + Pub/Sub push freshness · elicitation-based
disambiguation. Plus B-02 (non-Gmail backends) and B-03 (multi-account). **Nothing in this list may
be cited in a review to excuse a defect in a shipped capability.**

### E.4 Rejected — with the contract clause that justifies it

- **MCP Sampling for any purpose** — [VERIFIED] deprecated in spec 2026-07-28 ("new implementations
  SHOULD NOT adopt it") and never supported on the Claude-family clients we target (N-MCP-1).
- **Any generative LLM on the default path** — SC §8 permits, does not require; INJ-06's surface is
  unjustified without a measured need (D.8). Revisitable; the gate is named.
- **Message-wise semantic pool construction** — 6× the quota of thread-wise for the same pool
  ([VERIFIED] RO F7 arithmetic). A pure cost rejection.
- **Chroma / Pinecone / any vector database** — SC §11 and the stale-index paradox (CTX §45). The
  in-process vector LRU is memory-only and dies with the process; it is not an index.
- **`gmail.metadata` scope** — [VERIFIED] `q` is unusable under it and bodies are unavailable
  (N-04, SN §1.2).
- **MCP resources as the sole affordance channel** — [VERIFIED] resource exposure to the model is
  host-dependent and tool-returned links need not appear in `resources/list` (R-07, CD §5).
- **EmbeddingGemma as the zero-config default** — HF-gated (license acceptance + token), which is
  friction against NFR-04. Kept as a first-class opt-in swap.
- **`resultSizeEstimate` as any stated count** — [VERIFIED] it is an estimate (GMAIL-04, RO F1).
- **Node/TypeScript** — §B.8, with reversal criteria R1–R4.

**Where I think the contract over-scopes:** nowhere in §3's capability set. The over-scope risks I do
see are in the *rubric wording*, not the capability list — see §H.

---

## F. Loop 0 preflight

Every load-bearing assumption that code must not be built on top of until it is checked. Each is a
concrete check with a stated consequence of failure. **PF-1, PF-2 and PF-6 are blocking.** PF-4b,
PF-13, PF-14, PF-15 and PF-16 were added by the Round-1 repair; **PF-17..PF-20 by round 12**, and **PF-21 by round 28** (endpoint latency, the measurement behind `max_server_ms`), which registered four questions that were live in the code and in the round-11 handoff's guessed-shape table but named in no list a run works from (R-GMAIL round 11: G8, G3, G7; and the two scope spellings). PF-13 and PF-15 are **gate-blocking at
G0** because a design commitment rests on each (A.8b, A.10).

| ID | Check (exact) | Failure changes |
|---|---|---|
| **PF-1** | REST `threads.get(format=full)` message count vs the seeded manifest, on threads of 5 / 12 / 40 / 100 messages, on the seed account. Settles T-VR3 / #239 | If `threads.get` truncates: Baseline B is labelled **lossy** in every table, every comparison against it is re-interpreted, and **PART-01's manifest-equality bar is unachievable as written** ⇒ escalate to owner (§H-2) |
| **PF-2** | Does `threads.get(format=metadata, metadataHeaders=[Message-ID,In-Reply-To,References,Subject,From,To,Cc,Date])` actually return (a) those headers and (b) a per-message `snippet` and `internalDate`? The Format enum docs say METADATA returns "only email message ID, labels, and email headers" and do **not** mention `snippet` | (a) absent ⇒ reply-chain floor needs `format=full` (bytes/latency change, not quota). (b) absent ⇒ **primary fallback `threads.get(format=full)`** at the same 40 u (bytes/latency cost, not quota), pool text = subject+participants+body-head-400, `max_pool_threads` 25→15 with the reduced bound declared per T-RO1; only if PF-1 also shows `format=full` truncates, fall back to `messages.get(format=metadata)` with the pool hard-bounded to 60 rows (1,200 u) and the recall consequence declared; if neither is available, escalate (§I). **Not** "a cost change, not a design change" — see D.5, ADV-102 |
| **PF-3** | Empirical quota accounting: drive `messages.list` / `messages.get` / `threads.get` / `history.list` until 429 and infer the real unit costs against the published 5/20/40/2 and 6,000 u/min. Settles the standing RO F7 discrepancy flag | A ~4× tighter reality ⇒ `max_hit_threads` 12 → 6, `max_source_threads` 4 → 2, `max_pool_threads` 25 → 12, `max_quota_units` halved (1,200/2,400 → 600/1,200 — re-derived, not asserted), the reduced pool bound **declared** in every semantic response, and the **governor's per-minute budget re-set** from the measured figure (A.5c). PF-3's calibration date is carried on every published quota number (A.11) |
| **PF-4** | On the actual dev laptop, CPU only: cold model load time; per-text embed latency at real body/snippet lengths; wall clock to embed 100 / 200 / 400 texts; rerank latency for 25 pairs; RSS. For potion-retrieval-32M, bge-reranker-base (ONNX int8), Qwen3-Embedding-0.6B, EmbeddingGemma-ONNX | Sets `max_semantic_ms`, `max_pool_messages`, `max_rerank_pairs`, `max_model_rss_mb` and the default model. A stage-A **quality** failure fires **R1** (a design change: widen shortlist → shrink pool → bi-encoder stage A) |
| **PF-4b** *(new — ADV-103)* | **The Node arm.** Same pool, same laptop, same texts: `@huggingface/transformers` (ONNX q8) bi-encoder + `Xenova/bge-reranker-base`, and `node-llama-cpp` embed+rank. Report embed wall clock at 100/200/400 texts, rerank at 25 pairs, cold load, RSS | This is the measurement **R2 needs in order to be able to fire at all**. Without it the stack has no reversible latency evidence, only evidence about the path we chose. If the Node arm is materially faster at equal quality, R2 fires and the stack reopens as a finding |
| **PF-5** | (a) Anonymous (token-free) download of each candidate model via `mailweave setup-models`; record licence and SHA-256. (b) Run the full suite **cold-started**, with all egress except `gmail.googleapis.com` and `oauth2.googleapis.com` blocked — **the model host explicitly blocked**, to catch the `huggingface_hub` revalidation call that setup-time provisioning alone does not prevent (ADV-210). (c) Run D.4a's content pipeline **with sockets disabled** (INJ-04's zero-network condition) | A gated default ⇒ swap the default model. Any egress to the model host at runtime ⇒ `HF_HUB_OFFLINE` / `local_files_only` enforcement is missing or wrong and D.8 is not implemented. A parser that fetches a remote entity ⇒ INJ-04 fails |
| **PF-6** | Confirm the host output cap on the target client(s) — the [VERIFIED] 25 k default / 10 k warning and the `_meta["anthropic/maxResultSizeChars"]` raise — and set **both** self-truncation ceilings from the measurement — the 9,000-token normal ceiling and the 12,000-token floor-membership overflow (A.9a, D.4) | A lower real cap ⇒ lower both ceilings and re-tune the budget ladder before any disclosure measurement is taken. If the measured cap cannot hold the overflow, A.9a step 7 (split by source) becomes the only path and **H-9's owner decision is live** |
| **PF-7** | Drive the Python stdio server from a real MCP client end-to-end (search → map → get_messages), asserting `structuredContent`/text parity and zero host-side truncation | A Python-specific host incompatibility fires **stack reversal R3** |
| **PF-8** | Redaction canary: seed sentinels into query text and message bodies on the personal profile; grep traces, logs **and forced exception paths** for zero sentinels; verify the profile derives from `users.getProfile` and fails closed | Any leak ⇒ the `Redacted[str]` mechanism is wrong and must be fixed before real-mailbox development starts, not after |
| **PF-9** | Confirm Gmail `q` message-scoped semantics on the seed corpus: a two-constraint query whose constraints live in *different* messages of one thread returns nothing, and L1b decomposition/intersection recovers it | If `q` behaves thread-wide, L1b is unnecessary and its budget is returned to other rungs |
| **PF-10** | Freshness baseline: snapshot `historyId`, observe real delivered mail on both mailboxes, record arrival→first-surfacing per probe class, stratified by thread depth 0 vs 25 | Feeds MF1–MF6. Any MF firing makes FRESH-02 mandatory inside the loop |
| **PF-11** | Build Baseline E's honest primitives (`search_messages` with no silent cap, `get_message`, complete `get_thread`, real pagination, true totals) and run E-matched + E-generous **before** MailWeave is measured | If E cannot be built honestly, the project's central falsifier does not exist and no comparative claim may be made |
| **PF-12** | Harness OAuth: confirm the 7-day Testing-status expiry and that the seed-only test-user allowlist blocks personal-account consent at Google's side; time the re-consent flow | Blocking friction ⇒ harness moves to Production-unverified with the `getProfile` pinning assertion as the sole control (T-SN4 reversal) |
| **PF-13** *(new — ADV-104)* | **`answer_type_presence` base rate.** On a random sample of the seed corpus, per interrogative class (*when* / *how much* / *did we decide* / other), measure how often the predicate is `true` — against **quote-stripped** bodies specifically, since signatures, scheduling text and un-stripped `On … wrote:` attribution lines all carry date-like tokens. Also publish `exact_signal_match`'s **per-family firing rate** (A.8a) | A base rate near 1 means the predicate is a constant, not a signal: it is then inert as a downgrade, only its under-trigger rate matters, and E.2's removal gate is live. This number must exist **before** the design leans on the signal |
| **PF-14** *(new — ADV-204)* | **Date-boundary semantics.** On the seed account, seed messages at 23:30 and 00:30 local across an `after:`/`before:` boundary and determine empirically which zone Gmail resolves the operator in, and whether `after:` is inclusive and `before:` exclusive | A deterministic answer ⇒ `date_margin_days` drops from 1 to 0 and the change is recorded. A non-deterministic or account-dependent answer ⇒ the ±1d widening stays and is documented as an instrument limitation |
| **PF-15** *(new — ADV-002)* | **Cache-warm handle staleness.** MCP-06's mutate-then-redeem executed as **two** cases: cache-cold and **cache-warm**. Mint a `map_id`, deliver a message into the thread, redeem with the LRU populated | A warm-path pass that a mutation cannot break means the check is a tautology, not a verification. This is the case the previous design could not fail |
| **PF-16** *(new — ADV-107)* | **Suite quota budget and exclusivity.** PF-3 drives to 429 by design. Declare the suite's own per-run quota budget, an exclusive window on the project during PF-3, and a pre-run check that no other run is in flight | Contention makes PF-3's calibration wrong in the safe direction (apparent limits tighter than real), which would then propagate into every published cost number |
| **PF-17** *(new — round 12; named in `auth/consent.py` since round 11 and unregistered until now)* | **Does Google's token endpoint return `scope` on a first installed-app consent?** Record the raw token response's field set on the read client's first consent. R-GMAIL (round 11): the native-app guide lists `scope` among returned fields without the "only returned if" qualifier it gives `id_token`, but RFC 6749 §4.2.2 makes `scope` OPTIONAL precisely when the granted scope equals the requested one — which is this project's exact case. **G8, and the guess most likely to bite on the very first real run** | Absent ⇒ `verify_granted_scopes` fails closed and `auth login` cannot complete. The fix is a second read-back at `oauth2.googleapis.com/tokeninfo` (already on the runtime allowlist, and its `Tokeninfo` response documents `scope` independently of the token endpoint), **not** relaxing the check |
| **PF-18** *(new — round 12)* | **How long is a real Gmail continuation token?** Record the length and character class of every `nextPageToken` observed on `messages.list` and `history.list` during the preflight run, against the seal's 256 single-line-character bound. R-GMAIL confirmed the discovery document (`gmail:v1`, rev `20260727`) types it as a bare string with no format and no length on every listing endpoint, so nothing bounds it but us. **G3** | A token over the bound ⇒ `_sealed_page_token` refuses it and **pagination stops working entirely**; the bound is re-derived from the measurement and the seal's "narrowed, not closed" note is updated with the observed maximum |
| **PF-19** *(new — round 12)* | **Does `history.list` ever repeat a message id within one page?** Count, per page, ids appearing more than once and whether the repeats carry the same `threadId`. The client deduplicates today because the seal takes a per-id thread map and a repeated key is not a second message. **G7** | Never observed ⇒ the dedup is inert and is recorded as unexercised rather than as validated behaviour. Observed **with differing `threadId`s** ⇒ the per-id map is the wrong shape and the seal's thread attribution needs re-deriving before any thread-map claim rests on it |
| **PF-20** *(new — round 12)* | **Do the two spellings of "the whole mailbox" select the same set?** For each `MailboxScope` (`preflight/scope.py`), compare the id set from `q=<the scope's operator>` with its `includeSpamTrash` against the set an omitted `q` enumerates, on the seed account. A `q` goes through the search index and an omitted `q` enumerates, and PF-freshness-raw exists because those are not the same clock | Divergence ⇒ PF-1's listing arm is sampling a different mailbox from its `threads.get` arm and its counts are re-interpreted. The bias is known and directional — index lag can hide a message from the listing arm and cannot invent one — so it can only conceal a real PF-1 failure, never manufacture one, which is what PF-1 already declares and records |
| **PF-21** *(new — round 28)* | **What does one Gmail call cost in wall-clock time from the owner's machine?** Ten sequential calls each of `users.getProfile`, `messages.list` (one id), `messages.get(format=full)` and `threads.get(format=metadata)`, over the owner's own network; per endpoint the p50, p90 and max in milliseconds, the cold first sample reported separately. A.7 publishes `max_server_ms = 2,000` and `max_http_requests = 24` for the same query, which agree only at 83 ms per request including TLS and the round trip; nothing ever measured it — every test drives a zero-latency transport. Numbers only, no ids, no text. | `max_http_requests × slowest p90 > max_server_ms` ⇒ the published deadline cannot spend the published request cap on this network, and `max_server_ms` is re-derived from the measurement rather than asserted. The registered candidate is `max_http_requests × slowest p90` rounded up to the hundred; it is an upper-bound formula and **not the default by itself** — the proposed default is validated on neutral end-to-end searches before adoption, the constant then carries the figures and the date of the run (A.11), and the cap-table sweep test moves with it. |

---

## G. Falsifiability

`CTX` §57 asks what would prove MailWeave unnecessary. Here is each falsifier, the measurement that
would show it, and **what this architecture does in that world without abandoning the product.**

| Falsifier | Shown by | Architecture's response |
|---|---|---|
| Gmail message-level search + full thread fetch is already cheap and context-efficient enough | Baseline D + Baseline B matching MailWeave on recall at comparable tokens and latency | Ship the map-carrier layer alone. The honest claim narrows to explicit partiality — "a partial answer is labelled partial and carries a path to more" — which Baseline B structurally cannot provide and which the vendor's own tool description documents as absent (VR §0.1). The ladder above L1 becomes opt-in |
| Adaptive routing adds latency without improving retrieval | PERF-01/PERF-04 vs AD-05: cost separates but recall does not | Collapse the ladder to L0–L1 + LR, keep the RetrievalReport, publish the negative result (H-07). The escalation code stays behind `force_rungs` so the finding is re-testable |
| Semantic retrieval adds negligible recall | **SEM-05**: the paraphrase delta is inside the CI of zero | Publish the rejection with its numbers ("semantic rejected: +x recall, +y ms p95"). The rung stays behind `force_rungs`, the interface stays (SEM-03), the default trigger is disabled. Note this is a **backend/architecture** rejection, which EP explicitly still permits — it is *not* permission to delete the capability (SC §4) |
| Progressive disclosure costs more calls and worse end-to-end latency than a bigger context | DISC-04 + PERF-01 measured over the **whole transcript including follow-up rounds** | Raise the default disclosure budget so more evidence lands in round one, keep the map and the affordances. PD's value was never round-count |
| **Agents already manage thread expansion reliably with primitive tools** | **Baseline E-generous matching MailWeave on answer accuracy** | This is the one that matters most, and EP §8.7 pre-commits the response: the claim narrows to **cost, rounds, latency, predictability and explicit partiality**, in those words, in the README — enforced at the documentation-accuracy gate, not left to whoever writes the copy. The product still ships; the sentence changes |
| Target evidence is rarely buried enough to matter | The Tier-1 census showing real threads are short and hits are shallow | Report it. The position sweep (EP §4.4) stops being a headline and becomes a robustness guarantee. MailWeave's remaining value is the failure *class* — silent omission — not its frequency in one mailbox |
| Progressive disclosure's accuracy gain is near zero (2607.17598) | Already the prior, not a surprise | Already absorbed: T-1/T-VR1 route the claim onto the honest-partiality axis, and a null accuracy result is published as null. **A null result may never be reported as a win** |

The falsification discipline that makes this real rather than rhetorical: **Baseline E-generous is a
permanent fixture at every gate**, and **PF-11 requires it to exist before MailWeave is measured at
all**. We build the fairest possible opponent first.

---

## H. Flags for the owner — things I believe are unachievable or mis-worded as written

Per the instruction to flag rather than quietly design around.

**H-1 · `DISC-02` contradicts `SCOPE_CORRECTION` §6, and cites it while doing so.** DISC-02's
statement reads: "the shipped disclosure policy is measured against the fixed ±2 baseline at equal
token budget, **and the simpler policy ships if it wins** (SC §6; CTX §55)." SC §6 says the opposite:
"Do not treat fixed ±/-2 as MailWeave's final progressive disclosure policy… implement and review the
actual query-aware policy against it." `CONTEXT_DISCLOSURE_OPTIONS`'s addendum agrees, calling the
ship-the-simpler-policy clause "**genuinely invalidated as a scope decision**." As written, DISC-02
licenses exactly the scope reduction the correction forbids. **Requested:** reword DISC-02's
acceptance to "the comparison is run at equal budget and published either way; a loss is a reported
finding and a tuning input, not a scope reduction." I have built to SC §6, so if DISC-02 stands as
written, a reviewer could fail the shipped policy for existing.

**H-2 · `PART-01` may be unachievable, conditional on PF-1.** PART-01 requires `stated_total` to
equal the seeded manifest's true length on ≥98% of scored cases. MailWeave's only possible source for
that number is `threads.get`. If PF-1 confirms issue #239 — `threads.get` itself truncating on long
threads — then no implementation can pass PART-01, because there is no second oracle: Gmail has no
thread operator and no thread message-count field (T-3). **Requested — now unconditionally, not contingent on PF-1** (CONS-004):
PART-01 becomes "`stated_total` is extractable on 100 % of thread-bearing responses and equals **what
the source reported at `fetched_at`** on 100 % of cases," with the manifest-equality assertion moved
into GMAIL-03, where it belongs, because it measures the *instrument*, not the server. I will not
paper over this by inferring counts from a second call and presenting the inference as the source's
report.

**Amended after review (ADV-209).** The reviewer is right that the replacement as I first worded it is
self-satisfying: "our number equals the number we read from the call we made" is true of any
implementation, including a broken one, and "the discrepancy is published" is not a bar. So the
request now carries a **gate-binding bound**: GMAIL-03 registers, from PF-1's measurement at G0, a
ceiling on `|threads.get count − manifest length| / manifest length`, and **the criterion fails above
it**. Publication alone is not acceptance. Canonically: *a total is what the source reported at
`fetched_at`, never an unverifiable claim of absolute completeness; divergence from the seeded manifest
is a ground-truth-validation concern, not a runtime claim* — and it is bounded, not merely noted.

**Landed, and no longer an open escalation (reconciliation, Round 1).** `RELEASE_RUBRIC.md` PART-01 now
reads exactly this way — `stated_total` extractable on 100 % of thread-bearing responses and equal to
**what the source reported at `fetched_at`** on 100 % of cases, with the inference-from-a-second-call
route named as a T-3 violation — and the manifest-equality assertion sits in **GMAIL-03** with a
residual-discrepancy bound that is `[UNSET — registered at G0 from PF-1's measured
`|threads.get count − manifest length| / manifest length` distribution]` and **gate-binding**, so the
criterion can still fail. `PRODUCT_CONTRACT.md` R-08/§10 and `EVALUATION_PLAN.md` §16 carry the same
two halves. What remains is a **measurement**, not a decision: PF-1 at G0 sets the number. §I O-3 is
closed.

**H-3 · `DISC-05` will fire, by design, and that is the honest outcome.** A flat map of a
500-message thread is ~20 k tokens against a [VERIFIED] 25 k host cap — the segment map is forced by
a hard constraint, not chosen for sophistication. I am declaring the trigger met up front and
budgeting the depth-*n* vs depth-*n−1* measurement rather than defining the level away. If the
measurement does not show a win, the level is removed (E.2).

**The measurement now exists (reconciliation, Round 1).** `EVALUATION_PLAN.md` **§7.5.1** defines the
large-thread depth arm this flag budgeted for — PD-DEPTH-N1 (flat map + declared truncation +
affordance) vs PD-DEPTH-N (segment map), same cases at or above the PF-6 flat-map token boundary, same
budget, paired, reporting strict accuracy, `rounds`, `tokens_returned`, `map_tokens`,
`levels_traversed_to_answer` and latency — and CG-PD (EP §13.4) carries the gate cell that publishes it
either way. Rubric DISC-05 now names that arm in its acceptance. So DISC-05 is measurable rather than
permanently `NOT TESTED`, and E.2's removal path is live evidence, not an intention.

**Under-scoped, and corrected (ADV-208).** DISC-05's plain wording counts every separately-requestable
level, and I had scoped the commitment to the segment map alone. Two changes: **`raw` is no longer
independently requestable** (D.1), which removes a level outright; and the DISC-05 commitment is
**extended to the content-depth vocabulary** — `levels_traversed_to_answer` is instrumented over
stub → snippet → `body_clean` → `body_full` as well as over the segment map, which is what CD's T-CD1
already asks for as a first-class metric. D4's "orthogonal, not a routing hierarchy" defence is a
definitional move; from the agent's side sequential refinement is what 2607.17598 measured, so it is
recorded as a **claim to be tested**, not as a settlement. The default path is unaffected: search
returns evidence at `body_clean` in one call (C-06).

**Which branch of DISC-05's scope question this document takes (reconciliation, Round 1).** The rubric
offers two branches: drop the extra separately-requestable levels, or extend the depth measurement to
cover the content-depth vocabulary. **The second is taken, and it is the only one an agent may take** —
dropping a shipped level is a scope reduction (SC §1, §6), while extending the measurement adds an
obligation and weakens nothing. Concretely: `raw` is already not independently requestable (D.1),
`snippet` stays and must earn itself, `levels_traversed_to_answer` (EP §6.4, §7.5.1) instruments
`stub → snippet → body_clean → body_full` as well as the segment map, and any level that does not win
at matched budget is removed under E.2. No owner ruling is required for this; it is recorded as
resolved rather than escalated.

**H-4 · `SEC-07` is literally unsatisfiable as worded.** "Egress capture… shows connections only to
Gmail" cannot hold: OAuth refresh contacts `oauth2.googleapis.com`, which is not
`gmail.googleapis.com`. **Requested:** an explicit **two-host runtime allowlist — `gmail.googleapis.com` and
`oauth2.googleapis.com` (token refresh only) — and no other host**, replacing "only to Gmail"
everywhere it appears (CONS-002 lists the four documents carrying the wrong wording).

**Extended after review (ADV-210).** The allowlist must additionally name the **model host for the
setup step only**, and SEC-07/SEM-02 must be worded so that a *setup-time* download is not a runtime
egress event. Setup-time provisioning alone does **not** produce the property I claimed: the
`sentence-transformers` / `huggingface_hub` default load path revalidates the repo over the network
unless offline mode is forced. D.8 now states the enforcement (`HF_HUB_OFFLINE=1`,
`local_files_only=True`, checksum-pinned local path, never a repo id) and PF-5 verifies it by running
the suite cold with the model host **blocked**. This was a defect of the same class as H-4 that I did
not flag; it is flagged now.

**H-5 · `I-1`'s definition of `H` needs one clarifying word, or the semantic rung is
unimplementable.** I-1 defines `H` as "message IDs returned by the executed Gmail queries **and any
scored retriever**." Read literally, a semantic rung that assigns a cosine score to a 300-message pool
puts all 300 into `H`, so all 300 must appear in `R` — which collides head-on with DISC-04's token
ceiling and RANK-04's disclosure cap on the same run. **My original request is withdrawn as worded. The reviewer rejected it and was right** (ADV-109). It
had two defects: (1) "passes the retriever's **selection threshold**" hands the implementer the dial
that sets `|H|` — set the threshold at cosine 0.95 and `|H_semantic| ≈ 0`, and EV-01's exact set
assertion passes vacuously on every semantic case; EV-01's guard rules out the *inflationary*
degenerate and says nothing about the deflationary one, and I was asking to legalise the deflationary
one. (2) It narrowed only I-1's *second* clause, leaving D.5's step-(b) participant probes — which are
`messages.list` calls, so unambiguously in `H` under the **first** clause — untouched, while giving the
impression the `H` question was settled.

**Requested instead — three parts, all three or none:**

**(a)** `H` from a scored retriever = **the shortlist that enters the disclosure candidate set, whose
size is a declared, pre-registered constant** — `k = max_rerank_pairs = 25` with the selection rule
`"top-k by stage-A cosine"` — reported in every response as
`retrieval_report.shortlist{rule, k, size}`. **No score threshold selects `H`.** The size is a
published parameter, not a free implementer choice, so `|H|` cannot be tuned to make EV-01 easy.

**(b)** The **full scored pool is enumerated by ID in the trace** (`semantic.pool_ids[]`, never in the
response), so EV-01 is checked against a real set rather than against the implementer's account of one.
In the response the pool is disclosed by `pool{scope_rule, thread_count, message_count, window, why}`,
which is a stronger and cheaper disclosure than 300 stub rows.

**(c)** Step-(b) probe results are **explicitly covered by I-1's first clause** and are disposed of by
A.7a like any other `messages.list` result — disclosed, or a `withheld` record with
`cap: "max_pool_threads"` and a pool-widening affordance. This is stated in D.5 and A.7a, not left to
inference.

Canonically: **the hit set `H` is what the retriever returns as evidence candidates after its
shortlist/threshold — not every scored pool row — and the candidate pool is disclosed separately in
its own `pool` block with its size and scoping rule.** That resolves the I-1 / DISC-04 / RANK-04
collision, and it is the wording being applied identically in the contract and the rubric.

**Landed, and no longer an open escalation (reconciliation, Round 1).** All three parts are now in
force in the governing documents: `PRODUCT_CONTRACT.md` I-1 and `RELEASE_RUBRIC.md` EV-01 carry the
canonical clause quoted verbatim in A.7a, including (a) the declared, pre-registered shortlist size
and selection rule, (b) `pool{scope_rule, thread_count, message_count, why}` in the response with the
full pool enumerated **by ID in the trace** (`semantic.pool_ids[]`) and re-asserted by SEM-06, and
(c) pool-construction `messages.list` probes inside `H`'s first clause and disposed of by A.7a's
`withheld` mechanism. EV-01's guard now runs in **both** directions, so the deflationary degenerate
this flag warned about is ruled out by the criterion itself. §I O-5 is closed; nothing here awaits an
owner ruling.

**H-6 · `PERF-01` is at risk, not unachievable — and the design already answers it.** A p50 ceiling of
1.25× Baseline D is tight when MailWeave adds a `threads.get` for the map that Baseline D never makes.
Mitigations built in: the map fetch is issued **in parallel** with `messages.get`, not after; models
load lazily so a simple query never pays cold start; cold and warm are reported separately (EP §4.6).
PF-4 and PF-6 set the real numbers.

**Understated, and corrected (ADV-108).** The previous A.7 cost model omitted the map from L0 and L1
entirely, so the risk was larger than the published numbers implied — and it was not only a latency
risk. Position-within-thread (R-01) and `stated_total` (R-05) are derivable **only** from a
`threads.get`, so a rung with no map either silently costs 40 u more than published or returns a
response that is non-conforming under §5.3 regardless of retrieval quality. A.7 now prices the map
into L0 and L1, `max_map_threads` **never** governs hit-bearing threads (`max_hit_threads = 12` does,
and its overflow is a `withheld` record), and `max_quota_units` is re-derived from the corrected model
(1,200 / 2,400). H-6's own proposed mitigation is also weaker than it reads: making the map
conditional on multi-message threads does not remove the fetch, because a single-message thread still
needs the fetch to *know* it is single-message — it removes only the second one. If p50 still exceeds
the bar the honest fix remains a declared design change, not a widened bar.

**H-7 · `ROUTE-04`'s unconditional 100 % empty-diagnosis correctness is unachievable for queries with
more constraints than the relaxation probe budget** (ADV-105). ROUTE-04 requires that "on zero-hit
outcomes where dropping exactly one constraint restores results, the report names that constraint and
the count it restores; correctness of this diagnosis on constructed cases = **100 %**", with no
tolerance band. With `k` parsed constraints and a probe budget `b`, correct diagnosis is impossible
for `k > b` unless the drop ordering happens to try the right one first, and a probe budget that grows
without limit is a quota decision, not a routing one. **Built:** `max_relax_probes = min(k, 6)` (A.7),
and a third `empty_diagnosis` state — `{"status":"incomplete","tried":[…],"untried_drops":[…],
"affordance":{…}}` — because "unknown" was previously not a shape the schema could express and was
being conflated with `null`, which means the different and stronger claim *no single dropped constraint
restores results*. **Requested:** ROUTE-04's 100 % bar applies **over the drops actually attempted**,
with completeness itself reported and a pre-registered ceiling on the incomplete-diagnosis rate. If the
owner wants the bar to hold over all constructed cases, then EP's constructed set must be capped at
6 constraints, which is the honest alternative and should be stated rather than assumed.

**H-8 · `AD-04`/`CG-AD`'s "median network API calls ≤ 3" does not bound cost under HTTP batching**
(ADV-106). A counting proxy sees one HTTP request per `batch` endpoint call whatever *n* is, while
quota is charged per sub-request. A simple query issuing 1 list + 1 batch of 10 gets + 1 batch of 12
maps counts as **3** at the proxy while costing 665 u. The criterion intended to bound cost bounds
nothing, and OBS-04's "server-reported call counts agree with network-level counts" will fail
permanently or be silently reinterpreted, because the disagreement is systematic and unbounded rather
than a tolerance question. **Built:** two counters, `http_requests` and `api_calls`, defined and
separately capped (A.5b); OBS-04's tolerance binds on `http_requests` only. **Requested:** re-express
AD-04/CG-AD's bar in `api_calls` or in quota units. I have not silently reinterpreted it.

**H-9 · The E2 floor as previously worded was arithmetically impossible, and the repaired version
makes a narrower claim** (ADV-003). "Non-optional and not budget-negotiable" cannot coexist with a
9,000-token ceiling on a 40-message thread with 6 hits (~11,200 tok). A.9a resolves it by separating
**membership** (never negotiable) from **depth** (declared and degradable), tightening `body_clean`
600/250, and adding a declared 9,000→12,000 overflow reachable only for floor membership. The owner
should know that this is a real narrowing of the sentence T-CD2 previously carried, that it is the
honest version rather than the impossible one, and that F17 at each degradation tier is the
measurement that decides whether it is enough. **If F17 shows the floor at the depth the budget
actually produces does not beat Baseline F(±2), the requirement is not satisfiable at this ceiling and
the choice is the owner's:** raise the ceiling further, disclose fewer hits at body depth, or accept a
narrower claim for the floor. I am not making that choice quietly.

**H-10 · `PART-01`/`R-01` and the `withheld` mechanism — one reading to confirm.** A.7a caps
hit-bearing thread maps at 12 and turns the overflow into `withheld` records. That is conformant on
the reading that R-01 ("every message **present** carries … its position within that thread") and
PART-01 ("every thread **represented** declares its total") govern messages and threads that appear in
the payload, and that a `withheld` record — an id, a reason, a cap and a working affordance — is
exactly what I-1 contemplates instead. **Requested:** confirm that reading. If the owner instead reads
R-01/PART-01 as binding on withheld IDs too, then `max_hit_threads` must be unbounded, the quota model
changes materially, and that is a budget decision rather than a design one.

**Nothing in `PRODUCT_CONTRACT` §3's capability set is over-scoped.** The eleven capabilities are
buildable as specified within the budgets in §A.7, on the stack in §B.8, with the caveat that PF-1
through PF-6, PF-13 and PF-15 must land before the numbers in §D are anything more than starting values.

---

## I. For owner decision — reconciled after Round 1

*(Rewritten by the Round-1 **reconciliation** pass. The original table listed O-1…O-8 as open. Five of
the eight were closed by the parallel repair of `PRODUCT_CONTRACT.md`, `RELEASE_RUBRIC.md` and
`EVALUATION_PLAN.md`, which landed exactly the wording this document asked for; one is settled by a
named measurement; two remain genuinely the owner's. **Only the genuinely-owner items appear in
`docs/OWNER_DECISIONS.md`**, which is the single consolidated list. Per the repair rule, nothing was
closed by softening a requirement — every closure below points at wording that is at least as strong as
what this document asked for.)*

| # | Item | Outcome | Where it is settled |
|---|---|---|---|
| **O-1** | `ROUTE-04`'s **100 % empty-diagnosis correctness** for `k > max_relax_probes` | **RESOLVED (owner, 2026-08-30)** — `OWNER_DECISIONS.md` **OD-2**. Correctness over untried drops is unreachable at any probe budget short of `k`; the two honest repairs (scope the bar to attempted drops + a registered ceiling on the `incomplete` rate, or cap the constructed set at 6 constraints) differ in what MailWeave *promises*, which is not an agent's call | Built: `max_relax_probes = min(k, 6)` and the third `empty_diagnosis` state (A.7, D.2). ROUTE-04 **re-scoped by OD-2**: 100 % over drops *actually probed*, plus an `[UNSET — register at G0]` ceiling on the `incomplete` rate. MailWeave never promises correctness over untried drops |
| **O-2** | `AD-04`'s **"median network API calls ≤ 3"** as a cost bound | **DEFERRED TO MEASUREMENT** — the counter was wrong, not the intent. AD-04 now binds a real cost counter, `api_calls`, whose value is `[UNSET — registered at G0 per EP §13.2 against the G0-measured Baseline D `api_calls` distribution]`; the preserved ≤3 figure is retained as an `http_requests` bar, which is what OBS-04 cross-checks. No number was invented | `RELEASE_RUBRIC.md` AD-04; `EVALUATION_PLAN.md` §13.4 CG-AD (Added); A.5b here |
| **O-3** | `PART-01` **manifest equality** | **RESOLVED** — canonical semantics "what the source reported at `fetched_at`" at 100 %; manifest equality moved to **GMAIL-03** with a **gate-binding** residual-discrepancy bound registered from PF-1 at G0 | `RELEASE_RUBRIC.md` PART-01 + GMAIL-03; `PRODUCT_CONTRACT.md` R-08; §H-2 above. Residual is PF-1's *number*, not a ruling |
| **O-4** | `SEC-07`/`SEM-02` **"only Gmail"** | **RESOLVED** — two-host runtime allowlist + setup-time-only model host + forced-offline runtime loading, verified cold with the model host blocked | `RELEASE_RUBRIC.md` SEC-07, SEM-02; `PRODUCT_CONTRACT.md` N-06; `EVALUATION_PLAN.md` §7.1 bar 2, §3.9 S14; D.8 + PF-5 here |
| **O-5** | `I-1`'s `H` for a scored retriever | **RESOLVED** — the three-part amendment landed verbatim in contract I-1 and rubric EV-01, including the declared pre-registered shortlist size, the `pool{…}` block with by-ID trace enumeration, and pool-construction probes inside `H`. EV-01's guard now runs in both directions | `PRODUCT_CONTRACT.md` I-1; `RELEASE_RUBRIC.md` EV-01 + SEM-06; A.7a and §H-5 here, quoting the canonical clause |
| **O-6** | The **E2 floor at the token ceiling** | **DEFERRED TO MEASUREMENT, with an owner *acceptance*** — `OWNER_DECISIONS.md` **OD-3**. PF-6 sets both ceilings from the measured host cap; **F17** (EP §4.7, bound at CG-PD) at each degradation tier decides whether membership-plus-degraded-depth is enough. What the owner is asked to accept now is the *narrowing itself* — the floor guarantees **presence**, not full text — and to pre-authorise the branch if F17 fails | A.9a, D.4, §C T-CD2, §H-9 here; `EVALUATION_PLAN.md` §4.7 F17 + §13.4 CG-PD |
| **O-7** | `DISC-02`'s ship-the-simpler clause | **RESOLVED** — DISC-02 rewritten: the comparison runs at equal budget over ≥3 budget levels and is **published either way**; a loss is a reported finding and a tuning input, **never** a scope reduction; fixed ±2 may never ship as the policy and stays a permanent fixture | `RELEASE_RUBRIC.md` DISC-02 (CONS-001); `PRODUCT_CONTRACT.md` C-06; `EVALUATION_PLAN.md` §8.7, §8.8 |
| **O-8** | Cross-document changes this repair could not make | **RESOLVED except where O-1/O-2 carry the residue.** Landed in parallel: EP **§4.7 F17**, EP **§7.4 F11/F12 trigger ablation**, EP **§7.5.1 depth arm**, EP **§11.1 arm `H5-LRoff`**; contract **I-1** and **§5.1** collapsed-run allowance; rubric **DISC-02**, **PART-01/GMAIL-03**, **SEC-07/SEM-02**. Not applied by that pass: **AD-04** (now O-2) and **ROUTE-04** (now O-1) | This document's §C, §E.2, §H and D.8 now cite the landed locations rather than requesting them |
| **O-9** *(new)* | **H-10's reading** — do `R-01`/`PART-01` bind on **withheld** IDs? | **RESOLVED** — the repaired contract and rubric answer it in their own words: `R` = IDs present at any depth **plus** IDs listed as `withheld` (I-1), I-2 binds "for every thread **represented**", and PART-01 binds on "**thread-bearing responses**". A `withheld` record with `{id, thread_id, why, cap, affordance}` is therefore conformant, and `max_hit_threads` stays bounded | `PRODUCT_CONTRACT.md` I-1/I-2; `RELEASE_RUBRIC.md` PART-01, EV-01, EV-03; A.7a here |

**Two further owner items exist that this document never raised**, because they are not architecture
questions — they are in `docs/OWNER_DECISIONS.md` for completeness: **OD-1**, the Freshness Service
Level (`EVALUATION_PLAN.md` §11.2.2 says in terms that the plan may not set it), and **OD-4**, whether
an implementer agent may run `mailweave inspect` against the personal mailbox. **Both are DECIDED
(2026-08-30) — see `OWNER_DECISIONS.md`;** OD-4's ruling is applied at `EVALUATION_PLAN.md` §2.4.6.

**Nothing in this repair or this reconciliation reduced a capability, a budget obligation or a
disclosure obligation in order to make a finding go away.** Where the arithmetic did not permit the
previous wording, the wording was narrowed to what is true and the gap was escalated, not absorbed.

---

## REPAIR LOG (Round 1)

Source reviews: `docs/reviews/ARCH_REVIEW_1.md` (4 BLOCKER, 10 HIGH, 14 MEDIUM, 4 LOW) and the
architecture-relevant findings of `docs/reviews/CONSISTENCY_AUDIT_1.md`. Every BLOCKER and HIGH is
listed. **No BLOCKER or HIGH is left unclosed**; five carry an owner decision recorded in §I, which is
an escalation, not an omission.

| Finding | Sev | What changed | Section |
|---|---|---|---|
| **ADV-001** | BLOCKER | `H` defined (lexical pages + history IDs + declared shortlist); **`withheld := H − disclosed` computed as a set difference at envelope time** with an in-code assertion, so a cap that forgets fails loudly instead of dropping silently; withheld record shape `{id, thread_id, why, cap, affordance}` with a cap→affordance table covering L1/L2/L3, LR, the L5 pool probes and the token ceiling; `scan_scope` made a first-class per-query field with a page budget and a widening affordance; worked trace of the reviewer's own 46-ID reproduction | **A.7a** (new), A.2 §6, A.7, D.2, D.5, D.11 |
| **ADV-002** | BLOCKER | Circular digest check replaced by an **independent `history.list` liveness probe** (2 u) that does not read the cached artifact and 404-bypasses the LRU; LRU given TTL 60 s, 64-entry bound, key `(thread_id, history_id_at_fetch)` and eviction rules; **`fetched_at` is the cache-entry time, never restamped**, with a separate truthful `verified_at`; digest recomputation retained as defence-in-depth and *labelled a tautology on cache hits*; MCP-06 mutate-then-redeem required cache-warm (**PF-15**) | **A.10** (rewritten), D.2, §F |
| **ADV-003** | BLOCKER | Pool cap renamed **`max_pool_threads`** and pool declared **not a source** (no map, no stub rows) — removes the 287-row/11,480-tok case structurally; E2 floor restated as **non-negotiable in membership, declared-and-degradable in depth**; **published 8-step degradation precedence**; `body_clean` 1,000→600 with a 250-tok head-truncation step; declared **9,000→12,000 floor-only overflow ceiling**; re-derivation showing the ladder terminates on the reviewer's 40-message case; T-CD2 rewritten honestly with a **non-empty `Reversed by`** (F17 at each tier) | **A.9a** (new), A.9, D.4, A.7, §C T-CD2, §I O-6 |
| **ADV-004** | BLOCKER | **`exact_signal_match` defined normatively** as three enumerated branches (E-a `rfc822msgid`+`hit_count==1`; E-b verified verbatim phrase ≥3 tokens, `hit_count∈[1,3]`; E-c published structured-identifier lexicon) with "unique token"/frequency **withdrawn**; made a required trace field with its firing inputs; **ordering bug fixed** — `answer_type_presence` is now D.3 **rule 0**, evaluated before any stop, and only branch E-a stops unconditionally; **per-family firing rate pre-registered and published at G0**, including inside CG-SEM's SEM-OFF reference so the contamination §3 identified is visible | **A.8a/A.8b** (new), D.3, A.7, §C T-RC2 |
| **ADV-101** | HIGH | `historyId` **watermark persisted** in a named non-content `state/watermark.json` (0600; `{account_hash, history_id, observed_at}` only) — compatible with B-06/N-03 and purgeable; LR repriced **`2 + 20n`**, `n ≤ 8`, overflow → `withheld`; **closed re-check subset published** (from/to/cc, after/before on epoch ms, has:attachment, label:) with free-text explicitly **not** re-checked and a verbatim provenance string that never claims a Gmail `q` match | D.9, A.7, §C T-4, D7 |
| **ADV-102** | HIGH | PF-2's failure branch rewritten: it is a **design change**, and the old fallback cost the entire 6,000 u/min budget. Ranked real fallbacks — (1) `threads.get(format=full)` at the same 40 u with `max_pool_threads` 25→15 and the reduced bound declared per T-RO1; (2) bounded `messages.get` with a hard 60-row pool (1,200 u) and declared recall consequence; (3) escalate | D.5, §F PF-2 |
| **ADV-103** | HIGH | Overstated claim withdrawn: cited source says "static **or** a small bi-encoder", and the cost attributed to a Node bi-encoder was the quota cost thread-wise pooling already solved. Verified re-check: transformers.js model2vec support is an **open, unimplemented issue**, and model2vec ONNX exports **do** exist — so "only in Python" was false. Decision **re-justified on the API-surface asymmetry** (one library covering static + bi-encoder + cross-encoder), which is *stable under the design's own stage-A swaps* where the old argument evaporated. **R1 rewritten single-conjunct with a design consequence**; **PF-4b adds a Node arm** so R2 can fire; ~18 % MTEB deficit recorded as a live risk | **B.3, B.7, B.8**, §F PF-4b |
| **ADV-104** | HIGH | T-RC2 and A.8 repointed to **CG-AD** (confusion table, both off-diagonals) + **CG-SEM** (F11 `semantic_gain`, F12 ceiling) + the F11/F12 trigger ablation; **PF-9 reference deleted**; **PF-13** added to measure `answer_type_presence`'s **base rate per interrogative class** at G0, against quote-stripped bodies, with the "predicate may be near-constant" risk stated | A.8b, §C T-RC2, §F PF-13, E.2 |
| **ADV-105** | HIGH | `max_relax_probes = min(k_constraints, 6)`; third `empty_diagnosis` state `{"status":"incomplete", tried, untried_drops, affordance}`, distinguished from `null` ("no single drop restores"); ROUTE-04's unconditional 100 % bar escalated | A.7, D.2, **H-7**, §I O-1 |
| **ADV-106** | HIGH | **`http_requests` and `api_calls` split** and separately defined, capped (`max_http_requests = 24`, `max_api_calls = 80`) and bound: OBS-04 binds on `http_requests` only; `quota_units` demoted to **diagnostic**; the impossible `max_gmail_calls = 40` corrected; AD-04 escalated | A.5b, A.7, A.11, **H-8**, §I O-2 |
| **ADV-107** | HIGH | **A.5c added**: process-wide **quota governor** (token bucket sized to the PF-3-measured per-minute budget) with a `floor_reserve = 900 u`; **concurrency stated** (`max_concurrent_queries = 2`, single event loop, locks named); **single-flight model loading** with an RSS bound; retry accounting (every attempt charged, bounded backoff clamped to the remaining clock); **mid-rung timeout contract** (partials emitted, `not_tried`, caps named, unfetched hits → `withheld`); suite quota budget **PF-16**; the honest ≈2.7-escalated-queries/min figure published rather than hidden | **A.5c** (new), A.7, D.11, §F PF-16 |
| **ADV-108** | HIGH | L0/L1 cost lines corrected to include thread maps; `max_map_threads` **never** governs hit-bearing threads — `max_hit_threads = 12` does, with overflow → `withheld`; `max_quota_units` re-derived and **shown** (1,200 / 2,400); recoverability floor **costed at 845 u** with a clamp-and-report rule; H-6 corrected as understated | A.7, **H-6**, **H-10** |
| **ADV-109** | HIGH | **H-5 withdrawn as worded and rewritten in three parts**: shortlist size is a *declared pre-registered constant* (`k = max_rerank_pairs = 25`), not an implementer threshold; pool enumerated **by ID in the trace**; D.5 step-(b) probe results **explicitly covered** by I-1's first clause and disposed of by A.7a | **H-5**, A.7a, D.5, D.2 |
| **ADV-110** | HIGH | Mandatory **`score.basis`** naming the embedded text; **mixed-scale ranking forbidden** within one fill (`ordering_effect: false` unless the cosine exists for every candidate); "zero marginal cost" scoped to the pool∩fill intersection with the mechanical fallback stated | A.9, D.7, D.2 |
| ADV-201 | MED | Rate table completed for all six endpoints; `users.getProfile` added; `labels.list` given its consuming capability (LR's `label:` re-check) instead of being dead; budget arithmetic shown | A.5, A.7 |
| ADV-202 | MED | HTML→text parser (**selectolax**, MIT; lxml fallback) and quote stripper (**talon**, Apache-2.0) named with licences; `hidden_content` added to the `reductions` vocabulary; sockets-disabled obligation added to PF-5 | **D.4a** (new), D.2, §F |
| ADV-203 | MED | Full content-decoding pipeline: part selection, base64url, charset ladder, RFC 2047, undecodable-byte declaration, pre-embedding normalisation; B.5's overstatement corrected (Gmail parses MIME; the risk is decoding/part selection) and R4 narrowed accordingly | **D.4a**, B.8 R4 |
| ADV-204 | MED | Timezone policy stated once: host IANA zone declared in `asked_for`, absolute `window_utc` emitted, ±1 d boundary widening declared, all comparisons UTC-epoch, stamps RFC 3339 Z; **PF-14** measures the real boundary | **A.6a** (new), D.2, §F |
| ADV-205 | MED | Seed profile requires a **second condition config cannot fake** (harness OAuth `client_id`, whose Google-side allowlist excludes the personal account); salt provenance and storage specified; failed `getProfile` made **fatal at startup** | A.4, D.11, PF-8 |
| ADV-206 | MED | **D.11 closed error vocabulary** with the in-band vs tool-error partition rule, remediation and affordance per code | **D.11** (new) |
| ADV-207 | MED | `messages.attachments.get` **removed** from the surface; `mode:"metadata"` served from `payload.parts` | A.5, D.1 |
| ADV-208 | MED | `view:"raw"` no longer independently requestable (rejected with `unsupported_view`), removing one DISC-05 level; H-3's commitment extended to the content-depth vocabulary | D.1, H-3 |
| ADV-209 | MED | PART-01's replacement given a **gate-binding discrepancy ceiling** under GMAIL-03 rather than "published" | **H-2** |
| ADV-210 | MED | Runtime forced offline (`HF_HUB_OFFLINE=1`, `local_files_only`, checksum-pinned local path); model host allowlisted **setup-time only**; PF-5 verifies cold-start with the host blocked | D.8, **H-4**, §F PF-5 |
| ADV-211 | MED | Quota units labelled **diagnostic**; headline cost metric is `api_calls` × the PF-3-calibrated table, with the calibration date carried | A.11, A.5b |
| ADV-212 | MED | HMAC key persisted in the token store with a `key_epoch`; distinct **`handle_key_rotated`** class; floor cost published (845 u) with a clamp-and-report rule | A.10, A.7, D.11 |
| ADV-213 | MED | Coupling rules moved from "enforced by review" to **three CI gates** (import-linter contract, grep sweep job, scope-literal sweep) plus directory/working-directory isolation | B.9 |
| ADV-214 | MED | Hand-rolled client given a reversal criterion **R5**; transport named as first-class components (pager, batcher, retrier, decoder) | A.5a, B.8 R5 |
| ADV-301 | LOW | T-RC2 cites F11 with F12 as its negative control; stale "under-represented" clause dropped | §C T-RC2 |
| ADV-302 | LOW | T-CD2's `Reversed by` filled; **F17** raised as a concrete change request against EP §4.7 with name, n, construction and binding arm | §C T-CD2, §I O-8 |
| ADV-303 | LOW | B.3's "second signal" (transformers.js release cadence) **deleted** — B.8 says a release is not a reversal criterion, so it was never load-bearing | B.3 |
| ADV-304 | LOW | `retrieval_report.scan_scope[]` added with `page_size`, `pages_fetched`, `more_pages` and an affordance | D.2, A.7a |
| CONS-007 | HIGH | F17 requested against EP §4.7 and cited from T-CD2 | §C T-CD2, §I O-8 |
| CONS-016 | HIGH | "PF-9/CG-EP" replaced by CG-AD + CG-SEM + the F11/F12 trigger ablation | A.8b, §C T-RC2 |
| CONS-025 | HIGH | D.4a names every content-processing component with its licence | **D.4a** |
| CONS-031 | MED | LR moved from Chosen to **Experimental with a removal gate**, plus the LR-off freshness arm | E.1, E.2, §C T-4 |
| CONS-029 | LOW | "NFR-08" → contract N-08 / rubric NFR-04 | B.6 |
| CONS-036 | LOW | A.7's L1 stop rule gains `∧ answer_type_presence`, matching D.3 rule 2 | A.7 |
| CONS-037 | LOW | Stale "currently under-represented" clause corrected to cite EP §4.7 F11/F12 | §C T-RC2 |

**Findings NOT closed, and why:** none is left open on this document's side. Six items are **closed
here and escalated in §I** because the residual decision is the owner's, not the architecture's — O-1
(ROUTE-04's bar), O-2 (AD-04's bar), O-3 (PART-01's oracle), O-4 (SEC-07's wording), O-5 (I-1's `H`),
O-6 (the floor at the ceiling); each carries a built mechanism plus a requested wording change, not a
deferral. **O-8's items are out of this document's ownership** — they are changes to
`PRODUCT_CONTRACT.md`, `RELEASE_RUBRIC.md` and `EVALUATION_PLAN.md` being applied in parallel; this
document states the canonical wording it has built to so the two halves land identically.

**Re-review scope for Round 2**, per ARCH_REVIEW §4: **R-RETR** (A.7, A.7a, A.8a, D.3, D.5, H-5),
**R-DISC** (A.9, A.9a, D.4, T-CD2), **R-MCP** (A.10, D.11), **R-PERF** (A.5b, A.5c, A.11),
**R-SEC** (A.4, D.4a, D.8, B.9), **R-ARCH** (A.5, B.3, B.8) — and a second adversarial pass on the
degenerate build of ARCH_REVIEW §3 now that `exact_signal_match` is defined.


---

## REPAIR LOG — Round 1 — reconciliation

*Applied by the reconciliation pass after the contract/rubric/evaluation repair landed in parallel.
Purpose: make this document say exactly what those three now say, close the escalations that their
repairs settled, and hand only the genuine owner questions to `docs/OWNER_DECISIONS.md`. No
requirement was weakened; two edits **add** obligations (D.4a's status, DISC-05's branch), and the
rest are mirrors or pointer corrections.*

| # | What changed | Section | Why |
|---|---|---|---|
| **M-1** | **`H` / shortlist / `pool` wording replaced with the canonical clause, quoted rather than paraphrased**, from `PRODUCT_CONTRACT.md` I-1 and `RELEASE_RUBRIC.md` EV-01: the shortlist that enters the disclosure candidate set, not every scored row, with the shortlist size **and selection rule** a declared, pre-registered parameter reported in the retrieval report. MailWeave's declared parameter (`rule: "top-k by stage-A cosine"`, `k = max_rerank_pairs = 25`, reported as `retrieval_report.shortlist{rule,k,size}`) is stated as the *instantiation* of that clause, so a reviewer reading either document gets the same rule and the deflationary degenerate stays ruled out. `H`'s first clause now also carries the rubric's explicit "relaxation/broadening `messages.list` calls and the participant `from:`/`to:` probes" phrasing | **A.7a**, **H-5** | CONS-003 / ADV-109; O-5 |
| **M-2** | **Egress property mirrored and marked landed**: two runtime hosts, setup-time-only model host, forced-offline runtime loading, cold-start verification with the model host blocked — with the four documents that now carry it named (contract N-06; rubric SEC-07, SEM-02; EP §7.1 bar 2, §3.9 S14) | **D.8**, H-4 | CONS-002 / ADV-210; O-4 |
| **M-3** | **PART-01 → GMAIL-03 split marked landed**: runtime asserts "what the source reported at `fetched_at`"; manifest equality lives in ground-truth validation under GMAIL-03 with a **gate-binding** discrepancy bound registered from PF-1 at G0. The residue is a number PF-1 produces, not an owner ruling | **H-2**, T-3 | CONS-004 / ADV-209; O-3 |
| **M-4** | **T-RC2's resolution pointer** made explicit: **CG-AD + CG-SEM + the F11/F12 trigger ablation, which has now landed at `EVALUATION_PLAN.md` §7.4** and is a published CG-AD gate cell. **CG-EP was deliberately not reinstated** — ADV-104 established that CG-EP's bars (recall, FNF, Baseline-B proximity, hallucinated-found) measure no escalation trigger, so citing it would return T-RC2 to being settled by an instrument that cannot test it. Recorded here rather than applied silently | **§C T-RC2**, A.8b | ADV-104, CONS-016 |
| **M-5** | **T-CD2 cites F17 as landed**, not as a request: `EVALUATION_PLAN.md` §4.7 (n = 8) and CG-PD's requirement that it be "scored strictly in both the query-aware and Baseline F(±2) arms", at all three floor depths | **§C T-CD2** | CONS-007 / ADV-302 |
| **M-6** | **DISC-05's depth arm now exists and is cited**: `EVALUATION_PLAN.md` **§7.5.1** (PD-DEPTH-N1 vs PD-DEPTH-N at the PF-6 flat-map token boundary, paired, reporting accuracy/rounds/tokens/`map_tokens`/`levels_traversed_to_answer`) plus CG-PD's depth line, in T-1, T-CD1, H-3 and E.2 | **§C T-1/T-CD1**, **H-3**, **E.2** | CONS-006 |
| **M-7** | **DISC-05's scope branch chosen and recorded as resolved**: the measurement is extended to the content-depth vocabulary rather than levels being dropped, because dropping a shipped level is a scope reduction an agent may not make (SC §1, §6) while extending the measurement adds an obligation. `raw` was already made non-independently-requestable (D.1); `snippet` stays and must earn itself under E.2 | **H-3** | ADV-208; removes rubric/contract/EP owner item 5 |
| **M-8** | **LR enters the evaluation arm set by name**: E.2's gate cell now names arm **`H5-LRoff`** (`EVALUATION_PLAN.md` §11.1) as the arm MF6 and MF3 are evaluated on, with shipped-configuration arm `H5` reported alongside (EP §13.4 CG-FRESH) | **E.2**, T-4 | CONS-031; closes both halves |
| **M-9** | **CONS-025 closed here, explicitly.** D.4a gains a status paragraph stating that INJ-04, GMAIL-02 and DISC-03 now rest on named, licensed components (selectolax MIT · lxml BSD fallback · talon Apache-2.0 with an MIT fallback · stdlib `email`), and that the rubric's and plan's "NOT CLOSED — not ours" entries are updated to point here | **D.4a** | CONS-025 |
| **M-10** | **§I rewritten as a reconciled table.** O-3, O-4, O-5, O-7 → **RESOLVED**; O-2 → **DEFERRED TO MEASUREMENT** (G0 registration of AD-04's `api_calls` bar); O-6 → **DEFERRED TO MEASUREMENT** (PF-6 + F17) **with an owner acceptance** of the membership-not-full-text narrowing; O-1 → **OWNER**; O-8 → resolved except the AD-04/ROUTE-04 residue, which is now O-1/O-2; **O-9 added and resolved** — H-10's `withheld` reading is answered by the repaired contract's own words (`R` includes `withheld`; I-2 binds on threads *represented*; PART-01 on *thread-bearing responses*), so `max_hit_threads` stays bounded | **§I** | reconciliation |

**What this pass did *not* do.** It did not change `ROUTE-04`'s 100 % bar (OD-2 is the owner's), did not
set the Freshness Service Level (OD-1 is the owner's by EP §11.2.2's own terms), did not invent any
number — every bar it touched is `[UNSET]` with its registration procedure named — and did not
reinstate the CG-EP pointer in T-RC2 for the reason recorded in M-4.
