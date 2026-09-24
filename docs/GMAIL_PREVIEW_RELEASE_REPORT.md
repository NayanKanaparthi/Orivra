# GMAIL_PREVIEW_RELEASE_REPORT.md — draft, not a release

**Status: DRAFT.** This document exists so that the claims boundary and the verification record
are written down before anything is distributed, not after. It does not authorise a release,
and several rows below are open.

**Authorities.** Scope: `ORIVRA_V1_PLAN.md` §9a and
`docs/reviews/RELEASE_AMENDMENT_GMAIL_PREVIEW_2026-09-18.md`. Criteria: `RELEASE_RUBRIC.md`.
Process: `AGENT_LOOP.md`. Nothing here waives a rubric row; waiving is a human decision
recorded in the findings ledger.

---

## 1. What may be said about this release

Permitted:

- "Orivra for Gmail, preview." One connector. Read-only, on a single `gmail.readonly` scope.
- "The evidence graph is correct and bounded": every node and edge names its supporting
  sources; observed, source-stated and inferred relations are distinguishable on their face;
  every branch the budget dropped carries an executable handle; continuations are bound to a
  view so a changed page cannot silently skip or repeat evidence.
- "Live authorization and freshness are checked on every disclosure", including resources.
- "No generative model is called at runtime" — a hard constant, zero, not configurable.

## 2. What may not be said

Carried verbatim in force from `ORIVRA_V1_PLAN.md` §9a.4:

- **Nothing cross-source.** No "across your tools". Drive and Slack do not ship and do not
  appear in the surface, the docs or a screenshot.
- **Nothing about the graph's usefulness.** H4 is not decided in M3. "The graph is correct and
  bounded" is sayable; "the graph makes retrieval better" is not.
- **No performance or quality claim without its comparison.** H1/H2/H3 have not run. Nothing
  describes depth or ordering as query-aware, and nothing compares MailWeave to the native
  Gmail connector.
- **No freshness claim** before PF-10.
- **Not "v1".**

Added by this release's own work:

- **No claim that the inferred confidence is a probability.** `1/n` is a heuristic allocation
  across candidates nothing distinguishes. It is uncalibrated, no labelled set has been scored
  against the method, and it must not be thresholded or compared with another method's number.
- **No claim that the cache is persistent.** It is in-memory and per-process. Plan §5.1's
  on-disk cached category is not built (`docs/GMAIL_PREVIEW_CACHE.md` §2.1).
- **No claim that the whole suite passes on a clean machine.** It passes on the exported tree
  in an isolated runner, and the export is proven byte-identical to the working tree by a
  sha256 manifest. That is a different sentence and this report uses the different sentence.

## 3. Verification record

| What | Where it ran | Result |
|---|---|---|
| Full test suite | isolated Linux runner, over the export verified byte-identical to the working tree (634 files, sha256 manifest) | see §3.1 |
| Orivra, surface, graph, cache, walk and offline suites (18 files, 444 tests) | **the Mac working tree itself** | exit 0, no failures |
| `ruff` | the Mac working tree | clean over `orivra/src` and every test file this work touched |
| `mypy` | the Mac working tree | clean, 42 Orivra source files |
| `tools.guards` | the Mac working tree | clean: forbidden-import, generative-client, gmail-endpoint, ground-truth-isolation, no-listening-socket, no-model-host-at-runtime, scope-literal, unaudited-disk-write, unwrapped-http-client |
| Clean install from a distribution artifact (NFR-04) | fresh Python 3.12 venv, cloud container, no repo on the path | §3.2 |

### 3.1 Full suite

At working-tree head `3099a92`, over the export verified byte-identical to that tree by a
sha256 manifest across 634 files:

**4412 collected — 4408 passed, 4 skipped, 0 failed.**

The count rose by 14 from the previous run, which is exactly the tests this round added: 11
cache-wiring, 2 walk-demonstration, 1 confidence-semantics.

Two earlier failures are closed, and how they were closed matters more than that they were:

* **`ws10` never failed.** The earlier report of it was a parsing error — a regex matching the
  leading `F` of `FAILED` and `E` of `ERROR` in pytest's *summary* lines rather than its
  progress bar. Parsing the progress lines correctly shows no `F` or `E` against it in any run
  since, and it also passes as a planted subprocess under the replant harness.
