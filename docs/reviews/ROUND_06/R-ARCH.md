# R-ARCH — Round 6 review (architecture and code quality)

**Reviewer:** R-ARCH · **Date:** 2026-08-31 · Fresh instance · Scope: ROUND_06 HANDOFF.

## Execution record

Per the setup warning I raised last round: `rm -rf .venv .mypy_cache .pytest_cache .ruff_cache
.hypothesis && uv sync --all-packages --extra dev` from scratch, then confirmed
`import mailweave; mailweave.__file__` resolves to `/root/mailweave/server/...` before trusting
any result. `make check` in place: ruff clean, format clean, mypy (62 files) clean, **656
tests passed** (matches HANDOFF, up from 557), 7 guards clean, `rubric_status.py --check`
unchanged (8 PASS / 105 NOT TESTED / 10 transitions).

Every reintroduction below was made directly in `/root/mailweave` (sha256 of the original
recorded first), tests run, then the file restored and the hash re-verified — no `/tmp` copy,
no stale-install risk. All quote-stripper adversarial probes live in
`/tmp/mailweave_review/probe*.py`; none touched project source or tests.

## R-ARCH-015 — the quote stripper (priority)

**Verdict: the structural fix is real but materially narrower than claimed, and I found
genuine new content-destroying false positives beyond the declared residue.**

**What holds.** All ten trailing-line cases and the three-locale corpus attribution cases pass
(77/77 in `test_quote_corpus.py`). The pinned `known_gap` behaves exactly as declared, and
round 5's own defect (`SENDER_SENTENCE_CARRYING_ATTRIBUTION_EVIDENCE`) is fixed.

**New false positives — sender's own first-person sentence deleted, contradicting the "subject
not first-person" guarantee.** The check only inspects the single token immediately before the
verb match. Any true first-person subject separated from the verb by an adverb or conjunction is
invisible to it:
```
"I checked with devops@example.com at 15:14 and then wrote back:"
"Yesterday at 15:14 I emailed devops@example.com and later wrote a follow-up:"
```
Both, as the last line above a real `> ` quote, are deleted whole and counted `quoted`. This is
not the declared residue (scoped to third-person subjects) — it falsifies the claimed
protection on its own terms.

**First-person plural is not in `_FIRST_PERSON_RE` at all** (only singular `i/je/ich/yo/...`).
`"At 15:14 we wrote to devops@example.com confirming the freeze:"` and a Swedish `"Kl 15:14
skrev vi till ... :"` are both deleted though the subject is unambiguously the sender.

**The residue is a class, not the one pinned shape.** Against 15 realistic corporate-English
sentences (each containing an attribution verb + email/time evidence, the shape a person
actually writes — "per our call...", "following up on...", "the customer wrote:"), **6/15
(40%) were wrongly stripped**, all instances of evidence-before-verb regardless of subject
distance/plurality. The single `DECLARED_GAPS` entry undersells how common the trigger is; it
covers one shape correctly but the class is far larger.

**False negative found, out of the ten locales tested — Apple Mail / iOS "Begin forwarded
message:" format.** `email_reply_parser` merges the sender's last line and the separator into
one *non-hidden* fragment, so the module's `looks_quoted` reclassification (which only runs on
fragments the parser already flagged `hidden`/`signature`) never sees it: `"Begin forwarded
message:"` leaks into the disclosed `reply`, and the isolated `From:`/`Date:` header lines
(each alone, one field, below the 2-header `looks_quoted` bar) are individually filed as
`signature` — the exact "quoted prior conversation declared as signature" class R-ARCH-001 was
supposed to close, resurfacing through a fragment-merge path R-ARCH-001 didn't anticipate.

**Locale-count claim is off by one.** `_ATTRIBUTION_VERBS` has 12 entries but only **11
distinct patterns** — `"skrev"` (Swedish) is listed twice, verbatim, adding no coverage. Only
9 of the "ten locales" have working test coverage.

**Judgment:** a real, honest improvement over round 5, and every claimed test passes. But
"fixed structurally... residue pinned" reads as more complete than it is: the residue is a
whole class of business phrasing, not one shape, and one branch of it (true first-person,
non-adjacent) directly contradicts the stated guarantee — silent deletion, regardless of label.

