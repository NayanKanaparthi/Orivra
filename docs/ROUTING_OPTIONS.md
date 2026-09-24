# ROUTING_OPTIONS.md — Router / Adaptive-Policy Design Space

**Agent C deliverable — MailWeave routing & adaptive-policy research**
**Date:** 2026-08-30
**Inputs:** `MAILWEAVE_CONTEXT.md` (esp. §§12–15, 43, 46–47, invariants §39, Decision 9), Google Gmail docs, MCP specification site, published agentic-retrieval work. All external claims below carry a URL; anything unverified is explicitly marked **[speculation]** or listed in "What I could not verify."

**Binding invariants this document designs against** (from `MAILWEAVE_CONTEXT.md` §39, §12):

- **Recoverability** — a bad initial route must never force a false "not found."
- **Adaptive Cost** — expensive paths must never be mandatory for queries a cheap path answers confidently.
- **Partiality** — withheld context stays visible.
- **No trained router before real traces exist** (Decision 9).

---

## 0. What "routing" actually decides in MailWeave

Three distinct decisions get conflated under "router." Keeping them separate changes the design:

| Decision | Question | Frequency |
|---|---|---|
| **R1 — initial strategy** | Which retrieval method/filters to try first? | once per query |
| **R2 — escalation** | Result came back; is it sufficient, or what next? | every round |
| **R3 — stopping** | When do we stop spending and report? | every round |