* **`R213` was a real hole in the mutation harness, not in the product.** The planted
  subprocess inherited `dict(os.environ)`, and importing the semantic backend in the parent
  writes the offline flags into the *process* environment — so the child inherited exactly what
  the planted deletion removes. That is why it passed in isolation and failed only in the full
  suite: whether the parent had imported the backend yet decided the verdict. Fixed by
  excluding the variables the product writes, derived from the product rather than listed, with
  a guard test that fails if a second writer appears.

A run that reports only its successes is not a record. This one has no failures to name.

### 3.2 Clean install

Three wheels build from the tree (`mailweave`, `orivra`, `mailweave_harness`). Installing
`mailweave` and `orivra` — not the harness, which is not part of a release — into a fresh 3.12
venv gives:

- both packages resolving from `site-packages`, asserted **not** to resolve into the working
  tree;
- eight tools, every one `read_only_hint=True` and `destructive_hint=False`;
- one Gmail scope, `gmail.readonly`; runtime egress allowlist of exactly two hosts
  (`gmail.googleapis.com`, `oauth2.googleapis.com`), disjoint from the setup allowlist;
- `orivra --version` and `mailweave --version` answering;
- `orivra serve` with no configuration exiting **1**, naming the cause on stderr, with
  **zero bytes on stdout** — which matters because stdout is the MCP transport.

**Open, minor:** the startup refusal prints a 15-line Python traceback rather than one line.
The cause is named and stdout stays clean, so this is polish rather than a defect, but a first
run on someone else's machine is the worst place to show a traceback.

**Not yet done:** this was a clean *environment*, not a clean *machine*. NFR-04 as a release
check means someone else's computer, from a published artifact, following `SETUP.md` as
written.

## 4. Security and repository hygiene

### 4.1 Clean

- Neither OAuth client file is tracked; both are matched by `.gitignore` lines 16 and 17; both
  are mode `0600` on disk.
- No live secret shapes in tracked files. Every `ya29.`, `GOCSPX-` and `1//` literal found is a
  named synthetic canary in a test or a placeholder in `SETUP.md`.
- Nothing in the shipped code binds a listening socket (guard clean over both source trees).
- `GENERATIVE_LLM_CALLS` is 0 and is not configurable.

### 4.2 Open — **blocking distribution, and requiring separate approval**

- **Both OAuth client blobs are still reachable in git history.** They were committed and later
  untracked (`d3e3d5f`, `878c100` are the untracking commits; four commits touch each path).
  The blobs remain: `a455f6c36dc3` (405 bytes) and `34798b456543` (406 bytes). Untracking a
  file does not remove it from history, so **any push of this repository publishes both
  credentials.** This is plan §9a.3's "credential rotation and repository sanitisation" with a
  concrete target list. Rotation and history rewriting both need explicit approval and neither
  has been done.

  **Forensics completed 2026-09-19, and the picture is worse than "reachable in history".**

  | Fact | Finding |
  |---|---|
  | Reachable from `HEAD` | **both**, not only from orphaned commits |
  | Refs carrying them | `main`, `orivra-gmail-preview`, **and the `v0.1` tag** |
  | Introduced by | `0162e79` (server), `948bd2a` (harness); re-added at `dd0711c` |
  | Earliest offending commit | `0162e79`, **163 of 170** commits renamed |
  | Commits a rewrite renames | **163** of **170** (`0162e79` and every descendant, across both branches). Figures are read from the repository, not carried forward: `RELEASE_OWNER_ACTIONS.md` §4 states how |
  | Blob contents | Google installed-app client JSON: `client_id`, `client_secret`, `project_id`, the three URIs, `redirect_uris` |

  **Nothing else is exposed.** A sweep of all 1,955 blobs in history for `client_secret`,
  `refresh_token`, `access_token`, private-key headers, bearer tokens and the real Google
  client-id shape found the client-id shape in exactly those two blobs and nowhere else. Every
  other `client_secret` / `access_token` literal in history — in `tests/test_seed_driver.py`,
  `tests/test_auth_and_config.py`, `tests/test_round25.py`,
  `tests/test_mcp_surface_round24.py` and `docs/SETUP.md` — is a placeholder or a named
  synthetic canary, classified by shape rather than eyeballed.

  **Rotation before rewriting, not after.** A rewrite makes the blobs unreachable from the refs
  it rewrites; it does not make the secrets untrue. Whatever has already seen this repository
  has seen them, and the only act that ends the exposure is issuing new client credentials in
  the Google Cloud console and deleting the old ones there.

