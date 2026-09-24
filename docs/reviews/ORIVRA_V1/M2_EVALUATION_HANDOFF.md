# M2 evaluation handoff — what the campaign owns, and everything it is handed

**Status at `515cea5`+.** The harness is complete and runs end to end offline. Four MailWeave
arms, a primitive-tools floor at two registered budgets, first-response and expansion-reached
evidence measured separately, the pool and `cut_loss` measured on every arm, traces written and
read back, the three questions rendered, and the three hypotheses evaluated against the plan's
own falsifiers. The seeding path — consent, insert, verify, settle, cleanup — is built, gated
and tested against a double.

**Two things are genuinely outside it**, and both are named precisely below: the **cases**
(§1), and the owner's **approval for the first live write** (§5).

**This document does not ask you to invent a campaign.** `EVALUATION_PLAN.md` already specifies
every family, its size, its construction, its distractor taxonomy, its position discipline and
its scoring; `ORIVRA_V1_PLAN.md` §8.2 already states each hypothesis and exactly what falsifies
it. Everything below points at those. What is genuinely separate is narrow and is named in §1.

---

## 1. The separation, stated precisely

| Who | Holds |
|---|---|
| **This repository** | the corpus generator, the answer key, the case-file schema and its refusals, the ref→manifest→mailbox joins, both arms, the scoring primitives, the hypothesis clauses |
| **The evaluation side** | the **queries** and the **expected answers** — that is, the `query`, `query_variants`, `evidence[].quote`, `answer_field` and `scoring.answer_rule` of each case |

That is the whole of it. The separation is not about capability — the harness could produce
plausible cases — it is that an implementer writing the cases writes the exam it is sitting, and
the one thing a measurement cannot survive is the system under test having chosen the questions.

**What this repository may see afterwards:** the per-case numbers and the verdicts. It must not
see the case file before a run, and no case content reaches source control here. `EVALUATION_PLAN`
§5.2 already says case files and manifests live only in the harness; this keeps that true.

---

## 2. The input format

One JSON file. Print the authoritative version, with every refusal listed, from the repository:

```
uv run python -m mailweave_harness.evaluation --schema
```

It is `EVALUATION_PLAN.md` §4.1's object, field for field, wrapped in a file header that names
the corpus it was written against:

```json
{
  "schema_version": 1,
  "generator_version": "1",
  "master_seed": 1042,
  "cases": [
    {
      "case_id": "BE-t07-p37-s1042",
      "template_id": "BE-t07",
      "family": "buried_evidence",
      "seed": 1042,
      "query": "When did Priya agree to move the launch date?",
      "query_variants": ["Did Priya ever sign off on shifting the launch?"],
      "evidence": [
        {
          "ref": "thread:<thread_key>/pos:37",
          "rfc_message_id": "<optional; checked against the manifest>",
          "role": "primary",
          "quote": "Fine — let's move it to October 17.",
          "answer_field": {"date": "2026-03-11", "value": "October 17"}
        }
      ],
      "evidence_cardinality": "single",
      "distractors": [{"ref": "thread:<k>/pos:12", "type": "lexical_decoy", "note": "…"}],
      "position": {"thread_len": 100, "target_pos": 37, "fraction": 0.37},
      "paraphrase": {"tier": 2, "content_word_jaccard": 0.0},
      "expected_behavior": {
        "must_retrieve": ["primary"],
        "acceptable_not_found": false,
        "partiality_expected": true,
        "notes": "Full-thread dump also passes recall; the discriminator is tokens + partiality."
      },
      "scoring": {"recall_rule": "evidence message body disclosed (rfc_message_id join)",
                  "answer_rule": "date == 2026-03-11 OR contains 'October 17'"}
    }
  ]
}
```

Three things about it are worth knowing before you write a hundred of them.

