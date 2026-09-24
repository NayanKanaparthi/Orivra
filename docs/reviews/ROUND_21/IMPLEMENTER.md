# ROUND 21 — WS-06: handles and staleness, and the four things L4 said that were not true

**Implementer report.** Protocol `docs/AGENT_LOOP.md` §5, under **OD-6**'s build order and its
counter-rule. Gating reviewer: **R-RETR**.

**Result in one line.** A `map_id` now proves the named threads have not changed — by an
independent `history.list` walk over all four change types, not by re-reading its own cache —
or says which of the five ways it could not; the warm path is labelled `cache_tautology` so it
cannot borrow the cold path's guarantee; `fetched_at` is never restamped; and every over-claim
R-RETR filed one level out from the reply tree is closed, with the participant index kept out
of `mapping_digest` for a reason this round executes rather than asserts.

**Gates.** ruff, `ruff format --check`, `mypy --strict`, `python -m tools.guards`,
`pytest -q -m "not network"` **2,439 collected, all passing** (was 2,369). Rubric unchanged:
**6 PASS / 0 FAIL / 0 BLOCKER / 107 NOT TESTED**, 11 transitions. Full output at the end.

---

## 0. What I read first, and what I ran before changing anything

The work order's framing is that Part 0 comes before Part 1 because the handles sit directly on
top of the claims Part 0 repairs. I took that literally and ran R-RETR's own reproductions
against the unmodified tree first, so that every fix below starts from a defect I had seen
rather than from a description of one:

| Probe | Reproduced, unmodified tree |
|---|---|
| `/tmp/rretr20/p2_l4_evidence.py` | `t-root/r1 role parent reason: reply parent of c1` — three hops up; `<par@x.invalid>` never probed |
| `/tmp/rretr20/p11_caps_disposition.py` | `t-sib-1x s1x -> reply parent of c1` **and** `t-sib-1y s1y -> reply parent of c1` |
| `/tmp/rretr20/p9_quoted_mention.py` | quoted `cai@team.example` absent from participants; `mentions_not_scanned: ()` |
| `/tmp/rretr20/p22_depth_dependence.py` | one thread, two queries, two different participant indexes |
| `/tmp/rretr20/p23c.py` | `cai@team.exampl` on the wire — an address in no message of the mailbox |
| `/tmp/rretr20/p17_d4a.py` | `d2` vs `d3` — `distinguishable on the wire: False` |
| `/tmp/rretr20/p13_skipped.py` | no L4 `not_tried` entry of any kind for a declined identifier |
| `/tmp/rretr20/p6_ordering.py` | `'01000'`/`'1000'`: ordering treated them as a tie, `declared tied: ()` |

I did not read `/tmp/rretr15` … `/tmp/rretr19`, and nothing in my fixtures is taken from any of
them: my corpus, vocabulary (`quillevant`, `sprindle`), mailbox shapes and oracles are written
here. Running a reviewer's reproduction to confirm a defect is not tuning against the probe
set; **no test below asserts anything about a `/tmp/rretr20` fixture**, and the two new test
files stand on `tests/fixtures/mailbox.py` like every other end-to-end test in the suite.

---

# Part 0 — the carry-over

## 0.1 R-RETR-049 — L4 chased the thread root and disclosed it as the reply parent

**Changed.** `structure/reply_tree.py`, `reconstruct`: the id an unresolved child records is now

```python
nearest = view.in_reply_to[0] if view.in_reply_to else view.references[-1]
```

which is the module's own right-to-left rule (RFC 5322 §3.6.4) applied to the gap branch as it
already was to the resolution branch one line above. `Link.evidence`'s docstring said *"the one
it was looked for under when there is no parent"* and held `(in_reply_to + references)[0]` —
the leftmost reference, which is the *last* id `_resolve` would have tried. The docstring is
rewritten to say which id the field holds and why the old wording was wider than the code.

**What the tests establish.**
`test_the_id_an_unlinked_child_records_is_the_nearest_ancestor_its_headers_name` pins the field
at the unit for both header shapes (`References`-only, and `In-Reply-To` present alongside).
`test_l4_probes_for_the_parent_and_not_for_the_thread_root` drives the whole ladder over a
mailbox holding the root, a middle ancestor and the real parent in three separate threads, and
asserts the probe list is exactly `['rfc822msgid:<near@mail.invalid>']`, that `t-root` and
`t-middle` are not disclosed at all, and that the recovered row carries
`ReplyParentOf(child_id="c1")` — the relation the headers actually state.

