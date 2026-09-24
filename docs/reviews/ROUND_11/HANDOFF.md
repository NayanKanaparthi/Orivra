# ROUND 11 — implementer handoff: the Gmail client, OAuth, and the preflight harness

**Implementer, 2026-09-01.** Work order: `docs/reviews/ROUND_11/WORK_ORDER.md`.
Gating reviewers: `R-GMAIL`, `R-SEC`, `R-ARCH`.

**State of the gates:** `make check` green — ruff, `ruff format --check`, `mypy --strict`
(99 source files), 1,646 tests, all seven source guards clean, rubric status unchanged at
**7 PASS / 0 FAIL / 0 BLOCKER / 106 NOT TESTED**. No rubric criterion was marked, and no row
was added to `RUBRIC_TRANSITIONS.md` or `FINDINGS_LEDGER.md`. Test count 1,529 → 1,646.

---

## 1. What was built

### Part 1 — the Gmail client (`server/src/mailweave/gmail/`)

| Module | What is in it |
|---|---|
| `rates.py` | The five endpoints implemented, the published quota rates, their provenance, and the calibration sentence that travels with every unit figure |
| `models.py` | Hand-written Pydantic models for the four responses plus `getProfile`, and `parse_response`, the only supported way to turn a Gmail body into a model |
| `faults.py` | Six typed faults, each carrying its D.11 `ErrorCode`; one base class, `GmailFault` |
| `retry.py` | `BackoffPolicy` and `BackoffState`: A.5a's figures as data, with `sleep` and jitter injected |
| `meter.py` | `http_requests` / `api_calls` / `quota_units` as three separate increments (A.5b) |
| `client.py` | `GmailClient` — the transport, the pager, the seam wiring, and the public surface |

**The seam holds, and holds by construction.** `RecordingListTransport` is untouched. A
transport is built *per call*, inside the client, with the call's options bound onto the
fetcher by `functools.partial` — widening the seam's signature to carry `includeSpamTrash`,
`metadataHeaders` or the rung's remaining clock would have been working around it. Each
builder supplies only the fetcher its call uses, so reaching for the wrong one raises the
seam's own error rather than a `TypeError` about a keyword.

The three obligations the seam's docstring places on this client:

- **no method returns a bare id collection.** `list_messages` → counts and a continuation
  token. `history_additions` → counts. `get_thread` returns the thread's content, but it
  cannot be obtained except from a call that has already recorded every row into the ledger —
  there is no ordering in which a caller reads those ids before `H` has grown. Checked by
  reflection over every public method's return annotation, not by reading.
- **the raw fetchers are private and the transport is the client's to construct.**
- **listing fetchers carry `threadId` per id**, so an observed id can be withheld
  (R-DISC-009). `threads.get` observations additionally seal `stated_total`, `positions`,
  `internal_dates` and `history_id` (amendment A6).

**`messages.get` is deliberately not a sealed observation**, and the reasoning is in the code
rather than left to be rediscovered: `ObservedEndpoint` has three members and adding a fourth
is amendment A2, not a refactor. A `messages.get` response names exactly one message — the one
the caller asked for — so it cannot put an id into `H` that was not already there. What it
*can* do is answer with a **different** id, and nothing downstream re-checks that, so the
client does and refuses. `get_profile` returns an address and three counts and no id at all.

**Gated requirements, each with the test that holds it:**

| Requirement | Where |
|---|---|
| Every id-yielding response flows through a sealed observation with its `ObservedEndpoint` | `test_a_thread_is_recorded_into_H_before_its_content_is_reachable`, `test_history_additions_enter_H_under_the_history_clause_and_deduplicate` |
| Retry / backoff / rate-limit, quota units counted per call | `test_the_delay_sequence_is_exactly_the_architecture_s` (asserts 312.5 ms, 625.0 ms exactly), `test_every_attempt_is_charged_including_the_one_that_429d` |
| Pagination explicit, including the page budget | `test_the_page_budget_stops_the_walk_and_the_residue_is_declared`, `test_the_page_size_is_sent_explicitly_and_is_what_scan_scope_reports` |
| Typed errors, no bare exception crossing the layer | `test_every_failure_path_raises_a_gmail_fault`, `test_a_transport_error_arrives_as_a_gmail_fault_not_as_an_httpx_one` |
| Egress allowlist on every call | `test_every_call_goes_to_the_allowlisted_host_over_https`, `test_a_mock_transport_is_still_behind_the_allowlist` |
| No mail text in any log, trace or error | `test_no_part_of_a_gmail_error_body_reaches_a_mailweave_error_string` |

