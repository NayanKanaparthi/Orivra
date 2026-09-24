# ROUND 15 — IMPLEMENTER — WS-04: query analysis and the lexical rungs

**Work order:** `docs/reviews/ROUND_15/WORK_ORDER.md`
**Protocol:** `docs/AGENT_LOOP.md` §5, under §5a.
**Gating reviewer:** R-RETR, on new code.

---

## 0. The state I inherited, stated first

The working tree was **not** clean when this round started. An earlier, interrupted run of this
same work order had already written `server/src/mailweave/query/` (four modules),
`server/src/mailweave/retrieval/{ladder,signals,assemble}.py`, `tests/fixtures/mailbox.py`,
`tests/test_query_analysis.py` and `tests/test_exact_signal_match.py`, and had left the suite
**red**: two round-12 standing guards failed against `retrieval/ladder.py`.

I did not restart from zero, and I did not take that work on trust either. I read all of it,
fixed what was wrong, and every claim below is a claim about the tree as it now stands, verified
by execution. Where the inherited code was wrong I say so and name the fix. The single most
important thing the inherited state got right — and the reason I kept it — is that
`tests/fixtures/mailbox.py` evaluates `q` **message-scoped**, so L1b's recovery is a real
recovery rather than a generous double.

`tests/test_lexical_ladder.py` — the file the ladder's own docstring already cited — **did not
exist**. That is the round's largest single deliverable and it is new.

Baseline in the work order: 1,950 tests. Tree as I found it: 2,122 (red). Tree now: **2,180,
green**, with `ruff`, `ruff format --check`, `mypy --strict`, `python -m tools.guards` and
`python tools/rubric_status.py --check` all clean and the rubric table untouched
(7 PASS / 0 FAIL / 0 BLOCKER / 106 NOT TESTED, 11 transitions).

---

## 1. What is common to all five rungs, and the one test that covers it

The work order asks this explicitly, so it is the first substantive section.

**A rung is a plan plus an execution, and the plan is a pure function of the parsed query.**

```
plan_ladder(parsed) -> every Probe every rung would send, before any of them is sent
```

Four properties follow for all five rungs at once, and they are the *same four* properties for
L0, L1, L1b, L2 and L3 — not five statements that happen to rhyme:

| Property | What it means | How it is made true |
|---|---|---|
| **enumerable** | every probe that ran was listable before anything was sent | `LexicalRung.plan` takes only `ParsedQuery` |
| **reproducible** | the same `(query, now, zone)` yields the same plan | no plan reads a clock, a counter or a previous rung; `analyse` takes `now` as a parameter |
| **accountable** | every id a probe observed is in `H` | the only way a rung reaches Gmail is `GmailClient.list_messages`, which records the page into the `DispositionLedger` **before** the caller sees a count |
| **declared** | the response's account of what it scanned is the ledger's | every executed probe leaves a `ScanScopeEntry` with that probe's own `q`, rung and counts |

**The one test:**
`tests/test_lexical_ladder.py::test_every_rung_shares_the_one_property_that_makes_the_ladder_accountable`.

It drives a five-query corpus end to end and asserts all four properties per query, then closes
with

```python
assert executed_rungs == set(LADDER_RUNGS)
```

so the sweep cannot pass by covering nothing — round 12's failure mode, which round 13's
reviewer found independently. The population is read from `LADDER` **by name and by count** in
`test_the_ladder_population_is_the_five_rungs_the_architecture_names`, so narrowing the scope
fails a different test than the one being narrowed.

There is a **second** cross-rung property, and it is the one LEX-02 counts at zero:
`test_every_probe_of_every_rung_names_only_constraints_the_parse_produced` asserts, over eight
parse shapes × all five rungs, that `enforced` and `dropped` name only parsed constraints, never
overlap, and — for the four rungs that carry fragments verbatim — that every constraint a probe
claims to enforce really is in its `q`. L3 is excluded from the last clause and the reason is
written down: it rewrites fragments by design, so a fragment-presence check there would be
asserting that broadening does not broaden.

