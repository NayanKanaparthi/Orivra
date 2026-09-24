# ROUND 11 — WS-02: the Gmail client, OAuth, and the preflight harness

**Issued by:** orchestrator, 2026-08-31
**Protocol:** `docs/AGENT_LOOP.md` §5. Round 10 gated; the foundation phase is complete.

**This round changes character.** Ten rounds hardened components that never touched a network.
This one builds the thing that does. It is the first workstream whose correctness cannot be
fully established without real Gmail, so it is deliberately split: everything buildable without
credentials is built and gated now, and everything needing consent is *prepared* so that the
live phase is one command the owner runs.

## Part 1 — the Gmail client (WS-02)

Build on the `RecordingListTransport` seam the foundation established. The seam exists precisely
so this layer cannot return a bare id list, and that property is not negotiable here.

Endpoints needed now: `users.messages.list`, `users.messages.get`, `users.threads.get`,
`users.history.list`. Nothing else.

| Requirement | |
|---|---|
| Every response that yields ids flows through a sealed observation carrying its `ObservedEndpoint` | Gated |
| Retry, backoff and rate-limit handling, with quota units counted per call | Gated |
| Pagination semantics explicit, including the page budget from the architecture | Gated |
| Errors typed, never bare exceptions crossing the layer | Gated |
| Egress allowlist enforced on every call | Gated |
| No mail text in any log, trace or error message | Gated |

Testable now against a **fake transport** replaying recorded response shapes. Do not invent
response shapes casually — take them from the Gmail API discovery document, and where you guess,
mark it as a preflight question rather than a fact.

## Part 2 — OAuth, up to the consent boundary

Both clients already exist on disk and are gitignored: `mailweave-server-oauth.json`
(`gmail.readonly`, the real mailbox) and `mailweave-harness-oauth.json`
(`https://mail.google.com/`, the seed account only).

Build `mailweave auth login` as a desktop loopback flow, with:

- **Scope verification after consent.** Read back what Google actually granted and fail loudly
  if it differs from what was requested. Do not assume the request was honoured.
- **Account pinning.** The harness credential must be structurally unable to authenticate the
  owner's real mailbox. Check `getProfile().emailAddress` against the expected account before
  any harness operation, and refuse otherwise.
- Token storage using the atomic writer already built, with the correct permissions.
- **No secret in any log, error, or traceback.** This has been checked before; keep it true.

**The owner runs consent themselves, on their own machine.** Design the command so that is one
step and the output tells them plainly what was granted. Do not attempt consent from this
environment.

## Part 3 — the preflight harness (Loop 0), ready but not run

Build the PF-* probes as runnable code that produces a written record, so that the live phase is
execution rather than authoring. From the architecture's preflight list, at minimum:

- quota units actually charged per endpoint, against the documented figures;
- whether `References` and `In-Reply-To` survive `metadataHeaders`;
- the real messages-per-thread ceiling;
- `get_thread` completeness against a known thread (issue #239 says it can truncate, and the
  evaluation plan depends on it as ground truth);
- search-index freshness behaviour, as raw observation only — **no freshness claim**, since OD-1
  requires the full stratified experiment;
- the `Cf` strip question: whether stripping all format characters damages legitimate content in
  real mail. Both R-SEC and the Round 10 implementer flagged this and it needs a real mailbox.

Each probe states what it measures, what design commitment it validates, and **what changes if
it fails**. A probe that cannot fail is not a probe.

## Standing checks carried from the foundation

- **The "one shape validated, peers trusted" cycle has appeared six times**, including inside
  Round 10's own diff. Every new validator in this round gets checked against it before you
  finish, and the check is reported in the handoff whether or not it finds anything.
- Amendment A7 is **not** integrated with disclosure and must not be here; that is WS-11.

## Constraints

OD-1..OD-4 binding. Invariants I-1..I-4. Amendments A1..A7 binding; **A1 is still not yours to
build** — the counting proxy is WS-13/WS-16. No personal mail in fixtures or logs. No fabricated
thresholds. Do not mark any rubric criterion PASS and do not add rows to `RUBRIC_TRANSITIONS.md`
or `FINDINGS_LEDGER.md`. Seven criteria pass; do not regress them. Keep lint, `mypy --strict`,
tests and guards green.

**Do not build retrieval rungs, ranking, escalation policy or the MCP surface.** This is the
client and the probes, nothing above them.

## Gating reviewers

`R-GMAIL` (new domain this round: client correctness against the real API's documented
behaviour, and whether the probes can actually falsify anything), `R-SEC` (OAuth, scopes, account
pinning, token handling, egress), `R-ARCH` (the seam holds, test quality, the standing cycle
check).

## Exit condition

Zero open BLOCKER and zero open HIGH. The client is complete and tested against the fake
transport. `mailweave auth login` is one command with scope verification and account pinning.
Every preflight probe is runnable and states its own falsification condition.
