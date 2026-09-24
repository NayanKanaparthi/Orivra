# Scope Correction — Authoritative Project Direction

**Issued by:** Nayan (project owner), 2026-08-30
**Status:** AUTHORITATIVE. Supersedes any earlier scoping in `docs/archive/`.
**Applies to:** every agent, document and implementation decision in this repository.

This document records a direction correction issued after the first research wave.
It is reproduced substantially as written by the project owner. Where a later
document conflicts with this one, this one wins.

---

## 0. Why this exists

The first research wave produced six useful research documents and one architecture
synthesis. The synthesis interpreted several *baseline recommendations* as *settled
product scope*, and interpreted "loop engineering" as permission to stop early once a
minimal hypothesis was proven. Both interpretations were wrong. The research is
preserved. The scope verdicts are replaced.

---

## 1. We are building the complete MailWeave product

The phrase "smallest architecture that can test the thesis" no longer drives
implementation scope.

`A + thread map` is a strong foundation and baseline, but it is not automatically the
finished MailWeave product. The retrieval research describes it specifically as the
smallest architecture for Loops 1-3, with semantic retrieval, richer structural
retrieval and freshness recovery deferred until later experiments. That sequencing came
from a misunderstanding of what was meant by loop engineering.

The target product remains:

> **MailWeave — query-aware adaptive retrieval with progressive context disclosure for
> email agents.**

We determine the complete architecture required to honestly fulfill that product
definition, implement it, and use rigorous review loops to make the implementation
correct.

---

## 2. What "loop engineering" means here

It does **not** mean:

```
build minimal hypothesis -> benchmark -> decide whether to build the next capability -> maybe stop early
```

It means:

```
define complete product contract
  -> implementer agent builds
  -> reviewer agent audits against a fixed rubric
  -> reviewer gives concrete failures
  -> implementer fixes them
  -> reviewer checks again
  -> repeat until every mandatory criterion passes
```

There is an authoritative release rubric defining what "MailWeave is complete" means.
Implementer/reviewer loops run across architecture, retrieval correctness, progressive
disclosure, security, MCP behavior, real Gmail behavior, performance, tests and
documentation.

**The loop ends when the required implementation satisfies the rubric, not when a
minimal baseline proves the idea is plausible.**

Research and benchmarks still matter. They are used to validate implementation choices
and catch failures, not to justify prematurely stopping the product.

---

## 3. Lexical retrieval is the cheap first rung, not the entire retrieval system

Keep direct Gmail `messages.list(q)` and deterministic parsing as the cheapest path.
This is strongly aligned with MailWeave because Gmail returns message-level hit identity
and therefore preserves the evidence that caused the match.

But MailWeave must not become a lexical-only Gmail wrapper. The complete retrieval
system must support recoverable escalation:

```
query
  -> cheap deterministic/lexical retrieval
  -> if strong evidence, stop
  -> if weak/zero/ambiguous, broaden
  -> structural retrieval where relevant
  -> semantic retrieval where lexical retrieval is insufficient
  -> rerank/evaluate candidates when ambiguity requires it
  -> progressively expand context if evidence is still insufficient
```

The router is only an initial hypothesis. A wrong first route must not cause a false
"not found." Escalation matters more than perfect first-route accuracy.

---

## 4. Semantic retrieval is part of the complete MailWeave product

Semantic retrieval is **not** "maybe someday." It is an adaptive escalation path for
conceptual/paraphrased queries that Gmail lexical search cannot adequately resolve.

```
user asks: "When did we postpone the launch?"
email says: "We'll push go-live into Q4."
```

Lexical search may fail even though the evidence exists.

The architecture proposed in the retrieval research is a useful shape: run
lexical/structural retrieval first; when lexical evidence is weak, fetch a bounded live
candidate pool, embed the query and candidates on demand, rank them, and disclose the
resulting evidence. This avoids requiring a persistent mailbox-wide vector index.

A persistent semantic index is not automatically required. Whether semantic retrieval is
on-demand, indexed, local or hosted remains an architecture decision.

---

## 5. Structural / query-aware retrieval is also part of the product

The thread map is excellent and remains central. It provides the representation we were
looking for: every message in a touched thread can exist at least as a cheap stub, while
selected evidence is expanded. This makes silent disappearance structurally much harder
and gives the agent a navigable view of the information space.

But fixed adjacency is not enough to define query-aware context. MailWeave should be able
to use structural signals such as: reply relationships, participant relationships,
temporal relationships, thread position, subject/snippet relevance, and multi-thread
relationships where appropriate.

These can often be computed live from the thread map without requiring a persistent graph
or database. A persistent participant graph is therefore not a requirement, but
participant-aware and structural retrieval capability is.

