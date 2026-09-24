# ROUND 14 — implementer report

**Implementer:** round-14 implementer, 2026-09-03. Parts 1–5 of
`docs/reviews/ROUND_14/WORK_ORDER.md`.

I reproduced Parts 1, 2 and 3 from the reviewers' own scripts before changing anything, and
re-established the fix direction rather than taking it from either review. Everything below
that says a route is closed was run; everything I could not establish is in its own section
under the part it belongs to, and again at the end.

**The battery found two live gaps in this round's own work** — R6 and R11, both `NOT CAUGHT`
on the first pass, both real, both now closed and re-run. They are the most useful thing in
this report and they are recorded where they happened rather than summarised away.

---

## Reproduced first, on the shipped tree

| script | result before the change |
|---|---|
| `/tmp/rarch13/b5_vars.py` | `the certified facts have an instance __dict__: True` → `wire: {'partial': False, 'withheld': []}`, `repr: DispositionCertificate(H=1, disclosed=1, withheld=0)` |
| `/tmp/rarch13/a4_modelcopy_nested.py` | `model_copy(update={'sources': ...})` **ACCEPTED AND SERIALISED**, `positions on the wire: [0, 900] stated_total: 2 partial: False` |
| `/tmp/rarch13/a5_enumerate.py` | `Envelope model-after = 17`, `nested model-after = 24` |
| `/tmp/rarch13/a1_envelope_subclass.py` | A1, A2, A3 each **ACCEPTED AND SERIALISED** with `partial: False withheld: []` |
| `/tmp/rsec13/a1_classspoof.py` | `isinstance(imp, DispositionCertificate) -> True`, **ACCEPTED**, **SERIALISED** |
| `/tmp/rsec13/a2_noledger.py` | **ACCEPTED AND SERIALISED with no DispositionLedger in the process** |
| `/tmp/rsec13/rsec/p3_hidingdict.py` | `Hiding dict → *** PASSED THE WALK ***`, `PF-01.json -> {}`, `SUMMARY.md carries the body -> True` |

Every one of these is re-run at the end of this report against the finished tree.

---

## Part 1 — R-ARCH-032: the single authoritative record is mutable

### The fix direction, re-established rather than taken on anyone's word

The work order said explicitly not to trust this. `tests/test_certified_facts_round14.py::
test_a_named_tuple_refuses_the_writes_a_frozen_dataclass_allows` runs the whole table:

| shape | `vars()` write | `object.__setattr__` | `setattr` |
|---|---|---|---|
| `@dataclass(frozen=True)` | **lands** | **lands** | refused |
| `@dataclass(frozen=True, slots=True)` | refused (no `__dict__`) | **lands** | refused |
| `NamedTuple` | refused | refused | refused |

The middle row is why the choice matters: `slots=True` closes the two lines R-ARCH wrote and
leaves the finding open through two different ones.

### What changed

`_CertifiedFacts` and `ObservedThread` are `NamedTuple`s. That alone would have been the
eleventh "one shape validated, peers trusted", so the whole graph a certificate hands back is
covered rather than the record this round happened to change:

* the **mappings** were `MappingProxyType`s over the registry's own dicts. A `mappingproxy` is
  read-only at its surface and `gc.get_referents(proxy)[0]` is the dict behind it — executed,
  and writing into that dict changes what the proxy reports. They are now held in the record as
  tuples of pairs and rebuilt on every read, so a caller writes only into their own copy;
* the **`WithheldRecord`s** inside the record are Pydantic models, which have a writable
  `__dict__`. `vars(record)["id"] = "m9"` lands, and because the envelope compares its records
  against *these same objects*, both sides would have agreed about the new id. `withheld_seal`
  is a digest of the records' own wire form taken at mint and re-derived on every read of
  `withheld`, so the material is each record's `model_dump` and a field added to
  `WithheldRecord` later is sealed by existing;
* `ObservedThread` is handed out by `observed_thread_facts` and read by two of `Envelope`'s
  validators, so `vars(fact)["stated_total"] = 99` would have defeated A6's total check.

`_release`'s one-shot latch (R-ARCH-036, a false sentence in a file this diff touches) is now
held in `_RECORDED` **as well as** in `_consumed`. Both halves are load-bearing and they close
different routes: the registry survives `object.__setattr__(page, "_consumed", False)`, and the
slot survives a `copy.copy`, which the registry does not. `_RECORDED` drains: 5,000
record-and-drop cycles leave **0** entries.

`tools/field_census.py` was extended to read a `NamedTuple` — which it *demanded*, exactly as it
was written to: it raised rather than skipping the shape it could not read. The audited total
moves 207 → 208 (`withheld_seal`), and
`test_the_round_seven_reading_misses_exactly_the_shapes_it_cannot_read` now computes the old
reading's blind spot by shape instead of naming two classes, so it stays a statement about the
enumerator when the tree changes shape.

### Reintroduction check

