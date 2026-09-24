# ROUND 06 — Implementer handoff

**Implementer, 2026-08-31.** Scope: `docs/reviews/ROUND_06/WORK_ORDER.md` — one HIGH
(R-DISC-009) and nine mediums. Nothing outside it was touched: no A1 work, no Gmail
retrieval, no rungs, ranking or MCP surface, no rubric rows, no ledger rows.

## Gate state

| | Before (round 5) | After |
|---|---|---|
| `pytest -m "not network"` | 557 passed | **656 passed** |
| `ruff check` / `ruff format --check` / `mypy --strict` (62 files) | clean | clean |
| `python -m tools.guards` | 7 guards clean | 7 guards clean |
| `rubric_status.py --check` | 8 PASS / 105 NOT TESTED / 10 transitions | **unchanged** |

`make check` passes end to end. **Every fix below was verified by reintroducing the defect
in the real source file, watching the named tests fail, restoring from a backup and
confirming the restore is byte-identical (`diff`) with the suite green again.** Backups and
probes are in the scratchpad; no project file is left modified by a probe.

---

## Row per finding

### R-DISC-009 (HIGH) — cross-thread withheld-record borrowing

**Derived, not compared.** `note_withheld` no longer has a `thread_id` parameter at all.

| What changed | Where |
|---|---|
| The sealed observation carries the thread Gmail returned with each id: one `thread_id` for a `threads.get`, a per-id `thread_ids` map for the two listing endpoints (Gmail carries `threadId` on every `messages.list` item and every `messagesAdded` entry). Validated: no thread for an id the response did not return; no partial map; not both forms at once | `disposition.py::FetchedIds` |
| `_admit` writes the observed thread into `HitOrigin.thread_id`, which was previously written and never read. A later observation may supply a thread an earlier one did not carry (the ordinary `messages.list` → `threads.get` ladder); two observations that **disagree** about an id's thread raise rather than one being picked | `disposition.py::DispositionLedger._admit` |
| `note_withheld` takes only the cap, the reason and the affordance, and stores a `_WithheldNote`. It cannot state a thread, so the borrowing is unrepresentable rather than detected | `disposition.py::note_withheld` |
| `certify` mints each `WithheldRecord` with `thread_id` read from that id's `HitOrigin`. An id observed under no thread **cannot be withheld**: certification raises and names the observation that should carry the `threadId`, because guessing the thread from the source that wants to count the id *is* the defect | `disposition.py::_record_for` |
| The envelope now compares withheld records **whole** against the certificate, not by id set and length. Round 5's check would have accepted a hand-built envelope shipping the certified ids under rewritten threads — the same borrowing at the last editable point | `response.py::_withheld_matches_the_certificate` |
| A listing fetcher's obligation to carry `threadId` is stated where WS-02's author will look | `retrieval/transport.py` |

**Before.** R-DISC's reproduction, re-executed (`probe_disc009.py`): four ids observed for
`t1`, one real id `t2-only` observed for `t2`; `note_withheld(message_id="t2-only",
thread_id="t1")`; a `map_id`-bearing source for `t1` with `stated_total=5` and
`withheld_here=("t2-only",)`. Output: `BUILT. accounted_for=5 stated_total=5`,
`withheld=[('t2-only', 't1')]` — a complete map of a thread that is one message short.

**After.** The same probe raises `DispositionInvariantError: source t1 accounts for
['t2-only'] as withheld, but this response carries no withheld record for them` — because
the record for `t2-only` says `t2`, which is where it was observed.

**Failing-test-first.** Reintroduced by making `_record_for` take *any* observed thread
instead of this id's (the minimal spelling of "not derived per id"): **7 tests fail** —
`test_a_map_cannot_account_for_itself_with_another_threads_withheld_message`,
`test_the_thread_on_a_withheld_record_is_the_one_the_observation_recorded`,
`test_the_same_derivation_holds_for_an_id_observed_through_a_listing_page`,
`test_a_withheld_record_rewritten_after_certification_is_refused`,
`test_a_cap_that_records_its_reason_produces_a_derived_withheld_record`, and **both**
property tests. The envelope half was reintroduced separately (record equality neutered) →
`test_a_withheld_record_rewritten_after_certification_is_refused` alone fails with
`DID NOT RAISE`. Both files restored byte-identical.

