# MailWeave Evaluation Plan

**Author:** Agent E (evaluation / benchmark design)
**Revision:** 2 — reality-first three-tier methodology, complete-product coverage
**Date:** 2026-08-30 (Revision 1 same date; all external doc citations fetched that date)
**Governed by:** `docs/SCOPE_CORRECTION.md` (authoritative — §12, §13, §16, §17, Appendix A bind this document), `docs/AGENT_LOOP.md` (the loop this plan feeds), `docs/RELEASE_RUBRIC.md` (criteria authority; in preparation).
**Status:** Proposal for synthesis. Numeric bars are either (a) carried forward from Revision 1 as proposals, or (b) explicitly *unset* with a registered procedure for setting them. No bar in this document was invented to fill a blank.
**Inputs:** `MAILWEAVE_CONTEXT.md` §§4, 34–39, 53–58, 66; `SCOPE_CORRECTION.md`; `VERIFIED_RESEARCH.md` §8.1; `RETRIEVAL_OPTIONS.md`; `SECURITY_NOTES.md` §4.3.

---

# CHANGE LOG — Revision 1 → Revision 2

## What changed, and why

`SCOPE_CORRECTION.md` invalidated two structural assumptions of Revision 1.

**1. The centre of gravity was wrong.** Revision 1 made seeded synthetic corpora the primary metric substrate and the owner's real mailbox a "realism complement … spot-check" (Rev-1 §1.9). `SCOPE_CORRECTION.md` §13 reverses this:

> Reality discovers failures. Controlled cases measure them. Regression tests preserve the fixes.

Revision 2 is organised around exactly that sentence. Tier 1 (reality) is a **repeatable discovery protocol with blocker authority**; Tier 2 (seeded corpora in the dedicated account) is where numbers come from; Tier 3 (sanitized fixtures distilled from Tier-1 failures) is where fixes stay fixed.

**2. The product got bigger, so the coverage must too.** Revision 1 organised around Loops 0–6 in which semantic retrieval (Loop 4), structural expansion (Loop 5) and freshness (Loop 6) were *conditional* — built only if an earlier benchmark demonstrated need. `SCOPE_CORRECTION.md` §§1, 4, 5, 12 make all three mandatory product scope. Conditional entry gates are therefore deleted, replaced by mandatory capability gates, and measurement design is added for capabilities Revision 1 never specified: semantic retrieval (with a local-default vs optional-hosted comparison, per Appendix A.1), structural/participant/temporal retrieval, candidate ranking, escalation cost, and freshness as a completion bar.

A third, smaller change: Revision 1 used "Tier 1 / Tier 2" for *execution modes* (scripted driver vs agent-in-the-loop). That collides with the new three-tier substrate vocabulary, so those are renamed **M1 / M2**. The content is unchanged.

## Prior conclusions that were scope-dependent — SUPERSEDED

| # | Revision-1 conclusion | Status | Superseded by |
|---|---|---|---|
| 1 | Seeded corpora are the primary metric substrate; the personal mailbox is a spot-check for realism calibration (§0, §1.9) | **Superseded** — inverted. Reality is primary for *discovery*; seeded corpora remain primary for *measurement* | SCOPE §13 |
| 2 | Personal-mailbox observations are "qualitative, tagged `no-ground-truth`", useful only for bug discovery and sanity checks (§1.9 R2) | **Partly superseded.** The *claim* restriction is PRESERVED verbatim (no ground truth → no headline metric). The *role* is superseded: Tier 1 now runs content-free oracles, has a defined finding lifecycle, and can raise BLOCKERs | SCOPE §13, §17 |
| 3 | Loop 4 is a *conditional feature loop* with entry condition "lexical-only < 0.70 recall on F4-T2" and a reject branch ("otherwise reject semantic and log the negative result") (§8.2) | **Superseded.** Semantic retrieval is mandatory capability. The entry condition is deleted. A reject branch survives only for *backend/architecture* choices (on-demand vs persistent index; which local model; hosted opt-in) — never for the capability | SCOPE §4, §11 |
| 4 | Loop 5 is conditional on "measured failures concentrated in F5/F6/F7" (§8.2) | **Superseded.** Structural/participant/temporal retrieval is mandatory capability; fixed ±2 and fixed windows are baselines, not candidate policies | SCOPE §5, §6 |
| 5 | "No freshness claims of any kind before Loop 6 runs"; freshness sequenced last; "whether to add history-based sync is decided by these numbers, not in advance" (§0, §7, §8.2) | **Partly superseded.** The claim discipline and the representation/freshness separation are PRESERVED. Superseded: freshness is now part of the completion bar, observed from the first round (Tier-1 D6), and carries **pre-registered mitigation triggers that force implementation work inside the loop** rather than a post-hoc research decision | SCOPE §12 |
| 6 | Sequential Loops 0–6 with conditional later loops and possible early stop | **Superseded.** Replaced by one substrate gate (G0) plus mandatory capability gates that may be worked in any order but must all pass | SCOPE §2 |
| 7 | Paraphrase tier T3 (idiomatic/indirect) "reported separately, never gate-binding in Loops 1–3" (§2.5) | **Superseded.** T3 is in-scope product behaviour; it gets a pre-registered reported bar set at G0 | SCOPE §4 |
| 8 | Baseline E (primitive-tools agent) runs "e2e tier only" as one of five baselines (§4.5) | **Superseded — promoted.** E is the arm most able to falsify MailWeave's added value (`VERIFIED_RESEARCH.md` §8.1, arXiv 2607.17598). It is mandatory at every gate, in two budget variants | SCOPE §2; VERIFIED_RESEARCH §8.1 |
| 9 | Local-embedding tooling matters only "if Loops 4+ ever activate semantic retrieval" (`RETRIEVAL_OPTIONS.md` §4.5) | **Superseded.** A local, zero-paid-API semantic path is a day-one requirement; hosted providers may never be required for core functionality | SCOPE Appendix A.1 |
| 10 | Rev-1 "Tier 1 / Tier 2" execution-mode labels | **Renamed only** to M1 / M2. No substantive change | this revision |

## Prior conclusions PRESERVED — unchanged and still authoritative

Everything in this list is reproduced verbatim below in clearly-marked blocks. It is not re-derived, softened, or paraphrased.

- **Seeding mechanics and their citations** (Rev-1 §1.2 in full): `insert` vs `import` vs `send`; `internalDateSource=dateHeader` and its consequence; the three verbatim threading criteria; raw RFC 2822 construction; the 100-message-thread construction procedure and the conversation-ceiling hazard; label control. → §3.2 below.
- **Quota arithmetic** (Rev-1 §1.2.7): 6,000 units/min/user/project, per-method costs, 240 inserts/min ceiling, ≈45 min per full corpus, per-project quota isolation. → §3.2.7 below.
- **Scope requirements** (Rev-1 §1.2.8, §1.2.9): `https://mail.google.com/` is required for `batchDelete`; the reset protocol; the credential/scope matrix; the 7-day Testing-status refresh-token expiry. → §3.2.8–3.2.9 below.
- **Flagged risks and their smoke-test gates** (Rev-1 §1.3 S1–S10, §1.6 settle gate, §1.7 regeneration contract, §1.8 risk register, and the feasibility verdict). → §3.3–3.8 below.
- **Metric definitions** (Rev-1 §3 in full): evidence recall and `disclosed()`, irrelevant-context cost, latency protocol, network-level API counting, rounds, FNF with its paired hallucinated-found control, the P1–P5 partiality assertions and extraction-adapter discipline, the per-query trace schema, and the rule that headline metrics derive only from harness-measured + manifest-scored fields. → §6 below.
- **Anti-gaming architecture** (Rev-1 §5 G1–G8 in full): black-box-over-MCP, ground truth confined to the harness, seed regeneration, held-out seed ranges, two-profile discipline, the reviewer gate checklist, the experiment log format, measurement integrity. → §9 below.
- **Benchmark suite** (Rev-1 §2 in full): case schema, corpus shapes, families F1–F10, the position sweep, paraphrase tiers, distractor taxonomy. → §4 below.
- **Baselines** (Rev-1 §4 A–E and the comparison protocol). → §8 below.
- **Freshness probe mechanics** (Rev-1 §7): why not inserts, arms H0–H5, schedule, N ≥ 30 / ≥5 days design, censoring, the 60 s MailWeave-vs-direct-API rule. → §11.1 below.
- **Statistical hygiene** (Rev-1 §8.1) and the Loop 0/1/2/3 numeric proposals, carried into capability gates G0, CG-EP, CG-PD, CG-AD unchanged. → §13 below.
- **The claim rule**: no ground truth → no headline metric. Strengthened, never relaxed.

## Section-number map (Revision 1 → Revision 2)

Preserved blocks keep their Revision-1 internal cross-references (e.g. "§1.2.7", "§2.4", "§9"). Resolve them with this table.

| Rev-1 | Rev-2 | Rev-1 | Rev-2 |
|---|---|---|---|
| §0 purpose/falsifiers | §0 (revised) | §5 anti-gaming | §9 |
| §1.1–1.8 substrate | §3.1–3.8 | §6 execution tiers | §10 (renamed M1/M2) |
| §1.9 personal spot-checks | superseded by §2; quoted in §2.1 | §7 freshness protocol | §11.1 |
| §2 benchmark suite | §4 | §8.1 hygiene | §13.1 |
| §3 metrics | §6 | §8.2 loop exit criteria | §13.3–13.5 |
| §4 baselines | §8 | §9 open questions | §14 |
| — | — | §10 could not verify | §15 |

New in Revision 2: §1 (three-tier methodology), §2 (Tier 1 discovery protocol, including §2.1 on what it replaces and §2.4 on discovery under redaction), §4.7 (new query families), §5 (Tier 3 regression and the sanitization procedure), §6.4 (new metrics), §7 (complete-product coverage), §8.7 (Baseline E promotion) and §8.8 (Baseline F, hit-centred ±2), §9.9 (G9–G12), §11.2 (freshness mitigation trigger), §12 (rubric linkage), §13.2 (bar pre-registration procedure).

---

## 0. Purpose and falsifiability stance (revised)

This plan defines how MailWeave is measured, what would count as failure, and how we prevent ourselves from cheating.

The hypothesis under test (context doc §66):

> For email-agent retrieval, adaptive query-conditioned evidence selection plus progressive context disclosure can preserve or improve answer evidence recall while reducing irrelevant context relative to arbitrary fixed-K previews or full-thread dumps.

Revision 2 adds the complete-product corollaries from `SCOPE_CORRECTION.md`: retrieval must escalate recoverably through lexical → structural → semantic → ranking → progressive expansion (§3), semantic and structural retrieval are in scope (§§4–5), the core path must work with **zero paid API dependency** (Appendix A.1), and freshness is part of the completion bar (§12).

The benchmark must be able to **falsify** all of it. Each falsifier below has a measurement that could show it.

| Falsifier | Where this plan can show it |
|---|---|
| Message-level search + full thread fetch is already good enough | Baselines B and D beat or tie MailWeave on recall AND tokens AND latency (§8, §13) |
| Adaptive routing adds latency without improving retrieval | Escalation 2×2 confusion table + cheap-path latency vs Baseline D (§7.4) |
| Semantic retrieval adds negligible recall | Permanent **SEM-OFF ablation arm** (§7.1). This is now an *ablation*, not a build/don't-build gate — but if the ablation shows no gain anywhere, that is a publishable negative result about the semantic path's value and it constrains every claim we make about it |
| Structural/query-aware disclosure is no better than a fixed window at equal budget | Budget-matched comparison against Baseline F (hit ±2) and Baseline C across ≥3 budget levels (§7.2, §8.8) |
| Ranking machinery is unnecessary | `cut_loss` (pool_recall − disclosure_recall) is near zero without a reranker (§7.3) |
| Progressive disclosure causes more tool calls / worse end-to-end latency than larger context | Rounds + e2e latency vs Baseline B (§6.1, §10) |
| **Agents already manage thread expansion reliably with honest primitive tools** | **Baseline E, both budget variants, every gate** (§8.7). arXiv 2607.17598: gain is "near zero when a strong agent harness already divides and retrieves on its own"; "Progressive disclosure buys context, not intelligence" |
| Evidence is rarely buried enough to matter in real workloads | Tier-1 D1 structural census reports real thread-length / evidence-depth distributions (§2.5) |
| The local semantic default is too weak to be a real default | Backend-arm comparison SEM-LOCAL-DEFAULT vs SEM-HOSTED on identical cases (§7.1) |
| Gmail search is already fresh enough that the freshness story is invented | Freshness protocol arms H0–H2 with depth stratification (§11) |
| MailWeave's real-mailbox behaviour differs from its benchmark behaviour | Tier-1 content-free oracles O1–O9 run against the real mailbox every round (§2.4.5) |

Three ground rules, treated as law:

1. **No claim without a measurement** (context §58). The experiment log (§9, G7) is the only source of claims.
2. **No ground truth, no headline metric.** Tier 1 runs on a mailbox whose relevance judgements we do not own. It may raise BLOCKERs; it may not produce a scored number for a comparison table. (Preserved from Rev-1 §1.9, strengthened in §2.7.)
3. **Representation omission and search freshness stay separate problems** (context §4, SCOPE §12) — separate experiments, separate claims, separate rubric areas. Freshness is no longer *last*, but it is still *separate*.

Hard constraints inherited from `SCOPE_CORRECTION.md` §13 and Appendix A: all measurement runs execute against real Gmail; the seeded corpora live in a **separate dedicated Gmail account** (A.2) so the full-scope seeder credential never touches the personal mailbox; real-mailbox traces persist IDs, metadata, routing decisions, timings, scores and metrics only (A.3).

---

## 1. The three-tier methodology

```
                     TIER 1 — REALITY (primary, discovery)
                     owner's real mailbox, gmail.readonly
                     repeatable protocols D1–D8, content-free oracles O1–O9
                     OUTPUT: findings, BLOCKERs, corpus calibration
                     NEVER OUTPUTS: a scored metric
                                │
                    finding ────┤
                                ├──────────────► TIER 2 — CONTROLLED MEASUREMENT
                                │                dedicated seeded account, ground truth
                                │                families F1–F16, position sweeps, baselines
                                │                OUTPUT: every number this project quotes
                                │
                                └──────────────► TIER 3 — REGRESSION
                                                 sanitized deterministic fixtures
                                                 OUTPUT: the fix stays fixed, forever
```

### 1.1 What each tier is for, and what it may say

| | Tier 1 — Reality | Tier 2 — Controlled | Tier 3 — Regression |
|---|---|---|---|
| **Substrate** | Owner's real Gmail, read-only | Dedicated seeded Gmail account (SCOPE A.2) | Offline bytes + re-seeded cases; no network for F-offline |
| **Ground truth** | None for relevance; definitional truth for structure/counts/IDs | Complete, authored by the harness | Complete, inherited from the originating finding |
| **Primary question** | *What breaks that we did not imagine?* | *How much better/worse, with what confidence?* | *Did the thing we fixed come back?* |
| **May produce** | Findings, BLOCKERs, oracle-violation counts, census parameters, capability-coverage evidence | Recall/token/latency/rank/partiality metrics with CIs; baseline comparisons; all headline claims | Pass/fail per fixture; a green suite is a precondition, not a claim |
| **May NOT produce** | Any recall/precision figure, any comparison table, any headline number | A claim about behaviour on real personal mail that Tier 1 has not corroborated | A claim of general correctness (a fixture proves one bug is gone, nothing more) |
| **Cadence** | Every round; D1/D2 monthly or on mailbox change | Smoke profile inner-loop, full profile at gates | Every commit (F-offline), every gate (F-seeded) |
| **Failure authority** | Can raise BLOCKER (AGENT_LOOP §4) | Can fail a capability gate | Can fail a round |

### 1.2 The flow a failure takes

```
1. DISCOVER    Tier-1 protocol or oracle fires on the real mailbox
2. RECORD      REALITY-FINDING opened (§2.6), content-free by construction
3. TRIAGE      severity + class assigned; enters the AGENT_LOOP findings ledger
4. CHARACTERIZE  delta-debug to a minimal structural predicate
                 (step 2 of the sanitization procedure, §5.2)
5a. MEASURE    if the failure is measurable with ground truth →
               a Tier-2 case template / family extension; now it has a number
5b. PRESERVE   a Tier-3 fixture (F-offline and/or F-seeded) reproducing it
6. FIX         implementer work order (AGENT_LOOP §5)
7. VERIFY      reviewer re-runs the Tier-1 probe on the real mailbox AND the
               Tier-3 fixture AND, where 5a applied, the Tier-2 gate
8. CLOSE       finding closed only with all three; the fixture never leaves the suite
```

**A finding may not be closed without step 5b** (or a recorded, owner-approved `content-dependent, unreproducible` exception with a re-check schedule, §2.6.4). A finding with no fixture is `NOT TESTED` for rubric purposes, and `NOT TESTED` blocks release exactly like `FAIL` (AGENT_LOOP §6).

### 1.3 Why this ordering, stated as a falsifiable assumption

The methodology assumes that **real mail is structurally weirder than anything we would invent, and that most of that weirdness is expressible without its content**. If that assumption is false — if Tier-1 discovery finds nothing Tier-2 would not have found, over several rounds — this ordering is wasted effort and should be reported as such in the experiment log. §15 records this as an unverified assumption of the plan itself. The measurable proxy: the fraction of round-opening findings that originate in Tier 1 versus Tier 2, tracked over rounds.

---

## 2. TIER 1 — Reality: the discovery protocol

**Substrate:** the owner's real Gmail account.
**Credential:** `gmail.readonly` only, in its own GCP project, never the seeder credential (scope matrix preserved at §3.2.9). Mechanical account pinning per `SECURITY_NOTES.md` §2.5: every Tier-1 run asserts `users.getProfile(me).emailAddress` is the *personal* address and refuses to load any destructive code path.
**Authority:** may raise findings and BLOCKERs. May not produce a scored metric.

### 2.1 What Tier 1 keeps from Revision 1, and what it replaces

Revision 1 §1.9 is the ancestor of this section. Reproduced verbatim, it read:

> Purpose: catch ways the synthetic corpus is unrealistically easy (clean prose, shallow quoting, ASCII-only, no mailing lists, no 4 KB `References` chains). **Strictly separated from metric runs**: different credential (`gmail.readonly` only, §1.2.9), never seeded, never deleted from, never scored against a manifest, never in a metrics table.
>
> - **R1 Structural census (automated, aggregate-only).** Distributions of: thread length, body bytes, HTML fraction, quoting depth, attachment types, participants per thread, `References` chain length, thread age span. Output = histograms only; **no message content or addresses persist** to the repo. Used to calibrate generator parameters (recorded as "calibrated to census of <date>") and to answer falsifier 6 (§0): what fraction of real threads are long enough for evidence burial to matter.
> - **R2 Qualitative spot-checks (user-in-the-loop).** 10–20 user-authored queries about their own mail, run through MailWeave interactively; the user verifies answers against the Gmail UI. Recorded in the experiment log as qualitative observations tagged `no-ground-truth`; **prohibited from appearing in any headline claim or comparison table.** Their only sanctioned uses: bug discovery, and a sanity check that synthetic-corpus wins are not synthetic-only.

**Kept exactly:** the separate read-only credential; never seeded, never deleted from, never scored against a manifest; and the prohibition on personal-mailbox observations appearing in any headline claim or comparison table.

**Replaced:** the framing of R1/R2 as an occasional "complement" and "spot-check". R1 becomes D1; R2 becomes D4 with a defined session protocol and verdict schema; and six further protocols (D2, D3, D5, D6, D7, D8) plus nine content-free oracles are added so that discovery is *systematic and repeatable* rather than dependent on whether the owner happened to notice something.

### 2.2 The redaction constraint, restated as law

`SCOPE_CORRECTION.md` Appendix A.3, verbatim and binding:

> Persist IDs, metadata, routing decisions, timings, scores and metrics by default. No full personal email bodies in traces/logs. Short aggressively-redacted snippets may be persisted only when required to diagnose a specific real-mailbox failure. Full bodies remain memory-only during normal execution.

