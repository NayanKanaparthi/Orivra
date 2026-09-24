# M2 execution brief — Complete Gmail intelligence

Authorized 2026-09-10. Process fixed by the owner: **one implementation pass, one focused
independent review, one bounded correction pass.** No additional general audit rounds. Block only
on a critical correctness, privacy, permission, data-loss or security problem, or on an external
action that requires the owner.

Plan of record: `docs/ORIVRA_V1_PLAN.md` §9, M2. Design commitments: `docs/ARCHITECTURE_DECISION.md`
D.4/D.5/D.6/D.7/D.8/D.9/D.10, §F preflights, WS-14.

---

## 0. The gate this brief exists to name

M2's first line is "PF-2/PF-4/PF-10 run live and recorded." Those three are **not** paperwork. Each
one sets a constant or a design branch that the semantic rung is built on top of:

| Preflight | What it settles | What is undecidable without it |
|---|---|---|
| **PF-2** *(blocking)* | Does `threads.get(format=metadata, metadataHeaders=[…])` return (a) the RFC threading headers and (b) a per-message `snippet` and `internalDate`? | Pool text (`snippet` vs body-head-400), `max_pool_threads` (**25 or 15**), and whether the reply-chain floor needs `format=full` |
| **PF-4** | On the owner's laptop, CPU only: cold model load, per-text embed latency, wall clock at 100/200/400 texts, rerank latency at 25 pairs, RSS | `max_semantic_ms`, `max_pool_messages`, `max_rerank_pairs`, `max_model_rss_mb`, and **the default model** |
| **PF-10** | Freshness baseline: arrival → first-surfacing per probe class, stratified at thread depth 0 vs 25, on two mailboxes | Whether any of MF1–MF6 fires, which decides whether FRESH-02 is mandatory |

**None of the three can be run from this session.** The device shell has no network egress
(`gmail.googleapis.com`, `pypi.org` and `huggingface.co` all fail to resolve), and the OAuth
credential must never leave the owner's machine. PF-10 additionally needs real mail delivered over
wall-clock time. These are owner actions by construction, not by preference.

### How the code handles that, without guessing

The semantic rung is built in full, and **it refuses to arm itself without a preflight record.**
There is no guessed constant anywhere in the path. A `SemanticProfile` is loaded from
`preflight-records/`; if no record is present, or the record does not cover the constants the rung
needs, L5 emits the D.5 deterministic fallback:

```
not_tried: [{rung: "semantic", why: "<named missing record>", affordance: …}]
```

and the ladder continues. That is not a stub and it is not a placeholder waiting to be filled in
with a plausible number. It is D.5's own escalation behaviour — *"if neither is available, PF-2 has
failed blocking and the rung's design is escalated to the owner"* — expressed as code, and SEM-02's
guard already makes a silent no-op a BLOCKER by construction.

**This is the rule for the whole milestone: a constant that a preflight is supposed to set is read
from the record or the feature declines to run. It is never defaulted to a guess that would make a
test pass.**

---

## 1. What gets built, in dependency order

### 1.1 Preflight runners and the record contract *(no network needed to build)*

- `preflight-records/` gains a typed, versioned record schema, one file per PF, with the account
  hash, the run date, the tool revision and the measured values.
- PF-2 and PF-4 runners added to the existing harness preflight package (`probes/headers.py` and a
  new model-latency probe). PF-10's probe exists (`probes/freshness.py`) and needs a run.
- The server reads records through one loader. A missing or malformed record is a declined feature,
  never a default.

### 1.2 SEM-03: the semantic interface and its local default

- `embed(texts) -> list[Vector]`, `rerank(query, candidates) -> list[float]`. One protocol, a
  registry, local implementation registered by default, a second implementation registering without
  touching retrieval logic.
- **Offline enforcement (D.8, ADV-210).** `HF_HUB_OFFLINE=1`, `local_files_only=True`, weights
  loaded from a **checksum-pinned local path, never a repo id**. A load that would touch the network
  fails closed to the deterministic fallback rather than reaching out.
