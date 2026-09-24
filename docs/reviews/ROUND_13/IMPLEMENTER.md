# ROUND 13 — implementer report

**Implementer:** round-13 implementer, 2026-09-02. Parts 1–5 of
`docs/reviews/ROUND_13/WORK_ORDER.md`.

The work landed across two working sessions of this round. The second session began by
**re-verifying the first one by execution rather than by reading it** — running the round-12
attack scripts, then writing new ones against the new design. That pass found **three defects in
this round's own fixes**, each of which is recorded below under the part it belongs to and marked
*found by attacking this round's fix*. Two more were found by the reintroduction battery, which
reported `NOT CAUGHT` for defects it had genuinely introduced.

Everything here is written to be checked. The battery is **21 defects, reintroduced one at a time
against the finished tree, every anchor asserted before it was applied: 21 caught, 0 missed**, and
the scratch tree was byte-compared against its pristine snapshot afterwards
(`TREE RESTORED, ALL FILES MATCH`).

---

## The short answer to the round's question

**Yes, the two fixes share a mechanism, and it is a third module that neither of them owns.**

`mailweave.sealing.IdentityRegistry` is a side table keyed on object identity, holding what the
minting code established at the moment it established it. `SeedSession`'s credential nonce and
`DispositionCertificate`'s certified numbers both live in one, and both classes refuse
subclassing. That is the whole of Parts 1 and 2:

| | before | after |
|---|---|---|
| `SeedSession` | the proof bound `str(id(credential))` — an address, inherited by the next allocation | the proof binds a **nonce** held against the credential object in `_OBSERVED` |
| `DispositionCertificate` | the certified numbers sat in the instance's own `__slots__` | the object **holds nothing**; every property reads `_CERTIFIED` |

Both defects had one shape — *the object was asked to vouch for itself* — and the answer is a fact
the object cannot restate, that a copy does not inherit, and that a later object at the same
address cannot pick up. No construction path is consulted, so none has to be enumerated, which is
amendment A7's move (change the operation so the bad state is unrepresentable) applied to
authority instead of to text.

**What the shared mechanism does not buy, and this round had to learn by being caught by it:** a
registry makes the facts unreachable except by asking it; it cannot make a caller ask. See Part 2.

---

## Part 1 — R-SEC-045: the proof bound a memory address

### Reproduced first

`/tmp/rsec12/attack_public_forge.py` against the round-12 tree: four public attribute reads, drop
the honest session, allocate until a credential lands on the freed address, build with the public
constructor. **The id was reused on allocation #1** and `assert_bound_to` authorised a credential
reporting a different mailbox.

### What changed

New `server/src/mailweave/sealing.py` — `IdentityRegistry`, keyed by identity **twice over**: the
dict is keyed by `id(subject)` and the entry must then prove it belongs to *this* object
(`ref() is subject`). The second check is the one that matters: a recycled `id` finds an entry
whose weak reference no longer resolves to the caller's object, and that returns `None`, which
every caller treats as "never minted". A `WeakKeyDictionary` was rejected in terms — it consults
`__hash__`/`__eq__`, so an object that merely compares *equal* would inherit the authority, which
is the same defect one axis over on a value the subject's own class controls.

In `pinning.py`: `_mint_proof` mints a random nonce against the credential in `_OBSERVED` and HMACs
it; `_expected_proof` is lookup-only and returns `None` for a credential this process never
observed. A credential that cannot be weakly referenced is **refused at the mint**
(`CannotBeSealed`) rather than bound to an address. R-SEC-052's ambiguity is closed at the same
time: `_material` length-prefixes every component, and the two colliding pairs the finding named no
longer collide (executed).

### Verified by execution, with my own probes

`/tmp/r13/attacks/a_seed.py`:

* the R-SEC-045 route over **40 independent trials**: the id was reused in **32 of 40**, and
  **0 forgeries were authorised** — through the public constructor *and* through
  `object.__new__` + a copied `__dict__`, which skips `__post_init__` entirely;
* six rebuild paths (`copy`, `deepcopy`, pickle at two protocols, `__reduce_ex__(2)`,
  `object.__new__`) with a tampered address: **all refused**; the same six untampered: all still
  authorise their own credential, so the refusals mean something rather than tracking an artefact
  of deep copying;
