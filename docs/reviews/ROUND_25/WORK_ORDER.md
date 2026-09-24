# ROUND 25 — the thesis must be a thesis, and the surface must be safe

**Issued by:** orchestrator, 2026-09-05
**Protocol:** `docs/AGENT_LOOP.md` §5, gate per §5a **and OD-6's urgency rule**.
A fix round on WS-11 and WS-15, before the live milestone.

## Read this first

All five OD-6 workstreams are built and MailWeave is a server. Two reviewers then did what OD-6 said
would happen to any claim resting on components: they connected the pieces and found what only
connection reveals. **Both said do not declare the milestone.** They are right, and this round is
why the order was worth it.

The two findings that define this round:

**The thesis is currently ±2 in disguise.** R-DISC ran six materially different queries against one
thread and got **0 of 15 differing pairs** — identical fill, reason and score — because the
admitting component reads the subject and Gmail sends one subject per thread. The E4 top class is
Baseline F's ±2 window **position for position**. Amendment **A11** states the rule that fixes it.

**A sender can forge the connector's voice.** R-MCP found `split_fenced` closes on the literal `>>>`
rather than the nonce. A body line ending in `>>>` puts forged withheld records, a fabricated source
with `stated_total: 400`, a fabricated row and a fabricated affordance into the response as if
MailWeave said them. That is a prompt-injection hole in the one place the fence exists to prevent
it. The implementer's own forgery test planted a body with no `>>>`.

## Part 1 — the thesis (R-DISC-017, 018; amendment A11)

Read A11. Then:

* Make the admitting predicates **message-discriminating**. R-DISC offered two routes; A11 chooses
  the principled one — a component that fires identically on every candidate of a thread *ranks but
  does not admit* on that thread. That is A.9(3)'s existing `POSITION_ADJACENCY` rule generalised
  from the component to its behaviour on the thread. Not a new weight.
* **A candidate's rank may not be decided by query-independent components alone** — the ordering
  half round 23 left out while describing it as the fix.
* **The three-line test round 23 was missing**: a thread where every candidate fires the same
  anchored component; assert the E4 ranking is **not** the ±2 window.
* **The DISC-01 test as the rubric states it**: ≥ 5 queries over *one* thread whose subject carries
  all their terms; assert the included sets differ. Round 23's fairness tests compared across
  different threads, which is why they passed.

Do not fix this by adding a component that happens to differ on the fixture. It must be explainable
for a query nobody has written, and the reviewer will build one.

## Part 2 — the fence (R-MCP-002, safety)

`split_fenced` closes on the **nonce**, never on a literal. Then attack your own fix: a body
containing the nonce string itself, a body containing the closing sequence with different
whitespace, unicode confusables for `>`, a body that *is* a valid fenced block. The fence is
per-response and unguessable (WS-14 will build the rest); this round makes the closing side
unforgeable. The forgery test plants a body that **does** contain the closer.

## Part 3 — what the round found is bigger than it measured (R-DISC-019, 022; R-MCP-003)

Three findings are one defect from three sides: **the estimate is not the wire.**

* **R-DISC-019**: `snippet → stub` makes the response *larger* — a stub is charged 40 tokens, a
  snippet only its ≤ ~36-token text. A 9,300-token layout became 27,270 on the shipped path. A11's
  second rule: a row is charged its structural cost at every depth, so the ladder is monotone in
  cost as well as depth.
* **R-DISC-022**: the ceiling measures 1/20th to 1/85th of the actual response. A five-message reply
  renders 24,198 chars — 97 % of the 25,000-char host cap — while declaring 13 % of budget spent.
  600 rows render at 28× the cap.
* **R-MCP-003**: following the server's own collapsed-run affordance returns 33,478 tokens /
  255 KB, **272 % over** the declared 9,000 ceiling, with `truncated_by: null`. `_measure`
  re-implements the production estimate while claiming to measure the wire.

R-DISC verified `layout.cost() == measure_tokens(envelope)` on five shipped shapes — that property
is good and **must survive your fix**. The right change alters both measures in one place. Then
the self-truncation test measures the *rendered wire form*, not an estimate of it.

## Part 4 — the floor's own test is `digest(x) == digest(x)` (R-DISC-021)

`floor_of` skips a member that is itself a hit, so a hit's hit-parent or hit-child is outside
`floor_ids` and step 8 removes it. Reproduced: a disclosed hit whose direct child is withheld.
**Every floor test in round 23 checks the payload against `floor_of`'s own output** — a
self-comparison, in the project's biggest claim. Fix the floor, and write the floor's oracle out by
hand for at least one thread shape so the test can disagree with the implementation.