## R-DISC-009 test-count claim — inaccurate

Reintroducing the described defect (`_record_for` reading *any* observed thread instead of the
id's own) breaks **9 tests, not 7**: the 5 named + both property tests (7, as claimed) **plus**
`test_a_later_observation_may_supply_the_thread_an_earlier_one_did_not_carry` (same file) and
`test_the_withheld_record_carries_its_cap_reason_and_executable_call`
(`test_envelope_serialisation.py`) — both genuine, both omitted from HANDOFF's list. The
separate "envelope half" claim (record-equality neutered in `response.py`) is exactly right:
fails precisely `test_a_withheld_record_rewritten_after_certification_is_refused`, nothing
else. Both files restored byte-identical (sha256 verified).

## R-ARCH-017 — generator split: verified independently

Sampled both strategies directly (2,000 examples each, not through `pytest`): occupancy
generator — **100.0% in range**, 96.7% clash / 3.3% success (claimed 97%/3%, within noise). A3
generator — **83.8% out of range** (claimed 84.2%, within noise). Matches HANDOFF, confirmed by
construction (`start` drawn from the finished thread's own range) not by trusting the numbers.

## R-ARCH-018 — caption-swap test: verified against the real source

Performed the actual swap in `reasons.py::ThreadMember.render` (traded `self.position` and
`self.thread_id`), not the subclass version in the test file. Fails exactly
`test_every_parameter_is_rendered_in_the_place_that_names_it[thread_member]` and
`test_the_placement_check_catches_the_swap_that_passed_all_fifty_tests`, nothing else.
Restored, sha256-verified. Genuine.

## R-ARCH-014 — A4 propagation test: verified

`test_the_ruling_is_visible_everywhere_the_amendment_says_it_changed` reads real file content:
`ARCHITECTURE_DECISION.md` §D.2 does read `"included": 42"` with `AMENDED by A4` inline,
`ARCHITECTURE_AMENDMENTS.md` does have `## A4 ·`, both docstrings do contain `"A4"` — checked
rather than assumed constant-true. Genuine.

## The 3×3 payload-shape matrix — verified, claim exact once reproduced precisely

A shallow reintroduction (`Mapping`→`dict`, `getattr` fallback kept) only broke 4 tests.
Reproducing the *actual* round-5 shape — dict-subscript only, no attribute reading at all —
broke **exactly 11**, with `mapping_proxy` × `keyword_constructor` correctly still passing
(pydantic turns `**MappingProxyType` into a plain dict before the validator runs). Confirms the
claim is accurate and the matrix genuinely discriminates rather than blanket-failing.

## §4 — new findings

```
ID:            R-ARCH-019
Severity:      HIGH
Rubric:        DISC-03 (the reduction's count is honest; the classification of what qualifies
               as "quoted" text a sender wrote is not)
Location:      server/src/mailweave/content/quotes.py:199-236 (_looks_like_an_attribution_line)
Reproduction:  strip_quotes_and_signature("...\n\nI checked with devops@example.com at 15:14
               and then wrote back:\n\n> The freeze starts Friday.\n") -> the sender's own
               first-person sentence is fully deleted, quoted_chars=92
Expected:      A sentence with an explicit first-person subject "I" is exempted, per the
               claimed rule ("subject not first-person").
Actual:        The check inspects only the single token immediately before the verb match;
               "and then"/"and later" between "I" and "wrote" hides the subject entirely, and
               first-person-plural (we/nous/wir/vi/wij/...) is absent from _FIRST_PERSON_RE
               even when adjacent.
Required fix:  Scan a short window (or resolve the sentence's actual subject) rather than only
               the adjacent token; add first-person-plural pronouns to _FIRST_PERSON_RE.

ID:            R-ARCH-020
Severity:      MEDIUM
Rubric:        DISC-03
Location:      server/src/mailweave/content/quotes.py (strip_quotes_and_signature fragment loop)
Reproduction:  Apple-Mail-style forward, "FYI see below.\n\nBegin forwarded message:\n\nFrom:
               .../Date: .../To: .../Subject: ...\n\nDo we still need the room?" -> reply
               retains "Begin forwarded message:"; From:/Date: lines filed as signature_chars.
Expected:      A forward separator and its header block are declared quoted (R-ARCH-001).
Actual:        `email_reply_parser` merges the separator into a non-hidden "reply" fragment in
               this shape; `looks_quoted` reclassification only runs on fragments the parser
               already flagged hidden/signature, so an ordinary "reply" fragment is never
               checked against the module's own quote-shape predicate.
Required fix:  Run `looks_quoted`/`_SEPARATOR_RE` against every fragment, not only ones the
               upstream parser already flagged.

ID:            R-ARCH-021
Severity:      LOW
Rubric:        none — claim-accuracy (AGENT_LOOP §7.7)
Location:      server/src/mailweave/content/quotes.py:58-71 (_ATTRIBUTION_VERBS)
Reproduction:  len(_ATTRIBUTION_VERBS)==12, len(set(...))==11; "skrev" appears twice, verbatim.
Expected:      "all ten locales" implies ten distinct, tested word-order shapes.
Actual:        One entry is a no-op duplicate; only 9 locales have test coverage.
Required fix:  Replace the duplicate with a genuinely distinct verb, or correct claim to "nine."

ID:            R-ARCH-022
Severity:      LOW
Rubric:        none — claim-accuracy (AGENT_LOOP §7.7)
Location:      docs/reviews/ROUND_06/HANDOFF.md, R-DISC-009 section
Reproduction:  see "R-DISC-009 test-count claim" above
Expected:      "7 tests fail" is the exact, complete count for the described reintroduction.
Actual:        9 tests fail; 2 genuine failures omitted from the list.
Required fix:  Correct the ledger entry; no code change needed — extra coverage is a positive.
```

## Hollow-implementation list

None of the mechanisms directly probed by reintroduction were hollow — every defect
reintroduction failed exactly the expected tests, at the exact counts once reproduced
precisely: thread-derivation write path (9/1 split above), the Mapping-or-attribute payload
walk (11/11), the caption placement table (2/2), the split generators (percentages to noise).

**Thin, not hollow:** the occupancy property's "legitimately segmented map still builds"
branch is exercised by ~3% of 300 examples/run (~9 examples) — self-disclosed, confirmed by my
own 2,000-example sample (66/2000, 3.3%). Detection is unaffected (96.7%), but this branch is
closer to smoke-tested than property-tested.

**Degenerate-strategy probe, four mechanisms:**
- *Thread derivation:* dumbest pass-consistent version blindly overwrites `thread_id` on every
  observation — caught by `test_two_observations_that_disagree...`. Not degenerate.
- *Mapping-or-attribute reading:* dumbest version returns no children for anything unrecognized
  — caught by `test_the_same_structure_measures_the_same_however_it_is_spelled`. Not degenerate.
- *Quote-stripper rule:* the shipped rule **is already close to the dumbest one that passes the
  shown tests** — positional-token heuristics, no real subject/clause parsing; R-ARCH-019/020
  show the suite doesn't push it past that floor.
- *Split generators:* a degenerate single-run-only `runs_inside_the_thread` would still pass
  every assertion; my sample shows real diversity, so it isn't what shipped, but nothing in the
  test asserts that diversity — a silent regression there would go unnoticed.

## Per-criterion recommendations

- **R-ARCH-015 not closed.** Broaden `_FIRST_PERSON_RE` (plurals) and the adjacency window, or
  rewrite the claim to state the residue is a class (~40% of natural evidence-before-verb
  sentences), not one pinned shape.
- **R-ARCH-020** (Apple Mail leak): fix, or add a second `known_gap` — right now it is neither,
  the exact drift `test_the_known_gap_list_is_exactly_what_is_declared_open` exists to catch.
- **R-ARCH-021/022:** documentation-only, fix at next edit.
- **DISC-03** stays `NOT TESTED` per protocol; R-ARCH-019/020 should block it reaching PASS.
- No BLOCKER or previously-PASS criterion regressed. R-ARCH-017/018/014, the R-DISC-009
  envelope-half fix and the payload matrix are genuinely fixed; close as claimed, with the
  test-count ledger entry corrected per R-ARCH-022.