* subclassing refused three ways; `__bases__` reassignment refused by CPython's layout check;
* a `deepcopy` of the *credential* is refused — it never answered `getProfile`.

### Reintroduction checks

| | defect put back | anchors | result | caught by |
|---|---|---|---|---|
| D1 | the proof binds `str(id(credential))` again — **the shipped defect, verbatim** | matched | **caught** | 7 tests, incl. `…_stolen_proof_does_not_authorise_a_credential_at_the_freed_address`, `…_nonce_belongs_to_the_object_and_not_to_its_address` |
| D2 | nonce minted, but the use site looks it up on the **stored** credential | matched | **caught** | 3 tests, incl. `…_minted_from_one_credential_is_refused_by_another` |
| D3 | the use-site check disabled — the constructor is the only check again | matched | **caught** | 12 tests, incl. the standing sweep |
| D4 | `SeedSession` may be subclassed again | matched | **caught** | 2 tests, incl. the new subclassing sweep |
| D5 | HMAC material back to separator joining (R-SEC-052) | matched | **caught** | `test_two_different_triples_cannot_share_the_hmac_material` |
| D6 | `recall` stops proving the entry belongs to *this* object | matched | **caught** | `test_an_object_at_a_dead_entrys_address_recalls_nothing` + 1 |

### What I could not establish

* **Control 1 remains unverifiable from here.** Whether Google's Testing-status allowlist really
  refuses consent for the personal mailbox is a Console setting. The module still says so.
* **Nothing consumes a `SeedSession` yet.** `assert_bound_to` has no production caller; WS-16 must
  actually call it and no code can force that.
* **The cross-process claim is still tested by substituting the key**, not by spawning an
  interpreter. This suite runs no subprocess and I did not add one.
* **32/40 is a measurement of this interpreter**, not a constant. The finding never depended on the
  rate — one success is enough — but the number is CPython 3.12 in this container.

---

## Part 2 — R-SEC-046 / R-SEC-047: the same shape at the disposition seal

### What changed

`DispositionCertificate` **holds nothing**. `_CertifiedFacts` — every number `certify` computed —
lives in `_CERTIFIED`, an `IdentityRegistry` keyed by the certificate object, and every property
reads it through `_certified`, which raises for an object no ledger minted. A copy, a pickle round
trip, a `__reduce_ex__` rebuild or an `object.__new__` shell is a *different object*, so it does
not state a **different** disposition — it states **none**, and R-SEC's two plain assignments now
fail where they are written because the slots they wrote no longer exist.

One layer up (R-SEC-047), `Envelope` re-establishes its invariants **where the wire form is
produced**, in a `mode="wrap"` model serializer, and the validators are **discovered off the class**
rather than listed, so one added in a later round is covered the day it exists. `model_copy` gets
the same re-establishment as an early failure; `model_construct` and a write past `frozen=True`
walk past that and are caught at the wire.

### The defect this round's own fix did not close — found by attacking it

Holding the facts off the object closes every route that *rebuilds* a certificate. It closes none
that **replaces the reader**:

```python
class Forged(DispositionCertificate):        # the class statement, types.new_class, type.__new__
    @property
    def withheld(self): return ()
    @property
    def withheld_ids(self): return frozenset()

Envelope(..., disposition=object.__new__(Forged))   # ACCEPTED, and it serialised
```

`_certified` is never consulted, so nothing raises, and `Envelope`'s field is an `isinstance` check
a subclass passes. **I built this against the finished registry-based fix and the envelope
published `withheld: []` and `partial: false` for a response missing a message** — the same wire
output R-SEC-046 produced, through a route the fix had not touched.

This is R-RETR's round-3 attack 8 on this module's own mint token — defeat a token by subclassing
rather than by reaching for it — which `SeedSession` has refused since round 12 and which neither
of its two peers in the same category did. All three now refuse subclassing, and the standing sweep
enforces it so the rule outlives these three classes (Part 5).