### 4.3 Open — minor hygiene

- ~~`_to_delete/`, `Claude outputs/` and `walk.json` are untracked and **not** ignored.~~
  **Closed 2026-09-19.** All three are now ignored. `marketing/` is deliberately *not* ignored:
  it is untracked because it is being handled on a separate track, and hiding it from
  `git status` would be a different mistake from the one this row was about.
- `tests/` carries pre-existing `ruff` findings in files outside this work. Untouched
  deliberately: a broad autofix would put unreviewed changes into a release commit.

## 4a. Found while reconciling, 2026-09-19 — **the "v0.1 unchanged" claim is not true as written**

§9a.2 binds "The v0.1 legacy Gmail path unchanged in names, schemas, defaults and observable
behaviour", and §1 permits saying so. Comparing the four legacy tools' published input schemas
at `v0.1` against `HEAD`, key by key:

| Tool | Change | Breaking? |
|---|---|---|
| `mailweave_search` | `pool.scope` **removed** | **yes** |
| `mailweave_search` | `pool.window` **removed** | **yes** |
| `mailweave_search` | `pool.max_messages` added | no |
| `mailweave_search` | `budget.max_recency_fetch` added | no |
| `mailweave_thread_map` | `page` added | no |

Nothing else in the four schemas moved. The two removals are the whole of it, and they are a
real break rather than a paper one:

```
parse_search({"query": "x", "pool": {"scope":  "auto"}})  ->  REFUSED: unknown pool key 'scope'
parse_search({"query": "x", "pool": {"window": "7d"}})    ->  REFUSED: unknown pool key 'window'
```

At `v0.1` both keys were published, accepted, and documented as changing no retrieval because
the semantic rung was not built — "answered with an in-band `semantic_unavailable` note". M2
built that rung and reshaped the argument around it. So a v0.1 client that sent either key got
a successful response with a declared note, and the same call now gets `INVALID_PARAMS`.
Accepted-and-declared to rejected-as-malformed is an observable behaviour change on the legacy
path under any reading of the clause.

This was not introduced by the preview work; it arrived with M2 and went unnoticed because no
check compared the published schemas across the tag. **It is an owner decision, not a defect to
fix unilaterally**, and it is listed as such. The cheapest resolution is to accept both keys
again as declared no-ops, which restores the v0.1 contract exactly and changes no retrieval.

## 5. Every remaining row, reconciled

**Reconciled 2026-09-19.** Each row is now in exactly one of two states and carries the reason
and, where deferred, the claim limitation the deferral buys. "Explicitly deferred for this
beta" is a decision, not a gap: it means the row does not block distribution *provided* the
claim beside it is not made.

**The Desktop demonstration closes row 1 and nothing else.** It is one question, one mailbox,
one run, reported rather than machine-verified. It is not evidence for rows 2-6.

### 5.1 Must pass before distribution

