# ROUND 20 — WS-05: the thread map and structural retrieval

**Implementer report.** Protocol `docs/AGENT_LOOP.md` §5, under **OD-6**'s build order and its
counter-rule. Gating reviewer: **R-RETR**.

**Result in one line.** A thread's reply structure is now reconstructed from RFC headers alone or
declared unreconstructable in a closed vocabulary on every row; positions are chronological by
`internalDate` regardless of the order Gmail sends its array in; authorship, co-authorship, receipt,
`Reply-To` and mention are five distinguishable roles keyed on the address; L4 recovers a reply's
parent from another thread as a separate source; and every id either route put into `H` is still
accounted for by the disposition ledger.

**Gates.** ruff, `ruff format --check`, `mypy --strict`, `python -m tools.guards`,
`pytest -q -m "not network"` **2,369 passed** (was 2,290, of which 3 were red on arrival — see
"State on arrival"). Rubric unchanged: **6 PASS / 0 FAIL / 0 BLOCKER / 107 NOT TESTED**. Full output
at the end.

---

## 0. State on arrival, because it changes what "2,290 pass" meant

The working tree was **not green**. A previous, interrupted attempt at this round had left
`server/src/mailweave/structure/reply_tree.py` on disk importing `Linkage` and `RESOLVED_LINKAGES`
from `mailweave.envelope.vocab`, where neither existed. Three tests were failing:

* `test_every_test_a_source_docstring_names_exists` — that file's docstring cited
  `test_the_reconstruction_cannot_see_the_order_it_is_given`, which did not exist;
* both `test_new_operator_round19.py` scratch-tree tests, which run the suite inside a copy and
  therefore inherited the same failure.

`mypy --strict` also reported two errors in that file. All three failures and both type errors trace
to the one artifact. This round completed it rather than deleting it: the reconstruction logic in it
was sound, and its docstring's central claims are now executed rather than cited-and-absent.

I kept the module's structure and rewrote every paragraph of its docstring against the code as it
now stands, plus the changes listed in §2.

---

## 1. What was built

| Area | Where |
|---|---|
| `Linkage` (9 members), `RESOLVED_LINKAGES`, `DECLARED_GAP_LINKAGES`, `ParticipantRole` (5) | `server/src/mailweave/envelope/vocab.py` |
| JWZ / IMAP-REFERENCES reconstruction, completed | `server/src/mailweave/structure/reply_tree.py` |
| Address-keyed participant index | `server/src/mailweave/structure/participants.py` |
| The per-thread map: order + tree + participants | `server/src/mailweave/structure/threadmap.py` |
| L4 structural expansion (`rfc822msgid:` on unresolved parents) | `server/src/mailweave/retrieval/structural.py` |
| `is_an_address` / `MAX_ADDRESS_CHARS`, the one shared shape check | `server/src/mailweave/constants.py` |
| `MessageRow.linkage` / `.reply_parent_id`; `ThreadParticipant`; `ThreadStructureReport`; `Source.participants` / `.structure`; `WithheldCap.MAX_SOURCE_THREADS` | `server/src/mailweave/envelope/wire.py`, `vocab.py` |
| Chronological tie-break fixed; `RecordedThread.tied_on_internal_date` | `server/src/mailweave/gmail/client.py` |
| Map construction, structural roles/reasons, L4 execution, cap dispositions | `server/src/mailweave/retrieval/assemble.py` |
| `ThreadStructureError` | `server/src/mailweave/errors.py` |
| 46 test functions / 79 cases | `tests/test_thread_map_round20.py` |
| Reply headers, `Reply-To`, `Cc`, absent `Message-ID`, array-order control, PF-2's no-snippet and no-headers branches | `tests/fixtures/mailbox.py` |
| Round-20 replants **R29–R41** | `tests/fixtures/replants.py` |

### The plan's row, item by item

* **One `threads.get` per hit-bearing thread, deduped, `max_hit_threads = 12`** — already true from
  WS-04 and preserved: the map is carried from the fetch pass to the row pass rather than re-fetched.
  `test_one_threads_get_per_thread_and_never_two` asserts the call count equals disclosed sources plus
  not-included sources, sibling threads included.
* **JWZ / IMAP-REFERENCES with `linkage: "date-adjacent (no RFC reply headers)"` for orphans and no
  silent re-parenting** — §2 and §3.