Four decisions inside that table are worth a reviewer's attention:

1. **Gmail's `error.message` is discarded, always.** It is free text the remote side chose and
   on a `messages.list` failure it echoes the `q` that failed — which A.11's default profile
   stores as features plus a salted hash, never raw. What a fault carries is the endpoint, the
   status, the attempt count and a `reason` **slug** admitted only if it matches an anchored
   ASCII identifier pattern. The test plants a body whose `message` contains an address and
   the sentence *"the NDA we discussed on Tuesday"* and asserts none of it survives.
2. **A 403 with a quota `reason` is a rate limit, not an auth failure.** Gmail has historically
   answered per-user rate limiting with 403 rather than 429; reading that as auth would send
   the owner to re-consent for a condition a 300 ms sleep fixes. Which one a real mailbox
   emits is PF-3's to record, and PF-3 records the raw `(status, reason)` pairs so the set can
   be corrected from data.
3. **`max_retries = 3` is not reachable at the top of the jitter band.** 250 + 500 = 750 ms
   leaves 750 ms of the 1,500 ms total and the third delay is 1,000 ms before jitter, so the
   client makes **two** retries under unfavourable jitter and three under favourable. That is
   A.5a's own arithmetic — two bounds, the tighter one fires — and it is asserted so nobody
   later reads `max_retries = 3` as a promise of three.
4. **A listing run requires its widening affordance before the first HTTP call.**
   `ScanScopeEntry` refuses `more_pages: true` without one, but it refuses at *record* time,
   after `_admit` has already put the page's ids into `H` — which would leave ids in `H` with
   no scan-scope entry describing how they arrived. A caller cannot know in advance whether
   Gmail will send a continuation token, so the only safe place is the signature.

**Not built, and stated in "what I did not do":** the batcher, the quota governor, and any
async client.

### Part 2 — OAuth up to the consent boundary (`server/src/mailweave/auth/consent.py`)

- `read_installed_client` — reads the Desktop-app client JSON, refuses a `web` client and an
  over-permissive file.
- `exchange_code` / `refresh_access_token` — the token endpoint, through the allowlist, with
  `check_url` called on the composed URL as well.
- **`verify_granted_scopes`** — reads back what Google actually granted and refuses any
  difference **in either direction**. A narrower grant cannot serve; a wider one is capability
  nobody asked for. A response carrying no `scope` field at first consent **fails closed**
  (`ScopeUnverifiable`): "we requested readonly, therefore we hold readonly" is precisely the
  assumption this check removes. On a *refresh* an omitted `scope` means unchanged rather than
  unknown, because there is a previously verified grant to fall back on — the two call sites
  are not interchangeable and the difference is written where it is.
- `LoopbackReceiver` — one-shot `127.0.0.1` listener, ephemeral port, silenced logger (the
  request line contains the authorization code), ignores the browser's `/favicon.ico`.
- `run_login` — the flow, with the interactive step as a **parameter**. That is what makes
  every check reachable in tests with no browser and no socket, and it is why nothing in this
  module can start a consent by itself.
- `StoredTokenProvider` — refresh-token-backed `TokenProvider` for the CLI and the probes.
- **The redaction profile in the report is derived, not asserted.** It calls `derive_profile`
  with the salt and configuration at hand. Writing `Profile.PERSONAL` would have been correct
  in every case this command can currently produce and would still have been the project's own
  recurring defect.

**Account pinning** is in `harness/src/mailweave_harness/pinning.py`, because the server may
not name the destructive scope. Three controls, and the module says plainly that only one of
them is code:

1. **Google-side, the real one.** The harness client sits in a Testing-status project whose
   test-user allowlist holds only the seed account, so the personal mailbox *cannot hold a
   token for the harness client at all* (ADV-205). Not a check that can be skipped — a grant
   that cannot be issued.