- **`mailweave setup-models`** is the only code path permitted to contact the model host. Never
  invoked from the server process, never from a query path.
- **The egress-blocked test (NFR-01, SEM-02):** the suite runs cold with the model host blocked. A
  hidden revalidation call is a test failure, not a surprise.
- `model_id` and `model_revision` in every trace and every score provenance string.

### 1.3 D.8's hard floor

- `generative_llm_calls = 0` as a code-level constant.
- A CI gate that fails on any chat/completions client import in server code.
- Embeddings and cross-encoder scores are closed types by construction (float vectors and floats),
  which is how INJ-06 is satisfied structurally rather than by a validator that could be wrong.

### 1.4 L5, the semantic rung

- Thread-wise pool construction, priority order (a) L0–L3 threads, (b) participant probes from the
  query, (c) recency window. Capped by the profile's `max_pool_threads` / `max_pool_messages`.
- **Pool membership is not disclosure membership.** The pool creates no `source`, no mini-map and
  no stub rows. It is disclosed by its scoping rule and size in `retrieval_report.pool`, and
  enumerated by ID **in the trace only** as `semantic.pool_ids[]`.
- Step (b)'s participant probes are `messages.list` calls, so their IDs are in `H` under clause
  (H-lex) and are disposed of by A.7a like any other: disclosed if their thread is mapped, otherwise
  a `withheld` record with `cap: "max_pool_threads"` and a pool-widening affordance.
- `H` from the scored retriever is the **shortlist**: top-k by stage-A cosine with
  `k = max_rerank_pairs`, a pre-registered constant reported in
  `retrieval_report.shortlist{rule, k, size}`. **Not** a score threshold an implementer picks.
- Fires only when D.3 rule 4 holds and `exact_signal_match` is false. Never on exact-lookup or
  sender/date families (SEM-04).
- Cost disclosure: `cost.semantic_ms`, `cost.embed_texts`, `cost.rerank_pairs`,
  `model_id@revision`, `escalated: true`.

### 1.5 L6, bounded rerank

- Runs **only** on an ambiguity signal: hit-count band, `term_coverage < 1`, thread concentration,
  or a scored-retriever margin.
- **Hard prohibitions in code, not in a comment**: never when `exact_signal_match`, never when
  `hit_count == 1`, never on an `rfc822msgid:` route.
- Every numeric score carries `basis` — the text actually embedded. A reused stage-A cosine may
  affect ordering **only where it exists for every candidate in that comparison**; otherwise
  `ordering_effect: false` and the ordering is `mailweave/mechanical-v1` alone. Mixing scales inside
  one comparison is the fabricated comparability RANK-03 exists to prevent.
- Results selected by Gmail `q` say exactly that and carry **no** numeric score.

### 1.6 Query-aware disclosure (N-1)

- The selector's depth decision takes `QueryFacts` into account.
- **The reply-chain floor is asserted intact on every layout**, F17 in both arms.
- Until H1/H2/H3 are measured, nothing anywhere describes depth or ordering as query-aware or
  relevance-ranked in any public-facing string.

### 1.7 LR, the freshness rung (D.9)

- The `historyId` watermark persists at `~/.local/state/mailweave/watermark.json`, mode `0600`
  inside a `0700` directory, containing exactly `{schema, account_hash, history_id, observed_at}`.
  **No message IDs, no subjects, no addresses, no mail content of any kind.** It is a non-content
  synchronisation stamp, never served as an answer. `mailweave purge` deletes it.
- Cost is **`2 + 20n`** with `n ≤ max_recency_fetch = 8`. IDs beyond the cap become `withheld`
  records. The former flat "2 u" was wrong by up to two orders of magnitude.
- The 404 on an expired `historyId` triggers a **declared re-baseline** reported in the response,
  never silent.
