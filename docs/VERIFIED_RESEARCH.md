# VERIFIED_RESEARCH.md — Independent Source Re-Verification for MailWeave

**Verification date:** 2026-08-30 (all statuses, quotes, and probe results are as of this date)
**Verifier:** Agent A (source verification / prior-art research)
**Method:** Live web fetches (GitHub issue pages, GitHub REST API where it responded, Google/Anthropic/MCP documentation, arXiv, web search) plus one minimal, read-only, metadata-only probe of the production Claude Gmail connector attached to this session. No claim below is presented as fact unless it was directly observed today; everything else is marked **COULD NOT VERIFY**.

**Verdict legend**
- **VERIFIED** — observed directly today; matches the context doc.
- **VERIFIED, WITH DELTA** — observed directly today; context doc needs a correction or addition.
- **COULD NOT VERIFY** — attempted; what was tried is recorded.

---

## 0. Headline findings (read this first)

1. **THE BUG IS NOT FIXED — and it is now vendor-documented.** The production Claude Gmail connector's own `search_threads` tool description (read from the live tool schema in this session, 2026-08-30) now says, verbatim:
   > "IMPORTANT: search results are previews showing only the ~5 OLDEST messages of each thread; any newer messages in a thread are NOT included and no truncation marker is shown. Never answer questions about recent, latest, or unread email from these previews alone — call get_thread first to read each relevant thread in full."

   The failure mode the context doc is built on is no longer just a set of user bug reports: the vendor has acknowledged the ~5-oldest cap and the absence of a truncation marker in the tool description itself, and the prescribed mitigation is instructional ("always call get_thread"), not representational. The response payload still carries no total-count field and no partiality marker.

2. **Empirically reproduced today** on a real mailbox (minimal metadata-only probe, no bodies or subjects read): a 7-message thread active the same morning was returned by `search_threads` as a 5-message preview containing exactly the 5 oldest messages, silently omitting the 2 newest (both from 2026-08-30); `get_thread` on the same thread ID returned all 7. Details in §3.4.

