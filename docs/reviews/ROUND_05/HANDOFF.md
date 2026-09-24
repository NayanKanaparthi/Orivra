# ROUND 05 — Implementer handoff

**Implementer, 2026-08-31.** Scope: `docs/reviews/ROUND_05/WORK_ORDER.md`, three parts.
Amendment A3 built; the fifteen never-verified Round-1 findings worked one by one against the
**current** code; the Round-4 mediums closed or honestly bounded.

**Gate state.** `make check` clean: ruff, `ruff format --check`, `mypy --strict` (62 files),
**557 tests** (was 406), seven source guards (was six), rubric gate. Rubric unchanged: 7 PASS,
0 FAIL, 0 BLOCKER, 106 NOT TESTED, 9 transitions. No row added to `RUBRIC_TRANSITIONS.md` or
`FINDINGS_LEDGER.md`.

## How to read this

Every row states **whether a fix already existed**, what the current code did when I ran the
original reproduction myself, and the failing-test-first evidence. Where a fix already existed I
verified it by **reintroducing the defect** and recording which tests broke; that is the
"verified by reintroducing" obligation, and it is quoted per row.

The headline of Part 2 is not comfortable and should not be read as one: **of the fifteen, four
were genuinely fixed and adequately tested, one had been addressed as documentation only, eight
had no fix at all, and two are not an implementer's to close.** The Round-2 handoff's account of
its own work was accurate for the four it names and silent about the rest.

---

# Part 1 — amendment A3

| ID | Verdict | What changed |
|----|---------|--------------|
| **A3** | **BUILT** | `Source._every_position_lies_inside_the_thread` (`envelope/wire.py`) enforces `0 <= p < stated_total` for every `MessageRow.position` and every position in a `CollapsedRun`. `CollapsedRun._run_is_self_consistent` gained the run's own lower bound (`positions=(-3, -1)` was constructible). Out-of-range **raises**; nothing is clamped. |

**Where it sits and why.** The validator is ordered *after* `_one_position_holds_one_disposition`,
so a shape violating both still reports Round 4's occupancy clash first, with its Round-4 error
text unchanged. That was deliberate: the work order requires the occupancy checks to pass
unchanged, and pydantic runs `mode="after"` validators in definition order.

**Failing-test-first.** Eight tests were written before the validator existed; six failed
(`test_a_run_outside_the_thread_it_claims_to_map_is_refused`,
`test_a_single_row_beyond_stated_total_is_refused`,
`test_the_last_position_of_a_thread_is_inside_it_and_the_next_one_is_not`,
`test_an_out_of_range_position_raises_rather_than_being_moved`,
`test_the_position_bound_survives_the_full_builder_path`, and both property tests). Two — the
run's own lower bound and the `CollapsedRun(-3,-1)` refusal — passed only after the
`CollapsedRun` half landed.

**Reintroduction check.** With both range conditions replaced by `if False:`, seven tests fail
and the rest of the suite passes. The bound is therefore load-bearing and is not duplicated
anywhere.

**Acceptance, item by item.**

- R-RETR's proof — `stated_total=5`, run at `positions=(900, 904)` — raises with
  `collapsed run (900, 904)` and `0 <= p < 5` in the message
  (`test_a_run_outside_the_thread_it_claims_to_map_is_refused`), and again through a real
  ledger and `EnvelopeBuilder` (`test_the_position_bound_survives_the_full_builder_path`).
- R-ARCH-013's single-row corroboration (`stated_total=3`, `position=900`) raises.
- The property test draws `positions` from `[-4, 20]` and `stated_total` from `[1, 8]`
  **independently**, so roughly half the examples are legitimate and half are not and nothing
  hands the checker the answer. Row construction sits inside the `try` because a negative
  position is refused by `MessageRow` itself: A3 has a lower half and an upper half and the
  property is over the pair.
- Round 4's occupancy checks pass unchanged — the validator is untouched and all six of its
  dedicated tests are unmodified.

**One Round-4 test did change, and I want it read rather than skimmed.**
`test_a_source_that_builds_never_holds_two_dispositions_at_one_position` generates run starts in
`[0, 12]` while `stated_total` is the member count, so A3 legitimately refuses examples that
R-RETR-002 alone would not. Its **success branch — where the R-RETR-002 property is actually
stated — is byte-for-byte unchanged**. Only the refusal branch grew a second admissible cause
(`or any(not 0 <= position < total for position in slots)`). If a reviewer thinks that weakens
the property, the disagreement is visible in one line of diff.

