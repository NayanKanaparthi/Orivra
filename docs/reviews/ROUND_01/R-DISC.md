# R-DISC — Round 1 Progressive Disclosure & Context Representation Review

**Reviewer:** R-DISC (fresh instance, did not write this code) · **Date:** 2026-08-31
**Scope:** `server/src/mailweave/envelope/` (WS-03), per `WORK_ORDER.md`. No retrieval rungs
exist this round; judged as a representation — can it carry the contract's obligations, and
does it make violating them hard.
**Method:** execution only (`AGENT_LOOP.md` §4/§7); `HANDOFF.md` claims were not trusted.
Baseline: `make check` reproduced clean — ruff, mypy strict/55 files, `pytest -q -m "not
network"` = 199 passed, guards clean, `rubric_status.py --check` = 113 criteria NOT TESTED. 25
adversarial probes written to `/tmp/.../scratchpad/rdisc/` (not project source/tests); every
claim below names its probe. No project file other than this one was modified.

---

## Findings

### BLOCKER
None.

### HIGH

**R-DISC-001**
Severity: HIGH · Rubric: PART-05, R-06, C-06 §5.1's thread-map row obligation
Location: `server/src/mailweave/envelope/wire.py::Source` (no validator ties `map_id` to
per-message accounting)
Reproduction: built `Source(thread_id="t1", stated_total=42, included=5,
map_id="map-t1-full", messages=<5 matched rows>)` with **no** `collapsed_runs` and **no**
withheld records for the other 37 messages.
Expected: contract R-06/PART-05: "wherever a thread map is present, every message of that
thread appears as at least a stub row... Bare 'N omitted' with no per-message index: 0
occurrences where a map is claimed."
Actual: the `Source` builds successfully. `partial=True` is set correctly and an affordance
names the thread (R-07 holds), but 37 of 42 messages (88%) are represented **nowhere** — not
as stub rows, not as collapsed-run members, not as withheld records — because they were never
fetched into `H` at all. Nothing in the schema distinguishes "a map view, which must fully
enumerate" from "a search-result view with thread context, which need not." `map_id` is the
only signal that a `Source` purports to be a map, and no validator reads it.
Required fix: when `Source.map_id` is not `None`, require `included == stated_total` (every
stated position covered by `messages`/`collapsed_runs`). A schema-level fix, independent of
whether WS-05's `thread_map` producer exists yet — fixing it now means it can't ship silently.

### MEDIUM

**R-DISC-002**
Severity: MEDIUM · Rubric: DISC-06, R-10
Location: `server/src/mailweave/envelope/builder.py::EnvelopeBuilder.build` (ceiling check
gated on `self._truncated` alone)
Reproduction: `probe_r01_r10.py::r10_flag_bypasses_without_shrinking` — called
`mark_self_truncated()` then built a response with a 27,000-token message body against the
9,000-token ceiling; `builder.build()` returned successfully with `truncated_by="mailweave"`
and `measure_tokens(envelope) == 27000` (3× over ceiling), with zero content removed.
Expected: DISC-06 acceptance: "a response that would exceed it is truncated by MailWeave...
rather than letting the host truncate it silently."
Actual: the flag alone satisfies the validator; nothing checks the payload actually shrank.
Implementer's own disclosed gap (HANDOFF §4: "nothing yet makes it fit"), confirmed by
execution here rather than by reading the claim.
Required fix: once WS-11's degradation ladder lands, require `truncated_by == "mailweave"` to
imply `measure_tokens(envelope) <= ceiling.applied`, so the flag can't be used as a bypass.

**R-DISC-003**
Severity: MEDIUM · Rubric: C-07, PART-06 (usability half)
Location: `server/src/mailweave/envelope/response.py::Envelope` field order
Detail: see "What an agent actually sees" below. The wire schema places `sources` (the bulk,
unbounded content) third, **before** `partial`, `withheld`, and `retrieval_report`. There is no
envelope-root aggregate ("N of M disclosed, K withheld, rungs not tried") — a skimming reader
assembles that picture only by combining `sources[].stated_total/included`, `withheld[]`, and
`retrieval_report.not_tried[]` from three different, non-adjacent places, one of them after a
potentially large content block.
Required fix: reorder wire fields so `partial`/`withheld`/`retrieval_report.outcome` precede
`sources`, or add a compact root-level summary block. Not urgent for machine consumption
(every field is correct and present); real for a model reading the payload linearly.

