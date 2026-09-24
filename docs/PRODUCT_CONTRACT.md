# PRODUCT_CONTRACT.md — What "MailWeave works" means

**Status:** authoritative product definition.
**Governed by:** `docs/SCOPE_CORRECTION.md` (owner direction; §15 settled principles, §16 required
documents, Appendix A binding decisions). Where this document and `SCOPE_CORRECTION.md` disagree,
`SCOPE_CORRECTION.md` wins and this document is corrected.
**Companion:** `docs/RELEASE_RUBRIC.md` — this document states *what must be true*; the rubric states
*how it is measured and who confirms it*. `docs/AGENT_LOOP.md` defines the loop that enforces both.
**Not in scope for this document:** implementation plan, technology selection, exact tool names,
algorithms, file layout. Those belong to `ARCHITECTURE_DECISION.md` (`MAILWEAVE_CONTEXT.md` §32,
Decision 12).

---

## 0. How to read this

- **MUST / MUST NOT** — a release-blocking obligation. Every MUST has at least one rubric criterion.
- **SHOULD** — required unless architecture records a justification in `ARCHITECTURE_DECISION.md`.
- **Clause IDs** (`C-…`, `I-…`, `R-…`, `N-…`, `B-…`, `H-…`) are stable and are cited by rubric
  criteria and reviewer findings.
- Every clause states an **observable**: something a reviewer who did not write the code can check
  from tool responses, traces, tests, or the codebase. A clause with no observable is a defect in
  this document, not a soft requirement.
- Load-bearing facts cite their source: `CTX` = `MAILWEAVE_CONTEXT.md`, `SC` = `SCOPE_CORRECTION.md`,
  `RO` = `RETRIEVAL_OPTIONS.md`, `CD` = `CONTEXT_DISCLOSURE_OPTIONS.md`, `SN` = `SECURITY_NOTES.md`,
  `RT` = `ROUTING_OPTIONS.md`, `VR` = `VERIFIED_RESEARCH.md`, `EP` = `EVALUATION_PLAN.md`.
- **EP citations are to `EVALUATION_PLAN.md` Revision 2.** Revision-1 section numbers are stale and
  resolve to unrelated material (CONS-009).
- **Canonical vocabulary (one name per concept; CONS-033).** Tool names are `mailweave_*`, fixed by
  `ARCHITECTURE_DECISION.md` D.1. Disclosure depth is `stub / snippet / body_clean / body_full / raw`.
  Roles are the seven values of R-02. The per-message reason field is `reason`. The source-reported
  thread count is `stated_total` in the wire schema (`claimed_total` is only the evaluation harness's
  normalised name for it, EP §6.2). Cross-call state travels as a server-minted `map_id`; "cursor" is
  retired, because no design in this set produces one. Query-term coverage is `asked_for.term_coverage`;
  the long form `query_term_coverage` is retired. Substrates are Tier 1/2/3, execution modes are M1/M2,
  gates are G0 + `CG-*`, preflights are `PF-n`; "Loop *n*" survives only as `AGENT_LOOP.md` §5's round
  loop. Retrieval ladder rungs use `ARCHITECTURE_DECISION.md` A.7's numbering (L0–L3 lexical, L4
  structural, L5 semantic, L6 ranking, L7 disclosure, LR recency).

---

## 1. Product definition

> **MailWeave — query-aware adaptive retrieval with progressive context disclosure for email agents.**

MailWeave is a Gmail-backed MCP server that sits between a mailbox and an agent and answers the
question *"what evidence does this query require, and what is the smallest representation that
preserves that evidence while giving the agent an explicit path to more?"* (CTX §2).

**The problem it solves.** A retrieval layer can identify the correct message and then hand the agent
a representation from which that message is missing, with no marker that anything was withheld. The
agent then reasons over incomplete evidence and produces a confident false negative — "that email
does not exist" (CTX §1–§2). This is live, reproduced, and vendor-acknowledged: the deployed Gmail
connector's own tool description states that search results are previews of the ~5 oldest messages
per thread and that **no truncation marker is shown** (VR §0.1, §0.2). The failure is a class, not an
incident: silent HTML dropping, silent body loss, sender-specific silent misses, and thread-fetch
truncation are all reported in the same ecosystem (VR §11).

**The thesis.** The fix is not a larger fixed slice. There is no correct fixed *K* when the relevant
message can be #2, #37 or #99 (CTX §38). The fix is to make retrieval query-aware and adaptive, and
to disclose context progressively **without ever destroying the evidence that caused the match**.

**"MailWeave works" means** all four invariants of §4 hold, every capability clause of §3 is
observably satisfied, the MCP surface obligations of §5 are met on every response, and the public
claims obey §8. It does **not** mean "the minimal thesis test passed" (SC §1–§2).

---

## 2. Problem unbundling — what MailWeave does NOT claim

Three distinct problems are routinely conflated. MailWeave MUST keep them separate in code, in
measurement, and in every public sentence (CTX §4, §58; SC §12).

| | Problem | MailWeave's position |
|---|---|---|
| **A** | **Representation omission** — search identifies the evidence; the representation handed to the agent omits it | **Core scope.** This is what MailWeave is for. |
| **B** | **Search freshness** — the evidence exists but the search layer does not surface it yet | **Investigated and measured, not assumed solved.** Claims only after the CG-FRESH freshness protocol runs (EP §11; §3 C-09, §8 H-04). Evidence to date is that lag is account- and thread-variable, not universal (VR §11). |
| **C** | **Semantic retrieval gap** — the evidence exists and is searchable, but the user's wording does not match the mail's wording | **Core capability as an escalation path** (SC §4), with its *measured contribution* reported separately from A. |

**Explicit non-claims for this release.** MailWeave does not claim: to have solved the general
optimal-representation problem (CTX §8); that progressive disclosure improves any agent on any corpus
— controlled evidence says the gain depends on the harness and can be ~zero when a strong agent
already navigates well (VR §8.1); that it fixes Google's hosted server (it replaces it on the read
path); that semantic retrieval improves recall by any amount not yet measured; or that any number in
this repository was observed unless an experiment log entry contains it.

