# ROUND 09 — R-SEC / R-DISC combined review

**Reviewer:** combined R-SEC + R-DISC, independent instance, 2026-08-31. Verified by execution per
`AGENT_LOOP.md` §4/§7. Probes ran in `/tmp` and at the interpreter; source/tests were not modified
— one reintroduction-edit attempt on `disposition.py` was blocked by the sandbox before any bytes
changed (confirmed by re-reading the file), so the handoff's five reintroduction counts
(339/4/7/13/5 failures) are **reported, not re-run**; elsewhere "verified" means executed against
the live tree this session, including two attacks going further than the handoff's own (§1.2, §1.4).

## Environment

`.venv`/caches wiped, `uv sync --all-packages --extra dev`, `mailweave.__file__` →
`/root/mailweave/server/src/mailweave/__init__.py` (the repo, not a stale install). `ruff check`
clean, `ruff format --check` 95 files formatted, `mypy --strict` success on 69 files, `pytest -q
-m "not network"` **1,168 passed**, `tools.guards` 7 clean, `rubric_status.py --check` 8 PASS /
105 NOT TESTED / 10 transitions — matches `HANDOFF.md`. `test_a7_containment.py` collects and
passes 301 tests; its two containment properties run `max_examples=400` in-file, not reduced.

# Section 1 — R-SEC (retention)

## 1.1 The three named claims — all verified fixed

| ID | Claim | Verdict & evidence |
|---|---|---|
| R-SEC-029 | Line-break check now matches `str.splitlines()` | **VERIFIED.** `_is_one_line` *is* `value.splitlines()==[value]` — definitionally complete. Brute-forced U+0000–U+10FFFF against a naive `\n`/`\r` check: exactly VT/FF/NEL/LS/PS slip it and are caught by the new one; all 7 refused live via `FetchedIds(history_id=...)`. |
| R-SEC-030 | `history_id`/`internal_date` shape-checked like `fetched_at` | **VERIFIED.** `_GMAIL_NUMERIC_ID_RE=^[0-9]{1,20}$`, ASCII-only (`"٣".isdigit()`/`"²".isdigit()` are `True`, both rejected). 49-char sentence refused under both names; stub-row probe (`internal_dates` on a STUB-bound observation) raises before the ledger sees it. |
| R-SEC-031 | Id fields bounded, or the reflection test made honest | **VERIFIED — did both**, exceeding the work order's "or". `_sealed_id` bounds `_ids`/`_thread_id`/`_thread_ids`; reflection test replaced with `STRING_BEARING_SLOTS` (each slot attacked by name, 3 probes) plus proof every other slot is non-string. 5-line, 140-char mail text as an id: refused. |

**Stub-row judgment (R-SEC-030):** correct call — bounded, `internal_date` can no longer carry
content, and it orders the stub the same way `position` already does. Endorsed.

## 1.2 The sweep — all three left items confirmed real

- **S-2** (`strip_invisible_characters`, 16 of 170 `Cf` chars): confirmed by exhaustive count
  (`unicodedata.category(c)=="Cf"` over the full range → **170**, 16 handled). U+061C, U+00AD, and
  a `U+E0000`-block payload spelling `"HIDDEN"` all survive with `removed_chars=0`.
- **S-3** (`HistoryAddition.history_id`): confirmed **one layer further than the handoff** — built a
  full `Envelope` with `reason=HistoryAddition(history_id="Please review the attached NDA before
  end of day.")`; the sentence lands verbatim in the disclosed JSON `reason` string. No line-break
  check either — a U+2028 two-sentence value serialises too.
- **S-4** (`StoredCredentials.obtained_at`): confirmed, constructs cleanly with the sentence.
  Correctly lower stakes: local file only, never disclosed, never read back in production code.

**S-2 is more consequential than the handoff frames it.** `html_text.py` cites RR INJ-04 directly,
and `headers.py` imports this exact function for Subject/From/filename — the mechanism
`RUBRIC_TRANSITIONS.md` cites for **R-SEC-005**, itself the cited evidence for **INJ-04's PASS**
(round 5, full scope). Not a new regression — the lists predate this round — but a `PASS`ed
mandatory criterion rests on a hidden-character defense with a 154-character hole, including a
covert ASCII-payload channel. Recommend R-SEC re-walk INJ-04 next round.

## 1.3 Ruling: should `HistoryAddition.history_id` have been left open?

**No. It should have been in scope, and it gates this round.** It is not adjacent work — it is
R-SEC-030 **unfinished**: same field name, same missing check, found while executing the work
order's own instruction to sweep for this exact pattern. The scope-discipline caution is about
A7's surgery on `body_clean`'s many consumers; it does not extend to a one-field validator on an
unrelated, closed reason type. It is also **more exposed than the seal fields R-SEC-031 fixed**:
those sit behind a seal, this is a bare `Field(min_length=1)` on a `Reason` a `MessageRow` renders
straight to the wire via `field_serializer` — I reproduced it reaching an actual disclosed payload,
not just `.render()`. The fix is the regex already written and tested, zero risk to A7's gate or
the ledger — nothing like the risk the scope note warns against. Read for intent, the exit
condition ("no mail text reachable... by any encoding") is violated one door over from the seal.