* **Address-keyed participant index, authorship vs mentions** — §4.
* **Strict `internalDate` ordering, position on every row** — §5.
* **L4 sibling / structural expansion as separate sources, `max_source_threads = 4`** — §6.

---

## 2. The reply tree, and what changed from the artifact I inherited

Four substantive changes to the inherited `reply_tree.py`:

1. **`Linkage.NO_MESSAGE_ID`** added for AD **D.4a**'s case, and `Link.can_be_a_parent`. See §8 for
   the narrow reading and why it is recorded rather than glossed.
2. **`reconstruct` raises `ThreadStructureError` on two rows under one Gmail message id.** Every
   guarantee it makes is per message and two rows under one id have no single answer to any of them.
   Raised, not deduplicated, on amendment **A3**'s reasoning for an out-of-range position: quietly
   collapsing two rows moves evidence as silently as clamping does. The product never reaches it —
   `_thread_scalars` already refuses to seal positions for such a thread and `assemble` withholds it
   whole — so the refusal is asserted at the function, where the next caller meets it.
3. **`ThreadStructure.children_of` and `.gaps`**, both derived from the same links, so the two
   directions of one edge and the summary of the gaps cannot disagree with the rows.
4. The docstring's claims were rewritten to match the code (§8).

---

## 3. What is common to every reply-tree shape, and the one test covering it

**The commonality.** Every shape a reply tree can take — broken headers, subject change mid-thread,
forwards, orphans, cycles, self-references, duplicate `Message-ID`s, a reference to a message not in
the thread, a message with no `Message-ID` at all — differs only in *what the headers said*. What
does not differ is that **the reconstruction is a reading of the child's own headers and nothing
else**. Four properties make that statement checkable, and they are what separate a reading from a
guess:

1. every message of the thread gets **exactly one** `Link`, and its `linkage` is one member of the
   closed `Linkage` vocabulary;
2. a link either names a parent **that is a message of this same thread**, found under a `Message-ID`
   that (a) literally appears among this child's own `In-Reply-To`/`References` **and** (b) is the
   `Message-ID` that parent carries — or it names no parent at all and its `linkage` says which gap
   it is in;
3. following `parent_id` upward from any message terminates: the result is a forest;
4. `can_be_a_parent` is a function of this message's own `Message-ID` and of nothing else.

**The single test.**
`tests/test_thread_map_round20.py::test_every_reply_tree_shape_keeps_the_four_properties_that_make_it_not_a_guess`
— a Hypothesis property, 400 examples, over **generated** threads. The generator is written over the
*facts a Gmail response states* (which ids came back, which carried a `Message-ID`, what the reply
headers named, whether headers were observed at all), so duplicate `Message-ID`s, cycles,
self-references, references to absent messages, unobserved headers and empty reply headers arise from
those choices rather than being enumerated. A property that holds there holds for shapes nobody wrote
down.

Property 2's second half is the one that catches the guess. A reconstruction that attached each
message to its predecessor satisfies "the parent is in this thread" and fails "under an id the child
named". That is exactly what replant **R29** plants, and it is caught.

Permutation invariance is the companion property, split out because it needs a second input:
`test_the_reconstruction_cannot_see_the_order_it_is_given` rotates the input and compares the whole
result, and `test_the_reconstruction_is_not_given_anything_it_could_order_by` reads the same claim off
the dataclass fields, so it fails when an orderable field is *added* rather than when something starts
using it.

**Why the named shapes are still here, and what they are for.** A property over generated input is
worth nothing if the generator is narrow, and it cannot discriminate: a reconstruction that declared
*every* message unlinked under one value satisfies all four properties. So:

* `test_the_generator_reaches_every_shape_this_round_names` asserts every member of `SHAPES` is
  reachable from the real corpus, driven end to end;
* `test_every_value_of_the_linkage_vocabulary_is_one_the_product_can_produce` asserts **all nine**
  `Linkage` members are produced by the product across two runs — the ordinary corpus reaches eight,
  and PF-2's no-headers branch reaches `HEADERS_UNOBSERVED`. A closed vocabulary wider than the code
  is a claim wider than the code, and this is that question asked of the vocabulary this round adds;
* `test_each_declared_gap_is_the_one_the_headers_actually_produce` pins nine specific rows to nine
  specific gaps, so the values discriminate. `t-broken`'s `b2` and `t-subject`'s `s3` are adjacent
  rows of similar threads that land in different gaps because one carried an unreadable reply header
  and the other carried none.

---