**Property test, ids and threads generated independently.**
`test_certification_either_accounts_for_every_hit_or_raises` now draws threads from their
own alphabet (`T[A-Z]{1,4}`, disjoint from the id alphabet `[a-z0-9]{1,8}`) and pairs them
with ids by position, then asserts every certified record's thread equals the *observed*
thread for that id. `test_a_built_envelope_always_contains_every_hit` records the disclosed
ids under `t1` and the dropped ones under `t2` and asserts no withheld record ever names
`t1` — the thread of the source that would benefit from the claim.

**Acceptance, item by item.** R-DISC's reproduction raises ✓. A record whose thread
disagrees with its id's recorded origin is rejected at certification ✓ (the ledger derives,
so the disagreement cannot be filed; the envelope refuses a rewritten record against the
certificate). Property test generates ids and threads independently ✓.

**What this does *not* close.** The thread map is supplied by the same in-process code that
mints the observation, so an observation that can claim ids nothing fetched can claim
threads nothing observed. That is A1's residue, unchanged and now stated in `FetchedIds`'s
own docstring: deriving removes the *caller's* unchecked assertion, not every unchecked
assertion, and only A1's content witness closes it.

### R-DISC-008 / R-ARCH-014 — the A4 pinning test's stale docstring

`tests/test_envelope_contract.py`'s section header and the docstring of
`test_the_included_arithmetic_follows_contract_r05_and_not_ad_d2s_worked_example` now record
that A4 ruled R-05 correct, why, and that `§D.2` was corrected; the test itself is unchanged
and stays. `wire.py::Source._counts_match_the_payload` cited "the round-1 handoff" and now
cites A4 as settled. Added `test_the_ruling_is_visible_everywhere_the_amendment_says_it_changed`,
which reads `ARCHITECTURE_AMENDMENTS.md` and `ARCHITECTURE_DECISION.md` and asserts §D.2's
worked example reads `"included": 42` with A4 cited inline, plus that both docstrings name
A4 — the propagation is now checked rather than remembered, which is the thing that failed
twice. Verified failing-first: restoring the round-5 wording in `wire.py` fails it.

### R-ARCH-015 — the quote stripper deleting the sender's own sentence

Treated above its severity, as instructed: this is silent content loss.

**Before** (`probe_arch015.py`): body `"Two points before Friday.\n\nAs I wrote earlier,
check with devops@example.com at 15:14:\n\n> The freeze starts Friday.\n"` →
`reply='Two points before Friday.'`, `quoted_chars=88`. The sender's own sentence is gone
and declared as prior conversation.

**After**: `reply='Two points before Friday.\n\nAs I wrote earlier, check with
devops@example.com at 15:14:'`, `quoted_chars=27` (the real quoted line only).

**The rule.** `_looks_like_an_attribution_line` adds two structural conditions to round 5's
three: the identifying evidence (address or date/time) must sit **before** the attribution
verb — every locale in the verb list writes *when*, then *who*, then the verb, and only the
sender may follow it — and the verb's subject must not be first-person. Both are read off
the line's structure, not off a locale-specific prefix list, so they do not narrow the
locale coverage: all ten locales in `_ATTRIBUTION_VERBS` (the corpus's three plus the seven
R-ARCH verified independently in round 5) still strip correctly, verified by a
parametrised test over one shared body shape.

