# M2 acceptance handoff

**2026-09-16.** One document: what runs today, what the corpus still owes, who must write and
review what, and what only the owner can do. Supersedes the scattered copies of these lists in the
checkpoint and the readiness report where the two disagree.

M2's Accept line (`docs/ORIVRA_V1_PLAN.md` §M2): *H1, H2, H3 measured on F1-F17 against the v0.1
lexical arm; `generative_llm_calls` stays zero on F1/F2 traces; the injection fixtures pass; any
hypothesis that fails removes its machinery from the default path rather than being argued with.*

---

## 1. Runnable now, with no mailbox and no approval

Every command below runs offline or against local files only. The interpreter is whatever you
start them with; none of them creates or synchronises an environment.

| what | command | what it establishes |
|---|---|---|
| The whole evaluation pipeline, offline | `.venv/bin/python -m mailweave_harness.evaluation --dry-run` | Arms build, floor runs, report renders, verdicts compute - **including `no-rerank`**. Dummy cases with sentinel-token queries: it says nothing about retrieval |
| The case-authoring kit | `.venv/bin/python -m mailweave_harness.evaluation --export-kit DIR` | Hands an independent author the brief, field list, families, hypotheses and a standalone checker. Carries no queries, no answers, no retrieval code |
| The case-file interface | `.venv/bin/python -m mailweave_harness.evaluation --schema` | The contract a returned case file must satisfy |
| Validate a returned case file | `.venv/bin/python -m mailweave_harness.evaluation --validate CASES --manifest MANIFEST` | Structural and answer-key validity before anything is run |
| **Read-only mailbox inventory** | `.venv/bin/python -m mailweave_harness.seed --survey --seed-address mailweave.test@gmail.com --manifest benchmarks/manifest-gate-1042.json` | What is already in the account and whether any sentinel collides. Writes are refused on this transport. **This is the next action** (§4) |
| The offline suite | `.venv/bin/python -m pytest` | 4,170 passing; the H2 instrument (`tests/test_h2_rerank_arm.py`) and the R-M2-113 fallback (`tests/test_r_m2_113_semantic_unavailable_fallback.py`) among them |
| **PF-4b** - the Node latency arm | `mailweave-modelbench` exports the corpus; the Node arm reads it | Same rows as the Python arm, crossing the language boundary as data and checked by digest. **No mailbox, no seeding.** **Corrected 2026-09-16: as it stands it measures reranking only** - see below |
| **PF-5** - provisioning and isolation | per its protocol in AD's PF table | (a) anonymous model download with licence and SHA-256 recorded; (b) the full suite cold-started with all egress except `gmail.googleapis.com` and `oauth2.googleapis.com` blocked **and the model host blocked**; (c) the content pipeline with sockets disabled. **No mailbox, no seeding** |

**PF-4b and PF-5 do not require mailbox seeding.** Earlier notes in the checkpoint and the
readiness report grouped them with PF-10 as "live-mail validation"; that was wrong and is
corrected in place. Only **PF-10** (freshness) and **GMAIL-01** (live smoke) need a mailbox.

**Corrected 2026-09-16: PF-4b as it stands cannot answer R2, and the earlier claim that it "is
what lets R2 fire at all" was wrong.** `models-catalog.json` pins a `node-onnx` artifact set for
`stage_b_default` and for no other model, so a Node arm on this lock has nothing to embed with
and can measure the cross-encoder only. The code already says so rather than hiding it:
`NodeArm.stages_measured` records `["rerank"]`, and `modelbench.nodearm.comparison` returns
`r2_evaluable: False` with the reason, because R2 asks whether the Node stack is materially
faster *at equal quality* and the cost the semantic rung is bounded by at `MAX_POOL_MESSAGES` is
stage A. **Running PF-4b today produces a reranker latency comparison and leaves R2 not
evaluable.** Making R2 evaluable needs a Node artifact set for `stage_a_default`
(`minishlab/potion-retrieval-32M`) pinned in the catalogue first; that is a separate decision
and is not scoped here.

## 2. The corpus: what was seeded, and what acceptance needs

These are two different things and conflating them has already cost one round.