## 4. How authorship is distinguished from mention, and what happens when I cannot tell

**The distinction, mechanically.** `structure/participants.py` keeps **five** roles apart, and each is
a different fact about one message:

| Role | Evidence |
|---|---|
| `AUTHOR` | the address is the **sole** address of this message's `From` |
| `COAUTHOR` | `From` named this address **and others** (RFC 5322 §3.6.2 permits it) |
| `RECIPIENT` | the address is in `To` or `Cc` |
| `REPLY_TO` | the address is in `Reply-To` — a routing directive the *sender* asserts |
| `MENTION` | the address appears in text this response observed for the message, and in **none** of that message's address headers |

`ParticipantFacts` holds five disjoint message-id lists, not one membership list with a role beside
it: an address can author one message of a thread and be merely named in the next, and a shape that
could hold only one role per address would force a choice between those facts — which is how a mention
comes to be reported as authorship. `wrote_here` on the wire is a **computed** field over the two
authorship lists, so a caller cannot receive a "this person wrote here" flag that disagrees with the
lists printed beside it.

**Identity is the address, never the display name.** No display name is joined to an address anywhere
in this module or on the wire; `ThreadParticipant` has no `display_name` field. What survives is
`distinct_display_names`, a count, which answers the one question a display name can honestly answer:
*did this address present itself under more than one name in this thread?* The corpus plants
`From: "Ana Ito" <mallory@elsewhere.invalid>` and
`test_a_display_name_cannot_make_someone_the_author_of_a_message` asserts that message is authored by
mallory, that ana's real address authored nothing in that thread, and that the serialised participant
block contains no occurrence of the display name at all.

**Where I cannot tell — four cases, each declared rather than guessed.**

1. **A bare name in text is never resolved to an address.** "Ana said we should ship" attributes a
   mention to nobody. Mapping a name to an address needs a directory this product does not have, and
   inventing one is the same class of guess as re-parenting an orphan by date. The response carries
   `name_only_mentions_resolved: false` on every structural block — a constant the model *refuses* to
   let be `true` — so an empty `mentioned` list cannot be misread as "nobody was named"
   (`test_a_bare_name_in_text_is_never_resolved_to_an_address`).
2. **A `From` that yields no address has no author.** Not attributed to the previous message's sender,
   not to the thread's root, not at all. The message is listed in
   `ThreadStructureReport.authorship_unknown`
   (`test_a_message_with_no_readable_from_has_no_author_and_the_response_says_so`).
3. **A multi-address `From` is co-authorship, and is not promoted.** Which of them held the pen is not
   something the headers say
   (`test_a_from_naming_two_people_is_coauthorship_and_is_not_promoted_to_authorship`).
4. **A mention could not be looked for.** Two ways, both declared identically in
   `mentions_not_scanned`: no text arrived (PF-2 leaves even `snippet` open), or **no address headers
   arrived** — and without those a mention is not computable at all, since a mention is defined by
   what this message's own headers do *not* account for. This second case is a correction I made
   during the round: the field was originally derived from `text_observed`, which would have reported
   "no text" about a row a snippet had arrived with. `MessageParticipants.text_observed` is now
   truthful about the response and `mentions_scanned` is the derived predicate, and both are executed
   (`test_when_no_text_was_observed_mentions_are_declared_unscanned_rather_than_absent`,
   `test_under_pf2s_no_snippet_branch_the_unscanned_rows_are_named_end_to_end`).

Header text that is really prose never becomes an address: `email.utils.getaddresses` returns the
whole value for such a header, so its output is a candidate and not a result, and `is_an_address` —
one implementation, in the module every layer already imports, per R-ARCH-031 — is applied both at
extraction and at the wire boundary. `ThreadParticipant(address="Please review the attached NDA
before end of day.")` is unconstructible
(`test_header_text_that_is_really_prose_never_becomes_an_address`).

---

## 5. Ordering — and a defect I found in code I did not write

**The acceptance asked for a test where the API array order is not `internalDate` order.** Building
it found a real defect one layer down, in `gmail/client.py::_thread_scalars`:

```python
key=lambda index: (int(thread.messages[index].internal_date or "0"), index)
```

