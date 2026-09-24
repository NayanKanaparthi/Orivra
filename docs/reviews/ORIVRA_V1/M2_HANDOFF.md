# M2 handoff — what was built while you were away

**Range:** `7a3b93f..d98c3c4`, sixteen commits.
**Sections 1–6 describe `7a3b93f..96683ef`** (the first range, nine commits, 49 files,
+7,823 / −101) and are unchanged except where §5 and §6 were **wrong** — see the PF-4b bullet in §5,
which corrected an inaccurate statement about why PF-4b was blocked. **§7 onward describes
`a677ab7..d98c3c4`**, which is WS-14's injection posture, the `recency_recheck_excluded` pinning,
the acceptance status command and PF-4b's executable half.

**State of the gates at `d98c3c4`:** 82 test files green (`-m "not network and not replant"`),
231 replants in the manifest (34 written across both ranges, each verified CAUGHT individually),
**nine** CI guards clean, `ruff check` and `ruff format --check` clean over
`server harness orivra tests tools`, `mypy` at its pre-existing 15 errors in five files, none of them
touched here. **`ruff` is not clean over the repository root**: `marketing/brand/` now carries
untracked Python I have not touched — §8 step 1 says what to do about it.

**§8 is the ordered run on your machine**, with what each step costs, what it changes and what to
send back.

---

## 1. What is implemented and committed

**PF-4 closed on the qualified run** (`e6a1641`). Run 2 satisfies all three registered rules run 1
failed: the device is named (`cpu`, with `mps` present and unused), every size is warmed and
repeated five times, and both median curves rise with the work. The profile consumes it:
`bounds_provenance.basis = measured`, so `max_pool_messages = 300`, `max_rerank_pairs = 25` and
`max_semantic_ms = 6000` are declared as measured in every semantic response. Warm per-query work at
the published pool is **250 ms against a 6,000 ms budget**. Run 1 is untouched and still decides
nothing.

**L5, the semantic rung** (`d550bc1`). `semantic/pool.py`, `semantic/shortlist.py`,
`retrieval/semantic.py`. Thread-wise pool in D.5's priority order — threads L0–L3 touched, threads of
the participants the query named, the query's own date window or a bounded 90-day default — capped at
`max_pool_threads` / `max_pool_messages`, embedded on the PF-2-confirmed snippet branch, shortlisted
top-`k` by stage-A cosine with `k = max_rerank_pairs`. The gate is D.3 rule 4 with SEM-04's
prohibitions evaluated **first**, so a query that resolved an identity records `not_applicable` with
no affordance and `force_rungs` cannot lift it.

**L6, ranking** (`28ce5d9`). `ranking/gate.py`, `ranking/mechanical.py`, `ranking/rerank.py`,
`retrieval/ranking.py`. `mailweave/mechanical-v1` is a deterministic composite over five structural
signals with published integer weights, total over its component enum, ordered so a query-independent
component can break a tie and never outrank a query-derived one. The cross-encoder is gated on D.7's
four ambiguity signals and refused outright by its three prohibitions.

**LR, freshness** (`ef5defb`). `freshness/recheck.py`, `freshness/recency.py`. Priced `2 + 20n`,
`n ≤ max_recency_fetch`; an expired `startHistoryId` is a **declared** re-baseline; the local
re-check is D.9's closed subset and nothing else; a surfaced message is `role: context` with D.9's
sentence verbatim, ending *"free-text terms NOT re-checked — Gmail q did not match this message"*.
The watermark advances after the response is built, never before the walk.

**D.10, the trace sink** (`3be2694`). `trace/redaction.py`, `trace/schema.py`, `trace/sink.py`,
`trace/emit.py`. Redaction is a **type**: every formatting path — `__str__`, `__repr__`,
`__format__`, the serialiser — renders `<redacted:len=N:sha8=…>`, and `reveal()` is the single
greppable way back. The policy is a first-class field; `pool_ids[]` lives here and nowhere else.

**Offline enforcement and N-1** (`45048a6`). Three layers executed: the static sweep, the
environment flags (now set at module import, see §3), and the runtime allowlist. N-1's participant
component works for the first time — see §3.

**PF-4b and PF-10 harness** (`95e7b48`). `modelbench/nodearm.py`,
`mailweave_harness/freshness/analysis.py`. The halves that need no laptop.