**What that second test found.** Two silent drops in the inherited `BroadeningRung`:

* a date constraint MailWeave could not resolve into a window (`after:notadate` — Gmail judges
  the value, we do not) was **removed from the broadened `q`** while `enforced` went on claiming
  it. `_widened` now returns the query and the constraints it carried as one value, so the two
  cannot come apart, and the unwidenable constraint is carried unchanged. Executed by
  `test_a_date_operator_mailweave_cannot_resolve_is_still_carried_when_l3_broadens`;
* the `in:anywhere` probe's `enforced` was computed from a filter that did not match the
  fragments it actually emitted in its fallback branch. Same fix, same shape.

---

## 2. Issue #296 — the test that matters most

Gmail's own MCP server returns the right thread while omitting the message that caused the
match. There are **two** ways that can happen and this round asserts against both.

### 2.1 MailWeave drops it — asserted directly, and it does not

`ancient_thread()` is a nine-message thread whose only match is the **oldest** message, with
eight months of later traffic on top of it. A tool that returns "the thread" by taking its recent
messages returns eight messages, none of which is the answer.

`test_the_message_that_caused_the_match_is_in_the_response_even_though_it_is_the_oldest` asserts
the three things the bug destroys:

* `anc-1` is a row, `role: matched`, `depth: body_clean`, with the phrase in its fenced content;
* its `reason` is the mechanical `gmail q matched at L0: "the rollout window slipped"` — the `q`
  that admitted it, read off `HitOrigin`, not a rationale assembled later;
* `stated_total == included == 9` and the row set equals the whole thread, with
  `withheld == ()` and `partial is False`.

`test_the_oldest_message_is_at_position_zero_and_the_positions_are_chronological` closes the
other half: a present message at the wrong position is still not findable.