The tie-break was the **array index**. Where every `internalDate` differs, the index decides nothing,
so the sort *looked* order-independent and had been tested as though it were — "one shape validated,
peers trusted", at the one place amendment A3 exists to defend. Two messages of a thread stamped in
the same millisecond are an ordinary shape (a self-copy, a list expansion, a resend), and under the
old key their positions came out of the order Gmail happened to send the array in, which the API does
not promise and STR-03 says chronology must never depend on. Every fixture in this repository before
this round returned the array already sorted, which is exactly how such a dependence survives a suite.

**Fix.** The tie-break is the message id — a fact of the response rather than of its ordering — so the
position map is now a function of `{id: internalDate}` alone. It is **a** chronological order rather
than *the* one: with equal timestamps every relative order is chronologically valid, and which of them
a caller sees is settled by an id rather than by time. The response declares that, per thread, in
`ThreadStructureReport.tied_on_internal_date`, so the position claim cannot be read as stronger than
the evidence behind it.

**Executed.**

* `test_the_array_order_gmail_returns_does_not_change_the_representation` runs one query twice against
  the same corpus, once with `threads.get` returning its array in `internalDate` order and once
  reversed, and compares `(thread, id, position, linkage, parent)` for every row. The fixture asserts
  a reordering permutes rows and changes nothing else.
* `test_two_messages_stamped_in_the_same_millisecond_order_the_same_way_either_way` is the tie case,
  and asserts the declaration is present for the tied thread and empty for an untied one.
* Replant **R32** puts the array index back and is caught.
* Replant **R33** makes the thread map read the array order instead of the sealed positions and is
  caught.

Positions themselves are still read off the sealed observation and never computed in the map — a
second sort would be a second derivation of one fact, and the two could disagree.
`ThreadMap.build` **raises** rather than inventing an order the observation declined to state
(`test_a_thread_map_will_not_invent_a_position_the_observation_declined_to_state`).

---

## 6. L4, and what it deliberately does not do

**What it expands on is a fact, not a resemblance.** A message whose `In-Reply-To`/`References` names
a `Message-ID` its own thread does not hold is saying, in its own headers, that a parent exists
elsewhere. L4 asks Gmail for exactly that message by `rfc822msgid:`, and each thread that recovers
becomes a separate `source` with its own map, capped at `max_source_threads = 4`.

* **Scope is preserved by calling, not by restating.** The `q` is composed through
  `search_region_of` — the same one derivation `ExactOperatorRung` and `BroadeningRung` read — so a
  region operator nobody has added yet is carried onto L4's probes too.
  `test_structural_expansion_carries_the_region_the_query_named` is parametrised over
  `REGION_DECLARING_FRAGMENTS`, the population read from `KIND_BY_OPERATOR` rather than a written
  list, and `test_the_expansion_never_leaves_the_region_the_query_named_at_the_wire` checks the
  double's own record of every `q` and `includeSpamTrash` it was actually sent. Replant **R37**
  removes the region and is caught by both.
* **A recovered row does not claim the query matched it.** The probe is an identifier lookup
  *MailWeave composed*, so `role: matched` on it would be a confident-looking over-claim. The
  recovered message is `role: parent` with `reply parent of <child>`, and its own direct reply is
  `role: child` with `reply child of <parent>` — its own relation, not a copy of its neighbour's.
  `ReplyParentOf` and `ReplyChildOf` had existed in `reasons.py` since WS-03 with **nothing able to
  produce them**; this round is the producer, so that part of the reason vocabulary stops being wider
  than the code (`test_no_row_of_a_recovered_thread_claims_the_query_matched_it`,
  `test_a_structurally_included_row_names_the_relation_that_put_it_there`).
* **Caps are dispositions, not silences.** A thread past `max_source_threads` converts its hits into
  `withheld` records under the new `WithheldCap.MAX_SOURCE_THREADS` with a `mailweave_thread_map`
  affordance. More unresolved parents than `MAX_STRUCTURAL_PROBES` is a `not_tried{rung: L4, why:
  cap}` with an executable way to raise it. A `Message-ID` that cannot be put into a query — over
  length, or carrying Gmail's own query punctuation — is skipped and declared, never truncated: a
  shortened identifier is a different identifier and `rfc822msgid:` is exact.
* **The disposition sweep is over the ledger, not over the caps.** Round 19's assembly withheld
  `plan.hit_ids` for a capped thread, which was every id in it while `messages.list` was the only
  route putting ids there. L4 is a second route, so a cap enumerating what *it* knows about would
  under-count by exactly the ids the newer route contributed — and `certify` would refuse the
  response. `_withhold_undisclosed_threads` asks the ledger what it observed instead, so a third route
  inherits the disposition without editing that function. Replant **R38** empties the sweep and is
  caught.