**Corrected 2026-09-16. The cleanup record covers the malformed insertion, not the successful
reseed, and this section previously said the mailbox was empty.** The record does not support
that. Read in timestamp order:

| when | record | what it is |
|---|---|---|
| Sep 11 16:35 | `seeding-gate-1042.log` | 2,248 messages in 40 threads inserted into `mailweave.test@gmail.com`, writes approved. Settle gate: **40 discrepancies** |
| Sep 12 03:14 | `verification-gate-1042.MALFORMED-R-M2-033.json` | that insertion's verification report, marked malformed (R-M2-033) |
| Sep 12 04:06 | `cleanup-campaign.log`, `cleanup-verification-gate-1042.MALFORMED-R-M2-033.json` | 2,248 ids deleted, 0 already gone, 0 failed |
| Sep 12 **04:40** | `seeding-gate-1042.rerun.log`, `verification-gate-1042.json` | a **second** insertion of 2,248 messages, settling with **0 discrepancies** - *after* the cleanup |

**Surveyed 2026-09-16, and the mailbox is not empty.** `--survey` against
`manifest-gate-1042.json` reports **2,293 messages and 10 sentinel collisions**. That is
consistent with the 45 original messages plus the 2,248-message reseed remaining in place.
**It is not an individual-ID verification** - the survey counts messages and tests sentinels,
it does not match 2,248 ids one at a time - so what it establishes is that the account has
mail in it and that the "cleaned up" reading was wrong, not that these are those messages.
**No cleanup, deletion or reseeding is authorised** and none has been done. The mailbox's
status no longer blocks offline work.

The ids are what made this predictable. The cleanup record's `deleted` list is **2,248 ids, all of them in the
malformed report and none of them in the successful one**; the successful reseed's 2,248 ids
appear in no cleanup record at all. **So a corpus may still be in that mailbox, and nothing here
shows otherwise.** The earlier claim that it "no longer exists in the mailbox" was read off a
cleanup log whose ids were never checked against the reseed it was assumed to cover.

What the records do support: the seeding path works end to end, and one malformed insertion was
fully removed. **That corpus is not the acceptance corpus either way** - see below - but the
mailbox's actual contents are now an open question rather than a settled one, and they are the
first thing to establish.

**The acceptance corpus is not yet buildable**, and the blocker is content, not seeding:

  * The content gate is open. R-M2-067 to R-M2-073 are unclosed and the fifth independent
    content read stands at **NO**: an odds ratio of about 29 for hedging cues between evidence
    and distractors (R-M2-069), content-free thread shape identifying the family (R-M2-070),
    evidence positions fixed within a family (R-M2-072). The query-free baseline `qf-1`, handed
    the right conversation and no query, answers **6 of 13**.
  * A corpus that gives the family away from register or shape cannot support a retrieval
    claim, so **seeding one now would seed the wrong corpus.** The generator must change first,
    then a fresh manifest, then the content read, then the seed. The scope, the bar and the exit
    for that change are in **`CORPUS_REPAIR_PROPOSAL_2026-09-16.md`**: five determinate defects
    repaired to coverage rules, two statistical ones held to a pre-registered ceiling rather
    than driven to zero, and a hard stop after two rounds.
  * `benchmarks/manifest-gate2-2087.json` (2,452 messages) exists and has **never been seeded**.
    It is a candidate manifest, not an approved corpus.
  * And whatever the 04:40 reseed put there is presumably still there. It was generated by the
    same generator whose content the gate is open on, so it is not the acceptance corpus; it is
    mail in an account that has to be accounted for before anything is added to it.

**Order of operations, therefore:** establish what is in the mailbox now → generator changes →
new manifest → independent content read passes → owner approves the write → seed →
`--live-check` → acceptance run. Nothing downstream of the content read is worth starting before
it, and nothing at all should be written into that account until its current contents are
known.

## 3. Independent authoring and review assignments

The loop rule: the implementer may not write the exam, and may not be the only reader of the
instrument that grades it.

