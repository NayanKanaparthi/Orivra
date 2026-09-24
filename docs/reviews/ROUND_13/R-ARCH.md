# ROUND 13 — R-ARCH: Part 2, the disposition seal and the envelope contract

**Reviewer:** R-ARCH (independent), 2026-09-02. Gating reviewer for **Part 2** of
`docs/reviews/ROUND_13/WORK_ORDER.md` — R-SEC-046 and R-SEC-047, i.e. invariants **I-1**
(evidence preservation) and **I-2** (explicit partiality). Parts 1, 3, 4 and 5 belong to R-SEC
and are touched here only where they share `mailweave.sealing` with Part 2.

I did not write this code and did not take the implementer's report as evidence. Every claim
below was established by running something. Everything I could not establish is named in the
last section rather than softened.

---

## Environment

```
tree      /root/mailweave (not a git repo)
python    3.12.3 (main, Mar 23 2026) [GCC 13.3.0]  — .venv/bin/python
scratch   /tmp/rarch13/*.py   (attacks)  /tmp/rarch13/tree + /tmp/rarch13/pristine (reintroductions)
prior     /tmp/rsec12/snapshot  — the round-12 tree, used to diff what this round changed
```

**Every gate re-run by me, from the working tree, not read from the report:**

```
ruff check .................. All checks passed!
ruff format --check ......... 135 files already formatted
mypy --strict ............... Success: no issues found in 109 source files
python -m tools.guards ...... guards clean: forbidden-import, generative-client, gmail-endpoint,
                              ground-truth-isolation, scope-literal, unaudited-disk-write,
                              unwrapped-http-client over server/src
pytest -q -m "not network" .. all pass; 1847 tests collected
python tools/rubric_status.py --check
                              criteria: 113 (mandatory 110, conditional 2, optional 1)
                              PASS 7 / FAIL 0 / BLOCKER 0 / NOT TESTED 106
                              reviewer transitions recorded: 11
                              gate-blocking criteria: 105
```

All gates reproduce exactly as the implementer reports them, including the test count and the
rubric counts. `FINDINGS_LEDGER.md` and `RUBRIC_TRANSITIONS.md` are unmodified by me.

**What I diffed rather than read.** Against `/tmp/rsec12/snapshot`, `disposition.py` has 12 hunks
and `response.py` has 3. Nothing in `DispositionLedger` changed: `_admit`, `record_list_page`,
`record_history_additions`, `record_thread`, `record_shortlist`, `note_withheld`, `_record_for`
and `certify` are byte-identical to round 12. The set difference itself was not touched this
round, which is the right shape for a fix at the seal.

---

## Priority 1 — is the new design sound, or merely unbroken by the attacks tried so far?

### 1a. What the registry costs and assumes: measured, and it holds

`/tmp/rarch13/a7_registry.py`, all six executed against the shipped tree:

| question | result |
|---|---|
| does the side table drain? | 20,000 mint-and-drop → `len(_CERTIFIED._entries) == 0`. No leak in a long-lived process. |
| certificate outliving its ledger | ledger deleted and collected; `hit_count`, `withheld` still answer. The facts are held by the registry, not by the ledger, so this degrades to *nothing changes*. |
| two ledgers, one envelope | a certificate from ledger B attached to an envelope built from ledger A is refused by the disclosure digest. |
| concurrency | 8 threads × 3,000 mint-read cycles: 0 errors, table drains to the live set. |
| process boundary | pickling a whole `Envelope` succeeds; the unpickled certificate reports `<certifies nothing>` and `model_dump` refuses. **Fails closed.** |
| id reuse | 4,000 `object.__new__` shells against 200 freed certificate addresses: 3 landed on a freed address, **0 answered**. |

The `recall` double check (`id` key **and** `ref() is subject`) is what makes the last row true,
and it is load-bearing rather than belt-and-braces: my own reintroduction X2 (delete the
`ref() is subject` confirmation) is caught, and X10b (replace `recall` with a faithful
`WeakKeyDictionary`, equality lookup and all) is caught by
`test_the_registry_does_not_consult_the_subjects_own_equality`. The module's rejection of
`WeakKeyDictionary` is a pinned property, not prose.

*A note on my own method, because it is the failure mode this round exists to correct.* My first
attempt at X10 patched only the *lookup* and left the identity confirmation in place. The suite
stayed green and I nearly recorded a NOT CAUGHT. It was a **partial reintroduction** — my error,
not a gap in their tests. The implementer flagged exactly this shape for their own D7. It is very
easy to hit, and a reviewer who does not re-derive why a green run is green will manufacture a
false finding as readily as a false pass.

### 1b. "It states nothing" is a real property — and it is pinned

My reintroduction **X4** replaced `_certified`'s refusal with an empty `_CertifiedFacts`
(hit_count 0, withheld `()`, digest of the empty set) — the orchestrator's question turned into a
defect: *does anything notice if "states nothing" quietly becomes "states none"?* **Caught**, by
`test_a_rebuilt_certificate_certifies_nothing_at_all`. Ten property reads plus `assert_minted()`
are each asserted to raise. That is the right answer to the question, and it is asserted rather
than argued.