**`ref` is the portable identity, not `rfc_message_id`.** A ref is `thread:<thread_key>/pos:<n>`
and it survives regeneration: a new `master_seed` re-randomises names, dates and message ids
while the *shape* — thread count, lengths, position grid — is drawn from a generator seeded
without the seed. Cases pinned to positions carry across seeds; cases pinned to ids do not.
`rfc_message_id` is optional and, when present, is **checked** against what the manifest holds at
that position — a disagreement is refused, because a case written against a different corpus
scores a retrieval that never happened.

**`expected_behavior.notes` is required and non-empty.** §4.1 says it "states what would make a
pass hollow, which the gate reviewer reads". A case that cannot say what a hollow pass looks like
is refused at load.

**The refusals fire before any mailbox is touched.** An answerable case with no evidence, an
unanswerable control that names evidence or does not accept not-found, `must_retrieve` naming a
role no evidence carries, a `position` whose `fraction` does not describe it (§4.4 makes the
fraction normative), a `paraphrase` tier contradicting its own measured jaccard (§4.5), a family
or distractor type outside the plan's lists — each is a refusal rather than a warning, because
each would otherwise publish a number nobody could read.

---

## 3. The commands, in order

Everything runs from the repository root. Steps 1–3 and 5 need no mailbox; step 4 is the only
one that writes, and §5 is its approval.

```bash
# 1. the corpus. Offline: no credential, no mailbox, no network.
uv run python -m mailweave_harness.seed --generate --seed 1042 --profile gate --out benchmarks
uv run python -m mailweave_harness.seed --regenerate-check --seed 1042 --profile gate

# 2. write the case file against benchmarks/manifest-gate-1042.json   (§2 above)

# 3. check it before spending a seeding budget. Every refusal fires here, offline.
uv run python -m mailweave_harness.evaluation --validate cases-1042.json \
    --manifest benchmarks/manifest-gate-1042.json

# 4a. see exactly what seeding would do. Reads the OAuth client file; opens no token
#     store; sends nothing.
uv run python -m mailweave_harness.seed --plan-seeding \
    --manifest benchmarks/manifest-gate-1042.json \
    --seed-address mailweave.test@gmail.com

# 4b. consent as the seed account, at https://mail.google.com/, into the harness's own
#     token store. Refuses the server's client and the server's store.
uv run python -m mailweave_harness.seed --login \
    --seed-address mailweave.test@gmail.com \
    --client-path mailweave-harness-oauth.json \
    --token-path ~/.mailweave-harness/credentials.json

# 4c. THE ONE WRITE. Inserts, verifies, waits for EP §3.6's settle gate, writes
#     benchmarks/verification-gate-1042.json. `--approve-writes-to` must name the account.
uv run python -m mailweave_harness.seed --seed-mailbox \
    --manifest benchmarks/manifest-gate-1042.json \
    --seed-address mailweave.test@gmail.com \
    --approve-writes-to mailweave.test@gmail.com \
    --out benchmarks

# 5. every arm, every instrument, the three questions and the three verdicts.
uv run python -m mailweave_harness.evaluation --run \
    --cases cases-1042.json \
    --manifest benchmarks/manifest-gate-1042.json \
    --verification benchmarks/verification-gate-1042.json \
    --client-path mailweave-server-oauth.json \
    --traces benchmarks/traces-1042 \
    --out benchmarks/h1-h3-1042.json

# 6. remove exactly what step 4c inserted. Driven from the recorded ids, never from a query.
uv run python -m mailweave_harness.seed --cleanup benchmarks/verification-gate-1042.json \
    --seed-address mailweave.test@gmail.com \
    --approve-writes-to mailweave.test@gmail.com
```

Step 5 needs the **server** credential (`gmail.readonly`) and a seeded mailbox; it never sees
the harness credential, which is step 4's alone. Step 4 never sees the server credential, and
refuses before any network call if it is handed one.

**The whole of step 5's path is exercised offline** by `--dry-run`, which runs the same code —
arms, floor, traces, report, verdicts — against a dummy corpus, needing no credential and no
network:

