# ROUND 12 — implementer report (Parts 2, 3, 4, 5, 6)

**Implementer:** round-12 implementer, 2026-09-02. Part 1 was already landed and verified before
this session began; I did not touch it except where part 6 required it. **Part 3b was added after
the orchestrator independently attacked this round's own fix for Part 3 and defeated it**; it is
written up in full below, including the qualifications the orchestrator supplied, so R-SEC does not
have to rediscover that the finding is inert today.

Everything below is written to be checked rather than believed. Every fix carries a
**reintroduction check**: the defect put back into the source, the suite re-run, the exact test
that failed recorded. The battery is 23 separately reintroduced defects, run one at a time against
the final tree, every patch anchor asserted before it is applied: **23 caught, 0 missed.**

---

## Part 2 — R-SEC-043: no validation failure can quote a value

### What I found before writing anything

The reported shape reproduces: a `credentials.json` whose `refresh_token` is a dict makes
`TokenStore.load()` raise a `TokenStoreError` carrying `input_value={'v': '1//0gTHE-REAL-REFR...'}`
— an intact prefix and suffix of the real token. Two things the finding did not say, both found by
probing before fixing:

1. **`load_config` leaks the client secret whole, not in fragments.** `MailweaveConfig` has the
   same shape and a client secret is short enough to sit *inside* Pydantic's truncation window.
   `{"client_secrett": "<the secret>"}` — one typo'd key — produced
   `Extra inputs are not permitted [type=extra_forbidden, input_value='GOCSPX-…' ]` with the
   entire value.
2. **A secret written into `obtained_at` comes out untruncated through a different channel
   entirely.** `parse_instant` spelled its refusal `f"{field}={value!r} is not an RFC 3339
   instant"`, so the value reached `msg`, not `input_value`. `hide_input_in_errors` does nothing
   about that. This is why fixing "the `refresh_token` field of `StoredCredentials`" would have
   left the class open.

So there are **three channels**, not one: `input_value` (the value), `msg` (our own validators'
text) and `loc` (the field *path*, which for an `extra_forbidden` error is a key the document
chose — so a secret that became a JSON key is reported by name).

### What I changed

New `server/src/mailweave/validation.py`:

- **`SecretBearingModel`** — a base carrying `hide_input_in_errors=True` and overriding `__init__`,
  `model_validate` and `model_validate_json`. `StoredCredentials` and `MailweaveConfig` now inherit
  it. A failure becomes `errors.SecretDocumentMalformed` with field paths and error types only,
  raised `from None` so Pydantic's own report never reaches a traceback as a chained cause.
- **`failure_summary(model, failure)`** — the single renderer. It reads `loc` and `type`, never
  `msg`, and prints a path segment **only if the model's own field graph declares a field of that
  name**; anything else becomes `<withheld>`. Names are collected from the model graph rather than
  matched against a pattern, because a pattern says "this looks like a field name" and a secret is
  free to look like one.
- `gmail/models.py::_failure_paths` is **deleted** and its call site now uses `failure_summary`;
  `content/payload.py` stopped reading `errors()[0]["msg"]` and uses it too. There is now one
  renderer of a `ValidationError` in the tree, and a sweep keeps it that way.
- `envelope/wire.py::parse_instant` names the field and no longer quotes the value.
- `_GmailModel` gained `hide_input_in_errors=True`, so `parse_response`'s chained cause can no
  longer put mail-derived input values into a traceback either (AD A.11's rule applied to the
  exception it chains, not only to the message it writes).
- `MailweaveConfig`'s "scopes/allowlist are fixed" validator now raises `ConfigError` rather than
  `ValueError`. Pydantic propagates a non-`ValueError` instead of folding it into a report, so that
  refusal — whose text is entirely code-level constants — keeps its own words now that `msg` is no
  longer rendered. This is the mechanism `content/payload.py` already uses.