**Two review passes** (`e5c1b53`, `96683ef`) — see §4.

---

## 2. What was verified, and how

| Claim | How |
|---|---|
| the server process loads its models **once** | two real `mailweave_search` calls through the shipped `MailweaveService`, counting factory invocations (`test_the_server_process_reuses_one_backend_across_queries`). Not the registry in isolation — the service opens a fresh client, ledger and accountant per query, so the question is whether the *service* holds one registry |
| first-use cost is accounted, not assumed | `serve` warms the backend at startup; the load happens **outside** the semantic clock; `cold_load_ms` is reported separately from `semantic_ms` and never folded into a per-query figure |
| the pool creates no sources | a 20-thread pool with `k = 3`: at most `k` threads become sources and the rest come back as withheld records under the shortlist's own cap |
| redaction holds on the error path | a sentinel in the query, the subject and the body; the response carries it (it is the answer), the trace carries neither it, nor an address, nor a subject |
| the 221 replants | each behaviour removed one at a time, each citation run alone; 24 of them written this range, all CAUGHT. Four were **MISSED first** and each miss was a finding against my own test (§5) |
| the review's nine findings | an independent reviewer reproduced each with a script before reporting it, and re-ran those same scripts against the fixes: eight REPAIRED, one PARTIAL, one new defect. Both remaining items closed in `96683ef` |

---

## 3. Material decisions, and the defects that shipped before this range

**Three defects that were already in the tree.**

1. **`addresses_in_header` returns `(display name, address)` and `_addresses_of` unpacked it
   backwards.** The E4 fill's `participant_match` — the highest-weighted component of the
   query-aware fill, ranked first by A.9(3) *because* it is the most query-driven signal available —
   compared the query's addresses against display names, and against the empty string for every bare
   `bo@team.example`. It could fire only by coincidence, so on an all-hit thread every hit tied at
   zero and thread position decided which body survived: the oldest-K policy EV-02's
   degenerate-strategy guard names, wearing the published policy's name. **This is N-1's substantive
   half and it now works.** Fixed at all three call sites; R205/R215 plant it back.
2. **The offline flags were a claim the code did not make.** `local.py` said they are "deliberately
   module-level and deliberately above the imports that would read it" — and the constant was
   module-level while the *call* was not. Anything that imported `huggingface_hub` first would have
   bound `HF_HUB_OFFLINE` as unset, because it is read at import time. Now called at import.
3. **`hit_threads` ordered by the five-rung lexical ladder** and clamped anything outside it to L3,
   so a thread an L5 probe found would have been *reported as L3* — a rung attribution invented by an
   index clamp.

**Two declared additions to A.7a's cap table**, each because the certificate would otherwise refuse
the response and A.7a has no name for the state:

- `WithheldCap.MAX_RERANK_PAIRS` — a pool thread the pool *read* and the shortlist passed over. A.7a
  names a cap for the threads the pool never read and none for these. Its remedy is the thread map,
  not a wider `k`: `max_rerank_pairs` is the shortlist size PF-4 measured the cross-encoder against.
- `WithheldCap.RECENCY_RECHECK_EXCLUDED` — a recent arrival the closed local re-check found to
  *contradict* a constraint the query stated. Not a cap — nothing was bounded — and reporting it
  under `max_recency_fetch` would say the fetch bound stopped a message it did not stop.

**`peak_rss_mb: 1360` is not model memory.** It is the whole process: interpreter, torch,
transformers and both models in one number with no attribution. `candidate_max_model_rss_mb: 1700` is
a figure for you to look at, **not adopted**, and nothing in the server reads one. D.11's
`semantic_unavailable` RSS clause has no trigger until you adopt a number. Measuring model-only
memory needs a probe that is not registered.

**`max_recency_fetch` is the one width key that raises as well as lowers.** The others bound how much
of what Gmail already returned this server will *disclose*; this one bounds how many messages it will
fetch to find out whether they answer the query at all, at 20 u each, and `max_quota_units` still
bounds the total.

---

## 4. The independent review