```bash
uv run python -m mailweave_harness.evaluation --dry-run --traces /tmp/mw-dry
```

It prints every hypothesis as `NOT_EVALUABLE`, which is the correct output for six dummy cases
and is the behaviour that matters: the registered-`n` floor refuses to decide a hypothesis on a
corpus smaller than the plan registered.

---

## 4. The arms, and what each comparison isolates

Six arms run. Four are MailWeave configurations in a 2×2 over the two factors; two are the
primitive-tools floor at the two budgets MailWeave's own constants name.

| Arm | Semantic backend | Selector | Isolates |
|---|---|---|---|
| `full` | on | query-aware | — the reference |
| `sem-off` | **off** | query-aware | the semantic rungs (L5 embedding, L6 cross-encoder) |
| `fixed-window` | on | **Baseline F ±2** | the disclosure selector (DISC-02, EP §8.8) |
| `sem-off+fixed-window` | off | ±2 | **nothing on its own** — two factors differ at once |
| `primitive-floor-tight` | — | — | `MAX_BODY_FETCHES_L0 = 5` search+get, no ladder |
| `primitive-floor-generous` | — | — | `MAX_RERANK_PAIRS = 25` search+get, no ladder |

**`sem-off` is not the released v0.1 and no arm claims to be.** Turning the backend off disables
embeddings and the cross-encoder; it does not disable mechanical ranking, freshness/LR, the trace
schema or anything else added since the tag. `git diff v0.1..HEAD` names those directories, a
no-backend run still reports `L6` in its rungs, and `ArmSpec.does_not_isolate` carries that
sentence into the output of every run so a reader cannot acquire the wrong baseline by reading a
table. A true v0.1 comparison would be a second checkout, and it is not what these arms are.

---

## 5. What comes back, and how to read it

Three questions per comparison — **what improved, what did not, and what still fails** — and then
the three hypotheses with the clause that decided each:

| | Falsified if |
|---|---|
| **H1** | F4/F11 recall does not rise over the lexical arm, **or** embedding calls appear on F1/F2 traces |
| **H2** | F16 `cut_loss` does not fall, **or** F1 ordering changes, **or** F12 regresses |
| **H3** | F3 position-flatness does not improve, **or** F17 reversal recall drops in the query-aware arm |

Five properties of the report worth knowing in advance.

- **A difference inside overlapping Wilson intervals is reported as no change.** One corpus at
  one seed cannot call a small gap a win, and calling it one is how a null result becomes a
  headline. Every figure carries its interval and its *n*.
- **`NOT_EVALUABLE` is a verdict and is never rounded to `holds`.** A clause answered by fewer
  cases than EP §4.3/§4.7 registered reports the registered figure and the figure it had. A null
  result still falsifies — that is the plan's own falsifier and EP §7.1's publishable negative —
  but only at the registered size.
- **First-response and expansion-reached evidence are separate numbers.** `first_response` is
  what one call put in the reader's hands; `after_expansion` is what following the response's
  **own** offered affordances reached, bounded at four rounds, executing only calls the response
  itself made and never a call the harness invented. A message being named or reachable is not
  the same as the agent having read it, and the report never merges the two.
- **"Still failing" has three states, not one count.** `failed` (the product failed, with the
  reason it gave), `surfaced_never_carried` (named and reachable and the content never arrived —
  a recoverability result, not a retrieval one), and `never_named` (absent from every response).
  They license different conclusions.
- **`cut_loss` says which instrument produced it.** EP §6.4's pool is the exposed candidate set
  where there is one and "the union of messages it fetched, observable at the network layer"
  otherwise; `pool_source` names the clause per case. A negative mean is `INCONCLUSIVE`, never a
  figure: the shortlist is a subset of the pool, so a negative value means the pool read is not
  the pool the answer came from.

---

## 6. What is still outside this repository

**The cases.** §1. Nothing has changed there and nothing should.

