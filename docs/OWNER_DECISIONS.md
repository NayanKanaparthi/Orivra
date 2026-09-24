# OWNER_DECISIONS.md — the four things only Nayan can decide

> **STATUS: ALL FOUR DECIDED by the project owner, 2026-08-30.** The resolutions below are
> BINDING and supersede the options and recommendations recorded later in this file. Where a
> document conflicts with a resolution here, that document changes. No further owner input is
> pending on OD-1..OD-4.

## RESOLUTIONS (binding, 2026-08-30)

### OD-1 · Freshness Service Level — DECIDED

MailWeave H5/H6 must achieve **p90 <= 60 seconds** from H0/history-confirmed arrival, evaluated
**independently at thread depths 0, 5 and 25**. Pooling across depths is prohibited.

Additionally: **any confirmed real-mail false negative** — the message is present and should match,
and MailWeave does not surface it — **is a defect regardless of percentile**, and triggers the
mitigation build. This is a second, independent trigger; passing p90 does not excuse it.

### OD-2 · "Not found" semantics — DECIDED

MailWeave **never claims absolute mailbox nonexistence.**

- `NOT_FOUND` means: every retrieval path applicable to this query was **actually executed** and
  exhausted, and no evidence was found.
- If an applicable structural, semantic, freshness-recovery or other escalation path was **not
  executed** because of budget exhaustion, error, timeout or cap, the result is
  **`INCONCLUSIVE` / partial**, never `NOT_FOUND`.
- Every negative result reports: routes executed, relaxations performed, counts, and **routes not
  tried**.

This makes the distinction between "we looked everywhere applicable" and "we ran out of budget"
a first-class, machine-checkable property of the response.

### OD-3 · Reply-chain floor — DECIDED

The floor guarantees **presence and reachability as at least stubs**, not automatic full-body
disclosure. Body depth remains **query-aware and budget-aware**. Structurally necessary parents and
children are **promoted to deeper content** when the evidence depends on them.

This resolves the token-ceiling arithmetic without weakening evidence preservation: membership is
guaranteed, depth is earned.

### OD-4 · Personal-mailbox forensics — DECIDED

Autonomous agents **may** run metadata / ID / timing / structure-only diagnostics without approval.

**Persisting or surfacing any actual personal-mail text** for forensic debugging requires the
owner's **explicit approval, per incident**. Normal transient in-memory retrieval during query
execution is unaffected by this rule.

---

**Assembled:** 2026-08-30, by the Round-1 reconciliation pass over `ARCHITECTURE_DECISION.md`,
`PRODUCT_CONTRACT.md`, `RELEASE_RUBRIC.md` and `EVALUATION_PLAN.md`.
**Status:** this is the **only** open owner list. The four planning documents previously carried
overlapping "For owner decision" sections holding fourteen entries between them; ten were already
settled by the Round-1 repairs and have been closed in place, with the settlement recorded in each
document. What is left is here, and nothing here can be closed by an agent, by a measurement, or by
reading the specs harder.

**How to answer:** a sentence per item is enough. Write it wherever you like and the loop will apply
it; each item lists exactly which documents change under each option, so none of this needs you to
open a 1,900-line architecture document.

**Ordering:** by consequence. **OD-1** and **OD-2** change what MailWeave promises users. **OD-3** is
accepting a limit we cannot engineer away. **OD-4** is a privacy call about your own mailbox.

One of these blocks work: **OD-1 must be answered before the freshness experiment starts**, because
the whole point of writing the number down first is that it cannot be reverse-engineered from the
results. The other three can be answered any time before the release gate, but OD-2 and OD-3 will each
cost a rework round if they arrive late.

---

## OD-1 · How fresh must a search result be before we call it broken?

**The question, plainly.** Gmail's search index does not see a delivered message instantly, and the
reported failures suggest the lag is much worse for messages arriving deep inside a long thread than
for a brand-new one. We are about to measure that lag properly. Before we run the measurement, we need
your line: **how long may a delivered email be un-findable before that counts as a defect we must build
a fix for?** Give one duration, say which setup it applies to (MailWeave itself, as opposed to raw
Gmail), and say whether it is the same for a new message in a new conversation and a reply landing in a
long-running thread.

