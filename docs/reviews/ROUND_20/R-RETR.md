# ROUND 20 — R-RETR review (the tree does not guess; the *claims about other threads* do)

**Reviewer:** R-RETR, independent instance, 2026-09-05. Sole gating reviewer for round 20.
Verified by execution per `AGENT_LOOP.md` §4/§5/§5a, classified for severity **and** urgency per
**OD-6**. **Source, tests and docs untouched** — every probe ran from `/tmp/rretr20/*.py` against the
real tree; every plant ran in a scratch copy under `/tmp/rretr20/t_*`, each a **full** copy including
`docs/`, with `PYTHONPATH` set and `mailweave.__file__`, `mailweave_harness.__file__` **and**
`tests.__file__` asserted to resolve inside it and asserted *not* to resolve into `/root/mailweave`.
Probe files are named against every number below.

Nothing in `/tmp/rretr15` … `/tmp/rretr19` was used to build any of my sets; I read `mytree.py`'s
scratch-tree pattern from round 19 and rewrote it, and took nothing else. My vocabulary is invented
(`zorbal`, `mirephant`), my senders are `.example` / `.invalid`, my mailboxes, shapes and oracles are
mine, and every oracle here is written out in the probe file rather than borrowed from a product
predicate. No fixture below contains real or realistic personal mail text.

---

## Environment

| Gate | Result (run twice: before all probing, and again after) |
|---|---|
| `ruff check .` | All checks passed |
| `ruff format --check .` | 165 files already formatted |
| `mypy` (strict) | Success, 139 source files |
| `python -m tools.guards` | 7 guards clean (forbidden-import, generative-client, gmail-endpoint, ground-truth-isolation, scope-literal, unaudited-disk-write, unwrapped-http-client) |
| `pytest -q -m "not network"` | **rc 0**; independently re-counted via `--collect-only -q` summed per file = **2,369** |
| `pytest -m replant` | **4 passed** — the replant tests are in the default gate, not deselected from it |
| `tools/rubric_status.py --check` | criteria 113; **6 PASS / 0 FAIL / 0 BLOCKER / 107 NOT TESTED**, 11 transitions — unchanged |

`mailweave.__file__` → `/root/mailweave/server/src/mailweave/__init__.py`. The implementer's window
closes at `docs/reviews/ROUND_20/IMPLEMENTER.md`, 03:32 UTC; the newest code file is
`tests/fixtures/replants.py` at 03:22. Nothing under `server/`, `tests/`, `tools/` or `harness/` has a
modification time inside my review window (03:40 onward). **This file is the only thing I wrote.**

The implementer's §13 gate block is accurate as printed. The "2,290 currently pass" in the work order
was measured on a tree that was **not green** — I did not re-derive that, but the report's §0 account
of it is consistent with the artifact that is on disk and with the three tests it names.

---

## Reachability and urgency, as I applied them

* **Reachability (§5a).** REACHABLE = reproducible today by driving `analyse` → `LadderRunner.run` →
  `assemble` (or `reconstruct`/`_thread_scalars` directly) with a synthetic mailbox behind
  `httpx.MockTransport`. REACHABLE-IF-GMAIL = the code path exists and is defect-free only under an
  assumption about what Gmail returns that no in-process test can settle.
* **Urgency (OD-6).** *Blocks WS-06* = would make a handle wrong, or would make the thing a handle is
  minted over unstable. Everything else *rides along*. I applied that literally, and one finding
  (R-RETR-051) lands in a third place: it does not block WS-06 but WS-06 must know it before it
  chooses what `mapping_digest` covers, and I say so on the finding.

**No finding below is a critical correctness or safety defect in OD-6's sense.** I looked for one
specifically, because OD-6's counter-rule means that if I do not find one, integration proceeds.
I did not find one, and I say so plainly in the verdict.

---

# Part 1 — Trying to make it guess

The property under attack is the module's own: *a link is a reading of the child's own headers.*
`/tmp/rretr20/p1_guess.py` drives `reconstruct` directly over thirteen shapes; `/tmp/rretr20/p20_headers.py`
attacks the extractor; `/tmp/rretr20/p19_shapes.py` drives the named shapes end to end.

**Inside a thread I could not make it guess.** Every one of these produced a header-backed link or a
declared gap, and never a parent the child's own headers do not name:

