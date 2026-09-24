# Raw preflight evidence, preserved outside the reader's path

`server/src/mailweave/semantic/records.py` globs `preflight-records/*.json` and does not
recurse, so nothing in this directory is read by the server. Files here are kept as evidence
of what a run actually observed, including runs whose verdicts were later found not to mean
what they appeared to mean.

## PF-2-run1-2026-09-11-UNDER-EXERCISED.json

The first live PF-2 run. It reported `"verdict": "pass"`.

**Its reply-header verdict is invalid.** Not wrong - absent. The run compared exactly one
message, and that message carried neither `In-Reply-To` nor `References` in the full arm
(`headers_absent_from_both_arms` records both, and `cc`). Every rule fired correctly: no
header the full arm showed was dropped by the metadata arm, so `headers_dropped_by_metadata`
was empty, so the probe passed. The reply-linking question that AD D.5's thread-map pricing
rests on was never asked, because there was nothing in the sample that could have answered
it.

That is a result passing for a reason that does not establish what it claims - the defect
class of R-M1-003 and of replants R134 and R153, one layer out from the code and into the
instrument.

**What was done about it, and what was deliberately not done.** The file is unmodified. Its
verdict was not rewritten, its findings were not reinterpreted, and no conclusion was
back-filled into it. Instead the probe now writes a verdict per question
(`reply_header_verdict`, `snippet_verdict`), and the server-side reader treats a record
carrying neither key as having answered neither question. So this record decides nothing,
by virtue of what it does not contain rather than by anyone editing it.

The snippet observation in it is also from n=1 and is treated the same way, for the same
reason.

**What it is still good for.** It is the evidence that the metadata arm dropped no header it
was given, on the one message it saw, at that instant. And it is the reason the probe has an
exercise floor at all.

## PF-4-run1-2026-09-11-DEVICE-UNRECORDED-RERANK-UNWARMED.json

The first PF-4 run. It reported `"verdict": "pass"` and the bounds held comfortably: 165 ms
warm per-query against a 6,000 ms budget.

**Two things make its numbers unusable as established bounds, and the owner caught both.**

**The device was never selected or recorded.** AD F PF-4 registers the measurement as "on the
actual dev laptop, **CPU only**", and D.5's cost model is a CPU cost model. But
`SentenceTransformer(path, local_files_only=True)` with no `device` argument picks the best
available accelerator, so on an M-series Mac the run may have been on MPS while every
registered number described a CPU. Nothing in the output said which, so the question could
not be settled from the record. The loader now names the device, defaults to `cpu`, and the
finding carries it along with the accelerators present but unused.

**The rerank curve falls as the work grows.** 288 ms for 5 pairs, 229 ms for 10, 137 ms for
25. A cross-encoder does not get faster with more pairs. Each size was timed once, in
ascending order, with no reranker warm-up, so the 5-pair run paid for initialisation that the
10- and 25-pair runs inherited for free. Read as a capacity curve it says the opposite of what
it means.

`per_text_embed_ms: 18` carried the same hazard in a different form: 18 ms beside "100 rows
in 12 ms" invites multiplying out to 5.4 s for a 300-row pool. It is one call carrying one
row, so it is call overhead plus a row, and the field is now named `single_call_embed_ms`
with a note saying multiplying it is a category error.

**What was done.** The file is unmodified. Its verdict was not rewritten and no conclusion was
back-filled. The probe now warms each stage with a discarded call, runs every size five times
and records the median and every sample, names the device, and returns INCONCLUSIVE rather
than PASS when a median curve is not non-decreasing in size. The server-side reader treats a
PF-4 record carrying no `device`, no `repeats_per_size`, or a non-monotonic rerank curve as
having measured nothing, so this record decides nothing by virtue of what it lacks.

**What it is still good for.** It is evidence that the two models load and run on this
machine, that reuse holds (warm acquire 0 ms against a 5,483 ms cold load), and that peak RSS
was 948 MB. The cold-load figure also corrects the smoke run's 36,543 ms downward by a factor
of six, which is what a warm page cache looks like and is why the cold reading is recorded as
a bound rather than as the cold cost.