**Why no measurement and no agent can settle it.** A measurement can tell us what the lag *is*; it
cannot tell us what is *acceptable to a person waiting for an answer*. That is a product promise. It
also has to be written down **before** the probe run: the evaluation plan says in terms that it "does
not set it, and inventing a number here would be exactly the dishonesty the pre-registration discipline
exists to prevent" — a threshold chosen after seeing the data is a threshold chosen to pass.

**Options and what each one costs.**

| Option | What it means | Consequence |
|---|---|---|
| **(a) Tight** — a bound in the low minutes, applied equally to new threads and deep threads | The strongest promise, and the one that treats the deep-thread case as first-class | Most likely to be exceeded by real Gmail, which then **forces us to build a reconciliation path** (re-checking recent mail outside the search index) and verify it before any freshness sentence ships. That is real implementation work inside the loop, and it must not slow the cheap path |
| **(b) Moderate** — a bound of tens of minutes, applied equally across thread depths | A promise most users would accept for email | Fix only gets built if Gmail is materially worse than that. Middle cost, middle promise |
| **(c) No promise** — we publish the measured distribution and promise only that every result says whether it may be stale | Nothing to breach | We may then make **no freshness claim at all** in the README, and MailWeave's honesty rests entirely on the staleness label being present on every response |
| **(d) Looser for deep threads than for new mail** | Formally allowed | **Not recommended, and worth naming as a trap:** deep threads are exactly where the failure MailWeave exists to catch lives. Exempting them would make the number pass by looking away from the problem |

Note that four of the six triggers that force us to build a freshness fix **do not depend on your
number at all**: a message that never surfaces within 72 hours, a statistically significant deep-thread
penalty, any confirmed real false-negative on your own mailbox, and MailWeave being more than a minute
slower than raw Gmail each force work regardless. Choosing (c) does not switch off the safety net; it
only removes the "slower than we promised" trigger.

**Recommendation.** Option **(b)**, one bound applied uniformly across all thread depths, and pick the
figure yourself rather than ratifying one an agent proposed — the pre-registration is only meaningful
if the number is genuinely yours. Reasoning: (a) is honest but likely commits us to building the
reconciliation path on schedule pressure before we know it is needed; (c) is defensible but throws away
the ability to say anything about freshness at all, which is one of the three problems the project
separates and claims individually; (d) undermines the measurement's whole purpose.

**What changes under each option.** All options: the number is written into experiment log 001 before
the probe run, and the rubric's "service level registered before the run" criterion checks the
timestamp, not the value. (a)/(b): the freshness mitigation triggers in `EVALUATION_PLAN.md` §11.2.3
become live against your figure, and the freshness gate reads it. (c): `PRODUCT_CONTRACT.md` C-09's
claim wording and the README's freshness section are narrowed to "we always say when a result may be
stale", and the two lag-based triggers are recorded as not applicable.

---

## OD-2 · When MailWeave finds nothing, how much do we promise about *why*?

**The question, plainly.** When a search comes back empty, MailWeave tells you which part of your
request caused it — "nothing from Amy *after May*; drop the date and there are 12." It works by
re-running the search with one condition removed at a time. We budget six such probes per query. For a
request with more than six conditions we cannot promise we found the right one, because checking every
possibility is unbounded work. So: **do we promise the diagnosis is always correct for the conditions
we actually tested — and say plainly when we could not test them all — or do we keep an absolute
"always correct" promise and only ever test the product on requests with six conditions or fewer?**

**Why no measurement and no agent can settle it.** This is not an engineering gap; it is arithmetic.
Being right about a possibility you never tried is not achievable at any budget short of trying all of
them, and the number of conditions in a user's query has no ceiling. Both honest repairs give something
up: one narrows the promise, the other narrows the test set. Choosing which to give up is a statement
about what MailWeave guarantees, which is yours.

