# M2: what is ready, what is not, and the smallest path to a trustworthy comparison

**At `ea94873`.** This file answers four questions and nothing else: what is genuinely ready,
what is remaining *implementation* versus an *external* prerequisite, the smallest ordered set
of approvals and complete commands, and what results those commands will establish. It
supersedes the run instructions in `M2_HANDOFF.md` §8 where the two disagree.

---

## 1. What is genuinely ready

Everything that can be built without a case file and without a mailbox is built, tested and
committed. The whole campaign path executes offline, end to end, with every instrument attached:

```bash
uv run python -m mailweave_harness.evaluation --dry-run --traces /tmp/mw-dry
```

That command runs **four MailWeave arms and both primitive-floor budgets** over a dummy corpus,
writes and reads a trace per arm, renders the three comparisons and evaluates the three
hypotheses — through the same `_present` the live run uses. It needs no credential, no mailbox
and no network, and it exits 0.

| Piece | State |
|---|---|
| **The arm factorial** | `full`, `sem-off`, `fixed-window` (Baseline F ±2), `sem-off+fixed-window`. Each carries what it isolates **and what it does not**; the two-factor arm says in its own text that it isolates nothing on its own |
| **The v0.1 question, answered honestly** | no arm claims to be the released v0.1. `sem-off` disables embeddings and the cross-encoder; it does not disable mechanical ranking, freshness/LR, traces or anything else added since the tag. Verified by diffing `v0.1..HEAD` and by a live probe showing a no-backend run still reports `L6` |
| **The primitive-tools floor** | search-then-get at `MAX_BODY_FETCHES_L0 = 5` and `MAX_RERANK_PAIRS = 25`, reading bodies through the *same* content pipeline MailWeave uses, so the comparison isolates the policy and not the decoder |
| **First response vs expansion** | measured separately. The recovery driver executes **only** calls the response itself offered, bounded at four rounds, never a call the harness invented. A message being named or reachable is never counted as read |
| **Four states, not three** | `MEASURED`, `FAILED` (with the reason the product gave), `INCONCLUSIVE`, `UNMEASURED` (the instrument was absent). No clause collapses any two |
| **The pool and `cut_loss`** | EP §6.4's both clauses — the exposed candidate set where there is one, the ids observed at the network layer otherwise — with `pool_source` naming which produced each figure, and a negative mean reported `INCONCLUSIVE` rather than as a number |
| **The report** | what improved, what did not, what still fails. Wilson intervals on every figure, and a gap inside overlapping intervals is reported as **no change** |
| **The registered-`n` floor** | every clause refuses to decide on a corpus smaller than EP §4.3/§4.7 registered. A null result still falsifies — that is the plan's own falsifier — but only at the registered size |
| **The seeding path** | consent at the seeder scope into its own store, insert with `internalDateSource=dateHeader`, verify, EP §3.6's settle gate, cleanup from recorded ids. Four refusals before the first write. Paced against Gmail's rate limit, and a run that fails partway still writes the record cleanup needs |
| **The authoring kit** | `--export-kit DIR` writes the brief, the field list, the registered families, the hypotheses and a standalone checker whose schema modules are this repository's own files, copied at export time and asserted byte for byte. Runs on Python 3.12+ and pydantic with nothing else installed |
| **WS-14 / injection** | INJ-01…INJ-06 and SEC-07's guard, closed earlier in this milestone |

**Evidence.** 89 test files, 0 failures. Nine CI guards clean. `mypy` clean over
`server/src`, `harness/src`, `orivra/src`. `ruff` check and format clean outside `marketing/`
(the 78 lint errors and 12 unformatted files there are pre-existing, untouched, and belong to
work being handled separately). 240 replants, each citation failing alone when its behaviour is
removed.

---

## 2. Remaining implementation vs external prerequisites

**Remaining implementation: none for the M2 comparison.** There is no code left to write between
here and a run. That sentence is worth checking rather than trusting, and the check is
`make acceptance`: A1's four runnable checks are green and its one blocked line names only the
two items below.

**External prerequisites, both genuinely external:**