**Not established.** Whether chasing *one* ancestor is the right policy at all. R-RETR offered
the alternative (chase every named ancestor, and then the reason string must read "reply
ancestor of"); that is a larger change and an orchestrator decision, and I did not make it.

## 0.2 R-RETR-050 — one `Message-ID` in two threads, two rows each claiming to be the parent

**Changed.** `retrieval/assemble.py`: `_execute_structural_expansion` now returns a
`RecoveredParent` per thread carrying `(for_child_id, message_id_header, matched_messages)` —
how many ids **one** `rfc822msgid:` probe put into `H`. `_rows_of` reads it: one match is
`Role.PARENT` + `ReplyParentOf` as before; more than one is `Role.CONTEXT` and a new
`ReasonKind.REPLY_PARENT_AMBIGUOUS`, rendering

> `named parent of c1: Message-ID <twice@mail.invalid> is carried by 2 messages, so which one this reply names is not determined`

with `matched_messages` as a typed parameter, so an agent branches on the count rather than
parsing prose. This is R-RETR's option (a): the relation disclosed is one that is true, and the
ambiguity is declared. It is `_resolve`'s own standard — *"an id carried by two messages
resolves to nothing"* — applied at the rung that walked around it.

**What the tests establish.**
`test_one_child_is_never_told_it_has_two_reply_parents` asserts both recovered rows take the
ambiguous reason and `Role.CONTEXT`, that no row in the response carries `Role.PARENT`, and
that `reason_detail["matched_messages"] == 2` is on the wire.
`test_an_identifier_that_matches_once_is_still_the_parent_it_always_was` is the complement, so
the fix is not "never say parent again".

**Not established.** Whether one `Message-ID` in two threads occurs in a real mailbox. R-RETR
said the same; it is **R-GMAIL**'s. What is established is that the code now has a defence.

## 0.3 R-RETR-051 — the mention scanner, and the digest decision it binds

**Changed.** `assemble._observed_text` hands the participant index `processed.body_clean.text`
— the annotated body — instead of `processed.default_view`, which is the `original` spans only.
A7's rule is *annotate, do not delete*, and it applies to what is **scanned** as much as to
what is shown; the default view is still what is *disclosed*, which is a separate decision and
is unchanged. `threadmap.py`'s docstring claim — *"Mentions are scanned only in text this
response actually observed"* — is now true of its caller as well as of itself.

**Which did I do: fix 051, or keep participants out of the digest? Both, and the second is not
made redundant by the first.** Scanning the annotated body removes the *narrowing*. It does not
make the participant index a function of the thread: a row whose body was fetched is scanned
over the whole body, and a row that only ever had a `snippet` is scanned over about two hundred
characters, so the mention half still depends on **which rows this query matched**.
`test_the_participant_index_still_depends_on_depth_and_the_digest_therefore_excludes_it`
executes exactly that — one thread, two queries, two different participant blocks, with the
*authorship* half identical under both — and its assertion is written so that if the depth
dependence ever does disappear, the test fails and sends the next implementer to
`mailweave.handles.digest` to revisit the decision rather than leaving a stale comment there.

So `mapping_digest` covers the map — thread ids, `stated_total`, and per message its id,
chronological position, `linkage`, `reply_parent_id`, `can_be_a_parent`, plus
`tied_on_internal_date` — and does **not** cover `Source.participants`. Had I digested it, two
redemptions of one handle at different disclosure depths would produce `handle_stale` for a
thread nothing changed in, which is a false statement in the one field a caller trusts to be
conservative. `test_the_digest_does_not_cover_the_participant_block` and
`test_the_digest_changes_when_the_map_does` are the pair: the exclusion is not the digest
ignoring everything.

I considered digesting the authorship half only. I did not: splitting the participant block in
two inside the digest would put a rule there that the participant index does not itself
enforce, and the copy that stops matching is always the one nobody is looking at.

## 0.4 R-RETR-052 — a truncated snippet minted an address in no message

**Changed.** `structure/participants.py` gains `ObservedText(text, truncated_at_end)`;
`addresses_in_text` takes it, uses `finditer` rather than `findall` (the match's *position* is
the evidence, and `findall` throws it away), and discards any match whose end is the end of a
truncated text. `_observed_text` marks a `snippet` truncated — Gmail cuts it at a length, not at
a word — and an annotated body not truncated.

A short message whose snippet is really the whole body is treated as truncated too. That cannot
be told apart from here, and the cost is at most one mention missed at the very last character
— the direction this module already declares it prefers, stated rather than left implicit.

**What the tests establish.**
`test_a_truncated_snippet_never_mints_an_address_that_is_in_no_message` runs all three cases at
the scanner (touching the cut, the same string read as whole, and a truncation that does not
touch an address). `test_no_address_reaches_the_wire_that_appears_in_no_message_of_the_mailbox`
states the property over the response instead: every participant address is a substring of some
message the mailbox holds, under both queries.

**Not established.** The head-truncated `default_view` path R-RETR also names. It is no longer
the mention scanner's input at all, so the class is closed for mentions; whether A.9a's
truncation has other consumers with the same problem is **WS-11**'s to check when it builds
them.

## 0.5 R-RETR-054 — D.4a's compensating fact now reaches the row

**Changed.** `MessageRow` carries `can_be_a_parent: bool | None`, and a new validator,
`_not_knowing_whether_a_message_can_be_named_is_exactly_one_linkage`, holds `None` to
`Linkage.HEADERS_UNOBSERVED` **exactly** in both directions. That is what makes the field
impossible to omit: a row that declares any other linkage has had its headers read, so whether
it carries a `Message-ID` is something the response knows and must say. Left as a plain default
it would have been absent from most rows — which is the state R-RETR-054 filed, arriving
through the schema instead of through the module. `reply_tree.py`'s docstring claim that
`can_be_a_parent` *"is the half a caller needs"* — which R-RETR listed as false on execution —
is rewritten to say what changed and why the ruling it rests on now holds.

I did **not** reverse the linkage. R-RETR ruled the narrow reading stands and recommended
against reversing; the ruling was conditional on the fact reaching the caller, and it does.

**What the tests establish.**
`test_a_message_no_reply_can_ever_name_is_distinguishable_on_the_wire` builds D.4a's case with
a `Message-ID`-less message that the query **matches** (so it takes the body-bearing branch of
`_rows_of`) beside a second one that is a stub, because the field is written in two places in
that function and each is removable on its own — replants R46 and R57 are those two sites.
`test_not_knowing_whether_a_message_can_be_named_is_exactly_one_linkage` drives the
biconditional at the model.

**A finding about my own change, found by the replant harness.** Planting R40 (round 20's
"a parent may be named beside a declared gap") stopped being caught: my new validator refuses
the three probe documents before the parent/gap check is reached, so
`test_a_parent_beside_a_declared_gap_is_not_representable` was passing while asserting nothing
about the validator it is named for. Fixed by stating `can_be_a_parent` in that test's `base`
document. This is exactly the failure mode the manifest exists to catch and it caught it; I
swept the other `pytest.raises(ValidationError)` sites around `MessageRow` and the rest use
`HEADERS_UNOBSERVED`, so their assertions still do the work they claim.

## 0.6 R-RETR-053 — a lookup L4 declined to make is now in the response

**Changed.** `_l4_not_tried` emits a third entry —
`not_tried{rung: "L4:unprobeable_identifier", why: not_applicable}` — whenever
`StructuralPlan.skipped` is non-empty **and** probes ran. It is named apart from `L4` because
the rung *ran*: reporting it as `L4 not_applicable` beside probes that went out would
contradict `rungs`, and reporting nothing — which is what happened — leaves a lookup MailWeave
chose not to make invisible in a response that accounts for everything else. It is
`not_applicable` rather than `cap`: `is_probeable` is a permanent inability of that identifier,
and a `cap` would put an affordance beside it that cannot help.

`test_a_probe_declined_while_others_ran_is_reported_rather_than_invisible` and
`test_the_declined_entry_is_absent_when_every_identifier_was_probeable` are the pair, so the
entry is a fact about the response rather than a constant.

## 0.7 R-RETR-055 — one derivation of "when was this message stamped"

**Changed.** `gmail/client.py`, `_thread_scalars`: `moment = {id: int(internal_date)}` is
computed once and read by both the sort key and the tie census. The census used to run on the
raw string while the sort ran on the integer, so `"01000"` and `"1000"` — equal as integers,
unequal as strings, and `GmailNumericId` accepts a zero-padded value — tied in the ordering and
appeared in no `tied_on_internal_date` entry.
`test_a_tie_settled_by_message_id_is_declared_however_the_stamp_is_spelled` executes both the
repaired case and the two ordinary ones.

## 0.8 R-RETR-057 — the two narrowings `_resolve` makes

Taken as R-RETR permits: **recorded, and executed**. `_resolve`'s docstring now states both — a
multi-id `In-Reply-To` is arbitrated by wire order (and why that is a reading of the headers
rather than a choice between candidates the headers rank), and an `ambiguous` seen on the way
to a unique candidate is dropped and reaches no field.
`test_the_two_narrowings_resolve_makes_are_the_ones_its_docstring_states` pins both, so the
record is executed rather than asserted. Carrying the dropped ambiguity out would need a field
on `Link` **and** on `ThreadStructureReport`, which is a disclosure change rather than a
reconstruction one; I did not make it and say so in the docstring.

## 0.9 R-RETR-056 — not mine, and not taken

L4's `q` is composed from a sender-chosen `Message-ID` and is disclosed verbatim in
`scan_scope[].q`. R-RETR filed it as **R-SEC's and WS-14's to rule on** and I have left it
exactly as it is. Stripping Unicode format characters from an identifier before it enters a
`q` would change what `rfc822msgid:` matches, and that is a decision about an exact-match
operator, not a formatting change. Recorded here so the next round does not read the silence as
agreement.

---

# Part 1 — WS-06: handles and staleness

## 1.1 What was built

| Area | Where |
|---|---|
| The HMAC key in the `0600` token store, with `key_epoch` and a deliberate rotation | `server/src/mailweave/handles/keys.py`, `auth/tokenstore.py` (`map_key_hex`) |
| `map_id` payload, signature, and redemption step 1 (`verify`) | `server/src/mailweave/handles/mint.py` |
| `mapping_digest` — what it covers and what it deliberately does not | `server/src/mailweave/handles/digest.py` |
| The LRU: key `(thread_id, history_id_at_fetch)`, 60 s TTL, 64 entries, eviction on staleness | `server/src/mailweave/handles/cache.py` |
| The redemption order, the trace, and the seven shapes | `server/src/mailweave/handles/redeem.py` |
| The independent liveness probe over all four `historyTypes` | `gmail/client.py` — `liveness_of_threads`, `ThreadChange`, `LivenessProbe` |
| `messagesDeleted` / `labelsAdded` / `labelsRemoved` on `HistoryRecord`, with their consumer | `gmail/models.py` — `HistoryMessageEvent` |
| `HANDLE_ERROR_CODES`, `HandleRefused` | `errors.py` |
| `Source.map_id` minted from the response's own maps | `retrieval/assemble.py` — `_map_id_for`, `HandleMinter` |
| A mailbox that **moves**: add / delete / relabel, real `history.list` with `historyTypes` filtering, pagination and the 404 | `tests/fixtures/mailbox.py` |
| 48 tests | `tests/test_handles_round21.py` |
| Round-21 replants **R42–R57** | `tests/fixtures/replants.py` |

### The plan's row, item by item

* **`map_id` = base64url payload + HMAC over `{v, key_epoch, account_hash, thread_ids[], fetched_at, history_id, mapping_digest, ttl}`** — built, with one addition named and justified in §1.5.
* **Redemption order: verify → independent `history.list` liveness probe → fetch → digest recompute** — §1.2.
* **Five error classes, none collapsed into another** — §1.3, and the closed-vocabulary sweep asserts equality.
* **LRU `(thread_id, history_id_at_fetch)`, 60 s, 64 entries, eviction on staleness** — four tests, one per clause.
* **`fetched_at` never restamped; `verified_at` added on LRU service** — §1.4.
* **PF-15 cache-cold and cache-warm as two cases; the warm digest check labelled `cache_tautology`** — §1.2.
* **Restart keeps handles valid; rotation yields `handle_key_rotated`, not `handle_expired`** — §1.6.

## 1.2 The order is the design

`verify` (step 1) reads a string the caller sent and a key on disk. It establishes **that this
server minted this handle, for this mailbox, recently enough to be worth re-verifying** — and
nothing about the mailbox, because no network call has been made. Its docstring says exactly
that and `test_verifying_a_handle_establishes_nothing_about_the_mailbox` executes it: the
mailbox is mutated, `verify` still returns a payload, the double records zero calls, and the
same handle then redeems as `handle_stale`.

Step 2 is the verification. `GmailClient.liveness_of_threads` walks `history.list` with
`historyTypes = messageAdded, messageDeleted, labelAdded, labelRemoved` — a **different
resource** from the one the cache holds, which is what makes a cache hit unable to make it pass.
That is ADV-002 in one sentence, and PF-15's warm arm is the executed form of it.

**PF-15, two arms, two tests.**

* `test_pf15_mutate_then_redeem_cache_cold` — a message arrives after the mint; the probe
  catches it, `trace.changed == {"t-alpha": "1 messages added"}`, `trace.steps` is
  `(verify, liveness_probe)`, and nothing was served: a refused handle does not pay for a map.
* `test_pf15_mutate_then_redeem_cache_warm` — the same, with the cache first warmed by a clean
  redemption and asserted still live for this exact `(thread_id, history_id_at_fetch)` **before**
  the second redemption, so the arm is not vacuous. It fires, and the contradicted entry is
  evicted.

**The warm path does not borrow the cold path's guarantee.**
`test_a_warm_redemption_labels_its_digest_check_a_cache_tautology` asserts a cold redemption
reports `digest_check: recomputed_from_fetch` with `threads_fetched=('t-alpha',)`, and the warm
one reports `cache_tautology` with `threads_from_cache=('t-alpha',)`, one API call rather than
two, and `liveness: verified_unchanged`. The label is computed from where the content came
from, not passed in, so no caller can make a warm redemption claim otherwise.

## 1.3 What is common to the seven handle shapes, and the single test covering it

Five error classes and two cache states is **seven**, not ten: `handle_invalid`,
`handle_key_rotated` and `handle_expired` are settled at step 1, before any network call, so
they have no cache state at all; `handle_stale` and `handle_stale_unverifiable` have both.

**The commonality is not the code and not the cache state.** It is that a redemption's answer
is assembled step by step, and

> every field of the answer is produced by the step that produced it, and a step that did not
> run leaves its field at its "not reached" value.

That one sentence rules out the whole family: content served without a liveness probe; a
`verified_at` on a thread nothing verified; `fetched_at` restamped to now; a warm digest
recompute wearing the cold path's label; a refusal from step 1 that nevertheless spent a Gmail
call; an affordance minted from a document nothing verified.

**The single test** is
`tests/test_handles_round21.py::test_every_handle_outcome_only_claims_what_the_step_that_ran_produced`.
It builds the seven shapes from a matrix of conditions rather than a list — signature bit
flipped, key rotated under a real `TokenStore`, clock past the ttl, mutation × {cold, warm},
history expired × {cold, warm} — adds the clean redemption as the eighth answer, and asserts
eight clauses over every one of them:

| Clause | What it rules out |
|---|---|
| (a) the code is in `HANDLE_ERROR_CODES` and its surface is `ERROR_SURFACE`'s | a class invented at the call site, or a surface written by hand |
| (b) content is served **iff** `outcome ∈ {None, handle_stale_unverifiable}`, **iff** fetch and digest both ran | serving without the steps that produce content |
| (c) `liveness is not_reached` **iff** the class is settled at step 1, **iff** `steps == (verify,)`, **iff** `api_calls == 0` | a refusal that spent a call; a step-1 class that claims a probe |
| (d) `digest_check is cache_tautology` **iff** any thread came from the cache | the warm path claiming the cold path's guarantee |
| (e) `liveness is unverifiable` ⟹ nothing from the cache, and the class is `handle_stale_unverifiable` | serving a cached map the probe failed to check |
| (f) per thread, `verified_at is not None` **iff** `from_cache`, and `fetched_at < verified_at` | a restamped `fetched_at`; a `verified_at` on a live read |
| (g) `handle_stale` names what moved; every outcome has a non-empty account of itself | a silent refusal |
| (h) the re-derivation affordance exists **iff** the payload had verified | caller-supplied strings in a connector-voiced field |

And the matrix is asserted non-vacuous: `reached == HANDLE_ERROR_CODES` (equality, so a sixth
handle class added to D.11 fails here until something produces it) and both cache states are
present for the two classes that have them.

Beside it,
`test_every_value_of_every_redemption_vocabulary_is_one_the_product_can_produce` asks the
`Linkage`-sweep question of the three enums this round adds — `Step`, `Liveness`, `DigestCheck`
— as **equality**. Reaching `DigestCheck.MISMATCH` needs its own construction (a handle minted
over a digest the threads do not make), which is step 4's defence-in-depth branch and would
otherwise have been a vocabulary member with no producer.

## 1.4 `fetched_at` is never restamped

The cache stores the stamp the observation sealed and hands back that same string however many
times the entry is served; `verified_at` — this call's liveness-probe instant — is added beside
it on LRU service only, because a live fetch's `fetched_at` *is* this call's read and a second
stamp for one event would be a second fact.

`test_a_cached_map_keeps_the_stamp_of_the_read_that_produced_it` asserts the cold read's stamp
survives a warm service thirty seconds later, with `verified_at` set to the later instant and
strictly after it. `test_a_handle_in_continuous_use_still_expires` is the consequence stated as
the thing it protects: the same handle is redeemed across the whole 900 s ttl at 30 s intervals
and then once past it, and the last one is `handle_expired` — which is only true because
nothing along the way rewrote the stamp expiry is measured from. Every time in that test is
derived from the handle's own `fetched_at`, not from a fixture constant, so it is a statement
about the handle's age rather than about two clocks agreeing.

## 1.5 The one addition to A.10's payload, named

A.10 lists the payload as `{v, key_epoch, account_hash, thread_ids[], fetched_at, history_id,
mapping_digest, ttl}`. I added **`thread_history_ids[]`**, positionally aligned with
`thread_ids`, and I want a reviewer to look at it first. Two reasons, which are the same reason:

1. A.10 keys the LRU on `(thread_id, history_id_at_fetch)`, and MCP is stateless (SC §14). With
   no server-side session there is nowhere else `history_id_at_fetch` could come from, so a
   handle without it **cannot form the key A.10 specifies**.
2. The liveness probe needs a floor per thread. `history_id` is the watermark the walk starts
   from and it must be the *oldest* of the named threads' own ids, or a change to the oldest
   thread falls under the window and is invisible — a handle answering "unchanged" about a
   mailbox that moved. But a walk from there necessarily also returns changes already reflected
   in the map the handle was minted over, and counting those makes a freshly minted
   multi-thread handle redeem as `handle_stale` on its first use. The floor is what separates
   the two: a record counts against a thread only when the record's own `historyId` is greater
   than **that thread's** at fetch.

`history_id` is **derived** from `thread_history_ids` inside `mint`, and `HandlePayload`'s
validator re-derives it, so it cannot be a second, disagreeing claim about the same set.
`test_a_handles_watermark_is_the_oldest_of_the_threads_it_names` builds a two-thread handle
whose threads have different watermarks and asserts both halves: the payload's `history_id` is
the older one, and the probe reports no change even though the newer thread's own last change
sits inside the walked window.

Everything else in the payload is A.10's, verbatim. `ttl` is `[DESIGN] 900 s` — A.10 fixes the
LRU's 60 s and says the handle's own must be at least that, and fixes no number for this one;
`MIN_HANDLE_TTL_SECONDS = 60` is the floor `HandlePayload` refuses a smaller ttl against, so no
handle can outlive the cache that serves it, and
`test_the_cache_ttl_is_never_longer_than_a_handles_own` holds it from both sides.

## 1.6 Restart, rotation, and the key as a secret

`test_a_restart_does_not_invalidate_an_outstanding_handle` models a restart as one: the
process's `HandleKey` object is discarded and a new one is loaded from the same `0600` store,
and the outstanding handle redeems clean. That is the whole of why the key is on disk
(ADV-212); the previous design's misattributed `handle_expired`-on-a-fresh-handle was this.

`test_a_deliberate_key_rotation_is_reported_as_a_rotation_and_not_as_age` asserts a
seconds-old handle under the previous epoch redeems as `handle_key_rotated`, with zero API
calls, and that the store now holds one epoch rather than a keyring — a keyring retaining the
previous key would make rotation a no-op for exactly the handles rotation exists to invalidate.

**The key is a secret and it is covered by the machinery that exists.** `map_key_hex` is a
`SecretStr | None` on `StoredCredentials`, which is already a `SecretBearingModel`. The
reflection canary in `tests/fixtures/secret_models.py` discovers it from `model_fields` with no
edit: `corrupt_documents(StoredCredentials)` went from 29 shapes to **33** and each is driven
through **6** entry points, so the field arrived with 24 new canary executions and I weakened
nothing. `test_the_handle_key_is_covered_by_the_reflection_canary_the_moment_it_exists` asserts
that rather than assuming it.

One thing I had to change in the store and it is worth a reviewer's eye:
`TokenStore.save` unwrapped `refresh_token` by name. `model_dump` renders a `SecretStr` as
`**********`, so a second secret field not unwrapped would have been **persisted as asterisks**
and read back as a key that verifies nothing — indistinguishable from `handle_invalid` on every
outstanding handle after a restart. It is now a sweep over the model's own secret fields rather
than a second named line, and `test_the_key_written_to_the_store_is_the_key_read_back` asserts
the round trip against the real file.

`test_the_handle_key_is_never_rendered` and `test_the_signing_key_never_reaches_a_handle_or_a_response`
close the two rendering routes: `HandleKey.__repr__` is redacted (the `StaticToken` rule
reapplied — the default dataclass `__repr__` prints every field), and the key's hex and base64
forms appear nowhere in a serialised envelope.

## 1.7 The handle on the wire

`Source.map_id` is populated when `assemble` is given a `HandleMinter`, and `None` otherwise —
which is what every response before this round carried and is the honest value for a server
with no key. It is also `None` when the `threads.get` stated no `historyId`: a handle whose
liveness probe has nothing to walk from could only ever redeem as
`handle_stale_unverifiable`, and `map_id` is a claim.

`test_a_source_carries_a_handle_that_redeems_back_to_the_same_thread` mints through the real
ladder and redeems the source's own `map_id` back to the same thread in the same chronological
order. That closes STR-05's "each source carries a map affordance", which R-RETR named as one
of the three things stopping that criterion — the other two were R-RETR-049/050, also closed
here. **I mark nothing**; that is a reviewer's call.

## 1.8 Every docstring claim about what a handle guarantees, with its evidence

| Claim, and where it is written | Executed by |
|---|---|
| `verify`: *"establishes exactly one thing: this server minted this handle, for this mailbox, recently enough to be worth re-verifying … establishes **nothing about the mailbox**"* | `test_verifying_a_handle_establishes_nothing_about_the_mailbox` (mutate, verify, zero calls, then `handle_stale`) |
| `redeem`: a clean redemption guarantees no `messageAdded`/`messageDeleted`/`labelAdded`/`labelRemoved` record touched a named thread above that thread's own `historyId` | `test_a_handle_notices_every_way_the_mailbox_can_move_under_it` (three parametrised cases), `test_a_change_to_another_thread_does_not_make_this_handle_stale`, `test_a_handles_watermark_is_the_oldest_of_the_threads_it_names` |
| `redeem`: … and that the maps handed back digest to the value the handle carries | `test_every_value_of_every_redemption_vocabulary_is_one_the_product_can_produce` (the `MISMATCH` construction), `test_the_digest_changes_when_the_map_does` |
| `redeem`: *"does not guarantee … on a cache-served thread, anything at all from step 4"* | `test_a_warm_redemption_labels_its_digest_check_a_cache_tautology`; clause (d) of the seven-shape property |
| `cache`: *"`fetched_at` … is never restamped"* | `test_a_cached_map_keeps_the_stamp_of_the_read_that_produced_it`, `test_a_handle_in_continuous_use_still_expires`, clause (f) |
| `cache`: *"is not a verification and cannot become one"* — nothing in it is consulted by step 2 | `test_pf15_mutate_then_redeem_cache_warm` (warm entry live, probe fires anyway), `test_the_liveness_probe_is_charged_before_the_fetch_and_the_fetch_is_skipped` (`call_log == ["history.list"]`) |
| `cache`: TTL 60 s, 64 entries, keyed on both, evicted on staleness | four tests, one per clause |
| `keys`: *"a restart does not invalidate outstanding handles"*; *"old key material is not retained"* | `test_a_restart_does_not_invalidate_an_outstanding_handle`; `test_a_deliberate_key_rotation_is_reported_as_a_rotation_and_not_as_age` |
| `mint`: *"the signature is over the encoded payload **as received**, not over a re-encoding"* | `test_the_signature_covers_the_bytes_as_received_and_not_a_re_encoding` (same object, different bytes, refused) |
| `mint`: the refusal *"names field paths and error types only"* | `test_a_handle_that_is_not_one_is_refused_without_quoting_it`, six parametrised shapes |
| `digest`: *"ids are hashed, not carried"* | `test_the_digest_carries_no_identifier_it_was_computed_over` |
| `digest`: covers the map, not `Source.participants`, and why | `test_the_digest_does_not_cover_the_participant_block` + `test_the_participant_index_still_depends_on_depth_and_the_digest_therefore_excludes_it` |
| `liveness_of_threads`: *"no id this call observed leaves it, so nothing enters `H`"* | `test_the_liveness_probe_records_nothing_into_the_disposition_ledger` (`ledger.hit_ids == frozenset()` after a probe that saw an addition) |
| `HandleRefused.affordance`: `None` for the two classes decided before the signature is checked | `test_a_refusal_carries_the_re_derivation_call_only_once_it_has_verified`, clause (h) |

**One narrowing of D.11 I made deliberately, and a reviewer should rule on it.** D.11's table
gives every handle class "the re-derivation call" as its remediation. `handle_expired`,
`handle_stale` and `handle_stale_unverifiable` carry a concrete
`Affordance(mailweave_thread_map, {thread_ids: […]})`. `handle_invalid` and
`handle_key_rotated` carry **none** and name the call in words instead: both are decided while
the payload is still unverified — the epoch has to be read before the signature, because with
the rotated key gone the signature cannot verify either way — so filling an affordance's
arguments from it would put caller-supplied strings into a connector-voiced field, which is the
route R-SEC-030/032 closed on the disclosure side. I also bounded each `thread_ids` element at
`MAX_SEALED_ID_CHARS`, imported rather than restated, so an unverified payload cannot carry a
megabyte "thread id" into a refusal message
(`test_a_thread_id_inside_an_unverified_handle_is_bounded_like_every_other_id`).

## 1.9 What I could not establish

* **Anything about a real Gmail account.** Every probe here ran with `socket.connect` denied.
  OD-6 says in terms that this is not evidence for milestone criteria 2, 3 or 4-on-real-mail,
  and it is not.
* **Whether Gmail's `history.list` is complete**, whether it can omit a change, and what its
  retention window actually is. `handle_stale_unverifiable` exists because the 404 is
  documented; that the *absence* of a record means nothing happened is an assumption about
  Gmail. **R-GMAIL**, and it bounds what a clean redemption is worth.
* **PF-1** — whether `threads.get`'s array can be short of the thread. A handle digests the
  array it was given; if the array can be short, the digest is over a short thread and says so
  about a complete one. Unchanged from round 20, and named on `redeem`'s docstring.
* **Whether duplicate `Message-ID`s across threads or zero-padded `internalDate`s occur** in a
  real mailbox (R-RETR-050, R-RETR-055). The defence is established; the frequency is R-GMAIL's.
* **Concurrency.** MCP-02's acceptance names "a second concurrent client". The handle is
  stateless and the LRU is in-process, so two processes cannot see each other's cache — which
  is the right shape — but I have not run two clients, and `ThreadMapCache` is not
  thread-safe. **WS-15** owns the server surface and the concurrency test; the cache's
  `__slots__` and `OrderedDict` will need a lock or a per-request instance there.

## 1.10 Have I trusted a peer?

The question I asked at each site, and the answer:

* **The five error classes.** I did not write a list. `HANDLE_ERROR_CODES` is derived from
  `ErrorCode` by prefix, `HandleRefused` refuses a code outside it, `redeem_or_raise` reads the
  tool-error/in-band partition out of `ERROR_SURFACE`, and the sweep asserts **equality**. A
  sixth handle class is in the set the moment it exists and fails the sweep until something
  produces it.
* **The four `historyTypes`.** The first version of the probe asked for `messageAdded`, because
  that is what `_fetch_history` asks for and it was the shape in front of me. That is the exact
  defect — one shape validated, peers trusted — in the field that would have silently answered
  "unchanged". All four are asked for, the double *filters* on `historyTypes` and raises on one
  it does not implement, and R49 plants the narrowing back.
* **The two sites in `_rows_of` that set `can_be_a_parent`.** I wrote one replant, and the
  harness reported it caught while the other site was still plantable. Both are now covered by
  a fixture that reaches both branches, and by two manifest entries (R46, R57).
* **`TokenStore.save`'s secret unwrapping.** One named line for `refresh_token` would have made
  the second secret field the one nobody adds. It is a sweep over the model's own fields.
* **The three vocabularies this round adds.** `Step`, `Liveness` and `DigestCheck` are swept as
  equality, which is what surfaced `DigestCheck.MISMATCH` having no producer until I built one.
* **`is_an_address` / `parse_instant` / `GMAIL_NUMERIC_ID_RE` / `MAX_SEALED_ID_CHARS`.** Every
  shape check in the new code imports the one implementation. There is no new copy of any of
  them; `test_no_module_reimplements_the_gmail_numeric_shape` and its two siblings still pass.

**Where I know I have trusted something.** `_map_of` in `redeem.py` and `_map_of` in
`assemble.py` build a `ThreadMap` from the same inputs by two similar-looking routes. They must
agree or the digest fails — which is defence-in-depth and is also two derivations of one thing.
I did not unify them because the two callers hold different objects (a `LadderRun` with bodies
versus a bare `RecordedThread`), and the agreement is executed end to end by
`test_a_source_carries_a_handle_that_redeems_back_to_the_same_thread`: a handle minted through
`assemble` redeems through `redeem`, which only passes if the two agree exactly. If a reviewer
would rather see one function, that is a fair ask.

## 1.11 Unreachable from code that exists today

| Thing | Workstream | Blocks OD-6 integration? |
|---|---|---|
| `Source.verified_at` on a redeemed response — the field exists on `Source` and redemption produces `ServedThread.verified_at`, but nothing assembles a redeemed `Envelope` | **WS-15** (the `mailweave_thread_map` tool) | **No.** The value is produced and tested; what is missing is the tool that puts it on a response. |
| `HandleRefused` → an MCP tool error with D.11's code and the affordance | **WS-15** | No |
| The LRU shared across requests, and concurrency | **WS-15** | No — but it is a design decision that round must make, not inherit |
| `mailweave.handles` reachable from the CLI (`auth` never generates the key; `ensure_handle_key` runs on first mint) | **WS-01 / WS-15** | No |
| `handle_stale_unverifiable` reaching a caller as an in-band `errors[]` entry | **WS-03 surface, wired by WS-15** | No |
| Whether a handle should ever name more than one thread | **WS-11 / WS-15** — the payload supports 1–16 and `assemble` mints one thread per source | No |
| STR-02's `{display_name, address}` pair exposure; the seeded-corpus link-accuracy bar; GMAIL-03's discrepancy bound | WS-11, WS-16, R-GMAIL | No — all named by R-RETR in round 20 and unchanged |

Under OD-6's counter-rule: **this round produced integration progress rather than an audit.**
Part 0 closed seven filed findings and Part 1 built a workstream; nothing here is a critical
correctness or safety defect held back, and the next workstream (WS-10 or WS-15 by the plan's
own order) can start on this.

---

## 2. Reintroduction

`tests/fixtures/replants.py` carries **57** entries. R42–R57 are this round's: R42–R48 for the
seven claims R-RETR found wider than the code, R49–R57 for WS-06.

R42–R48 exist because round 20's manifest had **no entry for any of them** — which is how
R-RETR could mutate `Link.evidence` two different ways and the mention scanner's input one way
and get a green suite each time. A manifest that defends the reconstruction and not the claims
made about it defends half of what the round changed.

Two round-20 anchors rotted and were re-anchored against the code as it now stands: **R29**
(quoted `evidence=named[0]`, which R-RETR predicted) and **R32** (the sort key, which now reads
the shared `moment` map).

Three things the harness reported that I would not have found by reading:

* **R40 stopped being caught** — my new `MessageRow` validator made its catching test pass for
  a different reason (§0.5).
* **R46 was planting the wrong branch** — the 16-space anchor is a substring of the 20-space
  line, so `anchor_counts` read 1 while `plant` hit the body branch. Both anchors now carry a
  following line to disambiguate, and both branches are asserted.
* **R52 was not catchable as written** — the LRU bypass is defended twice (evict, then skip), so
  planting either alone leaves the behaviour intact. That is defence in depth working; the
  plant is now the condition they both read.

**Executed.** `run_replants` over the whole manifest in a full scratch copy including `docs/`,
with `mailweave`, `mailweave_harness` **and** `tests` asserted to resolve inside the copy and
asserted **not** to resolve into the working tree:

```
scratch: /tmp/tmps96ggwr4/tree
docs/RELEASE_RUBRIC.md in the copy: True
imports resolve into: ('/tmp/tmps96ggwr4/tree/server/src/mailweave/__init__.py', '/tmp/tmps96ggwr4/tree/harness/src/mailweave_harness/__init__.py', '/tmp/tmps96ggwr4/tree/tests/__init__.py')
rows=57 anchors!=1: 0  files unchanged: 0  missed: 0
```

And, for the sixteen new entries, the stronger question — *is this behaviour defended by
anything other than the test written for it?* — run with the named tests deselected:

```
R42-the-gap-records-the-thread-root-instead-of-the-nearest-ancestor    anchors=1 changed=True caught=True elsewhere=True
R43-a-message-id-in-two-threads-yields-two-parents-for-one-child       anchors=1 changed=True caught=True elsewhere=True
R44-the-mention-scanner-is-handed-the-quote-stripped-view-again        anchors=1 changed=True caught=True elsewhere=True
R45-a-truncation-boundary-is-treated-as-an-address-boundary            anchors=1 changed=True caught=True elsewhere=True
R46-a-message-no-reply-can-name-looks-like-an-ordinary-reply-again     anchors=1 changed=True caught=True elsewhere=True
R57-the-body-bearing-row-loses-the-same-fact                           anchors=1 changed=True caught=True elsewhere=True
R47-the-tie-census-reads-the-string-and-the-sort-reads-the-integer     anchors=1 changed=True caught=True elsewhere=True
R48-a-declined-l4-lookup-goes-unreported-when-other-probes-ran         anchors=1 changed=True caught=True elsewhere=True
R49-the-liveness-probe-asks-only-about-additions                       anchors=1 changed=True caught=True elsewhere=True
R50-a-warm-digest-recompute-claims-the-cold-paths-guarantee            anchors=1 changed=True caught=True elsewhere=True
R51-fetched-at-is-restamped-when-the-cache-serves-a-map                anchors=1 changed=True caught=True elsewhere=True
R52-a-probe-that-could-not-tell-is-read-as-a-probe-that-found-nothing  anchors=1 changed=True caught=True elsewhere=True
R53-a-deliberate-key-rotation-is-reported-as-age                       anchors=1 changed=True caught=True elsewhere=True
R54-the-mapping-digest-covers-the-participant-block                    anchors=1 changed=True caught=True elsewhere=True
R55-the-handle-watermark-is-the-newest-named-thread-instead-of-the-oldest anchors=1 changed=True caught=True elsewhere=True
R56-a-history-walk-that-stopped-early-is-read-as-clean                 anchors=1 changed=True caught=True elsewhere=True
```

## 3. State on arrival, and what moved

The tree was green on arrival: 2,369 collected and passing, all seven guards clean, rubric
6/0/0/107. It is green now at **2,439**. The counts that moved and why:

* `AUDITED_FIELD_TOTAL` 231 → **236**: `MessageRow.can_be_a_parent` (1) and
  `ReplyParentAmbiguous`'s three parameters plus its discriminator (4).
* `TREE_AFTER_VALIDATORS` 47 → **48**, `MessageRow`'s share 5 → 6:
  `_not_knowing_whether_a_message_can_be_named_is_exactly_one_linkage`. `Envelope`'s share is
  unchanged for the third round running, which is the half of that pair that matters.
* The reason-kind sweeps grew by one kind and two string parameters (10 → 12).
* `tests/fixtures/mailbox.py` gained mutation and a real `history.list`. Every default is the
  value it had before, so no existing test's mailbox behaves differently; a thread nothing has
  touched reports the *starting* watermark rather than the mailbox's current one, which is what
  makes "has this thread changed" answerable at all.

## 4. Rubric

**I marked nothing.** `docs/RELEASE_RUBRIC.md`, `docs/reviews/FINDINGS_LEDGER.md` and
`docs/reviews/RUBRIC_TRANSITIONS.md` are untouched. ROUTE-01 was not restored. Retry and
backoff constants were not touched.

---

## 5. Gate output

```
$ .venv/bin/ruff check .
All checks passed!

$ .venv/bin/ruff format --check .
173 files already formatted

$ .venv/bin/mypy
Success: no issues found in 147 source files

$ .venv/bin/python -m tools.guards
guards clean: forbidden-import, generative-client, gmail-endpoint, ground-truth-isolation, scope-literal, unaudited-disk-write, unwrapped-http-client over server/src

$ .venv/bin/python -m pytest -m "not network"
2439 passed in 126.84s (0:02:06)

$ .venv/bin/python -m pytest -m "not network" --co -q   (summed per file, independently)
2439 tests collected

$ .venv/bin/python -m pytest -m "replant"
4 passed, 2435 deselected in 90.29s (0:01:30)

$ .venv/bin/python tools/rubric_status.py --check
criteria: 113  (mandatory 110, conditional 2, optional 1)
status:
  PASS         6
  FAIL         0
  BLOCKER      0
  NOT TESTED   107
reviewer transitions recorded: 11
gate-blocking criteria (NOT TESTED / FAIL / BLOCKER): 106
```