2. **Process-side.** `verify_seed_account` calls `getProfile`, compares, and returns a
   `SeedSession` — not a boolean. Destructive operations take the session as a parameter, so a
   caller cannot invoke one without holding the object only a successful comparison produces.
   A `getProfile` that *fails* is not a pass: an unobservable address cannot be compared.
3. **Import-side.** `server/**` cannot import the harness; the CI guard is re-asserted from
   the pinning test file itself.

**Secret hygiene.** `test_no_secret_survives_into_a_traceback_on_any_failing_step` forces all
five failure modes of the flow and searches the **formatted traceback** — not just the
exception message — for the client secret, the authorization code, the access token and the
refresh token. Exception formatting renders locals through `__repr__`, which is why every
secret is a `SecretStr` and every dataclass that could hold one carries an explicit `__repr__`.

**`.gitignore`.** The work order says both client files are gitignored. In this working copy
they were not: the file held only build artefacts. The credential patterns from
`SECURITY_NOTES.md` §3.3 are now there, both client filenames explicitly. Note that **this
working copy is not a git repository** (RESUME.md's "extract the tarball and commit" step is
still outstanding), so I could not verify with `git check-ignore`, and the two files are still
in history at `0162e79` / `948bd2a` — the owner's open decision.

### Part 3 — the preflight harness (`harness/src/mailweave_harness/preflight/`)

Six probes, each split into a `measure` half that needs a mailbox and a **pure `analyse`
half** that does not. The judgement is therefore unit-tested with no network, and the live
phase is execution.

`python -m mailweave_harness.preflight --plan` prints every probe's falsification condition,
its consequence and its budget, and needs no credential. `--run` needs the owner's machine.

---

## 2. Response shapes I had to guess — as preflight questions, not facts

Everything in `tests/fixtures/gmail_shapes.py` carries one of two markers. `[DISCOVERY]` means
the shape is from the Gmail API v1 discovery document and the matching reference page.
`[PREFLIGHT]` means the *presence* of a field depends on something no document settles.

| # | The guess | Why it is a guess | What it would break |
|---|---|---|---|
| G1 | `threads.get(format=metadata)` returns a per-message `snippet` and `internalDate` | **Registered as PF-2(b)** (AD §F), and driven by the shipped `PF-2-metadata-headers` probe. The Format enum's own text says METADATA returns "only email message ID, labels, and email headers" and mentions neither; AD D.5's pool design assumes both. R-GMAIL re-confirmed the contradiction verbatim against the live discovery document. **The two contradict each other.** Both shapes are fixtured (`THREAD_METADATA`, `THREAD_METADATA_NO_INTERNAL_DATE`) and both are tested | PF-2. The client already refuses to invent positions when `internalDate` is missing, so this degrades a thread map rather than corrupting one |
| G2 | `metadataHeaders` honours `References` and `In-Reply-To` | Documented as a filter; not documented as honouring any particular header | PF-2. The reply tree loses its links |
| G3 | A Gmail continuation token fits in 256 single-line characters | The seal bounds it there and the token is documented as opaque with **no shape at all**. R-GMAIL confirmed against the live discovery document (`gmail:v1`, rev `20260727`) that `nextPageToken` is a bare `"type": "string"` with no format and no length on every listing endpoint. If a real token is longer, `_sealed_page_token` refuses it and pagination breaks. **Registered as PF-18** (AD §F) | Nothing until the first real listing; this is the shape I am least sure of |
| G4 | A per-user rate limit arrives as 429, or as 403 with `rateLimitExceeded` / `userRateLimitExceeded` / `quotaExceeded` / `dailyLimitExceeded` | Documented historically; not currently pinned by Google's own reference | Both are handled; PF-3 records the raw pairs so the set can be corrected |
| G5 | Gmail sends `Retry-After` on a 429, in the seconds form | Not documented for the Gmail API. Handled if present (it raises the delay and never lowers it), ignored if absent | Nothing; the exponential schedule is the fallback |
| G6 | The Google JSON error envelope is `error{code, message, errors[{domain, reason, message}], status}` | ~~The `errors[]` array is the older spelling; newer responses may carry only `status`.~~ **Corrected in round 12 (R-GMAIL, round 11): that framing is backwards for Gmail specifically.** Google's own `handle-errors` guide shows a canonical 403 carrying `errors[]` with **no top-level `status` at all**; `status` is the spelling with no confirmed Gmail-specific example. Both are read, `errors[].reason` first — so the code's ordering was already right and only this reasoning was inverted | A missing `reason` degrades a rate limit to an unknown-reason rate limit, never to an auth failure |
| G7 | `history.list` can report the same message id twice in one page | Not documented either way, confirmed by R-GMAIL against the discovery document. The client deduplicates, because the seal takes a per-id map and a repeated key is not a second message. **Registered as PF-19** (AD §F) | If Gmail never does it, the dedup is inert |
| G8 | Google's **token** response carries `scope` on an installed-app grant | **Registered as PF-17** (AD §F). Documented for the token endpoint generally; not pinned for this flow specifically. R-GMAIL: RFC 6749 §4.2.2 makes `scope` OPTIONAL exactly when the granted scope matches the requested one, which is this project's first-consent case. **If it is routinely absent, `auth login` fails closed and the owner cannot log in.** The fix is a second read-back at `oauth2.googleapis.com/tokeninfo` (already on the allowlist), *not* relaxing the check | This is the guess most likely to bite on the very first real run |
| G9 | A Desktop-app client JSON uses the `installed` key | Standard console output; a `web` client is refused with a message naming the difference | The command names the file and the flag |

