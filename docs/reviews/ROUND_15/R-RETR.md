# ROUND 15 — R-RETR review (WS-04: query analysis and the lexical rungs)

**Reviewer:** R-RETR, independent instance, 2026-09-03. Sole gating reviewer for round 15.
Verified by execution per `AGENT_LOOP.md` §4/§5/§5a and §7. Source and tests **untouched**;
every probe ran from `/tmp/rretr15/*.py` against the real tree, and every planted defect ran
in a scratch copy at `/tmp/rretr15/tree` (see *Scratch-tree caveat* below). Probe files are
named against each result.

## Environment

| Gate | Result |
|---|---|
| `ruff check .` | All checks passed |
| `ruff format --check .` | 153 files already formatted |
| `mypy --strict` | Success, 127 source files |
| `python -m tools.guards` | 7 guards clean (forbidden-import, generative-client, gmail-endpoint, ground-truth-isolation, scope-literal, unaudited-disk-write, unwrapped-http-client) |
| `pytest -q -m "not network"` | **2,180 passed**; re-counted independently via `--collect-only -q` summed per file = **2,180** |
| `tools/rubric_status.py --check` | 7 PASS / 0 FAIL / 0 BLOCKER / 106 NOT TESTED, 11 transitions — unchanged |

`mailweave.__file__` → `/root/mailweave/server/src/mailweave/__init__.py`;
`mailweave_harness.__file__` → `/root/mailweave/harness/src/mailweave_harness/__init__.py`.
All gates re-run twice, before and after all probing; identical both times. Nothing in
`/root/mailweave` was written by this review.

**Scratch-tree caveat, recorded because it nearly produced a false green.** The venv installs
`mailweave` as an editable `.pth` pointing at `/root/mailweave/server/src`. My first run of the
priority-5 plants executed with `cwd` in the scratch tree and **all four plants passed** — because
the imports still resolved to the real tree. Every plant result below was re-run with
`PYTHONPATH=/tmp/rretr15/tree/server/src:...` and `__pycache__` cleared, and `mailweave.__file__`
confirmed to resolve inside the scratch tree. A reviewer copying a tree in this repo and running
`pytest` inside it is testing the original.

## Reachability rule I applied (§5a)

The ladder and the assembly have **no production caller today**: `LadderRunner` and `assemble` are
imported only by tests; there is no MCP tool surface wired to them (`grep` over `server/src`,
`harness`, `tools`). I did **not** treat that as making WS-04's defects inert. §5a exists to stop
findings being filed against code that does not exist and to stop re-review of sealed modules; the
ladder is the code this round shipped, it executes today on ordinary query strings, and the work
order's own exit condition is that it runs. So: **a defect triggered by an ordinary query reaching
`LadderRunner.run` / `assemble` is reachable.** What I classify as *not reachable* is anything
requiring code that does not exist — the budget accountant (WS-10), thread maps and handles
(WS-05/06), the semantic pool (WS-08), the harness and its corpora (WS-16). One finding
(R-RETR-010) is split explicitly, because half of it depends on a Gmail response shape nobody has
measured and half does not.

---

## Priority 1 — does the ladder actually retrieve?

**What holds.** I drove 400 randomised mailboxes × 18 query shapes through the real client behind
`httpx.MockTransport` (`/tmp/rretr15/a8_sweep.py`) and asserted, from outside the process, that
`H` equals the ids the mailbox handed back and that `H ⊆ disclosed ∪ withheld`. **Zero accounting
violations in 400 trials**, and no phantom id ever appeared in a response. The `DispositionLedger`
holds under the ladder, which is the thing it had never been a consumer of.

A **fixture-scale position sweep** (`/tmp/rretr15/e1_position_sweep.py`,
`/tmp/rretr15/e2_sweep2.py`): a 40-message thread with the evidence moved through positions
0, 1, 6, 19, 32, 38, 39. Exact-phrase family: **7/7 found, all at `body_clean`, position correct,
`included == stated_total == 40`, `outcome: answered`**. Cross-message family
(`from:` at position 0, the term at position *p*): **6/6 recovered by L1b, all at `body_clean`,
positions correct**. Position-flat at this scale. This is *not* EV-02 — see the recommendations.

**Where it silently returns less than it should.** Three shapes, all reachable from a plain query:

1. **A query the parser produces zero constraints from becomes a whole-mailbox scan whose results
   are reported as matches.** `mailweave_search("(rollout OR escalation)")`,
   `mailweave_search("the and of")`, `mailweave_search("  ")` and `mailweave_search("newer_than:30d")`
   (when it returns nothing) all put **`q=in:anywhere`, `includeSpamTrash=true`** on the wire —
   Gmail's whole mailbox, spam and trash included. On a 60-message fixture: 60/60 ids into `H`
   including 6 spam messages, 12 arbitrary threads disclosed with `role: matched` and
   `reason: GmailQueryMatch(query="in:anywhere")`, 48 withheld records, `outcome: answered`,
   `sufficiency: ambiguous`, `asked_for.term_coverage: 1.0`. `Probe.__post_init__` refuses an
   *empty* `q` for exactly this reason and says so in its own message; `BroadeningRung._anywhere`
   walks around it because `"in:anywhere"` is a non-empty string. **R-RETR-006, BLOCKER.**
   (`/tmp/rretr15/d6_anywhere.py`, `/tmp/rretr15/d7_nonlexical.py`, `/tmp/rretr15/f2_dateonly.py`)

2. **The L1 stop switches L1b off and reports it as `not_applicable`.** See priority 2.
   **R-RETR-007, HIGH.**

3. **A cross-message constraint made of free text is not decomposable at all.** See priority 2.
   **R-RETR-008, HIGH.**

**Mis-parse recovery, on a case set I built (ROUTE-02 requires the reviewer to build it).**
Twelve adversarial mis-parses against one 4-message thread holding the evidence
(`/tmp/rretr15/b1_misparse.py`): wrong sender guess, wrong name-only sender, wrong relative
window, wrong absolute window, wrong operator class (typo), wrong label, wrong `is:` state, wrong
subject guess, near-miss phrase, right sender / wrong term, a boolean the parser drops, and two
terms split across messages. **Recovered 8/12. False-not-found: 0** — every failure is
`outcome: inconclusive` with an `empty_diagnosis`, never `not_found`. The four failures share two
root causes: a query whose only constraint is `terms` or `phrase` has **no recovery rung at all**
(L1b needs ≥2 constraints; L2's single drop renders an empty `q` and is not planned; L3's
broadening re-sends the same phrase) — **R-RETR-015** — and the unknown-operator class —
**R-RETR-012**.

**Paging.** `max_pages_per_query = 1` is an architecture cap, and `more_pages` + a widening
affordance is its declared disposition — which I confirmed fires per probe. But a run in which
*every* probe declares `more_pages: true` and the query's own answer was never observed still
reports `outcome: answered` (`/tmp/rretr15/a5_paging_fatal.py`): 200 unrelated threads
disclosed/withheld, the answering thread invisible, nothing in `outcome` reflecting that the scan
was declared incomplete. **R-RETR-016, LOW.**

---

## Priority 2 — L1b, the rung the project exists for