`SECURITY_NOTES.md` §4.3 adds the operational detail this plan adopts wholesale: the personal profile MUST NOT log bodies, snippets, subjects, header values, display names, email addresses, attachment filenames, **or raw query strings** (a user's own `q=` text is itself personal data); error paths count; and profile selection is keyed off the *authenticated account*, not a config flag.

**Two deliberate tightenings** beyond A.3, adopted because they cost nothing:

1. **Raw Gmail message/thread IDs of personal mail are permitted in local traces (A.3 allows them) but are NOT committed to the repository.** They are opaque, but they are working handles into that mailbox for anyone holding a token. Committed artifacts carry the finding ID, the shape record, the oracle vector and salted-hash correlation keys; raw IDs stay in `traces/personal/` (already gitignored per `SECURITY_NOTES.md` §3.3).
2. **The HMAC salt never leaves the machine** and never enters a trace file, a fixture, or the repo (§2.4.3).

### 2.3 The design problem this section solves

Tier 1 must find engineering failures in real mail while persisting no real mail. Naively these conflict: diagnosis usually means looking at the thing that broke.

They stop conflicting once you notice that **almost every failure MailWeave can have is relational or structural, not semantic**:

- "Gmail matched message M; MailWeave's answer neither disclosed M nor represented it" — an ID-set difference.
- "The response claimed the thread has 9 messages; it has 14" — two integers.
- "The HTML body decoded to 4,000 U+FFFD characters" — a count.
- "The quote-stripper removed the newest segment" — a quote-depth run-length vector before and after.
- "An advertised expansion handle returned nothing" — a boolean.

None of those require a single word of the owner's mail to persist. The toolkit below (§2.4) is built so that the *default* diagnostic path is content-free, and content is reached only through a gated escalation ladder that ends outside the repository.

### 2.4 Discovery under redaction: the derived-observable toolkit

**Principle: derive, don't copy.** Every persisted Tier-1 artifact is a function of content that is (a) sufficient to characterize a structural failure and (b) not a vehicle for prose.

#### 2.4.1 The shape record (structural fingerprint)

Computed in memory from a message, persisted in place of it. Fields:

```
mime_tree        type-only s-expression, no filenames, no text:
                 multipart/alternative( text/plain[qp,utf-8,1.4kB],
                   multipart/related( text/html[base64,utf-8,22kB],
                     image/png[inline,cid,88kB] ) )
header_profile   presence/absence vector over a fixed header list; per-header
                 byte-length bucket and cardinality (e.g. References: present,
                 len_bucket=4kB+, count=37; Received: 6; Date: absent)
header_anomalies class ids only: MISSING_DATE, DUP_MESSAGE_ID, MALFORMED_REFS,
                 RFC2047_ENCODED_WORD, 8BIT_HEADER, FOLDED_OVERLONG,
                 NO_CONTENT_TYPE_BOUNDARY, NESTED_RFC822, TNEF, PGP_MIME, SMIME, ICS
encoding_profile declared charset(s), transfer-encodings, detected script class
                 (latin|cjk|cyrillic|arabic|hebrew|mixed), emoji/ZWJ present bool,
                 zero-width char count, bidi-control count
size_profile     raw bytes, per-part bytes, text/html byte ratio, line count
html_shape       tag-name histogram only (no attribute values, no text nodes),
                 max nesting depth, style/script part presence, hidden-text
                 detector class ids
quote_geometry   per-line quote-depth run-length encoding: [0x12, 1x30, 2x8, 0x3]
                 quote_marker_style class id (ANGLE|OUTLOOK_ORIGINAL|GMAIL_ON_WROTE|
                 APPLE|LIST_FOOTER|NONE), quoted_byte_fraction
sig_profile      signature/disclaimer block detected bool, offset bucket, byte share
thread_context   thread message count, position (index by internalDate), age span
                 buckets, participant count, distinct-domain count
```

A shape record is the unit of Tier-1 evidence. It is committable, diffable, and — critically — it is exactly the input the Tier-3 sanitizer needs to build a structurally identical synthetic message (§5.2 step 3).

#### 2.4.2 Aggregate shape statistics

Census outputs are histograms over shape records, with **cell suppression: any bucket with n < 5 is merged into its neighbour** before persistence, so no histogram fingerprints a single unique thread. This is what calibrates the Tier-2 generator ("calibrated to census of <date>", preserved from Rev-1 §1.9 R1) and what answers the "is evidence ever actually buried?" falsifier.

#### 2.4.3 Salted-hash token vocabulary — and its honest limitation

Some diagnostics need term-level correlation without term-level content: *"the third content word of the query occurs in message A and not in message B"*, or *"the same rare token appears in the query and in the message Gmail matched but MailWeave dropped."*

Mechanism: tokenize in memory; `HMAC-SHA256(salt, normalized_token)` truncated to 12 hex; persist only hashes plus positional and statistical information (position index, document frequency bucket, IDF bucket, overlap counts, Jaccard). The salt is generated per machine, stored in the OS keyring alongside the OAuth tokens (`SECURITY_NOTES.md` §3.2), and never written to a trace, a fixture, or the repo.

**Honest limitation, stated because it matters:** these hashes are **pseudonymous, not anonymous**. Natural-language vocabulary is low-entropy; anyone holding the salt can dictionary-invert them trivially. Therefore:

- hashed-token records are `local-only` and live under `traces/personal/` (gitignored) — never committed;
- only *derived aggregates over hashes* (overlap counts, Jaccard, IDF buckets, "the dropped message contained k of the query's n content-word hashes") reach committed artifacts;
- the salt is rotated when the trace directory is purged, which deliberately breaks cross-purge correlation.

This is recorded as an open question for the owner and R-SEC (§14 Q13) rather than assumed acceptable.

#### 2.4.4 Query handling in Tier 1

The owner's own query text is personal data (`SECURITY_NOTES.md` §4.3). Persisted per query: intent class, operator kinds used, token count bucket, content-word count, paraphrase-tier estimate, entity-type classes (PERSON/ORG/DATE/AMOUNT counts, never values), and a salted hash for correlating the same query across systems and rounds. The literal query is **never persisted**. It exists in the engineer's terminal during an ephemeral `mailweave inspect` session (§2.4.6 Stage 1) and nowhere else; if a fixture needs it, it is re-expressed synthetically (§5.2). (Revision-2 repair, CONS-005: the previous wording put the raw query in a persisted forensic buffer, which `SECURITY_NOTES.md` §4.3 forbids outright and `SCOPE_CORRECTION.md` Appendix A.3 does not authorise.)

#### 2.4.5 Content-free oracles (O1–O9)

These make Tier-1 discovery **automatable and repeatable**, which is what turns "poking at the mailbox" into a protocol. Each oracle is a predicate over IDs, counts, timings, and structural invariants. Each runs on every Tier-1 execution (D8 wraps them all). Every violation auto-opens a REALITY-FINDING.

| ID | Oracle | Predicate (all content-free) | Fires on |
|---|---|---|---|
| **O1** | Evidence preservation | For an **exact-operator probe** (`rfc822msgid:`, `from:` + `after:`, `filename:`, `label:`, unique-token) the harness computes Gmail's own hit set `G` via direct `messages.list(q)`. MailWeave's response for the equivalent user query must satisfy `G ⊆ (disclosed ∪ stubbed_with_reachable_handle)` | An ID Gmail itself matched is neither disclosed nor represented — the original bug, measured on real mail. **BLOCKER-eligible** |
| **O2** | Partiality count | `claimed_total == |threads.get(tid, format=metadata).messages|` | A stated total that is wrong. Real threads are where this is hard |
| **O3** | Reachability | Every advertised expansion affordance resolves within the round budget and yields the IDs it promised; no dead handles, no handle that returns a different thread | Progressive disclosure that promises a path it cannot walk |
| **O4** | Identity / liveness | Every disclosed ID resolves via `messages.get(format=metadata)`; its `threadId` and `internalDate` match what the response asserted | Fabricated, stale, or mis-attributed message identity |
| **O5** | Parse fidelity | Structural invariants on extraction: decoded length within bounds of declared part size; `U+FFFD` count == 0; C0-control count == 0; zero unescaped HTML tags in plain-text-typed fields; the depth-0 quote run survives quote-stripping; attachment part count in the response == part count in the MIME tree; declared charset consistent with detected script | Mojibake, HTML leaking into text fields, a quote-stripper eating the newest message, dropped attachments |
| **O6** | Ordering | Any ordering the response claims (chronological, ranked) verified against `internalDate` / the stated rank field | Silent reordering; "latest" that isn't |
| **O7** | Freshness | Message present per `history.list` but absent from a query that should match it (see D6, §11) | Index lag reaching the user as a false negative. **Mitigation-forcing (MF4, §11.2.3)** |
| **O8** | Untrusted-content containment | Byte-provenance taint check: bytes originating in a Gmail API response appear **only** inside designated content leaf fields, always inside the per-response nonce fence (`SECURITY_NOTES.md` §6.3). Verified by field path + taint tracking, not by reading the text | Mail text interpolated into connector-spoken prose — the prompt-injection surface |
| **O9** | Redaction canary | Sentinel tokens injected into the query path and into a synthetic personal-profile message must appear in **no** emitted artifact, including error paths and stack traces | The privacy constraint itself failing. **BLOCKER, always** |

**Honest scoping of O1.** MailWeave's query understanding may legitimately differ from a naive translation of the owner's natural-language query, so O1 binds *only* on exact-operator probes where the correct hit set is unambiguous. On fuzzy natural-language queries the same computation runs but is **advisory** — it opens a finding for triage, not an automatic BLOCKER. This distinction is what keeps O1 from punishing correct behaviour.

#### 2.4.6 The forensic escalation ladder

When an oracle fires and structure alone does not explain it:

> **REVISION-2 REPAIR (CONS-005, BLOCKER).** The Revision-1 ladder's Stage 1 automatically persisted "the offending raw message(s) and full trace, **unredacted**" to `~/.local/state/mailweave/forensics/<RF-id>/` on every oracle fire, and §13.3 made that buffer a G0 exit requirement. Encryption, 0600 modes, gitignoring and a TTL do not authorise it: `SCOPE_CORRECTION.md` Appendix A.3 is binding and permits persistence of **short, aggressively-redacted snippets only** — "full bodies remain memory-only during normal execution". Contract N-05 repeats it; rubric SEC-05 asserts a full suite run leaves no message body, subject or address on disk outside the declared trace policy; `ARCHITECTURE_DECISION.md` resolves T-5/T-SN1 with ID-based re-fetch into memory, never disk, and its D10 type-level redaction gives a `PersonalTrace` no field that can hold mail text at all. §14 Q17 conceded that "a conservative reading of Appendix A.3 favours human-only", i.e. this plan already knew the mechanism was unauthorised. **The buffer is deleted. Stage 1 is now an ephemeral, memory-only inspection session.** Nothing below weakens the diagnostic ladder: Stage 1 still answers "I need to see it to fix it" — it simply never writes it down.

| Stage | What exists | Where it lives | Gate |
|---|---|---|---|
| **0** | Oracle vector + shape records + hashed-token aggregates | Committed to `docs/reviews/` / `experiments/` | Default. No gate |
| **1** | **`mailweave inspect <trace_id>`** — an interactive session that re-fetches the trace's message IDs **live from Gmail into process memory** and prints to the **terminal only** | **Nowhere. Nothing is written to disk**: no forensics directory, no encrypted buffer, no TTL, because there is no artifact to expire. The IDs it re-fetches come from the Stage-0 record, which is content-free | **Owner-approved per incident (OD-4), recorded in the finding**, because the session surfaces real message text. Metadata / ID / timing / structure-only diagnostics — Stage 0, and any `inspect` mode emitting no mail text — need no approval and may be run autonomously by an agent. Never automatic. Transient query-time in-memory retrieval is unaffected. Ends when the process ends. `mailweave inspect` must be built and PF-8 green before G0 closes (§13.3) |
| **2** | A ≤200-char snippet through the redaction pipeline (entity scrub → placeholder substitution → code-applied redaction) | Attached to the REALITY-FINDING | Requires: explicit `--diagnose=<RF-id>` / `--redacted-snippet <RF-id>` invocation naming the finding, **owner approval recorded in the finding**, and R-SEC sign-off at gate. Permitted only when Stage 0 + a Stage-1 session provably cannot characterize the failure. Redaction is applied by **code**, not by the engineer's judgement, and the output path is uncommitted and gitignored (`SECURITY_NOTES.md` T-SN2) |
| **3** | A synthetic fixture with no original bytes | `tests/fixtures/regression/` | The Tier-3 sanitization procedure (§5.2) |

**Why this still works.** Stage 1's diagnostic value was never the persistence; it was the ability to look at the offending message beside its trace. `mailweave inspect` gives exactly that, from IDs, live, in memory — and it is *cheaper* to comply with than the buffer was, which is the point `SECURITY_NOTES.md` T-SN1 makes: build the ID-based tooling before the pressure to relax the rule arrives. Two consequences follow and are handled below: delta-debugging (§5.2 step 2) runs **inside a single inspect session on an in-memory copy**, and the n-gram disjointness check (§5.2 step 6) is computed **against the live re-fetch in that session**, committing only its boolean result and the content hash. Neither needs bytes at rest.

**What is lost, stated plainly.** A failure that is not reproducible from a live re-fetch — because the message was deleted, or Gmail's response changed — cannot be re-examined later. That is a real cost of A.3, not an oversight: it is paid by opening the finding with its Stage-0 record and, if needed, escalating to Stage 2 while the message still exists.

#### 2.4.7 Mechanical enforcement

- Redaction profile selected from the authenticated account, defaulting to the personal (redacting) profile for any unrecognized account (`SECURITY_NOTES.md` §4.3). A config flag can be wrong; the account check cannot.
- O9 canary runs in CI against a personal-profile simulation on every commit.
- CI asserts: no file under `experiments/` or `tests/fixtures/` carries `mailbox_profile: personal` bytes; no salted-hash values in committed files; and — since CONS-005 removed the buffer — **no code path writes message bodies, subjects, addresses or raw query text to any filesystem location on the personal profile at all**, checked by a write-path audit plus a grep gate for any `forensics`-style directory (there is no writer to exempt any more). `mailweave inspect` is covered by the same audit: it must have no disk-writing branch.
- Repo hygiene per `SECURITY_NOTES.md` §3.3: `traces/personal/` gitignored.

### 2.5 The discovery protocols (D1–D8)

Each protocol is a script with a fixed output schema, a cadence, and a named consumer. None of them is "look around and see."

| ID | Protocol | Cadence | Method | Output (all Stage-0) | Consumer |
|---|---|---|---|---|---|
| **D1** | **Real-thread structure survey** | Monthly + at G0 | Stratified sample across thread-length deciles, age, label, participant count; compute shape records + thread_context | Suppressed histograms: thread length, participants, `References` chain length, age span, quoted-byte fraction, near-duplicate density; **evidence-depth feasibility**: what fraction of threads exceed each disclosure budget | Tier-2 generator calibration; the "is burial real?" falsifier; the position-sweep grid's realism |
| **D2** | **MIME / header / encoding weirdness inventory** | Monthly + on any parse finding | Enumerate distinct `mime_tree` signatures and `header_anomalies` classes across a large sample; rank by frequency and by fraction of the mailbox they cover | Signature frequency table; a coverage diff against what the Tier-2 corpus can currently produce | Every uncovered signature ≥ a frequency floor becomes a Tier-2 corpus-extension ticket **and** an O5 run |
| **D3** | **Quoting / signature / boilerplate reality** | Monthly | `quote_geometry` and `sig_profile` distributions; top- vs bottom-posting classification; quoted-byte-fraction ECDF; marker-style class frequencies | Distributions + the classes the parser must handle | Token accounting (a mailbox that is 70% quoted tail changes every token metric); quote-stripping correctness (O5) |
| **D4** | **Real query sessions** | ≥1 session (≥20 queries) per round | Owner authors a query **and its expected answer before running**, held in the session's memory / on the owner's own paper — never written to a repository or state directory (CONS-005); MailWeave and baselines run in blind-randomized order; owner assigns a verdict per system | Per query: intent class, operator classes, query hash, verdict, IDs (local-only), route trace, timings, rounds, tokens. Verdicts: `found-correct`, `found-wrong`, `missed-but-exists` (owner confirms in the Gmail UI), `genuinely-absent`, `ambiguous` | **Every `found-wrong` and every `missed-but-exists` opens a finding.** A `missed-but-exists` on an exact-operator query is an O1 BLOCKER. Verdict counts are diagnostics, never headline metrics |
| **D5** | **Latency / pagination / quota under real conditions** | Every round | Run the real mailbox at its real size: deep `nextPageToken` pagination, threads far larger than seeded ones, cold OAuth refresh, concurrent tool calls, deliberate 429 induction at the documented ceiling | Timings, page depths, HTTP status classes, retry counts, quota units consumed (computed from the §3.2.7 cost table), local-model cold-load time | Performance rubric area; sanity check that Tier-2 latency numbers are not a small-mailbox artifact |
| **D6** | **Freshness observation on real delivered mail** | Continuous, passive | The owner's real inbound mail is *real delivery* — data Tier 2 cannot manufacture. Snapshot `historyId`; on each new message observed via `history.list`, poll whether a body-term and an exact-ID query surface it | Per message: arrival time (H0-equivalent), first-surfacing time per probe class, thread depth at arrival, censoring flag. IDs local-only; aggregates committed | Feeds §11; **O7 violations are mitigation-forcing (MF4)** |
| **D7** | **Untrusted-content survey** | Quarterly + at G0 | Run O8 taint checking over a sample; run injection-pattern *detectors* (hidden text via CSS, zero-width sequences, HTML comments containing imperative-shaped text, bidi controls) and record **class counts only** | Detector class frequencies; O8 pass rate | Prompt-injection rubric area; Tier-3 injection fixtures built from *pattern classes*, never from real text |
| **D8** | **Always-on failure capture** | Every Tier-1 execution | Wraps D1–D7 and any interactive use: all oracles evaluated on every response; on violation, auto-open a finding with shape records + oracle vector + the message IDs needed to re-open it later via `mailweave inspect` (Stage 1) — **no message bytes are captured** (CONS-005) | The finding itself | Nothing is diagnosed from memory or recollection |

**Scheduling.** D4, D5, D8 run every round (they are cheap and they track the diff). D1, D2, D3, D7 run on a slower cadence because the mailbox's *shape* changes slowly — but they must have run at least once before G0 closes, since they calibrate Tier 2.

### 2.6 From a real-mailbox failure to a tracked item to a fixture

#### 2.6.1 The REALITY-FINDING record

Committed. Content-free by construction. Superset of the AGENT_LOOP §4 finding schema, so it drops straight into the findings ledger.

```
ID:              RF-0042
Discovered by:   D2 | D4 | D5 | D6 | D7 | D8 (+ oracle id if applicable)
Date / round:    2026-09-14 / ROUND_03
Substrate:       personal-mailbox (mailbox_profile: personal)
Oracle:          O5.mojibake
Class:           structural | parse | freshness | performance | disclosure |
                 security | retrieval-quality
Severity:        BLOCKER | HIGH | MEDIUM | LOW   (AGENT_LOOP §4 definitions)
Rubric area:     <area name from RELEASE_RUBRIC.md>
Rubric criteria: <the criterion IDs this finding moves, e.g. EV-01, PART-07 — §12>
Observation:     content-free statement of what the oracle computed
Shape record:    <inline or path to the committed shape record(s)>
Oracle vector:   O1..O9 booleans for the failing response
Local trace:     traces/personal/RF-0042/   (gitignored; message/thread IDs, timings,
                 route decisions, oracle vectors — and query *features* + salted hash.
                 NO bodies, subjects, headers, addresses, filenames or raw query text:
                 SECURITY_NOTES §4.3 forbids raw `q=` strings and A.3 forbids bodies)
Re-open with:    mailweave inspect RF-0042   (live re-fetch into memory; nothing persisted)
Minimal predicate: <filled at step 4 of §5.2 — the smallest structural condition
                 that still reproduces>
Promotion:       tier2-case: <template id | none>
                 tier3-fixture: <fixture path | none>
                 exception: <content-dependent-unreproducible + owner approval + recheck date>
Closing evidence: <round + reviewer id + the three verifications of §1.2 step 7>
```

#### 2.6.2 Triage

Within the round in which it opened. Severity by AGENT_LOOP §4. Two Tier-1-specific rules:

- An **O1, O7 or O9 violation is BLOCKER by default**; downgrading requires a reviewer's written argument in the ledger, not the implementer's.
- A `found-wrong` verdict from D4 on a query whose evidence the owner can point to in the Gmail UI is at least HIGH: it is the product's core failure mode occurring on the product's actual target mailbox.

#### 2.6.3 Promotion (mandatory)

Every finding of severity ≥ MEDIUM must produce **at least one** of:

- **(a) a Tier-3 fixture** — preferred, and required for anything with a structural predicate (§5.2);
- **(b) a Tier-2 case template / family extension** — required when the failure is *measurable with ground truth* (a retrieval-quality failure, a ranking failure, a disclosure-policy failure), so that the fix has a number and not only a green test;
- **(c) a recorded exception** — `content-dependent, unreproducible`, requiring owner approval, a re-check schedule, and re-evaluation every gate. Exceptions are counted and reported; a rising exception count is itself a review finding.

Most parse/structural findings take (a). Most retrieval-quality findings take (a)+(b). Freshness findings take (b) in the §11 protocol plus (a) as a reconciliation fixture.

#### 2.6.4 Closure

Per §1.2 step 7: the reviewer re-runs the originating Tier-1 probe against the real mailbox, the Tier-3 fixture passes, and where (b) applied the Tier-2 gate passes on a reviewer-selected held-out seed. Findings are never deleted (AGENT_LOOP §9); fixtures are never removed from the suite.

### 2.7 Tier-1 claim rules

**May be said:** "MailWeave handled N distinct real MIME signatures covering M% of a sample of the owner's mailbox, with zero O5 violations, on <date>." "Zero O1 violations across 312 exact-operator probes on the personal mailbox in ROUND_05." "Twelve findings originated in Tier 1 this round; nine are closed with fixtures."

**May not be said:** any recall, precision, accuracy or comparison figure derived from the personal mailbox; any statement of the form "MailWeave beats X on real mail"; any headline number whose denominator is a relevance judgement we do not own.

**The one bounded exception:** *content-free oracle violation counts* may be reported, because an oracle is definitional (an ID is in a set or it is not; two integers match or they do not) rather than a judgement of relevance. Such counts must always name the substrate, the date, the probe count, and carry the standing caveat that the personal mailbox provides **no ground truth for relevance**.

This preserves Rev-1 §1.9's prohibition exactly. What is new is only that Tier 1 can now *stop a release* — which requires no metric at all.

---

## 3. TIER 2 — Controlled measurement: the seeded substrate

> **PRESERVED — Revision 1 §1.1–1.8, verbatim.** Everything from here to §3.8 is Revision-1 text, unmodified except that section-heading *numbers* were renumbered (1.x → 3.x) and each heading now names its Revision-1 origin. Body text, tables, procedures, citations, smoke-test assertions and the feasibility verdict are untouched. **Cross-references inside these blocks use Revision-1 numbering** — resolve them with the map in the Change Log. Nothing here is re-derived or weakened; Revision 2 adds to it (§3.9) and never subtracts.
>
> One scope fact is now firmer than when this was written: `SCOPE_CORRECTION.md` Appendix A.2 **confirms** the separate dedicated Gmail account as owner-approved policy, so "dedicated test Gmail account" below is a binding decision rather than a proposal, and the full-scope seeder credential provably never touches the personal mailbox.

### 3.1 Design — *verbatim, Rev-1 §1.1*

```
corpus generator (deterministic from seed)
        ↓  users.messages.insert (raw RFC 2822, internalDateSource=dateHeader)
dedicated test Gmail account   ← the only mailbox metric runs touch
        ↓  real Gmail REST / real hosted MCP / MailWeave
systems under test (black boxes)
        ↓
harness scoring against the seed manifest (ground truth never leaves the harness)
```

Ground truth is knowable because we authored every message; realism of the *API path* is preserved because every read goes through real Gmail. The residual realism gap (synthetic prose, synthetic delivery path) is addressed by (a) generator calibration from a real-mailbox census and (b) read-only spot-checks on the user's personal mailbox — both in §1.9, both **excluded from metric tables**.

### 3.2 Verified seeding mechanics (against current Gmail API docs) — *verbatim, Rev-1 §1.2*

All items below were re-verified 2026-08-30 against Google's current documentation and the Gmail v1 discovery document (revision **20260727**, via the googleapis mirror).

**1.2.1 `users.messages.insert` vs `users.messages.import` vs `send`**

- `messages.insert`: "Directly inserts a message into only this user's mailbox similar to `IMAP APPEND`, bypassing most scanning and classification. Does not send a message."
  https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/insert
- `messages.import`: "Imports a message into only this user's mailbox, with standard email delivery scanning and classification similar to receiving via SMTP. This method doesn't perform SPF checks … Does not send a message." Extra params: `neverMarkSpam`, `processForCalendar`. Max message size 150 MB (discovery: `mediaUpload.maxSize` = 157286400 for both insert and import).
  https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/import
- `messages.send` actually delivers mail and costs 100 quota units; **never used for corpus seeding** (only for freshness probes, §7).

**Decision: seed with `insert`.** It is deterministic (no spam classification lottery), cheap (25 units), and mirrors IMAP APPEND semantics. `import` is kept as a fallback lever if inserted mail turns out to behave differently in search indexing (smoke test S8) — if used, always with `neverMarkSpam=true`.

**1.2.2 Controlling apparent dates: `internalDateSource=dateHeader`**

Enum (https://developers.google.com/workspace/gmail/api/reference/rest/v1/InternalDateSource):

- `receivedTime`: "Internal message date set to current time when received by Gmail." — **default for `insert`** (discovery doc `default: receivedTime`).
- `dateHeader`: "Internal message time based on 'Date' header in email, when valid." — **default for `import`** (discovery doc `default: dateHeader`).

`internalDate` "determines ordering in the inbox … for API-migrated mail, it can be configured by client to be based on the `Date` header" (Message resource reference).

**Consequence:** the seeder must pass `internalDateSource=dateHeader` explicitly on every `insert`, otherwise all seeded mail is stamped "now" and every date/temporal query family collapses. Date headers must be RFC-compliant ("when valid"); the smoke test asserts resulting `internalDate` equals the intended epoch ms (S4). Gmail `after:`/`before:`/`newer_than:` operators are evaluated against `internalDate`, and date operators resolve in the account's timezone — case dates keep ≥48 h margins from query boundaries to make timezone skew irrelevant.

**1.2.3 Threading on insert — what the docs actually say**

From the threads guide (https://developers.google.com/workspace/gmail/api/guides/threads) and the `Message.threadId` field reference — quoted criteria, verbatim:

1. "The requested `threadId` must be specified on the `Message` or `Draft.Message` you supply with your request."
2. "The `References` and `In-Reply-To` headers must be set in compliance with the RFC 2822 standard."
3. "The `Subject` headers must match."

So: **yes, you can and must specify `threadId`** in the message resource body when inserting replies, **and** the raw RFC 2822 payload must carry a valid `References`/`In-Reply-To` chain **and** a matching `Subject`. Also verified: "threads cannot be created, only deleted" — a thread comes into existence by inserting its first message (the insert response returns the new `threadId`).

Ambiguity to resolve empirically (S2): the API doc says Subject "must match"; Gmail's conversation-grouping behavior is documented by third parties as tolerating `Re:`/`Fwd:` prefixes. The seeder defaults to the **strictest reading — byte-identical Subject on every message in a thread** — and the smoke test also checks whether `Re: `-prefixed variants thread, so later "realistic" corpora can use them if safe.

**1.2.4 Constructing raw RFC 2822 messages**

Per the sending guide (https://developers.google.com/workspace/gmail/api/guides/sending): build an RFC 2822/MIME message (Python `email.message.EmailMessage` is the reference implementation), base64url-encode, place in the `raw` field. `raw` is "The entire email message in an RFC 2822 formatted and base64url encoded string." Attachments are ordinary MIME parts (S7 verifies they survive insert and are searchable via `has:attachment` / `filename:`).

Seeder conventions:

- **Caller-chosen `Message-ID`** headers, e.g. `<mw-s1042-tA07-m037@bench.invalid>` (RFC 2606/6761 reserved TLD). These are the join keys for ground truth and enable `rfc822msgid:` exact-match probes. Preservation of caller-supplied Message-IDs on insert is asserted by smoke test S3 (see §10 — not explicitly promised by docs).
- All personas are fictional, on `.example`/`.invalid` domains (`priya.n@meridianlabs.example`); `To:` is the test account address. Nothing seeded is deliverable to any real party, and no real person or org is imitated.
- Bodies mix plain text and HTML-with-quoting per the realism calibration (§1.9), including quoted-reply tails, signatures, and mailing-list-ish noise in filler threads.

**1.2.5 Building a 100-message thread with evidence at a controlled position**

```
1. Compose root m1: Subject S, Message-ID M1, Date D1.
   insert(raw=m1, internalDateSource=dateHeader) → {id_1, threadId T}
2. For k = 2..N:
   compose mk: Subject S (byte-identical), In-Reply-To: M(k-1),
   References: M1 … M(k-1), Date Dk (strictly increasing, minutes-to-days gaps),
   body = template slot-filled for role(k)   # role: filler | distractor | evidence
   insert(raw=mk, body.threadId=T, internalDateSource=dateHeader) → {id_k}
3. Verify: threads.get(T, format=metadata) → exactly N messages;
   sort by internalDate; assert sorted order == D1..DN;
   assert Message-ID at target position p == the evidence message's ID.
4. Emit manifest rows: (seed, thread_key, pos, gmail_id, rfc_message_id, date, role).
```

The **evidence position** is therefore controlled exactly: it is the rank of the evidence message in the thread's `internalDate` order, which we set. The harness always *re-derives* position from a post-seed `threads.get` rather than trusting the insert order (verification, not assumption — array order in `threads.get` is not treated as documented).

Known hazard: multiple third-party sources document a **~100-messages-per-conversation ceiling** in Gmail ("There's a maximum of 100 messages per thread/conversation," cloudHQ; Gmail Help describes splitting long conversations). The API docs' three threading criteria mention **no** cap, and whether `insert` with an explicit `threadId` is subject to the UI's split behavior is **unverified** (§10). The standard long thread is exactly N=100 with the deepest target at 99, which sits on this boundary — so smoke test **S6 seeds N=100 and N=105 threads and asserts single-threadId integrity**. Fallback if the ceiling binds at ≤100: shrink the standard long thread to N=90 and rescale positions by fraction (see §2.4).

**1.2.6 Label control**

- `Message.labelIds`: "List of IDs of labels applied to this message" — settable in the `insert` request body (S5 verifies applied-as-given, including `UNREAD`/`INBOX` system labels and custom labels).
- Custom labels via `labels.create` (5 units; scopes `gmail.labels` / `gmail.modify` / full — discovery doc).
- Every seeded message carries two labels: `mw-bench` (account-wide marker: *everything under this label is synthetic*) and `mw-run-<run_id>` (per-corpus instance, the unit of cleanup and of scoring).

**1.2.7 Quotas and rate limits relevant to seeding**

From https://developers.google.com/workspace/gmail/api/reference/quota (fetched 2026-08-30):

- "Per minute per project: 1,200,000 quota units"; "Per minute per user per project: **6,000 quota units**." (Older material cited 15,000/user/min; the current page says 6,000 — treat 6,000 as planning truth, re-confirm in Cloud Console, §10.)
- Method costs: `messages.insert` 25, `messages.import` 25, `messages.get` 20, `messages.list` 5, `messages.modify` 5, `threads.get` 40, `threads.list` 10, `messages.delete` 10, `messages.batchDelete` 50, `labels.create` 5, `history.list` 2, `messages.send` 100.

Seeding throughput ceiling: 6,000 / 25 = **240 inserts/min per user per project**. The full gate corpus (§2.2, ≈8,600 messages) seeds in ≈36 min at ceiling; the seeder targets 80% utilization with truncated exponential backoff on 429/403 rate errors (per docs' recommendation), so **plan ≈45 min per full corpus; ≈12 min for the dev smoke corpus**. This is a bounded, once-per-run cost, not a blocker.

Quota isolation: per-user limits are **per project**, so the seeder and each system-under-test run in **separate GCP projects** where possible; at minimum, seeding never overlaps metric runs (a settle gate sits between them, §1.6). This prevents seeding traffic from contaminating latency measurements and prevents one system's bursts from starving another's quota.

**1.2.8 Cleanup / reset — and the scope it forces**

- `messages.batchDelete`: "Deletes many messages by message ID. Provides no guarantees that messages were not already deleted or even existed at all." Required scope: **`https://mail.google.com/` only** (discovery doc lists no other scope; same for `messages.delete` and `threads.delete`).
  https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/batchDelete
- Scope semantics (https://developers.google.com/workspace/gmail/api/auth/scopes): `gmail.modify` "does not allow immediate, permanent deletion of threads and messages, bypassing the trash"; `https://mail.google.com/` = "Read, compose, send, and permanently delete all your email from Gmail."

**Consequence:** the **seeder credential needs the full `https://mail.google.com/` scope** (a restricted scope). This is acceptable *only* because it is confined to the disposable test account (§1.4). Reset protocol:

```
reset(run_id):
  ids = paginate messages.list(labelIds=[mw-run-<run_id>], maxResults=500, includeSpamTrash=true)
  for chunk in chunks(ids, 1000):        # max ids/call undocumented; 1000 defensive (§10)
      messages.batchDelete(ids=chunk)
  assert messages.list(labelIds=[mw-run-<run_id>]) is empty
  assert getProfile().messagesTotal decreased accordingly
full_wipe():  same, with q="in:anywhere" — legal because the account policy is
              "this mailbox contains only synthetic data, ever."
```

Fallback if full scope is ever unavailable: `gmail.modify` + `messages.trash` + scheduled empty-trash — slower, leaves 30-day residue; acceptable for the test account, noted as degraded.

**1.2.9 Account / OAuth setup**

- Dedicated consumer Gmail account, e.g. `mailweave.bench@gmail.com`. Policy: never used for anything but this harness; contains only synthetic mail; password/2FA in the project secret store.
- One GCP project for the seeder, OAuth consent screen: External + **Testing** publishing status, with the test account (and the user, for §1.9's read-only client) as designated test users. Restricted-scope verification is not needed while in Testing.
- **Operational gotcha (verified):** for External apps in Testing status, refresh tokens expire in 7 days — "a publishing status of 'Testing' is issued a refresh token expiring in 7 days" (https://developers.google.com/identity/protocols/oauth2). The harness must therefore support a scripted weekly re-auth, or the project uses a Workspace account with an Internal app to escape the 7-day expiry. **Decision left to synthesis (§9 Q2), but the harness design assumes re-auth is routine and automates detection of `invalid_grant`.**

**Scope matrix (also an anti-gaming boundary, §5):**

| Credential | Scopes | Held by | Purpose |
|---|---|---|---|
| Seeder | `https://mail.google.com/`, `gmail.labels` | harness only | insert, label, batchDelete |
| System-under-test (MailWeave, Baselines B–E) | `gmail.readonly` (preferred; decision for synthesis) | each system, own project | metric-run reads |
| Hosted-MCP baseline | whatever the Gmail MCP connector requests at sign-in | connector | Baseline A |
| Personal spot-check client | `gmail.readonly` only | user-approved session | §1.9 only; never the seeder scopes |

### 3.3 Verification-first: the substrate is load-bearing — *verbatim, Rev-1 §1.3*

Everything in this plan depends on §1.2 being true in practice, not just in docs. Loop 0 therefore opens with a **seeding smoke test** whose failure is a **loud, work-stopping blocker** (escalate to synthesis; do not quietly work around):

| # | Assertion (run against the live test account) |
|---|---|
| S1 | Insert root + 9 replies with `threadId` + compliant headers → one `threadId`, 10 messages. |
| S2 | Subject variants: byte-identical Subject threads correctly; `Re: `-prefixed variant — record whether it threads (informational, sets corpus policy). |
| S3 | Caller-supplied `Message-ID` is preserved verbatim (`messages.get format=metadata`) and `messages.list(q="rfc822msgid:<...>")` finds it. |
| S4 | `internalDateSource=dateHeader` yields `internalDate` == intended epoch ms for backdated messages (2024–2026 spread); `after:`/`before:` queries bound them correctly. |
| S5 | `labelIds` on insert are applied (custom + `INBOX`/`UNREAD`); `messages.list(labelIds=...)` retrieves exactly the seeded set. |
| S6 | N=100 and N=105 single-thread seeds: all messages under one `threadId` via `threads.get`; if split occurs, record the split point → triggers the §2.4 rescale fallback. |
| S7 | Attachment part survives insert; `has:attachment filename:pdf` matches; attachment downloadable via `messages.attachments.get`. |
| S8 | Search-indexing of inserted mail: measure time from insert until `messages.list(q=<unique body token>)` matches (the **settle time**, §1.6). Record distribution over ≥20 probes. |
| S9 | Reset: label-scoped `batchDelete` empties the run label; `getProfile.messagesTotal` returns to baseline. |
| S10 | Quota behavior at 80% target rate for 1,000 inserts: zero non-retryable errors; log 429 frequency. |

### 3.4–3.5 (consolidated above in Rev-1 §1.2.8–1.2.9)

### 3.6 Corpus settle gate — *verbatim, Rev-1 §1.6*

After seeding and before any metric run: poll a set of 10 sentinel queries (unique body tokens spread across the corpus) via direct `messages.list(q=...)` until all match their expected counts, twice in a row, 60 s apart. Record `settle_seconds` in the run header. **No metric run starts before the gate passes.** This separates "Gmail hasn't indexed the seed yet" from genuine retrieval failure — without it, every recall number is confounded. (Settle time of *inserted* mail is also kept strictly distinct from the Loop 6 freshness experiment, which uses real delivery — §7.)

### 3.7 Corpus regeneration contract — *verbatim, Rev-1 §1.7*

The generator is a pure function: `generate(generator_version, master_seed, size_profile) → (RFC2822 message set, manifest, case set)`. Same inputs → byte-identical corpus. Different `master_seed` → same *shapes* (families, sizes, position grid) but re-randomized names, dates, invoice numbers, subjects, paraphrase realizations, evidence positions, distractor placement. This is the §5.3 anti-gaming lever.

### 3.8 Substrate risk register — *verbatim, Rev-1 §1.8*

| Risk | Severity | Mitigation |
|---|---|---|
| 100-message conversation ceiling splits long threads | High (breaks position sweep) | S6; fallback N=90 rescale (§2.4) |
| Strict Subject matching breaks realistic `Re:` corpora | Low | S2 decides corpus policy |
| Inserted mail indexed differently/slower than delivered mail | Medium | S8 + settle gate; `import` fallback; freshness experiment uses real delivery |
| 7-day token expiry (Testing status) kills scheduled runs | Medium | automated re-auth detection; Workspace/Internal option (§9 Q2) |
| Quota figures change / differ in console | Low | seeder backoff; re-confirm in console |
| Test-account suspension (bulk API writes) | Low-Med | 80% rate cap, backoff, no outbound sending from seeder; second standby account documented in runbook |

**Feasibility verdict: no blocker found in current documentation.** Every mechanism the benchmark needs (raw insert, backdating, explicit threading, labels, deletion, quota headroom) is documented and, where docs are silent, has a designated smoke-test assertion (S1–S10) before anything depends on it.

### 3.9 Revision-2 notes on the preserved substrate

**Reading notes on preserved text.** Two clauses inside the blocks above and in §4 below carry Revision-1 *scope* conclusions that `SCOPE_CORRECTION.md` has superseded. The surrounding factual text is unaffected; only these conclusions are dead:

1. §3.1's parenthetical "(b) read-only spot-checks on the user's personal mailbox — both in §1.9, both **excluded from metric tables**". The *exclusion from metric tables* is preserved and still binds (§2.7). The characterization of personal-mailbox work as a "spot-check" is superseded by §2: it is now the primary discovery tier with blocker authority.
2. §4.3's F4 note "Falsifier for Loop 4: if lexical-only recall is already high, semantic search is unjustified", and §4.5's "T3 … never gate-binding in Loops 1–3". Semantic retrieval is mandatory product scope (SCOPE §4), so high lexical recall no longer makes it "unjustified" — it makes the SEM-OFF ablation's delta small, which is a finding to publish, not a decision to skip a capability. T3 becomes a reported family with a bar pre-registered at G0 (§13.2).

**Additional smoke-test assertions (S11–S14).** S1–S10 (§3.3) are unchanged and still work-stopping on failure. Revision 2's new capabilities depend on four further substrate facts, each with the same escalate-don't-work-around discipline:

| # | Assertion | Why Revision 2 needs it |
|---|---|---|
| **S11** | **Weird-MIME round-trip.** Seed one message per high-frequency MIME/header signature class found by D2 (nested `message/rfc822`, HTML-only with empty `text/plain`, RFC 2047 encoded-word Subject, non-UTF-8 declared charset, 4 KB+ `References`, inline `cid:` images, calendar part). Assert `messages.get(format=raw)` round-trips byte-identically, or record and characterize the delta | Tier-3 **F-seeded** fixtures assume Gmail preserves the structure that caused a real failure. If `insert` normalizes it away, structural fixtures must be F-offline only — a design consequence, not a workaround |
| **S12** | **Delivered reply into a deep thread.** From the second sending account, deliver (not insert) a reply into a seeded 25-message thread; assert it joins the same `threadId` | The freshness depth strata (§11.2.1) require real delivery into deep threads. If delivery does not join seeded threads, the strata must be built from delivered threads and the protocol needs a longer warm-up |
| **S13** | **Attachment-content indexing.** Seed a PDF/CSV whose unique token appears **only inside the attachment**; measure whether `messages.list(q=<token>)` ever matches it, and after how long | F8 scoring currently defines pass as "retrieve the carrying message + signal the attachment". Whether Gmail indexes attachment text decides whether attachment-content retrieval is a MailWeave responsibility or a Gmail capability — an open product question we currently cannot answer (§15) |
| **S14** | **Local semantic backend, offline.** In a container whose egress allowlist permits exactly `gmail.googleapis.com` **and** `oauth2.googleapis.com` (token refresh only) — CONS-002 — and with model loading forced offline (`local_files_only` / `HF_HUB_OFFLINE`) against a checksum-pinned local path: the pinned local embedding model loads **cold**, embeds a fixed input, and the full Tier-2 smoke profile runs to completion with **zero** requests to any other host (the cold load is the point — a warm model would never make the hub revalidation request this assertion exists to catch, ADV-210) (asserted by the counting proxy, §6.1). Record cold-load time, warm inference time, memory and disk footprint, and vector determinism across runs/machines | This is the mechanical proof of `SCOPE_CORRECTION.md` Appendix A.1 ("hosted providers must never be required for core MailWeave functionality"). It is a **definitional** bar — it needs no measurement to set, only to check |

**Corpus additions required by Revision 2** (shapes only; the §3.7 regeneration contract and the §9 G3/G4 seed discipline apply unchanged):

- **Deep threads for freshness strata:** seeded threads of depth 0 / 5 / 25 that a real delivered message can reply into (§11.2.1).
- **Near-duplicate clusters:** 4–6 message families differing in one decisive detail (invoice versions, successive reschedules) for F16 ranking stress (§4.7). D1's near-duplicate density calibrates how many.
- **MIME-signature coverage:** every D2 signature class above the frequency floor gets at least one seeded instance, so parse behaviour has a ground-truth home.
- **Structural/temporal scaffolding:** threads with subject changes mid-thread, forwards that start a new thread, and reply chains that break threading — the F15 material, calibrated from D1.

---

## 4. TIER 2 — Benchmark suite

> **PRESERVED — Revision 1 §2.1–2.6, verbatim.** Heading numbers renumbered (2.x → 4.x); bodies, schemas, tables, counts and construction rules untouched. Internal cross-references use Revision-1 numbering. §4.7–4.8 are new. Two embedded Revision-1 scope conclusions are superseded — see §3.9's reading notes.

### 4.1 Ground-truth case schema — *verbatim, Rev-1 §2.1*

One JSON object per case instance (instances are generated per seed; templates are versioned):

```json
{
  "case_id": "BE-t07-p37-s1042",
  "template_id": "BE-t07",
  "family": "buried_evidence",
  "seed": 1042,
  "query": "When did Priya agree to move the launch date?",
  "query_variants": ["Did Priya ever sign off on shifting the launch?"],
  "evidence": [
    {"ref": "thread:A07/pos:37",
     "rfc_message_id": "<mw-s1042-tA07-m037@bench.invalid>",
     "gmail_id": "<filled by seed manifest>",
     "role": "primary",
     "quote": "Fine — let's move it to October 17.",
     "answer_field": {"date": "2026-03-11", "value": "October 17"}}
  ],
  "evidence_cardinality": "single | all_of | any_of",
  "distractors": [
    {"ref": "thread:A07/pos:12", "type": "lexical_decoy",
     "note": "mentions 'launch date' but is a question, not agreement"},
    {"ref": "thread:B02/pos:3", "type": "cross_thread_decoy"},
    {"ref": "thread:A07/pos:88", "type": "participant_decoy",
     "note": "Marco reports 'Priya seemed OK with it' — hearsay, not Priya"}
  ],
  "position": {"thread_len": 100, "target_pos": 37, "fraction": 0.37},
  "paraphrase": {"tier": 2, "content_word_jaccard": 0.0},
  "expected_behavior": {
    "must_retrieve": ["primary"],
    "acceptable_not_found": false,
    "partiality_expected": true,
    "notes": "Full-thread dump also passes recall; the discriminator is tokens + partiality."
  },
  "scoring": {
    "recall_rule": "evidence message body disclosed (rfc_message_id join)",
    "answer_rule": "date == 2026-03-11 OR contains 'October 17'"
  }
}
```

Notes: `gmail_id` is joined in from the **seed manifest** at seeding time; case files + manifests live only in the harness (§5.2). `expected_behavior.notes` is a required field — it states what would make a pass hollow, which the gate reviewer reads (§5.6).

### 4.2 Corpus shape per seed (full gate profile) — *verbatim, Rev-1 §2.2*

- 84 long threads (100 msgs; one buried-evidence target each — clean attribution), ≈8,400 msgs
- ~20 medium threads (8–30 msgs) hosting decision-evolution, participant, paraphrase, attachment cases
- ~12 short threads + ~40 filler threads (census-calibrated noise, cross-thread decoys)
- ≈8,600 messages total; seeding ≈45 min (§1.2.7); reset ≈10 `batchDelete` calls.

Dev **smoke profile**: 3 buried templates × 7 positions + 2 cases per other family ≈ 2,400 msgs, ≈12 min seed. Inner-loop iteration uses smoke; gates use full (§5.5).

### 4.3 Query families, concretized — *verbatim, Rev-1 §2.3*

Counts are per seed. Every case has ≥1 distractor unless noted; every family includes at least one `query_variants` phrasing.

| Family | n | Construction | Evidence / distractor design | Expected behavior notes |
|---|---|---|---|---|
| **F1 exact lookup** | 10 | Unique token (invoice no., ticket id) in exactly one message body/subject | Distractors: near-collision tokens (A9231 vs A9213) in other threads | Must retrieve the one message; cheap path expected (Loop 3 latency family) |
| **F2 sender/date** | 10 | "What did <persona> send <window>?" — 2–5 qualifying msgs, controlled `internalDate` | Same sender outside window; other senders inside window | `all_of` cardinality; date margins ≥48 h (§1.2.2) |
| **F3 buried evidence** | 12 templates × 7 positions = 84 | Unique factual statement at controlled position in a 100-msg thread | ≥3 distractors incl. same-thread lexical decoy | The position adversary (§2.4). Recall must be position-flat |
| **F4 semantic paraphrase** | 12 | Query and evidence share **no content words** at tier 2 (§2.5); evidence position drawn from grid | Lexical decoys that *do* share the query's words but are wrong | Falsifier for Loop 4: if lexical-only recall is already high, semantic search is unjustified |
| **F5 decision evolution** | 8 | 4-stage chain in one thread: proposal → objection/tentative → **final confirmation** → later reminder (context §23) | The reminder and proposal are built-in distractors | Query asks for the *finalized* decision; correct answer = confirmation msg (`any_of` on {confirmation}; reminder-only = fail) |
| **F6 participant reasoning** | 8 | "What did X say about T?" — X's authored msg is evidence; hearsay ("Y says X agreed") planted | Hearsay distractor is the trap (context §22) | Answer must cite X-authored message |
| **F7 multi-thread** | 6 | Evidence split across 2–3 threads (e.g., decision in one, amount in another); `all_of` | Threads share vocabulary with 2 unrelated threads | Tests cross-thread retrieval + disclosure of *both* sources |
| **F8 attachment** | 6 | Fact exists only in/alongside an attachment (PDF/CSV name or covering message) | Same filename elsewhere with wrong version | Defines pass as retrieving the carrying message + signaling the attachment; content extraction is scored only if MailWeave claims it |
| **F9 freshness** | — | **Not in the core suite.** Runs as the separate Loop 6 protocol (§7) | — | No claims before Loop 6 |
| **F10 unanswerable controls** | 10 | Query with *no* supporting evidence; near-miss distractors present | e.g., asks for a decision that was proposed but never confirmed | Correct output = grounded "not found." Guards against gaming FNF by never saying not-found (§3.1) |

### 4.4 The standing adversary: position sweep — *verbatim, Rev-1 §2.4*

Every F3 template is instantiated at **all** of positions {2, 7, 20, 37, 51, 83, 99} of a 100-message thread (fractions 0.02–0.99). F4/F5 targets also draw their positions from this grid (randomized per seed) so paraphrase and decision cases are simultaneously position-adversarial.

- Per-gate n per position: 12 templates × 2 fresh seeds = 24 cases/position.
- **Position-independence criterion:** report the 7-point recall vector; compute `spread = max − min` and a Cochran–Armitage-style trend check (exploratory). Pass bars in §8 bind on *every* position, not the mean — a system that aces 2/7/20 and fails 83/99 (oldest-K behavior) or the reverse (newest-K) must fail the gate.
- Fallback if S6 finds a <100 split ceiling: thread length 90, positions rescaled by fraction {2, 6, 18, 33, 46, 75, 89}; the fractions, not the absolute indices, are normative.

### 4.5 Paraphrase distance — *verbatim, Rev-1 §2.5*

Recorded per case as `paraphrase.tier` + measured `content_word_jaccard` (stopword-stripped, lemmatized):

- **T0** exact phrase (used in F1).
- **T1** shared keywords, different syntax (jaccard 0.3–0.7).
- **T2** zero content-word overlap; synonym/concept level ("postpone launch" ↔ "push go-live into Q4"). Realizations drawn from a versioned synonym/idiom bank so each seed gets a fresh surface form.
- **T3** stretch set (idiomatic/indirect: "when did we pull the plug?"); reported separately, never gate-binding in Loops 1–3.

### 4.6 Distractor taxonomy (minimum standards) — *verbatim, Rev-1 §2.6*

Every scored family plants distractors from this taxonomy: `lexical_decoy` (shares query words, wrong meaning), `same_thread_near_miss` (proposal vs decision), `cross_thread_decoy` (same vocabulary, different thread), `participant_decoy` (hearsay), `temporal_decoy` (newer-but-weaker evidence, e.g. the reminder). Distractor refs are in the manifest, so "returned distractor tokens" is exactly computable (§3.1).

### 4.7 New families for complete-product coverage (F11–F16)

Same schema (§4.1), same distractor standards (§4.6), same position discipline (§4.4: targets draw positions from the sweep grid so every new family is simultaneously position-adversarial). Counts are proposals in the Revision-1 style, to be adopted by synthesis; they are corpus-design choices, not measurement thresholds.

| Family | n | Construction | Distractor design | What it measures / why it must exist |
|---|---|---|---|---|
| **F11 semantic-with-lexical-trap** | 10 | Query whose naive lexical translation matches a **confident-looking but wrong** message; the true evidence shares no content words with the query (T2) | The lexical decoy is deliberately *stronger* than usual: right vocabulary, right participants, wrong fact | The dangerous escalation case. A system that escalates only on zero/weak lexical hits will never escalate here and will answer confidently wrong. Tests escalation *triggering*, not just escalation *capability* (SCOPE §3) |
| **F12 semantic negative control** | 10 | The semantically nearest message is **wrong**; an exact lexical match is right | Paraphrase-shaped near-neighbours | Guards the degenerate strategy "always escalate to semantic" (§9 G5). Pairs with F1: together they bound both failure directions |
| **F13 temporal-structural** | 8 | "The version we settled on *after* the September review" — requires ordering plus reply-relationship reasoning, not date filtering alone | Pre-decision messages that match lexically and sit inside the date window | Temporal/structural signals as retrieval inputs (SCOPE §5), distinct from F2's date filtering |
| **F14 participant-graph** | 8 | "Who else was on the thread where we discussed X"; "what did the person who raised the objection say later" — participant relations computed live from the thread map | Inherits F6 hearsay traps; adds a same-name-different-address decoy and a reply-all bystander | Participant-aware retrieval **without** a persistent graph (SCOPE §5). Also tests that participant identity is not confused with display name (`SECURITY_NOTES.md` §7.2) |
| **F15 thread-structure reality** | 8 | Subject changed mid-thread; forward that starts a new thread; a reply that broke threading and lives outside the `threadId`; a thread split by the conversation ceiling | The "obvious" sibling thread that is *not* the continuation | The conversation the user means is not always the `threadId` Gmail assigns. Shapes calibrated from D1/D2 — this family exists **because Tier 1 will show these are common**, and its instance mix must be revisited each census |
| **F16 ranking stress** | 8 | 4–6 near-duplicate candidates (invoice v1–v5; four successive reschedules); exactly one is the answer | The other versions — maximally similar, differing in one decisive detail | Isolates **ranking** failure from **retrieval** failure via `cut_loss` (§6.4). Without this family, a reranker cannot be justified or refuted |
| **F17 decision-reversal (adversarial to query-aware selection)** | 8 | A thread whose **highest query-scoring** messages support answer A, and whose **low-scoring later reply reverses it to B**; the correct answer is **B**. Distractors reinforce A, so a policy that selects on query score alone will confidently return A | The reinforcing distractors *are* the trap: they make A look better-evidenced the harder the selector works | **The only test of the non-negotiable E2 reply-chain floor** (T-CD2). `ARCHITECTURE_DECISION.md` makes that floor "non-optional and not budget-negotiable" precisely because query-scored selection can hide the disconfirming message — and until this repair the family that settles it existed nowhere (CONS-007). F5 is the *opposite* shape: it scores the confirmation as the answer. Scored strictly; run in **both** the query-aware arm and the Baseline F(±2) arm, so the floor's budget cost is justifiable rather than asserted |

**F4 extension.** F4-T3 (idiomatic/indirect phrasing) is promoted from "reported separately, never gate-binding" to a reported family with a bar pre-registered at G0 (§13.2). Its realizations continue to come from the versioned idiom bank so each seed gets fresh surface forms (§9 G3).

**F9 unchanged.** Freshness remains outside the core suite and runs as the §11 protocol — separateness preserved (SCOPE §12 keeps representation and freshness as distinct problems), sequencing changed (it is no longer last).

### 4.8 What the new families cost

Adding F11–F16 at the proposed counts adds ~52 cases per seed, most of them hosted in medium threads (8–30 messages) plus one near-duplicate cluster set. Order-of-magnitude corpus growth is a few hundred messages against the ≈8,600-message full profile (§4.2), i.e. **well inside the ≈45-minute seeding budget** computed in §3.2.7 at 240 inserts/min. The smoke profile gains 2 cases per new family. No change to the quota arithmetic or the reset protocol is required.

---

## 5. TIER 3 — Regression: sanitized fixtures from real failures

**Purpose:** a failure that reality found, and that measurement characterized, must never silently return. Tier 3 is where that guarantee lives.

**Constraint:** a Tier-3 fixture is derived from the owner's real mail but must be **safe to commit**. The procedure below is what makes that true, and it is auditable — every fixture ships with a provenance record a reviewer can check without seeing anything private.

### 5.1 Fixture classes

| Class | What it contains | Runs | Use when |
|---|---|---|---|
| **F-offline** | Synthetic raw RFC 2822 bytes + recorded Gmail API response envelopes (IDs rewritten to synthetic), replayed against the server's parsing / representation / disclosure layers with **no network** | Every commit | The failure is in *our* code: parsing, MIME handling, quote stripping, partiality computation, fence containment, ranking given a fixed candidate set |
| **F-seeded** | A case template added to the Tier-2 generator, seeded into the dedicated account, scored against the manifest | Every gate (and smoke when cheap) | The failure involves *Gmail's* behaviour: search matching, threading, indexing, pagination, freshness, attachment handling |
| **F-both** | Both of the above for one finding | As above | Anything where the boundary between our bug and Gmail's behaviour is itself in question — which is most retrieval findings |

**Injection fixture classes.** The `I1` suite carries instructions in body, subject, display name, filename and hidden HTML. Revision 2 adds one class that the corrected scope makes unavoidable:

- **`I1-bait` — embedding-bait and keyword-stuffing fixtures (new, CONS-014).** A message crafted to score highly against *many* queries: dense topic-word stuffing, paraphrase-shaped padding, and text tuned to sit near the centroid of the query space. **Assertions:** (a) it does **not displace true evidence from the disclosed prefix**, compared pairwise against the identical corpus without it; (b) its **selection reason and `model_id@revision` are visible** in the response (P6 / rubric SEM-06); (c) it is **neither dropped nor unfenced** — a matching bait message is still retrieved and disclosed, fenced (rubric INJ-03 clause (b); dropping matching evidence is an EV-01 violation). This class is the standing consequence of putting semantic retrieval on the *default* path (`SECURITY_NOTES.md` addendum T-SN3, §5.3): it was named in ARCHITECTURE and SECURITY_NOTES and existed in no fixture inventory here, so INJ-03's fixture set did not include the attack the local semantic default introduces.

Every REALITY-FINDING of severity ≥ MEDIUM produces at least one (§2.6.3). A finding whose only artifact is a code change is not closed.

### 5.2 The sanitization procedure

Eight steps. Steps 1–4 are the normal path; step 5 is a gated exception; steps 6–8 always run.

**1. Capture (Stage 0, content-free).** The oracle fires; the harness records the oracle vector, the shape record(s), and the **message IDs** — and nothing else. No message bytes are written anywhere (CONS-005). The finding is now re-openable at any time via `mailweave inspect <RF-id>`, which re-fetches those IDs live from Gmail into process memory.

**2. Characterize — delta-debug to a minimal structural predicate.** **Inside a single `mailweave inspect` session, on an in-memory copy only**, iteratively remove MIME parts, headers, header values, and body line-ranges, re-running the oracle after each removal, until removal stops reproducing the violation. The session writes nothing; only the resulting predicate — a structural statement with no content in it — leaves the process. Output: the smallest structural condition that still fails — e.g. *"`text/html` part with declared `charset=iso-8859-1` containing an RFC 2047 encoded-word in a `Content-Disposition` filename, quote depth ≥ 2"*. This step is the heart of the procedure: it converts a failure that *looked* content-dependent into a structural one. Record the predicate in the finding.

**3. Re-express — structure-preserving synthesis.** Generate a synthetic message with the **identical shape record** (§2.4.1): same MIME tree and part order, same declared charsets and transfer encodings, same header set and anomaly classes, same quote-depth run-length profile and marker style, same per-part byte-length class (±5%), same attachment count and types. All prose comes from the Tier-2 persona/template banks; personas are fictional on `.example` / `.invalid` domains (§3.2.4). **No original bytes are copied — not a sentence, not a phrase, not a subject line.**

**4. Verify fidelity.** Run the oracle against the synthetic fixture. It must (a) **reproduce** the violation on pre-fix code and (b) **pass** on post-fix code. Both results are recorded in the fixture's provenance. If (a) fails, the failure was not purely structural → step 5.

**5. Content-dependent escape hatch (gated, rare).** In order, stopping at the first that works:

   1. **Reduce to a feature, not a sentence.** Identify the minimal *content feature* — a codepoint sequence, a zero-width or bidi control, an emoji ZWJ cluster, an encoded-word charset, a URL shape, a specific line-length — and rebuild synthetic prose *around that feature*. A codepoint is not personal content; a sentence is.
   2. **Widen the fingerprint.** Add the discriminating structural attribute the shape record was not capturing, and extend the shape-record schema for everyone (this is how the toolkit improves).
   3. **Redacted snippet (Stage 2).** Only if 1 and 2 both fail: a ≤200-character snippet through the redaction pipeline, requiring the explicit `--redacted-snippet <RF-id>` invocation, **owner approval recorded in the finding**, and R-SEC sign-off at the gate.
   4. **Exception.** If even that cannot reproduce it, record `content-dependent, unreproducible` with a re-check date (§2.6.3c). The finding stays open. Open exceptions are counted every gate and a rising count is itself a review finding.

**6. Scrub and assert (mechanical, in CI).** The fixture does not land until all of these pass:

   - no address outside `.example` / `.invalid`; no real domain literal anywhere;
   - no salted-hash values, no personal Gmail message/thread IDs, no `historyId` from the personal mailbox;
   - dates re-based onto the synthetic corpus epoch;
   - **n-gram disjointness:** computed locally **inside a `mailweave inspect` session against the live re-fetched original**, the fixture shares **no contiguous 8-token n-gram** with any original message. The check runs in memory on the engineer's machine; only its boolean result and a salted content hash of the original are committed — the original itself is never written to disk (CONS-005). If the original message no longer exists in the mailbox, the check cannot be run and the fixture does not land: record the exception per step 5.4;
   - the O9 canary passes with the fixture in the suite;
   - `PROVENANCE.md` present and complete.

**7. Approve and commit.** `tests/fixtures/regression/RF-XXXX/` contains the fixture plus `PROVENANCE.md`: originating finding, oracle, discovery protocol, minimal structural predicate, fidelity result (reproduces-before / passes-after), the scrub assertion results, whether step 5 was used and at which sub-step, and the approving owner/reviewer. A reviewer can audit the whole chain without seeing anything private — that is the design goal.

**8. Purge — now a no-op by construction.** There is nothing to purge: no buffer exists, so no message bytes ever came to rest and none can outlive the diagnosis (CONS-005). What remains is the content-free Stage-0 record, the fixture, and any Stage-2 redacted snippet, which is uncommitted, gitignored and covered by its own owner approval and R-SEC sign-off. The CI write-path audit of §2.4.7 is what keeps this true as the code changes.

### 5.3 The assumption this procedure rests on, stated plainly

Steps 2–4 assume **most real-mail failures are structural, and structure is transferable to synthetic content**. That assumption is unproven (§15). Step 4 measures it directly: the **structural reproduction rate** (fraction of findings whose synthetic fixture reproduces the original violation without step 5) is reported every gate. If it runs low, the plan is wrong about email failures and the escape hatch is carrying weight it was not designed to carry — which is a methodology finding worth publishing, and a trigger to revisit the privacy/diagnosis trade-off with the owner rather than to quietly widen step 5.

### 5.4 Lifecycle

- Fixtures are **never deleted** and never quarantined to make a build green. A fixture that starts failing is a regression, not a flaky test.
- F-offline fixtures run on every commit; F-seeded fixtures on every gate, on the gate's fresh HOLDOUT seed (§9 G4/G5) — a fixture that only passes on its original seed is measuring memorization, not the fix.
- Each fixture names the rubric area of its originating finding, so the regression suite is directly readable as rubric-area coverage (§12).
- Fixtures derived from personal mail carry `derived_from: personal-mailbox-structure` in provenance, so the set is auditable as a whole, and R-SEC re-checks the set at every release gate (§14 Q15 asks whether such fixtures may live in a public repo at all).

---

## 6. Metrics — precise definitions

> **PRESERVED — Revision 1 §3.1–3.3, verbatim.** Heading numbers renumbered (3.x → 6.x); every definition, formula, assertion table, classification rule and trace field is unchanged. This includes the two rules that make the whole plan honest: **FNF and hallucinated-found are always reported together**, and **headline metrics derive only from harness-measured + manifest-scored fields**. §6.4 adds metrics for capabilities Revision 1 did not cover; it adds nothing that weakens what is below.

All metrics are computed by the harness from (a) the recorded MCP transcript, (b) the network-level Gmail API call log (§3.3), and (c) the seed manifest. Notation per case: required evidence set `E`, disclosed message set `D`, thread true length `L`.

### 6.1 Core metrics — *verbatim, Rev-1 §3.1*

- **Evidence recall (per case):** `|{e ∈ E : disclosed(e)}| / |E|`. `disclosed(e)` is true iff the response contains the message's body content (at minimum the manifest `quote` span, whitespace-normalized) attributable to that message (rfc-Message-ID or Gmail id join). An id/snippet-only stub is **not** disclosure; it is counted separately as `surfaced_not_disclosed` (a legitimate progressive-disclosure state — but recall is only earned when the driver can reach the content within the round budget, §6.1).
  - **Case recall (strict):** 1 iff all `must_retrieve` evidence disclosed (for `any_of`: at least one qualifying).
  - Aggregates: mean per family, per position, overall; Wilson 95% CIs.
- **Irrelevant-context cost:**
  - `tokens_returned`: tokenizer-pinned (single tokenizer version recorded in the run header; same for all systems) count of all message-content tokens disclosed for the case, summed over rounds.
  - `relevant_token_fraction` = evidence-message tokens / total disclosed content tokens.
  - `distractor_tokens`: tokens from manifest-listed distractor messages (diagnostic of ranking quality, not just volume).
- **Latency:** wall-clock per round and per case (sum of rounds), measured at the MCP client boundary. Report p50/p95 per family and overall; cold (first query after settle) vs warm reported separately; systems interleaved round-robin per case with randomized order to neutralize time-of-day and index-warmth (§4.6).
- **Gmail API calls per query:** counted at the **network level** — each system-under-test runs with its HTTPS egress through a harness-owned counting proxy (mitmproxy-class; CONNECT/SNI count to `gmail.googleapis.com`, plus request-path tallies where TLS interception is configured). Self-reported counters (if MailWeave emits them) are recorded as `self_reported_api_calls` and cross-checked; a persistent mismatch is flagged at gate review. Hosted-MCP Baseline A gets `n/a` (calls happen inside Google) — noted asymmetry (§4.1).
- **Retrieval rounds:** number of MCP tool invocations the driver issued for the case (Tier-1 driver policies fix the maximum, §6.1).[^rounds]

[^rounds]: *Preserved-block footnote (CONS-039).* Read this Revision-1 sentence as "**M1** driver policies fix the maximum, **§10.1**". "Tier-1" here is Revision 1's *execution-mode* label, renamed M1 in Revision 2 (change-log item 10), and it collides with Revision 2's Tier 1 = the reality substrate; "§6.1" was Revision 1's own §3.1 self-reference and now resolves to this very section. The verbatim text is left standing per the preservation rule; the resolution lives here.
- **False "not found" rate (FNF):** over answerable cases, fraction whose terminal response asserts nonexistence/unavailability of the evidence. Classification: (a) if the response schema carries an explicit machine-readable not-found/empty-result field, use it; (b) else a pinned LLM classifier with a 3-label rubric {answered, not_found, other}, blind to system identity, validated once against 50 hand-labeled transcripts (report agreement ≥0.9 before use).
  - **Paired control — hallucinated-found rate:** over F10 unanswerable controls, fraction *not* classified not_found (i.e., the system invented support). **FNF and hallucinated-found are always reported together** so neither can be gamed by shifting the threshold.

> **Preserved-block extension (OD-2, VERIFICATION_2 B-1).** The classification vocabulary above is extended to **`answered | not_found | inconclusive | other`**, taken from `retrieval_report.outcome` (`ARCHITECTURE_DECISION.md` D.2) when present and from the classifier's fourth label otherwise. **`inconclusive` is excluded from FNF** — it asserts no nonexistence — and is **reported as its own separate rate, always alongside FNF and hallucinated-found**, so the three cannot be traded off invisibly. Nothing above is relaxed: FNF's definition and its paired control are unchanged.

### 6.2 Partiality transparency — mechanical assertions (no vibes) — *verbatim, Rev-1 §3.2*

Per system, a small **extraction adapter** (written once, frozen and reviewed at gate time, §5.6) maps its response format to a normalized record: `claimed_total`, `included_ids/positions`, `more_available_signal`, per-message `role_tag`, `content_type_tag`. The assertions then run mechanically per case:

> **Field-name mapping (CONS-023).** `claimed_total` **:=** the response's `stated_total` — the wire-schema field named by contract R-05 and `ARCHITECTURE_DECISION.md` D.2. They are one quantity with two names across the measurement boundary: `stated_total` in the response, `claimed_total` after adapter normalisation. Since P1/P1a are scored *through* the frozen adapter, this is exactly where an adapter bug could hide, so the mapping is stated once here and once in the rubric's How-to-use rather than left implicit.
>
> **Assertion-ID mapping (CONS-011).** `RELEASE_RUBRIC.md`'s `PART-0n` criterion IDs are **independent** of this table's `P-n` assertion IDs: PART-01 → P1/P1a, PART-02 → P2, PART-03 → P3, PART-04 → O3 + the P-follow driver, PART-05 → contract R-06, PART-06 → the end-to-end probe below, **PART-07 → P4 + P6**. A reviewer reading "P4 ≥ 0.95" against rubric PART-04 would be applying a bar that belongs to a different assertion.

> **Two more normalisations inside the preserved table below (CONS-033).** P3's phrase "cursor / named tool / explicit flag" predates the handle decision: the canonical affordance is a **server-minted `map_id` passed as an ordinary tool argument** (contract N-MCP-2; `ARCHITECTURE_DECISION.md` D.1/A.10). "Cursor" is retired — no design in this set produces one — and an adapter must not accept a bare cursor as satisfying P3. And the per-message field the adapters expose as `role_tag` normalises the wire field **`reason`** (contract R-03), which `CONTEXT_DISCLOSURE_OPTIONS.md` §5 calls `role_reason`: one concept, one wire name.

| ID | Assertion | Pass condition |
|---|---|---|
| P1 | Stated total present | `claimed_total` extractable for the focal thread |
| P1a | Stated total **correct** | `claimed_total == L` (manifest truth) |
| P2 | Included subset identified | extracted `included` set == messages actually present in the payload |
| P3 | More-available signaled | if `|D| < L`: a machine-actionable affordance (cursor / named tool / explicit flag) present; if `|D| == L`: affordance absent or explicit "complete" |
| P4 | Role and reason marking | every disclosed message carries a `role` from the **full closed seven-value set** `{matched, context, parent, child, requested, stub, derived}` (contract R-02; `ARCHITECTURE_DECISION.md` D.2) **and** a non-empty mechanical `reason` naming the mechanism (contract R-03); disclosed manifest evidence is tagged `matched`. Scored across all seven values — the Revision-1 three-value set (matched / context / derived) was narrower than the contract it was measuring, so a role-less or reason-less response could pass (CONS-008). Moves rubric **PART-07** |
| P5 | No silent derivation | any summary/derived text carries a derived-content tag and is never presented as message body |

Scored as per-case booleans → pass rates with CIs. **P2 and P3 are mechanical self-consistency assertions, not statistical ones, and their bar is therefore 1.00, not ≥0.98** — the rubric (PART-02, PART-03) already made that choice and CG-PD has been raised to match rather than the rubric lowered, because "the response's own account of what it contains is accurate" either holds or is a defect (CONS-011). Baselines B/C/D run through their own adapters and will **structurally fail** most of P1–P5 (a full dump trivially passes P1a/P3-complete; fixed-K fails P1/P3) — that contrast *is* the measurement of the Partiality Invariant's value, per context §39.

**End-to-end partiality probe (judge-free):** in Tier-2 runs, after the answer the driver always asks the scripted follow-up: *"How many messages does that thread contain in total, and how many did you actually see?"* The agent's two numbers are compared to `L` and `|D|` exactly. Pass = both correct or explicitly declared unknown; fail = confidently wrong or claims completeness while partial. This tests that partiality metadata survives into agent understanding, mechanically.

### 6.3 Per-query trace schema (context §35, made concrete) — *verbatim, Rev-1 §3.3*

Recorded for every (system, case, round):

```
run_id, seed, system, system_version, case_id, round_no
# measured by harness (authoritative):
latency_ms, gmail_api_calls_network, mcp_tool_name, request_bytes, response_bytes,
tokens_returned, disclosed_message_ids, rounds_total, terminal_class(answered|not_found|other)
# scored against manifest:
target_retrieved (bool per evidence), target_rank (if system exposes ranking; else null),
false_not_found, P1..P5, surfaced_not_disclosed
# self-reported by server via optional debug channel (diagnostic ONLY, never headline):
initial_route, final_route, fallback_triggered, routing_recovery_success,
candidate_count, ranking_depth, context_expansions, full_thread_fetch_required,
internal_model_calls, self_reported_api_calls
```

> **Preserved-block extension (OD-2, VERIFICATION_2 B-1).** `terminal_class` takes a fourth value: `terminal_class(answered|not_found|inconclusive|other)`, sourced from `retrieval_report.outcome` (`ARCHITECTURE_DECISION.md` D.2) where the system emits it. `false_not_found` is scored only against `not_found`, per §6.1.

Rule: **headline metrics derive only from harness-measured + manifest-scored fields.** Self-reported route fields exist to debug failures (context §53 "inspect retrieval traces") and may not appear in claims except labeled as self-reported diagnostics.

### 6.4 Additional metrics for the complete product (new)

All computed the same way: harness-measured or manifest-scored, never self-reported (§6.3's rule binds these too). Self-reported route fields may corroborate, never substitute.

**Retrieval vs ranking split** — the single most useful new diagnostic:

- `pool_recall` — fraction of required evidence present in the system's **pre-disclosure candidate set** (where the system exposes one; otherwise the union of messages it fetched, observable at the network layer).
- `rank_of_evidence` — rank of the first required evidence item in that candidate set.
- `cut_loss = pool_recall − recall` — evidence that was retrieved and then lost at the ranking/disclosure cut. **A reranker is justified by the `cut_loss` it removes, and by nothing else.**

**Escalation behaviour** (per case, from `route_sequence` cross-checked against network-observable calls):

- `escalated` (bool), `escalation_stages` (ordered), `stop_reason` per stage, `budget_consumed`.
- **Escalation confusion table**, computed over all answerable cases: rows = *cheap path alone would have sufficed* (yes/no, determined by running the SEM-OFF / lexical-only arm on the same case), columns = *did escalate* (yes/no). The two off-diagonal cells are the two failure modes, and naming them is the point:
  - **over-escalation** (cheap path sufficed, escalated anyway) → an Adaptive Cost Invariant violation, paid in latency and quota;
  - **under-escalation** (cheap path insufficient, did not escalate) → the dangerous one: a confidently wrong or falsely-not-found answer, a Recoverability Invariant violation.
- `recovery_rate` — of cases where the first route failed to surface evidence, the fraction recovered by any later stage (preserved from Rev-1 Loop 3, generalized past the single fallback).
- `escalation_cost` — marginal latency, network API calls, quota units and tokens attributable to escalation, reported as a distribution, not a mean.

**Disclosure-depth metrics (new, CONS-006):**

- `levels_traversed_to_answer` — the number of distinct disclosure levels the driver had to traverse before the evidence was in hand: the flat/segment map, each separately-requestable content depth (`snippet`, `body_clean`, `body_full`, `raw`), and each map-handle redemption. Counted from the MCP transcript, per case, per arm. `CONTEXT_DISCLOSURE_OPTIONS` T-CD1 asks for exactly this as "a first-class metric", and without it DISC-05's depth-*n* vs depth-*(n−1)* comparison has no dependent variable.
- `map_tokens` — tokens spent on map/index structure rather than message content, separated from `tokens_returned` so a deeper level cannot be judged on content savings it did not produce.

**Semantic-path metrics:**

- `semantic_gain` — paired per-case recall delta between an arm and the SEM-OFF ablation on identical instances (McNemar, per §13.1).
- `embedding_latency` split into **cold-load** and **warm inference** (cold model load is a real user-visible cost and Revision 1 never measured it).
- `pool_fetch_cost` — messages fetched to build the candidate pool, in API calls and quota units (`RETRIEVAL_OPTIONS.md` Option B: 100 candidates × 20 units ≈ one third of the per-minute user budget — this must be visible, not implicit).
- `non_google_egress_bytes` — measured at the counting proxy (§6.1). **Must be 0 for the default configuration.** Definitional, not empirical.
- `backend_parity` — per-family recall delta between SEM-LOCAL-DEFAULT and SEM-HOSTED on identical instances, with CI.

**Provenance and freshness assertions** (extending the P1–P5 table of §6.2, same mechanical style, same extraction-adapter discipline):

| ID | Assertion | Pass condition |
|---|---|---|
| **P6** | Selection provenance | Every disclosed message carries how it was selected (`lexical_hit` / `structural` / `semantic_similarity` / `thread_context`). A semantically-selected message is **never** presented as a Gmail search hit, and a similarity score, if shown, is labelled as similarity — not as confidence (`RETRIEVAL_OPTIONS.md` Option B honesty obligation) |
| **P7** | Temporal partiality | When the result depends on the search index and the index may not include very recent mail, the response says so in a machine-readable field. Required **regardless** of what the freshness experiment finds, because a measured median is not a per-query guarantee (§11.2.5) |

**Tier-1 counters** (content-free, from §2.4.5; never a headline metric, always substrate-labelled): per-oracle violation counts and probe denominators; MIME-signature coverage; structural reproduction rate (§5.3); open-exception count.

---

## 7. Coverage for the complete product

Revision 1 deferred four capabilities behind conditional gates. `SCOPE_CORRECTION.md` §§1, 4, 5, 8, 12 makes them mandatory. This section specifies how each is measured. Where a threshold cannot be honestly set before measurement exists, it is marked **UNSET** and §13.2 defines how it gets pre-registered — no number here was invented to fill a gap.

Throughout, bars fall into three classes:

- **Definitional** — settable now, because the criterion is structural or binary (zero egress, no unexplained not-found, provenance labelled). These need measurement only to *check*, not to *set*.
- **Inherited** — carried forward from Revision 1's proposals unchanged (Loop 1/2/3 bars → CG-EP / CG-PD / CG-AD).
- **UNSET-empirical** — requires a G0 baseline distribution before a bar can be honest.

### 7.1 Semantic retrieval

**Why it is measured at all, now that it is mandatory.** Making a capability mandatory does not make it good. The measurement question changes from *"should we build it?"* to *"does what we built earn its cost, and where does it fail?"*.

**Arms (identical case sets, paired scoring, §8.6 comparison protocol):**

| Arm | What it is | Status |
|---|---|---|
| **SEM-OFF** | Lexical + structural only | **Permanent ablation.** Not a decision gate any more — the reference point for `semantic_gain` |
| **SEM-LOCAL-DEFAULT** | The shipped default local model, pinned by name + revision hash + quantization in the run header | The configuration users get. Every headline semantic claim is about **this** arm |
| **SEM-LOCAL-ALT** | A second local model | Proves the interface is genuinely provider-agnostic and that results are not one model's idiosyncrasy |
| **SEM-HOSTED** | An optional hosted embedding/reranking provider | Opt-in, off by default. Benchmarking and explicit user opt-in only (SCOPE A.1) |

**Cases:** F4 (T1/T2/T3), F11 (semantic-with-lexical-trap), F12 (semantic negative control), plus F1/F2 as the cost-regression control. All position-adversarial via the §4.4 grid.

**Definitional bars (settable now, checked by S14 and the counting proxy):**

1. The default configuration makes **zero** requests to any non-Google host — `non_google_egress_bytes == 0` across the full suite.
2. The default configuration requires **no API key and no paid account**: the full Tier-2 smoke profile completes in an egress-allowlisted container permitting **exactly two hosts — `gmail.googleapis.com` and `oauth2.googleapis.com` (token refresh only)** — and no other. (Revision-2 repair, CONS-002: a container permitting `gmail.googleapis.com` only cannot refresh an OAuth token and therefore cannot complete the suite; the substantive assertion — no analytics, no crash reporting, no update checks, no query-time model download, zero mailbox bytes to any non-Google host — is unchanged and unweakened.) Model weights are provisioned at **setup time only** from a declared model-host, and runtime loading is **forced offline** (`local_files_only=True` / `HF_HUB_OFFLINE=1`) from a checksum-pinned local path, because the `sentence-transformers` / `huggingface_hub` default load path otherwise issues a hub revalidation request that this bar would catch as a violation (ARCH_REVIEW ADV-210).
3. The hosted arm is **off by default**, requires explicit opt-in, and its use is visible in the response provenance.
4. Semantic escalation does **not** fire on F1 exact-lookup cases (Adaptive Cost Invariant), and F1/F2 latency is unchanged with the semantic path installed but not triggered.
5. Every semantically-selected message satisfies **P6**: labelled as inferred relevance, never as a Gmail search hit.

**UNSET-empirical bars** (pre-registered at G0 per §13.2): `semantic_gain` on F4-T2/T3 and F11 relative to SEM-OFF; the acceptable `backend_parity` gap between SEM-LOCAL-DEFAULT and SEM-HOSTED; the F12 over-escalation ceiling; the p95 latency budget for the escalated path. Each is registered as a **delta against the G0-measured SEM-OFF distribution on the same held-out seed**, because no honest absolute number exists before that measurement.

**The parity honesty rule.** If SEM-HOSTED beats SEM-LOCAL-DEFAULT, the gap is published, and the README may not claim local parity. If the gap exceeds the registered tolerance, the required action is **to improve the local path** (different local model, better pooling, hybrid lexical+semantic rank fusion) — not to change the default. Hosted may never become required (SCOPE A.1).

**Architecture questions this measures but does not pre-judge** (SCOPE §11): on-demand embedding vs a persistent index is decided by measured latency/quota/freshness cost, and any persistent index must carry the staleness metadata and resync path of `SECURITY_NOTES.md` §4.2 — an index that can serve stale content re-creates the exact failure MailWeave exists to prevent, so its freshness is measured by the §11 protocol like any other arm.

### 7.2 Structural, participant and temporal retrieval

**Cases:** F5 (decision evolution), F6 (participant/hearsay), F7 (multi-thread) — all promoted from conditional to gate-mandatory — plus F13 (temporal-structural), F14 (participant-graph), F15 (thread-structure reality).

**The comparison that matters: equal budget.** `SCOPE_CORRECTION.md` §6 makes fixed ±2 a baseline, and the query-aware policy must be measured against it **under an identical context budget**. Otherwise "query-aware beats fixed window" degenerates into "spending more tokens beats spending fewer". Therefore:

- The comparison is a **budget–recall curve**, not a point: sweep ≥3 context budgets (proposed: tight / nominal / generous, values set from the §6.2 token accounting at G0) and plot recall and `relevant_token_fraction` for the query-aware policy, Baseline F (hit ±2, §8.8) and Baseline C (fixed K) at each budget.
- The claim MailWeave is allowed to make is exactly the shape of that curve: *at matched budget B, policy P achieves recall R*. Anything else is a token-spend argument dressed as a retrieval argument.

**Structural signal coverage.** SCOPE §5 names reply relationships, participant relationships, temporal relationships, thread position, subject/snippet relevance, and multi-thread relationships. Each must have at least one family whose *correct* answer requires that signal and whose distractors defeat the others: F5 (reply chain + decision ordering), F13 (temporal + reply), F14 (participant), F7 (multi-thread), F15 (thread position/identity), F3 (subject/snippet under burial). A signal with no such family is untested and its rubric area cannot pass.

**No persistent graph is required or forbidden** (SCOPE §5). If one is built, it is an index and inherits the §7.1 staleness obligations.

**Bars:** inherited where Revision 1 set them (F5/F6/F7 accuracy is folded into CG-PD/CG-AD via strict case recall); UNSET-empirical for F13/F14/F15 and for the budget–recall curve, pre-registered at G0 against the Baseline F curve measured there.

### 7.3 Candidate ranking

Ranking is only meaningful where candidates are ambiguous, so it is measured where ambiguity is manufactured: **F16** (near-duplicates), plus F4/F11 (semantic pools) and F7 (cross-thread pools).

- Report `pool_recall`, `rank_of_evidence` (MRR and recall@k over the candidate pool), and `cut_loss` (§6.4) for every system that exposes or can be observed to build a candidate set.
- **Diagnostic discipline:** a recall failure must be attributed to *retrieval* (evidence never entered the pool) or *ranking* (in the pool, below the cut). Reporting only end recall hides which half is broken, and Revision 1 could not make this split.
- **Reranker justification rule (definitional):** an expensive reranker may be adopted only against measured `cut_loss` it removes on held-out seeds, with its latency and `internal_model_calls` attributed to the case. Per SCOPE §8 and A.1, a reranker that requires a paid API cannot be the default; a local or deterministic fallback must exist and must itself be measured as an arm.
- **Cheap-path exclusion (definitional):** ranking machinery must not run on F1 exact-lookup cases (SCOPE §8: "an exact Message-ID or invoice-number query does not need an expensive reranker"). Checked from the trace and cross-checked against latency.

**Bars:** UNSET-empirical (`cut_loss` reduction, MRR) — registered at G0 against the no-reranker configuration on the same seed.

### 7.4 Escalation behaviour and cost

The ladder (`ROUTING_OPTIONS.md` §5.2) is instrumented end to end and measured by the escalation confusion table of §6.4.

**Definitional bars, settable now — these are the strongest guarantees available before any measurement exists:**

1. **No unexplained not-found.** For every case whose terminal class is `not_found`, the trace must show the escalation ladder ran to exhaustion over every applicable rung. A `not_found` emitted while an applicable rung was skipped for budget, cap, timeout or error is a Recoverability Invariant violation and a BLOCKER (OD-2); the correct terminal class for that case is **`inconclusive`**, surfaced to the caller with the cap, the untried routes and their affordances. This makes the original bug — a silent false negative — structurally impossible rather than statistically rare.
2. **Cheap-path non-regression.** Installing escalation must not change F1/F2 latency or API-call counts beyond noise when escalation does not fire (Adaptive Cost Invariant).
3. **Escalation is observable.** `escalated`, the stage sequence and each `stop_reason` appear in the trace and are cross-checkable against network-observed calls; a system whose escalation cannot be externally corroborated fails observability regardless of its recall.

**Trigger ablation (new — CONS-016).** `ARCHITECTURE_DECISION.md` A.8 makes `answer_type_presence` the whole of its answer to tension T-RC2 (the confident-but-wrong lexical result), labels it "a hypothesis, pre-registered", and points at "PF-9/CG-EP" to measure it — but PF-9 is the Gmail-`q` message-scoping check and CG-EP's bars are recall, FNF, Baseline-B proximity and hallucinated-found. Nothing measured the trigger, and an unmeasured hypothesis was deciding when to escalate on the shipped default path. Therefore:

> Run **F11** (semantic-with-lexical-trap — the under-escalation case) and **F12** (semantic negative control — the over-escalation case) with the escalation trigger set to (i) **query-shape only** and (ii) **query-shape ∨ `answer_type_presence`**, same cases, same seed, paired. Report **under-escalation on F11** and **over-escalation on F12** for each setting, with CIs. The composite trigger ships **only if it reduces under-escalation without breaching the registered F12 over-escalation ceiling or PERF-01's latency ceiling**; otherwise `answer_type_presence` is removed per `ARCHITECTURE_DECISION.md` E.2. The table is published either way, and it is what makes T-RC2 a closed tension rather than a nominally closed one.

**UNSET-empirical:** over-escalation and under-escalation rates (for both trigger settings above), and the `escalation_cost` p95 budget — registered at G0 from the measured cheap-path distribution. Revision 1's Loop 3 proposals (≤10% fallback on simple cases; ≥80% recovery) are carried forward as the starting proposals for two of these cells (§13.4 CG-AD).

### 7.5 Progressive disclosure under the corrected scope

P1–P5 (§6.2) are unchanged and still the mechanical core. Revision 2 adds P6 (selection provenance) and P7 (temporal partiality) from §6.4, and the budget–recall curve from §7.2. The M2 end-to-end partiality probe (§10) is unchanged.

#### 7.5.1 The large-thread depth arm (new — the measurement `DISC-05` requires)

**Why it exists.** Rubric `DISC-05` is a `C` criterion — mandatory once its trigger fires — and `ARCHITECTURE_DECISION.md` §H-3 declares the trigger **met by design**, because a segment map ships for very long threads. Until this repair, no arm, no case set, no metric and no gate cell in this plan defined the depth-*n* vs depth-*(n−1)* comparison that `DISC-05` demands, which left a mandatory-once-triggered criterion permanently `NOT TESTED` — and `NOT TESTED` blocks release exactly like `FAIL` (rubric PROC-01). It also left tensions **T-1** and **T-CD1** open, since their recorded reversal criterion is this comparison (CONS-006).

**Cases.** Threads at and above the measured flat-map token boundary — the point where a flat stub map alone approaches the response ceiling, determined by preflight PF-6, not assumed. Drawn from the F3 long-thread material plus the D1 census's real thread-length upper deciles, so the arm is exercised at lengths the owner's mailbox actually contains rather than only at 100 messages.

**Arms (same cases, same budget, paired scoring per §8.6):**

| Arm | Disclosure structure | What it is |
|---|---|---|
| **PD-DEPTH-N1** (depth *n−1*) | Flat map + **declared truncation** + an executable affordance for the untruncated remainder | The shallower design: one navigation level. Truncation is declared, never silent (contract R-04/R-06), so this arm is honest, not crippled |
| **PD-DEPTH-N** (depth *n*) | Segment map — the additional level the architecture ships | The deeper design |

**Reported per arm, per case:** strict case accuracy, `rounds`, `tokens_returned`, `map_tokens`, `levels_traversed_to_answer`, and latency. Paired, with McNemar for accuracy and paired bootstrap for tokens/rounds/levels, per §13.1.

**What the result means.** The prior this is measured against is `VERIFIED_RESEARCH.md` §8.1 / arXiv 2607.17598: a second, deeper routing level "never helps and sometimes breaks accuracy". So the segment level ships **only on a measured win** at matched budget; otherwise it is removed and the flat map plus declared truncation is the shipped design (`ARCHITECTURE_DECISION.md` E.2's removal path). The comparison is published either way — a loss here is a finding about our own design, and the honest outcome of a level that did not earn itself.

**Scope caveat — now resolved (Round-1 reconciliation).** Under `DISC-05`'s plain wording the separately-requestable `snippet` and `raw` views are *also* levels beyond the evidence response plus escape hatch (ARCH_REVIEW ADV-208). The resolution is **measure, do not remove**: `raw` is no longer independently requestable (`ARCHITECTURE_DECISION.md` D.1), `snippet` stays, and **this arm's `levels_traversed_to_answer` covers the content-depth vocabulary** — `stub → snippet → body_clean → body_full` — as well as the segment map, so every level that ships must earn itself here or be removed under `ARCHITECTURE_DECISION.md` E.2. Dropping a shipped level would be the scope reduction SCOPE §1/§6 forbids; extending the measurement adds an obligation and weakens nothing. This is no longer an owner item and has been removed from §16.

One scope consequence: because disclosure policy is now query-aware rather than a fixed window, the extraction adapters (§6.2) must expose the *reason* a message was included — the wire field is **`reason`** (contract R-03), which `CONTEXT_DISCLOSURE_OPTIONS.md` §5 calls `role_reason` (CONS-033 row 4) — not only that it was — otherwise P4 and P6 cannot be evaluated mechanically. Adapters remain frozen-and-reviewed at gate time (§9 G6), and an adapter change is a reviewable event precisely because an adapter can fabricate partiality fields.

### 7.6 Freshness

Design and mitigation trigger in §11. Two things to note here, because they are coverage decisions rather than protocol details:

- Freshness is observed **from the first round** via Tier-1 D6 on real delivered mail, not only in a terminal experiment. A single confirmed real-mailbox false negative on recent mail is mitigation-forcing on its own (MF4).
- **P7 is required regardless of the result.** If measurement shows Gmail search is fast, that is a sample-based median, not a per-query guarantee; the response must still be able to say that a result derives from a search index that may lag. Honest degradation is a product property, not a fallback for bad numbers.

---

## 8. Baselines — permanent harness fixtures

> **PRESERVED — Revision 1 §4.1–4.6, verbatim.** Heading numbers renumbered (4.x → 8.x). Baselines A–E, the Baseline A′ honesty rules, the frozen `naive_translate` function, and the comparison protocol are unchanged. Two changes are additive: Baseline E's *scope* is expanded (§8.7) and one baseline is **added** (§8.8). No baseline is ever removed — that rule is preserved and is what makes regressions against history visible.

All baselines are versioned adapters inside the harness repo, run on every gate against the same seeded corpus instances, forever (a baseline is never deleted; regressions vs history are visible). All read-only.

### 8.1 Baseline A — reported hosted-MCP behavior (reproduction protocol) — *verbatim, Rev-1 §4.1*

*Target:* the behavior documented in anthropics/claude-ai-mcp#296, #730 and claude-code#76396 (search finds the thread; the exposed `messages[]` omits the matching message).

*Reproduction protocol:*
1. Connect the Gmail MCP connector (Google's hosted `gmailmcp.googleapis.com/mcp/v1`, per https://developers.google.com/workspace/gmail/api/reference/mcp — Developer Preview; `search_threads` documented at .../mcp/tools_list/search_threads with `pageSize` ≤ 50 and **no documented per-thread message cap**, full bodies deferred to `get_thread`) **signed in as the seeded test account**.
2. For each case: issue the family-appropriate `search_threads(query=...)`; record the returned per-thread `messages[]` verbatim; score recall/partiality on exactly that payload. Then issue `get_thread` on the top thread and score again (the #296 contrast pair).
3. First run includes a direct replication attempt of the #296 signature: `rfc822msgid:` search for a deep message; assert whether the matched message is present in the preview.

*Honesty rules (binding):* If the hosted behavior has changed (bug fixed, caps different), **report what we measure and date it**; public-issue evidence is cited as provenance, never blended with our numbers. If the connector cannot be attached to the test account (workspace/consent constraints — §9 Q5), we run **Baseline A′ — reconstructed preview**: a deterministic adapter over the REST API (`threads.list(q)` → expose only the 5 oldest messages of the top thread), labeled `RECONSTRUCTED` in every table, with the reconstruction rationale (#296 reports ~oldest-five). A′ numbers are never presented as measurements of Google's server.

### 8.2 Baseline B — full-thread dump — *verbatim, Rev-1 §4.2*

`messages.list(q = naive_translate(query))` → take top-ranked matching thread(s) → `threads.get(format=full)` → disclose every message. `naive_translate` is a frozen, documented function (strip punctuation/stopwords, quote multi-word proper phrases; no operator inference) shared by B/C/D so they differ only in disclosure policy. Expected: recall ceiling, worst tokens. B is the **recall ceiling and token floor-of-shame** in every comparison.

### 8.3 Baseline C — fixed newest/oldest-K — *verbatim, Rev-1 §4.3*

Same thread selection as B; disclose exactly K messages: variants **C-old5** (mimics reported hosted behavior), **C-new5**, **C-new20**. Expected: position-sweep failure in opposite directions — the graphic argument for context §38.

### 8.4 Baseline D — plain message-level search — *verbatim, Rev-1 §4.4*

`messages.list(q = naive_translate(query), maxResults=20)` → `messages.get(format=full)` each hit → disclose matched messages only, no thread context. Tests "how far do Gmail primitives already get you" (context §36) and is the latency yardstick for simple families.

### 8.5 Baseline E — primitive-tools agent — *verbatim, Rev-1 §4.5; scope superseded, see §8.7*

The same pinned agent model as Tier-2 (§6.2), given raw primitive MCP tools (`search_messages(q)`, `get_message`, `get_thread`, paginated) with the same round budget. This is the direct test of falsifier "agents already manage thread expansion reliably with primitive tools" — if E matches MailWeave on recall/answers at similar cost, the MailWeave-specific machinery is unjustified.

### 8.6 Comparison protocol — *verbatim, Rev-1 §4.6*

Same corpus instance, same case order; systems interleaved per case in randomized order; each system in its own GCP project/credential (§1.2.7); settle gate before start; paired scoring (same instances) → McNemar for recall deltas, bootstrap paired deltas for tokens/latency (§8.1). Latency comparisons against hosted Baseline A carry a standing annotation: different network path and server locality; we report the asymmetry rather than pretending it away.

### 8.7 Baseline E, promoted: strong agent + honest primitive tools

Revision 1 ran Baseline E in the agent tier only, as one of five arms. Revision 2 makes it **mandatory at every gate**, because it is the arm most able to falsify MailWeave's added value.

The reason is external evidence, not taste. `VERIFIED_RESEARCH.md` §8.1 (arXiv 2607.17598, "Is Progressive Disclosure All You Need for Long-Context Agents?", He/Zhao/Wang/Chen, July 2026) reports, quoted: the gain from progressive disclosure is "near zero when a strong agent harness already divides and retrieves on its own"; a second routing level "never helps and sometimes breaks accuracy outright"; and "Progressive disclosure buys context, not intelligence." Domain transfer (books → email) is untested, so this is hypothesis-shaping rather than conclusive — which is exactly why it must be an arm we run rather than a paper we cite.

**"Honest" is load-bearing.** Baseline E's primitives must be the tools the broken connector is not: `search_messages(q)` returning message-level hits with no silent cap, `get_message`, `get_thread` returning the complete thread, proper pagination, and true totals. Beating a deliberately crippled baseline proves nothing. E is MailWeave's fairest possible opponent, and it is supposed to be hard to beat.

**Two budget variants, both run:**

| Variant | Round budget | The question it answers |
|---|---|---|
| **E-matched** | Same as MailWeave (§10 M2) | At equal interaction cost, does MailWeave's machinery help? |
| **E-generous** | 2× rounds, same tools | Can a good agent with good tools get there *at all*, given room? |

**The interpretation rule, pre-committed now so it cannot be negotiated later.** If **E-generous** matches MailWeave on answer accuracy, then MailWeave's claim is **not** "finds what agents cannot find". It narrows to cost, rounds, latency, predictability and explicit partiality — and the README must say so in those words. That narrowing is written into the release gate's documentation-accuracy check (§12), not left to whoever drafts the copy.

Cost is bounded by the M2 subsampling and caps already specified in §10; adding E-generous adds one arm at 2× rounds on the subsample, not on the full suite.

### 8.8 Baseline F — hit-centred fixed ±N (the SCOPE §6 baseline)

Revision 1's Baseline C is a *thread-level* fixed-K (oldest/newest K of the top thread). `SCOPE_CORRECTION.md` §6 names a different and more demanding baseline: **hit + two before + two after**, centred on the match. That baseline did not exist in Revision 1 and is added here.

- **F(±2):** run Baseline D's message-level search, then disclose each hit plus its 2 preceding and 2 following messages in `internalDate` order within the thread.
- **F(±N) sweep:** N ∈ {1, 2, 5} to produce the fixed-window budget–recall curve that §7.2's equal-budget comparison needs.
- Same frozen `naive_translate` as B/C/D (§8.2), so F differs from them only in disclosure policy — preserving Revision 1's design that baselines are comparable by construction.
- F is expected to be **strong**: it is cheap, it centres on the evidence, and it is exactly what a competent engineer would build first. If the query-aware policy cannot beat F(±2) at matched budget, `SCOPE_CORRECTION.md` §6's premise is the thing that failed, and that result goes in the log with the same weight as a win.

---

## 9. Anti-gaming structure (structural, not aspirational)

> **PRESERVED — Revision 1 §5, verbatim.** G1–G8 are reproduced below unchanged: black-box-over-MCP, ground truth confined to the harness, corpus regeneration from seeds, held-out seed partitions, two-profile discipline, the reviewer gate checklist, the experiment-log format with failures as first-class results, and measurement integrity. This is the architecture that makes the numbers trustworthy and none of it is relaxed. G9–G12 (§9.9) extend it to the tiers and capabilities Revision 2 adds. `AGENT_LOOP.md` §7 carries the reviewer-side obligations that pair with these.

**G1 — Black box over MCP.** The harness talks to MailWeave exclusively via the MCP protocol (spawned stdio subprocess or HTTP endpoint). The harness never imports server code; the server process runs in a separate working directory / container **without filesystem read access to the harness repo**, under the read-only Gmail credential. The only inputs it ever receives are: MCP initialize, the query text, and follow-up tool calls. Case metadata (family, position, expected answers) never crosses the wire — CI asserts the driver serializes nothing but the query string and protocol-native cursors.

**G2 — Ground truth lives only in the harness.** Case files, seed manifests, and metric code live in `benchmarks/` (harness repo). The server repo has no dependency on `benchmarks/`; CI gates on (a) dependency graph, (b) a grep sweep of server source for case ids, manifest paths, bench label names, and seeded-corpus literals (subjects, personas, invoice tokens from the template banks). The seeder credential (which could read manifests *out of the mailbox* — it can't; manifests are never mailed) is never mounted into the server environment.

**G3 — Corpora regenerate from seeds.** Every gate run seeds a fresh corpus from a fresh master seed (§1.7): evidence positions redrawn from the grid, paraphrase surfaces re-realized, names/dates/tokens re-randomized. Memorizing "the launch answer is at position 37" or caching Gmail message ids is worthless across runs by construction. The generator version + seed are in the run header, so any run is exactly reproducible *by the harness* while unpredictable *to the server*.

**G4 — Held-out seed ranges and templates.** Master seeds partitioned: `DEV 1000–1999` (unrestricted), `TUNE 2000–2999` (threshold/router tuning), `HOLDOUT 9000–9999` (gate-only; each holdout seed used for exactly one gate evaluation, then retired to DEV). Additionally ~20% of paraphrase/decision templates are marked holdout and first instantiated at gate time. Development literally cannot overfit to surface forms it has never seen.

**G5 — Two-profile discipline.** Inner-loop iteration runs the smoke profile on DEV seeds; **gate claims come only from full-profile runs on HOLDOUT seeds.** Smoke numbers are never quoted outside the log.

**G6 — Reviewer gate for closing any loop.** A loop closes only when a reviewer *who did not write the loop's code* (human, or an independent agent session given only the harness repo and diffs — no build-chat context) signs this checklist, recorded in the experiment log entry:

```
[ ] Fresh HOLDOUT seed run meets the loop's pre-registered exit criteria
[ ] Second fresh seed reproduces within CI bounds (§8.1); disagreements investigated, not averaged away
[ ] Diff audit since loop open: no reads of benchmarks/ paths; no case-id / persona / subject /
    token literals from template banks; no special-casing on query text patterns that mirror
    templates; no branches keyed on thread length 100 / positions {2,7,20,37,51,83,99}
[ ] Extraction adapters (§3.2) unchanged or re-reviewed (an adapter can fabricate partiality fields)
[ ] Trace spot-check: 5 random passes + ALL fails inspected — behavior generalizes vs pattern-matches
[ ] Experiment log entry complete, failures included as first-class results
[ ] Claims drafted for this loop are covered by measurements in this entry (§58 discipline)
```

**G7 — Experiment log (context §56 format), failures first-class.**

```
experiments/
  README.md            # index table: id, date, loop, hypothesis, decision
  001-loop0-baseline.md
  002-loop1-message-level.md ...
Each file:
  Hypothesis / Change / Dataset & seeds (exact ids) / Metrics (pre-registered primary vs exploratory)
  / Results (tables incl. CIs) / Failure examples (verbatim traces) / Decision / Next experiment
  / Gate review record (G6 checklist, reviewer identity)
```

A negative result (e.g., "semantic index rejected: +2.1 recall, +80% p95") gets the identical template and stays in the index forever. Deleting or rewriting a log entry is prohibited; corrections append.

**G8 — Measurement integrity.** Headline metrics only from harness-measured fields (§3.3); network-level API counting (not self-reports); pinned tokenizer; pinned judge/classifier models with recorded versions; blind judging (system identity stripped); run headers carry generator version, seeds, model versions, and git SHAs of harness and server.

### 9.9 Extensions for the three-tier methodology and the new capabilities

**G9 — Tier separation is enforced, not just intended.**
The Tier-1 client (personal, `gmail.readonly`) and the Tier-2 systems-under-test run under different credentials in different projects, and the harness refuses to score a manifest against a run whose `mailbox_profile` is `personal`. Concretely: the scoring path requires a seed manifest; the personal profile has none and cannot acquire one; and a run header carrying `mailbox_profile: personal` alongside manifest-derived fields is a hard error, not a warning. This makes "accidentally quote a personal-mailbox number" a structural impossibility rather than a discipline problem.

**G10 — Fixture provenance and the memorization check.**
A Tier-3 fixture derived from a real failure must not become a memorization target. Enforced by: `PROVENANCE.md` completeness (§5.2 step 7); the n-gram disjointness assertion; and the rule that **F-seeded fixtures run on the gate's fresh HOLDOUT seed**, so a fix that only works on the original instance is visible as a failure. Reviewers additionally apply `AGENT_LOOP.md` §7.2 (read the test, not just the result) to every new fixture: a fixture that asserts a hardcoded ID or a template literal is a HIGH finding even if the underlying bug is fixed.

**G11 — Ablations are permanent, like baselines.**
SEM-OFF, no-reranker, and fixed-window disclosure are permanent arms, not temporary comparisons deleted once a capability ships. This is the anti-gaming defence specific to mandatory capabilities: once a capability can no longer be rejected, the only remaining honesty mechanism is continuously measuring what it contributes. A capability that has shipped and whose ablation shows no measured contribution is a finding, and it is reported.

**G12 — Degenerate-strategy probes for the new metrics.**
`AGENT_LOOP.md` §7.5 requires asking, for every metric, what the dumbest implementation that maxes it looks like. Pre-registered answers for the Revision-2 metrics, each with its paired guard:

| Metric | Degenerate strategy | Guard |
|---|---|---|
| `semantic_gain` | Always escalate to semantic; report the gain | F12 negative controls + over-escalation cell of the confusion table + F1/F2 latency non-regression |
| `pool_recall` | Fetch enormous candidate pools | `pool_fetch_cost` in API calls and quota units is reported beside it; §7.4 cheap-path non-regression |
| `cut_loss` | Disclose the entire pool so nothing is cut | Token metrics and `relevant_token_fraction` (§6.1) bind simultaneously |
| `recovery_rate` | Escalate on every query so every failure is "recovered" | Denominator is *first-route failures*; over-escalation is measured separately; cheap-path cost is bound |
| P7 temporal partiality | Stamp "may be stale" on every response | Paired with the freshness measurement: an always-on marker is checked against measured lag; unconditional hedging is a disclosure failure, not a pass |
| Tier-1 oracle counts | Run fewer probes | Denominators are always reported; probe counts per protocol are pre-registered per round |
| Structural reproduction rate (§5.3) | Classify hard findings as `content-dependent` | Open exceptions are counted, listed and reviewed every gate; a rising count is a finding |

---

## 10. Execution modes: scripted retrieval vs agent-in-the-loop

> **PRESERVED — Revision 1 §6, verbatim except for labels.** Revision 1 called these "Tier 1" and "Tier 2". That vocabulary now belongs to the three-tier substrate methodology (§1), so the execution modes are renamed **M1** (scripted driver) and **M2** (agent-in-the-loop). The driver policies, round budgets, subsampling rules, judge-validation requirements, cost estimates and the interpretation contract are unchanged.
>
> **Global reading note:** wherever preserved Revision-1 text elsewhere in this document says "Tier 1" or "Tier-2" in reference to the driver, the agent, or §6, it means M1 / M2 — for example §6.1's "Tier-1 driver policies fix the maximum, §6.1", §6.2's "in Tier-2 runs, after the answer the driver…", §8.5's "the same pinned agent model as Tier-2 (§6.2)", and §13.1's "Tier-1 numbers … Tier-2 bars marked (e2e)". Substrate tiers are always written "Tier 1 / Tier 2 / Tier 3" with a capital T and a reference to §1–§5.
>
> One scope change: §10.2's "Baseline E exists only in M2" remains true of the *mode*, but E is now mandatory at **every gate** and runs in two budget variants (§8.7).

### 10.1 M1 — scripted retrieval metrics (every run, cheap, deterministic) — *Rev-1 §6.1, labels renamed*

A scripted MCP driver (no LLM) issues the case query to the system's entry tool and follows **ground-truth-blind, fixed expansion policies**:

- **P-min:** single call, no follow-ups → measures first-response quality (`recall@1round`).
- **P-follow:** while the response advertises a machine-actionable more/expand affordance and rounds < R=4: invoke it (deterministic choice: first-listed affordance, breadth-first) → `recall@≤4rounds`, tokens, rounds.

The driver never uses the manifest to decide anything (that would measure a clairvoyant client); scoring happens after the transcript is closed. M1 produces: recall, tokens, latency, API calls, rounds, FNF, P1–P5 — the loop-gate workhorse. Cost: no model tokens at all (except MailWeave's own internal calls, which are its cost to bear and appear in its latency/API numbers).

### 10.2 M2 — agent-in-the-loop (gate time + scheduled, expensive) — *Rev-1 §6.2, labels renamed*

A pinned agent (fixed model id, fixed minimal system prompt, temperature 0, round budget 8, output cap) receives only the system-under-test's MCP tools and the query; it must produce an answer. Scoring:

1. **Deterministic first:** `scoring.answer_rule` (date/value/quote containment) decides correct/incorrect where possible — most families are authored to make this decidable.
2. **LLM judge fallback** for free-text cases: pinned judge model + fixed rubric, blind to system identity, validated once against 50 hand-labeled transcripts (agreement reported; rubric frozen after validation).
3. The §3.2 partiality follow-up probe always runs.

**When each mode runs:** M1 on every experiment (smoke or full). M2 on: every gate (full profile, HOLDOUT seed) and at most weekly during a loop — on a stratified 25% subsample (every family represented; every position covered across the sample), plus **100%** of F5/F6/F7 at gates (families where disclosure format plausibly changes answers). Baseline E exists only in M2.

**Cost control:** subsampling as above; round/output caps; deterministic scoring preferred over judge; judge only on disagreement-prone families. Budget estimate at gate: ~60 Tier-2 cases × 6 systems × ~12k tokens ≈ 4–5M tokens — bounded and scheduled, not per-commit.

**Interpretation contract:** M1 answers "was the evidence preserved and disclosed efficiently" (the thesis); M2 answers "does it help an actual agent answer correctly." A gap (evidence disclosed, answer wrong) is a first-class tracked diagnostic — it indicts the disclosure format, and it is exactly the kind of result the log must keep (§5.7).

---

## 11. Freshness — protocol, completion bar, and mitigation trigger

`SCOPE_CORRECTION.md` §12 changes freshness from a terminal research question into part of the completion bar:

> Test real delivered mail. If direct Gmail API search is sufficiently fresh, document the result. If it exhibits meaningful lag, the implementer must build a mitigation such as History-based reconciliation/synchronization, or another defensible mechanism, before making freshness claims.

§11.1 is Revision 1's probe protocol, preserved. §11.2 is new: the depth stratification the reported failures demand, the pre-registered evidence that forces a mitigation build, and what a mitigation must do to count.

### 11.1 Freshness experiment protocol — *verbatim, Rev-1 §7*

**Standing rule (context §4, §54 Loop 6): no freshness claims — positive or negative, about anyone's system — until this protocol has run to completion.** This includes marketing-adjacent phrasing in the README.

**Why not inserts:** the reported failure (claude-code#82548) concerns mail that arrived through real delivery. `insert` bypasses the delivery path (§1.2.1), so freshness probes use **real delivery**: primary arm sends from a second, unrelated account (SMTP or its own Gmail) to the test account; a self-send variant via `messages.send` runs as a labeled secondary condition.

**Per probe:** unique nonce in subject+body, own Message-ID; record `t_send`. Immediately before sending, snapshot `historyId` via `getProfile`.

**Arms polled (each on its own credential/project where applicable):**

| Arm | Probe call | What it isolates |
|---|---|---|
| H0 | `history.list(startHistoryId=snap)` (2 units) | arrival ground truth — message accepted into the mailbox, independent of search index |
| H1 | direct `messages.list(q="rfc822msgid:<...>")` | exact-id search indexing |
| H2 | direct `messages.list(q="<nonce>")` | body-term search indexing (closest to reported failure) |
| H3 | hosted Gmail MCP `search_threads(query="<nonce>")` | the reported failing layer |
| H4 | hosted `get_thread(threadId)` once known — does the *new* message appear in the returned messages[]? | hosted thread-view staleness (the #296/#730 axis) |
| H5 | MailWeave query for the nonce | MailWeave end-to-end freshness |
| **H5-LRoff** | MailWeave query for the nonce with the **recency rung (LR) disabled** | *(new, CONS-031; architecture citation corrected by the Round-1 reconciliation)* Separates the server's freshness from its mitigation's. The recency rung (LR) is now **Experimental with a removal gate** in `ARCHITECTURE_DECISION.md` **E.2**, costs `2 + 20n` units rather than 2 (ADV-101), and fires on recency-cued queries; measuring H5 with it on would make the observed lag a property of the mitigation rather than of Gmail, which is the exact confound this protocol's arm separation exists to prevent. **This arm is the gate that decides whether LR ships at all** — E.2's removal path reads it. **MF6 and MF3 are evaluated on H5-LRoff**; H5 is reported alongside it as the shipped configuration, and the pair is what shows whether LR earns its place at all — a recency rung that ships unconditionally and unmeasured is an untested component on the default path |

**Schedule:** poll every 15 s for 5 min, every 1 min to 30 min, every 15 min to 24 h, stop at 72 h (censored if never surfaced). Quota cost per probe is trivial (≤ ~700 units/day/arm).

**Design:** N ≥ 30 probes, spread across ≥ 5 calendar days and ≥ 3 times of day. **Metric:** per-arm lag = first successful surfacing − H0 arrival time (using H0, delivery lag is excluded from index-lag measurement); report median, p90, full ECDF, and censoring counts. Paired per-probe comparisons across arms.

**Claim rules:** any freshness statement must name the arm, N, dates, and censoring; MailWeave freshness claims are made only relative to H1/H2 (its substrate) — if MailWeave's lag exceeds direct-API lag by >60 s median, that is a MailWeave bug to fix before any claim. Whether to add history-based sync to MailWeave is decided by these numbers, not in advance (context §4).

### 11.2 Completion bar, stratification, and the mitigation trigger (new)

#### 11.2.1 Two additions to the protocol above

**(a) Depth stratification — required.** The Revision-1 protocol sends standalone nonce messages. But `VERIFIED_RESEARCH.md` §1.3 records a decisive nuance in claude-code #76396: in that reporter's account **a fresh self-test email was indexed within seconds** while long, deep threads stayed stale. A protocol that only probes standalone messages could therefore measure "Gmail search is fresh" and completely miss the failure the product exists to prevent.

Every probe is therefore replicated across three strata, by delivering the nonce **as a reply into** a pre-seeded thread of depth 0 (new thread), 5, and 25 (S12 verifies delivery joins seeded threads, §3.9). Arms H0–H5 run identically in each stratum, and every result is reported per stratum. Pooling across strata is prohibited — pooling is exactly what would hide the effect.

**(b) Tier-1 D6 runs continuously in parallel.** Real inbound mail to the owner's real mailbox is real delivery into real threads at real depth — data the seeded account cannot manufacture. D6 (§2.5) records arrival-vs-surfacing on that mail with IDs and timestamps only. It cannot produce a lag distribution with controlled nonces, but it can produce something stronger: **a confirmed instance of a user-visible false negative on recent mail**.

#### 11.2.2 The Freshness Service Level (FSL) — a product decision, not a measurement

Several triggers below need a threshold answering: *how stale may a result be before the product is lying?* That is a product decision about acceptable user experience, not something a measurement can produce. **This plan does not set it, and inventing a number here would be exactly the dishonesty the pre-registration discipline exists to prevent.**

The FSL is set by the owner/synthesis, written into experiment log 001 **before the probe run starts**, and frozen thereafter (amendable only by the §13.2 amendment procedure, which retains the original). It must be expressed as: a lag bound, the arm it applies to, and the depth strata it applies to.

#### 11.2.3 Mitigation-forcing evidence (pre-registered; any one is sufficient)

If any of these holds, a mitigation **must be built and verified before any freshness claim is made** — this is implementation work inside the loop, not a future research idea (SCOPE §12).

| ID | Trigger | Why it forces work | Needs a number? |
|---|---|---|---|
| **MF1** | Any probe **censored at 72 h** (never surfaced) in an arm the product depends on | A message that never becomes findable is an unbounded false negative. No threshold can make this acceptable | No |
| **MF2** | p90 lag of the depended-on arm exceeds the **FSL**, in any stratum | Definition of "meaningful lag" for this product | FSL only (§11.2.2) |
| **MF3** | **Depth divergence**: paired per-probe lag in the depth-25 stratum exceeds the depth-0 stratum with the 95% CI of the difference excluding zero | This is the reported failure signature. A statistical criterion, so no threshold is invented | No |
| **MF4** | **Any** Tier-1 D6 instance where the owner confirms a message was in the mailbox and MailWeave returned not-found / omitted it for a query that should have matched (an O7/O1 violation on real mail) | One real reproduction outweighs a good median. This is the reality-first rule applied to freshness | No |
| **MF5** | The lag ECDF is **bimodal** with a mode beyond the FSL | A distinct failing population is not a slow tail; medians hide it | FSL only |
| **MF6** | MailWeave's own median lag exceeds direct-API lag by **> 60 s** | Preserved verbatim from Rev-1 §7: a MailWeave bug, to be fixed regardless of what the mitigation decision is | No (inherited) |

Five of six triggers need no invented number. That is deliberate: the design goal was to make the mitigation decision reachable **without** pre-registering thresholds we have no basis for.

#### 11.2.4 What a mitigation must do to count

The mechanism is the implementer's choice (SCOPE §12 says "History-based reconciliation/synchronization, or another defensible mechanism"). These properties are not optional:

1. **A path that does not depend on the search index.** `users.history.list` from a stored `historyId`, or a bounded `messages.list` by `internalDate` window, or `threads.get` re-reads of touched threads.
2. **It must do its own matching.** This is the trap: `history.list` returns *arrival events*, not *query matches*. A reconciliation layer that merely lists new message IDs has not answered the user's question. It must fetch and match the reconciled set against the query itself — and that matching cost is part of its measured cost. **Whether history-based reconciliation actually fixes search-shaped queries is a hypothesis until arm H6 measures it** (§15).
3. **Staleness metadata on every response** (`index_synced_at` / `history_id` / "search-index-derived" provenance), so no result can claim currency it does not have — the Partiality Invariant applied to time (`SECURITY_NOTES.md` §4.2). P7 (§6.4) is the mechanical check.
4. **The too-old-`historyId` full-resync path built from day one** (`history.list` 404s once the start ID ages out; docs say IDs are "typically valid for at least a week").
5. **Bounded cost.** It must respect the Adaptive Cost Invariant: no per-query reconciliation on the cheap path unless measurement shows it is free.

**Verification.** Add **arm H6 — MailWeave with the mitigation** and re-run the identical protocol, same strata, same N, same schedule. The mitigation passes only if it **removes the specific trigger that fired** (censored probes now surface; p90 ≤ FSL; the depth-divergence CI now includes zero) **and** does not regress the cheap-path latency and API-call bars (§7.4). A mitigation that improves freshness by making every query expensive has traded one invariant for another and does not pass.

#### 11.2.5 Claim rules

Revision 1's claim rules are preserved in full and extended:

- No freshness sentence of any kind — README, docs, commit messages, marketing-adjacent phrasing — until the protocol has run to completion and either no trigger fired or a mitigation passed H6 verification.
- Any freshness statement names: the arm, the depth stratum, N, the date range, and the censoring count. A statement that omits the stratum is not permitted, because the stratum is where the reported failure lives.
- **P7 is required regardless of the outcome.** A measured median is a sample, not a per-query guarantee. Honest degradation is a product property, not a consolation prize for bad numbers.
- Freshness and representation-omission claims are never bundled (context §58; SCOPE §12): "MailWeave does not silently drop matched messages" and "MailWeave sees new mail within X" are separate claims with separate evidence, and neither may be used to imply the other.

---

## 12. Rubric linkage — which measurement moves which criterion

`RELEASE_RUBRIC.md` now exists with stable, append-only criterion IDs, so this table is **keyed to those IDs** rather than only to the `SCOPE_CORRECTION.md` §16 areas (CONS-040): "which measurement moves which criterion" is literal here, not approximate. Its purpose is operational: a reviewer holding one of these criteria can find the named evidence, reproduce it, and set `PASS` — or find that the evidence does not exist and leave it `NOT TESTED`, which blocks release exactly like `FAIL` (`AGENT_LOOP.md` §6).

Reading the table: **Primary evidence** is what the criterion is chiefly decided on. **Corroboration** is what must also be true. **PASS requires** names the artifacts a reviewer must be able to point at. **Reviewer** is the `AGENT_LOOP.md` §2.3 domain that owns the verdict.

| Rubric area (SCOPE §16) + criterion IDs | Primary evidence | Corroboration | PASS requires (named artifacts) | Reviewer |
|---|---|---|---|---|
| **Evidence preservation**<br>`EV-01…EV-06` | Tier 2: F1 + F3 recall and the 7-point position vector (§4.4); CG-EP bars (§13.4) | Tier 1: zero O1 violations across the round's exact-operator probes; Tier 3: all evidence-preservation fixtures green | Experiment-log entry with both HOLDOUT seeds' tables + CIs; the round's Tier-1 oracle report; green fixture set | R-RETR |
| **Adaptive escalation**<br>`AD-01…AD-05, PERF-04` | Tier 2: escalation confusion table + `escalation_cost` distribution (§6.4) | Definitional bars §7.4 (1)(2)(3); Tier-1 D5 real-condition timings | Confusion table on a HOLDOUT seed; trace-level proof that no `not_found` is unexplained; cheap-path non-regression table | R-RETR + R-PERF |
| **Lexical retrieval**<br>`LEX-01…LEX-04` | Tier 2: F1/F2 vs Baseline D (§8.4) | Tier 1: O1 on exact-operator probes; D4 sessions | Paired comparison vs D with McNemar; zero unexplained O1 violations | R-RETR |
| **Semantic retrieval**<br>`SEM-01…SEM-06, NFR-01` | Tier 2: F4 (T1/T2/T3), F11, F12 across SEM-OFF / LOCAL-DEFAULT / LOCAL-ALT / HOSTED (§7.1) | S14 offline run; `non_google_egress_bytes == 0`; P6 provenance pass rate | Backend comparison table with CIs; the S14 container result; registered `semantic_gain` bar met on a HOLDOUT seed | R-RETR + R-SEC (egress) |
| **Structural retrieval**<br>`STR-01…STR-05` | Tier 2: F5, F6, F7, F13, F14, F15; budget–recall curve vs Baseline F and C at ≥3 matched budgets (§7.2) | Tier 1: D1 census showing the structures exist in real mail | Budget-matched curve, not a point estimate; every SCOPE §5 signal covered by ≥1 family | R-RETR + R-DISC |
| **Candidate ranking**<br>`RANK-01…RANK-04` | Tier 2: F16 plus `pool_recall` / `rank_of_evidence` / `cut_loss` (§6.4, §7.3) | Cheap-path exclusion verified from traces | Retrieval-vs-ranking attribution table; any reranker justified by measured `cut_loss` reduction | R-RETR |
| **Progressive disclosure**<br>`DISC-01…DISC-06` | Tier 2: P1–P7 pass rates with CIs (§6.2, §6.4); token and `relevant_token_fraction` deltas vs Baseline B | M2 partiality follow-up probe (§10.2); Baseline F/C contrast | CG-PD bars on a HOLDOUT seed; frozen, reviewed extraction adapters | R-DISC |
| **Explicit partiality**<br>`PART-01…PART-07` | Tier 2: P1a / P2 / P3 (§6.2) | **Tier 1: O2 and O3 on real threads** — real threads are where `claimed_total` is genuinely hard | Assertion pass rates + zero unresolved O2/O3 findings | R-DISC |
| **Router recoverability**<br>`ROUTE-01…ROUTE-04, EV-04` | Tier 2: `recovery_rate`, FNF with its paired hallucinated-found control, F10 unanswerable controls (§6.1) | Definitional "no unexplained not-found" bar (§7.4) | FNF and hallucinated-found reported together, always; recovery table | R-RETR |
| **Real Gmail reliability**<br>`GMAIL-01…GMAIL-07, E2E-01…E2E-04` | Tier 1: D1, D2, D5, D8 oracle vectors and MIME-signature coverage (§2.5) | Tier 2 full-profile runs traverse the live API by construction (§3.1) | Coverage table (signatures handled / signatures observed); zero open BLOCKER findings | R-GMAIL |
| **Freshness**<br>`FRESH-01…FRESH-06` | §11 protocol, per depth stratum, with ECDFs and censoring counts | Tier 1 D6 continuous observation; P7 assertion | Either **no MF trigger fired** (with published per-stratum ECDFs) **or** a mitigation built and passing H6 verification (§11.2.4) | R-GMAIL |
| **Performance / latency**<br>`PERF-01…PERF-04` | Tier 2: interleaved p50/p95, network API calls, quota units (§6.1, §8.6) | Tier 1 D5 at real mailbox scale; local-model cold-load (§6.4) | Cold/warm separated; interleaved execution; CG-AD latency bars | R-PERF |
| **OAuth / security / privacy**<br>`SEC-01…SEC-08` | Scope matrix (§3.2.9); O9 redaction canary; `non_google_egress_bytes` against the **two-host** allowlist (CONS-002); the §2.4.7 write-path audit proving **no message bytes at rest** and no forensics writer (CONS-005); fixture scrub assertions (§5.2 step 6) | `SECURITY_NOTES.md` §10 checklist items T3/T4 | Canary green including error paths; every committed fixture's `PROVENANCE.md` complete; no personal-profile bytes under `experiments/` or `tests/` | R-SEC |
| **MCP correctness**<br>`MCP-01…MCP-07` | Schema validity; server-minted handle discipline (MCP 2026-07-28, `VERIFIED_RESEARCH.md` §7) | **O3 reachability** — an advertised handle that does not resolve is an MCP defect and a disclosure defect | Protocol conformance run + zero O3 violations | R-MCP |
| **Prompt injection / untrusted email**<br>`INJ-01…INJ-06` | **O8** byte-provenance taint containment (§2.4.5) | Tier 1 D7 real-mail detector class counts; Tier 3 injection fixtures built from pattern classes | Zero O8 violations on the round's real-mail sample and on the fixture set; fence/nonce design per `SECURITY_NOTES.md` §6.3 | R-SEC |
| **Observability**<br>`OBS-01…OBS-04` | Trace-schema completeness (§6.3) plus `route_sequence` / escalation fields (§6.4) | Self-reported vs harness-measured cross-check (§6.1); redaction-profile correctness | Every headline number traceable to harness-measured fields; documented self-report divergences | R-ARCH + R-SEC |
| **Regression tests**<br>`REG-01…REG-04` | Tier 3: every finding ≥ MEDIUM has a green fixture (§5.1, §2.6.3) | Structural reproduction rate + open-exception count (§5.3) | Fixture inventory mapped to findings; zero findings closed without a fixture or an approved exception | R-ARCH |
| **Real-Gmail E2E testing**<br>`E2E-01…E2E-04, GMAIL-07` | Tier 2 full-profile HOLDOUT runs + Tier 1 D4/D5/D8 in the round | S1–S14 green | Both present in the same round; no substitution of one for the other | R-GMAIL |
| **Documentation accuracy**<br>`DOC-01…DOC-06` | Claims-vs-measurement audit (§9 G7/G8; `AGENT_LOOP.md` §7.7) | The §8.7 narrowing rule if E-generous matches MailWeave | Every README claim mapped to an experiment-log entry; separated freshness/representation claims; no bar quoted from a smoke or DEV-seed run; the CTX §58 seven-item bundle complete before the headline claim | **R-DOC** (+ adversarial reviewer at the gate) |

**Two standing constraints on this table.** First, no criterion may reach `PASS` on Tier-1 evidence alone where a number is required — Tier 1 corroborates and blocks, it does not score (§2.7). Second, no criterion may reach `PASS` on Tier-2 evidence alone where the area names real-mail behaviour (real Gmail reliability, prompt injection, freshness, explicit partiality) — those need the reality tier, because seeded corpora are exactly the material we authored to be tractable.

---

## 13. Statistical hygiene and exit criteria

### 13.1 Hygiene rules (all gates) — *verbatim, Rev-1 §8.1*

- **Pre-registration:** each loop's primary metrics and bars are written into the experiment log entry *before* the gate run (bars below are the proposal; synthesis finalizes at Loop 0). Everything else is exploratory and labeled so.
- Every reported proportion: n + Wilson 95% CI. Every token/latency summary: n + bootstrap 95% CI on the median. No bare point estimates.
- **Gate = 2 fresh HOLDOUT seeds**, full profile. Pass requires the point estimate to meet the bar on the pooled data AND per-seed results within CI of each other; a disagreement triggers a third seed and a variance investigation before any pass is declared. No cherry-picking: both seeds' tables go in the log.
- Paired designs throughout (same instances across systems): McNemar for recall differences, paired bootstrap for tokens/latency. α = 0.05, but decisions emphasize CIs and effect sizes; multiple-comparison inflation is controlled by having few pre-registered primaries per loop.
- Latency claims: interleaved execution (§4.6), cold/warm separated, time-of-day recorded.
- All bars below bind on HOLDOUT-seed, full-profile, Tier-1 numbers unless stated; Tier-2 bars marked (e2e).

### 13.2 Pre-registration procedure for bars that cannot honestly be set yet

Revision 1 pre-registered numeric proposals because it had a shape of measurement in mind for the capabilities it covered. For the capabilities Revision 2 adds, **no measurement exists**, and a number written today would be a guess wearing the costume of a threshold. The discipline is preserved by making the *procedure* binding instead of the *value*.

**Three classes of bar:**

| Class | Settable when | Examples |
|---|---|---|
| **Definitional** | **Now.** Structural or binary; measurement only checks it | Zero non-Google egress in the default config (§7.1); no unexplained `not_found` (§7.4); P6 provenance labelling; cheap-path exclusion of the reranker (§7.3); no fixture closed without a green regression test (§5.1) |
| **Inherited** | **Now.** Carried forward from Revision 1's proposals, unchanged | CG-EP, CG-PD, CG-AD bars (§13.4) |
| **UNSET-empirical** | **After G0.** Needs a measured baseline distribution to be honest | `semantic_gain`; `backend_parity` tolerance; F12 over-escalation ceiling; F13/F14/F15 accuracy; `cut_loss` reduction; escalated-path p95; F4-T3 bar; the budget levels for the budget–recall curve; the **FSL** (§11.2.2); the D2 frequency floor for signature coverage |

**The procedure for an UNSET bar:**

1. **G0 measures the reference distribution** on a HOLDOUT seed: the ablation or baseline arm the bar will be expressed against (SEM-OFF for semantic; no-reranker for ranking; Baseline F for disclosure policy; direct-API arms for freshness).
2. **Synthesis writes the bar into experiment log 001** as a *delta or bound against that named distribution*, with its rationale, **before any gate run of the capability**. A bar with no rationale is rejected by the gate reviewer.
3. **The bar is frozen** at that point. It binds on HOLDOUT-seed, full-profile numbers per §13.1.
4. **Amendment is possible but expensive and visible:** a changed bar requires a logged amendment naming the reason, retaining the original value in the log, and re-running the affected gate. Amendment *after seeing the gate result it would change* requires escalation to the human (`AGENT_LOOP.md` §8) — this is the specific failure mode the procedure exists to prevent.
5. **A capability whose bar was never registered cannot pass its gate.** Its rubric area is `NOT TESTED`, which blocks release.

### 13.3 G0 — substrate, baselines and reality baseline (no performance bar)

Revision 1's Loop 0 criteria, preserved verbatim:

- S1–S10 smoke assertions green on 2 seeds (S2/S6 may set fallback policy rather than fail).
- Baseline A protocol executed (or A′ invoked with the honesty label); the #296 replication attempt's outcome recorded either way.
- Baselines B, C(-old5,-new5,-new20), D produce full metric rows on the full suite; position-sweep table for C shows the expected complementary failure pattern (sanity check of the adversary itself: if C-old5 does *not* fail deep positions, the benchmark is broken — investigate before proceeding).
- Experiment log 001 written; bars for Loops 1–3 pre-registered.

**Added by Revision 2** (all required before G0 closes):

- **S11–S14 green** (§3.9), with S14's zero-egress container result recorded.
- **Tier-1 harness operational:** oracles O1–O9 implemented; redaction profile selection keyed to the authenticated account; O9 canary green including error paths; **`mailweave inspect` built and PF-8 green** — the ID-based, memory-only forensics path is the *only* forensics path, and it must exist before the first real-mailbox round creates pressure to relax the rule (`SECURITY_NOTES.md` T-SN1). *(Revision-2 repair, CONS-005: this line previously required "forensic buffer encrypted with a TTL agreed by the owner", making an unauthorised at-rest store a G0 exit requirement.)*
- **D1, D2, D3, D7 have run at least once**, with suppressed-histogram outputs, the MIME-signature frequency table, and the generator recalibrated against them ("calibrated to census of <date>", §3.7).
- **One D4 session executed** (≥20 owner-authored queries) with verdicts recorded, purely to shake out the session protocol before it carries weight.
- **Reference distributions measured** for every UNSET bar: SEM-OFF on F4/F11/F12; no-reranker on F16; Baseline F(±1/±2/±5) and Baseline C curves; Baseline E in both variants; direct-API freshness arms in all three depth strata.
- **FSL registered** by the owner/synthesis in experiment log 001 (§11.2.2).
- **All UNSET bars registered** per §13.2, or the corresponding capability gate is blocked.

### 13.4 Capability gates (replacing the conditional loops)

Loops 0–6 are replaced by one substrate gate (G0) and eight capability gates. **All are mandatory**; none has an entry condition that can excuse skipping it; they may be worked in any order the implementer/reviewer loop finds convenient (`AGENT_LOOP.md` §5). All bind on HOLDOUT-seed, full-profile numbers per §13.1.

**CG-EP — Evidence preservation.** Revision-1 Loop 1 bars, preserved verbatim:

- F1 + F3 (buried), n = 168 buried instances (12×7×2 seeds): **evidence recall ≥ 0.98 overall; ≥ 0.95 at every position; position spread ≤ 0.05.**
- **FNF = 0** on F1/F3 (any false "not found" on an exact/buried case is a gate failure — this is the original bug).
- Recall within 2 points of Baseline B (the ceiling) overall.
- Hallucinated-found on F10 ≤ 0.10 (guard rail active from the start).

Added: zero unresolved O1 findings from the round's Tier-1 probes; all evidence-preservation fixtures green on the gate's fresh seed.

**CG-PD — Progressive disclosure.** Revision-1 Loop 2 bars, preserved verbatim:

- All Loop 1 bars maintained.
- On F3 threads: **median tokens_returned ≤ 30% of Baseline B**; **median relevant_token_fraction ≥ 3× Baseline B's**.
- Partiality: **P1a ≥ 0.98** (inherited unchanged), and **P2, P3 = 1.00** across all scored families. *(Revision-2 repair, CONS-011: P2 and P3 are mechanical self-consistency assertions — "the included set is exactly what is in the payload", "partiality is announced when true and not claimed when false" — not statistical ones. Rubric PART-02/PART-03 already bind them at 100%, and the honest reconciliation is to **raise this bar to match**, not to lower the rubric to ≥0.98. Nothing here is relaxed.)* **P4, P5 ≥ 0.95**, with P4 now scored across the contract's full seven role values and its reason field (§6.2, CONS-008) — a widened assertion at the same bar, which is a strictly harder test than Revision 1's three-value version.
- Rounds: p95 ≤ 4 under P-follow; `recall@1round ≥ 0.85` on F1/F2 (first response already carries evidence for simple queries).
- (e2e) answer accuracy on the Tier-2 subsample ≥ Baseline B's − 3 points (token savings must not cost correctness), and partiality-probe pass ≥ 0.9.

Added: **P6 and P7** pass rates registered per §13.2 — P6 `[DEFINITIONAL]`, P7 **= 1.00, required in all cases whatever the freshness measurement showed** (rubric FRESH-06); the budget–recall curve produced at ≥3 matched budgets against Baseline F and C (§7.2); zero unresolved O2/O3 findings; **the F17 decision-reversal family scored strictly in both the query-aware and Baseline F(±2) arms** (§4.7, CONS-007); and **the depth comparison of §7.5.1 is published — the segment level (or any additional disclosure level) ships only on a measured win at matched budget, otherwise it is removed (`ARCHITECTURE_DECISION.md` E.2)**, which is the gate cell rubric DISC-05 verifies against (CONS-006).

**CG-AD — Adaptive escalation.** Revision-1 Loop 3 bars, preserved verbatim:

- Simple families (F1, F2): **p50 latency ≤ 1.25× Baseline D** and median network API calls ≤ 3; fallback triggered on ≤ 10% of simple cases.
- Hard families (F3–F7): recall not below Loop 2; of cases where the initial route failed to surface evidence, **≥ 80% recovered by fallback** (routing_recovery_success — diagnostic fields used here as the loop's named purpose, cross-checked against externally visible rounds).
- No family's p95 latency regresses > 20% vs Loop 2.

Added: **the cost bar binds `api_calls`, not HTTP requests.** The preserved "median network API calls ≤ 3" figure is retained as a bound on **`http_requests`** (one per HTTP request whatever a batch contains) — the counter OBS-04 cross-checks against network observation — and a second bar is registered here on **`api_calls`** (one per Gmail sub-request, which is what quota is charged on): `[UNSET — registered at G0 per §13.2 against the G0-measured Baseline D `api_calls` distribution on F1/F2]`. Under HTTP batching a counting proxy sees one request per batch whatever *n* is, so the ≤3 figure bounds chatter and not cost, while rubric AD-04's statement is a cost claim (`ARCHITECTURE_DECISION.md` §H-8, §A.5b; ARCH_REVIEW ADV-106). The preserved bar is not altered — it is joined, and `quota_units` is reported as diagnostic. Also added: **the incomplete-diagnosis rate registered here — `[UNSET — registered at G0 per §13.2]`** (rubric ROUTE-04, OD-2; §4's constructed relaxation cases stay uncapped); the escalation confusion table published with both off-diagonal cells; the three definitional bars of §7.4; `escalation_cost` distribution reported; and **the trigger ablation of §7.4 published** — under-escalation on F11 and over-escalation on F12 for query-shape-only vs query-shape ∨ `answer_type_presence`, with the composite shipping only on a measured under-escalation reduction inside the F12 ceiling and PERF-01 (CONS-016).

**CG-SEM — Semantic retrieval** *(replaces Loop 4; the conditional entry condition and the reject branch are deleted)*
- Definitional bars §7.1 (1)–(5), all binary, all checked: zero non-Google egress in the default config; no API key required; hosted off by default; no semantic escalation on F1; P6 provenance on every semantically-selected message.
- Registered `semantic_gain` bars met on F4-T2, F4-T3 and F11 against SEM-OFF; registered F12 over-escalation ceiling met; registered escalated-path p95 met; F1/F2 cheap-path non-regression.
- `backend_parity` published. If the hosted arm wins by more than the registered tolerance, the gate fails **and the required fix is improving the local path** — never changing the default.
- SEM-LOCAL-ALT runs, demonstrating the interface is provider-agnostic in fact and not only in the type signature.

**CG-STR — Structural / participant / temporal retrieval** *(replaces Loop 5; conditional entry deleted)*
- Every SCOPE §5 signal covered by ≥1 family whose correct answer requires it (§7.2).
- Registered accuracy bars met on F13, F14, F15; F5/F6/F7 at or above their CG-PD values.
- The budget–recall curve shows the query-aware policy's position against Baseline F(±2) at matched budget — reported whichever way it comes out.

**CG-RANK — Candidate ranking**
- `pool_recall`, `rank_of_evidence` and `cut_loss` reported for every family with an ambiguous pool.
- Registered `cut_loss` reduction met on F16 where a reranker is used; cheap-path exclusion verified from traces; any reranker's local/deterministic fallback measured as its own arm.

**CG-FRESH — Freshness** *(replaces Loop 6; now a completion bar with a build trigger)*
- §11 protocol complete: N ≥ 30 per stratum, ≥5 calendar days, ≥3 times of day, all arms, **per-stratum** ECDFs and censoring counts published.
- Either **none of MF1–MF6 fired**, **or** the mitigation is built and passes H6 verification (§11.2.4) by removing the *specific* trigger that fired, without regressing the cheap-path bars. Rubric FRESH-02's trigger is now the whole MF1–MF6 set, not the 60 s gap alone (CONS-010).
- The **FSL is registered in experiment log 001 before the probe run started** (§11.2.2; rubric FRESH-05) — a gate check on the entry's timestamp, not on its value.
- **MF6 and MF3 are evaluated on arm H5-LRoff** (recency rung disabled) so the measured lag is the server's, not the mitigation's (§11.1, CONS-031); H5 is reported alongside as the shipped configuration.
- MF6 (MailWeave lag vs direct API > 60 s) is fixed regardless of the mitigation decision.
- P7 present and correct in all cases, whatever the measurement showed (rubric FRESH-06).

**CG-REG — Regression**
- Every finding of severity ≥ MEDIUM has a green fixture or a recorded, owner-approved exception (§2.6.3).
- F-seeded fixtures pass on the gate's fresh HOLDOUT seed, not only their originating seed (§9 G10).
- Structural reproduction rate and open-exception count published (§5.3).

**CG-REAL — Real-mailbox behaviour** *(moves rubric **GMAIL-07**, which did not exist until Round 1 of the repair — the reality tier, the correction's headline methodology change, was previously unenforceable at the gate: CONS-022)*
- Zero open BLOCKER findings from Tier 1.
- O1, O2, O3, O5, O8, O9 clean across the round's Tier-1 runs (with denominators reported).
- D2 signature coverage at or above the registered floor; every uncovered signature above the floor has a corpus-extension ticket.
- D4 session executed this round with verdicts recorded and every `found-wrong` / `missed-but-exists` triaged.

### 13.5 Exit criteria changed from Revision 1 — the explicit list

| Revision 1 | Revision 2 | Why |
|---|---|---|
| Loop 4 entry condition: "lexical-only configuration scores < 0.70 recall on F4-T2 at HOLDOUT gate" | **Deleted.** CG-SEM is unconditional | SCOPE §4: semantic retrieval is part of the complete product |
| Loop 4 reject branch: "Otherwise **reject and log the negative result**" | **Deleted as a capability decision.** Survives only for backend/architecture choices (which local model, on-demand vs persistent index, hosted opt-in). SEM-OFF becomes a permanent ablation instead | SCOPE §4, §11 |
| Loop 4 adopt rule: "F4-T2 recall improves ≥ +15 points AND F4 p95 latency ≤ +50% …" | **Replaced by UNSET-empirical bars registered at G0** against the measured SEM-OFF distribution, plus five definitional bars that need no measurement | The +15 was calibrated to an adopt/reject decision that no longer exists; keeping the number would be borrowing authority it never had |
| Loop 5 entry condition: "measured failures concentrated in F5/F6/F7 (case accuracy < 0.75 …)" | **Deleted.** CG-STR is unconditional; F13/F14/F15 added | SCOPE §5 |
| Loop 5 adopt rule: "+10 points vs fixed-window expansion at ≤ +25% tokens" | **Replaced by a budget-matched budget–recall curve** against Baseline F(±2) and C at ≥3 budgets | SCOPE §6 names hit ±2 as the baseline; and an unmatched-budget comparison measures spending, not retrieval |
| Loop 6 sequencing: freshness measured last, after the product is otherwise complete | **Freshness observed from round 1** (Tier-1 D6) and gated by CG-FRESH | SCOPE §12: freshness is part of the completion bar |
| Loop 6: "Whether to add history-based sync to MailWeave is decided by these numbers, not in advance" | **Replaced by six pre-registered mitigation triggers (MF1–MF6)**, five of which need no invented number, plus required mitigation properties and H6 verification | SCOPE §12 requires the mitigation to be *built* before any freshness claim if lag is meaningful |
| Loop 6 completion: protocol complete, N ≥ 30, ≥5 days, pooled arms | **Adds mandatory depth stratification** (0 / 5 / 25) with pooling across strata prohibited | `VERIFIED_RESEARCH.md` §1.3: the reported failure is depth-specific; pooling would hide it |
| F4-T3: "reported separately, never gate-binding in Loops 1–3" | **Reported with a bar registered at G0** | Idiomatic phrasing is in-scope product behaviour |
| Baseline E: e2e tier only | **Mandatory every gate, two budget variants, with a pre-committed claim-narrowing rule** (§8.7) | It is the arm most able to falsify the product's value (arXiv 2607.17598) |
| Baseline set A–E | **Baseline F added** (hit-centred ±N) | SCOPE §6 names it, and Revision 1 had no hit-centred baseline |
| Personal mailbox: spot-checks, excluded from metric tables, no headline claims | **Metric exclusion preserved verbatim; role inverted.** Tier 1 becomes the primary discovery substrate with BLOCKER authority and a finding→fixture lifecycle (§2) | SCOPE §13 |
| Loop 0 gate | **G0 extended**: S11–S14, Tier-1 harness operational, D1/D2/D3/D7 run, reference distributions measured, FSL and all UNSET bars registered | Everything downstream depends on these existing before a number is quoted |
| Sequential Loops 0–6 with possible early stop | **G0 + eight mandatory capability gates**, order-free | SCOPE §2: the loop ends when the rubric passes, not when a minimal baseline looks plausible |

Unchanged and still binding: §13.1 in full (pre-registration, Wilson/bootstrap CIs, two fresh HOLDOUT seeds per gate with per-seed agreement, paired designs, interleaved latency), and the CG-EP / CG-PD / CG-AD numeric proposals exactly as Revision 1 wrote them.

---

## 14. Open questions for synthesis

Revision-1 questions 1–10 are retained (renumbered where their referenced sections moved); Q11–Q18 are new. Questions Revision 1 answered are marked.

1. **Thread-length fallback:** if S6 shows conversations split at ≤100 messages via API insert, adopt the N=90 fraction-preserving grid (§4.4)? Any objection to fractions-as-normative? *(open)*
2. **Auth architecture:** consumer test account + weekly re-auth (7-day Testing-status token expiry, §3.2.9) vs a Workspace account with an Internal OAuth app? *(open; now also affects the Tier-1 personal-mailbox client, which has the same expiry problem and is used every round)*
3. **Scope for MailWeave-under-test:** this plan assumes `gmail.readonly` for the server credential. Does the complete architecture require more (labels-as-state, an index needing `history.list` — which `gmail.readonly` does cover)? *(open; a compensating control is needed if it grows)*
4. **Baseline A attachability:** can the hosted Gmail MCP connector be signed into the seeded test account in our client environment(s)? If organizationally impossible, A′ (reconstructed, labelled) becomes permanent — acceptable? *(open)*
5. **M2 model pinning:** which agent model and judge model to pin, who owns the token budget, and the cadence. *(open; E-generous adds one arm on the subsample)*
6. **Network-level API counting:** TLS-intercepting proxy vs SNI/connection counting? *(now more consequential: the zero-egress assertion for the local semantic default is enforced at this layer, and SNI-only counting is sufficient for it while TLS interception is needed for per-path tallies)*
7. **Numeric bars:** re-scoped. Revision 1 asked synthesis to adopt/adjust all bars. Revision 2 asks a narrower question: confirm the three-class split of §13.2, and confirm that registering UNSET bars against G0-measured reference distributions is the right discipline rather than picking values now. *(open)*
8. **Multi-sender realism:** partly answered. A second sending account is now definitely required — for freshness probes **and** for the S12 delivered-reply-into-deep-thread check. Remaining question: do F2/F6/F14 personas need real sending accounts for realism, or do inserted From-headers suffice? *(open)*
9. **Privacy sign-off:** expanded. R-SEC must review, before first run: the shape-record schema, the salted-hash policy, **the `mailweave inspect` write-path audit** (proving the memory-only forensics path has no disk-writing branch — the forensic buffer it used to name no longer exists, CONS-005), and the fixture scrub assertions — not only the census script. *(open, and blocking G0)*
10. **Non-English cases:** now partly empirical — D2's script/charset distribution will show whether the owner's real mail needs them. Decide after the first census. *(open)*
11. **FSL value** (§11.2.2): the owner must set the freshness service level before the probe run. What lag, on which arm, in which strata, is acceptable for this product? *(open, and blocking CG-FRESH)*
12. **Local embedding model:** which model, which license, which quantization, what footprint, and who pins the revision hash? Note `RETRIEVAL_OPTIONS.md` §4.5's stack implication: Python's local-embedding ecosystem is its strongest argument, and Revision 1 discounted that because semantic retrieval was deferred. It is no longer deferred, so the stack decision should be re-weighed. *(open)*
13. **Salted-hash acceptability** (§2.4.3): hashed tokens are pseudonymous, not anonymous — dictionary-invertible by anyone holding the salt. Is local-only storage plus rotation an acceptable posture, or should token-level correlation be dropped entirely and diagnosis rely on structure alone? *(open; owner + R-SEC)*
14. **D4 cadence and owner attention budget:** real query sessions cost the owner's time, and they are the highest-yield discovery protocol. How many queries per round is sustainable, and is the pre-write-the-expected-answer protocol acceptable in practice? *(open)*
15. **Fixture provenance policy** (§5.4): may structurally-derived fixtures from personal mail live in a public repository at all, or only in a private test directory? The n-gram disjointness assertion makes them safe in our judgement; the owner's judgement governs. *(open)*
16. **Tier-1 counters in public material:** may content-free oracle-violation counts from the personal mailbox appear in the README at all, or is the personal mailbox strictly an internal substrate? §2.7 permits it with caveats; the owner may prefer a blanket no. *(open)*
17. **Forensic buffer TTL and access:** **CLOSED — no buffer exists** (CONS-005). Appendix A.3 permits persistence of short, aggressively-redacted snippets only; the plan's own text conceded "a conservative reading of Appendix A.3 favours human-only", which was the tell that the mechanism was unauthorised. Forensics is now `mailweave inspect`: live re-fetch by ID into process memory, terminal output only, nothing at rest, therefore no TTL to set and no buffer to grant access to. The Stage-2 redacted snippet remains the *only* persisted mail-derived artifact and keeps its per-incident flag, owner approval and R-SEC sign-off. The residual question — *may an implementer agent run `mailweave inspect` against the personal mailbox, or only the human owner?* — is **DECIDED: OD-4** (`docs/OWNER_DECISIONS.md`, 2026-08-30), applied at §2.4.6 Stage 1.
18. **Attachment-content scope** (S13): if Gmail does not index attachment text, is extracting it a MailWeave responsibility in this release, or explicitly out of scope with F8 scored as "retrieve the carrier and signal the attachment"? *(open; affects F8 scoring and a rubric area)*

---

## 15. What I could not verify

Revision-1 items 1–9 stand unchanged (they concern Gmail mechanics that no work since has touched). Items 10–16 are new to Revision 2.

1. **Whether `messages.insert` preserves a caller-supplied `Message-ID` verbatim in all cases.** Docs don't promise it; universally relied on in practice. Covered by smoke test S3; if it fails, ground-truth joins fall back to Gmail `id` from insert responses, losing only `rfc822msgid:` probe queries.
2. **Whether the ~100-messages-per-conversation ceiling applies to API inserts with explicit `threadId`.** Smoke test S6; fallback §4.4.
3. **Whether "The `Subject` headers must match" tolerates `Re:` prefixes at the API threading layer.** S2 decides; byte-identical Subject is the default until then.
4. **`batchDelete` maximum ids per call.** Undocumented; harness chunks at ≤1,000 defensively.
5. **Current live behavior of hosted `search_threads` per-thread message caps.** Baseline A measures and dates whatever is current; §8.1's honesty rules govern reporting either way. *(Note: `VERIFIED_RESEARCH.md` §0 records that the production connector's own tool description now states the ~5-oldest cap verbatim — which is vendor documentation of the behaviour, not a measurement of the API surface we benchmark.)*
6. **Search-indexing latency for *inserted* (non-SMTP-delivered) mail.** Measured by S8, absorbed by the settle gate; the freshness experiment avoids inserts entirely.
7. **The exact per-user rate limit as applied to our project.** Planning uses 6,000 units/min + backoff; confirm in Cloud Console.
8. **`threads.get` message array ordering.** The harness never relies on it — it sorts by `internalDate`.
9. **Gmail-side behavior under sustained bulk insert on a consumer account.** Cannot be verified except by operating.
10. **Whether the owner's real mailbox actually contains the structures this plan is built around** — threads long enough for burial to matter, deep quoting, exotic MIME, near-duplicate clusters, broken threading. D1/D2/D3 will say. If it does not, the position sweep and several new families are testing a hazard that does not exist for this user, and the corpus mix must be rebalanced rather than defended.
11. **The core assumption of the Tier-3 sanitization design: that structure-preserving synthetic re-expression reproduces real parse failures at a useful rate** (§5.2 step 4, §5.3). This is unproven. If the structural reproduction rate is low, the escape hatch of step 5 carries far more weight than intended and the privacy/diagnosis trade-off must be revisited with the owner. Step 4 measures it directly, and the rate is published every gate.
12. **The methodology's own premise** (§1.3): that Tier-1 discovery finds failures Tier 2 would not have found. Tracked as the fraction of round-opening findings originating in Tier 1. If it stays near zero over several rounds, this plan's ordering is wasted effort and should be reported as such.
13. **Whether salted-hash token correlation is an acceptable privacy posture to the owner** (§2.4.3). It is pseudonymous, not anonymous. Q13.
14. **Real-mail freshness behaviour by thread depth.** The depth-specific signature is reported in claude-code #76396 by one user in one account; we have measured nothing. The §11.2.1 stratification exists precisely because we cannot assume it either way.
15. **Whether `history.list`-based reconciliation actually fixes *search-shaped* freshness failures.** This is the sharp one. `history.list` returns arrival events, not query matches; a reconciliation layer must therefore fetch and match the reconciled set itself (§11.2.4 property 2). Whether that is fast enough, complete enough, and correct enough to close the gap is a hypothesis until arm H6 measures it — and `SCOPE_CORRECTION.md` §12 names history-based reconciliation as an example ("or another defensible mechanism"), not a guaranteed fix.
16. **Local embedding quality on email-shaped text.** No measurement exists. `RETRIEVAL_OPTIONS.md` §4.5's ecosystem claims are flagged there as general knowledge, not re-verified. Everything in §7.1 about the local default is a plan to measure, not a claim about what we will find.

### Primary sources (fetched 2026-08-30)

- insert: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/insert
- import: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/import
- InternalDateSource: https://developers.google.com/workspace/gmail/api/reference/rest/v1/InternalDateSource
- Message resource / threadId criteria: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages
- Threads guide: https://developers.google.com/workspace/gmail/api/guides/threads
- Sending guide (raw RFC 2822): https://developers.google.com/workspace/gmail/api/guides/sending
- batchDelete: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/batchDelete
- Quotas: https://developers.google.com/workspace/gmail/api/reference/quota
- Scopes: https://developers.google.com/workspace/gmail/api/auth/scopes
- OAuth token expiry (Testing status): https://developers.google.com/identity/protocols/oauth2
- Hosted Gmail MCP: https://developers.google.com/workspace/gmail/api/reference/mcp and .../mcp/tools_list/search_threads
- Discovery doc (defaults, scopes, media limits): googleapis/google-api-go-client `gmail/v1/gmail-api.json`, revision 20260727
- History/sync (Loop 6 background): https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.history/list , https://developers.google.com/workspace/gmail/api/guides/sync
- Conversation ceiling (third-party): https://support.cloudhq.net/how-does-gmail-decide-to-group-emails-into-conversations/

- arXiv 2607.17598, "Is Progressive Disclosure All You Need for Long-Context Agents?": https://arxiv.org/abs/2607.17598 (via `VERIFIED_RESEARCH.md` §8.1 — the basis for Baseline E's promotion, §8.7)
- arXiv 2604.03455, lightweight query routing for adaptive RAG: https://arxiv.org/abs/2604.03455 (via `VERIFIED_RESEARCH.md` §8.2)

### Internal governing documents

- `docs/SCOPE_CORRECTION.md` — authoritative scope; §12 (freshness), §13 (real Gmail primary), §16 (rubric areas), §17 (implementer/reviewer loop), Appendix A (binding owner decisions: A.1 local-default semantic backend, A.2 dedicated seed account, A.3 real-mailbox data handling)
- `docs/AGENT_LOOP.md` — finding schema, severities, round protocol, anti-gaming obligations, release gate
- `docs/RELEASE_RUBRIC.md` — criteria authority (in preparation; §12 references areas, not IDs)
- `docs/SECURITY_NOTES.md` — §1.5 scope sets, §2.5 account pinning, §3.2–3.3 secrets and repo hygiene, §4.1–4.3 data-at-rest and the two-mailbox redaction policy, §6.3 untrusted-content response format
- `docs/RETRIEVAL_OPTIONS.md` — Option B (on-demand semantic) and its honesty obligation, Option D (structural), quota and latency ground truth
- `docs/VERIFIED_RESEARCH.md` — §1.3 depth-specific freshness nuance, §7 MCP 2026-07-28 handle discipline, §8.1 progressive-disclosure prior art
- `MAILWEAVE_CONTEXT.md` — §4 (freshness separation), §34–39 (metrics, baselines, invariants), §53–58 (loop discipline, experiment log, falsifiability, claim discipline), §66 (the hypothesis)


---

## 16. For owner decision — reconciled after Round 1

*(Rewritten by the Round-1 **reconciliation** pass, which reconciled this list with
`ARCHITECTURE_DECISION.md` §I's O-1…O-8. Items 1, 2, 3, 5 and 6 are settled and are recorded as such;
the residue is consolidated in **`docs/OWNER_DECISIONS.md`**. Numbering stays shared with
`RELEASE_RUBRIC.md` and `PRODUCT_CONTRACT.md` §10.)*

**Settled — no longer open:**

1. ~~Completeness semantics (CONS-004; ARCH §H-2, ADV-209).~~ **RESOLVED.** PART-01 = "what the source
   reported at `fetched_at`" at 100 %; manifest equality sits in GMAIL-03 with a **gate-binding** bound
   registered from **PF-1 at G0** (§13.3). The residue is a measurement this plan already owns, not a
   ruling.
2. ~~DISC-02 (CONS-001; ARCH §H-1).~~ **RESOLVED.** Published either way; a loss is a finding and a
   tuning input; Baseline F(±2) stays a permanent fixture (§8.8, §9 PROC-04) and may never ship as the
   policy (SC §6).
3. ~~The hit set `H` (CONS-003; ARCH §H-5 as amended by ADV-109).~~ **RESOLVED.** Contract I-1 and rubric
   EV-01 carry one clause, and `ARCHITECTURE_DECISION.md` A.7a now quotes it verbatim with its
   instantiation named. Nothing in this plan's metrics changes: P6 (§6.2) and the trace's
   `semantic.pool_ids[]` are what EV-01 is joined against.
5. ~~DISC-05's scope (ADV-208).~~ **RESOLVED in the measure-don't-remove direction** — see §7.5.1's scope
   note. `levels_traversed_to_answer` covers the content-depth vocabulary; nothing is dropped.
6. ~~R-DOC as an eighth reviewer domain (CONS-019).~~ **RESOLVED.** `AGENT_LOOP.md` §2.3 now carries
   **R-DOC — documentation accuracy and claim discipline**, so §12's Documentation-accuracy row names a
   domain that exists in the process definition.

**DECIDED (2026-08-30) — see `docs/OWNER_DECISIONS.md`:**

4. **Who may run `mailweave inspect` against the personal mailbox** — an implementer agent, or the human
   owner only? The buffer is gone (CONS-005) and forensics is live-re-fetch-into-memory, but the access
   question A.3 raises survives the mechanism change. This is the residue of Q17. → **OD-4: decided —
   owner-approved per incident when mail text is surfaced; structure-only diagnostics autonomous**
   (applied at §2.4.6 Stage 1).

**Two owner items this plan itself creates, now named explicitly:**

- **OD-1 — the Freshness Service Level.** §11.2.2 states in terms that this plan may not set it and that
  inventing a number here would be the dishonesty the pre-registration discipline exists to prevent. It
  must be written into experiment log 001 **before the probe run starts** (rubric FRESH-05, §13.4
  CG-FRESH), expressed as a lag bound + the arm + the depth strata. **MF2 and MF5 cannot be evaluated
  without it**, so this is the one owner item that blocks a measurement rather than a document.
- **OD-3 — acceptance of the E2 reply-chain floor's depth narrowing** (ARCH §H-9). Decided in
  measurement by **F17** (§4.7) at each degradation tier, bound at CG-PD; the owner is asked to accept
  the narrowing now and to pre-authorise the branch if F17 fails, so the loop does not stall at a gate.

**OD-2** (ROUTE-04's 100 % empty-diagnosis bar) touches this plan only through the constructed
relaxation cases: if the owner keeps the bar absolute, the constructed set must be capped at
**6 constraints**, which would have been a §4 case-construction change. **Moot as of OD-2 (2026-08-30):**
the owner scoped the promise to drops actually probed, so §4's cases stay uncapped and no
case-construction change is required.

---

## REPAIR LOG (Round 1)

Applied against `docs/reviews/CONSISTENCY_AUDIT_1.md` (40 findings) and the rubric/contract-implicating
parts of `docs/reviews/ARCH_REVIEW_1.md`. Every BLOCKER and HIGH that names this document is listed,
including the ones **not** closed and why. Nothing below weakens a requirement: where a bar moved it
moved **up** (CG-PD P2/P3 0.98 → 1.00), where a mechanism was deleted it was **replaced** by one that
does the same job under the binding constraint, and every genuinely unmeasurable value stays UNSET with
its registration procedure named.

### BLOCKERs

| Finding | What changed | Where |
|---|---|---|
| **CONS-005** privacy — §2.4.6 Stage 1 persisted unredacted personal bodies | **Buffer deleted.** Stage 1 is now `mailweave inspect <trace_id>`: live re-fetch of the trace's message IDs into process memory, terminal output only, nothing written to disk — the mechanism `ARCHITECTURE_DECISION.md` resolves T-5/T-SN1 with. Stage 0/2/3 unchanged; Stage 2 keeps its per-incident flag, owner approval and R-SEC sign-off. The ladder still answers "I need to see it to fix it" | §2.4.6 (rewritten, with the reasoning recorded); §2.4.4 (raw query never persisted); §2.4.7 (CI now audits *write paths*, since there is no writer to exempt); §2.5 D4 and D8; §2.6.1 record (`Forensic buffer:` → `Re-open with:`; `Local trace:` no longer claims to hold raw query text, which SN §4.3 forbids); §5.2 steps 1, 2, 6, 8; §13.3 G0 (`forensic buffer encrypted with a TTL` → **`mailweave inspect` built and PF-8 green**); §12 R-SEC row; §14 Q9 and **Q17 closed as "no buffer exists"** |
| **CONS-006** DISC-05 unmeasurable | Added **§7.5.1 the large-thread depth arm**: PD-DEPTH-N1 (flat map + declared truncation + affordance) vs PD-DEPTH-N (segment map), same cases at/above the PF-6 flat-map token boundary, same budget, paired; plus metrics **`levels_traversed_to_answer`** and **`map_tokens`**; plus the CG-PD gate line "the depth comparison is published; the deeper level ships only on a measured win, else it is removed (E.2)" | §7.5.1 (new); §6.4 (new metric block); §13.4 CG-PD |
| **CONS-008** R-02/R-03 unmeasured | **P4 widened** from the three-value set (matched/context/derived) to the contract's **full seven-value role set**, and it now also asserts a non-empty mechanical `reason` on every disclosed message. P4 is the measurement behind new rubric criterion **PART-07** | §6.2 P4; §13.4 CG-PD (bar unchanged at ≥0.95 over a strictly harder assertion) |
| **CONS-002** egress unsatisfiable | Every "gmail.googleapis.com only" claim replaced by the **two-host runtime allowlist** `gmail.googleapis.com` + `oauth2.googleapis.com` (token refresh only); model hosts are **setup-time only** with runtime loading forced offline (`local_files_only` / `HF_HUB_OFFLINE`) from a checksum-pinned path, and S14 now asserts a **cold** load so the hub revalidation request is actually exercised (ADV-210) | §7.1 bar 2; §3.9 S14 |
| **CONS-015** SEM-01's retired bar | No EP change was needed and none was made: §13.5 already retired the +15 and deleted the entry condition, and §13.2 already classes `semantic_gain` as UNSET-empirical. The defect was the rubric reinstating them, and it was repaired there | (rubric SEM-01) |
| **CONS-001 / 003 / 004** | Repaired in `RELEASE_RUBRIC.md` / `PRODUCT_CONTRACT.md`; this plan's §12, §13.4 and §7.2 already read the corrected way and now cite the repaired criteria | — |

### HIGHs

| Finding | What changed | Where |
|---|---|---|
| **CONS-007** T-CD2 untested | Added family **F17 decision-reversal**, n = 8: highest query-scoring messages support A, a low-scoring later reply reverses it to B, distractors reinforce A; correct answer B; scored strictly; run in **both** the query-aware and Baseline F(±2) arms. It is the only test of the non-negotiable E2 reply-chain floor | §4.7; §13.4 CG-PD |
| **CONS-016** escalation trigger unmeasured | Added the **trigger ablation** to §7.4: F11/F12 with the trigger set to (i) query-shape only and (ii) query-shape ∨ `answer_type_presence`, reporting under-escalation (F11) and over-escalation (F12) for each; the composite ships only on a measured under-escalation reduction inside the F12 ceiling and PERF-01, else `answer_type_presence` is removed per E.2 | §7.4; §13.4 CG-AD |
| **CONS-014** embedding-bait fixtures missing | Added fixture class **`I1-bait`** with its three assertions (does not displace true evidence from the disclosed prefix in a paired comparison; selection reason and `model_id@revision` visible; neither dropped nor unfenced) | §5.1 |
| **CONS-011** partiality bars disagreed | **CG-PD's P2/P3 raised 0.98 → 1.00** to match rubric PART-02/03 — the honest direction, since these are mechanical self-consistency assertions — plus an explicit **PART-0n ↔ P-n mapping note** so a reviewer cannot apply P4's bar to PART-04 | §6.2 (mapping note); §13.4 CG-PD |
| **CONS-019** DOC criteria had no ordinary-round owner | §12's Documentation-accuracy row now names **R-DOC (+ adversarial reviewer at the gate)**. Adding R-DOC to `AGENT_LOOP.md` §2.3 is recorded as a **recommendation** — this plan does not own that file *(since applied by the Round-1 reconciliation pass; see that log below)* | §12; §16 item 6 |
| **CONS-010 / CONS-012** freshness | No weakening was needed here: §11.2.1's strata and §11.2.3's MF1–MF6 already said what the rubric had narrowed. CG-FRESH now states the FSL-registration check and the arm the MF triggers are evaluated on, and the rubric was brought up to this plan | §13.4 CG-FRESH; (rubric FRESH-01/02/05) |
| **CONS-013 / CONS-018 / CONS-020 / CONS-021 / CONS-022 / CONS-017 / CONS-009** | Rubric-side repairs (new criteria SEM-06, FRESH-06, SEC-08, DOC-06, GMAIL-07; PROC-04's baseline inventory; the three bracket classes; 39 stale citations). CG-REAL now names GMAIL-07 as the criterion it moves | §13.4 CG-REAL; (rubric) |
| **CONS-025** content-processing components unspecified | **NOT CLOSED — not ours.** The fix is a new `D.4a Content processing` subsection in `ARCHITECTURE_DECISION.md` (HTML→text parser, quote/signature stripper, MIME/charset boundary, each with its licence). INJ-04, GMAIL-02 and DISC-03 continue to rest on an unnamed component until the architecture agent lands it | escalated |

### MEDIUM / LOW closed here

**CONS-023** `claimed_total := stated_total` stated once in §6.2 and once in the rubric's How-to-use.
**CONS-031** added arm **H5-LRoff** to §11.1 so MF6/MF3 measure the server rather than the recency
mitigation; moving LR itself into ARCHITECTURE §E.2 with its removal gate is **not ours** and is
escalated. **CONS-039** the preserved §6.1 self-reference now carries a footnote resolving "Tier-1
driver policies … §6.1" to "**M1** driver policies … **§10.1**", with the verbatim text left standing
per the preservation rule. **CONS-040** §12 is re-keyed to `RELEASE_RUBRIC.md` criterion IDs, and the
REALITY-FINDING record gained a `Rubric criteria:` field.

### Not closed, and why

- **CONS-025** (architecture must name the parser/stripper/charset components) — `ARCHITECTURE_DECISION.md` was owned by another agent this round. **Since closed there: D.4a** names selectolax (MIT) + lxml (BSD) fallback, talon (Apache-2.0, MIT fallback), stdlib `email` with RFC 2047 decoding and a declared charset ladder, and the sockets-disabled test obligation under PF-5 — verified by the reconciliation pass against that document.
- **CONS-031(a)** (move the LR recency rung into ARCHITECTURE §E.2 with a removal gate) — same reason; the EP-side half (arm H5-LRoff) is done. **Since closed there: E.2's LR row** names arm `H5-LRoff` as its gate, so both halves now agree.
- **CONS-027** (spec-revision status) — the half that lands in `CONTEXT_DISCLOSURE_OPTIONS.md`'s addendum is outside this repair's file ownership; the `SECURITY_NOTES.md` half is appended to that document's addendum.
- **CONS-029 / 036 / 037** — all `ARCHITECTURE_DECISION.md` LOWs.
- **Items 1–6 of §16** are owner decisions, not defects an agent may close (`AGENT_LOOP.md` §8).
  **Reconciled after Round 1:** items 1, 2, 3, 5 and 6 are settled and recorded as such in §16; item 4
  is consolidated, with the plan's own two (the Freshness Service Level and the F17-decided acceptance),
  in `docs/OWNER_DECISIONS.md`.

### Preservation check

Every block marked *verbatim, Rev-1* is still verbatim. The Revision-1 text this repair touched was
touched **only** in Revision-2-authored sections (§2, §4.7, §5.1, §5.2, §6.2's assertion table and
§6.4, §7, §11.2, §12, §13.3–13.5, §14) or by **adding a footnote beside** preserved text without
altering it (§6.1, CONS-039). The two rules the plan calls the ones that make it honest — FNF and
hallucinated-found always reported together, and headline metrics deriving only from harness-measured
plus manifest-scored fields — are untouched, as are §13.1's hygiene rules and the "no ground truth →
no headline metric" claim rule.

---

## REPAIR LOG — Round 1 — reconciliation

*Applied by the reconciliation pass after `ARCHITECTURE_DECISION.md`'s parallel repair landed. Every
change below either records a settlement made elsewhere, corrects a citation that went stale when the
architecture changed under it, or adds a bar. **No bar was lowered, no case family was reduced, and no
`[UNSET]` was filled in with an invented number.***

| # | What changed | Where |
|---|---|---|
| **E-1** | **§16 rewritten.** Items 1, 2, 3, 5 and 6 recorded as **RESOLVED** with their settlement locations; item 4 (forensic access) stays open as **OD-4**. Two owner items this plan itself creates are now named — **OD-1** the Freshness Service Level (§11.2.2's own words: the plan may not set it; MF2/MF5 cannot be evaluated without it) and **OD-3** the acceptance decided by F17 — plus **OD-2**'s consequence for §4's constructed relaxation cases | §16 |
| **E-2** | **CG-AD's cost bar joined to `api_calls`.** The preserved "median network API calls ≤ 3" figure is retained as an `http_requests` bound and a second bar is registered on `api_calls` — `[UNSET — registered at G0 against the G0-measured Baseline D distribution on F1/F2]` — because under HTTP batching the proxy-visible count bounds chatter, not cost (ARCH §H-8, ADV-106). The Revision-1 text is joined, not altered, per the preservation rule; rubric AD-04 carries the identical pair | §13.4 CG-AD |
| **E-3** | **§11.1's `H5-LRoff` citation corrected.** It described LR as "a 2-unit recency rung shipped unconditionally" per ARCH D7; LR is now **Experimental with a removal gate** in ARCH E.2 and costs `2 + 20n` (ADV-101). The arm's purpose is unchanged and it is now identified as the gate E.2 reads | §11.1 |
| **E-4** | **§7.5.1's scope caveat resolved** in the measure-don't-remove direction: `raw` is not independently requestable, `snippet` stays, and `levels_traversed_to_answer` covers `stub → snippet → body_clean → body_full` as well as the segment map. Removing a shipped level would be the scope reduction SCOPE §1/§6 forbids | §7.5.1 |
| **E-5** | **Round-1 "Not closed" entries updated**: CONS-025 and CONS-031(a) have landed in `ARCHITECTURE_DECISION.md` (D.4a; E.2's LR row), verified against that document rather than taken on report | REPAIR LOG (Round 1) |

**Checked and deliberately not changed.** §4.7's F17, §7.4's trigger ablation, §7.5.1's depth arm and
§11.1's `H5-LRoff` are the measurements the architecture asked for; the reconciliation pass pointed the
architecture *at* them rather than editing them. Every block marked *verbatim, Rev-1* remains verbatim —
E-2 adds beside the preserved CG-AD text and does not alter it.