**The two client files do not exist in this environment**, so none of the above could be
checked against a real download. `mailweave-server-oauth.json` and
`mailweave-harness-oauth.json` are absent from `/root/mailweave` and from `~`.

---

## 3. The consent command, and what it prints

```
uv run mailweave auth login --client mailweave-server-oauth.json
```

Optional: `--state-dir`, `--expect-account you@example.com` (abort unless the consented
mailbox is that one), and `--dry-run`, which sends nothing and binds nothing.

**No browser is opened.** The command prints the URL and waits. Opening a browser is starting
a consent, and consent is the owner's to start.

`--dry-run` prints, verbatim:

```
client:            <id> (mailweave-server-oauth.json)
requested scopes:  https://www.googleapis.com/auth/gmail.readonly
token store:       ~/.local/state/mailweave/credentials.json

dry run: nothing was sent and no listener was bound. On a real run:
  1. a one-shot listener binds 127.0.0.1 on an ephemeral port
  2. this command prints a URL; you open it and consent
  3. the code is exchanged at oauth2.googleapis.com with PKCE S256
  4. the GRANTED scope set is read back and compared to the request;
     any difference in either direction aborts before anything is stored
  5. users.getProfile names the account; it is printed for you to check
  6. the refresh token is written 0600 inside a 0700 directory
```