**The implementer's claim is true as far as it goes.** On the shipped fixture,
`from:dev@team.example cutover` returns **zero at L1** (asserted, not assumed) and L1b recovers
`t-split` with both messages as rows. I reproduced that independently and extended it to a
40-message thread at six evidence positions (above): L1b's recovery is real, and the fixture's
message-scoped `q` makes it a real recovery rather than a generous double — I re-read
`tests/fixtures/mailbox.py` and confirmed it imports nothing from `mailweave.query`, evaluates
`q` per message, and raises `UnimplementedOperator` rather than ignoring an operator (it fired 26
times in my randomised sweep, on `thread:abc`, which is how I found R-RETR-012).

**Case 1 that L1b misses: the stop.** Put two ordinary single-message hits in the mailbox
alongside the split thread and run the same query (`/tmp/rretr15/a2_stop.py`):

```
'from:dev@team.example cutover', mailbox = t-split (evidence spread over spl-1/spl-2)
                                         + 2 unrelated single-message threads that match alone
  rungs run        : ['L1']              stop rule: D.3-2 after L1
  t-split in H     : set()               t-split in sources: False
  outcome          : answered            sufficiency: sufficient      partial: False
  empty_diagnosis  : None
  not_tried        : [('L0','not_applicable'), ('L1b','not_applicable'),
                      ('L2','not_applicable'), ('L3','not_applicable')]
```