3. **The four registry issues check out** (statuses re-confirmed; reproduction claims match the issue texts), and the hunt surfaced **five additional claude-ai-mcp/claude-code issues the context doc missed** (#239, #203, #349, #47024, #194, plus claude-code #48713) — including one (#239) that reports `get_thread` **itself** truncating/misbehaving on 10+-message threads, which weakens any design that treats `get_thread` as an always-reliable fallback.

4. **Directly relevant new prior art exists (July 2026):** arXiv 2607.17598, "Is Progressive Disclosure All You Need for Long-Context Agents?" — the first controlled study of progressive disclosure for agents. Findings both support and constrain the MailWeave thesis (§8.1).

5. **The MCP spec has moved substantially** (current revision **2026-07-28**): the protocol is now stateless, **Sampling is deprecated**, tool results have no protocol-level pagination, and cross-call state is expected to be carried by "explicit, server-minted handles passed as ordinary tool arguments" — which is architecturally load-bearing for MailWeave's progressive-disclosure tool design (§7).

---

## 1. GitHub issues in the section-65 registry

### 1.1 anthropics/claude-ai-mcp #296 — **VERIFIED, WITH DELTA (comments unread)**
- URL: https://github.com/anthropics/claude-ai-mcp/issues/296 (also read via https://api.github.com/repos/anthropics/claude-ai-mcp/issues/296)
- **Context doc claims:** title about truncated `messages[]`; opened May 15, 2026; rfc822msgid repro; `newer_than:1d` repro; `get_thread` returns the full 11-message thread; closed as not planned.
- **Verified today:** Title "[BUG] Gmail connector: search_threads returns truncated messages[] per thread, silently omitting matched messages in long threads". State: **closed**, `state_reason: not_planned`. Created 2026-05-15T03:59:54Z; closed 2026-05-18T16:00:39Z (3 days after filing). Label: bug. Author association: NONE (outside reporter). 2 comments exist. Body confirms all context-doc reproduction claims: exact `rfc822msgid:` search returned the correct thread with the target absent from `messages[]`; `newer_than:1d` returned a thread whose visible preview contained only April messages (older than the filter window); `get_thread(threadId)` returned the complete 11-message list; ~5 messages, oldest-first; reporter's stated impact is that agents "incorrectly conclude emails don't exist in Gmail."
- **Delta:** closed only 3 days after opening; **the content of the 2 comments (and who closed it, and why) could not be read** — see §10. The context doc should not imply anything about the closure rationale beyond "closed as not planned."

### 1.2 anthropics/claude-ai-mcp #730 — **VERIFIED, WITH DELTA (extra detail)**
- URL: https://github.com/anthropics/claude-ai-mcp/issues/730
- **Context doc claims:** opened July 30, 2026; 20+-message thread over ~16 months; different queries repeatedly return the same stale five-message snapshot; open.
- **Verified today:** Title "[BUG] Gmail search_threads returns stale, capped 5-message snapshot for long threads". **Open.** Opened July 30, 2026. Label: bug. Body matches: 20+ messages spanning ~16 months; identical 5-message snapshot for every query, including a sender-address query where that sender appears only in later messages; snapshot frozen ~2 months out of date; most recent same-day message never surfaced. No comments visible.
- **Delta (additions the context doc lacks):** (a) the reporter's secondary observation that date-bounded *Sent* queries stalled ~3 days behind while Inbox queries were current; (b) the issue explicitly distinguishes itself from #47024 (hard "Internal error") and #349 (sender-specific empty results) and hypothesizes a shared thread-state-caching root cause.

### 1.3 anthropics/claude-code #76396 — **VERIFIED, WITH DELTA (labels + nuance)**
- URL: https://github.com/anthropics/claude-code/issues/76396
- **Context doc claims:** opened July 10, 2026; active 14-message thread; `search_threads` returns an incomplete early slice; `get_thread` full and current; labeled `external`.
- **Verified today:** Title "Gmail MCP search_threads returns stale/incomplete results for long-running threads; get_thread by ID is accurate". **Open.** Opened July 10, 2026. Labels: **bug, external, stale** (the `stale` inactivity label is new since the context doc). Body matches: 14-message thread over ~2.5 weeks; multiple query variants (`in:anywhere`, `includeTrash:true`, `newer_than:3d`, etc.) capped the thread at its first 5 messages; `get_thread` returned all 14 instantly. No comments visible.
- **Delta (important nuance):** the reporter also found that **a fresh self-test email was indexed by `search_threads` within seconds** — i.e., in this account the staleness was specific to long/deep threads, not the mailbox as a whole. This cuts against a blanket "search index lags by days" interpretation and supports treating Problem A (representation) and Problem B (freshness) separately, exactly as the context doc's §4 insists.

### 1.4 anthropics/claude-code #82548 — **VERIFIED**
- URL: https://github.com/anthropics/claude-code/issues/82548
- **Context doc claims:** opened July 30, 2026; search lags mailbox by hours/days; `get_message`/`get_thread` by ID work; stale thread views inside search results.
- **Verified today:** Title "Gmail connector: search_threads index lags days behind mailbox; search results embed stale thread views". **Open**, no labels, no comments visible. Body matches and is precise: a July 27 message still unsearchable on July 30 (3+ days) under `from:`, keyword, and `in:anywhere` queries while `get_message` by ID returned it fully; separately, a 24-message thread rendered in every search result as 5 messages ending 8 days earlier; reporter ruled out auth/delivery/client causes; the only workaround stated is "locate thread via older terms, then always use get_thread."
- No Anthropic or Google response is visible on any of the four issues.

### 1.5 Registry accuracy note
All four issue numbers, repos, opening dates, statuses, and reproduction summaries in context-doc §3, §4, and §65 are accurate as of today. The only correction needed anywhere in those sections is additive (labels, extra observations, comment-content unknown).

---

## 2. anthropics/claude-ai-mcp repository purpose — **VERIFIED**
- URL: https://github.com/anthropics/claude-ai-mcp
- **Verified today:** README describes the repo as "the communication hub for MCP (Model Context Protocol) integration in Claude.ai." Root contents: `.github/ISSUE_TEMPLATE/`, `drafts/`, `LICENSE`, `README.md`, `SECURITY.md`. **No server implementation code** (no src/, no .ts/.py). ~340 stars, 146 open issues, 18 commits. Scope statement covers MCP integrations in Claude.ai (sessions, tools/resources, OAuth) and explicitly excludes the MCP spec/SDKs.
- The context doc's claim discipline in §5 ("no public implementation repo for the hosted server was found; do not overstate") remains the correct posture. Nothing found today contradicts it.

---

## 3. Google's hosted Gmail MCP — **VERIFIED, WITH IMPORTANT DELTAS**

### 3.1 Reference page — **VERIFIED**
- URL: https://developers.google.com/workspace/gmail/api/reference/mcp
- **Verified today:** Endpoint documented verbatim as "The Gmail MCP API MCP server has the following global MCP endpoints: https://gmailmcp.googleapis.com/mcp/v1". Status: **still Developer Preview** ("Available as part of the Google Workspace Developer Preview Program"). Page "Last updated 2026-07-21 UTC". Documented tool list (10 tools): create_draft, get_message, get_thread, label_message, label_thread, list_drafts, list_labels, search_threads, unlabel_message, unlabel_thread. **No statement anywhere about response caps, thread previews, or limits.** No changelog on the page.

### 3.2 search_threads tool page — **VERIFIED, WITH DELTA**
- URL: https://developers.google.com/workspace/gmail/api/reference/mcp/tools_list/search_threads
- **Verified today:** Parameters: `pageSize` (default 20, max 50), `pageToken`, `query` (Gmail syntax), `includeTrash` (default false), `view` (default `THREAD_VIEW_MINIMAL`). Response: `threads[]`, each with `messages[]` described only as "A list of messages in the thread, ordered chronologically." **The documented cap question is answered: Google's public docs do NOT document any per-thread messages[] cap.** The ~5-message truncation is entirely undocumented on Google's side (it surfaces only in the deployed tool description — §3.4). Pagination is thread-level only (`nextPageToken`); there is no pagination of messages within a thread. No staleness/freshness note. Last updated 2026-07-21; still Developer Preview.
- **Delta the context doc missed:** the `view` enum is `THREAD_VIEW_UNSPECIFIED` (maps to MINIMAL), `THREAD_VIEW_MINIMAL` ("Returns id, snippet, subject, from, to, cc, date, labelIds"), `THREAD_VIEW_METADATA_ONLY`. **There is no full/body view for search results at all** — search previews are snippet-level by design, and "ordered chronologically" is consistent with the observed oldest-first truncation window.

### 3.3 Gmail API release notes — **VERIFIED (no fix announced)**
- URL: https://developers.google.com/workspace/gmail/release-notes
- **Verified today:** The Gmail MCP server entered Developer Preview **April 22, 2026**. The 2026 entries after that are: May 1 (API quota re-tiering — quota-unit changes for `messages.get`, `threads.get`, etc.), May 13 and June 24 (Postmaster Tools v2). **No release note between April 22 and today mentions any MCP behavior change, cap change, or fix.** There is no documented evidence that the truncation/staleness behavior was ever changed.

### 3.4 Live behavior of the production Claude Gmail connector — **VERIFIED (bug present today)**
Observed directly in this session (the Gmail connector attached to this Cowork session), 2026-08-30. Privacy handling: the probe used `THREAD_VIEW_METADATA_ONLY` / `METADATA_ONLY` formats exclusively (no bodies, no subjects, no snippets read); no personal content, addresses, or subjects are reproduced here.

1. **The deployed `search_threads` tool description explicitly documents the bug** (quoted in §0.1): previews are "the ~5 OLDEST messages of each thread", newer messages "NOT included", "no truncation marker is shown". The deployed `get_thread` description recommends `PLAIN_TEXT` format "to prevent context exhaustion" and documents formats MINIMAL / FULL_CONTENT / METADATA_ONLY / PLAIN_TEXT / RAW, with PLAIN_TEXT converting HTML to plain text/markdown when no plain-text part exists.
2. **Reproduction:** a scan of 50 thread previews showed no preview with >5 messages, with many at exactly 5. For one thread (ID prefix `1a0390…`) the search preview contained 5 messages (oldest-first, 2026-08-25 → 2026-08-29); `get_thread` with `METADATA_ONLY` returned **7 messages**, the two newest from the morning of 2026-08-30 — silently absent from the search preview. The preview was exactly the 5 oldest. `get_thread` was complete and current (newest message ~4h old at probe time).
3. **Partiality invariant violation confirmed in the payload:** the search response carries no per-thread total-message count, no truncation flag, and no indication which message matched the query.
4. **Suggestive (not conclusive) staleness signal:** in a recency-ordered result list, the thread with the newest *true* activity (Aug 30) ranked below a thread whose newest activity was Aug 29 — consistent with #82548's "stale recency ordering" claim (ordering computed from the capped preview), but a 2-call probe cannot establish this; the hours-to-days index lag of #82548 was **not** reproduced (same-day threads did appear in results).
5. **Tool-surface delta:** the deployed connector exposes ~28 Gmail tools (including reply, forward, send_message, trash/spam operations, update_message_labels, sensitive-label tools) versus the 10 tools on Google's public MCP docs page; schema internals ("Request message for SearchThreads RPC", `x-google-enum-descriptions`) indicate a Google-protobuf-derived surface. The deployed server has evolved beyond the public docs; the public docs (last updated 2026-07-21) lag the deployed surface. Claim discipline: this does not establish who operates which layer — only that doc and deployment diverge.

**Net for the thesis:** the representation failure is real, current, reproducible, vendor-acknowledged, and mitigated only by an instruction to agents to distrust the preview and re-fetch full threads — i.e., the vendor's own workaround is "always consider dumping the full thread", which is precisely the context-inefficient baseline (Baseline B) MailWeave proposes to beat.

---

## 4. Gmail REST primitives — **VERIFIED, WITH USEFUL ADDITIONS**

### 4.1 users.messages.list — **VERIFIED**
- URL: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list
- **Verified today:** `q` "Supports the same query format as the Gmail search box. For example, `from:someuser@example.com rfc822msgid:<somemsgid@example.com> is:unread`." Params: `maxResults` (default 100, max 500), `pageToken`, `labelIds[]`, `includeSpamTrash`. Response: `messages[]` where "each message resource contains only an `id` and a `threadId`", plus `nextPageToken` and `resultSizeEstimate`.
- **Additions the context doc missed:** (a) **`q` cannot be used with the `gmail.metadata` scope** — a real constraint on any "minimum-scope, metadata-only" privacy architecture: message-level search requires at least `gmail.readonly`; (b) `resultSizeEstimate` is an estimate, not a count (relevant to honest sufficiency signals); (c) default page size is 100.

### 4.2 users.messages.get — **VERIFIED (enum values partially, via adjacent docs)**
- URL: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/get
- **Verified today:** `format` enum parameter exists; `metadataHeaders` "When given and format is `METADATA`, only include headers specified"; `id` "usually retrieved using `messages.list`". The get page itself did not inline the enum values; the threads.get page (below) documents full/metadata/minimal verbatim and the sync guide instructs "Set format to `FULL` or `RAW`" — jointly corroborating the full/metadata/minimal/raw set the context doc assumes.

### 4.3 users.threads.get — **VERIFIED**
- URL: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.threads/get
- **Verified today:** `format=full` "Returns the full email message data with body content parsed in the `payload` field"; `metadata` "Returns only email message IDs, labels, and email headers"; `minimal` "Returns only email message IDs and labels"; plus `metadataHeaders[]`. The REST docs do not state a per-thread message cap for threads.get; my live probe's REST-backed `get_thread` returned a complete 7/7. (But see issue #239, §6.1, before treating "get_thread always complete" as an invariant at the MCP layer.)

### 4.4 users.history.list + sync guide — **VERIFIED**
- URLs: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.history/list and https://developers.google.com/workspace/gmail/api/guides/sync
- **Verified today:** `startHistoryId` (required), `historyTypes` (messageAdded, messageDeleted, labelAdded, labelRemoved), `labelId`, `maxResults` (default 100, max 500). "Supplying an invalid or out of date `startHistoryId` typically returns an `HTTP 404` error code" → "your client must perform a full sync." Retention: "History records are typically available for at least one week and often longer… may be significantly less and records may sometimes be unavailable in rare cases" (the reference page adds a historyId "may be valid for only a few hours" in rare circumstances). Push: "You can also use push notifications to trigger partial synchronization in real-time" (users.watch + Cloud Pub/Sub, separate guide).
- **Addition:** the May 1, 2026 quota re-tiering changed quota units for `messages.get`/`threads.get` etc. — cost modeling for any MailWeave design that fans out per-message `get` calls should use current quota tables, not pre-May assumptions.

---

## 5. Prior-art Gmail/Workspace MCP repos

### 5.1 taylorwilsdon/google_workspace_mcp — **VERIFIED, WITH CLARIFICATION**
- URL: https://github.com/taylorwilsdon/google_workspace_mcp
- **Verified today:** MIT ("no CLA, no dual licensing"), ~3.0k stars / 944 forks, 2,685 commits (actively maintained; exact last-commit date not shown on the rendered page). Gmail tools as claimed: `search_gmail_messages`, `get_gmail_message_content`, `get_gmail_messages_content_batch`, `get_gmail_thread_content`, plus send/draft/labels/filters/attachments (~15 Gmail tools). Search is **message-level** (Gmail `q`), confirming the context doc's point that message-level search avoids the fixed-thread-preview trap.
- **Clarification:** its README's "three progressive tool tiers (core/extended/complete)" is about **which tools are registered**, not progressive disclosure of retrieved content. **No evidence of evidence-preserving or progressive content retrieval.** Deployment: stdio, streamable HTTP, Docker, OAuth 2.1 multi-user, stateless container mode, service accounts.

### 5.2 Maheidem/gmail-mcp — **VERIFIED**
- URL: https://github.com/Maheidem/gmail-mcp
- **Verified today:** MIT; 0 stars / 2 forks; read-only ("Only `gmail.readonly` scope is used — this server cannot send or modify emails"); tools exactly `search_emails`, `get_email`, `download_attachment`. No thread-handling documentation; no progressive/adaptive features.

### 5.3 CWBinder/gmail-mcp — **VERIFIED**
- URL: https://github.com/CWBinder/gmail-mcp
- **Verified today:** MIT; 2 stars / 1 fork; "A minimal MCP server for Gmail with full read and write access"; tools `gmail_list_messages`, `gmail_read_message`, `gmail_read_thread`, `gmail_send_message`, `gmail_reply_to_message`, `gmail_send_message_with_attachment`, `gmail_get_profile`. Gmail `q` search; no truncation/PD/adaptive features documented.

### 5.4 Ayush-k-Shukla/gmail-mcp-server — **VERIFIED, WITH DELTA (license)**
- URL: https://github.com/Ayush-k-Shukla/gmail-mcp-server
- **Verified today:** "Implementation of a Gmail MCP server with RAG support"; 6 stars / 3 forks; 14 commits. Tools include `global-search-emails`, `vector-search-emails`, `summarize-top-k-emails`, `get-unread-emails`, plus send/labels/delete. Semantic path: embeddings via **xenova** (local Transformers.js), indexed in **ChromaDB**; emails fetched by the search/summarize/unread tools are auto-indexed, and `vector-search-emails` queries Chroma. Confirms "Gmail MCP + embeddings" is existing prior art. No progressive-disclosure or evidence-preservation concepts.
- **Delta:** **no license file was visible** — the context doc lists it among prior art without a license claim, but any code reuse would require confirming licensing first. Also note its index is populated only by prior tool calls (a partial, usage-driven index) — an instructive stale-index cautionary example for context-doc §45.

### 5.5 Whether ANY prior-art repo implements evidence-preserving or progressive retrieval
**None of the four registry repos (nor GongRzhe, §8.4) documents anything resembling evidence-preserving retrieval, explicit partiality metadata, query-conditioned disclosure, or adaptive retrieval escalation.** The closest adjacent ideas are message-level search (taylorwilsdon, GongRzhe — avoids the trap but has no partiality semantics) and opt-in vector search (Ayush-k-Shukla). MailWeave's specific contribution remains unclaimed territory in the Gmail-MCP ecosystem as of today.

---

## 6. Additional claude-ai-mcp / claude-code ecosystem issues the context doc missed — **NEW, ALL VERIFIED TODAY**

### 6.1 claude-ai-mcp #239 — get_thread itself misbehaves on long threads ⚠️
- URL: https://github.com/anthropics/claude-ai-mcp/issues/239 — **closed as not planned**; opened April 28, 2026; label bug.
- Claim: `get_thread` with `messageFormat=FULL_CONTENT` on threads with **10+ messages** returns a truncated response or a single malformed message; new replies invisible. Proposed fix in the issue: expose `users.messages.list`/`users.messages.get` as MCP tools (i.e., message-level access — the same direction as MailWeave).
- **Impact:** the context doc (and issues #296/#76396/#82548, and my probe on a 7-message thread) treat `get_thread` as the reliable ground truth. #239 says that at least in April 2026 it was not reliable for 10+-message threads. My probe cannot arbitrate (7 < 10). **MailWeave's evaluation must include get_thread-completeness checks on long threads rather than assuming the fallback is sound.**

### 6.2 claude-ai-mcp #203 — HTML bodies inaccessible — **open**
- URL: https://github.com/anthropics/claude-ai-mcp/issues/203 — opened April 21, 2026; bug.
- `get_thread` FULL_CONTENT returned only `text/plain` of `multipart/alternative` mail; newsletter content living in `text/html` silently dropped; "The tool succeeds without error, creating a silent failure mode." Proposes a `bodyFormat` (text|html|raw) parameter.
- **Today's deployed schema** documents FULL_CONTENT as returning `html_body` and PLAIN_TEXT as converting HTML→markdown when plain text is absent — suggesting this axis has since improved at the schema level (unverified behaviorally; issue remains open). Relevant to MailWeave as a second instance of the same genus: *silent representation-layer information destruction*.

### 6.3 claude-ai-mcp #349 — sender-specific silent search misses — **closed as not planned (duplicate)**
- URL: https://github.com/anthropics/claude-ai-mcp/issues/349 — opened May 23, 2026; labels bug, duplicate.
- `search_threads` returned empty for a specific sender's post-April-2026 mail that was verifiably present and authenticated in the mailbox. A third failure genus: silent per-sender search false negatives.

### 6.4 claude-code #47024 — search_threads hard failure — **closed as not planned**
- URL: https://github.com/anthropics/claude-code/issues/47024 — opened April 12, 2026; labels area:cowork, area:mcp, bug, platform:macos.
- 100% "Internal error encountered" from `search_threads` since April 9, 2026 while get_thread/list_drafts worked; reporter's workaround (list_drafts → get_thread) "cannot discover new inbound emails." No visible Anthropic response.

### 6.5 claude-ai-mcp #194 — bodies stopped returning ~April 17, 2026 — **closed as not planned**
- URL: https://github.com/anthropics/claude-ai-mcp/issues/194 — opened April 19, 2026; bug.
- `get_thread` FULL_CONTENT stopped returning `plaintextBody` for specific emails; a scheduled workflow degraded to parsing ~200-char snippets. No visible response.

### 6.6 claude-code #48713 — the connector REMOVED message-level tools — **closed as not planned** (timeline evidence)
- URL: https://github.com/anthropics/claude-code/issues/48713 — opened April 15, 2026; labels area:mcp, bug, has repro, regression, stale.
- Reporter states the connector **previously exposed `gmail_read_message` and `gmail_search_messages`**, which were **replaced by `get_thread` and `search_threads`** (and that at that moment get_thread returned metadata only). Closed as not planned.
- **Impact:** strong narrative/timeline evidence (from a user report, not vendor confirmation) that the truncation era began with an abstraction migration *away from message-level access toward thread previews* in ~April 2026. MailWeave's core proposal — preserve message-level search hits — is, in part, a restoration of the abstraction that was removed.

**Pattern across all Gmail issues checked (8 total):** every one was either closed "not planned" without a visible staff explanation or remains open without a visible staff response; none links a fix PR. The vendor-side change that *did* happen is the warning text now embedded in the deployed `search_threads` description (§3.4.1).

---

## 7. MCP specification — **VERIFIED, WITH MAJOR DELTAS**
- URLs: https://modelcontextprotocol.io/specification/latest and .../2026-07-28/changelog and .../2026-07-28/server/utilities/pagination (the GitHub repo link in the context doc remains valid as the spec's source)
- **Current spec revision: 2026-07-28** (previous: 2025-11-25). Verified changes most relevant to MailWeave:
  1. **Stateless protocol.** No initialize handshake, no protocol-level sessions; "Servers that need cross-call state use explicit, server-minted handles passed as ordinary tool arguments." → MailWeave's progressive-expansion API (e.g., "expand evidence handle X to level N") is exactly the pattern the spec now canonizes; do not design around session state.
  2. **Sampling is DEPRECATED** (with Roots and Logging): "new implementations should not add support for them… integrate directly with LLM provider APIs instead of Sampling." → If MailWeave needs LLM calls for routing/reranking/sufficiency, they must be server-side provider calls or left to the client agent; do not build on MCP sampling.
  3. **Elicitation survives, restructured** into the new Multi Round-Trip Requests (MRTR) pattern: servers return `resultType: "input_required"` with `inputRequests`; clients retry with `inputResponses`. Every result now carries `resultType`.
  4. **Pagination exists only for list operations** (`tools/list`, `resources/list`, `prompts/list`, `resources/templates/list`) via opaque cursors. **Tool-call results have no protocol pagination** — chunked/progressive disclosure of retrieval results is an application-layer design problem, confirming context-doc §29's framing that MCP does not solve "how much / which data" (and it must be solved with handles/cursor arguments in tool schemas).
  5. Tools vs resources framing unchanged (Resources = context/data, Tools = model-executed functions). New: `ttlMs`/`cacheScope` freshness hints on list/read results — a protocol-level vocabulary for staleness metadata that resonates with context-doc §45 ("index last synchronized at…").
  6. **Extensions** are now formalized (Tasks for long-running async ops with polling; MCP Apps; Skills over MCP). Tasks could matter if expensive retrieval (e.g., first-time semantic indexing) exceeds a single call's budget.
  7. Security guidance verified: user consent/control, data privacy, and "descriptions of tool behavior such as annotations should be considered untrusted, unless obtained from a trusted server." The spec provides principles, not an email-content prompt-injection recipe — MailWeave's untrusted-content annotation design (context-doc §42) remains its own responsibility.

---

## 8. Newly found prior art (mid-2026 hunt)

### 8.1 arXiv 2607.17598 — "Is Progressive Disclosure All You Need for Long-Context Agents?" — **VERIFIED, HIGH RELEVANCE**
- URL: https://arxiv.org/abs/2607.17598 — He, Zhao, Wang, Chen; submitted July 20, 2026.
- First controlled study of the progressive-disclosure pattern (via Agent Skills packs) vs raw-document navigation vs a classical hybrid retriever, across 3 harnesses and 3 model families on InfiniteBench (books, not email). Abstract findings, quoted: on a single book "the gain depends on the harness… near zero when a strong agent harness already divides and retrieves on its own"; at multi-book scale "raw-document navigation collapses while one-level progressive disclosure degrades more slowly and pulls ahead"; "A second, deeper routing level never helps and sometimes breaks accuracy outright, so one level is enough"; "Progressive disclosure buys context, not intelligence."
- **Thesis impact:** (a) *supports* PD for corpus-scale spaces — a mailbox of hundreds of threads is the "many books" regime; (b) *warns against depth* — the context doc's illustrative Level 0→5 ladder (§10.2) is exactly the kind of multi-level hierarchy the paper found harmful; favor one strong disclosure level + full-fetch escape hatch, and benchmark depth explicitly; (c) *sharpens the falsification criterion* (context-doc §57): a strong agent with primitive complete tools may already suffice — MailWeave must beat that baseline, not only the broken preview. Domain transfer (books→email) is untested; treat as hypothesis-shaping, not conclusive.

### 8.2 arXiv 2604.03455 — "Lightweight Query Routing for Adaptive RAG: A Baseline Study on RAGRouter-Bench" — **VERIFIED, RELEVANT**
- URL: https://arxiv.org/abs/2604.03455 — Bansal & Agarwal; submitted April 3, 2026.
- 7,727 queries, 4 domains; classical classifiers routing among retrieval paradigms. TF-IDF + SVM: macro-F1 0.928, 93.2% accuracy, "28.1% token savings relative to always using the most expensive paradigm"; lexical features beat MiniLM embeddings by 3.1 F1 for routing ("surface keyword patterns are strong predictors of query-type complexity").
- **Thesis impact:** directly supports context-doc §13's Tier-1/Tier-2 plan — cheap deterministic/lexical routing first, no trained router needed initially — with quantitative evidence that inexpensive query-side routing captures most of the win.

### 8.3 Anthropic, "Effective context engineering for AI agents" — **VERIFIED**
- URL: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents (Sept 29, 2025)
- Advocates just-in-time retrieval via lightweight identifiers ("introduce external organization and indexing systems like file systems, inboxes, and bookmarks to retrieve relevant information on demand"), progressive discovery, token-efficient tools, compaction/structured notes. The canonical vendor articulation of the design philosophy MailWeave instantiates for email; cite as conceptual prior art (not email-specific, no evidence-preservation invariant).

### 8.4 GongRzhe/Gmail-MCP-Server — **VERIFIED — the most popular Gmail MCP, and it is ARCHIVED**
- URL: https://github.com/GongRzhe/Gmail-MCP-Server — MIT; **1.2k stars / 411 forks**; **archived by the owner March 3, 2026** (read-only).
- 19 tools; message-level `search_emails` (Gmail q syntax) + `read_email`; batch operations; no thread-preview trap, but also no partiality semantics, PD, or adaptive retrieval. The context doc's prior-art registry missed the ecosystem's most-starred Gmail MCP; its archival also signals maintenance-vacuum opportunity.

### 8.5 Other 2026 items surveyed (lower relevance, verified to exist; abstracts/titles only)
- Meilisearch, "Adaptive RAG explained: What to know in 2026" — practitioner overview of adaptive RAG routing (https://www.meilisearch.com/blog/adaptive-rag).
- Agentic RAG survey: arXiv 2501.09136 ("Agentic Retrieval-Augmented Generation: A Survey on Agentic RAG").
- Redis, "Agentic Retrieval Techniques" (https://redis.io/blog/agentic-retrieval-techniques/).
- Claude Cookbook, "Context engineering: memory, compaction, and tool clearing" (https://platform.claude.com/cookbook/tool-use-context-engineering-context-engineering-tools).
- MindStudio posts on progressive disclosure in agents/skills; various 2026 context-engineering guides (Sourcegraph et al.). None email-retrieval-specific.
- **No project was found that combines email + evidence-preserving retrieval + explicit partiality + adaptive escalation.** The niche remains open as of 2026-08-30.

---

## 9. Anthropic claude-agent-sdk-demos email agent — **VERIFIED, WITH LIMITS**
- URLs: https://github.com/anthropics/claude-agent-sdk-demos ; email-agent README and package.json via raw.githubusercontent.com
- **Verified today:** repo contains an `email-agent` demo: "An in-development IMAP email assistant" that can "Display your inbox / Perform agentic search to find emails / Provide AI-powered email assistance." Disclaimer verbatim: "These are demo applications by Anthropic. They are intended for local development only and should NOT be deployed to production or used at scale." MIT license.
- **Architecture facts from manifest:** `node-imap` + `mailparser` + `sqlite3` + `@anthropic-ai/claude-agent-sdk` + zod/React. **No embedding or vector-store dependency.** So its "agentic search" is agent-driven iteration over IMAP/SQLite-backed lexical primitives — evidence that Anthropic's own reference approach is "let the agent loop over cheap search tools," not semantic RAG.
- **Limit:** the README does not document the search-loop design; characterizing the loop beyond the manifest would require reading source, which was out of scope today. Conceptually reusable: local store + agentic iterative search + no mandatory semantic index — consistent with MailWeave's "adaptive, escalate-only-if-needed" stance.

---

## 10. Could not verify
1. **The 2 comments on issue #296, who closed it, and the closure rationale.** Tried: api.github.com issue endpoint (succeeded for the issue itself, confirming `comments: 2`, `state_reason: not_planned`), then the /comments endpoint four times across ~40 minutes (HTTP 403 every time — apparent unauthenticated rate-limiting through the fetch proxy), and the HTML issue page twice (rendered content truncated before the comment section). `gh` CLI is not installed in this environment. Per claim discipline, no curl workaround was attempted.
2. **Last-commit dates for the four prior-art repos** (taylorwilsdon, Maheidem, CWBinder, Ayush-k-Shukla). Rendered repo pages did not expose dates and the API was rate-limited. Activity levels are reported only as visible (commit counts, stars). GongRzhe's archival date (Mar 3, 2026) WAS visible and is verified.
3. **The context doc §7 naming-caveat specifics** ("a macOS utility for generating Apple Mail drafts from CSV data; an older unrelated GitHub project using the name"). A web search for "MailWeave" surfaced adjacent collisions — **MailWeaver.ch** (Swiss email-marketing service) and **mailweaver.com** (parked/for-sale) — but not the two specific claimed uses; GitHub's search page is robots-blocked to the fetcher. Treat the specific §7 examples as unconfirmed; the general caveat (name adjacency exists; check before release) is confirmed and if anything strengthened by the MailWeaver near-collision.
4. **Whether Google's hosted server or Anthropic's wrapper imposes the 5-message cap.** No public implementation exists for either layer (§2, §3); the cap is observable and now description-documented, but its architectural home remains unattributable from public sources.
5. **The #82548 hours-to-days search-index lag**, as distinct from the preview cap. Not reproduced in the minimal probe (same-day threads appeared in search); one suggestive stale-ordering observation noted in §3.4.4. The issue's claims are accurately reported but remain third-party.
6. **#239's get_thread truncation, today.** The probe's 7-message thread came back complete; 10+-message threads were not probed (would have required deeper reads of the user's mailbox than this verification warranted).

---

## 11. Thesis impact

**Strengthens the thesis:**
1. The core failure is **live today, empirically reproduced, and vendor-acknowledged in the deployed tool description** — with no data-level fix: no truncation marker, no total count, no match attribution in the payload (§0, §3.4). The thesis's factual foundation is stronger than when the context doc was written.
2. The vendor's prescribed workaround ("never trust previews; always get_thread") **institutionalizes Baseline B (full-thread dump)** — making MailWeave's efficiency comparison the exact right experiment.
3. The failure genus is wider than one tool: silent HTML dropping (#203), silent body loss (#194), silent sender-specific misses (#349), get_thread truncation (#239). "Representation layers silently destroying evidence" is a pattern, not an incident.
4. Timeline evidence (#48713) that the truncation era began when **message-level tools were removed** in favor of thread previews — MailWeave restores and then improves on the removed abstraction.
5. Ecosystem gap confirmed: none of five inspected Gmail MCPs (including the most popular, now archived) implements evidence preservation, partiality metadata, or adaptive disclosure (§5.5, §8.4). The most popular is archived; the field is open.
6. RAGRouter-Bench supports the cheap-router-first, no-trained-router plan with numbers (§8.2). The 2026-07-28 MCP spec's handle-based statelessness matches MailWeave's progressive-expansion API shape (§7.1).

**Weakens / constrains the thesis:**
1. **arXiv 2607.17598:** progressive disclosure adds ~nothing when a strong agent harness already navigates well, and **deep disclosure hierarchies can hurt** ("a second, deeper routing level never helps and sometimes breaks accuracy"). MailWeave must (a) benchmark against "strong agent + complete primitive tools", (b) default to shallow disclosure (one level + full fetch), (c) treat the §10.2 Level-0→5 ladder as an adversary hypothesis, not a design.
2. **#239 undermines "get_thread is reliable ground truth."** Every reproduction (including the context doc's and mine) leans on get_thread completeness; at least one April 2026 report says it fails on 10+-message threads. Benchmarks must validate the fallback itself (REST `users.threads.get` vs MCP `get_thread`).
3. **Freshness (Problem B) looks account-/thread-variable, not universal:** #76396's fresh self-test indexed in seconds; my probe found same-day search hits. The context doc's decision to keep freshness a separate, tested hypothesis is validated — and marketing claims about fixing staleness would be unsupported today.
4. **Scope constraint found:** Gmail `q` search is unavailable under the `gmail.metadata` scope — the minimum-scope privacy story and the search architecture interact (§4.1).
5. **MCP sampling deprecation** removes one architectural option for server-initiated LLM reranking (§7.2); plan for provider-API calls or agent-side reasoning instead.

**Invalidates:** nothing. No evidence was found that the bug is fixed; the opposite was observed.

---

## 12. Open questions for synthesis
1. **Baseline set must grow:** add "strong agent + honest primitive tools (message-level search + full thread get)" as the primary competitor per arXiv 2607.17598 — beating the broken preview is necessary but not sufficient.
2. **How deep should disclosure go?** Evidence says shallow. What is the minimal partiality contract (total count + explicit match attribution + one expansion handle) that satisfies the Evidence Preservation and Partiality invariants without a multi-level ladder?
3. **Can get_thread be trusted?** Design a get_thread-completeness check into Loop 0/1 (REST threads.get message count vs preview count vs any MCP-layer fetch), given #239.
4. **Scope vs search tradeoff:** is `gmail.readonly` acceptable, given `q` is unusable under `gmail.metadata`? What does the privacy architecture concede for message-level search?
5. **Freshness experiment design:** given the variance across accounts (#76396 vs #82548 vs my probe), the Loop-6 experiment needs multiple mailboxes and long-thread vs new-mail cases separated.
6. **Stateless handles:** adopt MCP 2026-07-28 conventions (server-minted handles as tool args; consider `ttlMs`-style staleness fields on MailWeave's own responses). Which SDK targets the new revision cleanly?
7. **Positioning/citation duties:** cite arXiv 2607.17598, RAGRouter-Bench, the Anthropic context-engineering post, and the archived GongRzhe server as prior art; the README's "documented bug" section can now also cite the deployed tool description's own warning text as vendor acknowledgment.
8. **Naming:** "MailWeaver" (.ch service, parked .com) is adjacent to "MailWeave"; the specific collisions named in context-doc §7 were not reconfirmed — re-run the name check before release.
9. **Comment archaeology:** the two unread comments on #296 may contain an official stance (Anthropic or Google) on whether truncation is considered intended behavior — worth one authenticated GitHub read when available.

---

## SCOPE CORRECTION ADDENDUM (2026-08-30)

**Added by:** research-revision agent, after `docs/SCOPE_CORRECTION.md` (authoritative).
**Nature of this addendum:** the body above is *source verification*. Verification findings are facts about the world; a scope correction cannot change them. Nothing above is edited, retracted, or renumbered. What changes is how this document's **thesis-impact and synthesis framing** (§11, §12) should be read now that the build target is the complete MailWeave product rather than "the smallest architecture that tests the thesis."

### 1. Status of this document's conclusions

**Stand unchanged (all of §§1–10, and the factual half of §11).** Every VERIFIED / VERIFIED-WITH-DELTA / COULD-NOT-VERIFY status, quote, probe result and URL is unaffected. The correction does not touch the evidence base; it touches what we build on top of it.

**Superseded as *scope framing*, still valid as *measurement*:**

| Original framing | Why it is superseded | What survives |
|---|---|---|
| §11 "Weakens/constrains #1": arXiv 2607.17598 implies MailWeave should "default to shallow disclosure" and treat the Level-0→5 ladder as "an adversary hypothesis, not a design" | Correction §7 makes progressive disclosure a **core product requirement**, not a hypothesis to be talked out of | The *depth* warning survives intact and is now a design constraint (see §4 below). "Shallow" is a depth budget, not a reason to omit PD. |
| §11 "Weakens #3": freshness looks account-/thread-variable, so "marketing claims about fixing staleness would be unsupported today" | Correction §12 requires freshness to be **tested on real delivered mail and mitigated if lag is found**, before any freshness claim | Entirely. This document's caution is *exactly* the correction's rule: measure, then claim, then mitigate — never claim first. |
| §12 open questions framed as "for synthesis" (i.e. things that might be deferred) | Correction §16 requires `PRODUCT_CONTRACT.md` + `RELEASE_RUBRIC.md` before implementation | All nine questions remain live; several are now rubric criteria rather than open research (see §5 below). |

**Genuinely invalidated: nothing.** This document invalidated nothing before and it invalidates nothing now. Its §11 "Invalidates: nothing" line stands.

**Strengthened by the correction:** §12 open question 1 — adding *"strong agent + honest primitive tools (message-level search + full thread get)"* as a first-class comparison arm. Under the old scope this was one baseline among several. Under the corrected scope it is the **only arm that can falsify the product's central claim**, because arXiv 2607.17598 says that is precisely the configuration in which progressive disclosure adds nothing. It must be built and kept live for the life of the project, not run once.

### 2. Baseline vs product requirement

| Item this document supplied | Status under the correction |
|---|---|
| "One strong disclosure level + full-fetch escape hatch" (§8.1b) | **Baseline / depth budget.** The starting depth for the required PD implementation, and the default to beat. Not a licence to ship a single level unmeasured, and not a ceiling that overrides a measured need for one more level. |
| "Strong agent + complete primitive tools" (§8.1c, §12.1) | **Mandatory permanent comparison arm.** Product ships only if it beats this, not merely the broken hosted preview. |
| Beating the hosted `search_threads` preview (§0.1, §3.4, §11.2) | **Necessary but not sufficient.** It is the *motivating* failure, not the bar. |
| `get_thread` as reliable ground truth | **Not a baseline — an unverified assumption** (§6.1, #239). Must be independently validated (REST `users.threads.get` message count vs any MCP-layer fetch) before any measurement leans on it. |
| Cheap lexical-first routing supported by RAGRouter-Bench (§8.2) | **Cheap first rung of a required ladder** (correction §3), not the whole retrieval system. TF-IDF+SVM's 0.928 macro-F1 / 28.1% token saving remains the evidence that the *cheap rung* is worth having — it says nothing about whether the expensive rungs are needed, and must not be cited as if it did. |
| "No trained router yet; collect traces first" (§8.2 read, and Decision 9) | **Confirmed product principle** (correction §9 and §15). Unchanged. |
| MCP 2026-07-28 stateless + server-minted handles (§7.1) | **Confirmed product principle** (correction §14). Unchanged. |
| Ecosystem gap: no Gmail MCP implements evidence preservation / partiality / adaptive escalation (§5.5, §8.4) | **Unchanged, and now the product's differentiation claim rather than a research observation.** Re-check before release; GongRzhe's archival (Mar 3, 2026) and the field's openness were verified today, not permanently. |

### 3. Facts that survive untouched

Architecture can rely on these without re-reading the body:

1. **The representation failure is live, reproduced, and vendor-documented today.** The deployed `search_threads` description states the ~5-oldest cap and the absence of a truncation marker verbatim; a 7-message thread returned as its 5 oldest was reproduced on a real mailbox (§0.1, §0.2, §3.4). The payload carries **no total count, no truncation flag, no match attribution** (§3.4.3).
2. **The vendor's own mitigation is instructional, not representational** — "always call `get_thread`" — which institutionalises the full-thread-dump baseline MailWeave must beat (§3.4 net, §11.2).
3. **Message-level search preserves hit identity.** `users.messages.list(q)` returns per-message `{id, threadId}`; `resultSizeEstimate` is an estimate, not a count; **`q` is unusable under the `gmail.metadata` scope** (§4.1). `gmail.readonly` is therefore the floor for any searching architecture.
4. **`threads.get` formats** `full` / `metadata` / `minimal` with `metadataHeaders[]`; no per-thread cap documented at REST level; no pagination within a thread (§4.3).
5. **`history.list` / sync semantics:** `startHistoryId` required; invalid/expired → HTTP 404 → full resync mandated; history records "typically available for at least one week," occasionally only hours (§4.4). This is the primitive any freshness mitigation under correction §12 will be built from.
6. **The failure genus is wider than one tool:** silent HTML dropping (#203), silent body loss (#194), sender-specific silent misses (#349), `get_thread` truncation on 10+-message threads (#239). Every Gmail issue checked (8) was closed "not planned" or is open without staff response (§6).
7. **Timeline evidence (#48713)** that the truncation era began when message-level tools were *replaced* by thread previews in ~April 2026 — MailWeave restores a removed abstraction (§6.6). User-reported, not vendor-confirmed.
8. **MCP 2026-07-28:** stateless, no protocol sessions, cross-call state via "explicit, server-minted handles passed as ordinary tool arguments"; **Sampling deprecated** ("integrate directly with LLM provider APIs instead"); **no protocol-level pagination of tool results**; `ttlMs`/`cacheScope` freshness hints exist on list/read results; tool annotations are to be treated as untrusted (§7).
9. **arXiv 2607.17598 (verified, quoted):** PD gain is "near zero when a strong agent harness already divides and retrieves on its own"; at multi-corpus scale one-level PD "pulls ahead" while raw-document navigation "collapses"; "A second, deeper routing level never helps and sometimes breaks accuracy outright, so one level is enough"; "Progressive disclosure buys context, not intelligence." Domain is books, not email — transfer untested.
10. **arXiv 2604.03455 (RAGRouter-Bench, verified):** TF-IDF+SVM routing at macro-F1 0.928 / 93.2% accuracy / 28.1% token saving vs always-most-expensive; lexical features beat MiniLM embeddings by 3.1 F1 *for routing*.
11. **Prior art:** no public implementation of the hosted Gmail MCP layer exists (§2, §3); Anthropic's own `email-agent` demo uses IMAP + SQLite + agentic iteration with **no embedding or vector dependency** (§9); Ayush-k-Shukla's Gmail MCP uses local xenova embeddings + ChromaDB populated only by prior tool calls — a usage-driven partial index, a cautionary example, not a model (§5.4).

### 4. Unresolved tension — stated, not smoothed

**T-VR1 — Progressive disclosure is a required product behaviour, and the best available controlled evidence says it may buy nothing here.**

This is a real conflict and it is not resolved by rewording either side.

- **Correction §7** requires the system to make matched/contextual/expanded/stub/partial/how-much-more/how-to-get-more distinctions explicit, and states that partial data must never masquerade as complete data.
- **arXiv 2607.17598 (§8.1)** finds that PD's *accuracy* gain is near zero when a strong agent harness already retrieves well, and that a second disclosure level "never helps and sometimes breaks accuracy outright."

Both can be honoured, and the honouring must be visible in the design rather than assumed:

1. **Implement PD as required.** It is not optional, and the correction is not negotiable on this point.
2. **Justify it on the axis the paper does not measure.** The paper measures accuracy on book QA. MailWeave's PD claim is primarily about **honest partiality** — that a partial answer is *labelled* partial and carries a path to more. That is a correctness/safety property (no silent false "not found"), not an accuracy-on-a-benchmark property, and it is exactly the property whose absence is vendor-documented in §0.1. State the claim on that axis and stop overclaiming accuracy.
3. **Keep the depth shallow and make depth a measured parameter.** Default to one strong disclosure level plus a full-fetch escape hatch. Any second level must be introduced with a measurement showing it helps, and must be removable.
4. **Keep the "strong agent + honest primitive tools" arm live permanently.** If that arm matches MailWeave on accuracy, the honest conclusion is "PD costs nothing and buys explicit partiality" — publishable and true. If MailWeave *loses* to it, that is a product-level finding that must be reported, not buried.
5. **Do not let a null accuracy result be reported as a win.** The falsification criterion in §12.1 is now a rubric obligation.

**T-VR2 — Real-Gmail-first development and a single mailbox cannot settle the freshness question.**

Correction §13 makes the owner's real mailbox the primary development environment, and §12 requires a freshness mitigation if meaningful lag is found. But this document's verified evidence (§11 "Weakens #3") is that freshness behaviour is **account- and thread-variable**: #76396's reporter saw a fresh self-test indexed within seconds while long threads stalled; #82548 reports 3+ day lag; today's probe found same-day threads in search results and did **not** reproduce the hours-to-days lag. Consequently:

- A negative result on one mailbox ("no lag observed") **cannot** license a "MailWeave search is fresh" claim, and must not be recorded as one.
- The freshness experiment needs at least the dedicated seeded account (correction A.2) *plus* the personal mailbox, and must separate the *new-mail* case from the *long-thread* case, because the reported failures differ between them.
- Note the confound: the hosted-MCP lag reports are about a black-box layer (§10.4 — the cap's architectural home is unattributable). Direct REST `messages.list(q)` may simply not share it. That is a distinct measurement and must not be conflated.

**T-VR3 — The fallback we measure against may itself be broken.**

Every reproduction in this document, and the correction's implicit model of "get the whole thread if in doubt," leans on `get_thread` completeness. Issue #239 (§6.1) reports `get_thread` itself truncating on 10+-message threads. Today's probe cannot arbitrate (7 messages < 10). If the full-thread baseline is itself lossy, comparisons against it are measuring the wrong thing. This must be settled by direct REST measurement before any baseline number is published.

### 5. What architecture must now decide that this document treated as deferred

1. **The minimal partiality contract** (§12.2), now a shipped API surface rather than an open question: total count + explicit match attribution + exactly one expansion handle, with a stated depth limit. Write it into `PRODUCT_CONTRACT.md`.
2. **A `get_thread`/`threads.get` completeness check** (§12.3) as a standing test on long threads, not a Loop-0 curiosity — it validates the measurement instrument.
3. **The freshness experiment design** (§12.5): two mailboxes minimum, new-mail and long-thread cases separated, direct REST distinguished from the hosted MCP, and a pre-registered decision rule for when `history.list`-based reconciliation becomes mandatory under correction §12.
4. **Handle design against MCP 2026-07-28** (§12.6): server-minted handles as ordinary tool arguments; consider `ttlMs`-style staleness fields on MailWeave's own responses; pick an SDK targeting the current revision.
5. **Where internal model calls run, given Sampling is deprecated** (§7.2 + correction §8 + Appendix A.1): the protocol will not lend the server a model. Any in-server intelligence is a local model, an opt-in provider key, or nothing. This is now on the critical path because semantic retrieval and reranking are product capabilities — see the addendum in `RETRIEVAL_OPTIONS.md` for the local-model assessment and `ROUTING_OPTIONS.md` for the resulting seam problem.
6. **Citation and claim discipline for the README** (§12.7): cite arXiv 2607.17598 *including* its negative finding, RAGRouter-Bench, the Anthropic context-engineering post, and the archived GongRzhe server. The deployed tool description's own warning text is now citable vendor acknowledgment.
7. **Name check before release** (§12.8) — "MailWeaver" collisions were found; the two specific collisions claimed in the original context doc were not reconfirmed.