R1 is the classic "router." R2/R3 are the *adaptive policy* — and per §47 ("adaptive retrieval is a loop, not just a classification") and §14 ("routing is probabilistic; retrieval must be recoverable"), **R2/R3 matter more than R1**. A mediocre R1 with strong R2/R3 still satisfies the invariants; a brilliant R1 with no R2/R3 is the single-point-of-failure architecture §13 forbids. Published work agrees: FrugalGPT-style cascades get most of their win from result-conditioned escalation, not from first-choice accuracy ([arXiv:2305.05176](https://arxiv.org/abs/2305.05176)); CRAG adds a lightweight retrieval evaluator whose verdict (correct / incorrect / ambiguous) triggers corrective fallback actions ([arXiv:2401.15884](https://arxiv.org/abs/2401.15884)); Adaptive-RAG routes by query complexity between no-retrieval / single-step / iterative strategies — and, notably for Decision 9, trains its small router classifier *from automatically collected outcome labels*, i.e., from exactly the traces MailWeave does not have yet ([arXiv:2403.14403](https://arxiv.org/abs/2403.14403), NAACL 2024).

---

## 1. Tier-1: deterministic query parsing → Gmail `q` operators

### 1.1 Verified operator inventory

Verified against Google's operator reference ([support.google.com/mail/answer/7190](https://support.google.com/mail/answer/7190), checked 2026-08-30) and the Gmail API `q` parameter docs ([users.messages.list reference](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list), [filtering guide](https://developers.google.com/workspace/gmail/api/guides/filtering)). The API reference states verbatim that `q` "Supports the same query format as the Gmail search box," and the filtering guide qualifies this to "most of the same advanced search syntax." Signals a deterministic parser can map with **no model call**:

| Query signal (user-language cue) | Gmail operator | Notes |
|---|---|---|
| Named/quoted sender ("from Sarah", an email address) | `from:` | Address is exact; a bare name matches display names |
| Recipient ("I sent to…", "email to billing@") | `to:`, `cc:`, `bcc:` | |
| Both directions with a person ("emails with Sarah") | `from:X OR to:X` | Compose with `{}`/`OR` |
| Subject cue ("subject line says…") | `subject:` | `subject:(a b)` groups terms |
| Quoted string / exact wording | `"exact phrase"` | Exact-phrase search |
| Exact word (no stemming/synonyms) | `+word` | Documented exact-match operator |
| Absolute dates ("in March", "on Aug 4") | `after:` / `before:` (also `older:`/`newer:`) | **Caveat:** dates are interpreted as midnight **PST**; the filtering guide recommends epoch-seconds values in `after:`/`before:` for timezone accuracy |
| Relative recency ("last week", "past 2 days") | `newer_than:Nd/Nm/Ny`, `older_than:` | d/m/y units only |
| Attachment cues ("the PDF", "spreadsheet she sent") | `has:attachment`, `filename:pdf`, `filename:budget.xlsx` | `filename:` matches name or type |
| Drive/Docs/YouTube content | `has:drive`, `has:document`, `has:spreadsheet`, `has:youtube` | Under the `has:` family |
| RFC Message-ID (agent- or system-supplied) | `rfc822msgid:<id>` | The strongest exact primitive — the #296 repro used it |
| Label / category ("in my Receipts label", "Promotions") | `label:`, `category:` | API also has a separate `labelIds[]` param |
| Location/state ("in spam?", "archived", "unread", "starred") | `in:anywhere`, `in:archive`, `in:snoozed`, `is:unread/read/starred/important/muted` | `in:anywhere` includes Spam/Trash; API also has `includeSpamTrash` |
| Mailing list | `list:` | |
| Delivered-to alias | `deliveredto:` | |
| Size cues ("huge attachment") | `size:`, `larger:10M`, `smaller:` | |
| Proximity ("X near Y") | `X AROUND 10 Y` | Rarely user-articulated; useful for server-generated relaxations |
| Custom header | `header:Name:value` | Niche |
| Negation ("not from Bob", "except invoices") | `-term`, `-from:bob` | |
| Boolean structure | `OR` / `{ }`, `AND`, `( )` | Space = implicit AND |

**API-side facts that constrain Tier-1** (all verified on the pages above):

1. `messages.list(q=…)` returns only `{id, threadId}` pairs plus `nextPageToken` and an **approximate** `resultSizeEstimate`; bodies come from separate `messages.get` calls. `maxResults` defaults to 100, caps at 500.
2. `q` **cannot be used with the `gmail.metadata` OAuth scope** (stated verbatim in the reference). Scope choice (Agent F's domain) directly gates whether Tier-1 exists at all.
3. API search is **message-scoped, not thread-wide**: the filtering guide notes the API does not do the UI's thread-wide matching or alias expansion. For MailWeave this is a *feature* — the hit is a message ID, which is exactly the evidence-preservation primitive the hosted `search_threads` abstraction destroyed (§3.1) — but it means "the UI found it, the API didn't" edge cases exist where a term matches across different messages of one thread.
4. `threads.list` also accepts `q` for thread-granularity listing ([reference](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.threads/list)) — useful when the query is genuinely about conversations, though I verified the `q` wording on `messages.list` directly and only spot-checked `threads.list`.

### 1.2 What Tier-1 parsing is and is not

Tier-1 is **signal extraction, not full understanding**. A deterministic parser (regex + date parser + email-address/name detection + quoted-phrase detection + a small keyword→operator table) can confidently handle:

- explicit addresses, quoted phrases, message-IDs, attachment/size/label/state keywords, absolute and relative dates;
- name→address resolution *when backed by a contacts/frequent-correspondents lookup* (a cheap `messages.list(q="from:sarah")` probe is itself a resolver).

It should **refuse to guess** on: paraphrase/concept queries ("when did we postpone launch?"), decision/temporal-reasoning queries, multi-thread topical queries, pronoun references. The correct Tier-1 output is a typed result:

```text
ParsedQuery {
  operators: [...],            # what mapped cleanly
  residual_text: "...",        # tokens that did not map (become plain q terms)
  confidence: exact | filtered | weak | non-lexical,
  ambiguities: [...]           # e.g. "sarah" -> 3 known addresses
}
```

`exact` (msgid, invoice number, quoted phrase + sender) → run and expect 1–few hits. `filtered` (sender/date/attachment) → run and expect a scannable set. `weak`/`non-lexical` → run the residual terms anyway (cheap), but pre-arm escalation. This graded output is what makes the parser honest instead of a silent misrouter.

**Failure modes to design around** [known behavior, partly folklore — flagged]: Gmail's plain-term matching applies stemming/partial matching inconsistently and does not do synonym expansion; `resultSizeEstimate` is documented as an estimate and is widely reported to be unreliable for counting — never use it as a sufficiency signal on its own **[speculation beyond "approximate," which is documented]**.

---

## 2. Tier-2: lightweight classification when parsing is inconclusive

Only reached when Tier-1 reports `weak`/`non-lexical` — by construction a minority of traffic if Tier-1 is decent. Options:

| Option | Marginal cost | Latency | Quality | SPOF risk | Verdict for Loop 3 |
|---|---|---|---|---|---|
| **A. Rule-based heuristics** (keyword cue tables: "when/finally/decided" → temporal+decision; "about/regarding X" → topical; interrogatives; entity counts) | ~zero | <1 ms | Decent on head patterns, brittle on tail | None — misclassification just picks a suboptimal *first* path; ladder recovers | **Build.** ~50 lines of code, fully loggable |
| **B. Small local model** (fastText / tiny transformer classifier) | zero per-query, real training cost | ~1–50 ms | Only as good as its training data | Low (same recovery argument) | **Defer — blocked by Decision 9.** No traces → no labels. This is precisely Adaptive-RAG's recipe (small LM trained on auto-collected outcome labels, [arXiv:2403.14403](https://arxiv.org/abs/2403.14403)); revisit after instrumentation (§6) produces data |
| **C. LLM API call for classification** | $ per query | ~0.3–2 s | Best zero-shot | Adds an availability + key dependency; must degrade to A on failure | **Do not build into the default path.** Violates Adaptive Cost if mandatory; redundant in the hybrid design (§3) because the *calling* model already classified the query when it chose tool + arguments |
| **D. No Tier-2 at all** — treat "parsing inconclusive" itself as the routing signal: run residual-term lexical search, and surface classification to the caller | zero | zero | Delegates to the strongest available model (the client LLM) | None server-side | **Default posture.** A+D together: heuristics pick the first path; the caller drives anything smarter |

**How each avoids being a single point of failure:** the same way in every case — classification output is only allowed to choose the *first* rung of a ladder whose later rungs do not depend on the classification being right (§13's "initial hypothesis, not irreversible decision"). Concretely: no branch of the classifier may terminate the query; every branch falls through to the escalation policy in §4. This is the property to unit-test, not classifier accuracy.

---

## 3. The no-explicit-router option, taken seriously

**Design:** MailWeave ships no query-understanding at all beyond Tier-1. It exposes well-described primitives — e.g., search (lexical), fetch message, expand context around a message, fetch thread segment/full thread, related-threads — and the calling agent (itself a frontier LLM) is the router: it decomposes the user's question, picks tools, judges sufficiency, escalates.

**Why this is credible, not a cop-out:**

- The calling model is the best query-understander in the system *and it is already paid for* — its tool-choice turn happens regardless. An in-server LLM router re-buys, with a weaker or costlier model, a classification the client model already made. Anthropic's agent guidance points the same direction: prefer the simplest structure; "consider adding complexity *only* when it demonstrably improves outcomes" ([Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)).
- The client has context the server can never see: conversation history resolves "her," "that invoice," "the thread from last week" *before* the tool call. A server-side router sees only the tool arguments.
- Tool descriptions are a real, documented steering channel — Anthropic's tool-design guidance treats description/spec wording as prompt engineering with "dramatic improvements" from small refinements, plus namespacing, token-efficient responses, and error messages that steer the next call ([Writing effective tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents)). The escalation ladder can literally be *written into* the search tool's description and its structured responses ("0 results; constraints X dropped would give ~N; call `expand_context` on hit m37 for neighbors").

**Where it fails:**

1. **Round-trip cost.** Every escalation is a full MCP round trip *plus* a model turn. A 4-rung ladder driven client-side is 4 inference passes over a growing context; driven server-side it is milliseconds of Gmail API calls inside one tool call. Latency and token cost scale with rungs.
2. **Weak or impatient clients.** Smaller models mis-sequence tools; and even strong agents give up early — the original bug class (§1–3) shows agents concluding "not found" from one impoverished response. If recovery *requires* client initiative, the Recoverability invariant is hostage to client quality. This is the decisive argument against the *pure* form.
3. **Primitive sprawl.** Many overlapping tools degrade tool selection; the same Anthropic guidance recommends fewer, consolidated tools.
4. **No enforceable stopping policy.** Budget caps live in the client's judgment, not in code.
5. **Unportable behavior.** Quality varies per host/model; MailWeave's benchmark numbers would partly measure the client.

**Hybrid (recommended) — split the ladder at the price line:**

- **Server owns the cheap, deterministic micro-ladder (R1 + low rungs of R2/R3):** inside a single search tool call, do Tier-1 parse → execute → auto-relax/broaden within a fixed budget (§4.2 rungs L0–L3). These rungs cost only Gmail API calls, need no intelligence, and guarantee the floor: *one tool call never returns a bare false "not found."*
- **Client owns the expensive macro-ladder (high rungs of R2, semantic/structural/multi-thread):** the server never *forces* an LLM call or embedding pass (Adaptive Cost); instead every response carries explicit partiality metadata and typed next-step affordances, so escalation is one obvious tool call away. The agent decides whether the question justifies spending.
- Tier-2 heuristics (§2-A) only pick which micro-rung to start on.

This keeps invariant enforcement in code (server) and intelligence at the layer that already has it (client), and it degrades gracefully: a weak client still gets the micro-ladder floor; a strong client gets full adaptive behavior.

---

## 4. Where routing intelligence can physically live under MCP

### 4.1 The options, with verified constraints

**(a) In-server deterministic code.** Always available, no model, no key, microseconds. Verdict: **primary home** for Tier-1 + micro-ladder.

**(b) In-server LLM calls via MCP sampling (`sampling/createMessage`).** This was the theoretically elegant answer (server borrows the *client's* model, no server API key). **Verified reality kills it:**

- **The MCP spec deprecated Sampling in the current revision (2026-07-28), via SEP-2577:** "New implementations **SHOULD NOT** adopt it; existing implementations **SHOULD** migrate to integrating directly with LLM provider APIs." It remains in the spec ≥12 months; earliest removal is the first revision on/after 2027-07-28. Roots and Logging were deprecated in the same SEP. Sources: [sampling page, 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/client/sampling), [deprecated-features registry](https://modelcontextprotocol.io/specification/2026-07-28/deprecated).
- **Client support was thin even before deprecation.** Claude Code's sampling feature request ([anthropics/claude-code#1785](https://github.com/anthropics/claude-code/issues/1785), opened 2025-06-08) remains open/unimplemented as of this check; I found no support in Claude Desktop or claude.ai either (see "could not verify"). VS Code did ship sampling support ([full-spec announcement, 2025-06-12](https://code.visualstudio.com/blogs/2025/06/12/full-mcp-spec-support)). So for MailWeave's most likely first-party hosts — Claude surfaces — sampling was never available to depend on.
- Even where supported, the spec's human-in-the-loop SHOULD (user approval per sampling request) makes per-query router calls a UX non-starter.

**Verdict: ruled out.** Do not build any routing on sampling. This is decision-grade: it removes the only mechanism by which an MCP server gets model intelligence "for free," and therefore structurally favors the hybrid in §3.

**(c) Server-side direct model API calls** (server holds a provider key; the spec's own stated migration path, per the deprecation notice above). Implications: per-query cost; 0.3–2 s latency; an availability dependency that must degrade to (a); and — critical for §41 — email-derived text leaves the user's Gmail trust boundary to a provider *chosen by the server, not the user*. Verdict: **permissible later as opt-in config** (explicit key, explicit privacy disclosure), only for capabilities traces prove necessary (Tier-2B/LLM rerank, Loop 4+). Zero server-side model calls in the default Loop 3 build.

**(d) Client-side via tool design** (§3). Free, robust, spec-aligned. Verdict: **primary home for expensive escalation.** Supporting channel worth noting: **Elicitation** (server asks the *user* structured questions via the client) is in the current spec and is *not* in the deprecated registry ([elicitation, 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/client/elicitation)) — a possible future disambiguation channel ("three Sarahs found — which one?"), though client support must be checked before relying on it.

### 4.2 Resulting placement

```text
CLIENT (LLM agent)        SERVER (MailWeave code)             GMAIL API
──────────────────        ─────────────────────────           ─────────
interprets user query
resolves referents
chooses tool + args  ───► Tier-1 parse (deterministic)
                          heuristic first-rung pick (§2-A)
                          L0 exact ───────────────────────►   messages.list(q)
                          L1 filtered lexical ─────────────►  messages.list(q)
                          L2 relax constraints ────────────►  messages.list(q')
                          L3 broaden scope (in:anywhere,
                             wider dates) ─────────────────►  messages.list(q'')
                          sufficiency check (§5)
                     ◄─── evidence + partiality metadata
                          + tried/untried report
                          + typed next-step affordances
judges sufficiency
escalates explicitly ───► expand_context / thread segment /
                          related threads / (later: semantic)
```

---

## 5. Sufficiency / confidence policy — concrete signals

### 5.1 Signals computable in the Loop 3 build (no models, no scores to fabricate — §20's honesty rule)

| Signal | Definition | Use |
|---|---|---|
| `hit_count` | messages returned by executed `q` (actual page, not `resultSizeEstimate`) | 0 → relax (L2); 1 with `exact` parse → sufficient; 1–5 → disclose all; > `narrow_threshold` (e.g. 20) → over-broad: tighten or report top page + count honestly |
| `exact_signal_match` | hit satisfies an `exact`-class operator (msgid, quoted phrase, invoice-like token) | strongest stop signal |
| `query_term_coverage` | fraction of Tier-1 signals actually enforced in the executed `q` (relaxation drops signals; track them) | coverage < 1 ⇒ results are *candidates, not answers*; must be disclosed ("date filter was dropped to find this") |
| `constraint_drop_depth` | how many relaxation steps produced this result set | proxy for confidence decay |
| `participant_authorship` | for "what did X say" queries: hit authored by X vs. merely mentioning X (§22) | rank + disclose |
| `window_containment` | hits inside the user's stated date window vs. found only after widening | disclose |
| `duplicate_thread_concentration` | hits clustered in 1 thread vs. scattered across many | 1 thread → thread-segment disclosure; many → multi-thread ambiguity, surface the map |
| `empty_diagnosis` | on 0 hits: which single dropped constraint restores results (drop one-at-a-time probes are cheap `messages.list` calls) | turns "not found" into "not found *with your date filter*; 3 matches without it" |
| **score gap** (top1 − top2), margin ratios | **only once a scored retriever exists** (semantic/rerank, Loop 4+) | ambiguity measure for rerank-vs-disclose decisions; do not fabricate for lexical hits |

**Ambiguity measure without scores** [design proposal, to be validated in Loop 3]: `ambiguity = f(hit_count band, term_coverage, thread_concentration)` — e.g. many hits + low coverage + scattered threads = high ambiguity → disclose a compact candidate map (subjects/senders/dates) rather than bodies, and let the agent (or eventually elicitation) disambiguate.

### 5.2 Escalation ladder with budget caps (starting numbers — tune in Loop 3)

```text
Rung  Action                                     Per-rung budget
L0    exact-operator query                       1 messages.list + ≤5 messages.get
L1    filtered lexical (all Tier-1 signals)      1 list + ≤10 get
L2    relax: drop weakest constraint(s),         ≤3 list probes
      one at a time; try +word→plain, phrase→terms
L3    broaden: in:anywhere, widen dates ×4,      ≤2 list probes
      from:→{from: OR to:}
──── server-side ladder ends; report if still insufficient ────
L4    context expansion around hits              agent-invoked tool
L5    thread segment / full thread               agent-invoked tool
L6    related threads / participant pivot        agent-invoked tool
L7    semantic retrieval                         agent-invoked; Loop 4+, only if
                                                 benchmarks show paraphrase misses
Global caps (per top-level query, server side):
  max_rounds = 3 list-rounds beyond L0/L1
  max_gmail_calls ≈ 25 (list + get combined)
  max_latency_budget ≈ 2 s server-side p95 for L0–L3
  llm_calls = 0 (Loop 3 build)
```

Caps are enforced in code and **reported in the response** when hit, so exhausting a budget is itself visible, not silent.

### 5.3 Recoverability: how a wrong route avoids a false "not found"

1. **No dead-end responses.** The failure response is a structured `RetrievalReport`: queries executed, constraints dropped and why, hit counts at each rung, what was *not* tried (deeper history, semantic, other labels), and the affordances that would try it. An agent reading it can always continue; a human reading the agent's answer sees "not found in X under constraints Y," never a bare "doesn't exist." This is the CRAG evaluator pattern ([arXiv:2401.15884](https://arxiv.org/abs/2401.15884)) with the corrective action split between server (cheap corrections, automatic) and client (expensive corrections, offered).
2. **Relaxation is systematic, not clever.** Dropping constraints one at a time is dumb and enumerable — which is what makes it recoverable and loggable.
3. **Evidence preservation bounds the damage.** Because hits are message IDs (§1.1 fact 3), a *found* target can't be lost downstream; routing errors can only delay finding, never un-find (Loop 1's guarantee composing with Loop 3).
4. **Benchmark it directly:** §37–38's buried-target and false-"not-found" cases, plus adversarial mis-parses (wrong sender guess, wrong date window) asserting the ladder recovers within budget.

---

## 6. Instrumentation: trace schema for a future learned router

Purpose (per §15 and Decision 9): make a learned router *possible* later — Adaptive-RAG-style, labels harvested from outcomes — without committing to one now. Log per top-level query, **content-free by default** (no bodies, no raw subjects; hashed IDs; raw query text only behind an explicit debug flag — Agent F to review):

```jsonc
{
  "trace_id": "...", "ts": "...", "schema_version": 1,
  "client": {"host_hint": "claude-code|unknown", "tool_called": "search", "args_shape": ["free_text","date_range"]},

  "query_features": {                       // extracted, not raw text
    "tier1_confidence": "exact|filtered|weak|non_lexical",
    "operators_parsed": ["from","after"], "residual_term_count": 3,
    "has_person_ref": true, "has_date_ref": true, "has_quoted_phrase": false,
    "interrogative": "when|what|where|none",
    "decision_cue": false, "paraphrase_risk_heuristic": 0.4,
    "char_len_bucket": "short|med|long"
  },

  "routing": {
    "initial_route": "L1_filtered_lexical",
    "route_chosen_by": "tier1|heuristic|client_explicit",
    "rungs_executed": ["L1","L2","L3"],
    "constraints_dropped": ["date_window"],
    "fallback_triggered": true, "fallback_reason": "zero_hits",
    "escalation_offers_returned": ["expand_context","widen_dates"],
    "client_escalations_taken": ["expand_context"]      // observed in later calls, joined by trace/session id
  },

  "retrieval_outcome": {
    "rounds": 3, "gmail_list_calls": 4, "gmail_get_calls": 7, "llm_calls": 0,
    "hit_count_per_rung": [0, 2, 2],
    "final_hit_count": 2, "distinct_threads": 1,
    "term_coverage_final": 0.6, "exact_signal_match": false,
    "budget_caps_hit": [],
    "sufficiency_verdict": "sufficient|insufficient_reported|ambiguous_map_returned",
    "false_notfound_guard": "report_returned"           // never "bare_empty"
  },

  "cost": {"latency_ms_total": 840, "latency_ms_per_rung": [...], "disclosed_tokens_est": 1900},

  "eval_join": {"benchmark_case_id": null,              // set when run under the harness
                 "target_evidence_retrieved": null, "target_rank": null}
}
```

The pair (`query_features`, eventual-successful-route + cost) is exactly a training example for a §2-B classifier; `eval_join` fields make supervised labels free whenever the benchmark harness runs. Decide-later flag: whether production traces (vs. benchmark traces) may ever be used for training at all.

---

## 7. Recommended starting policy for build Loop 3

**"Cheapest-first with recoverable escalation," concretely:**

1. **One consolidated search tool** (plus fetch/expand primitives), accepting structured args *and* free text. Tier-1 deterministic parser (§1) inside it. Description text written as routing guidance for the calling agent (§3), per [Anthropic's tool-writing guidance](https://www.anthropic.com/engineering/writing-tools-for-agents).
2. **In-server micro-ladder L0–L3** (§5.2) with the stated budget caps; heuristic first-rung selection (§2-A); zero LLM calls, zero embeddings, zero sampling.
3. **Every response** carries: evidence (message-level hits, preserved), partiality metadata, `RetrievalReport` on weak/empty outcomes, typed escalation affordances. Client agent is the macro-router for L4+.
4. **Full trace logging** per §6 from day one — the instrumentation *is* part of the loop's deliverable.
5. **Loop 3 exit metrics** (per context §54): simple-query p50/p95 latency ≈ unrouted lexical baseline; hard-query recall strictly above L1-only; fallback rate observed and reported; false-"not-found" rate = 0 on the benchmark by construction (guarded response shape) — verify the guard, then verify the *agent's final answers* also stop asserting non-existence.

**Deferred** (each blocked on a measured failure, per §55): Tier-2 small-model classifier (blocked on traces — Decision 9); any server-side LLM call (blocked on traces + opt-in privacy design); semantic route L7 (Loop 4, blocked on paraphrase-miss evidence); learned rerank; elicitation-based disambiguation (blocked on client-support check); RouteLLM-style preference-trained routing ([arXiv:2406.18665](https://arxiv.org/abs/2406.18665) — cited as the shape of a *much* later option) **[arXiv ID from prior knowledge, not re-fetched]**.

**Rejected:** MCP-sampling-based routing (deprecated spec-side, unsupported in Claude-family clients — §4.1b); mandatory LLM router on every query (violates Adaptive Cost); router-decides-then-commits with no ladder (violates Recoverability); training any router now (Decision 9).

---

## Open questions for synthesis

1. **Tool granularity vs. the micro-ladder:** does the consolidated search tool make the L2/L3 auto-relaxations too invisible? Should relaxation beyond one dropped constraint require client opt-in (`allow_relaxation: false` arg) so agents that *want* strictness get it? (Interacts with Agent D's partiality metadata design.)
2. **Where does the sufficiency verdict for *disclosure* live?** This doc places retrieval sufficiency server-side (counts/coverage) and reasoning sufficiency client-side; Agent D's disclosure levels must agree on the seam.
3. **Session identity for traces:** joining "client escalations taken" to the originating query needs a session/trace key across MCP tool calls — is there a clean spec-conformant way, or is it heuristic (temporal adjacency)? Affects §6's learnability claim.
4. **Name→address resolution:** probe-query resolver vs. a small local contacts cache — the first place a "structural" store might sneak in. Does Agent B's retrieval architecture want a frequent-correspondents index anyway?
5. **Weak-client floor:** do we accept that non-agentic clients only ever get L0–L3 + reports, or should an *optional* server-side "deep search" mode (opt-in LLM key, §4.1c) exist for them eventually?
6. **Freshness interaction:** if Loop 6 shows direct-API search lag, does the ladder need a "history-based recency rung" (`history.list` since last known `historyId`) as an L3 alternative for recency queries?
7. **Budget caps as API surface:** should callers be able to pass their own budgets (max rounds/latency) per call, making cost policy client-tunable rather than server-fixed?

## What I could not verify

- **Claude Desktop / claude.ai sampling support:** I found no positive evidence either supports `sampling/createMessage`, and the open Claude Code request ([#1785](https://github.com/anthropics/claude-code/issues/1785)) plus community discussion imply the Claude family lacks it — but I could not locate an authoritative current client-feature matrix (the old modelcontextprotocol.io "Example Clients" page now redirects to a general overview; the new [extension matrix](https://modelcontextprotocol.io/extensions/client-matrix.md) tracks extensions, not core client features; a third-party matrix site's domain has lapsed). Treat "no Claude-surface sampling" as very likely but not spec-page-verified.
- **`resultSizeEstimate` unreliability magnitude:** "approximate" is documented; *how* wrong it gets is community folklore, unmeasured here — measure it in Loop 0/1.
- **Gmail stemming/partial-match behavior for plain terms:** not precisely documented by Google; treat as empirical territory for the benchmark.
- **`threads.list` `q` semantics parity with `messages.list`:** reference-family knowledge; spot-checked but not exhaustively verified this session.
- **Whether SEP-2577's sampling deprecation will actually lead to removal on the earliest date** — the registry explicitly says removal timing is a maintainer decision; only the deprecation itself is fact.
- **Self-RAG / RouteLLM arXiv IDs** ([2310.11511](https://arxiv.org/abs/2310.11511), [2406.18665](https://arxiv.org/abs/2406.18665)) cited from prior knowledge; FrugalGPT, CRAG, Adaptive-RAG links were verified this session.
- **Claude Code #1785 status is "open as of fetch"** — assignee shown, no maintainer resolution visible in fetched content; re-check at build time.

---

## SCOPE CORRECTION ADDENDUM (2026-08-30)

**Added by:** research-revision agent, after `docs/SCOPE_CORRECTION.md` (authoritative).
**Nature of this addendum:** §§0–6 above are analysis and verified protocol/API facts and are untouched. What changes is §7's "Recommended starting policy for build Loop 3" — specifically its **Deferred** list and its placement of the expensive half of the escalation ladder on the client side. Nothing is edited, deleted or renumbered.

### 1. Status of this document's conclusions

**Stand unchanged, and are explicitly endorsed by the correction:**

- **§0's R1/R2/R3 split**, and the claim that R2/R3 (escalation, stopping) matter more than R1 (first route). Correction §3: "The router is only an initial hypothesis… Escalation matters more than perfect first-route accuracy." This document's central thesis is the correction's central thesis.
- **§5.3's recoverability design** — no dead-end responses, systematic one-at-a-time relaxation, `RetrievalReport` instead of a bare empty result, message-ID hits bounding the damage. Correction §15: "Routing is recoverable and must not create unrecoverable false negatives."
- **§7 Rejected list**: MCP-sampling-based routing (deprecated spec-side; §4.1b), mandatory LLM router on every query, router-decides-then-commits with no ladder, **training any router now**. Correction §9 restates the last one verbatim in substance: "Do not train a router now… Build a recoverable router/adaptive policy now. Instrument it."
- **§6's trace schema**, and its content-free-by-default posture. Correction Appendix A.3 makes this binding rather than advisory (see §2 below).
- **§1's verified operator inventory and API constraints**, including `q` being unusable under `gmail.metadata`.
- **§4.1(b)'s verified finding that MCP Sampling is deprecated** and was never supported on Claude surfaces. Correction §14 preserves the MCP/stateless findings wholesale.

**Superseded as product scope, still valid as baselines:**

| Original conclusion | Status now |
|---|---|
| §5.2 ladder: "L7 semantic retrieval — agent-invoked; Loop 4+, **only if benchmarks show paraphrase misses**" | **Superseded as a gate.** Correction §4: semantic retrieval is part of the complete product. L7 becomes a built rung. Its *cost gating* survives untouched: it must not fire on easy queries (correction §8). |
| §5.2 budget line: "`llm_calls = 0` (Loop 3 build)" | **Now a default configuration and a baseline arm, not a product ceiling.** Correction §8: "It was never decided that MailWeave must never call a model internally." Constrained by Appendix A.1: local, or opt-in with a local/deterministic fallback. |
| §2 option table: "**C. LLM API call for classification** — Do not build into the default path" | **Stands, and is now doubly binding**: A.1 forbids core quality depending on a paid API. A *local* model call is a different option than the one this table scored, and was not scored here. |
| §2 option B ("small local model classifier") "**Defer — blocked by Decision 9**" | **Stands unchanged.** Correction §9 re-affirms it. This is the one deferral in the document that the correction explicitly keeps. |
| §3/§4.2 seam: "**Server owns the cheap micro-ladder (L0–L3); client owns the expensive macro-ladder (L4+)**" | **Materially changed — see §4/T-RC1.** The correction requires escalation to *happen*, which this document itself argued cannot be left to client initiative without making Recoverability "hostage to client quality" (§3 failure mode 2). |
| §7.5's Loop-3 exit metrics | **Stand as exit metrics**, but they are now rubric criteria under correction §16, not the end of the project. |

**Genuinely invalidated:** the framing that a rung of the ladder may not exist until a benchmark shows its absence hurting. Under correction §3 the ladder's rungs are product scope. The document's *design* of each rung, its budget caps, and its insistence that a wrong route never terminates a query all survive intact.

### 2. Baseline vs product requirement

| Item | Our recommended baseline / first rung | Complete-product requirement |
|---|---|---|
| Query understanding | Tier-1 deterministic parser (§1.2), typed `ParsedQuery` with `exact/filtered/weak/non-lexical` confidence | Unchanged — this *is* the cheap first rung correction §3 asks for |
| Tier-2 classification | Rule-based heuristics (§2-A) picking the first rung only | Unchanged; trained classifier still blocked (correction §9) |
| Server-side ladder | L0–L3 (exact → filtered → relax → broaden), pure `messages.list` work | **L0–L3 plus structural, semantic and ranking rungs must exist as product capability** (correction §3, §4, §5, §8) — the open question is which of them the server can run inside one call |
| Semantic rung (L7) | Not built | **Required**; local zero-API-cost default (A.1); must not fire on easy queries (correction §8) |
| Reranking | Not built | **Required where candidate ambiguity requires it**; explicitly *not* for exact Message-ID / invoice-number queries (correction §8) |
| Internal LLM calls | Zero | Permitted architecture choice, local or opt-in-with-fallback (correction §8 + A.1) |
| Escalation ownership | Server: cheap rungs. Client: expensive rungs | **Unresolved** — see T-RC1. The invariant "a wrong first route must never cause a false 'not found'" is now a release criterion, and it cannot be delegated to a client we do not control |
| Router training | None; instrument for later | Unchanged (correction §9, §15) |
| Trace contents | Content-free by default, raw query text behind a debug flag | **Binding privacy constraint** (A.3): IDs / metadata / routing / timings / scores only; short aggressively-redacted snippets only to diagnose a specific real-mailbox failure |

### 3. Facts that survive untouched

- **Tier-1 operator inventory** (§1.1) and the four API-side constraints: `messages.list(q)` returns `{id, threadId}` + approximate `resultSizeEstimate`; **`q` unusable under `gmail.metadata`**; API search is message-scoped not thread-wide; `threads.list` also accepts `q`.
- **MCP Sampling is deprecated** (SEP-2577, spec 2026-07-28): "New implementations SHOULD NOT adopt it; existing implementations SHOULD migrate to integrating directly with LLM provider APIs." Roots and Logging deprecated in the same SEP. Client support on Claude surfaces was thin-to-absent even before deprecation (claude-code#1785 open). **Elicitation survives and is not deprecated** — a possible future disambiguation channel, pending a client-support check.
- **The published evidence for cheap-first cascades**: FrugalGPT (arXiv:2305.05176) — most of the win comes from result-conditioned escalation, not first-choice accuracy; CRAG (arXiv:2401.15884) — a lightweight retrieval evaluator emitting correct/incorrect/ambiguous drives corrective fallback; Adaptive-RAG (arXiv:2403.14403) — its small router is trained from *automatically collected outcome labels*, i.e. exactly the traces we do not have yet.
- **§5.1's sufficiency signals** computable without any model: `hit_count`, `exact_signal_match`, `query_term_coverage`, `constraint_drop_depth`, `participant_authorship`, `window_containment`, `duplicate_thread_concentration`, `empty_diagnosis`. And the honesty rule attached to them: **do not fabricate scores for lexical hits**; score-gap ambiguity measures only become available once a scored retriever exists.
- **§5.2's budget-cap principle**: caps enforced in code and **reported in the response when hit**, so exhausting a budget is visible rather than silent.
- **§6's trace schema** — `query_features` + eventual-successful-route + cost is exactly a training example for a future classifier, and `eval_join` makes supervised labels free under the harness.

### 4. Unresolved tensions — stated, not smoothed

**T-RC1 — The correction requires escalation that MCP structurally will not fund, and this document's recommended seam puts it where we cannot guarantee it.**

The chain of verified facts and binding requirements:

1. **MCP Sampling is deprecated** (§4.1b, verified) and was never available on Claude surfaces. The server cannot borrow the client's model.
2. **Appendix A.1** forbids core retrieval quality from depending on a paid API. So a server-side provider key cannot be the default path either.
3. **Correction §3** requires structural, semantic and rank-based escalation to happen when lexical evidence is weak, and §15 makes "routing is recoverable and must not create unrecoverable false negatives" a settled product principle.
4. **This document's own §3 failure mode 2**: if recovery *requires* client initiative, the Recoverability invariant "is hostage to client quality" — and the original bug class exists precisely because agents conclude "not found" from one impoverished response.

Put together: the expensive rungs must exist, must fire reliably, must not depend on a paid API, and cannot be borrowed from the client's model. The remaining options are all costly, and architecture must pick one rather than pretend the seam is settled:

- **(a) Server-local intelligence.** The server ships/loads a local embedding model (and optionally a local reranker) and can run L4–L7 inside one tool call under a budget. Cost: an install-weight and RAM dependency in the default build, cold-start latency, and — per `SECURITY_NOTES` — a mail-content-fed model on the default path rather than an opt-in one.
- **(b) Deterministic-only server ladder + client-driven expensive rungs.** Cheapest, spec-idiomatic, and what §3 recommended — but its recoverability guarantee is only as good as the calling agent, which the correction does not permit for a release criterion.
- **(c) Hybrid with a server-enforced floor.** Server always runs L0–L3 plus a **bounded** semantic rung under a hard budget when its sufficiency check says lexical evidence is weak; anything beyond that budget is offered to the client as typed affordances. This preserves the document's seam logic while making the *first* expensive rung non-optional. It is the shape most consistent with both documents, and it is the one that inherits T-RC2 below.

This document's recommendation was (b). Under the corrected scope, (b) is not sufficient on its own. **Stating this plainly rather than quietly rewriting §3: the seam moves, and the cost of moving it is a local model dependency in the default build.**

**T-RC2 — The trigger for escalation cannot be computed from the signals that are available before escalating.**

Correction §8 requires that expensive paths "must not run unnecessarily on easy queries." That makes the sufficiency verdict load-bearing. But §5.1 is explicit that score-based ambiguity measures **only exist once a scored retriever exists** — before escalating, we have only `hit_count`, `query_term_coverage`, `constraint_drop_depth`, thread concentration and `empty_diagnosis`.

Those signals detect the *empty* failure well and the *ambiguous* failure adequately. They do **not** detect the failure semantic retrieval exists to fix. Correction §4's own example — user says "postpone the launch," email says "push go-live into Q4" — will typically produce a lexical result set that is non-empty (other messages mention "launch"), has high term coverage, and is concentrated in a plausible thread. **A confident-but-wrong lexical result is, under these signals alone, indistinguishable from a confident-and-right one.** This is now on the critical path, because escalation is required rather than optional.

Candidate resolutions, none free, all needing measurement:
- Escalate on *query shape* rather than result shape — paraphrase-risk heuristics (interrogatives, decision/temporal cues, absence of any `exact`-class operator) already sketched in §6's `query_features`. Cheap; will over-trigger.
- Escalate on **verification** rather than detection: run the cheap rung, then cheaply check whether the top hits actually *answer* the query. That check is the CRAG evaluator pattern (§0) and needs either a model or a heuristic proxy — reintroducing T-RC1.
- Accept over-triggering on a bounded, cheap semantic rung (T-RO2 in `RETRIEVAL_OPTIONS`: local embeddings over a low-hundreds pool) and rely on the cost budget rather than the trigger to keep it honest.
- Whichever is chosen, **the benchmark must include the case where lexical returns plausible wrong hits**, not only the case where it returns nothing. The existing benchmark families skew toward the empty case.

**T-RC3 — Auto-relaxation and required escalation both erode "the user asked for X and got X."**

§5.1's `query_term_coverage` and the "constraints dropped and why" reporting were designed to keep relaxation honest. Adding required semantic and structural rungs multiplies the ways a returned message can be present for a reason the user never asked for. The document's original open question 1 ("should relaxation beyond one dropped constraint require client opt-in?") is now sharper and applies to the whole ladder: **every rung must attach a mechanical, non-fabricated reason to every returned message, and the response must remain readable as "here is what I actually searched for."** This is a constraint on the response format, not a reason to drop rungs.

### 5. What architecture must now decide that this document treated as deferred

1. **Where the seam sits** (T-RC1): (a), (b) or (c). This is the single largest open decision in this document and it determines whether a local model is a default-build dependency.
2. **The escalation trigger** (T-RC2), and the benchmark family that tests it — specifically the plausible-but-wrong lexical result, which is currently under-represented.
3. **Which rungs the server may run inside one tool call**, and the budget caps for each (extending §5.2's `max_rounds` / `max_gmail_calls` / `max_latency_budget` to cover embedding time and reranker time, which are CPU-bound rather than RTT-bound and need their own cap).
4. **Where the reranker fires and where it must not** (correction §8): a rule expressed in code, e.g. never when `exact_signal_match` is true, never when `hit_count == 1`, never on an `rfc822msgid:` route.
5. **The sufficiency-verdict seam with disclosure** (original open question 2, now unresolved in both directions): this document places retrieval sufficiency server-side and reasoning sufficiency client-side; `CONTEXT_DISCLOSURE_OPTIONS`'s query-aware policy is now the product policy and needs the same signals.
6. **Session/trace identity across MCP tool calls** (original open question 3) under a stateless spec — resolved in shape by correction §14 (server-minted handles as ordinary tool arguments), still needing a concrete design.
7. **Trace schema v2 under A.3**: confirm the schema persists IDs/metadata/routing/timings/scores only; decide the narrowly-gated exception for aggressively-redacted snippets when diagnosing a specific real-mailbox failure, and make the debug flag for raw query text conform to it. Note `query_features` was already designed to avoid raw text — keep it that way.
8. **Freshness rung** (original open question 6, now required by correction §12): if measured lag exists, does the ladder gain a `history.list`-based recency rung as an L3 alternative for recency queries?
9. **Client-tunable budgets** (original open question 7) — interacts with the release criterion: a client must not be able to set a budget that disables the recoverability floor.