| # | Item | State | Why it blocks |
|---|---|---|---|
| 7a | Replacement OAuth clients issued and verified | **open** — `RELEASE_OWNER_ACTIONS.md` §2. The procedure is now executable: every flag in it was run against the shipped parsers, and both harness refusals were observed firing before any network call. Three instructions that would not have worked were removed, including one that would have failed a correct run | Owner action. Reversible, and the precondition for 7b |
| 7b | Old OAuth clients retired | **open** — §3 | The only act that ends the exposure. Until it is done the secrets in history are live credentials, and every distribution widens the audience |
| 7c | Git history rewritten | **open** — §4 | Blocks pushing the repository. Does **not** block the artifact, which carries no history |
| 11 | `pool.scope` / `pool.window` restored | **CLOSED 2026-09-19** | Both republished as accepted no-ops with v0.1's own value shapes; `tests/test_v01_input_compatibility.py` compares the published key set against the tag on every run |
| 13 | Artifact inspected for credentials and unintended files | **CLOSED 2026-09-19** | All four artifacts enumerated member by member. `RELEASE_OWNER_ACTIONS.md` §6.1 |
| 14 | `uv.lock` regenerated after the version bump | **CLOSED 2026-09-19** at `2588740`. 104 packages before and after, none added, none removed; the only versions that moved are the two workspace members | — |
| 15 | PF-5(b) weights load and execute behind a real network boundary (case 1) | **open.** The 2026-09-19 Mac run is **proxy-constrained smoke evidence and closes no clause**. What it shows: exit 0, a real 512-dim embedding and a real rerank from provisioned local weights, isolated empty auxiliary caches, every proxy-honouring client pointed at a closed port. Log preserved byte-for-byte at `preflight-records/raw/PF-5b-case1-smoke-2026-09-19.log`, SHA-256 `45373dee…`; timings diagnostic only; the empty-cache listing is operator-reported, not in the log. **Still open, all six:** an enforced network boundary (proxy variables are not one), ADV-210's revalidation path (empty caches do not force it; an absent retry ladder does not distinguish blocked from never-attempted), the full suite cold-started, the in-band `semantic_unavailable` decline, the runtime allowlist against the two permitted hosts, and the cache listing as preserved evidence. `RELEASE_OWNER_ACTIONS.md` §7a | A safety clause, not a benchmark. **The gap is not the full-suite form alone** |
| 16 | PF-5(b) no-weights installation does not reach for them (case 2) | **open, evidence recorded.** Shown in isolation 2026-09-19, proxy-constrained: load fails by name, no download attempted, 0 files written to isolated caches. Same limit as row 15 — the constraint was proxy variables, not an enforced block, so this is evidence about the loader's behaviour, not about egress. Re-running it on the owner's machine would confirm it against their installed `sentence-transformers` | — |

### 5.2 Proposed deferrals — **owner decisions, not yet taken [corrected]**

**Nothing in this section is approved.** The first draft of it read as though these had been
decided; they have not. Each row is a *proposal*: the reason it is proposed for deferral, and
the claim the deferral forbids. They are split because they are not the same kind of thing.

#### 5.2a Safety checks — proposed for completion, not deferral

These bound what the software may do. A deferral here is a decision to ship without having
checked a boundary, which is different in kind from shipping without a performance number.
Two of the three are now closed; the third is one owner-run command away.

| # | Item | State | If deferred anyway, the claim it forbids |
|---|---|---|---|
| 4a | **PF-5(a)** token-free model download, licence and SHA-256 recorded | **CLOSED 2026-09-19.** `models.lock` records a pinned revision, per-file SHA-256 and the licence for both stages; `test_pf5_network_boundary.py` holds that the provisioning path reads no credential from the environment and sends no `Authorization` header, so the download cannot be one that only works on a machine with a token | — |
| 4c | **PF-5(c)** content pipeline with sockets disabled (INJ-04) | **CLOSED 2026-09-19.** The pipeline already ran under the suite's socket ban; what was missing was an input that tempts it. A document carrying an external DTD entity, a remote stylesheet, a remote image and a CSS `url()` now goes through both parsers: no fetch is attempted, none of the four hosts reaches the extracted text, and the entity body is not substituted in | — |
| 4b | **PF-5(b)** weights execute behind an enforced boundary | **OPEN — not partly closed.** `RELEASE_OWNER_ACTIONS.md` §7a splits it into two runs. Case 2 (no weights, no reach) ran in isolation; case 1 (real encode and rerank from provisioned local weights) ran on the owner's Mac on 2026-09-19 — log at `preflight-records/raw/PF-5b-case1-smoke-2026-09-19.log`, SHA-256 `45373dee…`, filed as **proxy-constrained smoke evidence**, timings diagnostic only, empty-cache listing operator-reported. **Neither closes a clause.** Both constrained proxy-honouring clients with environment variables, which is not an enforced boundary, and neither put the loader on ADV-210's revalidation path — empty auxiliary caches remove a fallback rather than forcing a revalidation, and an absent retry ladder does not distinguish blocked from never-attempted. What *is* held, in code and offline: the allowlists are disjoint, the offline flags are set before any hub-aware library is imported, the loader declines rather than reaching out, weights load by path and never by repo id, and a planted subprocess does not inherit the flags it is meant to set. §7a enumerates six open items | **No claim that the runtime has been proven not to reach the model host**, on a cold machine or any other. The boundary is described as **tested in code and not verified at runtime**; the words "enforced", "cold-verified" and "proven offline" are not used in any material. Specifically unclaimed: that egress was blocked, that ADV-210's revalidation path was exercised or suppressed, that the suite has run cold-started, that the server declines in band live, and that the runtime allowlist has been exercised against `gmail.googleapis.com` / `oauth2.googleapis.com` |