**The owner's approval for the first live write.** The seeding path is built, gated four ways
and tested against a double, and it has never run against a mailbox. What it needs is not code:
it is a person who has read what it will do — the account, the message count, the scope, the
isolation from existing mail, the verification procedure and the cleanup behaviour — and typed
the account name into `--approve-writes-to`. `--plan-seeding` prints all six without sending
anything.

**Baseline E, the primitive-tools *agent*.** The floor in §4 is a fixed policy — search, then get
the top *N* — not an agent with a model deciding what to fetch next. It is the honest lower bound
on what these tools give a caller with no ladder, and EP §4.5 item 8's agent arm, which needs a
model in the loop, is not it and is not here.

---

## 7. The handoff itself, and where to run it

**The handoff is a command, not a reading list.** From the repository root:

```bash
uv run python -m mailweave_harness.evaluation --export-kit ../m2-authoring-kit
cp benchmarks/manifest-gate-1042.json ../m2-authoring-kit/
```

That writes a self-contained folder. Send the **folder** — that is the whole handoff:

| In the kit | What it is |
|---|---|
| `README.md` | the brief: what the author is writing, why the split exists, how to read the corpus, what makes a case discriminate, what to avoid, and how to hand it back |
| `CASE_FILE_INTERFACE.txt` | the authoritative field list with every refusal, printed from the code that enforces it |
| `FAMILIES.md` | the registered families and per-seed counts, generated from `REGISTERED_N` rather than retyped |
| `HYPOTHESES.md` | H1/H2/H3 and their falsifiers, so the author knows what a case is *for* |
| `validate.py` + `kit_schema/` | the checker, and the repository's **own** `cases.py` and `manifest.py`, copied at export time and stamped with the commit in `VERSION.txt` |
| `manifest-gate-1042.json` | the corpus: 40 threads, 2,248 messages, every body and date, and the answer key |

**The kit runs where the author is.** It needs Python 3.12+ and pydantic, and nothing else — no
`mailweave_harness`, no PYTHONPATH, no network, no credential:

```bash
cd m2-authoring-kit
python validate.py cases-1042.json manifest-gate-1042.json
```

Exit 0 means every case loaded and every ref resolved; exit 2 prints each refusal with its case
id. **These are the same refusals the scoring run applies** — the schema modules are this
repository's files, asserted byte for byte by `tests/test_authoring_kit.py`, which exports a kit
and drives a case file through it in a subprocess with nothing on the path. So a file that passes
in the author's hands is not turned away later for a reason they could have seen.

It also reports where the file is short of a registered family count. That is not a refusal, and
it is worth knowing before the campaign rather than after: a clause below its registered `n`
reports `NOT_EVALUABLE` rather than a verdict.

**What the kit deliberately does not contain.** No retrieval code, no ladder, no ranking, no
selector, no arms. The author writes cases against the corpus and the plan, not against the
implementation, because a case written with the implementation in view tests what the
implementation already does. (`cases.py` keeps one `mailweave_harness` import under
`if TYPE_CHECKING`, which never executes — the mailbox half of the ref join is not the author's
half.)

**What comes back, and where it goes.** One file, `cases-1042.json`, by whatever channel you
agree. It must not enter this repository's source control at any point — `EVALUATION_PLAN.md`
§5.2 says case files and manifests live only in the harness. Two things enforce that and it is
worth being exact about which: `.gitignore` ignores `cases-*.json`, `benchmarks/`, `traces-*/`,
`verification-*.json` and `manifest-*.json`, which stops an accidental `git add`; and the
`ground-truth-isolation` CI guard refuses *ground-truth identifiers and string literals in
`server/**` and `orivra/**` source*, which is a different and narrower thing — **it does not
inspect committed data files**. Neither survives `git add -f`. So keep the returned copy outside
the working tree: `--cases` takes an absolute path.

**Do not send the author a list of questions to answer, and do not send them queries you would
have written.** The separation is the point: an implementer who supplies the questions has
written the exam it is sitting.