Scope: L5, L6, the ranking seam and the budget clock, over `7a3b93f..HEAD`. The reviewer reproduced
**nine** defects with scripts before reporting any of them. All nine fixed in `e5c1b53`; the reviewer
then re-ran its own scripts and reported eight REPAIRED, one PARTIAL, and **one new defect the fixes
had sharpened** — both closed in `96683ef`.

The two that mattered most:

- **L6 ran under no clock at all.** L5 entered and left the semantic clock before assembly, and the
  cross-encoder ran inside the assembly under neither cap. A backend taking ten minutes produced a
  normal response with an empty `budget_caps_hit`. `max_semantic_ms` now **accumulates** across
  entries, so L5 and L6 share one budget rather than getting six seconds each.
- **L5 was undeliverable above ~30 threads in the recency window.** Pool-capped and
  shortlist-passed-over threads were filed one record per message and could not fold, so a
  sixty-thread window produced 42,000 characters of disposition records and zero rows, and the host
  cap refused it — R-MCP-033's exact failure arriving through the rung whose design note says the
  pool creates no rows *because* stub rows would blow the ceiling. Now flat to 800 threads.

Also: every row of a semantic answer claimed a Gmail `q` match to a ninety-day window
(`gmail q matched at L5: after:1781346105`); `_reordered` produced the mixed scale its own docstring
forbade; the `max_pool_threads` affordance could not execute; the cold load was charged to the cap
PF-4's rule excludes it from; the body-head branch declared a body it never read; `semantic_order`
reached lexical threads; and L6 was named neither run nor not-tried.

**One finding stays open in the backlog, outside the reviewed diff.** `withheld_tail`'s
`max_hit_threads` affordance offers the cap's *current* value, so replaying it changes nothing — the
same affordance-that-cannot-execute shape, in round-29 code.

---

## 5. Limitations, stated rather than buried

- **No live acceptance has run for any of this.** Every number above is from a synthetic mailbox or
  from PF-4 on your laptop. M2's acceptance is H1/H2/H3 measured on F1–F17 against the v0.1 lexical
  arm, `generative_llm_calls` zero on F1/F2 traces, and the injection fixtures — none of it had run
  when this was written. **Since `44ae689` the injection fixtures exist and pass** (`make
  acceptance`, item A4); the other two still need the corpus and a mailbox. **M2 is not complete and
  nothing here says it is.**
- **Latency and quality are separate claims and stay separate.** PF-4 measures synthetic text of the
  right length, which is a sound instrument for latency and an unsound one for relevance. Nothing in
  this range measures whether the semantic rung finds better answers.
- **PF-4b has not run, and the reason is not the one this file gave.** It said the Node arm "needs a
  Node runtime and the `node-onnx` artifacts on your machine". That was inaccurate. The real blocker
  is that `models-catalog.json` pins a `node-onnx` artifact set for `stage_b_default` and for **no
  other model**: `stage_a_default` (`minishlab/potion-retrieval-32M`) has no Node artifact set, so a
  Node arm has nothing to embed with — and `read_node_results` required embed timings at all four
  pool sizes and refused any arm without them. PF-4b could not have produced an acceptable result
  however much Node you installed. Since `6d081c0` there **is** an executable command
  (`harness/node/pf4b-arm.mjs`, §8 step 5) and it measures the **reranker only**, declaring
  `stages_measured: ["rerank"]`; `comparison()` then reports R2 as **not evaluable** rather than as
  not firing, because R2 asks about the cost the semantic rung is bounded by at `MAX_POOL_MESSAGES`
  and that cost is stage A. Answering R2 in full needs a stage-A Node artifact set that does not
  exist in the catalog; adding one is a decision plus a pin, not an implementation.
- **PF-10 has not run.** Its analysis exists and its rules are registered; its observations need real
  mail arriving in two real mailboxes.
- **The body-head branch is now correct and unexercised against real mail.** This repo's PF-2 record
  selects the snippet branch, so the fallback path is live only on a machine with no preflight
  records.
- **Four replants were MISSED on first writing**, and each miss was a finding against my own test:
  R196 compared row counts, which a width cap satisfies by accident; R199 asserted `size <= k`, which
  every score threshold also satisfies; R203's fixture never ran L5, so an absent score was
  indistinguishable from a suppressed one; R206 planted a guard clause that was already dead.

---

## 6. What is blocked, and what unblocks it