---

# Part 2 — the fifteen never-verified Round-1 findings

## Summary table

| ID | Was a fix actually there? | Round-5 action |
|----|--------------------------|----------------|
| R-ARCH-001 | **Yes** — real, tested | Verified by reintroduction; no change |
| R-ARCH-002 | **Yes** — real, tested | Verified by reintroduction; no change |
| R-ARCH-003 | **Documentation only** | **Fixed in code** + 3 locales + 2 false-positive guards |
| R-ARCH-004 | **Yes** — real, strongly tested | Verified by reintroduction; no change |
| R-ARCH-006 | **No** | **Fixed**: seventh guard, `unwrapped-http-client` |
| R-ARCH-008 | Not an implementer's to close | Test added pinning the shipped reading; ruling still owed |
| R-DISC-002 | **Yes** — real, tested | Verified by reintroduction; no change |
| R-DISC-003 | **No** | **Fixed**: wire field order |
| R-DISC-004 | **No** | **Fixed**: all 10 renderers + OD-3 floor, 50 tests |
| R-DISC-005 | **No** | **Fixed**: RFC-3339 validation on both R-08 stamps |
| R-DISC-006 | **No** | **Fixed**: row-level and envelope-level validation |
| R-DISC-007 | Not an implementer's to close | Same test as R-ARCH-008 |
| R-SEC-004 | **No** | **Fixed** in `check_url`; client-level residue documented |
| R-SEC-006 | **No** | **Fixed**: shape bound before construction |
| R-SEC-007 | **No** | **Fixed**: typed error, depth bound below the recursion guard |

**Four of fifteen were genuinely fixed. Eight had nothing. One was documented but never fixed.
Two need a ruling.**

---

## R-ARCH-001 · quote chains mislabelled as `signature` — HIGH

**Was it fixed? Yes, and properly.** `content/quotes.py` classifies a `hidden`/`signature`
fragment on its own shape via `looks_quoted()`, with a latch (`in_quoted_chain`) so quoted prose
carrying no marker of its own does not fall back into `signature`. The corpus
(`tests/fixtures/reply_chains.py`) carries the Outlook header block and the forward, and
`test_each_removal_is_declared_under_the_kind_it_actually_is` asserts the counts sit under the
right kind — not merely that a reduction exists.

**Reintroduction.** Collapsing the branch back to `signature += len(content)` (Round 1's
behaviour) fails four tests:
`test_each_removal_is_declared_under_the_kind_it_actually_is[outlook_header_block]`,
`[original_message_separator]`, `[forwarded_message]`, `[html_gmail_blockquote]`.
**No change made.**

## R-ARCH-002 · undelimited corporate signature silently retained — HIGH

**Was it fixed? Yes.** `_trailing_signature_start` finds a sign-off with body text above it, few
short lines below, and cuts there. `SIGNATURE_NO_DELIMITER` and
`SIGNATURE_NO_DELIMITER_AFTER_QUOTE` are in the corpus, with two dedicated false-positive tests
("Thanks," at the top of a message; a long paragraph under a sign-off word).

**Reintroduction.** Forcing `cut = None` fails five tests, including
`test_the_undelimited_signature_case_that_previously_removed_nothing` — the one named for this
finding. **No change made.**

## R-ARCH-003 · non-English attribution line left dangling — MEDIUM

**Was it fixed? No — it was written down.** The Round-1 report's own "required fix" was a
fixture, not code, and the fixture existed (`FRENCH_ATTRIBUTION`, `known_gap=...`). Running it
against current code reproduced the finding exactly:

```
reply = "D'accord, allons-y.\n\nLe mar. 25 août 2026 à 15:14, Priya Shah <...> a écrit :"
```

The header of the quoted chain sat in `body_clean`, declared as neither quote nor noise. The
ledger keeps it OPEN as MEDIUM, so documentation is not a close.

**Fixed.** `quotes.py` gains `_ATTRIBUTION_VERBS` (eleven locales), a tail-position pattern
(`_ATTRIBUTION_TAIL_RE`) because German and Dutch put the sender *after* the verb, and
`_trailing_attribution_start`. The line is counted as `quoted`, which is what it is.

