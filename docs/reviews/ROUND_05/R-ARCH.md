# R-ARCH — Round 5 review (architecture and code quality)

**Reviewer:** R-ARCH · **Date:** 2026-08-31 · Fresh instance, no prior-round context beyond
`docs/reviews/ROUND_01/R-ARCH.md` (read per scope) and this round's HANDOFF/WORK_ORDER.
**Why this round matters:** Round 2 named R-ARCH gating and produced no report; six findings
went unverified for four rounds. This report exists specifically so that does not happen again.

## Execution record

All commands run by me. `/root/mailweave` for read-and-run; `/tmp/mw-review/fresh` and
`/tmp/mw-review/fresh2` (full copies, `.venv`/caches wiped, `uv sync --all-packages --extra dev`
from scratch) for every reintroduction, so no result depended on a stale editable-install
pointer back at the original tree — a mistake I made once and caught by checking
`module.__file__` before trusting a result.

- `make check` in place: ruff clean, `ruff format --check` clean, `mypy --strict` (62 files)
  clean, **557 tests passed** (matches HANDOFF), 7 guards clean, rubric gate clean (7 PASS,
  106 NOT TESTED, 9 transitions, unchanged).
- Reintroduced R-ARCH-001 (folded `hidden`/`signature` fragments back to `signature`),
  R-ARCH-002 (`cut = None`), R-ARCH-004 (`reconcile`'s comparison replaced with `if False`),
  R-DISC-004's two planted defects (`WindowOffset` dropping `offset`, `SnippetContains`
  returning a constant), and R-RETR-002's occupancy check (`_one_position_holds_one_disposition`
  neutered) — each in a from-scratch copy, each restored byte-identical afterward
  (`diff` confirmed).
- Wrote and ran 11 new locale/false-positive probes against `quotes.py`, a field-swap probe
  against `reasons.py`, a Hypothesis distribution probe against A3's shared shape generator
  (2,000 examples), and a direct-construction bypass probe against `content/payload.py`.
  All in `/tmp/mw-review/probes/`; none touched project source or tests.

## Verdict per finding

**R-ARCH-001 (quote chains mislabelled `signature`) — Genuinely fixed.** Reintroducing
Round 1's fold-everything-to-`signature` behavior fails exactly the four tests HANDOFF names
(`outlook_header_block`, `original_message_separator`, `forwarded_message`,
`html_gmail_blockquote`). Confirmed by execution, not by reading the diff.

**R-ARCH-002 (undelimited signature silently retained) — Genuinely fixed.** Reintroducing
`cut = None` fails exactly the five tests HANDOFF names, including the one named for the
finding. Confirmed by execution.

**R-ARCH-003 (non-English attribution dangling) — Fixed in code, verified beyond the tested
locales, with one new gap found.** The three corpus locales (French/German/Spanish) pass, and
I independently confirmed seven more locales already in the verb list but absent from the
corpus — Italian, Portuguese, Dutch, Polish, Swedish, Finnish, Danish — all strip correctly.
Locales with no listed verb (Japanese, Russian) dangle exactly as the implementer's own
"residue" note predicts. **New finding, not previously disclosed:** the false-positive guard
(address-or-time evidence + last-line + body-above) is defeated by a sender's own sentence
that happens to contain an attribution verb in ordinary use, an `@`-address, and a time,
immediately before a real quoted chain — e.g. `"As I wrote earlier, check with
devops@example.com at 15:14:"` followed by `"\n\n> The freeze starts Friday."` is silently
deleted. This is the mirror image of `SENDER_COLON_LINE_ABOVE_A_QUOTE`, which tests the same
shape *without* the coincidental evidence; nothing in the corpus tests it *with* evidence
present. **MEDIUM** — real content loss, narrow trigger, no fixture covers it.

**R-ARCH-004 (declared reductions checked for presence, not magnitude) — Genuinely fixed, and
it is the strongest mechanism in the diff.** `reductions.reconcile` compares declared removal
against measured shrinkage and raises on any mismatch, for every pipeline stage, not just
quotes. Reintroducing the exact R-ARCH-004 monkeypatch (declare 1, actually remove 220) now
fails with `DID NOT RAISE`, matching HANDOFF's own claimed evidence character-for-character.

**R-ARCH-006 (no guard on direct `httpx.Client()`) — Genuinely fixed.** Seventh guard
`unwrapped-http-client` exists, is registered, and its six planted-violation / four
non-firing tests pass. I independently probed `getattr(httpx, "Client")()`, a same-name
subclass, and a dict-of-constructors indirection: all three bypass, exactly as the guard's
own "Does not catch" list states. The residue is honestly bounded, not overclaimed.