---

## 3. Capability inventory

Each capability is a contract clause: a requirement, the observable behavior a reviewer checks, and
the observable that would prove a violation.

### C-01 — Lexical / deterministic retrieval (the cheap first rung)

**Requirement.** MailWeave MUST use Gmail's message-level search (`users.messages.list(q=…)`) as its
default first retrieval path, and MUST carry the returned message IDs through to the response. Gmail's
native search unit is the message, so the evidence that caused a match is identified *before* any
representation layer touches it (RO F1). Deterministic parsing of the user's query into Gmail `q`
operators is the first rung of the ladder, not the whole system (SC §3).

**Observable.** For any query, the trace records the executed `q` string(s) and the message IDs each
returned; every such ID is reachable in the response (§4 I-1). Exact-signal queries
(`rfc822msgid:`, quoted phrase, unique token) resolve without invoking any escalation rung.

**Violation.** A response whose underlying `messages.list` returned ID *m*, where *m* appears in no
form in the response and no `withheld` record names it.

**Bounded by fact.** The API has no thread operator and requires all `q` terms to match within a
*single* message (RO F2, F3). A query whose constraints are satisfied jointly by different messages
of a thread therefore MUST be handled by client-side decomposition/intersection, not by assuming
Gmail-UI thread semantics.

### C-02 — Structural retrieval

**Requirement.** MailWeave MUST be able to retrieve and select context using email's structure, not
only adjacency: reply relationships, participant relationships, temporal relationships, thread
position, subject/snippet relevance, and multi-thread relationships (SC §5). These MAY be computed
live from thread maps; a persistent graph or database is an architecture choice, not a requirement
(SC §5, §11).

**Observable.** (a) Reply parents/children are reconstructed from `In-Reply-To`/`References`, and
messages that could not be linked are declared as unlinked rather than silently re-parented; (b)
participant matching keys on the *address*, never the display name, and distinguishes
**authored-by-X** from **mentions-X** (SN §7.2; CTX §22); (c) ordering uses `internalDate`, never the
API's array order; (d) every structurally included message carries a mechanical reason naming the
relation used; (e) evidence split across threads is returned as multiple sources, each with its own
map reference.

**Violation.** A structurally included message with reason `null`, a generic reason ("relevant"), or
a hearsay message returned as if authored by the named participant.

### C-03 — Semantic retrieval as an escalation path

**Requirement.** Semantic retrieval MUST exist in the shipped product as an adaptive escalation path
for conceptual/paraphrased queries that lexical search cannot resolve (SC §4). It MUST NOT run on
queries the cheap path answers confidently. A persistent mailbox-wide vector index is **optional**;
Gmail remains the source of truth (SC §11).

**Observable.** On a paraphrase case where the query and the evidence share no content words, the
lexical rung reports weak/zero evidence and the semantic rung executes and surfaces the evidence. On
exact-lookup and sender/date cases, the trace records zero embedding calls. Whatever candidate pool
the semantic rung embeds is bounded, and the bound is **reported in the response**: whenever a scored
retriever ran, the response carries a `pool{scope_rule, thread_count, message_count, why}` block, and
the trace additionally enumerates the pool **by ID** so a reviewer can check the bound against a real
set rather than against the server's account of one (I-1; RO addendum T-RO1; ARCH_REVIEW ADV-109).

**Violation.** Embedding calls recorded on an exact-token query; or a paraphrase case where the
lexical rung returned zero hits and no semantic escalation was attempted or reported as untried.

**Constrained by N-01/N-02.** The default semantic path is local and free (Appendix A.1).

### C-04 — Candidate ranking and reranking

**Requirement.** When ambiguity requires it, MailWeave MUST rank/rerank candidates before disclosure.
When ambiguity does not require it — an exact Message-ID or invoice-number query — it MUST NOT
(SC §8).

**Observable.** (a) Ranking activates only when a recorded ambiguity signal fires (hit-count band,
`asked_for.term_coverage` < 1, thread concentration, or scored-retriever margin — RT §5.1); (b) the ordering is
reproducible given the same inputs; (c) **no fabricated scores**: a result selected because Gmail `q`
matched it says exactly that, and any numeric score names its method and model (CTX §20).

**Violation.** A displayed relevance number with no named method; or reranking invoked on a query
whose trace shows an exact-signal match.

### C-05 — Adaptive escalation and stopping

**Requirement.** Retrieval MUST be a loop, not a one-shot classification (CTX §47): cheap
deterministic path first; stop on strong evidence; broaden on weak, zero, or ambiguous evidence;
escalate through structural, then semantic, then ranking, then context expansion (SC §3). Every rung
MUST have a budget cap enforced in code, and exhausting a cap MUST be reported in the response
(RT §5.2).

**Observable.** Traces show cost scaling with measured ambiguity: simple families execute one rung
and few API calls; hard families execute more rungs and recover. A response produced under an
exhausted budget says so and names what was not tried.

**Violation.** Silent truncation of the ladder; a uniform pipeline that runs every stage regardless of
query; or a cap hit that leaves no trace in the response.

### C-06 — Query-aware progressive disclosure

**Requirement.** The representation returned MUST be conditioned on the query (SC §6, CTX §46).
Fixed ±2 neighbours is a **benchmark baseline only**; the shipped policy MUST be query-aware —
reply-chain floor plus query-scored structural selection over participant, subject/snippet and
temporal signals under an explicit context budget — and MUST be measured against the fixed-window
baseline at *equal token budget* (SC §6; CD §9).