| | defect put back | anchors | result | caught by |
|---|---|---|---|---|
| R1 | `_CertifiedFacts` is a `@dataclass(frozen=True)` again — R-ARCH-032 verbatim | matched (1/1) | **caught** | 3 tests, incl. `…_r_arch_032_fails_where_it_is_written` |
| R2 | `_CertifiedFacts` is `frozen=True, slots=True` — the near miss | matched (1/1) | **caught** | 3 tests |
| R3 | the withheld records are not sealed | matched (1/1) | **caught** | 2 tests |
| R4 | the mappings are handed out by reference | matched (1/1, 1/1) | **caught** | 2 tests |
| R5 | `ObservedThread` is a frozen dataclass again | matched (1/1) | **caught** | 2 tests |
| R17 | the one-shot latch is a slot again (R-ARCH-036) | matched (1/1) | **caught** | `…_the_one_shot_latch_cannot_be_re_armed` |
| R21 | the field census skips a shape it cannot read | matched (1/1) | **caught** | 2 tests |

### What I could not establish

* **Whether a `NamedTuple` is immutable against a future CPython.** I ran the table on 3.12.3
  in this container. `object.__setattr__` on a tuple subclass has no documented contract I can
  point at; the test is what would notice.
* **`python -O`.** The new refusals raise explicitly rather than asserting, and
  `test_invariant_under_optimised_python.py` exists, but I did not extend it and did not run the
  suite under `-O`. Unchanged from round 13, and now with more refusals not covered by it.

---

## Part 2 — R-ARCH-034: the chokepoint re-ran 17 of 41

### What changed

A new module, `server/src/mailweave/sealed_model.py`, holds the reader half of the seal:
`_after_validators_of`, `re_establish`, `re_establish_tree`, and `SealedModel`. Three things
are in it and they are three separate mechanisms:

1. **`re_establish_tree`** walks the payload from the model being serialised and re-establishes
   every nested model's after-validators, not only the outer model's. Driven from the top rather
   than left to each nested model's own serializer, so a node whose serializer is not this
   module's is still checked.
2. **`_after_validators_of` reads the MRO**, not `type(self).__pydantic_decorators__`. The
   merged table is what a subclass method of the same name *replaces*; each class's own
   `__dict__` still holds the function it declared. The rule that falls out is easy to state:
   **a subclass may add a validator; it cannot remove one.**
3. **`SealedModel.__init_subclass__` refuses a subclass of any model that declares fields** —
   Part 3, below.

`Envelope` now inherits `Frozen`, which inherits `SealedModel`. So do the reason models and
`Reduction`, which live in other packages — see the peer question.

### The count, asserted both ways

`TREE_AFTER_VALIDATORS = 42` and `ENVELOPE_AFTER_VALIDATORS = 18` are separate assertions.
One total would let the coverage narrow back to the outer model behind an unchanged number,
which is exactly what happened in round 13. The reach is asserted against the **annotations**:
`test_the_walk_reaches_every_model_the_annotations_can_hold` decomposes every field annotation
in the tree and fails if a model is ever declared inside a container the walk does not descend,
so the residue of the walk is bound by the schema rather than by a sentence.

### Reintroduction check

| | defect put back | anchors | result | caught by |
|---|---|---|---|---|
| R6 | the wire re-establishes only this model's own validators — R-ARCH-034 verbatim | matched (1/1 ×3) | **NOT CAUGHT** on the first run, **caught** after | see below |
| R7 | validators discovered off the runtime class only | matched (1/1) | **caught** | `…_a_subclass_may_add_a_validator_and_cannot_remove_one` |
| R12 | `model_copy` re-establishes only the outer model | matched (1/1) | **caught** | 2 tests |
| R18 | the walk stops descending sequences | matched (1/1) | **caught** | 2 tests |
| R19 | the reason models go back to a plain `BaseModel` base | matched (1/1 ×2) | **caught** | `…_no_model_in_the_envelope_tree_can_be_substituted` |
| R20 | `Reduction` goes back to a plain `BaseModel` base | matched (1/1 ×2) | **caught** | same |

**R6 was `NOT CAUGHT`, and the battery was right.** Replacing `re_establish_tree(self)` with
`re_establish(self)` at both chokepoints failed nothing, because a nested wire model
re-establishes *itself* when it is serialised — so on every route that serialises the nested
source, the two mechanisms are indistinguishable and my tests only drove those routes. I had
written "two independent nets" and tested one of them twice.

They come apart on a dump that omits the source. Measured both ways before writing the test:

```
with the tree walk             include partial    refused
with only the per-model check   include partial    ACCEPTED
```

`model_dump(include={"partial"})` on an envelope with a row at position 900 of a two-message
thread hands out a narrowed view of a broken payload. `test_a_narrowed_dump_of_a_tampered_
envelope_is_refused_even_though_it_omits_the_source` drives three such dumps, and R6 re-run is
caught by it.