**Options and what each one costs.**

| Option | What it means | Consequence |
|---|---|---|
| **(a) Promise over what we tested, and disclose the rest** | "Correct 100 % of the time about the conditions we probed"; when the budget runs out the response says so, lists what it tried, lists what it did not, and offers a way to continue | Keeps hard queries in the test suite. The guarantee becomes conditional, but the condition is **visible in the response** rather than implied. Adds one number to register before the gate: how often "we could not check everything" is allowed to happen |
| **(b) Keep the absolute promise, cap the tests at six conditions** | The promise stays simple and unconditional | The evaluation stops exercising the only case where the promise can fail. The risk does not disappear — it moves out of the test suite and into your mailbox. Real queries with seven conditions get behaviour nobody measured |
| **(c) Raise the probe budget until it always fits** | Try every condition, however many | Blows the cost and latency ceilings on exactly the adversarial queries that trigger it, and collides with the "simple queries stay cheap" criterion. Not recommended |

**Recommendation.** Option **(a)**, and keep the long-condition cases in the test suite rather than
capping them. Reasoning: this is the project's own core discipline applied to itself — a partial answer
that says it is partial and offers the path onward is exactly the behaviour MailWeave exists to
provide, and the machinery to report it is already built (there is a distinct "incomplete diagnosis"
state, separate from "no single condition explains it"). Option (b) would let the criterion pass by not
looking, which the anti-gaming rules treat as a defect in its own right.

**What changes under each option.** (a): the rubric's empty-result criterion is re-scoped to attempted
probes plus a registered ceiling on the incomplete rate; the evaluation plan registers that ceiling at
the substrate gate. (b): the rubric criterion is untouched and `EVALUATION_PLAN.md` §4's constructed
relaxation cases are capped at six conditions, recorded as a deliberate coverage limit. (c): the
architecture's probe budget and the cost ceilings both change, and the "cheap queries stay cheap"
criterion has to be re-derived. Until you answer, **the criterion stands at 100 % unchanged** — nothing
has been softened in the meantime.

---

## OD-3 · Accepting that the "nothing gets hidden" floor guarantees *presence*, not *full text*

**Read this one as an acceptance, not a choice.** There is a real limit here that no amount of
engineering removes, and the honest thing is to tell you rather than let a later reviewer discover it.

**What we promised.** When MailWeave answers from a conversation, the chain of replies leading to the
answer is always included — so a later message that *reverses* the decision cannot be silently dropped
while the earlier, more confident-looking messages are shown.

**What is actually possible.** The response has a size ceiling, because the calling agent's context
does. A routine large thread — 40 messages, six of them matching — needs roughly 11,200 tokens to show
every hit and the whole reply chain at readable length, against a 9,000-token ceiling (raised to 12,000
only to protect the chain). The arithmetic does not close. So the guarantee has been split honestly:
**membership is absolute** — every message in that chain is always in the response, never a bare count
— while **depth degrades** in declared steps: full cleaned text, then a shortened version, then a
one-line snippet, each labelled in place with a way to fetch the rest. A reversing reply is usually
short, so at snippet depth the reversal is often still readable. "Often" is the honest word.

**Why this needs you.** It narrows a sentence the product previously stated absolutely. And if the
measurement says snippet-depth presence is not enough, the fix is a trade-off nobody but you should
pick.

**What we will measure.** A purpose-built adversarial family: threads whose highest-scoring messages
support the wrong answer and whose quiet later reply reverses it, run at every degradation depth,
against the simple fixed-window baseline. If the floor at the depth the budget actually produces does
not beat that baseline, the floor is not doing its job at that depth.

**Pre-authorise one branch, so the loop does not stall at the gate:**

