# CONTEXT_DISCLOSURE_OPTIONS.md

**Agent D — progressive disclosure / context representation design space**
**Date:** 2026-08-30
**Scope:** Given that retrieval (Agents B/C) has identified candidate evidence, this document maps the options for *how much the agent sees, in what shape, and how partiality stays explicit*. It covers MAILWEAVE_CONTEXT.md §10.2 (progressive disclosure), §25 (query-aware vs fixed ±N expansion), §26 (disclosure semantics), and §48 (what progressive disclosure should mean).

**Governing invariants (from §39):**

- **Evidence Preservation** — a message identified as matching/supporting the query must never silently vanish from the representation.
- **Explicit Partiality** — any partial view must announce that it is partial and carry a concrete path to more.

Two corollaries this document adds and defends below:

- **Partiality is recursive** — quote-stripping, snippet truncation, and skeleton elision are themselves partial views and need the same explicit markers as thread-level truncation (see §5.4).
- **The affordance must live in-band** — the path to "more" must appear inside the tool result the model actually reads, whatever else (MCP resources, etc.) is also offered (see §7).

Everything here is an option space for the synthesis agent, **not a final API**. JSON shapes are sketches.

---

## 1. Verified foundations this design leans on

Facts checked on 2026-08-30 (see also "What I could not verify" at the end).

### 1.1 Gmail API primitives for disclosure

- **Thread fetch supports a metadata-only format.** `users.threads.get` takes `format` ∈ `full` | `metadata` | `minimal`; `metadata` "Returns only email message IDs, labels, and email headers," and `metadataHeaders[]` — "When given and format is METADATA, only include headers specified" — restricts which headers come back.
  https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.threads/get
  Same `Format` enum for messages (adds `RAW`): https://developers.google.com/workspace/gmail/api/reference/rest/v1/Format
- **Per-message metadata available for a skeleton.** The `Message` resource carries `id`, `threadId`, `labelIds[]`, `snippet` ("A short part of the message text"), `internalDate` ("The internal message creation timestamp (epoch ms), which determines ordering in the inbox"), `historyId`, `sizeEstimate` ("Estimated size in bytes of the message"), and `payload` (a `MessagePart`). `MessagePart.headers[]` is documented as: "List of headers on this message part. For the top-level message part, representing the entire message payload, it will contain the standard RFC 2822 email headers such as `To`, `From`, and `Subject`."
  https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages
- **RFC threading headers are RFC 2822/5322 standard headers.** `Message-ID`, `In-Reply-To`, and `References` are the identification fields of RFC 5322 (successor to RFC 2822), https://datatracker.ietf.org/doc/html/rfc5322. Since Gmail's `payload.headers[]` carries "the standard RFC 2822 email headers," these are the headers to request via `metadataHeaders` for reply-chain reconstruction. **Caveat:** Google's docs name `To`/`From`/`Subject` as *examples*; they do not enumerate `References`/`In-Reply-To` explicitly. Loop 0 must smoke-test that `format=metadata&metadataHeaders=Message-ID&metadataHeaders=In-Reply-To&metadataHeaders=References` returns them (expected: yes when present on the wire; a message whose client never set them has nothing to return).
- **Gmail threads ≈ conversations, not an RFC reply tree.** Gmail's threading guide states threads "group email replies with their original message into a single conversation," and — for a message to be appended to a thread — "The `References` and `In-Reply-To` headers must be set in compliance with the RFC 2822 standard" and "The `Subject` headers must match," plus the `threadId` must be supplied.
  https://developers.google.com/workspace/gmail/api/guides/threads
  Implication: a Gmail thread is a *flat set* of messages ordered by `internalDate`; the reply *tree* inside it must be reconstructed client-side from `Message-ID`/`In-Reply-To`/`References` — the classic JWZ threading algorithm (https://www.jwz.org/doc/threading.html), also standardized as the REFERENCES algorithm in the IMAP THREAD extension (https://datatracker.ietf.org/doc/html/draft-ietf-imapext-thread-10). Multiple maintained implementations exist (e.g., https://github.com/akuchling/jwzthreading).
- **Quota economics.** As listed on Google's quota page at fetch time: `messages.get` 20 units, `messages.list` 5, `threads.get` 40, `threads.list` 10, `messages.attachments.get` 20, `history.list` 2; per-user limit 6,000 quota units/min per project (≈100/s), per-project 1,200,000/min.
  https://developers.google.com/workspace/gmail/api/reference/quota
  *(Note: older third-party references cite different unit values, e.g. messages.get=5 / 250 units/user/sec; re-check at build time. The design conclusions below survive either table.)*
  **Key point:** the quota table has one row per method — `threads.get` costs the same whether `format=metadata` or `full`. A metadata skeleton saves **tokens, bandwidth, and latency**, not quota units.
- **Attachments are separately addressable.** Attachment bodies are fetched by `users.messages.attachments.get` (own quota row above); `MessagePart.filename`/`mimeType` identify them inside `payload` without fetching bytes.

### 1.2 MCP capabilities (what the protocol supports today)

Verified against the 2025-06-18 spec (current stable at research time; 2025-11-25 revision and a 2026-07-28 release candidate exist — see below):

- **Tool results** may contain `text`, `image`, `audio`, **`resource_link`** ("A tool MAY return links to Resources ... the tool will return a URI that can be subscribed to or fetched by the client"), and **embedded `resource`** content blocks; plus **`structuredContent`** with an optional **`outputSchema`** ("Servers MUST provide structured results that conform to this schema"). All content blocks support annotations (`audience`, `priority`, `lastModified`).
  https://modelcontextprotocol.io/specification/2025-06-18/server/tools
  Spec caveat: "Resource links returned by tools are not guaranteed to appear in the results of a `resources/list` request."
- **Resources**: `resources/list` (cursor pagination), `resources/read`, `resources/templates/list` with RFC 6570 URI templates, optional `subscribe`/`listChanged`. Resources are explicitly "**application-driven**, with host applications determining how to incorporate context" — i.e., the *model* is not guaranteed to see them unless the host wires them in.
  https://modelcontextprotocol.io/specification/2025-06-18/server/resources
- **2025-11-25 revision** adds icons, URL-mode elicitation, experimental long-running *tasks*, tool calling in sampling, JSON Schema 2020-12 — nothing that changes the disclosure design above; resource links/structured content carry forward.
  https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2025-11-25/changelog.mdx ; anniversary post: https://blog.modelcontextprotocol.io/posts/2025-11-25-first-mcp-anniversary/ ; RC: https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/

### 1.3 Host-side budget and tool-design guidance

- **Claude Code caps MCP tool responses at 25,000 tokens by default** (`MAX_MCP_OUTPUT_TOKENS`), warns at 10,000; a server can raise a per-tool cap via `_meta["anthropic/maxResultSizeChars"]` (≤500,000 chars). It issues `resources/list` on connect and supports `list_changed`.
  https://code.claude.com/docs/en/mcp
  Design consequence: **a full 100-message thread dump can silently hit the host cap** — the exact "invisible truncation" failure MailWeave exists to prevent, except now imposed by the *client*. Disclosure must keep every response comfortably under host caps so truncation authority stays with MailWeave, where it can be made explicit.
- **Anthropic's tool-design guidance** (verified quotes): "More tools don't always lead to better outcomes"; consolidate workflows ("Tools can consolidate functionality, handling potentially multiple discrete operations ... under the hood"); "Implement some combination of pagination, range selection, filtering, and/or truncation with sensible default parameter values"; use a `response_format`-style enum (their Slack example: concise ≈72 tokens vs detailed ≈206, ~35%); namespace related tools; "return only high signal information," preferring semantic fields over UUID soup.
  https://www.anthropic.com/engineering/writing-tools-for-agents
- **Progressive disclosure is now Anthropic-endorsed vocabulary** for tool surfaces: the code-execution post describes loading tool definitions on demand and keeping large intermediate results out of model context (their motivating example: 150,000 → 2,000 tokens, 98.7% reduction).
  https://www.anthropic.com/engineering/code-execution-with-mcp

### 1.4 The failure being designed against

Hosted Gmail MCP `search_threads` returns a matching thread whose `messages[]` preview omits the very message that matched (rfc822msgid repro; `newer_than:1d` repro), while `get_thread` returns everything — issues #296, #730, #76396 (statuses per MAILWEAVE_CONTEXT.md §3; Agent A owns re-verification). Disclosure design must make that class of bug *structurally impossible*: **the hit is always in the view, and the view always declares its edges.**

---

## 2. The two axes of disclosure

Every option below is a point on two independent axes. Conflating them is how APIs end up with meaningless "levels."

```text
Axis S — SELECTION breadth: which messages are in the view?
        (hit only → hit+parents → hit±N → segment → whole thread → multi-thread)

Axis D — DEPTH per message: how much of each selected message?
        (stub: headers only → snippet → cleaned body (quotes stripped) → full body → raw MIME)
```

A response is a *set of (message, depth) pairs plus partiality metadata*. "Progressive disclosure" = the agent can cheaply move outward on S and downward on D, and always knows how far it currently is on both.

---

## 3. Expansion strategies (Axis S option space)

For each: mechanism, when it wins, cost, failure modes. Costs assume the thread skeleton of §4 is available (one `threads.get?format=metadata` call); token figures use the economics of §6.

### E1. Fixed ±N neighbor window (baseline)

**Mechanism:** return the hit message plus N adjacent messages on each side in `internalDate` order.

- **When it wins:** conversational locality is real — replies usually respond to nearby messages. Wins on "what was decided in this exchange," clarifies pronouns/ellipsis in the hit ("yes, let's do that"), and is trivially predictable/debuggable. Already strictly better than the status quo because it is *anchored on the hit*, not on thread position 1–5.
- **Cost:** cheapest possible policy: zero extra reasoning; 2N extra message bodies ≈ 2N × 300–800 tokens cleaned (§6). API: bodies come from `messages.get` per included message, batchable.
- **Failure modes:**
  - *Adjacency ≠ relevance:* in multi-topic threads (the 16-month thread of issue #730) the ±2 neighbors may be a different conversation entirely.
  - *Split evidence:* proposal at msg 37, confirmation at msg 64 — no N short of 27 spans both; large N reintroduces the dump.
  - *Interleaved subthreads:* `internalDate` adjacency crosses reply-branch boundaries (the neighbor may be a sibling branch, not the parent).
- **Verdict:** correct **Loop 2 baseline** (§54 Loop 2 of the context doc names it); wrong resting point. N=2 is the suggested default (judgment, to be tuned).

### E2. Reply-chain expansion

**Mechanism:** reconstruct the reply tree from `Message-ID`/`In-Reply-To`/`References` (JWZ algorithm, §1.1) using headers already present in the skeleton; expand the hit to its parent(s), direct children, and optionally the root.

- **Verified feasibility:** headers are requestable via `threads.get?format=metadata&metadataHeaders=...` (one call for the whole thread — §1.1, with the smoke-test caveat). Gmail will *not* hand you the tree; MailWeave builds it. Gmail's own thread membership is looser than RFC threading (conversation grouping + subject rules), so expect messages in a thread with no RFC linkage — JWZ's dummy-container handling covers orphans.
- **When it wins:** questions about *dialogue structure*: "what was Sarah replying to?", "did anyone answer this?", "who pushed back?". Beats E1 exactly where E1 fails: interleaved subthreads — the parent may be 15 messages back in date order but one hop in the tree (§25 of the context doc calls this case out).
- **Cost:** tree construction is O(thread size) string work on data the skeleton already fetched — effectively free. Bodies for parent+children ≈ 2–4 messages. Latency: none beyond the skeleton call.
- **Failure modes:**
  - *Missing/broken headers:* some clients and list software drop or rewrite `In-Reply-To`/`References`; RFC 5322 permits trimming `References`. Result: orphaned nodes, false roots. Mitigation: fall back to E1 adjacency for unlinked messages, and say so in metadata (`"linkage": "date-adjacent (no RFC reply headers)"`).
  - *Top-posting culture:* in many corporate threads everyone replies to the latest message, so the "tree" degenerates to a chain and E2 ≈ E1.
  - *Deep chains:* "expand to root" on a 100-deep chain is a dump wearing a tree costume; needs a hop budget.
- **Verdict:** the highest value-per-cost structural upgrade; the natural core of the query-aware variant.

### E3. Temporal segment expansion

**Mechanism:** cluster the thread's `internalDate` sequence into bursts (e.g., gap > X hours ⇒ new segment); disclose the whole segment containing the hit, or the segment nearest a query-specified time.

- **When it wins:** "when did X change," "the discussion in March," decision-evolution queries (§21, §23) — email activity is bursty, and a burst usually corresponds to one episode (proposal day, decision day). Segment boundaries are also good *summary* units.
- **Cost:** clustering is free on the skeleton. Segments average small but are unbounded — a 30-message flame-day is a real risk, so segment disclosure needs an internal cap ("first/last K of segment + stubs").
- **Failure modes:** gap thresholds are corpus-dependent (judgment: start at 24h, tune in Loop 2); a decision and its confirmation may sit in different bursts; timezone display issues are cosmetic (internalDate is epoch ms) but *ordering by internalDate vs sent Date header* can disagree for delayed/imported mail.
- **Verdict:** cheap add-on; most useful as the unit for skeleton grouping and for temporal queries specifically, not as the universal policy.

### E4. Query-aware expansion

**Mechanism:** score the *non-included* skeleton entries against the query (cheap signals first: sender match, subject-token overlap, snippet-term overlap, date proximity to query time cues; optionally embeddings/reranker from Agent B's stack) and spend the expansion budget on the top-scoring messages regardless of adjacency, tagging each with why it was added.

- **When it wins:** split evidence (proposal@37 + confirmation@64 in one budget), participant queries ("what did *Sarah* say" → expand Sarah's messages only), multi-topic mega-threads. This is the thesis bet of the project (§25): related ≠ adjacent.
- **Cost:** scoring over skeleton fields is microseconds and token-free; scoring over *bodies* requires fetching bodies first (chicken-and-egg — mitigate by scoring on snippet+headers, fetching, then optionally re-scoring). LLM-based selection would add a model call (hundreds of ms + tokens) — keep optional per the Adaptive Cost Invariant.
- **Failure modes:**
  - *Wording overfit:* query-term scoring re-creates lexical search's paraphrase blindness inside the thread; the confirmation "Done — Oct 17 it is" shares no tokens with "postpone the launch."
  - *Self-confirmation bias:* expanding only query-similar messages can hide the *objection* that reverses the decision. Mitigation: always include E2 parents/children as a structural floor beneath the scored picks.
  - *Explainability debt:* per §20, never emit fabricated relevance scores; reasons must be mechanical ("snippet contains 'october'", "sender=sarah@", "parent of hit").
- **Verdict:** the **Loop 2 variant to test against E1** (recommendation §9). Hypothesis, not a proven win — Loop 2 exists to measure it.

### E5. Multi-thread expansion

**Mechanism:** from the current evidence, discover sibling threads: same normalized subject (`Re:`/`Fwd:` stripped), overlapping participant set within a time window, explicit forwards, or additional search hits already in hand from message-level search (`messages.list` naturally returns hits across threads — §16).

- **When it wins:** "what has Sarah told me about Apollo," decisions that migrate to a fresh subject line ("New thread for the launch date…"), forwarded context. Directly serves §37's multi-thread benchmark family.
- **Cost:** each sibling thread costs a `threads.get` skeleton (40 quota units each at listed rates) plus tokens for another map; discovery searches cost `messages.list` calls. This is the most expensive strategy per step — and the least bounded.
- **Failure modes:** topic drift ("Apollo" the project vs the gym class); subject normalization collisions ("Meeting notes"); combinatorial fan-out (each thread suggests more threads). Needs a hard thread-count budget and must always present sibling threads as *stubs first* (subject, participants, date range, hit count — not bodies).
- **Verdict:** expose as an explicit affordance (`related_threads[]` stubs + an expand call), never as automatic inclusion. Cross-thread *retrieval* is Agent B/C territory; disclosure's job is to represent it without dumping it.

### E6. Attachment surfacing

**Mechanism:** skeleton rows and message views list attachments from `payload.parts` (filename, mimeType, size) as stubs; bytes only via an explicit fetch (`messages.attachments.get`), and extracted *text* of a document only as a clearly derived artifact.

- **When it wins:** "find the spreadsheet Sarah sent" (§8, §37) — often the filename/type in the map answers the question with zero bytes fetched.
- **Cost:** metadata is free (already in `full`-format payload; **caveat:** whether `format=metadata` includes part structure/filenames is *not* documented — smoke-test; if absent, attachment stubs require the body fetch of that message anyway, which is when you want them). Bytes are 20 quota units + potentially megabytes — never inline into model context; hand over as MCP resource link / file path and extract text server-side on request.
- **Failure modes:** huge/binary files; prompt injection embedded in documents (§42) — extracted text must carry the same untrusted-content framing as bodies; OCR/parse failures must be reported as failures, not empty strings (a silent empty extraction is an evidence-destruction bug).
- **Verdict:** stubs always, bytes never by default, extraction on demand and marked derived.

### Comparison table

| Strategy | Extra API calls (with skeleton) | Token cost | Wins on | Worst failure | Complexity |
|---|---|---|---|---|---|
| E1 fixed ±N | body fetches only | ~2N×300–800 | local dialogue | adjacency ≠ relevance | trivial |
| E2 reply-chain | none (headers in skeleton) | ~2–4 bodies | interleaved subthreads, "replying to what?" | missing RFC headers | low |
| E3 temporal segment | none | segment-sized (cap!) | episodes, "when did X change" | bad gap threshold | low |
| E4 query-aware | none for scoring; bodies for picks | budget-bound | split/buried evidence | wording overfit, hides objections | medium |
| E5 multi-thread | +1 skeleton per sibling (+searches) | +map per thread | cross-thread topics | fan-out explosion | medium-high |
| E6 attachments | +1 per byte fetch | stub ≈ 15 tokens | document queries | injection, silent parse failure | low-medium |

**Composition rule (proposed):** E2 structural floor (parent + children) → fill remaining budget by policy (E1 blind or E4 scored) → E3/E5/E6 as query-triggered or agent-requested affordances. Everything not included appears as stubs.

---

## 4. Thread maps / skeletons

The single highest-leverage disclosure idea in this document.

### 4.1 What it is

For any thread touched by a result, MailWeave returns a **complete per-message index** — every message as one cheap row — so the agent sees the *shape* of a 100-message thread before opening anything:

```text
position | message id | from → to | date | reply-parent | flags (attachments, labels) | snippet
```

### 4.2 Cost — verified

- **One API call**: `threads.get?format=metadata` returns *all* messages' IDs, labels, and headers in a single response (§1.1). With `metadataHeaders` restricted to `From, To, Cc, Subject, Date, Message-ID, In-Reply-To, References`, the wire payload stays lean. Quota cost identical to a full fetch (one table row per method) — the win is context/bandwidth/latency, not quota.
- **Snippet caveat:** the `metadata` format description says "message ID, labels, and email headers"; whether `snippet`/`internalDate`/`sizeEstimate` accompany it is undocumented. Empirically expected yes (they are top-level resource fields, not payload) but **must be smoke-tested in Loop 0**; if absent, the skeleton falls back to headers `Date`/`Subject` and no snippet, or per-message `messages.get?format=minimal` is reconsidered (worse: minimal lacks headers).
- **Token cost:** a disciplined row ≈ 30–50 tokens (§6 math). 100-message thread ⇒ **~3,000–5,000 tokens** for total situational awareness — vs ~25,000+ (host-capped, §1.3) for a full dump. An 11-message thread (issue #296's repro) ⇒ ~400–500 tokens.

### 4.3 Value

- **Makes the invariants cheap to honor:** if every message exists at least as a row, nothing can *silently* vanish — omission becomes visually explicit (a stub row), and the "path to more" is simply "expand these ids."
- **Evidence-position invariance:** the agent can see msg 37's snippet mentions "October" and open *that*, regardless of where the window fell — directly attacks the §38 position-sweep adversary.
- **It is the natural carrier for hit-marking** (`role: matched` on rows), for reply-tree display (indentation/parent column), and for segment grouping (E3).
- **It converts disclosure from server guessing to agent choosing** — aligned with how Claude-class agents work best (explicit affordances in results; §7).

### 4.4 Compression for very large threads

A 500-message thread's map is ~20k tokens — too big. Options, all invariant-compliant because elision is *announced*:

- **Row diet:** drop snippet for non-hit rows beyond a distance; collapse `from` to display-name; positions instead of ids (ids resolvable via a `position → id` expand call keyed on the map's `map_id`).
- **Run collapsing:** `rows 41–78: 38 messages, 2026-01-03→2026-02-11, senders {list@…×31, bob×7}, 0 hits — expand_rows(41,78)`. The collapsed run is itself a stub with a fetch path (partiality is recursive).
- **Segment-level map (E3):** one row per burst with counts, participants, date range, hit flags; drill into a segment for message rows.
- **Judgment:** default to full rows ≤150 messages; segment map above that. Tune in Loop 2.

### 4.5 Derived summaries

Optional layer: a one-line or paragraph summary per segment/thread, produced by a model.

- **Rules (non-negotiable per §26):** always labeled `"derived": true` with `method` and `source_message_ids[]`; never *replaces* rows or bodies (a summary sits beside the map, not instead of it); inherits untrusted-content status (a summary of an injection email can carry the injection — §42); never generated silently on the hot path for latency reasons (Adaptive Cost Invariant) — generate on request or asynchronously.
- **Where they earn their cost:** very large threads where even the segment map is big; "how did this conversation evolve" queries. Where they don't: any query answerable from rows/snippets.
- **Risk:** summaries are the one representation that can *fabricate* — a wrong summary is worse than a missing one because it reads as evidence. Loop 2 should not include summaries; they are a later experiment (Loop 5+) with their own eval (summary-faithfulness).

---

## 5. Partiality metadata — candidate response shapes

Three sketches. Common vocabulary used by all three:

```text
role  (why is this message in the view):
  "matched"    — retrieval hit; reason string is mechanical ("gmail q matched", "rfc822msgid", "semantic sim 0.81 (cosine, model X)")
  "context"    — included by expansion policy (policy named: "window±2", "query-scored: snippet contains 'october'")
  "parent"/"child" — reply-chain structural inclusion
  "requested"  — agent explicitly asked for it
  "stub"       — present as index row only (depth = headers)

disclosure depth per message:
  "stub" | "snippet" | "body_clean" | "body_full" | "raw"
```

### Shape P1 — Coverage-header envelope (minimal delta from a normal search result)

A flat result plus one `coverage` block per thread. Closest to existing Gmail-MCP-style responses; easiest migration.

```json
{
  "query": "when did sarah agree to move the launch",
  "threads": [
    {
      "thread_id": "t_18c2...",
      "subject": "Launch planning",
      "coverage": {
        "total_messages": 100,
        "included_full": 3,
        "included_as_stubs": 0,
        "omitted": 97,
        "omitted_note": "97 messages not shown; no per-message index in this shape",
        "get_more": [
          {"call": "expand_thread", "args": {"thread_id": "t_18c2...", "around_message": "m_37", "radius": 4}},
          {"call": "thread_map", "args": {"thread_id": "t_18c2..."}}
        ]
      },
      "messages": [
        {
          "id": "m_36", "position": 36, "role": "context", "role_reason": "window±1",
          "from": "Bob <bob@ex.com>", "date": "2026-08-04T09:12:00Z",
          "disclosure": "body_clean",
          "body": "Can we realistically hold the date?",
          "body_meta": {"quoted_removed_chars": 4210, "get_full": {"call": "get_message", "args": {"id": "m_36", "view": "body_full"}}}
        },
        {
          "id": "m_37", "position": 37, "role": "matched", "role_reason": "gmail q: 'launch move sarah'",
          "from": "Sarah <sarah@ex.com>", "date": "2026-08-04T10:02:00Z",
          "disclosure": "body_clean",
          "body": "Fine — let's move the launch to October 17.",
          "body_meta": {"quoted_removed_chars": 0}
        },
        { "id": "m_38", "position": 38, "role": "context", "role_reason": "window±1", "disclosure": "body_clean", "from": "PM <pm@ex.com>", "date": "2026-08-04T10:40:00Z", "body": "Confirmed, updating the plan." }
      ]
    }
  ],
  "result_meta": {"tokens_estimate": 900, "search_scope": "messages.list q=..., 200 most recent scanned", "complete": false}
}
```

- **Pros:** small; low overhead (~60–100 tokens per thread); trivially satisfies "announce partiality + offer path."
- **Cons:** the 97 omitted messages are a *number*, not a *shape* — the agent can't target msg 64 without another call; weaker against buried-evidence cases. Evidence preservation holds only for hits inside the response; omitted-hit bugs remain representable if a bug drops a hit (nothing structural prevents it).

### Shape P2 — Map-carrier (skeleton always present; bodies attached selectively) — **recommended default**

The thread map *is* the response spine; every message appears at least as a stub row, so "silently missing" is structurally impossible; depth varies per row.

```json
{
  "thread_id": "t_18c2...",
  "subject": "Launch planning",
  "map": {
    "map_id": "map_9f2",  
    "total_messages": 100,
    "complete": true,
    "source": "threads.get format=metadata, fetched 2026-08-30T14:02:11Z",
    "reply_tree": "reconstructed from References/In-Reply-To (JWZ); 3 messages unlinked, shown date-ordered",
    "segments": [
      {"seg": 1, "rows": "1-22", "span": "2026-05-02..2026-05-19", "hits": 0},
      {"seg": 2, "rows": "23-51", "span": "2026-08-01..2026-08-09", "hits": 1},
      {"seg": 3, "rows": "52-100", "span": "2026-08-10..2026-08-29", "hits": 1}
    ],
    "rows": [
      {"pos": 36, "id": "m_36", "from": "bob@ex.com", "date": "2026-08-04", "parent_pos": 35, "depth_shown": "body_clean", "role": "context"},
      {"pos": 37, "id": "m_37", "from": "sarah@ex.com", "date": "2026-08-04", "parent_pos": 36, "depth_shown": "body_clean", "role": "matched", "snippet": "Fine — let's move the launch to October 17"},
      {"pos": 64, "id": "m_64", "from": "sarah@ex.com", "date": "2026-08-21", "parent_pos": 60, "depth_shown": "stub", "role": "stub", "snippet": "Confirmed: October 17 is final", "attachments": [{"filename": "launch-plan-v3.xlsx", "mime": "application/vnd...", "bytes": 48211}]}
      /* ... every one of the 100 rows present, most as stubs; long zero-hit runs may be collapsed with an explicit expand_rows affordance ... */
    ]
  },
  "bodies": [
    {"id": "m_36", "disclosure": "body_clean", "text": "...", "quoted_removed_chars": 4210},
    {"id": "m_37", "disclosure": "body_clean", "text": "Fine — let's move the launch to October 17.", "quoted_removed_chars": 0},
    {"id": "m_38", "disclosure": "body_clean", "text": "..."}
  ],
  "expand": {
    "by_id": {"call": "get_messages", "args": {"ids": ["..."], "view": "body_clean|body_full|raw"}},
    "by_rows": {"call": "expand_rows", "args": {"map_id": "map_9f2", "from_pos": 1, "to_pos": 100}},
    "note": "any row can be opened; stubs are withheld content, not absent content"
  }
}
```

- **Pros:** strongest invariant enforcement (omission ⇒ visible stub); agent can *aim* (sees msg 64's snippet and opens it directly — split-evidence case solved without server cleverness); reply tree and segments ride along free; `map_id` gives expansion calls a stable referent.
- **Cons:** map overhead on every thread response (~30–50 tokens/row); for multi-thread results with several large threads, maps dominate the budget — needs the §4.4 compression ladder; `complete: true` requires an actual full skeleton fetch (one extra API call vs P1 when the search only touched messages).

### Shape P3 — Evidence bundle + resource links (MCP-native large-body handling)

Compact in-band evidence; everything bulky is a `resource_link` content block resolvable via `resources/read` with RFC 6570 templates (`mailweave://thread/{threadId}`, `mailweave://message/{id}?view={view}`).

```json
{
  "evidence": [
    {"id": "m_37", "role": "matched", "role_reason": "gmail q match", "from": "sarah@ex.com", "date": "2026-08-04", "disclosure": "body_clean", "text": "Fine — let's move the launch to October 17."}
  ],
  "context_available": {
    "thread": {"id": "t_18c2...", "total_messages": 100, "shown": 1},
    "links": [
      {"type": "resource_link", "uri": "mailweave://thread/t_18c2/map", "name": "thread map (100 rows)", "mimeType": "application/json"},
      {"type": "resource_link", "uri": "mailweave://message/m_37?view=body_full", "name": "full body incl. quoted text"},
      {"type": "resource_link", "uri": "mailweave://message/m_64/attachment/0", "name": "launch-plan-v3.xlsx (48 KB)"}
    ]
  },
  "fallback": {"note": "if your client cannot read mailweave:// resources, the same views are available via the get_messages / thread_map tools", "calls": ["thread_map", "get_messages"]}
}
```

- **Pros:** minimum in-band tokens; protocol-idiomatic (verified: tools MAY return resource links, §1.2); large artifacts (raw MIME, attachments) never threaten the host token cap; URIs double as honest names for withheld content.
- **Cons (decisive):** resources are application-driven; the spec does not guarantee the model sees or can fetch them, and resource links from tools aren't even guaranteed to be listed (§1.2). Client support is uneven in practice (judgment; Claude Code reads resources via dedicated tools, other hosts vary). **A partiality affordance that some clients can't exercise violates the spirit of the Partiality Invariant.** Hence: P3 only ever as an *overlay* on P1/P2 with tool-call fallbacks in-band, as sketched.

### 5.4 Cross-cutting partiality rules (apply to whichever shape wins)

1. **No bare counts.** Every "N omitted / N total" is adjacent to a concrete call (tool + args or URI) that retrieves it.
2. **Why-present enum on every message** (`role` + mechanical `role_reason`); no fabricated scores (§20).
3. **Recursive partiality:** quote-stripping and truncation inside a body are declared in place — e.g. `"quoted_removed_chars": 4210` plus a `body_full` path, and `[truncated at 1000 tokens — get_message(id, view="body_full")]` markers *inside* the text. Rationale: stripped quotes can BE the evidence (inline replies interleaved with quoted text are common; parser limitations verified — github/email_reply_parser documents English-only "On...wrote" heuristics and brittle signature rules, https://github.com/github/email_reply_parser). Same for skeleton run-collapsing (§4.4) and for search scope ("scanned 200 most recent" in P1's `result_meta`).
4. **Freshness stamp:** every map/body carries fetch time (`source`), so a cached view can't masquerade as current (§45).
5. **Untrusted-content framing:** bodies, snippets, and derived summaries are user data, not instructions — delimit them structurally (this doc's shapes keep them in dedicated fields; Agent F owns the full story, §42).

---

## 6. Token economics

### 6.1 Verified reference numbers

- **Rule of thumb ~4 characters/token** (OpenAI help center, https://help.openai.com/en/articles/4936856-chatgpt-faq; consistent order of magnitude for Claude tokenizers — treat as ±30%).
- **New-content email bodies are small.** EnronSent corpus (Sent-folder messages cleaned of "as much non-human generated text as possible"): 96,107 messages, 13,810,266 words ⇒ **≈144 words ≈ 190–260 tokens average original body** (derived arithmetic from the corpus page, https://wstyler.ucsd.edu/enronsent/). Real bodies vary hugely (one-liners to pasted reports); treat 300–800 tokens as a planning range for a cleaned business email, and measure on the Loop 0 corpus.
- **Non-original lines are a large fraction even per single message.** Carvalho & Cohen 2004, 617-message corpus, 33,013 lines: 5,587 reply(quoted) lines (~17%) + 3,321 signature lines (~10%) ⇒ **~27% of lines are not new content**, and their line classifiers exceed 99% accuracy — stripping is tractable. https://www.cs.cmu.edu/~wcohen/postscript/email-2004.pdf
- **Quoted-reply inflation compounds along a thread (arithmetic, not measurement):** if each of n replies fully quotes its predecessors (default behavior of Gmail/Outlook-style clients), total transported body text grows O(n²): at ~150 words/message, a 100-message thread carries ~15k words of unique content but up to ~750k words (≈1M tokens) with full quoting — a **~50× inflation ceiling**. Real threads trim inconsistently; the honest claim is "unbounded multiple, commonly several ×," to be measured on the Loop 0 corpus (proposed metric: `unique_tokens / raw_tokens` per thread).
- **Host budget:** Claude Code warns at 10k and truncates MCP tool results at 25k tokens by default (§1.3). A single un-stripped long thread can exceed this on its own; **quote-stripped, map-first disclosure is what keeps MailWeave the author of its own truncation.**
- **Concise-by-default pays ~3×:** Anthropic's own example — 72 vs 206 tokens for concise vs detailed Slack responses (§1.3).

### 6.2 Verified tooling for the reduction pipeline

- **Quotation/signature stripping:** `mailgun/talon` (Python, Apache-2.0): `quotations.extract_from_plain`, `quotations.extract_from_html`, plus scikit-learn/SVM signature extraction trained on ENRON data — https://github.com/mailgun/talon. `github/email_reply_parser` (Ruby; built by GitHub to render email-reply comments; fragments = quoted/signature/hidden; documents its own English-pattern limitations) — https://github.com/github/email_reply_parser. Ports: `zapier/email-reply-parser` (Python, "A port of GitHub's Email Reply Parser library") — https://github.com/zapier/email-reply-parser; `crisp-oss/email-reply-parser` (Node, ~10 locales, states it processes ~1M inbound emails/day at Crisp) — https://github.com/crisp-oss/email-reply-parser.
- **HTML→text:** `html2text` (Python, originally by Aaron Swartz; converts HTML to "clean, easy-to-read plain ASCII text" that is valid Markdown) — https://github.com/Alir3z4/html2text. **License caution: GPLv3** — a permissively-licensed MailWeave should prefer alternatives (e.g., BeautifulSoup `get_text`, or Node `html-to-text` — latter unverified) or isolate the dependency. HTML email commonly multiplies size several-fold over its text content via markup/CSS/tracking (judgment; measure via `text_part_tokens / html_part_tokens` on the Loop 0 corpus — Gmail conveniently supplies both `text/plain` and `text/html` alternatives in `payload.parts` when senders include them).
- **Design consequence of parser fallibility:** strippers are heuristic (verified limitations above). Therefore stripping must be (a) lossy-but-declared (`quoted_removed_chars` + `body_full` path — §5.4 rule 3), and (b) *bypassable* — `view=body_full` and `view=raw` always exist. Never let a heuristic be the only path to the bytes.

### 6.3 Proposed budget ladder (starting points, to be tuned in Loop 2)

| View | Per-unit budget | Notes |
|---|---|---|
| Skeleton row | ≤ ~40 tokens | headers-derived; snippet only on hit/interesting rows |
| Snippet | ≤ ~25 tokens | Gmail's own `snippet` field (length undocumented; measure) |
| `body_clean` (default) | soft cap ~1,000 tokens | quote/sig-stripped, HTML→text; explicit in-text truncation marker + `body_full` path beyond cap |
| `body_full` | soft cap ~4,000 tokens | untrimmed text incl. quotes; truncation still explicit |
| `raw` | resource/file handoff only | never inline MIME into context |
| L1 evidence response (hits + structural floor + map) | target ≤ ~4,000 tokens | comfortably under the 10k host warning |
| Any single response | hard ceiling ~9,000 tokens | MailWeave truncates itself, explicitly, before the host does it silently |

Default depth policy: hits and structural floor at `body_clean`; window/scored picks at `body_clean`; everything else `stub`. Every cap violation produces a marker + affordance, never silent loss.

---

## 7. Tool-surface options

How the disclosure machinery is exposed to the agent.

### T1 — One high-level query tool with expansion parameters

`mail_query(query, expand="auto|window|reply_chain|segment", depth=..., budget=...)`; server runs the whole adaptive loop per call.

- **Pros:** single decision point; server controls budget precisely; matches Anthropic's consolidation advice for *workflows* (§1.3).
- **Cons:** parameter surface becomes a worse API than tools ("agents underuse exotic optional parameters" — judgment from observed Claude-class behavior; consistent with the writing-tools post's emphasis on clear, distinct purposes); conflates retrieval and disclosure so Loop 2/3 can't attribute wins; follow-ups ("open msg 64") are unnatural through a query interface.

### T2 — Small primitive set (search / map / expand / fetch)

```text
search_mail(query, ...)            → hits (+ mini-maps or map refs)   [Agent B/C owns internals]
thread_map(thread_id | map_id)     → the §4 skeleton
get_messages(ids | map_id+rows, view=stub|snippet|body_clean|body_full|raw)
get_attachment(message_id, part_id, mode=metadata|extract_text|save)
```

- **Pros:** matches how Claude-class agents actually operate — they reliably run search→peek→fetch loops *when each result names the next call* (judgment; the affordance blocks in §5 are designed exactly for this). Distinct purposes per tool (verified guidance); disclosure decisions are observable per call, which is what Loop 2 instrumentation needs; tool-count (4) is far under any realistic budget, especially namespaced (`mailweave_*`).
- **Cons:** more round trips than T1 on hard queries. Round-trip math: an extra call costs one network RT + one model turn (~1–3s, ~50–150 tokens of call+glue) and typically saves 5–20k tokens of unrequested thread — favorable whenever the agent would otherwise receive >~1k unneeded tokens (arithmetic; latency-sensitive hosts may weigh it differently). Risk: a lazy agent answers from L1 without expanding — mitigated by making insufficiency visible (stubs with tempting snippets) rather than by dumping more.

### T3 — Level parameter (L0 evidence map → L4 full thread)

A single `level` knob per call.

- **Pros:** legible ladder; easy to document.
- **Cons:** collapses the two axes of §2 — "L2" can't express "full body of msg 37 + stubs elsewhere," which is precisely the shape good disclosure wants. Levels work as *presets over* the two axes, not as the API itself.

### T4 — MCP resources for large bodies

Covered as Shape P3 (§5): verified protocol support, uneven host semantics; resources are application-driven and tool-returned links need not be listed.

### Recommendation (Agent D leaning — for synthesis, not decided)

**T2 primitives, with a `view` depth parameter (T3-as-preset) on `get_messages`, P2 map-carrier responses, and P3 resource links as an optional overlay for bulky artifacts (raw MIME, attachments) with in-band tool fallbacks always present.** `search_mail`'s response should embed enough (hits at `body_clean` + map) that easy queries finish in one call — preserving T1's one-shot ergonomics inside a T2 surface. This keeps the Adaptive Cost Invariant (cheap queries: 1 call), the Recoverability story (agent can always re-aim via the map), and Loop 2 attribution (every disclosure decision is a visible call).

---

## 8. How the agent learns what remains available

Channels, with verified support status:

1. **In-band result metadata (primary).** Coverage blocks, stub rows, `get_more` affordances, cursors (MCP list-pagination uses opaque cursors — same idiom works inside tool results). Works in *every* MCP client because tool results are the one channel the model is guaranteed to read. This is the recommended backbone.
2. **MCP resources + templates (secondary).** `resources/list`, `resources/read`, RFC 6570 templates (`mailweave://thread/{threadId}/message/{id}`), optional `subscribe` — all verified in spec (§1.2); Claude Code queries `resources/list` and honors `list_changed` (§1.3). But exposure to the *model* is host-dependent by design ("application-driven"), so resources may only ever be an additive convenience.
3. **Tool-returned `resource_link` blocks (bridge).** Verified in spec; carry `name`/`description`/`annotations`, so a link can *describe* withheld content compactly even for clients that will fetch it via a tool instead. Not guaranteed listable — treat as labels-with-URIs, not as the availability mechanism.
4. **Tool descriptions (static floor).** The tools' own descriptions state the disclosure model ("results are partial by default; every response says what was withheld and how to get it"), so even a fresh agent knows partiality is the contract. Judgment: description-taught behavior is weaker than result-taught behavior; rely on results.

**Recommendation:** both, with in-band as the invariant-bearing channel: the Partiality Invariant must be satisfiable by tool calls alone; resources may duplicate, never replace.

---

## 9. Recommended Loop 2 comparison (baseline + one query-aware variant)

Loop 2 (context §54) measures evidence recall vs context tokens across full-thread / fixed-window / structured-progressive arms, on the §38 position-sweep adversary. Concrete proposal:

**Common substrate for both MailWeave arms:** message-level search preserves hits (Loop 1 output); P2 map-carrier response shape; `body_clean` stripping with declared removals; budgets of §6.3. Equal *total token budget* per arm — the comparison is *where the budget is spent*, not who spends more.

- **Arm D-base (baseline): anchored fixed window.** Hits at `body_clean` + E1 window ±2 + full skeleton map (stubs elsewhere).
- **Arm D-var (query-aware variant): structural floor + scored fill.** Hits at `body_clean` + E2 reply-chain floor (parent + direct children) + remaining budget filled by E4 scoring over skeleton fields (sender/participant match, subject/snippet term overlap, temporal cues), each inclusion tagged with its mechanical reason; same map.
- **External baselines (Agent E's §36 set):** full-thread dump; fixed oldest-5 / newest-5 (status-quo reconstruction); message-hit-only (no expansion) as the floor.

**Measure per query (aligned with §34):** evidence recall (all gold messages at depth ≥ `body_clean` in ≤ K calls, K ∈ {1, 3}); context tokens per answered query; calls-to-answer; false "not found" rate; position-sweep variance (recall@37 vs @2 vs @99); partiality-transparency check (can a scripted probe recover `total`, `included`, and a working expand path from every response — should be 100% by construction for P2).

**Falsifiable hypotheses:** (H1) both MailWeave arms match full-dump recall at ≤25% of its tokens; (H2) D-var beats D-base on split-evidence and interleaved-subthread cases at equal budget; (H3) D-base suffices for single-locus cases (if H2 fails broadly, ship the simpler policy — per §55, features must answer measured failures).

---

## 10. Open questions for synthesis

1. **Who drives the loop — server policy or agent calls?** This doc leans agent-driven (T2) with rich affordances; Agent C's routing work leans server-side adaptivity. Where exactly is the seam? (Proposal: server adapts *retrieval*; agent drives *disclosure*; `search_mail` bundles the first disclosure step.)
2. **Map completeness vs multi-thread results:** P2 mandates a skeleton per thread — for a 10-thread result, is a mini-map (hit rows + counts + map ref) per thread acceptable, with full maps on demand? What's the mini-map's invariant-minimum content?
3. **Stateful `map_id`/cursors require server session state** (or stateless encoding of positions→ids). Which fits the chosen deployment model (Agent B's local vs hosted question)? Stateless re-derivation costs a repeat `threads.get`.
4. **Should `search_mail` auto-include the E2 structural floor, or is even that server-side cleverness Loop 2 must first justify?**
5. **Where does quote-stripping run** — at fetch time per message (latency on the hot path) or cached (then the §45 staleness rules apply to the cache)?
6. **Snippet provenance:** Gmail's `snippet` is Google-derived text. Is it "source" or "derived" under §26? (Proposal: treat as source-adjacent but label origin `gmail_snippet`; never synthesize our own text into a field named `snippet`.)
7. **Token accounting authority:** budgets are in tokens but the server sees characters. Standardize on chars/4 estimates, or ship a tokenizer? (Affects budget-equality fairness in Loop 2.)
8. **Attachment text extraction** (E6) — in-scope for the first build, or stub-only until a benchmark family demands extraction?
9. **How much of the partiality vocabulary belongs in `structuredContent` with an `outputSchema`** (verified supported, §1.2) vs plain text blocks? Structured output aids eval scripting; text may be read more reliably by some hosts. (Proposal: both, mirrored, per the spec's own backwards-compatibility advice.)
10. **Injection-safe framing of bodies** (with Agent F): do body fields need explicit `untrusted` wrappers/annotations in the response shapes, and do derived summaries inherit a taint flag?

## 11. What I could not verify

- **That `format=metadata` responses include `snippet`, `internalDate`, `sizeEstimate`, or attachment part metadata.** Docs say "message IDs, labels, and email headers" for the thread metadata format; the rest is expected from the resource model but undocumented — **Loop 0 smoke test required.** Same for `References`/`In-Reply-To` appearing under `metadataHeaders` selection (docs name To/From/Subject only as examples of the RFC 2822 headers carried).
- **Message ordering guarantees inside `threads.get` responses** (ascending `internalDate` is observed convention, not documented contract) — sort defensively.
- **Exact current Gmail quota unit values.** Two same-day fetches of Google's quota page consistently showed messages.get=20 / threads.get=40 / 6,000 units/user/min, but these differ from widely-cited older values (5/10/250-per-sec); the page may have changed or the cached read may be imperfect — re-verify at build time. Design conclusions don't hinge on the exact numbers.
- **Gmail `snippet` length** — no documented cap found; measure empirically.
- **A measured corpus-level figure for quoted-text inflation in real mailboxes.** The O(n²) argument is arithmetic; Carvalho & Cohen's ~17% reply-lines + ~10% signature-lines figure is per-message on a 2004-era 617-message corpus; EnronSent's cleaning confirms the problem's reality but publishes no removed-fraction statistic. Loop 0 should produce our own `unique_tokens/raw_tokens` numbers — they'd also make a strong README chart.
- **Host-by-host MCP resource UX** (which hosts surface resources/resource links to the model, and how). Verified only: the spec's "application-driven" stance, the tool-result `resource_link` type, and that Claude Code issues `resources/list` and exposes resource-reading tools. The claim "client support is uneven" is informed judgment.
- **Claude-class multi-call behavior claims** ("agents follow result-embedded affordances more reliably than description-buried parameters"; "agents underuse exotic optional parameters") — design judgment consistent with Anthropic's published guidance, not a cited measurement. Loop 2's calls-to-answer metric partially tests it.
- **The GitHub issue statuses (#296, #730, #76396, #82548)** — taken from MAILWEAVE_CONTEXT.md; independent re-verification is Agent A's deliverable.
- **`html-to-text` (Node) specifics** — named as a possible html2text alternative; not fetched. (html2text's GPLv3 license *is* verified.)

---

*Prepared by Agent D. All URLs fetched/searched 2026-08-30 unless noted. JSON shapes are illustrative options for ARCHITECTURE_DECISION.md, not an API commitment.*

---

## SCOPE CORRECTION ADDENDUM (2026-08-30)

**Added by:** research-revision agent, after `docs/SCOPE_CORRECTION.md` (authoritative).
**Nature of this addendum:** §§1–8 above (verified primitives, expansion strategies, thread maps, partiality shapes, token economics, tool surfaces) are untouched. What changes is §9's Loop-2 framing, which treated the query-aware policy as *a hypothesis to test before adopting*. Correction §6 settles that: fixed ±2 is a benchmark baseline only; the query-aware variant is the product policy. Nothing is edited, deleted or renumbered.

### 1. Status of this document's conclusions

**Stand unchanged, and several are explicitly adopted by the correction:**

- **Shape P2 (map-carrier) as the recommended response shape.** Correction §5: "every message in a touched thread can exist at least as a cheap stub, while selected evidence is expanded. This makes silent disappearance structurally much harder." That is §4.3 of this document, adopted verbatim in substance.
- **In-band affordances as the invariant-bearing channel** (§7, §8). Correction §7: "The path to more information must live directly in tool results, because that is the channel the model reliably sees." Adopted. P3 resource links remain an overlay only, exactly as §5's P3 verdict concluded.
- **The distinctions the response must carry** (§5's `role` / `role_reason` / depth vocabulary) are now enumerated as product requirements in correction §7: matched, contextual, expanded, stub, partial, how-much-more, how-to-get-more.
- **Recursive partiality** (§5.4 rule 3) — quote-stripping, truncation and run-collapsing are themselves partial views needing markers. Correction §7's "Partial data must never masquerade as complete data" is the same rule stated at the top level.
- **The no-fabricated-scores honesty rule** (§3-E4, §5.4 rule 2): mechanical reasons only.
- **All verified foundations in §1**, all token economics in §6, all tool-surface analysis in §7, and every "What I could not verify" item — including the Loop-0 smoke tests for `format=metadata` field coverage and `metadataHeaders` support for `References`/`In-Reply-To`, which are now blocking prerequisites rather than nice-to-haves, because the reply-chain floor is product scope.

**Superseded as product scope, still valid as baselines to measure against:**

| Original conclusion | Status now |
|---|---|
| §3-E1: fixed ±N window is the "correct **Loop 2 baseline**… wrong resting point," N=2 default | **Confirmed as a baseline and *only* a baseline.** Correction §6 names it explicitly: "Do not treat fixed ±/-2 as MailWeave's final progressive disclosure policy. Keep it as a simple baseline." |
| §9: Arm D-var (structural floor + query-scored fill) as "the Loop 2 variant to test against E1" | **Superseded as a scope gate: D-var is the product policy.** Correction §6: "implement and review the actual query-aware policy against it: reply-chain + query-scored structural selection using participant, subject/snippet and temporal signals under the same context budget." D-base remains the measurement arm. |
| §9 hypothesis H3: "if H2 fails broadly, **ship the simpler policy** — per §55, features must answer measured failures" | **Genuinely invalidated as a scope decision.** A null result no longer authorises shipping fixed ±2 as the product policy. H3 survives as a *finding to report and to tune with*, and as a genuine falsifier of the "related ≠ adjacent" claim — which must then be stated honestly in the README rather than converted into a scope reduction. |
| §3-E5 multi-thread verdict: "expose as an explicit affordance… **never as automatic inclusion**" | **Softened.** Correction §5 includes "multi-thread relationships where appropriate" in required structural capability. The fan-out caution, the thread-count budget and the stubs-first rule all survive as design constraints on a capability that must now exist. |
| §3-E2/E3 verdicts (reply-chain "highest value-per-cost"; temporal segments "cheap add-on") | **Promoted from recommendations to required signals.** Correction §5 names reply relationships, participant relationships, temporal relationships, thread position and subject/snippet relevance. |
| §4.5: derived summaries are "a later experiment (Loop 5+)" | **Stands.** Nothing in the correction requires summarisation, and §4.5's rules (labelled derived, never replacing rows, inherits untrusted status, never silently on the hot path) become more important once internal model calls are permitted (correction §8). |

**Genuinely invalidated:** H3's scope clause only. Everything else in this document is either unchanged or promoted.

### 2. Baseline vs product requirement

| Disclosure capability | Baseline (measure against) | Complete-product requirement |
|---|---|---|
| Selection policy (Axis S) | **E1 fixed ±2**, anchored on the hit | **E2 reply-chain structural floor + E4 query-scored fill** under the same context budget (correction §6), with E3 temporal segmentation and E5 multi-thread available where the query warrants |
| Depth policy (Axis D) | Hits + floor at `body_clean`; everything else `stub` | Unchanged — this is already the product shape |
| Response shape | P1 coverage-header envelope (comparison arm) | **P2 map-carrier** (correction §5, §7) |
| Partiality signalling | "N omitted" counts | Every message present at least as a stub; per-message `role` + mechanical reason; explicit `complete` flag; concrete expansion call adjacent to every count (§5.4) |
| Disclosure depth (number of levels) | One level + full-fetch escape hatch | **Constrained, not free** — see T-CD1 |
| External comparison arms | Full-thread dump; oldest-5/newest-5 status-quo reconstruction; message-hit-only floor | Unchanged, **plus** the "strong agent + honest primitive tools" arm required by `VERIFIED_RESEARCH` |
| Cross-call state | — | Server-minted handles as ordinary tool arguments (correction §14); `map_id` is exactly this pattern |
| Disclosure traces | — | IDs / roles / reasons / scores / token counts only on the real mailbox; **no full bodies** (Appendix A.3) |

### 3. Facts that survive untouched

- **`threads.get?format=metadata` with `metadataHeaders[]`** returns every message's IDs/labels/headers in one call — the thread-map primitive. **Quota cost is per method, not per format**: `threads.get` costs 40 units whether metadata or full. The map wins tokens, bandwidth and latency, never quota.
- **Gmail threads are a flat set ordered by `internalDate`; the reply tree must be reconstructed client-side** from `Message-ID`/`In-Reply-To`/`References` (JWZ / IMAP REFERENCES). Gmail's own thread membership is looser than RFC threading, so orphans are expected and must be labelled (`"linkage": "date-adjacent (no RFC reply headers)"`).
- **Claude Code caps MCP tool responses at 25,000 tokens by default and warns at 10,000** (`MAX_MCP_OUTPUT_TOKENS`; per-tool raise via `_meta["anthropic/maxResultSizeChars"]`, ≤500,000 chars). A full 100-message thread dump can silently hit the host cap — **MailWeave must author its own truncation before the host does it invisibly.** This is the single most operationally important number in the document.
- **Token economics:** ~4 chars/token rule of thumb; EnronSent-derived ≈144 words ≈190–260 tokens average original body, 300–800 tokens planning range for a cleaned business email; Carvalho & Cohen 2004: ~17% quoted lines + ~10% signature lines ⇒ ~27% non-original, with >99%-accurate line classifiers; quoted-reply inflation grows O(n²) with an inflation *ceiling* around 50× on a 100-message thread (arithmetic, not measurement). A disciplined map row ≈30–50 tokens ⇒ 100-message map ≈3,000–5,000 tokens for total situational awareness.
- **Stripping is heuristic and must be declared and bypassable**: `talon` (Apache-2.0), `github/email_reply_parser` (English-pattern limits documented), `crisp-oss/email-reply-parser` (Node, ~10 locales). **`html2text` is GPLv3** — isolate or avoid for a permissively-licensed server.
- **MCP tool results support `structuredContent` + `outputSchema`, `resource_link` and embedded `resource` blocks; annotations are exactly `audience`/`priority`/`lastModified`.** Resources are "application-driven" and tool-returned resource links are not guaranteed to appear in `resources/list` — which is why P3 can never carry the Partiality Invariant alone.
- **Anthropic tool-design guidance** (verified): consolidate rather than proliferate; implement pagination/range-selection/filtering/truncation with sensible defaults; a `response_format` enum bought ~3× (72 vs 206 tokens) in their Slack example; return high-signal fields, not UUID soup.

### 4. Unresolved tensions — stated, not smoothed

**T-CD1 — The large-thread compression ladder is itself a multi-level disclosure hierarchy, and the only controlled study we have says depth hurts.**

`VERIFIED_RESEARCH` §8.1 (arXiv 2607.17598, verified): "A second, deeper routing level never helps and sometimes breaks accuracy outright, so one level is enough." §4.4 of this document proposes, for very large threads, a ladder of **segment map → row map → snippet → body** — three or four navigational levels before evidence. Correction §7 requires progressive disclosure; it does not require depth, and the evidence argues against it.

This is a real conflict and both sides must be honoured:
- Keep the compression ladder, because a 500-message map at ~20k tokens is genuinely unusable against a 25k host cap — the ladder answers a hard constraint, not a preference.
- **But treat depth as a budgeted, measured parameter, not a design flourish.** Default to one navigational level (the map) plus a direct full-fetch escape; introduce the segment level only above the measured thread size where the flat map breaks the token budget, and measure accuracy at that boundary rather than assuming the extra level is harmless.
- **Instrument levels-traversed-to-answer** as a first-class metric. If deep threads show accuracy degradation at the segment level, that is a finding to publish, not to hide.
- Note the domain caveat honestly in both directions: 2607.17598 measured books, not email; its finding is hypothesis-shaping, not conclusive. It is still the best evidence in existence and should not be waved away because it is inconvenient.

**T-CD2 — Query-aware disclosure is now the shipped policy, and its documented failure mode is that it hides disconfirming evidence.**

§3-E4 records this plainly: "*Self-confirmation bias:* expanding only query-similar messages can hide the *objection* that reverses the decision," and "*Wording overfit:* query-term scoring re-creates lexical search's paraphrase blindness inside the thread." When E4 was a hypothesis to be tested, these were risks. Correction §6 makes E4 the product policy, so they are now **shipped risks on the default path**, and the mitigation must be mandatory rather than advisory:

- The **E2 reply-chain structural floor must be non-optional beneath the scored picks** — it is the only mechanism that can surface a message that disagrees with the query's framing.
- The benchmark needs an adversarial family this document does not currently specify: a thread where the *scored-highest* messages support one answer and a low-scoring reply reverses it. "Decision reversed later in the thread" is the canonical case and it is exactly what a query-scored selector will miss.
- Because every non-selected message still appears as a stub with a snippet under P2, the damage is bounded — the reversing message is *visible*, just not expanded. That is the map-carrier shape earning its cost, and it is the honest defence. It is not a guarantee that the agent will notice.

**T-CD3 — Beating fixed ±2 on paraphrase cases may require the semantic budget, which couples disclosure to retrieval's latency.**

§3-E4 notes that scoring over skeleton fields (sender / subject / snippet overlap / temporal proximity) is "microseconds and token-free," but also that this re-creates lexical blindness: the confirmation "Done — Oct 17 it is" shares no tokens with "postpone the launch." If query-aware selection must be *semantic* to beat E1 on the cases the correction cares about, then disclosure inherits the local-embedding cost analysed in `RETRIEVAL_OPTIONS`'s addendum (§5, T-RO2) — model load, per-text latency, and a cost that scales with thread size. A 100-message thread scored semantically is a second-scale operation on a laptop CPU.

Unresolved: whether cheap mechanical scoring is *sufficient* for the product's headline cases, or whether within-thread scoring must escalate to embeddings too — and if so, under what trigger, given that the trigger problem is itself unresolved (`ROUTING_OPTIONS` T-RC2). This should be a pre-registered Loop-2 measurement: **mechanical-scored D-var vs embedding-scored D-var vs D-base, at equal token budget.**

### 5. What architecture must now decide that this document treated as deferred

1. **The exact query-aware selection policy** — which signals, in what order, with what weights, and the mechanical reason string each produces. Correction §6 names the signal families (participant, subject/snippet, temporal, reply-chain); the composition rule in §3 ("E2 floor → budget filled by E4 → E3/E5/E6 as triggered") is the starting design and now needs to be pinned down as an API contract.
2. **Whether within-thread scoring is mechanical, semantic, or escalating** (T-CD3), and its budget.
3. **Multi-thread (E5) as required capability**: the thread-count budget, the sibling-discovery rule (normalised subject / participant overlap / explicit forwards / additional search hits), and the mini-map minimum content for a multi-thread result (original open question 2, now unavoidable rather than optional).
4. **Depth budget and the flat-map→segment-map boundary** (T-CD1), plus levels-traversed instrumentation.
5. **`map_id` under a stateless protocol** (original open question 3): correction §14 settles the *pattern* — server-minted handles passed as ordinary tool arguments — but not whether positions→ids are encoded in the handle or re-derived by a repeat `threads.get`.
6. **Structured output contract** (original open question 9): how much partiality vocabulary lives in `structuredContent` with an `outputSchema` versus mirrored text. Eval scripting wants structured; some hosts read text more reliably. The spec's backwards-compatibility advice supports mirroring both.
7. **Where quote-stripping runs** (original open question 5) — hot path vs cached; if cached, the staleness rules apply to the cache.
8. **Disclosure trace contents under A.3**: record per-response `{message_id, role, role_reason, depth_shown, tokens}` and the map's shape — **never body text** — on real-mailbox runs. Seeded-account runs may carry full content. This makes Loop-2 attribution possible without violating the privacy constraint, and it should be designed now rather than retrofitted.
9. **Attachment extraction (E6)** — still legitimately deferrable; the correction does not require it. Stub-first remains the default.