**One assumption is load-bearing and is pinned by a test rather than trusted:** Pydantic routes all
mapping validation through a model's custom `__init__`, which is why one override covers
`model_validate`, `model_validate_json`, `model_validate_strings`, the raw
`__pydantic_validator__`, and these models appearing as a field of another. That is internal
routing, not a documented contract. `test_every_pydantic_validation_entry_point_is_covered_for_a_
secret_bearing_model` drives every `model_validate*` name discovered on `BaseModel` plus the raw
validator plus a nesting model, and fails loudly if a future version stops honouring it. A
**non-mapping** input never reaches `__init__` — that path is refused by Pydantic itself, and is
where `hide_input_in_errors` is doing real work.

### The canary, which was incomplete as well as the code

`tests/fixtures/secret_models.py` **discovers** secret-bearing models by importing both trees and
asking every `BaseModel` whether any field annotation mentions `SecretStr`. Nothing names
`refresh_token`. The new tests in `tests/test_auth_consent.py` are parametrised over that
discovery, generate corruption shapes from each model's own field list, and drive every entry
point for every shape, asserting that **no eight-character window** of a planted secret appears in
`str`, `repr`, `args`, `format_exc()` or the full chained `format_exception()`. Five tests:

- `test_no_secret_survives_a_validation_failure_on_any_model_that_holds_one`
- `test_every_pydantic_validation_entry_point_is_covered_for_a_secret_bearing_model`
- `test_nothing_under_the_funnel_quotes_what_it_refused` — validates through a twin subclass with
  `BaseModel.__init__` restored, so the two defences *below* the entry-point overrides are tested
  rather than shadowed by them
- `test_the_credential_and_config_loaders_refuse_a_corrupt_file_without_quoting_it` — real files,
  real permissions, the reproduction's own route
- `test_the_canary_covers_every_model_that_holds_a_secret`

### Reintroduction checks

| Defect put back | Result | Test that failed |
|---|---|---|
| A · `hide_input_in_errors` removed | **caught** | `…_validation_failure_on_any_model_that_holds_one` (both models), `…_declares_that_it_may_not_quote_its_input`, `…_nothing_under_the_funnel…` |
| B · `loc` allowlisting removed (raw path printed) | **caught** | `…_validation_failure_on_any_model…`, `…_loaders_refuse_a_corrupt_file…` |
| C · `parse_instant` quotes its value again | **caught** | `test_nothing_under_the_funnel_quotes_what_it_refused[StoredCredentials]` |
| D · the `__init__` funnel removed | **caught** | `…_validation_failure_on_any_model…`, `…_every_pydantic_validation_entry_point_is_covered…` |
| D2 · **R-SEC-043 verbatim** — funnel gone, input not hidden, `load()` renders the report | **caught** | six tests, both models |
| D2′ · only `load()`'s half restored (the finding's literal code shape) | **not a leak** — see below |
| D3 · a second renderer of a `ValidationError` added to `load()` | **caught** | `test_no_module_renders_a_validation_error_any_other_way` |

**D2′, reported because it is informative rather than because it failed.** Restoring only the
call-site half — `load()` catching and interpolating the exception, which is R-SEC-043's literal
code shape — produces no leak and no test failure. That is not a gap in the canary: with the funnel
in place, the exception reaching that line is already the value-free `SecretDocumentMalformed`, so
interpolating it discloses nothing. The finding's literal shape can no longer produce a disclosure
by itself; the *property* (D2 above, all three defences removed) is caught six ways. I record it so
R-SEC does not spend time reproducing the original line and concluding the fix is untested.

### What I could not establish

- Whether Pydantic 2.14+ still routes validation through a custom `__init__`. I pinned the
  assumption with a test; I cannot pin the library.
- `content/payload.py` and `gmail/models.py` still chain the raw `ValidationError` as `__cause__`.
  With `hide_input_in_errors` now set on both model bases, the chained rendering carries paths and
  types but no input values. I did **not** verify that for every payload shape — only for the
  secret-bearing models, where the canary is exhaustive.
- `errors(include_input=True)` still returns the input object itself. That is data, not a
  rendering, and nothing in the tree calls it; I did not attempt to close it.

---

## Part 3 — R-SEC-039 / R-SEC-040: `SeedSession`

### What was actually wrong