**Four conditions, because the cost of a false positive here is deleting the sender's own
sentence:** last non-empty line only; body text above it; the line must carry a sender address or
a date/time (`_ATTRIBUTION_EVIDENCE_RE`); and a quoted chain must actually have been found.

**Failing-test-first.** French, German and Spanish cases were added to the corpus first; all
three failed `test_the_reply_survives_and_the_chain_does_not`. Two false-positive cases were
added at the same time and passed before *and* after — including the hard one,
`SENDER_COLON_LINE_ABOVE_A_QUOTE`, where a real quoted chain *is* present so only the missing
address/date keeps "This is what the vendor wrote:" in the body.

`test_the_known_gap_is_still_the_only_one_and_is_still_declared` is replaced by
`test_the_known_gap_list_is_empty_and_the_mechanism_still_works`: the list is now empty, and
`ASSERTED == CORPUS` keeps the mechanism as the thing that decides it rather than a comment.

**Residue, stated:** the verb list is a list. A locale not on it still dangles. Three locales are
in the corpus; eleven verbs are in the pattern; the other eight are untested.

## R-ARCH-004 · declared reductions checked for presence, not magnitude — MEDIUM

**Was it fixed? Yes, and it is one of the better mechanisms in the tree.**
`content/reductions.py::reconcile` compares each stage's declared removal against the shrinkage
it produced and raises `ContentProcessingError` on disagreement; the number that reaches the wire
is the *measured* delta. `test_a_stripper_that_under_reports_its_removal_fails_the_pipeline`
reproduces R-ARCH-004's monkeypatch verbatim, and a hypothesis property asserts declarations
never understate shrinkage.

**Reintroduction.** Neutering the comparison (`if False:`) fails
`test_a_stripper_that_under_reports_its_removal_fails_the_pipeline` with `DID NOT RAISE`.
**No change made.**

## R-ARCH-006 · no guard forbids direct `httpx.Client()` — LOW

**Was it fixed? No.** Six guards were registered; none looked at client construction. The
docstring's "the only supported way to get an HTTP client" was enforced by nothing.

**Fixed.** Seventh guard `unwrapped-http-client` (`tools/guards/sweeps.py`), allowlisting exactly
`mailweave/net/egress.py` — the same shape `unaudited-disk-write` uses for the token store. It
reuses the per-scope name resolution, so a module alias, a `from`-import alias and a plain
rebinding all resolve.

**Failing-test-first.** Six planted shapes, all reporting **0 violations** before the guard
existed; each reports exactly 1 now. Four "does not fire on the legitimate shape" tests were
written alongside: `build_client()` call sites, an unrelated class named `Client`, an
`httpx.BaseTransport` subclass, and the real tree.

**One existing test changed.** `test_the_round_one_bypass_files_no_longer_pass_the_guards`
asserted `{v.guard for v in violations} == set(GUARDS)`. R-SEC-001's four files construct no HTTP
client, so asserting the seventh guard fires on them would be asserting coverage the fixture does
not exercise. The expectation is now a named `R_SEC_001_GUARDS` frozenset plus
`R_SEC_001_GUARDS < set(GUARDS)`.

**Bound, in the docstring:** a client from a data structure, a factory return, `getattr`, a
third-party library's own sockets, or a subclass instantiated by its own name. The guard bounds
the ordinary way a client gets built without the allowlist; `AllowlistTransport` and the capture
are the enforcement.

## R-ARCH-008 / R-DISC-007 · the D.2-vs-R-05 `included` arithmetic — LOW

**Was it fixed? It cannot be by an implementer.** Both reviewers filed it as needing an
orchestrator ruling, and none is on record. The divergence is real and is arithmetic: contract
R-05 makes `included_as_stub` a **subset** of `included` (7 bodies + 35 stubs → `included=42`);
AD D.2's worked example makes them **disjoint** (`included=7`, `included_as_stub=35`, summing to
42). The code follows R-05.

**What I did instead of ruling.** Added
`test_the_included_arithmetic_follows_contract_r05_and_not_ad_d2s_worked_example`, which builds
the 7-plus-35 case both ways, asserts the R-05 shape builds and the D.2 shape is refused, and
names in its docstring both readings, the fact that no ruling exists, and the two places that
change if the ruling goes the other way (this test and
`Source._counts_match_the_payload`). Previously the ambiguity lived only in a Round-1 handoff and
a code comment; it is now visible to anyone who runs the suite.

