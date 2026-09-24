# ROUND 12 — R-SEC review

**Reviewer:** R-SEC, independent instance, 2026-09-02. Verified by execution per
`AGENT_LOOP.md` §4/§7. Source and tests untouched: every probe ran from `/tmp/rsec12/*.py`
against the live tree, and every reintroduction ran in a scratch copy at `/tmp/rsec12/tree`
(imported via `PYTHONPATH`, `mailweave.__file__` confirmed to resolve there and not into
`/root/mailweave`). `mailweave.__file__` / `mailweave_harness.__file__` resolve under
`/root/mailweave/*/src/...` for all live probes.

**Environment, re-run rather than read.** `ruff check` clean; `ruff format --check` — 131
files already formatted; `mypy --strict` — no issues in 105 source files;
`python -m tools.guards` — 7 guards clean over `server/src`; `pytest -q -m "not network"` —
**1,726 collected, 1,726 passed, 0 failed, 0 skipped** (recounted from a `--junitxml` run,
since the build prints no summary line); `python tools/rubric_status.py --check` —
**7 PASS / 0 FAIL / 0 BLOCKER / 106 NOT TESTED, 11 transitions**, unchanged as required.
The implementer's verification block reproduces exactly.

---

## Priority 1 — `SeedSession` (Parts 3 and 3b), attacked hardest

### What holds, established by execution

The orchestrator's list reproduces and I did not re-litigate it. Beyond it:

* **Subclassing is genuinely closed, four ways** (`attack_protocol_and_subclass.py`): the
  `class` statement, `types.new_class`, a direct `type.__new__(type, "F", (SeedSession,), {})`,
  and `__bases__` reassignment on an already-created class. The first three hit
  `__init_subclass__`; the fourth is refused by CPython's layout check. R-RETR's round-3
  move does not work here.
* **The proof really does bind all three fields.** `vars(session)["address"] = ...` succeeds —
  `frozen=True` intercepts `__setattr__` and does nothing about the instance `__dict__`, which
  is a public attribute and not the `object.__setattr__` the docstring names — and
  `assert_bound_to` still refuses. Field tampering by any route is caught. That half of 3b is
  real.
* **Part 3b's own reintroductions are caught**, on my anchors rather than the implementer's:
  reverting the use-site check to the identity comparison, recomputing over the *stored*
  credential, deleting the verification, baking `_MINT_KEY` into the module, removing
  `__init_subclass__`, and binding only the address — 6 for 6, by 1 to 12 tests each,
  including the standing sweep
  `test_the_seed_session_proof_is_verified_somewhere_other_than_its_constructor`.

### What does not hold — R-SEC-045

**The binding is `id(credential)`, and the argument that `id()` is stable rests on a field
that `assert_bound_to` no longer reads.** `_mint_proof` binds `str(id(credential))`;
`assert_bound_to` recomputes over the credential *passed in* and never consults
`self.credential`. The docstring says `self.credential` "is retained for one reason: it keeps
the minting credential alive, so its id cannot be recycled". Nothing enforces that the session
still holds it, and `proof` is a **public field**.

Three separate routes, all executed (`attack_id_reuse.py`, `attack_id_reuse2.py`,
`attack_id_reuse3.py`, `attack_public_forge.py`, `attack_forge_reliability.py`):

1. `vars(session)["credential"] = None` — the public instance `__dict__`, no
   `object.__setattr__` — then free the original and allocate. **Reused on the first
   allocation**; `assert_bound_to(evil)` authorised.
2. `pickle.loads(pickle.dumps(session))` in-process, then drop the original — the twin's proof
   binds a dangling id. Authorised. This is precisely the "a cache, xdist, multiprocessing"
   scenario the docstring says now fails closed; it fails closed only *across* processes.
3. **Entirely public, no tampering at all**: read `address`, `scopes` and `proof` off a real
   session (four public attribute reads), let it and its credential go out of scope, allocate
   an attacker-controlled credential onto the freed address, and build the session with the
   **ordinary public constructor**. `__post_init__` accepts it and `assert_bound_to` authorises
   it. Measured over independent trials: **59/60** with a bare credential object, **60/60**
   with a `GmailClient`-sized one.

So the module's closing claim — *"Importing `_mint_proof` … and `object.__new__` plus
`object.__setattr__` … Both are in-process, both are unclosable in Python … the difference is
that the claim is now true: neither is ordinary code"* — is **false in the same direction
round 11's claim was false**: neither private name is needed. This is the ninth appearance of
"one shape validated, peers trusted": `id()` was validated against the peer that copies a
session, and the peer that outlives a credential was trusted. It also falsifies the work
order's exit condition "*and is bound to its credential*", and the field comment "it authorises
nothing on its own" — with a groomed allocation, the proof alone authorises.