A real run then prints the URL, waits, and on success prints exactly this (rendered from the
shipped code path, with the owner's values substituted):

```
client:            8675309-abcdefg.apps.googleusercontent.com (mailweave-server-oauth.json)
requested scopes:  https://www.googleapis.com/auth/gmail.readonly
GRANTED scopes:    https://www.googleapis.com/auth/gmail.readonly
scope check:       OK - Google granted exactly what was requested
account:           you@example.com
redaction profile: personal
token store:       /home/you/.local/state/mailweave/credentials.json (0600, in a 0700 directory)
refresh token:     stored
obtained at:       2026-09-01T00:16:34.236172+00:00
```

The `GRANTED` line is read back from Google's token response, not echoed from the request.
On any mismatch the command prints `auth login: FAILED - …` naming `missing=` and
`unexpected=`, followed by `nothing was stored.`, and exits 1.

The refresh token is never printed. Nothing is written before the scope check and the account
observation have both passed.

---

## 4. The probes, and what falsifies each

| Probe | Falsified when | What changes |
|---|---|---|
| **PF-3-quota-units** | the inferred per-call costs are not in the published rank order (`history.list < messages.list < messages.get < threads.get`), **or** any endpoint's inferred cost differs from its published figure by a factor of two or more | A.5c's own consequence table executes: `max_hit_threads` 12→6, `max_source_threads` 4→2, `max_pool_threads` 25→12, `max_quota_units` halved and **re-derived**, the reduced pool bound declared in every semantic response, and the governor's budget re-set. Every published quota number then carries this run's calibration date |
| **PF-2-metadata-headers** | a header requested via `metadataHeaders` is absent from the metadata arm while the `format=full` arm shows the message carries it; or the metadata arm loses a `snippet` or an `internalDate` the full arm gives | AD F PF-2's branch table. The `format=full` arm is what makes this meaningful — without it, a missing header is indistinguishable from a message that never had one, and the probe would be measuring the mailbox's threading habits |
| **PF-1-thread-completeness** | for any thread, `threads.get` returned strictly fewer rows than `messages.list` attributed to that thread **at the same `includeSpamTrash` setting** | Baseline B is labelled lossy, every comparison against it is re-interpreted, PART-01's manifest-equality bar escalates to the owner (AD H-2), and `stated_total` is re-described as "the rows this response returned" — which is what the ledger already seals, so the code does not change, the claims do |
| **PF-thread-size-ceiling** | at least three sampled threads sit at exactly the maximum observed size and none exceeds it | A.9a's and OD-3's disclosure arithmetic is re-derived against the real ceiling, the corpus's 100-message thread shape becomes unbuildable, and a thread at the cap is known to continue in a *sibling* thread — which the reply-chain floor must then reach across, a structural change to WS-05 |
| **PF-freshness-raw** | a message observed through `history.list` is still not returned by an **id-exact** `rfc822msgid:` search at the end of the window | The LR rung's client-side re-check stops being a bridge over a delay and becomes the only path to those messages, so D.9's closed re-check subset has to widen — and FRESH-02 fires regardless of any percentile |
| **PF-cf-strip-damage** | any message using Arabic, Syriac, an Indic script, Kaithi, Thaana or Egyptian Hieroglyphs has a shaping-or-semantic format character removed (U+200C, U+200D, U+061C, U+0600–0605, U+06DD, U+070F, U+08E2, U+110BD, U+110CD, U+13430–1343F) | A7's rule extends from spans to characters: the pipeline **annotates** format characters instead of removing them, so the default view hides them and any wider view returns the text exactly. One instance is a failure — there is no rate here, because the question is whether the operation *can* destroy legitimate content |

**Every one of these is exercised failing.** `tests/test_preflight_probes.py` constructs, for
each probe, the observation that falsifies it and the observation that does not, and asserts
both verdicts — including PF-3 against the "~4× tighter reality" A.5c names, and PF-1 against
issue #239's exact shape (`threads.get` 100 rows, listing 137).

**Three things the probes refuse to do:**

- **No freshness claim.** `PF-freshness-raw` computes no percentile and its non-failing verdict
  is `OBSERVATION_ONLY`. A test asserts the findings carry no key from
  `{p50, p90, p95, median, mean, service_level, meets_od1, sla}`. OD-1's number is PF-10's to
  evaluate, stratified, against a pre-registered figure; this sample is unstratified and
  opportunistic and says so in its own notes.
- **No mail text in a record (OD-4).** `assert_record_is_content_free` walks every record
  before it is written and refuses any string that is multi-line, over 200 characters, or not
  on the narrow allowlist of the probe's *own* prose. Ids are salted digests. This is the same
  shape as amendment A6's sealed-scalar bound and for the same reason: checkable, not promised.
- **`INCONCLUSIVE` is never a pass.** A quota run that never reached a refusal, a Cf sample
  containing no at-risk script, a freshness window in which no mail arrived — each reports
  inconclusive and says what was left unvalidated. "A mailbox with no Arabic mail cannot answer
  whether stripping damages Arabic mail, and reporting that as a pass would be the sample
  answering a question it never saw."

PF-16 is enforced rather than documented: `run_probes` refuses to run PF-3 without
`--exclusive-window`, and the refusal says that nothing in the code can verify the
declaration.

---

## 5. The standing-cycle check — **it found two, both in this round's diff**

The check: *"one shape validated, peers trusted" has appeared six times, including inside
Round 10's own diff. Check every new validator in this round against it, and report the check
whether or not it finds anything.*

Every new validator in this round was checked against every existing validator of the same
shape: the models' numeric-id and length checks, the fault `reason` slug, `Retry-After` and
error-envelope parsing, the thread-scalar derivation, the two id-substitution refusals, the
granted-scope comparison, the client-file reader, the record content guard, the seed-account
comparison, and `ProbeSpec`'s own required-field check. **Two were instances of the cycle. Both are fixed by single-sourcing, and both are now
guarded by a mechanical sweep rather than by care.**

**Instance 7 — the one-line predicate, a fourth time.** `preflight/record.py` needed
`value.splitlines() == [value]` to refuse a multi-line string in a probe record. That predicate
already existed **twice**: `disposition._is_one_line` and `reasons._one_line`, the second being
R-ARCH-031, found by R-ARCH inside the round that diagnosed the pattern for the fifth time. The
harness cannot reach either — they are private helpers of `envelope/` — so a fourth hand-written
copy was the path of least resistance and I took it on the first pass. Fixed: the implementation
is now `constants.is_one_line`, in the module all four layers already import for
`GMAIL_NUMERIC_ID_RE`, and `disposition`, `reasons` and `record` all delegate to it. **This
closes R-ARCH-031**, which Round 10 carried as LOW.

**Instance 8 — one remote-API shape, two spellings.** `gmail/faults.py` checks Google's
`error.errors[].reason` against an anchored ASCII identifier pattern. `auth/consent.py`
checked the OAuth `error` code with `str.isidentifier()`. Same class of value — a
closed-vocabulary slug from a remote system — two different predicates, and the second one
accepts every Unicode identifier, including Arabic and CJK, none of which Google emits. Fixed:
`constants.clean_slug` / `REMOTE_SLUG_RE`, used by both.

**Near-misses examined and deliberately left distinct**, so a reviewer can disagree with the
call rather than discover it:

- `consent.verify_granted_scopes` vs `clients.ClientDescriptor.__post_init__`. Both compare
  scope sets. They are not the same check: one validates a *configured* set against
  `SERVER_SCOPES`, the other compares a *granted* set against whatever was requested, which
  for the harness would be the seeder scope. Merging them would push the destructive scope
  into a shared code path.
- `record.MAX_RECORD_STRING` (200) vs `disposition.MAX_SEALED_SCALAR_CHARS` (64). Same idea,
  deliberately different numbers, different purposes: one bounds a field on the disclosed
  wire, the other bounds a value in a local diagnostic file that legitimately holds a code
  point list. Sharing the constant would make one of the two wrong.
- `gmail/models.GmailId` and `GmailPageToken` **do** import `MAX_SEALED_ID_CHARS` and
  `MAX_SEALED_PAGE_TOKEN_CHARS` from the seal rather than restating them, so an over-long id
  is refused once, at the parse edge, as a transport error — instead of parsing here and then
  raising a `DispositionInvariantError`, an *internal* error class, because a remote system
  sent something unexpected.

**The check is now a test, not a habit.** `tests/test_standing_cycle_round11.py` sweeps both
source trees with `ast` for a second implementation of each of the three shapes that have
actually recurred (the one-line predicate, the slug check, the Gmail numeric id), and a fourth
test plants each idiom in a scratch file to prove the sweeps are reporting an empty result
rather than an empty search. The id-pattern sweep is deliberately narrow: its first version
matched `\d{1,2}` inside the quote stripper's calendar-date pattern, which is innocent code,
and a guard that reports innocent code is a guard that gets switched off.

**And one more, in the same family but not the same shape.** `run_login` originally reported
`profile=Profile.PERSONAL` as a literal. It would have been correct in every case this command
can currently produce, and it was still the project's central defect in miniature: a report
stating a value the code decided rather than one it computed. It now calls `derive_profile`,
and both branches — no seed configuration, and the AD A.4 config-forgery attempt — are tested
through the command.

---

## 6. What I did not do, and why

| Not built | Why |
|---|---|
| **The batcher** (A.5a, ≤50 sub-requests) | Not in the work order's gated list. A batch of *n* costs *n* quota units and changes `http_requests` only; `CallMeter.record_attempt(sub_requests=n)` exists so the counters stay separable when it lands. Building it now would add an untested code path with no caller |
| **The quota governor** (A.5c token bucket, `floor_reserve`, concurrency) | It is the ladder's policy, and putting the refusal inside the transport is where no reviewer of the ladder would look for it. `CallMeter` is a meter and refuses nothing, by design |
| **`users.labels.list`** | On A.5's surface, but nothing consumes labels until the LR rung's client-side `label:` re-check (WS-12). An endpoint with no caller is an endpoint whose response shape nobody has checked against reality. It stays in `constants.GMAIL_ENDPOINTS` — the CI sweep's allowlist is the architecture's surface, not this round's |
| **An async client** | The seam is synchronous, so the client is. A.5c's single event loop is WS-15's concern, and `net.build_async_client` already exists for it |
| **Retrieval rungs, ranking, escalation policy, the MCP surface** | Explicitly excluded |
| **A1's counting proxy** | Explicitly not mine. Nothing here claims to bound `H` from above |
| **A7 / disclosure integration** | Not this round; `envelope/` still references no `AnnotatedBody` |
| **Running any probe** | No credential exists in this environment, and none should |

---

## 7. Where this work is weakest

Ordered by how much I would want a reviewer to push.

1. **Every response shape is unverified against reality.** The fixtures are read off a
   discovery document by a process that has never seen a Gmail response. §2 lists nine
   guesses; G8 (does the token response carry `scope`?) is load-bearing for the very first
   real run, because if it is absent the flow fails closed and the owner cannot log in. That
   is the correct failure direction and it is still a failure the owner meets first.
2. **The PF-3 inference is the weakest measurement in the round.** Dividing a published
   per-minute budget by observed calls assumes one bucket, one project, and an exclusive
   window, and it infers a *cost* from a *refusal*. The rank-order clause is the primary
   falsifier precisely because it survives all three assumptions being approximately true —
   but if Gmail's refusal is not budget-driven at all, the probe measures something else and
   reports it confidently. It should be reviewed as an inference, not as a measurement.
3. **PF-1 without a seeded manifest.** Grouping `messages.list` rows by `threadId` is a real
   independent cross-check, and it is weaker than the seeder's manifest: both endpoints could
   truncate the same thread the same way and agree. It cannot produce a false FAIL, which is
   the direction that matters, but a PASS here is worth less than a PASS after WS-16.
4. **`RecordedThread` returns message ids.** I argue this is not a hole because the rows are in
   `H` before the object exists, and I believe that argument. It is still the only place in the
   client where a caller holds ids in a structure it could iterate, and it deserves a reviewer
   who does not accept my reasoning on my word.
5. **The loopback consent path is the least-tested code in the round.** Every check *around*
   it is exercised — state, scopes, account, storage, secret hygiene — but the listener itself
   is covered only by a bind test and a handler-contract test. The browser round trip, the
   `/favicon.ico` interleaving and the timeout have never run. They will first run on the
   owner's machine.
6. **`StoredTokenProvider` refreshes exactly once and never re-refreshes.** Fine for a CLI
   command and for a probe run; wrong for a long-lived server, which needs an expiry check and
   a single-flight guard. It is documented as such rather than half-built, but a probe run
   longer than an access token's life will fail with an auth error, not a refresh.
7. **The Cf probe's script detection is a heuristic** — the first word of `unicodedata.name`.
   It is right for the blocks that matter and it will silently ignore a script Unicode names
   differently. It bounds what a PASS means and does not bound what a FAIL means, which is the
   safe way round, but it is a heuristic in a probe whose whole job is to be trustworthy about
   damage.
8. **`_pending_thread` / `_pending_history` are mutable one-shot slots on the client.** They
   exist because the seam's fetcher contract is `FetchedIds` and nothing else, so a parsed
   response cannot come back through it. They are single-threaded-safe and the client is
   documented as such — but they are state, and state on a transport is where concurrency bugs
   live when WS-15 makes this async.