| Branch | Consequence |
|---|---|
| **(i) Show fewer matched messages at full text, so the reply chain keeps its depth** | Nothing is hidden; you see less matched content per response and follow up more often. Costs rounds, not truth |
| **(ii) Raise the response ceiling further** | Only viable if the client's real limit allows it — being truncated by the host instead of by us is a defect we forbid elsewhere. We will know from a preflight measurement |
| **(iii) Accept the narrower claim** | We say the chain is always present and navigable, and stop claiming the agent will necessarily notice the reversal |

**Recommendation.** Pre-authorise **(i)**, then **(ii)** if the measured client limit allows it, and
treat **(iii)** as the last resort. Reasoning: (i) preserves the invariant that actually distinguishes
MailWeave — nothing matched is ever silently absent — and pays for it in follow-up rounds, which is
recoverable. (iii) spends the product's headline honesty claim, which is not.

**What changes under each branch.** (i): the architecture's disclosure budgets and the "context
efficiency" criterion's expected numbers. (ii): the two response ceilings and the self-truncation
criterion, both bound to the preflight measurement. (iii): `PRODUCT_CONTRACT.md` C-06's floor sentence,
the architecture's tension record for this exact conflict, and the README's claim.

---

## OD-4 · Who may look at your real mail when something breaks?

**The question, plainly.** Development runs against your real mailbox from day one, so real failures
will need diagnosing. The debugging tool re-fetches the specific messages by ID **into memory** and
prints them to a terminal — nothing is written to disk, no bodies land in logs or traces. The remaining
question is not how it works but **who is allowed to run it: an AI implementer agent in the middle of a
debugging round, or only you?**

**Why no measurement and no agent can settle it.** It is your correspondence. The mechanism question is
closed — the at-rest buffer that used to exist has been deleted, and a redaction canary test runs
continuously — so what is left is purely a judgement about exposure, and an agent deciding its own
access to your mailbox is precisely the decision an agent should not make.

**Options and what each one costs.**

| Option | What it means | Consequence |
|---|---|---|
| **(a) You only** | Agents work from IDs, timings, routing decisions and metrics; when they need to see content, they ask you, or reproduce the failure on the separate seeded account | Strongest privacy. Slower loops, and a class of real-mail bugs — odd encodings, unusual formatting, real wording — takes longer to pin down |
| **(b) Implementer agents may run it freely** | Fastest diagnosis | Real message text enters an agent's context routinely. That is the exposure the whole redaction design exists to minimise, and it is not recoverable once it happens |
| **(c) Per-incident, narrow, logged** | An agent may run it only against message IDs already present in a failing trace, only for that incident, with each run recorded and visible to you afterwards | Most of (b)'s speed, with the blast radius bounded to messages a failure already implicated |

**Recommendation.** Default to **(a)**, with **(c)** as an exception you grant per incident. Reasoning:
the loop already has a designed alternative — reproduce on the seeded account, keep sanitized fixtures
from real failures — so the cost of (a) is round latency, which is recoverable, while the cost of a bad
(b) is not. (c) is the right shape for the exception because it inherits the bound from the failure
itself rather than from an agent's judgement.

**What changes under each option.** (a): the security criteria's verification wording says the tool is
owner-invoked, and the evaluation plan's forensic ladder names you as the operator. (c): the same, plus
an audit-record obligation on each run and a per-incident approval step. (b): the architecture's
strictest-profile-governs-debugging resolution is re-opened, and the security review's stricter default
is formally overridden — which should be recorded as your decision, not absorbed quietly.

---

## Appendix — what was closed, so you can see nothing was buried

These ten were open across the four documents this morning and are **not** on your list. Each is closed
in place, with the location recorded in that document's repair log.