**Observable.** For the same thread, two different queries produce different included sets, each
inclusion carrying its own reason. Disclosure depth is expressed per message from the closed vocabulary
`stub` / `snippet` / `body_clean` / `body_full` / `raw`. Disclosure is **shallow by default** — one strong
evidence level plus a full-fetch escape hatch — because deeper hierarchies are the failure mode
controlled study 2607.17598 identified ("a second, deeper routing level never helps and sometimes
breaks accuracy"; VR §8.1). Any additional level MUST be justified by measurement.

**Violation.** Identical output for two materially different queries against the same thread; a
disclosure level that exists but has never been benchmarked against the level below it.

### C-07 — Explicit partiality

**Requirement.** Partial data MUST NOT masquerade as complete data (SC §7, CTX §26). The agent MUST
be able to distinguish: which messages matched; which are contextual; what has been expanded; what
remains a stub; whether the result is partial; how much more exists; and how to get it.

**Observable.** Enforced by the response-shape obligations R-01…R-09 of §5.2, checkable mechanically
on every response.

**Violation.** Any response containing fewer messages than the source thread holds, without a stated
total, a stated included set, and an executable affordance for the remainder.

### C-08 — Recoverable routing

**Requirement.** The router is an initial hypothesis. A wrong first route MUST NOT produce a false
"not found" (SC §3, CTX Decision 8). Escalation matters more than first-route accuracy.

**Observable.** There is **no bare empty response**. A no-evidence outcome is a structured retrieval
report: queries executed, constraints dropped and why, hit counts per rung, what was *not* tried, and
the affordances that would try it (RT §5.3). Relaxation is systematic — one constraint at a time,
enumerable and logged — not clever. Where zero hits are returned, the report names which single
dropped constraint restores results, when one does.

**Violation.** A response that asserts nonexistence, or returns an empty set with no report; or a
relaxation step that dropped a constraint without recording it.

### C-09 — Freshness behavior

**Requirement.** Freshness is part of the complete-product quality bar and is tested against real
delivered mail (SC §12). If direct Gmail API search is sufficiently fresh, MailWeave documents the
measurement. If it exhibits meaningful lag, MailWeave MUST implement a defensible mitigation —
`users.history.list`-based reconciliation or equivalent — before any freshness claim is made.

**Observable.** (a) Every map, body and any cached artifact carries the time it was fetched, so a
stale view cannot masquerade as current (CTX §45; CD §5.4); (b) the CG-FRESH protocol (EP §11) has been executed
and its lag distribution published before any freshness sentence exists in public material; (c) if a
cache or index is ever introduced, it carries `historyId` + last-sync stamps, a full-resync path for
the documented 404-on-expired-`historyId` case, and a purge command (RO F6; SN §4.2).

**Violation.** Any response served from cached state without a fetch/sync stamp; any public freshness
sentence with no experiment log entry behind it.

### C-10 — Observability and instrumentation

**Requirement.** Instrumentation is built in from the start (SC §15), and the trace schema MUST be
rich enough that a routing policy could later be learned from real traces — without training one now
(SC §9).

**Observable.** Every top-level query emits one joinable trace carrying at minimum: query *features*
(not raw text on the personal profile), initial and final route, rungs executed, constraints dropped,
fallback triggered and why, candidate counts, ranking depth, context expansions, budget caps hit,
Gmail call counts by method, model/embedding call counts, latency per rung, disclosed-token estimate,
and the sufficiency verdict (RT §6). Traces obey N-05.

**Violation.** A tool call with no corresponding trace; a headline metric sourced from a
server-self-reported field rather than harness measurement (EP §6.3).

### C-11 — Untrusted-content handling

**Requirement.** Email is attacker-authorable. Every string MailWeave derives from mail MUST reach
the agent marked as untrusted third-party data, and MUST NOT be able to impersonate MailWeave's own
voice or the protocol surface (CTX §42; SN §6.3).

**Observable.** (a) Mail-derived text appears only in dedicated leaf fields, fenced with a
per-response nonce so mail cannot close its own fence; (b) connector semantics — counts, roles,
reasons, affordances — are never interpolated with mail text; (c) tool names, descriptions and schemas
are compile-time constants; (d) derived/summary text (if any) is labeled derived, names its source
message IDs, and inherits untrusted status; (e) an injected message that legitimately matches a query
is still **retrieved and disclosed** — fenced, not dropped.

**Violation.** Mail text found in a connector-voiced field, an unfenced body, a tool description built
from mailbox data, or a "safety" filter that silently removes matching evidence.

---

## 4. The four invariants, as testable clauses

Restated from CTX §39 with the observable that proves a violation. These are release-blocking; a
violated invariant is a BLOCKER by definition (AGENT_LOOP §4).

### I-1 — Evidence Preservation

**Clause.** If any retrieval stage identifies a message as matching or supporting the query, no later
stage may remove it from the representation while still presenting the result as the match.

**Testable form.** Let `H` — the **hit set** — be:

1. every message ID returned by an **executed Gmail query**, including the queries a rung issues for
   its own bookkeeping (relaxation and broadening `messages.list` calls at L2/L3, and the
   participant `from:`/`to:` probes that build a semantic candidate pool — those are executed Gmail
   queries and their IDs are in `H`); **plus**
2. from any **scored retriever**, the candidates that pass the retriever's selection threshold — the
   **shortlist that enters the disclosure candidate set** — **not** every row that received a score.
   The shortlist size and the selection rule are a **declared, pre-registered parameter** reported in
   the retrieval report, never a free per-run implementer choice, so `|H|` cannot be shrunk to make
   this invariant pass (ARCH_REVIEW ADV-109).

The **scored pool itself is disclosed by its scoping rule and its size** under R-08's `pool` block —
`pool{scope_rule, thread_count, message_count, why}` — and enumerated by ID **in the trace**, not by
emitting a stub row per pool member. Enumerating the pool in the response would collide with the
disclosure budget and is not what preserves evidence; declaring it does.

Let `R` = the set of message IDs present in the response at any depth (a stub counts) plus the set
explicitly listed as `withheld`, each `withheld` record carrying `{id, thread_id, why, affordance}`
where `why` names the specific cap that withheld it and the affordance is executable.
**`H ⊆ R` must hold on every response.** A cap — per-rung fetch budget, map-thread cap, token
ceiling — may never silently drop a hit: it converts the hit into a `withheld` record. The response
also declares its **scan scope** (pages fetched, `maxResults` used, whether unfetched pages remain),
so `H` is a checkable set rather than an open one (ARCH_REVIEW ADV-001).

**Proof of violation (any one).** (a) `m ∈ H`, `m ∉ R`; (b) a response for a query whose
`rfc822msgid:` form returns *m*, in which *m* is absent; (c) evidence recall that varies with the
target's position in the thread beyond the pre-registered spread; (d) a terminal response asserting
nonexistence for a case whose evidence was in `H`.

### I-2 — Explicit Partiality

**Clause.** Any intentionally partial representation discloses that it is partial and preserves a
mechanism to reach the rest.

**Testable form.** For every thread represented: `stated_total` is present and equals the source's
reported message count; the included set is exactly the set present in the payload; if
`included < total`, a machine-actionable affordance is present and, when invoked, returns the named
content; if `included == total`, the response says complete and offers no phantom remainder. Nested
losses count: quote-stripping, body truncation, collapsed stub runs and scan-scope limits are each
declared in place with a path to the unabridged form (CD §5.4).

**Proof of violation (any one).** (a) a bare count with no call attached; (b) `stated_total` that
disagrees with the source; (c) an affordance that errors, returns different content, or is not
executable by an ordinary MCP client; (d) a constant `complete: false` that is never `true` even when
the whole thread is present; (e) stripped quoted text with no byte count and no full-body path.

### I-3 — Adaptive Cost

**Clause.** Expensive retrieval or reasoning paths are not required for queries a cheaper path
answers confidently.

**Testable form.** Per query family, cost (Gmail calls measured at the network level, latency,
embedding calls, model calls) is reported; simple families stay within the pre-registered ceiling
relative to a plain message-level-search baseline, while hard-family recall does not regress. Cost
must correlate with recorded ambiguity signals, not with a fixed pipeline.

**Proof of violation (any one).** (a) embedding or model calls on an exact-signal query; (b) identical
rung sequences across all families; (c) simple-family latency or call counts exceeding the ceiling;
(d) the *inverse* failure — cheap everywhere because escalation never fires, shown by hard-family
recovery rate below its bar.

### I-4 — Recoverability

**Clause.** A bad initial route must not force a false "not found"; the system can broaden or change
strategy.

**Testable form.** On adversarial mis-parse cases (wrong sender guess, wrong date window, wrong
operator), the ladder recovers within budget at the pre-registered rate; false-not-found rate on
answerable cases is **0**; and the paired hallucinated-found rate on unanswerable controls stays
within its bar, so recoverability cannot be bought by never admitting absence.

**Proof of violation (any one).** (a) a bare empty result; (b) a case where evidence exists, an
untried rung would have found it, and the response neither tried nor reported it as untried; (c)
false-not-found > 0 on the answerable set; (d) hallucinated support invented on the unanswerable set.

---

## 5. Behavioral contract of the MCP surface

**Naming is settled elsewhere.** Tool names, argument names and JSON field names are fixed by
`ARCHITECTURE_DECISION.md` D.1 (`mailweave_search`, `mailweave_thread_map`, `mailweave_get_messages`,
`mailweave_get_attachment`). The provisional forms written `«like_this»` below are retained only to
show which obligation each name carries; where they differ from D.1, D.1 is the name and this table is
the obligation. The **obligations** are not provisional.

### 5.1 What an agent can ask

MailWeave MUST expose, at minimum, these capabilities as agent-callable operations:

| Obligation | Provisional name | Must accept | Must return |
|---|---|---|---|
| Find evidence for a query | `«search_mail»` | free-text query; optional structured constraints; optional budget/limit | evidence at body depth + partiality metadata + affordances (§5.2) |
| See a thread's complete shape | `«thread_map»` (`mailweave_thread_map`) | thread id or `map_id` | every message of the thread as at least a stub row — **or inside a declared collapsed run carrying an expansion affordance (R-06)** — with position, sender, date, reply parent, and hit flags |
| Open specific content | `«get_messages»` | message ids or map handle + positions; a depth/`view` selector | the requested messages at the requested depth, with declared stripping |
| Inspect an attachment | `«get_attachment»` | message id + part id; mode | attachment metadata by default; extraction only if built, sandboxed, opt-in (SN §7.3) |

An easy query MUST be completable in a single call: `«search_mail»` returns evidence at readable
depth, not a handle the agent has to redeem (CD §7 T2 recommendation). Nothing in the surface may
require the agent to guess a follow-up call that the response did not name.

### 5.2 What an agent always gets back — response-shape obligations

These hold for **every** response that carries mail content. They are the mechanical form of C-06,
C-07, C-11 and invariants I-1/I-2.

- **R-01 Hit identity.** Every message present carries a stable message identifier that joins to
  Gmail's own id, plus its thread id and its position within that thread.
- **R-02 Role.** Every message carries a role from a closed set — matched / context / parent / child /
  requested / stub / derived.
- **R-03 Reason.** Every message carries a *mechanical* reason for its presence naming the mechanism
  ("gmail q matched", "rfc822msgid", "reply parent of m37", "window ±1", "snippet contains 'october'",
  "semantic cosine 0.81, model X"). No decorative rationales, no unexplained numbers (CTX §20).
- **R-04 Depth.** Every message declares its disclosure depth from the closed set
  `stub` / `snippet` / `body_clean` / `body_full` / `raw`, and every reduction
  applied to its content (quote stripping, HTML→text, truncation) is declared in place with a size
  count and a path to the unabridged form.
- **R-05 Totals vs included.** Every thread represented declares its total message count as reported
  by the source — the wire field is **`stated_total`** — the count included in this response, and the
  count included as stubs only. (`claimed_total` is the evaluation harness's normalised name for the
  same quantity, EP §6.2; it is not a second field.)
- **R-06 What remains unexpanded.** Withheld content is represented as *visible stubs*, not as a
  number alone, wherever the map is present. A bare "97 omitted" is not compliant on its own.
- **R-07 Affordance to get more.** Every partiality statement is adjacent to a concrete, executable
  call — tool name plus arguments — that retrieves what it describes. The affordance MUST work
  through ordinary tool calls; MCP resources MAY duplicate it and MUST NOT be the only path, because
  resource exposure to the model is host-dependent (CD §5, §8).
- **R-08 Completeness and freshness stamps.** Each map/body states when it was fetched (`fetched_at`)
  and whether the set is complete *as reported by the source at that time*. MailWeave MUST NOT assert
  absolute completeness it cannot verify (see §9 T-3): `stated_total` means "what the source reported
  at `fetched_at`", never a claim of absolute completeness. Where a scored retriever ran, the same
  block carries the candidate-pool declaration `pool{scope_rule, thread_count, message_count, why}`
  (I-1, C-03), and where paging stopped short it carries the **scan scope** (pages fetched,
  `maxResults` used, whether unfetched pages remain).
- **R-09 Untrusted-content envelope.** All mail-derived text is fenced and labeled untrusted, with
  provenance fields (`source`, `trust`, and for derived text its source message ids). The static tool
  description — never per-result text — states that fenced content is third-party data and must not
  be followed as instructions (SN §6.3).
- **R-10 Self-truncation.** If a response would exceed MailWeave's own size ceiling, MailWeave
  truncates it *explicitly*, with markers and affordances, rather than letting the host truncate it
  silently (CD §6.3).

### 5.3 What must never be absent

A response that carries mail content and omits any of: hit identity (R-01), role (R-02), reason
(R-03), totals-vs-included (R-05), an executable affordance while partial (R-07), or the untrusted
envelope (R-09) is **non-conforming** regardless of retrieval quality. These six are the minimum
partiality contract.

### 5.4 Protocol posture

- **N-MCP-1.** MailWeave targets MCP revision **2026-07-28**. It MUST NOT build on **Sampling**,
  which that revision deprecates ("new implementations SHOULD NOT adopt it"), and which was in any
  case unsupported in the Claude-family clients MailWeave targets (RT §4.1b; VR §7).
- **N-MCP-2.** The protocol is stateless. Cross-call state (map references and expansion referents)
  MUST be carried by an **explicit server-minted handle — `map_id` — passed as an ordinary tool
  argument** (SC §14; VR §7). No hidden protocol sessions, and no "cursor": no design in this set
  produces one, so the word is retired to keep one name per concept.
- **N-MCP-3.** A handle that has expired or become invalid MUST fail loudly with a re-derivation path.
  It MUST NOT silently resolve to different content than it named.
- **N-MCP-4.** Tool annotations MUST be truthful (`readOnlyHint: true` while §7 B-01 holds).
  Structured output and its serialized text form MUST agree.
- **N-MCP-5.** Tool-call results have no protocol-level pagination in this revision; progressive
  disclosure is therefore an application-layer obligation carried in tool arguments and result
  fields (VR §7.4).

---

## 6. Non-functional requirements

- **N-01 Zero paid-API dependency for core function.** Every core capability of §3 MUST work with no
  paid API key configured. Hosted embedding/reranking providers MAY exist behind a
  provider-agnostic interface as explicit opt-ins for benchmarking or users who choose them, and MUST
  NEVER be required (Appendix A.1). Any internal model call must either run locally or be an opt-in
  enhancement with a deterministic or local fallback; core retrieval quality may not depend on a paid
  API (Appendix A.1).
- **N-02 Local semantic default.** The shipped default semantic path is local: mailbox content does
  not leave the machine for retrieval purposes unless the user explicitly opts into a remote provider,
  and that choice is documented at the point of configuration (Appendix A.1; SN §4.2).
- **N-03 Gmail is the source of truth.** No response may be served solely from local state without a
  staleness stamp, and no local index may be introduced unless a measured failure justifies it, at
  which point C-09's freshness obligations attach (SC §11; CTX §44–§45).
- **N-04 Minimum scope.** The server holds exactly `https://www.googleapis.com/auth/gmail.readonly`
  and no other Gmail scope. `gmail.metadata` is not viable: it cannot use `q` and cannot read bodies
  (SN §1.2). Seeding/teardown scopes live only in the evaluation harness, in a separate OAuth client,
  pinned to a separate dedicated Gmail account (Appendix A.2; SN §0).
- **N-05 Trace and privacy constraints (Appendix A.3, rubric-enforceable).** IDs, metadata, routing
  decisions, timings, scores and metrics are persisted by default. **No full personal email bodies in
  traces or logs.** Short, aggressively redacted snippets may be persisted only when required to
  diagnose a specific real-mailbox failure. Full bodies remain memory-only during normal execution.
  Raw user query text is itself personal data on the personal profile and is stored as derived
  features or a salted hash, not verbatim (SN §4.3). The redaction profile is selected from the
  *authenticated account*, not from a config flag, and error paths are covered.
- **N-06 No telemetry.** MailWeave reports to nobody: no analytics, no crash reporting, no update
  checks, no query-time model download, and zero mailbox bytes to any non-Google host. The only
  **runtime** network peers are exactly two hosts — `gmail.googleapis.com` and `oauth2.googleapis.com`
  (token refresh only) — plus, under N-01's explicit opt-in, a user-configured provider. Model weights
  are fetched **at setup time only**, from a declared model-host, and runtime model loading is forced
  offline (`local_files_only` / `HF_HUB_OFFLINE`) against a checksum-pinned local path, so the
  two-host runtime property survives library loading rather than being assumed from it
  (ARCH_REVIEW ADV-210; SN addendum §4/T-SN3).
- **N-07 Local-first operation.** Default transport is stdio; no listening socket in the default
  configuration (SN §10 P1).
- **N-08 Reproducible setup.** A clean machine can install, authorize and run MailWeave from
  documented steps, with pinned dependencies, and the offline test suite passes without Gmail
  credentials.

---

## 7. Capability boundaries for this release

- **B-01 Read-only, intentionally and for now.** The first MailWeave retrieval release is
  intentionally read-only and uses the minimum viable Gmail scope (SC §10). No send, draft, reply,
  label, modify, trash or delete tool exists, and no such code path is reachable from any MCP tool.
  This is a scope choice with a security dividend — it removes the consequential-action leg of the
  lethal trifecta inside the connector (SN §6.1) — **not** a statement that MailWeave is permanently
  incapable of Gmail actions. Sending, drafting and modifying mail are outside the current
  retrieval-focused product boundary (SC §10). If write capability is ever added it requires a
  separate consent ceremony, separate token, draft-first defaults and per-call confirmation
  (SN §8).
- **B-02 Gmail only.** IMAP, Outlook/Graph, and other mail sources are outside this release. Gmail is
  the testbed for a general representation problem (CTX §30); the abstraction boundary should not
  foreclose other backends, but no other backend is contracted here.
- **B-03 Single mailbox per server instance.** Multi-account fan-out is out of scope.
- **B-04 Attachments: metadata by default.** The carrying message and the attachment's metadata are
  retrieved and signalled. Content extraction, if built, is sandboxed, size- and depth-capped, and
  opt-in (SN §7.3).
- **B-05 No trained router.** Routing is deterministic/heuristic with recoverable escalation; traces
  are collected so a learned policy is possible later. Training one now is out of scope (SC §9).
- **B-06 No persistent mail-content store by default.** Stateless with respect to mail content unless
  a measured failure justifies an index, subject to N-03 and C-09.

**Deferrals are scope statements, not quality excuses.** Each deferred item below names what would
bring it into scope. Nothing here may be cited in a review to excuse a defect in a shipped capability.

| Deferred | Why deferred | What brings it in |
|---|---|---|
| Write/draft/send tools | Outside the retrieval product boundary for this release (SC §10) | An explicit owner decision plus SN §8's gating sequence |
| Persistent semantic index | Optional by direction; creates the stale-index paradox it exists to prevent (SC §11; CTX §45) | A measured recall/latency win over on-demand semantic retrieval, with the C-09 freshness obligations budgeted into the same loop |
| Persistent participant graph | Structural capability is required; a persistent graph is not (SC §5) | Measured failure of live thread-map computation on participant/multi-thread families |
| Learned routing policy | Not enough real traces or labels yet (SC §9) | A trace corpus large enough to train and hold out honestly |
| Derived summaries / decision timelines | Summaries can fabricate; a wrong summary reads as evidence (CD §4.5) | A summary-faithfulness evaluation, plus C-11's derived-content labeling |
| Attachment content extraction | Sandboxing workstream not justified yet (SN §7.3) | A benchmark family that fails on metadata-only attachment handling |
| Push notification freshness (`users.watch` + Pub/Sub) | Introduces a hosted external dependency, colliding with N-01/N-02; polling `history.list` costs ~2 quota units (RO F6, F7) | Measured lag that polling cannot close, and an opt-in design that keeps core function key-free |
| Elicitation-based disambiguation | Client support unverified (RT §4.1d) | A verified client-support check |

---

## 8. Honest-claims contract

MailWeave may state publicly only what it has measured. This section is enforced at the release gate
(AGENT_LOOP §10.7).

- **H-01 Claim→measurement map.** Every capability claim in the README, post, or resume line maps to
  a specific experiment log entry containing the number. A claim with no entry is removed, not
  softened.
- **H-02 Unbundled.** Public material states which problem is solved — representation omission,
  freshness, semantic retrieval — separately, and never lets one claim borrow another's evidence
  (CTX §58.7).
- **H-03 Minimum proof before "MailWeave fixes the Gmail MCP problem."** All of CTX §58: a faithful
  reproduction or reconstruction of the reported failure; buried-evidence tests; evidence-preservation
  results; comparison against full-thread and fixed-K baselines; latency and context-size
  measurements; a real MCP client successfully using MailWeave; and an explicit statement of which
  problem is solved.
- **H-04 No freshness sentence before the freshness protocol.** See C-09.
- **H-05 Baseline honesty.** Public evidence (issue reports, vendor tool descriptions) and our own
  measurements are labeled separately and never blended. If a reconstructed baseline stands in for the
  hosted server, it is labeled reconstructed everywhere it appears (EP §8.1).
- **H-06 Comparison completeness.** Beating the broken preview is necessary but not sufficient.
  Claims of value must also report the comparison against a strong agent given honest primitive tools,
  because controlled evidence says progressive disclosure can add ~nothing when the harness already
  navigates well (VR §8.1; EP §8.5, §8.7).
- **H-07 Negative results are published.** A rejected capability (e.g. "semantic index rejected:
  +x points recall, +y % p95" — placeholders, because no such measurement exists yet and a quotable
  number here would itself breach H-01) gets the same experiment log treatment as a win and stays in
  the index permanently (EP §9 G7).
- **H-08 Limitations section.** Public material names what was not measured, what is untested, and
  the domain-transfer limits of the prior art it cites.

---

## 9. Tensions handed to architecture

These are unresolved conflicts between owner direction and verified research. They are recorded here
because an implementer must not resolve them silently (AGENT_LOOP §8).

- **T-1 — Disclosure depth.** SC §7 requires a rich set of disclosure distinctions and CTX §10.2
  sketches a Level 0→5 ladder; arXiv 2607.17598 found that a second, deeper routing level "never
  helps and sometimes breaks accuracy," and that progressive disclosure's gain is near zero when a
  strong agent harness already retrieves well (VR §8.1). **Resolution required:** the shipped default
  is one strong disclosure level plus a full-fetch escape hatch (C-06), and disclosure depth is an
  explicitly benchmarked variable rather than an assumed good. Architecture must state the depth it
  ships and the measurement that justifies it.
- **T-2 — Structural retrieval at multi-thread scale.** SC §5 says structural signals can be computed
  live from thread maps without persistent storage. The primitives price that: `threads.get` costs 40
  quota units versus 20 for a single `messages.get`, returns whole threads with no in-thread
  pagination, and there is no thread operator in `q` (RO F3, F4, F7). Multi-thread structural
  retrieval therefore costs one whole-thread fetch per candidate thread. Architecture must state the
  cost model and the cap, or justify a metadata-only cache under N-03.
- **T-3 — What "complete" can honestly mean.** R-05/R-08 require a truthful total, but Gmail offers no
  independent oracle for thread completeness — no thread operator to cross-check with, no count field
  — and `get_thread` truncation on long threads has itself been reported (VR §6.1, §11.2). MailWeave
  can therefore only assert "complete as reported by the source at time T." Architecture must define
  the completeness semantics and a G0 validation of the fallback itself.
- **T-4 — Freshness mitigation vs zero-dependency.** SC §12 requires a mitigation if lag is real;
  the push primitive (`users.watch`) needs Cloud Pub/Sub, an external hosted dependency that collides
  with N-01/N-02, while `history.list` polling is cheap and readonly-compatible (RO F6, F7).
  Architecture must resolve in favour of a key-free core path or record why not.
- **T-5 — Real-mailbox debuggability vs A.3.** SC §13 makes the real mailbox the primary development
  environment; A.3 forbids full personal bodies in traces. Failure forensics on personal-mailbox
  failures must therefore run through redacted snippets or be reproduced on the seed account.
  Architecture must specify which, and the mechanism that enforces it (SN §4.3, open question 3).


---

## 10. For owner decision — reconciled after Round 1

*(Rewritten by the Round-1 **reconciliation** pass, which reconciled this list with
`ARCHITECTURE_DECISION.md` §I's O-1…O-8. Items 1, 2, 3, 5 and 6 are settled; the residue is
consolidated in **`docs/OWNER_DECISIONS.md`**, which is the only list to take to the owner. Numbering
stays shared with `RELEASE_RUBRIC.md` and `EVALUATION_PLAN.md` §16.)*

**Settled — no longer open:**

1. ~~Completeness semantics (CONS-004).~~ **RESOLVED.** `stated_total` means "what the source reported
   at `fetched_at`" (R-08, T-3); manifest equality is an *instrument* measurement carrying a
   **gate-binding** discrepancy bound under rubric GMAIL-03, registered from PF-1 at G0. Both halves are
   in force in the rubric, the plan and `ARCHITECTURE_DECISION.md` §H-2. The residue is PF-1's number.
2. ~~DISC-02 (CONS-001).~~ **RESOLVED.** Rubric DISC-02 now publishes the comparison either way and
   states that a loss is a reported finding and a tuning input, never a scope reduction; C-06's "the
   shipped policy MUST be query-aware" stands and fixed ±2 may never ship.
3. ~~The hit set `H` (CONS-003 as amended by ADV-109).~~ **RESOLVED.** I-1 and rubric EV-01 carry one
   clause; `ARCHITECTURE_DECISION.md` A.7a now quotes it verbatim and names its instantiation
   (`rule: "top-k by stage-A cosine"`, `k = max_rerank_pairs = 25`, reported as
   `retrieval_report.shortlist{rule, k, size}`), so the declared, pre-registered parameter this clause
   requires is a published constant rather than an implementer's dial. Pool-construction probes remain
   inside `H` and are handled by `withheld` (A.7a), and the pool is enumerated by ID in the trace.
   **Related and also resolved:** the reading `ARCHITECTURE_DECISION.md` §H-10 asked to confirm — that
   `R-01`/`PART-01` bind on what is *represented*, with `withheld` records as the disposition for the
   rest — is answered by this document's own repaired text (I-1's definition of `R`; I-2's "for every
   thread represented") and by rubric PART-01's "thread-bearing responses".
5. ~~Disclosure-level scope (ADV-208).~~ **RESOLVED in the measure-don't-remove direction.** `raw` is no
   longer independently requestable; `snippet` stays and the depth measurement is extended to the
   content-depth vocabulary (EP §7.5.1; ARCH §H-3). C-06's "any additional level MUST be justified by
   measurement" is satisfied by measurement rather than by deletion — deletion would be the scope
   reduction SC §1/§6 forbids.
6. ~~R-DOC (CONS-019).~~ **RESOLVED.** `AGENT_LOOP.md` §2.3 now carries **R-DOC** as an eighth reviewer
   domain, so H-01…H-08's rubric criteria (DOC-01…DOC-06) have an ordinary-round owner.

**Still open — consolidated in `docs/OWNER_DECISIONS.md`:**

4. **Forensics access (CONS-005).** May an implementer agent run `mailweave inspect` against the
   personal mailbox, or the human owner only? N-05 and A.3 settle the *mechanism*; this is the remaining
   access question. → **OD-4 — DECIDED 2026-08-30**: metadata / ID / timing / structure-only diagnostics
   are autonomous; persisting or surfacing actual personal-mail text requires the owner's per-incident
   approval; transient in-memory retrieval during query execution is unaffected.

Also open, though neither was raised in this document: **OD-1** the Freshness Service Level (the product
statement C-09's honesty rests on — `EVALUATION_PLAN.md` §11.2.2 says the plan may not set it),
**OD-2** ROUTE-04's 100 % empty-diagnosis bar (C-08/I-4's promise for heavily-constrained queries), and
**OD-3** the owner's acceptance that C-06's reply-chain floor guarantees **presence** at a declared
depth rather than full text at the token ceiling (ARCH §H-9; decided in measurement by F17).

---

## REPAIR LOG (Round 1)

Against `docs/reviews/CONSISTENCY_AUDIT_1.md` and the contract-implicating findings of
`docs/reviews/ARCH_REVIEW_1.md`.

### BLOCKERs

| Finding | What changed | Where |
|---|---|---|
| **CONS-003** I-1's `H` made the semantic rung unimplementable | `H` restated: (1) every ID returned by an **executed Gmail query** — explicitly including L2/L3 relaxation/broadening calls and the participant `from:`/`to:` probes that build a semantic pool, which are `messages.list` calls and were the half ARCH §H-5 left unaddressed — **plus** (2) from a scored retriever, only the **threshold-passing shortlist**, with the shortlist size a **declared, pre-registered parameter** so `|H|` is not an implementer dial (ADV-109). The scored pool is disclosed by `pool{scope_rule, thread_count, message_count, why}` and enumerated **by ID in the trace**, not by 300 stub rows. `R` now spells out the `withheld` record shape, and the response declares its **scan scope**, so a cap converts a hit into a withheld record instead of dropping it (ADV-001) | §4 I-1; §3 C-03; §5.2 R-08 |
| **CONS-002** N-06 unsatisfiable | Rewritten to the **two-host runtime allowlist** (`gmail.googleapis.com` + `oauth2.googleapis.com`, refresh only) with model hosts **setup-time only** and runtime loading forced offline from a checksum-pinned path (ADV-210). Every substantive prohibition is retained and none weakened | §6 N-06 |

### HIGHs

| Finding | What changed | Where |
|---|---|---|
| **CONS-009** stale Revision-1 EP citations | All four re-pointed (§3.3→§6.3, §4.1→§8.1, §4.5→§8.5/§8.7, §5 G7→§9 G7), and "EP citations are to Revision 2" added to §0. "Loop 6 protocol" → the CG-FRESH protocol (EP §11) in §2 and C-09; "Loop 0 validation" → G0 validation in T-3 | §0, §2, C-09, H-05, H-06, H-07, T-3 |

### MEDIUM / LOW

| Finding | What changed | Where |
|---|---|---|
| **CONS-026** invented numbers inside a claim-discipline clause | H-07's `"semantic index rejected: +2.1 recall, +80% p95"` → `"+x points recall, +y % p95"`, with a note that a quotable number there would itself breach H-01 | §8 H-07 |
| **CONS-030** §5.1's thread_map row unsatisfiable on long threads | Row now reads "every message … as at least a stub row, **or inside a declared collapsed run carrying an expansion affordance (R-06)**", matching rubric PART-05 and the architecture's budgets — a 500-message thread at ~40 tokens/stub is ~20,000 tokens against a 9,000-token ceiling | §5.1 |
| **CONS-023 / CONS-033** terminology drift | One canonical name per concept, listed in §0 and applied: `stated_total` in the wire schema (`claimed_total` is only the harness's normalised name); depth tokens `stub / snippet / body_clean / body_full / raw` (R-04, C-06); server-minted **`map_id`** with "cursor" retired (N-MCP-2); `asked_for.term_coverage` with `query_term_coverage` retired (C-04); tool names fixed by ARCH D.1, with §5.1's provisional forms kept only to carry the obligation; Tier 1/2/3 substrates, M1/M2 modes, G0 + `CG-*` gates, `PF-n` preflights, and ARCH A.7's rung numbering | §0, §5.1, R-04, R-05, R-08, N-MCP-2, C-04, C-06 |

### Orphan clauses now covered by a criterion

R-02 and R-03 → **PART-07**; C-03's pool declaration → **SEM-06** (and EV-01); N-07 → **SEC-07**;
B-04 → **SEC-02**; B-05 → **SEC-08**; H-03 → **DOC-06**; H-07 → **DOC-01**; C-11(d) remains covered
only vacuously while derived summaries are deferred (§7) — a LOW the audit itself scoped that way, and
it becomes live the moment a summary ships.

### Not closed, and why

- **CONS-025, CONS-029, CONS-031(a), CONS-036, CONS-037** — `ARCHITECTURE_DECISION.md` edits, owned by
  another agent this round. Escalated. **All five have since landed there** (CONS-025 → D.4a's named,
  licensed content-processing components; CONS-031(a) → E.2's LR row with its removal gate and the
  `H5-LRoff` arm; CONS-029 → B.6; CONS-036 → A.7; CONS-037 → §C T-RC2), verified by the Round-1
  reconciliation pass against that document rather than taken on report.
- **CONS-027** — the `CONTEXT_DISCLOSURE_OPTIONS.md` half is outside this repair's file ownership;
  N-MCP-1's 2026-07-28 target was already correct and needed no change.
- **Items 1–6 of §10** — owner rulings. **Reconciled after Round 1:** items 1, 2, 3, 5 and 6 are
  settled and recorded as such in §10; item 4 is consolidated, with three further items, in
  `docs/OWNER_DECISIONS.md`.

---

## REPAIR LOG — Round 1 — reconciliation

*Applied by the reconciliation pass. **No clause of this contract changed.** The capability inventory,
the four invariants, the response-shape obligations, the non-functional requirements and the
honest-claims contract are byte-identical to the Round-1 repair; what changed is §10, which was
presenting settled items as open.*

| # | What changed | Where |
|---|---|---|
| **C-1** | **§10 rewritten.** Items 1, 2, 3, 5 and 6 recorded as **RESOLVED** with the location of each settlement, so no reader is sent to the owner for a question the documents already answer. Item 4 (forensics access) remains open as **OD-4**. Three further owner items are named because they bear on contract clauses even though this document never raised them: **OD-1** the Freshness Service Level (C-09), **OD-2** ROUTE-04's bar (C-08/I-4), **OD-3** the acceptance that C-06's reply-chain floor guarantees presence at a declared depth rather than full text (ARCH §H-9) | §10 |
| **C-2** | **ARCH §H-10's reading recorded as resolved** inside §10 item 3: this document's own repaired text answers it — I-1 defines `R` as IDs present at any depth **plus** IDs listed as `withheld`, and I-2 binds "for every thread **represented**" — so a `withheld` record is the conformant disposition and `max_hit_threads` need not be unbounded. No clause was changed to reach that reading; it was already there | §10 item 3 |
| **C-3** | **Round-1 "Not closed" bullet updated**: the five `ARCHITECTURE_DECISION.md` items escalated from here (CONS-025, CONS-029, CONS-031(a), CONS-036, CONS-037) have all landed in that document, each verified against it | REPAIR LOG (Round 1) |

**Checked and deliberately not changed.** I-1's `H`, N-06's two-host allowlist and §5.1's collapsed-run
allowance are the canonical wording the architecture has now copied verbatim; editing them here would
have re-opened the divergence this pass exists to close.