**Still owed: an orchestrator ruling.** Nothing here closes it.

## R-DISC-002 · `mark_self_truncated()` bypassed the ceiling — MEDIUM

**Was it fixed? Yes.** `Envelope._self_truncation_is_verified_against_the_ceiling` measures the
assembled payload and refuses both an oversized response (flag or no flag) *and* a truncation
claim with no ladder artifact behind it. Three tests cover it, including R-DISC-002's own
27,000-tokens-against-9,000 reproduction.

**Reintroduction.** Exempting `truncated_by is not None` from the ceiling and disabling the
artifact check fails
`test_declaring_self_truncation_does_not_let_an_oversized_response_ship`,
`test_a_truncation_claim_with_nothing_removed_is_refused_even_under_the_ceiling` and
`test_an_oversized_response_is_refused_whether_or_not_it_claims_truncation`.
**No change made.**

## R-DISC-003 · bulk content serialised before the partiality signals — MEDIUM

**Was it fixed? No.** `Envelope` still declared `sources` fourth, ahead of `partial`, `withheld`
and `retrieval_report`.

**Fixed.** Field order is wire order in pydantic, so the declaration order changed to
`schema_version, fence_nonce, asked_for, partial, withheld, retrieval_report, sources, ...`. No
field added, removed or renamed.

**Failing-test-first.** `test_the_partiality_signals_are_serialised_before_the_bulk_content`
(parsed key order) and `test_a_reader_truncated_mid_payload_has_already_seen_the_partiality_signals`
(byte offsets in the serialised text — the level at which a streaming client actually fails) both
failed before; a third test pins the field *set* so a reorder cannot become a rename.

**Deliberately not done: the root-level summary block** the finding offered as an alternative.
Every number in it would restate a fact the payload already carries, and this codebase derives
`included`, `partial` and `withheld` from the payload rather than asserting them beside it — a
summary block is exactly the assertion-beside-the-enumeration shape R-DISC-001 was filed against.
The reasoning is in a comment above the fields, so the choice is arguable rather than invisible.

## R-DISC-004 · 8 of 10 `Reason.render()` variants untested; OD-3 shape never exercised — MEDIUM

**Was it fixed? No, not in any part.** `grep` over `tests/` still returned zero hits for
`Rfc822MsgId`, `ReplyParentOf`, `ReplyChildOf`, `SemanticScore`, `HistoryAddition`,
`RequestedById`, `SnippetContains` and `WindowOffset`, and no test constructed a
`PARENT`/`CHILD`-at-`STUB` row. This is the finding that blocks `PART-07`, and it had been open
for four rounds with nothing done.

**Fixed.** New `tests/test_reason_coverage.py`, 50 tests. It is deliberately **not** "each
renderer was called once":

- **completeness** — `{v.kind for v in VARIANTS} == set(ReasonKind) == ALL_REASON_KINDS`, so an
  eleventh kind added without a test fails this module rather than passing silently;
- **participation** — every field of every reason is mutated in turn (enum members swapped,
  strings suffixed, numbers incremented) and the render **must change**. A renderer that ignores
  a parameter or returns a constant fails. This is PART-07's "mechanical, never decorative" as a
  property rather than a spot-check;
- **distinctness** — no two kinds render the same string, so PART-07's degenerate strategy is
  visible;
- **wire form** — for all ten: `reason` serialises to `render()`, `reason_detail` carries the
  typed dump, every field reaches the wire, and each round-trips through the discriminated union;
- **OD-3 floor, end to end** — a `MATCHED` reversal row with its reply parent and child as `STUB`
  rows, built through a real `DispositionLedger` and `EnvelopeBuilder`: the stubs are disclosed
  and not withheld, each names why it is present and carries a working `unabridged` affordance,
  role and depth are independent (a `PARENT` promoted to `body_clean` builds, per OD-3's
  "depth is earned"), and the shape survives serialisation with its reasons intact;
- **all seven roles** carried by rows that actually build — Round 1 only checked the enum had
  seven members.