**R-DISC-004**
Severity: MEDIUM · Rubric: PART-07, test quality (AGENT_LOOP §7.2)
Location: `tests/test_envelope_contract.py`, `tests/test_envelope_serialisation.py`,
`tests/fixtures/envelope_kit.py`
Detail: of the 10 `ReasonKind` variants in `reasons.py`, only `GmailQueryMatch` and
`ThreadMember` are ever constructed by the test suite (`grep -rn` confirms zero hits for
`Rfc822MsgId`, `ReplyParentOf`, `ReplyChildOf`, `SemanticScore`, `HistoryAddition`,
`RequestedById`, `SnippetContains`, `WindowOffset` outside `reasons.py` itself). Each has its
own `.render()` f-string — exactly the mechanism PART-07 grades ("non-empty mechanical reason")
— and none of the other 8 is checked to render correctly. Relatedly, no test constructs the
OD-3 reply-chain-floor shape (`role=PARENT`/`role=CHILD` at `depth=STUB` beside a `MATCHED`
sibling) even though it is the round's headline capability; see OD-3 section below.
Required fix: one parametrized render test over all 10 `ReasonKind` variants; one fixture/test
exercising the parent/child-stub floor shape end-to-end through `EnvelopeBuilder`.

### LOW

**R-DISC-005** · Rubric: R-08 · `wire.py::Source.fetched_at` is `str, min_length=1` with no
timestamp format/plausibility check — `fetched_at="not-a-real-timestamp-at-all"` is accepted
(`probe_fetched_at.py`). Low risk (server-set, not caller-influenced in practice) but cheap to
close with a datetime-parse validator.

**R-DISC-006** · Rubric: C-06/DISC-01 · `wire.py::MessageRow.constraint_coverage` is a live
field (`tuple[str, ...] = ()`) with no validator and zero references anywhere in `tests/` —
currently a no-op placeholder for query-conditioning evidence (WS-04 doesn't exist yet; track
so it isn't forgotten once it does).

**R-DISC-007** · informational, not new · HANDOFF.md §3 item 3 already flags
`Source.included`/`included_as_stub` diverging from AD D.2's worked example (7+35=42,
non-subset). Restated only so it isn't lost outside the handoff — needs an orchestrator ruling.

---

## R-01 .. R-10 classification (contract §5.2)

| # | Obligation | Class | Evidence |
|---|---|---|---|
| R-01 | Hit identity (id/thread_id/position) | **ENFORCED** | all three required, non-empty; cross-checked (`row.thread_id == source.thread_id`) |
| R-02 | Role, closed 7-value set | **ENFORCED** | missing role, and `role="primary"`, both rejected |
| R-03 | Mechanical reason, never decorative | **ENFORCED** | missing reason rejected; free string `"you may find this useful"` rejected (discriminated union, no `str` variant) |
| R-04 | Depth, closed 5-value set + declared reductions | **ENFORCED** | missing/bad depth rejected; `raw` never inline; zero-size `Reduction` rejected |
| R-05 | Totals vs included, arithmetically true | **ENFORCED** | `included`/`included_as_stub` recomputed from payload, mismatches rejected |
| R-06 | Withheld as visible shape, not a bare number | **EXPRESSIBLE** | `WithheldRecord`/`CollapsedRun` themselves cannot lie about their own shape (ENFORCED) — but see R-DISC-001: nothing ties `Source.map_id` to full per-message accounting, so a "map" can omit most of a thread with no record at all |
| R-07 | Executable affordance while partial | **ENFORCED** | empty-args `Affordance` rejected; incomplete source with no reachable affordance rejected |
| R-08 | Completeness/freshness stamps | **EXPRESSIBLE** | `pool`/`shortlist`/`scan_scope` structurally strong (ENFORCED) — but `fetched_at` accepts any non-empty string (R-DISC-005) |
| R-09 | Untrusted-content envelope, fenced | **ENFORCED** | unfenced content rejected; mail text cannot forge its own fence-close |
| R-10 | Self-truncation before host truncation | **EXPRESSIBLE** | ceiling raises `ResponseCeilingExceeded` by default (ENFORCED) — but `mark_self_truncated()` bypasses it with zero verified shrinkage (R-DISC-002) |