- The client-side re-check is a **closed published subset**: `from`/`to`/`cc`, `after`/`before`,
  `has:attachment`, `label:`. Never free-text terms, `subject:` semantics, stemming, phrases, or
  `OR`/negation grouping.
- A message surfaced by LR while any residual free-text term exists is disclosed with
  `role: "context"` and the verbatim reason string from D.9. **It is never attributed to the user's
  query as a `q` match.**

### 1.8 The trace sink (D.10)

- Schema v2, every required field, with the **redaction policy as a first-class field**.
- `pool_ids[]` lives only in the trace, never in the response.
- Personal-profile traces carry no mail-derived text at any depth, **including error paths**.
- JSONL on disk under the profile-bound type.

### 1.9 WS-14, the remaining injection posture

- **Trust labels on every leaf.**
- **Connector-voiced fields provably free of source text** — proved by construction, not by scan.
- **The quarantined-model rule enforced by type**: expansion parameters only ever from the agent's
  explicit tool arguments, never from mail content.

---

## 2. Demos M2 must produce

| Demo | Bar |
|---|---|
| F4 paraphrase | Answered by L5 where v0.1 returned nothing |
| F16 near-duplicate | Ordered by L6 with a named method |
| F17 reversal | Caught in the query-aware arm |
| Fresh delivery | Found by LR within the measured lag |

## 3. Acceptance

- H1, H2, H3 measured on F1–F17 **against the v0.1 lexical arm**.
- `generative_llm_calls` stays zero on F1/F2 traces.
- The injection fixtures pass.
- **Any hypothesis that fails removes its machinery from the default path rather than being argued
  with.** A rejection is published with its numbers; the rung stays behind `force_rungs`, the
  interface stays, the default trigger is disabled. That is a backend rejection, not permission to
  delete the capability.

## 4. Compatibility, preserved

- The v0.1 legacy Gmail path is unchanged: names, schemas, defaults and observable behaviour, with
  no silent change to the legacy default path.
- Both compatibility levels stay green: byte identity under injected clock, nonce and key; live
  semantic equivalence after normalising volatile fields.
- Legacy `map_id` handles keep working. Orivra reuses the legacy payload for Gmail thread maps.
- Every new behaviour gets a replant citing a **named** test, each run alone.

## 5. What this brief does not authorize

Reopening M1. Its seven backlog items are re-triaged against M2's rubric where M2 touches the same
code, and are otherwise left alone. Non-critical observations about M1 are not grounds to reopen it.

---

## 6. PF-2 correction, 2026-09-11

PF-2's first live run returned **PASS** having never asked its own question. It compared one
message, and that message carried neither `In-Reply-To` nor `References` in the full arm. No
header the full arm showed was dropped, so `headers_dropped_by_metadata` was empty, so the
probe passed. The reply-linking survival that AD D.5's thread-map pricing rests on was not
measured, because nothing in the sample could have exhibited it.

Same defect class as R-M1-003 and replants R134 and R153, one layer out: this time in the
instrument rather than in the code it measures.

**What changed.**

1. **Per-question verdicts.** `reply_header_verdict` and `snippet_verdict`, each INCONCLUSIVE
   unless at least one shared message's *full arm* could have exhibited it. The overall
   verdict is the conservative join: FAIL if either failed, INCONCLUSIVE if either was
   under-exercised, PASS only when both were exercised and both held. The snippet floor is
   the identical defect one branch over, found while fixing the first.
2. **Deterministic selection that can answer.** Candidates are ordered by message count
   descending then thread id ascending, and the first carrying a reply-linking header wins.
   The old selector took `sorted(thread_ids)[0]`, which is the smallest id in the sample and
   has nothing to do with the property under test. `--thread-id` lets the operator name one
   instead. The selector's full arm is reused rather than refetched, because two
   `threads.get` calls are two instants and a message delivered between them reads as a
   dropped header.