| Blocked | On |
|---|---|
| M2 acceptance (H1/H2/H3 on F1–F17) | **the case file — the queries and the expected answers — and a seeded mailbox.** The two-arm harness is built (`467df37`): the schema, the joins, both arms, the scoring and the three hypothesis clauses run today against dummy cases. What is separate is the questions, because an implementer writing them writes the exam it is sitting. `EVALUATION_PLAN.md` §4 already specifies every family, size, construction and scoring rule, so nothing needs inventing. `M2_EVALUATION_HANDOFF.md` is the complete handoff |
| Seeding a real mailbox | a concrete `SeedTransport` — four methods, `https://mail.google.com/`, harness credential only. The seeder, verification, settle gate and cleanup are built and tested; the transport is handed over rather than shipped untested because its first run is irreversible |
| PF-4b's **full** answer (R2) | a `node-onnx` artifact set for `stage_a_default`, which the catalog does not have. The rerank half runs today — §8 step 5 |
| PF-10 | real delivered mail in two mailboxes over the observation window |
| PF-5 cold-start verification | a run with the model host blocked at the socket, on your machine |
| SEC-07's "no listening socket" | ~~a ninth CI guard~~ — **built** (`85ccd4c`). What is left is the port scan itself: the guard refuses the code that would open a listener, and only a scanner can show none is open |
| adopting `max_model_rss_mb` | your decision, and a probe that measures model-only memory. **Still not adopted, and nothing reads one** |

`make acceptance` prints this table from the code rather than from this file, per acceptance line,
with the runnable half run. `make acceptance-plan` prints the same without running anything.

The 15 pre-existing `mypy` errors are in `tests/test_preflight_runner_end_to_end.py`,
`tests/test_semantic_interface.py`, `tests/test_modelbench_pf4.py`,
`tests/test_model_provisioning.py` and `tools/guards/sweeps.py`. They predate this range (26 before
it, 15 after) and CI runs `uv run mypy` on your machine, whose resolver may differ from the
container's.

---

## 7. What was built after this file was first written (`a677ab7..d98c3c4`)

**WS-14's injection posture, which `ORIVRA_V1_PLAN.md` said stayed in M2.** It was implementation,
not testing, and it is now implemented. Six commits.

| | What |
|---|---|
| **INJ-05** (`a677ab7`) | A display name is not an identity, a `Reply-To` is not a `From`, and `Authentication-Results` is somebody else's record rather than this connector's verdict. `ThreadParticipant.display_names` carries the pairs fenced and keyed on the address; `MessageRow` gains `headers_observed`, `reply_to_differs` and `authentication`. `SenderAuthentication` has no `passed`/`verdict`/`spf` field and computes none; an oversize record is **declared, not truncated**. Charges measured, not chosen |
| **INJ-02 / INJ-03** (`44ae689`) | Every string on the wire is classified off its own annotation — fenced `Content`, `SenderScalar`, or an address — and a marker planted in every mail-derived field must appear in no other class. Run over all four tools and a semantic response. `I1` is disclosed fenced, never dropped, and steers no call; `I1-bait` gets two tests because the plan's "does not displace true evidence" is true of a wide shortlist and cannot be true of a narrow one |
| **INJ-06** (`a46edeb`) | The closed-typing half was already asserted at the seam. The second clause — *expansion parameters originate only in tool arguments* — now has both forms: no minted call carries a word a message wrote, and every argument value comes from a closed set (an **observed** id, a minted handle, a published enum, a budget key, or a query whose every word the caller typed) |
| **`recency_recheck_excluded`** (`0d4121a`) | Pinned as distinguishable from budget exhaustion in every surface: structurally (it has no `BudgetCapName` twin, so a producer cannot spell it as one), behaviourally (**answered, partial, no cap, `bound: null`** — a combination no budget exhaustion produces), on the text mirror and in the trace. Its recovery is asserted as an **executed** call: a direct read of that id, on the same read-only scope, widening no budget key |
| **`make acceptance`** (`12b7a80`) | §8's status, as a command. Each check either runs here or names its prerequisite; the dataclass refuses one that does both, because a blocked half hiding behind a green citation is the reporting failure it exists to prevent. Every citation is resolved by parsing before anything runs |
| **PF-4b** (`6d081c0`) | The Node command that was missing, and the accurate account of what it can measure — see §5 |