**Count: 7 ENFORCED, 3 EXPRESSIBLE, 0 ABSENT.** The three EXPRESSIBLE cases are not sloppy
schemas — each has a real, tested enforced core — but each also has a specific, demonstrated
gap where the type system currently accepts exactly the violation the criterion exists to
forbid, and the fixes are cheap, targeted validators.

---

## Execution record

```
make check                          → lint/format/types/tests/guards/gate all clean (199 tests,
                                       mypy strict/55 files, 113 rubric criteria NOT TESTED)
uv run pytest tests/test_envelope_*.py tests/test_disposition_*.py
  tests/test_outcome_od2.py -q      → 63/63 pass
uv run python probe_r01_r10.py      → 23 probes: 22 violations rejected, 1 confirmed gap (R-10)
probe (map completeness)            → confirmed gap (R-06 → R-DISC-001)
probe (fetched_at)                  → confirmed gap (R-08 → R-DISC-005)
uv run python build_realistic.py    → built + serialised the scenario below; passed every
                                       Envelope validator on the first attempt
```
Full probe source: `/tmp/claude-0/-home-claude/575d70c1-c8ad-5ed4-8fc6-31be74875a3b/scratchpad/rdisc/`
(`probe_r01_r10.py`, `build_realistic.py`).

---

## What an agent actually sees