| Was | Now |
|---|---|
| What "this thread has N messages" is allowed to mean | **Resolved.** It means what Gmail reported at fetch time — the only honest claim, since Gmail exposes no independent count. Agreement with the seeded ground truth is now measured as a property of the *instrument*, with a bound that can fail the gate |
| Whether a simpler fixed-window disclosure policy may ship if it wins the comparison | **Resolved.** It may not: the comparison is published either way, a loss is a tuning input, and the fixed window stays a baseline. This is what your scope correction already said |
| Which retrieved messages must appear in the response (the "hit set") | **Resolved.** One definition now appears word-for-word in the contract, the rubric and the architecture, with the shortlist size published in advance so it cannot be shrunk to make the test pass |
| Whether a capped-away message still has to be fully represented | **Resolved.** It is disclosed as an explicit withheld record with a working way to fetch it — which the contract's own repaired wording already required |
| Egress: "connects only to Gmail" | **Resolved.** Two hosts at runtime (Gmail plus token refresh) and nothing else; model weights are fetched at setup only, and the runtime is forced offline and verified with the model host blocked |
| Whether extra viewing depths must be dropped or measured | **Resolved** in the measure-don't-remove direction; dropping a shipped level would be the scope reduction your correction forbids |
| Nobody owned the documentation-accuracy criteria | **Resolved.** A documentation-and-claims reviewer domain has been added to the loop definition |
| The content-processing components were never selected | **Resolved.** Parser, quote/signature stripper and encoding pipeline are now named with their licences, and tested with the network switched off |
| The "cheap queries stay cheap" bar counted HTTP requests, which batching makes meaningless | **Corrected, then deferred to measurement.** It now also binds the count that costs money, with the value registered at the first gate rather than invented |
| The recency shortcut shipped unmeasured | **Resolved.** It is now explicitly experimental, with a named experiment arm that measures freshness with it switched off, so it cannot flatter itself |

---

## OD-5 — mailbox provenance is a field, not a mention (2026-09-03)

**Question put to the owner.** `MessageRow` has no field saying a message came from SPAM or TRASH.
R-RETR's round-17 verdict, which the orchestrator accepted and escalated: keeping L3's published
`in:anywhere` broadening step is right — it fires only after nothing was found — but **declaring the
probe is not declaring the row.** A caller saw `role: matched` and `outcome: answered` with only the
substring `in:anywhere` buried inside a reason string to tell them a row came from spam.

**Decision — binding.**

1. **Every `MessageRow` carries machine-readable mailbox provenance**, derived from the message's
   **actual labels**, not inferred from the query that found it and not a prose mention. Spam and
   trash results are explicitly identified as such, in a field a caller can branch on.
2. **L3's `in:anywhere` broadening is kept, and only when the user specified no scope.** A query
   that names a scope — positively or negatively — never has that scope widened.
3. **An explicit scope is preserved across every probe.** `-in:spam` must never search spam. This is
   not a per-operator rule: a negated scope operator *is* the region declaration, and the invariant's
   asymmetry clause must be derived from what an operator does, so it holds for scope operators
   nobody has added yet.
4. **A negated phrase remains an exclusion.** `-"phrase"` is never searched *for*.
5. **L0 uses the corrected `enforced` semantics** — derived where `enforced` is computed, not
   per rung, so a rung added later inherits it.
6. **Regression and mutation tests are required**, failing when any of the above is replanted,
   including an **operator-family sweep** rather than per-operator cases.

**Why this is recorded here rather than as an amendment alone.** It is a schema change to a wire
model, and `AGENT_LOOP.md` §8 puts those with the owner. Amendment **A9** carries the mechanics; this
entry carries the authority.

**Standing consequence.** Point 1 makes the round-17 open question moot rather than deferred: no
future round may answer "the probe was declared in `scan_scope`" to a question about what a *row*
discloses.

---

## OD-6 — build order changes; scope does not (2026-09-04)

**Decision, verbatim in effect.** Proceed working-product-first. **This changes the order, not the
final scope.** After round 19's independent review, prioritise **WS-05, WS-06, WS-10, WS-11,
WS-15**, and reach a *usable milestone* before returning to the remaining workstreams.

### The usable milestone is complete only when all six hold

1. The MCP server **starts through a documented command**.
2. It **connects to an authorised Gmail account**.
3. **Claude can invoke it** and successfully search for and retrieve a **real** email or thread.
4. Results carry **stable handles**, **truthful scope**, and **Spam/Trash provenance**.
5. There is a **reproducible end-to-end smoke test** and a **written demonstration procedure**.
6. The milestone is **committed and independently reviewed**.