`FetchedIds` is included for uniformity, and its docstring says plainly that it buys less there: it
stops the one-shot `_release` latch being overridden and makes `retrieval/transport.py`'s three
`isinstance(page, FetchedIds)` checks mean the class — and it does **not** touch amendment A1's
over-recording residue, because that constructor is public by design.

### Verified by execution

`/tmp/r13/attacks/a_cert2.py`, `a_sub.py`, `a_wire.py`:

* the three subclass routes refused, `__bases__` reassignment refused by CPython;
* a duck-typed impostor refused by `Envelope`'s field type (a fact about the consumer, and the
  docstring now says so rather than claiming it as a property of the certificate);
* a bare `object.__new__` shell of the real class answers **nothing**;
* **ten serialisation routes** driven against a tampered envelope — `model_dump()` in both modes,
  `model_dump_json()`, `include`, `exclude`, `by_alias`, `warnings=False`, the envelope as a field
  of another model, and a `TypeAdapter` over a list — every one refused, plus `copy`, `deepcopy`
  and `pickle` of the whole envelope;
* the round-12 scripts `attack_forged_certificate.py`, `attack_disposition_seal.py` and
  `attack_seal_peers.py` all refuse on the finished tree.

**One route survives and is named rather than patched:** `dict(envelope)` is Pydantic's
field-iteration convenience — a bulk attribute read — so it returns the tampered values exactly as
`envelope.withheld` does, and a caller who serialises that dict themselves has assembled a payload
this class never produced. Closing `__iter__` would close one route out of every possible hand
assembly and leave the impression the class is sealed against all of them, which is the enumeration
habit this round exists to correct. It is written into `response.py` and pinned by
`test_the_attribute_read_residue_is_what_the_docstring_says`, which asserts the residue **still
exists**, so the paragraph cannot quietly become an overstatement.

### Reintroduction checks