## Part 5 — the surface cannot tell "declined" from "broke" (R-MCP-001, 006, 007, 009)

* **R-MCP-001**: `call` catches three exception types and **every `GmailFault` escapes** as
  `-32603 Internal server error`. Four D.11 codes — `auth_reauth_required`, `upstream_unavailable`,
  `upstream_rate_limited`, `partial_source_failure` — can never reach the partition. The partition
  test drove `declined()` against the table and never a real producer. Fix is small; the code is
  already on the exception. **Then drive the partition test through a real producer.**
* **R-MCP-009**: the token is exchanged **once for the process's life**. After ~1 h every call fails
  permanently with an opaque protocol error, no recovery, no instruction. `StoredTokenProvider` needs
  its expiry check and single-flight refresh — WS-15's own implementer named this gap.
* **R-MCP-006**: a revoked refresh token, a narrowed scope and a 401 all collapse into
  `auth_profile_underivable`, so GMAIL-06's re-auth instruction never appears at startup. Four
  distinct causes, four distinct messages.
* **R-MCP-007**: `mailweave serve` **tracebacks** with `FileNotFoundError` on the exact condition
  criterion 1 is about. It must refuse, with the reason and the next step, exit 1 — it already does
  for a missing config; make the missing-token case behave the same.

## Part 6 — SETUP as a stranger reads it (R-MCP-008), and the rest

R-MCP followed `docs/SETUP.md` as a stranger and was stopped at step 4: it omits `chmod 600` on the
OAuth client file, `doctor` exits 0, and the printed remedy points at the wrong place. Fix the
document **and** make `doctor` diagnose the permission. Then R-DISC-020 (`DisclosureLadderExhausted`
escaping as unhandled — ~700 matching messages kills the tool call; it must become a declared
in-band result), R-DISC-023..030 and R-MCP-004, 005, 010..015 as filed, where the fix is genuine.

## What survived, and must keep surviving

R-DISC: the driver-level floor gates with real plants (its own plant went red five ways); the single
`Selector` making DISC-02's equal-budget property structural; `layout.cost() == measure_tokens`.
R-MCP: the serve loop under every planted fault; 83 minted affordances all accepted; `force_rungs`
monotone over 180 combinations; metadata byte-identical across three processes; no Sampling four
ways; no write path; a handle redeemed across a real process boundary; `stdio_server()` driven as a
real subprocess. **Your fixes may not regress any of these**, and the reviewer will check.

## Constraints

OD-1..OD-6; I-1..I-4; A1..A11 (A1 not yours). No Sampling, no LLM call, no embedding. No network in
tests. No real or realistic personal mail text. Do not touch retry/backoff. Do not mark any rubric
criterion PASS; do not restore ROUTE-01; do not edit `FINDINGS_LEDGER.md` or `RUBRIC_TRANSITIONS.md`.
Do not tune against any reviewer's probe set (`/tmp/rretr15..22/`, `/tmp/rdisc23/`, `/tmp/rmcp24/`).

Gates clean: ruff, ruff format, mypy --strict, `python -m tools.guards`,
`pytest -q -m "not network"` (**2,615** currently pass). Rubric stays **6 PASS / 0 FAIL / 0 BLOCKER
/ 107 NOT TESTED**.

Reintroduction: every anchor matched, every file changed, all three packages resolving into your
scratch tree (whole tree incl. `docs/`), every `caught_by` citation catching individually. After
R-DISC-021: **no test in your diff may compare a derivation with itself.**

## Deliverable

`docs/reviews/ROUND_25/IMPLEMENTER.md`: per part, what changed, what each test establishes, what you
could **not** establish. Then: the DISC-01 result on your own ≥ 5-query single-thread set, with the
numbers; proof the E4 ranking is not the ±2 window on a shared-subject thread; the fence attacked
your own way; the wire-versus-estimate relationship stated once and measured on the rendered form;
your answer to "have I trusted a peer?"; and the honest OD-6 table — which of the six criteria your
work touches and what remains for the live half.

## Gating reviewers

`R-DISC` (Parts 1, 3, 4) and `R-MCP` (Parts 2, 5, 6), findings by severity **and** urgency.

## Exit condition

Five materially different queries against one thread produce different fills for a reason a
stranger can read. The E4 ranking on a shared-subject thread is not the ±2 window. No mail text can
close the fence. No degradation step makes a response larger, and the declared ceiling bounds the
rendered wire. Every `GmailFault` lands on its side of the partition. A server left running for an
hour still answers. `mailweave serve` refuses, never tracebacks, and SETUP works when a stranger
follows it.
