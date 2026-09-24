# ROUND 13 — R-SEC review

**Reviewer:** R-SEC, independent instance, 2026-09-02. Gating for Parts 1, 3, 4 and 5;
Part 2 belongs to R-ARCH and is reported here anyway, because I found it. Verified by
execution per `AGENT_LOOP.md` §4/§7. I did not write this code and I have taken every claim
in `ROUND_13/IMPLEMENTER.md` as a hypothesis.

**Environment.** CPython **3.12.3**, pydantic **2.13.5**, `/root/mailweave/.venv`.
`mailweave.__file__` and `mailweave_harness.__file__` both resolve under
`/root/mailweave/*/src/...` (the venv carries two editable `.pth` files pointing there).
Gates re-run by me, twice, at the start and at the end:

```
ruff check .                 All checks passed!
ruff format --check .        135 files already formatted
mypy (strict, from pyproject) Success: no issues found in 109 source files
python -m tools.guards       guards clean: forbidden-import, generative-client,
                             gmail-endpoint, ground-truth-isolation, scope-literal,
                             unaudited-disk-write, unwrapped-http-client over server/src
pytest -m "not network"      1847 passed, 0 failed  (exit 0)
tools/rubric_status.py --check   PASS 7 / FAIL 0 / BLOCKER 0 / NOT TESTED 106,
                                 11 reviewer transitions — unchanged, as required
```

The suite prints no summary line because `addopts = "-q --strict-markers"` in
`pyproject.toml` plus a `-q` on the command line is `-qq`. That has been reported as a
curiosity in two previous rounds; it is a pytest verbosity artefact and nothing else. I
recounted through a `pytest_sessionfinish` plugin: `{'passed': 1847}`, exit 0.