3. **Run 1 preserved, not reinterpreted.** The file is unmodified at
   `preflight-records/raw/PF-2-run1-2026-09-11-UNDER-EXERCISED.json` with a README stating
   what it does and does not establish. Its claim is withdrawn by *absence*: the server-side
   reader treats a record carrying no per-question verdict as having answered neither
   question, so the record decides nothing without anyone editing evidence.
4. **Revised quota bound, registered before the rerun** (PF-16). 80 u when the operator names
   a thread (two `threads.get` at 40 u). Otherwise `40K + 40` with `K = MAX_SELECTION_PROBES
   = 4`, so **200 u**. Written into the SPEC, not into a comment.
5. **Regressions.** `test_a_one_message_thread_with_no_reply_headers_cannot_produce_a_reply_
   header_pass` is the focused one. Replants R175 to R179 cover the reply floor, the snippet
   floor, the selector ordering, the single-instant read, and the reader's treatment of a
   verdict-less record. All five CAUGHT, each citation run alone.

**A test in the suite encoded the defect.**
`test_a_header_absent_from_both_arms_is_the_message_s_doing_not_the_api_s` asserted PASS on
exactly the shape run 1 produced. Its stated claim was correct and is unchanged: a header
absent from both arms is not a metadata failure. What it had no business asserting was that
this shape reaches PASS overall. The end-to-end double had the same gap, and its threads now
carry RFC threading headers so the reply question is exercised there too.

**Still not established.** Whether the metadata arm preserves reply-linking headers on real
Gmail. That is what the rerun is for.

### PF-2 answered, 2026-09-11

Rerun on the 12-message Harbor thread (`--thread-id`, 80 u, no selection probes).

| Question | Verdict | Exercised by |
|---|---|---|
| reply-header survival | **pass** | 11 of 12 messages carry `In-Reply-To` and `References` in the full arm; the metadata arm dropped neither |
| snippet / internalDate survival | **pass** | 12 of 12 carry both in the full arm; none lost under `format=metadata` |

`messages_compared: 12`, `headers_dropped_by_metadata: {}`,
`reply_header_bearing_messages_compared: 11`. The one message with no reply headers is the
thread root, which is what a root is.

**Consequences, executed rather than described.**

- The pool takes **D.5's optimistic branch**: pool text is `subject + participants + snippet`
  from `threads.get(format=metadata)`, and `max_pool_threads` is **25**, not the fallback's
  15. The profile now reports this as `measured`, citing the record and its run date.
- **The reply-chain floor does not need `format=full`.** It stays on `format=metadata` at
  40 u, measured rather than assumed.
- `bounds_provenance` is still `assumed`: `max_semantic_ms`, `max_pool_messages` and
  `max_rerank_pairs` are PF-4's to set and PF-4 has not run. The profile's `measured`
  property is therefore still False, which is the point of requiring both halves.

**What this run does not establish.** `Cc` was carried by no message in the thread
(`messages_carrying_each_requested_header_in_the_full_arm` records `cc: 0`), so its survival
is unexercised. No design commitment in D.5 rests on it, and the coverage map makes the gap
visible without a rerun, which is exactly the number whose absence let run 1 pass unnoticed.
One thread was compared, which is what AD F PF-2 specifies.

---

## 7. Setup corrections, 2026-09-11

Four, all from the owner's verification of the first provisioning build.

**1. The redirect host.** Both `model.safetensors` URLs redirect to `us.aws.cdn.hf.co`, which
no enumerated allowlist contained. Enumerating that one host would move the failure to the
next person in another region, so `check_url` gained an **opt-in suffix arm**, default empty.
The runtime path passes no suffixes and is byte-for-byte unchanged; only `provision.py`
passes `MODEL_CDN_SUFFIXES`. A suffix must start with a dot and carry two more labels, and a
host must be strictly longer than the suffix, so `.hf.co` admits `us.aws.cdn.hf.co` and not
`evilhf.co`.