Nine of my ten first-batch reintroductions were caught (X1–X9), plus X10b, X11 and X13 in the
second batch. The tree was restored byte-identical. I have no reason to doubt the implementer's
21/21, and I confirmed their two most load-bearing rows independently (X1 ≙ D8, X3 ≙ D10).

### 1c. **But the facts are reachable from the certificate, and they are writable**

> "**The object holds nothing.** … there is no state on the instance to copy, to rebuild, or to
> write over" — `DispositionCertificate`, `disposition.py:848`

The third clause is false. `_CertifiedFacts` is `@dataclass(frozen=True)` **without** `slots`, so
every instance has an ordinary `__dict__`; and the facts object is one dereference away on the
certificate, through `_certified`, which is a single-underscore attribute on an object the caller
already holds. Two plain writes — *the same two writes R-SEC-046 used, one level down* — rewrite
the registry's own record:

```python
facts = certificate._certified            # not a module private; an attribute on the object
vars(facts)["withheld"] = ()              # `object.__setattr__` also works; neither is needed
vars(facts)["hit_count"] = 1              #   past `frozen=True`, which guards __setattr__ only
```

Executed (`/tmp/rarch13/b1_facts_mutation.py`, `/tmp/rarch13/b5_vars.py`) against the shipped
tree:

```
before:  certificate withheld = ['m2']  hit_count = 2  envelope.partial = True
the certified facts have an instance __dict__: True
certificate now: 1 []
wire: {'partial': False, 'withheld': []}
repr of the certificate: DispositionCertificate(H=1, disclosed=1, withheld=0)
```

`Envelope(**fields)` with `withheld=()` and `partial=False` is **accepted at the constructor** —
every validator runs and every one passes — and `model_dump(mode="json")` publishes
`"withheld": []`, `"partial": false` for a ledger holding a hit with a withheld record. No
`copy`, no `pickle`, no subclass, no `model_copy`, no `model_construct`, no import of `_CERTIFIED`.

This is **worse than R-SEC-046**, not equivalent to it. R-SEC-046 produced a *second, lying*
object that could in principle be told apart from the true one. Here there is exactly one record
of what `certify` computed and it has been rewritten, so every cross-check in the envelope agrees
with the lie, the certificate's own `__repr__` reports the lie as genuine, and nothing in the
process still knows the truth. Moving the facts off the object removed the *second* copy an
attacker could disagree with; it did not make the remaining copy immutable.

It also falsifies, by execution, two further sentences:

* *"a certificate cannot be lifted from one response and attached to another"* — rewrite the
  digest, threads and counts on the facts object and response A's certificate validates
  response B's payload (`/tmp/rarch13/b3_lift.py`, ACCEPTED, `partial: false`);
* *"the check is not somewhere a caller must remember to make it, it is the only way the facts
  can be reached at all"* — the facts can be reached, and reaching them is also how to change them.

The fix is small and I verified the direction rather than asserting it: a `NamedTuple` refuses
`object.__setattr__` (`AttributeError: can't set attribute`) while
`@dataclass(frozen=True, slots=True)` does **not** (`G(hit_count=1)`). Whatever is chosen, the
requirement is that what a property hands back cannot be written through, and that `_certified`
stops handing out the registry's own record.

**The round's exit condition is met and the property is not.** "No `DispositionCertificate` that
`certify` never minted is accepted by an `Envelope`" is *true* of the shipped code. This attack
uses a certificate `certify` **did** mint. An exit condition phrased over provenance cannot see a
defect in mutability, and this is the second time in two rounds that the seal has been defeated by
a door the exit condition did not name.

### 1d. The same move against `FetchedIds`