* **What it does not do, in the response and not only here.** D.6 lists four sibling-discovery
  signals; only the identifier lookup is exact. Normalised subject, participant overlap and forward
  detection are *similarity judgements*, and a source assembled from one would be MailWeave asserting
  a relationship nobody's headers state. The response carries
  `not_tried{rung: "structural_similarity", why: not_applicable}` so an absent source cannot read as
  an absent relationship (`test_the_similarity_signals_this_round_did_not_build_are_named_in_the_response`).

`_not_tried`'s docstring — which previously said L4/L5/L6/LR are absent because they are not built —
was corrected: L4 now reports itself, `not_applicable` when nothing held an unresolved parent
(`test_l4_reports_itself_not_applicable_when_no_thread_held_an_unresolved_parent`).

---

## 7. Every docstring claim about what reconstruction guarantees, with executed evidence

| Claim (module, paraphrased from its own words) | Executed by |
|---|---|
| `reply_tree`: "a parent is a fact read off the child's own RFC reply headers, or there is no parent" | `test_no_row_is_attached_to_a_parent_its_own_headers_do_not_name` (end to end, checked against the mailbox's own headers, not against the reconstruction's output); property 2 of the commonality test; replant **R29** |
| `reply_tree`: "`reconstruct` never sees a date … it is something it cannot do" | `test_the_reconstruction_cannot_see_the_order_it_is_given` (permutation, whole-result comparison); `test_the_reconstruction_is_not_given_anything_it_could_order_by` (the dataclass fields) |
| `reply_tree`: "every message gets exactly one `Link`, one closed-vocabulary `linkage`" | property 1 |
| `reply_tree`: "a link names a parent of this same thread, under an id in the child's own headers that is the id that parent carries" | property 2 |
| `reply_tree`: "following `parent_id` upward terminates: the result is a forest" | property 3; replant **R30** |
| `reply_tree`: "an id two messages carry resolves to neither" | `test_each_declared_gap_is_the_one_the_headers_actually_produce[t-dup/d3]`; replant **R31** |
| `reply_tree`: "a link that closes a cycle — including a self-reference — is refused for every member of that cycle" | the same parametrised test over `c1`, `c2`, `r1`; property 3 |
| `reply_tree`: "a message whose headers were not observed is neither linked nor declared parentless" | `test_every_value_of_the_linkage_vocabulary_is_one_the_product_can_produce` (PF-2 no-headers branch, end to end) |
| `reply_tree`: "`NO_REPLY_HEADERS` carries AD D.6's published string verbatim" | `test_the_orphan_linkage_carries_the_string_the_architecture_published` — the literal string is asserted |
| `reply_tree`: the D.4a narrow reading (`can_be_a_parent` beside a header-backed link) | `test_a_message_with_no_message_id_still_gets_the_link_its_own_headers_support`; property 4 |
| `reply_tree`: "raises on two rows under one Gmail id rather than collapsing them" | `test_a_reply_tree_over_two_rows_under_one_gmail_id_is_refused_rather_than_collapsed` |
| `threadmap`: "derives nothing it was not given; raises rather than inventing an order" | `test_a_thread_map_will_not_invent_a_position_the_observation_declined_to_state`; replant **R33** |
| `threadmap`: "text is passed in, never fetched" | true by signature; the consequence is executed by `test_under_pf2s_no_snippet_branch_the_unscanned_rows_are_named_end_to_end` |
| `structure/__init__`: "nothing here fetches, caches or persists — no persistent graph" | `test_one_threads_get_per_thread_and_never_two` |
| `participants`: the five roles are kept apart | `test_every_participant_role_is_one_an_index_can_actually_report` (all five produced by `roles_in`); `test_an_address_a_message_only_names_is_not_an_address_that_wrote_it`; replants **R34**, **R35**, **R36** |
| `participants`: "identity is the address, never the display name" | `test_a_display_name_cannot_make_someone_the_author_of_a_message` |
| `participants`: the three "cannot tell" statements | §4, items 1, 2 and 4; replant **R41** |
| `participants`: "no header or body text reaches this module's output" | `test_header_text_that_is_really_prose_never_becomes_an_address` |
| `client._thread_scalars`: "the tie-break is the message id … a function of `{id: internalDate}` alone" | `test_two_messages_stamped_in_the_same_millisecond_order_the_same_way_either_way`; replant **R32** |
| `structural`: "scope is preserved by calling `search_region_of`" | the `REGION_DECLARING_FRAGMENTS` sweep + the wire-level test; replant **R37** |
| `structural`: "every id these probes return is in `H`; a capped thread becomes withheld records" | `test_sibling_threads_beyond_the_cap_are_withheld_rather_than_dropped`; `test_every_message_the_ladder_and_the_expansion_saw_is_still_accounted_for`; replant **R38** |
| `structural`: "`not_tried` carries `structural_similarity` as `not_applicable`" | `test_the_similarity_signals_this_round_did_not_build_are_named_in_the_response` |
| `wire.MessageRow.linkage`: "required rather than defaulted" | `test_a_message_row_carries_exactly_one_linkage_and_it_is_never_absent`; replant **R39** |
| `wire.MessageRow`: "a parent beside a declared gap is not representable" | `test_a_parent_beside_a_declared_gap_is_not_representable`; replant **R40** |
| `wire.Source`: "the summary cannot disagree with the rows; a claim names messages this source carries" | `test_the_structural_report_cannot_disagree_with_the_rows_it_summarises`, `test_a_reply_parent_outside_the_thread_is_not_representable`, `test_the_participant_index_cannot_cite_a_message_the_source_does_not_disclose` |