### What I could not establish

* **Whether Pydantic keeps revalidating a nested model instance passed to an outer model's
  constructor.** I confirmed it does on pydantic 2.13.5 — a `Source.model_construct` with a row
  at 900 is refused at `Envelope(...)`, `loc=sources.0`. That is what makes R-ARCH-034 a
  post-construction defect rather than a construction one, and nobody can pin the library.
* **Whether the eventual MCP surface routes through Pydantic serialisation.** There is still no
  response surface in the tree. R-ARCH-038 stands untouched: WS-15 must emit a text mirror
  alongside `structuredContent`, and nothing here constrains where that is derived from.
* **The cost, which is real and is not free.** A dump of the fixture envelope takes **0.888 ms**
  with the re-establishment and **0.175 ms** without it — about five times the bare dump, on a
  small payload, because the tree is walked at the envelope and again at each nested model as
  Pydantic serialises it. I have not measured it on a large one and there is no benchmark for
  response assembly to put it in.

---

## Part 3 — R-SEC-054 and R-ARCH-033: sealing the object, trusting the reader

### R-SEC-054: `isinstance` is not a type check against forgery

`assert_is_a_minted_certificate` asks the two questions that are not the same question, and asks
**neither of them of the candidate**:

* `type(candidate) is DispositionCertificate` — the actual type slot. A `__class__` property
  cannot lie to `type()`, and `isinstance` consults `__class__` when `type()` does not match,
  which is the whole finding;
* `_CERTIFIED.recall(candidate) is not None` — this process minted this object. `type` alone
  admits a `copy.copy`; `recall` alone admits a duck somebody `remember`ed.

It is called from a `mode="after"` validator, so it is re-established at the wire like every
other one. **The covering test now plants the duck that declares `__class__`**, and
`test_isinstance_really_is_defeated_by_a_class_property` asserts the hole is real first — a test
of a fix, not a restatement of the type annotation. The paragraph in `disposition.py` that
claimed the field type refused a duck is corrected rather than softened.

### R-ARCH-033: the reader must be as unsubstitutable as the thing it reads

Four routes, not three. The fourth was found while closing the first three and nobody filed it:

```python
class Sneaky(Envelope):
    @field_serializer("withheld")
    def _empty_on_the_way_out(self, withheld): return []
```

Every object-level check passes for that class and only the emitted form differs — after the
chokepoint has run. Defending route (c) by name would have left it, which is the enumeration
habit. What the four share is that **a substituted class reaches the wire in place of the one
this repository declared**, so that is what is refused: `SealedModel.__init_subclass__` refuses
a subclass of any model that *declares fields*. Extending a base that declares none — `Frozen`,
`_ReasonBase`, `SealedModel` — is how the schema is written and stays allowed.

`__init_subclass__` rather than `__pydantic_init_subclass__`, because `type.__new__` invokes the
first and not the second; supplying `__init_subclass__` in the new class's own namespace does
not help, since CPython looks the hook up with `super(type, type)`.

Two tests had to be re-expressed, and both are noted where they live. R-ARCH named the first:
`test_a_validator_added_after_this_round_is_re_run_at_the_wire_without_being_listed` *required*
`Envelope` to be subclassable, in the same file as a class sealed against subclassing for that
reason. It is now built on `Frozen`, which is where the property actually lives.
`test_the_placement_check_catches_the_swap_that_passed_all_fifty_tests` subclassed
`ThreadMember`; it is now a twin on `_ReasonBase` declaring the same fields.

### The emitted form

`_the_emitted_disposition_is_the_certified_one` reads I-1's and I-2's two claims back **out of
the mapping that is about to be returned** and compares them with the certificate. Every other
check in `response.py` is a check on the object; this is a check on what is handed out, which is
the statement the exit condition is actually about. Two fields and only two — that narrowness is
the claim and is asserted by a test, not left in a docstring.

### Reintroduction check

| | defect put back | anchors | result | caught by |
|---|---|---|---|---|
| R8 | a wire model may be extended again | matched (1/1) | **caught** | 8 tests across three files |
| R9 | the disposition field is trusted to be a certificate | matched (1/1) | **caught** | 2 tests |
| R10 | the mint check is an `isinstance` check again | matched (1/1) | **caught** | 2 tests |
| R11 | the emitted form is not compared with the certificate | matched (1/1) | **NOT CAUGHT** on the first run, **caught** after | see below |

**R11 was `NOT CAUGHT`, and it is the same defect round 13 was caught by.** The test I had
written drove `_the_emitted_disposition_is_the_certified_one` directly, which establishes what
the function does and nothing about whether anything calls it — the shape of round 13's "test
that discovered the validators and then ran them itself". Deleting the call site failed nothing.
`test_the_emitted_form_check_is_actually_wired_into_the_serializer` now replaces the module
global, drives one dump, and asserts it was called exactly once **with the mapping the dump
returned**; a second test replaces it with one that raises and asserts the refusal reaches the
caller. R11 re-run is caught by both.