**Verification by reintroduction** (this one matters most, so I broke it deliberately). Two
planted defects in `reasons.py` — `WindowOffset.render` dropping `offset`, and `SnippetContains`
returning `"you may find this useful"` — fail three tests:
`test_every_reason_renders_a_non_empty_mechanical_string[snippet_contains]` and
`test_every_parameter_of_every_reason_participates_in_its_rendering[snippet_contains]` and
`[window_offset]`. Restored, all 50 pass.

**What this does not do.** It does not promote `PART-07`; that is a reviewer's call, and the
criterion's coverage half is R-DISC's to judge.

## R-DISC-005 · `fetched_at` accepts any non-empty string — LOW

**Was it fixed? No.** `fetched_at: str = Field(min_length=1)`, unchanged.

**Fixed.** `wire.parse_instant` requires an ISO-8601 date **and** time **and** a UTC offset;
`Source._freshness_stamps_are_instants_in_order` applies it to `fetched_at` and `verified_at` and
refuses a verification that precedes its own fetch.

**Failing-test-first.** Six rejection cases (including the finding's own
`"not-a-real-timestamp-at-all"`, a bare date, and an offset-less instant) plus the two
`verified_at` tests all failed before; three acceptance spellings passed throughout.

**Deliberately not checked: whether the instant is plausibly recent.** A "not in the future" rule
would make a valid response depend on the checking machine's clock, and clock skew failing a
response is a worse defect than the one it catches. The reasoning is in the function's docstring,
not only here.

## R-DISC-006 · `constraint_coverage` is a live field with no validator — LOW

**Was it fixed? No.** Still `tuple[str, ...] = ()`, still zero references in `tests/`.

**Fixed, at two levels.** `MessageRow._constraint_coverage_is_a_set_of_named_constraints` refuses
an unnamed or repeated entry. `Envelope._constraint_coverage_names_constraints_the_query_carried`
refuses a row claiming coverage of a constraint the response's own `asked_for` never carried —
where the admissible set is `enforced ∪ {dropped}`, because a relaxed-away constraint is still one
the user wrote and a message may legitimately satisfy it.

**Failing-test-first.** `test_a_row_cannot_claim_coverage_of_a_constraint_that_was_never_in_the_query`
and `test_a_row_cannot_list_the_same_constraint_twice` both failed before; the two positive cases
(an enforced constraint, a dropped one) passed before and after.

**This is the one Part-2 fix I am least sure belongs to this round** — see "Where this work is
weakest".

## R-SEC-004 · `check_url` raises `idna.core.InvalidCodepoint`, not `EgressBlocked` — MEDIUM

**Was it fixed? No.** Reproduced immediately on current code:

```
CRASH idna.core.InvalidCodepoint  https://xn--gmailgoogleapis-3ye.com/
CRASH idna.core.InvalidCodepoint  https://xn--a-ecp.ru/
CRASH idna.core.IDNAError         https://xn--0.pt/
```

**Fixed.** `check_url` reads `scheme`/`host` inside a `try` and re-raises any parse failure as
`EgressBlocked`, so every rejection path is the one type the codebase catches. The catch is narrow
enough that a host which *does* parse is still decided on the allowlist
(`test_the_unparseable_host_path_does_not_swallow_a_real_allowlist_decision`).

**Honest residue, and it is a real one.** Through an `httpx` *client*, the host is decoded while
the `Request` object is built — before any transport, and therefore before any MailWeave code,
is consulted. `client.get("https://xn--...")` still raises `idna`'s exception and there is no seam
here at which to convert it. It still fails closed. Both facts are asserted:
`test_a_malformed_punycode_host_still_never_reaches_the_transport` (nothing is sent) and
`test_the_client_level_residue_is_exactly_what_egress_documents` (the exception is `idna`'s and is
**not** `EgressBlocked`) — so if that ever changes, the test fails and the docstring is corrected
with it. The module docstring states the residue.

## R-SEC-006 · payload construction is unbounded before `MIME_PART_CAP` engages — LOW

**Was it fixed? No.** `MessagePayload` had no pre-validation bound; the walk cap still ran after
the whole tree existed.

**Fixed.** `content/payload.py` gains `measure_raw_shape` (iterative, model-free) and
`refuse_unbounded_payload`, called from a `mode="before"` model validator — so **every**
construction path is covered, including a direct `MessagePayload.model_validate(...)`, which is
the call R-SEC measured and the one a Gmail client is most likely to reach for. A bound only the
convenience wrapper applied would be a bound the next caller walks around
(`test_the_bound_holds_on_model_validate_too_not_only_on_the_helper`).