`object.__setattr__(page, "_consumed", False)` re-arms the one-shot latch, and the ledger records
one observation twice: `scan_scope` grows to 2 entries for one executed call. The refusal's own
text says this is what it prevents ("recording it again would put a second entry in scan_scope for
one executed call, claiming a query returned ids it never ran to get (AD A.7a, R-RETR-003)").
`FetchedIds`' constructor is public by design and A1 already concedes `|H|` is bounded above by
nothing, so the *effect* sits inside an admitted residue — but the R-RETR-003 sentence is not true
of the code as shipped, and it is one of the sentences this round was told to make true.

### 1e. Does the shared mechanism unify Parts 1 and 2? Partly

The primitive is genuinely shared and genuinely load-bearing: X2 and X10b, patched in
`sealing.py`, are caught by tests in *both* `tests/test_sealing.py` and
`tests/test_harness_pinning.py`, so the two users really do stand or fall together on the
identity rule. But the two applications are not the same strength and the report's "that is the
whole of Parts 1 and 2" flattens the difference:

* **Part 2** empties the object — reading *is* checking, so no caller can skip it (subject to 1c);
* **Part 1** keeps `proof` on the session and the check remains a comparison inside
  `assert_bound_to`, which a caller must reach. The implementer says plainly that nothing calls
  it yet.

"One mechanism, two strengths" is the accurate statement. The report's own table draws the
distinction correctly; the summary sentence above it does not.

---

## Priority 2 — the serializer as chokepoint

### 2a. It is a real chokepoint for `Envelope`'s own fields

I drove the routes myself rather than trusting the list. A tampered envelope
(`vars(env)["withheld"] = ()`) is refused by `model_dump()`, `model_dump(mode="json")`,
`model_dump_json()`, `include`, `exclude`, `warnings=False`, a `TypeAdapter` over a list, nesting
in another model, `model_copy`, `model_construct`, and a whole-envelope `pickle` round trip. The
honest envelope serialises unchanged and the JSON and python dumps agree. That half is sound.

### 2b. It is **not** complete: 17 validators of 41 (R-ARCH-034)

`_re_establish_every_invariant` discovers `type(self).__pydantic_decorators__.model_validators`.
That is `Envelope`'s validators and nothing else. Counted (`/tmp/rarch13/a5_enumerate.py`):

```
Envelope model-after = 17   (re-run at the wire)
nested  model-after = 24   (NOT re-run at the wire)
  Source 7 · MessageRow 4 · RetrievalReport 3 · CollapsedRun 1 · Reduction 1 · Ceiling 1 · …
```

`Envelope(...)` *does* revalidate a `Source` instance handed to it (I checked: a
`Source.model_construct` with a bad position is refused at construction, `loc=sources.0`). So
construction is guarded and exactly the three post-construction routes R-SEC-047 named are open —
one field over from where R-SEC-047 wrote them:

```python
envelope.model_copy(update={"sources": (a_source_built_with_model_construct,)})
```

→ **ACCEPTED AND SERIALISED**: `positions on the wire: [0, 900]  stated_total: 2  partial: False`
(`/tmp/rarch13/a4_modelcopy_nested.py`). The same result via `Envelope.model_construct` and via a
`vars(row)["position"] = 900` write past `frozen=True`. A second row moved onto an occupied slot
(`vars(row)["position"] = 0`, R-RETR-002's defect) also reaches the wire
(`/tmp/rarch13/a3_a3amendment.py`). Both values are refused at construction, so the checks exist
and are simply not among the ones re-established.

This is the project's persistent failure — **one shape validated, peers trusted** — for the tenth
time, and it is the *fix's* peer that was trusted: the round re-established the outer model and
left the twenty-four validators inside it, having pinned the identical `vars()`-past-`frozen`
attack on the outer model in its own test file.

What escapes is bounded and worth stating precisely. Anything that changes the **set of disclosed
ids** is caught by the certificate's digest (I verified: dropping a row from a `Source` is
refused). What escapes is everything about *where* and *how* evidence sits — A3's position bound,
R-RETR-002's occupancy, `MessageRow`'s reduction/affordance obligations. A3's own text is the
indictment: "Out-of-range positions **raise**. Clamping them into range would silently move
evidence to a slot it was never at, which is the failure class this project exists to prevent."
Moving `m2` to position 900 of a two-message thread is that, on the wire.

### 2c. Is there a response path that does not pass through Pydantic serialisation?

**Today, no — because there is no response path at all.** There is no MCP surface in the tree
(`server/src/mailweave/` has no server module; `cli.py` is `doctor`/`purge`/`auth login`). Nothing
in `server/src` or `harness/src` calls `dict(envelope)` or assembles a payload from attribute
reads; `measure.py` reads attributes but is called *from inside* a validator, so it is within the
check, not around it.

**Tomorrow, yes, and it is scheduled.** WS-15 (`IMPLEMENTATION_PLAN.md`) must emit
`structuredContent` **and a text mirror that agrees with it** (MCP-03, `AD §D.3`, PF-7). A text
mirror is by definition a second rendering, and nothing in this round constrains where it is
derived from. If it is built from the dumped dict it inherits the chokepoint; if it is built by
walking `envelope.sources`, it does not.

### 2d. Judging the `dict(env)` residue: honestly named, not honestly bounded

The paragraph in `response.py` is accurate and the test that pins it
(`test_the_attribute_read_residue_is_what_the_docstring_says`) is doing real work — it asserts the
residue *still exists*, so the paragraph cannot rot into an overstatement. I do not think closing
`__iter__` would be an improvement, and the "enumeration habit" argument against it is right.

But the residue is doing more work than the paragraph admits, for one reason the paragraph does
not give: **the two halves of Part 2 have different strengths under attribute reads.** For the
certificate, attribute reads fail closed — `copy.copy(cert).withheld` raises. For the envelope
they do not, and the object silently disagrees with its own proof:

```
t.withheld              -> ()
dict(t)['withheld']     -> ()
t.disposition.withheld  -> ['m2']      <- disagrees; only the serializer notices
repr(t)                 -> Envelope(... withheld=() ...)
```

`repr` is worth calling out on its own: an envelope that cannot be serialised still *renders* the
tampered value into any log or error message. The residue is therefore not "one convenience
method"; it is every read of the object, including the ones a human reads.

---

## Priority 3 — does it hold the contract, not just the attack?

Re-derived from `PRODUCT_CONTRACT.md` §4 and executed (`/tmp/rarch13/a8_contract.py`), against
the clauses rather than against round 12's finding.

**I-1, the set difference.** `withheld := H − disclosed` computes exactly what it did in round 12:
the ledger is byte-identical, and behaviourally `H = {m1,m2,m3}`, `certify(['m1','m2'])` yields
`withheld = {m3}`, `hit_count = 3`, `disclosed_hits = 2`, `H == disclosed ∪ withheld`. All three
residues still raise with their own messages: a hit with no cap note, a note for a disclosed id, a
note for an id not in `H`. **Unchanged and correct.**

**I-1 proof-of-violation (a) — `m ∈ H`, `m ∉ R`.** Producible on the wire by R-ARCH-032 and
R-ARCH-033. Not producible by any route that changes the disclosed set, because the digest binds it.

**A2 — an id enters `H` through any observed response, including `threads.get`.** Holds:
`record_thread` admits both ids, origins carry `clause='H-thr'`, `endpoint='threads.get'`, and the
certificate carries their threads. Unchanged by this round.

**A3 — 0-based, `0 <= p < stated_total`, raising not clamping.** Holds *at construction* for
`-1`, `2` and `900`, each refused with "places evidence outside the thread it describes", none
clamped. **Does not hold at the wire** — R-ARCH-034.

**A4 — `included` counts stubs.** Holds: a three-message thread disclosed as one body and two
stubs reports `included=3`, `included_as_stub=2`, `stated_total=3`,
`complete_as_reported=True`, `partial=False`, and the wire carries all three numbers. Unchanged.

**A1 — nothing this round claims what A1 says is impossible in-process.** Checked and clean.
`FetchedIds`' docstring says its subclass refusal "does **not** touch the over-recording
residue … the constructor is public by design", `sealing.py` says the registry "is not a defence
against code that imports the owning module", and `certify`'s bound-below/bound-above split is
untouched. No sentence added this round claims a content witness. The one A1-adjacent overstatement
is R-RETR-003's scan-scope claim (1d), which is about double-*recording*, not about `|H|`.

**I-2 — explicit partiality.** The clause that fails is the one my findings produce:
`partial: false` beside a real remainder, i.e. proof-of-violation (d) inverted. `_partial_flag_is_derived`
is correct and is re-run at the wire; what defeats it is that the facts it derives from can be
rewritten (032) or the validator itself replaced (033).

---

## Priority 4 — regression risk, and the tenth "one shape validated, peers trusted"

### 4a. The reader is not sealed (R-ARCH-033)

This round sealed `DispositionCertificate` against subclassing on an argument it stated in terms:

> "keeping the facts here is half of the property and the other half is that **only this type can
> be the one reading them**." — `sealing.py:59`

The type that reads them is `Envelope`. It is an ordinary Pydantic model and it is not sealed.
Three routes, all public, all executed (`/tmp/rarch13/a1_envelope_subclass.py`), each producing
R-SEC-046's exact wire output — `partial: false`, `withheld: []`, for a certificate that still
certifies `m2` withheld:

```
A1  subclass Envelope, redefine `_withheld_matches_the_certificate` by name   -> ACCEPTED, SERIALISED
A2  subclass Envelope, override `_re_establish_every_invariant`               -> ACCEPTED, SERIALISED
A3  subclass Envelope, redefine the wrap `model_serializer` by name           -> ACCEPTED, SERIALISED
```

Route A1 is the one that matters architecturally. `_re_establish_every_invariant` reads the
validators off `type(self)`, and a subclass method with the same name **replaces** the entry in
`__pydantic_decorators__.model_validators`. The discovery loop then faithfully runs the attacker's
no-op. *Discovery off the runtime class is a strength against forgetting and a weakness against
overriding* — it is future-proof only for a class nobody can substitute a reader into. The round
established this proposition for the certificate and did not carry it one level up to the class
that does the discovering.

I checked the narrow half of the fix by execution: patching the loop to read
`Envelope.__pydantic_decorators__` closes A1 (the forged subclass is then refused at the wire) and
does **not** close A2 or A3. It also fails
`test_a_validator_added_after_this_round_is_re_run_at_the_wire_without_being_listed`, which
subclasses `Envelope` to make its point. So the round has, in one file, a test that *depends on*
`Envelope` being subclassable with validator-substitution semantics, and a class next door sealed
against subclassing for exactly that reason. Any fix must resolve that, not just apply a decorator.

### 4b. The capability sweep cannot see this, by construction (R-ARCH-035)

`tests/test_standing_cycle_round13.py` sweeps classes that *check* a capability — an `is`
comparison against a module-private `object()` sentinel, a `compare_digest`, or a `recall`. Its
population is exactly `SeedSession`, `FetchedIds`, `DispositionCertificate`, and I confirmed the
planted-instance and innocent-code tests are genuine, not tautologies.

But its **rule 2** — "it refuses subclassing, because moving the facts off the object does not
stop a subclass overriding the members that do the asking" — is a rule about *the object that
does the asking*, and its population is *the object that holds the capability*. `Envelope` asks;
`Envelope` is not in the population and cannot be, because it compares no sentinel and calls no
`recall`. The sweep therefore enforces this round's newly-discovered rule on the three classes
that did not need it most and leaves the reading site — where the rule was actually discovered —
unswept. E2 in the implementer's report shows the re-scoping is load-bearing; it is load-bearing
one level below where the defect now lives.

### 4c. New constraints on future validators, undocumented (R-ARCH-037)

Putting the check inside the serializer makes the serializer re-entrant from any validator. A
future `mode="after"` validator that calls `self.model_dump()` now recurses and dies at
construction (`RecursionError` wrapped in `ValidationError`, executed). It fails loudly, so it is
LOW — but "a validator added in a later round is covered the day it exists" is true only for
validators that do not serialise, and nothing says so. (I checked the other half of this worry and
withdrew it: a classmethod-style `mode="after"` validator *is* handled correctly by
`validator.func(self)`.)

### 4d. Spot-checks of the round's own claims

* **"Three live defects found in its own fixes."** I re-derived the subclass finding independently
  before reading their account of it, and reproduced it — it is real and it is the right lesson.
* **"A test passing for the wrong reason."** I read the round-13 certificate tests line by line
  looking for others. `test_a_forged_certificate_cannot_reach_an_envelope`,
  `test_the_slots_r_sec_rewrote_do_not_exist_to_be_rewritten`, the rebuild parametrisation and the
  subclass parametrisation are all genuine and none is a tautology. The one I would flag is
  `test_every_after_validator_is_re_run_at_the_wire_rather_than_a_chosen_few`, which discovers the
  validators and then calls them *itself* — it establishes nothing about the serializer. The
  implementer noticed this and added the second test, which does. Not a finding; worth knowing the
  first one is weaker than its name.
* **"21/21 caught."** Not verified as such — I ran my own thirteen. 12 caught, 1 was my own
  partial reintroduction. I found no reason to doubt theirs.
* **`assert_minted` has no caller** anywhere in the tree. Harmless, but it is the named form of a
  check nothing names.

---

## Findings

```
ID: R-ARCH-032  Severity: HIGH  Rubric: none — contract I-1 / I-2, AD A.7a (RR EV-01, EV-03; bears on PART-03)
Location: server/src/mailweave/envelope/disposition.py:806 (_CertifiedFacts), :936 (_certified)
Repro: /tmp/rarch13/b5_vars.py and /tmp/rarch13/b1_facts_mutation.py —
  facts = certificate._certified            # a single-underscore attribute on the object
  vars(facts)["withheld"] = ()              # `frozen=True` guards __setattr__, not __dict__;
  vars(facts)["hit_count"] = 1              #   the dataclass has no __slots__
  Envelope(**fields, withheld=(), partial=False).model_dump(mode="json")
  Also /tmp/rarch13/b3_lift.py: rewriting digest+threads+counts lifts response A's certificate
  onto response B's payload and it validates.
Expected: "The object holds nothing … there is no state on the instance to copy, to rebuild, or
  to write over" (disposition.py:848); "a certificate cannot be lifted from one response and
  attached to another" (:843); I-1 — no cap may silently drop a hit; I-2 — a partial response
  discloses that it is partial.
Actual: the certified facts are one dereference from the certificate and are writable by two
  ordinary assignments — no copy, no pickle, no subclass, no model_copy, no model_construct, no
  import of the module-private `_CERTIFIED`. The Envelope is ACCEPTED at the constructor with
  every validator running and passing, and publishes `"withheld": []`, `"partial": false` for a
  ledger holding a hit with a withheld record. Strictly worse than R-SEC-046: the single
  authoritative record is rewritten rather than a second lying copy created, so every cross-check
  agrees and the certificate's own __repr__ reports the lie as genuine. Inert today — nothing in
  the tree mutates it — which is why HIGH and not BLOCKER, on the same reasoning R-SEC used for
  R-SEC-046. Note the round's exit condition is *satisfied*: this certificate WAS minted by certify.
Required fix: what a certificate property hands back must not be writable, and `_certified` must
  stop handing out the registry's own record. Verified fix direction (executed, not asserted): a
  NamedTuple refuses `object.__setattr__`; `@dataclass(frozen=True, slots=True)` does not. Then
  re-state the exit condition over what a certificate may STATE, not only over what minted it,
  because a provenance-shaped exit condition cannot see a mutability defect.
```
```
ID: R-ARCH-033  Severity: HIGH  Rubric: none — contract I-1 / I-2, AD A.7a (RR EV-01, EV-03; bears on PART-03)
Location: server/src/mailweave/envelope/response.py:87 (class Envelope), :206
  (_re_establish_every_invariant), :228 (_the_wire_form_states_only_what_still_holds)
Repro: /tmp/rarch13/a1_envelope_subclass.py — three routes, each ACCEPTED and SERIALISED:
  (a) class Quiet(Envelope): @model_validator(mode="after")
      def _withheld_matches_the_certificate(self): return self       # same name -> replaces it
  (b) class Deaf(Envelope):  def _re_establish_every_invariant(self): return None
  (c) class Loud(Envelope):  @model_serializer(mode="wrap")
      def _the_wire_form_states_only_what_still_holds(self, handler): return handler(self)
  Each yields `partial: false`, `withheld: []` while `env.disposition.withheld_ids == {'m2'}`.
Expected: "keeping the facts here is half of the property and the other half is that only this
  type can be the one reading them" (sealing.py:59); "nothing reaches the wire without the
  invariants holding of it" (response.py:232).
Actual: the certificate is sealed against subclassing and its sole reader is not. Route (a) is
  silent because the discovery reads `type(self).__pydantic_decorators__`, and a subclass method
  of the same name replaces the entry — so "discovered rather than listed", which makes the check
  future-proof against forgetting, makes it invisible against overriding. This is R-RETR round-3
  attack 8 and this round's own finding, one level up from where the round applied it.
Required fix: the reader must be as unsubstitutable as the thing it reads — seal `Envelope`
  against subclassing as `DispositionCertificate` is sealed, or make the wire check independent of
  the runtime class. Note the constraint: scoping the discovery to `Envelope.__pydantic_decorators__`
  closes (a) only, and `test_a_validator_added_after_this_round_is_re_run_at_the_wire_without_being_listed`
  currently *requires* Envelope to be subclassable, so that test must be re-expressed at the same
  time (executed both halves; see §4a).
```
```
ID: R-ARCH-034  Severity: HIGH  Rubric: none — amendment A3, contract I-2 / R-06 (bears on PART-05)
Location: server/src/mailweave/envelope/response.py:206-226 (_re_establish_every_invariant)
Repro: /tmp/rarch13/a4_modelcopy_nested.py —
  bad = Source.model_construct(**fields_with_a_row_at_position_900)
  envelope.model_copy(update={"sources": (bad,)}).model_dump(mode="json")
  -> ACCEPTED: positions on the wire [0, 900], stated_total 2, partial False.
  Same via Envelope.model_construct and via vars(row)["position"] = 900.
  /tmp/rarch13/a3_a3amendment.py additionally lands two rows on one slot (R-RETR-002).
  /tmp/rarch13/a5_enumerate.py: Envelope after-validators 17, nested after-validators 24.
Expected: R-SEC-047's required fix — "the disposition invariant holds for every envelope that
  leaves the process"; A3 — "Out-of-range positions raise rather than being clamped, because
  clamping would silently move evidence, which is the failure class this project exists to prevent."
Actual: the chokepoint re-establishes 17 of the 41 after-validators in the envelope tree — its own,
  and none of Source's 7, MessageRow's 4, RetrievalReport's 3 or the rest. Envelope() does
  revalidate a nested instance, so construction is guarded and exactly R-SEC-047's three
  post-construction routes are open, one field over from where R-SEC-047 wrote them. Anything
  that changes the disclosed-id SET is still caught by the digest; what escapes is where and how
  evidence sits. This is the project's tenth "one shape validated, peers trusted", in the fix.
Required fix: the wire form must re-establish the invariants of the payload it is about to emit,
  not only of the model that owns the serializer — recursively, or by a mechanism that does not
  have to enumerate which models are nested. Whatever is chosen, the count (17 vs 41) is the thing
  to assert, so the guarantee cannot narrow again without a test noticing.
```
```
ID: R-ARCH-035  Severity: MEDIUM  Rubric: none — round-12 Part 5 / round-13 Part 5 exit condition
Location: tests/test_standing_cycle_round13.py:65 (_checks_a_capability), :85 (capability_classes),
  :177 (test_every_capability_token_also_refuses_subclassing)
Repro: the sweep's population is {SeedSession, FetchedIds, DispositionCertificate}; `Envelope`
  compares no module-private sentinel, calls no compare_digest and no recall, so
  `capability_classes` never returns it. R-ARCH-033 is therefore invisible to the standing check
  that exists to prevent exactly it.
Expected: the sweep's own stated rule — "it refuses subclassing, because moving the facts off the
  object does not stop a subclass overriding the members that do the asking. That rule exists
  because it caught this round."
Actual: the rule is about the object that does the asking; the population is the object that holds
  the capability. The reading site is out of the population by construction, and it is where the
  defect the rule was written for now lives.
Required fix: extend the population to the classes that *re-establish* a capability as well as
  those that hold one — a class that reads a sealed object's facts and acts on them is the second
  half of the same property — or state, in the sweep, that reading sites are out of scope and why,
  so the gap is asserted rather than implied.
```
```
ID: R-ARCH-036  Severity: LOW  Rubric: none — AD A.7a / R-RETR-003
Location: server/src/mailweave/envelope/disposition.py:683 (_release), :700 (the refusal text)
Repro: /tmp/rarch13/b3_lift.py — after one legitimate record_list_page, a second is refused; then
  object.__setattr__(page, "_consumed", False) and the second record is ACCEPTED, leaving
  scan_scope with 2 entries for 1 executed call.
Expected: "recording it again would put a second entry in scan_scope for one executed call,
  claiming a query returned ids it never ran to get (AD A.7a, R-RETR-003)".
Actual: the one-shot latch is an ordinary slot and is re-armable. The *effect* on |H| sits inside
  A1's admitted residue (the constructor is public), but the scan-scope sentence is a separate
  claim and it is not true of the code as shipped.
Required fix: either hold `_consumed` where the object cannot restate it — the registry this round
  already built is the obvious place — or narrow the sentence to what the latch actually buys
  (an early failure on an honest double-record), and say the scan-scope count is bounded by the
  same public constructor A1 already concedes.
```
```
ID: R-ARCH-037  Severity: LOW  Rubric: none — maintainability of the round-13 chokepoint
Location: server/src/mailweave/envelope/response.py:206 (_re_establish_every_invariant)
Repro: /tmp/rarch13/b4_discovery_edges.py — an Envelope subclass with a `mode="after"` validator
  that calls `self.model_dump()` dies at construction with RecursionError wrapped in ValidationError.
Expected: "a validator added in a later round is covered the day it exists, and none of this has
  to be revisited when one is".
Actual: true only for validators that do not serialise the model. Putting the check in the
  serializer makes the serializer re-entrant from any validator, which is a new and undocumented
  constraint on every future validator. It fails loudly, hence LOW.
Required fix: say so where the constraint applies, or re-enter guarded (a per-instance sentinel).
  I checked and withdrew the neighbouring worry: a classmethod-style after-validator IS handled
  correctly by `validator.func(self)`.
```
```
ID: R-ARCH-038  Severity: LOW  Rubric: none — MCP-03 / WS-15 (forward-looking); contract I-2
Location: server/src/mailweave/envelope/response.py:252-262 (the residue paragraph),
  tests/test_certificate_seal_round13.py:422
Repro: /tmp/rarch13/a9_residue.py — on a tampered envelope, `t.withheld == ()` and
  `dict(t)["withheld"] == ()` while `t.disposition.withheld == ['m2']`; `repr(t)` renders the
  tampered value; only `model_dump` refuses. No consumer exists today (there is no MCP surface in
  the tree; nothing in server/src or harness/src reads an envelope's attributes from outside a
  validator).
Expected: the residue is "named rather than patched", which I agree with.
Actual: it is named but not bounded. The one planned consumer, WS-15, must emit `structuredContent`
  AND an agreeing text mirror (MCP-03, PF-7) — a second rendering by definition — and nothing
  requires that second rendering to be derived from the dumped form. The paragraph also understates
  the asymmetry it lives inside: for the certificate, attribute reads fail closed; for the envelope
  they return the lie, including through `repr` into logs.
Required fix: bound the residue where it will actually be crossed — a standing check that the
  MCP surface's text mirror is derived from the serialised form and not from attribute walks — and
  add the `repr`/`disagrees-with-its-own-certificate` case to the residue paragraph, since the
  paragraph is the thing the test pins.
```

---

## Recommendations, per criterion — **scoped, and none of them a PASS**

I am not marking anything and these are not transitions. Each is a recommendation about one
criterion, with its scope written into the sentence so it cannot be recorded as an unqualified
verdict. Twice in this project a scoped recommendation was banked as a PASS; these are written so
that reading only the first clause still gets it right.

* **EV-01 (Retrieved-hit containment, M, NOT TESTED).** *Recommend: leave NOT TESTED.* Nothing in
  this round changes that, and A1's bounded-above half is still unbuilt. My finding R-ARCH-032
  produces `m ∈ H, m ∉ R` on the wire, which is EV-01's proof-of-violation (a); that is a reason
  not to advance it, not a reason to fail it, since it is inert.
* **EV-03 (Withheld-record discipline, M, NOT TESTED).** *Recommend: leave NOT TESTED.* Same
  reasoning. The set difference itself is unchanged from round 12 and correct; what is defeated is
  the seal around it.
* **PART-03 (More-available signalled iff partial, M, currently PASS).** *Recommend: no transition
  from me — this is the orchestrator's call, and I am explicitly not recommending a revert.* I
  record only this, and it should not be read as a verdict on the criterion: PART-03's `[DEFINITIONAL]`
  basis is that the type will not build the bad shape, and R-ARCH-032 builds `partial: false` beside
  a real remainder **through the ordinary constructor with every validator passing**. Round 12 left
  PART-03 at PASS with R-SEC-046 open, which is the precedent; R-ARCH-032 is a wider defeat than
  R-SEC-046 was, which is the new fact. I have no view on which way that resolves.
* **PART-05 (Unexpanded content is visible as stubs, M, NOT TESTED).** *Recommend: leave NOT TESTED.*
  R-ARCH-034 puts evidence at a position outside the thread on the wire, which is PART-05's own
  territory; A3 remains enforced at construction and not at the wire.
* **Round 13, Part 2 as a whole.** *Recommend: Part 2 is NOT complete and should not be closed this
  round.* Three HIGH findings, two of them (032, 033) reproducing R-SEC-046's exact wire output
  through routes the fix did not consider, and one (034) reproducing R-SEC-047's own repro line one
  field over. This recommendation is about Part 2 only; I did not review Parts 1, 3, 4 or 5 and
  express no view on them.
* **The standing sweep (Part 5, in so far as it touches Part 2).** *Recommend: the sweep's population
  be revisited before it is relied on as the standing guarantee for this class of defect.* This is a
  recommendation about the sweep's scope, not about whether the sweep is good work — it is, and its
  planted-instance and innocent-code tests are genuine.

---

## Verdict

**BLOCKER: no.** Nothing here is release-blocking on its own terms: all three HIGH findings are
inert in the shipped tree — no production code copies, subclasses, `model_copy`s or mutates either
object, and there is no response surface for any of it to reach. That is the same reasoning R-SEC
applied to R-SEC-046 and R-SEC-047, and I am applying it consistently rather than escalating a
finding of the same class because it is mine.

**Round-blocking: yes.** Three HIGH findings, which `AGENT_LOOP.md` §4 makes round-blocking by
definition. Part 2's substance — moving the certified facts off the object, and re-establishing
the envelope's invariants where the wire form is produced — is the right architecture and I would
not have it undone. What it has not yet done is close the class it belongs to:

* the facts moved off the object are still **writable** (032);
* the object that **reads** them is not sealed, though the reason for sealing was stated (033);
* the re-establishment covers the outer model and **none of the twenty-four validators inside it**
  (034), through the very route R-SEC-047 filed.

The single sentence I would put in front of the next work order: **this round's exit condition is
met and the property it stands for is not.** "No `DispositionCertificate` that `certify` never
minted is accepted by an `Envelope`" is true of the shipped code; R-ARCH-032 uses a certificate
`certify` did mint, and publishes `withheld: []` for a ledger holding an unaccounted hit. An exit
condition phrased over *provenance* cannot see a defect in *mutability*, and the next one should be
phrased over what a certificate may state.

---

## Established by execution

All seven gates reproduce from the working tree, including 1,847 tests and the exact rubric counts
(7 PASS / 0 FAIL / 0 BLOCKER / 106 NOT TESTED, 11 transitions). The disposition ledger is
byte-identical to round 12, so `withheld := H − disclosed` computes the same set, and it does:
`H = {m1,m2,m3}`, `certify(['m1','m2'])` → `withheld = {m3}`, and all three residues still raise.
A2 holds (`threads.get` admits under `H-thr`), A3 holds at construction for −1, 2 and 900 and
raises rather than clamping, A4 holds (`included=3`, `included_as_stub=2`, complete map reports
complete). The `IdentityRegistry` is sound on every axis I could measure: the table drains to zero
after 20,000 mint-and-drops, a certificate outlives its ledger unaffected, a foreign certificate is
refused by the digest, 8 threads × 3,000 cycles produce no error, a pickled envelope fails closed,
and 3 `object.__new__` shells landing on freed certificate addresses answered nothing. "It states
nothing" is a pinned property, not prose: replacing the refusal with empty facts is caught. The
registry's rejection of equality-based lookup is pinned too. The honest envelope serialises
unchanged in both modes. Twelve of my thirteen reintroductions were caught and the scratch tree was
restored byte-identical (the thirteenth was my own partial reintroduction, not a gap). And the
three findings above: the certified facts are rewritable by two plain assignments and the result is
accepted at the constructor and serialised; three public subclass routes on `Envelope` each produce
`partial: false, withheld: []`; and `model_copy(update={"sources": ...})` puts a message at
position 900 of a two-message thread on the wire.

## False on execution

*"There is no state on the instance to copy, to rebuild, or to write over"* — there is, one
dereference away, and `vars()` writes it. *"A certificate cannot be lifted from one response and
attached to another"* — rewrite the digest on the facts object and it can. *"The check … is the
only way the facts can be reached at all"* — the facts can be reached, and that is also how to
change them. *"Only this type can be the one reading them"* — the reading type is subclassable
three ways. *"Nothing reaches the wire without the invariants holding of it"* — 24 of the 41
after-validators in the envelope tree are not re-established there, and A3's position bound and
R-RETR-002's occupancy rule both reach the wire. *"Recording it again would put a second entry in
scan_scope for one executed call"* — `object.__setattr__` re-arms the latch and produces exactly
that second entry. *"A validator added in a later round is covered the day it exists"* — unless it
serialises, in which case it recurses. I also withdrew one suspicion I could not sustain: a
classmethod-style `mode="after"` validator **is** handled correctly.

## Not establishable here at all

Whether the eventual **MCP surface** routes its responses through Pydantic serialisation. There is
no surface in the tree, so "the serializer is the chokepoint" is a statement about a path that does
not exist yet; WS-15's MCP-03 obligation to emit a text mirror *alongside* `structuredContent`
guarantees a second rendering, and nothing today constrains where it is derived from. This is the
single largest thing I could not settle, and it is the one that decides whether R-ARCH-038 is a
LOW or the whole ballgame.

Whether either object ever **crosses a real process boundary**. I established that it fails closed
under `pickle` in this interpreter; I ran no subprocess and neither did the round.

Whether the behavioural guarantees hold under **`python -O`**. The invariants raise explicitly
rather than asserting, and `test_invariant_under_optimised_python.py` exists, but neither the round
nor I extended it to the new refusals.

Whether **Pydantic keeps** revalidating a nested model instance passed to an outer model's
constructor — the property that makes R-ARCH-034 a post-construction defect rather than a
construction one. I confirmed it at this version, on this tree; nobody can pin the library.

Whether `|H|` is **bounded above**. A1's content witness is unbuilt, is not this round's job, and
nothing this round shipped claims otherwise — which I checked sentence by sentence and found clean.
