# R-ARCH — Round 7 verification

**Reviewer:** R-ARCH (fresh instance, did not write this code or `HANDOFF.md`). 2026-08-31. Method: execution only (`AGENT_LOOP.md` §4/§7).

**Setup.** `.venv`/caches wiped in `/tmp/mailweave-review/mailweave`; `uv sync --all-packages --extra dev`; `mailweave.__file__` confirmed inside that tree before trusting any result. `ruff check`/`ruff format --check`/`mypy` clean, `python -m tools.guards` clean (7 guards), `pytest -m "not network"` → **775 passed**, matches HANDOFF. Every file patched for a reintroduction test was restored and diffed byte-identical against `/root/mailweave` before the next edit.

## §1 — The quote stripper, against my own corpus

### 1a. False positives — 36 sentences I wrote (none from `reply_chains.py`/HANDOFF.md)

Tested in two placements: `ABOVE_QUOTE` (last line above a real `>` chain — the implementer's tested position) and `STANDALONE` (ordinary prose, sender's text before *and* after, no quote — the more common shape, not theirs). **All 36 survive whole, both placements** (72/72 kept):

| Category | Sentences (all outcome: kept, both placements) |
|---|---|
| Corporate prose | The vendor mentioned in their reply that the shipment would arrive a week early. · Marketing flagged a concern about the launch date during yesterday's sync. · Legal noted that the indemnification clause needs another look before signing. · The customer wrote back this morning to confirm the renewal terms. · Our account manager replied to say the invoice had already been paid. · IT confirmed the migration window will not affect production traffic. · The auditor raised a question about the Q3 numbers during the call. · Procurement responded that the new vendor contract is still under review. |
| Meeting notes quoting a colleague | In standup, Priya noted that the API changes are blocking two other teams. · During the retro, Sam mentioned the deploy pipeline had been flaky all week. · Dana pointed out in the planning meeting that the estimate was too optimistic. · The notes say Rey flagged the schema migration as risky before the freeze. · According to the meeting minutes, finance asked for the revised budget by Friday. |
| Address/time mid-paragraph | I checked with ops@example.com around 15:14 and they confirmed the window holds. · The ticket was reassigned to support@vendor.example just after 09:02 this morning. · We looped in billing@example.com at 14:05 to clarify the discrepancy. · Someone from procurement@example.com called around 11:30 about the renewal. · The escalation went to devops@example.com at 15:14, and they are on it now. |
| Forward/reply described in passing | I'm forwarding this thread so you have the full context before Monday. · Sharing the vendor's reply below in case it's useful for the audit. · Looping you in on the earlier exchange with finance about the invoice. · Passing along the note from support since it affects our rollout plan. · Replying all here so the rest of the team sees the updated timeline. |
| 1st-person / 1st-person-plural, adverbs intervening | I quickly checked with devops@example.com and then replied with the all-clear. · We carefully reviewed the contract yesterday and eventually signed off on it. · Earlier today I briefly spoke with the vendor and immediately followed up in writing. · We had already discussed this on Tuesday and subsequently agreed to the new date. · I later circled back with legal and promptly confirmed the clause was fine. · We jointly reviewed the proposal this morning and quietly flagged two issues. |
| Non-English (ro/fr/de/it/es/pt) | Am verificat rapid cu furnizorul si apoi am raspuns echipei. · J'ai verifie rapidement avec le fournisseur avant de repondre a l'equipe. · Wir haben gestern kurz mit dem Kunden gesprochen und danach schriftlich geantwortet. · Ho controllato velocemente con il fornitore e poi ho risposto al team. · Hemos revisado cuidadosamente el contrato y luego confirmamos por escrito. · Verificamos rapidamente com o fornecedor antes de responder a equipa. |

**Measured false-positive rate on my own corpus: 0/36 = 0.0%, both placements.** A5's zero-gate holds for prose of this shape. It does not hold in general — §1b.