**R-ARCH-008 / R-DISC-007 (D.2-vs-R-05 arithmetic) — Ruling issued (A4), but not applied
consistently, which is the specific thing the work order's addendum asked reviewers to
check, and it fails.** `ARCHITECTURE_AMENDMENTS.md` A4 states the ruling and explicitly
commits to two changes: "`ARCHITECTURE_DECISION.md` §D.2's worked example" and "the Round 5
test that pinned the shipped reading... its docstring is updated to record that the ruling
now exists rather than that it is owed." **Neither happened.** `ARCHITECTURE_DECISION.md`
§D.2 (line 1069) still reads `"included": 7, "included_as_stub": 35` — the disjoint reading
A4 rules wrong — with no mention of A4 anywhere in the file. `tests/test_envelope_contract.py`'s
`test_the_included_arithmetic_follows_contract_r05_and_not_ad_d2s_worked_example` still opens
with "neither has a ruling on record" and "An implementer may not decide which document
changes, so this test does not decide it" — both false as of A4. `grep -rl "amendment A4"`
across the repo returns exactly two files: the amendments doc and the Round 5 work order
addendum. The code's own behavior (R-05, `included=42`) is correct and matches the ruling;
only the paper trail was left unfinished. **MEDIUM** — not a runtime defect, but a concrete,
checkable promise in the project's own governing document that the current tree breaks, and
exactly the failure mode (a ruling that exists but isn't visible where a reader would look
for it) that let this sit for four rounds the first time.

## Test-quality section (the 151-test jump, per AGENT_LOOP §7)

**R-DISC-004's 50 tests (`tests/test_reason_coverage.py`) are real, not an enumeration smoke
test.** Completeness is checked against the live `ReasonKind` enum, not a hardcoded count.
Participation is checked by mutating every field of every reason and asserting the render
changes — confirmed load-bearing by reintroducing both defects the HANDOFF names, which fail
exactly the three tests claimed. Distinctness and wire round-trip are both genuine (also
executed, not read). **One weak spot found by probing rather than reading:** the participation
test only checks "changing this field changes *some* output," not "this field's value appears
in the *correct* place." Swapping which field renders where in `ThreadMember.render()`
(`position` and `thread_id` traded) — a real mislabeling, not a no-op — passes all 50 tests
unmodified. This is a gap in the anti-hollow-implementation property, not evidence the actual
code has this defect (it does not); recommend a positional/format-string assertion per
variant, not full mutation testing of field-placement correctness, given the low probability
this is worth much engineering effort.

**A3's Hypothesis property (`test_a_source_that_builds_never_holds_two_dispositions_at_one_position`)
still catches a full removal of R-RETR-002's occupancy check** — confirmed by reintroduction;
Hypothesis's shrinker finds `shape=[(0,1),(0,1)]` and the test fails via the success-branch
assertion, which A3 left untouched. But the shared generator is **measurably diluted**: a
2,000-example distribution probe over the same strategy shows only **13 examples (0.65%)**
land in the branch that directly exercises the R-RETR-002 invariant in-range, and only
**567 (28.4%)** land in the overlap-only refusal branch that also exercises it meaningfully.
The remaining **71%** are independently out-of-range and would raise via A3's own check
regardless of whether occupancy detection works at all — under the test's `max_examples=300`,
that leaves roughly ~85 of 300 examples per run actually testing R-RETR-002, not 300. The
property is not masked to the point of failure today, but it is a genuine, quantified
regression in test density that a further tightening of the position range (plausible in a
future round) would worsen toward zero. **LOW-MEDIUM** — recommend two independent generators
(one that stays in-range by construction) rather than one shared strategy carrying two
unrelated properties.

**R-ARCH-001/002/004's tests are unchanged from what HANDOFF describes and are load-bearing**,
confirmed above by direct reintroduction rather than by reading the diff.

## Hollow-implementation list

