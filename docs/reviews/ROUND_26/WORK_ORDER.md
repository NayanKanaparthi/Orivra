# ROUND 26 — the eight things between here and a truthful live demonstration

**Issued by:** orchestrator, 2026-09-06
**Protocol:** `docs/AGENT_LOOP.md` §5, gate per §5a, scope per **OD-7**.

## Scope is closed. Read OD-7 before anything.

The owner set a spending checkpoint. This round fixes **exactly the eight findings** both round-25
reviewers marked *fix before demo* — the ones that prevent safe or truthful end-to-end use — and
nothing else. Twelve other findings from the same reviews are real and stay **tracked**. If you find
something new, file it in your report and leave it; do not fix it here unless it makes one of the
eight impossible to fix honestly. Every fix here must be the small one the reviewer scoped.

## Part 1 — the thesis, undone by two characters (R-DISC-031, R-DISC-034)

Gmail sends `Subject: S` on a thread root and `Re: S` on every reply. `content_tokens` keeps `re` as
a content token, so `message_discriminating_facts` classifies the subject — the very fact A11 was
written about — as message-discriminating, and it admits again. R-DISC drove five queries end to end
on the shape Gmail actually sends: **0 of 10** differing included sets, protected top-10 = the ten
earliest, every time. The round-25 fixture that produced 15/15 names the `Re:` prefix in prose and
omits it from the data.

Fix: the reply prefix is not content. Then R-DISC-034 — `hit_ranks` lacks `rank`'s all-or-none
sweep, so when the subject collapses to uniform it reverts to oldest-K. Give it the same sweep.

**The test that was missing**: the round-25 DISC-01 test re-run on a fixture whose root carries
`S` and whose replies carry `Re: S`. Five queries, and the sets must differ.

## Part 2 — the owner's named item: the host cap (R-DISC-032, R-DISC-033, R-MCP-020, R-MCP-021)

Four findings, one defect, seen from both sides.

* **R-DISC-033**: a 12-message thread of ~110-word messages renders a 25,358-character
  `CallToolResult` against the host's 25,000-character cap while declaring `truncated_by: null`,
  `partial: false`, `withheld: []`, `included: 12 of 12`. **That is issue #296's shape, produced by
  MailWeave.** R-MCP crosses it at seven messages on its own fixture.
* **R-MCP-021**: neither the server nor the SDK truncates — byte-identical in-process and at the
  client — so the cut happens above the SDK where nothing can declare it. **No character measure
  exists anywhere in `surface/`.** `grep -rl maxResultSizeChars server/src` returns nothing.
* **R-DISC-032**: underneath both, `measure_tokens` charges **nothing** for `Source.participants`,
  which is 82 % of the rendered response. Round 25's headline property — the estimate is an upper
  bound on the wire — is **false on execution** at 25+ distinct senders, worst measured 11.5×. The
  test certifying it varied size across six values with one sender at every size.
* **R-MCP-020**: three tool descriptions and `SETUP.md` §6 tell the model *"the host never has to
  truncate it"*, on evidence that measures tokens. That sentence is currently false, and it is the
  first thing a user's model reads.

Fix, as both reviewers scoped it: a **character measure on the rendered `CallToolResult`**, applied
as a ceiling at the surface, with self-truncation before the host's cap and a declared
`truncated_by` when it fires — so the response never crosses 25,000 characters without saying so.
Charge `Source.participants` in `measure_tokens`. Correct the three descriptions and SETUP §6 to say
what is now true. Keep `layout.cost() == measure_tokens(envelope)` — R-DISC verified it on five
shapes and it must survive.

**The test**: a thread that renders past 25,000 characters comes back under it with `truncated_by`
naming the cap, `partial: true`, and the cut rows as withheld records with affordances. Measure the
*rendered* form, not an estimate of it.

## Part 3 — the fence and the filename (R-MCP-016, safety)

The fence held 22 attack shapes and the nonce is unguessable. Then a **sender-chosen attachment
filename** containing one `\n` walks around it: four attacker lines reach the residue, forging a
withheld record, a source claiming `stated_total: 400`, an affordance MailWeave never offered — and
re-attributing a real message body to an invented id. `strip_invisible_characters` removes Cf, not
Cc. **`is_one_line` already exists** (used by `ReasonScalar`, imported by `wire.py`) and is not
applied to the one model whose fields a sender chooses.

Apply it there. Then sweep: **every wire field a sender can influence** gets the same bound. Name
them in your report. This is the seventeenth instance of one shape validated and its peers trusted,
and the sweep is what stops the eighteenth.

## Part 4 — the most likely failure on demo day (R-MCP-017)

A refresh refused mid-session, and a vanished credential store, escape `call` as `-32603 Internal
server error`. `ConsentFailed` and `TokenStoreError` are not `GmailFault`s and are raised from
`client.py:451`, outside every `try`. GMAIL-06's `mailweave auth login` instruction is constructed
and thrown away. D.11 names the 7-day Testing-status clock as the trigger, and the owner's project is
in Testing. Route both onto D.11's `auth_reauth_required` side with the instruction intact.

## What this round does not do

R-DISC-024/025/028, R-MCP-004/005/011..015/018/019/022, and the round 19–21 ride-alongs: tracked,
untouched. WS-08/09/12/13/14/16/17/18: not started. The comparison against the native connector:
after the demo, with the owner's agreement on questions, and **not** by building WS-16.

## Constraints

OD-1..OD-7; I-1..I-4; A1..A11. No Sampling, no LLM call, no embedding. No network in tests. No real
or realistic personal mail text. Do not touch retry/backoff. Do not mark any rubric criterion PASS;
do not restore ROUTE-01; do not edit `FINDINGS_LEDGER.md` or `RUBRIC_TRANSITIONS.md`. Do not tune
against any reviewer's probe set.

Gates clean: ruff, ruff format, mypy --strict, `python -m tools.guards`,
`pytest -q -m "not network"` (**2,691** currently pass). Rubric stays **6 PASS / 0 FAIL / 0 BLOCKER
/ 107 NOT TESTED**.

Reintroduction: every anchor matched, every file changed, all three packages resolving into your
scratch tree (whole tree incl. `docs/`), every `caught_by` citation catching individually. No test
compares a derivation with itself.

## Deliverable

`docs/reviews/ROUND_26/IMPLEMENTER.md`: per part, what changed, what each test establishes, what you
could **not** establish. The DISC-01 numbers on the `Re:`-prefixed fixture. The character ceiling
measured on the rendered form at 5, 7, 12, 30 and 60 messages. The list of sender-influenced wire
fields and the bound on each. "Have I trusted a peer?" Anything new, filed and left.

## Gating reviewer

One pass, `R-MCP`, scoped to the eight — the surface is where all eight meet the host.

## Exit condition

Five queries on a `Re:`-prefixed thread produce five different fills. No rendered response crosses
25,000 characters without `truncated_by` saying so. No sender-chosen field can close the fence. A
refused refresh tells the model to run `mailweave auth login`. Nothing else changed.