| # | assignment | to whom | inputs | done when |
|---|---|---|---|---|
| A1 | **Author the F1-F17 case file.** Natural questions a person would actually send about the corpus. **Do not write questions to satisfy a mechanism** - eligibility is verified separately, by us, against what comes back | An independent author | `--export-kit DIR` | `--validate` passes and the author has not seen this repository's retrieval code |
| A2 | **Independent content read of the corpus**, the sixth | An independent reader, not A1 | The repaired manifest | C1-C4 of `CORPUS_REPAIR_PROPOSAL_2026-09-16.md` §3 |
| R1 | **Independent review of the acceptance runner** before its numbers are read. **Brief written: `RUNNER_REVIEW_BRIEF_2026-09-16.md`** - eight rubric items, the known-already list, and the offline commands that need no credential | An independent reviewer, not the implementer | That brief | Findings recorded in the ledger and the HIGH/MEDIUM ones resolved |
| ~~R2~~ | Folded into R1 as rubric item **R2 - the bypass is an absence**; it was never a separate review | - | - | - |
| V1 | **Mechanism-eligibility report**, ours, after A1 returns | Us | The returned case file | States, per hypothesis, how many families exercise it: H1 needs incremental semantic retrieval, H2 an exercised reranking comparison, H3 an exercised query-aware versus position-based comparison. **A hypothesis no case exercises is reported `unmeasured`**, which is a result |

**H3 still has no exercised comparison.** R-M2-098 measured the `fixed-window` arms as
wire-identical to their twins on this corpus: every layout is far over the cap, A.9a takes the
fill's depth first, and zero `Band.FILL` rows survive any served first response. Unlike H2's,
this is not a missing arm - the arms exist. It needs cases whose responses *fit* well enough for
the selector's choice to survive the ladder. That belongs in A1's brief and in V1's report.

## 4. Owner actions

1. ~~**Establish what is in `mailweave.test@gmail.com` now.**~~ **Done 2026-09-16: 2,293
   messages, 10 sentinel collisions** (§2). Kept below because it is the command to re-run if
   the account is ever touched again. The seeder already has the
   read-only command for it, on a transport that refuses writes by construction
   (`approved=False`), and it reports sentinel collisions as well as presence:

   ```
   .venv/bin/python -m mailweave_harness.seed --survey \
       --seed-address mailweave.test@gmail.com \
       --manifest benchmarks/manifest-gate-1042.json
   ```

   That manifest is the one the 04:40 reseed inserted. Exit 0 means safe, 2 means a collision.
   This is yours because it needs the account, and it is **first** because every other mailbox
   decision assumes an answer nobody has. **No writes and no deletions until you have it** -
   including no `--cleanup`, which would be a second deletion run aimed from a record we have
   just established does not describe what is there.
2. **Approve or decline the generator work** the content gate implies (§2). Everything else
   waits behind it.
3. **Commission A1, A2 and R1.** These are the only items that cannot be done here. R1's brief
   is written and needs no corpus, so it can start today.
4. **Approve the first write** (`--approve-writes-to mailweave.test@gmail.com`) when a manifest
   has passed the content read - not before.
5. **Decide PF-10's second account.** Its protocol needs a seed account *and* a second unrelated
   sending account; only one exists.
6. **Optional, and cheap now:** run PF-5 (§1). It needs no mailbox and is the only check that
   the model host is not reached at runtime. PF-4b is also runnable and also needs no mailbox,
   but **it will not make R2 evaluable** in its current form (§1); run it for the reranker
   number, or pin a `stage_a_default` Node artifact set first if R2 is what you want.
7. **Triage the harness's 38 `B023`** before the next campaign if you want `make lint` green;
   they are not a defect (R-M2-114, demonstrated) and a `per-file-ignores` entry citing
   `tests/test_corpus_redraw_closure_binding.py` closes them without touching the generator.

## 5. What is deliberately not here

No held-out acceptance questions were authored. No full factorial: three factors would be eight
arms and five are run. No campaign was started. No mailbox was written. No M3 work. The A16
measurement is closed and its records are preserved at `benchmarks/a16-models.VyHeie/`.

**Nothing in this document claims M2 acceptance, and no number produced so far is an acceptance
number.** The diagnostic set's own metadata says `sufficient_for_m2_acceptance: false`.