| Mechanism | Verdict | Basis |
|---|---|---|
| Quote/signature declared-magnitude accounting (`reductions.reconcile`) | **Not hollow-able.** | Reintroduction (R-ARCH-004) fails loudly; applies to every pipeline stage, not one. |
| Quote-stripper classification (R-ARCH-001/002) | **Not hollow-able for the fixed shapes.** Residual gap is disclosed (verb-list locales) plus one **undisclosed** false-positive (above). | Reintroduction + 11 new locale/edge probes. |
| `ReasonKind` render coverage (R-DISC-004) | **Not hollow for value-presence; hollow for field-placement correctness.** | Reintroduction of two planted defects caught; field-swap probe not caught. |
| A3 position bounds (`_every_position_lies_inside_the_thread`) | **Not hollow-able.** Reintroducing `if False:` on both range checks fails 7 dedicated tests (not independently reverified line-by-line this round, but the mechanism is simple and the Round 4 occupancy check it sits beside was independently stress-tested — see next row). | Read + `_every_position_lies_inside_the_thread` traced against A3's own acceptance table. |
| R-RETR-002 occupancy check, post-A3 | **Not hollow, but diluted** (quantified above). | Reintroduction + distribution probe. |
| `unwrapped-http-client` guard | **Not hollow for its stated scope; residues honestly bounded.** | 3 independent bypass probes (getattr, same-name subclass, dict indirection) all match the documented "Does not catch" list exactly. |
| `PAYLOAD_PART_CAP`/`PAYLOAD_DEPTH_CAP` (R-SEC-006/007) | **Hollow for a real, demonstrated path.** `refuse_unbounded_payload`'s `measure_raw_shape` only walks raw `dict` nodes (`isinstance(node, dict)`); a `Part` tree built by direct model construction (bottom-up, no dict at any level) and passed to `parse_payload()`, `MessagePayload.model_validate()`, or the plain constructor is measured as `parts=1, depth=1` regardless of actual size. Demonstrated: a 2,000-level-deep `Part` tree — 16× past `PAYLOAD_DEPTH_CAP=120` — was accepted by all three entry points with zero refusal. This directly contradicts the module's own docstring claim ("every construction path is covered... including a direct `MessagePayload.model_validate(...)`"). Real-world exposure is narrow — genuine Gmail API responses arrive as JSON-decoded dicts, never pre-built `Part` objects — but the guarantee as stated is false, and nothing in the test suite constructs a payload this way to notice. | Direct probe, `/tmp/mw-review/probes/`, reproduced independently through all three entry points. **MEDIUM finding.** |
| A4 ruling (R-ARCH-008/R-DISC-007) | **Hollow as a paper trail**, though the underlying code was already correct. | `grep` across the repo; both promised updates missing. |

## The implementer's own two flags

1. **R-RETR-002 property after A3.** Judgment above: genuinely tested (reintroduction still
   catches a full-removal regression) but measurably diluted (~71% of examples no longer
   exercise it). Not masked to failure; worth a follow-up regardless.
2. **`PAYLOAD_PART_CAP` with no measured upper anchor.** On its own — a fail-closed,
   documented, conservative choice with no real-mail corpus yet to validate against — this
   is **acceptable** for this round, on the same basis Round 1 accepted the quote-stripper's
   disclosed synthetic-only gap. Combined with the direct-construction bypass found above,
   the honest state is: the bound is unmeasured *and* has a real hole in its own enforcement
   path. Recommend both be tracked as one open item, closed together, before GMAIL-02/DISC-03
   claim PASS against real Gmail mail.

## Per-criterion recommendations

- **PART-05** (needs A3): supports PASS from R-ARCH's side — position bound is real,
  reintroduction-tested, and the Round 4 occupancy check it sits beside is intact.
- **PART-07** (needs R-DISC-004): supports promotion from R-ARCH's side on mechanism
  strength; the field-placement gap above is a test-quality note, not a blocker — the
  underlying renderers are not decorative and are not hollow in the way PART-07 cares about.
- **R-05/D.2 arithmetic**: code-correct; **do not treat A4 as closed** until
  `ARCHITECTURE_DECISION.md` §D.2 and the pinning test's docstring are actually edited. This
  is a five-minute fix; leaving it is what turned two Round-1 findings into a four-round gap
  last time.
- **SEC-06/DISC-03 against real mail**: not yet — the quote-stripper's new false positive and
  the payload-bound bypass are both exactly the class of gap only real Gmail mail (or a much
  larger adversarial fixture set) would have surfaced first.

## Summary

Zero BLOCKER. Of the six findings in scope: three (001, 002, 004) are genuinely fixed and
reintroduction-verified with no residual concern. One (003) is genuinely fixed with a new,
previously-undisclosed MEDIUM false-positive gap found by probing beyond the corpus. One (006)
is genuinely fixed with honestly-bounded residue. One (008, paired with R-DISC-007) has a real
orchestrator ruling that the current tree does not yet reflect in either place A4 itself names
— a MEDIUM process finding, not a code defect. Independently, probing the round's newest
mechanism (`PAYLOAD_PART_CAP`/`PAYLOAD_DEPTH_CAP`) found a real bypass via direct model
construction that the test suite does not exercise — MEDIUM, narrow real-world exposure. The
151 new tests are, on the whole, substantially better than a padding read would suggest:
R-DISC-004's 50 are genuinely adversarial by construction, and R-ARCH-001/002/004's existing
tests held up to independent reintroduction rather than merely reading the diff.