### 1b. The gate is defeated: BLOCKER, found by testing a position the harness never tries

Every A5 protection (`_client_attribution_template`'s address/date/first-person checks, `_reclaim_unrecognised_attribution_head`) is wired to fragments `email_reply_parser` marks `fragment.quoted` (a `>`-prefixed line) or to the reply's last line. The **library's own** `QUOTE_HDR_REGEX = re.compile('On.*wrote:$')`, `HEADER_REGEX` (`From:`/`Sent:`/`To:`/`Subject:` at line-start) and `SIG_REGEX` (`-\w`/`--`/`__` at line-start) run underneath — no address, no date, no first-person check — and **retroactively mark every fragment below them `hidden`**, which `strip_quotes_and_signature` deletes with no reclaim path (`elif fragment.signature or fragment.hidden:` never calls `_client_attribution_template`). Five ordinary sentences, sender's own text following, **no quote chain anywhere**:

| Sentence | ABOVE_QUOTE | STANDALONE |
|---|---|---|
| Once the negotiations concluded, the legal team wrote: | kept, `amb=1` | **destroyed**, `amb=0` |
| Only after the third follow-up, the vendor finally wrote: | kept, `amb=1` | **destroyed**, `amb=0` |
| One of the engineers on the incident bridge wrote: | kept, `amb=1` | **destroyed**, `amb=0` |
| Ongoing talks with the reseller wrote a new chapter for the account, the rep wrote: | kept, `amb=1` | **destroyed**, `amb=0` |
| (control, no colon) Once the vendor read the proposal they wrote back quickly. | kept | kept |

`strip_quotes_and_signature("Thanks for the update on this.\n\nOnce the negotiations concluded, the legal team wrote:\n\nWe should have a decision by end of week either way.\n")` → `.reply == "Thanks for the update on this."` — 2nd paragraph gone, incl. a sentence with **no** attribution shape; `quoted_chars=106`, `ambiguous_lines=0`, silently. The no-colon control survives, proving *position* — not wording — flips this: confirms weakness #2 was right to worry about, just not in the direction their own corpus tests. Two more trigger shapes reproduced: `HEADER_REGEX` (`"To: whoever reviews this next, please..."` deletes it and the next paragraph as `signature`, `amb=0`) and `SIG_REGEX` (`"-1 day change to the schedule..."`, same). **Filed R-ARCH-022, BLOCKER** (§4) — violates the round's gated acceptance and A5's own invariant.

### 1c. False negatives, my own corpus of 19 real client headers

Independent of `CLIENT_ATTRIBUTION_LINES`, written from client conventions, not copied. **7/19 = 36.8% survive, not 12.5%:** gmail_fr/de/sv/pl, outlook_desktop, owa_block, apple_mail_macos/ios, yahoo_block, mailing_list_paren, bare `>`/`>>` chains (12) correctly removed; gmail_en_no_address/thunderbird/protonmail (3, ordinal-date) are already-known gap shapes; **gmail_en, gmail_nl, gmail_android, gmail_fi (4) are addressed, correctly-shaped, and still survive** — real address, real date, template order — because `_FIRST_PERSON_RE` unions pronouns across ten locales and collides with weekday abbreviations the same locales' clients emit:

| Weekday abbrev. | Collides with |
|---|---|
| en `Mon` (Monday) | fr `mon` ("my") |
| de `Mi.` (Mittwoch) | es `mi` ("my") |
| nl `ma` (maandag) | fr `ma` ("my", fem.) |
| sv `ons` (onsdag) | nl `ons` ("our") |
| fi `ma` (maanantai) | fr `ma` ("my", fem.) |

A header dated a Monday in en/nl/fi, or Wednesday in de/sv, is silently kept regardless of address — ~1-in-7-days across five locales, not the "two address-less English forms" HANDOFF reports; every worked example in `reply_chains.py`/`CLIENT_ATTRIBUTION_LINES` uses **Tuesday**. **Filed R-ARCH-023, HIGH** (§4) — false negatives are A5's safe direction so this doesn't block, but the reported residue shape is materially wrong.

### 1d. R-ARCH-019/020/021 — reproduced by execution

Apple Mail split: reverting `_text_above_a_forward_separator` to `return None` breaks exactly **3** tests. Duplicate `"skrev"`: reintroducing breaks exactly **1**. Portuguese example removed from `CLIENT_ATTRIBUTION_LINES`: breaks exactly **1**. All match HANDOFF.

## §2 — Auditing the audit, and amendment A6

### 2a. Classification spot-checks (one per class) — all correct

D: `hit_count_per_rung` confirmed removed from `builder.build`'s signature, read from `certificate.hits_per_rung`. C: `Affordance.tool` confirmed closed `ToolName(StrEnum)`, 4 members. O: `MessageRow.position` confirmed — `FetchedIds` carries no per-id order, only A3's bound applies. S: `FetchedIds.*` confirmed deliberately no `ids` property/`__iter__` — sealed by design. I: `DispositionLedger._origins` etc. confirmed private dataclass fields, no envelope model references them. **"Observed but unsealed" is a real class**, not a dodge — six of seven prior instances were fixable and the audit fixed them; the remainder is genuine.

### 2b. The two audit-found instances (real, fixed) — and does the audit's own claim reproduce?

Confirmed by reintroduction (§3): `ThreadMember.thread_id`/`.position` were genuinely unchecked before this round; `hit_count_per_rung`'s *value* (not just its length) was never compared to anything before this round. Both check now. Looking for a live *ninth*: `Score.*`/`PoolBlock.*` (WS-08 unbuilt, no real values to compare); `NotIncludedSource.thread_id` (zero production construction sites — built only in one contract test expecting a `ValidationError`, so no live behaviour to be wrong yet). Everything else open is already named in HANDOFF's "what I did NOT fix." No live field-derivation miss found — but the audit's own **methodology** claim does not reproduce: running HANDOFF's published enumerator script verbatim gives **`TOTAL FIELDS: 173`**, not 187. `FetchedIds` (7 fields, the seal itself) and `DispositionCertificate` (7 fields) are plain Python classes — neither `BaseModel` nor `@dataclass` — so the script's own type checks silently skip both; their 14 fields are in HANDOFF's table by hand. Both rows check out accurate against source, so no field is actually misclassified — but "enumerated programmatically... cannot silently omit a field" is false as published: the script offered as the source of "187" produces 173. The same failure shape the round exists to catch, inside the audit itself. **Filed R-ARCH-024, MEDIUM** (§4) — rigor, not correctness; this is the process-level eighth instance.

### 2c. The three reasons field-level derivation can't close the class — sound, one overclaims

(1) Seal narrower than response: definitional, confirmed by reading `FetchedIds`. (2) `computed_field` serialises last: verified true on pydantic 2.13.5 — but a `@model_serializer` *can* reorder computed fields (built one, confirmed it), so "no mechanism exists" overclaims; the real cost is that a hand-written serializer is a second parallel structure that silently drops a field if `model_fields` changes without updating it — an instance of the same defect class this round is about, so the conclusion survives but should say "at a cost," not "impossible." (3) `mode="before"` reopens R-SEC-021: sound — that finding was exactly a raw-input shape-bound gap, and `before` validators see raw input while `after` sees typed attributes; `mode="after"` + `object.__setattr__` can fill a field without parsing raw input, but cannot remove the parameter (a caller can still override it), landing on the same "checked, not removed" pattern used everywhere else in the codebase. **Net: the argument holds.**

### 2f. Amendment A6 — verdict: **AMEND**, not accept or reject as written

**Accept the diagnosis**: class O is real, field-level derivation alone cannot close it, A1 alone doesn't make an in-process claim checkable.

**Reject "whole response" — a cheaper mechanism closes the same class.** Of A6's 20 target fields, only **2** (`Content.text`, `Content.source`) are mail text/payload; the other **18** are small typed scalars (a count, an index, a timestamp, an id). A **named-fields** widening of `FetchedIds`/`HitOrigin` (~6 new typed scalars, captured at observation time, as `thread_ids` already is) closes all 18 without a message body ever entering the ledger. The 2 text fields don't need this: `Content.text`'s own basis is "it *is* the payload; nothing to derive," and it already has a working mechanism (fenced with the response's nonce). A6 as written creates a **second, differently-governed copy** of text the fencing already protects, for no benefit.

