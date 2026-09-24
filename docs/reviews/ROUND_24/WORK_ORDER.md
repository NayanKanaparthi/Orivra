# ROUND 24 — WS-15: the MCP server surface. The last piece before the milestone.

**Issued by:** orchestrator, 2026-09-05
**Protocol:** `docs/AGENT_LOOP.md` §5, gate per §5a **and OD-6's urgency rule**.
Fifth of OD-6's five workstreams. After this round, MailWeave is a server.

## What this round is for

Everything built since round 15 — the ladder, the thread map, the handles, the policy, the
disclosure — is reachable today only from tests. **Nothing is a server yet.** This round makes it one.
When you finish, `mailweave serve` should start, speak MCP over stdio, and answer a tool call by
running the whole retrieval stack under the disposition ledger.

OD-6's milestone then needs a *live* account to be declared, and that is not this round's to
claim. Your exit is: **the server starts, serves the four tools, and a real MCP client can drive a
search → thread map → get_messages loop against the fake transport end to end.** The live half is
OD-6 criteria 2 and 3, and mocks are explicitly not evidence for them.

## What you are building — `docs/IMPLEMENTATION_PLAN.md` WS-15 row is normative

* **The four compile-time-constant tools of AD §D.1** over **stdio**, each with
  `readOnlyHint: true`. Four, not three and not five; a tool added at runtime is a tool nobody
  reviewed. Metadata is constant across restarts and the test proves it.
* **`structuredContent` mirrored to an agreeing text rendering.** The structured form is what a
  client parses; the text form is what a model reads. They must say the same thing, and a property
  test must show they cannot drift.
* **No Sampling.** MCP spec revision 2026-07-28 deprecated it, and MailWeave's `generative_llm_calls
  = 0` invariant means the server never asks the client's model anything.
* **Argument validation**, including `view: "raw"` → `unsupported_view`, and
  `mode: "metadata"`-only attachments served from `payload.parts`.
* **D.11's closed error vocabulary** with its **in-band / tool-error partition**. A budget refusal
  is an in-band declared result, not a protocol error. An unknown tool is a protocol error, not a
  result. The partition is the contract; get it wrong and a client cannot tell "MailWeave declined"
  from "MailWeave broke".
* **`force_rungs` can only add rungs.** A client may ask for more work, never less.
* `scan.max_pages` and budget arguments **honour the floor clamp** (WS-10's 845).
* **The untrusted-data warning lives in the static tool description**, never in per-result text
  (WS-14 will build the rest of the injection defences; this one belongs to the surface).

## Acceptance, from the plan's own column

* **Spec-revision conformance** against MCP 2026-07-28 — a real client library, not a hand-rolled
  JSON-RPC shim.
* **Structured / text parity** as a property test.
* **Annotation truthfulness**: no tool can write. Prove it by trying.
* **Metadata constancy across restarts.**
* **PF-7**: a real MCP client drives `mailweave_search` → `mailweave_thread_map` →
  `mailweave_get_messages` **with zero host-side truncation** — the response never exceeds the
  ceiling it declared (WS-11's self-truncation before host truncation).

## The `serve` command — OD-6 criterion 1 is "starts through a documented command"

`mailweave serve` (or whatever the CLI already establishes) must start the server with **one
documented invocation**, refuse to start without a valid credential (WS-01's `auth_profile_
underivable` is fatal, never defaulted), and print nothing that is not safe to print — the secret
canary covers you here and you must not weaken it. Write the SETUP fragment that documents it, and
write it for someone who has never seen this repository.

## What exists — use it, do not rebuild it

`mailweave.cli` (extend, do not fork), `mailweave.auth` (WS-01 token store and profile derivation),
`mailweave.gmail.GmailClient`, `DispositionLedger`, `mailweave.query`/`retrieval`/`structure`/
`handles`/`policy`/`disclosure`, `MailboxProvenance` on every row, `mailweave.content`. The
envelope's serialiser is the wire chokepoint (rounds 13–14): `model_dump` re-establishes every
invariant, so a tool result that reaches the client has already been checked. **Do not add a second
serialisation path around it.**

Network-free pattern: `tests/test_lexical_ladder.py` and `tests/test_thread_map_round20.py` stand a
mailbox up behind `httpx.MockTransport`. Your end-to-end test stands the **server** up over that.

`mcp` is not yet a dependency. Add it to `server/pyproject.toml` (**pin an exact version**; 2.1.1
resolves), `uv sync`, and record the pin in the SETUP fragment. The `generative-client` guard must
stay clean — `mcp` is a protocol library, not a model client, and the guard should agree.

## The two defects this project keeps producing

Nineteen instances of **"one shape validated, peers trusted."** Four tools times the in-band/
tool-error partition times structured/text is the shape space; find the commonality and test that.
**A claim wider than the code**: the tool descriptions are the first prose a *user's model* will ever
read about MailWeave. Every sentence in them is a claim; every claim gets executed.

## Constraints

OD-1..OD-6; I-1..I-4; A1..A10 (A1 not yours). **No Sampling, no LLM call, no embedding.** No network
in tests. No real or realistic personal mail text. Do not touch retry/backoff. Do not mark any
rubric criterion PASS; do not restore ROUTE-01; do not edit `FINDINGS_LEDGER.md` or
`RUBRIC_TRANSITIONS.md`. Do not tune against any reviewer's probe set (`/tmp/rretr15..23/`).

**Do not claim OD-6's milestone.** Your report says what the fake-transport loop established and
names criteria 2, 3 and the live half of 4 as not established here.

Gates clean: ruff, ruff format, mypy --strict, `python -m tools.guards`,
`pytest -q -m "not network"` (**2,557** currently pass). Rubric stays **6 PASS / 0 FAIL / 0 BLOCKER
/ 107 NOT TESTED**.

Reintroduction: every anchor matched, every file changed, all three packages resolving into your
scratch tree (whole tree incl. `docs/`), every `caught_by` citation catching individually.

## Deliverable

`docs/reviews/ROUND_24/IMPLEMENTER.md`: what you built, what each test establishes, what you could
**not** establish. Then: the commonality across the tool surface and the test covering it, with
matrix reach shown; the in-band / tool-error partition stated once and the test that each error
lands on its side; the exact `serve` invocation and the SETUP fragment; every claim in the four tool
descriptions with its executed evidence; your answer to "have I trusted a peer?"; and the honest
statement of which OD-6 criteria remain unestablished and why.

## Gating reviewer

`R-MCP` — the protocol domain, which has never run — with findings by severity **and** urgency.

## Exit condition

`mailweave serve` starts through one documented command and refuses without a valid credential. A
real MCP client lists exactly four read-only tools, drives search → map → get_messages end to end
against the fake transport, and every result's structured and text forms agree. No response exceeds
its declared ceiling. The server never samples.