**Three claims I found wider than the code during the round and narrowed rather than defended.**

1. `_l4_not_tried`'s docstring said three entries were possible, including one for the
   `max_source_threads` cap. The code emits two; the source cap is a `withheld` record, and listing it
   as `not_tried` as well would be two accounts of one fact. Docstring rewritten to say that.
2. `assemble`'s module docstring said the module is "deliberately **not** WS-05's thread map". It is
   now. Rewritten, and the `not_found` paragraph corrected from "L4/L5/L6/LR are not built" to
   "L5/L6/LR".
3. `participants`' `text_unobserved` reported "no text" about a row a snippet had arrived with when its
   headers had not. Split into a truthful `text_observed` and a derived `mentions_scanned` (§4, item 4).

---

## 8. The one place I read a governing document narrowly, recorded rather than glossed

AD **D.4a** says: *"A missing `Message-ID` yields `linkage: 'no Message-ID'` (D.6), never a guessed
parent."*

`Linkage.NO_MESSAGE_ID` is given to the message that sentence is the whole story for: **no
`Message-ID` observed and no parent named** — nothing structural is known about it in either
direction. Where a message carries no `Message-ID` but its **own** `In-Reply-To` names a parent this
thread holds, MailWeave states the link and sets `Link.can_be_a_parent = False` beside it.

**Why.** Refusing a link the child's own headers support would discard evidence that was actually
read, and D.4a's clause forbids *guessing* a parent, which stating a header-backed one is not.
`can_be_a_parent` is the other half of the same fact and is the half a caller needs: it says that any
reply to this message will arrive unlinked however well-formed the reply is.

This is a reading, not a derivation, and **R-RETR should rule on it.** It is executed either way:
`test_a_message_with_no_message_id_still_gets_the_link_its_own_headers_support` asserts both branches,
so reversing the decision is a one-line change with a test that says what changed.

---

## 9. "Have I trusted a peer?" — where I looked, and what I found

The question, asked of each new population rather than answered in general:

* **`Linkage`, 9 members.** Asked, and it *was* short: eight members were reachable from the corpus
  and `HEADERS_UNOBSERVED` was reachable only at the unit, because no fixture in this repository could
  produce a `threads.get` row with an `internalDate` and no `payload`. I added
  `metadata_returns_headers` to the double for PF-2's third branch and
  `test_every_value_of_the_linkage_vocabulary_is_one_the_product_can_produce` now asserts the set of
  reached values **equals** `set(Linkage)`, so a member added later without a producer fails.
* **`ParticipantRole`, 5 members.** Asked, and it was short in a worse way: `RECIPIENT`, `REPLY_TO`
  and `MENTION` were enum members **no code path produced** — a vocabulary wearing an enum's clothes.
  I added `ParticipantFacts.roles_in`, written against the five lists so a role the object records and
  the method forgets is not expressible, and
  `test_every_participant_role_is_one_an_index_can_actually_report` asserts the produced set equals
  `set(ParticipantRole)`.
