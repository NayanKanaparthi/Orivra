# ROUND 20 — WS-05: the thread map and structural retrieval

**Issued by:** orchestrator, 2026-09-04
**Protocol:** `docs/AGENT_LOOP.md` §5, gate per §5a **and OD-6's urgency rule**.

## Where this sits

`docs/OWNER_DECISIONS.md` **OD-6** changed the build order: WS-05, WS-06, WS-10, WS-11, WS-15,
then a *usable milestone* — an MCP server Claude can query real Gmail through. **This is the first
of those five.** Read OD-6 before you start, including what may not be used to declare the
milestone met and the counter-rule about audit-only rounds.

Round 19's review closed with *integration should proceed*: six findings, all classified ride-along
rather than blocking, none a critical correctness or safety defect. They are **not yours** this
round unless your own diff touches them.

## What you are building

WS-05 from `docs/IMPLEMENTATION_PLAN.md`, whose row is normative:

* **One `threads.get` per hit-bearing thread**, deduped per query, `max_hit_threads = 12`.
* **JWZ / IMAP-REFERENCES reply-tree reconstruction.** Orphans get
  `linkage: "date-adjacent (no RFC reply headers)"` and **no silent re-parenting** — a guess that
  looks like a fact is the defect this whole project exists to prevent.
* **An address-keyed participant index** distinguishing **authorship from mentions**. Someone
  quoted in a thread is not someone who wrote in it, and a retrieval system that confuses the two
  answers "who decided this?" wrongly.
* **Strict `internalDate` ordering**, with a position on every row (amendment **A3**: 0-based
  indices into chronological order, bounded, raising rather than clamping).
* **L4 sibling / structural expansion** as separate sources, `max_source_threads = 4`.

## What already exists — use it, do not rebuild it

* `mailweave.envelope.disposition.DispositionLedger` — every observed id enters `H`;
  `withheld := H − disclosed` at envelope construction. **You do not do this accounting.** Fifteen
  review rounds went into making a silent drop impossible; read `disposition.py`'s docstring first.
* `mailweave.query` and `mailweave.retrieval` — the parsed query and the L0–L3 ladder.
  `declares_the_search_region` and `KIND_BY_OPERATOR` are the region rule (A9); **scope is
  preserved across every probe**, and anything you compose inherits that.
* `MailboxProvenance` on every `MessageRow`, computed from observed `labelIds` (**OD-5**). Rows you
  add carry it too, including stubs.
* `mailweave.content` — annotates rather than deletes (A7).
* `tests/test_lexical_ladder.py` — the pattern for network-free testing: a whole mailbox behind
  `httpx.MockTransport` with the real client, real URLs, real retry ladder, real egress check.

## Acceptance, from the plan's own column

* Reply-tree fixtures including **broken threading**, **a subject change mid-thread**, and
  **forwards**.
* An **ordering test where the API array order is not `internalDate` order** — Gmail does not
  promise the array is sorted, and code that assumes it will be wrong on exactly the threads that
  matter.
* **Hearsay-versus-authorship discrimination.**
* **Declared-gap assertions**: where the reply tree could not be reconstructed, the response says so.

## The two defects this project keeps producing

Fifteen instances of **"one shape validated, peers trusted"**, and the last five appeared inside
the fix for the previous one. A reply tree has many shapes: broken headers, subject changes,
forwards, orphans, cycles, self-references, duplicate `Message-ID`s. Find what is common to all of
them and test **that**, not a list.

And **a claim wider than the code**: round 18 wrote a correct rule in a docstring over an
implementation that asked a different question. Every claim you make about what the reconstruction
guarantees gets executed.

## Hard constraints

- No LLM call, no embedding. `generative_llm_calls = 0` is CI-enforced.
- No network in tests. **No real or realistic personal mail text** in any fixture.
- Do not mark any rubric criterion PASS; do not restore ROUTE-01; do not edit `FINDINGS_LEDGER.md`
  or `RUBRIC_TRANSITIONS.md`.
- Do not touch retry/backoff constants — open owner decision.
- Do not tune against any reviewer's probe set (`/tmp/rretr15..19/`).
- Gates clean: ruff, ruff format, mypy --strict, `python -m tools.guards`,
  `pytest -q -m "not network"` (2,290 currently pass). Rubric stays **6 PASS / 0 FAIL / 0 BLOCKER /
  107 NOT TESTED**.
- Reintroduction: assert every anchor matched, every file changed, and `mailweave`, `tests` and
  `mailweave_harness` all resolving into your scratch tree — copy the **whole** tree including
  `docs/`.

## Deliverable

`docs/reviews/ROUND_20/IMPLEMENTER.md`: what you built, what each test establishes, what you could
**not** establish. Then:

- what is common to every reply-tree shape, and the test covering the commonality;
- every docstring claim about what reconstruction guarantees, with executed evidence;
- how authorship is distinguished from mention, and the case where you cannot tell;
- anything not reachable from code that exists today — name it and its workstream (§5a), and under
  OD-6 also say whether it would block integration.

Finish with clean output of ruff, ruff format, mypy, guards, pytest and rubric_status.

## Gating reviewer

`R-RETR`, on what this round builds, with findings classified by severity **and** urgency.

## Exit condition

A thread's reply structure is reconstructed or declared unreconstructable, never guessed. Positions
are chronological by `internalDate` regardless of array order. Authorship and mention are
distinguishable. Every message the ladder saw is still accounted for by the ledger.