Two smaller residues, both in-process and neither closable, but neither named where the module
enumerates what remains possible:

* **The `ProfileSource` boundary is an object, and an object's method table is mutable.**
  `client.get_profile = lambda: Profile(<any address>)` on the very client that will run the
  destructive call mints a session for an address no honest `getProfile` returned, with
  `id()` unchanged, so `assert_bound_to(client)` authorises it after the instance attribute is
  deleted again. Executed.
* **Nothing type-checks a session at a use site.** `class Fake: def assert_bound_to(self, c):
  pass` satisfies any caller. The docstring names "an operation that never calls
  `assert_bound_to`" as the residue; "an operation handed something that is not a
  `SeedSession`" is the same residue one step over and is not named.

### `__post_init__` as "an early failure, not the guarantee"

Checked as instructed. **Nothing in either source tree consumes a `SeedSession` at all** —
zero call sites for `assert_bound_to` outside `pinning.py` and the tests — so nothing in
production relies on `__post_init__` as the guarantee. Within the tests, three cases
(`…public_constructor_cannot_mint…`, `…re_pointed_at_another_mailbox…`,
`…proof_of_one_session_does_not_validate_another`) assert on `__post_init__`'s refusal, which
is exactly what the module says it is for. **The description is honest.**

---

## Priority 1b — the standing sweep's deliberate narrowing, judged

The implementer scoped
`test_the_seed_session_proof_is_verified_somewhere_other_than_its_constructor` to `pinning.py`
and argued that a general rule would flag "several honestly constructor-only `__post_init__`
validators (`ProbeSpec` among them)". `ProbeSpec` is indeed innocent. But the rule that
matters is not "`__post_init__` validators" — it is **capability tokens and mint proofs**, and
a sweep scoped to *those* would flag exactly two sites in this repository. The second is not
innocent.

**`server/src/mailweave/envelope/disposition.py` has the identical defect, in the server
tree** (`attack_disposition_seal.py`, `attack_forged_certificate.py`). `_MINT_TOKEN` is checked
in `DispositionCertificate.__init__` and nowhere else, and `__init__` is not the only way that
object comes into being:

```
legit  = ledger.certify([...])           # the honest certificate
forged = copy.copy(legit)                # __init__ never runs; no token presented
forged._withheld  = ()                   # plain assignment: properties are read-only,
forged._hit_count = forged.disclosed_hits  #   the slots behind them are not
Envelope(**{**fields_of(honest_envelope), "withheld": (), "partial": False,
            "disposition": forged})      # ACCEPTED
```