**2. Artifact sets instead of whole repos.** `BAAI/bge-reranker-base` carries
`model.safetensors`, `pytorch_model.bin` **and** `onnx/model.onnx`: about **3,359,121,141
bytes** for roughly 1.1 GB any one runtime loads, which blew its own 1,610,612,736-byte
bound. A catalog entry now declares one or more sets, each naming a runtime and the patterns
it takes. The Python arm and PF-4b's ONNX arm are locked separately under
`stage_b_default.python-st` and `stage_b_default.node-onnx`, in separate directories, so a
measurement citing "bge-reranker-base" also says which artifacts it ran against.

Every `required` pattern must match at least one file at pin time. A pattern that silently
matches nothing is how a tokenizer goes missing, and a missing tokenizer does not present as
one: it presents as a loader failure later and gets read as evidence about the model.

**The bound is now enforced inside the chunk loop.** Checking after each complete file meant
a 2 GB file blew a 1.5 GB bound only once all 2 GB were on disk, which is a report rather
than a limit.

**Model bytes are reported separately** from Python runtime dependencies. `uv sync` fetches
the latter and they are not counted in the figures `setup-models` prints.

**3. Potion loading, diagnosed before it is measured.** At revision
`6fc8051fab2a1e0ee76689cf08c853792ac285e7`, `modules.json` declares
`sentence_transformers.models.StaticEmbedding` and `Normalize`, and the model page documents
`SentenceTransformer` loading. So `modules.json` is **required**, not optional, in
`stage_a_default.python-st`: without it `SentenceTransformer` takes a transformer-style path
this repo cannot satisfy, and the failure would look like a model problem.

`mailweave setup-models --smoke` loads offline, encodes two texts, reranks two pairs, and
reports dims, scores and timings. On a load failure it says, in the output, that this is a
packaging result rather than a model result, and names the three things to check in order. A
packaging failure must never enter a performance record.

**4. PF-10's service level was already decided.** OD-1, binding, 2026-08-30: p90 <= 60 s from
H0/history-confirmed arrival for H5/H6, independently at depths 0, 5 and 25, pooling
prohibited; and any confirmed real-mail false negative is a defect regardless of percentile.
`PF10_PROTOCOL.md` now reproduces it and instantiates MF2, MF4 and MF5 against it.

The earlier draft read `EVALUATION_PLAN.md` §11.2.2 and §13, which still list the FSL as
UNSET, and asked the owner to decide it again. Those two passages predate OD-1 and are stale;
`OWNER_DECISIONS.md`'s RESOLUTIONS section is the authority. The error was reading one
document's account of a fact instead of the record that holds it.

Replants R184 to R188 cover set selection, the unmatched-requirement refusal, the
mid-transfer bound, the runtime allowlist taking no suffixes, and the per-set directory.
R184 was MISSED twice before it was right: the include list and the exclude list each keep
the duplicates out on their own, so a single-line plant proved nothing, and the excludes turn
out to be a second line that never fires with the sets as shipped. That is now said in the
code rather than left to look like enforcement.

---

## 8. Models installed, and the lifecycle defect the smoke run exposed

Pinned and installed 2026-09-11, verified against `models.lock`:

| Lock key | Repo @ revision | Files | Model bytes |
|---|---|---|---|
| `stage_a_default.python-st` | `minishlab/potion-retrieval-32M` @ `6fc8051fab2a` | 7 | 131,197,807 |
| `stage_b_default.python-st` | `BAAI/bge-reranker-base` @ `2cfc18c9415c` | 6 | 1,134,374,819 |

**1,265,572,626 model bytes** against the estimate of roughly 1.25 GB. Neither set pulled a
duplicate weight format: no `pytorch_model.bin`, no `onnx/model.onnx`. The whole
`bge-reranker-base` repo is 3,359,121,141 bytes, so set selection avoided **2.22 GB** of
download for weights nothing would have loaded.

The smoke check passed: dim 512, the on-topic candidate scored above the off-topic one, and
`modules.json` did its job. Those numbers are a smoke check and are not used anywhere.