**Retention, under OD-4 / SCOPE_CORRECTION A.3.** A.3 permits bodies "memory-only during normal execution," so A6 doesn't violate it on its face. But OD-4 records that an earlier at-rest buffer holding raw messages for debugging was ruled **unauthorised and deleted** (`EVALUATION_PLAN.md`, CONS-005) precisely because persisting raw content beyond the minimum necessary is rejected here, and the architecture elsewhere enforces this with types (`PersonalTrace` "has no field that can hold mail text at all"). A6's seal, living for a whole multi-rung `DispositionLedger`, is the same class of exposure growth — in memory not at rest, so not the same violation, but unjustified for 2 of its 20 fields.

**Recommend:** (a) named-scalar widening for the 18 non-text fields, excluding body/subject/text; (b) `Content.text`/`.source` stay out of scope, on the existing fencing mechanism; (c) any wider "observation" object, if still wanted, scoped to one request and R-SEC-reviewed against OD-4/A.3 first. `R-DISC.md` reached a compatible, distinct conclusion (A6 alone doesn't close fabrication without A1) — no contradiction.

## §3 — Reintroduction counts, verified by execution

| Item | Claimed | Reproduced |
|---|---|---|
| R-DISC-011 latch → `return self` | 5 | 5 ✓ |
| `stated_total` bound → `return self` | 1 | 1 ✓ |
| `ThreadMember` position / thread checks neutered (2 total) | 2 | 1+1 ✓ |
| `hit_count_per_rung` envelope check → stub | 2 | 2 ✓ |
| `hit_count_per_rung` builder emits zeros | 30 | 30 ✓ |
| Apple Mail split → `return None` | 3 | 3 ✓ |
| Duplicate `"skrev"` | 1 | 1 ✓ |
| Portuguese example removed | 1 | 1 ✓ |
| R-SEC-026 scope model reverted to `ast.walk` | 6 | 6 ✓ |
| R-SEC-027 mode-token gate removed | 6 | 6 ✓ |
| R-SEC-028 substring match restored (faithful revert†) | 4 | 4 ✓ |

† A naive `token in name.lower()` revert breaks 6 (also loses camelCase splitting — a different regression); word-splitting kept, joined-words substring-matched, reproduces exactly 4.

**10/10 matched exactly** — an improvement over rounds 5-6's mismeasurements. `MessageRow` regaining `thread_id` (claimed 2) not independently re-broken, but `test_disposition_invariant.py:1171` (`assert "thread_id" not in MessageRow.model_fields`) is consistent with the claim.

**2nd stated weakness (R-SEC-026's call-walker) — no bypass found.** Two probes beyond HANDOFF's three controls: a comprehension name that must *not* leak after the comprehension ends (`[os for os in range(3)]` then real `os.replace(a,b)` — caught), and a lambda default calling a write through a same-named parameter (`lambda os=os.replace(a,b): os` — caught, defaults evaluate in the enclosing scope). No false negative found.

## §4 — Findings

```
ID: R-ARCH-022 | Severity: BLOCKER | Rubric: WORK_ORDER Part 2 ("FPs on sender prose: zero...
gated"); A5 | Location: content/quotes.py:561-569
Reproduction: §1b — strip on two paragraphs, 2nd opening "Once the negotiations concluded, the
legal team wrote:", no quote chain
Expected: zero sender sentences removed; uncertainty via zero-sized Reduction
Actual: both paragraphs deleted `quoted`, ambiguous_lines=0 — no signal anything happened
Required fix: route `fragment.hidden` content through `_client_attribution_template` before
deleting, as `fragment.quoted` content already is
```
```
ID: R-ARCH-023 | Severity: HIGH | Rubric: none — measurement accuracy, A5 (reported not gated)
Location: content/quotes.py:204-219 (`_FIRST_PERSON_RE`)
Reproduction: §1c; template("On Mon, Aug 24, 2026 at 9:02 AM Dana Whitfield <d@x.com> wrote:")
→ None ("Mon" matches French "mon")
Expected: HANDOFF: residue is "both English attributions carrying no address"
Actual: addressed, correctly-shaped headers survive on weekday/pronoun collisions (en/de/nl/sv/fi)
Required fix: scope the first-person scan off calendar tokens already consumed by the date match
```
```
ID: R-ARCH-024 | Severity: MEDIUM | Rubric: none — audit methodology (AGENT_LOOP §7.1)
Location: ROUND_07/HANDOFF.md:34-48
Reproduction: run the published enumerator verbatim → 173, not 187
Expected: "enumerated programmatically... cannot silently omit a field"
Actual: FetchedIds/DispositionCertificate (14 fields) are plain classes the script can't see;
both hand-added to the table (and, on inspection, accurate)
Required fix: extend the enumerator to plain classes, or state these two were audited by hand
```

## Hollow-test check and execution record

Hollow-test: AST scan of `tests/*.py` for assertion-free `test_*` functions over-reported (a detection bug — `ast.dump` text doesn't contain the literal substring `"pytest.raises"`); manually re-read a sample in `test_envelope_contract.py`/`test_auth_and_config.py`/`test_disposition_invariant.py` and all are legitimate `pytest.raises(...)` checks with meaningful arguments, not tautologies. None found hollow in the files read; not an exhaustive sweep of all ~40 test files.

Commands: `uv sync`; `__file__` check; `ruff check`/`format --check`; `mypy`; `pytest -m "not network"` (775, twice); `python -m tools.guards`. Six files patched for reintroductions, each run against the full suite and restored+diffed clean before the next: `content/quotes.py` (×3), `envelope/response.py` (×3), `envelope/wire.py` (×2), `envelope/builder.py` (×1), `tools/guards/sweeps.py` (×3), `tests/fixtures/reply_chains.py` (×1). Two standalone corpora (`my_corpus.py`, `my_headers.py`) run from outside the tree against the installed package, never copied into `tests/`. `RELEASE_RUBRIC.md`/`FINDINGS_LEDGER.md`/`RUBRIC_TRANSITIONS.md` untouched.

## Per-criterion recommendations

| Criterion | Recommendation |
|---|---|
| A5 false-positive gate | **Not met.** R-ARCH-022 destroys sender text outside the one position HANDOFF's corpus tests. Round does not gate until fixed and re-measured across positions. |
| A5 false-negative reporting | Correct before relying on it — real residue is a locale/calendar collision (R-ARCH-023), ~3× the reported rate. |
| R-ARCH-019/020/021 | Confirmed closed, exact match. |
| Part 1 field audit | Classification sound throughout; conclusion holds under direct testing. Its own completeness claim doesn't (R-ARCH-024) — low severity, fix before re-citing "187, programmatic." |
| Amendment A6 | **Amend, don't adopt as written.** Diagnosis sound; mechanism too broad for 18/20 target fields, unneeded for the other 2. Narrow to named scalars, exclude body/text, scope to one request, route through R-SEC. |
| Part 3 (R-SEC-026/027/028) | Counts confirmed exactly. No false negative found in the shared call-walker. |
| Overall Round 7 gate | **Does not close** — one open BLOCKER (R-ARCH-022) against a criterion this round explicitly gates. Everything else checked verified correct. |