Filed as **R-SEC-032**, **HIGH** (matches R-SEC-030's own severity — same mechanism, one layer
up). AGENT_LOOP §6 requires zero open HIGH; this was known, reproduced, and left.

## 1.4 My own fresh retention attack

- **Regex ordering, no bypass:** `_sealed_numeric_id` runs `_sealed_scalar` before the digit regex,
  so Python's `$`-before-trailing-`\n` quirk is pre-filtered by call order — worth a comment, not a
  hole. Fullwidth digits (U+FF10–19) confirmed rejected by `[0-9]`, same as Arabic-Indic.
- **Id-as-sentence, confirmed live, not new:** `id="Meet me at 3pm today to discuss the layoffs
  quietly"` (51 chars, one line) as both the sealed and disclosed id reaches the wire verbatim.
  `_sealed_id`'s docstring already declines a character-class check; recorded as
  confirmed-and-accepted, matching `next_page_token`'s "narrowed, not closed" status.
- **`sweep_orphaned_temporaries` crash, re-run live (R-SEC-035 below):** a real `TokenStore` with
  `.credentials.json.².abcd` in its directory makes it raise `ValueError` uncaught, from `save()`,
  contradicting "every error is swallowed."

## 1.5 New findings

```
ID: R-SEC-032  Severity: HIGH  Rubric: none — A6/A7 retention (OD-4); same mechanism as R-SEC-030
Location: envelope/reasons.py:104-109 (HistoryAddition.history_id, no format check)
Repro: full Envelope w/ HistoryAddition(history_id=<sentence>) row → sentence reaches
  model_dump_json()["sources"][0]["messages"][0]["reason"] verbatim; U+2028 value too.
Expected: same ^[0-9]{1,20}$ check the seal's history_id now has. Actual: any string, len>=1.
Required fix: one field_validator, same regex R-SEC-030 already wrote.
```
```
ID: R-SEC-033  Severity: HIGH  Rubric: INJ-04 (PASS, round 5); R-SEC-005's cited evidence
Location: content/html_text.py:24-30 (16 hand-listed chars); content/headers.py:26,98 (reused)
Repro: "Pay؜now", "Pay\xadnow", a U+E0000-block "HIDDEN" payload all survive, removed_chars=0.
  Full Cf sweep: 170 exist, 16 handled.
Expected: "hidden constructs removed" to cover the format-character category generally.
Actual: 154 Cf chars, incl. a documented invisible-payload channel, pass unflagged.
Required fix: strip by unicodedata.category(c)=="Cf" minus a keep-list, own reduction accounting
  (as the handoff specifies). Re-walk INJ-04's PASS once fixed.
```
```
ID: R-SEC-034  Severity: LOW  Rubric: none — SEC-04 adjacent (PASS)
Location: auth/tokenstore.py:55 (StoredCredentials.obtained_at, no format check)
Repro: constructs cleanly with a full sentence as obtained_at.
Expected/Actual: same parse_instant check fetched_at/verified_at carry; absent — but never
  disclosed, never read back today, much lower stakes than R-SEC-032.
Required fix: parse_instant("obtained_at", value) at construction.
```
```
ID: R-SEC-035  Severity: LOW  Rubric: none — SEC-04 adjacent
Location: auth/tokenstore.py:131 (fields[0].isdigit() then int(fields[0]))
Repro: temp file ".credentials.json.².abcd" makes sweep_orphaned_temporaries() raise ValueError
  uncaught, reachable from save() — reproduced live against a real TokenStore.
Expected: docstring's "every error is swallowed." Actual: crash on a superscript-digit filename.
Required fix: guard the int() call, or require .isascii() alongside .isdigit().
```

## 1.6 Recommendation (R-SEC)

**Do not gate on retention as-is.** R-SEC-029/030/031 are genuinely closed and well-tested.
R-SEC-032 is open, HIGH, self-diagnosed, trivial to fix — a same-day follow-up, not a full round.
R-SEC-033 should be scheduled promptly (INJ-04 tie) though outside scope; R-SEC-034/035 backlog.

---

# Section 2 — R-DISC (does A7 compose with disclosure?)

## 2.1 Depth vocabulary — not yet wired; no second hierarchy exists, but the risk is real

`grep` for `AnnotatedBody`/`SpanClass`/`default_view` under `envelope/`: **zero matches.**
`ProcessedMessage` is used only inside `content/` and its own tests; `MessageRow.content` is still
a bare `Content(text: str)`; `Depth` is untouched. Confirms the handoff's own "weakest point #5":
**the composition this round asks about does not exist yet to judge** — nothing from A7 has
reached the wire, so nothing has literally been smuggled in.