The token check lived in `_issue`, a classmethod **beside** the public constructor. R-SEC's attack
did not need to reach for `_SESSION_TOKEN` because it did not need `_issue`. And the session held
two strings, so nothing tied it to the client that answered `getProfile`.

### What I changed (`harness/src/mailweave_harness/pinning.py`)

- `verify_seed_account` now takes the **credential** — a `ProfileSource` protocol,
  `get_profile() -> Profile`, which `mailweave.gmail.GmailClient` already satisfies unmodified — and
  calls `getProfile` on it. There is no separate address-fetcher, so "the credential that produced
  the observation" is not something a caller can get wrong.
- A session carries `address`, `scopes`, `credential` and a `proof`: an HMAC over all three keyed
  by a per-process, module-private `_MINT_KEY`. `__post_init__` verifies it, so the check is in the
  constructor rather than beside it. **Read Part 3b before believing that sentence does the work I
  originally claimed for it: `__init__` is not the only construction path, and the guarantee now
  lives at the point of use.**
- Why an HMAC and not a capability-token field: `dataclasses.replace` is public, ordinary, needs no
  private name, and re-runs `__post_init__`. A token field travels through it untouched, so
  `replace(seed_session, address="<the owner's mailbox>")` would have forged a session from a
  legitimate one. Binding the fields makes that fail.
- `__init_subclass__` refuses subclassing. R-RETR's round-3 attack on the disposition seal
  (`ROUND_03/R-RETR.md`, attack 8) defeated a mint token by subclassing rather than by reaching for
  it, and that move defeats any `__post_init__` check.
- `assert_bound_to(credential)` closes R-SEC-040: two clients holding one token are two
  credentials and only one of them was asked who it was. **Superseded in Part 3b** — it compared
  identities, which turned out to track an artefact of deep copying rather than the proof; it now
  recomputes the proof over the credential passed in, which settles the same question and three
  others.
- `__repr__` renders neither the credential (whose own `repr` may print a token) nor the proof.

### The docstring, which is the finding

Rewritten to say plainly that the previous claim was **wrong**, in a section headed *"The claim
this module used to make, and why it was false"* — and then rewritten again in Part 3b, because my
replacement claim was itself insufficient. Both corrections are in the module, in that order, so a
reader can see which claims this module has had to withdraw. It states what remains possible:
`object.__new__` + `object.__setattr__`, and importing `_mint_proof`. Both are unclosable in
Python; the difference is that the module's claim is now true — those are the only routes, and each
is a line a reviewer sees. `test_the_private_path_is_the_residue_the_docstring_describes` asserts
the residue **still works**, so the honest half cannot silently become an overstatement either.

### Reintroduction checks