### What I could not establish

* **That the four subclass routes are all of them.** They are the four I could build. What is
  asserted is not "these four are refused" but "a subclass of a field-declaring model does not
  come into being", which is one rule and does not have to be complete over routes — except that
  `__bases__` reassignment is refused by *CPython's* layout check and not by us, which is
  asserted as such so a future interpreter change shows up here.
* **Whether a consumer other than `Envelope` will ask.** In-process, no object can force a
  caller to ask it a question. `tests/test_standing_cycle_round14.py` sweeps for reading sites so
  the *next* one is covered on the day it is written; it cannot make one exist.

---

## Part 4 — R-SEC-055: the OD-4 walk has two writers and checks for one

`isinstance(record, dict)` became `type(record) is dict`, and so did the sequence and scalar
branches. The reason is the second writer rather than tidiness: `write_records` calls
`json.dumps` **and** `render_summary`, and they do not use the same interfaces —
`json.dumps` iterates a mapping with `items()` and formats a scalar with its base type, while
`render_summary` looks keys up with `__getitem__` and interpolates values with `__str__`. "The
checker and the writer agree" is a claim about a pair, and there is no single pair.

**The peer of my own fix, found while making it and not filed by anyone:**

```python
class Sneaky(int):
    def __str__(self): return <a body>
```

passes an `isinstance(record, bool | int | float)` check, is written to the JSON as `1`, and puts
the body into `SUMMARY.md` through `f"budget {row['quota_budget_units']} u"`. That is R-SEC-055
exactly, one type over. Fixing only the container would have shipped the same defect in the same
function. Executed before and after: before, `walk PASSED an int subclass whose __str__ is a
body` and `SUMMARY.md carries the body -> True`; after, refused at `quota_budget_units`.

Four shapes are driven — hiding `dict`, hiding `dict` one level down, lying `int`, hiding `list`
— each both through the walk and through `write_records`, where the assertion is that **nothing
is written at all**, since R-SEC-055's harm was the file rather than the return value. The
records the six shipped probes actually emit still pass; `as_record` writes literals, `list(...)`,
`dict`s and `enum.value`, all exact types.

`_plain` is now a second net rather than the first — a `str` subclass no longer reaches the
bound at all — so it is exercised directly, because a defence nothing exercises is decoration.

### Reintroduction check

| | defect put back | anchors | result | caught by |
|---|---|---|---|---|
| R13 | the walk admits `dict` subclasses again | matched (1/1) | **caught** | 2 tests |
| R14 | the walk admits scalar subclasses again (the peer) | matched (1/1) | **caught** | 2 tests |

### What I could not establish

* **Whether `render_summary` would be safe on its own.** It is not rewritten to read only from
  the walked record; what changed is that the record it reads is now the exact `dict` the walk
  read. If a future writer takes a record the walk has not seen, nothing here notices.
* **The declared prose residue is unchanged.** `{"notes": [<a 380-character body>]}` still
  passes and must, because that is where probes write their own prose. Round 13's AST sweep
  finding two integer interpolations into any `notes=` is unchanged and unre-run by me.

---

## Part 5 — the LOWs, and the claims behind them

**R-SEC-056.** `validation.py` said `hide_input_in_errors` "closes it for *every* renderer". It
closes the default string rendering. `.errors()` and `.json()` default to `include_input=True`
and `.json()` returns a string, so "not a rendering" was not available either. The paragraph now
says what the flag closes, what it does not, and that the round-12 AST sweep plus
`failure_summary`'s explicit `include_input=False` are what keep the two open surfaces out of
this tree. The A/B is a test, and a second test parses `validation.py` and asserts every
`.errors()` call in it passes `include_input=False` and that it calls `.json()` nowhere.

I also tried R-SEC's optional suggestion — adding the no-argument forms to the canary's
`renderings()` for the *top-level* failure — and **backed it out**, because it turns the suite
red for a true reason: `Model.__pydantic_validator__.validate_python(<not a mapping>)` returns a
raw `ValidationError` whose `.errors()` carries the input, and no code in this module can wrap
it. Making the canary assert a property that is false would have been worse than the sentence I
was correcting. The no-argument `errors()` **is** added for linked exceptions, where the
property does hold.

**R-SEC-057.** `_refuse_unless_comparable` validates that `proof` is an ASCII `str` before
comparing and raises `SeedAccountMismatch` otherwise. Six shapes, six `SeedAccountMismatch`,
with the real credential authorised as a control in the same run. `TypeError` is not caught and
continued past; the answer is the refusal.

