# ROUND 06 — Consolidated findings and gate decision

**Orchestrator, 2026-08-31.** Reviewers: R-DISC, R-SEC, R-ARCH. All three wiped and resynced
their scratch environments after R-ARCH's stale-editable-install warning, and all three
reproduced the baseline independently before trusting anything.

## Gate decision: **ROUND 06 DOES NOT CLOSE.** Two HIGH.

## Closed

**R-DISC-009**, the cross-thread withheld borrowing, is closed and closed well. R-DISC attacked
every route in the brief: fabricating an observation's thread, two threads disagreeing on one id
(raises across all four endpoint combinations), a hand-built record reattached with a forged
thread, nested tampering under whole-record equality, an id observed under no thread, and the
`threads.get` versus listing paths separately. All five constructor attacks raise. The property
test's id and thread alphabets are confirmed disjoint over 5,000 generated pairs.

**R-SEC-021 / R-ARCH-016**, the shape-bound pattern, holds across eight spellings including
`MappingProxyType`, `OrderedDict`, `defaultdict`, a custom `Mapping` subclass, a dataclass and a
pydantic model. R-SEC swept every `isinstance(dict/Mapping/list)` gate in the codebase and found
**no fourth instance**, and independently confirmed the third instance was real and the two
cleared candidates genuinely safe.

**R-SEC-022, 023, 024** closed for their cited bypasses. **R-DISC-008 / R-ARCH-014** closed.
**R-ARCH-017** verified by independent measurement: 100% in-range and 83.8% out-of-range,
matching the claim, so both properties are exercised at full strength again.

## Open HIGH

**R-DISC-011 — the seventh instance of the same shape.** The borrowing R-DISC-009 closed on the
withheld side is still open on the **disclosed** side. `MessageRow.thread_id` is never
cross-checked against the observed `HitOrigin.thread_id`. R-DISC built a working exploit: a
"complete" four-message map of thread `t1` that borrows a message genuinely observed under
thread `t5`, with `partial=False`.

**R-ARCH-015 — the quote stripper is destroying content.** Round 5 fixed it, Round 6 verified
the fix and then defeated it. An adverb between the pronoun and the verb slips the first-person
check, and first-person-plural pronouns are absent from the pattern entirely. Against fifteen
realistic corporate sentences, **six were wrongly stripped**. Also a real false negative (Apple
Mail "Begin forwarded message" separators leak through and misfile header fields as `signature`),
and the "ten locales" claim is off by one because `_ATTRIBUTION_VERBS` contains "skrev" twice.

Decided as **amendment A5**: the stripper biases toward under-stripping and strips only on a
strong structural signal. Leaving a header in costs tokens. Deleting a sentence someone wrote
destroys evidence, which is the thing this project exists to prevent.

## Two honest undercounts, both in the implementer's favour to have disclosed

The handoff claimed that reintroducing the R-DISC-009 defect breaks 7 tests. R-DISC measured 8,
R-ARCH measured 9. Both filed it as a minor accuracy issue rather than a defect, and both noted
it does not change the verdict. Worth recording because it is the kind of small inflation that
usually runs the other way.

## New MEDIUM

| ID | Defect |
|----|--------|
| R-SEC-026 | Comprehensions and lambda parameters are not modeled as scopes; a comprehension variable named `os` shadowing the real import misresolves and false-positives on both guards. 3 of 3 reproduced |
| R-SEC-027 | The generic `.open()` fallback flags any mode-word containing w, a, x or +. "readonly" contains an 'a' and is flagged as a write on a non-file class |
| R-SEC-028 | LOW: the ground-truth isolation guard substring-matches, flagging "manifestly" and "harnessed" |
| R-ARCH-019 | Apple Mail forward separators leak into `body_clean` and misfile headers as `signature` |
| R-ARCH-020 | `_ATTRIBUTION_VERBS` has a duplicate entry; nine locales have coverage, not ten |

## The thing worth naming

R-DISC-011 is the **seventh** appearance of one defect shape in this project: *a value is
accepted from the caller when the same value is already derivable from what was observed.*
Withheld records, thread maps, collapsed runs, the hit set, positions, shape bounds, and now
disclosed rows.

Six of those were fixed one at a time. Round 7 does not fix a seventh instance. It audits for
the whole class, because a defect that recurs seven times is a systemic property of the design
rather than seven unrelated mistakes, and patching the seventh will produce an eighth.

## Criteria

8 pass, unchanged. `PART-05` blocked again by the same class in a new location. `PART-07`'s
structural half remains ready and its full pass still needs live agent infrastructure. No
security criterion promoted, correctly: `SEC-05` and `SEC-07` need runtime evidence this round
could not produce.