L1b **had a plan** and was skipped by the `stopped` short-circuit in `run_parsed`; the response
then states `not_applicable`, which in OD-2's vocabulary is the claim that the rung *could not have
helped*. It could: it is the only rung that can see this thread. This is LEX-03's statement
("Queries whose constraints are satisfied jointly by different messages of a thread are not
silently missed") failing, silently, on an `answered`/`sufficient` response. The implementer's §8
note 1 and amendment A8's note 1 name the `not_applicable` vocabulary problem **only for L2/L3
when evidence already existed**; the L1b case, where the reason is a stop and the cost is the
project's founding bug, is not named anywhere.

Two aggravating details, both executed (`/tmp/rretr15/a3_conjunct.py`):

* D.3 rule 2's fourth conjunct is `answer_type_presence`; the code tests
  `not run.answer_type.blocks_stop`, i.e. `present is not False`. That imports rule **1b**'s "or the
  query carries no answer-type cue" escape into rule **2**, where D.3 and A.7's L1 row do not put
  it. Consequence: the stop fires on *every* ordinary non-question query with 1–5 hits, which is
  what makes this reachable.
* Whether the split thread is found therefore depends on the query's *grammar*:
  `from:dev@team.example cutover` → stops, misses it; `when did we cutover from:dev@team.example`
  → does not stop (`present is False` blocks it), finds it. Same mailbox, same evidence.

**Case 2 that L1b misses: free text is one constraint.** `_build_constraints` packs every residual
term into a single `terms` constraint, so `mailweave_search("rollout cutover")` over a thread whose
two messages carry one term each parses to **one** constraint, `DecompositionRung.plan` returns
`()`, and the rung is skipped (`/tmp/rretr15/a1_terms.py`):

```
  parsed constraints : [('terms','terms')]
  rungs run          : ['L1','L3']     rungs skipped: ['L0','L1b','L2']
  probes             : L1 'rollout cutover' -> 0 ;  L3 'in:anywhere rollout cutover' -> 0
  outcome            : inconclusive     not_tried: [... ('L1b','not_applicable') ...]
```

This is the originating bug's shape in its commonest form — two content words that live in
different messages of one thread — and the rung built to recover it does not fire. The response is
honest (`inconclusive`, `empty_diagnosis: incomplete`), so this is a recall gap rather than a lie,
except for the `not_applicable` label. `DecompositionRung`'s docstring says a query whose
constraints are jointly satisfied by different messages "matches nothing at L1, however correct the
parse was. **Decomposition is the answer**" — for this class it is not.

**Does the "can only under-name a thread whose messages are already in `H`" bound hold? No.**
The bound is stated as a necessary condition: a thread drops out of the intersection *only* when a
probe's whole contribution was already admitted, "which means one single message satisfied both
constraints", and therefore "those ids are in `H` already". Counterexample by execution
(`/tmp/rretr15/a4_paging.py`, `/tmp/rretr15/a5_paging_fatal.py`): give one decomposition probe more
than `page_size` matches. Its page truncates at 100, the answering thread's message is not on it,
the thread drops out of the intersection, and its ids are **not** in `H` — no single message
satisfied both constraints, and nothing was "already admitted".

```
  L1b  q='from:ana@team.example' returned=100 more_pages=True
  L1b  q='cutover'               returned=100 more_pages=True
  intersection: []      zz-1 in H? False   zz-2 in H? False
  t-answer in sources? False   t-answer in withheld? False   outcome: answered
```

The docstring cites `test_l1b_can_only_under_name_a_thread_whose_messages_are_already_in_H`, which
executes the *sufficient* case (`t-dense`) and reads as though it established the *necessary* one.
**R-RETR-013, MEDIUM.**

**What the L1b cap does not cost.** `MAX_DECOMPOSITION_PROBES = 3` means a 5-constraint query never
probes constraints 4 and 5 — and since `terms` is built last, the free-text constraint is the one
always dropped (`/tmp/rretr15/d1_battery.py`). I checked the docstring's "superset, so the cap costs
precision and never recall" claim and **it holds**, but not for the reason given: the intersection is
a superset, and separately every hit-bearing thread is mapped whatever the intersection says, so a
thread under-named by the cap still becomes a `Source`. The residue is that an under-named thread
sorts *after* the intersection in `hit_threads`, so at `max_hit_threads` it is the one that becomes
a withheld record. That is a declared disposition, not a drop.

---

## Priority 3 — evidence preservation under the ladder

I could not construct a run in which an observed id is neither disclosed nor withheld.

* **400-trial randomised sweep**: `H == disclosed ∪ withheld` in every trial.
* **Overflow**: 14 hit-bearing threads against `max_hit_threads = 12` → 12 sources, 2 threads'
  hits become `withheld` records carrying `cap: max_hit_threads`, a `why` naming the counts, and a
  `mailweave_thread_map` affordance; `partial: true`. At 200 threads: 188 withheld records, all
  with affordances (`/tmp/rretr15/a5_paging_fatal.py`).
* **Relaxation/broadening**: L2 and L3 reach Gmail only through `list_messages`, so their pages
  enter `H` on the same path; the sweep covers them.
* **A rung raising midway**: forced `messages.list` to 500 after the second probe
  (`/tmp/rretr15/e3_final.py`). The retry ladder exhausts, `GmailUnavailable` propagates out of
  `run_parsed`, **no envelope is produced**. Fail-closed: nothing observed can escape unaccounted,
  at the cost of no partial answer (the mid-rung timeout contract is WS-10's and is absent, correctly).
* **A hit with no `threadId`** (an id in `H` that `hit_threads` would skip, hence never planned and
  never withheld): unreachable — `parse_response(MessageListPage, ...)` refuses the page
  (`GmailResponseMalformed ... messages.0.threadId:missing`) before anything is sealed
  (`/tmp/rretr15/a7_nothread.py`).
* **Dropping an id between the wire and the seal**: planted in `_fetch_list_page` in the scratch
  tree. Dropping the id alone is refused *by the seal itself* ("this messages.list observation names
  a thread for ids it did not return"); dropping id and thread together gets past the seal and is
  caught by the commonality test's accountable clause (`/tmp/rretr15/p2_accountable.py`,
  `/tmp/rretr15/p3_accountable2.py`).

**Verdict: the ledger holds under its new consumer.** The one place evidence is lost is *upstream*
of it — a probe whose page truncated never observes the ids at all, so there is nothing for the
ledger to account for (R-RETR-013/016).

---

## Priority 4 — A3 positions and A6 `stated_total`

**I could not get a row onto the wire at a position outside its thread.** `Source` validates
`0 <= p < stated_total`, the sealed observation validates the same range and injectivity before
that, and `assemble`'s fallback index is bounded by `len(chronological)`. `model_copy` past the
model is closed by round 14's `re_establish_tree`. Reversing the chronological sort in the scratch
tree is caught by the #296 test.

**But positions are invented when the observation refused to state them.** `_thread_scalars` is
careful: if any message of a `threads.get` lacks `internalDate` — PF-2's suspected `format=metadata`
behaviour — it returns **no** position map for the whole thread and records
`scalars_absent_because`, because "inventing them would be the failure this project exists to
prevent". `assemble` then computes `position = index if observed is None else observed` over its own
`sorted(..., key=lambda m: (int(m.internal_date or "0"), m.id))` — which, with every `internalDate`
missing, degenerates to **alphabetical order by message id**, presented as a 0-based index into
chronological order. `scalars_absent_because` has **no consumer** outside `tests/test_gmail_client.py`;
nothing in the response says the order could not be derived (`/tmp/rretr15/a6_positions.py`):

```
metadata_returns_internal_date=True   rows: [('m-zulu',0,'matched'), ('m-alpha',1,'stub')]
metadata_returns_internal_date=False  rows: [('m-alpha',0,'stub'),  ('m-zulu',1,'matched')]
                                      ledger positions: {'m-zulu': None, 'm-alpha': None}
```

`m-zulu` is chronologically first and is the matched message; in the second run it is reported at
position 1 of 2. A3's own words: out-of-range positions raise rather than clamp "because clamping
would silently move evidence". This moves evidence silently while staying in range.
**R-RETR-009, HIGH.** No test drives `metadata_returns_internal_date=False` through the ladder or
`assemble`; the flag is exercised only at the client level.

**A6 `stated_total` holds.** `stated_total` is `len(recorded.thread.messages)`, the observation
seals the same number, and both the exactness validator and the ≥-observed floor refuse a
disagreement (executed below under priority 7). `included == stated_total` on every mapped thread I
built, including the 40-message sweep.

---

## Priority 5 — is the commonality test vacuous? **No.**

This is the strongest thing in the round, and I tried hard to break it. Every plant below ran in the
scratch tree with imports verified to resolve there; each was applied with an anchor assertion and a
file-changed assertion, and reverted afterwards.

| Plant | Property attacked | Result |
|---|---|---|
| runner sends one probe that was never in the published plan (L1) | **enumerable** | **FAILS** at `test_lexical_ladder.py:329` — `Extra items in the left set: (L1, 'procurement extra')` |
| `FilteredRung.plan` reads a module counter | **reproducible** | **FAILS** at `:321` — the two independent parses plan different `q` |
| L3 lists through a throwaway ledger | **accountable** | **FAILS** at `:337` |
| `_fetch_list_page` drops one id *and* its thread before sealing | **accountable**, isolated | **FAILS** at `:347` — `ledger.hit_ids != returned` |
| `_fetch_list_page` drops the id only | **accountable**, upstream | refused by the seal itself, before the test |
| the wire gets a `q` the probe does not record | **declared** | **FAILS** at `:337` |
| `_execute` records a `Probe` that is not the one planned (`why` rewritten) | **plan/execution identity** | **FAILS** at `:333` |
| `DecompositionRung.plan` always returns `()` | **anti-vacuity guard** | **FAILS** at `:353` — `executed_rungs != set(LADDER_RUNGS)` |
| `LADDER` loses `DecompositionRung` | **population** | **FAILS** — and in a *different* test, `test_the_ladder_population_is_the_five_rungs_the_architecture_names`, exactly as claimed |

(`/tmp/rretr15/p1_commonality.py`, `p2_accountable.py`, `p3_accountable2.py`, `p4_more.py`,
`p5_identity.py`.)

I also checked the clause I initially suspected of being a self-comparison —
`[e.probe for e in execution.executed] == list(execution.planned)` — by rewriting the recorded probe
in `_execute`. It fires. **Retracted.**

**The citation sweep is also live.** Planting a stale `test_…` name in `FilteredRung`'s docstring
fails `test_every_test_a_source_docstring_names_exists` (`/tmp/rretr15/p7_citation.py`).

**Issue-#296 reintroduction, three shapes the orchestrator did not try** (`/tmp/rretr15/p6_296.py`).
All three are caught by
`test_the_message_that_caused_the_match_is_in_the_response_even_though_it_is_the_oldest`:
(a) the oldest matched message disclosed as a **stub** instead of `body_clean` — the depth-reduction
form the ledger structurally *cannot* catch, since A.7a permits depth reduction; (b) chronological
order reversed, so every message is present at an in-range but wrong position; (c) the oldest row
dropped outright.

---

## Priority 6 — docstring claims, executed

| Claim | Where | Verdict |
|---|---|---|
| "Decomposition is the answer" for constraints spread across messages | `DecompositionRung` | **false for the term-only class** (R-RETR-008) |
| L1b "can only under-name a thread whose messages are already in `H`" | `Decomposition` | **false under page truncation** (R-RETR-013) |
| "if L1's evidence was sufficient there is nothing to decompose for" | `LadderRunner._should_run` | **false** — L1's 2 unrelated hits are not "nothing to decompose for" (R-RETR-007) |
| passthrough tokens are "carried into the executed `q` byte for byte, so Gmail's own parser sees exactly what the user wrote" | `query/operators.py` module docstring | **false** — `rollout OR escalation` reaches the wire as `rollout escalation`. `ParsedQuery.render`'s docstring says the opposite ("**not** re-emitted") and is the true one; two docstrings in this round's code contradict each other (R-RETR-014) |
| an unknown operator "is additionally named in `ParsedQuery.unknown_operators` so a **reader** can see that MailWeave declined to prove it" | `query/operators.py` | **false for any reader of a response** — the field has no wire consumer (R-RETR-012) |
| relative windows "widened by `DATE_MARGIN_DAYS` and declared" | A.6a rule 3, `timepolicy` | **half false** — declared but not applied to the `q` for `newer_than:`/`older_than:` (R-RETR-011) |
| "not expressible in the shipped schema — arithmetic rather than effort" | A8, `_refuse_a_source_that_omits_its_own_hits`, IMPLEMENTER §2.2 | **false** — A.7a's answer builds today if the thread is not made a `Source` (R-RETR-010) |
| the cap "costs precision and never recall" | `DecompositionRung` | **true**, verified (see priority 2) |
| "a hit beyond `max_body_fetches` is disclosed as a stub row, not withheld" | `_fetch_bodies` | **true** — 14 hits in one thread → 10 `body_clean` + 4 `stub`, all `role: matched`, 0 withheld |
| "the consequence of the cap is a withheld record per hit … never a silent drop" | `hit_threads` | **true** — 14 and 200 thread cases |
| "It never emits `outcome: not_found`" / "It computes no score" | `assemble` module | **true** — no `NOT_FOUND` anywhere in `retrieval/`; no row carried a score in any run |
| "there is no path in this module that fetches ids without recording them" | `ladder` module | **true**, and structurally so — the transport seam refuses anything that is not a sealed `FetchedIds` |
| `include_spam_trash` derived from the probe's own `q` | `Probe` | **true**, and it is the reason R-RETR-006 sets `includeSpamTrash=true` — the coupling works; the policy it faithfully implements is the defect |

**LEX-02's fidelity table, re-derived independently** (`/tmp/rretr15/d1_battery.py`): all 21 members
of `OperatorName` parse **and** reach L1's executed `q` verbatim; negation (`-from:`), quoting
(`subject:"vendor selection"`) and angle-address normalisation
(`from:"Amy Smith <Amy.SMITH@Example.Test>"` → `amy.smith@example.test`, display `Amy Smith`) all
correct. **`exact_signal_match`**: `ExactBranch` has exactly three members; `evaluate_exact_signal`'s
signature carries no corpus, count-table or threshold parameter; precedence E-a → E-b → E-c holds on
a query carrying all three candidates; E-b verifies locally against subject *and* default view.
**`empty_diagnosis`**: all four states executed —
`complete/restores=<name>` (8/8 correct restoring constraint over my constructed cases),
`complete/restores=None`, `incomplete` with a complete `untried_drops` at the `min(k,6)` budget
(k=8 → 6 probed, `('subject','terms')` untried), and `None` on an answered response.
**ROUTE-03**: for a 5-constraint query, `RelaxationRung().plan()`'s drop order and the executed
`RelaxationStep` sequence are **equal as ordered lists**, `['after','from','to','subject','terms']`.

---

## Priority 7 — A8: is the contradiction real, and was escalating right?

**The contradiction is real, and I reproduced both halves** (`/tmp/rretr15/c1_a8.py`,
`/tmp/rretr15/c2_a8_floor.py`). For a 10-message thread whose `threads.get` omits the one message
`messages.list` returned:

* `stated_total = 9` → `_stated_total_is_not_below_what_was_observed_in_the_thread`:
  *"states the thread holds 9 messages, but 10 distinct messages were observed in it"*; and
  independently PART-03's phantom remainder when the source reports itself complete.
* `stated_total = 10` → `_stated_total_is_the_one_the_observation_stated`:
  *"source t-anc states 10 and the observation said 9"*.

So **no `Source` for that thread is constructible.** That much of A8 is exactly right, and the
implementer was right that a `Source` carrying two completeness claims needs a schema change.

**But the escalation's stated reason is wrong, and something buildable was missed.** A8 and
IMPLEMENTER §2.2 say the A.7a answer — *a `partial_source_failure` withheld record with a
`mailweave_get_messages` affordance* — is "not expressible in the shipped schema". It is. Do not
make the disagreeing thread a `Source` at all: withhold **every** id observed in it under
`WithheldCap.PARTIAL_SOURCE_FAILURE` with a `why` naming the disagreement and a
`mailweave_get_messages` affordance per id. The envelope **builds, validates and serialises**
(`/tmp/rretr15/c3_a8_alt.py`): `partial: true`, ten withheld records, disclosure digest intact.
It costs the thread's other messages as disclosed rows — they become withheld with affordances —
which is a real cost and a fair thing to escalate. It is not arithmetic.

**And the cost of the current behaviour is larger than recorded.** One self-disagreeing thread
denies the *entire* response. Five healthy threads retrieved correctly plus one disagreeing thread
→ `DispositionInvariantError`, no envelope, nothing returned (`/tmp/rretr15/c4_blast.py`). A8 says
"the bug cannot be shipped. That is safe" — it is safe about that thread and unsafe about every
other query the mailbox can answer.

**Judgement.** Escalating the *schema* question to WS-11 with PF-1 as its input is correct and I
endorse it. Escalating on the grounds that **no** conformant answer exists is not, and the claim is
load-bearing: it is why nothing was built. **R-RETR-010, HIGH** — split by reachability below.

---

## Findings

```
ID:            R-RETR-006
Severity:      BLOCKER
Reachability:  REACHABLE today. Triggered by ordinary query strings through
               LadderRunner.run + assemble, both of which exist and execute.
Rubric:        LEX-02 (mandatory); also contract I-3 (adaptive cost) and I-4's paired
               hallucinated-found guard; AD A.7 L3.
Location:      server/src/mailweave/retrieval/ladder.py, BroadeningRung._anywhere
               (the `if not chosen:` fallback, and the unconditional
               `" ".join([ANYWHERE_OPERATOR, *fragments])` when `fragments` is empty)
Repro:         /tmp/rretr15/d6_anywhere.py, /tmp/rretr15/d7_nonlexical.py,
               /tmp/rretr15/f2_dateonly.py
                 mailweave_search("(rollout OR escalation)")   -> wire: ('in:anywhere', True)
                 mailweave_search("the and of")                -> wire: ('in:anywhere', True)
                 mailweave_search("  ")                        -> wire: ('in:anywhere', True)
                 mailweave_search("newer_than:30d")  [0 hits]  -> wire: ..., ('in:anywhere', True)
Expected:      A.7 L3 broadens *the query*. LEX-02: a dropped signal is named and the
               coverage reported. Probe.__post_init__'s own message: "a listing with no
               query asks Gmail for the whole mailbox" is the thing not to do.
Actual:        A query the parser produced zero constraints from is broadened to the whole
               mailbox including spam and trash. On a 60-message fixture: |H| = 60 (6 spam),
               12 threads disclosed with role=matched and reason
               GmailQueryMatch(query="in:anywhere"), 48 withheld records, outcome=answered,
               sufficiency=ambiguous, asked_for.term_coverage=1.0,
               asked_for.constraint_drop_depth=1. The response asserts that 12 unrelated
               threads match a query whose terms were never sent. Cost: an unbounded listing
               plus 12 thread maps (480 u) for a query that should cost one probe or none.
               `confidence: non_lexical` -- D.3 rule 4's escalation trigger -- is computed
               and then ignored.
Required fix:  BroadeningRung must not plan an `anywhere` probe that carries no fragment of
               the user's query; a bare mailbox-scope operator is not a probe. A parse with
               no constraints must reach an honest outcome (inconclusive, with the parse
               failure named) rather than a whole-mailbox scan. `term_coverage` must not
               report 1.0 for a query whose content the parser could not carry.
```
```
ID:            R-RETR-007
Severity:      HIGH
Reachability:  REACHABLE today. Any ordinary (non-interrogative) two-constraint query with
               1-5 L1 hits.
Rubric:        LEX-03 (mandatory); contract I-4 proof-of-violation (b), reported as untried
               with a false reason rather than not reported at all; AD D.3 rule 2, A.7 L1 row.
Location:      server/src/mailweave/retrieval/ladder.py — LadderRunner.run_parsed (`stopped`
               short-circuits every later rung), LadderRunner._after_rung (the L1 branch's
               fourth conjunct), and assemble._not_tried (every skipped rung -> not_applicable)
Repro:         /tmp/rretr15/a2_stop.py, /tmp/rretr15/a3_conjunct.py
                 mailbox = t-split (from:dev in spl-1, "cutover" in spl-2)
                         + 2 unrelated single-message threads matching both constraints
                 query   = "from:dev@team.example cutover"
Expected:      LEX-03: a thread whose constraints are satisfied jointly by different
               messages is not silently missed. OD-2: `not_applicable` means the rung could
               not have helped. D.3 rule 2's fourth conjunct is `answer_type_presence`.
Actual:        rungs run = ['L1'], stop_rule = D.3-2. L1b had a non-empty plan and never ran.
               t-split is not in H, not a source, not withheld. Response:
               outcome=answered, sufficiency=sufficient, partial=False,
               empty_diagnosis=None, not_tried=[..., ('L1b','not_applicable'), ...].
               The fourth conjunct is implemented as `not answer_type.blocks_stop`
               (= `present is not False`), which imports rule 1b's "or the query carries no
               answer-type cue" escape into rule 2. Whether the split thread is found
               therefore turns on grammar: "when did we cutover from:dev@team.example" finds
               it (present is False blocks the stop); "from:dev@team.example cutover" does not.
Required fix:  Either L1b runs before the D.3 rule-2 stop can fire (A.7's table calls L1b
               "feeds L1"), or a rung skipped by a stop is reported with a reason that is
               true -- which needs the fourth `not_tried[].why` value already escalated in
               A8 note 1, whose scope must widen to cover this case. Separately, the fourth
               conjunct must match D.3 rule 2 as written, or D.3 must be amended to carry
               rule 1b's no-cue escape explicitly.
```
```
ID:            R-RETR-008
Severity:      HIGH
Reachability:  REACHABLE today. Any query of two or more free-text words.
Rubric:        LEX-03 (mandatory)
Location:      server/src/mailweave/query/analysis.py, _build_constraints (all residual terms
               become one `terms` Constraint); server/src/mailweave/retrieval/ladder.py,
               DecompositionRung.plan (`if len(parsed.constraints) < 2: return ()`)
Repro:         /tmp/rretr15/a1_terms.py
                 thread t-terms: tt-1 body "The rollout is on the agenda.",
                                 tt-2 body "Cutover is scheduled for the second week."
                 query "rollout cutover"
Expected:      LEX-03 and DecompositionRung's own docstring: a constraint spread across
               different messages of one thread is recovered by decomposition.
Actual:        parsed constraints = [('terms','terms')] -- one constraint -- so L1b is not
               applicable, L2's only drop renders an empty q and is not planned, and L3
               re-sends the same conjunction. rungs run = ['L1','L3'], both zero. The
               response is honest (inconclusive, empty_diagnosis incomplete,
               untried_drops=('terms',)) but names L1b `not_applicable`, and the founding
               bug's commonest shape is unrecoverable.
Required fix:  Decomposition must be able to split the free-text constraint -- one probe per
               content term, or a `terms` constraint that is decomposable even though it is
               a single relaxation unit. The relaxation grouping and the decomposition
               grouping are different questions and are currently the same object.
```
```
ID:            R-RETR-009
Severity:      HIGH
Reachability:  REACHABLE today. The code path is live in assemble; the trigger is a
               threads.get response with any message lacking internalDate, which is the
               shape PF-2 exists to measure for format=metadata.
Rubric:        amendment A3 (positions are indices into chronological order); EV-05's
               position claim; PART-05 adjacent.
Location:      server/src/mailweave/retrieval/assemble.py, assemble()
                 `position = index if observed is None else observed`, over
                 `sorted(..., key=lambda m: (int(m.internal_date or "0"), m.id))`;
               RecordedThread.scalars_absent_because (server/src/mailweave/gmail/client.py)
               has no consumer outside tests/test_gmail_client.py
Repro:         /tmp/rretr15/a6_positions.py
                 SyntheticMailbox(..., metadata_returns_internal_date=False)
                 thread t-p: m-zulu (chronologically first, the matched message),
                             m-alpha (chronologically second)
Expected:      A3: a position is a 0-based index into the thread's chronological order, and
               out-of-range positions raise rather than clamp "because clamping would
               silently move evidence". _thread_scalars refuses to invent positions for
               exactly this input and records why.
Actual:        With no internalDate, ledger positions are None for every message and
               assemble falls back to its own index, whose sort key degenerates to
               alphabetical order by message id. The matched, chronologically-first message
               is reported at position 1 of 2; on a 9-message thread the whole order is
               alphabetical. Nothing in the response says the order could not be derived --
               scalars_absent_because is computed and discarded. No test drives this path
               through the ladder or assemble.
Required fix:  When the observation states no positions, assemble must not state them
               either: omit `position` (and the claim), or carry
               scalars_absent_because onto the wire so the reader knows the order is the
               response's array order and not chronology. Inventing an order the seal
               explicitly refused to invent is the failure A3 names.
```
```
ID:            R-RETR-010
Severity:      HIGH
Reachability:  SPLIT, deliberately.
               (a) The claim "not expressible in the shipped schema" -- REACHABLE and false
                   today; it is a statement about code that exists, disproved by execution
                   with no Gmail dependency. This half blocks.
               (b) The blast radius (one disagreeing thread denies the whole response) --
                   code path REACHABLE today and executed by the round's own green test;
                   whether real Gmail emits the shape is unmeasured and is PF-1's question.
                   The schema *change* A8 contemplates remains correctly DEFERRED to WS-11.
Rubric:        EV-03 / EV-01 adjacent; AD A.7a; amendment A8; contract R-08/PART-03
Location:      server/src/mailweave/retrieval/assemble.py,
               _refuse_a_source_that_omits_its_own_hits (and its docstring);
               docs/ARCHITECTURE_AMENDMENTS.md A8; docs/reviews/ROUND_15/IMPLEMENTER.md §2.2
Repro:         /tmp/rretr15/c1_a8.py  (both validators, by execution:
                 stated_total=9  -> "states the thread holds 9 messages, but 10 distinct
                                     messages were observed in it"  (and PART-03 phantom)
                 stated_total=10 -> "source t-anc states 10 and the observation said 9")
               /tmp/rretr15/c3_a8_alt.py  (the answer A8 says cannot be built -- BUILDS:
                 no Source for the thread; every observed id withheld under
                 WithheldCap.PARTIAL_SOURCE_FAILURE with a mailweave_get_messages
                 affordance; partial=true; envelope validates and serialises)
               /tmp/rretr15/c4_blast.py  (5 healthy threads + 1 disagreeing thread ->
                 whole response refused, nothing returned)
Expected:      A.7a: the disposition for a source that cannot enumerate its own hit is a
               partial_source_failure withheld record with a retrieval affordance.
Actual:        MailWeave raises and produces no response at all, for every thread in the
               query. A8 and IMPLEMENTER §2.2 justify that by saying the conformant answer
               is inexpressible; it is expressible, provided the disagreeing thread is not
               made a Source. What is genuinely inexpressible is narrower: a *Source*
               carrying two different completeness claims.
Required fix:  Either build the withhold-the-thread disposition (which is A.7a's own words
               and needs no schema change), or amend A8 and IMPLEMENTER §2.2 to state
               precisely what is inexpressible and why the whole-response refusal, with its
               blast radius, is preferred to it. The current claim is wider than the code,
               which is the defect class this round was told to hunt.
```
```
ID:            R-RETR-011
Severity:      MEDIUM
Reachability:  REACHABLE today. Any query using newer_than: or older_than:.
Rubric:        LEX-02 (asked_for correctness); EV-05's recency clause; AD A.6a rules 2 and 3
Location:      server/src/mailweave/query/timepolicy.py, window_from_operators (widens the
               window for the relative family); server/src/mailweave/query/analysis.py,
               _build_constraints (the operator's own fragment, un-widened, is what goes to
               Gmail) and enforced_declarations (appends the widening declaration anyway)
Repro:         /tmp/rretr15/d3_margin.py   (now = 2026-09-03T12:00Z)
                 query "newer_than:7d rollout"
                 declared window_utc      : {'start': '2026-08-26T12:00:00Z'}
                 executed q on the wire   : 'newer_than:7d rollout'  (cuts at 08-27T12:00Z)
                 message at 2026-08-27T00:00Z: inside the declared window, excluded by the q,
                 never in H, never disclosed, never withheld
                 asked_for.enforced       : (..., 'date_window_widened:±1d, timezone-boundary safety')
Expected:      A.6a rule 2: "The reader can always see what was actually searched."
               A.6a rule 3: relative-date windows are widened by date_margin_days on each
               side, so the boundary risk the margin exists for is actually covered.
Actual:        The widening is applied only to the declared window_utc, never to the query.
               window_utc overstates the searched range by a day on each side, and the
               boundary safety is inert for the whole newer_than:/older_than: family --
               the family EV-05's second clause is about. The existing test
               tests/test_query_analysis.py::test_a_gmail_relative_age_operator_is_relative_
               and_is_widened asserts parsed.window.widened_days == DATE_MARGIN_DAYS and
               nothing about the executed q, so it pins the declaration and not the deed.
Required fix:  Either emit the widened window as the executed date fragments for the
               relative-operator family (as the derived `date_window` constraint already
               does), or stop declaring a widening that was not applied and narrow
               window_utc to what was actually searched.
```
```
ID:            R-RETR-012
Severity:      MEDIUM
Reachability:  REACHABLE today. Any query containing an unrecognised `name:value` token --
               a typo (`form:`), a newer Gmail operator, or `thread:`.
Rubric:        LEX-02 (mandatory); ROUTE-02
Location:      server/src/mailweave/query/analysis.py, analyse()
                 `_build_constraints(..., (*search_terms, *unknown), ...)`;
               server/src/mailweave/retrieval/assemble.py, _asked_for (ParsedQuerySummary
                 carries parsed.search_terms, which excludes unknown operators)
Repro:         /tmp/rretr15/a9_unknown_op.py
                 query "thread:abc rollout"
                   executed q            : 'rollout thread:abc'
                   asked_for.parsed.terms: ('rollout',)
                   asked_for.parsed.operators: {}
                   asked_for.dropped     : []      term_coverage: 1.0   drop_depth: 0
                 query "form:ana.smith@team.example rollout"  (a from: typo)
                   executed q            : 'rollout form:ana.smith@team.example'
Expected:      LEX-02: parsed signals are either enforced in the executed q or reported as
               dropped; every dropped signal is named; operators used are limited to
               Gmail's documented set (RO F3). operators.py's docstring: the token is
               "named in ParsedQuery.unknown_operators so a reader can see that MailWeave
               declined to prove it".
Actual:        The token is conjoined into the q -- so it can only reduce recall -- and
               appears nowhere in asked_for: not as an operator, not as a term, not as a
               drop. term_coverage reports 1.0. `unknown_operators` has no wire consumer, so
               no reader of a response can see it; only scan_scope[].q shows the literal.
               No recovery is possible: the token rides inside the single `terms`
               constraint, so L2 cannot drop it separately (see R-RETR-015).
Required fix:  Declare unknown operators in asked_for -- as a named drop, or as a distinct
               `unproven_operator` entry -- and decide deliberately whether an unproven
               token belongs in the executed q at all. Whichever is chosen, term_coverage
               must reflect it.
```
```
ID:            R-RETR-013
Severity:      MEDIUM
Reachability:  REACHABLE today. Any decomposition probe matching more than page_size (100)
               messages -- a bare `from:` on a busy correspondent is the ordinary case.
Rubric:        LEX-03 (the documented bound); EV-01 adjacent
Location:      server/src/mailweave/retrieval/ladder.py, Decomposition docstring; and
               tests/test_lexical_ladder.py::test_l1b_can_only_under_name_a_thread_whose_
               messages_are_already_in_H, which executes the sufficient case only
Repro:         /tmp/rretr15/a4_paging.py, /tmp/rretr15/a5_paging_fatal.py
                 120 messages match `from:ana@team.example`; 120 match `cutover`;
                 the answering thread's two messages sort behind the first 100 of each
                 L1b  q='from:ana@team.example' returned=100 more_pages=True
                 L1b  q='cutover'               returned=100 more_pages=True
                 intersection: []   zz-1 in H: False   zz-2 in H: False
                 t-answer in sources: False   in withheld: False   outcome: answered
Expected:      The docstring's stated necessary condition: a thread drops out of the
               intersection "only when a probe's entire contribution to it consists of ids
               an earlier probe already admitted -- which means one single message satisfied
               both constraints ... Those ids are in `H` already".
Actual:        A truncated page drops a thread from the intersection with no message
               satisfying both constraints and with its ids not in H at all. The bound is a
               statement about the admission delta and does not survive the page budget.
Required fix:  Restate the bound to name the page budget as its other precondition, and
               execute the truncation case in a test, so the claim's scope and the test's
               scope are the same. (Widening the page budget is A.7's decision, not this
               finding's.)
```
```
ID:            R-RETR-014
Severity:      LOW
Reachability:  REACHABLE today (documentation of shipped behaviour).
Rubric:        none — LEX-02 documentation; round 14's "a claim wider than the code" theme
Location:      server/src/mailweave/query/operators.py, module docstring, versus
               server/src/mailweave/query/analysis.py, ParsedQuery.render docstring
Repro:         /tmp/rretr15/d5_claims.py
                 "rollout OR escalation"   -> wire 'rollout escalation'
                 "(rollout escalation)"    -> wire 'in:anywhere'
Expected:      One statement about what happens to passthrough tokens.
Actual:        operators.py says they are "carried into the executed `q` byte for byte, so
               Gmail's own parser sees exactly what the user wrote". render() says they are
               "**not** re-emitted" and explains why. The wire follows render(); operators.py
               is false. Both docstrings are round-15 code.
Required fix:  Correct operators.py to match render(), which is the true and better-reasoned
               of the two.
```
```
ID:            R-RETR-015
Severity:      MEDIUM
Reachability:  REACHABLE today. Any single-constraint query -- a bare keyword set or a bare
               quoted phrase, the commonest query shape there is.
Rubric:        ROUTE-02 (mandatory); contract I-4
Location:      server/src/mailweave/retrieval/ladder.py — RelaxationRung.plan (a probe whose
               remaining constraints render an empty q is not planned) and
               BroadeningRung._anywhere (for a phrase-only query the broadened q is the same
               phrase); DecompositionRung.plan (needs >= 2 constraints)
Repro:         /tmp/rretr15/b1_misparse.py  (12 reviewer-built mis-parse cases, 8 recovered)
                 '"the rollout schedule slipped"' -> L0,L1,L3 all zero; L2 skipped;
                   empty_diagnosis incomplete, untried_drops=('phrase',)
                 'rollout OR escalation'          -> L1,L3 zero; untried_drops=('terms',)
                 'rollout note'                   -> L1,L3 zero; untried_drops=('terms',)
Expected:      I-4: a bad initial route must not force a false negative; the system can
               broaden or change strategy. ROUTE-02: evidence is recovered on adversarial
               mis-parse cases.
Actual:        For k = 1 the ladder has no recovery rung at all -- L1b needs two constraints,
               L2's only drop would render an empty q and is not planned, and L3's
               broadening re-sends the same phrase or terms. The response is honest
               (inconclusive, untried_drops naming the drop) and the recovery rate is
               structurally zero on this family. 0 false-not-found, so EV-04's letter holds.
Required fix:  A recovery route for single-constraint queries -- term-level relaxation
               inside the `terms` constraint, phrase-to-terms degradation at L3, or an
               explicit statement in A.7 that k = 1 is out of L2/L3's scope and which rung
               owns it. Note that "drop the only constraint" must not become the bare
               `in:anywhere` probe of R-RETR-006.
```
```
ID:            R-RETR-016
Severity:      LOW
Reachability:  REACHABLE today. Any query whose probes exceed one page.
Rubric:        none — EV-04 / ROUTE-01 adjacent; AD A.7 max_pages_per_query
Location:      server/src/mailweave/retrieval/assemble.py, assemble()
                 `outcome=(Outcome.ANSWERED if (disclosed and run.evidence_count) else ...)`
Repro:         /tmp/rretr15/a5_paging_fatal.py — every executed probe reports
               more_pages=True, the query's own answering thread was never observed, and the
               response reports outcome=answered with 200 unrelated threads.
Expected:      `answered` is a claim that the query was answered. The scan scope already
               declares that pages remain unfetched.
Actual:        `outcome` is derived from disclosure and evidence count with no reference to
               declared scan incompleteness, so a run that declares every probe truncated
               still reports `answered`.
Required fix:  Fold declared scan incompleteness into the outcome (or into `partial`), so a
               response that says "pages remain" does not also say "answered". WS-10 owns
               outcome policy; recorded here because the field is emitted this round.
```

---

## Recommendations, per criterion

**I mark nothing. Each recommendation is scoped; a scoped recommendation recorded as an
unqualified pass has happened twice in this project.**

* **LEX-01 · Message-level search is the first rung — RECOMMEND PASS, scoped.**
  Scope of my evidence: fixture-driven runs behind the real client and the real egress check.
  Established: on every run I drove (5-query corpus, 12 mis-parse cases, 3 exact-signal cases,
  400 randomised trials), the **first** Gmail call is `messages.list` with a non-empty `q`
  (`call_log[0]`, the transport's own log). `hit_threads` derives the hit set only from
  `ObservedEndpoint.MESSAGES_LIST` origins, so no thread listing can feed `H`'s hit half; message
  ids are carried end to end into rows, positions and withheld records. Not covered: the live
  account. Note for the record that R-RETR-006 makes that first call `q=in:anywhere` for
  zero-constraint queries — LEX-01's letter still holds, its spirit does not.

* **LEX-02 · Operator-parse fidelity and coverage reporting — RECOMMEND NOT PASS.**
  The fidelity half is established independently of the shipped table: all 21 `OperatorName`
  members parse and reach L1's executed `q`; negation, quoting and address normalisation correct.
  The **coverage-reporting** half fails on three counts, each executed: R-RETR-006
  (`term_coverage: 1.0` on a query none of whose content was executed), R-RETR-012 (an unproven
  token on the wire and absent from `asked_for`), R-RETR-011 (a widening declared in
  `asked_for.enforced` that was never applied). The acceptance clause "cases where a signal was
  silently dropped: 0" is not met.

* **LEX-03 · Multi-constraint decomposition — RECOMMEND NOT PASS.**
  Positive and reproducible: L1b recovers the cross-message case at six evidence positions of a
  40-message thread, at `body_clean`, with correct positions, and L1 returns zero on the same
  query. Blocking: R-RETR-007 (the L1 stop switches L1b off and calls it `not_applicable`) and
  R-RETR-008 (the term-only case cannot be decomposed at all). Independently, the criterion's
  recall bar is `[UNSET — register at G0]` against a Baseline D that does not exist, so no rate can
  be reported by anyone this round.

* **LEX-04 · Exact-signal stop — RECOMMEND PASS, scoped.**
  Established on all three A.8a branches (`rfc822msgid:`, qualifying phrase, structured identifier)
  against a 40-message thread: **rungs executed = 1** in each case, `stop_rule` D.3-1 / D.3-1b /
  D.3-1b, zero embedding calls, zero model calls, zero reranker invocations (none exist; the
  `generative-client` guard is clean), and **3 Gmail calls measured at the transport boundary**
  (`messages.list`, `messages.get`, `threads.get`) — not the meter's self-report. Not covered: the
  criterion says the count must come from network-level measurement (PERF-02) over a *family*
  distribution with a median. A `MockTransport` boundary is closer to that than `CallMeter` but it
  is one case per branch, not a family median. **The cost bar belongs to R-PERF on WS-16's counting
  proxy.**

* **EV-02 · Position-independent evidence recall — CANNOT ESTABLISH.**
  My sweep is 40 messages, 7 positions, two families, one seed, on a synthetic double. EV-02
  requires the EP §4.4 sweep on a ~100-message thread, a reviewer-chosen **holdout** seed, two
  fresh seeds agreeing within CI, and DISC-04 + PERF-01 passing on the same run. None of that
  machinery exists. Report my result as encouraging, not as evidence. **WS-16.**

* **EV-04 · Zero false "not found" — RECOMMEND NOT PASS, with the letter noted.**
  Over roughly 430 executed runs, `not_found` was never emitted and never can be — `NOT_FOUND`
  does not appear in `retrieval/` at all — so the false-not-found count is trivially 0 and stays
  0 while `outcome` has only two reachable values. That is not evidence for the criterion, whose
  rate is over the exact-lookup and buried-evidence families of a corpus that does not exist, and
  whose **paired hallucinated-found rate** cannot be reported at all. R-RETR-006 is a
  hallucinated-found-shaped response, which is precisely the guard EV-04 pairs with. **WS-16**
  for the measurement; R-RETR-006 blocks regardless.

* **EV-05 · Issue #296 signature is non-reproducible — RECOMMEND PARTIAL, scoped; do not record
  as PASS.**
  Clause 1 (`rfc822msgid:<m>` for a deep *m* returns *m* at body depth) is established on
  fixtures: 40-message thread, `m` at position 0, `role: matched`, `depth: body_clean`, reason
  read off `HitOrigin`, `stated_total == included == 40`, one rung, and no query-pattern special
  case (the id-exact route is the ordinary L0 `messages.list`). I reintroduced the bug in three
  shapes the orchestrator did not try — omission, depth reduction, and position reversal — and all
  three fail the shipped test. Clause 2 (recency) is established only weakly: an out-of-window
  message arrives as a stub with empty `constraint_coverage` and its own `internal_date` on the
  wire beside `window_utc`, which is a declaration a careful reader can check — and it is
  undermined by R-RETR-011 (`window_utc` wider than the executed `q`) and R-RETR-009 (positions
  invented when chronology is underivable). The criterion says both assertions pass **on the live
  account and** on the seeded corpus; neither exists. **Credentials, then R-GMAIL; WS-16.**

* **EV-06 · Recall against the full-dump ceiling — CANNOT ESTABLISH.** No Baseline B, no corpus
  instance, no paired scoring, no interleaved session. Nothing in this round is evidence for it.
  **WS-16.**

* **ROUTE-02 · Mis-parse recovery — CANNOT MARK PASS; measured, and the shortfall is
  structural.**
  On a case set I built (the criterion requires the reviewer to build it): **8/12 recovered,
  0 false-not-found**, and where relaxation recovered, the diagnosis named the correct restoring
  constraint in 8/8. The four failures are two named defects (R-RETR-015, R-RETR-012), not noise.
  The bar itself is `[UNSET — register at G0]`, so no one can mark this criterion this round.

* **ROUTE-03 · Relaxation is systematic and enumerable — RECOMMEND PASS, scoped.**
  This is the one criterion I can establish on the code as it stands. Established by independent
  replay: exactly one constraint dropped per probe; the order is `RELAXATION_ORDER` with ties
  broken by write order; the **published plan and the executed sequence are equal as ordered
  lists** on a 5-constraint query (not merely a containment); the plan is reproducible from
  `(query, now, zone)` alone and was proved to be so by planting a counter-reading plan, which
  fails the commonality test; each step logs its dropped constraint, `q` and hit count;
  `max_relax_probes = min(k, 6)` binds at k = 8 and the two unreached drops are named. Scope: the
  guarantee has no subject when k = 1 (R-RETR-015) — that is a ROUTE-02 gap, not a ROUTE-03 one,
  but a reader of a PASS should know it.

* **ROUTE-04 · Empty-result diagnosis — RECOMMEND PASS, scoped.**
  All four states executed on constructed cases whose restoring constraint I chose:
  `complete` + correct `restores` (8/8), `complete` + `restores: None` when nothing restores,
  `incomplete` with a complete `untried_drops` when `min(k,6)` cut the plan short, and `None` on
  a response that answered. OD-2's scoping holds: the promise is over probed drops, the shortfall
  is disclosed, and `outcome` is `inconclusive` in every incomplete case. Scope: 100 % correctness
  is over **my** constructed cases, not a corpus; the incomplete-diagnosis-rate ceiling is
  `[UNSET — G0]`; and the diagnosis is only as good as the relaxation that feeds it, which is
  empty for k = 1.

---

## Overall verdict

**Round 15 does not close.** One BLOCKER and five HIGH findings, all reachable from ordinary query
strings through code that exists and executes today.

The foundation the last eleven rounds built **holds under its first real consumer** — that is the
most important positive result here, and I tried to break it from four directions. The failures are
in the retrieval *policy* layered on top of it: a broadening rung that turns an unparsed query into
a whole-mailbox scan and calls the result matches (R-RETR-006); a stop rule that switches off the
rung this project exists for and reports it as inapplicable (R-RETR-007); a constraint model in
which free text cannot be decomposed (R-RETR-008); an assembly that invents the one ordering the
seal deliberately refused to invent (R-RETR-009); and an escalation whose stated reason —
"not expressible" — is false on execution (R-RETR-010).

The work order asked whether the ladder actually retrieves. It does, well, when it runs: L1b's
recovery is real and position-flat, the ledger accounts for everything it observes, and the #296
signature does not reproduce in any of the three shapes I planted. What it does badly is *decide
when to run* and *say what it did not run and why*.

---

## Established by execution

* `H = disclosed ∪ withheld` under the ladder, in 400 randomised mailbox × query trials, witnessed
  from outside the process by the double's own returned-ids log. Zero violations.
* The commonality test is **not vacuous**: nine independent plants — one per property, two for
  accountability, plus probe identity, the anti-vacuity population assertion, and the scope-narrowing
  guard — each make it fail, at the specific assertion each attacks. The citation sweep fires on a
  planted stale citation.
* Issue #296 does not reproduce, and its three reintroduction shapes (omission, depth reduction,
  position reversal) are all caught. A 40-message position sweep finds the evidence at every
  position, at body depth, with correct positions, `included == stated_total`.
* L1b recovers the cross-message-constraint case at every evidence position — when it runs.
* LEX-02's fidelity half: 21/21 operators parsed and carried into the executed `q`; negation,
  quoting and address normalisation correct.
* `exact_signal_match` is closed at three branches, takes no frequency input by signature, and its
  precedence is E-a → E-b → E-c on a query carrying all three candidates.
* ROUTE-03 in full, and all four `empty_diagnosis` states with a correct restoring constraint in
  8/8 constructed cases.
* Exact-signal queries resolve on one rung with 3 transport-level Gmail calls and no model,
  embedding or rerank call.
* Caps behave: `max_hit_threads` overflow → withheld records with caps, reasons and affordances,
  `partial: true`; `max_body_fetches` overflow → stub rows, never withheld.
* Fail-closed on a mid-rung transport failure: no envelope, nothing leaks.
* **A8's contradiction is real** — both validators refuse, by execution, at 9 and at 10.

## False on execution

* "Decomposition is the answer" for constraints spread across messages — not for free text
  (R-RETR-008), and not when an earlier stop fired (R-RETR-007).
* L1b "can only under-name a thread whose messages are already in `H`" — false under page
  truncation (R-RETR-013).
* "If L1's evidence was sufficient there is nothing to decompose for" (R-RETR-007).
* Passthrough tokens are "carried into the executed `q` byte for byte" (R-RETR-014).
* An unknown operator "is named … so a reader can see that MailWeave declined to prove it" — no
  reader of a response can see it (R-RETR-012).
* Relative windows are "widened by `DATE_MARGIN_DAYS`" — declared, not applied (R-RETR-011).
* **"Not expressible in the shipped schema — arithmetic rather than effort"** — A.7a's own answer
  builds, validates and serialises today (R-RETR-010).
* L3 "broadens": for a zero-constraint query it replaces the query with the whole mailbox
  (R-RETR-006).

## Not establishable here at all

I have no live Gmail, no seeded corpus, no Baseline B or D, and no counting proxy. The following are
outside anything I could establish, and no part of this review should be read as evidence for them:

* **EV-02** (position sweep against the EP §4.4 corpus, holdout seed, two seeds within CI,
  DISC-04 + PERF-01 on the same run) — **WS-16**.
* **EV-06** (recall within 2 points of Baseline B, paired McNemar, same corpus instance) — **WS-16**.
* **EV-04**'s rate and its paired hallucinated-found rate on unanswerable controls — **WS-16**.
* **EV-05**'s live-account half, and **PF-9** (whether real Gmail's `q` is thread-wide — I executed
  message-scoping against the double, which is a fact about the double) — **credentials, R-GMAIL**.
* **LEX-04**'s network-level median-≤3 bar over a family distribution — **WS-16 / R-PERF**.
* **LEX-03**'s and **ROUTE-02**'s and **ROUTE-04**'s recall/recovery/incompleteness bars, all
  `[UNSET — register at G0]` — **G0**.
* **PF-2**: whether `threads.get(format=metadata)` really omits `internalDate`. R-RETR-009's code
  path is live and wrong either way, but its frequency is PF-2's answer.
* **PF-1**: whether real Gmail returns a `threads.get` that omits its own `messages.list` hit.
  R-RETR-010's *claim* half needs no measurement; its blast-radius half does.
* **PF-14**: the real `after:`/`before:` boundary behaviour, which decides whether
  `date_margin_days` should be 1 or 0 — R-RETR-011 is about the margin not being applied, not
  about its value.
* **ADV-104 / PF-13**: the `answer_type_presence` base rate. R-RETR-007 shows the predicate is
  load-bearing for whether L1b runs at all, which raises the stakes on that measurement.
* Whether an MCP surface will ever pass the query shapes R-RETR-006 fires on. There is no MCP
  surface; I judged the finding reachable on the code that exists, and a caller that sanitised
  input would narrow but not remove it (`(rollout OR escalation)` and `newer_than:30d` are valid
  queries by any input rule).