| Attack | Result |
|---|---|
| `References` of 3 hops, none held | `named parent is not in this thread`, no parent |
| `References` of 3 hops, only the root held | linked to the root, `linkage: references` (JWZ's own fallback: the nearest *available* ancestor) |
| root **and** nearest ancestor both held | linked to the **nearest**, i.e. `References` is read right-to-left |
| `In-Reply-To` says A, last `References` says B, both held | A — IMAP-REFERENCES order |
| case-varied `Message-ID` (`<A@X>` vs `<a@x>`) | gap, not a link (errs toward declaring) |
| whitespace inside the brackets, `<>`, empty, over-900-char inner | no `Message-ID` extracted; safe direction |
| folded / comma-separated / commentary-carrying `References` | every `<msg-id>` extracted, in wire order |
| self-reference, 2-cycle, cycle with a tail | every edge **on** the cycle refused; the tail keeps its own header-backed parent |
| duplicate `Message-ID` inside the thread | `AMBIGUOUS_PARENT`; neither picked |
| empty thread / single message / all-orphan thread | no link, no crash, gap declared on every row |
| subject change mid-thread, forward, header present-and-empty | linked on headers; the forward declared an orphan; the empty header `reply headers carried no readable Message-ID` |

Permutation invariance holds at both layers. `/tmp/rretr20/p7_order_e2e.py` runs **all 24** array
permutations of a four-message thread through the full ladder and compares
`(thread, id, position, linkage, parent, role, participant set)` for every row: identical in 24/24,
and identical again in 24/24 when every message shares one `internalDate`.

**Two guesses do survive, and both are one level out from `reconstruct` — in what L4 does with the
gap the tree declared, and in what the response then says about the row L4 brought back.** They are
R-RETR-049 and R-RETR-050.

## 1.1 R-RETR-049 — L4 chases the *oldest* named ancestor, and calls what it finds the parent

`reply_tree.reconstruct` resolves `References` right-to-left, because the rightmost entry is the
nearest ancestor — its docstring says exactly that, and the code does it. But when nothing resolves,
the id it records as `Link.evidence` is

```python
named = view.in_reply_to + view.references
...
evidence=named[0],
```

`named[0]` for a `References`-only child is the **leftmost** entry: the thread root, the farthest
ancestor. That id is `ThreadStructure.unresolved_parent_ids`' payload, which is L4's whole input, and
the row L4 recovers is then disclosed with `ReplyParentOf(child_id=...)` — rendered *"reply parent of
c1"*.

Executed end to end, `/tmp/rretr20/p2_l4_evidence.py` — a child in `t-child` whose `References` is
`<root@x.invalid> <mid@x.invalid> <par@x.invalid>` and no `In-Reply-To`, with the real parent
`<par@x.invalid>` in `t-parent` and the root `<root@x.invalid>` in `t-root`:

```
probe sent:  rfc822msgid:<root@x.invalid>
source t-root
    row r1 role parent reason: reply parent of c1 | linkage: date-adjacent (no RFC reply headers)
```

`r1` is three hops up. `c1`'s headers say it is an ancestor; the response says it is the parent. The
actual parent, in `t-parent`, was never probed and is not in the response.

The correction is one line, and it is the module's own rule applied to the same field:

```python
evidence=(view.in_reply_to[0] if view.in_reply_to else view.references[-1]),
```

Applied in a scratch tree, the same run recovers `t-parent` and *"reply parent of c1"* becomes true
(`/tmp/rretr20/t_evb_FIX-n`). **Nothing pins the current value.** I ran the whole suite with
`evidence` set to the nearest ancestor and again with it set to `named[-1]`, replants deselected in
both: **0 behavioural failures each time** (`/tmp/rretr20/p5b.py`). The only failure either way is
`test_every_replant_anchor_matches_exactly_once_in_the_tree`, because R29's anchor quotes the line.

## 1.2 R-RETR-050 — the ambiguity the tree refuses inside a thread is asserted twice across threads

`_resolve`'s docstring is the standard this project holds itself to: *"An id carried by two messages
resolves to nothing: picking either would be a guess dressed as a link."* At L4 that standard is not
applied. `/tmp/rretr20/p11_caps_disposition.py` puts two messages carrying one `Message-ID` in two
different threads:

```
t-sib-1x   s1x   -> reply parent of c1   (linkage date-adjacent (no RFC reply headers))
t-sib-1y   s1y   -> reply parent of c1   (linkage date-adjacent (no RFC reply headers))
```

`c1` has one reply parent. The response asserts two, in two sources, with no ambiguity declaration
anywhere. Inside a thread this exact shape is `AMBIGUOUS_PARENT`; across threads it is two confident
`role: parent` rows.

## 1.3 Two smaller asymmetries in the same principle (R-RETR-057)

* An `In-Reply-To` naming **two different** ids that this thread holds resolves to the **first**,
  silently (`p1_guess.py` case 6). One id held by two messages is refused; two ids each held by one
  message is arbitrated by wire order. Both are "the headers name more than one candidate".
* `_resolve` sets `ambiguous = True` and then keeps looking; if a later candidate resolves uniquely,
  the link is made and the ambiguity is **dropped**, appearing in no field (`p1_guess.py` case 7). A
  caller cannot tell that a duplicate `Message-ID` was seen in the thread it is reading.

Neither invents a parent, so both are LOW. I record them because the round's own thesis is that a
principle applied at one site and not its peers is the defect this project keeps producing.

---

# Part 2 — Is the Hypothesis property vacuous? No, and I could not make it be

Two questions, both answered by execution.

**Does it fail when each of the four properties is violated?** I planted my own violation of each in
a scratch tree (`/tmp/rretr20/p4_plant_properties.py`) — not the manifest's plants:

| Planted violation | Property | Caught |
|---|---|---|
| unobserved-header rows get no `Link` at all | 1 | **yes** |
| unresolved children linked to any message carrying a `Message-ID` | 2 | **yes** |
| only self-references refused; 2-cycles kept | 3 | **yes** |
| `can_be_a_parent = True` whenever a parent was found | 4 | **yes** |

**Is the generator's range wide enough for that to mean anything?** I sampled `header_views()` for
3,000 examples and classified the *facts* independently of the product
(`/tmp/rretr20/p3_generator_range.py`):

```
linkage values reached          all 9 of 9 (IN_REPLY_TO 317 · REFERENCES 276 · NO_REPLY_HEADERS 221
                                · NO_MESSAGE_ID 263 · UNPARSEABLE 496 · UNRESOLVED 2409
                                · AMBIGUOUS 620 · REPLY_CYCLE 734 · HEADERS_UNOBSERVED 4518)
duplicate Message-ID in one thread   544 examples
self-reference                      1030
cycle refused                        677
named parent absent                 1860
fully linked chain of length > 1      14
```

The generator reaches cycles, duplicates, self-references and absent parents without any of them being
enumerated, and every member of the closed vocabulary. This is not a list of cases wearing a property's
clothes. It is the strongest artifact in the round.

**What the property does not assert, and what that cost.** It never looks at `Link.evidence` on the
gap branch — which is exactly the field R-RETR-049 lives in. Property 2 constrains `evidence` only for
*resolved* links. That is a real hole in an otherwise excellent property, and it is why a MEDIUM
finding survived 400 examples × 46 test functions.

---

# Part 3 — Ordering and positions (A3, STR-03)

**The fix is real and I re-derived it.** `/tmp/rretr20/p6_ordering.py` drives `_thread_scalars`:

```
array reversed, all distinct                     positions={'m1':0,'m2':1,'m3':2}  tied=()
every message the same millisecond               positions={'ma':0,'mb':1,'mc':2}  tied=('ma','mb','mc')
tie, array order [mb, ma] vs [ma, mb]            identical under permutation: True
one row carries no internalDate                  positions=None, why_absent set  (all-or-nothing)
the same message id twice in one thread          positions=None, why_absent set
empty thread / single message                    None / {'only': 0}
```

End to end (`p7_order_e2e.py`): 24/24 permutations identical, and 24/24 identical on the all-tied
thread with `tied_on_internal_date` correctly naming all four rows.

**A3's bound raises rather than clamps** (`p7b_a3.py`): with `stated_total=2`, `position=0` and `1`
are accepted, `position=2`, `5` and `900` are refused at `Source` with A3's own message, and
`position=-1` is refused at `MessageRow`. Nothing clamps.

**One gap in the *declaration*, not in the order (R-RETR-055).** The sort compares
`int(internal_date)`; the tie declaration compares the `internal_date` **string**:

```
'01000' and '1000' - equal ints, unequal strings   positions={'m1':0,'m2':1}   tied=()
   -> ordering treated them as a tie: True | declared tied: ()
```

`GmailNumericId` is `[0-9]{1,N}`, so a zero-padded stamp validates. Two rows whose relative order was
settled by message id are then presented with no `tied_on_internal_date` entry — which is the one
thing that field exists to prevent. Whether Gmail ever zero-pads is R-GMAIL's; the *disagreement
between the two derivations* is here today and costs one line (`Counter(int(...))`).

---

# Part 4 — Authorship versus mention

## 4.1 I could not find a mention recorded as authorship

`/tmp/rretr20/p8_authorship.py` runs sixteen adversarial header shapes through
`participants_of_message` and `roles_in`. Every one lands correctly:

| Shape | Result |
|---|---|
| the sender's own address quoted in their own body | `author`, **not** mention (headers subtracted) |
| `"Ana Ito" <mallory@elsewhere.invalid>` | authored by mallory; ana authors nothing; no display name on the wire |
| an address only in a signature block | `mention` |
| `Reply-To` ≠ `From` | `reply_to`, never author |
| a forwarded original sender in the body | `mention` |
| `From` that is prose containing an address | **no author**, `unreadable_headers=('from',)`, `authorship_unknown` |
| `From: ana@x (mallory@y)` — an RFC comment holding another address | ana only |
| `From: undisclosed-recipients:;` | no author, declared |
| `From` naming two mailboxes | `coauthor` for both, not promoted |
| a recipient also named in the body | `recipient`, not mention |
| a `To` display name that is itself another address | that string never becomes an address |
| a 393-char `From` address | refused by `is_an_address`, declared unreadable |
| no `From` at all, addresses in the body | no author; the body addresses are mentions; declared |

The one asymmetry I found runs the **safe** way: `From: <.ana@team.example>` with `.ana@team.example`
in the body records the *sender* as a mention of a stripped variant, because `addresses_in_text`
applies `.strip(".")` and `addresses_in_header` does not. An author is understated; a mention is never
promoted. I am not filing it.

The response's own participant blocks reach all five `ParticipantRole` members
(`/tmp/rretr20/p15_roles_in_product.py`), not only the hand-built index the implementer's sweep uses.

## 4.2 R-RETR-051 — the mention scanner is handed the quote-stripped view, and the row says it was scanned

`assemble._observed_text` returns `processed.default_view` for a fetched body.
`DEFAULT_VIEW_CLASSES = {SpanClass.ORIGINAL}` — quoted and signature spans are **excluded**. So the
commonest mention shape in real mail, an address inside a quoted reply or a forwarded block, is never
seen. `/tmp/rretr20/p9_quoted_mention.py`:

```
default_view given to the mention scanner:
    'Agreed zorbal, let us ship on Friday.\n\nOn Tue, 2 Jun 2026, Cai wrote:'
full annotated text holds the quote: True
default view holds the quoted address: False

participants:  ana@team.example authored ('q1',) mentioned ()
structure.mentions_not_scanned: ()
```

`cai@team.example` is in the message, is in `body_clean`, is returned by the unabridged path — and is
absent from the participant index, with the response stating that the mention scan *ran* on that row.
That last part is what makes it a finding rather than a policy choice: `mentions_not_scanned` is the
field a caller reads to know that "no mentions" is not a negative derived from an absence, and here it
is exactly that.

**The consequence is that the index is a function of the query, not of the thread**
(`/tmp/rretr20/p22_depth_dependence.py`, one thread, two queries):

```
query='zorbal'     participants: ana(authored w1), bo(authored w2)
query='mirephant'  participants: ana(authored w1), bo(authored w2), cai(mentioned w1)
```

Same thread, same mail, two different answers to "who is named here", because a different row happened
to be the hit and therefore got its body fetched and its quotes stripped. `p10_depth_asym.py` shows
the two halves side by side in one response: the same quoted line yields a mention on the stub row and
nothing on the body row.

**Nothing pins the current input.** I changed `_observed_text` to hand over `processed.body_clean.text`
and ran the whole suite, replants deselected: **rc 0, 0 failures** (`/tmp/rretr20/p24_fixprobe.py`).

## 4.3 R-RETR-052 — a truncated snippet mints an address that is in no message

The scanner treats whatever text it is given as whole. A `snippet` is a truncation by construction, so
an address straddling the cut becomes a **different address**, and it passes `is_an_address` and the
`ThreadParticipant` validator because it is still shaped like one. Deterministic reproduction,
`/tmp/rretr20/p23c.py`:

```
snippet: 'xxxxxxxxxxxxxxxx On Mon Cai wrote:\n> loop in cai@team.exampl'
participant addresses on the wire: ['ana@team.example', 'bo@team.example', 'cai@team.exampl']
addresses in the response that appear in NO message of this mailbox: ['cai@team.exampl']
   is_an_address: True | mentioned in: ('w1',) | wrote_here: False
```

`cai@team.exampl` is a participant identity the response invented out of a cut string, and
`mentioned_only` — the hearsay set STR-02 scores — reports it. The same class applies to the
head-truncated `default_view` at A.9a's 250-token step, which is the other truncating input.

---

# Part 5 — Evidence preservation and provenance under the new paths

I could not break `H = disclosed ∪ withheld` anywhere.

**L4 overflow past `max_source_threads`** (`p11_caps_disposition.py`; 4 probes each recovering 2
threads, because one `Message-ID` is carried by two messages in two threads):

```
sources disclosed: t-hit, t-sib-1x, t-sib-1y, t-sib-2x, t-sib-2y
withheld:          s3x s3y s4x s4y   cap=max_source_threads
|H| = 14  disclosed = 10  withheld = 4
H == disclosed | withheld : True      disclosed & withheld : set()
```

**`max_hit_threads` overflow** (15 hit threads, `p12_more_caps.py`): 12 sources, 3 withheld under
`max_hit_threads`, `H` closed.

**A thread the observation left unplaced** (PF-2 branch a, no `internalDate` anywhere): 0 sources, a
`not_included_sources` entry naming the reason, `H` closed.

**Provenance on every row, including structurally added ones** — the spam siblings L4 recovered:

```
t-sib-1x  s1x  role=parent  observed=True  regions=()        outside=False
t-sib-1y  s1y  role=parent  observed=True  regions=('spam',) outside=True
```

**Scope is carried onto L4's probes.** With `in:anywhere` in the query, every probe was
`in:anywhere rfc822msgid:<…>` with `includeSpamTrash=True`. I re-derived the population question my
own way: `REGION_DECLARING_FRAGMENTS` is built from `KIND_BY_OPERATOR` and both polarities, not from a
list, so the sweep cannot be narrowed silently. My own independent plant that composes L4's `q` without
the region is caught (Part 8).

**One thing L4 does that nothing declares (R-RETR-053).** `StructuralPlan.skipped` — a named parent
whose `Message-ID` L4 refuses to put in a `q` (over-length, or carrying Gmail's query punctuation) — is
computed, documented as "a permanent inability", and **read by nothing**. `grep` over `server/src`
finds it used only inside `StructuralPlan.applicable`. `/tmp/rretr20/p13_skipped.py`, one probeable and
one unprobeable parent in one thread:

```
queries: ['zorbal', 'rfc822msgid:<ok@m.invalid>']
not_tried: [('L0','not_applicable'), ('L1b','not_applicable'), ('L2','not_applicable'),
            ('L3','not_applicable'), ('structural_similarity','not_applicable')]
```

No L4 entry at all. `_l4_not_tried` reports exactly two facts — `cap` and, only when **nothing** was
probed, `not_applicable` — and there is a third: *a probe declined while others ran*. The child's own
row still declares its gap, so nothing is lost silently at the message level; what is missing is the
rung's account of a lookup it chose not to make.

**One new disclosure surface (R-RETR-056).** L4 is the first rung whose `q` is composed from **mail
content**, and that `q` is disclosed verbatim in `scan_scope[].q`. `/tmp/rretr20/p18_wire_leak.py` and
`p21_zerowidth.py`:

```
.retrieval_report.scan_scope[1].q = rfc822msgid:<subject-to-the-attached-nda-review@evil.invalid>
scan_scope q = 'rfc822msgid:<hidden​‍directive@evil.invalid>'
```

Bounded (≤256 chars, one token, no whitespace, no `"{}()` ) and truthful — it is a `q` MailWeave really
ran. But it is sender-chosen text in a connector-voiced field with no fence and no `content.trust`
label, and round 10's format-character stripping runs in the content pipeline, not here. This is
R-SEC's and WS-14's to rule on; I record it because this round's diff opened the door.

---

# Part 6 — Ruling on the D.4a narrow reading

AD **D.4a** §4: *"A missing `Message-ID` yields `linkage: 'no Message-ID'` (D.6), never a guessed
parent."* The implementer gives `NO_MESSAGE_ID` only to the message with no `Message-ID` **and** no
parent named, and where such a message's own `In-Reply-To` resolves, states the link with
`Link.can_be_a_parent = False` beside it.

**On the reading itself I agree with the implementer.** The clause's named harm is *guessing*, and
stating a link the child's own headers support is not guessing; refusing it would discard evidence that
was actually read, which is the opposite of what A2, A7 and OD-5's third-state discipline all do
elsewhere. And the strict reading would force `Linkage` — a field whose documented meaning is *how this
message's reply parent was determined* — to carry a fact about the message's own `Message-ID` instead,
which is a different question.

**But the reading as shipped is not the reading as argued, and that is what I am ruling against.** The
justification rests on `can_be_a_parent` being *"the other half of the same fact and … the half a
caller needs"*. It is not a half a caller has. `grep` over the whole tree finds `can_be_a_parent`
inside `structure/reply_tree.py` and in tests, and **nowhere else**: not on `MessageRow`, not on
`ThreadStructureReport`, not on `Source`. `threadmap` does not read it; `assemble` does not read it.
Executed, `/tmp/rretr20/p17_d4a.py` — `d2` carries no `Message-ID` and its `In-Reply-To` resolves;
`d3` is an ordinary reply to the same parent; `d4` is a well-formed reply *to* `d2`:

```
d1  linkage='date-adjacent (no RFC reply headers)'    parent=None
d2  linkage='in-reply-to'                             parent=d1
d3  linkage='in-reply-to'                             parent=d1
d4  linkage='named parent is not in this thread'      parent=None

d2 vs d3 as serialised: identical in every field but id and position
=> distinguishable on the wire: False
```

So on the wire the message D.4a is about is indistinguishable from an ordinary reply, and its own
child reports *"named parent is not in this thread"* about a parent that **is** in this thread. A
caller has both halves of the puzzle and no way to join them.

**Ruling.** The narrow reading of D.4a **stands** — do not reverse the linkage. But it is conditional
on the compensating fact reaching the response, and today it does not, so as shipped the reading is not
the one that was argued for. Filed as **R-RETR-054** with the fix on the row rather than on the enum:
carry `can_be_a_parent` (or an equivalently named boolean) onto `MessageRow`, third state included
(`None` when no headers were observed), so `linkage: in-reply-to` beside `can_be_a_parent: false` says
what the module already knows. That also makes `d4`'s gap legible: its parent is present and
unnameable, which is a different repair from a parent in another thread. If the orchestrator prefers
the strict reading instead, the reversal is the one-line change the implementer says it is and
`test_a_message_with_no_message_id_still_gets_the_link_its_own_headers_support` says what changed — but
I do not recommend it, because it trades a visible gap for a discarded fact.

---

# Part 7 — The two "trusted a peer" gaps, and whether the sweeps are vacuous

Both sweeps assert **equality**, not containment: `reached == set(Linkage)` and
`reached == set(ParticipantRole)`. I confirmed they are not vacuous by adding a tenth `Linkage` member
and a sixth `ParticipantRole` member with no producer, in scratch trees
(`/tmp/rretr20/p14_sweep_vacuity.py`):

| Plant | Named sweep fails |
|---|---|
| `Linkage.PLANTED_UNPRODUCED` added, nothing produces it | **yes** |
| `ParticipantRole.PLANTED_ROLE` added, nothing reports it | **yes** |

I also independently confirmed the *range* of the `Linkage` sweep from the other side: my 3,000-example
generator sweep (Part 2) reaches all nine members from the reconstruction alone, and the end-to-end
sweep reaches eight plus `HEADERS_UNOBSERVED` from PF-2's third fixture branch. Both are real.

**One narrowing worth recording, which I resolved in the implementer's favour.**
`test_every_participant_role_is_one_an_index_can_actually_report` builds its index by hand from the
fixture's `Msg` fields with `observed_text=message.body` — the *raw* body — rather than reading the
roles off the response. Given R-RETR-051 that difference is exactly the one that matters, so the test
does not establish what its name says about the product. I established the product-level version
myself (`p15_roles_in_product.py`): reading only `Source.participants` from a real run, all five roles
are reached, missing = none. The claim holds; the test asserts it one layer in from the response.

The implementer's own §9 note — that `ThreadStructureReport`'s five gap fields have no equivalent sweep
— is accurate, and I would ask for it, but it is a LOW-value ask next to the two above.

---

# Part 8 — Replants

**The harness.** `make_scratch_tree` copies the whole tree with only `.venv`, `.git`, `__pycache__`,
`.*_cache` and `.hypothesis` excluded; I confirmed by execution that `docs/RELEASE_RUBRIC.md` exists in
the copy. `assert_imports_resolve_into_the_scratch_tree` probes all three packages and asserts both the
positive (inside the copy) and the negative (not under the working tree). `run_replants` proves the
named tests pass on the pristine copy before planting.

**I reproduced the whole table independently** (`/tmp/rretr20/replant_table.txt`, driving
`run_replants` from my own script rather than through pytest): **41 entries, anchors matching ≠ 1: none,
`changed=True` and `caught=True` on all 41**, R1–R41 including the two round-18 anchors
(`R9-provenance-is-not-the-observed-labels`, `R21-stub-rows-lose-their-provenance`) that rotted when
WS-05 moved the row-building loop into `_rows_of` and were re-anchored. Both match exactly once and
both still catch.

**Spot-check my own way.** A manifest can be tuned to its tests, so I wrote **ten of my own mutations**
of the same behaviours — different spellings, different files, different mechanisms — and ran the whole
suite against each with replants deselected (`/tmp/rretr20/p16_my_plants.py`). All ten caught, and the
first failure is a *behavioural* test each time, not the anchor test:

```
mine-R29-reparent-to-the-last-message                   caught  four-properties
mine-R31-ambiguity-picks-the-second-holder              caught  permutation invariance
mine-R32-tie-breaks-on-the-reversed-array-index         caught  array-order test
mine-R33-map-sorts-by-array-index                       caught  array-order test
mine-R34-mentions-appended-to-authored-at-aggregation   caught  generator-reaches-every-shape
mine-R35-mentions-no-longer-subtract-own-headers        caught  author-vs-hearsay disjointness
mine-R36-multi-address-from-promoted                    caught  participant-role sweep
mine-R37-L4-composes-without-the-region                 caught  region-carried sweep
mine-R38-cap-sweep-skips-L4-contributed-ids             caught  capped-sibling withheld test
mine-R41-mentions-scanned-drops-the-headers-half        caught  linkage vocabulary sweep
```

This is the strongest replant result I have seen in this project. The manifest is not tuned to itself.

**What the manifest does not defend**, and this is where R-RETR-049 and R-RETR-051 came from: no entry
covers `Link.evidence`'s choice among named ids, and none covers which text the mention scanner is
given. I demonstrated both by mutating them and getting a green suite (Parts 1.1 and 4.2).

---

## Findings

```
ID:            R-RETR-049
Severity:      MEDIUM
Reachability:  REACHABLE today. An ordinary query through LadderRunner.run + assemble against a
               mailbox holding one reply whose `References` names >1 absent Message-ID and whose
               `In-Reply-To` is absent - which is what a forward, a split thread or a
               list-expanded reply produces routinely.
Blocks WS-06?  NO - rides along. A handle is minted over the threads actually disclosed, so it
               stays internally consistent; the defect is in which thread that is and in what the
               row says about it. It should be fixed before WS-11 puts these reasons in front of a
               model, and it is a one-line change with a test.
Rubric:        STR-01 (a link derived from In-Reply-To/References), STR-05 (multi-thread assembly),
               contract C-02(a) and C-02(d) ("a mechanical reason naming the relation used"),
               AD D.6.
Location:      server/src/mailweave/structure/reply_tree.py, reconstruct - the unresolved branch
                 sets `evidence=named[0]` where `named = view.in_reply_to + view.references`, so a
                 References-only child records its LEFTMOST reference, the oldest ancestor. The
                 same function resolves References right-to-left one branch above, and the module
                 docstring states that rule.
               server/src/mailweave/structure/reply_tree.py, ThreadStructure.unresolved_parent_ids
                 - hands that id to L4.
               server/src/mailweave/retrieval/assemble.py, _rows_of - the recovered row is given
                 ReplyParentOf(child_id=entry.recovered_for), rendered "reply parent of <child>".
               server/src/mailweave/structure/reply_tree.py, Link.evidence docstring - "the one it
                 was looked for under when there is no parent" is not what the field holds: the
                 first id looked under was references[-1].
Repro:         /tmp/rretr20/p2_l4_evidence.py
                 t-child/c1  References: <root@x.invalid> <mid@x.invalid> <par@x.invalid>
                 t-parent/p1 Message-ID:  <par@x.invalid>      (the real parent)
                 t-root/r1   Message-ID:  <root@x.invalid>     (three hops up)
                 probe sent            rfc822msgid:<root@x.invalid>
                 disclosed             t-root/r1  role=parent  "reply parent of c1"
                 never probed          <par@x.invalid>
               /tmp/rretr20/p5b.py - whole suite, replants deselected, with `evidence` changed to
                 the nearest named ancestor: 0 failures; with it changed to `named[-1]`: 0 failures.
                 No behavioural test pins this field.
               /tmp/rretr20/t_evb_FIX-n - the same run under the correction recovers t-parent.
Expected:      The relation the row asserts is the relation the headers state. `References` is
               right-to-left (RFC 5322 s3.6.4, and this module's own docstring), so the parent a
               child names is `in_reply_to[0]` when present, else `references[-1]`.
Actual:        L4 chases the thread root, recovers it, and discloses it as the child's reply
               parent. The child's own row stays honest (`named parent is not in this thread`);
               the over-claim is on the recovered row's mechanical reason, which is the one place
               C-02(d) requires the relation to be named exactly.
Required fix:  `evidence=(view.in_reply_to[0] if view.in_reply_to else view.references[-1])`, and
               correct `Link.evidence`'s docstring to say which id it holds. Then extend property 2
               of `test_every_reply_tree_shape_keeps_the_four_properties_that_make_it_not_a_guess`
               to the gap branch - for an unresolved link, `evidence` is the nearest ancestor the
               child's own headers name - and add a replant. If the orchestrator would rather L4
               chase every named ancestor rather than one, that is a larger change and the reason
               string must then say "reply ancestor of", not "reply parent of".
```
```
ID:            R-RETR-050
Severity:      MEDIUM
Reachability:  REACHABLE today. Needs one Message-ID carried by messages in two threads - a
               resend, a list copy filed apart from the sender's own, a re-delivered message.
               Whether that is common in a real mailbox is R-GMAIL's; that the code has no
               defence is established here.
Blocks WS-06?  NO - rides along.
Rubric:        STR-01, STR-05, contract C-02(a) ("declared as unlinked rather than silently
               re-parented") and C-02(d); AD D.6; the reply tree's own AMBIGUOUS_PARENT rule.
Location:      server/src/mailweave/retrieval/assemble.py, _execute_structural_expansion -
                 `recovered.setdefault(thread_id, structural.for_child_id)` per returned id, so
                 one probe that returns two threads yields two sibling sources, each recorded as
                 recovered *for the same child*;
               server/src/mailweave/retrieval/assemble.py, _rows_of - each such row gets
                 ReplyParentOf(child_id=entry.recovered_for) with no arbitration and no
                 declaration;
               contrast server/src/mailweave/structure/reply_tree.py, _resolve, whose docstring is
                 the standard being broken: "An id carried by two messages resolves to nothing:
                 picking either would be a guess dressed as a link."
Repro:         /tmp/rretr20/p11_caps_disposition.py
                 t-sib-1x/s1x and t-sib-1y/s1y both carry Message-ID <absent1@m.invalid>
                 t-sib-1x   s1x   -> reply parent of c1
                 t-sib-1y   s1y   -> reply parent of c1
                 c1's own row: linkage 'named parent is not in this thread', reply_parent_id None
                 no ambiguity is declared anywhere in the envelope
Expected:      A child has one reply parent. Where the identifier lookup returns that identifier
               from more than one thread, MailWeave cannot tell which message the child named, and
               the answer it gives one level down is to declare rather than pick.
Actual:        Both are disclosed as `role: parent` with the same mechanical reason. A caller
               reading the response is told two different messages are the parent of one message.
Required fix:  Detect the shape where one L4 probe's returned ids span more than one thread (or
               more than one message), and either (a) disclose them with a relation that is true -
               a "named Message-ID matched in N places" reason and a declared ambiguity - or (b)
               withhold them under a declared ambiguity cap with the thread-map affordance. Either
               way `AMBIGUOUS_PARENT`'s reasoning has to reach L4. Test: the fixture above, plus a
               replant that removes the arbitration.
```
```
ID:            R-RETR-051
Severity:      MEDIUM
Reachability:  REACHABLE today. Any thread in which a matched row's body is fetched and the body
               quotes an address - the ordinary shape of a reply chain.
Blocks WS-06?  NO for correctness - but WS-06 must read this before it decides what
               `mapping_digest` covers. The participant index is not a function of the thread: it
               is a function of the thread AND of which rows this query matched. A digest that
               includes `Source.participants` would therefore differ between two redemptions of
               one handle at different disclosure depths and produce `handle_stale` for a thread
               nothing changed in. Digesting the map (ids, order, positions, linkages, parents)
               is safe today; digesting the participant block is not.
Rubric:        STR-02 ("what did X say" / authorship vs hearsay), contract C-02(b), I-2's
               "nested losses count ... declared in place", AD D.6 participants.
Location:      server/src/mailweave/retrieval/assemble.py, _observed_text - returns
                 `processed.default_view` for a fetched body;
               server/src/mailweave/content/annotate.py, DEFAULT_VIEW_CLASSES = {ORIGINAL} - so
                 quoted and signature spans are excluded from what the scanner sees;
               server/src/mailweave/structure/participants.py, MessageParticipants.mentions_scanned
                 - true whenever headers and *some* text were observed, so the narrowed input is
                 reported as a completed scan;
               server/src/mailweave/structure/threadmap.py docstring - "Mentions are scanned only
                 in text this response actually observed", which is wider than what is passed.
Repro:         /tmp/rretr20/p9_quoted_mention.py
                 body quotes cai@team.example inside "On Tue, 2 Jun 2026, Cai wrote:"
                 default_view handed to the scanner   'Agreed zorbal, ... On Tue, 2 Jun 2026, Cai wrote:'
                 body_clean holds the address          True
                 default_view holds the address        False
                 participants                          cai absent entirely
                 structure.mentions_not_scanned        ()      <- the row is reported as scanned
               /tmp/rretr20/p10_depth_asym.py - one thread, one quoted line: a mention on the stub
                 row, nothing on the body row, in the same response.
               /tmp/rretr20/p22_depth_dependence.py - one thread, two queries, two different
                 participant indexes.
               /tmp/rretr20/p24_fixprobe.py - scanning `processed.body_clean.text` instead: whole
                 suite green, 0 failures. Nothing pins the current input.
Expected:      Either the scan covers the text the response observed - which is what the module
               says - or the rows whose text was narrowed are named in `mentions_not_scanned`. An
               empty `mentioned` list must not be a negative derived from a narrowing the caller
               cannot see.
Actual:        The commonest mention shape in real mail is invisible, and the field that exists to
               declare an unscanned row says the row was scanned.
Required fix:  Scan the annotated body (`body_clean.text`), which is the text this response
               observed, and keep the default view for *disclosure* - annotate, do not delete (A7)
               applies to what is scanned as much as to what is shown. If instead the narrowing is
               deliberate, it must be declared: a row whose scanned text is narrower than its
               observed text belongs in `mentions_not_scanned`, or in a field beside it. Test: the
               fixture above, asserting a quoted address is either found or declared unscanned, and
               that one thread's participant block is identical under two queries that select
               different rows. Add a replant.
```
```
ID:            R-RETR-052
Severity:      MEDIUM
Reachability:  REACHABLE today, deterministically. Needs only an address that straddles the point
               where `snippet` is cut, or the A.9a head-truncation point of `default_view`.
Blocks WS-06?  NO - rides along.
Rubric:        STR-02 ("matching keys on the address"), contract C-02(b), I-1/I-2 (a claim the
               source does not support), R-SEC-030/032's rule that a field named `address` is not
               a route for mail-derived text that merely looks like one.
Location:      server/src/mailweave/structure/participants.py, addresses_in_text - applies
                 TEXT_ADDRESS_RE to whatever string it is handed, with no notion that the string
                 may be a prefix of a longer one;
               server/src/mailweave/retrieval/assemble.py, _observed_text - hands it `snippet`,
                 which is a truncation by construction, and a head-truncated `default_view`;
               server/src/mailweave/constants.py, is_an_address - passes `cai@team.exampl`,
                 correctly: it is the floor that keeps prose out, not a deliverability check;
               server/src/mailweave/envelope/wire.py, ThreadParticipant - accepts it for the
                 same reason.
Repro:         /tmp/rretr20/p23c.py
                 snippet   'xxxxxxxxxxxxxxxx On Mon Cai wrote:\n> loop in cai@team.exampl'
                 real mail  cai@team.example
                 participant addresses on the wire  ['ana@team.example','bo@team.example','cai@team.exampl']
                 'cai@team.exampl' appears in no message of this mailbox; is_an_address True;
                 mentioned in ('w1',); it is what `mentioned_only` reports as hearsay.
Expected:      An address in the participant index is an address that appeared in mail. A
               truncation boundary is not an address boundary and the code must not treat it as
               one.
Actual:        A prefix of a real address is minted as a participant identity and reported as
               someone the thread talks about.
Required fix:  Carry truncation with the text - a `(text, truncated_at_end: bool)` pair, or scan
               the untruncated annotated body per R-RETR-051 and drop the snippet path's tail
               match - and discard any match that touches a truncation boundary. Missing a mention
               is the direction this module already declares it prefers; inventing one is not.
               Test: an address straddling the cut yields no participant; add a replant.
```
```
ID:            R-RETR-053
Severity:      LOW
Reachability:  REACHABLE today. One unresolved parent whose Message-ID carries Gmail query
               punctuation or exceeds 256 characters, beside at least one that does not.
Blocks WS-06?  NO - rides along.
Rubric:        AD D.2's `not_tried` closed vocabulary, contract I-2 and I-4 ("an untried rung ...
               neither tried nor reported as untried"), the round's own rule that an absent source
               must not read as an absent relationship.
Location:      server/src/mailweave/retrieval/structural.py, StructuralPlan.skipped - set,
                 documented as "a permanent inability", and read by nothing but `applicable`;
               server/src/mailweave/retrieval/assemble.py, _l4_not_tried - emits `cap` for
                 `over_cap` and `not_applicable` only when `executed == 0`, so the mixed case
                 emits no L4 entry at all.
Repro:         /tmp/rretr20/p13_skipped.py
                 c1 In-Reply-To <ok@m.invalid>      (probeable, recovered)
                 c2 In-Reply-To <qu"ote@m.invalid>  (declined: Gmail query punctuation)
                 queries    ['zorbal', 'rfc822msgid:<ok@m.invalid>']
                 not_tried  L0/L1b/L2/L3 not_applicable, structural_similarity not_applicable
                 - no L4 entry of any kind, and nothing names the declined identifier.
Expected:      Three facts are reportable about L4 and only two are reported. A parent MailWeave
               declined to look for is a rung that did not run for a nameable reason.
Actual:        Invisible. The child's own row still declares its gap, so no message is lost; what
               is lost is the account of the lookup.
Required fix:  Emit a third entry - `not_tried{rung: L4, why: not_applicable}` with a note, or a
               dedicated declaration carrying the `(child, identifier)` pairs - whenever
               `plan.skipped` is non-empty, independent of whether other probes ran. Two lines in
               `_l4_not_tried` and an assertion in the existing L4 test.
```
```
ID:            R-RETR-054
Severity:      MEDIUM
Reachability:  REACHABLE today. A message with no `Message-ID` whose own In-Reply-To resolves in
               its thread - AD D.4a's own case, and the corpus already builds it (`t-nomsgid`).
Blocks WS-06?  NO - rides along.
Rubric:        AD D.4a ("A missing Message-ID yields linkage: 'no Message-ID' ... never a guessed
               parent"), AD D.6, STR-01's declared-gap clause, contract C-02(a), I-2.
Location:      server/src/mailweave/structure/reply_tree.py, Link.can_be_a_parent - computed
                 correctly, and read by nothing outside this module. `grep -rn can_be_a_parent
                 server/src tests` finds `reply_tree.py`, the property test and two replant
                 anchors, and no other production site;
               server/src/mailweave/envelope/wire.py, MessageRow - carries `linkage` and
                 `reply_parent_id` and no field for this fact;
               server/src/mailweave/structure/threadmap.py, assemble._rows_of - neither reads it.
Repro:         /tmp/rretr20/p17_d4a.py
                 d2 no Message-ID, In-Reply-To <d1@m.invalid> (resolves)
                 d3 ordinary reply to the same parent
                 d4 well-formed reply naming <d2@m.invalid>
                 d2  linkage 'in-reply-to'                          parent d1
                 d3  linkage 'in-reply-to'                          parent d1
                 d4  linkage 'named parent is not in this thread'   parent None
                 d2 and d3 serialise identically in every field but id and position.
Expected:      Whatever D.4a's clause means, it exists so that a caller can tell that message
               apart - and so that d4's gap ("my parent is here and unnameable") is legible as
               something other than "my parent is in another thread", which is what L4 will now go
               and look for.
Actual:        Indistinguishable on the wire. The reading is defensible; the half of it that makes
               it defensible does not leave the module.
Required fix:  Carry the fact onto `MessageRow` with its third state (`None` for headers
               unobserved), and assert in `test_a_message_with_no_message_id_still_gets_the_link_
               its_own_headers_support` that the two rows differ on the wire. See Part 6 for the
               full ruling, including why I do not recommend reversing the linkage instead.
```
```
ID:            R-RETR-055
Severity:      LOW
Reachability:  REACHABLE-IF-GMAIL. The disagreement between the two derivations is here today and
               is demonstrated at the unit; whether Gmail ever returns a zero-padded
               `internalDate` is R-GMAIL's. `GmailNumericId` accepts one.
Blocks WS-06?  NO - rides along.
Rubric:        STR-03 ("chronology never depends on API array order"), amendment A3, AD D.6
               temporal.
Location:      server/src/mailweave/gmail/client.py, _thread_scalars - the sort key is
                 `int(internal_date)` and the tie census is
                 `Counter(message.internal_date)` over the raw string. Two rows whose stamps are
                 equal as integers and unequal as strings tie in the sort and are absent from
                 `tied_on_internal_date`.
Repro:         /tmp/rretr20/p6_ordering.py
                 rows '01000' and '1000'
                 positions {'m1': 0, 'm2': 1}     tied ()
                 int('01000') == int('1000')      True   <- the order WAS settled by message id
Expected:      One derivation. `tied_on_internal_date` exists so a position claim cannot be read
               as stronger than the evidence; it must be computed on the value the ordering uses.
Actual:        A pair ordered by id is presented with no tie declaration.
Required fix:  `Counter(int(m.internal_date) for m in thread.messages)` and the same normalisation
               in the tie predicate. One line, plus a unit case in the existing tie test.
```
```
ID:            R-RETR-056
Severity:      LOW
Reachability:  REACHABLE today.
Blocks WS-06?  NO - rides along. R-SEC / WS-14 own the ruling; I am recording the surface this
               round opened.
Rubric:        INJ-01/INJ-02 (mail-derived text is fenced and labelled), contract R-09,
               AD A.11's mail-text-out-of-metadata rule, INJ-04's hidden-character clause.
Location:      server/src/mailweave/retrieval/structural.py, plan_structural_expansion - composes
                 `q` from a `Message-ID` header value chosen by the sender;
               server/src/mailweave/envelope/wire.py / retrieval report - `scan_scope[].q` carries
                 that string verbatim, unfenced and with no `content.trust`;
               server/src/mailweave/content/html_text.py's format-character stripping runs in the
                 content pipeline and not on this path.
Repro:         /tmp/rretr20/p18_wire_leak.py
                 .retrieval_report.scan_scope[1].q
                   = 'rfc822msgid:<subject-to-the-attached-nda-review@evil.invalid>'
               /tmp/rretr20/p21_zerowidth.py
                 scan_scope q = 'rfc822msgid:<hidden​‍directive@evil.invalid>'
                 - U+200B and U+200D travel into the outbound Gmail `q` and into the response.
Expected:      L4 is the first rung whose `q` is composed from mail content rather than from the
               caller's query. Mail-derived text in a connector-voiced field is INJ-02's subject
               whether or not it is bounded.
Actual:        Verbatim, unfenced, unlabelled, format characters included. It is genuinely
               bounded - `is_probeable` caps at 256 characters, requires a whole `<msg-id>` token
               with no whitespace, and rejects Gmail's own query punctuation - which is why this
               is LOW and not higher.
Required fix:  R-SEC's call. The two obvious options are to strip Unicode format characters from
               a `Message-ID` before it is put in a `q` (and declare the strip), or to label the
               `scan_scope` entry as carrying mail-derived text. Do not truncate the identifier:
               `rfc822msgid:` is exact and this module is already right about that.
```
```
ID:            R-RETR-057
Severity:      LOW
Reachability:  REACHABLE today.
Blocks WS-06?  NO - rides along.
Rubric:        STR-01, contract C-02(a), AD D.6.
Location:      server/src/mailweave/structure/reply_tree.py, _resolve - returns the first named
                 candidate the thread holds exactly one message under, so an `In-Reply-To` naming
                 two different in-thread parents is arbitrated by wire order with no declaration;
                 and an `ambiguous` flag raised by an earlier candidate is discarded when a later
                 candidate resolves.
Repro:         /tmp/rretr20/p1_guess.py
                 case 6: In-Reply-To '<a@x> <b@x>', both held -> parent a, linkage in-reply-to,
                         no declaration that two parents were named
                 case 7: In-Reply-To '<dup@x> <uniq@x>' where <dup@x> is carried by two messages
                         -> parent u, linkage in-reply-to, the ambiguity seen and dropped
Expected:      The module refuses to choose when one id maps to two messages. Two ids each
               mapping to one message is the same question - "the headers name more than one
               candidate" - and RFC 5322 permits a multi-id `In-Reply-To`.
Actual:        Arbitrated by wire order, undeclared. Neither case invents a parent: both links are
               named by the child, which is why this is LOW.
Required fix:  Either declare it (a flag on the `Link`, surfaced on `ThreadStructureReport`) or
               record in the docstring that wire order arbitrates a multi-id `In-Reply-To` and
               why that is a reading of the headers rather than a choice. Executed either way.
```

---

## Recommendations, per criterion

**I mark nothing.** Every recommendation is scoped and I name what my evidence does not cover.

* **STR-01 · Reply-tree reconstruction with declared gaps — RECOMMEND NOT YET.** What I can
  establish, and it is a great deal: over 3,000 generated threads plus thirteen hand-built
  pathological shapes plus the corpus end to end, **no message inside a thread is attached to a
  parent its own headers do not name**; every unlinked message declares *which* gap it is in from a
  closed nine-member vocabulary in which every member has an executed producer; the four properties
  that separate a reading from a guess are asserted over a generator whose range I measured
  independently and found wide; and the whole result is invariant under permutation of the input at
  both layers. What stops the mark: (1) the acceptance's **100 % link accuracy against the seeded
  corpus manifest** has no instrument — there is no seeded corpus and `server/**` may not name one,
  so this is **WS-16 / R-GMAIL**, exactly as the implementer says; (2) **R-RETR-049** and
  **R-RETR-050** mean a *structurally added* row can assert a relation the headers do not state,
  which is C-02(d) and inside STR-01's own subject; (3) **R-RETR-054** — D.4a's case is
  unrepresentable on the wire. (2) and (3) are small, defined fixes.
* **STR-02 · Participant retrieval keyed on address; authorship vs hearsay — RECOMMEND NOT YET.**
  The authorship half is in good shape and I attacked it hard: sixteen adversarial header shapes,
  and **no case where a mention is recorded as authorship**; identity is the address in every path;
  no display name reaches the wire; a multi-address `From` is never promoted; an unreadable `From`
  yields no author and is declared. What stops the mark: **R-RETR-051** (the mention half never sees
  quoted text and says it did, so the index depends on the query rather than on the thread) and
  **R-RETR-052** (a truncated snippet mints an address that is in no message) are both squarely
  inside this criterion's own guard — "return every message in which the string X appears" is ruled
  out, but so must be "report an address the mail does not contain". Separately, the acceptance's
  `{display_name, address}` **pair exposure** is not built and is **WS-11**'s surface, which the
  implementer states plainly and I confirm; and the case-accuracy bar is `[UNSET — register at G0]`.
* **STR-03 · Temporal ordering from internalDate — RECOMMEND NOT YET, and the shuffle clause is
  established.** The acceptance's shuffle test is met at a level I will stand behind: 24/24 array
  permutations produce an identical representation, 24/24 again with every message sharing one
  `internalDate`, and the position map is a function of `{id: internalDate}` alone — I verified the
  fix to `_thread_scalars` and re-derived the defect it repaired. The array-index tie-break was a
  genuine defect in existing code and finding it is to the implementer's credit. What stops the
  mark: the criterion's other half — real timezone-boundary cases — is **R-GMAIL**'s and needs a
  live account; the named verifier for the shuffle half is **R-ARCH**, not me; and **R-RETR-055**
  leaves one class of tie undeclared.
* **STR-04 · Thread position exposed — RECOMMEND PASS, scoped.** Executed: `position` present on
  100 % of rows across every run I made, `stated_total` on every source, positions contiguous
  `0 … n-1` and consistent with the map, A3's bound `0 <= p < stated_total` **raised** at both ends
  and never clamped, and the whole set invariant under array permutation. A thread the observation
  declined to place is refused rather than mapped, at `ThreadMap.build` and again in `assemble`.
  *Scope:* my evidence is my own runs plus the round's suite, all behind `MockTransport`; the
  criterion's "over the full suite" schema sweep is **R-DISC**'s and I do not substitute for it, and
  "the thread's total" is `stated_total`, whose accuracy against the real thread is **GMAIL-03**'s
  open question below.
* **STR-05 · Multi-thread evidence assembly — RECOMMEND NOT YET.** Executed and correct: evidence
  in another thread comes back as a **separate `Source`** with its own `thread_id`, `stated_total`,
  `fetched_at`, map, participant block and structural report; the cap converts overflow into
  `withheld` records rather than dropping them; provenance is right on every recovered row including
  a spam sibling; and the three similarity signals D.6 lists are declared `not_applicable` rather
  than silently absent, which is the honest disposition. What stops the mark: the criterion requires
  each source to carry a **map affordance**, and `Source.map_id` is `None` — that is **WS-06**, the
  next workstream; **R-RETR-049/050** can make the assembled sibling the wrong thread or two
  contradictory ones; and the strict-case-accuracy bar is `[UNSET]` against Baselines F(±2) and C,
  which is **WS-16**.
* **GMAIL-03 · Thread-completeness semantics validated — CANNOT ESTABLISH HERE, and nothing in this
  round moves it.** The *semantics* half is implemented and I checked it: `stated_total` is
  `len(recorded.thread.messages)` — exactly what the source reported at `fetched_at` — and
  `Completeness` has one member, `as_reported_by_source`, so no code path can assert more. The
  *gate-binding* half is a measured discrepancy rate against manifest truth with a bound that is
  `[UNSET — register at G0 from PF-1]`. PF-1 is whether `threads.get`'s array can be short of the
  thread; nothing in-process can detect that, since a short array and a short thread are identical
  from here. **R-GMAIL, against a real account, after the bound is registered.** The implementer
  claims exactly this and I confirm it.

---

## Verdict on the D.4a reading

**The narrow reading stands; the shipped implementation of it does not.** Stating a link a child's
own headers support is not the guess D.4a forbids, and refusing it would discard evidence that was
read — so `Linkage.NO_MESSAGE_ID` correctly belongs to the message the clause is the whole story for.
But the argument for that reading rests entirely on `can_be_a_parent` reaching the caller, and it
reaches nothing outside `reply_tree.py`. Carry it onto the row (**R-RETR-054**) and the reading is
sound. Do not reverse the linkage.

---

## Overall verdict

**WS-06 should proceed on this map.**

The map itself is sound where WS-06 depends on it. Thread membership is complete
(`included == stated_total` on every mapped thread), positions are chronological and stable under
every array permutation I could produce, `H = disclosed ∪ withheld` held in every probe including
both cap overflows and both new routes into `H`, provenance is on every row including the
structurally added ones, and one `threads.get` per thread is preserved with L4 in the middle. The
reply tree does not guess: I attacked it for a full round with generated threads, hand-built
pathologies, header-extraction edge cases and permutations, and could not make it attach a message to
a parent its own headers do not name.

Under **OD-6's counter-rule** I am explicit: **none of my nine findings is a critical correctness or
safety defect**, and none of them blocks integration. Seven ride along. Two — R-RETR-049 and
R-RETR-050 — are over-claims on rows L4 adds, which is the sharpest thing I found and which I would
want fixed in the round that next touches `structural.py`, not before WS-06 starts. One,
**R-RETR-051**, is not a blocker but is a *precondition on a WS-06 design decision*: do not put
`Source.participants` inside `mapping_digest` until the mention scan is a function of the thread
rather than of the query, or handles will report `handle_stale` for threads nothing changed in. That
is the one sentence of this review WS-06 must read.

This round produced integration progress rather than an audit, and it produced the two best pieces of
verification machinery in the project so far: a property whose generator I measured and found genuinely
wide, and a 41-entry replant manifest that survived ten of my own independently written mutations. The
two vocabulary sweeps assert equality and fail on a planted unproduced member. The one weakness in all
of it is that the property does not look at `Link.evidence` in the gap branch and nothing pins what the
mention scanner is fed — which is where four of my five MEDIUMs came from, and which is the round's own
"one shape validated, peers trusted" arriving one field to the left.

---

## Established by execution

1. All gates clean, twice, before and after all probing; 2,369 tests collected and passing; rubric
   6 PASS / 0 FAIL / 0 BLOCKER / 107 NOT TESTED, 11 transitions; no file under `server/`, `tests/`,
   `tools/` or `harness/` modified in my window.
2. Inside a thread, `reconstruct` never produces a parent the child's own headers do not name, over
   3,000 generated threads, 13 hand-built pathological shapes, and the corpus end to end.
3. `References` is read right-to-left for *resolution*: with both the root and the nearest ancestor
   present, the nearest is chosen.
4. The four-property Hypothesis test is non-vacuous: my own planted violation of each is caught.
5. The generator's range is wide: all nine `Linkage` members, plus cycles, duplicate `Message-ID`s,
   self-references and absent parents, arise without being enumerated.
6. The reconstruction is invariant under permutation at the unit and end to end: 24/24 array
   permutations identical, and 24/24 again on an all-tied thread.
7. `_thread_scalars`' tie-break is the message id; the position map is a function of
   `{id: internalDate}` alone; all-or-nothing when a row lacks `internalDate`; a duplicated id in one
   thread refuses the seal.
8. A3's bound raises rather than clamps, at both ends.
9. No case, in sixteen adversarial header shapes, where a mention is recorded as authorship;
   identity is the address everywhere; no display name on the wire.
10. `H = disclosed ∪ withheld` holds across `max_hit_threads` overflow (15 threads → 12 + 3 withheld),
    `max_source_threads` overflow (8 recovered → 4 + 4 withheld), an unmappable thread, and L4 as a
    second route into `H`.
11. Every row carries `MailboxProvenance` from its own labels, including L4-recovered rows; a spam
    sibling reports `regions=('spam',)`, `outside_the_default_mailbox=True`.
12. L4's probes carry the region the query named (`in:anywhere rfc822msgid:<…>`,
    `includeSpamTrash=True`); my own plant that composes without the region is caught.
13. Both vocabulary sweeps assert equality and fail on a planted member no code produces; the
    product's own participant blocks reach all five `ParticipantRole` members.
14. All 41 replants reproduce independently: anchors match exactly once, files change, all caught;
    `docs/` is in the scratch copy; three packages resolve inside it and none into the working tree.
15. Ten of my own mutations of the R29–R41 behaviours are all caught, each by a behavioural test.
16. The nine findings above, each with the reproduction named in its record.

## False on execution

1. *"`can_be_a_parent` … is the half a caller needs"* (IMPLEMENTER §8, and `reply_tree.py`'s
   docstring). It is not a half a caller has: the field never leaves the module, and a message with
   no `Message-ID` is byte-identical on the wire to an ordinary linked reply (R-RETR-054).
2. *`Link.evidence` is "the one it was looked for under when there is no parent"*
   (`reply_tree.py`). For a `References`-only child it is the leftmost entry; the first id looked
   under was the rightmost (R-RETR-049).
3. *"Mentions are scanned only in text this response actually observed"* (`threadmap.py`) — the
   scanner is given the quote-stripped `default_view`, which is narrower than what was observed, and
   the row is nonetheless reported as scanned (R-RETR-051).
4. *"An id carried by two messages resolves to neither: picking either would be a guess dressed as a
   link"* (`_resolve`) — true inside a thread, and not applied at L4, where both are disclosed as
   *the* parent (R-RETR-050).
5. `tied_on_internal_date` does not name every pair whose order was settled by message id: the
   census runs on the string, the sort on the integer (R-RETR-055).
6. `StructuralPlan.skipped` — documented as a declared permanent inability — reaches no response
   field at all (R-RETR-053).
7. The claim that `test_every_participant_role_is_one_an_index_can_actually_report` asserts *the
   product's* produced role set: it asserts a hand-built index's. The underlying claim is true — I
   established it at the response — but the test does not establish it.

## Not establishable here at all

1. **STR-01's 100 % link accuracy against the seeded-corpus manifest.** No seeded corpus exists and
   `server/**` may not name one. **WS-16 / R-GMAIL.**
2. **GMAIL-03's discrepancy bound, and PF-1.** Whether `threads.get`'s array can be short of the
   thread is undetectable in-process; the bound is `[UNSET]` and must be registered at G0 before
   review. **R-GMAIL.**
3. **PF-2's three branches.** All three now have a fixture switch and a declared degradation, which
   is the right preparation; which branch is real is a fact about Gmail. `Linkage.HEADERS_UNOBSERVED`
   is reachable in the product only if Gmail can return a thread row with `internalDate` and no
   `payload`. **R-GMAIL.**
4. **STR-02's case-accuracy bar and STR-05's strict-case bar**, both `[UNSET — register at G0]`
   against baselines that do not exist yet. **WS-16.**
5. **STR-02's `{display_name, address}` pair exposure** — a disclosure surface that is **WS-11**'s
   and does not exist.
6. **`map_id` on a `Source`**, so a map is redeemable — **WS-06**, which is what comes next.
7. **Whether duplicate `Message-ID`s across threads (R-RETR-050) or zero-padded `internalDate`
   values (R-RETR-055) actually occur in a real mailbox.** The absence of a defence is established
   here; the frequency is **R-GMAIL**'s.
8. **Amendment A1's external content witness.** Every statement in this review is exactly as
   trustworthy as "I executed this call against `httpx.MockTransport`", and that is not checkable
   in-process. Unchanged from every prior round.
9. **Anything bearing on OD-6's milestone criteria 2 and 3.** Every probe here ran with sockets
   denied. Nothing in this review is evidence that MailWeave can reach a real Gmail account, and
   OD-6 says in terms that it may not be used as such.