## PF-5b-case1-smoke-2026-09-19.log

**Label: proxy-constrained smoke evidence.** Isolated auxiliary caches, proxy-constrained,
one CLI command. **Not full PF-5(b) acceptance, and not evidence of an enforced network
boundary.**

SHA-256 `45373dee9a04efe7399489cbc2f49ba50252f63d40aef5067dd6d87f47b9fbc8`, 553 bytes,
10 lines. The owner ran `RELEASE_OWNER_ACTIONS.md` §7a case 1 on the Mac on 2026-09-19 from a
temporary directory macOS would have reaped; the file is copied here byte-for-byte. Nothing in
it was rewritten.

### What is in the log, and what is not

The log holds the smoke command's own output: `smoke: OK`, the model id and revision, a load
time, `embed 2 vectors, dim 512`, `rerank 2 scores`, the two scores, and a sanity line stating
the on-topic candidate outscored the off-topic one. It ends with the command's own disclaimer
that its timings are a smoke check and not a measurement.

**The post-run cache-file listing is not in this log.** The `find … -type f | wc -l` step is a
separate command and its output was reported by the owner, not captured here. That the
isolated caches were empty is therefore **operator-reported**, at the same evidential level as
the Desktop demonstration record, not something this file shows.

### What it establishes

That the two model stages load from the provisioned local weights and really execute: a real
512-dimensional embedding over two texts and a real cross-encoder rerank over two candidates,
ordered correctly. That is a packaging and load result, and it is a real one.

### What it does not establish, and may not be read as

- **It is not evidence of an enforced network boundary.** The method was proxy environment
  variables pointed at a closed port. Those constrain only clients that read them. A library
  using a raw socket, a client that ignores proxy variables, a resolver call, a subprocess that
  rebuilds its environment, or anything connecting directly is untouched by it. What the run
  shows is that **no proxy-honouring client completed a fetch during it** — not that the model
  host was unreachable, and not that egress was enforced. The word "enforced" does not belong
  anywhere near this record; an earlier draft of this section used it and was wrong.
- **ADV-210's revalidation path was not exercised.** The weights were loaded from
  `--models-dir`. Empty `HF_HOME` and `XDG_CACHE_HOME` mean there was *no auxiliary cache to
  fall back on*; they are not a condition that forces `huggingface_hub` to revalidate. The
  absence of a `Retrying in Ns [Retry n/5]` ladder is therefore equally consistent with
  "revalidation was attempted and could not proceed" and with "revalidation was never on this
  code path at all", and nothing in the log distinguishes the two. **No claim about ADV-210
  follows from this run**, in either direction.
- **It is not PF-5(b).** PF-5(b) is the full suite cold-started with egress blocked except the
  two Gmail hosts. This is one CLI command. The suite's own socket ban is a different and
  stronger instrument in kind — it denies `connect`, `connect_ex`, `create_connection` and
  `getaddrinfo` — and weaker in setting, since it runs against whatever cache the machine has.
  Neither substitutes for the other.
- It says nothing about the server answering a query with `semantic_unavailable` in band. That
  path is covered offline by
  `test_offline_enforcement.py::test_the_semantic_rung_declines_in_band_rather_than_reaching_for_a_host`
  and by no live run.
- It says nothing about the runtime egress allowlist holding against `gmail.googleapis.com` /
  `oauth2.googleapis.com`.
- **Its timings are diagnostic only.** PF-4 is the measurement; `PF-4-model-latency.json`
  carries the bounds. No number in this log is a bound, a budget or a published figure, and
  the `load 4680 ms` line in particular is not a cold-load figure — PF-4 records why.

### One thing worth carrying elsewhere

An earlier attempt at this proxy constraint set only the uppercase variables and constrained
nothing, because a preset lowercase `https_proxy` takes precedence. Both cases are set in §7a
for that reason. That is a fact about proxy variable precedence; it is not a fact about network
enforcement, which is the confusion this whole section exists to prevent.