---

## 6. Fixed +/-2 is only a benchmark baseline

Do not treat fixed +/-2 as MailWeave's final progressive disclosure policy. Keep it as a
simple baseline (`hit + two before + two after`), but implement and review the actual
query-aware policy against it: reply-chain + query-scored structural selection using
participant, subject/snippet and temporal signals under the same context budget.

That richer query-aware disclosure is much closer to the MailWeave product definition.

---

## 7. Progressive disclosure remains a core product requirement

The system must make these distinctions explicit:

- which messages matched the query
- which messages are contextual
- what has been expanded
- what remains only a stub
- whether the current result is partial
- how much more information exists
- how the agent can retrieve more

**Partial data must never masquerade as complete data.** The map-carrier / in-band
partiality approach is strongly aligned with this and is retained. The path to more
information must live directly in tool results, because that is the channel the model
reliably sees.

---

## 8. Internal LLM calls and reranking are not banned

It was never decided that MailWeave must never call a model internally. The architecture
decides whether internal model calls materially improve: difficult query interpretation,
semantic retrieval, candidate reranking, decision/change interpretation, or evidence
sufficiency evaluation.

They must not run unnecessarily on easy queries. Similarly, reranking should exist where
candidate ambiguity requires it, but an exact Message-ID or invoice-number query does not
need an expensive reranker.

**The product requirement is adaptive behavior and good retrieval, not the use or
avoidance of a particular technology.**

---

## 9. Do not train a router now

This part of the existing work remains correct. We do not yet have enough real MailWeave
retrieval traces and labels to train a router intelligently.

Build a recoverable router/adaptive policy now. Instrument it. Later, actual traces may
justify learning a routing policy.

---

## 10. Read-only is the first release, not the project's identity

The MailWeave server initially uses exactly `gmail.readonly`. The security analysis gives
a strong reason: it is the minimum viable scope that still permits Gmail `q` search,
message bodies, thread retrieval, history and attachment access. This gives the first
release a clean security story and keeps Gmail actions outside the agent's capability.

Word this as: **"The first MailWeave retrieval release is intentionally read-only."**

Do not frame MailWeave as permanently incapable of Gmail actions. Sending, drafting and
modifying mail are simply outside the current retrieval-focused product boundary.

---

## 11. Persistent indexes and databases are architecture choices

Do not add Chroma/Pinecone/database infrastructure merely to make the project look
advanced. Also do not declare them permanently out of scope before the architecture is
complete.

A persistent semantic index creates its own freshness/synchronization problem and can
recreate the exact stale-information failure MailWeave is meant to prevent. Therefore:

- semantic retrieval is **required as a capability**;
- persistent semantic indexing is **optional**;
- **Gmail remains the source of truth** unless a properly synchronized architecture is
  justified.

---

## 12. Freshness is part of the complete-product quality bar

Keep representation omission and search freshness as separate problems. But do not treat
freshness testing as something performed after declaring the product complete.

Test real delivered mail. If direct Gmail API search is sufficiently fresh, document the
result. If it exhibits meaningful lag, the implementer must build a mitigation such as
History-based reconciliation/synchronization, or another defensible mechanism, before
making freshness claims.

Any discovered production-relevant freshness failure becomes implementation feedback for
the loop, not merely a future research idea.

---

## 13. Real Gmail is the primary development environment from day one

Development and debugging run against the owner's real Gmail account from the beginning.
We do not optimize exclusively against invented test corpora and then discover the
assumptions fail on real email.

- **Primary:** the real mailbox — for development, discovery, smoke testing, real thread
  behavior, real MIME/header weirdness, real wording, OAuth, latency, pagination,
  freshness and integration behavior.
- **Secondary:** controlled seeded messages inside a real Gmail account, where
  deterministic ground truth is necessary for measurements such as evidence-position
  sweeps.
- **Regression:** sanitized deterministic fixtures created from real failures we discover.

The evaluation methodology must make real-mailbox behavior a first-class source of
engineering failures, not merely a spot-check after synthetic evaluation.

> **Reality discovers failures. Controlled cases measure them. Regression tests preserve
> the fixes.**

---

## 14. Keep the current MCP/stateless findings

Preserve the recommendation to align with MCP's stateless direction and use explicit
server-minted handles for cross-call progressive retrieval state. MCP 2026-07-28 expects
cross-call state to use explicit server-minted handles rather than hidden protocol
sessions. That is aligned with MailWeave's progressive disclosure design.

---

## 15. Settled product principles

This replaces any earlier "decisions already settled" section.