But the shape is a latent risk: `SpanClass` has 5 members, `view()` takes an arbitrary class set,
and the suite already frames a graded `ONE_WIDENING=(ORIGINAL,UNCERTAIN)` step. If a future round
exposes "widen by span class" as an affordance independent of `Depth`, that is structurally the
second navigational level `CONTEXT_DISCLOSURE_OPTIONS.md` T-CD1 rejected on cited evidence ("a
second, deeper routing level never helps and sometimes breaks accuracy outright"). The composition
that avoids this: `Depth.BODY_CLEAN` stays `view()` (original only), `Depth.BODY_FULL` becomes all
classes — `SpanClass` stays internal to one `Depth` step, never a second axis. Filed as
**R-DISC-014**, MEDIUM — a requirement for the wiring round, not a Round 9 defect.

## 2.2 Token budgets and the OD-3 floor — units consistent; no consumer exists yet

`measure.py::measure_tokens` and `normalize.py::count_tokens` both reduce to `len(text.split())`
— the **same whitespace-token estimate**, both disclaimed as not DISC-04's pinned tokenizer: no
divergent definition introduced. `process_message(..., head_truncate_tokens=N)` truncates
`default_view` while `body_clean` stays whole — the shape OD-3 needs (declared, reversible, "a
way to fetch the rest"). But no ladder/rung/floor-selection code exists anywhere in `server/src`
(confirmed absent, consistent with the work order excluding "rungs, ranking"). So this composition
cannot be answered by execution — only structural compatibility can, and it holds.

## 2.3 Round 5's field ordering — holds, checked not assumed

Built a realistic 3-message, mixed-depth partial envelope and read the JSON key order: `partial`,
`withheld` and `retrieval_report` all precede `sources`, per R-DISC-003. Expected, since A7 hasn't
touched `response.py` — but checked, not assumed, per the work order's instruction.

## 2.4 Reading a partial envelope as a consuming agent

For the `body_clean`-depth row in that envelope: one fenced string, no signal that any span
classification exists underneath — because none did; the fixture supplied the text directly. The
wire is exactly as legible as before A7, which is also the answer: **nothing on the wire says
anything about spans yet.** `AnnotatedBody.hidden_chars`/`.latched` are Python properties with no
serialised counterpart; the `detail` string A7 writes into `Reduction` is free text, unbranchable
by a program. Filed as **R-DISC-015**, MEDIUM: once wired, `latched` needs a structured field, or
A7's "one widening away" promise is unverifiable by a program reading the response.

## 2.5 Ruling on the `uncertain` default

**Keep `original` as the default — an interim position, conditioned on two follow-ups landing in
the wiring round.**

Costs, both measured: **`original`** hides 14/254=5.5% of measured sender prose by default
(recoverable, not destroyed) and, worse, **0/1,264** latch-corpus reversal characters — a real gap
against exactly what OD-3 protects. **`original+uncertain`** recovers all 1,264/1,264, but
`uncertain` covers *any* unmarked-end quote/forward — 28/161=17.4% of real header shapes — so the
wide default would show the **entire** unclosed quote chain by default in that fraction of real
threads, not just the reversing reply: the cost quote-classification exists to control, unboundedly.

Not a coin flip: OD-3's own tension one level down, already answered there — membership absolute,
depth budget-earned, degradation declared with a widening affordance, *not* "show everything." A7's
`uncertain` gives that shape within one message, and does it better (no re-fetch, just a `view()`
call on data already in hand). Applying OD-3's resolution consistently: **stay narrow**, because
the wide default's cost is unbounded and the narrow default's residual risk is bounded and cheap
to close — provided the closing mechanism gets built. Two requirements, attached to R-DISC-014/015
(no floor-selection code exists yet to hold a defect): (a) a structured `latched` signal so a
caller can detect judged extents without parsing English; (b) the floor-selector must widen
*specifically* the OD-3 floor messages, not apply one global default.

## 2.6 Additional finding

```
ID: R-DISC-016  Severity: LOW  Rubric: DOC-01 adjacent (claims match measurement)
Location: ARCHITECTURE_AMENDMENTS.md A7 — "The disclosure layer decides what to show..." (present)
Repro: zero matches for AnnotatedBody/SpanClass/default_view under envelope/.
Expected: text describing what is built, or marked as intent. Actual: reads as completed
  integration; nothing consumes A7's output yet — the handoff says so candidly, the amendment
  doc does not.
Required fix: a line in A7 noting the disclosure-layer half is unbuilt as of round 9.
```

## 2.7 Recommendation (R-DISC)

**R-DISC's assigned question is currently unanswerable by execution, and that is the honest
finding.** Checked and holds: field ordering (2.3), token-unit consistency, truncation-shape
compatibility (2.2). Unbuilt: any `envelope/` consumer of `AnnotatedBody`, any structured
`uncertain` signal, any floor selector. None of R-DISC-014/015/016 block Round 9's own exit
condition — they are requirements on the wiring round, filed now so they are not rediscovered then.

## Gate recommendation

**Round 9 does not gate.** One open HIGH: **R-SEC-032**, self-diagnosed, reproduced end-to-end to
the disclosed wire, fix known and trivial. R-SEC-029/030/031 are genuinely closed; A7's containment
gate holds (301/301 tests, both 400-example properties pass) — this review did not re-attack A7's
corpus claims, R-ARCH's own. R-DISC-014/015/016 are advisory, not blockers. Fix R-SEC-032,
re-verify, then gate; schedule R-SEC-033 for its INJ-04 tie.