Built a realistic partial response: a decision-reversal thread (`t1`, 42 messages) where an
early "shipping today" message (`m12`) is reversed by a later "hold, legal has NOT signed off"
message (`m14`), then re-confirmed by `m20`; `m14`'s reply parent/child are present as stubs
only (OD-3's floor); 7 unrelated early messages are collapsed; a second thread's one candidate
(`m99`) is capped away by `max_hit_threads`; a semantic (L5) rung ran and its pool is declared;
`outcome=inconclusive` because L6 didn't run for budget reasons.

The partiality signals are all individually present and correctly shaped:

```json
"partial": true,
"withheld": [{"id": "m99", "thread_id": "t2", "cap": "max_hit_threads",
  "why": "13 hit-bearing threads found; max_hit_threads=12, t2 ranked 13th by recency",
  "affordance": {"tool": "mailweave_search",
    "args": {"q": "subject:launch (shipped OR approved)", "scan": {"max_hit_threads": 20}}}}]
```
```json
"retrieval_report": {"outcome": "inconclusive", ...,
  "not_tried": [{"rung": "L6", "why": "budget",
    "affordance": {"tool": "mailweave_search", "args": {"q": "...", "force_rungs": ["L6"]}}}]}
```
```json
"sources": [{"thread_id": "t1", "stated_total": 42, "included": 13, "included_as_stub": 9, ...}]
```

Judgment: **an agent skimming this would likely notice partiality — `partial: true` is an
unambiguous boolean — but would have to work to build the full picture.** The three pieces
that together answer "how much more exists and how do I get it" (per-source
`stated_total`/`included`, `withheld[]`, `retrieval_report.not_tried[]`) sit in three
non-adjacent places, and `sources` (60% of this payload's lines) is serialised **before** all
three in the wire order (R-DISC-003) — a reader working top-to-bottom, or a client that
renders/truncates sequentially, hits the bulk content before the metadata saying it's
incomplete. The upside: every affordance is a copy-pasteable tool call — nothing requires
inferring a follow-up the response didn't name (R-07's bar, met). The reversal message (`m14`)
is disclosed at `body_clean`, not a stub — the floor works on this case. No natural-language
narration exists at this layer (by design — WS-15's text-rendering mirror isn't built), so
today's noticeability depends entirely on the calling agent already knowing to check
`partial`/`withheld` explicitly.

---

## Role and reason: closed vocabulary confirmed

`Role` (`vocab.py`) is a 7-member `StrEnum`; all seven are exercisable
(`test_every_role_in_the_closed_set_is_representable`). `reason` is a `Field(discriminator=
"kind")` union of 10 typed classes — no `str` variant, so a decorative reason ("you may find
this useful") is rejected at construction, not disapproved of by a validator. Both fields are
required on `MessageRow`; a row cannot be constructed with either omitted (probed, R-02/R-03).
`reason_detail` (typed) and `reason` (rendered string) both ship, so a harness can join on
structure without regexing prose.

## OD-3: presence-as-stub with deeper content available

Constructed directly: `MessageRow(id="m10", role=Role.PARENT, reason=ReplyParentOf(child_id=
"m14"), depth=Depth.STUB, unabridged=Affordance(tool=GET_MESSAGES, args={"message_ids":
["m10"], "view": "body_full"}), content=None)` — builds cleanly. `role` (why it's here) and
`depth` (how much of it you're seeing) are independent fields; nothing forces a parent/child row
to stay a stub, and nothing prevents it. `Depth`'s five values (`stub`/`snippet`/`body_clean`/
`body_full`/`raw`) are semantic names with no ordinal/"level N of 5" framing anywhere in the
source (`grep -rn level server/src/mailweave/envelope/` returns nothing depth-related) — OD-3's
"not accidentally a routing hierarchy" concern does not materialize here. Gap: as R-DISC-004
notes, this exact shape is never exercised by a test, only by this review's probe.

## Test quality: `test_envelope_contract.py` vs `test_envelope_serialisation.py`

`test_envelope_contract.py` (517 lines) is genuinely adversarial: nearly every test's shape is
"construct the violation, assert it's refused" — e.g. `test_included_counts_are_derived_from_
the_payload_not_asserted` (claims 5, ships 2, asserts `"2 messages are present"` in the error),
`test_a_reason_cannot_be_a_free_string`, `test_more_pages_without_a_widening_affordance_is_non_
conforming`. `test_disposition_invariant.py` and `test_disposition_property.py` go further:
the latter is Hypothesis-driven (200 examples) over "a deliberately unreliable cap that
sometimes forgets to file its record," asserting `DispositionInvariantError` is raised in
exactly the forgotten-record case and never otherwise — this is the strongest test in the round.

`test_envelope_serialisation.py` (155 lines) is comparatively thin: 6 of 7 tests assert
well-formed shape (field presence, depth/role values, digest exclusion) on one already-valid
built envelope; only `test_an_envelope_cannot_be_constructed_without_a_disposition_certificate`
attempts an omission. It never re-verifies that `test_envelope_contract.py`'s rejections
survive the JSON round-trip. Not a defect — construction failure already prevents
serialisation — but the file's name promises wire-form testing and mostly delivers happy-path
shape description.

---

## WS-03 criteria: PASS / not-yet-PASS recommendations

| Criterion | Recommendation | Why |
|---|---|---|
| PART-02 (included matches payload) | **Recommend PASS** | purely mechanical self-consistency; fully reproduced by construction + tests + probes, no live data needed |
| PART-03 (partial iff true) | **Recommend PASS** | `partial` is computed, not asserted, both directions tested and reproduced |
| PART-07 (role+reason present) | **Recommend PASS** (structural half only) | universally true by construction (required, closed, non-free fields) — but see R-DISC-004: 8/10 reason renderers are untested, so mark the *coverage* half not-yet-PASS |
| ROUTE-01 (no bare empty response) | **Recommend PASS** | mechanical, self-contained validator, tested and reproduced |
| PART-05 (unexpanded content visible as stubs) | **Not yet PASS** | R-DISC-001: a demonstrated violating case is currently accepted |
| DISC-06 (self-truncation) | **Not yet PASS** | R-DISC-002: ceiling bypass confirmed by execution; degradation itself is WS-11 |
| EV-01, EV-03 (hit containment / withheld discipline) | **Not yet PASS** | mechanism is strong and fuzz-tested, but "no unlogged filter" needs a live retrieval→representation boundary (WS-04/05/08) to audit against, which doesn't exist yet |
| PART-01 (stated total correct) | **Not yet PASS** | schema self-consistency holds now; "equals what the source reported" needs GMAIL-03 against real `threads.get` |
| PART-04 (affordances executable) | **Not yet PASS** | needs a live server + scripted driver (P-follow, EP §10.1); no MCP surface exists this round |
| PART-06 (partiality survives into agent understanding) | **Not yet PASS** | explicitly requires agent-in-the-loop runs against a pinned model; no infra this round |

No criterion is recommended `BLOCKER`/`FAIL`; all remain within the round's disclosed scope.
Most "not yet PASS" items are blocked on later workstreams (WS-04/05/08/11/15), not defects in
WS-03 — except PART-05 and DISC-06, where this review found concrete, fixable gaps
(R-DISC-001, R-DISC-002) worth closing before later rounds build on top of them.
