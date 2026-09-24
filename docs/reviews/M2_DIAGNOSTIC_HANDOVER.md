# The bounded M2 diagnostic: one command, and what it can and cannot establish

This is the executable route to a diagnostic result. It is not an M2 acceptance run, it does
not change the registered acceptance criteria, and it touches no mailbox.

## The command

Run this on the Mac, in Terminal, using that machine's own interpreter and the models already
provisioned there. Nothing about it writes to a mailbox, and nothing about it modifies `.venv`.

```bash
cd ~/Desktop/Nayan/MailWeave && \
PYTHONPATH=server/src:harness/src:orivra/src:tests/fixtures:. \
.venv/bin/python benchmarks/run-diagnostic-4311.py \
  --models-root ~/.local/share/mailweave/models \
  --device cpu
```

To confirm the weights load and stop there, add `--preflight-only`. That takes seconds.

Outputs land beside the case file: `benchmarks/diagnostic-run-4311.txt` (the report) and
`benchmarks/diagnostic-run-4311.json` (every outcome, with the untruncated decline text).
Exit code is 1 if any fatal problem was found, 0 otherwise, 2 if the preflight refused.

## The preflight refuses rather than falls back

`preflight()` loads both locked models and exercises each one (an embedding, then a rerank of
two candidates) before anything else happens. If the lock cannot be read, if the digests do
not match, if a directory is missing, or if the model runtime is not installed, it prints what
failed and exits 2 having run nothing.

**There is no stub path in the runner to fall back to.** The development fixture's
`_WordBackend` is bag-of-words over the corpus's own vocabulary; an arm running on it would
produce numbers labelled "semantic" that say nothing about semantic retrieval, and a
comparison that silently degraded to it would be the most misleading thing this script could
do. `benchmarks/verify-diagnostic-runner.py` proves the absence rather than asserting it: it
runs the preflight against a missing model root, checks the exit code and the message, and
greps the runner for a stub call site.

## No mailbox is contacted

The corpus is generated in memory at seed 4311, profile `sample`, and served by
`SyntheticMailbox` through the same `GmailClient` the product uses. Nothing is inserted,
modified or deleted anywhere. The gate corpus is not built or seeded.

## The arms and the budgets, stated before the numbers

| arm | what it is |
|---|---|
| `full` | the current server, real backend, query-aware selection |
| `sem-off` | no backend registered. **Not** the released v0.1 - see `evaluation/arms.py` |
| `fixed-window` | real backend, fixed ±2 disclosure selector |
| `sem-off+fixed-window` | neither |
| `primitive-floor-tight` | `messages.list` + `messages.get`, 5 bodies (`MAX_BODY_FETCHES_L0`) |
| `primitive-floor-generous` | the same, 25 bodies (`MAX_RERANK_PAIRS`, the widest set MailWeave ever scores) |
| `qf-1` | the frozen query-free baseline, **handed the right conversation** |

Expansion is bounded at `MAX_RECOVERY_ROUNDS = 4` follow-up calls. The primitive floor is a
fixed policy, not EP §4.5's Baseline E agent, and `primitive.py` says so at length.

## Fatal versus residual, as the report separates them

**Fatal** is the reader left able to conclude only a wrong thing, or the product not
answering: a forbidden value in hand with the answer absent; a control with a forbidden figure
in hand and no abstention; an arm that raised or declined. **Residual dataset bias** is
measured and disclosed, not treated as failure: `qf-1`'s score, and the EP §4.6 competitor
class distribution. A competitor appearing beside the evidence is not a defect - a retrieval
surface is supposed to return the candidates.

`qf-1`'s score is what the corpus gives away *once retrieval has already succeeded*. The gap
between it and any other arm is **not** a count of cases solved by retrieval: the arms are not
nested and they do not get the same cases right. Read the paired case-level table, not the
margin.

## Read R-M2-076 before reading the numbers

Building the runner surfaced this, from the two arms that register no backend at all, so no
stand-in is involved: `DisclosureLadderExhausted` fires on 7 of 15 cases on `sem-off` and 7 of
15 on `sem-off+fixed-window`. The refusal is correct under DISC-06 and OD-3, but an arm that
declines scores zero for a reason that has nothing to do with the mechanism under test. Until
that is understood, a low score on those cases is uninterpretable. It is recorded OPEN and not
repaired: repairing it is a retrieval change and this round has no authorisation for one.

## Why the gate corpus is 11,862 messages

It is not a realism choice. It falls out of `REGISTERED_N` and EP §4.4's position sweep.

| band | threads | messages | share |
|---|---|---|---|
| F3 `buried_evidence` | 84 | 7,769 | 65% |
| filler and short | 93 | 1,236 | 10% |
| every other family | 162 | 2,857 | 24% |
| **total** | **339** | **11,862** | |

EP §4.3 registers 84 F3 cases, and §4.4's seven-fraction sweep requires each to sit in a long
thread; §4.2 sizes those at ~100, rescaled to 90 under §3.8's conversation ceiling. 84 × ~92.5
is 7,769 messages before any other family exists. The figure grew from ~10,600 to 11,862
across the repair rounds because several families gained the material the coverage rules now
check - F7's sibling threads, F15's four structural shapes, F8's 88 attachments spread across
fifteen families instead of four.

**The 84 is the lever.** Cutting F3's registered count is the only way to make the corpus
materially smaller, and that is a change to the registered acceptance criteria, not an
implementation decision.

## The minimum live corpus for the diagnostic run

**The whole `sample` profile: 1,725 messages in 76 threads, seed 4311.** That is 15% of the
gate corpus.

The fifteen cases reference 20 threads holding 767 messages directly. Those 767 cannot be
seeded alone: the remaining 56 threads are the distractor population the cases are scored
against, and the generator's construction guarantees - uniform reference markers, the
attachment base rate, the value-frequency and shape checks - hold for a whole profile and not
for a subset of it. Seeding only the referenced threads would make every target trivially
findable and the result would measure the seeding, not the retrieval.

For the offline run above, none of that matters: the corpus is in memory. The 1,725 figure is
the answer to "what would a live diagnostic need", and seeding it needs separate approval that
has not been asked for or given.

## What this run cannot establish

- **Anything about acceptance.** Fifteen hand-authored cases over one sample corpus. The case
  file says `sufficient_for_m2_acceptance: false` in its own metadata.
- **Gmail's own behaviour**: threading, `q` semantics, ranking, latency, quota. The synthetic
  mailbox is the product's client over an in-memory store.
- **DIAG-EXP-01's and DIAG-EXP-02's segmentation premise.** The case author marked both
  UNVERIFIED rather than reading the server to check them.
- **Whether a correct answer was reached by the mechanism under test.** Each case's
  `expected_behavior.notes` says which trajectory evidence to require; the runner checks the
  corpus, not the trajectory.
- **The content gate.** R-M2-067 through R-M2-073 are still open and the fifth independent
  read still stands at NO.

## Placement

The runner and its verification live under `benchmarks/`, which is gitignored by design
because the held-out case file lives there. Whether the runner should move to
`harness/scripts/` and leave only the case data behind is a question for the owner.
