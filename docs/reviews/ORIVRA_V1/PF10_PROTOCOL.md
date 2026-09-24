# PF-10 — the pre-registered freshness baseline, and why the raw probe is not it

**Status:** protocol assembled 2026-09-11, **reconciled against OD-1 the same day**. The
service level is already decided and is reproduced in §5. Nothing here is waiting on an owner
decision.

## 0. PF-freshness-raw is not PF-10

The registered probe `PF-freshness-raw` is `Verdict.OBSERVATION_ONLY`, and its own spec says
what that means:

> no percentile is computed and no aggregate is labelled a service level; OD-1's number is
> evaluated by PF-10 and by nothing else

It measures one thing on one mailbox inside one window: for each message first seen through
`history.list`, the seconds until an id-exact `rfc822msgid:` search returns it, or the fact
that it never did. That is a useful sanity check on D.9's assumption that a message observed
through history becomes findable through search. It is **not** a freshness baseline, it
licenses no freshness sentence, and treating its numbers as one would breach T-VR2 directly:

> A negative result on one mailbox licenses no freshness sentence.

PF-10 is a different instrument: two mailboxes, stratified by thread depth, paired across
arms, run against a service level fixed before the first observation.

## 1. What PF-10 measures

Per AD F PF-10: snapshot `historyId`, observe **real delivered mail** on **both** mailboxes,
record arrival → first-surfacing per probe class, stratified by thread depth. Real delivery
is the thing Tier 2 cannot manufacture, which is why this probe exists at all rather than
being folded into the seeded corpus.

Per probe, recorded:

| Field | Why it is not optional |
|---|---|
| arrival time (H0-equivalent) | the zero of every lag |
| first-surfacing time, **per probe class** | a body-term query and an id-exact query are different questions about the index |
| thread depth at arrival | MF3 is a depth-divergence test and cannot be computed without it |
| censoring flag | a probe that never surfaced is MF1, and averaging it away is the failure mode |
| mailbox | T-VR2's two-mailbox rule is only enforceable if the arm is recorded |

IDs stay local. Aggregates are committed. No mail text is recorded at any depth, which is
the same OD-4 rule the preflight record writer already enforces mechanically.

## 2. Strata

**Thread depth 0 / 5 / 25** (OD-1's three), with depth 0 and depth 25 as the contrast MF3 is
evaluated on. The depth-25 stratum is the reported failure signature: a message arriving into
a long thread is the case the design believes is slower, and a protocol that did not separate
it would report an average over two populations.

## 3. Arms

| Arm | What it is | Why it exists |
|---|---|---|
| **direct REST** | `history.list` / `messages.list` straight against Gmail | the floor. MF6 compares MailWeave's median against it |
| **H5** | MailWeave, shipped configuration, LR on | what a user actually gets |
| **H5-LRoff** | MailWeave with the recency rung **disabled** | **MF6 and MF3 are evaluated on this arm.** Measuring with LR on would make the observed lag a property of the mitigation rather than of Gmail |

`H5-LRoff` is the arm the LR removal gate reads. A recency rung that shipped unconditionally
and unmeasured would be an untested component on the default path.

## 4. The mitigation triggers, pre-registered

Not restated here. They are `EVALUATION_PLAN.md` §11.2.3, MF1 through MF6, and **any one is
sufficient** to make FRESH-02 mandatory. Five of the six need no invented number, which was
deliberate: the decision was designed to be reachable without pre-registering thresholds
nobody has a basis for.

The one that is not a threshold at all is **MF4**: a single confirmed real-mailbox false
negative on recent mail forces mitigation regardless of any percentile. One real
reproduction outweighs a good median.

**MF6 is a MailWeave bug**, not a mitigation trigger in the same sense: if our own median lag
exceeds direct-API lag by more than 60 s, that is fixed regardless of what the mitigation
decision turns out to be.

## 5. The Freshness Service Level, already decided

**OD-1, binding, 2026-08-30** (`docs/OWNER_DECISIONS.md`, RESOLUTIONS):

> MailWeave H5/H6 must achieve **p90 <= 60 seconds** from H0/history-confirmed arrival,
> evaluated **independently at thread depths 0, 5 and 25**. Pooling across depths is
> prohibited.
>
> Additionally: **any confirmed real-mail false negative** — the message is present and
> should match, and MailWeave does not surface it — **is a defect regardless of percentile**,
> and triggers the mitigation build. This is a second, independent trigger; passing p90 does
> not excuse it.

That is the FSL. It is not a range to be chosen from and it is not an open question. It was
registered before any observation, which is the whole property a pre-registered threshold is
supposed to have.

Read against EP §11.2.3, it settles both triggers that were stated in terms of the FSL:

| Trigger | How OD-1 instantiates it |
|---|---|
| **MF2** — p90 of the depended-on arm exceeds the FSL in any stratum | p90 > 60 s at depth 0, 5 **or** 25, each evaluated on its own. Pooling is prohibited, so a passing average over three strata is not a pass |
| **MF5** — the lag ECDF is bimodal with a mode beyond the FSL | a mode beyond 60 s, per stratum |
| **MF4** — a confirmed real-mail false negative | OD-1 states this independently and in the same words: a defect regardless of percentile |

The zero of every lag is **H0/history-confirmed arrival**, which is OD-1's wording and which
this protocol already records per probe (§1). The arms OD-1 names are **H5/H6**, so the
service level is asserted about the shipped configuration and its mitigated successor. MF6
and MF3 are still evaluated on `H5-LRoff` (§3), because those two ask about the server's own
lag rather than about the promise.

### A stale statement elsewhere, and where the authority sits

`EVALUATION_PLAN.md` §13 still lists the FSL under `UNSET-empirical`, and §11.2.2 still
describes it as a decision to be written into experiment log 001. Both predate OD-1 and are
stale. `OWNER_DECISIONS.md`'s RESOLUTIONS section is the authority; a value decided there is
decided, and a table that has not caught up is a documentation defect rather than a live
question.

An earlier draft of this protocol read those two EP passages, concluded the FSL was unset,
and asked the owner to choose it again. That was wrong, and it is the failure mode this
project keeps naming: reading one document's account of a fact instead of the record that
holds it.

## 6. Run shape

- Both mailboxes, continuously, passively, from the first round rather than only in a
  terminal experiment (Tier-1 D6).
- Lag measured from **H0/history-confirmed arrival**, per OD-1.
- Probes are paired per message across arms, so MF3's CI is computed on differences rather
  than on two independent distributions.
- **72 h censoring horizon.** A probe still unsurfaced at 72 h is censored and fires MF1.
- No pooling across depth strata anywhere in the reporting.

## 7. Verification, if a mitigation is built

Arm **H6** — MailWeave with the mitigation — re-runs the identical protocol, same strata,
same N, same schedule. It passes only if it removes **the specific trigger that fired**, and
does not regress the cheap-path latency and API-call bars. A mitigation that improves
freshness by making every query expensive has traded one invariant for another.

## 8. What this document does not do

It does not run anything, and it does not set the FSL: OD-1 did that on 2026-08-30 and this
document reproduces it rather than restating it in its own words. It also does not supersede
`PF-freshness-raw`, which keeps its own narrow job and its own `OBSERVATION_ONLY` verdict.
Two instruments, two claims, and the smaller one does not get promoted by being the one that
has already run.