- MailWeave is its own Gmail-backed MCP server.
- The first retrieval release is read-only and uses the minimum viable Gmail scope.
- Real Gmail is used from day one.
- Retrieval is query-aware at message level.
- Exact search-hit identity must always be preserved.
- Retrieval is adaptive: cheap paths first, escalation when required.
- Semantic retrieval is part of the escalation architecture.
- Structural/thread/participant/temporal signals may guide retrieval and context selection.
- Routing is recoverable and must not create unrecoverable false negatives.
- Progressive disclosure is a core product behavior.
- Partial results must always be explicit and navigable.
- Fixed +/-2 is only a benchmark baseline.
- The thread-map/stub representation remains a core architectural candidate.
- Freshness and representation correctness are evaluated separately.
- Instrumentation is built in from the start.
- No trained router yet; collect real traces first.
- Persistent indexes, databases, internal LLMs, specific rerankers and persistent graphs
  are architecture choices rather than mandatory or forbidden technologies.
- MailWeave's final architecture is frozen only after the complete-product design has
  been synthesized.

---

## 16. Required documents before implementation

`PRODUCT_CONTRACT.md` — the complete MailWeave behavior and capability boundaries.

`RELEASE_RUBRIC.md` — objective mandatory criteria for completion, covering at least:
evidence preservation, adaptive escalation, lexical retrieval, semantic retrieval,
structural retrieval, candidate ranking, progressive disclosure, explicit partiality,
router recoverability, real Gmail reliability, freshness, performance/latency,
OAuth/security/privacy, MCP correctness, prompt-injection/untrusted-email handling,
observability, regression tests, real-Gmail E2E testing, documentation accuracy.

Each criterion needs measurable acceptance conditions and a status of
`PASS / FAIL / BLOCKER / NOT TESTED`.

---

## 17. The implementer/reviewer loop

**Implementer agent** receives the product contract, architecture decision, rubric,
existing reviewer feedback and codebase.

**Reviewer agents** independently inspect the implementation rather than trusting the
implementer's summary. Reviewers cover at minimum: retrieval correctness, progressive
disclosure/context representation, architecture/code quality, security/privacy,
performance, MCP protocol/tool quality, and real Gmail integration/testing.

Reviewer feedback must be concrete: severity, failing rubric criterion,
reproduction/test, expected behavior, actual behavior, required fix.

Then: `implement -> test -> independent review -> feedback -> fix -> review again` until

- zero blocking/high-severity findings;
- every mandatory rubric criterion passes;
- all required real-Gmail E2E tests pass;
- benchmark/performance thresholds pass;
- README/product claims match measured behavior.

**Do not accept self-declared completion from the implementer.**

---

## 18. Revise the existing research outputs; do not discard them

`VERIFIED_RESEARCH.md`, `RETRIEVAL_OPTIONS.md`, `ROUTING_OPTIONS.md`,
`CONTEXT_DISCLOSURE_OPTIONS.md`, `EVALUATION_PLAN.md` and `SECURITY_NOTES.md` contain
useful work. Do not rewrite them merely to agree with this correction. Instead:

- preserve their factual research;
- clearly distinguish baseline recommendations from final product requirements;
- update any conclusions whose scope depended on the previous misunderstanding of loop
  engineering;
- update the evaluation methodology to make real-mailbox development first-class;
- then synthesize the complete architecture.

---

## Appendix A — Owner decisions, 2026-08-30

Answered directly by the project owner when asked. These are binding.

### A.1 Semantic/model backend

> Pluggable semantic backend with a local, zero-API-cost default. MailWeave should ship
> with a fully local embedding/semantic retrieval path so the complete product works
> without paid APIs and personal mailbox content does not leave the machine by default.
> The semantic interface should remain provider-agnostic and support optional hosted
> embedding/reranking providers for benchmarking or users who explicitly opt in.
> **Hosted providers must never be required for core MailWeave functionality.**

Implication for internal LLM calls (section 8): any internal model call must either run
locally or be an opt-in enhancement with a deterministic or local fallback. Core
retrieval quality may not depend on a paid API.

### A.2 Deterministic ground-truth corpus location

A **separate dedicated Gmail account** holds seeded corpora. The full-scope seeder
credential (required for `insert` and `batchDelete`) never touches the personal mailbox.
Destructive resets are therefore safe and account-pinned.

### A.3 Real-mailbox data handling during development

> Persist IDs, metadata, routing decisions, timings, scores and metrics by default. No
> full personal email bodies in traces/logs. Short aggressively-redacted snippets may be
> persisted only when required to diagnose a specific real-mailbox failure. Full bodies
> remain memory-only during normal execution.

This is a rubric-enforceable privacy constraint, not a guideline.