### The finding: the backend was being built on every acquire

The smoke run priced a cold load at **36,543 ms**. `MAX_SEMANTIC_MS` is 6,000.

`BackendRegistry.acquire` called its factory every time. So the semantic rung would have
loaded 1.27 GB of weights **per query**, blown a 6-second budget by a factor of six, and
declined - with a timeout. A timeout reads as "the model is slow". It would not have read as
"the model is loaded once per query", and nothing in the suite would have said otherwise.

Fixed: `acquire` memoises for the process lifetime, under a lock held **across the build**
rather than around the dictionary, because two concurrent queries are permitted and a
check-then-build would pay the cold cost twice on a session's first two queries. A decline is
remembered too, so a machine with no weights does not retry an expensive failure per query;
the consequence is stated rather than hidden, which is that installing models into a running
server takes effect on the next process.

The server is one long-lived process per stdio session (`run_stdio`), so per-process is the
correct lifetime: the load is paid once at first use and every later query sees a warm model.

### PF-4, built to measure that rather than assume it

`python -m mailweave_harness.modelbench --run`. No credential, no mailbox, no network: it
needs the weights and nothing else, which is why it is a separate runner from the Gmail
preflight rather than an eighth probe in it.

It reports the **cold acquire and the warm second acquire separately**, and **fails** when
the second is not materially cheaper than the first - under 5% of it *and* under 1,000 ms, so
a uniformly slow machine cannot satisfy the check by making both numbers large. A reuse
failure is reported as an architecture defect rather than a tuning result, and a run that
fails it offers no measured constant at all, because numbers from a process that reloads per
use are not numbers about the product.

The per-query budget is warm work only: `embed(pool) + rerank(k)`. If that exceeds
`MAX_SEMANTIC_MS`, the pre-registered consequence is to re-derive `max_pool_messages`
**downward** to the largest measured size that fits and declare it per T-RO1. Not to raise
the budget to whatever was measured, which is how a bound becomes a description.

Rows are synthetic, deterministic from a seed, at real pool-row lengths, and carry no mail
content. Length is what costs time in a transformer, so that is a sound instrument for
latency and an unsound one for relevance; the spec says so in a pre-registered rule, and
H1/H2/H3 measure quality on F1-F17. A further rule records that a two-item smoke check is not
a measurement and that none of its numbers appear in this record.

Replants R189-R192 cover the memo, the remembered decline, the reuse check, and the
downward re-derivation. All four CAUGHT.

---

## 9. PF-4 run 1, and why its PASS does not set a bound

Run 1 passed: 165 ms warm per-query against a 6,000 ms budget, reuse holding at 0 ms against a
5,483 ms cold load, peak RSS 948 MB. The owner then asked two questions that make the numbers
unusable as established bounds, and both were right.