| | What it is | Why it cannot be done here |
|---|---|---|
| **E1 — the cases** | the `query`, `query_variants`, `evidence[].quote`, `answer_field` and `scoring.answer_rule` of each case | an implementer writing the cases writes the exam it is sitting. The handoff is a command — `--export-kit DIR` — and `M2_EVALUATION_HANDOFF.md` §7 says what is in it and where the author runs it |
| **E2 — approval for the first live write** | a person who has read what the seeding run will do, typing the account name | the code is built, gated four ways and tested against a double. What is missing is a decision, not a function. §4 below is the request |

**Not prerequisites for M2's comparison, listed so nobody waits for them:** PF-5's cold-start
capture (needs a real network), SEC-07's port scan (needs a scanner), PF-10 (needs real mail in
two mailboxes), and Baseline E — EP §4.5 item 8's primitive-tools *agent*, which needs a model in
the loop and is not the fixed-policy floor in §1.

---

## 3. The ordered commands

Steps 1–3 need nothing. Step 4 is the only one that writes, and §4 is its approval.

```bash
# --- offline, right now ------------------------------------------------------------------
# 0. the whole campaign path, on dummy cases. No credential, no mailbox, no network.
uv run python -m mailweave_harness.evaluation --dry-run --traces /tmp/mw-dry     # ~1 min

# 1. the corpus: 2,248 messages in 40 threads (5-90 long), 80 sentinels, 40% distractors.
uv run python -m mailweave_harness.seed --generate --seed 1042 --profile gate --out benchmarks
uv run python -m mailweave_harness.seed --regenerate-check --seed 1042 --profile gate

# 2. hand E1 out. This IS the handoff: a self-contained folder, no reading list.
uv run python -m mailweave_harness.evaluation --export-kit ../m2-authoring-kit
cp benchmarks/manifest-gate-1042.json ../m2-authoring-kit/
#    The author runs `python validate.py cases-1042.json manifest-gate-1042.json` inside it.
#    Python 3.12+ and pydantic, nothing else. Same refusals as the scoring run.

# 3. when the cases come back, check them before spending a seeding budget.
uv run python -m mailweave_harness.evaluation --validate /abs/path/cases-1042.json \
    --manifest benchmarks/manifest-gate-1042.json                                # seconds

# --- needs your approval (E2) ------------------------------------------------------------
# 4a. what seeding would do. Reads the OAuth client file; opens no token store; sends nothing.
uv run python -m mailweave_harness.seed --plan-seeding \
    --manifest benchmarks/manifest-gate-1042.json \
    --seed-address mailweave.test@gmail.com

# 4b. consent as the SEED account only, at https://mail.google.com/, into its own store.
uv run python -m mailweave_harness.seed --login \
    --seed-address mailweave.test@gmail.com \
    --client-path mailweave-harness-oauth.json \
    --token-path ~/.mailweave-harness/credentials.json

# 4c. read-only: what is already in that mailbox, and whether any sentinel already matches.
uv run python -m mailweave_harness.seed --survey \
    --manifest benchmarks/manifest-gate-1042.json \
    --seed-address mailweave.test@gmail.com

# 4d. THE ONE WRITE. Insert, verify, settle, write benchmarks/verification-gate-1042.json.
uv run python -m mailweave_harness.seed --seed-mailbox \
    --manifest benchmarks/manifest-gate-1042.json \
    --seed-address mailweave.test@gmail.com \
    --approve-writes-to mailweave.test@gmail.com \
    --out benchmarks

# --- the measurement ---------------------------------------------------------------------
# 5. every arm, every instrument, the three questions and the three verdicts.
uv run python -m mailweave_harness.evaluation --run \
    --cases /abs/path/cases-1042.json \
    --manifest benchmarks/manifest-gate-1042.json \
    --verification benchmarks/verification-gate-1042.json \
    --client-path mailweave-server-oauth.json \
    --traces benchmarks/traces-1042 \
    --out benchmarks/h1-h3-1042.json

# 6. remove exactly what 4d inserted, from the recorded ids and never from a query.
uv run python -m mailweave_harness.seed --cleanup benchmarks/verification-gate-1042.json \
    --seed-address mailweave.test@gmail.com \
    --approve-writes-to mailweave.test@gmail.com
```

Step 5 uses the **server** credential (`gmail.readonly`) and never sees the harness credential.
Step 4 uses the **harness** credential and refuses, before any network call, if handed the
server's client or asked to write into the server's token store.

---

## 4. The seeding approval request

Everything a decision needs, in one place. `--plan-seeding` prints the first six of these from
the code rather than from this document.