**R-SEC-058.** Each whitespace-delimited token is NFKC-normalised and stripped of Gmail's
grouping punctuation at both ends before the fold. `(in:anywhere)`, `{in:anywhere in:spam}`,
`in:anywhere,`, `[in:trash]`, `in:spam;` and the fullwidth spelling are all flagged;
`-in:spam`, `in:spammers`, `"in:anywhere"` and `in:inbox` are still not. Both steps can only
refuse a disagreeing pair that used to be allowed. The residue is re-stated at the right width —
a different *intent*, punctuation *inside* the operator (a zero-width space between `in` and
`:`, which survives NFKC and is pinned as still not seen), and what Gmail's parser actually
does, which is PF-20's.

**R-SEC-059.** Not fixed, named. `seed_address` is a keyword argument with no default and no
configuration binding; `scopes` has a default and no validation; the only related config field
is a hash that cannot be fed to a plaintext comparison; there is no caller. Binding it to a
config field for a caller that does not exist would be guessing at WS-16's shape. The residue
list now carries it as a stated precondition on WS-16, and a test pins the three facts the note
rests on — including an assertion that fails the day somebody closes it, which is the prompt to
delete the note rather than let it describe a gap that is gone.

**R-ARCH-035.** `tests/test_standing_cycle_round14.py` sweeps the other half of round 13's rule.
Its subjects are classes that **re-establish** somebody else's capability — discovered by an AST
sweep for a call to `assert_is_a_minted_certificate` — and the rule is round 13's, applied where
it came from. Two deliberate differences: the refusal is checked **by execution** (`Envelope`
inherits its refusal and has no `__init_subclass__` of its own, so an AST check would have
reported it unsealed), and the population is asserted by name. It also sweeps the whole envelope
tree structurally, which is what caught R19 and R20.

### Reintroduction check

| | defect put back | anchors | result | caught by |
|---|---|---|---|---|
| R15 | the proof comparison raises `TypeError` again | matched (1/1) | **caught** | `…_an_uncomparable_proof_is_a_refusal_and_not_a_type_error` |
| R16 | the widening check stops normalising and stripping | matched (1/1) | **caught** | `…_the_same_operator_with_punctuation_or_normalisation_around_it_is_flagged` |

---

## Every claim this diff makes about what a check covers or what an attacker must do

The standing instruction for the round. Where I could not execute a claim I narrowed it until I
could; the last three rows are claims stated as *unestablished*, which is the artifact the work
order asked for.

