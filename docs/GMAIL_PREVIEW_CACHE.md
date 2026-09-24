# GMAIL_PREVIEW_CACHE.md — what the preview caches, and what it defers

**Status of plan §5.1's "Cached" row for this release: partially met, and the part that is not
met is named below rather than marked complete.**

---

## 1. What is wired, and where

One seat, on one execution path: **`orivra_expand`'s thread read**.

| | |
|---|---|
| Kind | `CacheKind.STRUCTURE` (plan §5.4) |
| What it holds | one thread's structure as evidence nodes: ids, thread membership, reply parents, participants, dates. Rows at `stub` depth |
| Key | the full §5.4 tuple, built by `orivra.cache.structure_key` — `principal`, `connector`, `native_id`, `content_version` (the thread's `historyId`), `permission_hash`, `model_id=None`, `extraction_schema_version`, `redaction_policy`, `kind` |
| Revalidation | `GmailClient.liveness_of_threads` — a `history.list` walk, which is **a different resource from the one the entry holds** |
| Serves when | `probe.conclusive and not probe.saw_a_change` |
| Lifetime | in process memory, `TTL_BY_KIND[STRUCTURE]`, bounded by entry count, LRU by write time |
| Built at | `ConnectorRegistry.from_runtime`, once per process |

### Why this seat and not another

The Gmail preview repeats exactly two kinds of source read. One of them is not cacheable and
saying why is half the design:

* **`version_of`, per message, on every disclosure.** The measured hot path: `orivra_graph`
  pages and `orivra_expand` each re-read every held message's `historyId`. It is **deliberately
  uncached**, and `graph/access.py` states the rule from the other side — it is the answer
  whose whole point is that it is asked now. Caching it would be a cheaper answer to the one
  question that must not be cheap.
* **`threads.get`, on expansion.** Measured duplicate: an `orivra_ask` that reads a thread and
  a later `orivra_expand` of that same thread read it twice. Here a cheap, independent
  revalidation exists, so this is the seat.

The rule that makes it safe is ADV-002's, which this repository already paid for once: **the
check must read a different resource from the one the cache holds.** A `history.list` walk
knows nothing about the cache, so a cache hit cannot make it pass.

The asymmetry is `LivenessProbe`'s own (amendment A10, R-RETR-059): a walk that **saw** a
change has established one whatever it did not read, so only the *negative* answer needs a
conclusive walk. An expired watermark (Gmail's 404, RO F6) and a walk that stopped with pages
outstanding both mean "could not tell", which §5.3 is explicit is not a licence to serve.

### What a served entry says about itself

* **Freshness is restamped from the revalidation, not inherited from the fetch.** The
  envelope keeps its own `fetched_at` — the instant the content was read — and the node's
  `verified_at` is the instant the probe confirmed it had not moved. Two facts, both true.
  `GmailAdapter._fresh`'s docstring named this as where the cache would land, and it has.
* **Spend reports the walk, not the fetch it avoided.** Re-reporting the original read's API
  calls would be the accounting equivalent of restamping `fetched_at`. A served entry reports
  the probe's pages and the published units for them, and `rungs_executed` is empty because no
  rung ran.
* **No body text, ever.** Plan §5.1 excludes message bodies from every category. A thread map
  returns `stub` rows, which is what makes this kind cacheable at all, and the adapter refuses
  to write an entry whose nodes carry content rather than trusting that to stay true.

### Demonstrated, through the tool boundary

`tests/test_orivra_cache_wiring.py` drives `call(service, "orivra_expand", …)` and counts what
reached Gmail. Reuse: the second expansion of one thread makes zero `threads.get` and one
`history.list`. Invalidation: four routes, each its own test — the probe saw a change; the
probe was inconclusive (expired watermark, and pages outstanding, separately); the entry was
dropped by `invalidate_native`; and the thread's revision moved, which misses structurally
before any probe runs.

---

## 2. What is deferred, proposed explicitly

### 2.1 Persistent storage — **propose: defer to M4, and say so in the release report**

Plan §5.1 specifies the cached category at `~/.local/share/orivra/cache/`, SQLite, `0700`
directory, `0600` files, deletable by `orivra purge`. **None of that is built.** The cache
above is in process memory and dies with the process.

Proposed as a preview-scope decision rather than an omission, on three grounds:

1. **The security surface is the expensive half, and it is not needed yet.** Persisting the
   cached category means derived mailbox data at rest: `SECURITY_NOTES.md` §4.2's territory,
   the token store's protection class, a new `orivra purge`, and a setup document that tells
   the user what is on their disk. A preview that keeps nothing on disk owes none of that and
   cannot get it wrong.
2. **The measured benefit is small at one connector.** The seat above saves a `threads.get`
   and spends a `history.list`. Across process restarts it would save more, but a preview is
   run interactively, and the plan's own adoption rule (§5.5) is that an optimisation stays
   only if a pre-registered number moved. No number has been measured.
3. **The dimensions persistence most needs are the ones M4 adds.** `principal` and
   `permission_hash` isolation matter structurally the moment two connectors and two grants
   are in play. Building the store now would be building it against one connector's shape.

**What this does not authorise.** The rubric row for the cached category is not `PASS`. The
release report says this cache is in-memory and per-process, the setup material says nothing
is written to disk because nothing is, and if either claim stops being true the store has to
arrive with §5.1's protections rather than after them.

### 2.2 The other kinds — **built, unused, and not claimed**

`CacheKind` publishes six kinds. One is wired. The rest:

| Kind | Status |
|---|---|
| `STRUCTURE` | wired, above |
| `VECTOR` | the natural next seat and the one §5.5 adopts at M2: its revalidation is free, because the content version is already in the retrieval response rather than a second source call. It sits in `mailweave/retrieval/semantic.py`, which is server code, and Orivra's cache reaching into it would invert the dependency direction. Deferred with that question |
| `METADATA` | Gmail's per-item revalidation is the same call that returns the payload, so it saves nothing without amortising one `history.list` across many items. That is the change-feed optimisation §5.5 says to measure before adopting |
| `OBSERVED_EDGE` | recomputed from a response already in hand; §5.5 lists graph-fragment caching as measured-before-adoption |
| `ENTITY_CANDIDATE` | no entity resolution ships in this release |
| `NEGATIVE` | needs the same change-feed amortisation as `METADATA` |

Published but unused is a deliberate choice: the enum is plan §5.1's cached category and
narrowing it to the one kind in use would lose the statement of what may be cached at all.

---

## 3. What a reviewer should check

- The revalidator reads `history.list` and the entry holds a `threads.get`. If those ever
  become the same resource, the seat is unsafe whatever the tests say.
- An entry serves only on `conclusive and not saw_a_change`. Both inconclusive shapes report
  `touched={}`, which reads like "nothing changed" and is not.
- A served entry's `verified_at` is this call's, its envelope's `fetched_at` is the original
  read's, and its spend is the walk's.
- Nothing in the cache carries `content`.
- The cache is built once per process in `ConnectorRegistry.from_runtime`, not per adapter and
  not at module level.