| | |
|---|---|
| **Account** | `mailweave.test@gmail.com` — the declared seed account, and the only one the run may touch. Compared against a real `users.getProfile` before the first insert and again before the first delete |
| **Message count** | **2,248** messages in 40 threads (5 to 90 messages each), carrying 80 sentinel tokens, at 40% distractors — the `gate` profile at seed 1042. Senders and recipients are `@team.example`; message ids are `<1042.nnn.nnn@team.example>`; subjects look like `Budget Draft 72-000` |
| **Credential and scope** | the **harness** OAuth client (`mailweave-harness-oauth.json`) at `https://mail.google.com/` only, stored at `~/.mailweave-harness/credentials.json`. The server credential stays `gmail.readonly` and is not read by any of step 4. Three controls keep them apart: Google's own test-user allowlist on the harness client, a CI guard that stops `server/**` importing the harness package, and a binding re-checked at the point of every write |
| **Isolation from existing test mail** | the corpus is **added** to whatever is already in that account, not written into an empty one. `--survey` (4c) reports how many messages are already there and whether any manifest sentinel already matches one of them; a collision is a refusal, because a sentinel matching pre-existing mail makes the settle gate pass early and a recall metric join on a row the seeder did not insert. Nothing outside the inserted set is ever read for content, modified, or deleted |
| **Verification** | three checks after the inserts, all against the **mailbox**: every manifest message is present, every manifest thread is one Gmail conversation, and every sentinel is unique in the mailbox. Any discrepancy is recorded and the run reports a non-zero exit. Then EP §3.6's settle gate: ten sentinel queries must match their manifest counts **twice in a row, 60 s apart**, giving up after 30 minutes. No metric run starts before that returns |
| **Cleanup** | `--cleanup` deletes exactly the Gmail ids the verification report records, one by one, permanently (not to Trash) — never anything a query matched. The account is re-asserted before the first delete. **A run that fails partway still writes that report**, marked `partial`, so a half-seeded mailbox always has an exact list of what to remove |
| **Duration and cost (estimate, unverified)** | 2,248 inserts at 25 quota units each is ~56,200 units; Gmail's per-user ceiling puts a floor of roughly 4 minutes on that, and sequential round-trips make ~10–20 minutes the realistic figure, plus 2–30 minutes for the settle gate. The transport paces itself against a 429 (six attempts, 2 s doubling to a 64 s cap, honouring `Retry-After`) rather than failing the run |
| **Reversibility** | the inserts are reversible by step 6. Nothing else about the account is changed: no labels, no filters, no settings, no reads of pre-existing content |

**What I need from you is one line:** whether step 4d may run against
`mailweave.test@gmail.com`. If the answer is yes, running 4a then 4c first is free and tells you
what the account looks like before anything is written.

---

## 5. What these commands establish — and what they do not

**They establish**, per family and per arm, with Wilson intervals and the registered `n`:

- **What the new Gmail retrieval improves**: families where `full` put more required evidence in
  the reader's hands than `sem-off` (the semantic rungs) or than `fixed-window` (the disclosure
  selector), with the arm and the isolated factor named beside every figure.
- **What it does not improve**: the same families where the intervals overlap, reported as loudly
  as the first. EP §7.1 pre-registered an ablation for exactly this, and a no-gain result removes
  the machinery from the default path rather than being argued with.
- **What still fails**: per case, in three separate states — the product failed (with its own
  reason), the evidence was surfaced and never carried (a recoverability result), or it was never
  named at all (a retrieval result).
- **H1, H2 and H3**, each against the falsifiers `ORIVRA_V1_PLAN.md` §8.2 states, quoted in the
  output so a report cannot drift from the plan.
- **The floor**: what the same mailbox gives a caller with search and get and no ladder, at both
  of MailWeave's own budget constants.

**They do not establish** that MailWeave is better. One corpus at one seed cannot support that,
and nothing in the output claims it: a difference inside overlapping intervals is reported as no
change, a clause below its registered `n` reports `NOT_EVALUABLE`, and `NOT_EVALUABLE` is never
rounded to `holds`. They also do not move a rubric row — only a reviewer who did not write the
code may do that, and `make gate` is what checks it.

**They are not a gate.** A falsified hypothesis removes its machinery from the default path; one
that holds is a citation a gating reviewer re-runs.
