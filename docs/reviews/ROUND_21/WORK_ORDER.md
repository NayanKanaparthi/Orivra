# ROUND 21 — WS-06 handles, and the four things L4 says that are not true

**Issued by:** orchestrator, 2026-09-04
**Protocol:** `docs/AGENT_LOOP.md` §5, gate per §5a **and OD-6's urgency rule**.
Second of OD-6's five workstreams to the usable milestone.

## Read the shape of this round before the parts

WS-05's reply tree **cannot be made to guess** — R-RETR attacked it over 3,000 generated threads,
13 hand-built pathologies and all 24 array permutations, and no message was ever attached to a
parent its own headers do not name. That is settled and you are not re-opening it.

**Every over-claim it found is one level out**, in what `Link.evidence` carries and what `assemble`
does with it. Those are Part 0. They are honesty defects — a response stating something the
evidence does not support — which is the class this whole project exists to prevent, and they sit
directly under the handles you are about to build.

## Part 0 — the carry-over, and it comes first because handles depend on it

**R-RETR-051 (MEDIUM) is binding on your design.** The mention scanner is handed the
quote-stripped `default_view`, so addresses in quoted and forwarded blocks are invisible *and*
`mentions_not_scanned` reports the row as scanned. The participant index therefore becomes a
function of **which row the query matched**, not of the thread.

R-RETR's one-sentence instruction to you: **do not put `Source.participants` inside
`mapping_digest` until R-RETR-051 is fixed** — two redemptions at different disclosure depths would
otherwise produce `handle_stale` for a thread nothing changed in. Fix 051, or keep participants out
of the digest and say which you did and why.

**R-RETR-049 (MEDIUM).** L4 chases the **leftmost** `References` entry — the thread root — not the
nearest ancestor its own module's right-to-left rule names, and then discloses what it recovered as
*"reply parent of `<child>`"*. The real parent is never probed. **No test pins the field**: the
reviewer ran the whole suite with it set two different ways and got zero failures both times. Fix
the claim and the traversal, and pin the field.

**R-RETR-050 (MEDIUM).** One `Message-ID` carried by messages in two different threads yields **two
rows both disclosed as the parent of one child**. The reply tree already refuses exactly this
ambiguity *inside* a thread; the cross-thread case walks around that refusal.

**R-RETR-052 (MEDIUM).** A truncated snippet mints an address that exists in no message
(`cai@team.exampl`) and reports it as hearsay. An address that was never in the mailbox must not
reach a participant index.

**R-RETR-054 — the D.4a ruling, decided.** The narrow reading **stands**; the shipped
implementation of it does not. `can_be_a_parent` never leaves `reply_tree.py`, so on the wire a
`Message-ID`-less message is byte-identical to an ordinary reply while its own well-formed child
reports *"named parent is not in this thread"*. **Carry the fact onto `MessageRow`. Do not reverse
the linkage.**

R-RETR-053, 055, 056, 057 as filed — take them where the fix is genuine.

## Part 1 — WS-06: handles and staleness

From `docs/IMPLEMENTATION_PLAN.md`, whose WS-06 row is normative:

* `map_id` = base64url payload + **HMAC** over `{v, key_epoch, account_hash, thread_ids[],
  fetched_at, history_id, mapping_digest, ttl}`.
* Redemption order, and the order is the point: **verify → independent `history.list` liveness
  probe → fetch → digest recompute**. A handle that verifies its own cached copy is a tautology,
  not a liveness check.
* Error classes, each distinct and none collapsed into another: `handle_invalid`,
  `handle_key_rotated`, `handle_expired`, `handle_stale`, `handle_stale_unverifiable`.
* The LRU keyed `(thread_id, history_id_at_fetch)`, 60 s TTL, 64 entries, eviction on staleness.
* **`fetched_at` is never restamped.** `verified_at` is added on LRU service. A handle that
  refreshes its own age is a handle that cannot expire.

**PF-15 is the acceptance test and it has two arms**: mutate-then-redeem, executed **cache-cold and
cache-warm as two separate cases**. The warm case must label its digest check `cache_tautology` in
the trace, because a warm digest recompute over a cached copy proves nothing about the mailbox and
saying otherwise would be the exact defect Part 0 is about.

Also: restart-with-outstanding-handle keeps handles valid; deliberate key rotation yields
`handle_key_rotated`, **not** `handle_expired`.

## What exists — use it, do not rebuild it

`DispositionLedger` (you do not do the accounting), `mailweave.query` + `mailweave.retrieval`
(scope preserved across every probe, A9), `MailboxProvenance` on every row including stubs (OD-5),
`mailweave.structure` (WS-05's map), `mailweave.content` (A7), and
`tests/test_lexical_ladder.py` / `tests/test_thread_map_round20.py` for the network-free pattern.

## The two defects this project keeps producing

Sixteen instances of **"one shape validated, peers trusted."** Five error classes and two cache
states is seven shapes; find what is common to them and test that. And **a claim wider than the
code** — R-RETR-049 is one, and `cache_tautology` exists precisely so the warm path cannot become
another.

## Constraints

OD-1..OD-6; I-1..I-4; A1..A9 (A1 not yours). No LLM call, no embedding. No network in tests. No
real or realistic personal mail text. Do not touch retry/backoff. Do not mark any rubric criterion
PASS; do not restore ROUTE-01; do not edit `FINDINGS_LEDGER.md` or `RUBRIC_TRANSITIONS.md`. Do not
tune against any reviewer's probe set (`/tmp/rretr15..20/`).

**The HMAC key is a secret**: `server/src/mailweave/validation.py`'s `SecretBearingModel` and the
reflection-based canary in `tests/fixtures/secret_models.py` exist for exactly this, and a new
secret-bearing model is covered by that canary the moment it exists. Do not weaken it.

Gates clean: ruff, ruff format, mypy --strict, `python -m tools.guards`,
`pytest -q -m "not network"` (2,369 currently pass). Rubric stays **6 PASS / 0 FAIL / 0 BLOCKER /
107 NOT TESTED**.

Reintroduction: assert every anchor matched, every file changed, and `mailweave`, `tests` and
`mailweave_harness` all resolving into your scratch tree — copy the **whole** tree including `docs/`.

## Deliverable

`docs/reviews/ROUND_21/IMPLEMENTER.md`: per part, what changed, what each test establishes, what
you could **not** establish. Then: what is common to the seven handle shapes and the test covering
it; whether you fixed R-RETR-051 or kept participants out of the digest, and why; every docstring
claim about what a handle guarantees, with executed evidence; your answer to "have I trusted a
peer?"; and anything unreachable, with its workstream and whether it blocks integration.

Finish with clean gate output.

## Gating reviewer

`R-RETR`, findings classified by severity **and** urgency.

## Exit condition

A handle proves the mailbox has not changed, or says which of the five ways it could not. The warm
path never claims the cold path's guarantee. No participant, parent, or address reaches the wire
that the observed messages do not support.