### What may not be used to declare it

**Unit tests, mocks, or individual components are not evidence for this milestone.** Every prior
round has been established against `httpx.MockTransport`; that is the right way to build and it is
not the thing being claimed here. Criteria 2 and 3 require a live account and real mail.

### The counter-rule, equally binding

**Audit-only rounds may not indefinitely postpone integration.** A round that produces no
integration progress needs a *critical correctness or safety defect* to justify itself, named as
such. Absent that, integration proceeds. This is the counterweight to `AGENT_LOOP.md` §5a: §5a stops
the loop chasing unreachable defects, OD-6 stops it chasing reachable-but-minor ones instead of
shipping.

### After the milestone

Continue **automatically** through every remaining workstream, the full evaluation harness, all 110
mandatory criteria, documentation, and the release gate. The ledger and the rigorous reviews are
maintained throughout.

**The usable milestone is not permission to reduce the specification or to stop the complete
build.** It is a checkpoint inside it.

### The one thing that genuinely blocks criteria 2 and 3

OAuth consent status is **unknown** and has been since the credential-permissions fix. `uv run
mailweave auth login --client mailweave-server-oauth.json` runs natively on the owner's Mac, whose
home directory this session cannot see, so the empty token-store check is *inconclusive*, not a
failure. Everything up to that point can be built without it; criteria 2, 3 and 4-on-real-mail
cannot be met without it. This is named here so no future round quietly substitutes a mock and calls
the milestone met.

---

## OD-7 — a spending checkpoint after the usable milestone (2026-09-06)

**Decision, verbatim in effect.** Resume from `RESUME.md` at `e0bdba6`. Preserve all existing work
and the full remaining specification. **One instruction changes: do not automatically continue
through the entire remaining build after the usable milestone.** This is a spending checkpoint, not
a cancellation and not a reduction in scope.

### What is in scope up to the checkpoint

1. Finish Round 25's independent reviews (R-DISC on Parts 1, 3, 4; R-MCP on Parts 2, 5, 6).
2. Address **named defects that prevent safe and truthful end-to-end use**. Other findings stay
   tracked in the ledger, not fixed on the way.
3. **Demonstrate Claude retrieving real mail through MailWeave**, against the owner's authorised
   account. **The known large-response / host-truncation issue is included in those checks** — the
   token ceiling does not bound the host's 25,000-character cap, and a 60-message reply rendered at
   68,363 characters in round 25.
4. A **small, fair comparison** against the native Gmail connector, using its existing search and
   full-thread tools *properly*. Questions agreed with the owner first, covering ordinary cases and
   difficult conversations. Compare answer correctness and supporting evidence, plus calls, tokens
   and latency where measurable. **An early decision-making exercise, not a release benchmark and
   not a marketing claim.** WS-16's evaluation framework is **not** built to conduct it.
5. **Before the comparison: a bounded estimate of the work involved.** If completing the checkpoint
   requires substantial additional work, explain what and why before expanding it.

### At the checkpoint

Save and commit the exact pickup state, the outstanding findings, and the full remaining plan. Report
what works, what remains unreliable, and whether the comparison supports further investment. **Wait
for the owner's approval before the remaining large build** (WS-08/09/12/13/14/16/17/18, the
measurement campaign, the release gate).

### Two constraints on the orchestrator

* **Tell the owner exactly what non-secret Gmail login status is needed. Never request tokens or
  secrets in chat.**
* The owner is separately testing the native Claude Gmail connector with Codex, without MailWeave.
  **Do not duplicate that experiment.** The owner will share observations before deciding on the next
  large build phase.

### What this does not change

OD-1..OD-6 remain binding except OD-6's "continue automatically" clause, which OD-7 supersedes.
The 110 mandatory criteria, `AGENT_LOOP.md` §5a, amendments A1–A11, and the complete product
specification are untouched.