**Does not catch, and now pinned in the corpus rather than only in a docstring.** A sentence
whose *first* clause carries a date or address ahead of the verb — `"Following our 15:14
call, here is what the vendor wrote:"` — is still removed. It is a declared `known_gap`
(`ATTRIBUTION_SHAPED_SENTENCE_STILL_REMOVED`), its current behaviour is pinned by
`test_the_declared_gap_still_behaves_exactly_as_it_is_declared_to`, and
`test_the_known_gap_list_is_exactly_what_is_declared_open` now checks the list in both
directions (round 5's version asserted it was empty).

**Failing-test-first**: reverting to "evidence anywhere on the line" fails 4 tests, including
the new corpus case and both false-positive shapes.

### R-ARCH-016 + R-SEC-021 — the shape bound that read one spelling

Fixed as one defect. `measure_raw_shape` read `node["parts"]` only when `node` was a literal
`dict`, and the validator gated on `isinstance(data, dict)`. Both are now read by *shape*:
`_child_parts` takes children from a `Mapping` key or an object attribute, holding a list or
a tuple; `_declared_payload` does the same at the root; the `isinstance` gate on the
validator is gone.

**Before** (`probe_payload.py`): `measure_raw_shape` on a 2,000-level `Part` tree returned
`(1, 1)`, and all three entry points (`MessagePayload(...)`, `model_validate`,
`parse_payload`) accepted it; a `MappingProxyType`-wrapped 32,000-part payload built in
0.07s through `model_validate` and `parse_payload`.
**After**: the same tree measures `(2001, 2001)` and every entry point refuses with
`ContentProcessingError`; both `MappingProxyType` paths refuse.

**Tests are a matrix, because testing one spelling is what let the others through**: three
spellings (`raw_dict`, `mapping_proxy`, `built_part_models`) × three entry points
(`parse_payload`, `model_validate`, `keyword_constructor`), asserted over-part-cap refused,
over-depth-cap refused, and at-cap still built — plus a measurement test that all three
spellings of one structure measure identically. Reintroducing **both** halves fails **11**
of those; `mapping_proxy-keyword_constructor` correctly still passes (`**proxy` becomes a
real dict), which is the matrix discriminating rather than blanket-failing.

**Where else does the pattern appear?** The work order asked. I swept every
`isinstance`-on-a-container in `server/**` and probed the two that walk structures
(`probe_pattern_sweep.py`):

| Site | Verdict |
|---|---|
| `content/payload.py` (`measure_raw_shape`, the validator gate) | **the defect** — fixed |
| `wire.py::Affordance.mentions` — walks `dict`/`list` over `JsonValue` | **not the defect, and the reason matters.** The walk runs on *already-validated* data: a `MappingProxyType` or a tuple nested in `args` is refused by pydantic before `mentions` ever runs, and a `MappingProxyType` passed *as* `args` is coerced to a real `dict`. The payload walk ran in a `mode="before"` validator on unvalidated input, which is precisely why the same spelling-sensitivity was a hole there and is not here |
| `config.py::load_config` (`isinstance(raw, dict)`) | not the defect: the input is `json.loads` output, which can only be `dict`/`list`/`str`/`int`/`float`/`None`; the check is exhaustive for "is this a JSON object" |
| `content/mime.py`, `envelope/measure.py` | no type gates; both walk already-built `Part`/`Envelope` models |
| `content/headers.py`, `content/html_text.py` | `str`/`bytes` from `email.header.decode_header`, and lxml's own documented "tag is not a string" comment/PI convention. Exhaustive by the library contract |
| **`tools/guards/sweeps.py::_populate`** | **the same pattern, in the guard engine — this is R-SEC-023.** A resolution pass that handled one concrete spelling of an assignment (`len(targets) == 1`) and was silently absent for the others. Fixed below, and the connection is recorded in the code comment |

So: the pattern appeared in **three** places, not two. The third is R-SEC-023, which the
work order listed separately; I would not have connected them without the instruction to
look for the pattern rather than patch the instances.

**Does not catch** (now in `refuse_unbounded_payload`'s docstring and pinned by a test):
`Part.model_validate(<deep raw dict>)` has no bound — `Part` is the leaf model, not the
boundary, and putting the walk there would re-measure every subtree at every level of an
ordinary parse.

### R-ARCH-017 — A3's bound diluting R-RETR-002's property

Measured before touching anything (`probe_arch017.py`, 2,000 examples of the shared
strategy): **72.4% out of range** (refused by A3 regardless of whether occupancy works),
27.1% overlap-only, **0.6% reaching the success branch** — matching R-ARCH's 71% / 28.4% /
0.65% independently.

Split into two generators, one per property. `runs_inside_the_thread()` draws sizes first
and then each start from the range the finished thread actually has, so every example is in
range by construction; `free_shape` draws positions from `[-4, 12]` independently of the
thread length. After (`probe_arch017b.py`, 2,000 examples each):

| Generator | Exercises its property | Wasted on the other check |
|---|---|---|
| occupancy (`test_a_source_that_builds_never_holds_two_dispositions_at_one_position`) | **100%** in range: 97% clash, 3% success branch | 0% |
| A3 (`test_a_source_that_builds_places_every_position_inside_the_thread`) | **84.2%** out of range | — |

The occupancy test's refusal branch now asserts *which* check fired (`"same thread position"
in message`), so the property cannot silently drift back into being a test of A3's bound.
Verified failing-first, and that each catches only its own defect: disabling the occupancy
check fails the occupancy property alone; disabling A3's upper bound fails the A3 property
plus the two pre-existing dedicated tests.

### R-ARCH-018 — participation is not placement

Added a `CAPTIONS` table (one word per field: the number after `position` is the position,
the name after `thread` is the thread), a completeness test that every kind and every field
has a caption, and `test_every_parameter_is_rendered_in_the_place_that_names_it`. Floats are
matched by value within 0.01, because `cosine` legitimately renders rounded. Plus
`test_the_placement_check_catches_the_swap_that_passed_all_fifty_tests`, which builds
R-ARCH's swapped renderer as a subclass, shows it still passes participation, and shows it
fails placement on both traded fields.

**Failing-test-first**: performing R-ARCH's actual swap in `reasons.py::ThreadMember.render`
— the one that passed all 50 tests in round 5 — now fails 2 tests.

This is not a format-string copy: the captions are an independent statement of meaning, and
the *values* come from the constructed variants, never from the source.

### R-SEC-022 — `import httpx._client as hc; hc.Client()`

The guard matched the module string `"httpx"` exactly. It now matches the `httpx` package:
`module == "httpx" or module.startswith("httpx.")`, for `Client`/`AsyncClient`. Four shapes
tested (module alias, dotted attribute, `from`-import, rebinding from the submodule), plus
`test_the_private_submodule_path_is_the_same_class_object`, which asserts at runtime that
`httpx._client.Client is httpx.Client` — so the widening rests on a fact about `httpx`
rather than on my say-so — plus a false-positive control (`vendor.httpx_compat.Client()` is
not caught). Reintroducing the exact-match fails all four.

### R-SEC-023 — chained assignment (the shared engine)

`_populate`'s third pass required exactly one target, so `a = b = os.write` resolved
*neither* name and both guards lost it. Replaced with `_assigned_pairs`, which yields every
`(name, value)` an assignment binds: every target of a chained assignment, and element-wise
pairs of a tuple/list assignment. Starred unpacking is deliberately **not** read (the
pairing would depend on a length this pass may not know, and a wrong pairing resolves a name
to the wrong callable) and is documented and pinned. Five shapes tested across both guards;
the sibling assertion that calling the *other* name of a tuple assignment is not a write
guards the false-positive direction. Reintroducing the single-target restriction fails 3;
also disabling the tuple branch fails the other 2.

### R-SEC-024 (LOW) — inherited attributes, and the seventh guard's gap list

Both halves. **Code**: `_Scope` records each class's bases and `class_attribute` follows them
depth-first in declaration order, own body winning, with a visited set; nested classes lift
their bases with their tables. `class Base: handler = os.write` / `class Sub(Base): pass` /
`Sub.handler(...)` and `Sub().handler(...)` are both caught now, at two levels of
inheritance, for both guards. A subclass that *overrides* the attribute correctly reports
nothing. **Documentation**: the seventh guard's docstring was written fresh in round 5 with
a gap list that was a strict subset of what its shared mechanism misses. It now names the
instance attribute, the instance held in a variable, the data-structure/factory/`getattr`
shapes, the same-named subclass and the out-of-file base class — and every one of those six
is exercised against the guard by `test_each_documented_http_client_gap_is_really_a_gap`, so
the list cannot be wrong in either direction. It also now states what it *does* resolve
(class attributes, dataclass fields, chained assignment), which round 5 left unmentioned
while relying on it. Reintroducing the inheritance walk removal fails 4.

**False positives.** The ordinary-code sweep was extended with a class hierarchy whose
inherited attribute is called `write`, a subclass overriding `clean`, and chained/tuple
assignments binding names the guard resolves. Still exactly three violations, all real
writes. The seven shipped guards remain clean over `server/src`.

---

## What I did NOT fix, and why

- **R-SEC-025** (`field(default_factory=lambda: os.write)` unresolved while the
  non-functioning `field(default_factory=os.write)` is "caught"). Not in the work order.
  Round 5's handoff claim about it was an overstatement, so rather than leave that standing
  I corrected the *claim*: the guard's "Does not catch" list now names the lambda form and
  says the working idiom is missed, and `ROUND_FIVE_WRITE_GAPS` runs it against the guard so
  the statement is pinned. Documented, not fixed.
- **R-DISC-010** (`+0000` offsets accepted though the label says RFC 3339). Not in the work
  order; untouched.
- **A1's content witness.** Explicitly not mine to build; R-DISC-009's residue above is its
  responsibility and is stated as such.
- **`Part.model_validate` unbounded.** Deliberate, argued in the docstring, pinned by a test.
- **The seventh guard's remaining residues** (instance attribute, instance-held variable,
  `getattr`, factory, dict, same-named subclass, out-of-file base). Documented and pinned,
  not caught. `self.ctor = httpx.Client; self.ctor()` still bypasses.

## Where my work is weakest

1. **R-ARCH-015 is still a heuristic, and it is the change most likely to be wrong on real
   mail.** "Evidence before the verb, subject not first-person" is a structural rule about
   ten locales' word order that I verified against fifteen constructed lines and a
   twenty-case corpus — none of it real mail, because there is none in this repository. The
   residue I pinned is one shape; I do not claim it is the only one. If a reviewer wants to
   attack anything, attack this: a line ending in a colon above a quoted chain is a small
   target and the cost of being wrong is deleting what somebody wrote.
2. **R-DISC-009 moves the unchecked assertion rather than eliminating it.** The thread now
   travels inside the sealed observation, which is where a fabricated observation would put
   it too. I believe this is the correct place for it and it is A1's job to check it, but a
   reviewer should confirm that the derivation is real (`HitOrigin` → record) and not merely
   relocated, and should attack the origin-upgrade path I added: a second observation may
   supply a thread the first did not carry, which is a write to an existing origin and the
   only place in this module where a recorded fact is revised. Its disagreement case raises,
   but the *upgrade* case is trusted by construction.
3. **The occupancy generator now sits at the other extreme**: 97% of its examples clash and
   only 3% reach the success branch. Detection is unaffected (removing the check moves the
   97% into the success branch, where the assertion catches them), but the "a legitimately
   segmented map still builds" direction is exercised by ~9 examples per run.
4. **The `CAPTIONS` table is a hand-written statement about ten renderers.** It catches the
   swap it was built for, and the completeness test forces a new kind to arrive with an
   entry — but a renderer that used the *same* caption for two fields would satisfy it, and
   nothing checks that captions are distinct within a kind.
5. **Guard-engine changes were verified against planted files, never against a large real
   corpus.** The inheritance walk is new resolution machinery, and new resolution machinery
   is what produced R-SEC-015's false positive. My false-positive evidence is the extended
   ordinary-code sweep plus the shipped tree; R-SEC's own independent sweep would be worth
   re-running.