The resulting `Envelope` states `withheld = []` and `partial = False` for a response whose
ledger recorded a hit (`m2`) that no record accounts for. Every one of `Envelope`'s
cross-checks passes, because the forged certificate is internally consistent and the disclosure
digest is untouched. **No private name of `disposition.py`, no `object.__setattr__`, no reach
for `_MINT_TOKEN`** — which is word for word the claim that module makes ("*not a defence
against code that deliberately reaches for a private name in the same process*"), and word for
word the claim R-SEC-039 falsified in `pinning.py`. `deepcopy` and `pickle` happen to fail on a
`mappingproxy`; that is an artefact, exactly like the deepcopy artefact 3b identified in
`SeedSession`, and it protects nothing.

**And one layer up, one ordinary line does it without copying a certificate at all:**
`envelope.model_copy(update={"withheld": (), "partial": False})` skips every
`model_validator` — including `_withheld_matches_the_certificate` — and the result serialises
to the wire with `"withheld": []` while its own certificate still certifies one withheld id.

`FetchedIds`' one-shot record seal, tested the same way, **holds**: a `copy.copy` of a consumed
page is still refused.

**Judgement: the narrowing is convenient, not merely defensible.** The argument offered against
a wider sweep is an argument against sweeping `__post_init__`; it is not an argument against
sweeping capability tokens, and the shape it declines to sweep is live in the layer the product
contract rests on. This is pre-existing, not introduced by round 12 — but the work order's
standing check asked whether the sweep covers the shapes, and the honest answer is that it
covers this round's instance and leaves its older twin uncovered.

---

## Priority 2 — secret handling (Part 2)

### The finding was real, and is fixed

Reconstructed R-SEC-043 **verbatim** in the scratch tree (`run_part2b.py`): funnel removed,
`hide_input_in_errors` removed, `load()` interpolating the raw report. `TokenStoreError`'s
message then carries an **18-character intact prefix and a 22-character intact suffix** of a
51-character refresh token, and 9 tests fail. On the shipped tree the same file yields a
value-free `SecretDocumentMalformed`. The finding was real and the fix addresses it.

### The two "extra" leaks are real, and the three-channel analysis is correct

* **`load_config` echoing the whole client secret.** With the three defences removed, a
  `config.json` carrying one typo'd key (`client_secrett`) puts `GOCSPX-…` into the message
  **in full** — the secret sits inside Pydantic's truncation window. Reproduced.
* **`parse_instant` as an independent `msg` channel.** With `hide_input_in_errors` **still
  on**, restoring `f"{field}={value!r}"` puts the entire 51-character token, untruncated, into
  the message via `obtained_at`. That establishes the report's mechanism claim by execution:
  `hide_input_in_errors` does nothing about `msg`.

### My own reintroduction battery (not the implementer's)

Six Part-2 defects, each applied alone to a snapshot with **every anchor asserted before the
patch** and the tree byte-compared afterwards (`ALL FILES MATCH`, verified):

| Defect | Result |
|---|---|
| `hide_input_in_errors` removed | caught, 6 tests |
| `loc` allowlisting removed | caught, 3 tests |
| `parse_instant` quotes its value | caught, 1 test |
| the `__init__` funnel removed | caught, 4 tests |
| the `model_validate` override removed | **not caught — and not a leak** |
| R-SEC-043 verbatim (all three) | caught, 9 tests |

The `model_validate` case is the mirror of the implementer's D2′: Pydantic routes mapping
validation through `__init__`, so removing that override changes nothing observable. It is
redundancy, not a gap, and I confirmed no leak by direct reproduction rather than by the tests
being green.

### The wide attack: 131 model-level and 21 loader-level forced failures

Eleven corruption shapes (secret as a value, in a list, two levels deep, **as a key**, as a
nested key, whole document replaced by the secret, …) × seven entry points (`model_validate`,
`model_validate_json`, `model_validate_strings`, `Model(**d)`, the raw
`__pydantic_validator__` at both `validate_python` and `validate_json`, and a
`model_construct` round trip), plus the same shapes driven through the real loaders on real
files with real permissions. Every fragment searched at an **8-character window**
(`attack_secrets_wide.py`).

**`str`, `repr`, `args`, `__notes__` and `traceback.format_exception` are clean on every one of
the 152 failures.** That is a real result and it is stronger than the shipped canary's.

**One residue: `__context__`** (`attack_context_chain.py`). `raise … from None` sets
`__cause__ = None` and `__suppress_context__ = True`, so the traceback is clean — but
`__context__` still holds the raw `ValidationError`. On the shapes where the secret became a
JSON key, **`str(exc.__context__)` prints the whole secret untruncated**; on every shape,
`.errors()` / `.json()` on it carry the input. No test in the suite mentions `__context__`. The
report declares `errors(include_input=True)` as a known non-closure; it does not say the
exception object itself is still hanging off the refusal. R-SEC-049.

### The canary's reflection discovery, tested against models that do not exist yet

Planted new models in the scratch tree and re-ran:

* **A new secret-bearing model in the *harness* tree** (`mailweave_harness.seeder_creds`) is
  discovered the moment it exists and fails **5 tests** plus the standing sweep. The strongest
  claim in the report — "covered the day it exists" — is **true**, established by execution.
* **`SecretStr` inside a generic, a union, a 3-way union, `Optional`, `Annotated`, and
  `dict[str, list[SecretStr | None]]`**: all discovered. `annotation_parts` does its job.
* **Three shapes are missed, and each leaks**: a `SecretStr` **subclass** (`part is SecretStr`
  is identity, not `issubclass`); **`SecretBytes`**, which is not considered at all; and a model
  that is **not a module-level name** (nested in a class, or built by a factory) — never in
  `vars(module)`, so never discovered. Each was driven to a `ValidationError` quoting the
  planted secret in full. R-SEC-050.
* A secret-bearing model **as a field of a plain `BaseModel`** is clean: Pydantic invokes the
  inner model's `__init__`, so the funnel fires. The report's claim holds.

---

## Priority 3 — OD-4 (Part 5)

**The reported shape is fixed, both directions**, and the six untested exempt keys are now
tested. Dict keys are checked and never exempt. **The refusals never quote what they refused** —
verified across a mail-shaped key, a mail-shaped top-level key and a nested value; all render
`<key withheld>` and none contains any window of the offending text. My own reintroductions of
J/K/L/M are all caught (7, 9, 14 and 8 tests respectively).

**A fourteenth shape exists** (`attack_od4.py`). `_is_our_prose` accepts one prose key followed
by *nothing but list indices*, with no depth limit — so a body buried in **nested lists** under
any of the seven exempt keys is exempt at any depth:

```
assert_record_is_content_free({"notes": [[<multi-line, 380-char body>]]})   # passes
assert_record_is_content_free({"notes": [[[[[<the same body>]]]]]})          # passes
assert_record_is_content_free({"measures": [(<the same body>,)]})            # passes
```

Driven to disk: `json.dumps` writes the body out intact. The docstring says the exemption is
"exactly the shape `notes` and `pre_registered_rules` are written in" — but `notes[0][0]` is
not that shape, and for the five prose keys `as_record` emits as **plain strings**
(`title`, `measures`, `validates`, `falsified_when`, `changes_if_it_fails`) even `notes[0]`-style
list nesting is wider than the producer. The work order's exit condition — "rejects mail text at
any nesting depth under any key" — is not met.

Two more containers the walk never enters: `set` / `frozenset`, and any `Mapping` that is not a
`dict` (`collections.UserDict`). Their contents are unchecked. `json.dumps` would then raise,
so nothing is written — a crash, not a refusal — but `assert_record_is_content_free`'s own
docstring says it walks "a record … at any depth", and it does not. A `str` subclass overriding
`__len__`/`splitlines` also passes; contrived, but it shows the bound is taken on the value's
own word. R-SEC-048.

**One guard does not guard what its docstring says.** I reintroduced the R-ARCH-031 shape the
de-duplication exists to prevent — a divergent copy of `PROSE_FIELDS` inside `record.py`,
widened by one key — and **nothing failed**.
`test_the_exempt_set_is_the_producers_own_list_and_still_matches_it` compares `spec.PROSE_FIELDS`
against `as_record()`'s keys; it never checks that `record.py` uses spec's set rather than its
own. R-SEC-053.

---

## Priority 4 — Parts 6 and 4

### Part 6: the coupling is swept, not unrepresentable

**At the wire it is right**, verified independently by spying on the transport rather than by
running the shipped test: a whole `run_probes` sends 28 listings at
`q='-in:spam -in:trash'` with `includeSpamTrash` absent, and `measure_threads` at
`WHOLE_MAILBOX` sends `q='in:anywhere'` with `includeSpamTrash=true`. Zero out-of-step calls in
either direction. My reintroductions of the pair split, the mispaired table row, and a probe
spelling the operator itself are all caught.

**But it is not unrepresentable.** `GmailClient.list_messages` keeps two independent
keyword parameters (`query: str`, `include_spam_trash: bool = False`), so `mypy --strict`
accepts any disagreement; the coupling lives entirely in two AST sweeps, and both have holes
(`attack_scope_sweep.py`). The pairing sweep only inspects calls where `include_spam_trash` is
**present**, and the operator sweep only matches `ast.Constant` strings:

```
client.list_messages(..., query=MailboxScope.WHOLE_MAILBOX.query)   # flag simply omitted
client.list_messages(..., query=f"in:{where}")                       # f-string
client.list_messages(..., query="in:" + "anywhere")                  # concatenation
client.list_messages(..., query="in:{}".format("anywhere"))          # format
```

All four evade **both** sweeps and put `q=in:anywhere` on the wire with `includeSpamTrash=false`
— the exact disagreement the enum exists to make impossible. The first is the likeliest real
mistake and uses the enum exactly as intended. R-SEC-051.

### Part 4: correct, and registered

* **The `errors[]` correction is right.** I fetched Google's current Gmail
  `handle-errors` guide: **all seven** JSON examples on the page (400 `badRequest`, 401
  `authError`, 403 ×4, 500 `backendError`) carry an `errors[]` array and **none** carries a
  top-level `status`. R-GMAIL's finding and the corrected HANDOFF text are corroborated.
  Independently of that, the correction is operationally inert: `_error_reason` reads
  `errors[].reason` first and falls back to `status`, and I drove six envelope shapes
  (`errors[]` only, `status` only, both disagreeing, empty `errors[]`, neither, and a `reason`
  that is a sentence) — the right slug every time, and no mail text survives any of them.
* **PF-17..PF-20 are registered in AD §F with a stated consequence each**, and the two tests
  that assert it are real: I confirmed `_NAMED_IN_SOURCE` scans both trees and `_REGISTERED`
  parses §F's table, and the `[PREFLIGHT PF-18]` / `[PREFLIGHT PF-19]` / `[PREFLIGHT PF-20]`
  markers exist at the page-token bound, the history dedup and `scope.py`.
* **One observation, not a finding:** the register is a document. `mailweave-preflight --plan`
  prints six probes and mentions none of PF-17..20, so an operator working from the tool rather
  than from AD §F will not see them.

### Part 1: verified

Every registered probe was driven **selected alone** through `run_probes` against the fake
transport (`drive_every_probe.py`) — which is R-SEC-041's exact shape, since the crash was on
the first unconditional call regardless of selection. All six complete; PF-3 correctly demands
`--exclusive-window` first. R-SEC-041 is closed as far as a fake transport can close it.

---

## On the implementer's own process claim

It reports a first run of the 3b cases that produced three false greens because `ruff format`
had reflowed the code and its `str.replace` anchors matched nothing. **I verified this
independently by hitting the same failure mode myself**: my first attempt to reintroduce
`parse_instant`'s quoting asserted its anchor and reported `ANCHOR MISS (0)` — the docstring
had been rewritten, so the string I patterned on no longer existed. Every one of my 20
reintroductions asserts `text.count(old) == 1` before patching, restores from a snapshot
afterwards, and the whole tree was byte-compared against the snapshot at the end and matched.

**I did not replicate their 23; I ran 20 of my own.** 18 caught, 2 not. Of the two, one
(`model_validate` override) is benign redundancy and I confirmed no leak by direct
reproduction; the other (the `PROSE_FIELDS` copy) is a genuine gap in a guard the report
describes as existing (R-SEC-053). The claim "23 caught, 0 missed" is not falsified — my cases
are not theirs — but "perfect" is not what an independent battery finds.

---

## Findings

```
ID: R-SEC-045  Severity: HIGH  Rubric: none — SEC-03 account pinning
Location: harness/src/mailweave_harness/pinning.py (_mint_proof, SeedSession.assert_bound_to,
  and the docstring's "what remains possible" section)
Repro: /tmp/rsec12/attack_public_forge.py — read address/scopes/proof off a real session (four
  public attribute reads), let the session and its credential go out of scope, allocate an
  attacker-controlled ProfileSource onto the freed address, then build the session with the
  ORDINARY PUBLIC CONSTRUCTOR. __post_init__ accepts it; assert_bound_to(evil) authorises it.
  Reliability measured in /tmp/rsec12/attack_forge_reliability.py: 59/60 and 60/60 over
  independent trials. Two further routes in attack_id_reuse.py (vars(session)["credential"]=None,
  reused on the FIRST allocation) and attack_id_reuse3.py (in-process pickle round trip, then
  drop the original).
Expected: "No construction path matters ... none of them can produce fields that agree with a
  proof they cannot compute"; the only surviving routes are importing _mint_proof and
  object.__new__ + object.__setattr__; and the work order's "is bound to its credential".
Actual: the proof does not have to be computed — it is a public field — and id(credential) is
  inheritable by a later allocation, because assert_bound_to never reads self.credential and
  nothing enforces that a session still holds the credential it names. R-SEC-040 is reopened by
  public API alone. Inert today: nothing consumes a SeedSession.
Required fix: do not derive the binding from a value a fresh object can take on. Bind a
  per-credential random nonce held in a module-private WeakKeyDictionary (or equivalent), so a
  credential the mint never saw has no nonce and cannot match; keep the recomputation at the use
  site. Then correct the enumeration again — and consider whether an enumeration of "what
  remains possible" is a claim this module should keep making, given it has now been wrong three
  times. Also name the two unnamed residues: a mutable get_profile on the bound object, and a
  duck-typed impostor at the use site.
```
```
ID: R-SEC-046  Severity: HIGH  Rubric: none — contract I-1 / AD A.7a (RR EV-01, EV-03)
Location: server/src/mailweave/envelope/disposition.py (DispositionCertificate.__init__,
  _MINT_TOKEN)
Repro: /tmp/rsec12/attack_forged_certificate.py — copy.copy(certificate) rebuilds it without
  __init__ ever running, so _MINT_TOKEN is never presented; two PLAIN attribute assignments
  (forged._withheld = (), forged._hit_count = forged.disclosed_hits) make it internally
  consistent; the resulting Envelope is ACCEPTED with withheld=[] and partial=False for a
  response whose ledger recorded a hit no record accounts for.
Expected: "an Envelope cannot be built without one, and one cannot be made without running the
  set difference ... not a defence against code that deliberately reaches for a private name".
Actual: forging needs no private name at all — copy.copy and two ordinary assignments. This is
  R-SEC-039's defect and part 3b's defect, in the server tree, in the seal the product contract
  rests on. Inert today: no source module copies a certificate.
Required fix: re-establish the certificate's own consistency where it is used rather than where
  it is minted — Envelope's validator already re-derives three of the four facts and should
  reject a certificate whose invariant it cannot re-check — or make the token unforgeable by
  reconstruction (e.g. bind it into the digest). And widen the round-12 sweep from "pinning.py"
  to "capability tokens and mint proofs", which flags exactly this site and no innocent one.
```
```
ID: R-SEC-047  Severity: HIGH  Rubric: none — contract I-1 / AD A.7a (RR EV-01, EV-03)
Location: server/src/mailweave/envelope/response.py (Envelope's model_validators)
Repro: /tmp/rsec12/attack_seal_peers.py —
  envelope.model_copy(update={"withheld": (), "partial": False}) skips EVERY model_validator,
  including _withheld_matches_the_certificate. The result serialises via model_dump(mode="json")
  with "withheld": [] while its own certificate still certifies one withheld id.
Expected: an envelope may not restate the certificate's conclusion differently (the validator's
  own docstring); the disposition invariant holds for every envelope that leaves the process.
Actual: one documented, ordinary line of Pydantic produces a wire-serialisable envelope stating
  a false disposition. Inert today: no source module calls model_copy.
Required fix: re-check the disposition at serialisation rather than only at construction, or
  forbid model_copy on Envelope (override it to re-validate). A sweep for model_copy /
  model_construct on invariant-bearing models would make it structural.
```
```
ID: R-SEC-048  Severity: MEDIUM  Rubric: OD-4 — no mail text in a record without approval
Location: harness/src/mailweave_harness/preflight/record.py (_is_our_prose,
  assert_record_is_content_free)
Repro: /tmp/rsec12/attack_od4.py — assert_record_is_content_free({"notes": [[<a multi-line
  380-char body>]]}) passes, as does depth 5, as does a tuple inside a list, for all seven
  exempt keys; json.dumps then writes the body out intact. Separately, sets, frozensets and
  non-dict Mappings are never walked at all.
Expected: the work order's exit condition — "rejects mail text at any nesting depth under any
  key" — and the module's own "one top-level prose key, then nothing but list indices, which is
  exactly the shape notes and pre_registered_rules are written in".
Actual: the index rule has no depth limit, so notes[0][0] inherits the exemption though it is not
  the shape notes is written in; and for the five prose keys as_record emits as plain strings,
  even one level of list nesting is wider than the producer. Unreachable through the six shipped
  probes, exactly as R-SEC-042 was.
Required fix: bound the exemption to the producer's actual shape — one prose key plus at most
  one list index — or, better, derive it from the value's type rather than its path. Walk sets
  and Mappings, or refuse a record containing a container the walk does not understand.
```
```
ID: R-SEC-049  Severity: LOW  Rubric: SEC-04 — no secret in log/error/traceback/file
Location: server/src/mailweave/validation.py (SecretBearingModel.__init__ / model_validate /
  model_validate_json, all three `raise ... from None`)
Repro: /tmp/rsec12/attack_context_chain.py — `raise X from None` inside an except block sets
  __cause__=None and __suppress_context__=True but leaves __context__ pointing at the raw
  ValidationError. For a secret that became a JSON key, str(exc.__context__) prints the WHOLE
  secret untruncated; for every shape, .errors()/.json() on it carry the input. No test in the
  suite mentions __context__.
Expected: "Pydantic's own report never reaches a traceback as a chained cause" — true — and the
  broader property that no secret is reachable from the refusal.
Actual: the traceback is clean; the object is not. Any handler that walks __context__ (a
  structured-logging integration, a debugger, a future test) renders it.
Required fix: build the message inside the handler and raise OUTSIDE it, so __context__ is never
  set; or clear it explicitly. Add the surface to the canary's `renderings()`.
```
```
ID: R-SEC-050  Severity: LOW  Rubric: SEC-04 / SEC-06 — the canary's completeness
Location: tests/fixtures/secret_models.py (_mentions_secret, models_with_secrets) and
  tests/test_standing_cycle_round12.py::test_every_model_that_declares_a_secret_cannot_render_its_input
Repro: /tmp/rsec12/probe_canary_discovery.py and /tmp/rsec12/probe_nested_leak.py, plus planted
  models in the scratch tree. `part is SecretStr` is identity, so a SecretStr SUBCLASS is missed;
  SecretBytes is not considered at all; and a model that is not a module-level name (nested in a
  class, or returned by a factory) is never in vars(module). Each was driven to a ValidationError
  quoting the planted secret in full.
Expected: "A new secret-bearing model is covered the moment it exists."
Actual: covered for the shapes checked — generics, unions, Annotated, both trees, all verified —
  and not for three others. No such model exists today.
Required fix: test `isinstance(part, type) and issubclass(part, SecretStr | SecretBytes)`, and
  discover models by walking each module's classes recursively rather than only its module-level
  names (or assert that no BaseModel subclass is defined below module level).
```
```
ID: R-SEC-051  Severity: LOW  Rubric: none — part 6's coupling
Location: tests/test_standing_cycle_round12.py (_scope_argument_pairs,
  test_no_module_spells_a_mailbox_scope_operator_outside_the_scope_enum);
  server/src/mailweave/gmail/client.py::list_messages
Repro: /tmp/rsec12/attack_scope_sweep.py — four call shapes evade BOTH sweeps and put
  q=in:anywhere on the wire with includeSpamTrash=false. The likeliest is simply
  `client.list_messages(..., query=MailboxScope.WHOLE_MAILBOX.query)` with the flag omitted:
  _scope_argument_pairs returns early when include_spam_trash is absent. The others spell the
  operator non-literally (f-string, concatenation, .format), which ast.Constant matching misses.
Expected: "the two settings cannot be supplied independently"; "structural rather than a
  docstring's promise".
Actual: it is an AST sweep with two holes, not a property of the types — list_messages still
  takes the two as independent keywords and mypy --strict accepts every plant. No such call
  exists today.
Required fix: flag a call that passes `query=<x>.query` without include_spam_trash beside it;
  and prefer giving the client a single `scope` parameter, which removes the sweep's job rather
  than widening it.
```
```
ID: R-SEC-052  Severity: LOW  Rubric: none — SEC-03, hardening only
Location: harness/src/mailweave_harness/pinning.py::_mint_proof
Repro: /tmp/rsec12/probe_material_ambiguity.py — the HMAC material is
  "\x00".join((address, "\x1f".join(scopes), str(id(credential)))), which is ambiguous:
  _mint_proof("a\x00b", ("c",), c) == _mint_proof("a", ("b\x00c",), c), and
  _mint_proof("x", ("p\x1fq",), c) == _mint_proof("x", ("p","q"), c).
Expected: a proof binds one (address, scopes, credential) triple.
Actual: distinct triples share material. Not exploitable today — the address comes from
  getProfile and the scopes from a module constant, so neither can be steered to carry a
  separator — and it becomes exploitable only if a caller ever supplies either.
Required fix: length-prefix each component (or hash each separately and HMAC the digests).
```
```
ID: R-SEC-053  Severity: LOW  Rubric: none — guard quality
Location: tests/test_preflight_probes.py::test_the_exempt_set_is_the_producers_own_list_and_still_matches_it
Repro: reintroduce the R-ARCH-031 shape the de-duplication exists to prevent — a local
  PROSE_FIELDS copy inside record.py, widened by one key — and re-run the suite. Nothing fails
  (/tmp/rsec12/run_rest.py, case N).
Expected: the test's own docstring — "One list, in the module that writes the record - not a copy
  in the module that checks."
Actual: it compares spec.PROSE_FIELDS against as_record()'s keys and never checks where record.py
  gets its set, so a divergent copy in the checker is invisible.
Required fix: assert `record.PROSE_FIELDS is spec.PROSE_FIELDS`, or sweep record.py's AST for a
  local binding of the name.
```

---

## Recommendations, per criterion

Scoped recommendations only. **None of these is a PASS**, and each says exactly what it covers.

* **SEC-03 (harness isolation and account pinning).** **Do not move toward PASS.** R-SEC-039 is
  genuinely closed and R-SEC-040 is not: the credential binding is forgeable through public API
  (R-SEC-045). As in round 11 this reaches no write today, so it is **not a BLOCKER** — and as
  in round 11 it is a hard precondition on WS-16. Control 1 (Google's Testing-status allowlist)
  remains unverifiable from here; the module still says so and I did not weaken that.
* **SEC-04 (token storage hygiene) — currently PASS, scoped to round 3's atomicity evidence.**
  I recommend recording, **as a scoped observation and not as a re-PASS**, that on this tree no
  secret fragment reaches `str`, `repr`, `args`, `__notes__` or `traceback.format_exc()` across
  152 forced validation failures spanning 11 corruption shapes, 7 entry points and both
  secret-bearing models. That is a much wider claim than SEC-04's existing PASS covers and
  should not be folded into it. **R-SEC-043 is closed**; R-SEC-049 and R-SEC-050 are hardening.
* **SEC-06 (trace redaction canary).** The canary is real and its reflection discovery works for
  the shapes I could plant. Do not treat "covered the moment it exists" as unqualified until
  R-SEC-050's three shapes are closed.
* **OD-4 (no mail text in a record without approval).** R-SEC-042 is closed for the reported
  shape and six untested keys are now covered. The exit condition as written ("any nesting
  depth under any key") is **not** met — R-SEC-048. Fix before probes gain structured notes,
  which is the same trigger the work order gave for R-SEC-042.
* **EV-01 / EV-03 and contract I-1 (the disposition invariant).** R-SEC-046 and R-SEC-047 are
  the round's most consequential findings and neither is round 12's fault. They belong in the
  next work order, together, because they are one shape.
* **Part 1 / R-SEC-041.** Closed as far as a fake transport can close it: all six probes run
  end to end when selected alone.
* **Part 4.** Correct and registered. The `errors[]` correction is corroborated against
  Google's live guide.
* **R-SEC-044 (egress port)** remains open and untouched, as the implementer states.

---

## Established by execution

R-SEC-043 was real (18-char prefix + 22-char suffix of a live refresh token) and is fixed; both
"extra" leaks are real and the three-channel analysis is correct; `msg` is an independent
channel that `hide_input_in_errors` does not touch. No secret reaches `str`/`repr`/`args`/
`__notes__`/`format_exception` across 152 forced failures. The canary discovers a brand-new
secret-bearing model in the harness tree and fails five tests plus the sweep; generics, unions,
`Annotated` and nested submodels are all handled. `SeedSession` refuses subclassing four ways
and refuses every field tampering. R-SEC-042 is fixed for the reported shape and six previously
untested keys; the refusals never quote what they refused. All six probes run end to end
individually. Both mailbox scopes reach the wire as one agreeing pair, verified at the transport.
The `errors[]` correction matches Google's current guide, and `_error_reason` handles six
envelope shapes without leaking mail text. 18 of my 20 independent reintroductions were caught;
the tree was restored byte-identical. All gates reproduce, including 1,726 tests and the exact
rubric counts.

## False on execution

*"No construction path matters … [importing `_mint_proof` and `object.__new__` +
`object.__setattr__`] are the only routes"* — a fully public forgery exists, reliably
(R-SEC-045). *"[the proof] authorises nothing on its own"* — with a groomed allocation, it does.
*"`id(credential)` … cannot be reused while any session names it"* — true of a session that
holds it; nothing enforces that, and `assert_bound_to` no longer reads the field. *"A
certificate … cannot be made without running the set difference … not a defence against code
that deliberately reaches for a private name"* — `copy.copy` and two plain assignments suffice,
and the result is accepted by `Envelope` (R-SEC-046). *"The envelope may not restate the
certificate's conclusion differently"* — `model_copy` skips the validator that says so
(R-SEC-047). *"`assert_record_is_content_free` rejects mail text at any nesting depth under any
key"* — not for nested lists under a prose key (R-SEC-048). *"The two settings cannot be
supplied independently"* — four ordinary call shapes do (R-SEC-051). *"One list … not a copy in
the module that checks"* — a copy is not detected (R-SEC-053). And the sweep's narrowing is
argued against a rule nobody proposed: the shape it declines to cover is live in
`disposition.py`.

## Not establishable here at all

Whether Google's Console **Testing-status test-user allowlist** actually refuses consent for the
personal mailbox on the harness client — control 1, still the strongest of the three, still a
Console setting and not executable code, still trusted on prose alone. This is the review's
largest gap and it has been the largest gap since round 11.

Whether **Gmail behaves as the fixtures do**: every verdict in this round's end-to-end evidence
is a verdict about an `httpx.MockTransport`. PF-17..PF-20 exist precisely because four shapes
are guessed; none can be settled without the live run. Whether Gmail's token endpoint returns
`scope` (PF-17) is the one most likely to break the owner's first attempt.

Whether **Pydantic will keep routing mapping validation through a custom `__init__`** — I
confirmed it does today, at this version, on this tree; the shipped test pins the assumption and
nobody can pin the library.

Whether a session or a certificate ever **crosses a real process boundary** — both cross-process
claims here are made by substituting a key or by copying in-process. This suite spawns no
subprocess and I did not add one.

Whether **`id()` recycling is as reliable on the owner's machine** as it is in this container:
59/60 and 60/60 here, on CPython 3.12's allocator. The finding does not depend on the rate — one
success is enough — but the number is a measurement of this interpreter, not a constant.

Whether the **historical** claim about `errors[]` versus `status` is right. I established what
Gmail's guide shows today (all seven examples carry `errors[]`; none carries `status`), which is
what the correction actually asserts. Which spelling is *older* across Google's APIs is a claim
about a history I cannot check from here, and the code reads both regardless.

---

**Overall: no BLOCKER.** Round 12's four fixes are real work and three of them are better than
their reports claim. But **two round-blocking HIGHs on this round's own subject** (R-SEC-045)
and **two more on the shape this round's standing check was supposed to be about**
(R-SEC-046/047, pre-existing) mean the round should not close as done. None reaches a Gmail
write or a real response today, which is why none is a BLOCKER — and that is the same sentence
round 11 wrote about R-SEC-039, which is exactly why it should not be leaned on twice.