**Source and tests untouched.** I hashed all 109 `.py` files at the start and again at the
end: identical. All my probes ran in `/tmp/rsec13/rsec/*.py` against a scratch copy at
`/tmp/rsec13/rsec/tree`, which I byte-compared to the working tree before and after use.
I did not edit `FINDINGS_LEDGER.md`, `RUBRIC_TRANSITIONS.md` or `RELEASE_RUBRIC.md`
(mtimes 2026-09-02 20:12 / 2026-08-31 22:08 / 2026-08-31 22:08 — all older than the
implementer's last source write at 21:57, so its "verified unmodified" holds).

**One trace of unlanded work.** `tests/__pycache__/test_zz_diag.cpython-312-pytest-9.1.1.pyc`
is an orphan: the `.py` is gone. I unmarshalled it — code objects `test_diag` and `steal`,
globals `FakeCredential`, `PERSONAL`, `SEED`, `verify_seed_account`, `gc`, written 20:54.
That is the implementer's own in-tree id-reuse diagnostic; it was deleted and only the
bytecode remains. `.gitignore` covers `__pycache__`, so nothing would be committed. No
`.orig`/`.bak`/`.rej` files, no `REINTRO`/`DEFECT` markers anywhere in source or tests.
**Nothing was left patched.**

---

## Priority 1 — `SeedSession` and `mailweave.sealing.IdentityRegistry`

### The registry, attacked at the entry rather than at the address

`/tmp/rsec13/rsec/p1_registry.py`, `p1_resurrect.py`. I went after the *entry* — what makes
one stale, what stops the weak-reference callback firing, and whether anything can occupy an
entry it did not mint — rather than repeating the orchestrator's allocation loop.

* **The entry dies with its subject in every collection mode I could construct**: plain
  refcount drop, and a reference cycle collected by `gc`. Removed in both.
* **The weakref-in-the-cycle escape does not apply.** CPython documents that a weak
  reference *inside* a collected cycle does not get its callback invoked. The registry's
  reference lives in a module-global dict, so it is never in the garbage set. I tried to drag
  it in — made the subject hold `_entries[id(self)]` — and the entry was still removed.
* **`__del__` resurrection.** During `__del__` the entry is still present and `recall(self)`
  still answers, which is correct (it is the same object). Once the resurrected object is
  genuinely dropped the entry goes, and a fresh object landing on the freed key recalls
  `None`. My first run reported a leak here; that was **my** bug — I had left a live local
  bound to the resurrected object. Corrected in `p1_resurrect.py`; no leak.
* **A forced stale entry cannot be inherited.** I planted a dead weak reference at a live
  object's key by hand and asked for it: `recall` → `None`. The `ref() is subject` arm is
  reachable and is the arm that answers.
* **`__eq__`/`__hash__` cannot substitute for identity.** An object equal to everything with
  a constant hash recalls nothing. The `WeakKeyDictionary` rejection is load-bearing.
* **Objects that cannot be weakly referenced** — `object()`, a `__slots__` class without
  `__weakref__`, `int`, `str`, `tuple` — are refused at `remember` with `CannotBeSealed`, and
  `recall` on each returns `None` without raising. Interned singletons (`None`, `True`, `5`,
  `()`, `""`, `Ellipsis`, `NotImplemented`) recall nothing.
* **Re-minting replaces rather than accumulates**, and an orphaned older weak reference's
  callback does not revoke the successor's entry (the `current[0] is dead` guard is real).
* **`repr` does not print facts**; `pickle.dumps(registry)` raises. `copy.copy(registry)`
  shares the table and `IdentityRegistry` itself is subclassable — neither matters, because
  the module holds the one instance and reaching it needs the private name the docstring
  already concedes.

I could not construct a way for two distinct objects to satisfy `reference() is subject`.
In CPython that is object identity and there is no user-space hook on it.

### R-SEC-045 itself, my own allocation strategy

`/tmp/rsec13/rsec/p1_pinning.py`. The orchestrator probed one object at a time; I allocated
whole batches and then searched them, which puts different pressure on the allocator.
**id reused in 11 of 40 trials; forgeries authorised: 0** — through the public constructor
*and* through `object.__new__` + a copied `__dict__`, which never runs `__post_init__`.
A second ordering (clear the session's `credential` field so the credential dies while the
session lives, then land an attacker credential on the freed id, then call the **honest
session object's** own `assert_bound_to`): 0/40 reuse in my run, 0 forgeries.

**Nothing inherits the observed credential's nonce.** All of these were refused, and the
real credential was authorised immediately afterwards in the same script so that the
refusals mean something rather than tracking an artefact:

| candidate | result |
|---|---|
| `__getattr__` delegate wrapping the real credential | refused |
| `weakref.proxy(real)` | refused |
| `copy.copy` / `copy.deepcopy` / pickle round trip of the credential | refused |
| a subclass instance with the real credential's `__dict__` copied in | refused |
| `object.__new__(Cred)` + copied `__dict__` | refused |
| **the real credential (control)** | **authorised** |

### Subclassing, every route I know

All refused with `TypeError`: the class statement, `types.new_class`, `type.__new__`
directly, `__bases__` reassignment (both from a plain class and from a `__slots__` class),
`__mro_entries__`, a custom metaclass, and **supplying `__init_subclass__` in the new
class's own namespace** (CPython looks the hook up with `super(type, type)`, which skips the
new class, so this does not work — I checked rather than assumed). `instance.__class__ =
SeedSession` raises `AttributeError`.

The **one** route that succeeds is a `__class__` property duck, which is not a subclass and
passes `isinstance`. For `SeedSession` that costs nothing: nothing in either tree does
`isinstance(x, SeedSession)`, and the module says so. For `DispositionCertificate` it is a
live forgery — see Priority 2 below.

### R-SEC-052 — genuinely closed

`_material` is length-prefixed with a part count. Both collision pairs the finding named are
now distinct, as are four more I constructed by hand (`("ab",("c",))` vs `("a",("bc",))`,
`("a",(),"bN")` vs `("a",("b",),"N")`, and two that try to forge the length prefix itself:
`("1:a",("b",))` vs `("a",("1:b",))`). A brute force over an alphabet chosen to attack the
encoding (`""`, `"a"`, `"b"`, `"\x00"`, `"\x1f"`, `"1:"`, `"2|"`, `"aa"`, `"10:"`) across
0–2 scopes produced **7,371 distinct materials and 0 collisions**.

### The cross-process claim — the one the implementer said it did not test

`pinning.py` claims a session that reaches another process "authorises nothing there, twice
over: `_MINT_KEY` differs and the nonce table is empty". The implementer tested this by
substituting the key in-process and wrote plainly that it added no subprocess. **I added
one** (`/tmp/rsec13/rsec/p1_crossprocess.py`): pickled `(session, credential)` to disk,
spawned a fresh interpreter, unpickled both.

```
parent: assert_bound_to(cred) -> authorised (control)
  child: unpickled a session naming mailweave.seed@harness.example
  child: nonce table size -> 0
  child: refused -> this SeedSession does not authorise this credential...
  child: a session minted HERE authorises here -> yes
  child: does the PARENT's proof match the child's? -> False
```

The child refuses, its registry is empty, and a session minted **in the child** works there —
so the refusal is the property and not "everything fails in a subprocess". **The claim is
now established by execution, not by substitution.**

### Where the module's claims are still slightly wider than the code

The docstring's positive property — *"`assert_bound_to(credential)` succeeds only if a
`Profile` naming `self.address` was observed from that object in this process, and only if
the session's fields are the ones that observation produced"* — is **true of the code as
shipped**, on every route I could build. That is a real change from round 12, where the
equivalent sentence was false.

Two smaller things do not match, both in the safe direction or close to it:

* the residue list says *"importing `_mint_proof` mints a nonce for any object"*. It does
  not: an object that cannot be weakly referenced is refused (`SeedAccountMismatch`). This
  **overstates the attacker**, so it is not a finding.
* the refusal is described as *"one comparison and it has one answer"*. It is not, for a
  `proof` that is not an ASCII `str` — see **R-SEC-057**.

And one gap the residue list does not name, which is about who supplies the input rather
than about the mechanism: **R-SEC-059**.

**Judgement on Part 1: R-SEC-045 is closed.** I could not forge a session by any route that
does not reach a private name, over 80 id-reuse trials in two orderings, seven credential
substitutions, nine subclassing routes and a real process boundary.

---

## Priority 2 — the disposition seal (R-ARCH's part; reported because I found it)

The subclass hole this round closed is real and closed. **A `__class__` property impostor is
not**, and the module claims it is. `disposition.py:880`:

> a **duck-typed impostor** - a class that merely has the same properties - is refused by
> `Envelope`'s field type, which is an `isinstance` check.

`isinstance` consults `obj.__class__` when `type(obj)` does not match, so a plain object with
a `__class__` property returning `DispositionCertificate` passes. Reproduced (the
orchestrator's `/tmp/rsec13/a1_classspoof.py` and `a2_noledger.py`, both re-run by me):

```
isinstance(imp, DispositionCertificate) -> True     type(imp) -> Impostor
*** ACCEPTED by Envelope() ***     states withheld: []   partial: False
*** SERIALISED ***                 wire withheld: []     wire partial: false
```

and the second script does it with **no `DispositionLedger` anywhere in the process** —
`disclosure_digest` is a public module-level function and the attacker controls the payload.
This is byte-for-byte the wire output R-SEC-046 produced, through a route neither the
registry nor `__init_subclass__` touches. Filed as **R-SEC-054**.

The test that is supposed to cover this,
`test_a_certificate_impostor_that_is_not_a_subclass_is_refused_by_the_envelope`, plants a
duck that does **not** declare `__class__` — so it exercises the weakest member of the class
its own name asserts. That is the failure mode `AGENT_LOOP.md` §7.2 calls out, and it is the
third instance of it this round has produced.

`sealing.py`'s "What it does not do" section has the same shape of omission: it names
subclassing as the residue and says both users refuse it, which reads as completeness. A
non-subclass impostor at the **consumer's** `isinstance` is a third route neither half
addresses.

---

## Priority 3 — R-SEC-048 and the OD-4 record walk

### R-SEC-048 is closed

`/tmp/rsec13/rsec/p3_od4.py`, 70-odd shapes. For **all seven** prose keys, at the producer's
declared depth the value passes and at any greater depth it is refused — lists to depth 5,
tuples, and a dict below the key. The five depth-0 keys refuse even one list level. Sets,
frozensets, `UserDict`, `UserList`, `deque`, `bytes`, `bytearray`, `memoryview`, generators,
`range`, `array`, `MappingProxyType`, `complex`, `object()`, `OrderedDict`, `defaultdict`
and `Counter` are all refused as unreadable. Keys are checked and never exempt, including
a body as a key *at the prose key's own depth*, and `bool`/`int`/`float`/`None`/tuple keys.
A `str` subclass that lies about `__len__`/`splitlines`/`__str__` is caught as a value and
as a key. No refusal quoted the content it refused.

(My first pass printed a wall of `!!` — that was an inverted comparison in **my** harness
(`must="refuse"` vs `got="refused"`); every one of those lines is the correct behaviour.)

### What the new rule still misses: `isinstance(record, dict)` is not `type(record) is dict`

The module's stated fix is that the walk **"refuses what it cannot read"**. A `dict`
subclass whose `items()`/`keys()`/`__iter__` are empty *is* a container the walk cannot read,
and it is not refused — it is read as empty and passes.

The implementer found this shape and dismissed it: *"the two hiding subclasses pass the check
and write nothing, because `json.dumps` uses the same overridden iteration — the checker and
the writer agree, which is the property that matters."* **There are two writers, and only one
of them agrees.** `write_records` calls `json.dumps(record, ...)` — which uses `.items()` —
and then `render_summary(rows, ...)`, which reads `row['probe']`, `row['credential']`,
`row['notes']` and nine other keys by **`__getitem__`**. Reproduced
(`/tmp/rsec13/rsec/p3_hidingdict.py`), on `credential`, which is **not** a prose field, so
this is not the declared prose residue:

```
plain dict, credential=BODY  -> refused: a preflight record would carry credential: multi-line string...
Hiding dict, same content    -> *** PASSED THE WALK ***
PF-01.json -> {}
SUMMARY.md carries the body -> True
excerpt: 'fails:** c\n- **Credential:** `Hi Sam,\nThe filing is attached; the auditor flagged three lines in the'
```

No test in the suite covers a hiding `dict` subclass — `test_a_container_the_walk_cannot_read_
is_refused_rather_than_stepped_over` plants `set`, `frozenset`, `UserDict`, `bytes`,
`object()` and a tuple key, all of which fail `isinstance(record, dict)`. Filed as
**R-SEC-055**. Unreachable through the six shipped probes (`as_record` returns a literal
`dict`), exactly as R-SEC-042 and R-SEC-048 were before it.

### The re-stated exit condition

The implementer's re-statement is accurate as far as it goes, and I verified the AST claim it
rests on: an interpolation sweep over both trees finds exactly two interpolations into any
`notes=`, both integers. The residue — a declared prose field is unbounded at the producer's
own shape — is real, correctly named, and empty today. The sentence *"refuses outright any
value it cannot walk"* is the part R-SEC-055 falsifies.

---

## Priority 4 — the round-12 LOWs, one at a time

| finding | verdict | how I established it |
|---|---|---|
| R-SEC-049 `__context__` | **closed** | 24 forced failures, 2 models × 6 entry points × 2 shapes, walking `__cause__`/`__context__` to any depth over `str`/`repr`/`args`/`__notes__`/`__dict__`/`errors()`/`json()`/`format_exception`: every one raised `SecretDocumentMalformed` with `__context__` **and** `__cause__` `None`, and **no leak in any rendering**. Even `model_validate_strings` and the raw `__pydantic_validator__` route through the custom `__init__` for mapping input. Reintroduction M10 caught by 2 tests. |
| R-SEC-050 canary | **closed for the three shapes, refused at source for the fourth** | I planted seven models in the scratch tree. A plain `BaseModel` + `SecretStr` that skips the safe base: **5 tests fail**, including the behavioural one, quoting *21 fragments* of the planted secret. A `SecretStr` **subclass**, a **`SecretBytes`** carrier, a model **nested in a class**, and a generic `tuple[SecretStr \| None, ...]`: all discovered, all caught. An honest model using `SecretBearingModel`: not flagged (no false positive). A model defined **inside a function**: not discovered by reflection, and caught by `test_no_model_is_defined_where_reflection_cannot_find_it` instead. Reintroduction M11 caught by 3 tests. |
| R-SEC-051 scope coupling | **closed for the case evasion; the residue is wider than named** | `IN:ANYWHERE`, `In:Anywhere`, `iN:aNyWhErE`, `IN:TRASH`, and capitals beside another operator are all flagged. `-in:spam`, `in:spammers`, `"in:anywhere"` and `in:inbox` correctly are not. The check is symmetric (a widening flag with a narrow `q` is refused too) and `_fetch_list_page` is the only site in either tree that writes `includeSpamTrash` or `q`. Reintroduction M9 caught by 2 tests. **New**: see R-SEC-058. |
| R-SEC-052 HMAC material | **closed** | 0 collisions in 7,371 materials; both named pairs distinct. Reintroduction M12 caught. |
| R-SEC-053 `PROSE_FIELDS` copy | **closed** | I planted the exact R-ARCH-031 shape in the scratch tree — `record.py` binding its own copy, widened by one key (`"findings": 1`) — and the suite went red on `test_the_checker_uses_the_producers_declaration_rather_than_its_own_copy`. Anchor asserted before application. |

**None of the five was closed by narrowing a test.** Each reintroduction I wrote myself, in my
own phrasing, was caught by a test that asserts the defence rather than its absence.

### The one left open is honestly left open — I reproduced it

The implementer says the anti-vacuity guard `assert refused >= len(driven) - 1` misfires for a
one-field secret model. I planted `class PlantedOneField(SecretBearingModel): refresh_token:
SecretStr` — correctly written, using the safe base — and got exactly
`AssertionError: most of this battery asserted nothing`. **The stated open item is real, is
described accurately, and relaxing the guard would have been the narrowing this round is
judged against. Leaving it is the right call.**

### One claim in `validation.py` that is false

> 1. `input_value=...` - the value itself. Closed by `hide_input_in_errors`, below, which
>    closes it for *every* renderer of that error, not only for the callers we edited.

A/B with the flag on and off:

```
Shown    hide=False  str=True  errors()=True  json()=True
Hidden   hide=True   str=False errors()=True  json()=True
   Hidden.json() excerpt: [{"type":"int_parsing","loc":["a"],..., "input":"SECRET-YYYY..."}]
```

`hide_input_in_errors` closes `str()` and nothing else. `ValidationError.json()` **is** a
renderer — it returns a string with the input in full — and it needs no argument. The
implementer's recorded residue is *"`errors(include_input=True)` still returns the input
object. Data, not a rendering"*; that is narrower than the truth on both counts. Filed as
**R-SEC-056**. Reachable only via `__pydantic_validator__` with a non-mapping document — no
code in either tree does that, and the round-12 AST sweep forbids `.errors()`/`.json()` inside
a `ValidationError` handler — so it is inert, and it is still a false sentence in the module
whose whole subject is which surfaces are closed.

---

## Priority 5 — the sweep's re-scoping, both experiments run

I ran both experiments myself, in the scratch tree, every anchor asserted for an exact
occurrence count and every patched file `ast.parse`d before the suite ran
(`/tmp/rsec13/rsec/p5_experiments.py`, `p6_reintro.py`).

**E1 — narrow the sweep back to `pinning.py`, change nothing else.** Caught, by **two**
tests, not one: `test_every_capability_token_is_re_established_at_a_use_site` (the
`len(swept) >= 3` population assertion the implementer named) **and**
`test_the_capability_sweep_reaches_the_three_sites_it_is_about` (the named-set assertion it
did not name). The re-scoping cannot be silently reverted; the implementer understated its
own guard.

**E2 — narrow it *and* relax both self-checks, with nothing else changed.** Suite green,
1847 passed. **E2b — the same, with R-SEC-046 live** (I reintroduced the certificate holding
its own facts, with the mint token checked only in `__init__`): 83 tests fail and **all three
capability-sweep tests are silent**. So the structural half of the defence is entirely
switched off by that pair of edits and only the behavioural certificate tests remain — which
is the implementer's conclusion. My number is 83 where its was 8, because my reintroduction
patch is broader than its; the conclusion is the same and the difference is not meaningful.

I cannot reproduce the round-12 tree in which "nothing failed at all", and I say so rather
than repeating it.

**Is "capability token" a decidable category?** The sweep's discriminator is: a class
containing a call whose unparsed callee *contains the substring* `compare_digest` or
`recall`, or an `is`/`is not` comparison against a module-private name bound to a bare
`object()`. That is loose in the over-inclusive direction — `x.recall_anything()` matches —
which is the safe direction, since over-inclusion only demands a use site and a subclassing
refusal. `test_the_capability_sweep_does_not_report_innocent_code` plants `ProbeSpec`
verbatim and shows it is not reported, and
`test_the_capability_sweep_states_what_it_cannot_decide` plants a boolean capability and
shows the sweep is blind to it. Both fire. **I accept the argument**: the category is
decidable *for this repository's two idioms*, the sweep asserts its own population, and the
thing it cannot decide is asserted rather than described.

The `_refuses_subclassing` correction (first statement after any docstring must be the
`raise`) is real: my **M3** and **M5** put `return None` above the `raise` in `SeedSession`
and `DispositionCertificate` respectively, and both were caught.

---

## The secret-handling work from round 12 has not regressed

Required check, done: a planted secret-bearing model that **skips the safe base class**
(`class PlantedLeaky(BaseModel): refresh_token: SecretStr; obtained_at: str`) fails
immediately and loudly —

```
FAILED test_no_secret_survives_a_validation_failure_on_any_model_that_holds_one[...PlantedLeaky]
    -> PlantedLeaky leaked 21 fragment(s) of a secret through model_validate
FAILED test_every_pydantic_validation_entry_point_is_covered_for_a_secret_bearing_model[...]
FAILED test_a_secret_bearing_model_declares_that_it_may_not_quote_its_input[...]
FAILED test_nothing_under_the_funnel_quotes_what_it_refused[...]
FAILED test_the_discovery_still_finds_exactly_the_models_that_hold_a_secret
```

I also planted an *honest* model (safe base) carrying a `field_validator` that spells its
refusal `f"obtained_at={v!r} ..."` — channel 2, the `parse_instant` shape R-SEC-043 came in
through. Caught by `test_nothing_under_the_funnel_quotes_what_it_refused`. The defence is
live, not decorative.

---

## My own reintroduction battery — 12 defects, my phrasings, not the implementer's

`/tmp/rsec13/rsec/p6_reintro.py`. Every anchor asserted for an exact occurrence count;
refusal if the replacement leaves the file unchanged; `ast.parse` on every patched file
before the suite runs, so a syntactically broken patch cannot masquerade as "caught"; the
file restored from `/root/mailweave` afterwards. **Baseline green first**, which is how I
caught my own first run leaving M12 applied after a timeout.

| | defect | caught by |
|---|---|---|
| M1 | the proof binds `str(id(credential))` again — R-SEC-045 verbatim | 7 tests |
| M2 | `recall` stops proving the entry belongs to *this* object | 2 tests |
| M3 | `SeedSession.__init_subclass__` returns before it raises | 2 tests |
| M4 | the certificate keeps its facts in its own slots again — R-SEC-046 | 83 tests |
| M5 | `DispositionCertificate` may be subclassed again | 2 tests |
| M6 | the prose exemption takes any number of list indices — R-SEC-048 | 2 tests |
| M7 | `_plain` removed: a `str` subclass measured on its own word | 1 test |
| M8 | an unreadable container is stepped over, not refused | 1 test |
| M9 | case-folding removed from the widening check — R-SEC-051 | 2 tests |
| M10 | the refusal raised inside the handler with `from None` — R-SEC-049 | 2 tests |
| M11 | the canary back to `part is SecretStr` — R-SEC-050 | 3 tests |
| M12 | HMAC material back to separator joining — R-SEC-052 | 1 test |

**12 applied, 12 caught, 0 missed**, and the scratch tree byte-compared afterwards:
`ALL FILES MATCH`. This does not confirm the implementer's 21/21 — my cases are not its
cases — but it is an independent 12 that lands on the same conclusion, and I found no defect
whose reintroduction the suite is blind to.

---

## Findings

```
ID: R-SEC-054  Severity: HIGH  Rubric: none — contract I-1 / AD A.7a (RR EV-01, EV-03)
Location: server/src/mailweave/envelope/disposition.py:880 (the "duck-typed impostor" claim),
  DispositionCertificate; tests/test_certificate_seal_round13.py::
  test_a_certificate_impostor_that_is_not_a_subclass_is_refused_by_the_envelope
Repro: /tmp/rsec13/a1_classspoof.py and /tmp/rsec13/a2_noledger.py (orchestrator's scripts,
  re-run and confirmed by me). Build a plain object with `@property def __class__(self):
  return DispositionCertificate` and the certificate's public attribute names as class
  attributes. `isinstance(imp, DispositionCertificate)` is True (CPython consults
  `obj.__class__` when `type(obj)` does not match), Envelope(**fields, disposition=imp) is
  ACCEPTED, and model_dump(mode="json") emits `"withheld": []`, `"partial": false` for a
  ledger that recorded a withheld hit. a2 does it with no DispositionLedger in the process
  at all, computing the digest with the public `disclosure_digest`.
Expected: the module's own sentence — "a duck-typed impostor - a class that merely has the
  same properties - is refused by `Envelope`'s field type, which is an `isinstance` check".
Actual: not refused. This is R-SEC-046's exact wire output through a route that neither the
  IdentityRegistry (which closes rebuilds) nor `__init_subclass__` (which closes subclasses)
  touches, and it is the third route in the same family. The covering test plants a duck
  that does not declare `__class__`, so it exercises the weakest member of the class its
  name asserts — a test passing for the wrong reason (AGENT_LOOP §7.2). Inert today: no
  source module constructs an Envelope from an untrusted disposition object.
Required fix: this is Part 2 and belongs to R-ARCH, so I recommend rather than prescribe.
  Verify at the point of use as the round did elsewhere — Envelope's validator can ask the
  registry (`_CERTIFIED.recall(disposition) is not None`, or call `assert_minted()`) instead
  of trusting the field type, which closes ducks, subclasses and rebuilds with one check and
  needs no route enumerated. Whatever is chosen, correct the paragraph: `isinstance` is not
  a type check against forgery, and the test must plant the `__class__`-declaring duck.
```
```
ID: R-SEC-055  Severity: MEDIUM  Rubric: OD-4 — no mail text in a record without approval
Location: harness/src/mailweave_harness/preflight/record.py
  (assert_record_is_content_free's `isinstance(record, dict)` branch; write_records ->
  render_summary)
Repro: /tmp/rsec13/rsec/p3_hidingdict.py.
    class Hiding(dict):
        def items(self): return []
        def keys(self): return []
        def __iter__(self): return iter(())
        def __len__(self): return 0
    record = Hiding({...,"credential": <a multi-line 380-char body>})
  A plain dict with that content is refused ("credential: multi-line string"). The Hiding
  subclass PASSES the walk, PF-01.json is written as `{}`, and SUMMARY.md then contains
  "- **Credential:** `Hi Sam,\nThe filing is attached; ...`" in full, because
  render_summary reads row['credential'] by __getitem__ rather than through .items().
  `credential` is not in PROSE_FIELDS, so this is not the declared prose residue.
Expected: the module docstring — "The walk now **refuses what it cannot read**: a record is
  the JSON types or it is refused" — and the round-13 exit condition that the walk "refuses
  outright any value it cannot walk".
Actual: `isinstance(record, dict)` admits any subclass, so a dict whose contents the walk
  cannot read is not refused, it is read as empty. The implementer's stated defence — "the
  checker and the writer agree, because json.dumps uses the same overridden iteration" — is
  true of json.dumps and false of render_summary, which is the second writer over the same
  record in the same function. No test covers a hiding dict subclass: the unreadable-container
  test plants set, frozenset, UserDict, bytes, object() and a tuple key, none of which is a
  dict subclass. Unreachable through the six shipped probes, exactly as R-SEC-042 and
  R-SEC-048 were.
Required fix: refuse a mapping the walk cannot read as itself — require `type(record) is
  dict` and refuse every other mapping through _refuse_unreadable, or cross-check
  `len(record)` against the number of items yielded. Either makes the rule "refuses what it
  cannot read" true for the container the walk is most likely to be handed. Separately,
  render_summary should be written from the walked record rather than by key lookup, or
  the exit condition should stop claiming a property that holds for only one of the writers.
```
```
ID: R-SEC-056  Severity: LOW  Rubric: SEC-04 — no secret in log/error/traceback/file
Location: server/src/mailweave/validation.py (module docstring, channel 1); the residue
  recorded in ROUND_13/IMPLEMENTER.md
Repro: /tmp/rsec13/rsec/p4_context2.py and a direct A/B --
    class Hidden(BaseModel):
        model_config = ConfigDict(hide_input_in_errors=True)
        a: int
    try: Hidden(a="SECRET-...")
    except ValidationError as e:
        str(e)          -> secret absent
        e.errors()      -> secret PRESENT   (no argument passed)
        e.json()        -> secret PRESENT   (no argument passed)
  Reachable on a live object only through `Model.__pydantic_validator__.validate_python(x)`
  with a non-mapping document, which returns a raw ValidationError; every entry point the
  module overrides, and every mapping document through the raw validator, produces
  SecretDocumentMalformed with __context__ and __cause__ both None and no leak anywhere.
Expected: the docstring — hide_input_in_errors "closes it for *every* renderer of that
  error, not only for the callers we edited".
Actual: it closes `str()` only. `.errors()` and `.json()` default to include_input=True, and
  `.json()` is a rendering by any reading — it returns a string with the input in full. The
  residue as recorded ("errors(include_input=True)... Data, not a rendering") understates it
  twice: no argument is needed, and one of the two surfaces is a string. Inert: nothing in
  either tree calls .errors()/.json() on a ValidationError, and the round-12 AST sweep
  forbids the idiom inside a ValidationError handler.
Required fix: correct the sentence — say hide_input_in_errors closes the default string
  rendering and that .errors()/.json() carry the input unless include_input=False is passed,
  and that the AST sweep is what keeps them out of this tree. Optionally add .json() and
  .errors() with no arguments to the canary's renderings() so the claim is pinned rather
  than asserted.
```
```
ID: R-SEC-057  Severity: LOW  Rubric: none — SEC-03, robustness only
Location: harness/src/mailweave_harness/pinning.py (SeedSession.__post_init__,
  SeedSession.assert_bound_to; both `hmac.compare_digest(self.proof, expected)`)
Repro: /tmp/rsec13/rsec/p1_pinning.py section E. Build a session shell with
  object.__new__(SeedSession) and a `proof` that is None / an int / bytes / a non-ASCII str /
  a list / object(), then call assert_bound_to(real_credential):
    proof=NoneType  -> TypeError: unsupported operand type(s)...
    proof=bytes     -> TypeError: a bytes-like object is required, not 'str'
    proof=str(é*64) -> TypeError: comparing strings with non-ASCII characters is not supported
  Six shapes, six TypeErrors, zero SeedAccountMismatch.
Expected: the docstring — "The refusal does not say *which* of the three failed. It is one
  comparison and it has one answer: this session does not authorise this credential."
Actual: for a proof that is not an ASCII str the comparison raises TypeError before it
  answers. This is fail-closed — the operation aborts — but a WS-16 call site written as
  `except SeedAccountMismatch:` gets an exception it did not plan for, and the sentence
  above is not true of the code. Requires a type violation mypy --strict would reject in
  this tree, so it is a robustness matter and not a forgery route.
Required fix: either validate that `proof` is an ASCII str before comparing and raise
  SeedAccountMismatch otherwise, or amend the docstring to say the comparison is defined
  only for the declared type. Do not catch TypeError and continue.
```
```
ID: R-SEC-058  Severity: LOW  Rubric: none — the part 6 coupling
Location: server/src/mailweave/constants.py::widens_beyond_the_default_mailbox (the docstring's
  account of what it is "still not")
Repro: /tmp/rsec13/rsec/p4_scope.py --
    W("(in:anywhere)")          -> False        W("in:anywhere,")  -> False
    W("{in:anywhere in:spam}")  -> False        W("in:anywhere)")  -> False
    W("ＩＮ：ＡＮＹＷＨＥＲＥ")           -> False, and NFKC-normalising it gives "IN:ANYWHERE",
                                   which W() DOES flag
    W("in​:anywhere")      -> False (zero-width space inside the operator)
  Each of these therefore travels with includeSpamTrash=false without _fetch_list_page
  raising.
Expected: the docstring names its residue as "a different spelling of the same *intent* -
  `label:spam`, or something Gmail adds later".
Actual: the shapes above are not a different intent, they are the SAME operator with
  punctuation or Unicode equivalence around it, which is a different class from the one
  named — and it is the same class as the case evasion this round closed. `query.split()`
  tokenises on whitespace only, so any grouping syntax Gmail supports adjacent to the
  operator evades the pairing check. Whether Gmail parses "(in:anywhere)" or a fullwidth
  spelling as the operator is a live-Gmail question I cannot settle here; the guard is
  conservative in the safe direction if it does not, and open if it does.
Required fix: cheapest honest fix is to strip Gmail's grouping punctuation from each token
  before comparing and to NFKC-normalise, both of which can only refuse a disagreeing pair
  that used to be allowed. If that is judged premature, widen the docstring's residue to say
  the vocabulary is matched on whitespace-delimited, non-normalised tokens and add these
  shapes to PF-20 so the live run answers them.
```
```
ID: R-SEC-059  Severity: LOW  Rubric: none — SEC-03, a precondition on WS-16
Location: harness/src/mailweave_harness/pinning.py::verify_seed_account (the `seed_address`
  and `scopes` parameters), and the module docstring's control 2
Repro: /tmp/rsec13/rsec, "residue 2/3" probe. Public API only, no private name:
    class Cred:
        def __init__(self, a): self.a = a
        def get_profile(self): return Profile(email_address=a, ...)
    s = verify_seed_account(Cred("owner@personal.example"),
                            seed_address="owner@personal.example")
    s.assert_bound_to(that_object)          # authorised, names the owner's mailbox
  And `verify_seed_account(cred, seed_address=SEED, scopes=("https://mail.google.com/",
  "EXTRA"))` mints a session declaring a scope nobody granted. Grep: no non-test caller of
  verify_seed_account exists in either tree.
Expected: control 2 as the module states it — "users.getProfile(me).emailAddress is compared
  with **the configured** seed address before any harness operation".
Actual: `seed_address` is an ordinary keyword argument with no default and no configuration
  binding; `scopes` is a keyword argument with a default and no validation. The only related
  config field is `MailweaveConfig.seed_account_hash`, which is a hash and cannot be passed
  to `assert_seed_account`, which compares plaintext addresses. So the whole of control 2
  reduces to "whoever calls this passes the right address", and there is no caller yet to
  establish that it will. The mechanism this round fixed (the credential binding) is sound;
  the input it is compared against is not yet pinned to anything. The module's residue list
  explicitly declines to claim completeness, so this is an omission rather than a false
  claim — but it is the residue that decides whether control 2 works at all.
Required fix: name it in the residue list, and make it a stated precondition on WS-16 that
  `seed_address` is read from configuration rather than passed by a caller — either by
  deriving it inside this module from `MailweaveConfig`, or by resolving the
  hash-vs-plaintext mismatch so `seed_account_hash` can actually be the input. Consider
  refusing scopes that are not a subset of SEEDER_SCOPES.
```

---

## Recommendations, per criterion

Scoped recommendations only. **None of these is a PASS**, and each says exactly what it
covers and what it does not. A scoped recommendation recorded as an unqualified pass has
happened twice in this project; please do not let this be the third.

* **SEC-03 — Harness isolation and account pinning (NOT TESTED).**
  **R-SEC-045 is closed** and I recommend recording that as a **scoped observation, not a
  transition**: on this tree, over 80 id-reuse trials in two allocation orderings (id reused
  11/40 in mine, 0 forgeries), seven credential-substitution routes, nine subclassing routes,
  and a **real subprocess**, no session that `assert_bound_to` accepts names an address whose
  profile was not observed from the object in hand, by any route that does not reach a
  private name. The cross-process claim, which the implementer could not establish, is now
  established by execution.
  **Do not move SEC-03 toward PASS.** Three things stand between here and that: control 1
  (Google's Testing-status allowlist) is not verifiable from this environment at all; nothing
  consumes a `SeedSession` yet, so `assert_bound_to` has no production caller and no test can
  force one; and **R-SEC-059** means the address the pin compares against is not yet bound to
  configuration. All three are WS-16 preconditions.
  R-SEC-057 is cosmetic beside those and can ride the next round.

* **SEC-04 — Token storage hygiene (currently PASS, scoped to round 3's atomicity evidence).**
  **No regression.** I recommend recording, **as a scoped observation and not as a re-PASS**,
  that a planted secret-bearing model skipping `SecretBearingModel` fails 5 tests immediately
  with 21 quoted fragments, that a planted honest model with a value-quoting `field_validator`
  is caught by the under-the-funnel battery, and that 24 forced failures across 2 models × 6
  entry points × 2 corruption shapes produce `SecretDocumentMalformed` with `__context__` and
  `__cause__` both `None` and no leak in any rendering. **R-SEC-049 is closed.**
  **R-SEC-056 is open** and is a docstring correction, not a code change; it does not affect
  the PASS.

* **SEC-06 — Trace redaction canary (NOT TESTED).**
  **R-SEC-050 is closed** for the three shapes reflection can reach, verified by me by
  planting all four in a scratch tree, plus a generic wrapper and an honest control that is
  correctly not flagged. The fourth shape (a model defined inside a function) is refused at
  source instead, and I confirmed that refusal fires. Recommend recording as a **scoped
  observation**. The anti-vacuity guard's misfire on a one-field secret model is real — I
  reproduced it — and **should stay open**; it is a false *positive* on a model nobody has
  written, and relaxing it would be the narrowing this round exists to prevent.

* **OD-4 — no mail text in a record without approval.**
  **R-SEC-048 is closed**, verified across all seven prose keys at every depth I could
  construct, plus keys, `str`-subclass liars and seventeen unreadable container types.
  **R-SEC-055 is open and is the same class of defect**: fix it before probes gain structured
  notes or any probe's `as_record` stops returning a literal `dict`. Do not record the
  re-stated exit condition as met while the walk reads a hiding `dict` subclass as empty and
  a second writer publishes what it hid.

* **EV-01 / EV-03 and contract I-1 (the disposition invariant).**
  Not my part, and I am not recommending a status for it. **R-SEC-054 is a HIGH that R-ARCH
  must gate**: the seal is not closed against a `__class__`-declaring impostor, the module
  claims it is, and the covering test plants the weaker duck. The registry-based fix and the
  wire-time re-derivation are otherwise real — my M4 reintroduction was caught by 83 tests
  and M5 by 2.

* **On the standing sweep (Part 5).** The re-scoping to capability tokens is load-bearing and
  I recommend keeping it: E1 is caught by two of its own assertions, and E2b shows it goes
  silent only if someone relaxes those assertions as well. The category is decidable for the
  two idioms this repository uses, the sweep asserts its own population, and what it cannot
  decide is asserted rather than described. **One consequence worth writing down:** the sweep
  enforces "no subclassing", and R-SEC-054 shows that is not the whole of "only this type
  reads the facts". A future round should decide whether the sweep can also require that the
  *consumer* re-establishes rather than type-checks.

---

## Established by execution

* **R-SEC-045 is closed.** No forgery by any public route: 40 batch-allocation id-reuse
  trials (11 reuses, 0 forgeries) plus a second ordering; seven credential substitutions all
  refused with the real credential authorised as a control; nine subclassing routes all
  refused, including `__bases__` reassignment and supplying `__init_subclass__` in the
  namespace.
* **The `IdentityRegistry` survives the lifecycle attacks I could construct**: refcount and
  cycle collection both remove the entry; the weakref-in-the-cycle escape does not apply;
  `__del__` resurrection leaves no permanent stale entry and a successor at the freed key
  recalls `None`; a hand-planted stale entry is not inherited; equality and hashing cannot
  substitute for identity; non-weak-referenceable objects are refused at the mint and recall
  `None` without raising; re-minting replaces rather than accumulates; an orphaned callback
  cannot revoke a successor's entry.
* **The cross-process refusal is real, in a real subprocess** — and a session minted in the
  child works there, so the refusal is the property and not an artefact.
* **R-SEC-052 is closed**: 0 collisions in 7,371 materials.
* **R-SEC-048 is closed** across all seven prose keys, all depths, keys as well as values,
  `str`-subclass liars, and seventeen container types refused as unreadable.
* **R-SEC-049 is closed**: 24 forced failures, `__context__` and `__cause__` both `None`
  everywhere, no leak in any rendering.
* **R-SEC-050 is closed** for the three reachable shapes and honestly refused at source for
  the fourth — established by planting all four myself, with an honest control that is
  correctly not flagged.
* **R-SEC-051's case evasion is closed**, and the pairing check is symmetric and sited at the
  only place in either tree that writes `includeSpamTrash`.
* **R-SEC-053 is closed**: a divergent widened `PROSE_FIELDS` copy in `record.py` turns the
  suite red.
* **The Part 5 re-scoping cannot be silently reverted** (E1 caught by two assertions), and
  **relaxing those assertions does make the R-SEC-046 class invisible to the sweep** (E2b:
  all three sweep tests silent, only behavioural tests fail).
* **The secret-handling work has not regressed**, including channel 2 (a value-quoting
  validator on an otherwise honest model).
* **12 of my own reintroductions, 12 caught, 0 missed**, anchors asserted, tree byte-restored.
* **The working tree is unmodified and nothing was left patched**: 109 `.py` files hashed
  before and after, identical; no patch artefacts; all six gates clean, twice.

## False on execution

* **`disposition.py`'s claim that a duck-typed impostor is refused by `Envelope`'s field
  type.** It is not: a `__class__` property defeats `isinstance`, the envelope accepts it and
  serialises `withheld: []` / `partial: false`, with no ledger in the process. **R-SEC-054**,
  HIGH. The covering test plants a duck without `__class__` and therefore passes without
  exercising the property it names.
* **`record.py`'s "the walk refuses what it cannot read".** A `dict` subclass that hides its
  `items()` is read as empty, passes, and its contents are then written to `SUMMARY.md` by
  the second writer. **R-SEC-055**, MEDIUM. The implementer's defence ("the checker and the
  writer agree") is true of `json.dumps` and false of `render_summary`.
* **`validation.py`'s "`hide_input_in_errors` closes it for *every* renderer of that
  error".** It closes `str()` only; `.errors()` and `.json()`, with no arguments, carry the
  input in full. **R-SEC-056**, LOW.
* **`pinning.py`'s "one comparison and it has one answer".** A non-ASCII-`str` proof raises
  `TypeError` out of `compare_digest`. **R-SEC-057**, LOW. Fail-closed, but not one answer.
* **`constants.py`'s account of what its check "is still not".** The residue is described as
  a different spelling of the same intent; grouping punctuation and Unicode equivalence
  around the *same operator* also evade it. **R-SEC-058**, LOW.
* **Two smaller over-statements that run in the safe direction**, so not filed: `_mint_proof`
  does not mint "a nonce for any object" (a non-weak-referenceable one is refused), and the
  implementer's E1 is caught by two assertions rather than the one it names.

## Not establishable here at all

This is the section that matters most, and the list has not got shorter.

* **Control 1 — Google's Testing-status test-user allowlist.** The strongest of the three
  pinning controls is a Cloud Console setting. It is not code, no test in this repository can
  read it, and I have no Console access. Everything I established about `SeedSession` is
  about control 2, which the module correctly describes as the *weaker* one. If control 1 has
  been changed, or the project was moved to Production, nothing here would notice.
* **Whether `assert_bound_to` is ever called.** It has no production caller. In-process, no
  object can force a caller to ask it a question, and the design's whole answer — that a
  session is a *parameter* a destructive operation must already hold — is a claim about code
  WS-16 has not written. I can establish that the check is correct; I cannot establish that
  it will run.
* **Where `seed_address` will come from.** See R-SEC-059. No caller exists, and the one
  related config field is a hash that cannot be fed to the plaintext comparison.
* **Whether Gmail treats `IN:ANYWHERE`, `(in:anywhere)`, `{in:anywhere ...}`, a fullwidth
  spelling or `label:spam` as widening the scope.** These are facts about Gmail's query
  parser. The guard is now conservative in the safe direction for the case variants; for the
  rest I can only say what the guard does, not what Gmail does. PF-20.
* **Whether the six preflight probes behave against a real mailbox.** No live Gmail, no
  credentials, no network. Every probe result I have seen is against the fake transport.
* **The blanket `Cf` strip against real Arabic, Indic or Syriac content.** Standing item,
  unchanged, needs real mail.
* **Whether Pydantic keeps routing mapping validation through a custom `__init__`, and keeps
  running a `mode="wrap"` model serializer on every dump route.** I confirmed both hold on
  pydantic 2.13.5 and that tests pin them, but they are internal routing rather than a
  documented contract, and a future version may change them.
* **Behaviour under `python -O`.** The new refusals raise explicitly rather than using
  `assert`, and `test_invariant_under_optimised_python.py` exists, but neither the
  implementer nor I extended it to this round's refusals. I did not run the suite under `-O`.
* **Whether the implementer's 21/21 battery is what it says.** Its scripts are in `/tmp/r13`,
  which does not exist in this container. I ran twelve of my own instead and found no gap;
  that is corroboration, not verification of its number.
* **Whether a *fourth* defect exists in this round's own fixes.** The implementer asked
  reviewers to assume one does. I found two it did not have (R-SEC-055, R-SEC-056) and
  confirmed the one the orchestrator found (R-SEC-054). I would not assume the list is
  complete; this module family has now been wrong about its own residues four rounds running.

---

## Verdict

**No BLOCKER.** Nothing found this round reaches a Gmail write, a real mailbox, or a secret
in transit. The two most serious items are inert today for the same reason they were inert in
rounds 11 and 12: nothing consumes a `SeedSession`, and no source module builds an `Envelope`
from a disposition object it did not mint.

**But the round should not close as done.** One **HIGH** is open — **R-SEC-054**, a live
forgery of the disposition seal through a route the round did not touch, producing the same
wire output as R-SEC-046, with a covering test that passes without exercising its own
property. Per `AGENT_LOOP.md` §4 that is round-blocking. It is Part 2 and therefore R-ARCH's
to gate; I raise it because silence would be worse than overlap.

One **MEDIUM** is open in my own part — **R-SEC-055** — and should be fixed before any probe
gains structured notes.

Parts 1, 3, 4 and 5 are otherwise in good shape, and better than the implementer's report
claims in two places (E1 is caught twice over; the cross-process refusal is now established
against a real process boundary rather than a substituted key). The report is unusually
honest: every open item it declared, I reproduced, and the one it chose not to close by
narrowing a guard was the right call. Its blind spot is the same one the module family has
had for four rounds — it enumerates the routes it thought of and then writes a sentence as if
the enumeration were complete. **R-SEC-054, R-SEC-055, R-SEC-056, R-SEC-057 and R-SEC-058 are
all the same shape: a claim wider than the code.** That, rather than any single mechanism, is
what I would ask the next round to attack.