`test_an_exact_message_id_returns_that_message_at_body_depth_on_one_rung` is EV-05's own
acceptance sentence executed — `rfc822msgid:<m>` for a deep `m` returns `m` at body depth — plus
LEX-04's `rungs executed = 1`, plus an assertion that the id-exact route is the **ordinary** L0
probe with the ordinary `messages.list` and no special case (REG-03's concern).

`test_no_id_the_ladder_observed_leaves_the_response_without_a_disposition` runs the accounting
over the whole corpus from **outside** the process: the witness is the fixture's own
`returned_ids` log, not the ladder's account of itself.

### 2.2 Gmail drops it — and here I could not deliver what the contract asks for

I built the harder case as well: a mailbox whose `threads.get` comes back **without** a message
its own `messages.list` returned for the same query. Today MailWeave **refuses to answer**:
`assemble` raises `DispositionInvariantError` naming the id, the thread, the shape and the
escalation. No response is produced, so the bug cannot be shipped — but a refusal is not the
answer AD A.7a asks for, which is a `partial_source_failure` withheld record with a
`mailweave_get_messages` affordance.

**I could not build that answer, and the reason is arithmetic rather than effort.** For a thread
where `threads.get` states nine messages and `messages.list` put a tenth id in that thread,
`Envelope` requires `Source.stated_total` to be

* **exactly** what the `threads.get` observation stated (amendment A6,
  `_stated_total_is_the_one_the_observation_stated`), i.e. 9; **and**
* **at least** the number of distinct ids the ledger observed in that thread
  (`_stated_total_is_not_below_what_was_observed_in_the_thread`), i.e. 10.

There is no value satisfying both, so no `Source` for that thread can be constructed at all.
Independently, PART-03's phantom-remainder rule
(`_incomplete_sources_carry_a_path_to_the_rest`) refuses any withheld record charged to a source
that reports itself complete — which this one does, on its own enumeration's terms. I verified
both by execution, not by reading.

Expressing the disagreement needs a schema that can say *complete as the thread enumeration
reported, incomplete against what was retrieved*. That is a **contract change** (PART-03, R-08),
which AGENT_LOOP §8 says is not an implementer's call. **Escalation, with an executed
reproduction:** `test_a_thread_map_that_omits_one_of_its_own_hits_is_refused_rather_than_shipped`.
It belongs to **WS-11** (disclosure), and **PF-1** is the measurement that says whether real
Gmail produces the shape at all.

What I did do is make the failure diagnosable at the line where it is visible:
`_refuse_a_source_that_omits_its_own_hits`. Before, the operator saw a downstream
"phantom remainder (PART-03)" and would have blamed the assembly.

---

## 3. L1b — the rung that makes §2 possible

`test_l1b_recovers_a_thread_whose_constraints_live_in_different_messages` is the plan's
acceptance row and PF-9's shape: `from:dev@team.example cutover` against a thread where `spl-1`
is from `dev` and `spl-2` contains `cutover`. L1 returns **zero** — asserted, not assumed. L1b
sends one `messages.list` per constraint, intersects on `threadId`, and the thread comes back
with both messages as rows.

The fixture's fidelity is asserted separately, before L1b is credited with anything:
`test_gmail_cannot_match_a_constraint_spread_across_two_messages_of_one_thread` executes RO F2
against the double itself, and `test_the_double_refuses_an_operator_it_does_not_evaluate`
executes the double's refusal to ignore an operator — an ignored operator silently widens the
query and makes a rung look successful.

**The inherited `Decomposition` docstring made a bound I had to make good on.** It claimed the
intersection can only *under*-name a thread, never lose a message, because a probe reports the ids
it was first to admit. I built the case that reaches it — six messages that each satisfy both
constraints alone, so both probes admit nothing new and the intersection is empty — and asserted
that all six are in `H`, disclosed, and rows of the response:
`test_l1b_can_only_under_name_a_thread_whose_messages_are_already_in_H`. That name was cited by
the docstring and did not exist; it does now.

**A defect §3 turned up.** `_asked_for` was reading L1b's per-constraint probes as *dropped*
constraints, because `Probe.dropped` meant two different things at two rungs. For
`newer_than:60d procurement` — which L1 matches with **both** constraints enforced — the response
reported `dropped: [newer_than]` and `term_coverage: 0.5`. `Probe.relaxes` now marks the
distinction structurally (true at L2 and nowhere else) rather than by a rung check at the reader.
Executed by `test_a_decomposition_probe_is_not_reported_as_a_dropped_constraint`.

A second defect in the same function: the scoping was `ids_admitted` (the delta into `H`) rather
than `ids_returned` (the page's own count), so a relaxation whose hits an earlier rung had
already recorded went unreported — the ROUTE-04 case itself. Its own docstring said "a relaxation
probe that found nothing", which is a statement about the page. Fixed to match.

---

## 4. L2 relaxation, and `empty_diagnosis`

`test_every_probe_l2_would_send_is_listable_before_any_of_them_is_sent` asserts an **equality**,
not a containment: the published plan and the executed sequence are the same list in the same
order, each step naming the constraint it dropped. A containment would be satisfied by a rung
that planned the whole mailbox and sent one probe.

`test_relaxation_drops_exactly_one_constraint_per_probe` and
`test_the_relax_probe_budget_binds_at_min_k_six_and_names_what_it_did_not_reach` cover A.7's
`max_relax_probes = min(k, 6)`.

**ADV-105's third state was reintroduced through the other door, and I closed it.**
`RelaxationRung.untried_drops` answered from the *plan*, so a drop no probe reached because the
rung never executed — dropping a single-constraint query's only constraint renders an empty `q`,
which asks Gmail for the whole mailbox — was reported as *every drop tried, none restored*. That
is exactly the conflation the third state exists to prevent. `untried_drops` now takes `probed`
as a parameter and `LadderRun.untried_drops` has one writer, at the end of the run, reading what
ran. Executed by `test_a_drop_no_probe_reached_is_untried_even_when_the_budget_was_not_the_reason`.

**`empty_diagnosis` was also emitted on responses that were not empty**, saying *no single
dropped constraint restores results* about queries whose constraints were never relaxed. ROUTE-04
scopes the field to zero-hit outcomes. It is now `None` when the query answered, and the number
read is `LadderRun.unrelaxed_evidence_count` — new — rather than `evidence_count`, because:

* disclosure alone counts the threads a broad L1b probe *obliged* the ledger to carry, which
  suppresses the diagnosis on the queries that most need it;
* `evidence_count` includes L2's own hits, which suppresses it the moment a relaxation
  **succeeds** — the ROUTE-04 case.

All three states are executed: `..._names_the_single_drop_that_restores_results` (which also
asserts the diagnosis survives its own success, alongside `outcome: answered`),
`..._reports_that_no_single_drop_restores_results`, `..._says_incomplete_when_the_probe_budget_ran_out`,
plus `test_a_response_that_found_something_carries_no_empty_diagnosis`.

`outcome` now needs **both** halves — rows in the payload *and* evidence the query produced — so
a response carrying only the threads a broad decomposition probe obliged the ledger to disclose
is `inconclusive`, not `answered`.

---

## 5. The two standing guards that were red, fixed structurally

Both failures were in `retrieval/ladder.py`. Neither guard was weakened.

**`test_the_two_scope_settings_cannot_be_supplied_independently`** requires
`include_spam_trash` to be read off the same object the `query` came from. `Probe.q` is now
`Probe.query`, so the call site reads `query=probe.query, include_spam_trash=probe.include_spam_trash`.
A `Probe` is a *stronger* form of round 12's pairing than the harness's `MailboxScope`, because
its flag is **derived from** its query (`widens_beyond_the_default_mailbox`) rather than declared
beside it. `test_a_probe_derives_its_mailbox_scope_from_its_own_query_and_cannot_disagree`
executes it at the wire, on L3's whole-mailbox probe — the only probe in the ladder that leaves
the default mailbox.

**`test_no_module_spells_a_mailbox_scope_operator_outside_the_scope_enum`** — the ladder wrote
`"in:anywhere"` three times, once in a docstring (the sweep reads every string constant, prose
included). All three now go through `mailweave.constants.ANYWHERE_OPERATOR`.

---

## 6. Every docstring claim about coverage, with its executed evidence

The work order asks for this list, and I made it **mechanical** rather than a list I wrote by
hand: `test_every_test_a_source_docstring_names_exists` reads every string constant in both
source trees, extracts every `test_…` identifier — including ones a formatter wrapped
mid-identifier, which are exactly the longest and most aspirational names — and requires each to
resolve to a real test function or test module. It fires on a planted instance
(`test_the_citation_sweep_fires_on_a_planted_instance`), because a sweep that has never fired is
a sweep nobody has tested.

**It found four stale citations when I first ran it**, all in round-15 code:

| Citation | State when found | Now |
|---|---|---|
| `test_every_rung_shares_the_one_property_that_makes_the_ladder_accountable` | did not exist | written (§1) |
| `test_l1b_can_only_under_name_a_thread_whose_messages_are_already_in_H` | did not exist | written (§3) |
| `test_the_returned_fetch_stamp_is_the_one_the_observation_sealed` | did not exist | written, in `tests/test_gmail_client.py` |
| `test_the_relaxation_order_covers_every_constraint_kind` | wrong name (`…_this_parser_produces`) | docstring corrected |

The citations that now stand, all executed:

| Module | Citation |
|---|---|
| `mailweave/gmail/client.py` | `test_the_returned_fetch_stamp_is_the_one_the_observation_sealed` |
| `mailweave/query/identifiers.py` | `test_the_identifier_lexicon_has_exactly_the_four_published_kinds` |
| `mailweave/query/operators.py` | `test_every_token_of_every_fidelity_case_is_classified_exactly_once`, `test_query_analysis` |
| `mailweave/query/timepolicy.py` | `test_an_explicit_absolute_date_is_not_widened` |
| `mailweave/retrieval/ladder.py` | `test_every_rung_shares_the_one_property_that_makes_the_ladder_accountable`, `test_l1b_can_only_under_name_a_thread_whose_messages_are_already_in_H`, `test_lexical_ladder`, `test_the_relaxation_order_covers_every_constraint_kind_this_parser_produces`, `test_no_module_spells_a_mailbox_scope_operator_outside_the_scope_enum`, `test_the_two_scope_settings_cannot_be_supplied_independently` |
| `mailweave/retrieval/signals.py` | `test_the_exact_signal_definition_is_closed_at_three_branches`, `test_the_evaluator_takes_no_frequency_input`, `test_branch_precedence_is_ea_then_eb_then_ec` |

One coverage claim is **not** a test citation and is worth naming here because it is the largest
one this round makes: `retrieval/assemble.py`'s module docstring says what the assembly
deliberately does **not** do — no `not_found`, no score, no A.9a degradation ladder. Executed by
`test_this_round_never_claims_not_found` and `test_no_row_this_round_produces_carries_a_number`.

That second test exists because writing this section caught me making the defect it is about.
My first draft of this paragraph said the absence of scores was safe because "`Envelope` refuses
a fabricated one". It does not: `MessageRow.score` is an optional field with **no validator
behind it**, and the only thing keeping a number out is that no code path writes one. The claim
was wider than the code, so the code now has a test instead of the claim having an adjective.

---

## 7. Other verified behaviour

* **Operator-parse fidelity table** (inherited, re-verified): `FIDELITY_TABLE` is `parametrize`d
  over `OperatorName` and bound to it by
  `test_the_fidelity_table_covers_every_operator_the_lexicon_claims`, so a member added without
  a row fails. Each operator is asserted twice — as a parse, and **at L1's executed `q`**,
  because fidelity is a statement about what is sent.
* **`exact_signal_match`** (inherited, re-verified): closed at three branches by execution, no
  frequency input by signature reflection, branch precedence E-a → E-b → E-c on a query carrying
  all three candidates, and the property all three share — a candidate that was not *executed*
  never fires — asserted **once over all three**.
* **D.3 rule 1b / ADV-004's ordering fix**, which the inherited code implemented and nothing
  executed. Now executed both ways:
  `test_a_missing_answer_type_refuses_the_l0_stop_that_would_otherwise_fire` (the phrase matches,
  verifies locally, would stop — the query asks *when*, the hit carries no date-like token, and
  the stop is refused) and `test_the_same_stop_fires_when_the_answer_type_is_there`. The tri-state
  `present is None` is a third state, not a missing one:
  `test_a_query_with_no_answer_type_cue_is_a_third_state_and_not_a_missing_one`.
* **A.6a time policy** (inherited, re-verified): relative windows emitted twice (operator form and
  `window_utc`), widened by `DATE_MARGIN_DAYS` and declared; explicit absolute dates **not**
  widened; every published relative expression executed; `contains_ms` on integer epoch ms.
* **Caps.** `test_hits_beyond_max_hit_threads_become_withheld_records_with_an_affordance` executes
  A.7a's worked example on 14 hit-bearing threads against `max_hit_threads = 12`.
  `test_a_hit_beyond_max_body_fetches_is_a_stub_row_and_not_a_withheld_record` executes the
  distinction A.7a warns makes withheld lists meaningless.
* **LEX-02's last clause.** `constraint_coverage` on every matched row, derived from the probe
  that admitted the id, through the one function that computes it
  (`signals.constraint_coverage_of`, which `assemble` previously duplicated inline — a second
  derivation of one fact). `test_every_matched_row_names_the_constraints_its_admitting_query_enforced`.
* **EV-05's recency half, at the width this round can establish.**
  `test_a_row_the_date_window_does_not_contain_is_declared_rather_than_passed_off`: for every id
  the mailbox handed over whose `internalDate` falls outside the declared `window_utc`, the
  response either withholds it with a reason and an affordance, or discloses it with a
  `constraint_coverage` that does **not** claim the date constraint.
* **Fixtures carry no real mail.** Executed, not asserted in prose:
  `test_no_fixture_in_this_file_carries_anything_that_could_be_real_mail` requires every address
  in the reserved `.example`/`.invalid` TLDs and refuses formatted identifiers. Its digit checks
  are deliberately shaped to ignore `internalDate` epochs, which are the point of the fixture.
* **Fixture fidelity, tightened.** The inherited double matched participants by *substring*, so
  `from:ops@team.example` matched `bulkops@team.example` — permissiveness in a double is a test
  passing for the wrong reason. It now matches the whole address, its local part, or a display
  word: stricter than Gmail, which can only make a rung look *less* successful.
* **Dead code removed** rather than left as a dead abstraction: `signals.term_coverage` (a
  zero-caller wrapper over an identical `ParsedQuery` method — a second derivation of one fact),
  `timepolicy.free_text_of`, `assemble.coverage_index`. Also removed one unexplained non-English
  entry from the published `STOPWORDS` list, which is a closed published table.

---

## 8. What I could **not** establish, and the workstream that would make it reachable

Under §5a this is a correct answer, not a gap. Nothing below was fixed this round.

| Not established | Why it is not reachable today | Where it becomes reachable |
|---|---|---|
| **Position-sweep recall against the full-dump ceiling** (the plan's own acceptance column; EV-02, EV-06) | needs the seeded ~100-message corpus, Baseline B run interleaved (PROC-04), and reviewer-chosen held-out seeds. None of that machinery exists | **WS-16** |
| **EV-05 on the live account** | its acceptance says "on the live account **and** on the seeded corpus". Only the fixture half exists; consent status is still unknown (`RESUME.md`) | **credentials**, then R-GMAIL |
| **PF-9 as a measurement** | I executed Gmail's message-scoping against the double, which is a fact about the double. Whether real Gmail's `q` is thread-wide is a live observation | **PF-9** on the seed account |
| **The `not_found` branch of OD-2** | `not_found` requires no applicable rung untried; L4/L5/L6/LR are not built, so every empty result here is honestly `inconclusive`. The rule is asserted only in the negative | **WS-10** |
| **`exact_signal_match` per-family firing-rate bound** (A.8a's countermeasure against a broad predicate) | pre-registered at G0 against EP families that do not exist | **WS-16**, registered at **G0** |
| **`answer_type_presence` base rate** (ADV-104: a predicate true 97 % of the time is a constant) | needs a random sample of the seed corpus, measured against quote-stripped bodies | **PF-13** |
| **LEX-04's cost bar** (`network Gmail calls ≤ median 3`) | must come from network-level counts, not self-reports. I assert `api_calls <= 3` from the meter, which is a self-report | **WS-16**'s counting proxy, verified by R-PERF |
| **The A.7a record-and-affordance answer to a `threads.get` that omits its own hit** | not expressible in the shipped envelope schema — see §2.2 for the arithmetic. Contract change, escalated | **WS-11** (PART-03, R-08); **PF-1** says whether Gmail produces the shape |
| **`participant_authorship` and `duplicate_thread_concentration`** (A.8 sufficiency signals) | not built. Both need thread structure and authorship, which is the thread map | **WS-05** |
| **`window_containment` as a reported signal** | the predicate exists and is tested (`TimeWindow.contains_ms`); nothing puts it on the wire | **WS-10/WS-11** |
| **The trace fields** `ExactSignal.as_trace_fields` / `AnswerTypePresence.as_trace_fields` | A.8a requires the field and D.10 names both; **neither has a production consumer today**. Kept because the shapes are normative and both are tested; named here so a reviewer does not have to discover it | **WS-13** |
| **`more_pages` / `scan.max_pages` widening on a ladder run** | `max_pages_per_query = 1` and no corpus query exceeds one page, so no ladder test exercises a continuation token. The client's own paging is covered in `tests/test_gmail_client.py` | a multi-page corpus, **WS-16** |
| **`map_id` accounting on a ladder-built source** | handles are WS-06; sources here carry `map_id: None`, so `_a_claimed_map_accounts_for_every_message` is not exercised by this round | **WS-06** |

Two more, stated plainly because they are judgements rather than absences:

1. **`not_tried[].why` is `not_applicable` for every skipped lexical rung**, including L2 and L3
   when the escalation policy declined to run them because evidence already existed. The closed
   vocabulary of D.2 has no value for "the policy declined", and `budget | cap | timeout | error`
   would all be false. This never violates the machine-checkable OD-2 rule because this round
   never emits `not_found` — but a reviewer should decide whether the vocabulary needs a fourth
   value, which is a schema question and therefore not mine.
2. **L4, L5, L6 and LR are absent from `not_tried` entirely**, rather than listed as
   `not_applicable`. Claiming they could not have helped would be the false half of the OD-2
   distinction. The consequence is carried by never emitting `not_found`.

---

## 9. Rubric

I marked nothing. `docs/reviews/FINDINGS_LEDGER.md` and `docs/reviews/RUBRIC_TRANSITIONS.md` are
untouched. `python tools/rubric_status.py --check` is unchanged at
**7 PASS / 0 FAIL / 0 BLOCKER / 106 NOT TESTED, 11 reviewer transitions recorded**.

WS-04 targets LEX-01..04, EV-02, EV-04..06, ROUTE-02..04. My own reading of what a reviewer will
find reproducible, offered as a hypothesis and not as a claim:

* **LEX-01, LEX-02, LEX-03, ROUTE-03** have executed evidence on fixtures for every clause.
* **LEX-04** has everything but the network-level cost bar (§8).
* **EV-05** has its fixture half; the live half is blocked on credentials.
* **ROUTE-04** has all three `empty_diagnosis` states plus the OD-2 scoping; the registered
  incomplete-rate ceiling is a G0 item.
* **EV-02, EV-04, EV-06, ROUTE-02** need the harness and a reviewer-built case set. Nothing here
  should be read as evidence for them.

---

## 10. Gates, as run

```
ruff check .                     All checks passed!
ruff format --check .            153 files already formatted
mypy --strict                    Success: no issues found in 127 source files
python -m tools.guards           guards clean: forbidden-import, generative-client,
                                 gmail-endpoint, ground-truth-isolation, scope-literal,
                                 unaudited-disk-write, unwrapped-http-client over server/src
pytest -q -m "not network"       2,180 passed
python tools/rubric_status.py    PASS 7 / FAIL 0 / BLOCKER 0 / NOT TESTED 106
  --check                        reviewer transitions recorded: 11
```

`generative_llm_calls = 0` is enforced by the `generative-client` import guard, which is in that
clean list. Nothing in `mailweave/query/` or `mailweave/retrieval/` imports a model, embeds
anything, or consults corpus frequency; `evaluate_exact_signal`'s signature is asserted to carry
no frequency parameter, which is the only place such a dial could be wired in.

The retry and backoff constants were not touched. They remain the open owner decision recorded in
`RESUME.md`.

---

## 11. Reintroduction discipline

Every source edit this round was applied by a script that **asserted its anchor matched exactly
once before applying it** and **asserted the file changed** before writing. Two edits aborted on
a failed anchor assertion and were re-derived from the real file rather than forced — which is
the failure mode round 12 produced three false greens with and round 13's reviewer hit
independently.

The citation sweep of §6 is the standing form of the same discipline for the *other* half:
anchors keep an edit honest about the code; the sweep keeps a docstring honest about the tests.