| | defect put back | anchors | result | caught by |
|---|---|---|---|---|
| D7 | certificate keeps its facts in its own slots, token checked only in `__init__` — **the shipped defect, verbatim** | matched | **caught** | 9 tests, incl. `…_forged_certificate_cannot_reach_an_envelope` and the capability sweep |
| D8 | `DispositionCertificate` may be subclassed again (this round's own finding) | matched | **caught** | 4 tests |
| D9 | `FetchedIds` may be subclassed again | matched | **caught** | 4 tests |
| D10 | the wire form stops re-establishing the invariants | matched | **caught** | 11 tests |
| D11 | `model_copy` stops re-establishing them | matched | **caught** | `test_model_copy_cannot_restate_the_disposition` |
| D12 | the wire re-runs a hand-written validator instead of discovering them | matched | **caught** | 12 tests |

D7's patch reverts `__repr__`'s registry lookup as well as the property's. Without that it is a
*partial* reintroduction: the class keeps a use site the sweep can see, the sweep does not fire, and
the battery's result would have understated what the sweep covers. The first run showed exactly
that and the patch was corrected.

### What I could not establish

* **`dict(envelope)` and direct attribute reads** are outside any check here, permanently.
* **The refusal's type does not survive serialisation.** Pydantic wraps whatever a serializer
  raises, so a caller sees `PydanticSerializationError` carrying the invariant's message. That is a
  real cost of checking at the wire rather than in a hand-written `to_wire`, taken deliberately.
* **Nothing in the tree copies or `model_copy`s either object today**, so both findings were inert,
  exactly as R-SEC said — and exactly as R-SEC-039 was before WS-16 was scheduled.
* **A1's bound-above is untouched.** `|H|` is still bounded below by what the transport fetched and
  above by nothing until the content witness exists.

---

## Part 3 — R-SEC-048: the exemption is now the producer's own shape

`spec.PROSE_FIELDS` became a mapping of **key → the list depth the producer writes it at** (0 for
the five keys `as_record` emits as plain strings, 1 for `notes` and `pre_registered_rules`), and
`_is_our_prose` requires exactly that many indices. `notes[0]` is prose; `notes[0][0]` is structure
somebody added. The walk also **refuses what it cannot read** — a record is the JSON types or it is
refused — instead of stepping over sets, frozensets and non-`dict` mappings, which is the same move
as bounding by shape rather than by intention.

Verified with `/tmp/rsec12/attack_od4.py` (every burial shape the finding named, over all seven
keys, now refused, and no refusal quotes what it refused) and `/tmp/r13/attacks/a_record.py`, which
adds shapes the finding did not raise: a `dict` subclass that hides its `items()`, a `list` subclass
that hides its contents, `OrderedDict`, a tuple subclass, a `bool` key, `bytes`. The two hiding
subclasses pass the check **and write nothing**, because `json.dumps` uses the same overridden
iteration — the checker and the writer agree, which is the property that matters.

| | defect put back | anchors | result | caught by |
|---|---|---|---|---|
| D13 | the exemption takes any number of list indices again | matched | **caught** | 8 tests, all seven keys |
| D14 | an unreadable container is stepped over, not refused | matched | **caught** | `test_a_container_the_walk_cannot_read_is_refused_rather_than_stepped_over` |
| D15 | a `str` subclass is measured on its own word again | matched | **caught** | `test_the_bound_is_taken_on_the_characters…` |

**D15 was `NOT CAUGHT` on the first run, and the test that should have caught it existed.** Its
planted liar returned `["short"]` from `splitlines`, and `is_one_line` compares
`value.splitlines() == [value]`, so a *different* string came back and the value was refused as
multi-line whether or not `record._plain` reduced it. The defence under test was never exercised —
a test passing for the wrong reason, which `AGENT_LOOP.md` §7.2 makes a finding in its own right. A
liar that returns `[self]` reports itself as one line and is caught only by the reduction; the test
now asserts `is_one_line(lying)` first, so it fails if the case ever stops being a case.

**Re-stated exit condition, matching what the code guarantees.** `assert_record_is_content_free`
refuses a multi-line or over-length string at any depth under any key, in any dict, list or tuple,
as a value **or as a key**, and refuses outright any value it cannot walk. It does **not** bound a
declared prose field at the producer's own shape: `{"notes": [<a 380-character body>]}` passes, and
must, because that is where probes write their own prose. That exemption is the residue, and today
it is empty by inspection — an AST sweep of both trees finds exactly **two** interpolations into any
`notes=`, both integers (`threads.py:187`). A probe that interpolated observed text there would
defeat the check, and no mechanism here would notice.

---

## Part 4 — the LOW findings

**R-SEC-049 (`__context__`) — closed.** The refusals are built inside the handler and raised
outside it, at all three entry points, so `__context__` is `None` rather than suppressed and the
raw `ValidationError` is unreferenced. Verified independently of the suite by
`/tmp/r13/attacks/a_context.py`: **50 forced failures** across both secret-bearing models × five
entry points (`__init__`, `model_validate`, `model_validate_json`, `model_validate_strings`, the
raw `validate_python`) × five corruption shapes, walking `__cause__` and `__context__` to any depth
— **0 problems**: no retained context, no secret fragment in any rendering. Reintroduction **D17**
(raise inside the handler with `from None` again) is caught by 3 tests.

**R-SEC-050 (the canary's completeness) — closed for the two shapes reflection can reach, and
refused at the source for the third.** `_mentions_secret` now asks
`issubclass(part, (SecretStr, SecretBytes))`, and discovery walks each class's own namespace as
well as the module's. Verified by **planting** all four shapes in the scratch tree: a `SecretStr`
subclass, a `SecretBytes` carrier, a model nested inside a class, and an honestly-written model —
the three planted leaks were discovered immediately and failed **15 tests** plus the standing sweep.
A model defined *inside a function* is in no namespace until the function runs and cannot be found
by any reflection, so it is refused at the source instead
(`test_no_model_is_defined_where_reflection_cannot_find_it`). Reintroductions **D18** and **D19**
are caught by 3 and 1 tests.

**R-SEC-051 (the scope coupling) — closed at the request, not at the sweep, and then closed
again.** `GmailClient._fetch_list_page` checks the **composed query** against the flag where the
request parameters are built, which is the only place the two settings meet; all four call shapes
R-SEC found are refused before anything reaches the transport.

*Found by attacking this round's fix:* the guard matched the operators **exactly**, so `IN:ANYWHERE`
— Gmail's operators are case-insensitive — passed the pairing check and reached the wire beside
`includeSpamTrash=false`. That is a fifth evasion of the same coupling, and it falsified the
comment beside the operator table ("that catches every spelling, because by then there is no
spelling left, only a string"). `widens_beyond_the_default_mailbox` now case-folds, which can only
refuse a *disagreeing* pair that used to be allowed. Reintroductions **D20** (the check removed)
and **D21** (the case-folding removed) are caught by 10 and 4 tests.

**R-SEC-052 (ambiguous HMAC material) — closed**, above, D5.

**R-SEC-053 (the `PROSE_FIELDS` de-duplication guard) — closed.**
`test_the_checker_uses_the_producers_declaration_rather_than_its_own_copy` asserts both that
`record.PROSE_FIELDS is spec.PROSE_FIELDS` and that `record.py`'s AST contains no local binding of
the name. Reintroduction **D16** — the exact R-ARCH-031 shape, a divergent copy widened by one key —
is caught, and the older test R-SEC named as insufficient still does not catch it, which is the
finding.

### What I could not close honestly, and did not

* **The canary's anti-vacuity guard is wrong for a model that does not exist yet.**
  `test_nothing_under_the_funnel_quotes_what_it_refused` asserts `refused >= len(driven) - 1` so the
  battery cannot pass by refusing nothing. For a **one-field** secret model whose field accepts a
  plain string, two of the seven corruption shapes are *valid documents*, so only five refuse and
  the guard fires — I hit this with a correctly-written planted model. It is not a leak and it fails
  loudly rather than silently, and relaxing an anti-vacuity guard to accommodate a model nobody has
  written is the narrowing this round is judged against. **Left as it is, recorded here.**
* **The widening vocabulary is three operators, not a parser.** `label:spam` and anything Gmail adds
  later are not seen. Whether such a spelling widens the set is a question about Gmail; the
  docstring now points at PF-20 rather than claiming the check is complete.
* **`errors(include_input=True)`** still returns the input object. Data, not a rendering; nothing
  calls it; unchanged from round 12.
* **R-SEC-044** (the egress allowlist and the port) is not in this work order and is untouched.

---

## Part 5 — the sweep's scope, argued

**Capability tokens are a decidable category here**, and the argument is not "we can recognise
authority in general" — it is that *this repository mints authority in exactly two idioms and both
are visible in the source*: a module-private sentinel compared with `is`, and a keyed proof compared
with `hmac.compare_digest`. To those the round adds a third way of establishing the same thing:
reading the object's facts out of a `sealing.IdentityRegistry`, which is the same property with
nothing left on the object to check.

`tests/test_standing_cycle_round13.py` sweeps for classes that do any of those and asserts two
things about each:

1. **it re-establishes the capability somewhere a use site reaches** — not only in a constructor;
2. **it refuses subclassing**, because moving the facts off the object does not stop a subclass
   overriding the members that do the asking. That rule exists because it caught this round.

The population is exactly three: `SeedSession`, `FetchedIds`, `DispositionCertificate`. A class that
checks no capability is **not in the population** rather than excused from it, which is why round
12's stated objection does not apply: `ProbeSpec` validates its own fields, checks no token, and is
never considered. Both halves are shown firing against planted instances, and
`test_the_capability_sweep_does_not_report_innocent_code` plants three innocent shapes — including
`ProbeSpec` verbatim — and shows none is reported.

**What the sweep cannot decide is asserted, not described.**
`test_the_capability_sweep_states_what_it_cannot_decide` plants a capability expressed as a plain
boolean and shows the sweep does **not** see it. That is a real gap; the alternative — guessing at
what looks like a token — is the sweep that reports innocent code and gets switched off.

**Is the re-scoping load-bearing? Measured, not asserted.** Two experiments in the scratch tree:

* **E1 — narrow the sweep back to `pinning.py`, change nothing else.** Caught immediately, by the
  sweep's own population assertion: it declares it must reach three sites and fails when it reaches
  one. The re-scoping cannot be silently reverted.
* **E2 — narrow it *and* relax its two self-checks, with the R-SEC-046 defect live.** The sweep goes
  quiet; only the eight behavioural certificate tests fail. That is exactly round 12's position,
  where those eight tests did not exist and nothing failed at all.

**And the sweep was fooled once, by this round's own battery.** `_refuses_subclassing` originally
accepted any `raise` anywhere inside `__init_subclass__`, so the battery's `return None` above the
`raise` left the sweep reporting the class as still refusing — a genuinely reintroduced defect
reported as `NOT CAUGHT`. The check is now on the first statement after any docstring, and
`test_a_refusal_that_returns_before_it_raises_is_not_a_refusal` keeps that case.

---

## Every module that claims something about what an attacker must do, and how I checked it

I ran each claim rather than re-reading it. Where a claim was false, the code changed — not the
claim's confidence.

| module | the claim | how it was verified |
|---|---|---|
| `harness/…/pinning.py` | `assert_bound_to` succeeds only if a `Profile` naming `self.address` was observed **from that object** in this process; residues named without a completeness claim | `a_seed.py`: 40 id-reuse trials (32 reuses, 0 forgeries), 6 rebuild paths × tampered/untampered, 3 subclass routes, `__bases__`; battery D1–D5 |
| `server/…/sealing.py` | closes every route that **rebuilds or rewrites** a sealed object; **says nothing about a subclass** | the subclass forgery was built and accepted before the claim was written this way — that is why the paragraph exists; `a_sub.py`, `a_cert2.py`, battery D6, D8, D9 |
| `server/…/envelope/disposition.py` (`DispositionCertificate`) | a certificate `certify` did not mint states **none** of the disposition; subclassing refused; a duck is refused **by the consumer**, not by this class | `a_cert2.py` (subclass, duck, shell, re-mint), `attack_forged_certificate.py`, `attack_disposition_seal.py`; battery D7, D8 |
| `…disposition.py` (`_RECORD_TOKEN`, `FetchedIds`) | "no supported call hands a caller the IDs a page returned"; subclassing now refused; A1's over-recording residue **still open** | enumerated the object's public surface: `endpoint, more_pages, next_page_token, page_size, recorded, size, thread_id` — not iterable, not indexable, no message ids; battery D9 |
| `server/…/envelope/response.py` | every route **through the serializer** re-derives the invariants; attribute reads are **not** covered | `a_wire.py`: 10 serialisation routes + 3 whole-envelope copies, all refused; `dict(envelope)` **does** return the tampered value and is named as the residue; battery D10–D12 |
| `harness/…/preflight/record.py` | refuses mail-shaped text at any depth under any key, and refuses what it cannot read | `attack_od4.py` (all seven keys, every burial), `a_record.py` (hiding subclasses, `OrderedDict`, tuple subclass, `bool` key, `bytes`); battery D13–D15 |
| `server/…/constants.py`, `harness/…/preflight/scope.py` | the two settings cannot disagree, "by then there is no spelling left, only a string" | **falsified by case** (`IN:ANYWHERE`), fixed, re-verified; battery D20, D21 |
| `server/…/validation.py` | no secret reaches any rendering, and the refusal leaves nothing to walk | `a_context.py`: 50 forced failures, 2 models × 5 entry points × 5 shapes, chains walked to any depth — 0 problems; battery D17 |
| `tests/fixtures/secret_models.py` | "a new secret-bearing model is covered the moment it exists" | four models planted in the scratch tree; three leaks discovered immediately, 15 tests + the sweep failed; the one shape reflection cannot reach is refused at the source; battery D18, D19 |

---

## The reintroduction battery, and why its result can be believed

`/tmp/r13/reintro.py` + `/tmp/r13/defects.py`. Each defect is applied to a scratch copy of the
finished tree at `/tmp/r13/tree`, imported through `PYTHONPATH` (confirmed: `mailweave.__file__`
resolves under `/tmp/r13/tree`), the whole offline suite is run, and the file is restored from
`/tmp/r13/pristine`.

**Anchors are asserted, twice over.** `apply()` refuses unless `text.count(old)` equals the count
the patch declares, **and** refuses if the replacement leaves the file unchanged. An `AnchorMiss` is
recorded as an ERROR and never as a pass. Round 12's failure — `ruff format` reflowing the code
after the anchors were written, so `str.replace` matched nothing and three defects reported green —
cannot produce a silent pass here.

That machinery earned itself in this round:

* the first dry run reported **three anchor problems**, including one caused by a `ruff format` pass
  that had reflowed a file minutes earlier — the exact round-12 failure mode, caught;
* every patched tree is `ast.parse`d before the suite runs, so a syntactically broken patch cannot
  masquerade as "caught" through collection errors;
* the first full run reported **two `NOT CAUGHT`** results, and both were real gaps in this round's
  own work: no behavioural test for `FetchedIds` subclassing (D9), and a test that passed for the
  wrong reason (D15). Both are fixed above.

**Final run: 21 defects, all anchors matched, 21 caught, 0 missed**, and
`TREE RESTORED, ALL FILES MATCH`. Two rows report `MISSING EXPECTED` — my *prediction* of which test
would catch it was wrong, not the result: D12 is caught by the new
`test_a_validator_added_after_this_round_is_re_run_at_the_wire_without_being_listed` rather than by
the older discovery test, and D16 by the new R-SEC-053 guard rather than by the older one R-SEC
named as insufficient. Both are the finding, restated as a measurement.

---

## What this round did not do

* **Did not touch `gmail/retry.py` or `rates.py`.** The backoff curve is the owner's decision.
* **Did not build amendment A1.**
* **Did not mark any rubric criterion** and added no rows to `FINDINGS_LEDGER.md` or
  `RUBRIC_TRANSITIONS.md`. Verified unmodified.
* **Did not update `RESUME.md`.** Round status is the orchestrator's to write.
* **No real or realistic personal mail text** was added to any fixture, test, log or record. The
  record-walker fixtures are synthetic filler chosen to be multi-line and over the bound, which is
  all the check looks at.

---

## What I could not establish at all

* Whether Google's Console **Testing-status allowlist** refuses consent for the personal mailbox.
  Unchanged, and still the largest gap in this area.
* Whether Gmail treats `IN:ANYWHERE` as the operator. The guard is now conservative in the safe
  direction either way, but the underlying fact is a live-run question (PF-20).
* Whether **Pydantic keeps routing mapping validation through a custom `__init__`**, and whether it
  keeps running a `mode="wrap"` model serializer on every dump route. Both are pinned by tests that
  fail loudly if a future version changes; neither can be pinned in the library.
* Whether either capability object ever **crosses a real process boundary**. Both cross-process
  claims are made by substituting a key or copying in-process. No subprocess was added.
* Whether the **behavioural** guarantees hold under `python -O`. The invariants raise explicitly
  rather than using `assert`, and `test_invariant_under_optimised_python.py` exists; I did not
  extend it to this round's new refusals.

---

## Final verification, verbatim

```
=== ruff check ===
All checks passed!

=== ruff format --check ===
135 files already formatted

=== mypy --strict ===
Success: no issues found in 109 source files

=== python -m tools.guards ===
guards clean: forbidden-import, generative-client, gmail-endpoint, ground-truth-isolation,
scope-literal, unaudited-disk-write, unwrapped-http-client over server/src

=== pytest -q -m 'not network' ===
........................................................................ [ 93%]
........................................................................ [ 97%]
...............................................                          [100%]

(the build prints no summary line; recounted with --collect-only)
1847 tests collected

=== python tools/rubric_status.py --check ===
criteria: 113  (mandatory 110, conditional 2, optional 1)
status:
  PASS         7
  FAIL         0
  BLOCKER      0
  NOT TESTED   106
reviewer transitions recorded: 11
gate-blocking criteria (NOT TESTED / FAIL / BLOCKER): 105
```

**Reintroduction battery:** 21 defects, one at a time, every anchor asserted before it was applied,
every patched tree parsed before the suite ran — **21 caught, 0 missed**, tree restored
byte-identical.

I did not verify my own work in the sense that matters. Three of this round's defects were found by
attacking its own fixes and two more by its own battery reporting `NOT CAUGHT`; R-SEC and R-ARCH
should assume there is a fourth and a sixth, and should attack the subclassing rule and the
`dict(envelope)` residue first, because those are the two places where this report's claims are
narrowest.