| # | where | the claim | executed evidence |
|---|---|---|---|
| 1 | `disposition.py` `_CertifiedFacts` | "a `NamedTuple` refuses `vars()`, `setattr` **and** `object.__setattr__`; a frozen dataclass with or without `slots` does not" | `test_a_named_tuple_refuses_the_writes_a_frozen_dataclass_allows` — all nine cells run |
| 2 | `disposition.py` `_CertifiedFacts` | "every field is an immutable scalar, a tuple of them, or sealed by `withheld_seal`" | `test_every_value_a_certificate_hands_back_refuses_to_be_written`, parametrised over all ten properties; writes attempted, and a write into a returned mapping is asserted not to survive |
| 3 | `disposition.py` `observed_threads` | "there is no `mappingproxy` whose underlying dict is one `gc.get_referents` away" | `test_a_mapping_proxy_is_read_only_only_to_a_caller_who_does_not_reach_behind_it` establishes the hazard; row 2 establishes the fix |
| 4 | `disposition.py` `withheld` | "a record rewritten after certification is refused, on every read" | `test_a_withheld_record_rewritten_after_certification_is_refused` (id) and `…_a_rewritten_reason_is_refused_as_well_as_a_rewritten_id` (a non-id field) |
| 5 | `disposition.py` `assert_is_a_minted_certificate` | "`type(...) is` has no hook a property can defeat; `isinstance` does" | `test_isinstance_really_is_defeated_by_a_class_property` + `test_a_class_property_impostor_is_refused_by_the_envelope` |
| 6 | `disposition.py` `assert_is_a_minted_certificate` | "neither half is redundant" | `test_the_check_is_the_mint_and_not_the_objects_own_answer` — a `copy.copy` fails the registry half, a duck fails the type half |
| 7 | `disposition.py` `FetchedIds.recorded` | "the registry survives `object.__setattr__`; the slot survives a copy; neither alone is the property" | `test_the_one_shot_latch_cannot_be_re_armed` and `test_a_copy_of_a_recorded_page_is_still_refused` |
| 8 | `disposition.py` `FetchedIds` | "`isinstance(page, FetchedIds)` does **not** mean the class" — the round-13 sentence, narrowed | `test_an_isinstance_check_is_not_a_type_check_for_this_class_either` |
| 9 | `sealed_model.py` `_after_validators_of` | "a subclass may add a validator; it cannot remove one" | `test_a_subclass_may_add_a_validator_and_cannot_remove_one` — the merged table is asserted to hold the subclass's function first |
| 10 | `sealed_model.py` `re_establish_tree` | "every after-validator in the tree is re-established at the chokepoint, not only the envelope's own" | `test_the_tree_has_more_after_validators_than_the_envelope_does` (42 vs 18) + `test_every_after_validator_in_the_tree_runs_when_an_envelope_is_serialised`, which wraps each validator and counts |
| 11 | `sealed_model.py` `_DESCENDED` | "the walk enters mappings, sequences and sets; anything else is a leaf, and the schema is pinned to that" | `test_the_walk_reaches_every_model_the_annotations_can_hold` decomposes every annotation in the tree |
| 12 | `sealed_model.py` `SealedModel` | "a subclass of a field-declaring model does not come into being, by any route" | `test_a_wire_model_cannot_be_substituted_by_any_route` — 3 routes × 3 models; plus the four named routes; plus `__bases__`, refused by CPython and asserted as CPython's |
| 13 | `sealed_model.py` `SealedModel` | "extending a base that declares no fields is still how the schema is written" | `test_the_base_that_declares_no_fields_is_still_extensible` — and its own subclass is then refused |
| 14 | `response.py` serializer | "every route through Pydantic's serializer passes through this" | 16 routes driven against a nested tamper; 15 refused. The 16th is a `MessageRow` dumped alone, which is **accepted and correct** — a row carries no `stated_total` — and is asserted as such in `test_a_row_dumped_on_its_own_states_no_bound_it_does_not_carry` |
| 15 | `response.py` serializer | "`_the_emitted_disposition_is_the_certified_one` reads the claims back out of the emitted mapping" | `test_the_emitted_form_check_is_actually_wired_into_the_serializer` asserts one call per dump with the mapping the dump returned; `…_refuses_from_inside_the_serializer` asserts the refusal reaches the caller |
| 16 | `response.py` `_the_emitted…` | "two fields and only two; a key that is absent is not checked" | `test_the_emitted_form_is_compared_with_the_certificate_not_only_the_object` (four doctored mappings + a non-mapping) and `test_a_partial_dump_is_not_treated_as_a_missing_disposition` |
| 17 | `response.py` residue paragraph | "`dict(env)` and `repr(env)` return the tampered value; only serialisation refuses" | `test_the_attribute_read_residue_is_what_the_docstring_says`, now asserting the `repr` case and the disagreement with the certificate too (R-ARCH-038's required fix) |
| 18 | `record.py` docstring | "the JSON types themselves, because there are two writers and they use different interfaces" | `test_a_json_type_lookalike_is_refused_rather_than_read_as_empty` (4 shapes) + `test_nothing_is_written_for_a_record_the_walk_refuses` + `test_the_second_writer_reads_the_same_object_the_walk_read` |
| 19 | `record.py` docstring | "nothing the six shipped probes emit is refused" | `test_the_records_the_six_shipped_probes_actually_emit_still_pass`, and the whole preflight end-to-end suite |
| 20 | `validation.py` docstring | "`hide_input_in_errors` closes `str()`; `.errors()`/`.json()` carry the input with no argument" | `test_hide_input_in_errors_closes_the_string_rendering_and_not_the_other_two` — A/B with the flag on and off |
| 21 | `validation.py` docstring | "the AST sweep is what keeps those two out of this tree" | `test_nothing_in_either_tree_renders_a_validation_error_the_two_open_ways` parses `validation.py` and asserts every `.errors()` passes `include_input=False` |
| 22 | `pinning.py` `assert_bound_to` | "one answer, for every input, including one `compare_digest` cannot be asked about" | `test_an_uncomparable_proof_is_a_refusal_and_not_a_type_error`, 6 shapes, with the real credential authorised as a control |
| 23 | `constants.py` docstring | "the same operator with punctuation or Unicode equivalence around it is flagged; a narrowing query is not" | 10 widening spellings and 6 non-widening, each parametrised |
| 24 | `constants.py` docstring | "a zero-width space *inside* the operator is **not** seen" — stated as a residue | `test_the_residue_the_docstring_now_names_is_the_residue_that_exists` |
| 25 | `pinning.py` residue list | "`seed_address` has no configuration binding and no caller" — stated as unestablished | `test_the_seed_address_is_a_callers_parameter_with_no_configuration_binding` |
| 26 | `sealing.py` (unchanged) | "not a defence against code that imports the owning module" — stated as unclosable | not executable, and not claimed to be; unchanged from round 13 |

---

## Have I trusted a peer rather than checked one?

I asked it four times and it found four things. Three of them were peers I had trusted; the
fourth was a mechanism I had tested twice under two names.

1. **Part 1 — the record is immutable; what is *inside* it?** `_CertifiedFacts` holds
   `WithheldRecord`s (Pydantic models with a writable `__dict__`), `ObservedThread`s (frozen
   dataclasses), and mappings behind a `mappingproxy` (whose backing dict is reachable). Three
   peers, all writable, all inside the object I had just sealed. Closed by `withheld_seal`, by
   making `ObservedThread` a `NamedTuple`, and by rebuilding the mappings per read.
2. **Part 4 — the container is exact-typed; what about the scalars?** `class Sneaky(int)` with a
   `__str__` that returns a body reaches `SUMMARY.md` through the second writer. That is
   R-SEC-055 one type over, inside the fix for R-SEC-055. Closed by exact-typing the scalars too.
3. **Part 2/3 — the wire models are sealed; what about the models that are not wire models?**
   `Reduction` lives in `mailweave.content.reductions` and the ten reason kinds in
   `mailweave.envelope.reasons`. They reach the wire and they did not inherit the base. My own
   standing sweep is what caught it — `test_no_model_in_the_envelope_tree_can_be_substituted`
   listed eleven models — and closing it is why the machinery is in `mailweave.sealed_model`
   rather than in `wire.py`: a base two of the three families could not import would have covered
   the one that could, which is the defect rather than a fix for it.
4. **Part 2 — the tree walk and the per-model check are "two independent nets".** They are not
   independent on any route my tests drove, and the battery said so with a `NOT CAUGHT`. They
   come apart only on a dump that omits the nested model. I had tested one mechanism twice and
   called it two.

The one I would flag for a reviewer to attack first: **the exact-type rule in `record.py` is an
enumeration**, and the round's whole subject is that enumerations are wrong. My argument is that
it enumerates what the walk *can read faithfully* and refuses everything else, which is
R-SEC-048's own move — but a `str` subclass is still admitted by `isinstance` inside
`_over_the_bound`, and the reason that is safe is that the walk refuses it first. Two
mechanisms, one of which is now unreachable from the walk. I exercised `_plain` directly so it
is not decoration, but a reviewer should ask whether keeping both is a second net or a second
place to be wrong.

---

## Is the exit condition satisfied, and is it well shaped?

> No response reaches any serialisation route stating a disposition that differs from what the
> ledger it was retrieved with computed — **whatever** was done to the objects in between, and
> whether the certificate was minted or not.

**Every route I know is refused: 22/22**, driven in one script
(`/tmp/claude-0/…/scratchpad/exit_condition.py`) rather than reasoned about — the two `vars()`
writes, `object.__setattr__` on the record, a rewritten withheld record, a write into a returned
mapping, the `__class__` duck with and without a ledger in the process, `copy.copy`, a pickled
envelope, four `Envelope` subclass routes, `Source` and `MessageRow` subclasses, `model_copy`
and `model_construct` on the envelope's own fields and on its sources, `vars()` past
`frozen=True` at both levels, a narrowed dump, two rows on one slot, the envelope nested in
another model, and the re-armed one-shot latch.

**And the exit condition is still not the property.** Three things reach a reader and are not
"a serialisation route":

* `dict(envelope)["withheld"]` returns `()` for a tampered envelope;
* `repr(envelope)` renders the tampered value into any log line or error message;
* a `MessageRow` dumped on its own emits `position: 900` — correctly, because a row carries no
  thread length, but a caller who assembles rows into a payload has a disposition nothing checked.

All three are named in `response.py` and pinned by tests that assert the residue **still
exists**. So the honest statement is: *the exit condition is satisfied for every route through
Pydantic's serializer, and the phrase "any serialisation route" is doing more work than the code
supports the moment a caller stops using one.*

**Where I think the condition is still badly shaped, and I am arguing this the way R-ARCH argued
about round 13's.** Round 13's was phrased over *provenance* and could not see a *mutability*
defect. This one is phrased over *the route*, and it cannot see a defect in *who is reading*.
Two of this round's four findings — R-SEC-054 and R-ARCH-033 — are not about a route at all;
they are about the payload being handed to a different reader, which then chooses its own route.
A condition phrased over routes is satisfied by enumerating them, and enumerating routes is
precisely the habit this round exists to correct. It also cannot see R-ARCH-038, which is about
a consumer that does not exist yet and will render a text mirror from somewhere.

The condition I would put in front of round 15, phrased over what a *reader* may obtain rather
than over how it obtains it:

> Any account of a response's disposition that a consumer can obtain — serialised, iterated,
> rendered, or assembled from its parts — either agrees with what the ledger computed or is
> refused; and where a route is left open, the response cannot be the thing that carries it.

That is deliberately harder than what I built. Under it, `dict(envelope)` and `repr(envelope)`
are open and would have to be either closed or moved out of the envelope's reach, and WS-15's
text mirror would have to be derived from the dumped form by construction rather than by
convention. I did not build that this round and I am not claiming to have.

---

## The reintroduction battery, and why its result can be believed

`/tmp/claude-0/-home-claude/575d70c1-c8ad-5ed4-8fc6-31be74875a3b/scratchpad/reintro.py`, against
a scratch copy at `/tmp/r14/tree` with a pristine snapshot at `/tmp/r14/pristine`.

**Anchors are asserted before anything is applied.** `apply()` refuses unless
`text.count(old)` equals the count the patch declares, **and** refuses if the replacement leaves
the file unchanged. An `AnchorMiss` is recorded as an ERROR and never as a pass. Every patched
file is `ast.parse`d before the suite runs, so a syntactically broken patch cannot masquerade as
"caught" through a collection error. Import isolation is confirmed rather than assumed:

```
isolation confirmed: ['/tmp/r14/tree/server/src/mailweave/__init__.py',
                      '/tmp/r14/tree/harness/src/mailweave_harness/__init__.py']
baseline: green
```

**First run: 21 defects, every anchor matched, 19 caught, 2 `NOT CAUGHT`** — R6 and R11, both
real gaps in this round's own work, both described above under their parts. After the two tests
that close them, R6, R11 and R18 were re-run under the same rules: **all three caught.**

```
19/21 caught      (first pass)
 3/3  caught      (R6, R11, R18 re-run after the fix)
tree restored, all files match: True
```

No anchor missed in either run, which I note without pride: the anchors are strings I wrote
minutes earlier, and `ruff format` ran between writing the code and writing the battery, which
is exactly the round-12 failure. The count assertion is what would have caught it.

---

## What this round did not do

* **Did not touch `gmail/retry.py` or `rates.py`.** The backoff curve is the owner's decision.
* **Did not build amendment A1's content witness.** `|H|` is still bounded above by nothing.
* **Did not mark any rubric criterion** and added no rows to `FINDINGS_LEDGER.md` or
  `RUBRIC_TRANSITIONS.md`. Both verified unmodified by mtime (`2026-09-02 22:54` and
  `2026-08-31 22:08`, both older than my first source write).
* **Did not update `RESUME.md`.** Round status is the orchestrator's to write.
* **No real or realistic personal mail text** was added to any fixture, test, log or record. The
  round-14 fixtures use `"line one of a message-shaped block\n"` repeated, which is multi-line
  and over the bound — all the check looks at.
* **Did not fix R-ARCH-038.** The text-mirror constraint is a WS-15 obligation and there is no
  MCP surface to attach it to; the residue paragraph now names the `repr` case and the test pins
  it, which is the half that was available.

---

## What I could not establish at all

* **Whether the MCP surface will route through Pydantic serialisation.** Unchanged and still the
  largest thing between this work and the property it stands for. WS-15 must emit a text mirror
  alongside `structuredContent`; nothing constrains where it is derived from.
* **Control 1, Google's Testing-status allowlist.** Not code, not readable from here.
* **Where `seed_address` will come from.** R-SEC-059, named rather than fixed, and pinned.
* **Whether Gmail parses `(in:anywhere)`, a fullwidth spelling or `label:spam` as widening.**
  Facts about Gmail's parser. PF-20.
* **Behaviour under `python -O`.** Not extended to this round's refusals, and I did not run the
  suite under `-O`.
* **Whether Pydantic keeps revalidating nested model instances, and keeps running a `mode="wrap"`
  model serializer on every dump route.** Both confirmed on 2.13.5, both pinned by tests, neither
  pinnable in the library.
* **The cost of the re-establishment on a large payload.** Measured on the fixture only: 0.888 ms
  against 0.175 ms without. There is no response-assembly benchmark to put that in.
* **Whether a *fifth* defect exists in this round's own fixes.** The battery found two. Round 13's
  implementer asked reviewers to assume a fourth and there were three. I would attack, in order:
  the exact-type rule in `record.py` (the enumeration I defended above); the `_DESCENDED` walk,
  whose residue is bound by a test over *annotations* and not over runtime values; and whether
  `_after_validators_of`'s cache can go stale for a class built after the first lookup.

---

## Final verification, verbatim

```
=== ruff check ===
All checks passed!

=== ruff format --check ===
141 files already formatted

=== mypy --strict ===
Success: no issues found in 115 source files

=== python -m tools.guards ===
guards clean: forbidden-import, generative-client, gmail-endpoint, ground-truth-isolation,
scope-literal, unaudited-disk-write, unwrapped-http-client over server/src

=== pytest -q -m 'not network' ===
........................................................................ [ 96%]
........................................................................ [ 99%]
......                                                                   [100%]

(the build prints no summary line; recounted with --collect-only)
1950 tests collected            (1,847 at the start of this round)

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

**Reintroduction battery:** 21 defects, one at a time, every anchor asserted before it was
applied and every patched tree parsed before the suite ran — **19 caught, 2 `NOT CAUGHT`, both
real, both closed and re-run as caught**; tree restored byte-identical.

I did not verify my own work in the sense that matters. Two of this round's tests existed and
established nothing, and its own battery is what said so. R-SEC and R-ARCH should attack the
`record.py` enumeration and the `_DESCENDED` walk first, because those are the two places where
this report's claims are narrowest, and should ask of Part 2 the question the battery asked:
*which of these two mechanisms is doing the work, and is there a route where only the other one
would have caught it?*