#### 5.2b Performance and comparison — proposed for deferral

These are measurements. Deferring one costs a claim and nothing else.

| # | Item | Why deferral is proposed | Claim the deferral forbids |
|---|---|---|---|
| 3 | FRESH-01 / PF-10 freshness protocol, OD-1's service level | live and timed; mailbox work is frozen | No claim about freshness *latency* or any service level. The freshness *check* is offline-tested and may be described; how fast it is may not |
| 9 | Comparative acceptance H1/H2/H3 | a campaign, out of scope for a beta | **The widest one.** No performance claim, no quality claim, no comparison against any baseline, no "better than", no retrieval-quality number |
| 10 | Plan §5.1 persistent cache | not built; deferral argued in `GMAIL_PREVIEW_CACHE.md` §2.1 | No claim of cache persistence across processes. The in-memory per-process cache may be described as exactly that |
| 12 | Graph pagination beyond the simple case; cache reuse | offline coverage only; not exercised live | No claim that cursor/view refusal or cache reuse has been demonstrated against a live mailbox |

#### 5.2c Coverage — proposed for deferral, each with a live check behind it

| # | Item | Why deferral is proposed | Claim the deferral forbids |
|---|---|---|---|
| 2 | GMAIL-01 live-mailbox smoke suite | needs the real mailbox | No claim that the preview is verified end-to-end against a live mailbox beyond the single demonstration in 5.3 |
| 5 | SEC-07 port scan | needs the server running plus a scanner | The `no-listening-socket` guard is clean over both source trees and **that** may be said. "Scanned and found closed" may not |
| 6 | NFR-04 on a clean *machine* | needs a second computer | §3.2's clean *environment* result may be described as such. No claim that someone else has installed this from the artifact and had it work |
| 8 | M1 re-closing on the amended level-2 claim | needs one live equivalence run | No claim that M1 is closed against the current code. M1 closed at `91a2607` on the **unamended** claim |

> **Approval to record in the findings ledger, once decided:**
>
> "The deferrals in §5.2b and §5.2c are approved for the `0.2.0b1` beta, on the condition that
> none of the claims in the last column is made in any material. **PF-5(b) is open.** The two
> 2026-09-19 smoke runs are proxy-constrained evidence and close no clause, so rows 15 and 16
> are not closed rows. What remains is the whole of `RELEASE_OWNER_ACTIONS.md` §7a's six-item
> list — an enforced network boundary, ADV-210's revalidation path, the full suite
> cold-started, the in-band `semantic_unavailable` decline, the runtime allowlist against the
> two permitted hosts, and the cache listing as preserved evidence — and **not the full-suite
> item alone**. Those are [approved for deferral / to be completed before distribution — delete
> one]."

### 5.3 The one row the demonstration closed

| # | Item | State |
|---|---|---|
| 1 | Live demonstration, both paths (`docs/GMAIL_PREVIEW_DEMO.md`) | **CLOSED for Path B, 2026-09-19**, at `6b1846c`, third attempt — `benchmarks/gmail-preview-harbor.desktop-2026-09-19b.preserved`. First response carried no message evidence; recovery stayed on the graph path; all 12 Harbor messages read; content continuation worked. **Operator-reported; no machine transcript preserved or independently verified.** Graph pagination partial, cache reuse and comparative benefit not established — those are row 12 and row 9, and they stay open |