**Measured before/after** on R-SEC-006's own 200,000-sibling payload:

| | Round 1 (reported) | now |
|---|---|---|
| construction + processing | 1.7s + 4.5s | **refused in 0.32s** |
| peak RSS | ~420MB | ~124MB (mostly the caller's own dict) |

**About the numbers.** `PAYLOAD_PART_CAP = MIME_PART_CAP * 100` and
`PAYLOAD_DEPTH_CAP = MIME_DEPTH_CAP * 10`, registered in `constants.py` under the same "defensive
parse bound, not a product threshold" framing the HTML caps already carry — no rubric criterion is
measured against them and neither is an `[UNSET]` value. They are derived from the caps the
pipeline honours rather than picked, and the factors are stated. A payload past them is refused
**whole**, with a typed error, never silently truncated, because a truncated payload would be a
silent reduction with nothing to declare it. The part factor is engineering judgement with no
upper anchor — see "Where this work is weakest".

## R-SEC-007 · deep nesting raises `pydantic.ValidationError`, not a typed error — LOW

**Was it fixed? No.** Reproduced: 3,000 levels of nesting raised
`pydantic_core._pydantic_core.ValidationError`.

**Fixed, two halves.** The depth bound sits **below** the interpreter's own recursion guard, so
the refusal is `ContentProcessingError` rather than Pydantic's; and `parse_payload()` converts any
remaining `ValidationError` (a missing `id`, a wrong type) into `ContentProcessingError` with
Pydantic's report preserved as the cause.

**The depth number is measured, not assumed.** My first attempt used `MIME_DEPTH_CAP * 100 = 1200`
and a legitimate 1,198-level payload was refused *by Pydantic*, not by us — the guard bites at
**255** levels on this interpreter. The factor is now 10, and
`test_the_depth_bound_sits_below_the_interpreters_own_recursion_guard` binary-searches for the
real limit at runtime and asserts our bound is under it. If an interpreter, a Pydantic version or
the constant ever moves the two past each other, that test fails rather than the typed refusal
quietly reverting.

---

# Part 3 — Round 4 mediums

## R-SEC-017 · closure called before a later rebind, misclassified — MEDIUM (false positive)

**Fixed.** `_Scope` gains `defined_at`; `_owner_and_entry` returns both the owning scope and the
line at which the lookup entered it. `function_named` now branches three ways: the owning scope
itself resolves by call line (unchanged); the **module** scope keeps "last binding wins", which is
where its justification actually holds; an enclosing **function** scope resolves as of the line
the closure was *created*, which is the best static approximation of what the free variable held
when the closure was made.

**Failing-test-first.** R-SEC's reproduction reported 1 violation before, 0 after
(`test_a_closure_called_before_a_later_rebind_is_not_an_unconditional_write`). Two tests written
at the same time to stop the fix gutting the guard — a free variable bound *above* the closure,
and the module-level helper-above-its-constant shape "last wins" exists for — passed before and
after, so the edit is a narrowing and not a removal.

**I treated this as seriously as a bypass, per the work order.** A new realistic sweep
(`test_the_widened_resolution_finds_no_false_positives_in_ordinary_code`, ~100 lines of ordinary
code) reuses `write`, `copy`, `open`, `render` and `clean` across a dataclass, a two-level nested
class, a closure reconfigured after it is called, a method named `open`, a `with open(...)` read
and a comprehension — with exactly three real writes, which are the only three reported.

**The trade, stated.** The fix converts a false positive into a false negative: a closure whose
free variable is bound *after* the `def` is now missed. That is named in the guard's "Does not
catch" list with the code shape spelled out, and pinned by
`test_each_round_five_gap_is_really_a_gap[closure_over_a_later_binding]` so the claim cannot drift
in either direction.

## R-SEC-019 · nested-class attribute dispatch bypasses — MEDIUM

**Fixed.** After a class body is walked, nested class tables are lifted onto the enclosing scope
under the dotted path a caller outside actually writes (`Outer.Inner`) — recursive by
construction, since each level lifts what the level below already lifted. `class_attribute`
resolves ownership from the first segment; `_dotted_name`/`_class_receiver` replace the bare-`Name`
receiver requirement in both `_qualified_target` and `_writes_to_disk`.

**Failing-test-first.** `Outer.Inner.handler(fd, body)` and the three-level `A.B.C.handler(...)`
both reported 0 violations before, 1 each after. Two non-regression tests: a nested-class
attribute bound to `str.strip` is not a violation, and `dbm.gnu.open(path, "c")` — a chained
*module* attribute — still resolves as a module and is still caught.

## R-SEC-020 · dataclass field defaults bypass entirely — MEDIUM

**Fixed.** `_populate`'s resolution pass handles single-target `ast.AnnAssign` with a value, and
`_record_assignment` learns `field(default=...)` / `field(default_factory=...)` via
`_field_default_target`. `_class_receiver` additionally resolves an immediate instantiation
(`Writer().handler(...)`), which is how a dataclass field default is normally called and is the
literal shape in R-SEC's reproduction.

**Failing-test-first.** All three forms — `field(default=os.write)`, the bare
`handler: Callable = os.write`, and a module-level `_writer: Callable = os.write` — reported 0
violations before, 1 each after. Two non-regression tests: an annotated field bound to `str.strip`
is clean, and a bare annotation with **no** value still shadows correctly (it binds without
resolving, which is what stops a later `= str.strip` from inheriting an outer `os.write`).

**Residue:** an instance held in a variable (`w = Writer(); w.handler(...)`) is still missed. Named
in "Does not catch" and pinned by
`test_each_round_five_gap_is_really_a_gap[instance_held_in_a_variable]`.

## R-SEC-018 · the fold's "does not read" list under-enumerates — LOW

**Fixed (documentation, which is what the finding is).** The single "a value that travels through
a **variable**" bullet is replaced by a four-shape enumeration: variable, class/instance
attribute, container element, function return value — each with its own reason (no assignment
propagation, no attribute evaluation, no container indexing, no call-return substitution) and the
note that folding a literal string's slice *is* supported, which is a different thing.

**And the enumeration is executed, not just written.** `FOLD_INDIRECTION_SHAPES` builds
`ground_truth/cases.json` through each of the five spellings and asserts the ground-truth guard
reports nothing, so if a future fold starts following one of them the test fails and the bullet is
corrected with it. `test_the_fold_documentation_names_all_four_indirection_shapes` keeps the prose
and the probes in step. One existing assertion in
`test_each_unfolded_idiom_is_named_in_the_docstring_rather_than_silently_missed` was updated to
the new wording.

## R-ARCH-012 · the mechanical gate's structural ceiling — MEDIUM (document, not fix)

**Documented, explicitly.** `tools/rubric_status.py` gains a "What this check cannot do
(R-ARCH-012)" section stating that it verifies records are well-formed, signed and round-numbered
— and cannot verify any of it is **true**: it never opens the file a row cites, a reviewer
signature is a string in a markdown cell rather than an identity, and a row can cite evidence that
exists but does not support the criterion it is filed against. That last one is not hypothetical:
it is precisely what R-ARCH-009 and R-ARCH-010 found in Round 4, and **both of those rows would
pass this check today**.

The honest statement of a green `--check` is written out: *no criterion is marked PASS without a
signed, round-numbered, non-empty citation* — not "every PASS is earned". Two consequences are
named, including that Round 4's fifteen never-verified findings are exactly the kind of thing this
file could never have noticed, and that pointing at a green gate would have been the wrong
reassurance.

**Demonstrated, not just asserted.**
`test_a_row_citing_evidence_that_does_not_exist_passes_the_check` builds a rubric whose only PASS
cites `tests/test_nothing_of_the_kind.py::test_invented_by_this_row`, signed `R-SEC`, and asserts
`check(view) == []` **and** that the cited file does not exist. If a future version starts
verifying citations, the test fails and the ceiling paragraph gets corrected with it.

## R-RETR-003 · a page can be recorded twice — MEDIUM (carried from Round 3)

**Fixed.** `FetchedIds._release` set `_consumed = True` and never read it. It now refuses a second
release. `H` was never affected (`setdefault` is idempotent); `scan_scope` was — two entries for
one executed call is a false account of the retrieval.

**Failing-test-first.** `test_the_same_page_cannot_be_recorded_twice` and
`test_the_replay_is_refused_across_every_intake_not_just_the_one_it_used` both failed before
(`DID NOT RAISE`). Two tests guard against over-fixing: `recorded` flips exactly once, and two
*distinct* observations carrying the same ids remain two `scan_scope` entries — because a repeat
query really did run.

---

# What I did NOT fix, and why

1. **R-ARCH-008 / R-DISC-007** — the `included`/`included_as_stub` ruling. Not mine to make. I
   pinned the shipped reading in a test that names both readings, the missing ruling and the two
   change sites. **An orchestrator ruling is still owed.**
2. **Amendment A1** (the content witness) — explicitly out of scope; WS-13/WS-16.
3. **`EV-01`'s bounded-above half** — unchanged and unchangeable in-process, per A1.
4. **R-SEC-004's client-level path** — `httpx` decodes the host before any MailWeave code runs.
   Documented and pinned rather than claimed.
5. **The disk-write guard's remaining residues** — `self.handler`, a name holding an instance, a
   data-structure or factory alias, `getattr`, `sqlite3.connect`, and R-SEC-017's new false
   negative. All named in "Does not catch"; the two new ones are pinned by tests.
6. **The fold's four indirection shapes** — corrected in the documentation, not in the code.
   Following them is constant propagation, which is a different mechanism from a constant fold and
   a much larger change than a LOW documentation finding warrants.
7. **R-ARCH-012's actual ceiling** — a markdown parser cannot re-run a citation. Documented.
8. **No rubric transitions, no ledger rows** — orchestrator-only.

# Where this work is weakest

Ordered by how much it would bother me if I were reviewing it.

1. **`PAYLOAD_PART_CAP` has no upper anchor.** The depth bound is genuinely constrained from above
   by a measured interpreter limit that a test re-measures at runtime. The part bound (6,400) is
   only `MIME_PART_CAP * 100` with a stated rationale — no measurement says a real Gmail message
   never exceeds it, because I have no real-mail corpus. If one ever does, the message is refused
   **whole**. That is a fail-closed choice against an unmeasured number, and it is the single
   riskiest thing I added this round.
2. **R-DISC-006's envelope-level rule invents a semantic WS-04 has not defined.** "A row's
   `constraint_coverage` ⊆ `asked_for.enforced ∪ dropped`" is a defensible reading, and I argued
   for constraining a live field before its first producer decides what it means — but WS-04 owns
   this field, and if its design differs, this validator is a constraint it did not ask for. The
   row-level half (non-empty, unique) is uncontroversial; the envelope-level half is a judgement
   call an implementer made in a workstream that is not his.
3. **R-SEC-017 trades a false positive for a false negative.** The trade is defended in the
   docstring and pinned by a test, and it is the right direction given "false positives get guards
   switched off". But the guard now misses a real shape it used to catch, and someone who cares
   more about bypasses than about adoption would reasonably rank it the other way.
4. **The attribution detector is a verb list.** Eleven locales are in the pattern, three are in the
   corpus, eight are asserted by nothing. And the "must carry an address or a date/time" condition
   is a heuristic that a genuine attribution line without either would fail — I have no measurement
   of how often that shape occurs, because that needs real mail.
5. **One Round-4 property test's refusal branch changed.** Its success branch — where the
   R-RETR-002 property lives — is untouched, but a reviewer should look at that diff themselves
   rather than take this paragraph's word for it.
6. **R-ARCH-003, R-DISC-003 and the quote work are all still synthetic.** Every corpus case is
   invented in-repo. R-ARCH's Round-1 conclusion that "the synthetic fixtures already understate
   real-world failure modes" is as true now as it was then, and nothing this round changed that.
7. **`Writer().handler(...)` resolves but `w = Writer(); w.handler(...)` does not**, which is an
   awkward line to have to defend: the two shapes are equally ordinary, and only one is caught.
   Documented, but the asymmetry is real.
8. **I verified the four already-fixed findings by reintroduction, not by re-deriving the original
   reviewer's probe from scratch.** Reintroduction proves the tests are load-bearing; it does not
   prove the tests cover everything the original reviewer was worried about. For R-ARCH-001 and
   R-ARCH-002 I did also run the current stripper against the corpus by hand, but I did not rebuild
   R-ARCH's `/tmp/mw-review/` probe files.