**Four defects, R-M2-016 to R-M2-019** (`FINDINGS_LEDGER.md`). Two were latent HIGH refusals
reachable today: a map source on the expansion path never named its own withheld ids, so the first
A.9a step-8 withholding there made `Source` refuse the response the server had just built; and R-07
required an incomplete source's recovery call to name the *thread*, which a map whose remainder is
enumerated id by id cannot do without handing the caller back the response they are reading. One was
`Score.basis` carrying a candidate's own subject, participants and snippet verbatim into a
connector-voiced field — INJ-02's exact prohibition, in the field ADV-110 created to make a score
legible. The fourth is a finding against my own test: the first INJ-02 sweep could not have found the
third, because nothing in it ran L5 and a walk over payloads with no model output passes a rule about
model output for free.

**One thing I did not do, and it is a real gap.** The disclosure estimate is ~8 % high on ordinary
shapes and ~18 % high on a single long `body_full` row. That is the direction it is allowed to err
in, and it costs a response: a `body_full` row of 1,200 words estimates at 25,082 characters against
a 25,000 cap and renders at ~21,300, so `mailweave_get_messages` declines something that would have
fitted. Recorded as **R-M2-017, open**. Tightening it is a measurement pass of its own and must not
be done by fitting one fixture.

---

## 8. Your machine: the ordered run, with what each step costs and returns

Everything runs from the repository root. **Steps 1–4 need no credential and no network.**
Step 5 onward say what they need. Four things in the previous version of this section were
wrong and are corrected here: PF-4 is not re-run, PF-4b's model path was guessed, PF-5 asked for
machine-wide network changes, and step 1 conflated a product gate with a repository gate.

### Step 1 — the product gates (≈ 4–8 min)

**Run the gates scoped to the product, because the repository gate is currently red for a reason
that is not MailWeave.** `marketing/brand/` carries untracked Python I have not touched and will
not: 77 `ruff check` errors and 11 files `ruff format` would rewrite. Scoping the command is not
hiding that — §Step 1a reports it separately.

```bash
uv run ruff check server harness orivra tests tools
uv run ruff format --check server harness orivra tests tools
uv run mypy
uv run pytest -q -m "not network"
uv run python -m tools.guards
uv run python tools/rubric_status.py --check
uv run python -m mailweave_harness.acceptance --check
```

**Expected:** `ruff` clean on both; `mypy` at **15 errors** in five files
(`tests/test_preflight_runner_end_to_end.py`, `tests/test_semantic_interface.py`,
`tests/test_modelbench_pf4.py`, `tests/test_model_provisioning.py`, `tools/guards/sweeps.py`), all
pre-existing and none in this work; 83 test files green; nine guards clean; the rubric gate
green; 0 unresolved acceptance citations.
**Side effects:** none beyond `.venv` and `uv`'s cache.
**Return:** the last line of each. If `mypy` is not at 15, its full output.

### Step 1a — the repository gate, reported rather than fixed (≈ 1 min)

```bash
uv run ruff check .              # 77 errors, all under marketing/brand/
uv run ruff format --check .     # 11 files, all under marketing/brand/
```

`make check` runs these unscoped and is therefore red. That is a marketing-side decision and it
is yours: either add `marketing/**` to `[tool.ruff] extend-exclude` in `pyproject.toml`, the way
`docs/reviews/**` is already excluded, or run `uv run ruff format marketing/` once. **I have
changed nothing under `marketing/`**, including `marketing/README.md`, which was already modified
in your working tree when this range began and still is.

### Step 2 — M2's acceptance status (≈ 3–5 min)

```bash
uv run python -m mailweave_harness.acceptance --run
```

**Expected:** four items, each `runnable half green` with one blocked check, and a closing line
saying this is evidence status rather than acceptance.
**Side effects:** none. It runs `pytest` over named node ids and writes nothing.
**Return:** the whole output.

### Step 3 — the evaluation harness's own loop (≈ 2 min)

```bash
uv run python -m mailweave_harness.evaluation --schema
uv run python -m mailweave_harness.seed --regenerate-check --seed 1042 --profile gate
uv run pytest -q tests/test_evaluation_harness.py
```