* **Reply-tree shapes.** The whole of §3 is this question answered by a property rather than a list.
* **Region operators at L4.** Not enumerated: the sweep is over `REGION_DECLARING_FRAGMENTS`, read
  from `KIND_BY_OPERATOR`, so a region operator registered tomorrow joins it with no edit here.
* **`WithheldCap`.** One member added, exercised end to end.
* **Row-construction sites.** Making `linkage` required rather than defaulted forced every one of the
  23 `MessageRow(...)` construction sites in the tree to be updated, which is the point: a default would have made
  "every unlinked message says so" a comment beside a declaration, which is exactly what R-RETR-038
  found for `mailbox` in round 18.

**Where I have *not* closed it, honestly.** The `ThreadStructureReport` fields are a population of
five gap declarations and I did not write a sweep asserting each is individually reachable end to end;
four of the five are (`authorship_unknown`, `mentions_not_scanned`, `tied_on_internal_date`,
`name_only_mentions_resolved`), and `linked`/`unlinked` are re-derived by the model. A reviewer
wanting the same treatment as `Linkage` would be right to ask for it.

---

## 10. What I could not establish

* **Nothing here is evidence for OD-6's milestone.** Every test in this round runs behind
  `httpx.MockTransport` with sockets denied. OD-6 says in terms that unit tests and mocks are not
  evidence for criteria 2 and 3. This round moves criterion 4 forward on the *shape* of the data —
  stable structural handles, truthful scope on L4's probes, provenance on every row including the
  sibling sources — and establishes none of it against real mail.
* **PF-1 and PF-2 remain open and this round leans on both.** PF-2 decides whether
  `format=metadata` really returns the eight `metadataHeaders`, `snippet` and `internalDate`. All
  three branches now have a fixture switch and a test, so the product degrades in a declared way under
  each — but which branch is real is a fact about Gmail (**R-GMAIL**). PF-1 decides whether
  `threads.get`'s array can be short of the thread; `GMAIL-03`'s discrepancy bound is `[UNSET]` and no
  code here can measure it.
* **STR-01's manifest accuracy figure is not measurable here.** The criterion asks for 100 % link
  accuracy against the seeded corpus manifest. This round has no seeded corpus and the server may not
  name one (the ground-truth-isolation guard); what I can say is that on the constructed corpus every
  link is header-backed and every non-link is declared, which is the property, not the metric.
* **STR-02's `{display_name, address}` pair exposure is not built.** The criterion requires From/To/
  Cc/Reply-To to be *exposed* as unjoined pairs. The retrieval index is address-keyed, which is WS-05's
  half; exposing the pairs is header disclosure on the row, which is **WS-11**'s surface and does not
  exist. `ThreadParticipant` deliberately has no `display_name` field, and I have said so in its
  docstring rather than leaving a reader to infer that the pair requirement was met.
* **`Linkage.HEADERS_UNOBSERVED` is reachable in the product only if Gmail can return a thread row
  with `internalDate` and no `payload`.** The fixture can; whether Gmail can is R-GMAIL's.
* **No score, no ranking, no degradation ladder.** Unchanged from WS-04: L6 and WS-11 own those.
* **The three items RESUME.md lists as owed to the owner are untouched** — OAuth consent status, the
  two OAuth client files in history, and the retry/backoff curve (250 ms base against Google's
  documented 1-2-4 s). I did not touch a retry constant.

---

## 11. Not reachable from code that exists today (AGENT_LOOP §5a), and OD-6's question for each

| Item | Workstream | Blocks integration under OD-6? |
|---|---|---|
| `{display_name, address}` pair exposure on the row (STR-02, INJ-05) | **WS-11** disclosure + **WS-14** injection posture | **No.** The retrieval index keys on the address, which is what makes "what did X say" correct today; exposing the pair is a disclosure surface the milestone does not need. |
| `map_id` on a `Source`, so a structural map is redeemable | **WS-06** | **No** for this round; **yes** for milestone criterion 4's "stable handles". WS-06 is the next workstream in OD-6's order and depends on WS-05, which is now built. |
| Reply-chain floor promotion (parents/children to deeper content, OD-3) | **WS-11** | **No.** Membership is already absolute here — every message of a mapped thread is a row and `included == stated_total` — which is the half OD-3 calls absolute. Depth is WS-11's. |
| Similarity-based sibling discovery: normalised subject, participant overlap, forward detection (D.6) | **WS-09** ranking / **WS-08** semantic, which have the machinery to score and declare a soft relationship | **No.** Declared in the response as `not_applicable` rather than absent. |
| `outcome: not_found` ever being emitted | **WS-10** | **No.** `inconclusive` is the honest outcome while L5/L6/LR are unbuilt. |
| GMAIL-03's discrepancy bound; PF-1; PF-2's three branches | **G0 / R-GMAIL**, against a real account | **Yes for the milestone's criteria 2–4**, and only there. Nothing before a live account can settle them, which is OD-6's own named blocker. |
| Amendment A1's external content witness | **WS-13 / WS-16** | **No.** Same standing as every prior round: this round's guarantees are exactly as trustworthy as "I executed this call", and that is not checkable in-process. |