| Defect put back | Result | Test that failed |
|---|---|---|
| E · proof check leaves `__post_init__` (round 11's shape) | **caught** | `test_the_public_constructor_cannot_mint_a_session` + 3 more |
| F · proof binds only the address | **caught** | `test_a_session_cannot_be_re_pointed_at_another_mailbox_after_it_is_minted` |
| G · subclassing allowed again | **caught** | `test_a_session_cannot_be_minted_by_subclassing_the_check_away` |
| H · credential binding removed (R-SEC-040) | **caught** | `test_a_session_minted_from_one_credential_is_refused_by_another` |
| I · docstring reverts to the false claim | **caught** | `test_the_module_no_longer_claims_a_private_name_is_needed` |

### What I could not establish

- Nothing consumes a `SeedSession` yet, so `assert_bound_to` has no production caller. It is the
  contract WS-16 will be written against, as before. I did not build a consumer.
- Control 1 (Google's Testing-status allowlist) remains unverifiable from here, exactly as R-SEC
  said. The docstring still says so and I did not weaken that.
- The HMAC binds `id(credential)`. That identity is stable because the session holds a reference,
  so the object cannot be collected and its id cannot be reused while a session names it. I
  reasoned this rather than measuring it under GC pressure.

---

## Part 3b — the orchestrator's finding: the HMAC had no chokepoint

**Raised by the orchestrator after Part 3 landed, verified by me before fixing.** My own Part 3
docstring said the check was "*in* the constructor, not beside it". That was true and it was not
enough, and it is worth being blunt about what it was: **the eighth appearance of "one shape
validated, peers trusted", inside the fix for the seventh.** I defended `dataclasses.replace` and
trusted its peers.

### Reproduced first

```
legit    = verify_seed_account(cred, seed_address=SEED)
tampered = copy.copy(legit); object.__setattr__(tampered, "address", PERSONAL)

copy.copy(tampered).assert_bound_to(cred)      -> AUTHORISED   (address = the real mailbox)
copy.deepcopy(tampered).assert_bound_to(cred)  -> refused
pickle round-trip .assert_bound_to(cred)       -> refused
```

`SeedSession` defines none of `__reduce__`, `__reduce_ex__`, `__getstate__`, `__setstate__`,
`__copy__`, `__deepcopy__`, so all three restore `__dict__` directly and `__post_init__` never
runs. Worth recording that **two of the three refused for the wrong reason**: `deepcopy` and
`pickle` copy the credential too, so the old `credential is self.credential` comparison failed on
an artefact of deep copying rather than on anything about the proof. A session whose credential
was not deep-copied sailed through, which is the `copy.copy` line.

### I took the orchestrator's option, and here is the argument for it

**Verify at the point of use.** `assert_bound_to` now recomputes the proof over the credential in
hand and compares; the identity check is gone, subsumed. One `compare_digest` settles all three
things minting settled — the address and scopes are the ones a profile was observed for, the
credential about to be used is the one that answered `getProfile`, and some code in this process
ran that check, because `_mint_proof` is computed in exactly one other place and that place holds
a `Profile`. **No construction path matters**, including ones Python has not shipped.

I considered a `__setstate__` chokepoint plus a sweep and rejected it, for the reason the
orchestrator gave and one more of my own. The reason given: it defends three dunders by name and
leaves a fourth for round 13. My own: the claim "all copy protocols funnel through `__getstate__`"
is itself a claim about CPython's copy protocol that I would then be trusting — a fourth shape
validated with its peers trusted, one level down. Verifying at use needs no such claim.

Two consequences worth stating rather than leaving to be found:

- **A legitimate `deepcopy` still works with its own client**, which the identity comparison
  refused. Recomputing over the *passed* credential is what makes the refusals mean something
  rather than track an artefact.
- **A session cannot cross a process boundary**, because `_MINT_KEY` is per-process. The
  orchestrator's xdist/multiprocessing/cache scenario now fails closed on the receiving side
  instead of skipping verification silently.

`__post_init__` keeps its check and is now documented as what it is: an **early failure** for
`__init__` and `dataclasses.replace`, so the ordinary mistake is loud where it is written. It is
explicitly not the guarantee.

### The docstring, corrected the same way the first claim was

A new section, *"The second correction: a check in the constructor is still a check at
construction"*, records the reproduction verbatim, says my own claim was insufficient, and carries
**both of the orchestrator's qualifications**: nothing in either tree pickles or copies a session
today, so this was inert exactly as R-SEC-039 was; and `object.__setattr__` presumes in-process
code execution — but that is the same threat model under which `replace` was defended, so the
defence was incomplete on its own terms. It also names the residue 3b does **not** close: an
operation that never calls `assert_bound_to` is stopped by nothing here, and in-process no object
can force a caller to ask it a question.

### Reintroduction checks

| Defect put back | Result | Test that failed |
|---|---|---|
| 3b-1 · the use-site check reverts to the identity comparison (**the shipped defect, exactly**) | **caught** | `test_no_way_of_rebuilding_a_session_authorises_a_tampered_one` on 5 of 9 paths (`copy.copy`, both `__reduce_ex__` protocols, `object.__new__`, the object itself), plus `…_still_authorises_its_own_credential[copy.deepcopy]`, plus the standing sweep `test_the_seed_session_proof_is_verified_somewhere_other_than_its_constructor` |
| 3b-2 · the use-site check recomputes over the *stored* credential | **caught** | `test_a_session_minted_from_one_credential_is_refused_by_another` and 4 legitimate-rebuild cases |
| 3b-3 · verification deleted from `assert_bound_to` | **caught** | 11 tests |
| 3b-4 · `_MINT_KEY` becomes a literal that outlives the process | **caught** | `test_the_mint_key_is_generated_per_process_and_not_baked_into_the_module` |

The battery is parametrised over **nine** reconstruction paths — the tampered object itself,
`copy.copy`, `copy.deepcopy`, `pickle` at three protocols, `__reduce_ex__(2)` and `(4)` applied by
hand, and `object.__new__` with a copied `__dict__` — in both directions: tampered sessions must
be refused, untampered rebuilds must still authorise their own credential.

**A process note, because it nearly cost me this section.** My first run of 3b-1..3 reported all
three *passing*, i.e. not caught. The cause was not the tests: `ruff format` had reflowed
`assert_bound_to`'s condition onto one line after I wrote the patch anchors, so `str.replace` found
nothing and the "reintroduced" defect was never actually introduced. The re-run asserts every
anchor before patching. A reintroduction check that silently fails to reintroduce anything is a
green result that means nothing, and it is the same failure mode as a test that asserts an empty
search — I would rather record that I hit it than have it discovered.

### Standing sweep, extended to this shape

`tests/test_standing_cycle_round12.py` now guards **four** couplings. The fourth:
`test_the_seed_session_proof_is_verified_somewhere_other_than_its_constructor` parses
`pinning.py`, finds every method whose body compares a mint proof, and fails if the only one is
`__post_init__`. Shown firing against a planted constructor-only class in the same
`test_the_sweeps_would_actually_catch_a_planted_instance` parametrisation as the other three.

It is scoped to that one module and that one comparison **on purpose**, and I want to be clear
about why rather than overselling it: the general rule — "an invariant established at construction
must be re-established at use" — is not statically sweepable without reporting innocent code. This
codebase has several honestly constructor-only `__post_init__` validators (`ProbeSpec` among them),
and a sweep that flagged them is a sweep that gets switched off, which is round 11's own stated
reason for keeping these narrow. So the sweep guards *this* chokepoint; the nine-path battery is
the evidence that the property holds generally.

### What I could not establish

- The cross-process claim is tested by **replacing the module's key**, not by spawning an
  interpreter. That establishes "given a different key, it fails closed"; a separate source-level
  assertion establishes that the key really is generated per import. Neither is an actual second
  process. This suite runs no subprocesses and I did not add one for a constant.
- Nothing consumes a `SeedSession` yet, so `assert_bound_to` still has no production caller. 3b
  makes holding a session prove nothing on its own, which is the point — but WS-16 must actually
  call it, and no code can force that. It is written in the module docstring and belongs in WS-16's
  review.
- I did not attempt to make the session unpicklable or uncopyable. It is now harmless to copy, and
  blocking it would be the enumeration this fix exists to avoid.
---

## Part 4 — documentation, no behaviour change

**The `errors[]` claim.** `docs/reviews/ROUND_11/HANDOFF.md`'s G6 row said the `errors[]` array is
"the older spelling". Corrected in place, struck through rather than silently rewritten, with
R-GMAIL's finding: Google's own `handle-errors` guide shows a canonical 403 carrying `errors[]`
with **no top-level `status` at all**, and `status` is the spelling with no confirmed
Gmail-specific example. The code's ordering (`errors[].reason` first, `status` as fallback) was
already right; only the reasoning was inverted. It appears nowhere else — I grepped both source
trees and all of `docs/` for it.

**The four still-open shapes are now registered as preflight questions** in AD §F's table, which
is the list a live run works from:

| ID | Shape | Was |
|---|---|---|
| PF-2(b) | metadata `snippet`/`internalDate` (G1) | already registered; the row now names R-GMAIL's re-confirmation and the shipped probe that drives it |
| **PF-17** | the token response's `scope` field (G8) | named in `auth/consent.py` since round 11, registered nowhere |
| **PF-18** | real page-token length against the seal's 256-char bound (G3) | in the handoff's guessed-shape table, in no list |
| **PF-19** | duplicate message ids within one `history.list` page (G7) | same |
| **PF-20** | whether the two "whole mailbox" spellings select the same set | introduced by round 12's own part 1, registered nowhere |

Each row states the check *and the consequence of failure*, which is AD §F's own rule for what
makes a row a preflight question rather than a note. The code sites now carry `[PREFLIGHT PF-18]`
and `[PREFLIGHT PF-19]` markers at the page-token bound and the history dedup; `consent.py` points
PF-17 at the table.

### Reintroduction checks

| Defect put back | Result | Test that failed |
|---|---|---|
| Q · PF-20 dropped from the register while still named in code | **caught** | `test_every_preflight_question_named_in_the_source_is_registered_in_the_architecture` |
| R · PF-18's consequence column emptied | **caught** | `test_the_four_still_open_shapes_each_have_a_registered_consequence` |

### What I could not establish

The `errors[]` correction has **no reintroduction test**. Its only home is a past round's
`HANDOFF.md`, and a test that pins the wording of a review record would be asserting against
`docs/reviews/`, which §9 of the loop treats as records rather than as sources. I corrected it and
am telling you it is unguarded.

---

## Part 5 — R-SEC-042: `assert_record_is_content_free` at any depth

### What I changed (`harness/src/mailweave_harness/preflight/record.py`)

The walk carries the **whole path** instead of a single frozen `key`, and the exemption applies
only where prose actually lives: **one top-level prose key, then nothing but list indices** —
which is exactly the shape `notes` and `pre_registered_rules` are written in. So
`notes.raw_snippet` is not `notes`, and neither is `findings.notes`.

Two things beyond the finding:

- **Dict keys are now checked**, and are never exempt. Nothing checked them at all, so
  `{"<a mail body>": 1}` was written out intact — the same hole one axis over from the reported
  one. A key is a name we or a probe chose; a 400-character multi-line one is mail text whatever
  it sits beside.
- **The refusal never quotes what it refused.** A key can *be* the offending value, and naming it
  would put mail text into an exception message in order to complain that it was about to be put
  into a file. Over-bound segments render as `<key withheld>`.

The exempt names moved to `spec.PROSE_FIELDS`, beside `ProbeResult.as_record()` which produces
them, and `record.py` imports them. A copy in the checker is the R-ARCH-031 shape: it stops
matching the day `as_record` grows a field.
`test_the_exempt_set_is_the_producers_own_list_and_still_matches_it` asserts the two agree.

### Reintroduction checks

| Defect put back | Result | Test that failed |
|---|---|---|
| J · round 11's walk restored (key frozen at the first dict level) | **caught** | `test_no_exempt_key_carries_its_exemption_down_into_a_nested_shape` — all 7 keys — + 4 more |
| K · dict keys unchecked | **caught** | same, + `test_a_key_is_checked_and_is_never_exempt` |
| L · exemption becomes "a prose name anywhere in the path" | **caught** | 14 failures incl. `test_an_exempt_name_used_as_a_nested_key_is_not_exempt` |
| M · the refusal quotes the offending key | **caught** | `test_the_refusal_never_quotes_what_it_refused` + 5 |

The nesting battery is parametrised over **all seven** exempt keys and five burial shapes (dict
directly under, two levels down, inside a list, list-of-dict-of-list, and as a key). R-SEC tested
one key in one shape; six of the seven had never been tested at all.

### What I could not establish

- No fixture here is real or realistic mail. The test string is deliberately synthetic filler that
  is multi-line and over the bound, which is all the check looks at.
- The check still bounds by *shape* (one line, ≤200 characters). A single-line 150-character
  sentence of real mail would pass, exactly as before. That is the documented limit of the
  mechanism and I did not change it.

---

## Part 6 — the orchestrator's addition: `in:anywhere` exercised by nothing

Confirmed before fixing: `unfiltered_query` had two branches, no test referenced either spelling,
and no call site passed `True`. The docstring made a safety claim — the two settings may not
disagree — and nothing enforced it.

### What I changed

New `harness/src/mailweave_harness/preflight/scope.py`: **`MailboxScope`**, an enum whose two
members each carry *both* spellings — `WITHOUT_SPAM_AND_TRASH = ("-in:spam -in:trash", False)` and
`WHOLE_MAILBOX = ("in:anywhere", True)`. `measure.walk_mailbox` is the one place a scope is taken
apart, and both halves leave it in the same call. There is no longer a caller holding two values to
pass to two places, which is what the docstring previously asked callers to get right.

- `sample_mailbox` lost its `query` parameter entirely. It was the escape hatch that let the two
  settings drift, and nothing ever passed it.
- `measure_quota`'s second listing call goes through `walk_mailbox` too — it was the call site a
  fix aimed only at the crash would have missed.
- `measure_threads` takes a `MailboxScope`; `ThreadObservation` records the scope and the record
  now carries both `include_spam_trash` and `listing_query`, so PF-1's "at the same setting"
  claim is a recorded fact rather than an assumption.
- I removed two parameters I had briefly added (`walk_mailbox(rung=…)` and `measure_quota(scope=…)`)
  once I noticed no caller would ever vary them. Adding an unexercised branch two lines below the
  fix for an unexercised branch is not a joke I wanted in the diff.

### How the branch is exercised — not by calling the function with `True`

`test_both_mailbox_scopes_reach_the_wire_as_one_agreeing_pair` is parametrised over **both**
members and drives `measure_threads` through the real `GmailClient`, real URL construction and the
real egress allowlist to an `httpx.MockTransport`, then asserts what the *request* carried. It
asserts the pairing twice: once against the scope, and once **independently** —
`("in:anywhere" in q) is (includeSpamTrash == "true")` — because the first assertion alone would
agree with a table that itself paired the two wrongly.
`test_no_listing_in_a_whole_run_can_send_the_two_settings_out_of_step` applies that independent
statement to every `messages.list` a full `run_probes` makes.

Two AST sweeps make the coupling structural: the `in:` scope operators may appear only in
`scope.py`, and `include_spam_trash=` may only be a scope attribute (or a pure forward of a
parameter of the same name, which is what the Gmail client does internally) — never a literal, and
never without `query=<the same scope>.query` beside it.

### Reintroduction checks

| Defect put back | Result | Test that failed |
|---|---|---|
| N · the pair split at the call site (`include_spam_trash=False` beside `scope.query`) | **caught** | `test_both_mailbox_scopes_reach_the_wire_as_one_agreeing_pair[whole_mailbox]`, `test_the_two_scope_settings_cannot_be_supplied_independently` |
| O · `WHOLE_MAILBOX` paired with `False` in the table itself | **caught** | same wire test (via the independent assertion), `test_both_scopes_declare_both_spellings_and_they_do_not_collide` |
| P · a probe spells `in:anywhere` itself | **caught** | `test_no_module_spells_a_mailbox_scope_operator_outside_the_scope_enum`, `…_cannot_be_supplied_independently` |

### What I could not establish

- **No production call site passes `WHOLE_MAILBOX` today.** It is exercised end to end through
  `measure_threads` at the wire, which is a real measurement function and not a unit call on the
  enum, but the runner still walks the default scope. I did not add a CLI flag: that changes what
  the owner's first live run measures, and it is not mine to decide.
- **An observation for whoever does decide.** PF-1 compares `messages.list` against `threads.get`.
  At `WITHOUT_SPAM_AND_TRASH` the listing arm excludes spam replies while `threads.get` returns
  them, so `threads.get` returns *more* — which PF-1 already handles as a coverage note rather
  than a failure. The apples-to-apples arm is arguably `WHOLE_MAILBOX`. I did not change it; the
  probe's semantics are a design question, not a defect, and PF-20 is now registered to settle the
  underlying fact first.
- `_freshness_run`'s id-exact `rfc822msgid:` search carries neither spelling. That is agreement —
  both settings then mean the default mailbox — so the sweeps pass it. Whether a message delivered
  to spam is findable by that search is a real measurement question and is what PF-20 asks.

---

## The work order's standing check, answered

> *Confirm your changes do not introduce a fourth shape that the sweep does not cover, and say so.*

**Not confirmed as "no new shapes" — I introduced four, and all four are now swept. One of them
I did not find myself: the orchestrator did, in this round's own fix.**
`tests/test_standing_cycle_round12.py` adds them beside round 11's three, in the same style, each
shown firing against a planted instance:

1. **A model that declares a `SecretStr` must inherit `SecretBearingModel`.** By reflection over
   both trees, so a model added in a later round is covered the day it exists.
2. **A caught `ValidationError` may only be chained, counted, or passed to `failure_summary`.**
   This one *found a real peer while I was writing it*: `content/payload.py` was still rendering
   `errors()[0]["msg"]` — the peer I had decided to leave alone. I fixed it rather than narrowing
   the sweep.
3. **The two mailbox-scope settings cannot be supplied independently** (two sweeps: the operator
   literals, and the argument pairing).
4. **A mint proof must be verified somewhere a use site reaches, not only in the constructor**
   (Part 3b). This is the one I got wrong: I defended `dataclasses.replace` and trusted
   `__reduce_ex__` / `__copy__` / `__deepcopy__`, which is the pattern itself, committed inside
   the fix for the previous instance of it. The count of appearances of this defect in the project
   is therefore **eight**, not seven, and one of them is mine.

Three more duplications I introduced and then removed, before a reviewer had to find them:

- `validation._nested_models` and the canary's `_mentions_secret` were two recursive annotation
  walkers answering different questions. Now one exported `annotation_parts`, used by both.
- `test_standing_cycle_round11.py` and `…round12.py` each had a `python_files()` walker. Now one
  `tests/fixtures/source_trees.source_files`, imported by both — two copies of a file walker in
  the pair of files whose subject is second copies would have been its own finding.
- `record._OUR_PROSE` duplicated the key names `ProbeResult.as_record()` produces. Now
  `spec.PROSE_FIELDS`, with a test that the two still agree.

**What the sweeps do not cover, stated plainly.** They cover the three idioms round 11 named and
the four couplings above. They are not a duplication detector and are not claimed to be one. Two
specific gaps I know of: the sweeps read the two `src` trees and not `tests/`, and sweep 2 reasons
about a single `except` handler, so a handler that stashes the failure in an attribute and renders
it elsewhere would not be seen.

---

## Things I did not do

- I did not touch `gmail/retry.py` or `rates.py`. The backoff curve is the owner's decision.
- I did not build amendment A1.
- I did not mark any rubric criterion, and added no rows to `FINDINGS_LEDGER.md` or
  `RUBRIC_TRANSITIONS.md`. `rubric_status.py --check` is unchanged: 7 PASS / 0 FAIL / 0 BLOCKER /
  106 NOT TESTED, 11 transitions.
- I did not update `RESUME.md`. Round status is the orchestrator's to write.
- R-SEC-044 (the egress allowlist not checking the port) is not in this work order and I left it
  alone.

---

## Final verification, verbatim

```
=== ruff check ===
All checks passed!

=== ruff format --check ===
131 files already formatted

=== mypy --strict ===
Success: no issues found in 105 source files

=== python -m tools.guards ===
guards clean: forbidden-import, generative-client, gmail-endpoint, ground-truth-isolation, scope-literal, unaudited-disk-write, unwrapped-http-client over server/src

=== pytest -q -m 'not network' ===
........................................................................ [ 91%]
........................................................................ [ 95%]
......................................................................   [100%]

(the build prints no summary line; recounted with --collect-only)
1726 tests collected

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

**Reintroduction battery:** 23 defects reintroduced one at a time against the final tree,
**23 caught, 0 missed**. Every patch anchor is asserted before it is applied, after an earlier run
of Part 3b's cases silently patched nothing and reported three false greens — that episode is
written up under Part 3b rather than quietly re-run. Each case restores its file from a snapshot
afterwards, and every file was byte-compared against that snapshot at the end
(`ALL FILES MATCH THE INTENDED FINAL STATE`).

I did not verify my own work in the sense that matters. R-SEC should re-run the battery with its
own defects rather than mine.