The first prints the case-file interface the campaign is handed (§7 of
`M2_EVALUATION_HANDOFF.md`). The second checks EP §3.7's regeneration contract on the gate
profile — same inputs, byte-identical corpus — which nothing had run at that profile.
**Side effects:** none; `--regenerate-check` writes nothing.
**Return:** whether the contract holds, and the test summary line.

### Step 4 — the replant manifest (≈ 40–90 min; the slow one)

```bash
uv run pytest tests/test_replants.py -m replant -q
```

231 behaviours, each removed one at a time, each citation re-run **alone** in a scratch copy of
the tree. 34 are this work's (R196–R231), each verified CAUGHT individually in the container;
this is the whole manifest on your resolver.
**Side effects:** a temporary tree under your system temp directory, removed on exit. Nothing in
the repository is modified.
**Return:** the summary line, and every `MISSED` row. A MISSED row is a finding against the test,
not against the code — that is how four of this work's were found.

### Step 5 — PF-4: **do not re-run it** (≈ 1 min to confirm)

`preflight-records/PF-4-model-latency.json` records run 2 with verdict **pass**, and nothing in
this range touches the semantic backend, the profile bounds or the measurement path. Re-running
would replace a qualified record with a fresh one for no reason, and PF-4b (step 6) compares the
Node arm against **the recorded** Python numbers rather than against a re-measurement, because
comparing a Node run from one machine-state against a Python run from another is what PF-4b's
first registered rule rules out one level up from the rows.

```bash
uv run mailweave setup-models --status   # confirms the weights are installed and verified
```

Re-run PF-4 only if one of these changes: the lock, the models directory, the machine, or
`mailweave_harness.modelbench`. None of them did.

### Step 6 — PF-4b, the half that can run (≈ 20–40 min, mostly the ONNX download)

**The `node-onnx` artifacts are not pinned yet.** `models.lock` holds
`stage_a_default.python-st` and `stage_b_default.python-st` and nothing else, so the first
command below is a pin, not a re-download — and it is the one command in this repository that
reaches a host outside the runtime pair.

```bash
uv run mailweave setup-models --pin stage_b_default.node-onnx
uv run mailweave setup-models --status          # prints the directory it installed into
```

`--status` prints the path; take it from there rather than from this document. The layout is
`~/.local/share/mailweave/models/<lock key>/<revision>` with `/` in the key replaced by `__`, so
it will be `…/stage_b_default.node-onnx/<the revision the pin recorded>` — **an earlier version
of this section guessed `…/BAAI/bge-reranker-base`, which is not where anything is.**

```bash
uv run python -m mailweave_harness.modelbench --export-node-corpus preflight-records/pf4b-corpus.json
(cd harness/node && npm install @huggingface/transformers)
node harness/node/pf4b-arm.mjs \
  --corpus preflight-records/pf4b-corpus.json \
  --model-dir "$(uv run mailweave setup-models --status | grep node-onnx | awk '{print $NF}')" \
  --out preflight-records/pf4b-node-arm.json
uv run python -m mailweave_harness.modelbench \
  --node-results preflight-records/pf4b-node-arm.json \
  --corpus preflight-records/pf4b-corpus.json \
  --out preflight-records
```

**What it measures and what it will tell you it did not:** the reranker only. The catalog pins a
`node-onnx` set for `stage_b_default` and for no other model, so the comparison prints
`R2: NOT EVALUABLE` and says why. That is the correct answer, not a missing one.
**Side effects:** the ONNX artifacts on disk; two files under `preflight-records/`;
`harness/node/node_modules/` (untracked — delete it afterwards or add it to `.gitignore`).
**Return:** the comparison block, and `--status`'s line for the new set.

### Step 7 — PF-5, isolated and reversible (≈ 20–40 min)

**Do not change your machine's networking.** The previous version of this section asked for
machine-wide egress blocking, which would have disrupted whatever else you were doing and is not
reversible in one step. PF-5 needs a *process* that cannot reach the model host, and a container
gives that with no effect outside it.