**Under OD-6's counter-rule.** This round produced integration progress rather than an audit: WS-05 is
built, it is the first of the five workstreams OD-6 names, and it unblocks WS-06 (handles need maps).
I found and fixed one genuine correctness defect in existing code — the array-index tie-break in
`_thread_scalars`, §5 — but I am **not** naming it a critical correctness or safety defect and it did
not postpone anything: it was reachable, it was in my own diff's blast radius, and it is fixed with a
replant defending it.

---

## 12. The reintroduction run

`tests/fixtures/replants.py` gains **R29–R41**, one per behaviour this round changed. The harness is
round 19's and unmodified: it copies the **whole** tree (`docs/` included — verified), asserts
`mailweave`, `mailweave_harness` **and** `tests` all resolve inside the copy and none into the working
tree, asserts each anchor matches **exactly once** before writing, asserts the file's digest changed
after, and runs every named test on the pristine copy first so a CAUGHT row is a test that changed its
mind rather than one already failing.

```
plant                                                                  anchors changed caught
R29-an-orphan-is-re-parented-to-the-first-message-of-the-thread              1 True    True
R30-a-reply-cycle-is-kept-instead-of-refused                                 1 True    True
R31-an-ambiguous-message-id-resolves-to-whichever-came-first                 1 True    True
R32-chronological-ties-break-on-the-array-index-again                        1 True    True
R33-the-thread-map-reads-the-array-order-instead-of-the-sealed-positions     1 True    True
R34-a-mention-is-counted-as-authorship                                       1 True    True
R35-a-senders-own-address-in-their-own-body-becomes-hearsay-about-them       1 True    True
R36-a-multi-address-from-is-promoted-to-sole-authorship                      1 True    True
R37-structural-expansion-drops-the-region-the-query-named                    1 True    True
R38-a-capped-sibling-thread-is-dropped-instead-of-withheld                   1 True    True
R39-linkage-is-optional-on-a-row                                             1 True    True
R40-a-parent-may-be-named-beside-a-declared-gap                              1 True    True
R41-a-message-whose-text-was-never-observed-reports-no-mentions              1 True    True
```

Two round-18 anchors (**R9**, **R21**) rotted when WS-05 moved the row-building loop out of `assemble`
into `_rows_of`; both were **re-anchored where the code moved**, which
`test_every_replant_anchor_matches_exactly_once_in_the_tree` caught rather than my noticing. That test
earned its keep this round.

Pinned counts moved with the schema, each with the reason recorded beside it: the audited field census
**213 → 231**, the wire tree's after-validator total **43 → 47** (all four in the structural models,
`Envelope`'s own share unchanged).

---

## 13. Gates

```
$ ruff check .
All checks passed!

$ ruff format --check .
165 files already formatted

$ mypy
Success: no issues found in 139 source files

$ python -m tools.guards
guards clean: forbidden-import, generative-client, gmail-endpoint, ground-truth-isolation,
scope-literal, unaudited-disk-write, unwrapped-http-client over server/src

$ pytest -q -m "not network"
2369 passed in 107.33s (0:01:47)

$ python tools/rubric_status.py --check
criteria: 113  (mandatory 110, conditional 2, optional 1)
status:
  PASS         6
  FAIL         0
  BLOCKER      0
  NOT TESTED   107
reviewer transitions recorded: 11
gate-blocking criteria (NOT TESTED / FAIL / BLOCKER): 106
```

No rubric criterion was marked PASS. ROUTE-01 was not restored. `FINDINGS_LEDGER.md` and
`RUBRIC_TRANSITIONS.md` are untouched. No retry or backoff constant was changed. No reviewer probe set
under `/tmp/rretr*/` was read. `generative_llm_calls` remains 0 and no test opens a socket.