**The device was never selected or recorded.** AD F PF-4 registers the measurement as "CPU
only" and D.5's cost model is a CPU cost model, but `SentenceTransformer(path,
local_files_only=True)` with no `device` argument picks the best available accelerator. On an
M-series Mac the run may have been on MPS while every registered number described a CPU, and
nothing in the output could settle it.

The loader now **names** the device, defaults to `cpu`, and the finding carries it along with
the accelerators present but unused and the `torch` / `sentence-transformers` / `transformers`
versions. A device chosen by a library default is an unverified assumption sitting under every
number the probe produces.

**The rerank curve fell as the work grew.** 288 ms at 5 pairs, 229 at 10, 137 at 25. A
cross-encoder does not speed up with more pairs. Each size was timed once, ascending, with no
reranker warm-up, so the 5-pair run paid for initialisation the later runs inherited.

Each stage now gets a discarded warm-up, every size runs **five** times, the record carries
the median **and every sample**, and a median curve that is not non-decreasing in size makes
the verdict **INCONCLUSIVE rather than PASS**: constants derived from a curve nobody can read
have no warrant.

**A third hazard in the same family**, found while fixing those two. `per_text_embed_ms: 18`
sat beside "100 rows in 12 ms", and multiplying it out gives 5.4 s for a 300-row pool. It is
one call carrying one row, so it is call overhead plus a row. Renamed `single_call_embed_ms`,
with a note in the record saying multiplying it is a category error.

**Run 1 is preserved unmodified** at
`preflight-records/raw/PF-4-run1-2026-09-11-DEVICE-UNRECORDED-RERANK-UNWARMED.json`. Its claim
is withdrawn by absence, the same way PF-2 run 1's was: the resolver treats a PF-4 record with
no `device`, no `repeats_per_size`, or a non-monotonic rerank curve as having measured
nothing. The file is untouched and simply stops deciding anything.

One number from it survives as evidence rather than as a bound: the cold load came in at 5,483
ms against the smoke run's 36,543 ms, a factor of six, which is what a warm page cache looks
like and is why the probe already records its cold reading as a bound rather than as the cold
cost.

**Two existing guards caught me while fixing this.** `runtime_versions` was first written as a
loop calling `__import__(name)`, and both the forbidden-import and generative-client sweeps
refused it: an import contract cannot be checked against a name no static pass can read. Three
explicit imports instead.

Replants R193 to R195 cover the named device, the INCONCLUSIVE verdict on a falling curve, and
the resolver's refusal of an unqualified record. R193 and R195 were MISSED first: R193's test
asserted a constant rather than the behaviour, and R195's three guards each reject run 1 alone,
so the plant has to disable all three.

## 10. PF-4 run 2, qualified — and the one number that is not a bound

Run 2, recorded `2026-09-11T08:40:01Z`, satisfies every rule run 1 failed:

| registered rule | run 2 |
|---|---|
| the device is named by the loader | `device: "cpu"`, with `accelerators_available_but_unused: ["mps"]` |
| every size warmed, then repeated | `repeats_per_size: 5`, medians and all samples recorded |
| a curve that is not non-decreasing is INCONCLUSIVE | `rerank_curve_is_non_decreasing: true`, `embed_curve_is_non_decreasing: true` |
| cold load reported separately, never folded in | `cold_acquire_ms: 5410`, `warm_acquire_ms: 0`, `reuse_holds: true` |

The rerank curve now rises with the work: 59 / 101 / 226 ms at 5 / 10 / 25 pairs, samples
tight (225–233 at 25). Embedding 300 rows takes 24 ms. The warm per-query figure at the
published pool is **250 ms against a 6,000 ms budget** — a 24× margin, which is the number
the L5 design is built on.

`resolve_profile()` now reports `bounds_provenance.basis = measured` and `profile.measured =
True`, so `max_pool_messages = 300`, `max_rerank_pairs = 25` and `max_semantic_ms = 6000`
are declared in every semantic response as measured rather than assumed. Run 1 stays
untouched on disk and still decides nothing.

### `peak_rss_mb: 1360` is not model memory, and no memory limit is adopted from it

The probe reports the **whole process's** peak resident set: the CPython interpreter, `torch`
2.14.0 and its native libraries, `transformers`, `sentence-transformers`, the synthetic
corpus, and the two models' weights — in one number, with no attribution between them. It is
an upper bound on what the models cost and nothing more; the models' own footprint is
strictly smaller and this probe did not measure it.

So `candidate_max_model_rss_mb: 1700` is what its name and `candidate_is_a_bound_not_a_default:
true` say it is: a figure reported for the owner to look at, not a constant. **No
`max_model_rss_mb` is adopted, and nothing in the server reads one.** D.11's
`semantic_unavailable` lists an RSS bound among its causes; until the owner adopts a number,
that clause has no trigger and the rung declines only on a runtime or weights failure. The
same treatment PF-21 gave `max_server_ms`.

Measuring model-only memory would need a separate probe — baseline RSS of a bare interpreter
with the libraries imported and no weights loaded, subtracted from the loaded peak — and that
probe is not registered. Quoting 1,360 MB as "MailWeave needs 1.4 GB for its models" would be
the same class of claim as run 1's falling rerank curve: a number that is real and an
inference from it that the measurement does not support.


## 11. M2's credential-independent build, closed 2026-09-11

Everything §1 lists that does not need live mail is built, reviewed and committed at `96683ef`. The
consolidated account is `M2_HANDOFF.md`; this section records only what changed about the *brief*.

**§1.6 (N-1) was reachable all along and did not work.** The brief says "the selector's depth
decision takes `QueryFacts` into account", and it did - through a component that compared the query's
addresses against display names, because `_addresses_of` unpacked `(display name, address)`
backwards. On an all-hit thread every hit therefore tied at zero and thread position decided which
body survived, which is the oldest-K policy EV-02's degenerate-strategy guard names. Fixed; the
component now separates two hits that differ only in who they are from.

**§1.9's remaining injection posture is not in this range.** WS-14's trust labels, the
connector-voiced fields and the quarantined-model rule are untouched and stay in M2's scope.

**Two additions to A.7a's published cap table**, each argued where the value is defined:
`MAX_RERANK_PAIRS` for a pool row the shortlist passed over, and `RECENCY_RECHECK_EXCLUDED` for a
recent arrival the local re-check contradicted. Both exist because the disposition certificate would
otherwise refuse the response and A.7a has no name for the state.

**One addition to the wire**: `retrieval_report.semantic_cost`, which is AD D.5's own cost disclosure
(`escalated`, `embed_texts`, `rerank_pairs`, `semantic_ms`, `cold_load_ms`, `model@revision`,
`ordering_method`) and had never been built. Without it, D.7's rule that a `q`-selected row carries no
numeric score left two responses - one reranked, one not - byte-identical in their rows and silent
about the model.

**The review.** One focused independent pass over L5, L6, the ranking seam and the budget clock
reproduced nine defects; the recheck of the fixes found a tenth. All ten are fixed. The two that
mattered most were L6 running under no clock at all, and L5 becoming undeliverable above about thirty
threads in its own recency window - R-MCP-033's failure arriving through the rung whose design note
says the pool creates no rows *because* stub rows would blow the ceiling.

**What the brief still asks for and this range does not deliver:** every live acceptance gate.
H1/H2/H3 on F1-F17, `generative_llm_calls` zero on F1/F2 traces, the injection fixtures, PF-4b, PF-10
and PF-5. M2 is not complete.

---

## 12. The second range, 2026-09-11 (`a677ab7..d98c3c4`)

`ORIVRA_V1_PLAN.md` recorded that WS-14's remaining injection posture stayed in M2's scope. It was
implementation, not testing, and it is built: INJ-05, INJ-02, INJ-03 and INJ-06's second clause, with
INJ-01 and INJ-04 already covered. Four defects found while building it - R-M2-016 to R-M2-019 - two
of them latent HIGH refusals reachable on the shipped surface today.

`recency_recheck_excluded` is pinned as distinguishable from budget exhaustion in every surface a
reader would check, and its recovery is asserted as an executed direct read on the same read-only
scope. The property held already; nothing had pinned it.

**Of the brief's remaining asks, the injection fixtures now pass.** The rest stands: H1/H2/H3 and the
F1/F2 trace check need the case corpus and a mailbox, PF-10 and PF-5 need the owner's machine, and
PF-4b's embed half needs a `node-onnx` artifact set for `stage_a_default` that `models-catalog.json`
does not have - its rerank half is runnable and its command is `harness/node/pf4b-arm.mjs`.

`make acceptance` reports all of that from the code, per acceptance line, with the runnable half run.
It is evidence status and not a verdict: it moves no rubric row, and the rule that only a reviewer
who did not write the code may is unchanged.

**`max_model_rss_mb` remains unadopted** and is documented as whole-process RSS.