```bash
# 7a. PF-5(b): the suite, cold, with NO network at all. Stronger than an allowlist:
#     the suite is marked `not network`, so a green run here proves it needs none.
docker run --rm --network none -v "$PWD":/w -w /w python:3.12 \
  sh -c 'pip install -q uv && uv sync --extra dev --offline || uv sync --extra dev; \
         uv run pytest -q -m "not network"'

# 7b. PF-5(b) proper: the two Gmail hosts reachable, the model host NOT.
#     One container, one hosts entry, nothing outside it touched.
docker run --rm --add-host huggingface.co:127.0.0.1 --add-host cdn-lfs.huggingface.co:127.0.0.1 \
  -v "$PWD":/w -v "$HOME/.local/share/mailweave/models":/models:ro -w /w python:3.12 \
  sh -c 'pip install -q uv && uv sync --extra dev && \
         MAILWEAVE_MODELS_DIR=/models uv run pytest -q -m "not network"'

# 7c. PF-5(c): D.4a's content pipeline with sockets denied, which is already a test.
docker run --rm --network none -v "$PWD":/w -w /w python:3.12 \
  sh -c 'pip install -q uv && uv sync --extra dev; \
         uv run pytest -q tests/test_content_pipeline.py::test_the_pipeline_runs_with_networking_denied'
```

**Why in-process assertions do not settle this:** step 1 proves the allowlist refuses a blocked
host *inside* the process. PF-5 asks whether the process made any other connection, and only a
real network boundary can answer that. `--network none` is that boundary and it exists only for
the life of the container.
**If you do not have Docker:** the reversible alternative is a per-process proxy —
`HTTPS_PROXY=http://127.0.0.1:1 uv run pytest -q -m "not network"` — which makes every outbound
HTTPS call fail in that shell only. It is weaker evidence (it proves nothing about a call that
bypasses the proxy variable) and it is honest to record it as the weaker instrument.
**Side effects:** none outside the container, or outside the one shell for the fallback.
**Return:** whether the suite stayed green in each, and for 7b whether anything reported a
connection to `huggingface.co`. If it did, that is a defect in `HF_HUB_OFFLINE`/`local_files_only`
enforcement and a finding, not a configuration note.

### Step 8 — what needs your mailbox, and what needs the evaluation side

**Superseded at `cbd3d6c`.** Items 1 and 2 below were written when the seeding transport did not
exist. It does now, with its driver, its four refusals and fifteen offline tests, so the list is:

1. **The case file.** Unchanged and still separate. `EVALUATION_PLAN.md` §4 specifies every
   family, size, construction, distractor taxonomy and scoring rule; what is separate is the
   queries and the expected answers, which this process must not hold.
   `M2_EVALUATION_HANDOFF.md` §7 names exactly which files the case author is given and what
   they hand back.
2. **Your approval for the first live write.** `GmailSeedTransport` and `seed/driver.py` are
   built, gated and tested against a double; they have never touched a mailbox.
   `--plan-seeding` prints the account, the client, the token store, the scope, the message
   count, the settle gate and the cleanup behaviour, and sends nothing. The approval is
   `--approve-writes-to <the seed account>`, typed, and compared.
3. **PF-10**, once real mail is arriving in two mailboxes. Its analysis and rules are built.
4. **SEC-07's port scan.** The ninth guard refuses the code that would open a listener; only a
   scanner shows none is open.

### What I am not asking you to decide

`max_model_rss_mb` stays **open and unadopted**, documented as whole-process RSS. D.11's
`semantic_unavailable` clause has no trigger until you adopt a number, and nothing in the server
reads one. Unchanged and deliberate.

---

## 9. The smallest ordered set of next steps

1. **Steps 1, 1a, 2 and 3.** Fifteen minutes between them, and they tell you whether this work
   is green on your resolver, what M2 still owes, and that the evaluation harness runs.
2. **Read `M2_EVALUATION_HANDOFF.md`.** It is the one thing standing between here and M2's
   acceptance, and what it needs from you is two decisions rather than more building from me:
   who writes the cases (§1 and §7), and whether the seeding run may write to the test account
   (§6). `--plan-seeding` answers the second one's questions without sending anything.
3. **Step 4**, when you can leave it running.
4. **Steps 6 and 7** if you want PF-4b and PF-5 closed. Neither gates M2's acceptance. **Step 5
   is a confirmation, not a run.**
5. **Read §7's five findings**, R-M2-017 in particular: the one open defect this work found and
   did not fix, left open because fixing it by fitting one fixture is the failure mode.
